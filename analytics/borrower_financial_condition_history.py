"""Historical Borrower Financial Condition reconstruction utilities.

The historical series is stored separately from the live macro archive.  This
keeps sparse annual/quarterly reconstruction rows from polluting the general
macro table while allowing the dashboard to display one continuous series.

No historical value is manufactured at runtime.  The companion CLI in
``tools/backfill_borrower_financial_condition.py`` downloads SEC data, writes the retained raw
inputs, and produces the accepted history file.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HISTORY_PATH = PROJECT_ROOT / "data" / "borrower_financial_condition_history.csv"
DEFAULT_FUNDAMENTALS_PATH = (
    PROJECT_ROOT / "data" / "borrower_financial_condition_fundamentals_history.csv"
)
DEFAULT_COMMITMENTS_HISTORY_PATH = (
    PROJECT_ROOT / "data" / "capital_commitments_history.csv"
)
DEFAULT_REVIEW_PATH = PROJECT_ROOT / "data" / "capital_commitments_review.csv"
DEFAULT_AUDIT_PATH = PROJECT_ROOT / "data" / "borrower_financial_condition_backfill_audit.csv"

BORROWER_FINANCIAL_CONDITION_CIKS = {
    "MSFT": "0000789019",
    "AMZN": "0001018724",
    "GOOG": "0001652044",
    "META": "0001326801",
    "ORCL": "0001341439",
    "NVDA": "0001045810",
    "AMD": "0000002488",
    "IREN": "0001878848",
    "SMCI": "0001375365",
    "ANET": "0001596532",
}

HISTORY_COLUMNS = [
    "Date",
    "Observation Frequency",
    "Borrower Financial Condition",
    "Borrower Cash Flow Strain",
    "Borrower Debt Capacity Strain",
    "Borrower Committed Burden",
    "Borrower Contingent Exposure",
    "FCF Margin",
    "Reinvestment Ratio",
    "Positive EBITDA Net Debt/EBITDA",
    "Negative EBITDA Net Debt/Revenue",
    "Committed Burden Ratio",
    "Contingent Burden Ratio",
    "Borrower Financial Condition Version",
    "Valid Components",
    "Component Coverage",
    "Cohort Companies",
    "Target Cohort Size",
    "Financial Companies",
    "Commitment Companies",
    "Contingent Companies",
    "Latest Financial Filing Date",
    "Latest Commitment Filing Date",
    "Cohort Tickers",
    "Commitment Tickers",
    "Contingent Tickers",
    "Backfill Status",
]

FUNDAMENTAL_COLUMNS = [
    "Date",
    "Observation Frequency",
    "Ticker",
    "Revenue",
    "Operating Cash Flow",
    "CapEx",
    "Free Cash Flow",
    "EBITDA",
    "Total Debt",
    "Cash",
    "Net Debt",
    "Financial Period End",
    "Financial Filing Date",
    "Flow Method",
    "Revenue Quarters",
    "OCF Quarters",
    "CapEx Quarters",
    "EBITDA Quarters",
    "Source URL",
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
    "Extraction Confidence",
    "Extraction Status",
]

REVIEW_COLUMNS = [
    "Ticker",
    "As Of Date",
    "Filing Date",
    "Form",
    "Category",
    "Amount",
    "Confidence",
    "Accepted",
    "Source URL",
    "Label",
    "Excerpt",
    "Method",
]


FLOW_TAG_ALIASES: Mapping[str, Sequence[str]] = {
    "Revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "Revenues",
        "SalesRevenueGoodsNet",
    ),
    "Operating Cash Flow": (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    "CapEx": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsForAdditionsToPropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ),
    "Operating Income": (
        "OperatingIncomeLoss",
    ),
    "D&A": (
        "DepreciationDepletionAndAmortization",
        "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
        "DepreciationAndAmortization",
        "Depreciation",
    ),
}

DEBT_GROUPS: Sequence[Sequence[str]] = (
    (
        "LongTermDebtAndFinanceLeaseObligationsCurrent",
        "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
    ),
    (
        "LongTermDebtCurrent",
        "LongTermDebtNoncurrent",
        "ShortTermBorrowings",
    ),
    (
        "DebtCurrent",
        "DebtNoncurrent",
    ),
    (
        "LongTermDebt",
        "ShortTermBorrowings",
    ),
    (
        "LongTermDebtAndCapitalLeaseObligations",
        "ShortTermBorrowings",
    ),
)

CASH_GROUPS: Sequence[Sequence[str]] = (
    ("CashCashEquivalentsAndShortTermInvestments",),
    ("CashAndCashEquivalentsAtCarryingValue", "ShortTermInvestments"),
    (
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "ShortTermInvestments",
    ),
    ("CashAndCashEquivalentsAtCarryingValue",),
)


@dataclass(frozen=True)
class FactValue:
    value: float
    period_end: pd.Timestamp | pd.NaT
    filed: pd.Timestamp | pd.NaT
    method: str
    quarters: int = 0
    tags: tuple[str, ...] = ()


def historical_observation_dates(
    *,
    annual_start: int = 2014,
    annual_end: int = 2024,
    quarterly_start: str | date = "2025-03-31",
    end_date: str | date = "2026-06-13",
) -> list[tuple[pd.Timestamp, str]]:
    """Return the agreed annual history and quarterly bridge dates."""
    observations: list[tuple[pd.Timestamp, str]] = []
    for year in range(int(annual_start), int(annual_end) + 1):
        observations.append((pd.Timestamp(year=year, month=12, day=31), "Historical Annual"))

    start = pd.Timestamp(quarterly_start).normalize()
    end = pd.Timestamp(end_date).normalize()
    quarter_ends = pd.date_range(start=start, end=end, freq="QE")
    for value in quarter_ends:
        observations.append((value.normalize(), "Quarterly Bridge"))

    if not observations or observations[-1][0] < end:
        observations.append((end, "Quarterly Bridge"))

    unique = {(stamp.normalize(), label) for stamp, label in observations if stamp <= end}
    return sorted(unique, key=lambda item: item[0])


def _empty_frame(columns: Sequence[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=list(columns))


def _read_csv(path: Path, columns: Sequence[str]) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return _empty_frame(columns)
    try:
        frame = pd.read_csv(path)
    except (ValueError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return _empty_frame(columns)
    for column in columns:
        if column not in frame.columns:
            frame[column] = np.nan
    return frame


def load_borrower_financial_condition_backfill(path: str | Path | None = None) -> pd.DataFrame:
    frame = _read_csv(Path(path) if path else DEFAULT_HISTORY_PATH, HISTORY_COLUMNS)
    if frame.empty:
        return frame
    frame = frame.copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce").dt.date.astype("string")
    frame = frame.loc[frame["Date"].notna()].copy()
    for column in [
        "Borrower Financial Condition",
        "Borrower Cash Flow Strain",
        "Borrower Debt Capacity Strain",
        "Borrower Committed Burden",
        "Borrower Contingent Exposure",
        "Component Coverage",
    ]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.sort_values("Date", kind="stable").reset_index(drop=True)


def combine_borrower_financial_condition_history(
    live_macro_history: pd.DataFrame | None,
    backfill_history: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Combine accepted backfill rows with live archive rows.

    Live rows win on duplicate dates.  Only Borrower Financial Condition fields are carried
    into this dedicated frame; unrelated macro columns are intentionally not
    manufactured for historical dates.
    """
    backfill = (
        load_borrower_financial_condition_backfill()
        if backfill_history is None
        else backfill_history.copy()
    )
    live = live_macro_history.copy() if isinstance(live_macro_history, pd.DataFrame) else pd.DataFrame()

    desired = [
        "Date",
        "Borrower Financial Condition",
        "Borrower Cash Flow Strain",
        "Borrower Debt Capacity Strain",
        "Borrower Committed Burden",
        "Borrower Contingent Exposure",
        "Borrower Financial Condition Version",
        "Observation Frequency",
        "Valid Components",
        "Component Coverage",
        "Backfill Status",
    ]

    frames = []
    if not backfill.empty:
        for column in desired:
            if column not in backfill.columns:
                backfill[column] = np.nan
        backfill["_source_priority"] = 0
        frames.append(backfill[desired + ["_source_priority"]])

    if not live.empty and {"Date", "Borrower Financial Condition"}.issubset(live.columns):
        live = live.copy()
        # Early archives used the previous label even after the debt-capacity
        # branch was introduced.  Preserve the old column and only use it as a
        # compatibility fallback when the explicit current field is absent.
        if "Borrower Debt Capacity Strain" not in live.columns:
            live["Borrower Debt Capacity Strain"] = np.nan
        if "Borrower Book Leverage" in live.columns:
            current_version = live.get(
                "Borrower Financial Condition Version", pd.Series(index=live.index, dtype=object)
            ).astype(str).eq("3.0")
            missing = live["Borrower Debt Capacity Strain"].isna() & current_version
            live.loc[missing, "Borrower Debt Capacity Strain"] = pd.to_numeric(
                live.loc[missing, "Borrower Book Leverage"], errors="coerce"
            )
        for column in desired:
            if column not in live.columns:
                live[column] = np.nan
        live["_source_priority"] = 1
        frames.append(live[desired + ["_source_priority"]])

    if not frames:
        return _empty_frame(desired)

    combined = pd.concat(frames, ignore_index=True, sort=False)
    combined["Date"] = pd.to_datetime(combined["Date"], errors="coerce")
    combined = combined.loc[combined["Date"].notna()].copy()
    combined = (
        combined.sort_values(["Date", "_source_priority"], kind="stable")
        .drop_duplicates("Date", keep="last")
        .drop(columns="_source_priority")
        .reset_index(drop=True)
    )
    combined["Date"] = combined["Date"].dt.date.map(lambda value: value.isoformat())
    return combined


