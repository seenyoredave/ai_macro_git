from __future__ import annotations

from pathlib import Path
import sys
import time
import warnings

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
from analytics.context_read_snapshot import build_context_read_pair
from analytics.factor_engine import calc_sector_factors
from analytics.regime_engine import build_regime_metrics
from analytics.macro_dataframe import build_macro_dashboard_data
from analytics.sector_engine import build_sector_metrics
from archive.archive_reader import load_fred_history, load_macro_history
from benchmarks.benchmark_service import get_benchmark_metrics_from_market_frame
from config.deployment import developer_mode
from config.load_policy import LoadPolicy, RefreshSource, build_load_policy
from config.market_clock import market_date, utc_now
from config.metric_definitions import METRIC_DEFINITIONS
from config.sector_config import SECTOR_CONFIG, all_tickers
from rendering.sector import render_basket_tier_developer_tool
from loaders.construction_loader import load_data_center_construction
from loaders.debt_markets_loader import load_debt_markets_data
from loaders.energy_loader import load_energy_data
from loaders.infrastructure_loader import load_infrastructure_data
from loaders.connectivity_loader import load_connectivity_data
from loaders.workforce_loader import load_workforce_data
from loaders.economic_impact_loader import load_economic_impact_data
from loaders.water_loader import load_water_utilization_data
from loaders.adaptation_loader import load_adaptation_data
from loaders.commercialization_loader import load_commercialization_data
from loaders.fred_loader import describe_fred_load, latest_fred_archive_date, load_fred
from loaders.market_loader import describe_edgar_archive_status, describe_yf_archive_status, load_market_universe
from loaders.market_valuation_loader import load_market_valuation_context
from loaders.nfci_loader import load_nfci_history
from loaders.snapshot_writer import persist_refresh_snapshots
from loaders.weekly_context_loader import load_current_context, load_weekly_context
from loaders.current_context_daily import (
    describe_current_context_state,
    finalize_context_report,
    load_public_shared_context_snapshot,
    refresh_current_context_once_daily,
)
from rendering.components import render_masthead, render_platform_purpose
from rendering.snapshot_status import market_snapshot_label
from rendering.dashboard import render_research_dashboard
from rendering.theme import inject_research_theme
from analytics.sector_builder import get_sector_data
from analytics.spatial_context import attach_water_context

APP_VERSION = "v6.10.19"
APP_STATE_SCHEMA_VERSION = "68.0-source-grounded-current-context"

DOMAIN_REFRESH_LABELS = {
    "current_context": "Current Context",
    "compute": "Compute",
    "data_centers": "Data Centers",
    "connectivity": "Connectivity",
    "power": "Power",
    "grid_storage": "Grid & Storage",
    "water": "Water",
    "adoption": "Adoption",
    "workforce": "Workforce",
    "economic_outcomes": "Economic Outcomes",
}
ALL_DOMAIN_REFRESH = "__all_domains__"

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

if "tier_test_module_open" not in st.session_state:
    st.session_state.tier_test_module_open = False

if "developer_load_report_open" not in st.session_state:
    st.session_state.developer_load_report_open = False

if "force_yfinance_refresh" not in st.session_state:
    st.session_state.force_yfinance_refresh = False

if "force_edgar_refresh" not in st.session_state:
    st.session_state.force_edgar_refresh = False

if "yfinance_refresh_token" not in st.session_state:
    st.session_state.yfinance_refresh_token = 0

if "edgar_refresh_token" not in st.session_state:
    st.session_state.edgar_refresh_token = 0

if "force_fred_refresh" not in st.session_state:
    st.session_state.force_fred_refresh = False

if "fred_refresh_token" not in st.session_state:
    st.session_state.fred_refresh_token = 0

if "force_nyfed_refresh" not in st.session_state:
    st.session_state.force_nyfed_refresh = False

if "nyfed_refresh_token" not in st.session_state:
    st.session_state.nyfed_refresh_token = 0

if "domain_refresh_request" not in st.session_state:
    st.session_state.domain_refresh_request = None

