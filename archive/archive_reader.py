from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from config.market_clock import market_date

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_DIR = PROJECT_ROOT / "archive"

def resolve_archive_path(archive_path: str | Path) -> Path:
    path = Path(archive_path)

    if path.is_absolute():
        return path

    if path.parts and path.parts[0] == "archive":
        return PROJECT_ROOT / path

    return ARCHIVE_DIR / path

ARCHIVE_PATHS = {
    "benchmark": ARCHIVE_DIR / "benchmark_history.csv",
    "edgar": ARCHIVE_DIR / "edgar_history.csv",
    "energy": ARCHIVE_DIR / "energy_history.csv",
    "fred": ARCHIVE_DIR / "fred_history.csv",
    "macro": ARCHIVE_DIR / "macro_history.csv",
    "sector": ARCHIVE_DIR / "sector_history.csv",
    "yf": ARCHIVE_DIR / "yf_history.csv",
}

ARCHIVE_KEYS = {
    "benchmark": ["Date", "Benchmark"],
    "edgar": ["Date", "Sector", "Ticker"],
    "energy": ["Date"],
    "fred": ["Date"],
    "macro": ["Date"],
    "sector": ["Date", "Sector"],
    "yf": ["Date", "Sector", "Ticker"],
}

EDGAR_REQUIRED_COLUMNS = [
    "Date",
    "Sector",
    "Ticker",
    "Revenue",
    "Revenue Growth",
    "CapEx",
    "CapEx Growth",
    "Revenue FY",
    "CapEx FY",
    "CIK",
    "EDGAR Status",
]

def today_iso() -> str:
    return market_date().isoformat()

def parse_archive_dates(values) -> pd.Series:
    return pd.to_datetime(
        values,
        errors="coerce",
        format="mixed",
    ).dt.date

def normalize_date_column(df: pd.DataFrame, date_col: str = "Date") -> pd.DataFrame:
    df = df.copy()

    if date_col not in df.columns:
        return df

    parsed = parse_archive_dates(df[date_col])
    df = df.loc[parsed.notna()].copy()
    parsed = parsed.loc[df.index]
    df[date_col] = parsed.map(lambda d: d.isoformat())

    return df

def is_blank(value) -> bool:
    if value is None:
        return True

    try:
        if pd.isna(value):
            return True
    except Exception:
        pass

    if isinstance(value, str) and value.strip() == "":
        return True

    return False

def is_valid_value(value) -> bool:
    return not is_blank(value)

def normalize_key_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "Ticker" in df.columns:
        df["Ticker"] = df["Ticker"].astype(str).str.upper().str.strip()

    if "Sector" in df.columns:
        df["Sector"] = df["Sector"].astype(str).str.strip()

    if "Benchmark" in df.columns:
        df["Benchmark"] = df["Benchmark"].astype(str).str.upper().str.strip()

    return df

def read_archive(
    archive_path: str | Path,
    required_columns: Optional[Sequence[str]] = None,
    normalize_dates: bool = True,
) -> pd.DataFrame:
    path = resolve_archive_path(archive_path)

    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()

    df = pd.read_csv(path)

    if df.empty:
        return df

    df = df.dropna(how="all").copy()
    df = normalize_key_columns(df)

    if normalize_dates and "Date" in df.columns:
        df = normalize_date_column(df, "Date")

    if required_columns:
        for col in required_columns:
            if col not in df.columns:
                df[col] = np.nan

    return df

def load_benchmark_history():
    return read_archive(ARCHIVE_PATHS["benchmark"])

def load_edgar_history():
    return read_archive(
        ARCHIVE_PATHS["edgar"],
        required_columns=EDGAR_REQUIRED_COLUMNS,
    )

def load_energy_history():
    return read_archive(ARCHIVE_PATHS["energy"])

def load_fred_history():
    return read_archive(ARCHIVE_PATHS["fred"])

def load_macro_history():
    return read_archive(ARCHIVE_PATHS["macro"])

def load_sector_history():
    return read_archive(ARCHIVE_PATHS["sector"])

def load_yf_history():
    return read_archive(ARCHIVE_PATHS["yf"])

def rows_for_date(
    df: pd.DataFrame,
    target_date: date | str | None = None,
) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()

    if "Date" not in df.columns:
        return df.iloc[0:0].copy()

    if df.empty:
        return df.iloc[0:0].copy()

    target = target_date or market_date()
    target = pd.to_datetime(target).date().isoformat()

    return df[df["Date"].astype(str) == target].copy()

def current_sunday_saturday_window(reference_date: date | None = None):
    ref = reference_date or market_date()
    start = ref - timedelta(days=(ref.weekday() + 1) % 7)
    end = start + timedelta(days=6)
    return start, end

def rows_for_current_week(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()

    if "Date" not in df.columns:
        return df.iloc[0:0].copy()

    if df.empty:
        return df.iloc[0:0].copy()

    start, end = current_sunday_saturday_window()
    parsed = parse_archive_dates(df["Date"])
    mask = (parsed >= start) & (parsed <= end)
    return df.loc[mask.fillna(False)].copy()

def filter_expected_tickers(
    df: pd.DataFrame,
    tickers: Mapping | Iterable,
    sector: str | None = None,
) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()

    if "Ticker" not in df.columns:
        return df.iloc[0:0].copy()

    if df.empty:
        return df.iloc[0:0].copy()

    if isinstance(tickers, Mapping):
        ticker_set = {str(t).upper().strip() for t in tickers.keys()}
    else:
        ticker_set = {str(t).upper().strip() for t in tickers}

    filtered = df[df["Ticker"].astype(str).str.upper().str.strip().isin(ticker_set)].copy()

    if sector is not None and "Sector" in filtered.columns:
        filtered = filtered[filtered["Sector"].astype(str) == str(sector)].copy()

    return filtered

def has_expected_tickers(df: pd.DataFrame, tickers: Mapping | Iterable) -> bool:
    if df is None or df.empty or "Ticker" not in df.columns:
        return False

    if isinstance(tickers, Mapping):
        expected = {str(t).upper().strip() for t in tickers.keys()}
    else:
        expected = {str(t).upper().strip() for t in tickers}

    found = set(df["Ticker"].dropna().astype(str).str.upper().str.strip())
    return expected.issubset(found)

def latest_complete_ticker_rows(
    df: pd.DataFrame,
    tickers: Mapping | Iterable,
    sector: str | None = None,
) -> pd.DataFrame | None:
    filtered = filter_expected_tickers(df, tickers, sector=sector)

    if filtered.empty or "Date" not in filtered.columns:
        return None

    parsed = parse_archive_dates(filtered["Date"])
    filtered = filtered.loc[parsed.notna()].copy()
    filtered["_parsed_date"] = parsed.loc[filtered.index]

    for archive_date in sorted(filtered["_parsed_date"].dropna().unique(), reverse=True):
        candidate = filtered[filtered["_parsed_date"] == archive_date].copy()

        if has_expected_tickers(candidate, tickers):
            return candidate.drop(columns=["_parsed_date"], errors="ignore")

    return None

def latest_nonempty_row(df: pd.DataFrame) -> pd.Series | None:
    if df is None or df.empty:
        return None

    working = normalize_date_column(df, "Date") if "Date" in df.columns else df.copy()

    if "Date" in working.columns:
        working["_parsed_date"] = parse_archive_dates(working["Date"])
        working = working.loc[working["_parsed_date"].notna()].sort_values(
            "_parsed_date",
            kind="stable",
        )

    if working.empty:
        return None

    return working.iloc[-1]
