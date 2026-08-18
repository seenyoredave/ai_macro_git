from __future__ import annotations

from pathlib import Path
import sys
import time
import warnings

MIN_PYTHON = (3, 11)
if sys.version_info < MIN_PYTHON:
    required = ".".join(str(part) for part in MIN_PYTHON)
    current = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    raise RuntimeError(f"AI Macro requires Python {required}+; current runtime is {current}.")

warnings.filterwarnings(
    "ignore",
    message="Cannot parse header or footer so it will be ignored",
    category=UserWarning,
    module=r"openpyxl\.worksheet\.header_footer",
)

# Streamlit can execute this script inside a process that has already imported
# an unrelated third-party package named ``archive``.  Put the application root
# first and discard only a foreign cached ``archive`` package before importing
# the rest of the application graph.
PROJECT_ROOT = Path(__file__).resolve().parent
_project_root_text = str(PROJECT_ROOT)
sys.path[:] = [entry for entry in sys.path if entry != _project_root_text]
sys.path.insert(0, _project_root_text)


def _archive_package_is_local(module: object) -> bool:
    expected_root = (PROJECT_ROOT / "archive").resolve()
    locations: list[object] = []
    module_file = getattr(module, "__file__", None)
    if module_file:
        locations.append(module_file)
    locations.extend(getattr(module, "__path__", ()))
    for location in locations:
        try:
            resolved = Path(location).resolve()
        except (OSError, TypeError, ValueError):
            continue
        if resolved == expected_root or expected_root in resolved.parents:
            return True
    return False


_loaded_archive = sys.modules.get("archive")
if _loaded_archive is not None and not _archive_package_is_local(_loaded_archive):
    for _module_name in tuple(sys.modules):
        if _module_name == "archive" or _module_name.startswith("archive."):
            sys.modules.pop(_module_name, None)

import streamlit as st

from analytics.dashboard_context import DashboardContext
from analytics.reader_snapshot import build_reader_snapshot
from analytics.factor_engine import calc_sector_factors
from analytics.regime_engine import build_regime_metrics
from analytics.macro_dataframe import build_macro_dashboard_data
from analytics.sector_engine import build_sector_metrics
from archive.archive_reader import load_fred_history, load_macro_history
from benchmarks.benchmark_service import get_benchmark_metrics_from_market_frame
from config.deployment import developer_mode
from config.load_policy import LoadPolicy, RefreshSource, build_load_policy
from config.market_clock import market_date
from config.metric_definitions import METRIC_DEFINITIONS
from config.sector_config import SECTOR_CONFIG, all_tickers
from rendering.sector import render_basket_tier_developer_tool
from developer.panel import render_developer_tools
from developer.state import (
    ALL_DOMAIN_REFRESH,
    DOMAIN_REFRESH_LABELS,
    initialize_developer_state,
    record_domain_refresh,
)
from loaders.construction_loader import load_data_center_construction
from loaders.debt_markets_loader import load_debt_markets_data
from loaders.energy_loader import load_energy_data
from loaders.infrastructure_loader import load_infrastructure_data
from loaders.connectivity_loader import load_connectivity_data
from loaders.workforce_loader import load_workforce_data
from loaders.economic_impact_loader import load_economic_impact_data
from loaders.water_loader import load_water_utilization_data
from loaders.adoption_loader import load_adoption_data
from loaders.commercialization_loader import load_commercialization_data
from loaders.fred_loader import describe_fred_load, latest_fred_archive_date, load_fred
from loaders.market_loader import describe_edgar_archive_status, describe_yf_archive_status, load_market_universe
from loaders.market_valuation_loader import load_market_valuation_context
from loaders.nfci_loader import load_nfci_history
from loaders.snapshot_writer import persist_refresh_snapshots
from loaders.current_context_loader import load_current_context
from loaders.current_context_daily import (
    describe_current_context_state,
    finalize_context_report,
    load_retained_context_snapshot,
    refresh_current_context_once_daily,
)
from rendering.components import render_masthead, render_platform_purpose
from rendering.snapshot_status import market_snapshot_label
from rendering.dashboard import render_research_dashboard
from rendering.theme import inject_research_theme
from analytics.sector_builder import get_sector_data
from analytics.spatial_context import attach_water_context
from automation.retained_state import refresh_retained_state_manifest

