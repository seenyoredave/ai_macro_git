"""Audited, retained private-equity market observations (separate from LP fund returns)."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pandas as pd

MARKET_CONTEXT_PATH = Path(__file__).resolve().parents[1] / "data/private_capital/market_context.csv"
FLOW_KEYS = ("deal_value", "exit_value", "fundraising")
VALUATION_KEYS = ("buyout_ev_ebitda", "buyout_ev_ebitda_sub1b", "buyout_ev_ebitda_1bplus")
REQUIRED = {
    "metric", "label", "geography", "period", "period_start", "period_end",
    "value", "unit", "precision", "count", "count_unit", "source",
    "source_url", "published_on", "definition",
}


def validate_market_context(frame: pd.DataFrame) -> pd.DataFrame:
    """Fail closed on incomplete, mixed-scope, duplicated or future observations."""
    if frame is None or not REQUIRED.issubset(frame.columns):
        raise ValueError("Private-equity market source has missing fields")
    if len(frame) < len(FLOW_KEYS) + len(VALUATION_KEYS):
        raise ValueError("Private-equity market source is incomplete")
    clean = frame.copy()
    for col in ("metric", "label", "geography", "period", "unit", "precision", "source", "source_url", "definition"):
        if clean[col].isna().any() or clean[col].astype(str).str.strip().eq("").any():
            raise ValueError(f"Private-equity market source has missing {col}")
        clean[col] = clean[col].astype(str).str.strip()
    if clean.duplicated(["metric", "geography", "period_end"]).any():
        raise ValueError("Private-equity market source has duplicated observations")
    if not clean["metric"].isin((*FLOW_KEYS, *VALUATION_KEYS)).all():
        raise ValueError("Private-equity market source has unknown metric")
    for col in ("period_start", "period_end", "published_on"):
        clean[col] = pd.to_datetime(clean[col], errors="coerce")
        if clean[col].isna().any():
            raise ValueError(f"Private-equity market source has invalid {col}")
    current = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    if (clean["period_start"] > clean["period_end"]).any() or (clean["period_end"] > current).any() or (clean["published_on"] > current).any():
        raise ValueError("Private-equity market dates are inconsistent or in the future")
    if (clean["published_on"] < clean["period_end"]).any():
        raise ValueError("Private-equity market report predates its covered period")
    clean["value"] = pd.to_numeric(clean["value"], errors="coerce")
    clean["count"] = pd.to_numeric(clean["count"], errors="coerce")
    if clean["value"].isna().any() or not np.isfinite(clean["value"]).all() or clean["value"].le(0).any():
        raise ValueError("Private-equity market values must be positive finite numbers")
    reported_counts = clean["count"].dropna()
    if reported_counts.lt(1).any() or not np.isfinite(reported_counts).all() or reported_counts.mod(1).ne(0).any():
        raise ValueError("Private-equity market counts must be positive integers")
    if not clean["source_url"].map(lambda u: urlparse(u).scheme == "https" and bool(urlparse(u).netloc)).all():
        raise ValueError("Private-equity market observations require HTTPS source links")
    is_flow = clean["metric"].isin(FLOW_KEYS)
    is_valuation = clean["metric"].isin(VALUATION_KEYS)
    if not clean.loc[is_flow, "geography"].eq("Global").all() or not clean.loc[is_valuation, "geography"].eq("United States").all():
        raise ValueError("Private-equity market geography differs from metric definition")
    if not clean.loc[is_flow, "unit"].eq("USD billions").all() or not clean.loc[is_valuation, "unit"].eq("EV/EBITDA multiple").all():
        raise ValueError("Private-equity market metric units differ from definitions")
    # Earlier KPMG global exit counts are not consistently disclosed; do not
    # invent a count to accompany a source-backed dollar value.
    count_required = clean["metric"].isin(("deal_value", "fundraising"))
    if clean.loc[count_required, "count"].isna().any() or clean.loc[is_valuation, "count"].notna().any():
        raise ValueError("Private-equity market count coverage differs from definitions")
    if clean.loc[is_flow, "count_unit"].isna().any() or clean.loc[is_flow, "count_unit"].astype(str).str.strip().eq("").any():
        raise ValueError("Private-equity market count labels are required")
    return clean.sort_values(["period_end", "metric"], kind="stable").reset_index(drop=True)


def load_pe_market_context(path: Path | str | None = None) -> pd.DataFrame:
    target = Path(path) if path is not None else MARKET_CONTEXT_PATH
    if not target.exists():
        return pd.DataFrame()
    return validate_market_context(pd.read_csv(target))


def build_pe_market_context(path: Path | str | None = None) -> dict:
    """Pick the most recent *complete* observation set by geography and period."""
    frame = load_pe_market_context(path)
    if frame.empty:
        return {"observations": frame, "flows": {}, "previous_flows": {}, "flow_yoy_pct": {}, "valuations": {}}
    def latest_complete(keys, geography):
        group = frame.loc[frame["metric"].isin(keys) & frame["geography"].eq(geography)]
        for period_end in sorted(group["period_end"].unique(), reverse=True):
            same_period = group.loc[group["period_end"].eq(period_end)]
            if (set(same_period["metric"]) == set(keys)
                    and same_period["period_start"].nunique() == 1
                    and same_period["period"].nunique() == 1):
                return {row["metric"]: row.to_dict() for _, row in same_period.iterrows()}
        return {}
    flows = latest_complete(FLOW_KEYS, "Global")
    prior_flows = {}
    if flows:
        period_end = next(iter(flows.values()))["period_end"]
        # H1-versus-H1 is valid; H1-versus-FY or different geography is not.
        prior = frame.loc[
            frame["metric"].isin(FLOW_KEYS)
            & frame["geography"].eq("Global")
            & frame["period_end"].eq(period_end - pd.DateOffset(years=1))
        ]
        if (set(prior["metric"]) == set(FLOW_KEYS)
                and prior["period_start"].nunique() == 1
                and prior["period"].nunique() == 1
                and prior.iloc[0]["period_start"] == next(iter(flows.values()))["period_start"] - pd.DateOffset(years=1)):
            prior_flows = {row["metric"]: row.to_dict() for _, row in prior.iterrows()}
    changes = {}
    if prior_flows:
        for key in FLOW_KEYS:
            old = float(prior_flows[key]["value"])
            new = float(flows[key]["value"])
            changes[key] = (new / old - 1) * 100 if old > 0 else float("nan")
    return {
        "observations": frame,
        "flows": flows,
        "previous_flows": prior_flows,
        "flow_yoy_pct": changes,
        "valuations": latest_complete(VALUATION_KEYS, "United States"),
    }
