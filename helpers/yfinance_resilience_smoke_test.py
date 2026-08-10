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
        # non-rate-limit transport reason.  Both must retry without relaxing
        # the complete-live-row publication contract.
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

    print("PASS  YFinance adaptive pacing · retry only misses · rate-limit cooldown · complete-row contract preserved")


if __name__ == "__main__":
    main()