APP_VERSION = "v9.6.0"
APP_STATE_SCHEMA_VERSION = "71.0-universal-data-center-registry"

st.set_page_config(
    page_title="AI Macro",
    layout="wide",
)
inject_research_theme()

if "archive_suspended" not in st.session_state:
    st.session_state.archive_suspended = False

if "current_context_load_report" not in st.session_state:
    st.session_state.current_context_load_report = {}

if st.session_state.get("app_state_schema_version") != APP_STATE_SCHEMA_VERSION:
    st.session_state.force_rebuild = True
    st.session_state.app_state_schema_version = APP_STATE_SCHEMA_VERSION

if "force_rebuild" not in st.session_state:
    st.session_state.force_rebuild = True

initialize_developer_state(st.session_state)


def build_tabs():
    return st.tabs(
        ["AI MACRO", "MARKET", "FINANCE", "COMPUTE", "DATA CENTERS", "CONNECTIVITY", "POWER", "GRID & STORAGE", "WATER", "ADOPTION", "WORKFORCE", "ECONOMIC OUTCOMES", "EVIDENCE"],
        key="domain-navigation",
        on_change="rerun",
    )

def build_sector_dashboard_data(load_policy: LoadPolicy):
    sector_data = {}
    sector_metrics = {}

    ticker_map = {ticker: ticker for ticker in all_tickers()}

    raw_universe_data = load_market_universe(
        ticker_map,
        force_yfinance_refresh=st.session_state.force_yfinance_refresh,
        yfinance_refresh_token=st.session_state.yfinance_refresh_token,
        force_edgar_refresh=st.session_state.force_edgar_refresh,
        edgar_refresh_token=st.session_state.edgar_refresh_token,
        allow_yfinance_live=load_policy.allows_live(RefreshSource.YFINANCE),
        allow_edgar_live=load_policy.allows_live(RefreshSource.EDGAR),
    )
    st.session_state.market_universe_load_report = raw_universe_data.get("_load_report", {})
    benchmark_started = time.perf_counter()
    benchmark_metrics = get_benchmark_metrics_from_market_frame(
        "QQQ",
        raw_universe_data.get("yfinance"),
    )
    benchmark_report = {
        "source_mode": benchmark_metrics.get("source_mode"),
        "elapsed_sec": time.perf_counter() - benchmark_started,
        "returned_tickers": benchmark_metrics.get("member_count", 0),
        "live_tickers": benchmark_metrics.get("live_tickers", 0),
        "archive_fallback_tickers": benchmark_metrics.get("archive_fallback_tickers", 0),
        "missing_tickers": benchmark_metrics.get("missing_tickers", []),
        "latest_data_date": benchmark_metrics.get("market_data_date"),
        "member_aliases": benchmark_metrics.get("member_aliases", {}),
    }
    st.session_state.market_universe_load_report.setdefault("benchmark", {}).update(benchmark_report)

    for sector, cfg in SECTOR_CONFIG.items():
        df = get_sector_data(
            sector,
            cfg["basket"],
            raw_universe_data=raw_universe_data,
        )
        factor_df = calc_sector_factors(
            sector=sector,
            yf_df=df,
            benchmark_metrics=benchmark_metrics,
        )
        sector_data[sector] = df
        sector_metrics[sector] = build_sector_metrics(factor_df, df)

    return sector_data, sector_metrics, raw_universe_data, benchmark_metrics