if "domain_refresh_tokens" not in st.session_state:
    st.session_state.domain_refresh_tokens = {
        key: 0 for key in DOMAIN_REFRESH_LABELS
    }

if "last_domain_refresh" not in st.session_state:
    st.session_state.last_domain_refresh = None


def request_domain_refresh(domain: str) -> None:
    if domain not in DOMAIN_REFRESH_LABELS:
        raise KeyError(f"Unknown domain refresh: {domain}")
    tokens = dict(st.session_state.domain_refresh_tokens)
    tokens[domain] = int(tokens.get(domain, 0) or 0) + 1
    st.session_state.domain_refresh_tokens = tokens
    st.session_state.domain_refresh_request = domain
    st.session_state.force_rebuild = True


def request_all_domain_refreshes() -> None:
    tokens = dict(st.session_state.domain_refresh_tokens)
    for domain in DOMAIN_REFRESH_LABELS:
        tokens[domain] = int(tokens.get(domain, 0) or 0) + 1
    st.session_state.domain_refresh_tokens = tokens
    st.session_state.domain_refresh_request = ALL_DOMAIN_REFRESH
    st.session_state.force_rebuild = True


SOURCE_REFRESH_STATE = {
    "yfinance": ("force_yfinance_refresh", "yfinance_refresh_token"),
    "edgar": ("force_edgar_refresh", "edgar_refresh_token"),
    "fred": ("force_fred_refresh", "fred_refresh_token"),
    "nyfed": ("force_nyfed_refresh", "nyfed_refresh_token"),
}


def request_source_refresh(source: str) -> None:
    """Arm one provider refresh before Streamlit reruns the application."""
    if source not in SOURCE_REFRESH_STATE:
        raise KeyError(f"Unknown source refresh: {source}")
    force_key, token_key = SOURCE_REFRESH_STATE[source]
    st.session_state[token_key] = int(st.session_state.get(token_key, 0) or 0) + 1
    st.session_state[force_key] = True
    st.session_state.force_rebuild = True
    # Show the transaction that was just requested without requiring a second
    # button click/rerun after the provider work finishes.
    st.session_state.developer_load_report_open = True


def request_all_source_refreshes() -> None:
    for source in SOURCE_REFRESH_STATE:
        force_key, token_key = SOURCE_REFRESH_STATE[source]
        st.session_state[token_key] = int(st.session_state.get(token_key, 0) or 0) + 1
        st.session_state[force_key] = True
    st.session_state.force_rebuild = True
    st.session_state.developer_load_report_open = True


