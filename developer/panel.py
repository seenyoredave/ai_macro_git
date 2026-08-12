"""Four-workspace Developer Tools panel for v7."""

from __future__ import annotations

import json

import streamlit as st

from analytics.dashboard_context import DashboardContext
from analytics.read_evidence import EVIDENCE_ARCHITECTURE_VERSION, build_evidence_packets, evidence_snapshot_id, model_evidence_packets
from analytics.read_prompts import DOMAIN_PROMPT_VERSION, MACRO_PROMPT_VERSION
from analytics.read_service import READ_SERVICE_COMPATIBLE_VERSIONS, generate_validated_read_artifact, reapply_last_read, regenerate_macro_read, resume_saved_read_attempt
from analytics.read_store import latest_recoverable_attempt, load_read_artifact
from automation.config import AUTOMATION_START_LOCAL, AUTOMATION_TIMEZONE
from automation.status import load_automation_status
from config.openai_config import load_openai_config
from developer.load_report import render_developer_load_report
from developer.reports import current_context_status, format_seconds
from developer.state import (
    DOMAIN_REFRESH_LABELS,
    SOURCE_REFRESH_LABELS,
    request_all_domain_refreshes,
    request_all_source_refreshes,
    request_domain_refresh,
    request_source_refresh,
)

WORKSPACES = ("Operations", "Current Context", "AI", "Diagnostics")
CANVAS_VIEWS = ("Dashboard", "Basket / Tier diagnostics")


def _header(app_version: str) -> None:
    st.markdown(
        f"""
        <div class="rm-developer-tools-header">
            <span class="rm-developer-tools-title">Developer Tools</span>
            <span class="rm-developer-tools-version">ver. {app_version.removeprefix('v')}</span>
        </div>
        <div class="rm-developer-tools-divider"></div>
        """,
        unsafe_allow_html=True,
    )


def _last_operation() -> None:
    operation = dict(st.session_state.get("developer_last_operation") or {})
    if not operation:
        return
    label = str(operation.get("label") or "Operation")
    status = str(operation.get("status") or "unknown").replace("_", " ")
    st.caption(f"Last operation: {label} · {status}")
    errors = operation.get("errors") or []
    if errors:
        with st.expander("Operation warnings", expanded=False):
            for message in errors:
                st.write(str(message))


def _operations_workspace() -> None:
    st.markdown("**Application**")
    if st.button("Rebuild from retained data", use_container_width=True, key="dev-rebuild-retained"):
        st.session_state.force_rebuild = True
        st.session_state.developer_last_operation = {"kind": "rebuild", "label": "Retained rebuild", "status": "requested"}
        st.rerun()
    if st.button("Clear application cache", use_container_width=True, key="dev-clear-cache"):
        st.cache_data.clear()
        st.session_state.force_rebuild = True
        st.session_state.developer_last_operation = {"kind": "cache", "label": "Application cache", "status": "cleared"}
        st.rerun()
    archive_label = "Resume archive" if st.session_state.archive_suspended else "Suspend archive"
    if st.button(archive_label, use_container_width=True, key="dev-toggle-archive"):
        st.session_state.archive_suspended = not st.session_state.archive_suspended
        st.session_state.developer_last_operation = {"kind": "archive", "label": "Archive", "status": "resumed" if not st.session_state.archive_suspended else "suspended"}
        st.rerun()

    st.markdown("---")
    st.markdown("**Source refresh**")
    source = st.selectbox("Source", tuple(SOURCE_REFRESH_LABELS), format_func=SOURCE_REFRESH_LABELS.get, label_visibility="collapsed", key="dev-source-select")
    if st.button("Refresh source", use_container_width=True, key="dev-refresh-source"):
        request_source_refresh(st.session_state, source)
        st.rerun()
    if st.button("Refresh all sources", use_container_width=True, key="dev-refresh-all-sources"):
        request_all_source_refreshes(st.session_state)
        st.rerun()

    st.markdown("---")
    st.markdown("**Domain refresh**")
    domain = st.selectbox("Domain", tuple(DOMAIN_REFRESH_LABELS), format_func=DOMAIN_REFRESH_LABELS.get, label_visibility="collapsed", key="dev-domain-select")
    if st.button("Refresh domain", use_container_width=True, key="dev-refresh-domain"):
        request_domain_refresh(st.session_state, domain)
        st.rerun()
    if st.button("Refresh all domains", use_container_width=True, key="dev-refresh-all-domains"):
        request_all_domain_refreshes(st.session_state)
        st.rerun()
    st.caption("Evidence updates with the source domains above.")
    last = dict(st.session_state.get("last_domain_refresh") or {})
    if last:
        st.caption(f"Last domain refresh: {last.get('label')} · {last.get('source_mode')}")

    st.markdown("---")
    st.markdown("**Automation**")
    automation = load_automation_status()
    st.caption(f"Scheduled publication worker: {AUTOMATION_START_LOCAL} · {AUTOMATION_TIMEZONE}")
    if automation:
        result = str(automation.get("result") or "unknown").replace("_", " ")
        finished = str(automation.get("finished_at_utc") or automation.get("started_at_utc") or "")
        st.write(f"Last run: `{result}`")
        if finished:
            st.caption(f"Completed: {finished}")
        paid = dict(automation.get("paid_calls") or {})
        if paid:
            st.caption(
                f"Paid calls: {int(paid.get('this_run', 0) or 0)} this run · "
                f"{int(paid.get('today_after_run', paid.get('today_before_run', 0)) or 0)}/"
                f"{int(paid.get('daily_ceiling', 0) or 0)} today"
            )
        warnings = [str(item) for item in (automation.get("warnings") or []) if item]
        if warnings:
            st.caption(f"Refresh warnings: {len(warnings)} · valid retained fallbacks remained available.")
        if automation.get("publish_ready"):
            st.caption("Publication gate: validated and committed by the automation workflow.")
        elif automation.get("errors"):
            st.caption("Publication gate: blocked; prior published state retained.")
    else:
        st.caption("No committed automation run has been recorded yet.")
    _last_operation()


