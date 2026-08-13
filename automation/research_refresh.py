"""Headless deterministic research refresh using the same loaders as Streamlit."""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any

from analytics.dashboard_context import DashboardContext
from analytics.factor_engine import calc_sector_factors
from analytics.macro_dataframe import build_macro_dashboard_data
from analytics.regime_engine import build_regime_metrics
from analytics.sector_builder import get_sector_data
from analytics.sector_engine import build_sector_metrics
from analytics.spatial_context import attach_water_context
from archive.archive_reader import load_fred_history, load_macro_history
from benchmarks.benchmark_service import get_benchmark_metrics_from_market_frame
from config.deployment import automation_mode
from config.load_policy import LoadPolicy, RefreshSource
from config.market_clock import market_date
from config.sector_config import SECTOR_CONFIG, all_tickers
from developer.state import refresh_errors
from loaders.adoption_loader import load_adoption_data
from loaders.commercialization_loader import load_commercialization_data
from loaders.connectivity_loader import load_connectivity_data
from loaders.construction_loader import load_data_center_construction
from loaders.current_context_daily import finalize_context_report, load_retained_context_snapshot, refresh_current_context_once_daily
from loaders.current_context_loader import load_current_context
from loaders.debt_markets_loader import load_debt_markets_data
from loaders.economic_impact_loader import load_economic_impact_data
from loaders.energy_loader import attach_power_series, load_energy_data
from loaders.fred_loader import describe_fred_load, load_fred
from loaders.infrastructure_loader import load_infrastructure_data
from loaders.market_loader import load_market_universe
from loaders.nfci_loader import load_nfci_history
from loaders.snapshot_writer import persist_refresh_snapshots
from loaders.water_loader import load_water_utilization_data
from loaders.workforce_loader import load_workforce_data


AUTOMATED_DOMAIN_SOURCES = frozenset({
    RefreshSource.COMPUTE,
    RefreshSource.DATA_CENTERS,
    RefreshSource.CONNECTIVITY,
    RefreshSource.POWER,
    RefreshSource.GRID_STORAGE,
    RefreshSource.WATER,
    RefreshSource.ADOPTION,
    RefreshSource.WORKFORCE,
    RefreshSource.ECONOMIC_OUTCOMES,
})
AUTOMATED_MARKET_SOURCES = frozenset({
    RefreshSource.YFINANCE,
    RefreshSource.EDGAR,
    RefreshSource.FRED,
    RefreshSource.NYFED,
})
AUTOMATED_SOURCES = frozenset({
    *AUTOMATED_DOMAIN_SOURCES,
    *AUTOMATED_MARKET_SOURCES,
    RefreshSource.CURRENT_CONTEXT,
})


@dataclass(slots=True)
class RefreshBundle:
    context: DashboardContext
    reports: dict[str, Any]
    snapshot_write_report: dict[str, Any]
    timings: dict[str, float] = field(default_factory=dict)


def _token() -> int:
    return int(time.time_ns() % 2_000_000_000)


def _phase_start(label: str) -> float:
    print(f"[automation] START {label}", flush=True)
    return time.perf_counter()


def _phase_end(label: str, started: float, timings: dict[str, float]) -> None:
    elapsed = max(0.0, time.perf_counter() - started)
    timings[label] = round(elapsed, 3)
    print(f"[automation] DONE  {label} · {elapsed:.1f}s", flush=True)