def _unit_records(companyfacts: Mapping, tag: str) -> list[dict]:
    concept = (
        ((companyfacts or {}).get("facts", {}) or {}).get("us-gaap", {}) or {}
    ).get(tag, {}) or {}
    units = concept.get("units", {}) or {}
    records: list[dict] = []
    for unit_name, entries in units.items():
        if unit_name not in {"USD", "USD/shares", "pure"}:
            continue
        for entry in entries or []:
            payload = dict(entry)
            payload["_tag"] = tag
            payload["_unit"] = unit_name
            records.append(payload)
    return records


def _fact_frame(
    companyfacts: Mapping,
    tags: Iterable[str],
    cutoff: str | date | pd.Timestamp,
    *,
    duration: bool,
) -> pd.DataFrame:
    rows: list[dict] = []
    priorities = {tag: index for index, tag in enumerate(tags)}
    cutoff_ts = pd.Timestamp(cutoff).normalize()
    for tag in tags:
        for record in _unit_records(companyfacts, tag):
            record["_priority"] = priorities[tag]
            rows.append(record)
    if not rows:
        return pd.DataFrame()

    frame = pd.DataFrame(rows)
    frame["filed"] = pd.to_datetime(frame.get("filed"), errors="coerce")
    frame["end"] = pd.to_datetime(frame.get("end"), errors="coerce")
    frame["start"] = pd.to_datetime(frame.get("start"), errors="coerce")
    frame["val"] = pd.to_numeric(frame.get("val"), errors="coerce")
    frame["form"] = frame.get("form", "").astype(str)
    valid_forms = frame["form"].str.startswith(("10-K", "10-Q", "20-F", "40-F"))
    mask = (
        valid_forms
        & frame["filed"].notna()
        & (frame["filed"] <= cutoff_ts)
        & frame["end"].notna()
        & frame["val"].notna()
        & np.isfinite(frame["val"])
    )
    if duration:
        mask &= frame["start"].notna()
    frame = frame.loc[mask].copy()
    if frame.empty:
        return frame

    if duration:
        frame["days"] = (frame["end"] - frame["start"]).dt.days + 1
        frame = frame.loc[frame["days"].between(45, 430)].copy()

    # For each exact period, use the best-standardized tag and latest fact that
    # was public by the observation date.  This handles amendments without
    # allowing later filings to leak into earlier snapshots.
    keys = ["start", "end"] if duration else ["end"]
    frame = (
        frame.sort_values(
            keys + ["_priority", "filed"],
            ascending=[True] * len(keys) + [True, False],
            kind="stable",
        )
        .groupby(keys, dropna=False, as_index=False)
        .head(1)
        .sort_values("end", kind="stable")
        .reset_index(drop=True)
    )
    return frame


