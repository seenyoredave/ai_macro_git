"""Four-workspace Developer Tools panel for AI Macro v10."""

from __future__ import annotations

from dataclasses import replace

import streamlit as st

from analytics.dashboard_context import DashboardContext
from analytics.domain_state import with_domain_states
from analytics.read_briefing import BRIEFING_VERSION
from analytics.read_evidence import EVIDENCE_ARCHITECTURE_VERSION
from analytics.read_service import (
    PUBLISHABLE_STATUSES,
    READ_SERVICE_COMPATIBLE_VERSIONS,
    generate_validated_read_artifact,
    reapply_last_read,
)
from analytics.read_store import load_read_artifact
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
    if status.approved_evidence_candidates:
        st.write(f"Approved evidence candidates `{status.approved_evidence_candidates:,}`")
    if status.approved_source_sweep_candidates:
        st.caption(
            f"Publisher-first sweep candidates `{status.approved_source_sweep_candidates:,}`"
            + (f" · grounded `{status.approved_source_sweep_grounded:,}`" if status.approved_source_sweep_grounded else "")
        )
    if status.discovery_leads:
        st.caption(
            f"Unapproved discovery leads observed `{status.discovery_leads:,}` · audit only; do not consume routine grounding attempts"
        )
    if status.preground_unique_candidates or status.preground_duplicates_clustered or status.preground_retained_duplicates_skipped:
        st.caption(
            f"Distinct approved events queued for grounding `{status.preground_unique_candidates:,}`"
            + (f" · duplicate nominations clustered `{status.preground_duplicates_clustered:,}`" if status.preground_duplicates_clustered else "")
            + (f" · already-current events skipped `{status.preground_retained_duplicates_skipped:,}`" if status.preground_retained_duplicates_skipped else "")
        )
    st.write(f"Grounding attempted `{status.attempted:,}`")
    st.write(f"Grounded `{status.grounded:,}`")
    if status.trusted_headline_grounded:
        st.caption(
            f"Approved-publisher headline evidence `{status.trusted_headline_grounded:,}` · "
            "clean approved-source headlines may establish the event without body-text restatement"
        )
    if status.unique_grounded_after_dedup and status.unique_grounded_after_dedup != status.grounded:
        st.caption(
            f"Grounded events after exact ownership deduplication `{status.unique_grounded_after_dedup:,}`"
        )
    st.write(f"Qualified `{status.qualified:,}`")
    st.write(f"Newly selected this refresh `{status.selected:,}`")
    if status.continuity_attempted:
        st.write(
            f"Retained continuity revalidated `{status.continuity_recovered:,}/{status.continuity_attempted:,}`"
            + (f" · restored `{status.continuity_selected:,}`" if status.continuity_selected else "")
        )
    st.write(f"Eligible retained developments rendered now `{status.rendered:,}`")

    st.markdown("**News selection**")
    st.write(
        f"Domains with eligible retained developments `{status.coverage_selected_domains}` · "
        f"highest selected tier `{status.coverage_tier_reached}` {status.coverage_tier_label}"
    )
    st.caption(
        f"Selection target: {status.selection_target_min}-{status.selection_target_max} fresh developments when available · "
        f"preferred window: {status.preferred_window_days} days · hard window: {status.hard_window_days} days · "
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
                    f"{row.discovered:,} discovered → {row.approved_evidence_candidates:,} approved candidates → "
                    f"{row.attempted:,} attempted → {row.grounded:,} grounded → "
                    f"{row.selected:,} newly selected; {row.rendered:,} retained eligible now"
                )
                if row.approved_source_sweep_candidates:
                    st.caption(f"Publisher-first sweep candidates: {row.approved_source_sweep_candidates:,}")
                if row.preground_unique_candidates or row.preground_duplicates_clustered or row.preground_retained_duplicates_skipped:
                    st.caption(
                        f"Distinct approved events queued: {row.preground_unique_candidates:,}"
                        + (f" · duplicate nominations clustered: {row.preground_duplicates_clustered:,}" if row.preground_duplicates_clustered else "")
                        + (f" · already-current events skipped: {row.preground_retained_duplicates_skipped:,}" if row.preground_retained_duplicates_skipped else "")
                    )
                if row.discovery_leads:
                    st.caption(f"Unapproved leads observed (audit only): {row.discovery_leads:,}")
                if row.trusted_headline_grounded:
                    st.caption(f"Approved-publisher headline evidence: {row.trusted_headline_grounded:,}")
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
    failures = [
        item
        for key in ("hard_failures", "diagnostics", "failures")
        for item in (validation.get(key) or [])
        if isinstance(item, dict)
    ]
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
    elif status == "published_with_warnings":
        st.warning("New commentary published with validation diagnostics")
    elif status == "retained_prior":
        st.success("Evidence evaluated; prior commentary retained")
    elif status in {"rejected_hard_validation", "rejected_unparseable"}:
        st.error("Completed response rejected; prior commentary retained")
    elif status == "reapplied":
        st.success("Last published Read reapplied for 24 hours")
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
    raw_responses = result.get("raw_responses")
    if isinstance(raw_responses, dict) and raw_responses:
        with st.expander("Raw OpenAI responses", expanded=False):
            st.json(raw_responses)
    with st.expander("Generation metadata", expanded=False):
        st.json(generation)


