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
from loaders.market_freshness import merge_live_with_archive  # noqa: E402
from archive.archive import build_yf_archive_snapshot  # noqa: E402


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
    # Regression for the observed production case: all 204 ticker rows returned
    # live, while 21 optional cells were filled from the prior snapshot. This is
    # a complete live universe and must remain eligible for persistence.
    tickers = {f"T{i:03d}": f"Company {i}" for i in range(204)}
    fresh = pd.DataFrame({
        "Ticker": list(tickers),
        "Market Data Date": ["2026-08-07"] * 204,
        "Price": [100.0 + i for i in range(204)],
        "Forward Revenue": [pd.NA if i < 21 else 1000.0 + i for i in range(204)],
    })
    retained_frame = pd.DataFrame({
        "Ticker": list(tickers),
        "Market Data Date": ["2026-07-29"] * 204,
        "Price": [90.0 + i for i in range(204)],
        "Forward Revenue": [900.0 + i for i in range(204)],
    })
    merged = merge_live_with_archive(
        fresh,
        retained_frame,
        tickers,
        required_columns=("Ticker", "Market Data Date", "Price", "Forward Revenue"),
        metadata_columns=("Ticker",),
    )
    merged_report = dict(merged.attrs.get("load_report", {}))
    if merged_report.get("source_mode") != "live_complete":
        raise AssertionError(f"204/204 live rows were mislabeled: {merged_report}")
    if int(merged_report.get("live_tickers") or 0) != 204:
        raise AssertionError(f"Live ticker count changed: {merged_report}")
    if int(merged_report.get("archive_fallback_tickers") or 0) != 0:
        raise AssertionError(f"Field fills were mislabeled as ticker-row fallback: {merged_report}")
    if int(merged_report.get("archive_field_backfills") or 0) != 21:
        raise AssertionError(f"Expected 21 retained field fills: {merged_report}")

    # The retained YFinance archive must be built from the provider frame, not
    # the EDGAR-priority analytical sector frame. This also preserves the
    # provider observation date required by the load report after restart.
    raw_snapshot = pd.DataFrame({
        "Ticker": ["AAA"],
        "Company": ["Alpha"],
        "Market Data Date": ["2026-08-07"],
        "Price": [123.0],
        "Revenue": [100.0],
    })
    resolved_sector = {
        "Compute": pd.DataFrame({
            "Ticker": ["AAA"],
            "Revenue": [999.0],
            "Basket Score": [1.0],
            "Basket Tier": ["Core"],
            "Basket Weight": [1.0],
        })
    }
    archive_snapshot = build_yf_archive_snapshot(raw_snapshot, resolved_sector)
    if archive_snapshot.loc[0, "Market Data Date"] != "2026-08-07":
        raise AssertionError("YFinance archive snapshot lost Market Data Date")
    if float(archive_snapshot.loc[0, "Revenue"]) != 100.0:
        raise AssertionError("Resolved sector fundamentals leaked into YFinance archive")
    if archive_snapshot.loc[0, "Sector"] != "Compute":
        raise AssertionError("YFinance archive snapshot lost sector metadata")

    calls: list[str] = []
    call_kwargs: dict[str, dict] = {}
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
            "today_iso",
        )
    }
    try:
        snapshot_writer.repository_writes_enabled = lambda: True
        snapshot_writer.today_iso = lambda: "2026-08-09"
        for name in (
            "append_benchmark_history",
            "append_edgar_history",
            "append_energy_history",
            "append_fred_history",
            "append_macro_history",
            "append_sector_history",
            "append_yf_history",
        ):
            def recorder(*args, _name=name, **kwargs):
                calls.append(_name)
                call_kwargs[_name] = dict(kwargs)
            setattr(snapshot_writer, name, recorder)
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
            "source_mode": "live_complete",
            "expected_tickers": 4,
            "live_tickers": 4,
            "archive_fallback_tickers": 0,
            "archive_field_backfills": 0,
            "missing_tickers": [],
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
        if call_kwargs.get("append_yf_history", {}).get("observation_date") != "2026-08-09":
            raise AssertionError(
                f"YFinance archive did not use the manual refresh snapshot date: {call_kwargs.get('append_yf_history')}"
            )
        for name in ("append_benchmark_history", "append_sector_history", "append_macro_history"):
            if call_kwargs.get(name, {}).get("observation_date") != "2026-08-07":
                raise AssertionError(
                    f"{name} did not preserve the market observation date: {call_kwargs.get(name)}"
                )
        if call_kwargs.get("append_macro_history", {}).get("market_data_date") != "2026-08-07":
            raise AssertionError(
                "Macro history lost the distinct YFinance market observation date"
            )

        # A complete live ticker universe may contain a small number of
        # field-level fills from the prior snapshot. Those fills are diagnostic
        # metadata, not failed ticker rows, and must not block the manual archive.
        calls.clear()
        field_fill_payloads = _payloads()
        field_fill_payloads["raw_universe_data"]["yfinance"] = pd.DataFrame({
            "Ticker": [f"T{i:03d}" for i in range(204)],
            "Market Data Date": ["2026-08-07"] * 204,
        })
        field_fill_payloads["raw_universe_data"]["_load_report"]["yfinance"] = {
            "source_mode": "live_complete",
            "expected_tickers": 204,
            "live_tickers": 204,
            "archive_fallback_tickers": 0,
            "archive_field_backfills": 21,
            "missing_tickers": [],
        }
        field_fill_payloads["benchmark_metrics"] = {"source_mode": "live"}
        field_fill_yfinance = snapshot_writer.persist_refresh_snapshots(
            policy=LoadPolicy.refresh([RefreshSource.YFINANCE]),
            archive_suspended=False,
            **field_fill_payloads,
        )
        expected = {
            "append_yf_history",
            "append_benchmark_history",
            "append_sector_history",
            "append_macro_history",
        }
        if set(calls) != expected or field_fill_yfinance.get("status") != "written":
            raise AssertionError(
                "Complete YFinance refresh with field fills was not retained: "
                f"calls={calls}, report={field_fill_yfinance}"
            )

        # A retained ticker-row fallback is different: the live universe itself
        # is incomplete, so it must not advance the retained archive.
        calls.clear()
        row_fallback_payloads = _payloads()
        row_fallback_payloads["raw_universe_data"]["_load_report"]["yfinance"] = {
            "source_mode": "live_with_archive_row_fallback",
            "expected_tickers": 4,
            "live_tickers": 3,
            "archive_fallback_tickers": 1,
            "archive_field_backfills": 7,
            "missing_tickers": [],
        }
        row_fallback_yfinance = snapshot_writer.persist_refresh_snapshots(
            policy=LoadPolicy.refresh([RefreshSource.YFINANCE]),
            archive_suspended=False,
            **row_fallback_payloads,
        )
        if calls or row_fallback_yfinance.get("status") != "no_successful_live_sources":
            raise AssertionError(
                "Incomplete YFinance ticker universe advanced retained history: "
                f"calls={calls}, report={row_fallback_yfinance}"
            )
        if "complete live ticker universe" not in str((row_fallback_yfinance.get("errors") or {}).get("yfinance", "")):
            raise AssertionError(f"Incomplete YFinance refresh was not explained: {row_fallback_yfinance}")

        # An archive-only fallback is a failed live refresh and must never
        # re-date retained market history.
        calls.clear()
        failed_yfinance_payloads = _payloads()
        failed_yfinance_payloads["raw_universe_data"]["_load_report"]["yfinance"] = {
            "source_mode": "archive_fallback",
            "live_tickers": 0,
            "live_error": "provider unavailable",
        }
        failed_yfinance = snapshot_writer.persist_refresh_snapshots(
            policy=LoadPolicy.refresh([RefreshSource.YFINANCE]),
            archive_suspended=False,
            **failed_yfinance_payloads,
        )
        if calls or failed_yfinance.get("status") != "no_successful_live_sources":
            raise AssertionError(
                "Archive-only YFinance fallback re-dated retained history: "
                f"calls={calls}, report={failed_yfinance}"
            )

        calls.clear()
        nyfed_payloads = _payloads()
        nyfed_payloads["debt_markets_data"] = {
            "load_report": {"source_mode": "live_manual"}
        }
        nyfed = snapshot_writer.persist_refresh_snapshots(
            policy=LoadPolicy.refresh([RefreshSource.NYFED]),
            archive_suspended=False,
            **nyfed_payloads,
        )
        if calls:
            raise AssertionError(f"NY Fed refresh leaked into generic snapshot writers: {calls}")
        if nyfed.get("retained_by_loader") != ["nyfed"] or nyfed.get("status") != "written":
            raise AssertionError(f"NY Fed retained write was not reported: {nyfed}")

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
    print("PASS  YFinance archive Date records refresh date separately from market observation date")
    print("PASS  complete YFinance live rows may retain individual field fills")
    print("PASS  YFinance archive-only fallback is not re-dated")
    print("PASS  successful NY Fed refresh reports its loader-owned retained write")
    print("PASS  failed EDGAR refresh preserves retained dates")
    print("PASS  successful EDGAR refresh writes only EDGAR")


if __name__ == "__main__":
    main()