def _discrete_quarters(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert SEC duration facts into best-effort discrete fiscal quarters."""
    columns = ["start", "end", "value", "filed", "tag", "method"]
    if frame is None or frame.empty:
        return pd.DataFrame(columns=columns)

    direct = frame.loc[frame["days"].between(60, 125)].copy()
    direct["value"] = direct["val"]
    direct["tag"] = direct["_tag"]
    direct["method"] = "Direct quarter"
    direct = (
        direct.assign(_distance=(direct["days"] - 91).abs())
        .sort_values(["end", "_distance", "filed"], kind="stable")
        .groupby("end", as_index=False)
        .head(1)
    )

    derived_rows: list[dict] = []
    # Cumulative Q2/Q3/FY facts share the same fiscal-period start as Q1.
    # Include the Q1 fact in each start-date chain so Q2 can be obtained by
    # subtraction; standalone later quarters normally have different starts
    # and therefore remain isolated.
    cumulative = frame.copy()
    for start, group in cumulative.groupby("start", dropna=True):
        group = group.sort_values("end", kind="stable")
        previous = None
        for _, row in group.iterrows():
            if previous is not None and row["end"] > previous["end"]:
                value = float(row["val"]) - float(previous["val"])
                elapsed = int((row["end"] - previous["end"]).days)
                if 55 <= elapsed <= 130 and np.isfinite(value):
                    derived_rows.append(
                        {
                            "start": previous["end"] + pd.Timedelta(days=1),
                            "end": row["end"],
                            "value": value,
                            "filed": max(row["filed"], previous["filed"]),
                            "tag": row["_tag"],
                            "method": "Derived from cumulative SEC facts",
                        }
                    )
            previous = row

    derived = pd.DataFrame(derived_rows, columns=columns)
    combined = pd.concat([direct[columns], derived], ignore_index=True, sort=False)
    if combined.empty:
        return combined
    # Direct quarterly disclosures are preferred over subtraction-derived data.
    combined["_method_priority"] = combined["method"].map(
        {"Direct quarter": 0, "Derived from cumulative SEC facts": 1}
    ).fillna(9)
    return (
        combined.sort_values(["end", "_method_priority", "filed"], kind="stable")
        .drop_duplicates("end", keep="first")
        .drop(columns="_method_priority")
        .reset_index(drop=True)
    )


def ttm_fact(
    companyfacts: Mapping,
    tags: Sequence[str],
    cutoff: str | date | pd.Timestamp,
) -> FactValue:
    frame = _fact_frame(companyfacts, tags, cutoff, duration=True)
    if frame.empty:
        return FactValue(np.nan, pd.NaT, pd.NaT, "Unavailable")

    quarters = _discrete_quarters(frame)
    if len(quarters) >= 4:
        latest = quarters.tail(4).copy()
        spans = latest["end"].sort_values().diff().dt.days.dropna()
        if spans.empty or bool(spans.between(55, 140).all()):
            return FactValue(
                float(latest["value"].sum()),
                latest["end"].max(),
                latest["filed"].max(),
                "Trailing four fiscal quarters",
                quarters=4,
                tags=tuple(sorted(set(latest["tag"].astype(str)))),
            )

    annual = frame.loc[frame["days"].between(325, 405)].copy()
    if not annual.empty:
        row = annual.sort_values(["end", "filed"], kind="stable").iloc[-1]
        return FactValue(
            float(row["val"]),
            row["end"],
            row["filed"],
            "Latest annual SEC fact",
            quarters=0,
            tags=(str(row["_tag"]),),
        )

    return FactValue(np.nan, pd.NaT, pd.NaT, "Unavailable")


def _instant_series(
    companyfacts: Mapping,
    tag: str,
    cutoff: str | date | pd.Timestamp,
) -> pd.DataFrame:
    frame = _fact_frame(companyfacts, (tag,), cutoff, duration=False)
    if frame.empty:
        return frame
    return frame[["end", "filed", "val", "_tag"]].copy()


def instant_group_fact(
    companyfacts: Mapping,
    groups: Sequence[Sequence[str]],
    cutoff: str | date | pd.Timestamp,
) -> FactValue:
    for group in groups:
        series_by_tag = {
            tag: _instant_series(companyfacts, tag, cutoff)
            for tag in group
        }
        available = {tag: frame for tag, frame in series_by_tag.items() if not frame.empty}
        if not available:
            continue

        all_ends = sorted(
            set().union(*(set(frame["end"].dropna()) for frame in available.values())),
            reverse=True,
        )
        for period_end in all_ends:
            values = []
            filed_dates = []
            used_tags = []
            for tag in group:
                frame = available.get(tag)
                if frame is None:
                    continue
                row = frame.loc[frame["end"] == period_end]
                if row.empty:
                    continue
                chosen = row.sort_values("filed", kind="stable").iloc[-1]
                values.append(float(chosen["val"]))
                filed_dates.append(chosen["filed"])
                used_tags.append(tag)
            if values:
                return FactValue(
                    float(sum(values)),
                    pd.Timestamp(period_end),
                    max(filed_dates),
                    "Latest SEC balance-sheet fact",
                    tags=tuple(used_tags),
                )
    return FactValue(np.nan, pd.NaT, pd.NaT, "Unavailable")


def build_company_snapshot(
    ticker: str,
    companyfacts: Mapping,
    cutoff: str | date | pd.Timestamp,
    observation_frequency: str,
) -> dict:
    cutoff_ts = pd.Timestamp(cutoff).normalize()
    revenue = ttm_fact(companyfacts, FLOW_TAG_ALIASES["Revenue"], cutoff_ts)
    ocf = ttm_fact(companyfacts, FLOW_TAG_ALIASES["Operating Cash Flow"], cutoff_ts)
    capex = ttm_fact(companyfacts, FLOW_TAG_ALIASES["CapEx"], cutoff_ts)
    operating_income = ttm_fact(
        companyfacts, FLOW_TAG_ALIASES["Operating Income"], cutoff_ts
    )
    depreciation = ttm_fact(companyfacts, FLOW_TAG_ALIASES["D&A"], cutoff_ts)
    debt = instant_group_fact(companyfacts, DEBT_GROUPS, cutoff_ts)
    cash = instant_group_fact(companyfacts, CASH_GROUPS, cutoff_ts)

    capex_value = abs(capex.value) if pd.notna(capex.value) else np.nan
    fcf = (
        float(ocf.value) - float(capex_value)
        if pd.notna(ocf.value) and pd.notna(capex_value)
        else np.nan
    )
    ebitda = (
        float(operating_income.value) + abs(float(depreciation.value))
        if pd.notna(operating_income.value) and pd.notna(depreciation.value)
        else np.nan
    )
    net_debt = (
        float(debt.value) - float(cash.value)
        if pd.notna(debt.value) and pd.notna(cash.value)
        else np.nan
    )

    facts = [revenue, ocf, capex, operating_income, depreciation, debt, cash]
    period_ends = [fact.period_end for fact in facts if pd.notna(fact.period_end)]
    filed_dates = [fact.filed for fact in facts if pd.notna(fact.filed)]
    flow_methods = sorted(
        {fact.method for fact in [revenue, ocf, capex, operating_income, depreciation]}
    )

    cik = BORROWER_FINANCIAL_CONDITION_CIKS.get(str(ticker).upper())
    return {
        "Date": cutoff_ts.date().isoformat(),
        "Observation Frequency": observation_frequency,
        "Ticker": str(ticker).upper(),
        "Revenue": revenue.value,
        "Operating Cash Flow": ocf.value,
        "CapEx": capex_value,
        "Free Cash Flow": fcf,
        "EBITDA": ebitda,
        "Total Debt": debt.value,
        "Cash": cash.value,
        "Net Debt": net_debt,
        "Financial Period End": max(period_ends).date().isoformat() if period_ends else None,
        "Financial Filing Date": max(filed_dates).date().isoformat() if filed_dates else None,
        "Flow Method": "; ".join(flow_methods),
        "Revenue Quarters": revenue.quarters,
        "OCF Quarters": ocf.quarters,
        "CapEx Quarters": capex.quarters,
        "EBITDA Quarters": min(operating_income.quarters, depreciation.quarters),
        "Source URL": (
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
            if cik
            else None
        ),
    }


def snapshot_to_sector_data(snapshot: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if snapshot is None or snapshot.empty:
        return {}
    expected = [
        "Ticker",
        "Revenue",
        "Operating Cash Flow",
        "CapEx",
        "Free Cash Flow",
        "EBITDA",
        "Total Debt",
        "Cash",
        "Net Debt",
    ]
    frame = snapshot.copy()
    for column in expected:
        if column not in frame.columns:
            frame[column] = np.nan
    return {"Historical Borrower Financial Condition Cohort": frame[expected].copy()}


def borrower_condition_result_to_history_row(
    observation_date: str | date | pd.Timestamp,
    observation_frequency: str,
    result: Mapping,
    fundamentals_snapshot: pd.DataFrame,
    ledger_snapshot: pd.DataFrame,
    *,
    version: str = "4.0",
) -> dict:
    components = (result or {}).get("components", {}) or {}
    component_score = lambda name: (components.get(name, {}) or {}).get("score", np.nan)

    financial_filing = pd.to_datetime(
        fundamentals_snapshot.get("Financial Filing Date"), errors="coerce"
    ) if not fundamentals_snapshot.empty else pd.Series(dtype="datetime64[ns]")
    commitment_filing = pd.to_datetime(
        ledger_snapshot.get("Filing Date"), errors="coerce"
    ) if not ledger_snapshot.empty else pd.Series(dtype="datetime64[ns]")

    valid_components = int((result or {}).get("valid_components", 0) or 0)
    score = (result or {}).get("score", np.nan)
    status = "Accepted" if pd.notna(score) and valid_components >= 3 else "Insufficient coverage"

    return {
        "Date": pd.Timestamp(observation_date).date().isoformat(),
        "Observation Frequency": observation_frequency,
        "Borrower Financial Condition": score,
        "Borrower Cash Flow Strain": component_score("Cash Flow Strain"),
        "Borrower Debt Capacity Strain": component_score("Debt Capacity Strain"),
        "Borrower Committed Burden": component_score("Committed Burden"),
        "Borrower Contingent Exposure": component_score("Contingent Exposure"),
        "FCF Margin": (components.get("Cash Flow Strain", {}) or {}).get("raw", np.nan),
        "Reinvestment Ratio": (components.get("Cash Flow Strain", {}) or {}).get("secondary_raw", np.nan),
        "Positive EBITDA Net Debt/EBITDA": (components.get("Debt Capacity Strain", {}) or {}).get("raw", np.nan),
        "Negative EBITDA Net Debt/Revenue": (components.get("Debt Capacity Strain", {}) or {}).get("secondary_raw", np.nan),
        "Committed Burden Ratio": (components.get("Committed Burden", {}) or {}).get("raw", np.nan),
        "Contingent Burden Ratio": (components.get("Contingent Exposure", {}) or {}).get("raw", np.nan),
        "Borrower Financial Condition Version": version,
        "Valid Components": valid_components,
        "Component Coverage": (result or {}).get("coverage", np.nan),
        "Cohort Companies": (result or {}).get("cohort_companies", 0),
        "Target Cohort Size": (result or {}).get("target_cohort_size", len(BORROWER_FINANCIAL_CONDITION_CIKS)),
        "Financial Companies": int(fundamentals_snapshot["Ticker"].nunique()) if not fundamentals_snapshot.empty else 0,
        "Commitment Companies": len((result or {}).get("commitment_tickers", []) or []),
        "Contingent Companies": len((result or {}).get("contingent_tickers", []) or []),
        "Latest Financial Filing Date": (
            financial_filing.max().date().isoformat()
            if not financial_filing.empty and financial_filing.notna().any()
            else None
        ),
        "Latest Commitment Filing Date": (
            commitment_filing.max().date().isoformat()
            if not commitment_filing.empty and commitment_filing.notna().any()
            else None
        ),
        "Cohort Tickers": ";".join((result or {}).get("cohort_tickers", []) or []),
        "Commitment Tickers": ";".join((result or {}).get("commitment_tickers", []) or []),
        "Contingent Tickers": ";".join((result or {}).get("contingent_tickers", []) or []),
        "Backfill Status": status,
    }
