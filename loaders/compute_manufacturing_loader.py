from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = PROJECT_ROOT / "data" / "infrastructure" / "derived" / "compute_manufacturing_history.csv"
PROJECT_LEDGER_PATH = PROJECT_ROOT / "data" / "infrastructure" / "derived" / "compute_project_ledger.csv"
SOURCE_MANIFEST_PATH = PROJECT_ROOT / "data" / "infrastructure" / "source_manifest.csv"
FIELD_DICTIONARY_PATH = PROJECT_ROOT / "data" / "infrastructure" / "field_dictionary.csv"
SERIES_CONTRACT_PATH = PROJECT_ROOT / "data" / "infrastructure" / "derived" / "compute_series_contract.csv"
SERIES_VALIDATION_PATH = PROJECT_ROOT / "data" / "infrastructure" / "derived" / "compute_series_validation.csv"

OUTPUT_SERIES = {
    "Computer and Peripheral Equipment Output": "Computer/peripheral output",
    "Communications Equipment Output": "Communications-equipment output",
    "Semiconductor and Electronic Component Output": "Semiconductor/component output",
}
UTILIZATION_SERIES = {
    "Computer and Peripheral Equipment Capacity Utilization": "Computer/peripheral utilization",
    "Semiconductor and Electronic Component Capacity Utilization": "Semiconductor/component utilization",
}

def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path)

def _normalize_history(frame: pd.DataFrame) -> pd.DataFrame:
    expected = ["Observation Date", *OUTPUT_SERIES, *UTILIZATION_SERIES]
    if frame is None or frame.empty:
        return pd.DataFrame(columns=expected)
    output = frame.copy()
    for column in expected:
        if column not in output.columns:
            output[column] = pd.NaT if column == "Observation Date" else np.nan
    output["Observation Date"] = pd.to_datetime(output["Observation Date"], errors="coerce", format="mixed")
    for column in [*OUTPUT_SERIES, *UTILIZATION_SERIES]:
        output[column] = pd.to_numeric(output[column], errors="coerce")
    return (
        output.dropna(subset=["Observation Date"])
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

def _project_summary(projects: pd.DataFrame) -> dict:
    if projects.empty:
        return {
            "projects": 0,
            "portfolios": 0,
            "states": 0,
            "expected_capex_usd_b": np.nan,
            "direct_funding_usd_b": np.nan,
            "available_loans_usd_b": np.nan,
            "component_layers": pd.DataFrame(columns=["Component Layer", "Projects"]),
            "ai_relevance": pd.DataFrame(columns=["AI Relevance", "Projects"]),
        }
    clean = projects.copy()
    for column in ["Expected CapEx USD B", "Direct Funding USD B", "Available Loan USD B", "Cleanroom Square Feet"]:
        if column in clean.columns:
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
    component_layers = (
        clean.groupby("Component Layer", dropna=False)
        .size()
        .rename("Projects")
        .reset_index()
        .sort_values(["Projects", "Component Layer"], ascending=[False, True], kind="stable")
    )
    ai_relevance = (
        clean.groupby("AI Relevance", dropna=False)
        .size()
        .rename("Projects")
        .reset_index()
        .sort_values(["Projects", "AI Relevance"], ascending=[False, True], kind="stable")
    )
    return {
        "projects": int(len(clean)),
        "portfolios": int(clean["Portfolio ID"].replace("", np.nan).nunique()),
        "states": int(clean["State"].replace("", np.nan).nunique()),
        "expected_capex_usd_b": _deduplicated_portfolio_sum(clean, "Expected CapEx USD B"),
        "direct_funding_usd_b": _deduplicated_portfolio_sum(clean, "Direct Funding USD B"),
        "available_loans_usd_b": _deduplicated_portfolio_sum(clean, "Available Loan USD B"),
        "component_layers": component_layers,
        "ai_relevance": ai_relevance,
    }

@st.cache_data(ttl=86400)
def load_compute_manufacturing_data(refresh_token: int = 0) -> dict:
    del refresh_token
    history = _normalize_history(_load_csv(HISTORY_PATH))
    projects = _load_csv(PROJECT_LEDGER_PATH)
    if not projects.empty:
        for column in ["Source Retrieval Date"]:
            if column in projects.columns:
                projects[column] = pd.to_datetime(projects[column], errors="coerce", format="mixed")
        projects = projects.sort_values(["State", "Recipient", "Facility"], kind="stable").reset_index(drop=True)
    series_contract = _load_csv(SERIES_CONTRACT_PATH)
    series_validation = _load_csv(SERIES_VALIDATION_PATH)
    series = {column: _series_summary(history, column) for column in [*OUTPUT_SERIES, *UTILIZATION_SERIES]}
    if not series_contract.empty and "metric" in series_contract.columns:
        contract_by_metric = series_contract.set_index("metric").to_dict(orient="index")
        for column, item in series.items():
            item.update(contract_by_metric.get(column, {}))
    return {
        "source_mode": "retained",
        "history": history,
        "series": series,
        "projects": projects,
        "project_summary": _project_summary(projects),
        "source_manifest": _load_csv(SOURCE_MANIFEST_PATH),
        "field_dictionary": _load_csv(FIELD_DICTIONARY_PATH),
        "series_contract": series_contract,
        "series_validation": series_validation,
        "quality_summary": _quality_summary(series_validation),
        "output_series": OUTPUT_SERIES.copy(),
        "utilization_series": UTILIZATION_SERIES.copy(),
    }
