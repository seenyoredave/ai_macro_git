from __future__ import annotations

from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st

from config.deployment import repository_writes_enabled
from helpers.atomic_io import atomic_write_csv

from config.debug_config import debug_print

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = PROJECT_ROOT / "data" / "infrastructure" / "derived" / "compute_manufacturing_history.csv"
M3_HISTORY_PATH = PROJECT_ROOT / "data" / "infrastructure" / "derived" / "compute_m3_history.csv"
PROJECT_LEDGER_PATH = PROJECT_ROOT / "data" / "infrastructure" / "derived" / "compute_project_ledger.csv"
INFO_INVESTMENT_PATH = PROJECT_ROOT / "data" / "info_processing_investment_history.csv"
SOURCE_MANIFEST_PATH = PROJECT_ROOT / "data" / "infrastructure" / "source_manifest.csv"
FIELD_DICTIONARY_PATH = PROJECT_ROOT / "data" / "infrastructure" / "field_dictionary.csv"
SERIES_CONTRACT_PATH = PROJECT_ROOT / "data" / "infrastructure" / "derived" / "compute_series_contract.csv"
SERIES_VALIDATION_PATH = PROJECT_ROOT / "data" / "infrastructure" / "derived" / "compute_series_validation.csv"

OUTPUT_SERIES = {
    "Computer and Peripheral Equipment Output": "IPG3341S",
    "Communications Equipment Output": "IPG3342S",
    "Semiconductor and Electronic Component Output": "IPG3344S",
}
CAPACITY_SERIES = {
    "Computer and Peripheral Equipment Capacity": "CAPG3341S",
    "Communications Equipment Capacity": "CAPG3342S",
    "Semiconductor and Electronic Component Capacity": "CAPG3344S",
}
UTILIZATION_SERIES = {
    "Computer and Peripheral Equipment Capacity Utilization": "CAPUTLG3341S",
    "Communications Equipment Capacity Utilization": "CAPUTLG3342S",
    "Semiconductor and Electronic Component Capacity Utilization": "CAPUTLG3344S",
}
M3_SERIES = {
    "Computer and Electronic Product Shipments": "A34SVS",
    "Computer and Electronic Product New Orders": "A34SNO",
    "Computer and Electronic Product Inventory to Shipments": "A34SIS",
    "Computer and Electronic Product Unfilled Orders to Shipments": "A34SUS",
}

SUPPLY_CHAIN_LAYER = {
    "Leading-edge logic": "Logic",
    "Logic fabrication": "Logic",
    "Advanced memory": "Memory / HBM",
    "Memory fabrication": "Memory / HBM",
    "HBM and advanced packaging": "Memory / HBM",
    "Advanced packaging": "Packaging / test",
    "Advanced packaging and test": "Packaging / test",
    "Foundry and advanced packaging": "Packaging / test",
    "Optical interconnect": "Photonics / interconnect",
    "Analog and embedded processing": "Analog / embedded",
    "Semiconductor R&D": "R&D / pilot capacity",
}


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path)


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    if not repository_writes_enabled():
        return
    atomic_write_csv(frame, path)


def _fetch_fred_series(series: dict[str, str]) -> pd.DataFrame:
    ids = ",".join(series.values())
    response = requests.get(
        f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={ids}",
        timeout=30,
        headers={"User-Agent": "ai-macro-compute/1.0"},
    )
    response.raise_for_status()
    frame = pd.read_csv(StringIO(response.text))
    date_column = next((column for column in ["DATE", "observation_date", "date"] if column in frame.columns), None)
    if date_column is None:
        raise ValueError("FRED compute response did not contain an observation date")
    rename = {date_column: "Observation Date"}
    rename.update({series_id: metric for metric, series_id in series.items()})
    output = frame.rename(columns=rename)
    for metric in series:
        if metric not in output.columns:
            output[metric] = np.nan
        output[metric] = pd.to_numeric(output[metric], errors="coerce")
    output["Observation Date"] = pd.to_datetime(output["Observation Date"], errors="coerce")
    return (
        output[["Observation Date", *series]]
        .dropna(subset=["Observation Date"])
        .sort_values("Observation Date", kind="stable")
        .drop_duplicates("Observation Date", keep="last")
        .reset_index(drop=True)
    )


