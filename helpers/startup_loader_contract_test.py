"""Independent retained-startup contract for the recovery branch.

This test deliberately runs the loader graph with every network route converted
into a hard failure. It also hashes retained files before and after the run so a
passing result proves that normal startup reads retained data without silently
refreshing providers or mutating snapshots.
"""

from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import sys
import time
import types
from typing import Callable
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REPORT_DIR = ROOT / "audit" / "startup_loader"
REPORT_PATH = REPORT_DIR / "startup_loader_report.json"
PERFORMANCE_GATE_SECONDS = 15.0


class _FakeCache:
    def __call__(self, *args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda function: function

    def clear(self) -> None:
        return None


class _FakeStreamlit(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("streamlit")
        self.session_state = {}
        self.secrets = {}
        self.cache_data = _FakeCache()
        self.cache_resource = _FakeCache()


class _BlockedYFinance(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("yfinance")

        class Ticker:
            def __init__(self, *args, **kwargs):
                raise AssertionError("YFinance provider access attempted in retained mode")

        self.Ticker = Ticker


class _BlockedFredAPI(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("fredapi")

        class Fred:
            def __init__(self, *args, **kwargs):
                raise AssertionError("FRED provider access attempted in retained mode")

        self.Fred = Fred


sys.modules["streamlit"] = _FakeStreamlit()
sys.modules["yfinance"] = _BlockedYFinance()
sys.modules["fredapi"] = _BlockedFredAPI()

if "requests" not in sys.modules:
    fake_requests = types.ModuleType("requests")

    class _Session:
        def request(self, method, url, *args, **kwargs):
            raise AssertionError(
                f"Network request attempted in retained mode: {method} {url}"
            )

    fake_requests.sessions = types.SimpleNamespace(Session=_Session)
    fake_requests.Session = _Session
    fake_requests.get = lambda url, *args, **kwargs: _Session().request(
        "GET", url, *args, **kwargs
    )
    sys.modules["requests"] = fake_requests

if "bs4" not in sys.modules:
    fake_bs4 = types.ModuleType("bs4")

    class _BeautifulSoup:
        def __init__(self, *args, **kwargs):
            raise AssertionError("HTML parsing should not run in retained mode")

    fake_bs4.BeautifulSoup = _BeautifulSoup
    sys.modules["bs4"] = fake_bs4

import pandas as pd  # noqa: E402
import requests  # noqa: E402

from analytics.dashboard_context import DashboardContext  # noqa: E402
from analytics.factor_engine import calc_sector_factors  # noqa: E402
from analytics.macro_dataframe import build_macro_dashboard_data  # noqa: E402
from analytics.read_architecture import build_platform_reads  # noqa: E402
from analytics.regime_engine import build_regime_metrics  # noqa: E402
from analytics.sector_builder import get_sector_data  # noqa: E402
from analytics.sector_engine import build_sector_metrics  # noqa: E402
from analytics.spatial_context import attach_water_context  # noqa: E402
from archive.archive_reader import load_fred_history, load_macro_history  # noqa: E402
from benchmarks.benchmark_service import get_benchmark_metrics  # noqa: E402
from config.load_policy import LoadPolicy, RefreshSource, build_load_policy  # noqa: E402
from config.market_clock import market_date  # noqa: E402
from config.sector_config import SECTOR_CONFIG, all_tickers  # noqa: E402
from loaders.adaptation_loader import load_adaptation_data  # noqa: E402
from loaders.commercialization_loader import load_commercialization_data  # noqa: E402
from loaders.connectivity_loader import load_connectivity_data  # noqa: E402
from loaders.construction_loader import load_data_center_construction  # noqa: E402
from loaders.debt_markets_loader import load_debt_markets_data  # noqa: E402
from loaders.economic_impact_loader import load_economic_impact_data  # noqa: E402
from loaders.energy_loader import load_energy_data  # noqa: E402
from loaders.fred_loader import load_fred  # noqa: E402
from loaders.infrastructure_loader import load_infrastructure_data  # noqa: E402
from loaders.market_loader import load_market_universe  # noqa: E402
from loaders.nfci_loader import load_nfci_history  # noqa: E402
from loaders.water_loader import load_water_utilization_data  # noqa: E402
from loaders.weekly_context_loader import load_current_context, load_weekly_context  # noqa: E402
from loaders.workforce_loader import load_workforce_data  # noqa: E402


def _tracked_files() -> list[Path]:
    paths: list[Path] = []
    for directory in (ROOT / "archive", ROOT / "data"):
        if not directory.exists():
            continue
        paths.extend(
            path
            for path in directory.rglob("*")
            if path.is_file() and path.suffix.lower() in {".csv", ".json", ".parquet"}
        )
    return sorted(paths)


def _hash_files(paths: list[Path]) -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


@contextmanager
def _network_blocker():
    attempts: list[str] = []
    original_request = requests.sessions.Session.request
    original_urlopen = urllib.request.urlopen
    original_create_connection = socket.create_connection
    original_connect = socket.socket.connect

    def blocked_request(self, method, url, *args, **kwargs):
        attempts.append(f"requests:{method}:{url}")
        raise AssertionError(f"Network request attempted in retained mode: {method} {url}")

    def blocked_urlopen(url, *args, **kwargs):
        attempts.append(f"urlopen:{url}")
        raise AssertionError(f"URL open attempted in retained mode: {url}")

    def blocked_create_connection(address, *args, **kwargs):
        attempts.append(f"socket.create_connection:{address}")
        raise AssertionError(f"Socket connection attempted in retained mode: {address}")

    def blocked_connect(self, address):
        attempts.append(f"socket.connect:{address}")
        raise AssertionError(f"Socket connection attempted in retained mode: {address}")

    requests.sessions.Session.request = blocked_request
    urllib.request.urlopen = blocked_urlopen
    socket.create_connection = blocked_create_connection
    socket.socket.connect = blocked_connect
    try:
        yield attempts
    finally:
        requests.sessions.Session.request = original_request
        urllib.request.urlopen = original_urlopen
        socket.create_connection = original_create_connection
        socket.socket.connect = original_connect


def _timed(label: str, function: Callable[[], object], timings: dict[str, float]):
    started = time.perf_counter()
    result = function()
    timings[label] = time.perf_counter() - started
    return result


def _finite_fred_series(payload: dict) -> int:
    count = 0
    for value in (payload or {}).values():
        item = value if isinstance(value, dict) else {"value": value}
        number = pd.to_numeric(item.get("value"), errors="coerce")
        if pd.notna(number):
            count += 1
    return count


def _assert_policy_contract() -> LoadPolicy:
    policy = build_load_policy()
    if not policy.is_read_mode or policy.is_explicit_refresh:
        raise AssertionError(f"Default policy is not retained-only: {policy.describe()}")
    for source in RefreshSource:
        if policy.allows_live(source):
            raise AssertionError(f"Default policy unexpectedly authorizes {source.value}")

    public_refresh = build_load_policy(force_yfinance_refresh=True)
    if public_refresh.allows_live(RefreshSource.YFINANCE):
        raise AssertionError("Public mode forged an explicit YFinance refresh")

    prior_mode = os.environ.get("AI_MACRO_MODE")
    try:
        os.environ["AI_MACRO_MODE"] = "developer"
        refresh = build_load_policy(force_yfinance_refresh=True)
        if not refresh.allows_live(RefreshSource.YFINANCE):
            raise AssertionError("Developer YFinance refresh was not authorized")
        unauthorized = [
            source.value
            for source in RefreshSource
            if source is not RefreshSource.YFINANCE and refresh.allows_live(source)
        ]
        if unauthorized:
            raise AssertionError(f"YFinance refresh leaked authorization: {unauthorized}")

        all_sources = build_load_policy(
            force_yfinance_refresh=True,
            force_edgar_refresh=True,
            force_fred_refresh=True,
            force_nyfed_refresh=True,
        )
        expected_sources = {
            RefreshSource.YFINANCE,
            RefreshSource.EDGAR,
            RefreshSource.FRED,
            RefreshSource.NYFED,
        }
        if {source for source in RefreshSource if all_sources.allows_live(source)} != expected_sources:
            raise AssertionError(f"All-source refresh authorization changed: {all_sources.describe()}")

        all_domains = build_load_policy(
            refresh_domains={
                "current_context",
                "compute",
                "data_centers",
                "connectivity",
                "power",
                "grid_storage",
                "water",
                "adoption",
                "workforce",
                "economic_outcomes",
            }
        )
        expected_domains = {
            RefreshSource.CURRENT_CONTEXT,
            RefreshSource.COMPUTE,
            RefreshSource.DATA_CENTERS,
            RefreshSource.CONNECTIVITY,
            RefreshSource.POWER,
            RefreshSource.GRID_STORAGE,
            RefreshSource.WATER,
            RefreshSource.ADOPTION,
            RefreshSource.WORKFORCE,
            RefreshSource.ECONOMIC_OUTCOMES,
        }
        if {source for source in RefreshSource if all_domains.allows_live(source)} != expected_domains:
            raise AssertionError(f"All-domain refresh authorization changed: {all_domains.describe()}")
    finally:
        if prior_mode is None:
            os.environ.pop("AI_MACRO_MODE", None)
        else:
            os.environ["AI_MACRO_MODE"] = prior_mode
    return policy


def _assert_application_routing() -> None:
    source = (ROOT / "ai_macro.py").read_text(encoding="utf-8")
    required = (
        "build_load_policy(",
        "allow_yfinance_live=load_policy.allows_live(RefreshSource.YFINANCE)",
        "allow_edgar_live=load_policy.allows_live(RefreshSource.EDGAR)",
        "allow_live=load_policy.allows_live(RefreshSource.FRED)",
        "persist_refresh_snapshots(",
        "if load_policy.allows_live(RefreshSource.CURRENT_CONTEXT):",
        "Rebuild from retained data",
        "Refresh All Sources",
        "Refresh All Domains",
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise AssertionError(f"Application loader-policy routing is incomplete: {missing}")


def main() -> None:
    policy = _assert_policy_contract()
    _assert_application_routing()

    tracked = _tracked_files()
    before = _hash_files(tracked)
    timings: dict[str, float] = {}
    started = time.perf_counter()

    with _network_blocker() as network_attempts:
        tickers = {ticker: ticker for ticker in all_tickers()}
        market = _timed(
            "market_universe",
            lambda: load_market_universe(
                tickers,
                allow_yfinance_live=policy.allows_live(RefreshSource.YFINANCE),
                allow_edgar_live=policy.allows_live(RefreshSource.EDGAR),
            ),
            timings,
        )
        benchmark = _timed(
            "benchmark",
            lambda: get_benchmark_metrics(
                "QQQ", allow_live=policy.allows_live(RefreshSource.YFINANCE)
            ),
            timings,
        )
        fred = _timed(
            "fred",
            lambda: load_fred(allow_live=policy.allows_live(RefreshSource.FRED)),
            timings,
        )
        nfci = _timed(
            "nfci",
            lambda: load_nfci_history(allow_live=policy.allows_live(RefreshSource.FRED)),
            timings,
        )
        energy = _timed(
            "energy",
            lambda: load_energy_data(fred_data=fred, allow_live=False),
            timings,
        )
        debt = _timed(
            "nyfed",
            lambda: load_debt_markets_data(
                allow_live=policy.allows_live(RefreshSource.NYFED)
            ),
            timings,
        )
        infrastructure = _timed("infrastructure", load_infrastructure_data, timings)
        connectivity = _timed(
            "connectivity",
            lambda: load_connectivity_data(infrastructure.get("campus_registry")),
            timings,
        )
        construction = _timed(
            "construction", load_data_center_construction, timings
        )
        water = _timed("water", load_water_utilization_data, timings)
        adoption = _timed("adoption", load_adaptation_data, timings)
        workforce = _timed("workforce", load_workforce_data, timings)
        outcomes = _timed("economic_outcomes", load_economic_impact_data, timings)
        commercialization = _timed(
            "commercialization", load_commercialization_data, timings
        )
        current_context = _timed(
            "current_context",
            lambda: load_current_context(as_of=market_date(), include_live=False),
            timings,
        )
        sector_context = _timed(
            "sector_context",
            lambda: load_weekly_context(
                as_of=market_date(), surface="sector", limit=15, include_live=False
            ),
            timings,
        )

        def build_sectors():
            sector_data = {}
            sector_metrics = {}
            for sector, config in SECTOR_CONFIG.items():
                frame = get_sector_data(
                    sector,
                    config["basket"],
                    raw_universe_data=market,
                )
                factors = calc_sector_factors(
                    sector=sector,
                    yf_df=frame,
                    benchmark_metrics=benchmark,
                )
                sector_data[sector] = frame
                sector_metrics[sector] = build_sector_metrics(factors, frame)
            return sector_data, sector_metrics

        sector_data, sector_metrics = _timed(
            "sector_analytics", build_sectors, timings
        )

        def build_derived_outputs():
            regime = build_regime_metrics(
                sector_metrics=sector_metrics,
                sector_data=sector_data,
                fred_history=load_fred_history(),
                fred_data=fred,
                construction_data=construction,
                macro_history=load_macro_history(),
            )
            enriched_infrastructure, enriched_water = attach_water_context(
                infrastructure,
                water,
            )
            dashboard = build_macro_dashboard_data(
                sector_metrics=sector_metrics,
                regime_metrics=regime,
            )
            context = DashboardContext(
                sector_data=sector_data,
                sector_metrics=sector_metrics,
                dashboard_data=dashboard,
                regime_metrics=regime,
                fred_data=fred,
                nfci_history=nfci,
                energy_data=energy,
                debt_markets_data=debt,
                infrastructure_data=enriched_infrastructure,
                connectivity_data=connectivity,
                water_data=enriched_water,
                adaptation_data=adoption,
                workforce_data=workforce,
                economic_impact_data=outcomes,
                commercialization_data=commercialization,
                current_context=current_context,
            )
            return regime, dashboard, build_platform_reads(context)

        regime, dashboard, platform_reads = _timed(
            "derived_outputs", build_derived_outputs, timings
        )

    total_elapsed = time.perf_counter() - started
    after = _hash_files(tracked)
    changed_files = sorted(path for path in before if before[path] != after.get(path))

    expected_tickers = len(tickers)
    market_report = market.get("_load_report", {})
    yf_report = market_report.get("yfinance", {})
    edgar_report = market_report.get("edgar", {})
    assertions = {
        "network_attempts": network_attempts,
        "changed_retained_files": changed_files,
        "expected_tickers": expected_tickers,
        "yfinance_returned": int(yf_report.get("returned_tickers", 0) or 0),
        "edgar_returned": int(edgar_report.get("returned_tickers", 0) or 0),
        "fred_returned": _finite_fred_series(fred),
        "nfci_rows": int(len(nfci)),
        "benchmark_source_mode": benchmark.get("source_mode"),
        "energy_source_mode": (energy.get("load_report", {}) or {}).get("source_mode"),
        "nyfed_source_mode": (debt.get("load_report", {}) or {}).get("source_mode"),
        "infrastructure_records": int(len(infrastructure.get("facility_registry", []))),
        "connectivity_records": int(
            len(connectivity.get("submarine_cable_systems", []))
        ),
        "construction_has_value": bool(construction),
        "water_has_data": bool(water),
        "adoption_has_data": bool(adoption),
        "workforce_has_data": bool(workforce),
        "outcomes_has_data": bool(outcomes),
        "commercialization_has_data": bool(commercialization),
        "current_context_domains": int(len(current_context.get("by_domain", {}))),
        "sector_context_events": int(len(sector_context.get("events", []))),
        "sector_count": int(len(sector_data)),
        "platform_read_count": int(len(platform_reads)),
        "dashboard_has_data": dashboard is not None,
        "regime_has_data": bool(regime),
    }

    failures: list[str] = []
    if network_attempts:
        failures.append(f"network attempts: {network_attempts}")
    if changed_files:
        failures.append(f"retained files changed: {changed_files}")
    if assertions["yfinance_returned"] != expected_tickers:
        failures.append(
            f"YFinance retained coverage {assertions['yfinance_returned']}/{expected_tickers}"
        )
    if assertions["edgar_returned"] != expected_tickers:
        failures.append(
            f"EDGAR retained coverage {assertions['edgar_returned']}/{expected_tickers}"
        )
    if yf_report.get("source_mode") != "archive_read_mode":
        failures.append(f"YFinance source mode: {yf_report.get('source_mode')}")
    if edgar_report.get("source_mode") != "archive_read_mode":
        failures.append(f"EDGAR source mode: {edgar_report.get('source_mode')}")
    if assertions["fred_returned"] < 20:
        failures.append(f"FRED retained series: {assertions['fred_returned']}")
    if assertions["nfci_rows"] < 1:
        failures.append("NFCI retained history is empty")
    if assertions["benchmark_source_mode"] != "archive_read_mode":
        failures.append(
            f"Benchmark source mode: {assertions['benchmark_source_mode']}"
        )
    if assertions["energy_source_mode"] != "archive_read_mode":
        failures.append(f"Energy source mode: {assertions['energy_source_mode']}")
    if assertions["nyfed_source_mode"] != "archive_read_mode":
        failures.append(f"NY Fed source mode: {assertions['nyfed_source_mode']}")
    if assertions["infrastructure_records"] < 1:
        failures.append("Infrastructure retained registry is empty")
    if assertions["connectivity_records"] < 1:
        failures.append("Connectivity retained cable ledger is empty")
    if assertions["current_context_domains"] < 11:
        failures.append(
            f"Current Context retained domain coverage: {assertions['current_context_domains']}"
        )
    if assertions["sector_count"] != len(SECTOR_CONFIG):
        failures.append(
            f"Sector analytics coverage: {assertions['sector_count']}/{len(SECTOR_CONFIG)}"
        )
    if assertions["platform_read_count"] < 12:
        failures.append(
            f"Platform Read coverage: {assertions['platform_read_count']}"
        )
    if total_elapsed > PERFORMANCE_GATE_SECONDS:
        failures.append(
            f"retained loader graph took {total_elapsed:.2f}s; gate is {PERFORMANCE_GATE_SECONDS:.2f}s"
        )

    report = {
        "contract": "retained startup: no network, no writes, complete retained payloads",
        "policy": policy.describe(),
        "total_elapsed_sec": total_elapsed,
        "performance_gate_sec": PERFORMANCE_GATE_SECONDS,
        "timings_sec": timings,
        "assertions": assertions,
        "status": "FAIL" if failures else "PASS",
        "failures": failures,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    if failures:
        raise AssertionError("; ".join(failures))

    print(f"PASS  retained loader graph: {total_elapsed:.2f}s")
    print(f"PASS  YFinance retained coverage: {assertions['yfinance_returned']}/{expected_tickers}")
    print(f"PASS  EDGAR retained coverage: {assertions['edgar_returned']}/{expected_tickers}")
    print(f"PASS  provider network attempts: {len(network_attempts)}")
    print(f"PASS  retained file changes: {len(changed_files)}")
    print(f"REPORT {REPORT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