def _current_context_workspace() -> None:
    report = dict(st.session_state.get("current_context_load_report") or {})
    status = current_context_status(report)
    refresh_status = str(report.get("refresh_status") or "")
    if status.engine_mismatch:
        st.warning("Retained Current Context predates the installed discovery engine.")
    elif refresh_status == "failed_retained_fallback":
        st.error("Latest Current Context refresh failed before publication; prior retained context remains active.")
        if report.get("error"):
            st.caption(f"Refresh error: `{report.get('error')}`")
    elif refresh_status == "coverage_floor_not_met_retained_fallback":
        st.warning("Latest Current Context refresh did not reach the six-domain coverage floor; prior retained context remains active.")
    elif status.refresh_required:
        st.warning("Current Context requires another refresh before the retained snapshot is considered current.")
    else:
        st.caption(f"{status.source_mode.upper()} · engine {status.engine_version} · as of {status.as_of or 'unknown'}")
    if status.snapshot_id:
        st.caption(f"Snapshot `{status.snapshot_id}`")

    if st.button("Refresh Current Context", use_container_width=True, key="dev-refresh-current-context"):
        request_domain_refresh(st.session_state, "current_context")
        st.rerun()

    st.markdown("**Pipeline**")
    st.write(f"Discovered `{status.discovered:,}`")
    if status.metadata_qualified:
        st.write(f"Metadata qualified `{status.metadata_qualified:,}`")
    st.write(f"Grounding attempted `{status.attempted:,}`")
    st.write(f"Grounded `{status.grounded:,}`")
    st.write(f"Qualified `{status.qualified:,}`")
    st.write(f"Newly selected this refresh `{status.selected:,}`")
    if status.continuity_attempted:
        st.write(
            f"Retained continuity revalidated `{status.continuity_recovered:,}/{status.continuity_attempted:,}`"
            + (f" · restored `{status.continuity_selected:,}`" if status.continuity_selected else "")
        )
    st.write(f"Eligible retained developments rendered now `{status.rendered:,}`")

    st.markdown("**Coverage**")
    coverage_state = "met" if status.coverage_target_met else "not met"
    st.write(
        f"Domain coverage `{status.coverage_selected_domains}/{status.coverage_target}` · "
        f"floor {coverage_state} · tier `{status.coverage_tier_reached}` {status.coverage_tier_label}"
    )
    st.caption(
        f"Preferred window: {status.preferred_window_days} days · hard window: {status.hard_window_days} days · "
        f"expanded qualification: {'yes' if status.expanded_qualification else 'no'}"
    )
    if status.selected_domains_by_tier:
        tier_text = " · ".join(f"{key}: {count} domains" for key, count in status.selected_domains_by_tier if count)
        if tier_text:
            st.caption(f"Selected domain quality: {tier_text}")

    if status.domains:
        with st.expander("Domain pipeline", expanded=False):
            for row in status.domains:
                label = row.domain.replace("_", " ").title()
                st.markdown(f"**{label}**")
                st.caption(
                    f"{row.discovered:,} discovered → {row.metadata_qualified:,} metadata → "
                    f"{row.attempted:,} attempted → {row.grounded:,} grounded → "
                    f"{row.selected:,} newly selected; {row.rendered:,} retained eligible now"
                )
    if status.grounding_rejections:
        with st.expander("Rejection analysis", expanded=False):
            for row in status.grounding_rejections[:12]:
                st.write(f"`{int(row.get('count', 0) or 0)}` · {row.get('reason', '')}")
    if status.provider_errors:
        with st.expander(f"Provider failures ({len(status.provider_errors)})", expanded=False):
            for row in status.provider_errors[:20]:
                st.write(f"{row.get('domain', '')}:{row.get('provider', '')}: {row.get('error', '')}")
    with st.expander("Snapshot / provenance", expanded=False):
        st.write(f"Installed engine: `{status.engine_version}`")
        st.write(f"Retained discovery engine: `{status.retained_version}`")
        st.write(f"Reader snapshot: `{report.get('reader_snapshot_version', 'pending')}`")
        st.write(f"Evidence architecture: `{report.get('evidence_architecture_version', EVIDENCE_ARCHITECTURE_VERSION)}`")
        if report.get("evidence_snapshot_id"):
            st.write(f"Evidence snapshot: `{report.get('evidence_snapshot_id')}`")