def _normalize_history(frame: pd.DataFrame) -> pd.DataFrame:
    expected = ["Observation Date", *OUTPUT_SERIES, *CAPACITY_SERIES, *UTILIZATION_SERIES]
    if frame is None or frame.empty:
        return pd.DataFrame(columns=expected)
    output = frame.copy()
    for column in expected:
        if column not in output.columns:
            output[column] = pd.NaT if column == "Observation Date" else np.nan
    output["Observation Date"] = pd.to_datetime(output["Observation Date"], errors="coerce", format="mixed")
    for column in expected[1:]:
        output[column] = pd.to_numeric(output[column], errors="coerce")

    derived_pairs = [
        (
            "Computer and Peripheral Equipment Output",
            "Computer and Peripheral Equipment Capacity Utilization",
            "Computer and Peripheral Equipment Capacity",
        ),
        (
            "Semiconductor and Electronic Component Output",
            "Semiconductor and Electronic Component Capacity Utilization",
            "Semiconductor and Electronic Component Capacity",
        ),
    ]
    for output_column, utilization_column, capacity_column in derived_pairs:
        missing = output[capacity_column].isna()
        utilization = output[utilization_column].where(output[utilization_column] > 0)
        derived = output[output_column] / (utilization / 100.0)
        output.loc[missing, capacity_column] = derived.loc[missing]

    return (
        output[expected]
        .dropna(subset=["Observation Date"])
        .sort_values("Observation Date", kind="stable")
        .drop_duplicates("Observation Date", keep="last")
        .reset_index(drop=True)
    )


def _normalize_m3_history(frame: pd.DataFrame) -> pd.DataFrame:
    expected = ["Observation Date", *M3_SERIES]
    if frame is None or frame.empty:
        return pd.DataFrame(columns=expected)
    output = frame.copy()
    for column in expected:
        if column not in output.columns:
            output[column] = pd.NaT if column == "Observation Date" else np.nan
    output["Observation Date"] = pd.to_datetime(output["Observation Date"], errors="coerce", format="mixed")
    for column in expected[1:]:
        output[column] = pd.to_numeric(output[column], errors="coerce")
    return (
        output[expected]
        .dropna(subset=["Observation Date"])
        .sort_values("Observation Date", kind="stable")
        .drop_duplicates("Observation Date", keep="last")
        .reset_index(drop=True)
    )


def _normalize_info_investment(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["Observation Date", "Info Processing Investment Level"])
    output = frame.copy()
    if "Observation Date" not in output.columns or "Info Processing Investment Level" not in output.columns:
        return pd.DataFrame(columns=["Observation Date", "Info Processing Investment Level"])
    output["Observation Date"] = pd.to_datetime(output["Observation Date"], errors="coerce", format="mixed")
    output["Info Processing Investment Level"] = pd.to_numeric(
        output["Info Processing Investment Level"], errors="coerce"
    )
    return (
        output.dropna(subset=["Observation Date", "Info Processing Investment Level"])
        .sort_values("Observation Date", kind="stable")
        .drop_duplicates("Observation Date", keep="last")
        .reset_index(drop=True)
    )


def _series_summary(history: pd.DataFrame, column: str) -> dict:
    if history.empty or column not in history.columns:
        return {"value": np.nan, "date": None, "yoy_growth": np.nan}
    clean = history[["Observation Date", column]].dropna(subset=[column]).copy()
    if clean.empty:
        return {"value": np.nan, "date": None, "yoy_growth": np.nan}
    latest = clean.iloc[-1]
    latest_date = pd.Timestamp(latest["Observation Date"])
    prior = clean.loc[clean["Observation Date"] <= latest_date - pd.DateOffset(years=1)]
    yoy = np.nan
    if not prior.empty:
        prior_row = prior.iloc[-1]
        day_gap = (latest_date - pd.Timestamp(prior_row["Observation Date"])).days
        prior_value = pd.to_numeric(prior_row[column], errors="coerce")
        if pd.notna(prior_value) and prior_value != 0 and 330 <= day_gap <= 400:
            yoy = float(latest[column]) / float(prior_value) - 1.0
    return {
        "value": float(latest[column]),
        "date": latest_date.date().isoformat(),
        "yoy_growth": yoy,
    }


def _quality_summary(validation: pd.DataFrame) -> dict:
    if validation is None or validation.empty:
        return {
            "status": "unvalidated",
            "series_checked": 0,
            "series_current": 0,
            "series_needing_remediation": 0,
            "checked_on": None,
        }
    statuses = validation.get("comparison_status", pd.Series("", index=validation.index)).fillna("").astype(str)
    checked = pd.to_datetime(validation.get("checked_on"), errors="coerce", format="mixed")
    issues = int((~statuses.eq("pass_current")).sum())
    return {
        "status": "validated_current" if issues == 0 else "needs_remediation",
        "series_checked": int(len(validation)),
        "series_current": int(statuses.eq("pass_current").sum()),
        "series_needing_remediation": issues,
        "checked_on": None if checked.dropna().empty else checked.max().date().isoformat(),
    }


