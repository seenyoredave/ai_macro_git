"""Detailed provider/load report renderer for the developer Diagnostics workspace."""

from __future__ import annotations

import streamlit as st

from developer.reports import format_seconds


def _render_source(label: str, block: dict | None) -> None:
    block = dict(block or {})
    missing = block.get("missing_tickers") or block.get("missing_series") or []
    stale = block.get("recent_missing_tickers") or []
    fallback_symbols = block.get("archive_fallback_symbols") or []
    st.markdown(f"**{label}**")
    st.write(f"Mode: `{block.get('source_mode', 'unknown')}`")
    st.write(f"Elapsed: `{format_seconds(block.get('elapsed_sec'))}`")
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
                summary = ", ".join(f"{column} ({count})" for column, count in sorted(columns.items()))
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
        failed = block.get("provider_failed_tickers") or []
        if failed:
            st.caption(f"Provider misses after retries ({len(failed)}): {', '.join(failed[:30])}")
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
        st.write(f"Live refresh: `{len(succeeded)}` succeeded · `{len(failed)}` failed · `{len(rejected)}` kept retained values")
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


def render_developer_load_report(report: dict | None, *, snapshot_write_report: dict | None = None, policy: dict | None = None) -> None:
    report = dict(report or {})
    if not report:
        st.caption("No load report is available yet.")
        return
    policy = dict(policy or report.get("load_policy") or {})
    if policy:
        sources = policy.get("refresh_sources") or []
        if sources:
            st.caption("Live refresh requested: " + ", ".join(str(source).replace("_", " ").title() for source in sources))
        else:
            st.caption("Load mode: retained data")
    st.caption(f"Total load: {format_seconds(report.get('total_elapsed_sec'))}")
    _render_source("YFinance", report.get("yfinance"))
    benchmark = dict(report.get("benchmark") or {})
    if benchmark:
        st.markdown("**QQQ reference**")
        st.write(f"Mode: `{benchmark.get('source_mode', 'unknown')}`")
        st.write(f"Returned: `{benchmark.get('returned_tickers', 0)}` members")
        if benchmark.get("latest_data_date"):
            st.write(f"Data through: `{benchmark.get('latest_data_date')}`")
        aliases = benchmark.get("member_aliases") or {}
        if aliases:
            st.caption("Retained-universe class mapping: " + ", ".join(f"{target} from {source}" for target, source in sorted(aliases.items())))
        if benchmark.get("live_error"):
            st.error(f"Benchmark refresh failed: {benchmark.get('live_error')}")
    st.markdown("---")
    _render_source("EDGAR", report.get("edgar"))
    st.markdown("---")
    _render_source("FRED", report.get("fred"))
    st.markdown("---")
    _render_source("NY Fed", report.get("debt_markets"))
    write_report = dict(snapshot_write_report or {})
    if write_report:
        st.markdown("---")
        written = write_report.get("written") or []
        retained = write_report.get("retained_by_loader") or []
        saved = list(dict.fromkeys([*written, *retained]))
        st.markdown("**Retained data writes**")
        st.write(f"Status: `{write_report.get('status', 'unknown')}`")
        st.write(f"Saved: `{', '.join(saved) if saved else 'none'}`")
        finance = dict(write_report.get("finance_derivatives") or {})
        if finance:
            st.markdown("**Finance derivatives**")
            st.write(f"SEC fundamentals: `{int(finance.get('fundamental_companies') or 0)}/10` companies")
            st.write(f"Definition-matched debt: `{int(finance.get('debt_companies') or 0)}/{int(finance.get('debt_target_companies') or 0)}` companies")
            for key, label in (("debt_updated_tickers", "Debt updated automatically"), ("debt_reviewed_tickers", "Debt filing-reviewed fallback")):
                tickers = finance.get(key) or []
                if tickers:
                    st.caption(f"{label} ({len(tickers)}): {', '.join(tickers)}")
            unresolved = finance.get("debt_unresolved_tickers") or []
            if unresolved:
                st.warning(f"Debt unresolved ({len(unresolved)}): {', '.join(unresolved)}")
        if write_report.get("reason"):
            st.caption(f"Reason: {write_report.get('reason')}")
        for label, message in (write_report.get("errors") or {}).items():
            st.error(f"{label}: {message}")
