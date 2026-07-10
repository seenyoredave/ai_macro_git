import pandas as pd
import numpy as np

from pathlib import Path
from datetime import datetime

from benchmarks.benchmark_service import get_benchmark_metrics
from config.benchmark_config import BENCHMARK_UNIVERSES
from helpers.macro_normalization import normalize_put_call
from archive.archive_reader import (
    ARCHIVE_KEYS,
    EDGAR_REQUIRED_COLUMNS,
    PUT_CALL_COLUMNS,
    dedupe_by_key,
    ensure_columns,
    normalize_date_column,
    normalize_key_columns,
    read_archive,
    today_iso,
    resolve_archive_path,
)


def _validate_archive_keys(df, key_cols, archive_file, *, require_values=False):
    """Validate that archive identity columns exist before any write.

    require_values=True is used for write outputs so a malformed dataframe with
    blank Date/Ticker/Sector keys cannot be persisted.
    """
    if not key_cols:
        return

    missing = [col for col in key_cols if col not in df.columns]

    if missing:
        raise ValueError(
            f"Refusing to write malformed archive {archive_file}: "
            f"missing required key columns {missing}"
        )

    if require_values:
        for col in key_cols:
            blank = df[col].isna() | (df[col].astype(str).str.strip() == "")
            if blank.any():
                raise ValueError(
                    f"Refusing to write malformed archive {archive_file}: "
                    f"{int(blank.sum())} rows have blank required key column {col!r}"
                )

    if "Date" in key_cols and "Date" in df.columns:
        parsed = pd.to_datetime(df["Date"], errors="coerce")

        if parsed.isna().any():
            bad_count = int(parsed.isna().sum())
            raise ValueError(
                f"Refusing to write malformed archive {archive_file}: "
                f"{bad_count} rows have unparseable Date values"
            )


def _normalize_snapshot_for_write(snapshot, archive_file, key_cols):
    snapshot = snapshot.copy()
    snapshot = snapshot.dropna(how="all").copy()
    snapshot = normalize_key_columns(snapshot)

    if "Date" in snapshot.columns:
        parsed = pd.to_datetime(snapshot["Date"], errors="coerce")
        snapshot = snapshot.loc[parsed.notna()].copy()
        parsed = parsed.loc[snapshot.index]
        snapshot["Date"] = parsed.dt.date.map(lambda d: d.isoformat())

    _validate_archive_keys(snapshot, key_cols, archive_file, require_values=True)
    return snapshot


def _read_existing_for_write(archive_file, key_cols):
    """Read an existing archive without adding or dropping identity columns.

    Runtime writes must never silently repair or reshape a corrupted archive.
    If the existing file is malformed, fail before writing so the prior file is
    preserved and the user can restore from backup.
    """
    if not archive_file.exists() or archive_file.stat().st_size == 0:
        return pd.DataFrame()

    existing = pd.read_csv(archive_file)

    if existing.empty:
        return existing

    existing = existing.dropna(how="all").copy()
    existing = normalize_key_columns(existing)

    _validate_archive_keys(existing, key_cols, archive_file, require_values=True)

    if "Date" in existing.columns:
        existing = normalize_date_column(existing, "Date")
        _validate_archive_keys(existing, key_cols, archive_file, require_values=True)

    return existing


def _ordered_archive_columns(existing, snapshot, key_cols):
    ordered = []

    for col in key_cols or []:
        if col not in ordered:
            ordered.append(col)

    for frame in (existing, snapshot):
        for col in frame.columns:
            if col not in ordered:
                ordered.append(col)

    return ordered


def _drop_rows_replaced_by_snapshot(existing, snapshot, replace_today, key_cols):
    if existing is None or existing.empty or not replace_today:
        return existing

    if "Date" not in existing.columns or "Date" not in snapshot.columns:
        return existing

    today = today_iso()

    # Existing archive contract is one snapshot per archive date/key. Runtime
    # writes replace the current dashboard date only. Historical dates are not
    # deduped or reshaped during normal app execution.
    return existing[existing["Date"].astype(str) != today].copy()


def _atomic_archive_write(df, archive_file, key_cols):
    _validate_archive_keys(df, key_cols, archive_file, require_values=True)

    tmp_file = archive_file.with_suffix(archive_file.suffix + ".tmp")
    df.to_csv(tmp_file, index=False)

    # Read the file exactly as it will be persisted and validate the identity
    # columns before replacing the live archive.
    check = pd.read_csv(tmp_file)
    _validate_archive_keys(check, key_cols, archive_file, require_values=True)

    tmp_file.replace(archive_file)


