"""Regression coverage for provider-friendly YFinance refresh pacing."""

from __future__ import annotations

from pathlib import Path
import sys
import types

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Keep the test independent of a live Streamlit runtime.
if "streamlit" not in sys.modules:
    fake_streamlit = types.ModuleType("streamlit")
    def _cache_data(*args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda fn: fn
    fake_streamlit.cache_data = _cache_data
    sys.modules["streamlit"] = fake_streamlit

if "yfinance" not in sys.modules:
    fake_yfinance = types.ModuleType("yfinance")
    class _Ticker:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Live YFinance access is not used by this fixture test")
    fake_yfinance.Ticker = _Ticker
    sys.modules["yfinance"] = fake_yfinance

import loaders.market_loader as market_loader  # noqa: E402
from benchmarks import benchmark_service  # noqa: E402
from config.benchmark_config import QQQ_MEMBERS  # noqa: E402
from rendering.snapshot_status import market_snapshot_label  # noqa: E402


def _row(ticker: str) -> dict:
    return {
        "Ticker": ticker,
        "Company": ticker,
        "Market Data Date": "2026-08-07",
        "Price": 100.0,
    }


def main() -> None:
    original_attempt = market_loader._fetch_company_attempt
    original_sleep = market_loader.time.sleep
    sleeps: list[float] = []
    calls: dict[str, int] = {}

    def fake_sleep(value):
        sleeps.append(float(value))

    def fake_attempt(ticker, company):
        ticker = str(ticker).upper()
        calls[ticker] = calls.get(ticker, 0) + 1
        # One ticker rate-limits on its first attempt; another fails once for a
        # non-rate-limit transport reason. Both must retry without refetching
        # the already successful tickers.
        if ticker == "BBB" and calls[ticker] == 1:
            return {
                "ticker": ticker,
                "result": None,
                "error": "YFRateLimitError: Too Many Requests (429)",
                "rate_limited": True,
            }
        if ticker == "CCC" and calls[ticker] == 1:
            return {
                "ticker": ticker,
                "result": None,
                "error": "TimeoutError: timed out",
                "rate_limited": False,
            }
        return {"ticker": ticker, "result": _row(ticker), "error": "", "rate_limited": False}

    try:
        market_loader._fetch_company_attempt = fake_attempt
        market_loader.time.sleep = fake_sleep
        frame = market_loader.pull_yfinance(
            (("AAA", "AAA"), ("BBB", "BBB"), ("CCC", "CCC")),
            attempts=3,
        )
    finally:
        market_loader._fetch_company_attempt = original_attempt
        market_loader.time.sleep = original_sleep

    if not isinstance(frame, pd.DataFrame) or set(frame["Ticker"]) != {"AAA", "BBB", "CCC"}:
        raise AssertionError(f"Adaptive YFinance retry lost live rows: {frame}")

    report = dict(frame.attrs.get("provider_report", {}) or {})
    if report.get("requested_tickers") != 3 or report.get("succeeded_tickers") != 3:
        raise AssertionError(f"Provider report lost complete coverage: {report}")
    if report.get("retry_rounds") != 1:
        raise AssertionError(f"Failed tickers were not retried in one adaptive round: {report}")
    if report.get("rate_limit_events") != 1:
        raise AssertionError(f"Rate-limit signal was not observable: {report}")
    if report.get("failed_tickers"):
        raise AssertionError(f"Recovered retry remained marked failed: {report}")
    if calls != {"AAA": 1, "BBB": 2, "CCC": 2}:
        raise AssertionError(f"Successful tickers were redundantly refetched: {calls}")
    if not any(value >= market_loader.YFINANCE_PULL_RATE_LIMIT_DELAY_SECONDS for value in sleeps):
        raise AssertionError(f"Rate limiting did not trigger the longer cooldown: {sleeps}")

    # A transported row with a lagging provider date is retried just like a
    # transport miss, while already coherent rows remain untouched.
    calls.clear()
    sleeps.clear()
    def stale_date_once(ticker, company):
        ticker = str(ticker).upper()
        calls[ticker] = calls.get(ticker, 0) + 1
        row = _row(ticker)
        if ticker == "BBB" and calls[ticker] == 1:
            row["Market Data Date"] = "2026-08-06"
        return {"ticker": ticker, "result": row, "error": "", "rate_limited": False}

    try:
        market_loader._fetch_company_attempt = stale_date_once
        market_loader.time.sleep = fake_sleep
        coherent = market_loader.pull_yfinance(
            (("AAA", "AAA"), ("BBB", "BBB"), ("CCC", "CCC")),
            attempts=3,
        )
    finally:
        market_loader._fetch_company_attempt = original_attempt
        market_loader.time.sleep = original_sleep

    coherent_report = dict(coherent.attrs.get("provider_report", {}) or {})
    if set(coherent["Market Data Date"]) != {"2026-08-07"}:
        raise AssertionError(f"Market-date retry remained incoherent: {coherent}")
    if calls != {"AAA": 1, "BBB": 2, "CCC": 1}:
        raise AssertionError(f"Market-date retry refetched coherent rows: {calls}")
    if coherent_report.get("market_date_mismatch_events") != 1:
        raise AssertionError(f"Market-date mismatch was not reported: {coherent_report}")
    if coherent_report.get("market_date_retry_tickers") != ["BBB"]:
        raise AssertionError(f"Market-date retry ticker was not retained: {coherent_report}")

    # A persistent miss must remain a miss; merge/persistence code may resolve
    # it from retained data for display, but it cannot masquerade as a live row.
    calls.clear()
    sleeps.clear()
    def persistent_miss(ticker, company):
        ticker = str(ticker).upper()
        calls[ticker] = calls.get(ticker, 0) + 1
        if ticker == "BBB":
            return {
                "ticker": ticker,
                "result": None,
                "error": "TimeoutError: timed out",
                "rate_limited": False,
            }
        return {"ticker": ticker, "result": _row(ticker), "error": "", "rate_limited": False}

    try:
        market_loader._fetch_company_attempt = persistent_miss
        market_loader.time.sleep = fake_sleep
        partial = market_loader.pull_yfinance(
            (("AAA", "AAA"), ("BBB", "BBB")),
            attempts=2,
        )
    finally:
        market_loader._fetch_company_attempt = original_attempt
        market_loader.time.sleep = original_sleep

    partial_report = dict(partial.attrs.get("provider_report", {}) or {})
    if set(partial["Ticker"]) != {"AAA"} or partial_report.get("failed_tickers") != ["BBB"]:
        raise AssertionError(f"Persistent provider miss was hidden: {partial_report}")
    if calls.get("AAA") != 1 or calls.get("BBB") != 2:
        raise AssertionError(f"Retry path refetched successful rows or skipped the miss: {calls}")

    # A persistent stale or failed ticker degrades locally. Fresh rows remain
    # current while only the affected ticker is supplied from retained history.
    tickers = {"AAA": "AAA", "BBB": "BBB", "CCC": "CCC"}
    current_live = pd.DataFrame([_row("AAA"), _row("BBB")])
    retained = pd.DataFrame([
        {**_row("AAA"), "Market Data Date": "2026-08-05", "Price": 90.0},
        {**_row("BBB"), "Market Data Date": "2026-08-05", "Price": 91.0},
        {**_row("CCC"), "Market Data Date": "2026-08-05", "Price": 92.0},
    ])
    merged = market_loader.merge_live_yfinance_with_archive(
        current_live, retained, tickers
    )
    resolved = market_loader.resolve_yfinance_market_date_mismatch(
        merged, retained, tickers
    )
    resolved_dates = set(resolved["Market Data Date"].astype(str))
    resolved_report = dict(resolved.attrs.get("load_report", {}) or {})
    if resolved_dates != {"2026-08-07", "2026-08-05"}:
        raise AssertionError(f"Current rows were rolled back by one stale ticker: {resolved_dates}")
    if float(resolved.loc[resolved["Ticker"] == "AAA", "Price"].iloc[0]) != 100.0:
        raise AssertionError("Fresh AAA data was replaced by retained history")
    if float(resolved.loc[resolved["Ticker"] == "CCC", "Price"].iloc[0]) != 92.0:
        raise AssertionError("Failed CCC ticker did not retain its last-good row")
    if resolved_report.get("source_mode") != "live_with_archive_row_fallback":
        raise AssertionError(f"Ticker-level fallback was not explicit: {resolved_report}")
    if resolved_report.get("archive_fallback_tickers") != 1:
        raise AssertionError(f"Only one ticker should have fallen back: {resolved_report}")
    if resolved_report.get("current_market_date_tickers") != 2:
        raise AssertionError(f"Fresh market-date coverage was lost: {resolved_report}")
    if resolved_report.get("latest_market_data_date") != "2026-08-07":
        raise AssertionError(f"Latest market date did not advance: {resolved_report}")


    # Retained fallback selection is also per ticker. The newest AAA row may be
    # newer than the newest BBB row without forcing AAA back to BBB's date.
    original_history_loader = market_loader.load_yf_history
    retained_history = pd.DataFrame([
        {"Date": "2026-08-05", "Ticker": "AAA", "Market Data Date": "2026-08-05", "Price": 90.0},
        {"Date": "2026-08-05", "Ticker": "BBB", "Market Data Date": "2026-08-05", "Price": 91.0},
        {"Date": "2026-08-07", "Ticker": "AAA", "Market Data Date": "2026-08-07", "Price": 100.0},
    ])
    try:
        market_loader.load_yf_history = lambda: retained_history.copy()
        latest = market_loader.read_latest_yf_history({"AAA": "AAA", "BBB": "BBB"})
    finally:
        market_loader.load_yf_history = original_history_loader
    latest_lookup = latest.set_index("Ticker")
    if float(latest_lookup.at["AAA", "Price"]) != 100.0 or float(latest_lookup.at["BBB", "Price"]) != 91.0:
        raise AssertionError(f"Retained ticker history rolled back fresh rows: {latest_lookup[["Price", "Market Data Date"]]}")

    # The fixed benchmark accepts mixed per-member freshness rather than
    # crashing the refresh when one constituent is retained.
    benchmark_rows = []
    for index, ticker in enumerate(QQQ_MEMBERS):
        benchmark_rows.append({
            "Ticker": ticker,
            "Market Data Date": "2026-08-06" if ticker == "TSLA" else "2026-08-07",
            "1Y Return": 0.10 + index * 0.01,
            "Beta": 1.0,
            "Enterprise Value": 1000.0 + index,
            "Forward EBIT": 100.0 + index,
        })
    benchmark_frame = pd.DataFrame(benchmark_rows)
    benchmark_frame.attrs["load_report"] = {
        "source_mode": "live_with_archive_row_fallback",
        "archive_fallback_tickers": 1,
        "missing_tickers": [],
    }
    benchmark = benchmark_service.get_benchmark_metrics_from_market_frame(
        "QQQ", benchmark_frame
    )
    if benchmark.get("source_mode") != "mixed_market_universe":
        raise AssertionError(f"Mixed benchmark freshness was not retained: {benchmark}")
    if benchmark.get("market_data_date") != "2026-08-07":
        raise AssertionError(f"Benchmark latest date did not advance: {benchmark}")
    if benchmark.get("archive_fallback_tickers") != 1:
        raise AssertionError(f"Benchmark stale-member count changed: {benchmark}")

    # A genuinely unavailable benchmark member still must not crash the market
    # refresh. If no retained benchmark exists, benchmark metrics degrade to
    # unavailable while the market universe remains usable.
    missing_benchmark_frame = benchmark_frame.loc[benchmark_frame["Ticker"] != "TSLA"].copy()
    missing_benchmark_frame.attrs["load_report"] = {"source_mode": "live_complete"}
    original_archived_benchmark = benchmark_service.get_archived_benchmark_metrics
    try:
        benchmark_service.get_archived_benchmark_metrics = lambda *args, **kwargs: None
        unavailable_benchmark = benchmark_service.get_benchmark_metrics_from_market_frame(
            "QQQ", missing_benchmark_frame
        )
    finally:
        benchmark_service.get_archived_benchmark_metrics = original_archived_benchmark
    if unavailable_benchmark.get("source_mode") != "unavailable_missing_members":
        raise AssertionError(f"Missing benchmark member still caused a hard failure: {unavailable_benchmark}")
    if unavailable_benchmark.get("missing_tickers") != ["TSLA"]:
        raise AssertionError(f"Missing benchmark member diagnostics changed: {unavailable_benchmark}")

    label = market_snapshot_label(resolved)
    expected_label = "Market data through 8.7.2026 · 2/3 current · 1 retained from 8.5.2026"
    if label != expected_label:
        raise AssertionError(f"Mixed market freshness label changed: {label!r}")

    print("PASS  YFinance adaptive pacing · retry only misses · rate-limit cooldown · ticker-level fallback")


if __name__ == "__main__":
    main()
