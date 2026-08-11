from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from loaders.official_series_refresh import refresh_single_series, refresh_templated_history

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCTIVITY_PATH = PROJECT_ROOT / "data" / "economic_impact_productivity_history.csv"
INVESTMENT_PATH = PROJECT_ROOT / "data" / "info_processing_investment_history.csv"
CPI_PATH = PROJECT_ROOT / "data" / "economic_impact_cpi_history.csv"
TRANSMISSION_PATH = PROJECT_ROOT / "data" / "economic_value_transmission_history.csv"
DISTRIBUTION_PATH = PROJECT_ROOT / "data" / "household_earnings_distribution_history.csv"


def _read(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        frame = pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
    for column in ["Date", "Observation Date"]:
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce", format="mixed")
    for column in ["Value", "Info Processing Investment Level", "CPI"]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def _latest_metric(frame: pd.DataFrame, sector: str, measure: str, metric: str = "Year-over-year change") -> dict:
    if frame.empty:
        return {"value": np.nan, "date": None, "series_id": ""}
    mask = (
        frame.get("sector_name", pd.Series("", index=frame.index)).astype(str).eq(sector)
        & frame.get("measure_text", pd.Series("", index=frame.index)).astype(str).eq(measure)
        & frame.get("Metric", pd.Series("", index=frame.index)).astype(str).eq(metric)
    )
    clean = frame.loc[mask].dropna(subset=["Date", "Value"]).sort_values("Date", kind="stable")
    if clean.empty:
        return {"value": np.nan, "date": None, "series_id": ""}
    latest = clean.iloc[-1]
    return {"value": float(latest["Value"]), "date": pd.Timestamp(latest["Date"]), "series_id": str(latest.get("Series ID", ""))}


def _investment_summary(frame: pd.DataFrame) -> dict:
    if frame.empty or not {"Observation Date", "Info Processing Investment Level"}.issubset(frame.columns):
        return {"value": np.nan, "date": None, "yoy": np.nan}
    clean = frame.dropna(subset=["Observation Date", "Info Processing Investment Level"]).sort_values("Observation Date", kind="stable")
    if clean.empty:
        return {"value": np.nan, "date": None, "yoy": np.nan}
    latest = clean.iloc[-1]
    target = latest["Observation Date"] - pd.DateOffset(years=1)
    prior = clean.loc[clean["Observation Date"] <= target]
    yoy = np.nan
    if not prior.empty and float(prior.iloc[-1]["Info Processing Investment Level"]) > 0:
        yoy = float(latest["Info Processing Investment Level"] / prior.iloc[-1]["Info Processing Investment Level"] - 1.0) * 100.0
    return {"value": float(latest["Info Processing Investment Level"]), "date": pd.Timestamp(latest["Observation Date"]), "yoy": yoy}


def _inflation_summary(frame: pd.DataFrame) -> dict:
    if frame.empty or not {"Date", "CPI"}.issubset(frame.columns):
        return {"value": np.nan, "date": None, "yoy": np.nan}
    clean = frame.dropna(subset=["Date", "CPI"]).sort_values("Date", kind="stable")
    if clean.empty:
        return {"value": np.nan, "date": None, "yoy": np.nan}
    latest = clean.iloc[-1]
    target = pd.Timestamp(latest["Date"]) - pd.DateOffset(years=1)
    prior = clean.loc[clean["Date"] <= target]
    yoy = np.nan
    if not prior.empty and float(prior.iloc[-1]["CPI"]) > 0:
        yoy = (float(latest["CPI"]) / float(prior.iloc[-1]["CPI"]) - 1.0) * 100.0
    return {"value": float(latest["CPI"]), "date": pd.Timestamp(latest["Date"]), "yoy": yoy}


def _index_summary(frame: pd.DataFrame, series: str) -> dict:
    if frame.empty or not {"Date", "Series", "Value"}.issubset(frame.columns):
        return {"value": np.nan, "date": None, "yoy": np.nan, "since_2020": np.nan}
    clean = frame.loc[frame["Series"].astype(str).eq(series)].dropna(subset=["Date", "Value"]).sort_values("Date", kind="stable")
    if clean.empty:
        return {"value": np.nan, "date": None, "yoy": np.nan, "since_2020": np.nan}
    latest = clean.iloc[-1]
    target = pd.Timestamp(latest["Date"]) - pd.DateOffset(years=1)
    prior = clean.loc[clean["Date"] <= target]
    base = clean.iloc[0]
    yoy = np.nan
    since_2020 = np.nan
    if not prior.empty and float(prior.iloc[-1]["Value"]) != 0:
        yoy = (float(latest["Value"]) / float(prior.iloc[-1]["Value"]) - 1.0) * 100.0
    if float(base["Value"]) != 0:
        since_2020 = (float(latest["Value"]) / float(base["Value"]) - 1.0) * 100.0
    return {
        "value": float(latest["Value"]),
        "date": pd.Timestamp(latest["Date"]),
        "yoy": yoy,
        "since_2020": since_2020,
        "series_id": str(latest.get("Series ID", "")),
    }


def _distribution_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or not {"Date", "Series", "Value"}.issubset(frame.columns):
        return pd.DataFrame(columns=["Series", "Dimension", "Date", "Value", "YoY", "Since 2020", "Relative to all workers"])
    rows: list[dict] = []
    overall_latest = np.nan
    prepared: dict[str, dict] = {}
    for series, group in frame.groupby("Series", sort=False):
        group = group.dropna(subset=["Date", "Value"]).sort_values("Date", kind="stable").copy()
        if group.empty:
            continue
        group["Four-quarter average"] = group["Value"].rolling(4, min_periods=4).mean()
        valid = group.dropna(subset=["Four-quarter average"])
        if valid.empty:
            continue
        latest = valid.iloc[-1]
        prior = valid.loc[valid["Date"] <= pd.Timestamp(latest["Date"]) - pd.DateOffset(years=1)]
        base = valid.loc[valid["Date"] < pd.Timestamp("2021-01-01")]
        base_value = float(base.iloc[-1]["Four-quarter average"]) if not base.empty else float(valid.iloc[0]["Four-quarter average"])
        yoy = np.nan
        if not prior.empty and float(prior.iloc[-1]["Four-quarter average"]) != 0:
            yoy = (float(latest["Four-quarter average"]) / float(prior.iloc[-1]["Four-quarter average"]) - 1.0) * 100.0
        since = (float(latest["Four-quarter average"]) / base_value - 1.0) * 100.0 if base_value else np.nan
        prepared[str(series)] = {
            "Series": str(series),
            "Dimension": str(latest.get("Dimension", "")),
            "Date": pd.Timestamp(latest["Date"]),
            "Value": float(latest["Four-quarter average"]),
            "YoY": yoy,
            "Since 2020": since,
            "Seasonality": str(latest.get("Seasonality", "")),
            "Series ID": str(latest.get("Series ID", "")),
        }
    if "All full-time workers" in prepared:
        overall_latest = prepared["All full-time workers"]["Value"]
    for payload in prepared.values():
        value = payload["Value"]
        payload["Relative to all workers"] = (value / overall_latest - 1.0) * 100.0 if pd.notna(overall_latest) and overall_latest else np.nan
        rows.append(payload)
    return pd.DataFrame(rows).sort_values(["Dimension", "Series"], kind="stable").reset_index(drop=True)


def _capture_summary(transmission: pd.DataFrame, distribution: pd.DataFrame) -> dict:
    productivity = _index_summary(transmission, "Labor productivity")
    real_comp = _index_summary(transmission, "Real hourly compensation")
    labor_share = _index_summary(transmission, "Labor share")
    overall = distribution.loc[distribution.get("Series", pd.Series("", index=distribution.index)).astype(str).eq("All full-time workers")]
    median = overall.iloc[-1].to_dict() if not overall.empty else {}
    productivity_gap = np.nan
    if pd.notna(productivity.get("since_2020")) and pd.notna(real_comp.get("since_2020")):
        productivity_gap = float(productivity["since_2020"] - real_comp["since_2020"])
    sex_rows = distribution.loc[distribution.get("Dimension", pd.Series("", index=distribution.index)).astype(str).eq("Sex")]
    men = sex_rows.loc[sex_rows.get("Series", pd.Series("", index=sex_rows.index)).astype(str).eq("Men")]
    women = sex_rows.loc[sex_rows.get("Series", pd.Series("", index=sex_rows.index)).astype(str).eq("Women")]
    women_to_men = np.nan
    if not men.empty and not women.empty and float(men.iloc[-1]["Value"]) != 0:
        women_to_men = float(women.iloc[-1]["Value"] / men.iloc[-1]["Value"] * 100.0)
    group_growth = pd.to_numeric(distribution.loc[distribution["Series"].ne("All full-time workers"), "Since 2020"], errors="coerce").dropna()
    participation_spread = float(group_growth.max() - group_growth.min()) if not group_growth.empty else np.nan
    return {
        "productivity": productivity,
        "real_compensation": real_comp,
        "labor_share": labor_share,
        "median_real_earnings": median,
        "productivity_real_comp_gap": productivity_gap,
        "women_to_men_earnings_pct": women_to_men,
        "group_growth_spread_ppts": participation_spread,
    }


@st.cache_data(ttl=21600)
def load_economic_impact_data(force_refresh: bool = False, refresh_token: int = 0, allow_live: bool = False) -> dict:
    del refresh_token
    live_refresh = bool(force_refresh and allow_live)
    refresh_reports = {}
    if live_refresh:
        productivity, refresh_reports["productivity"] = refresh_templated_history(
            PRODUCTIVITY_PATH,
            start_date="2020-01-01",
            required_columns=("Series", "Metric", "Unit", "Source", "sector_name", "measure_text"),
        )
        investment, refresh_reports["investment"] = refresh_single_series(
            INVESTMENT_PATH,
            series_id="A679RX1Q020SBEA",
            output_date_column="Observation Date",
            output_value_column="Info Processing Investment Level",
            start_date="2007-01-01",
        )
        cpi, refresh_reports["cpi"] = refresh_single_series(
            CPI_PATH,
            series_id="CPIAUCSL",
            output_date_column="Date",
            output_value_column="CPI",
            start_date="2020-01-01",
        )
        transmission, refresh_reports["value_transmission"] = refresh_templated_history(
            TRANSMISSION_PATH,
            start_date="2020-01-01",
            required_columns=("Series", "Metric", "Unit", "Source", "Attribution boundary"),
        )
        distribution, refresh_reports["earnings_distribution"] = refresh_templated_history(
            DISTRIBUTION_PATH,
            start_date="2020-01-01",
            required_columns=("Series", "Dimension", "Metric", "Unit", "Seasonality", "Source", "Attribution boundary"),
        )
    else:
        productivity = _read(PRODUCTIVITY_PATH)
        investment = _read(INVESTMENT_PATH)
        cpi = _read(CPI_PATH)
        transmission = _read(TRANSMISSION_PATH)
        distribution = _read(DISTRIBUTION_PATH)

    if not investment.empty and "Observation Date" in investment.columns:
        investment = investment.loc[investment["Observation Date"] >= pd.Timestamp("2020-01-01")].reset_index(drop=True)
    distribution_summary = _distribution_summary(distribution)
    capture = _capture_summary(transmission, distribution_summary)

    modes = [str(report.get("source_mode", "")) for report in refresh_reports.values()]
    source_mode = (
        "live_refresh" if modes and all(mode == "live_refresh" for mode in modes)
        else "partial_refresh" if modes and any(mode in {"live_refresh", "partial_refresh"} for mode in modes)
        else "retained_fallback" if modes
        else "retained_official"
    )
    snapshot_dates = []
    for frame, column in [(productivity, "Date"), (transmission, "Date"), (distribution, "Date"), (investment, "Observation Date")]:
        if isinstance(frame, pd.DataFrame) and not frame.empty and column in frame.columns:
            snapshot_dates.append(pd.to_datetime(frame[column], errors="coerce", format="mixed").max())
    return {
        "source_mode": source_mode,
        "load_report": {"source_mode": source_mode, "datasets": refresh_reports},
        "productivity_history": productivity,
        "investment_history": investment,
        "cpi_history": cpi,
        "value_transmission_history": transmission,
        "earnings_distribution_history": distribution,
        "earnings_distribution_summary": distribution_summary,
        "capture_summary": capture,
        "nonfarm_productivity": _latest_metric(productivity, "Nonfarm Business", "Labor productivity (output per hour)"),
        "nonfarm_output": _latest_metric(productivity, "Nonfarm Business", "Real value-added output"),
        "nonfarm_compensation": _latest_metric(productivity, "Nonfarm Business", "Hourly compensation"),
        "nonfarm_unit_labor_cost": _latest_metric(productivity, "Nonfarm Business", "Unit labor costs"),
        "manufacturing_productivity": _latest_metric(productivity, "Manufacturing", "Labor productivity (output per hour)"),
        "manufacturing_output": _latest_metric(productivity, "Manufacturing", "Real value-added output"),
        "information_investment": _investment_summary(investment),
        "inflation": _inflation_summary(cpi),
        "snapshot_date": max([date for date in snapshot_dates if pd.notna(date)], default=pd.NaT),
        "source_manifest": pd.DataFrame([
            {"Dataset": "Productivity, output, compensation, and unit labor costs", "Source": "BLS Labor Productivity and Costs", "Frequency": "Quarterly", "Coverage": "2020-present", "Attribution boundary": "Realized macro outcomes; no causal attribution to AI."},
            {"Dataset": "Productivity, real compensation, and labor-share transmission", "Source": "BLS Labor Productivity and Costs", "Frequency": "Quarterly", "Coverage": "2020-present", "Attribution boundary": "Economy-wide worker-capture test. Labor share is an index, and none of the movement is assigned to AI alone."},
            {"Dataset": "Real median weekly earnings by sex and race/ethnicity", "Source": "BLS Current Population Survey", "Frequency": "Quarterly", "Coverage": "2020-present", "Attribution boundary": "Full-time wage and salary workers only. Group series show broad participation and distribution, not AI-specific effects or total household welfare."},
            {"Dataset": "Information-processing equipment and software investment", "Source": "BEA via FRED retained history", "Frequency": "Quarterly", "Coverage": "Chronology through latest retained release", "Attribution boundary": "Real chained-dollar investment in the broader information-processing asset class, not exclusively AI."},
            {"Dataset": "Consumer Price Index", "Source": "BLS via FRED retained history", "Frequency": "Monthly", "Coverage": "2020-present", "Attribution boundary": "Used only to express nominal compensation and unit-labor-cost growth in inflation-adjusted terms."},
        ]),
    }
