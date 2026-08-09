"""Regression tests for targeted refresh snapshot persistence."""

from __future__ import annotations

from pathlib import Path
import sys
import types

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class _FakeCache:
    def __call__(self, *args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda function: function


class _FakeStreamlit(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("streamlit")
        self.session_state = {}
        self.secrets = {}
        self.cache_data = _FakeCache()
        self.cache_resource = _FakeCache()


sys.modules.setdefault("streamlit", _FakeStreamlit())

if "yfinance" not in sys.modules:
    fake_yfinance = types.ModuleType("yfinance")
    fake_yfinance.Ticker = object
    sys.modules["yfinance"] = fake_yfinance

if "fredapi" not in sys.modules:
    fake_fredapi = types.ModuleType("fredapi")
    fake_fredapi.Fred = object
    sys.modules["fredapi"] = fake_fredapi

if "requests" not in sys.modules:
    fake_requests = types.ModuleType("requests")
    fake_requests.get = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("Network access is not available in this smoke test")
    )
    sys.modules["requests"] = fake_requests

from config.load_policy import LoadPolicy, RefreshSource  # noqa: E402
from loaders import snapshot_writer  # noqa: E402


def _payloads():
    return {
        "regime_metrics": {"x": 1},
        "fred_data": {"x": {"value": 1}},
        "fred_report": {"source_mode": "retained"},
        "sector_metrics": {"x": 1},
        "benchmark_metrics": {"source_mode": "archive_read_mode"},
        "sector_data": {"x": 1},
        "raw_universe_data": {
            "yfinance": pd.DataFrame(
                {
                    "Ticker": ["A", "B", "C", "D"],
                    "Market Data Date": ["2026-08-07"] * 4,
                }
            ),
            "edgar": {},
            "_load_report": {
                "yfinance": {"source_mode": "archive_read_mode"},
                "edgar": {
                    "source_mode": "archive_read_mode",
                    "live_succeeded_tickers": [],
                },
            },
        },
        "energy_data": {
            "load_report": {
                "source_mode": "archive_read_mode",
                "market_source_mode": "retained",
            }
        },
        "debt_markets_data": {
            "load_report": {"source_mode": "archive_read_mode"}
        },
    }


def main() -> None:
    calls: list[str] = []
    originals = {
        name: getattr(snapshot_writer, name)
        for name in (
            "repository_writes_enabled",
            "append_benchmark_history",
            "append_edgar_history",
            "append_energy_history",
            "append_fred_history",
            "append_macro_history",
            "append_sector_history",
            "append_yf_history",
            "build_edgar_archive_snapshot",
        )
    }
    try:
        snapshot_writer.repository_writes_enabled = lambda: True
        for name in (
            "append_benchmark_history",
            "append_edgar_history",
            "append_energy_history",
            "append_fred_history",
            "append_macro_history",
            "append_sector_history",
            "append_yf_history",
        ):
            setattr(
                snapshot_writer,
                name,
                lambda *args, _name=name, **kwargs: calls.append(_name),
            )
        snapshot_writer.build_edgar_archive_snapshot = lambda *args, **kwargs: {}

        retained = snapshot_writer.persist_refresh_snapshots(
            policy=LoadPolicy.retained(),
            archive_suspended=False,
            **_payloads(),
        )
        if calls or retained.get("reason") != "retained_read_mode":
            raise AssertionError(
                f"Retained startup entered snapshot writes: calls={calls}, report={retained}"
            )

        calls.clear()
        current_context = snapshot_writer.persist_refresh_snapshots(
            policy=LoadPolicy.refresh([RefreshSource.CURRENT_CONTEXT]),
            archive_suspended=False,
            **_payloads(),
        )
        if calls or current_context.get("status") != "no_successful_live_sources":
            raise AssertionError(
                "Current Context refresh leaked into unrelated repository snapshots"
            )

        calls.clear()
        yfinance_payloads = _payloads()
        yfinance_payloads["raw_universe_data"]["_load_report"]["yfinance"] = {
            "source_mode": "live_complete"
        }
        yfinance_payloads["benchmark_metrics"] = {"source_mode": "live"}
        yfinance = snapshot_writer.persist_refresh_snapshots(
            policy=LoadPolicy.refresh([RefreshSource.YFINANCE]),
            archive_suspended=False,
            **yfinance_payloads,
        )
        expected = {
            "append_yf_history",
            "append_benchmark_history",
            "append_sector_history",
            "append_macro_history",
        }
        if set(calls) != expected:
            raise AssertionError(
                f"YFinance refresh wrote the wrong snapshots: {calls}"
            )
        if yfinance.get("status") != "written":
            raise AssertionError(f"YFinance write report changed: {yfinance}")

        calls.clear()
        failed_edgar_payloads = _payloads()
        failed_edgar_payloads["raw_universe_data"]["_load_report"]["edgar"] = {
            "source_mode": "manual_archive_fallback",
            "live_succeeded_tickers": [],
        }
        failed_edgar = snapshot_writer.persist_refresh_snapshots(
            policy=LoadPolicy.refresh([RefreshSource.EDGAR]),
            archive_suspended=False,
            **failed_edgar_payloads,
        )
        if calls or failed_edgar.get("status") != "no_successful_live_sources":
            raise AssertionError(
                "Failed EDGAR refresh re-dated retained fallback data"
            )

        calls.clear()
        successful_edgar_payloads = _payloads()
        successful_edgar_payloads["raw_universe_data"]["_load_report"]["edgar"] = {
            "source_mode": "live_complete",
            "live_succeeded_tickers": ["A", "B"],
        }
        successful_edgar = snapshot_writer.persist_refresh_snapshots(
            policy=LoadPolicy.refresh([RefreshSource.EDGAR]),
            archive_suspended=False,
            **successful_edgar_payloads,
        )
        if calls != ["append_edgar_history"]:
            raise AssertionError(
                f"EDGAR refresh wrote snapshots it does not own: {calls}"
            )
        if successful_edgar.get("status") != "written":
            raise AssertionError(f"EDGAR write report changed: {successful_edgar}")
    finally:
        for name, value in originals.items():
            setattr(snapshot_writer, name, value)

    print("PASS  retained startup writes nothing")
    print("PASS  unrelated domain refresh writes no generic snapshots")
    print("PASS  successful YFinance refresh writes only owned snapshots")
    print("PASS  failed EDGAR refresh preserves retained dates")
    print("PASS  successful EDGAR refresh writes only EDGAR")


if __name__ == "__main__":
    main()