def _refresh_errors(payload) -> list[str]:
    messages: list[str] = []

    def visit(value) -> None:
        if isinstance(value, dict):
            error = value.get("error")
            if error:
                messages.append(str(error))
            errors = value.get("errors")
            if isinstance(errors, dict):
                messages.extend(str(message) for message in errors.values() if message)
            for key, nested in value.items():
                if key not in {"error", "errors"} and isinstance(nested, (dict, list, tuple)):
                    visit(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                visit(nested)

    visit(payload)
    return list(dict.fromkeys(messages))


def _record_domain_refresh(domain: str, report: dict | None) -> None:
    payload = dict(report or {})
    mode = str(
        payload.get("source_mode")
        or payload.get("refresh_status")
        or "completed"
    )
    st.session_state.last_domain_refresh = {
        "domain": domain,
        "label": "All domains" if domain == ALL_DOMAIN_REFRESH else DOMAIN_REFRESH_LABELS.get(domain, domain),
        "source_mode": mode,
        "completed_at_utc": utc_now().isoformat(),
        "errors": _refresh_errors(payload),
    }

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

def render_developer_load_report(report):
    if not report:
        st.caption("No load report is available yet.")
        return

    policy = dict(
        (report or {}).get("load_policy")
        or st.session_state.get("current_load_policy", {})
        or {}
    )
    if policy:
        sources = policy.get("refresh_sources") or []
        source_labels = {
            "yfinance": "YFinance",
            "edgar": "EDGAR",
            "fred": "FRED",
            "nyfed": "NY Fed",
            "current_context": "Current Context",
            "compute": "Compute",
            "data_centers": "Data Centers",
            "connectivity": "Connectivity",
            "power": "Power",
            "grid_storage": "Grid & Storage",
            "water": "Water",
            "adoption": "Adoption",
            "workforce": "Workforce",
            "economic_outcomes": "Economic Outcomes",
        }
        if sources:
            source_text = ", ".join(source_labels.get(source, source) for source in sources)
            st.caption(f"Live refresh requested: {source_text}")
        else:
            st.caption("Load mode: retained data")

    def fmt_seconds(value):
        try:
            return f"{float(value):.2f}s"
        except Exception:
            return "n/a"

    def render_source(label, block):
        block = block or {}
        missing = block.get("missing_tickers") or block.get("missing_series") or []
        stale = block.get("recent_missing_tickers") or []
        fallback_symbols = block.get("archive_fallback_symbols") or []
        st.markdown(f"**{label}**")
        st.write(f"Mode: `{block.get('source_mode', 'unknown')}`")
        st.write(f"Elapsed: `{fmt_seconds(block.get('elapsed_sec'))}`")
        returned = block.get("returned_series", block.get("returned_tickers", 0))
        unit = "series" if "returned_series" in block else "tickers"
        st.write(f"Returned: `{returned}` {unit}")
        if block.get("decision"):
            st.write(f"Decision: `{block.get('decision')}`")
        if block.get("refresh_trigger"):
            trigger_label = "Release" if label == "NY Fed" else "Refresh"
            st.write(f"{trigger_label}: `{block.get('refresh_trigger')}`")
        if "archive_tickers" in block:
            st.write(f"Archive rows: `{block.get('archive_tickers', 0)}` tickers")
        if "live_tickers" in block:
            st.write(f"Live rows: `{block.get('live_tickers', 0)}` tickers")
            fallback_rows = int(block.get("archive_fallback_tickers", 0) or 0)
            fallback_fields = int(block.get("archive_field_backfills", 0) or 0)
            if fallback_rows:
                st.write(f"Retained ticker rows: `{fallback_rows}`")
            if fallback_fields:
                st.write(f"Retained field fills: `{fallback_fields}`")
                columns = block.get("archive_field_backfill_columns") or {}
                if columns:
                    summary = ", ".join(
                        f"{column} ({count})"
                        for column, count in sorted(columns.items())
                    )
                    st.caption(f"Fields filled from the prior snapshot: {summary}")
        if label == "YFinance" and block.get("provider_fetch_attempts"):
            st.caption(
                "Provider pacing: "
                f"{int(block.get('provider_initial_workers') or 0)} initial workers · "
                f"batch {int(block.get('provider_batch_size') or 0)} · "
                f"{int(block.get('provider_fetch_attempts') or 0)} ticker attempts"
            )
            retry_rounds = int(block.get("provider_retry_rounds") or 0)
            rate_limits = int(block.get("provider_rate_limit_events") or 0)
            if retry_rounds:
                delays = block.get("provider_retry_delays_sec") or []
                delay_text = ", ".join(f"{float(value):.1f}s" for value in delays) if delays else "adaptive"
                st.caption(f"YFinance retries: {retry_rounds} round(s) · cooldowns {delay_text}")
            if rate_limits:
                st.warning(f"YFinance rate-limit signals observed: {rate_limits}; adaptive cooldown was applied.")
            provider_failed = block.get("provider_failed_tickers") or []
            if provider_failed:
                st.caption(f"Provider misses after retries ({len(provider_failed)}): {', '.join(provider_failed[:30])}")
        if block.get("requested_at_utc"):
            st.write(f"Requested: `{block.get('requested_at_utc')}`")
        if block.get("latest_complete_date"):
            st.write(f"Latest complete archive: `{block.get('latest_complete_date')}`")
        if block.get("latest_data_date"):
            st.write(f"Data through: `{block.get('latest_data_date')}`")
        if block.get("market_source_mode"):
            st.write(f"Market backbone: `{block.get('market_source_mode')}`")
            returned_rows = block.get("market_returned_rows") or {}
            if returned_rows:
                st.write(f"Market rows: `{sum(int(value or 0) for value in returned_rows.values()):,}`")
        if block.get("market_error"):
            st.error(str(block.get("market_error")))
        if block.get("live_error"):
            st.error(f"Live refresh failed: {block.get('live_error')}")
        if block.get("error"):
            st.error(str(block.get("error")))
        attempted = block.get("live_attempted_tickers") or []
        succeeded = block.get("live_succeeded_tickers") or []
        failed = block.get("live_failed_tickers") or []
        rejected = block.get("live_rejected_quality_tickers") or []
        if attempted:
            st.write(
                "Live refresh: "
                f"`{len(succeeded)}` succeeded · `{len(failed)}` failed · "
                f"`{len(rejected)}` kept retained values"
            )
        if fallback_symbols:
            shown = ", ".join(fallback_symbols[:30])
            suffix = "" if len(fallback_symbols) <= 30 else f" … +{len(fallback_symbols) - 30}"
            st.caption(f"Archive row fallback ({len(fallback_symbols)}): {shown}{suffix}")
        if missing:
            shown = ", ".join(missing[:30])
            suffix = "" if len(missing) <= 30 else f" … +{len(missing) - 30}"
            st.caption(f"Missing from resolved load ({len(missing)}): {shown}{suffix}")
        if stale and label == "EDGAR":
            shown = ", ".join(stale[:30])
            suffix = "" if len(stale) <= 30 else f" … +{len(stale) - 30}"
            freshness_days = block.get("freshness_days")
            window = f"{freshness_days}-day freshness window" if freshness_days else "freshness window"
            st.caption(f"Older retained EDGAR rows ({len(stale)}) outside the {window}: {shown}{suffix}")

    st.caption(f"Total load: {fmt_seconds(report.get('total_elapsed_sec'))}")
    render_source("YFinance", report.get("yfinance"))
    benchmark_block = dict(report.get("benchmark") or {})
    if benchmark_block:
        st.markdown("**QQQ reference**")
        st.write(f"Mode: `{benchmark_block.get('source_mode', 'unknown')}`")
        st.write(f"Returned: `{benchmark_block.get('returned_tickers', 0)}` members")
        if benchmark_block.get("latest_data_date"):
            st.write(f"Data through: `{benchmark_block.get('latest_data_date')}`")
        aliases = benchmark_block.get("member_aliases") or {}
        if aliases:
            alias_text = ", ".join(f"{target} from {source}" for target, source in sorted(aliases.items()))
            st.caption(f"Retained-universe class mapping: {alias_text}")
        if benchmark_block.get("live_error"):
            st.error(f"Benchmark refresh failed: {benchmark_block.get('live_error')}")
    st.markdown("---")
    render_source("EDGAR", report.get("edgar"))
    st.markdown("---")
    render_source("FRED", report.get("fred"))
    st.markdown("---")
    render_source("NY Fed", report.get("debt_markets"))
    write_report = dict(st.session_state.get("snapshot_write_report", {}) or {})
    if write_report:
        st.markdown("---")
        written = write_report.get("written") or []
        retained_by_loader = write_report.get("retained_by_loader") or []
        saved = list(dict.fromkeys([*written, *retained_by_loader]))
        st.markdown("**Retained data writes**")
        st.write(f"Status: `{write_report.get('status', 'unknown')}`")
        st.write(f"Saved: `{', '.join(saved) if saved else 'none'}`")
        finance_derivatives = dict(write_report.get("finance_derivatives") or {})
        if finance_derivatives:
            st.markdown("**Finance derivatives**")
            fundamental_count = int(finance_derivatives.get("fundamental_companies") or 0)
            debt_count = int(finance_derivatives.get("debt_companies") or 0)
            debt_target = int(finance_derivatives.get("debt_target_companies") or 0)
            st.write(f"SEC fundamentals: `{fundamental_count}/10` companies")
            st.write(f"Definition-matched debt: `{debt_count}/{debt_target or 0}` companies")
            updated = finance_derivatives.get("debt_updated_tickers") or []
            reviewed = finance_derivatives.get("debt_reviewed_tickers") or []
            unresolved = finance_derivatives.get("debt_unresolved_tickers") or []
            if updated:
                st.caption(f"Debt updated automatically ({len(updated)}): {', '.join(updated)}")
            if reviewed:
                st.caption(f"Debt filing-reviewed fallback ({len(reviewed)}): {', '.join(reviewed)}")
            if unresolved:
                st.warning(f"Debt unresolved ({len(unresolved)}): {', '.join(unresolved)}")
        if write_report.get("reason"):
            st.caption(f"Reason: {write_report.get('reason')}")
        for label, message in (write_report.get("errors") or {}).items():
            st.error(f"{label}: {message}")

if developer_mode():
    with st.sidebar:
        st.markdown(
            f"""
            <div class="rm-developer-tools-header">
                <span class="rm-developer-tools-title">Developer Tools</span>
                <span class="rm-developer-tools-version">ver. {APP_VERSION.removeprefix("v")}</span>
            </div>
            <div class="rm-developer-tools-divider"></div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("Rebuild from retained data", use_container_width=True):
            st.session_state.force_rebuild = True
            st.rerun()

        if st.button("Clear cache", use_container_width=True):
            st.cache_data.clear()
            st.session_state.force_rebuild = True
            st.rerun()

        archive_label = "Resume archive" if st.session_state.archive_suspended else "Suspend archive"
        if st.button(archive_label, use_container_width=True):
            st.session_state.archive_suspended = not st.session_state.archive_suspended
            st.rerun()

        st.markdown("---")
        context_block = dict(st.session_state.get("current_context_load_report") or {})
        if context_block:
            st.markdown("**Current Context**")
            st.write(f"Mode: `{context_block.get('source_mode', context_block.get('refresh_status', 'unknown'))}`")
            st.write(f"Engine: `{context_block.get('engine_version', 'unknown')}` · retained snapshot: `{context_block.get('retained_discovery_version', context_block.get('discovery_version', 'unknown'))}`")
            if context_block.get("snapshot_id"):
                st.write(
                    f"Snapshot: `{context_block.get('snapshot_id')}` · "
                    f"Context+Read pair: `{context_block.get('context_read_pair_version', 'pending')}`"
                )
            if context_block.get("as_of"):
                st.write(f"Context as of: `{context_block.get('as_of')}`")
            if "candidate_count" in context_block:
                st.write(f"Candidates: `{int(context_block.get('candidate_count', 0) or 0)}` · qualified: `{int(context_block.get('qualified_count', 0) or 0)}`")
            grounding = context_block.get("grounding") or {}
            if grounding:
                st.write(
                    f"Source grounding: `{int(grounding.get('succeeded', 0) or 0)}/{int(grounding.get('attempted', 0) or 0)}` "
                    f"succeeded · `{int(grounding.get('failed', 0) or 0)}` rejected · contract `{grounding.get('version', 'unknown')}`"
                )
                rejection_reasons = grounding.get("rejection_reasons") or []
                if rejection_reasons:
                    with st.expander("Source-grounding rejection reasons", expanded=False):
                        for row in rejection_reasons[:8]:
                            st.write(f"`{int(row.get('count', 0) or 0)}` · {row.get('reason', '')}")
                by_domain_grounding = grounding.get("by_domain") or {}
                if by_domain_grounding:
                    with st.expander("Source-grounding by domain", expanded=False):
                        for domain, row in by_domain_grounding.items():
                            if not isinstance(row, dict):
                                continue
                            metadata_count = int(row.get("metadata_qualified", 0) or 0)
                            attempted_count = int(row.get("attempted", 0) or 0)
                            succeeded_count = int(row.get("succeeded", 0) or 0)
                            selected_count = int(row.get("selected", 0) or 0)
                            if domain not in {"market", "finance"} and not any((metadata_count, attempted_count, succeeded_count, selected_count)):
                                continue
                            st.write(
                                f"**{domain.replace('_', ' ').title()}** · metadata `{metadata_count}` · "
                                f"attempted `{attempted_count}` · grounded `{succeeded_count}` · selected `{selected_count}`"
                            )
                            domain_reasons = row.get("rejection_reasons") or []
                            for reason_row in domain_reasons[:3]:
                                st.caption(
                                    f"Rejected {int(reason_row.get('count', 0) or 0)} · {reason_row.get('reason', '')}"
                                )
            selected_counts = context_block.get("selected_counts") or {
                domain: len(items) if isinstance(items, list) else 0
                for domain, items in (context_block.get("selected") or {}).items()
            }
            if selected_counts:
                st.write(
                    "Selected: "
                    + " · ".join(
                        f"{domain.replace('_', ' ').title()} `{count}`"
                        for domain, count in selected_counts.items()
                        if domain in {"market", "finance"} or int(count or 0) > 0
                    )
                )
            rendered_counts = context_block.get("rendered_context_counts") or {}
            if rendered_counts:
                st.write(
                    "Rendered: "
                    + " · ".join(
                        f"{domain.replace('_', ' ').title()} `{count}`"
                        for domain, count in rendered_counts.items()
                        if domain in {"market", "finance"} or int(count or 0) > 0
                    )
                )
            if context_block.get("engine_mismatch") or context_block.get("refresh_required"):
                st.warning("Retained Current Context predates the installed discovery engine. Use Refresh Current Context to exercise the new policy.")
            fetch_errors = context_block.get("fetch_errors") or [
                row for row in (context_block.get("fetch_status") or [])
                if isinstance(row, dict) and str(row.get("error") or "").strip()
            ]
            if fetch_errors:
                with st.expander(f"Current Context provider errors ({len(fetch_errors)})", expanded=False):
                    for row in fetch_errors[:20]:
                        st.write(f"{row.get('domain', '')}:{row.get('provider', '')}: {row.get('error', '')}")
            st.markdown("---")

        st.markdown("**Refresh data sources**")

        st.button(
            "Refresh All Sources",
            use_container_width=True,
            on_click=request_all_source_refreshes,
            key="refresh-all-sources",
        )
        st.button(
            "Refresh YFinance",
            use_container_width=True,
            on_click=request_source_refresh,
            args=("yfinance",),
            key="refresh-yfinance",
        )
        st.button(
            "Refresh EDGAR",
            use_container_width=True,
            on_click=request_source_refresh,
            args=("edgar",),
            key="refresh-edgar",
        )
        st.button(
            "Refresh FRED",
            use_container_width=True,
            on_click=request_source_refresh,
            args=("fred",),
            key="refresh-fred",
        )
        st.button(
            "Refresh NY Fed",
            use_container_width=True,
            on_click=request_source_refresh,
            args=("nyfed",),
            key="refresh-nyfed",
        )

        st.markdown("---")
        st.markdown("**Refresh domains**")
        if st.button("Refresh All Domains", use_container_width=True):
            request_all_domain_refreshes()
            st.rerun()
        for domain, label in DOMAIN_REFRESH_LABELS.items():
            if st.button(f"Refresh {label}", use_container_width=True, key=f"refresh-domain-{domain}"):
                request_domain_refresh(domain)
                st.rerun()
        st.caption("Evidence updates with the source domains above.")
        last_domain_refresh = st.session_state.get("last_domain_refresh") or {}
        if last_domain_refresh:
            st.caption(
                "Last domain refresh: "
                f"{last_domain_refresh.get('label')} · "
                f"{last_domain_refresh.get('source_mode')}"
            )
            refresh_warnings = last_domain_refresh.get("errors") or []
            if refresh_warnings:
                with st.expander("Refresh warnings", expanded=False):
                    for warning in refresh_warnings:
                        st.write(str(warning))

        st.markdown("---")

        if st.button(
            "Close tier diagnostics" if st.session_state.tier_test_module_open else "Open tier diagnostics",
            use_container_width=True,
        ):
            st.session_state.tier_test_module_open = not st.session_state.tier_test_module_open
            st.rerun()

        if st.button(
            "Close load report" if st.session_state.developer_load_report_open else "Open load report",
            use_container_width=True,
        ):
            st.session_state.developer_load_report_open = not st.session_state.developer_load_report_open
            st.rerun()

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
        allow_live=(
            load_policy.allows_live(RefreshSource.FRED)
            or load_policy.allows_live(RefreshSource.POWER)
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
        force_facility_refresh=refreshing("data_centers"),
        force_compute_refresh=refreshing("compute"),
    )
    connectivity_data = load_connectivity_data(
        infrastructure_data.get("campus_registry"),
        force_refresh=refreshing("connectivity"),
        refresh_token=domain_token("connectivity"),
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
    )
    infrastructure_data, water_data = attach_water_context(infrastructure_data, water_data)
    adaptation_data = load_adaptation_data(
        force_refresh=refreshing("adoption"),
        refresh_token=domain_token("adoption"),
        allow_live=load_policy.allows_live(RefreshSource.ADOPTION),
    )
    workforce_data = load_workforce_data(
        force_refresh=refreshing("workforce"),
        refresh_token=domain_token("workforce"),
    )
    economic_impact_data = load_economic_impact_data(
        force_refresh=refreshing("economic_outcomes"),
        refresh_token=domain_token("economic_outcomes"),
    )
    commercialization_domains = {"compute", "adoption", "economic_outcomes"}
    commercialization_refresh = bool(refresh_domains & commercialization_domains)
    commercialization_data = load_commercialization_data(
        force_refresh=commercialization_refresh,
        refresh_token=combined_domain_token(*commercialization_domains),
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
        sector_weekly_context = load_weekly_context(
            as_of=market_date(),
            path=context_registry_path,
            surface="sector",
            limit=15,
        )
        context_refresh = finalize_context_report(context_refresh, current_context)
        current_context = dict(current_context)
        current_context["snapshot_id"] = context_refresh.get("snapshot_id", "")
        current_context["snapshot_retrieved_at"] = context_refresh.get("retrieved_at", "")
        current_context["snapshot_ttl_seconds"] = context_refresh.get("snapshot_ttl_seconds", 900)
    else:
        # Reader mode keeps repository data immutable while allowing the
        # ephemeral Current Context layer to advance as one shared ~15-minute
        # packet.  Streamlit's shared cache means contemporaneous readers see
        # the same Context rather than independently hitting discovery feeds.
        shared_context = load_public_shared_context_snapshot(as_of=market_date())
        context_refresh = dict(shared_context.get("report") or {})
        current_context = dict(shared_context.get("current_context") or {})
        sector_weekly_context = dict(shared_context.get("sector_weekly_context") or {})
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
            "adoption": {"adoption": adaptation_data.get("load_report", {}), "commercialization": commercialization_data.get("load_report", {})},
            "workforce": workforce_data.get("load_report", {}),
            "economic_outcomes": {"outcomes": economic_impact_data.get("load_report", {}), "commercialization": commercialization_data.get("load_report", {})},
        }
        if refresh_request == ALL_DOMAIN_REFRESH:
            _record_domain_refresh(
                ALL_DOMAIN_REFRESH,
                {domain: domain_reports.get(domain, {}) for domain in DOMAIN_REFRESH_LABELS},
            )
        else:
            _record_domain_refresh(refresh_request, domain_reports.get(refresh_request, {}))
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
        adaptation_data=adaptation_data,
        workforce_data=workforce_data,
        economic_impact_data=economic_impact_data,
        commercialization_data=commercialization_data,
        current_context=current_context,
    )
    context_read_pair = build_context_read_pair(read_context, context_report=context_refresh)
    platform_reads = context_read_pair["reads"]
    st.session_state.current_context_load_report.update({
        "context_read_pair_version": context_read_pair.get("pair_version", ""),
        "read_architecture_version": context_read_pair.get("read_architecture_version", ""),
        "snapshot_id": context_read_pair.get("snapshot_id", context_refresh.get("snapshot_id", "")),
    })
    regime_metrics["Macro Interpretation"] = platform_reads["macro"]
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
    st.session_state.adaptation_data = adaptation_data
    st.session_state.workforce_data = workforce_data
    st.session_state.economic_impact_data = economic_impact_data
    st.session_state.commercialization_data = commercialization_data
    st.session_state.sector_weekly_context = sector_weekly_context
    st.session_state.dashboard_data = dashboard_data
    st.session_state.platform_reads = platform_reads
    st.session_state.force_yfinance_refresh = False
    st.session_state.force_edgar_refresh = False
    st.session_state.force_fred_refresh = False
    st.session_state.force_nyfed_refresh = False
    st.session_state.force_rebuild = False

# Render the developer load report only after any requested rebuild has
# completed, so the visible report always describes the transaction that just
# ran rather than the previous session-state snapshot.
if developer_mode() and st.session_state.developer_load_report_open:
    with st.sidebar:
        st.markdown("---")
        render_developer_load_report(st.session_state.get("market_universe_load_report"))

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
adaptation_data = st.session_state.get("adaptation_data", {})
workforce_data = st.session_state.get("workforce_data", {})
economic_impact_data = st.session_state.get("economic_impact_data", {})
commercialization_data = st.session_state.get("commercialization_data", {})
sector_weekly_context = st.session_state.get("sector_weekly_context", {})
dashboard_data = st.session_state.get("dashboard_data")
platform_reads = st.session_state.get("platform_reads", {})

# Public Reader sessions can remain open across several Current Context cache
# windows.  Ask only for the shared cached packet on every Streamlit rerun; if
# its snapshot id advanced, rebuild the deterministic Reads against the already
# loaded immutable analytical data without reloading any retained-data provider.
if not developer_mode():
    shared_context = load_public_shared_context_snapshot(as_of=market_date())
    shared_report = dict(shared_context.get("report") or {})
    previous_report = dict(st.session_state.get("current_context_load_report") or {})
    if str(shared_report.get("snapshot_id") or "") != str(previous_report.get("snapshot_id") or ""):
        current_context = dict(shared_context.get("current_context") or {})
        sector_weekly_context = dict(shared_context.get("sector_weekly_context") or {})
        refreshed_read_context = DashboardContext(
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
            adaptation_data=adaptation_data,
            workforce_data=workforce_data,
            economic_impact_data=economic_impact_data,
            commercialization_data=commercialization_data,
            current_context=current_context,
        )
        context_read_pair = build_context_read_pair(refreshed_read_context, context_report=shared_report)
        platform_reads = context_read_pair["reads"]
        regime_metrics = dict(regime_metrics or {})
        regime_metrics["Macro Interpretation"] = platform_reads["macro"]
        shared_report.update({
            "context_read_pair_version": context_read_pair.get("pair_version", ""),
            "read_architecture_version": context_read_pair.get("read_architecture_version", ""),
            "snapshot_id": context_read_pair.get("snapshot_id", shared_report.get("snapshot_id", "")),
        })
        st.session_state.current_context_load_report = shared_report
        st.session_state.sector_weekly_context = sector_weekly_context
        st.session_state.platform_reads = platform_reads
        st.session_state.regime_metrics = regime_metrics

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

render_masthead(
    "AI Macro",
    "An economic research platform focused on the evolution of the AI economy.",
    version=APP_VERSION,
    status=market_snapshot_label(st.session_state.get("market_snapshot_frame")),
)
render_platform_purpose(METRIC_DEFINITIONS["Purpose Statement"])

if st.session_state.tier_test_module_open:
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
        adaptation_data=adaptation_data,
        workforce_data=workforce_data,
        economic_impact_data=economic_impact_data,
        commercialization_data=commercialization_data,
        market_universe_summary=market_universe_summary,
        sector_weekly_context=sector_weekly_context,
        dashboard_data=dashboard_data,
        platform_reads=platform_reads,
    )
    render_research_dashboard(build_tabs(), dashboard_context)
