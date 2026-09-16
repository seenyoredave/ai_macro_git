"""Dependency-aware deterministic research refresh for publication automation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
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
from automation.refresh_graph import (
    RefreshPlan,
    build_refresh_plan,
    save_refresh_graph_state,
    stable_signature,
)
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
from loaders.current_context_daily import (
    finalize_context_report,
    load_retained_context_snapshot,
    refresh_current_context_once_daily,
)
from loaders.current_context_loader import load_current_context
from loaders.debt_markets_loader import debt_markets_cache_token, load_debt_markets_data
from loaders.economic_impact_loader import load_economic_impact_data
from loaders.energy_loader import attach_power_series, energy_cache_token, load_energy_data
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

_NODE_SOURCE_MAP: dict[str, tuple[RefreshSource, ...]] = {
    "yfinance": (RefreshSource.YFINANCE,),
    "edgar": (RefreshSource.EDGAR,),
    "fred": (RefreshSource.FRED,),
    "nyfed": (RefreshSource.NYFED,),
    "construction": (RefreshSource.DATA_CENTERS,),
    "compute": (RefreshSource.COMPUTE,),
    "data_centers": (RefreshSource.DATA_CENTERS,),
    "connectivity": (RefreshSource.CONNECTIVITY,),
    "power_supply": (RefreshSource.POWER,),
    "grid_storage": (RefreshSource.GRID_STORAGE,),
    "water": (RefreshSource.WATER,),
    "adoption": (RefreshSource.ADOPTION,),
    "workforce": (RefreshSource.WORKFORCE,),
    "economic_outcomes": (RefreshSource.ECONOMIC_OUTCOMES,),
    "current_context": (RefreshSource.CURRENT_CONTEXT,),
    # Commercialization has its own retained bundle and does not participate in
    # generic snapshot_writer authorization.
    "commercialization": (),
}


@dataclass(slots=True)
class RefreshBundle:
    context: DashboardContext
    reports: dict[str, Any]
    snapshot_write_report: dict[str, Any]
    timings: dict[str, float] = field(default_factory=dict)
    refresh_graph_report: dict[str, Any] = field(default_factory=dict)


def _token() -> int:
    return int(time.time_ns() % 2_000_000_000)


def _phase_start(label: str) -> float:
    print(f"[automation] START {label}", flush=True)
    return time.perf_counter()


def _phase_end(label: str, started: float, timings: dict[str, float]) -> None:
    elapsed = max(0.0, time.perf_counter() - started)
    timings[label] = round(elapsed, 3)
    print(f"[automation] DONE  {label} · {elapsed:.1f}s", flush=True)


def _elapsed(started: float) -> float:
    return max(0.0, time.perf_counter() - started)


def _date_token(value: Any) -> str:
    candidate = value or market_date()
    if hasattr(candidate, "date") and not hasattr(candidate, "year"):
        candidate = candidate.date()
    if hasattr(candidate, "isoformat"):
        return str(candidate.isoformat())[:10]
    return str(candidate)[:10]


def _report_mode(report: Any) -> str:
    if not isinstance(report, dict):
        return ""
    return str(
        report.get("source_mode")
        or report.get("refresh_status")
        or report.get("status")
        or ""
    ).strip().lower()


def _node_outcome(report: Any, *, attempted_live: bool) -> tuple[str, str]:
    if not attempted_live:
        return "retained", ""
    payload = dict(report or {}) if isinstance(report, dict) else {}
    mode = _report_mode(payload)
    errors = refresh_errors(payload)
    error_text = "; ".join(errors)
    fatal_tokens = ("unavailable", "failed", "error")
    fallback_only = "fallback" in mode and "live" not in mode and "refresh" not in mode
    if any(token in mode for token in fatal_tokens) or fallback_only:
        return "failed", error_text or f"source_mode={mode or 'unknown'}"
    if "partial" in mode or errors:
        return "partial", error_text
    return "success", ""


def _record_node(
    plan: RefreshPlan,
    node_id: str,
    *,
    attempted_live: bool,
    report: Any,
    semantic_output: Any,
    elapsed_sec: float,
) -> None:
    status, error = _node_outcome(report, attempted_live=attempted_live)
    plan.record(
        node_id,
        attempted_live=attempted_live,
        status=status,
        output_signature=stable_signature(semantic_output),
        elapsed_sec=elapsed_sec,
        error=error,
    )


def _refresh_policy(plan: RefreshPlan) -> LoadPolicy:
    sources: set[RefreshSource] = set()
    for node_id, report in plan.run_report.items():
        if report.get("attempted_live"):
            sources.update(_NODE_SOURCE_MAP.get(node_id, ()))
    return LoadPolicy.refresh(sources) if sources else LoadPolicy.retained()


def _infrastructure_node_report(
    infrastructure_data: dict,
    node_id: str,
) -> dict[str, Any]:
    report = dict((infrastructure_data or {}).get("refresh_report") or {})
    errors = dict(report.get("errors") or {})
    if node_id == "construction":
        relevant = {key: value for key, value in errors.items() if key == "construction"}
        mode = (
            "live_refresh"
            if "construction" in (report.get("refreshed_datasets") or []) and not relevant
            else "partial_refresh"
            if "construction" in (report.get("refreshed_datasets") or [])
            else "retained_fallback"
            if report.get("construction_executed")
            else "retained"
        )
    elif node_id == "compute":
        relevant = {key: value for key, value in errors.items() if str(key).startswith("compute_")}
        mode = str(report.get("compute_source_mode") or "retained")
    elif node_id == "data_centers":
        relevant = {
            key: value
            for key, value in errors.items()
            if key in {"im3_locations", "fractracker"}
        }
        live_parts = bool(report.get("map_refreshed")) or str(
            (report.get("fractracker") or {}).get("source_mode") or ""
        ) == "live_refresh"
        mode = (
            "live_refresh"
            if live_parts and not relevant
            else "partial_refresh"
            if live_parts
            else "retained_fallback"
            if report.get("data_center_executed")
            else "retained"
        )
    else:
        raise KeyError(node_id)
    return {"source_mode": mode, "errors": relevant}


def _energy_node_report(energy_data: dict, node_id: str) -> dict[str, Any]:
    report = dict((energy_data or {}).get("load_report") or {})
    if node_id == "power_supply":
        errors = {}
        if report.get("error"):
            errors["supply"] = report.get("error")
        if report.get("market_error") and str(report.get("market_refresh_scope") or "") in {"all", "power"}:
            errors["power_market"] = report.get("market_error")
        mode = str(report.get("source_mode") or "retained")
        market_mode = str(report.get("market_source_mode") or "")
        if market_mode and market_mode not in {"retained", "retained_local", "archive_read_mode"}:
            if "partial" in market_mode and "partial" not in mode:
                mode = "partial_refresh"
        return {"source_mode": mode, "errors": errors}
    if node_id == "grid_storage":
        errors = dict(report.get("market_errors") or {})
        if report.get("market_error"):
            errors.setdefault("market", report.get("market_error"))
        return {
            "source_mode": str(report.get("market_source_mode") or "retained"),
            "errors": errors,
        }
    raise KeyError(node_id)


def refresh_research_state(*, as_of=None, live: bool = True, run_id: str = "") -> RefreshBundle:
    """Build one complete publication candidate using an incremental source DAG.

    Source nodes decide independently whether a provider contact is due. Nodes
    that are not due execute their retained load path, so the deterministic
    analytics layer always receives a complete current-best state. Dependency
    changes can force downstream provider work earlier than its normal cadence.
    """
    if not automation_mode():
        raise PermissionError("Headless research refresh requires AI_MACRO_MODE=automation.")

    token = _token()
    timings: dict[str, float] = {}
    target_date = as_of or market_date()
    date_token = _date_token(target_date)
    now = datetime.now(timezone.utc)
    plan = build_refresh_plan(
        now=now,
        trigger_tokens={
            "yfinance": date_token,
            "edgar": date_token,
            "fred": date_token,
            "current_context": date_token,
            "power_supply": energy_cache_token(),
            "nyfed": debt_markets_cache_token(),
        },
    )
    if not live:
        for node_id in tuple(plan.decisions):
            plan.retain(node_id, reason="retained_mode")

    ticker_map = {ticker: ticker for ticker in all_tickers()}

    # Source DAG: domain-owned providers. Retained FRED is available before the
    # shared FRED node resolves so Energy can assemble a complete interim state.
    phase_started = _phase_start("domain sources")
    retained_fred_data = load_fred(force_refresh=False, refresh_token=0, allow_live=False)

    construction_live = live and plan.should_refresh("construction")
    compute_live = live and plan.should_refresh("compute")
    data_centers_live = live and plan.should_refresh("data_centers")
    infra_started = time.perf_counter()
    infrastructure_data = load_infrastructure_data(
        refresh_token=token,
        force_construction_refresh=construction_live,
        force_data_center_refresh=data_centers_live,
        force_compute_refresh=compute_live,
        allow_construction_live=construction_live,
        allow_data_center_live=data_centers_live,
        allow_compute_live=compute_live,
    )
    infra_elapsed = _elapsed(infra_started)
    infra_divisor = max(1, int(construction_live) + int(compute_live) + int(data_centers_live))
    _record_node(
        plan,
        "construction",
        attempted_live=construction_live,
        report=_infrastructure_node_report(infrastructure_data, "construction"),
        semantic_output=(infrastructure_data or {}).get("construction_history"),
        elapsed_sec=infra_elapsed / infra_divisor,
    )
    _record_node(
        plan,
        "compute",
        attempted_live=compute_live,
        report=_infrastructure_node_report(infrastructure_data, "compute"),
        semantic_output=(infrastructure_data or {}).get("compute_manufacturing"),
        elapsed_sec=infra_elapsed / infra_divisor,
    )
    _record_node(
        plan,
        "data_centers",
        attempted_live=data_centers_live,
        report=_infrastructure_node_report(infrastructure_data, "data_centers"),
        semantic_output={
            "registry": (infrastructure_data or {}).get("data_center_registry"),
            "entities": (infrastructure_data or {}).get("data_center_entities"),
            "observations": (infrastructure_data or {}).get("data_center_observations"),
            "summary": (infrastructure_data or {}).get("data_center_registry_summary"),
        },
        elapsed_sec=infra_elapsed / infra_divisor,
    )

    if plan.node_changed("data_centers"):
        plan.force_dependents("data_centers")
    connectivity_live = live and plan.should_refresh("connectivity")
    connectivity_started = time.perf_counter()
    connectivity_data = load_connectivity_data(
        infrastructure_data.get("data_center_registry"),
        force_refresh=connectivity_live,
        refresh_token=token if connectivity_live else 0,
        allow_live=connectivity_live,
    )
    _record_node(
        plan,
        "connectivity",
        attempted_live=connectivity_live,
        report=connectivity_data.get("load_report", {}),
        semantic_output={
            key: value
            for key, value in connectivity_data.items()
            if key not in {"load_report", "source_mode"}
        },
        elapsed_sec=_elapsed(connectivity_started),
    )
    infrastructure_data["connectivity"] = connectivity_data

    power_live = live and plan.should_refresh("power_supply")
    grid_live = live and plan.should_refresh("grid_storage")
    market_scope = (
        "all" if power_live and grid_live
        else "power" if power_live
        else "grid_storage" if grid_live
        else "all"
    )
    energy_started = time.perf_counter()
    energy_data = load_energy_data(
        fred_data=retained_fred_data,
        force_refresh=power_live,
        refresh_token=token if power_live else 0,
        force_fred_refresh=False,
        fred_refresh_token=0,
        force_market_refresh=power_live or grid_live,
        market_refresh_token=token if (power_live or grid_live) else 0,
        market_refresh_scope=market_scope,
        allow_supply_live=power_live,
        allow_fred_live=False,
        allow_market_live=power_live or grid_live,
    )
    energy_elapsed = _elapsed(energy_started)
    energy_divisor = max(1, int(power_live) + int(grid_live))
    _record_node(
        plan,
        "power_supply",
        attempted_live=power_live,
        report=_energy_node_report(energy_data, "power_supply"),
        semantic_output={
            "series": energy_data.get("series"),
            "large_load": energy_data.get("large_load_pipeline"),
        },
        elapsed_sec=energy_elapsed / energy_divisor,
    )
    _record_node(
        plan,
        "grid_storage",
        attempted_live=grid_live,
        report=_energy_node_report(energy_data, "grid_storage"),
        semantic_output={
            key: value
            for key, value in energy_data.items()
            if "grid" in str(key).casefold() or "storage" in str(key).casefold() or "queue" in str(key).casefold()
        },
        elapsed_sec=energy_elapsed / energy_divisor,
    )

    water_live = live and plan.should_refresh("water")
    water_started = time.perf_counter()
    water_data = load_water_utilization_data(
        force_refresh=water_live,
        refresh_token=token if water_live else 0,
        allow_live=water_live,
    )
    _record_node(
        plan,
        "water",
        attempted_live=water_live,
        report=water_data.get("refresh_report", {}) or {"source_mode": water_data.get("source_mode")},
        semantic_output={key: value for key, value in water_data.items() if key not in {"refresh_report", "source_mode"}},
        elapsed_sec=_elapsed(water_started),
    )
    infrastructure_data, water_data = attach_water_context(infrastructure_data, water_data)

    adoption_live = live and plan.should_refresh("adoption")
    adoption_started = time.perf_counter()
    adoption_data = load_adoption_data(
        force_refresh=adoption_live,
        refresh_token=token if adoption_live else 0,
        allow_live=adoption_live,
    )
    _record_node(
        plan,
        "adoption",
        attempted_live=adoption_live,
        report=adoption_data.get("load_report", {}),
        semantic_output={key: value for key, value in adoption_data.items() if key not in {"load_report", "source_mode"}},
        elapsed_sec=_elapsed(adoption_started),
    )

    workforce_live = live and plan.should_refresh("workforce")
    workforce_started = time.perf_counter()
    workforce_data = load_workforce_data(
        force_refresh=workforce_live,
        refresh_token=token if workforce_live else 0,
        allow_live=workforce_live,
    )
    _record_node(
        plan,
        "workforce",
        attempted_live=workforce_live,
        report=workforce_data.get("load_report", {}),
        semantic_output={key: value for key, value in workforce_data.items() if key not in {"load_report", "source_mode"}},
        elapsed_sec=_elapsed(workforce_started),
    )

    economic_live = live and plan.should_refresh("economic_outcomes")
    economic_started = time.perf_counter()
    economic_impact_data = load_economic_impact_data(
        force_refresh=economic_live,
        refresh_token=token if economic_live else 0,
        allow_live=economic_live,
    )
    _record_node(
        plan,
        "economic_outcomes",
        attempted_live=economic_live,
        report=economic_impact_data.get("load_report", {}),
        semantic_output={key: value for key, value in economic_impact_data.items() if key not in {"load_report", "source_mode"}},
        elapsed_sec=_elapsed(economic_started),
    )

    commercialization_live = live and plan.should_refresh("commercialization")
    commercialization_started = time.perf_counter()
    commercialization_data = load_commercialization_data(
        force_refresh=commercialization_live,
        refresh_token=token if commercialization_live else 0,
        allow_live=commercialization_live,
    )
    _record_node(
        plan,
        "commercialization",
        attempted_live=commercialization_live,
        report=commercialization_data.get("load_report", {}),
        semantic_output={key: value for key, value in commercialization_data.items() if key not in {"load_report", "source_mode"}},
        elapsed_sec=_elapsed(commercialization_started),
    )
    _phase_end("domain sources", phase_started, timings)

    # Shared market/finance sources. YFinance and EDGAR are independently
    # authorized by the plan; load_market_universe executes the two live calls
    # concurrently when both are due.
    phase_started = _phase_start("market sources")
    yfinance_live = live and plan.should_refresh("yfinance")
    edgar_live = live and plan.should_refresh("edgar")
    market_started = time.perf_counter()
    raw_universe_data = load_market_universe(
        ticker_map,
        force_yfinance_refresh=yfinance_live,
        yfinance_refresh_token=token if yfinance_live else 0,
        force_edgar_refresh=edgar_live,
        edgar_refresh_token=token if edgar_live else 0,
        allow_yfinance_live=yfinance_live,
        allow_edgar_live=edgar_live,
    )
    market_elapsed = _elapsed(market_started)
    market_report = dict(raw_universe_data.get("_load_report", {}) or {})
    _record_node(
        plan,
        "yfinance",
        attempted_live=yfinance_live,
        report=market_report.get("yfinance", {}),
        semantic_output=raw_universe_data.get("yfinance"),
        elapsed_sec=float((market_report.get("yfinance") or {}).get("elapsed_sec") or market_elapsed),
    )
    _record_node(
        plan,
        "edgar",
        attempted_live=edgar_live,
        report=market_report.get("edgar", {}),
        semantic_output=raw_universe_data.get("edgar"),
        elapsed_sec=float((market_report.get("edgar") or {}).get("elapsed_sec") or market_elapsed),
    )

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

    fred_live = live and plan.should_refresh("fred")
    fred_started = time.perf_counter()
    fred_data = load_fred(
        force_refresh=fred_live,
        refresh_token=token if fred_live else 0,
        allow_live=fred_live,
    )
    fred_elapsed = _elapsed(fred_started)
    fred_report = describe_fred_load(
        fred_data,
        elapsed_sec=fred_elapsed,
        force_refresh=fred_live,
    )
    nfci_history = load_nfci_history(
        force_refresh=fred_live,
        refresh_token=token if fred_live else 0,
        allow_live=fred_live,
    )
    _record_node(
        plan,
        "fred",
        attempted_live=fred_live,
        report=fred_report,
        semantic_output={"fred": fred_data, "nfci": nfci_history},
        elapsed_sec=fred_elapsed,
    )

    nyfed_live = live and plan.should_refresh("nyfed")
    nyfed_started = time.perf_counter()
    debt_markets_data = load_debt_markets_data(
        force_refresh=nyfed_live,
        refresh_token=token if nyfed_live else 0,
        allow_live=nyfed_live,
    )
    _record_node(
        plan,
        "nyfed",
        attempted_live=nyfed_live,
        report=debt_markets_data.get("load_report", {}),
        semantic_output={key: value for key, value in debt_markets_data.items() if key not in {"load_report", "source_mode"}},
        elapsed_sec=_elapsed(nyfed_started),
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

    # Current Context is daily and source-grounded. Its retained path is used
    # when the graph says the daily discovery transaction is already current.
    phase_started = _phase_start("current context")
    current_context_live = live and plan.should_refresh("current_context")
    context_started = time.perf_counter()
    if current_context_live:
        context_refresh = refresh_current_context_once_daily(
            as_of=target_date,
            force=bool(plan.force_full),
        )
        current_context = load_current_context(
            as_of=target_date,
            path=context_refresh.get("registry_path"),
            limit_per_domain=4,
        )
        context_refresh = finalize_context_report(context_refresh, current_context)
        current_context = dict(current_context)
        current_context["snapshot_id"] = context_refresh.get("snapshot_id", "")
        current_context["snapshot_retrieved_at"] = context_refresh.get("retrieved_at", "")
    else:
        retained_context = load_retained_context_snapshot(as_of=target_date)
        context_refresh = dict(retained_context.get("report") or {})
        current_context = dict(retained_context.get("current_context") or {})
    _record_node(
        plan,
        "current_context",
        attempted_live=current_context_live,
        report=context_refresh,
        semantic_output=current_context,
        elapsed_sec=_elapsed(context_started),
    )
    _phase_end("current context", phase_started, timings)

    # Assemble and persist the exact evidence state. No provider I/O occurs
    # beyond this boundary.
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

    policy = _refresh_policy(plan)
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

    graph_report = plan.compact_report()
    reports["refresh_graph"] = graph_report

    # Historical canonical reconstruction is automation-owned retained state.
    # Run the migration inside the same publication transaction so the Git
    # transport, rather than an owner commit, publishes the resulting Parquet.
    try:
        from analytics.canonical_history_bootstrap import bootstrap_legacy_canonical_history

        canonical_history_bootstrap_report = bootstrap_legacy_canonical_history(write=True)
        canonical_history_bootstrap_report["source_mode"] = (
            "failed"
            if canonical_history_bootstrap_report.get("errors")
            else str(canonical_history_bootstrap_report.get("status") or "unknown")
        )
    except Exception as exc:
        canonical_history_bootstrap_report = {
            "status": "failed",
            "source_mode": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "errors": [f"{type(exc).__name__}: {exc}"],
        }
    reports["canonical_history_bootstrap"] = canonical_history_bootstrap_report

    try:
        from analytics.canonical_store import persist_canonical_snapshot

        context, canonical_report = persist_canonical_snapshot(
            context,
            observation_date=target_date,
            run_id=run_id,
            publication_source="automation_refresh",
            source_status={key: value for key, value in reports.items() if key != "snapshot_write"},
        )
    except Exception as exc:
        canonical_report = {
            "status": "failed",
            "source_mode": "failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
    reports["canonical"] = canonical_report

    plan.state["last_run_id"] = str(run_id or "")
    plan.state["last_observation_date"] = date_token
    plan.state["last_canonical_snapshot_id"] = str(canonical_report.get("snapshot_id") or "")
    try:
        save_refresh_graph_state(plan.state, now=now)
        graph_report["state_status"] = "written"
    except Exception as exc:
        graph_report["state_status"] = "write_failed"
        graph_report["state_error"] = f"{type(exc).__name__}: {exc}"
    _phase_end("assemble + persist", phase_started, timings)
    return RefreshBundle(
        context=context,
        reports=reports,
        snapshot_write_report=snapshot_write_report,
        timings=timings,
        refresh_graph_report=graph_report,
    )


def refresh_warnings(bundle: RefreshBundle) -> list[str]:
    """Return non-fatal provider degradation while retained evidence remains usable."""
    messages: list[str] = []
    for label, report in bundle.reports.items():
        if label in {"snapshot_write", "refresh_graph"}:
            continue
        if label == "market" and isinstance(report, dict):
            for source_name in ("yfinance", "edgar"):
                source_report = dict(report.get(source_name) or {})
                source_mode = _report_mode(source_report)
                if source_mode in {"partial_refresh", "retained_fallback", "archive_fallback"}:
                    for message in refresh_errors(source_report):
                        messages.append(f"market {source_name}: {message}")
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
    for node_id, node in (bundle.refresh_graph_report.get("nodes") or {}).items():
        if node.get("status") in {"partial", "failed"} and node.get("error"):
            messages.append(f"refresh node {node_id}: {node['error']}")
    if bundle.refresh_graph_report.get("state_status") == "write_failed":
        messages.append(
            "refresh graph state: " + str(bundle.refresh_graph_report.get("state_error") or "write failed")
        )
    for label, message in (
        dict(bundle.snapshot_write_report or {}).get("warnings") or {}
    ).items():
        if message:
            messages.append(f"snapshot {label}: {message}")
    return list(dict.fromkeys(messages))


def blocking_refresh_errors(bundle: RefreshBundle) -> list[str]:
    """Return only failures that make a new publication state unsafe."""
    messages: list[str] = []

    context_report = dict(bundle.reports.get("current_context") or {})
    context_mode = _report_mode(context_report)
    if context_mode in {"failed", "unavailable", "error"}:
        errors = refresh_errors(context_report) or [f"source_mode={context_mode}"]
        messages.extend(f"Current Context: {message}" for message in errors)

    fatal_modes = {"failed", "unavailable", "error"}
    market_report = dict(bundle.reports.get("market") or {})
    for source_name in ("yfinance", "edgar"):
        source_report = dict(market_report.get(source_name) or {})
        source_mode = _report_mode(source_report)
        if source_mode in fatal_modes:
            errors = refresh_errors(source_report) or [f"source_mode={source_mode}"]
            messages.extend(f"market {source_name}: {message}" for message in errors)

    for label, report in bundle.reports.items():
        if label in {"current_context", "snapshot_write", "refresh_graph"}:
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