if st.session_state.force_rebuild:
    refresh_request = st.session_state.get("domain_refresh_request")
    refresh_domains = (
        set(DOMAIN_REFRESH_LABELS)
        if refresh_request == ALL_DOMAIN_REFRESH
        else {refresh_request} if refresh_request else set()
    )
    domain_tokens = dict(st.session_state.get("domain_refresh_tokens", {}) or {})

    def refreshing(domain: str) -> bool:
        return domain in refresh_domains

    def domain_token(domain: str) -> int:
        return int(domain_tokens.get(domain, 0) or 0) if refreshing(domain) else 0

    def combined_domain_token(*domains: str) -> int:
        return max((domain_token(domain) for domain in domains), default=0)

    load_policy = build_load_policy(
        force_yfinance_refresh=st.session_state.force_yfinance_refresh,
        force_edgar_refresh=st.session_state.force_edgar_refresh,
        force_fred_refresh=st.session_state.force_fred_refresh,
        force_nyfed_refresh=st.session_state.force_nyfed_refresh,
        refresh_domains=refresh_domains,
    )
    st.session_state.current_load_policy = load_policy.describe()
    # Consume the request before any network or file work. A downstream failure
    # must not silently replay the same manual refresh on the next rerun.
    st.session_state.domain_refresh_request = None

    sector_data, sector_metrics, raw_universe_data, benchmark_metrics = (
        build_sector_dashboard_data(load_policy)
    )

    fred_started = time.perf_counter()
    fred_data = load_fred(
        force_refresh=st.session_state.force_fred_refresh,
        refresh_token=st.session_state.fred_refresh_token,
        allow_live=load_policy.allows_live(RefreshSource.FRED),
    )
    fred_report = describe_fred_load(
        fred_data,
        elapsed_sec=time.perf_counter() - fred_started,
        force_refresh=st.session_state.force_fred_refresh,
    )
    nfci_history = load_nfci_history(
        force_refresh=st.session_state.force_fred_refresh,
        refresh_token=st.session_state.fred_refresh_token,
        allow_live=load_policy.allows_live(RefreshSource.FRED),
    )

    energy_market_scope = (
        "all" if refreshing("power") and refreshing("grid_storage")
        else "power" if refreshing("power")
        else "grid_storage" if refreshing("grid_storage")
        else "all"
    )
    energy_data = load_energy_data(
        fred_data=fred_data,
        force_refresh=refreshing("power"),
        refresh_token=domain_token("power"),
        force_fred_refresh=st.session_state.force_fred_refresh,
        fred_refresh_token=st.session_state.fred_refresh_token,
        force_market_refresh=refreshing("power") or refreshing("grid_storage"),
        market_refresh_token=combined_domain_token("power", "grid_storage"),
        market_refresh_scope=energy_market_scope,
        allow_supply_live=load_policy.allows_live(RefreshSource.POWER),
        allow_fred_live=load_policy.allows_live(RefreshSource.FRED),
        allow_market_live=(
            load_policy.allows_live(RefreshSource.POWER)
            or load_policy.allows_live(RefreshSource.GRID_STORAGE)
        ),
    )
    debt_markets_data = load_debt_markets_data(
        force_refresh=st.session_state.force_nyfed_refresh,
        refresh_token=st.session_state.nyfed_refresh_token,
        allow_live=load_policy.allows_live(RefreshSource.NYFED),
    )
    infrastructure_data = load_infrastructure_data(
        refresh_token=combined_domain_token("compute", "data_centers", "grid_storage"),
        force_construction_refresh=refreshing("data_centers") or refreshing("grid_storage"),
        force_data_center_refresh=refreshing("data_centers"),
        force_compute_refresh=refreshing("compute"),
        allow_construction_live=(
            load_policy.allows_live(RefreshSource.DATA_CENTERS)
            or load_policy.allows_live(RefreshSource.GRID_STORAGE)
        ),
        allow_data_center_live=load_policy.allows_live(RefreshSource.DATA_CENTERS),
        allow_compute_live=load_policy.allows_live(RefreshSource.COMPUTE),
    )
    connectivity_data = load_connectivity_data(
        infrastructure_data.get("data_center_registry"),
        force_refresh=refreshing("connectivity"),
        refresh_token=domain_token("connectivity"),
        allow_live=load_policy.allows_live(RefreshSource.CONNECTIVITY),
    )
    # Data Centers retains only a compact site-economics cross-signal; the
    # canonical transport evidence and refresh contract live in Connectivity.
    infrastructure_data["connectivity"] = connectivity_data
    construction_data = load_data_center_construction(
        force_refresh=False,
        refresh_token=combined_domain_token("data_centers", "grid_storage"),
        allow_live=False,
    )
    fred_history = load_fred_history()
    macro_history = load_macro_history()
    regime_metrics = build_regime_metrics(
        sector_metrics=sector_metrics,
        sector_data=sector_data,
        fred_history=fred_history,
        fred_data=fred_data,
        construction_data=construction_data,
        macro_history=macro_history,
    )
    water_data = load_water_utilization_data(
        force_refresh=refreshing("water"),
        refresh_token=domain_token("water"),
        allow_live=load_policy.allows_live(RefreshSource.WATER),
    )
    infrastructure_data, water_data = attach_water_context(infrastructure_data, water_data)
    adoption_data = load_adoption_data(
        force_refresh=refreshing("adoption"),
        refresh_token=domain_token("adoption"),
        allow_live=load_policy.allows_live(RefreshSource.ADOPTION),
    )
    workforce_data = load_workforce_data(
        force_refresh=refreshing("workforce"),
        refresh_token=domain_token("workforce"),
        allow_live=load_policy.allows_live(RefreshSource.WORKFORCE),
    )
    economic_impact_data = load_economic_impact_data(
        force_refresh=refreshing("economic_outcomes"),
        refresh_token=domain_token("economic_outcomes"),
        allow_live=load_policy.allows_live(RefreshSource.ECONOMIC_OUTCOMES),
    )
    commercialization_domains = {"compute", "adoption", "economic_outcomes"}
    commercialization_refresh = bool(refresh_domains & commercialization_domains)
    commercialization_data = load_commercialization_data(
        force_refresh=commercialization_refresh,
        refresh_token=combined_domain_token(*commercialization_domains),
        allow_live=any(
            load_policy.allows_live(source)
            for source in (
                RefreshSource.COMPUTE,
                RefreshSource.ADOPTION,
                RefreshSource.ECONOMIC_OUTCOMES,
            )
        ),
    )
    if developer_mode():
        if load_policy.allows_live(RefreshSource.CURRENT_CONTEXT):
            context_refresh = refresh_current_context_once_daily(
                as_of=market_date(),
                force=True,
            )
            context_registry_path = context_refresh.get("registry_path")
        else:
            # Developer startup remains a strict retained-data read.  The
            # owner chooses when to exercise the discovery providers.
            context_refresh = describe_current_context_state()
            context_registry_path = None
        current_context = load_current_context(
            as_of=market_date(),
            path=context_registry_path,
            limit_per_domain=2,
        )
        context_refresh = finalize_context_report(context_refresh, current_context)
        current_context = dict(current_context)
        current_context["snapshot_id"] = context_refresh.get("snapshot_id", "")
        current_context["snapshot_retrieved_at"] = context_refresh.get("retrieved_at", "")
        current_context["snapshot_ttl_seconds"] = context_refresh.get("snapshot_ttl_seconds", 900)
    else:
        # Public Reader mode is a strict retained-state reader. Current Context
        # is refreshed only by the desktop developer workflow or automation worker.
        retained_context = load_retained_context_snapshot(as_of=market_date())
        context_refresh = dict(retained_context.get("report") or {})
        current_context = dict(retained_context.get("current_context") or {})
    st.session_state.current_context_load_report = dict(context_refresh or {})
    if refresh_domains:
        domain_reports = {
            "current_context": context_refresh,
            "compute": {
                "compute": (infrastructure_data.get("compute_manufacturing", {}) or {}).get("load_report", {}),
                "commercialization": commercialization_data.get("load_report", {}),
            },
            "data_centers": infrastructure_data.get("refresh_report", {}),
            "connectivity": connectivity_data.get("load_report", {}),
            "power": energy_data.get("load_report", {}),
            "grid_storage": {
                "source_mode": (energy_data.get("load_report", {}) or {}).get("market_source_mode"),
                "error": (energy_data.get("load_report", {}) or {}).get("market_error"),
                "errors": (energy_data.get("load_report", {}) or {}).get("market_errors", {}),
            },
            "water": water_data.get("refresh_report", {}),
            "adoption": {"adoption": adoption_data.get("load_report", {}), "commercialization": commercialization_data.get("load_report", {})},
            "workforce": workforce_data.get("load_report", {}),
            "economic_outcomes": {"outcomes": economic_impact_data.get("load_report", {}), "commercialization": commercialization_data.get("load_report", {})},
        }
        if refresh_request == ALL_DOMAIN_REFRESH:
            record_domain_refresh(st.session_state, 
                ALL_DOMAIN_REFRESH,
                {domain: domain_reports.get(domain, {}) for domain in DOMAIN_REFRESH_LABELS},
            )
        else:
            record_domain_refresh(st.session_state, refresh_request, domain_reports.get(refresh_request, {}))
    dashboard_data = build_macro_dashboard_data(
        sector_metrics=sector_metrics,
        regime_metrics=regime_metrics,
    )
    read_context = DashboardContext(
        sector_data=sector_data,
        sector_metrics=sector_metrics,
        dashboard_data=dashboard_data,
        regime_metrics=regime_metrics,
        fred_data=fred_data,
        nfci_history=nfci_history,
        energy_data=energy_data,
        debt_markets_data=debt_markets_data,
        infrastructure_data=infrastructure_data,
        connectivity_data=connectivity_data,
        water_data=water_data,
        adoption_data=adoption_data,
        workforce_data=workforce_data,
        economic_impact_data=economic_impact_data,
        commercialization_data=commercialization_data,
        current_context=current_context,
    )
    reader_snapshot = build_reader_snapshot(read_context, context_report=context_refresh)
    platform_reads = reader_snapshot["reads"]
    st.session_state.current_context_load_report.update({
        "reader_snapshot_version": reader_snapshot.get("snapshot_version", ""),
        "read_service_version": reader_snapshot.get("read_service_version", ""),
        "evidence_architecture_version": reader_snapshot.get("evidence_architecture_version", ""),
        "evidence_snapshot_id": reader_snapshot.get("evidence_snapshot_id", ""),
        "snapshot_id": reader_snapshot.get("snapshot_id", context_refresh.get("snapshot_id", "")),
    })
    market_report = dict(st.session_state.get("market_universe_load_report", {}) or {})
    market_report["fred"] = fred_report
    market_report["debt_markets"] = debt_markets_data.get("load_report", {})
    market_report["total_elapsed_sec"] = float(
        market_report.get("total_elapsed_sec", 0.0) or 0.0
    )
    market_report["total_elapsed_sec"] += float(
        fred_report.get("elapsed_sec", 0.0) or 0.0
    )
    market_report["total_elapsed_sec"] += float(
        (debt_markets_data.get("load_report", {}) or {}).get("elapsed_sec", 0.0) or 0.0
    )
    st.session_state.snapshot_write_report = persist_refresh_snapshots(
        policy=load_policy,
        archive_suspended=st.session_state.archive_suspended,
        regime_metrics=regime_metrics,
        fred_data=fred_data,
        fred_report=fred_report,
        sector_metrics=sector_metrics,
        benchmark_metrics=benchmark_metrics,
        sector_data=sector_data,
        raw_universe_data=raw_universe_data,
        energy_data=energy_data,
        debt_markets_data=debt_markets_data,
        edgar_refresh_token=st.session_state.edgar_refresh_token,
    )
    if load_policy.is_explicit_refresh:
        refresh_retained_state_manifest(source="desktop_refresh")
        from helpers.build_release_manifest import build_manifest
        from helpers.atomic_io import atomic_write_json
        atomic_write_json(build_manifest(), PROJECT_ROOT / "data" / "release_manifest.json")


    # Report archive status after persistence, not the pre-refresh status captured
    # before provider work. This makes a successful manual refresh visible
    # immediately in the load report.
    fred_report["latest_complete_date"] = latest_fred_archive_date()
    market_report["fred"] = fred_report
    market_report["load_policy"] = load_policy.describe()
    resolved_tickers = {ticker: ticker for ticker in all_tickers()}
    market_report.setdefault("yfinance", {}).update(
        describe_yf_archive_status(resolved_tickers, sector=None)
    )
    market_report.setdefault("edgar", {}).update(
        describe_edgar_archive_status(resolved_tickers)
    )
    st.session_state.market_universe_load_report = market_report
    # Persist the loaded market frame because Streamlit reruns execute this file
    # from scratch. The masthead renders outside the rebuild block and must not
    # depend on the local raw_universe_data variable surviving a rerun.
    st.session_state.market_snapshot_frame = raw_universe_data.get("yfinance")

    st.session_state.sector_data = sector_data
    st.session_state.sector_metrics = sector_metrics
    st.session_state.fred_data = fred_data
    st.session_state.nfci_history = nfci_history
    st.session_state.construction_data = construction_data
    st.session_state.regime_metrics = regime_metrics
    st.session_state.energy_data = energy_data
    st.session_state.debt_markets_data = debt_markets_data
    st.session_state.infrastructure_data = infrastructure_data
    st.session_state.connectivity_data = connectivity_data
    st.session_state.water_data = water_data
    st.session_state.adoption_data = adoption_data
    st.session_state.workforce_data = workforce_data
    st.session_state.economic_impact_data = economic_impact_data
    st.session_state.commercialization_data = commercialization_data
    st.session_state.dashboard_data = dashboard_data
    st.session_state.platform_reads = platform_reads
    st.session_state.current_context = current_context
    st.session_state.commentary_status = dict(reader_snapshot.get("commentary") or {})
    st.session_state.force_yfinance_refresh = False
    st.session_state.force_edgar_refresh = False
    st.session_state.force_fred_refresh = False
    st.session_state.force_nyfed_refresh = False
    st.session_state.force_rebuild = False

