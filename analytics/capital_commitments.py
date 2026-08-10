from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPONENTS_PATH = PROJECT_ROOT / "data" / "capital_commitment_components.csv"
DEFAULT_LEDGER_PATH = PROJECT_ROOT / "data" / "capital_commitments.csv"

FORWARD_CATEGORIES = {
    "Uncommenced Leases",
    "Purchase or Contractual Commitments",
}
CONTINGENT_CATEGORY = "Contingent Exposure"

COMPONENT_COLUMNS = [
    "Ticker",
    "Component ID",
    "Category",
    "Value",
    "As Of Date",
    "Filing Date",
    "Source URL",
    "Scope",
    "Included in Forward Commitments",
    "Carried Forward",
    "Notes",
]

LEDGER_COLUMNS = [
    "Ticker",
    "As Of Date",
    "Filing Date",
    "Uncommenced Leases",
    "Purchase or Contractual Commitments",
    "Contingent Exposure",
    "Source URL",
    "Notes",
]


def _as_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    normalized = series.astype("string").str.strip().str.casefold()
    return normalized.isin({"true", "1", "yes", "y"})


def normalize_commitment_components(
    frame: pd.DataFrame | None,
    *,
    as_of_date=None,
) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=COMPONENT_COLUMNS)

    missing = [column for column in COMPONENT_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Capital commitment component ledger missing columns: {missing}")

    out = frame.copy()
    out["Ticker"] = out["Ticker"].astype(str).str.upper().str.strip()
    out["Component ID"] = out["Component ID"].astype(str).str.strip()
    out["Category"] = out["Category"].astype(str).str.strip()
    out["Value"] = pd.to_numeric(out["Value"], errors="coerce")
    out["As Of Date"] = pd.to_datetime(out["As Of Date"], errors="coerce", format="mixed")
    out["Filing Date"] = pd.to_datetime(out["Filing Date"], errors="coerce", format="mixed")
    out["Included in Forward Commitments"] = _as_bool(out["Included in Forward Commitments"])
    out["Carried Forward"] = _as_bool(out["Carried Forward"])
    out["Available Date"] = out["Filing Date"].fillna(out["As Of Date"])

    valid_categories = FORWARD_CATEGORIES | {CONTINGENT_CATEGORY}
    invalid = sorted(set(out.loc[~out["Category"].isin(valid_categories), "Category"]))
    if invalid:
        raise ValueError(f"Unsupported capital commitment categories: {invalid}")

    invalid_forward = out[
        out["Included in Forward Commitments"] & ~out["Category"].isin(FORWARD_CATEGORIES)
    ]
    if not invalid_forward.empty:
        raise ValueError("Only uncommenced leases and purchase/contractual commitments may enter Forward Commitments.")

    if as_of_date is not None:
        cutoff = pd.to_datetime(as_of_date, errors="coerce")
        if pd.isna(cutoff):
            raise ValueError(f"Invalid capital-commitment as_of_date: {as_of_date}")
        out = out[out["Available Date"].notna() & (out["Available Date"] <= cutoff)].copy()

    out = out.dropna(subset=["Ticker", "Component ID", "Category", "Value", "Available Date"])
    out = out[out["Value"] >= 0].copy()
    return (
        out.sort_values(
            ["Ticker", "Component ID", "Available Date", "As Of Date"],
            kind="stable",
        )
        .drop_duplicates(["Ticker", "Component ID"], keep="last")
        .reset_index(drop=True)
    )


def load_commitment_components(path=None, *, as_of_date=None) -> pd.DataFrame:
    source = Path(path) if path is not None else DEFAULT_COMPONENTS_PATH
    if not source.exists() or source.stat().st_size == 0:
        return pd.DataFrame(columns=COMPONENT_COLUMNS)
    return normalize_commitment_components(pd.read_csv(source), as_of_date=as_of_date)


def _join_distinct(values) -> str:
    items = []
    for value in values:
        text = str(value or "").strip()
        if text and text.casefold() != "nan" and text not in items:
            items.append(text)
    return " | ".join(items)


def aggregate_commitment_components(
    frame: pd.DataFrame | None,
    *,
    as_of_date=None,
) -> pd.DataFrame:
    components = normalize_commitment_components(frame, as_of_date=as_of_date)
    if components.empty:
        return pd.DataFrame(columns=LEDGER_COLUMNS)

    rows = []
    for ticker, company in components.groupby("Ticker", sort=True):
        forward = company[company["Included in Forward Commitments"]].copy()
        contingent = company[company["Category"].eq(CONTINGENT_CATEGORY)].copy()

        def category_total(category: str):
            values = pd.to_numeric(
                forward.loc[forward["Category"].eq(category), "Value"], errors="coerce"
            ).dropna()
            return float(values.sum()) if not values.empty else np.nan

        contingent_values = pd.to_numeric(contingent["Value"], errors="coerce").dropna()
        carried = company[company["Carried Forward"]]
        scope_summary = _join_distinct(company["Scope"])
        carried_text = _join_distinct(carried["Component ID"])
        note_parts = [f"Component ledger: {len(company)} reviewed components."]
        if scope_summary:
            note_parts.append(f"Scope: {scope_summary}.")
        if carried_text:
            note_parts.append(f"Carried forward components: {carried_text}.")
        note_parts.append(
            "Forward Commitments include only uncommenced leases and purchase or contractual commitments; contingent exposure remains separate."
        )

        rows.append(
            {
                "Ticker": ticker,
                "As Of Date": company["As Of Date"].max(),
                "Filing Date": company["Filing Date"].max(),
                "Uncommenced Leases": category_total("Uncommenced Leases"),
                "Purchase or Contractual Commitments": category_total(
                    "Purchase or Contractual Commitments"
                ),
                "Contingent Exposure": (
                    float(contingent_values.sum()) if not contingent_values.empty else np.nan
                ),
                "Source URL": _join_distinct(company["Source URL"]),
                "Notes": " ".join(note_parts),
            }
        )

    return pd.DataFrame(rows, columns=LEDGER_COLUMNS).sort_values("Ticker").reset_index(drop=True)


def build_current_commitment_ledger(*, components_path=None, as_of_date=None) -> pd.DataFrame:
    return aggregate_commitment_components(
        load_commitment_components(components_path, as_of_date=as_of_date),
        as_of_date=as_of_date,
    )