def _ai_workspace(context: DashboardContext | None) -> None:
    configured = load_openai_config()
    session_key = ""
    credential_source = "environment / Streamlit secrets" if configured.configured else "not configured"

    st.markdown("**Runtime**")
    if not configured.configured:
        session_key = str(
            st.text_input(
                "OpenAI API key",
                type="password",
                key="developer_openai_api_key",
                help=(
                    "Used only for this local Streamlit session. The key is not written to the repository, "
                    "retained research state, or publication artifacts."
                ),
                placeholder="sk-…",
            )
            or ""
        ).strip()
        if session_key:
            configured = replace(configured, api_key=session_key)
            credential_source = "local session"

    config = configured
    current_artifact = load_read_artifact()
    stored_packets = dict(current_artifact.get("evidence_packets") or {}) if current_artifact else {}
    current_snapshot = str(current_artifact.get("evidence_snapshot_id") or "") if current_artifact else ""
    fact_count = sum(len((packet or {}).get("facts", []) or []) for packet in stored_packets.values())

    st.write(f"API: `{'configured' if config.configured else 'not configured'}`")
    st.caption(f"Credential source: {credential_source}")
    if not config.configured:
        st.caption("Enter an OpenAI API key above to enable local preview and publication controls.")
    st.write(f"Model: `{config.model}`")
    st.write(f"Reasoning: `{config.reasoning_effort}`")
    st.write(f"Editorial briefing: `{BRIEFING_VERSION}`")
    st.write(f"Published evidence: `{current_snapshot or 'unavailable'}` · `{fact_count:,}` facts")
    st.write(f"Last published Read: `{str(current_artifact.get('generated_at') or 'unavailable')}`")
    st.write(f"Recent developments considered: `{len(current_artifact.get('editorial_context_event_ids', []) or [])}`")

    disabled = context is None or not config.configured
    publishable = bool(
        current_artifact
        and str(current_artifact.get("status") or "") in PUBLISHABLE_STATUSES
        and str(current_artifact.get("service_version") or "") in READ_SERVICE_COMPATIBLE_VERSIONS
        and isinstance(current_artifact.get("reads"), dict)
    )
    st.markdown("**Actions**")
    if st.button("Preview one editorial synthesis", use_container_width=True, key="dev-preview-commentary-v12", disabled=disabled):
        try:
            with st.spinner("Generating one non-publishing editorial response…"):
                prepared_context = with_domain_states(context)
                result = generate_validated_read_artifact(
                    prepared_context,
                    config,
                    persist=False,
                    force_preview=True,
                )
            result = {**dict(result), "preview_only": True}
            previews = list(st.session_state.get("developer_editorial_previews") or [])
            previews.append(result)
            st.session_state.developer_editorial_previews = previews[-5:]
            st.session_state.developer_last_ai_result = result
            st.session_state.developer_last_operation = {
                "kind": "ai",
                "label": "Editorial preview",
                "status": str(result.get("status") or "unknown"),
            }
        except Exception as exc:
            st.session_state.developer_last_ai_result = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}

    if st.button("Generate and publish editorial synthesis", use_container_width=True, key="dev-generate-commentary-v12", disabled=disabled):
        try:
            with st.spinner("Evaluating evidence and generating one editorial response…"):
                prepared_context = with_domain_states(context)
                result = generate_validated_read_artifact(prepared_context, config, persist=True)
            st.session_state.developer_last_ai_result = result
            if result.get("status") in (PUBLISHABLE_STATUSES | {"retained_prior"}):
                st.session_state.force_rebuild = True
                st.session_state.developer_last_operation = {"kind": "ai", "label": "Editorial synthesis", "status": str(result.get("status"))}
                st.rerun()
        except Exception as exc:
            st.session_state.developer_last_ai_result = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}

    if st.button("Apply last Read", use_container_width=True, key="dev-apply-last-read-v10", disabled=not publishable):
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

    result = dict(st.session_state.get("developer_last_ai_result") or {})
    if result.get("status") == "error":
        st.error(result.get("error", "OpenAI request failed."))
    else:
        _render_ai_result(result)
        if result.get("status") in (PUBLISHABLE_STATUSES | {"retained_prior"}) and isinstance(result.get("reads"), dict):
            with st.expander("Reads", expanded=False):
                st.json(result.get("reads"))

    previews = list(st.session_state.get("developer_editorial_previews") or [])
    if previews:
        with st.expander(f"Editorial previews ({len(previews)})", expanded=False):
            for index, preview in enumerate(reversed(previews), start=1):
                st.markdown(f"**Preview {len(previews) - index + 1} · {preview.get('status', 'unknown')}**")
                preview_reads = dict(preview.get("reads") or {})
                updated_domains = list(preview.get("editorial_update_domains") or [])
                candidates = list(preview.get("editorial_candidate_domains") or [])
                if candidates:
                    st.caption("Candidates: " + ", ".join(candidates))
                st.caption("Updated domains: " + (", ".join(updated_domains) if updated_domains else "none"))
                macro = dict(preview_reads.get("macro") or {})
                if macro:
                    st.write(str(macro.get("headline") or ""))
                    for paragraph in macro.get("analysis_paragraphs") or [macro.get("analysis")]:
                        if paragraph:
                            st.write(str(paragraph))
                validation = dict(preview.get("validation") or {})
                if validation.get("diagnostics"):
                    st.caption(f"Style diagnostics: {len(validation.get('diagnostics') or [])}")

    commentary = dict(st.session_state.get("commentary_status") or {})
    if commentary:
        st.markdown("**Published**")
        st.write(f"Status: `{commentary.get('status', 'unknown')}`")
        st.write(f"Generated: `{commentary.get('generated_at', '') or 'unknown'}`")
        publication = dict(commentary.get("publication") or {})
        st.write(f"Expires: `{publication.get('expires_at', '') or 'unknown'}`")


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