def refresh_research_state(*, as_of=None, live: bool = True) -> RefreshBundle:
    """Refresh and assemble one publication candidate in dependency order.

    The automation worker is the only non-developer runtime permitted to call
    this function. Public Streamlit never reaches this path. Live automation
    deliberately executes domain-owned providers first, shared market sources
    second, and Current Context third. The final context is assembled only
    after every preceding phase completes, so OpenAI cannot see a partial run.
    """
    if not automation_mode():
        raise PermissionError("Headless research refresh requires AI_MACRO_MODE=automation.")

    token = _token()
    timings: dict[str, float] = {}
    force = bool(live)
    policy = LoadPolicy.refresh(AUTOMATED_SOURCES) if live else LoadPolicy.retained()
    ticker_map = {ticker: ticker for ticker in all_tickers()}

    # Phase 1: refresh every domain-owned provider. Power can be refreshed from
    # its own providers using retained FRED inputs; the fresh shared FRED values
    # are joined after the market-source phase without repeating domain I/O.
    phase_started = _phase_start("domain sources")
    retained_fred_data = load_fred(force_refresh=False, refresh_token=0, allow_live=False)

    infrastructure_data = load_infrastructure_data(
        refresh_token=token,
        force_construction_refresh=force,
        force_facility_refresh=force,
        force_compute_refresh=force,
        allow_construction_live=live,
        allow_facility_live=live,
        allow_compute_live=live,
    )
    connectivity_data = load_connectivity_data(
        infrastructure_data.get("campus_registry"),
        force_refresh=force,
        refresh_token=token,
        allow_live=live,
    )
    infrastructure_data["connectivity"] = connectivity_data

    energy_data = load_energy_data(
        fred_data=retained_fred_data,
        force_refresh=force,
        refresh_token=token,
        force_fred_refresh=False,
        fred_refresh_token=0,
        force_market_refresh=force,
        market_refresh_token=token,
        market_refresh_scope="all",
        allow_supply_live=live,
        allow_fred_live=False,
        allow_market_live=live,
    )
    water_data = load_water_utilization_data(
        force_refresh=force,
        refresh_token=token,
        allow_live=live,
    )
    infrastructure_data, water_data = attach_water_context(infrastructure_data, water_data)
    adoption_data = load_adoption_data(
        force_refresh=force,
        refresh_token=token,
        allow_live=live,
    )
    workforce_data = load_workforce_data(
        force_refresh=force,
        refresh_token=token,
        allow_live=live,
    )
    economic_impact_data = load_economic_impact_data(
        force_refresh=force,
        refresh_token=token,
        allow_live=live,
    )
    commercialization_data = load_commercialization_data(
        force_refresh=force,
        refresh_token=token,
        allow_live=live,
    )
    _phase_end("domain sources", phase_started, timings)

    # Phase 2: refresh the shared market/finance providers, then compute every
    # market-derived frame from that one resolved universe.
    phase_started = _phase_start("market sources")
    raw_universe_data = load_market_universe(
        ticker_map,
        force_yfinance_refresh=force,
        yfinance_refresh_token=token,
        force_edgar_refresh=force,
        edgar_refresh_token=token,
        allow_yfinance_live=live,
        allow_edgar_live=live,
    )
    market_report = dict(raw_universe_data.get("_load_report", {}) or {})
    benchmark_metrics = get_benchmark_metrics_from_market_frame(
        "QQQ", raw_universe_data.get("yfinance")
    )

    sector_data: dict[str, Any] = {}
    sector_metrics: dict[str, Any] = {}
    for sector, cfg in SECTOR_CONFIG.items():
        frame = get_sector_data(sector, cfg["basket"], raw_universe_data=raw_universe_data)
        factors = calc_sector_factors(
            sector=sector,
            yf_df=frame,
            benchmark_metrics=benchmark_metrics,
        )
        sector_data[sector] = frame
        sector_metrics[sector] = build_sector_metrics(factors, frame)

    fred_started = time.perf_counter()
    fred_data = load_fred(
        force_refresh=force,
        refresh_token=token,
        allow_live=live,
    )
    fred_report = describe_fred_load(
        fred_data,
        elapsed_sec=time.perf_counter() - fred_started,
        force_refresh=force,
    )
    nfci_history = load_nfci_history(
        force_refresh=force,
        refresh_token=token,
        allow_live=live,
    )
    debt_markets_data = load_debt_markets_data(
        force_refresh=force,
        refresh_token=token,
        allow_live=live,
    )
    energy_data = attach_power_series(energy_data, fred_data)
    construction_data = load_data_center_construction(
        force_refresh=False,
        refresh_token=token,
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
    _phase_end("market sources", phase_started, timings)

    # Phase 3: refresh contextual developments only after the retained domain
    # and market source state has resolved.
    phase_started = _phase_start("current context")
    if live:
        context_refresh = refresh_current_context_once_daily(
            as_of=as_of or market_date(),
            force=True,
        )
        current_context = load_current_context(
            as_of=as_of or market_date(),
            path=context_refresh.get("registry_path"),
            limit_per_domain=2,
        )
        context_refresh = finalize_context_report(context_refresh, current_context)
        current_context = dict(current_context)
        current_context["snapshot_id"] = context_refresh.get("snapshot_id", "")
        current_context["snapshot_retrieved_at"] = context_refresh.get("retrieved_at", "")
    else:
        retained_context = load_retained_context_snapshot(as_of=as_of or market_date())
        context_refresh = dict(retained_context.get("report") or {})
        current_context = dict(retained_context.get("current_context") or {})
    _phase_end("current context", phase_started, timings)

    # Phase 4: assemble and persist the exact evidence state that generation
    # will receive. No provider calls occur beyond this point.
    phase_started = _phase_start("assemble + persist")
    dashboard_data = build_macro_dashboard_data(
        sector_metrics=sector_metrics,
        regime_metrics=regime_metrics,
    )
    context = DashboardContext(
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

    snapshot_write_report = persist_refresh_snapshots(
        policy=policy,
        archive_suspended=False,
        regime_metrics=regime_metrics,
        fred_data=fred_data,
        fred_report=fred_report,
        sector_metrics=sector_metrics,
        benchmark_metrics=benchmark_metrics,
        sector_data=sector_data,
        raw_universe_data=raw_universe_data,
        energy_data=energy_data,
        debt_markets_data=debt_markets_data,
        edgar_refresh_token=token,
    )

    reports: dict[str, Any] = {
        "market": market_report,
        "fred": fred_report,
        "finance": debt_markets_data.get("load_report", {}),
        "power_grid": energy_data.get("load_report", {}),
        "infrastructure": infrastructure_data.get("refresh_report", {}),
        "connectivity": connectivity_data.get("load_report", {}),
        "water": water_data.get("refresh_report", {}),
        "adoption": adoption_data.get("load_report", {}),
        "workforce": workforce_data.get("load_report", {}),
        "economic_outcomes": economic_impact_data.get("load_report", {}),
        "commercialization": commercialization_data.get("load_report", {}),
        "current_context": context_refresh,
        "snapshot_write": snapshot_write_report,
    }
    _phase_end("assemble + persist", phase_started, timings)
    return RefreshBundle(
        context=context,
        reports=reports,
        snapshot_write_report=snapshot_write_report,
        timings=timings,
    )


def _report_mode(report: Any) -> str:
    if not isinstance(report, dict):
        return ""
    return str(report.get("source_mode") or report.get("refresh_status") or "").strip().lower()


def refresh_warnings(bundle: RefreshBundle) -> list[str]:
    """Return non-fatal refresh degradation retained by a valid data fallback.

    A provider miss is operationally important, but it is not automatically a
    reason to throw away otherwise valid retained evidence.  The automation
    ledger exposes these warnings while publication remains blocked only for
    unavailable/failed required state or snapshot-write failures.
    """
    messages: list[str] = []
    for label, report in bundle.reports.items():
        if label == "snapshot_write":
            continue
        mode = _report_mode(report)
        if label == "current_context":
            if mode in {"failed_retained_fallback", "retained_fallback"}:
                for message in refresh_errors(report):
                    messages.append(f"{label}: {message}")
            continue
        if mode in {"partial_refresh", "retained_fallback", "archive_current", "archive_read_mode"}:
            errors = refresh_errors(report)
            if errors:
                messages.extend(f"{label}: {message}" for message in errors)
    return list(dict.fromkeys(messages))


def blocking_refresh_errors(bundle: RefreshBundle) -> list[str]:
    """Return only refresh failures that make a new release unsafe.

    Retained/partial fallbacks remain usable evidence and are reported as
    warnings instead.  Hard failure is reserved for unavailable/failed required
    state and any failure to persist the deterministic snapshot transaction.
    """
    messages: list[str] = []

    context_report = dict(bundle.reports.get("current_context") or {})
    context_mode = _report_mode(context_report)
    if context_mode in {"failed", "unavailable", "error"}:
        errors = refresh_errors(context_report) or [f"source_mode={context_mode}"]
        messages.extend(f"Current Context: {message}" for message in errors)

    fatal_modes = {"failed", "unavailable", "error"}
    for label, report in bundle.reports.items():
        if label in {"current_context", "snapshot_write"}:
            continue
        mode = _report_mode(report)
        if mode in fatal_modes:
            errors = refresh_errors(report) or [f"source_mode={mode}"]
            messages.extend(f"{label}: {message}" for message in errors)

    write_report = dict(bundle.snapshot_write_report or {})
    for key, message in (write_report.get("errors") or {}).items():
        if message:
            messages.append(f"snapshot {key}: {message}")
    return list(dict.fromkeys(messages))