def write_archive_snapshot(
    snapshot,
    archive_path,
    replace_today=True,
    key_cols=None,
):
    archive_file = resolve_archive_path(archive_path)
    archive_file.parent.mkdir(parents=True, exist_ok=True)

    key_cols = list(key_cols or [])

    snapshot = _normalize_snapshot_for_write(snapshot, archive_file, key_cols)

    existing = _read_existing_for_write(archive_file, key_cols)
    existing = _drop_rows_replaced_by_snapshot(
        existing,
        snapshot,
        replace_today,
        key_cols,
    )

    if existing is not None and not existing.empty:
        combined = pd.concat([existing, snapshot], ignore_index=True)
    else:
        combined = snapshot.copy()

    combined = normalize_key_columns(combined)

    if "Date" in combined.columns:
        combined = normalize_date_column(combined, "Date")

    ordered_cols = _ordered_archive_columns(existing, snapshot, key_cols)
    combined = combined.reindex(columns=ordered_cols)

    # Final write is atomic and validates the exact persisted file. This is the
    # guardrail that prevents Date/Sector/Ticker/Benchmark columns from being
    # stripped by any intermediate dataframe operation.
    _atomic_archive_write(combined, archive_file, key_cols)

def append_dataframe_history(df, archive_path, key_cols=None):
    snapshot = df.copy()

    snapshot.insert(
        0,
        "Date",
        today_iso()
    )

    write_archive_snapshot(
        snapshot,
        archive_path,
        key_cols=key_cols,
    )


def append_macro_history(
    regime_metrics,
    fred_data,
    market_sentiment=None,
):
    row = {
        "Date": today_iso(),

        "Maturation Index": regime_metrics.get("Maturation Index", np.nan),
        "Divergence": regime_metrics.get("Divergence", np.nan),

        "Power Stress Index": regime_metrics.get("Power Stress Index", np.nan),
        "Raw Power Stress Z": regime_metrics.get("Raw Power Stress Z", np.nan),

        "Concentration HHI": regime_metrics.get("Concentration HHI", np.nan),
        "Raw AI HHI": regime_metrics.get("Raw AI HHI", np.nan),

        "Avg Sector Pressure": regime_metrics.get("Avg Sector Pressure", np.nan),

        "Consumer Sentiment": fred_data.get("Consumer Sentiment", {}).get("value", np.nan),
        "Fed Funds Rate": fred_data.get("Fed Funds Rate", {}).get("value", np.nan),
        "Industrial Production": fred_data.get("Industrial Production", {}).get("value", np.nan),
    }

    snapshot = pd.DataFrame([row])

    write_archive_snapshot(
        snapshot,
        "archive/macro_history.csv",
        key_cols=ARCHIVE_KEYS["macro"],
    )


def append_sector_history(sector_metrics):
    rows = []

    for sector, metrics in sector_metrics.items():
        rows.append({
            "Date": today_iso(),
            "Sector": sector,
            "Sector Score": metrics.get("Sector Score"),
            "Pressure": metrics.get("Sector Pressure"),
            "Forward P/E": metrics.get("Forward P/E"),
            "Avg Return": metrics.get("Avg Return"),
        })

    snapshot = pd.DataFrame(rows)

    write_archive_snapshot(
        snapshot,
        "archive/sector_history.csv",
        key_cols=ARCHIVE_KEYS["sector"],
    )


