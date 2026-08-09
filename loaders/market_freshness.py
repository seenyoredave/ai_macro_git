from __future__ import annotations

import pandas as pd

from config.market_clock import utc_now

def _ticker_order(tickers):
    raw = tickers.keys() if isinstance(tickers, dict) else tickers
    return [str(ticker).upper().strip() for ticker in raw]

def _normalize_rows(frame, expected, required_columns):
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=list(required_columns))

    normalized = frame.copy()
    for column in required_columns:
        if column not in normalized.columns:
            normalized[column] = pd.NA
    if "Ticker" not in normalized.columns:
        return pd.DataFrame(columns=list(required_columns))

    normalized["Ticker"] = normalized["Ticker"].astype(str).str.upper().str.strip()
    normalized = normalized.loc[normalized["Ticker"].isin(expected)].copy()
    return normalized.drop_duplicates(subset=["Ticker"], keep="last")

def merge_live_with_archive(
    fresh,
    fallback,
    tickers,
    *,
    required_columns,
    metadata_columns=("Date", "Sector", "Ticker", "Company"),
):
    expected_order = _ticker_order(tickers)
    expected = set(expected_order)
    live = _normalize_rows(fresh, expected, required_columns)
    archive = _normalize_rows(fallback, expected, required_columns)

    live_tickers = set(live["Ticker"]) if not live.empty else set()
    archive_tickers = set(archive["Ticker"]) if not archive.empty else set()

    if live.empty and archive.empty:
        merged = pd.DataFrame(columns=list(required_columns))
    elif live.empty:
        merged = archive.copy()
    elif archive.empty:
        merged = live.copy()
    else:
        merged = (
            live.set_index("Ticker")
            .combine_first(archive.set_index("Ticker"))
            .reset_index()
        )

    merged = _normalize_rows(merged, expected, required_columns)
    if not merged.empty:
        row_order = {ticker: index for index, ticker in enumerate(expected_order)}
        merged["_ticker_order"] = merged["Ticker"].map(row_order)
        merged = (
            merged.sort_values("_ticker_order", kind="stable")
            .drop(columns="_ticker_order")
            .reset_index(drop=True)
        )

    returned = set(merged["Ticker"]) if not merged.empty else set()
    archive_row_fallback = sorted((expected - live_tickers) & archive_tickers)
    missing = sorted(expected - returned)

    field_backfills = 0
    field_backfill_details = []
    field_backfill_columns = {}
    shared = live_tickers & archive_tickers
    if shared:
        live_lookup = live.set_index("Ticker")
        archive_lookup = archive.set_index("Ticker")
        comparable = [
            column
            for column in required_columns
            if column not in set(metadata_columns)
            and column in live_lookup.columns
            and column in archive_lookup.columns
        ]
        for ticker in sorted(shared):
            for column in comparable:
                live_value = live_lookup.at[ticker, column]
                archive_value = archive_lookup.at[ticker, column]
                if pd.isna(live_value) and pd.notna(archive_value):
                    field_backfills += 1
                    field_backfill_details.append(f"{ticker}: {column}")
                    field_backfill_columns[column] = int(field_backfill_columns.get(column, 0)) + 1

    # A complete live refresh is defined by row coverage, not by every optional
    # provider field being populated. YFinance regularly omits individual
    # fundamentals even when the ticker itself refreshed successfully. Those
    # cells are resolved from the previous retained snapshot and are reported
    # separately; they do not turn a 204/204 live universe into a failed refresh.
    if not live_tickers and returned:
        source_mode = "archive_fallback"
    elif archive_row_fallback:
        source_mode = "live_with_archive_row_fallback"
    elif live_tickers:
        source_mode = "live_complete"
    else:
        source_mode = "unavailable"

    merged.attrs["load_report"] = {
        "source_mode": source_mode,
        "requested_at_utc": utc_now().isoformat(timespec="seconds"),
        "live_tickers": len(live_tickers),
        "archive_fallback_tickers": len(archive_row_fallback),
        "archive_fallback_symbols": archive_row_fallback,
        "archive_field_backfills": int(field_backfills),
        "archive_field_backfill_details": field_backfill_details,
        "archive_field_backfill_columns": dict(sorted(field_backfill_columns.items())),
        "missing_tickers": missing,
        "returned_tickers": len(returned),
    }
    return merged