def _deduplicated_portfolio_sum(projects: pd.DataFrame, value_column: str) -> float:
    if projects.empty or value_column not in projects.columns:
        return np.nan
    clean = projects[["Portfolio ID", value_column] + (["Funding Scope"] if "Funding Scope" in projects.columns else [])].copy()
    clean[value_column] = pd.to_numeric(clean[value_column], errors="coerce")
    clean = clean.dropna(subset=[value_column])
    if clean.empty:
        return np.nan
    if value_column == "Direct Funding USD B" and "Funding Scope" in clean.columns:
        total = 0.0
        for _, group in clean.groupby("Portfolio ID", dropna=False):
            site = group.loc[group["Funding Scope"].fillna("").astype(str).str.lower().eq("site allocation"), value_column]
            portfolio = group.loc[~group.index.isin(site.index), value_column]
            total += float(site.sum())
            if not portfolio.empty:
                total += float(portfolio.max())
        return total
    return float(clean.groupby("Portfolio ID", dropna=False)[value_column].max().sum())


def _normalize_projects(projects: pd.DataFrame) -> pd.DataFrame:
    if projects is None or projects.empty:
        return pd.DataFrame()
    output = projects.copy()
    if "Source Retrieval Date" in output.columns:
        output["Source Retrieval Date"] = pd.to_datetime(output["Source Retrieval Date"], errors="coerce", format="mixed")
    output["Supply Chain Layer"] = (
        output.get("Component Layer", pd.Series("", index=output.index))
        .fillna("")
        .astype(str)
        .map(SUPPLY_CHAIN_LAYER)
        .fillna("Other compute supply")
    )
    return output.sort_values(["State", "Recipient", "Facility"], kind="stable").reset_index(drop=True)



def _critical_supply_chain_summary(projects: pd.DataFrame) -> dict:
    """Summarize the explicitly tracked AI-critical manufacturing layers.

    Project rows are retained evidence, not national production capacity.  The
    summary therefore reports coverage and announced capital rather than an
    invented self-sufficiency score.
    """
    critical_layers = [
        "Logic",
        "Memory / HBM",
        "Packaging / test",
        "Photonics / interconnect",
    ]
    if projects is None or projects.empty:
        return {
            "layers": pd.DataFrame(columns=["Supply Chain Layer", "Sites", "States", "Expected CapEx USD B", "Direct Funding USD B"]),
            "covered_layers": 0,
            "critical_layers": len(critical_layers),
            "core_ai_sites": 0,
            "core_ai_capex_usd_b": np.nan,
        }
    frame = projects.copy()
    frame["Supply Chain Layer"] = frame.get("Supply Chain Layer", "Other compute supply").fillna("Other compute supply").astype(str)
    frame["AI Relevance"] = frame.get("AI Relevance", "").fillna("").astype(str)
    for column in ["Expected CapEx USD B", "Direct Funding USD B", "Available Loan USD B"]:
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
    grouped = frame.groupby("Supply Chain Layer", as_index=False).agg(
        Sites=("Facility", "size"),
        States=("State", lambda values: int(pd.Series(values).replace("", np.nan).nunique())),
        **{
            "Expected CapEx USD B": ("Expected CapEx USD B", "sum"),
            "Direct Funding USD B": ("Direct Funding USD B", "sum"),
        },
    )
    grouped["Critical AI Layer"] = grouped["Supply Chain Layer"].isin(critical_layers)
    ordering = {layer: index for index, layer in enumerate([*critical_layers, "Analog / embedded", "R&D / pilot capacity", "Other compute supply"])}
    grouped["_order"] = grouped["Supply Chain Layer"].map(ordering).fillna(99)
    grouped = grouped.sort_values(["_order", "Supply Chain Layer"], kind="stable").drop(columns="_order").reset_index(drop=True)
    core = frame.loc[frame["AI Relevance"].str.casefold().eq("core ai")].copy()
    covered = int(grouped.loc[grouped["Supply Chain Layer"].isin(critical_layers) & grouped["Sites"].gt(0), "Supply Chain Layer"].nunique())
    return {
        "layers": grouped,
        "covered_layers": covered,
        "critical_layers": len(critical_layers),
        "core_ai_sites": int(len(core)),
        "core_ai_capex_usd_b": _deduplicated_portfolio_sum(core, "Expected CapEx USD B"),
        "boundary": "Tracked CHIPS projects show disclosed domestic commitments across critical layers; they do not measure current output, global market share, or supply-chain independence.",
    }

def _project_summary(projects: pd.DataFrame) -> dict:
    if projects.empty:
        return {
            "projects": 0,
            "portfolios": 0,
            "states": 0,
            "expected_capex_usd_b": np.nan,
            "direct_funding_usd_b": np.nan,
            "available_loans_usd_b": np.nan,
        }
    clean = projects.copy()
    for column in ["Expected CapEx USD B", "Direct Funding USD B", "Available Loan USD B", "Cleanroom Square Feet"]:
        if column in clean.columns:
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
    return {
        "projects": int(len(clean)),
        "portfolios": int(clean["Portfolio ID"].replace("", np.nan).nunique()),
        "states": int(clean["State"].replace("", np.nan).nunique()),
        "expected_capex_usd_b": _deduplicated_portfolio_sum(clean, "Expected CapEx USD B"),
        "direct_funding_usd_b": _deduplicated_portfolio_sum(clean, "Direct Funding USD B"),
        "available_loans_usd_b": _deduplicated_portfolio_sum(clean, "Available Loan USD B"),
    }