def _generation_totals(generation: dict) -> tuple[float, int, int, int]:
    elapsed = 0.0
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    for block in generation.values():
        if not isinstance(block, dict):
            continue
        elapsed += float(block.get("elapsed_sec", 0) or 0)
        input_tokens += int(block.get("input_tokens", 0) or 0)
        output_tokens += int(block.get("output_tokens", 0) or 0)
        total_tokens += int(block.get("total_tokens", 0) or 0)
    return elapsed, input_tokens, output_tokens, total_tokens


def _validation_claim_counts(validation: dict) -> tuple[int, int]:
    checked = int(validation.get("checked_claims", 0) or 0)
    grounded = int(validation.get("grounded_claims", 0) or 0)
    if checked:
        return checked, grounded
    for key in ("domain", "macro"):
        block = validation.get(key)
        if isinstance(block, dict):
            checked += int(block.get("checked_claims", 0) or 0)
            grounded += int(block.get("grounded_claims", 0) or 0)
    return checked, grounded


def _validation_failures(validation: dict) -> list[dict]:
    failures = [item for item in (validation.get("failures") or []) if isinstance(item, dict)]
    for key in ("domain", "macro"):
        block = validation.get(key)
        if isinstance(block, dict):
            failures.extend(item for item in (block.get("failures") or []) if isinstance(item, dict))
    return failures


def _render_ai_result(result: dict) -> None:
    if not result:
        return
    status = str(result.get("status") or "unknown")
    if status == "validated":
        st.success("Validated commentary artifact")
    elif status == "reapplied":
        st.success("Last validated Read reapplied for 24 hours")
    elif status == "validation_failed":
        st.error(f"Validation failed at {result.get('stage', 'unknown')} stage")
    else:
        st.warning(status.replace("_", " ").title())
    if result.get("evidence_snapshot_id"):
        st.caption(f"Evidence snapshot `{result.get('evidence_snapshot_id')}`")
    if result.get("attempt_id"):
        st.caption(f"Saved attempt `{result.get('attempt_id')}`")
    publication = dict(result.get("publication") or {})
    if publication.get("expires_at"):
        st.caption(f"Published through: {publication.get('expires_at')}")
    generation = dict(result.get("generation") or {})
    elapsed, input_tokens, output_tokens, total_tokens = _generation_totals(generation)
    if generation:
        st.caption(f"{format_seconds(elapsed)} · {input_tokens:,} input · {output_tokens:,} output · {total_tokens:,} total tokens")
    validation = dict(result.get("validation") or {})
    if validation:
        checked, grounded = _validation_claim_counts(validation)
        if checked:
            st.caption(f"Claims grounded: {grounded}/{checked}")
        failures = _validation_failures(validation)
        if failures:
            with st.expander(f"Rejected claims ({len(failures)})", expanded=True):
                for failure in failures:
                    if not isinstance(failure, dict):
                        continue
                    st.markdown(f"**{failure.get('label', 'validation')}**")
                    sentence = str(failure.get("sentence") or "").strip()
                    if sentence:
                        st.write(sentence)
                    fact_ids = failure.get("fact_ids") or []
                    if fact_ids:
                        st.caption("Fact IDs: " + ", ".join(f"`{item}`" for item in fact_ids))
                    st.caption(str(failure.get("message") or failure.get("reason") or "Validation failed."))
        with st.expander("Validation report", expanded=False):
            st.json(validation)
    generated_output = result.get("generated_output")
    if isinstance(generated_output, dict) and generated_output:
        with st.expander("Generated output", expanded=False):
            st.json(generated_output)
    with st.expander("Generation metadata", expanded=False):
        st.json(generation)


