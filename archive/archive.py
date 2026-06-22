import pandas as pd
import numpy as np

from pathlib import Path
from datetime import datetime

from benchmarks.benchmark_service import get_benchmark_metrics
from config.benchmark_config import BENCHMARK_UNIVERSES

from analytics.hhi_engine import calc_hhi_from_sector_data
from analytics.power_engine import calculate_power_stress_zscore
from archive.archive_reader import load_fred_history

from helpers.macro_normalization import (
    normalize_power_stress,
    normalize_hhi
)


def write_archive_snapshot(
    snapshot,
    archive_path,
    replace_today=True
):
    archive_file = Path(archive_path)

    today = str(datetime.now().date())

    snapshot = snapshot.copy()

    if archive_file.exists() and archive_file.stat().st_size > 0:
        existing = pd.read_csv(archive_file)

        if replace_today and "Date" in existing.columns:
            existing["Date"] = existing["Date"].astype(str)

            existing = existing[
                existing["Date"] != today
            ]

        combined = pd.concat(
            [existing, snapshot],
            ignore_index=True
        )

        combined.to_csv(
            archive_file,
            index=False
        )

    else:
        snapshot.to_csv(
            archive_file,
            index=False
        )

def append_dataframe_history(df, archive_path):
    snapshot = df.copy()

    snapshot.insert(
        0,
        "Date",
        datetime.now().date()
    )

    write_archive_snapshot(
        snapshot,
        archive_path
    )

def append_macro_history(
    sector_metrics,
    fred_data,
    market_sentiment,
    sector_data=None,
):
    sector_score = [
        metrics.get("Sector Score", np.nan)
        for metrics in sector_metrics.values()
    ]

    pressure_scores = [
        metrics.get("Sector Pressure", np.nan)
        for metrics in sector_metrics.values()
    ]

    fred_history = load_fred_history()

    raw_power_stress = calculate_power_stress_zscore(
        fred_history,
        column="Industrial Production",
        lookback=24
    )

    power_stress = normalize_power_stress(raw_power_stress)

    raw_hhi = (
        calc_hhi_from_sector_data(sector_data)
        if sector_data is not None
        else np.nan
    )

    ai_concentration_hhi = normalize_hhi(raw_hhi)

    avg_maturation_index = np.nanmean(sector_score)
    
    avg_pressure = np.nanmean(pressure_scores)

    row = {
        "Date": datetime.now().date(),

        "Maturation Index": avg_maturation_index,
        "Divergence": avg_maturation_index - avg_pressure,

        "Power Stress Index": power_stress,
        "Raw Power Stress Z": raw_power_stress,

        "Concentration HHI": ai_concentration_hhi,
        "Raw AI HHI": raw_hhi,

        "Avg Pressure": avg_pressure,
        "Put/Call Ratio": market_sentiment.get("PutCallRatio", np.nan),
        "Consumer Sentiment": fred_data.get("Consumer Sentiment", {}).get("value", np.nan),
        "Fed Funds Rate": fred_data.get("Fed Funds Rate", {}).get("value", np.nan),
        "Industrial Production": fred_data.get("Industrial Production", {}).get("value", np.nan),
    }

    snapshot = pd.DataFrame([row])

    write_archive_snapshot(
        snapshot,
        "archive/macro_history.csv"
    )

def append_sector_history(sector_metrics):
    rows = []

    for sector, metrics in sector_metrics.items():
        rows.append({
            "Date": datetime.now().date(),
            "Sector": sector,
            "Sector Score": metrics.get("Sector Score"),
            "Pressure": metrics.get("Sector Pressure"),
            "Forward P/E": metrics.get("Forward P/E"),
            "Avg Return": metrics.get("Avg Return"),
        })

    snapshot = pd.DataFrame(rows)

    write_archive_snapshot(
        snapshot,
        "archive/sector_history.csv"
    )

def append_benchmark_history():
    rows = []

    for benchmark in BENCHMARK_UNIVERSES.keys():
        metrics = get_benchmark_metrics(benchmark)

        rows.append({
            "Date": datetime.now().date(),
            "Benchmark": benchmark,
            "Forward P/E": metrics.get("forward_pe"),
            "Avg Return": metrics.get("avg_return"),
            "Beta": metrics.get("beta"),
            "Member Count": metrics.get("member_count"),
        })

    snapshot = pd.DataFrame(rows)

    write_archive_snapshot(
        snapshot,
        "archive/benchmark_history.csv"
    )

def append_yf_history(sector_data):
    rows = []

    yf_cols = [
        "Ticker",
        "Company",
        "Price",
        "P/E",
        "Forward P/E",
        "Market Cap",
        "Revenue",
        "Revenue Growth",
        "CapEx",
        "CapEx Growth",
        "Beta",
        "52W High",
        "52W Low",
        "1Y Return",
        "Basket Score",
        "Basket Tier",
        "Basket Weight",
    ]

    for sector, df in sector_data.items():
        if df is None or df.empty:
            continue

        available = [
            col for col in yf_cols
            if col in df.columns
        ]

        temp = df[available].copy()
        temp.insert(0, "Sector", sector)

        rows.append(temp)

    if not rows:
        return

    snapshot = pd.concat(
        rows,
        ignore_index=True
    )

    append_dataframe_history(
        snapshot,
        "archive/yf_history.csv"
    )

def append_edgar_history(sector_data):
    rows = []

    edgar_cols = [
        "Ticker",
        "Company",
        "Market Cap",
        "Revenue",
        "Revenue Growth"
    ]

    for sector, df in sector_data.items():
        if df is None or df.empty:
            continue

        available = [
            col for col in edgar_cols
            if col in df.columns
        ]

        temp = df[available].copy()
        temp.insert(0, "Sector", sector)

        rows.append(temp)

    if not rows:
        return

    snapshot = pd.concat(
        rows,
        ignore_index=True
    )

    append_dataframe_history(
        snapshot,
        "archive/edgar_history.csv"
    )

def append_fred_history(fred_data):
    row = {
        "Date": datetime.now().date()
    }

    for indicator, payload in fred_data.items():
        if isinstance(payload, dict):
            row[indicator] = payload.get("value", np.nan)
        else:
            row[indicator] = payload

    snapshot = pd.DataFrame([row])

    write_archive_snapshot(
        snapshot,
        "archive/fred_history.csv"
    )

def append_put_call_history(market_sentiment):
    row = {
        "Date": datetime.now().date(),
        "PutCallRatio": market_sentiment.get("PutCallRatio", np.nan),
    }

    snapshot = pd.DataFrame([row])

    write_archive_snapshot(
        snapshot,
        "archive/put_call_history.csv"
    )