@st.cache_data(ttl=86400)
def load_compute_manufacturing_data(force_refresh: bool = False, refresh_token: int = 0) -> dict:
    del refresh_token
    history = _normalize_history(_load_csv(HISTORY_PATH))
    m3_history = _normalize_m3_history(_load_csv(M3_HISTORY_PATH))
    source_mode = "retained"
    refresh_errors: dict[str, str] = {}
    refreshed_datasets: list[str] = []

    if force_refresh:
        try:
            refreshed = _normalize_history(_fetch_fred_series({**OUTPUT_SERIES, **CAPACITY_SERIES, **UTILIZATION_SERIES}))
            if not refreshed.empty:
                output = refreshed.copy()
                output["Observation Date"] = output["Observation Date"].dt.date.astype(str)
                output["Source"] = "Federal Reserve G.17 / FRED public CSV"
                output["Evidence Class"] = "agency_index"
                output["Evidence Grade"] = "A"
                output["Resilience Grade"] = "R1"
                _atomic_csv(output, HISTORY_PATH)
                history = refreshed
                refreshed_datasets.append("g17")
        except Exception as exc:
            debug_print(f"Compute G.17 refresh failed -> {exc}")
            refresh_errors["g17"] = f"{type(exc).__name__}: {exc}"
        try:
            refreshed_m3 = _normalize_m3_history(_fetch_fred_series(M3_SERIES))
            if not refreshed_m3.empty:
                output = refreshed_m3.copy()
                output["Observation Date"] = output["Observation Date"].dt.date.astype(str)
                output["Source"] = "U.S. Census Bureau M3 / FRED public CSV"
                output["Evidence Class"] = "agency_estimate"
                output["Evidence Grade"] = "A"
                output["Resilience Grade"] = "R1"
                _atomic_csv(output, M3_HISTORY_PATH)
                m3_history = refreshed_m3
                refreshed_datasets.append("m3")
        except Exception as exc:
            debug_print(f"Compute M3 refresh failed -> {exc}")
            refresh_errors["m3"] = f"{type(exc).__name__}: {exc}"

        source_mode = (
            "live_refresh" if len(refreshed_datasets) == 2 and not refresh_errors
            else "partial_refresh" if refreshed_datasets
            else "retained_fallback"
        )

    projects = _normalize_projects(_load_csv(PROJECT_LEDGER_PATH))
    info_investment = _normalize_info_investment(_load_csv(INFO_INVESTMENT_PATH))
    series_contract = _load_csv(SERIES_CONTRACT_PATH)
    series_validation = _load_csv(SERIES_VALIDATION_PATH)
    series = {
        column: _series_summary(history, column)
        for column in [*OUTPUT_SERIES, *CAPACITY_SERIES, *UTILIZATION_SERIES]
    }
    series["Info Processing Investment Level"] = _series_summary(
        info_investment, "Info Processing Investment Level"
    )
    m3_series = {column: _series_summary(m3_history, column) for column in M3_SERIES}

    if not series_contract.empty and "metric" in series_contract.columns:
        contract_by_metric = series_contract.set_index("metric").to_dict(orient="index")
        for column, item in series.items():
            item.update(contract_by_metric.get(column, {}))

    return {
        "source_mode": source_mode,
        "load_report": {
            "source_mode": source_mode,
            "requested_datasets": ["g17", "m3"] if force_refresh else [],
            "refreshed_datasets": refreshed_datasets,
            "errors": refresh_errors,
        },
        "history": history,
        "m3_history": m3_history,
        "info_investment_history": info_investment,
        "series": series,
        "m3_series": m3_series,
        "projects": projects,
        "project_summary": _project_summary(projects),
        "critical_supply_chain": _critical_supply_chain_summary(projects),
        "source_manifest": _load_csv(SOURCE_MANIFEST_PATH),
        "field_dictionary": _load_csv(FIELD_DICTIONARY_PATH),
        "series_contract": series_contract,
        "series_validation": series_validation,
        "quality_summary": _quality_summary(series_validation),
        "output_series": OUTPUT_SERIES.copy(),
        "capacity_series": CAPACITY_SERIES.copy(),
        "utilization_series": UTILIZATION_SERIES.copy(),
        "m3_series_contract": M3_SERIES.copy(),
    }