def _ai_workspace(context: DashboardContext | None) -> None:
    config = load_openai_config()
    if config.configured:
        st.success("OpenAI API configured")
    else:
        st.warning("OPENAI_API_KEY is not configured.")
    st.write(f"Model: `{config.model}`")
    st.write(f"Reasoning: `{config.reasoning_effort}`")
    st.caption(f"Prompts: {DOMAIN_PROMPT_VERSION} · {MACRO_PROMPT_VERSION}")
    st.caption(f"Evidence schema: {EVIDENCE_ARCHITECTURE_VERSION}")
    st.caption("Paid attempts persist in `openai_artifacts/attempts/`; only validated output is promoted to `openai_artifacts/current.json`.")

    packets = build_evidence_packets(context) if context is not None else {}
    current_snapshot = ""
    recoverable = {}
    if packets:
        fact_count = sum(len(packet.facts) for packet in packets.values())
        current_snapshot = evidence_snapshot_id(packets)
        st.caption(f"Current evidence: `{current_snapshot}` · {fact_count:,} facts")
        model_packets = model_evidence_packets(packets)
        model_chars = len(json.dumps(model_packets, ensure_ascii=False, separators=(",", ":")))
        st.caption(f"Model evidence projection: {model_chars:,} compact JSON characters · actual billed tokens reported after generation")
        recoverable = latest_recoverable_attempt(evidence_snapshot_id=current_snapshot, domain_prompt_version=DOMAIN_PROMPT_VERSION)
        if recoverable:
            generated = dict(recoverable.get("generated_output") or {})
            resume_cost = "no new API call" if generated.get("macro") else "Macro call only"
            st.info(
                f"Saved failed attempt available: `{recoverable.get('attempt_id', '')}` · resume uses {resume_cost}."
            )
        with st.expander("Model evidence packet", expanded=False):
            st.json(model_packets)

    disabled = context is None or not config.configured
    if recoverable and st.button("Revalidate / resume saved attempt", use_container_width=True, key="dev-resume-commentary", disabled=disabled):
        try:
            with st.spinner("Revalidating saved output and resuming from the next unpaid stage…"):
                result = resume_saved_read_attempt(
                    context,
                    config,
                    str(recoverable.get("attempt_id") or ""),
                    persist=True,
                )
            st.session_state.developer_last_ai_result = result
            if result.get("status") == "validated":
                st.session_state.force_rebuild = True
                st.session_state.developer_last_operation = {"kind": "ai", "label": "Commentary resume", "status": "validated"}
                st.rerun()
        except Exception as exc:
            st.session_state.developer_last_ai_result = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}

    current_artifact = load_read_artifact()
    reapply_ready = bool(
        current_artifact
        and bool((current_artifact.get("validation") or {}).get("passed"))
        and str(current_artifact.get("service_version") or "") in READ_SERVICE_COMPATIBLE_VERSIONS
        and isinstance(current_artifact.get("reads"), dict)
    )
    if st.button("Apply last Read", use_container_width=True, key="dev-apply-last-read", disabled=not reapply_ready):
        try:
            renewed = reapply_last_read(persist=True, source="manual_reapply")
            st.session_state.developer_last_ai_result = {
                "status": "reapplied",
                "attempt_id": renewed.get("attempt_id", ""),
                "evidence_snapshot_id": renewed.get("evidence_snapshot_id", ""),
                "publication": renewed.get("publication", {}),
            }
            st.session_state.force_rebuild = True
            st.session_state.developer_last_operation = {"kind": "ai", "label": "Apply last Read", "status": "reapplied"}
            st.rerun()
        except Exception as exc:
            st.session_state.developer_last_ai_result = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    st.caption("No OpenAI call. Republishes the most recent validated commentary for another 24 hours while preserving its original evidence snapshot and generation time.")

    macro_only_ready = bool(
        current_artifact
        and str(current_artifact.get("evidence_snapshot_id") or "") == current_snapshot
        and bool(((current_artifact.get("validation") or {}).get("domain") or {}).get("passed"))
        and isinstance(current_artifact.get("reads"), dict)
    )
    if st.button("Regenerate AI Macro Read only", use_container_width=True, key="dev-regenerate-macro", disabled=disabled or not macro_only_ready):
        try:
            with st.spinner("Synthesizing and validating AI Macro Read…"):
                result = regenerate_macro_read(context, config, persist=True)
            st.session_state.developer_last_ai_result = result
            if result.get("status") == "validated":
                st.session_state.force_rebuild = True
                st.session_state.developer_last_operation = {"kind": "ai", "label": "AI Macro Read", "status": "validated"}
                st.rerun()
        except Exception as exc:
            st.session_state.developer_last_ai_result = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    st.caption("Macro-only regeneration reuses the current validated domain Reads and spends one Macro API call.")

    if st.button("Generate new commentary", use_container_width=True, key="dev-generate-commentary", disabled=disabled):
        try:
            with st.spinner("Generating and validating commentary…"):
                result = generate_validated_read_artifact(context, config, persist=True)
            st.session_state.developer_last_ai_result = result
            if result.get("status") == "validated":
                st.session_state.force_rebuild = True
                st.session_state.developer_last_operation = {"kind": "ai", "label": "Commentary", "status": "validated"}
                st.rerun()
        except Exception as exc:
            st.session_state.developer_last_ai_result = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}

    result = dict(st.session_state.get("developer_last_ai_result") or {})
    if result.get("status") == "error":
        st.error(result.get("error", "OpenAI request failed."))
    else:
        _render_ai_result(result)
        if result.get("status") == "validated" and isinstance(result.get("reads"), dict):
            with st.expander("Generated Reads", expanded=False):
                st.json(result.get("reads"))

    commentary = dict(st.session_state.get("commentary_status") or {})
    if commentary:
        st.markdown("**Published artifact**")
        st.write(f"Status: `{commentary.get('status', 'unknown')}`")
        if commentary.get("model"):
            st.write(f"Model: `{commentary.get('model')}`")
        if commentary.get("generated_at"):
            st.caption(f"Generated: {commentary.get('generated_at')}")
        publication = dict(commentary.get("publication") or {})
        if publication.get("published_at"):
            st.caption(f"Applied: {publication.get('published_at')}")
        if publication.get("expires_at"):
            st.caption(f"Published through: {publication.get('expires_at')}")
        if commentary.get("evidence_snapshot_id"):
            st.caption(f"Current evidence: `{commentary.get('evidence_snapshot_id')}`")
        artifact_snapshot = commentary.get("artifact_evidence_snapshot_id")
        if commentary.get("publication_active") and artifact_snapshot and not commentary.get("evidence_current"):
            st.warning(
                f"The published Read targets `{artifact_snapshot}` while current evidence is `{commentary.get('evidence_snapshot_id')}`. "
                "Its 24-hour publication lease remains active; generate new commentary if the evidence change is material."
            )
        elif commentary.get("status") == "expired":
            st.warning("The last validated Read is retained but its 24-hour publication lease has expired. Apply last Read or generate new commentary.")