def append_benchmark_history():
    rows = []

    for benchmark in BENCHMARK_UNIVERSES.keys():
        metrics = get_benchmark_metrics(benchmark)

        rows.append({
            "Date": today_iso(),
            "Benchmark": benchmark,
            "Forward P/E": metrics.get("forward_pe"),
            "Avg Return": metrics.get("avg_return"),
            "Beta": metrics.get("beta"),
            "Member Count": metrics.get("member_count"),
        })

    snapshot = pd.DataFrame(rows)

    write_archive_snapshot(
        snapshot,
        "archive/benchmark_history.csv",
        key_cols=ARCHIVE_KEYS["benchmark"],
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
        "Operating Cash Flow",
        "Free Cash Flow",
        "Net Income",
        "EBITDA",
        "Total Debt",
        "Cash",
        "Net Debt",
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

        sector_snapshot = df[available].copy()
        sector_snapshot.insert(0, "Sector", sector)

        rows.append(sector_snapshot)

    if not rows:
        return

    snapshot = pd.concat(
        rows,
        ignore_index=True
    )

    append_dataframe_history(
        snapshot,
        "archive/yf_history.csv",
        key_cols=ARCHIVE_KEYS["yf"],
    )


def append_edgar_history(sector_data, raw_edgar_data=None):
    rows = []

    if raw_edgar_data is not None:
        sources = [
            str(payload.get("EDGAR Source", ""))
            for payload in raw_edgar_data.values()
            if isinstance(payload, dict)
        ]

        # EDGAR fundamentals are freshness-window based, not daily market data.
        # Reusing recent archive rows should not stamp duplicate EDGAR snapshots
        # onto every dashboard date. Archive only when at least one ticker was
        # refreshed from SEC live data.
        if sources and not any(source == "SEC Live" for source in sources):
            return

        for sector, df in sector_data.items():
            if df is None or df.empty or "Ticker" not in df.columns:
                continue

            for _, row in df.iterrows():
                ticker = str(row.get("Ticker", "")).upper().strip()
                if not ticker:
                    continue

                edgar_row = raw_edgar_data.get(ticker, {}) or {}

                rows.append({
                    "Sector": sector,
                    "Ticker": ticker,
                    "Company": row.get("Company", np.nan),
                    "Revenue": edgar_row.get("Revenue", np.nan),
                    "Revenue Growth": edgar_row.get("Revenue Growth", np.nan),
                    "CapEx": edgar_row.get("CapEx", np.nan),
                    "CapEx Growth": edgar_row.get("CapEx Growth", np.nan),
                    "Revenue FY": edgar_row.get("Revenue FY", np.nan),
                    "CapEx FY": edgar_row.get("CapEx FY", np.nan),
                    "Market Cap": edgar_row.get("Market Cap", np.nan),
                    "CIK": edgar_row.get("CIK", np.nan),
                    "EDGAR Status": edgar_row.get("EDGAR Status", np.nan),
                })
    else:
        edgar_cols = [
            "Ticker",
            "Company",
            "Market Cap",
            "Revenue",
            "Revenue Growth",
            "CapEx",
            "CapEx Growth",
            "Revenue FY",
            "CapEx FY",
            "CIK",
            "EDGAR Status",
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

    snapshot = pd.DataFrame(rows)
    snapshot = ensure_columns(snapshot, [c for c in EDGAR_REQUIRED_COLUMNS if c != "Date"])

    append_dataframe_history(
        snapshot,
        "archive/edgar_history.csv",
        key_cols=ARCHIVE_KEYS["edgar"],
    )


def append_fred_history(fred_data):
    if not fred_data:
        return

    # Archive only actual live FRED pulls. Reusing an archive row should not
    # create another duplicate weekly macro snapshot.
    sources = [
        payload.get("source")
        for payload in fred_data.values()
        if isinstance(payload, dict)
    ]

    if sources and not any(str(source).lower().startswith("fred live") for source in sources):
        return

    row = {
        "Date": today_iso()
    }

    for indicator, payload in fred_data.items():
        if isinstance(payload, dict):
            row[indicator] = payload.get("value", np.nan)
            row[f"{indicator} Date"] = payload.get("date", None)
        else:
            row[indicator] = payload
            row[f"{indicator} Date"] = None

    snapshot = pd.DataFrame([row])

    write_archive_snapshot(
        snapshot,
        "archive/fred_history.csv",
        key_cols=ARCHIVE_KEYS["fred"],
    )


def append_put_call_history(market_sentiment):
    if not market_sentiment:
        return

    source = str(market_sentiment.get("Source", ""))

    # Archive only fresh live values or explicit migrated/backfilled values.
    # Do not stamp a stale fallback value onto a new dashboard date.
    if "Archive" in source and "Backfilled" not in source:
        return

    raw_pcr = market_sentiment.get("PutCallRatio", np.nan)
    normalized = market_sentiment.get("Normalized PutCall", normalize_put_call(raw_pcr))

    row = {
        "Date": today_iso(),
        "PutCallRatio": raw_pcr,
        "Normalized PutCall": normalized,
        "Source": source or "SPY Options",
    }

    snapshot = pd.DataFrame([row])
    snapshot = ensure_columns(snapshot, PUT_CALL_COLUMNS)

    write_archive_snapshot(
        snapshot,
        "archive/put_call_history.csv",
        key_cols=ARCHIVE_KEYS["put_call"],
    )