sector_data = st.session_state.sector_data
sector_metrics = st.session_state.sector_metrics
fred_data = st.session_state.fred_data
nfci_history = st.session_state.get("nfci_history")
regime_metrics = st.session_state.regime_metrics
energy_data = st.session_state.get("energy_data", {})
debt_markets_data = st.session_state.get("debt_markets_data", {})
infrastructure_data = st.session_state.get("infrastructure_data", {})
connectivity_data = st.session_state.get("connectivity_data", (infrastructure_data or {}).get("connectivity", {}))
water_data = st.session_state.get("water_data", {})
adoption_data = st.session_state.get("adoption_data", {})
workforce_data = st.session_state.get("workforce_data", {})
economic_impact_data = st.session_state.get("economic_impact_data", {})
commercialization_data = st.session_state.get("commercialization_data", {})
dashboard_data = st.session_state.get("dashboard_data")
platform_reads = st.session_state.get("platform_reads", {})
current_context = st.session_state.get("current_context", {})

# Public Reader sessions never advance research state. A new retained snapshot
# reaches hosted readers only through the publication/deployment path.

loaded_tickers = {
    str(ticker).strip().upper()
    for frame in sector_data.values()
    if frame is not None and not frame.empty and "Ticker" in frame.columns
    for ticker in frame["Ticker"].dropna()
    if str(ticker).strip()
}
configured_tickers = {
    str(ticker).strip().upper()
    for config in SECTOR_CONFIG.values()
    for ticker in config.get("basket", [])
    if str(ticker).strip()
}
market_universe_summary = {
    "loaded_sectors": sum(
        1 for frame in sector_data.values()
        if frame is not None and not frame.empty and "Ticker" in frame.columns
    ),
    "configured_sectors": len(SECTOR_CONFIG),
    "loaded_tickers": int(len(loaded_tickers)),
    "configured_tickers": int(len(configured_tickers)),
    "valuation_context": load_market_valuation_context(),
}

