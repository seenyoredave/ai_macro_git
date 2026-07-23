"""Rebuild derived history from preserved raw archives.

This script intentionally treats calculated archives as disposable. It never
modifies the raw YFinance, EDGAR, or benchmark observations. It rebuilds:

- sector AEI scores from archived company and benchmark observations;
- macro AEI and concentration HHI;
- release-aware Power Stress and its raw FRED inputs;
- ADI and its four pillars where the 3-of-4 data contract is met;
- Capital Stress where archived financial fields and filing disclosures exist;
- Speculation Gap = AEI - ADI.

Pressure v2 is rebuilt only when its four price/volume inputs were actually
archived. Older pressure values are retained in an explicit Legacy Pressure
column rather than being mislabeled as Pressure v2.
"""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analytics.capital_stress_engine import calculate_capital_stress
from analytics.development_engine import calculate_ai_development_intensity
from analytics.factor_engine import (
    calc_dispersion,
    calc_earnings_yield_discount,
    calc_momentum_breadth,
    calc_relative_performance,
)
from analytics.hhi_engine import calc_hhi_from_sector_data, normalize_hhi
from analytics.power_engine import calculate_power_stress
from analytics.regime_engine import calc_aei, calc_avg_sector_pressure
from analytics.sector_engine import (
    calc_sector_scores,
    calc_trading_pressure,
    normalize_factor_table,
)

ARCHIVE_DIR = PROJECT_ROOT / "archive"
DATA_DIR = PROJECT_ROOT / "data"

AEI_VERSION = "2.0"
ADI_VERSION = "1.0"
POWER_STRESS_VERSION = "3.0"
CAPITAL_STRESS_VERSION = "2.0"
PRESSURE_VERSION = "2.0"

RAW_FINANCIAL_COLUMNS = [
    "Revenue",
    "Revenue Growth",
    "CapEx",
    "CapEx Growth",
    "Operating Cash Flow",
    "Free Cash Flow",
    "Net Income",
    "EBITDA",
    "Total Debt",
    "Cash",
    "Net Debt",
]

EDGAR_OVERRIDE_COLUMNS = [
    "Revenue",
    "Revenue Growth",
    "CapEx",
    "CapEx Growth",
]

PRESSURE_RAW_COLUMNS = [
    "Price Extension 200D",
    "Momentum Acceleration",
    "Volatility Expansion",
    "Volume Activity",
]

