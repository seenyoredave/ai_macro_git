from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from loaders.official_series_refresh import refresh_single_series, refresh_templated_history

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CES_PATH = PROJECT_ROOT / "data" / "workforce_ces_history.csv"
JOLTS_PATH = PROJECT_ROOT / "data" / "workforce_job_openings_history.csv"
FLOW_PATH = PROJECT_ROOT / "data" / "workforce_labor_flows_history.csv"
EXPOSURE_PATH = PROJECT_ROOT / "data" / "workforce_llm_exposure_snapshot.csv"
CPI_PATH = PROJECT_ROOT / "data" / "economic_impact_cpi_history.csv"

CHANNEL_TO_LABOR_MARKET = {
    "Computer systems design": "Professional and business services",
    "Computing infrastructure": "Information",
    "Semiconductor manufacturing": "Manufacturing",
    "Power & communication construction": "Construction",
}


def _read_history(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        frame = pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
    if "Date" in frame.columns:
        frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce", format="mixed")
    if "Value" in frame.columns:
        frame["Value"] = pd.to_numeric(frame["Value"], errors="coerce")
    required = [column for column in ["Date", "Value"] if column in frame.columns]
    return frame.dropna(subset=required).reset_index(drop=True)


def _read_cpi(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=["Date", "CPI"])
    try:
        frame = pd.read_csv(path)
    except Exception:
        return pd.DataFrame(columns=["Date", "CPI"])
    frame["Date"] = pd.to_datetime(frame.get("Date"), errors="coerce", format="mixed")
    frame["CPI"] = pd.to_numeric(frame.get("CPI"), errors="coerce")
    return frame.dropna(subset=["Date", "CPI"]).sort_values("Date", kind="stable").reset_index(drop=True)



def _read_exposure(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        frame = pd.read_csv(path, dtype={"O*NET-SOC Code": str, "SOC Major Code": str})
    except Exception:
        return pd.DataFrame()
    numeric = [
        "Human Direct LLM Exposure",
        "Human Blended LLM Exposure",
        "Human LLM + Software Exposure",
        "GPT-4 Direct LLM Exposure",
        "GPT-4 Blended LLM Exposure",
        "GPT-4 LLM + Software Exposure",
    ]
    for column in numeric:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["O*NET-SOC Code", "Occupation"]).reset_index(drop=True)


def _exposure_outputs(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    if frame.empty or not {"Major Occupational Group", "Human Direct LLM Exposure", "Human LLM + Software Exposure"}.issubset(frame.columns):
        return pd.DataFrame(), {}
    clean = frame.copy()
    direct = pd.to_numeric(clean["Human Direct LLM Exposure"], errors="coerce")
    software = pd.to_numeric(clean["Human LLM + Software Exposure"], errors="coerce")
    clean = clean.assign(_direct=direct, _software=software).dropna(subset=["_direct", "_software"])
    group = (
        clean.groupby("Major Occupational Group", as_index=False)
        .agg(
            **{
                "Occupations": ("Occupation", "count"),
                "Median direct exposure": ("_direct", "median"),
                "Median LLM + software exposure": ("_software", "median"),
                "High-exposure occupations": ("_software", lambda values: int((values >= 50).sum())),
            }
        )
    )
    group["High-exposure share"] = group["High-exposure occupations"] / group["Occupations"] * 100.0
    group = group.sort_values("Median LLM + software exposure", ascending=False, kind="stable").reset_index(drop=True)
    summary = {
        "occupations": int(len(clean)),
        "major_groups": int(clean["Major Occupational Group"].nunique()),
        "median_direct_exposure": float(clean["_direct"].median()),
        "median_llm_software_exposure": float(clean["_software"].median()),
        "share_at_least_10_pct": float((clean["_software"] >= 10).mean() * 100.0),
        "share_at_least_50_pct": float((clean["_software"] >= 50).mean() * 100.0),
        "benchmark_vintage": str(clean.get("Benchmark Vintage", pd.Series([""])).iloc[0]),
    }
    return group, summary

def _latest_summary(frame: pd.DataFrame, *, metric: str | None = None) -> pd.DataFrame:
    clean = frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    if clean.empty or not {"Date", "Series", "Value"}.issubset(clean.columns):
        return pd.DataFrame(columns=["Series", "Date", "Value", "YoY Change"])
    if metric is not None and "Metric" in clean.columns:
        clean = clean.loc[clean["Metric"].astype(str).eq(metric)]
    rows = []
    for series, group in clean.groupby("Series", sort=False):
        group = group.dropna(subset=["Date", "Value"]).sort_values("Date", kind="stable")
        if group.empty:
            continue
        latest = group.iloc[-1]
        target = pd.Timestamp(latest["Date"]) - pd.DateOffset(years=1)
        prior = group.loc[group["Date"] <= target]
        yoy = np.nan
        if not prior.empty:
            previous = pd.to_numeric(prior.iloc[-1]["Value"], errors="coerce")
            current = pd.to_numeric(latest["Value"], errors="coerce")
            if pd.notna(previous) and previous != 0 and pd.notna(current):
                yoy = float(current / previous - 1.0)
        rows.append({
            "Series": str(series),
            "Date": pd.Timestamp(latest["Date"]),
            "Value": float(latest["Value"]),
            "YoY Change": yoy,
            "Unit": str(latest.get("Unit", "")),
            "Series ID": str(latest.get("Series ID", "")),
        })
    return pd.DataFrame(rows).sort_values("Series", kind="stable").reset_index(drop=True)


def _latest_flow_summary(frame: pd.DataFrame) -> pd.DataFrame:
    clean = frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    if clean.empty or not {"Date", "Series", "Metric", "Value"}.issubset(clean.columns):
        return pd.DataFrame(columns=["Series", "Metric", "Date", "Value", "YoY Change", "History Percentile"])
    rows: list[dict] = []
    for (series, metric), group in clean.groupby(["Series", "Metric"], sort=False):
        group = group.dropna(subset=["Date", "Value"]).sort_values("Date", kind="stable")
        if group.empty:
            continue
        latest = group.iloc[-1]
        target = pd.Timestamp(latest["Date"]) - pd.DateOffset(years=1)
        prior = group.loc[group["Date"] <= target]
        yoy = np.nan
        if not prior.empty:
            yoy = float(latest["Value"] - prior.iloc[-1]["Value"])
        percentile = float(group["Value"].rank(pct=True, method="average").iloc[-1] * 100.0)
        rows.append({
            "Series": str(series),
            "Metric": str(metric),
            "Date": pd.Timestamp(latest["Date"]),
            "Value": float(latest["Value"]),
            "YoY Change": yoy,
            "History Percentile": percentile,
            "Unit": str(latest.get("Unit", "")),
            "Series ID": str(latest.get("Series ID", "")),
        })
    return pd.DataFrame(rows).sort_values(["Metric", "Series"], kind="stable").reset_index(drop=True)


def _real_earnings_history(earnings: pd.DataFrame, cpi: pd.DataFrame) -> pd.DataFrame:
    if earnings.empty or cpi.empty:
        return pd.DataFrame(columns=["Date", "Series", "Value"])
    left = earnings.copy().sort_values("Date", kind="stable")
    right = cpi[["Date", "CPI"]].copy().sort_values("Date", kind="stable")
    merged = pd.merge_asof(left, right, on="Date", direction="backward")
    merged["Nominal Value"] = pd.to_numeric(merged["Value"], errors="coerce")
    merged["Value"] = merged["Nominal Value"] / pd.to_numeric(merged["CPI"], errors="coerce") * 100.0
    return merged.dropna(subset=["Date", "Series", "Value"])


def _history_yoy_percentile(frame: pd.DataFrame, series: str) -> tuple[float, float]:
    group = frame.loc[frame.get("Series", pd.Series("", index=frame.index)).astype(str).eq(series)].copy()
    group = group.dropna(subset=["Date", "Value"]).sort_values("Date", kind="stable")
    if group.empty:
        return np.nan, np.nan
    group["YoY"] = group["Value"].pct_change(12)
    valid = group.dropna(subset=["YoY"])
    if valid.empty:
        return np.nan, np.nan
    latest = float(valid.iloc[-1]["YoY"] * 100.0)
    percentile = float(valid["YoY"].rank(pct=True, method="average").iloc[-1] * 100.0)
    return latest, percentile


def _flow_cell(latest: pd.DataFrame, market: str, metric: str) -> tuple[float, float]:
    rows = latest.loc[
        latest.get("Series", pd.Series("", index=latest.index)).astype(str).eq(market)
        & latest.get("Metric", pd.Series("", index=latest.index)).astype(str).eq(metric)
    ]
    if rows.empty:
        return np.nan, np.nan
    row = rows.iloc[-1]
    return float(row.get("Value", np.nan)), float(row.get("History Percentile", np.nan))


def _build_transmission_matrix(
    employment: pd.DataFrame,
    real_earnings: pd.DataFrame,
    flow_latest: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict] = []
    for channel, market in CHANNEL_TO_LABOR_MARKET.items():
        employment_yoy, employment_pct = _history_yoy_percentile(employment, channel)
        real_yoy, real_pct = _history_yoy_percentile(real_earnings, channel)
        openings, openings_pct = _flow_cell(flow_latest, market, "Job openings rate")
        hires, hires_pct = _flow_cell(flow_latest, market, "Hires rate")
        quits, quits_pct = _flow_cell(flow_latest, market, "Quits rate")
        layoffs, layoffs_pct = _flow_cell(flow_latest, market, "Layoffs and discharges rate")
        layoff_support = 100.0 - layoffs_pct if pd.notna(layoffs_pct) else np.nan

        if pd.notna(employment_yoy) and employment_yoy > 0 and pd.notna(real_yoy) and real_yoy > 0 and pd.notna(layoff_support) and layoff_support >= 50:
            status = "Expansion with worker capture"
        elif pd.notna(employment_yoy) and employment_yoy > 0 and pd.notna(real_yoy) and real_yoy <= 0:
            status = "Jobs up; real earnings lag"
        elif pd.notna(employment_yoy) and employment_yoy <= 0 and pd.notna(layoff_support) and layoff_support < 35:
            status = "Contraction and separation pressure"
        else:
            status = "Mixed transmission"

        rows.append({
            "Channel": channel,
            "Labor market": market,
            "Employment YoY": employment_yoy,
            "Real earnings YoY": real_yoy,
            "Openings rate": openings,
            "Hires rate": hires,
            "Quits rate": quits,
            "Layoffs rate": layoffs,
            "Employment support": employment_pct,
            "Real earnings support": real_pct,
            "Openings support": openings_pct,
            "Hires support": hires_pct,
            "Quits support": quits_pct,
            "Low-layoff support": layoff_support,
            "Status": status,
        })
    return pd.DataFrame(rows)


@st.cache_data(ttl=21600)
def load_workforce_data(force_refresh: bool = False, refresh_token: int = 0) -> dict:
    del refresh_token
    refresh_reports = {}
    if force_refresh:
        ces, refresh_reports["ces"] = refresh_templated_history(
            CES_PATH, start_date="2020-01-01", required_columns=("Series", "Metric", "Unit", "Source")
        )
        jolts, refresh_reports["jolts_openings"] = refresh_templated_history(
            JOLTS_PATH, start_date="2020-01-01", required_columns=("Series", "Metric", "Unit", "Source")
        )
        flows, refresh_reports["jolts_flows"] = refresh_templated_history(
            FLOW_PATH,
            start_date="2020-01-01",
            required_columns=("Series", "Metric", "Unit", "Source", "Attribution boundary"),
        )
        cpi, refresh_reports["cpi"] = refresh_single_series(
            CPI_PATH,
            series_id="CPIAUCSL",
            output_date_column="Date",
            output_value_column="CPI",
            start_date="2020-01-01",
        )
        exposure = _read_exposure(EXPOSURE_PATH)
    else:
        ces = _read_history(CES_PATH)
        jolts = _read_history(JOLTS_PATH)
        flows = _read_history(FLOW_PATH)
        cpi = _read_cpi(CPI_PATH)
        exposure = _read_exposure(EXPOSURE_PATH)

    exposure_by_group, exposure_summary = _exposure_outputs(exposure)
    employment = ces.loc[ces.get("Metric", pd.Series(index=ces.index, dtype=str)).astype(str).eq("Employment")].copy()
    earnings = ces.loc[ces.get("Metric", pd.Series(index=ces.index, dtype=str)).astype(str).eq("Hourly earnings")].copy()
    real_earnings = _real_earnings_history(earnings, cpi)
    flow_latest = _latest_flow_summary(flows)
    transmission_matrix = _build_transmission_matrix(employment, real_earnings, flow_latest)

    modes = [str(report.get("source_mode", "")) for report in refresh_reports.values()]
    source_mode = (
        "live_refresh" if modes and all(mode == "live_refresh" for mode in modes)
        else "partial_refresh" if modes and any(mode in {"live_refresh", "partial_refresh"} for mode in modes)
        else "retained_fallback" if modes
        else "retained_official"
    )
    dates = []
    for frame in (employment, earnings, jolts, flows):
        if isinstance(frame, pd.DataFrame) and not frame.empty and "Date" in frame.columns:
            dates.append(frame["Date"].max())
    return {
        "source_mode": source_mode,
        "load_report": {"source_mode": source_mode, "datasets": refresh_reports},
        "employment_history": employment,
        "earnings_history": earnings,
        "real_earnings_history": real_earnings,
        "job_openings_history": jolts,
        "labor_flows_history": flows,
        "cpi_history": cpi,
        "employment_latest": _latest_summary(employment),
        "earnings_latest": _latest_summary(earnings),
        "real_earnings_latest": _latest_summary(real_earnings),
        "job_openings_latest": _latest_summary(jolts),
        "labor_flow_latest": flow_latest,
        "transmission_matrix": transmission_matrix,
        "occupation_exposure": exposure,
        "occupation_exposure_by_group": exposure_by_group,
        "exposure_summary": exposure_summary,
        "snapshot_date": max([date for date in dates if pd.notna(date)], default=pd.NaT),
        "source_manifest": pd.DataFrame([
            {"Dataset": "Employment, hourly earnings, and U.S. total-private wage benchmark", "Source": "BLS Current Employment Statistics", "Frequency": "Monthly", "Coverage": "2020-present", "Attribution boundary": "Directly relevant industries plus a national private-sector benchmark; not every job or wage movement is attributed to AI."},
            {"Dataset": "Job openings", "Source": "BLS Job Openings and Labor Turnover Survey", "Frequency": "Monthly", "Coverage": "2020-present", "Attribution boundary": "Broad labor-demand context; not AI-specific postings."},
            {"Dataset": "Openings, hires, quits, and layoffs rates", "Source": "BLS Job Openings and Labor Turnover Survey", "Frequency": "Monthly", "Coverage": "2020-present", "Attribution boundary": "Broad industry labor flows; they show demand, mobility, and separation conditions but do not identify AI-caused worker transitions."},
            {"Dataset": "Occupation-level theoretical LLM task exposure", "Source": "Eloundou, Manning, Mishkin, and Rock — GPTs are GPTs", "Frequency": "Fixed research benchmark", "Coverage": "923 O*NET-SOC occupations · 2023 task rubric", "Attribution boundary": "Static task-capability exposure; not observed adoption, automation, displacement, employment effects, or a forecast."},
            {"Dataset": "Consumer Price Index", "Source": "BLS via FRED retained history", "Frequency": "Monthly", "Coverage": "2020-present", "Attribution boundary": "Used only to express hourly earnings in constant purchasing-power terms."},
        ]),
    }