def _diagnostics_workspace() -> None:
    view = st.selectbox("Canvas view", CANVAS_VIEWS, index=CANVAS_VIEWS.index(st.session_state.get("developer_canvas_view", "Dashboard")) if st.session_state.get("developer_canvas_view", "Dashboard") in CANVAS_VIEWS else 0, key="dev-canvas-select")
    if st.button("Open diagnostic view", use_container_width=True, key="dev-open-canvas"):
        st.session_state.developer_canvas_view = view
        st.rerun()
    if st.session_state.get("developer_canvas_view") != "Dashboard":
        if st.button("Return to dashboard", use_container_width=True, key="dev-return-dashboard"):
            st.session_state.developer_canvas_view = "Dashboard"
            st.rerun()
    with st.expander("Latest load report", expanded=False):
        render_developer_load_report(
            st.session_state.get("market_universe_load_report"),
            snapshot_write_report=st.session_state.get("snapshot_write_report"),
            policy=st.session_state.get("current_load_policy"),
        )
    current = dict(st.session_state.get("current_context_load_report") or {})
    errors = current.get("fetch_errors") or []
    if errors:
        st.warning(f"Current Context provider errors: {len(errors)}")


def render_developer_tools(app_version: str, *, commentary_context: DashboardContext | None = None) -> None:
    """Render the owner-only sidebar. Caller is responsible for developer-mode gating."""
    with st.sidebar:
        _header(app_version)
        workspace = st.radio("Workspace", WORKSPACES, key="developer_workspace", horizontal=False)
        st.markdown("---")
        if workspace == "Operations":
            _operations_workspace()
        elif workspace == "Current Context":
            _current_context_workspace()
        elif workspace == "AI":
            _ai_workspace(commentary_context)
        else:
            _diagnostics_workspace()