SECTOR_ALIAS_FOR_ADI = {
    "SEMICAP_SUPPLY_CHAIN": "SEMICAP_EQUIPMENT",
}


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path)


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    """Write derived archives deterministically.

    Derived values are rounded only at CSV serialization precision; raw source
    archives are never passed through this writer.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, float_format="%.12g")


def _as_date(value) -> pd.Timestamp:
    return pd.to_datetime(value, errors="coerce", format="mixed").normalize()


def _latest_available_date(dates: pd.Series, target) -> str | None:
    target_ts = _as_date(target)
    parsed = pd.to_datetime(dates, errors="coerce", format="mixed").dt.normalize()
    valid = parsed[parsed.notna() & (parsed <= target_ts)]
    if valid.empty:
        return None
    return valid.max().date().isoformat()


def _latest_rows_as_of(df: pd.DataFrame, target_date, keys: list[str]) -> pd.DataFrame:
    if df is None or df.empty or "Date" not in df.columns:
        return pd.DataFrame()

    target = _as_date(target_date)
    out = df.copy()
    out["_date"] = pd.to_datetime(out["Date"], errors="coerce", format="mixed").dt.normalize()
    out = out.loc[out["_date"].notna() & (out["_date"] <= target)].copy()
    if out.empty:
        return out

    out = out.sort_values(keys + ["_date"], kind="stable")
    out = out.groupby(keys, as_index=False, dropna=False).tail(1)
    return out.drop(columns=["_date"], errors="ignore").reset_index(drop=True)


def _overlay_edgar(yf_rows: pd.DataFrame, edgar_rows: pd.DataFrame) -> pd.DataFrame:
    out = yf_rows.copy()
    if out.empty or edgar_rows is None or edgar_rows.empty:
        return out

    available = [c for c in EDGAR_OVERRIDE_COLUMNS if c in edgar_rows.columns]
    if not available:
        return out

    ed = edgar_rows[["Ticker"] + available].copy()
    ed["Ticker"] = ed["Ticker"].astype(str).str.upper().str.strip()
    ed = ed.drop_duplicates("Ticker", keep="last").set_index("Ticker")

    out["Ticker"] = out["Ticker"].astype(str).str.upper().str.strip()
    for col in available:
        if col not in out.columns:
            out[col] = np.nan
        mapped = out["Ticker"].map(ed[col])
        out[col] = mapped.where(mapped.notna(), out[col])

    return out


def _sector_data_as_of(
    yf_history: pd.DataFrame,
    edgar_history: pd.DataFrame,
    target_date,
) -> tuple[dict[str, pd.DataFrame], str | None]:
    market_date = _latest_available_date(yf_history["Date"], target_date)
    if market_date is None:
        return {}, None

    rows = yf_history.loc[yf_history["Date"].astype(str) == market_date].copy()
    edgar_rows = _latest_rows_as_of(edgar_history, target_date, ["Ticker"])
    rows = _overlay_edgar(rows, edgar_rows)

    sector_data: dict[str, pd.DataFrame] = {}
    for sector, group in rows.groupby("Sector", sort=False):
        sector_name = SECTOR_ALIAS_FOR_ADI.get(str(sector), str(sector))
        group = group.copy().reset_index(drop=True)

        # Keep the original sector grouping for AEI/HHI, but add the alias in a
        # separate merged view where ADI needs a current sector name.
        sector_data[str(sector)] = group
        if sector_name != str(sector):
            if sector_name in sector_data:
                sector_data[sector_name] = pd.concat(
                    [sector_data[sector_name], group], ignore_index=True, sort=False
                )
            else:
                sector_data[sector_name] = group.copy()

    return sector_data, market_date


def _benchmark_as_of(benchmark_history: pd.DataFrame, target_date) -> dict:
    if benchmark_history.empty:
        return {"avg_return": np.nan, "forward_pe": np.nan}

    rows = benchmark_history[
        benchmark_history["Benchmark"].astype(str).str.upper() == "QQQ"
    ].copy()
    date_value = _latest_available_date(rows["Date"], target_date)
    if date_value is None:
        return {"avg_return": np.nan, "forward_pe": np.nan}

    row = rows.loc[rows["Date"].astype(str) == date_value].iloc[-1]
    return {
        "avg_return": pd.to_numeric(row.get("Avg Return"), errors="coerce"),
        "forward_pe": pd.to_numeric(row.get("Forward P/E"), errors="coerce"),
    }


def _factor_frame(sector: str, df: pd.DataFrame, benchmark: dict) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Sector": sector,
                "Factor": "relative_performance",
                "Value": calc_relative_performance(df, benchmark.get("avg_return")),
            },
            {
                "Sector": sector,
                "Factor": "earnings_yield_discount",
                "Value": calc_earnings_yield_discount(df, benchmark.get("forward_pe")),
            },
            {
                "Sector": sector,
                "Factor": "momentum_breadth",
                "Value": calc_momentum_breadth(df),
            },
            {
                "Sector": sector,
                "Factor": "dispersion",
                "Value": calc_dispersion(df),
            },
        ]
    )


def _mean_numeric(df: pd.DataFrame, column: str) -> float:
    if df is None or df.empty or column not in df.columns:
        return np.nan
    values = pd.to_numeric(df[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
    return float(values.mean()) if values.notna().any() else np.nan


def _sector_metrics_for_date(
    yf_history: pd.DataFrame,
    edgar_history: pd.DataFrame,
    benchmark_history: pd.DataFrame,
    target_date,
) -> tuple[dict[str, dict], dict[str, pd.DataFrame], str | None]:
    sector_data, market_date = _sector_data_as_of(yf_history, edgar_history, target_date)
    if not sector_data or market_date is None:
        return {}, {}, market_date

    # AEI should use the sectors actually present in the archived market
    # snapshot. Alias-only ADI frames are excluded from this loop.
    original_rows = yf_history.loc[yf_history["Date"].astype(str) == market_date]
    original_sectors = list(dict.fromkeys(original_rows["Sector"].astype(str).tolist()))
    benchmark = _benchmark_as_of(benchmark_history, market_date)

    metrics: dict[str, dict] = {}
    for sector in original_sectors:
        df = sector_data.get(sector, pd.DataFrame())
        factor_df = _factor_frame(sector, df, benchmark)
        normalized = normalize_factor_table(factor_df)
        score = calc_sector_scores(normalized)
        pressure, _ = calc_trading_pressure(df, factor_df)
        metrics[sector] = {
            "Sector Score": score,
            "Sector Pressure": pressure,
            "Forward P/E": _mean_numeric(df, "Forward P/E"),
            "Avg Return": _mean_numeric(df, "1Y Return"),
        }

    return metrics, sector_data, market_date


def _load_power_sources() -> tuple[pd.DataFrame, pd.DataFrame]:
    series = _read_csv(DATA_DIR / "power_series_history.csv")
    releases = _read_csv(DATA_DIR / "power_release_calendar.csv")
    series["Observation Date"] = pd.to_datetime(series["Observation Date"], errors="coerce")
    releases["Release Date"] = pd.to_datetime(releases["Release Date"], errors="coerce")
    releases["Sales Observation Date"] = pd.to_datetime(
        releases["Sales Observation Date"], errors="coerce"
    )
    releases["System Observation Date"] = pd.to_datetime(
        releases["System Observation Date"], errors="coerce"
    )
    return series, releases.sort_values("Release Date")


def _series_value(series: pd.DataFrame, observation_date, column: str) -> float:
    date_value = _as_date(observation_date)
    rows = series.loc[series["Observation Date"] == date_value]
    if rows.empty or column not in rows.columns:
        return np.nan
    return pd.to_numeric(rows.iloc[-1][column], errors="coerce")


def _yoy(series: pd.DataFrame, observation_date, column: str) -> float:
    date_value = _as_date(observation_date)
    current = _series_value(series, date_value, column)
    prior = _series_value(series, date_value - pd.DateOffset(years=1), column)
    if pd.isna(current) or pd.isna(prior) or prior == 0:
        return np.nan
    return float(current / prior - 1.0)


def _power_payload_for_date(
    target_date,
    series: pd.DataFrame,
    releases: pd.DataFrame,
) -> tuple[dict, dict]:
    target = _as_date(target_date)
    eligible = releases.loc[releases["Release Date"] <= target]
    if eligible.empty:
        release = releases.iloc[0]
    else:
        release = eligible.iloc[-1]

    sales_date = release["Sales Observation Date"]
    system_date = release["System Observation Date"]

    commercial = _series_value(series, sales_date, "Commercial Electricity Sales")
    residential = _series_value(series, sales_date, "Residential Electricity Sales")
    utilization = _series_value(series, system_date, "Electric Power Capacity Utilization")
    output = _series_value(series, system_date, "Electric Power Output")
    capacity = _series_value(series, system_date, "Electric Power Capacity")

    commercial_yoy = _yoy(series, sales_date, "Commercial Electricity Sales")
    residential_yoy = _yoy(series, sales_date, "Residential Electricity Sales")
    output_yoy = _yoy(series, system_date, "Electric Power Output")
    capacity_yoy = _yoy(series, system_date, "Electric Power Capacity")

    payload = {
        "Commercial Electricity Sales YoY": {"value": commercial_yoy},
        "Residential Electricity Sales YoY": {"value": residential_yoy},
        "Electric Power Capacity Utilization": {"value": utilization},
        "Electric Power Output YoY": {"value": output_yoy},
        "Electric Power Capacity YoY": {"value": capacity_yoy},
    }

    raw = {
        "Commercial Electricity Sales": commercial,
        "Commercial Electricity Sales Date": sales_date.date().isoformat(),
        "Residential Electricity Sales": residential,
        "Residential Electricity Sales Date": sales_date.date().isoformat(),
        "Commercial Electricity Sales YoY": commercial_yoy,
        "Commercial Electricity Sales YoY Date": sales_date.date().isoformat(),
        "Residential Electricity Sales YoY": residential_yoy,
        "Residential Electricity Sales YoY Date": sales_date.date().isoformat(),
        "Electric Power Capacity Utilization": utilization,
        "Electric Power Capacity Utilization Date": system_date.date().isoformat(),
        "Electric Power Output": output,
        "Electric Power Output Date": system_date.date().isoformat(),
        "Electric Power Output YoY": output_yoy,
        "Electric Power Output YoY Date": system_date.date().isoformat(),
        "Electric Power Capacity": capacity,
        "Electric Power Capacity Date": system_date.date().isoformat(),
        "Electric Power Capacity YoY": capacity_yoy,
        "Electric Power Capacity YoY Date": system_date.date().isoformat(),
        "Power Release Date": release["Release Date"].date().isoformat(),
    }
    return payload, raw




def _power_payload_from_fred_archive(
    target_date,
    fred_history: pd.DataFrame,
) -> tuple[dict, dict]:
    """Use the latest complete archived power observation available by date."""
    required = [
        "Commercial Electricity Sales YoY",
        "Residential Electricity Sales YoY",
        "Electric Power Capacity Utilization",
        "Electric Power Output YoY",
        "Electric Power Capacity YoY",
    ]
    if fred_history is None or fred_history.empty:
        return {}, {}

    working = fred_history.copy()
    working["_date"] = pd.to_datetime(
        working["Date"], errors="coerce", format="mixed"
    ).dt.normalize()
    target = _as_date(target_date)
    working = working.loc[working["_date"].notna() & (working["_date"] <= target)].copy()
    if working.empty:
        return {}, {}

    for column in required:
        if column not in working.columns:
            return {}, {}
        working[column] = pd.to_numeric(working[column], errors="coerce")

    working = working.dropna(subset=required).sort_values("_date", kind="stable")
    if working.empty:
        return {}, {}

    row = working.iloc[-1]
    payload = {name: {"value": row.get(name, np.nan)} for name in required}

    raw_columns = [
        "Commercial Electricity Sales",
        "Commercial Electricity Sales Date",
        "Residential Electricity Sales",
        "Residential Electricity Sales Date",
        "Commercial Electricity Sales YoY",
        "Commercial Electricity Sales YoY Date",
        "Residential Electricity Sales YoY",
        "Residential Electricity Sales YoY Date",
        "Electric Power Capacity Utilization",
        "Electric Power Capacity Utilization Date",
        "Electric Power Output",
        "Electric Power Output Date",
        "Electric Power Output YoY",
        "Electric Power Output YoY Date",
        "Electric Power Capacity",
        "Electric Power Capacity Date",
        "Electric Power Capacity YoY",
        "Electric Power Capacity YoY Date",
        "Power Release Date",
    ]
    raw = {column: row.get(column, np.nan) for column in raw_columns}
    return payload, raw


def _load_construction_sources() -> tuple[pd.DataFrame, pd.DataFrame]:
    history = _read_csv(DATA_DIR / "data_center_construction_history.csv")
    calendar = _read_csv(DATA_DIR / "construction_release_calendar.csv")
    history["Observation Date"] = pd.to_datetime(history["Observation Date"], errors="coerce")
    calendar["Release Date"] = pd.to_datetime(calendar["Release Date"], errors="coerce")
    calendar["Observation Date"] = pd.to_datetime(calendar["Observation Date"], errors="coerce")
    return history, calendar.sort_values("Release Date")


def _construction_for_date(target_date, history: pd.DataFrame, calendar: pd.DataFrame) -> dict:
    target = _as_date(target_date)
    eligible = calendar.loc[calendar["Release Date"] <= target]
    if eligible.empty:
        row = calendar.iloc[0]
    else:
        row = eligible.iloc[-1]

    observation_date = row["Observation Date"]
    current = history.loc[history["Observation Date"] == observation_date]
    prior = history.loc[
        history["Observation Date"] == observation_date - pd.DateOffset(years=1)
    ]
    if current.empty:
        return {}

    current_row = current.iloc[-1]
    value = pd.to_numeric(current_row["Data Center Construction"], errors="coerce")
    nonres = pd.to_numeric(
        current_row["Private Nonresidential Construction"], errors="coerce"
    )
    prior_value = (
        pd.to_numeric(prior.iloc[-1]["Data Center Construction"], errors="coerce")
        if not prior.empty
        else np.nan
    )

    yoy = value / prior_value - 1.0 if pd.notna(value) and pd.notna(prior_value) and prior_value else np.nan
    share = value / nonres if pd.notna(value) and pd.notna(nonres) and nonres else np.nan

    return {
        "value": value,
        "date": observation_date.date().isoformat(),
        "release_date": row["Release Date"].date().isoformat(),
        "yoy_growth": yoy,
        "share_private_nonresidential": share,
        "source": "Census Historical Workbook",
    }


def _component_value(result: dict, name: str, field: str = "score"):
    return ((result or {}).get("components", {}).get(name, {}) or {}).get(field, np.nan)


def rebuild_fred_history(
    fred_history: pd.DataFrame,
    power_series: pd.DataFrame,
    power_releases: pd.DataFrame,
) -> pd.DataFrame:
    if fred_history.empty:
        return fred_history

    out = fred_history.copy()
    raw_rows = []
    for date_value in out["Date"].astype(str):
        _, raw = _power_payload_for_date(date_value, power_series, power_releases)
        raw_rows.append(raw)
    raw_df = pd.DataFrame(raw_rows, index=out.index)

    for column in raw_df.columns:
        out[column] = raw_df[column]

    return out


def rebuild_sector_history(
    yf_history: pd.DataFrame,
    edgar_history: pd.DataFrame,
    benchmark_history: pd.DataFrame,
    prior_sector_history: pd.DataFrame,
) -> pd.DataFrame:
    legacy_lookup = {}
    if not prior_sector_history.empty:
        for _, row in prior_sector_history.iterrows():
            key = (str(row.get("Date")), str(row.get("Sector")))
            value = pd.to_numeric(row.get("Legacy Pressure", row.get("Pressure")), errors="coerce")
            legacy_lookup[key] = value

    rows = []
    for target_date in sorted(yf_history["Date"].astype(str).unique()):
        metrics, _, market_date = _sector_metrics_for_date(
            yf_history,
            edgar_history,
            benchmark_history,
            target_date,
        )
        if market_date != target_date:
            continue

        for sector, values in metrics.items():
            pressure = pd.to_numeric(values.get("Sector Pressure"), errors="coerce")
            rows.append(
                {
                    "Date": target_date,
                    "Sector": sector,
                    "Sector Score": values.get("Sector Score", np.nan),
                    "Pressure": pressure,
                    "Forward P/E": values.get("Forward P/E", np.nan),
                    "Avg Return": values.get("Avg Return", np.nan),
                    "AEI Version": AEI_VERSION,
                    "Pressure Version": PRESSURE_VERSION if pd.notna(pressure) else pd.NA,
                    "Legacy Pressure": legacy_lookup.get((target_date, sector), np.nan),
                }
            )

    return pd.DataFrame(rows).sort_values(["Date", "Sector"], kind="stable").reset_index(drop=True)


def rebuild_macro_history(
    prior_macro_history: pd.DataFrame,
    sector_history: pd.DataFrame,
    yf_history: pd.DataFrame,
    edgar_history: pd.DataFrame,
    benchmark_history: pd.DataFrame,
    fred_history: pd.DataFrame,
    construction_history: pd.DataFrame,
    construction_calendar: pd.DataFrame,
) -> pd.DataFrame:
    context_columns = [
        "Consumer Sentiment",
        "Fed Funds Rate",
        "Industrial Production",
        "Industrial Production YoY",
    ]

    prior_by_date = prior_macro_history.set_index("Date", drop=False) if not prior_macro_history.empty else pd.DataFrame()
    legacy_pressure = {}
    if not prior_macro_history.empty:
        for _, row in prior_macro_history.iterrows():
            legacy_pressure[str(row.get("Date"))] = pd.to_numeric(
                row.get("Legacy Avg Sector Pressure", row.get("Avg Sector Pressure")),
                errors="coerce",
            )

    rows = []
    target_dates = sorted(prior_macro_history["Date"].astype(str).unique())
    for target_date in target_dates:
        metrics, sector_data, market_date = _sector_metrics_for_date(
            yf_history,
            edgar_history,
            benchmark_history,
            target_date,
        )

        aei = calc_aei(metrics)
        avg_pressure = calc_avg_sector_pressure(metrics)
        raw_hhi = calc_hhi_from_sector_data(
            {k: v for k, v in sector_data.items() if k in metrics}
        ) if sector_data else np.nan
        hhi = normalize_hhi(raw_hhi)

        power_payload, power_raw = _power_payload_from_fred_archive(
            target_date, fred_history
        )
        power_result = calculate_power_stress(power_payload)
        construction = _construction_for_date(
            target_date, construction_history, construction_calendar
        )
        development = calculate_ai_development_intensity(
            sector_data,
            construction_data=construction,
            power_result=power_result,
        )
        capital = calculate_capital_stress(
            sector_data,
            as_of_date=target_date,
        )

        adi = pd.to_numeric(development.get("score"), errors="coerce")
        power_score = pd.to_numeric(power_result.get("score"), errors="coerce")
        capital_score = pd.to_numeric(capital.get("score"), errors="coerce")
        speculation = float(aei - adi) if pd.notna(aei) and pd.notna(adi) else np.nan

        row = {
            "Date": target_date,
            "Market Data Date": market_date,
            "AI Equity Index": aei,
            "AI Development Intensity": adi,
            "Speculation Gap": speculation,
            "Power Stress Index": power_score,
            "Capital Stress": capital_score,
            "Concentration HHI": hhi,
            "Raw AI HHI": raw_hhi,
            "Avg Sector Pressure": avg_pressure,
            "Legacy Avg Sector Pressure": legacy_pressure.get(target_date, np.nan),
            "ADI Capital Deployment": _component_value(development, "Capital Deployment"),
            "ADI Data Center Construction": _component_value(development, "Data Center Construction"),
            "ADI Compute Supply Realization": _component_value(development, "Compute Supply Realization"),
            "ADI Power Footprint": _component_value(development, "Power Footprint"),
            "Power Nonresidential Load": _component_value(power_result, "Nonresidential Load Pressure"),
            "Power Grid Utilization": _component_value(power_result, "Grid Utilization Pressure"),
            "Power Capacity Response": _component_value(power_result, "Capacity Response Gap"),
            "Capital Cash Flow Strain": _component_value(capital, "Cash Flow Strain"),
            "Capital Book Leverage": _component_value(capital, "Book Leverage"),
            "Capital Committed Burden": _component_value(capital, "Committed Burden"),
            "Capital Contingent Exposure": _component_value(capital, "Contingent Exposure"),
            "AEI Version": AEI_VERSION if pd.notna(aei) else pd.NA,
            "ADI Version": ADI_VERSION if pd.notna(adi) else pd.NA,
            "Power Stress Version": POWER_STRESS_VERSION if pd.notna(power_score) else pd.NA,
            "Capital Stress Version": CAPITAL_STRESS_VERSION if pd.notna(capital_score) else pd.NA,
            "Pressure Version": PRESSURE_VERSION if pd.notna(avg_pressure) else pd.NA,
            "Construction Observation Date": construction.get("date"),
            "Construction Release Date": construction.get("release_date"),
            **power_raw,
        }

        if not prior_macro_history.empty and target_date in prior_by_date.index:
            prior_row = prior_by_date.loc[target_date]
            if isinstance(prior_row, pd.DataFrame):
                prior_row = prior_row.iloc[-1]
            for column in context_columns:
                row[column] = prior_row.get(column, np.nan)

        rows.append(row)

    return pd.DataFrame(rows).sort_values("Date", kind="stable").reset_index(drop=True)


def validate_rebuild(
    macro: pd.DataFrame,
    sector: pd.DataFrame,
    yf_raw_before: pd.DataFrame,
    yf_raw_after: pd.DataFrame,
    edgar_raw_before: pd.DataFrame,
    edgar_raw_after: pd.DataFrame,
    benchmark_raw_before: pd.DataFrame,
    benchmark_raw_after: pd.DataFrame,
) -> None:
    if not yf_raw_before.equals(yf_raw_after):
        raise AssertionError("Raw YFinance archive changed during derived-history rebuild")
    if not edgar_raw_before.equals(edgar_raw_after):
        raise AssertionError("Raw EDGAR archive changed during derived-history rebuild")
    if not benchmark_raw_before.equals(benchmark_raw_after):
        raise AssertionError("Raw benchmark archive changed during derived-history rebuild")

    if macro.empty or sector.empty:
        raise AssertionError("Rebuild produced an empty derived archive")

    for column in ["AI Equity Index", "Power Stress Index", "Concentration HHI"]:
        if column not in macro.columns or not pd.to_numeric(macro[column], errors="coerce").notna().any():
            raise AssertionError(f"Rebuild failed to produce {column}")

    valid_power_versions = set(macro.loc[macro["Power Stress Index"].notna(), "Power Stress Version"].dropna().astype(str))
    if valid_power_versions != {POWER_STRESS_VERSION}:
        raise AssertionError(f"Mixed Power Stress versions remain: {valid_power_versions}")

    valid_aei_versions = set(macro.loc[macro["AI Equity Index"].notna(), "AEI Version"].dropna().astype(str))
    if valid_aei_versions != {AEI_VERSION}:
        raise AssertionError(f"Mixed AEI versions remain: {valid_aei_versions}")


def main() -> None:
    yf_path = ARCHIVE_DIR / "yf_history.csv"
    edgar_path = ARCHIVE_DIR / "edgar_history.csv"
    benchmark_path = ARCHIVE_DIR / "benchmark_history.csv"
    fred_path = ARCHIVE_DIR / "fred_history.csv"
    sector_path = ARCHIVE_DIR / "sector_history.csv"
    macro_path = ARCHIVE_DIR / "macro_history.csv"

    yf_history = _read_csv(yf_path)
    edgar_history = _read_csv(edgar_path)
    benchmark_history = _read_csv(benchmark_path)
    fred_history = _read_csv(fred_path)
    prior_sector = _read_csv(sector_path)
    prior_macro = _read_csv(macro_path)

    yf_before = yf_history.copy(deep=True)
    edgar_before = edgar_history.copy(deep=True)
    benchmark_before = benchmark_history.copy(deep=True)

    power_series, power_releases = _load_power_sources()
    construction_history, construction_calendar = _load_construction_sources()

    rebuilt_fred = rebuild_fred_history(fred_history, power_series, power_releases)
    rebuilt_sector = rebuild_sector_history(
        yf_history,
        edgar_history,
        benchmark_history,
        prior_sector,
    )
    rebuilt_macro = rebuild_macro_history(
        prior_macro,
        rebuilt_sector,
        yf_history,
        edgar_history,
        benchmark_history,
        rebuilt_fred,
        construction_history,
        construction_calendar,
    )

    validate_rebuild(
        rebuilt_macro,
        rebuilt_sector,
        yf_before,
        yf_history,
        edgar_before,
        edgar_history,
        benchmark_before,
        benchmark_history,
    )

    _write_csv(rebuilt_fred, fred_path)
    _write_csv(rebuilt_sector, sector_path)
    _write_csv(rebuilt_macro, macro_path)

    print(
        "Rebuilt derived history: "
        f"{len(rebuilt_sector)} sector rows, "
        f"{len(rebuilt_macro)} macro rows, "
        f"{len(rebuilt_fred)} FRED rows."
    )


if __name__ == "__main__":
    main()
