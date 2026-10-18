"""Public-pension private equity cash-flow returns from complete disclosed cohorts."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "private_capital" / "fund_performance.csv"
METADATA_PATH = PROJECT_ROOT / "data" / "private_capital" / "metadata.json"
WSIB_DATA_PATH = PROJECT_ROOT / "data" / "private_capital" / "wsib_fund_performance.csv"
WSIB_METADATA_PATH = PROJECT_ROOT / "data" / "private_capital" / "wsib_metadata.json"
CALPERS_DATA_PATH = PROJECT_ROOT / "data" / "private_capital" / "calpers_fund_performance.csv"
CALPERS_METADATA_PATH = PROJECT_ROOT / "data" / "private_capital" / "calpers_metadata.json"


def validate_private_capital_snapshot(frame: pd.DataFrame, *, expected_date=None) -> pd.Timestamp:
    """Reject incomplete automatic snapshots before saving or selecting them."""
    required = {"Manager", "Fund", "Vintage", "Exposure Tier", "Capital Committed",
                "Paid In Capital", "Distributions", "NAV", "Net IRR", "Source As Of"}
    if not required.issubset(frame.columns) or len(frame) < 12:
        raise ValueError("Private-fund snapshot is incomplete")
    if frame["Manager"].nunique() < 4 or frame["Fund"].duplicated().any():
        raise ValueError("Private-fund snapshot has insufficient managers or duplicate funds")
    dates = pd.to_datetime(frame["Source As Of"], errors="coerce")
    if dates.isna().any() or dates.nunique() != 1:
        raise ValueError("Private-fund snapshot must have one observation date")
    as_of = dates.iloc[0]
    if as_of > pd.Timestamp.now(tz="UTC").tz_localize(None).normalize():
        raise ValueError("Private-fund snapshot has a future observation date")
    if expected_date is not None and as_of != pd.Timestamp(expected_date):
        raise ValueError("Private-fund records and metadata dates disagree")
    for column in ("Vintage", "Capital Committed", "Paid In Capital", "Distributions", "NAV"):
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.isna().any() or not np.isfinite(values).all():
            raise ValueError(f"Private-fund snapshot has invalid {column}")
        if column == "Vintage":
            if not (values.ge(2012) & values.le(as_of.year) & values.mod(1).eq(0)).all():
                raise ValueError("Private-fund snapshot has invalid investment years")
        elif values.lt(0).any() or (column == "Paid In Capital" and values.le(0).any()):
            raise ValueError(f"Private-fund snapshot has invalid {column}")
    if frame[["Manager", "Fund", "Exposure Tier"]].isna().any().any():
        raise ValueError("Private-fund snapshot has missing fund identifiers")
    return as_of


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame.get(column), errors="coerce").replace([np.inf, -np.inf], np.nan)


COHORT_SCOPE = "broad_pe"
MIN_COHORT_FUNDS = 100
MIN_COHORT_MANAGERS = 15


def validate_broad_pe_snapshot(frame: pd.DataFrame, *, metadata: dict) -> pd.Timestamp:
    """Accept only sufficiently broad, explicitly classified pension PE holdings."""
    if metadata.get("cohort_scope") != COHORT_SCOPE:
        raise ValueError("Private-equity source is an old manager-selected cohort")
    as_of = validate_private_capital_snapshot(frame, expected_date=metadata["source_as_of"])
    if len(frame) < MIN_COHORT_FUNDS or frame["Manager"].nunique() < MIN_COHORT_MANAGERS:
        raise ValueError("Private-equity source has insufficient broad-portfolio coverage")
    return as_of


def _selected_paths() -> tuple[Path | None, Path | None]:
    """Prefer the newest verified broad pension-PE cohort, never a technology subset.

    Same-date priority: CalSTRS retained, WSIB, then CalPERS; no cross-LP pooling.
    """
    selected: tuple[Path | None, Path | None] = (None, None)
    latest = pd.NaT
    for data_path, metadata_path in (
        (DATA_PATH, METADATA_PATH),
        (WSIB_DATA_PATH, WSIB_METADATA_PATH),
        (CALPERS_DATA_PATH, CALPERS_METADATA_PATH),
    ):
        try:
            metadata = json.loads(metadata_path.read_text())
            frame = pd.read_csv(data_path)
            as_of = validate_broad_pe_snapshot(frame, metadata=metadata)
            if pd.isna(latest) or as_of > latest:
                selected, latest = (data_path, metadata_path), as_of
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue
    return selected


def load_private_capital_funds(*, paths=None) -> pd.DataFrame:
    """Load the retained public-LP cohort and derive comparable multiples."""
    selected_data, _ = paths or _selected_paths()
    if selected_data is None or not selected_data.exists():
        return pd.DataFrame()
    frame = pd.read_csv(selected_data)
    required = {
        "Manager", "Fund", "Vintage", "Exposure Tier", "Paid In Capital",
        "Distributions", "NAV", "Net IRR", "Source As Of",
    }
    if not required.issubset(frame.columns):
        return pd.DataFrame()

    for column in ("Vintage", "Capital Committed", "Paid In Capital", "Distributions", "NAV", "Net IRR"):
        frame[column] = _numeric(frame, column)
    frame["Source As Of"] = pd.to_datetime(frame["Source As Of"], errors="coerce")
    frame = frame.loc[frame["Paid In Capital"].gt(0) & frame["Vintage"].notna()].copy()
    if frame.empty:
        return frame

    paid_in = frame["Paid In Capital"]
    frame["DPI"] = frame["Distributions"] / paid_in
    frame["RVPI"] = frame["NAV"] / paid_in
    frame["TVPI"] = (frame["Distributions"] + frame["NAV"]) / paid_in
    denominator = frame["Distributions"] + frame["NAV"]
    frame["Realized Share"] = np.where(denominator.gt(0), frame["Distributions"] / denominator, np.nan)
    source_year = frame["Source As Of"].dt.year
    frame["Fund Age"] = source_year - frame["Vintage"]
    frame["Maturity"] = np.select(
        [frame["Fund Age"].ge(5), frame["Fund Age"].ge(3)],
        ["Mature (5y+)", "Developing (3-4y)"],
        default="Young (0-2y)",
    )
    return frame.sort_values(["Vintage", "Manager", "Fund"], ascending=[False, True, True], kind="stable").reset_index(drop=True)


def load_private_capital_metadata(*, paths=None) -> dict:
    selected_data, selected_metadata = paths or _selected_paths()
    if selected_metadata is None or not selected_metadata.exists():
        return {}
    try:
        metadata = json.loads(selected_metadata.read_text())
        metadata.setdefault("source_short", "WSIB" if selected_data == WSIB_DATA_PATH else "CalPERS" if selected_data == CALPERS_DATA_PATH else "CalSTRS")
        return metadata
    except (OSError, json.JSONDecodeError):
        return {}


def _pooled_metrics(frame: pd.DataFrame) -> dict:
    if frame is None or frame.empty:
        return {}
    paid_in = float(_numeric(frame, "Paid In Capital").sum())
    distributed = float(_numeric(frame, "Distributions").sum())
    nav = float(_numeric(frame, "NAV").sum())
    total_value = distributed + nav
    if paid_in <= 0:
        return {}
    irr = _numeric(frame, "Net IRR").dropna()
    return {
        "fund_count": int(len(frame)),
        "manager_count": int(frame["Manager"].nunique()),
        "paid_in": paid_in,
        "distributed": distributed,
        "nav": nav,
        "dpi": distributed / paid_in,
        "rvpi": nav / paid_in,
        "tvpi": total_value / paid_in,
        "realized_share": distributed / total_value if total_value > 0 else np.nan,
        "median_net_irr": float(irr.median()) if not irr.empty else np.nan,
    }


COHORT_ORDER = ("Mature (5y+)", "Developing (3-4y)", "Young (0-2y)")


def build_private_capital_cohorts(funds: pd.DataFrame) -> list[dict]:
    """Group the same LP positions as the scatterplot; pool dollar cash flows."""
    if funds is None or funds.empty:
        return []
    groups = []
    for label in COHORT_ORDER:
        subset = funds.loc[funds["Maturity"].eq(label)]
        metrics = _pooled_metrics(subset)
        if metrics:
            groups.append({"maturity": label, **metrics})
    all_metrics = _pooled_metrics(funds)
    if all_metrics:
        groups.append({"maturity": "All holdings", **all_metrics})
    return groups


def build_private_capital_realization() -> dict:
    """Return fund detail, comparable maturity cohorts, and audit metadata."""
    paths = _selected_paths()
    funds = load_private_capital_funds(paths=paths)
    metadata = load_private_capital_metadata(paths=paths)
    if funds.empty:
        return {"funds": funds, "mature_funds": funds, "metrics": {}, "all_metrics": {}, "cohorts": [], "metadata": metadata}

    mature = funds.loc[funds["Fund Age"].ge(5)].copy()
    return {
        "funds": funds,
        "mature_funds": mature,
        "metrics": _pooled_metrics(mature),
        "all_metrics": _pooled_metrics(funds),
        "cohorts": build_private_capital_cohorts(funds),
        "metadata": metadata,
        "as_of": funds["Source As Of"].max(),
    }