if developer_mode():
    commentary_context = DashboardContext(
        sector_data=sector_data,
        sector_metrics=sector_metrics,
        dashboard_data=dashboard_data,
        regime_metrics=regime_metrics,
        fred_data=fred_data,
        nfci_history=nfci_history,
        energy_data=energy_data,
        debt_markets_data=debt_markets_data,
        infrastructure_data=infrastructure_data,
        connectivity_data=connectivity_data,
        water_data=water_data,
        adoption_data=adoption_data,
        workforce_data=workforce_data,
        economic_impact_data=economic_impact_data,
        commercialization_data=commercialization_data,
        current_context=current_context,
    )
    render_developer_tools(APP_VERSION, commentary_context=commentary_context)

render_masthead(
    "AI Macro",
    "An economic research platform focused on the evolution of the AI economy.",
    version=APP_VERSION,
    status=market_snapshot_label(st.session_state.get("market_snapshot_frame")),
)
render_platform_purpose(METRIC_DEFINITIONS["Purpose Statement"])

developer_canvas_view = st.session_state.get("developer_canvas_view", "Dashboard") if developer_mode() else "Dashboard"
if developer_mode() and developer_canvas_view == "Basket / Tier diagnostics":
    render_basket_tier_developer_tool(sector_data)
else:
    dashboard_context = DashboardContext(
        sector_data=sector_data,
        sector_metrics=sector_metrics,
        fred_data=fred_data,
        regime_metrics=regime_metrics,
        nfci_history=nfci_history,
        energy_data=energy_data,
        debt_markets_data=debt_markets_data,
        infrastructure_data=infrastructure_data,
        connectivity_data=connectivity_data,
        water_data=water_data,
        adoption_data=adoption_data,
        workforce_data=workforce_data,
        economic_impact_data=economic_impact_data,
        commercialization_data=commercialization_data,
        current_context=current_context,
        market_universe_summary=market_universe_summary,
        dashboard_data=dashboard_data,
        platform_reads=platform_reads,
    )
    render_research_dashboard(build_tabs(), dashboard_context)
