from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_DIR = PROJECT_ROOT / "archive"


def resolve_archive_path(archive_path: str | Path) -> Path:
    """Resolve archive paths relative to the project root, not the process CWD."""
    path = Path(archive_path)

    if path.is_absolute():
        return path

    if path.parts and path.parts[0] == "archive":
        return PROJECT_ROOT / path

    return ARCHIVE_DIR / path

ARCHIVE_PATHS = {
    "benchmark": ARCHIVE_DIR / "benchmark_history.csv",
    "edgar": ARCHIVE_DIR / "edgar_history.csv",
    "fred": ARCHIVE_DIR / "fred_history.csv",
    "macro": ARCHIVE_DIR / "macro_history.csv",
    "put_call": ARCHIVE_DIR / "put_call_history.csv",
    "sector": ARCHIVE_DIR / "sector_history.csv",
    "yf": ARCHIVE_DIR / "yf_history.csv",
}

ARCHIVE_KEYS = {
    "benchmark": ["Date", "Benchmark"],
    "edgar": ["Date", "Sector", "Ticker"],
    "fred": ["Date"],
    "macro": ["Date"],
    "put_call": ["Date"],
    "sector": ["Date", "Sector"],
    "yf": ["Date", "Sector", "Ticker"],
}

EDGAR_REQUIRED_COLUMNS = [
    "Date",
    "Sector",
    "Ticker",
    "Company",
    "Revenue",
    "Revenue Growth",
    "CapEx",
    "CapEx Growth",
    "Revenue FY",
    "CapEx FY",
    "Market Cap",
    "CIK",
    "EDGAR Status",
]

PUT_CALL_COLUMNS = [
    "Date",
    "PutCallRatio",
    "Normalized PutCall",
    "Source",
]


#################################################
# DATE + VALUE NORMALIZATION
#################################################

def today_iso() -> str:
    return date.today().isoformat()


def parse_archive_dates(values) -> pd.Series:
    """
    Parse legacy archive date strings into normalized pandas dates.

    Accepts ISO dates and historical M/D/YY style dates. Two-digit years are
    parsed by pandas into the expected 2000s range for the existing archive.
    """
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


#################################################
# GENERIC ARCHIVE READS
#################################################

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


def load_fred_history():
    return read_archive(ARCHIVE_PATHS["fred"])


def load_macro_history():
    return read_archive(ARCHIVE_PATHS["macro"])


def load_put_call_history():
    return read_archive(
        ARCHIVE_PATHS["put_call"],
        required_columns=PUT_CALL_COLUMNS,
    )


def load_sector_history():
    return read_archive(ARCHIVE_PATHS["sector"])


def load_yf_history():
    return read_archive(ARCHIVE_PATHS["yf"])


#################################################
# FILTERS + COMPLETENESS HELPERS
#################################################

def rows_for_date(
    df: pd.DataFrame,
    target_date: date | str | None = None,
) -> pd.DataFrame:
    if df is None or df.empty or "Date" not in df.columns:
        return pd.DataFrame()

    target = target_date or date.today()
    target = pd.to_datetime(target).date().isoformat()

    return df[df["Date"].astype(str) == target].copy()


def current_sunday_saturday_window(reference_date: date | None = None):
    ref = reference_date or date.today()
    start = ref - timedelta(days=(ref.weekday() + 1) % 7)
    end = start + timedelta(days=6)
    return start, end


def rows_for_current_week(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "Date" not in df.columns:
        return pd.DataFrame()

    start, end = current_sunday_saturday_window()
    parsed = parse_archive_dates(df["Date"])
    mask = (parsed >= start) & (parsed <= end)
    return df.loc[mask.fillna(False)].copy()


def latest_rows_by_key(
    df: pd.DataFrame,
    key_cols: Sequence[str],
) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    missing = [col for col in key_cols if col not in df.columns]
    if missing:
        return pd.DataFrame()

    working = normalize_date_column(df, "Date") if "Date" in df.columns else df.copy()
    working = normalize_key_columns(working)

    if "Date" in working.columns:
        working["_parsed_date"] = parse_archive_dates(working["Date"])
        working = working.sort_values(["_parsed_date"], kind="stable")

    latest = working.groupby(list(key_cols), dropna=False, as_index=False).tail(1)

    return latest.drop(columns=["_parsed_date"], errors="ignore").copy()


def filter_expected_tickers(
    df: pd.DataFrame,
    tickers: Mapping | Iterable,
    sector: str | None = None,
) -> pd.DataFrame:
    if df is None or df.empty or "Ticker" not in df.columns:
        return pd.DataFrame()

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


#################################################
# DEDUPE / MIGRATION HELPERS
#################################################

def coalesce_duplicate_group(group: pd.DataFrame) -> pd.Series:
    """
    Keep the latest row by file order, then fill only its blank fields from
    earlier duplicate rows for the same logical archive key.
    """
    if group.empty:
        return pd.Series(dtype="object")

    base = group.iloc[-1].copy()

    for _, older in group.iloc[:-1].iloc[::-1].iterrows():
        for col in group.columns:
            if is_blank(base.get(col)) and is_valid_value(older.get(col)):
                base[col] = older[col]

    return base


def dedupe_by_key(df: pd.DataFrame, key_cols: Sequence[str]) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    missing = [col for col in key_cols if col not in df.columns]
    if missing:
        return df.copy()

    working = df.copy()
    working["_file_order"] = range(len(working))

    rows = []

    # Use explicit group iteration instead of groupby.apply. Newer pandas
    # versions may exclude grouping columns from apply payloads, which strips
    # archive key columns like Date/Sector/Ticker before writing.
    for _, group in working.groupby(list(key_cols), dropna=False, sort=False):
        rows.append(coalesce_duplicate_group(group.copy()))

    if not rows:
        return working.drop(columns=["_file_order"], errors="ignore").copy()

    deduped = pd.DataFrame(rows)
    deduped = deduped.sort_values("_file_order", kind="stable")
    return deduped.drop(columns=["_file_order"], errors="ignore").copy()


def ensure_columns(df: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    df = df.copy()

    for col in columns:
        if col not in df.columns:
            df[col] = np.nan

    return df
