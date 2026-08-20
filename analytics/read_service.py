"""One-call incremental commentary orchestration and publication control."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from analytics.dashboard_context import DashboardContext
from analytics.read_capsules import (
    CAPSULE_ARCHITECTURE_VERSION,
    build_evaluated_state,
    build_signal_capsules,
    materially_changed_domains,
    prior_publication_payload,
    required_update_domains,
)
from analytics.read_context import attach_current_context
from analytics.read_evidence import (
    DOMAIN_LABELS,
    DOMAIN_ORDER,
    EvidencePacket,
    build_evidence_packets,
    evidence_fact_index,
    evidence_snapshot_id,
)
from analytics.read_generation import (
    generate_editorial_synthesis,
    prompt_versions,
)
from analytics.read_materiality import compare_evidence_materiality
from analytics.read_models import GeneratedDomainRead, GeneratedEditorialSynthesis, GeneratedMacroRead
from analytics.read_store import (
    load_evaluated_state,
    load_read_artifact,
    new_attempt_id,
    persist_evaluated_state,
    persist_read_artifact,
    persist_read_attempt,
)
from analytics.read_validation import EDITORIAL_VALIDATOR_VERSION, validate_editorial_synthesis
from config.openai_config import OpenAIConfig

READ_SERVICE_VERSION = "5.0.0"
READ_SERVICE_COMPATIBLE_VERSIONS = {
    READ_SERVICE_VERSION,
    "4.5.0", "4.4.0", "4.3.0", "4.2.0", "4.1.0", "3.2.0", "3.0.0",
}
COMMENTARY_PUBLICATION_LEASE_HOURS = 24
UNAVAILABLE_HEADLINE = "Commentary temporarily unavailable."
UNAVAILABLE_ANALYSIS = "The analyst has wandered off. The data have not."
MAX_MACRO_REFERENCES = 6
PUBLISHABLE_STATUSES = {"validated", "published_with_warnings"}


def _packet_dicts(packets: dict[str, EvidencePacket]) -> dict[str, dict]:
    return {domain: packet.to_dict() for domain, packet in packets.items()}


def _change_key(change: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(change.get("kind") or ""),
        str(change.get("fact_id") or change.get("domain") or ""),
        str(change.get("field") or ""),
    )


def _editorial_materiality(
    evaluation_comparison: dict[str, Any],
    publication_comparison: dict[str, Any],
    *,
    required_domains: list[str],
) -> dict[str, Any]:
    """Combine new evaluation changes with publication-staleness repairs.

    The paid-call trigger stays anchored to the last completed evaluation.  A
    later call must still repair any published sentence made stale by an older
    rejected response, so changes to cited facts are also brought forward from
    the last-good publication baseline for required domains only.
    """
    merged = dict(evaluation_comparison)
    changes: list[dict[str, Any]] = []
    positions: dict[tuple[str, str, str], int] = {}
    for raw in evaluation_comparison.get("changes", []) or []:
        if not isinstance(raw, dict):
            continue
        item = {**raw, "comparison_basis": "last_completed_evaluation"}
        positions[_change_key(item)] = len(changes)
        changes.append(item)

    required = set(required_domains)
    for raw in publication_comparison.get("changes", []) or []:
        if not isinstance(raw, dict):
            continue
        domain = str(raw.get("domain") or str(raw.get("fact_id") or "").split(".", 1)[0])
        if domain not in required:
            continue
        item = {**raw, "comparison_basis": "last_good_publication"}
        key = _change_key(item)
        if key in positions:
            existing = changes[positions[key]]
            existing["also_changed_since_publication"] = True
            existing["publication_old_value"] = raw.get("old_value")
            existing["publication_new_value"] = raw.get("new_value")
            continue
        positions[key] = len(changes)
        changes.append(item)

    merged.update({
        "changes": changes,
        "change_count": len(changes),
        "material_change_count": sum(bool(item.get("material")) for item in changes),
        "immaterial_change_count": sum(not bool(item.get("material")) for item in changes),
        "publication_repair_domains": [domain for domain in DOMAIN_ORDER if domain in required],
    })
    return merged


def _claim_rows(read_model: Any) -> list[dict[str, Any]]:
    rows = [{"field": "headline", **read_model.headline.model_dump()}]
    rows.extend(
        {"field": f"analysis[{index}]", **item.model_dump()}
        for index, item in enumerate(read_model.analysis)
    )
    return rows


def _domain_public_read(
    read_model: GeneratedDomainRead,
    packet: dict[str, Any],
    *,
    snapshot_id: str = "",
    generated_at: str = "",
) -> dict[str, Any]:
    sentences = [item.text for item in read_model.analysis]
    return {
        "domain": read_model.domain,
        "label": DOMAIN_LABELS[read_model.domain],
        "headline": read_model.headline.text,
        "analysis": " ".join(sentences),
        "analysis_sentences": sentences,
        "references": [dict(item) for item in packet.get("references", []) or []],
        "claim_support": _claim_rows(read_model),
        "evidence_snapshot_id": str(snapshot_id or ""),
        "generated_at": str(generated_at or ""),
        "generator": "openai",
        "version": READ_SERVICE_VERSION,
    }


def _macro_public_read(
    read_model: GeneratedMacroRead,
    packets: dict[str, dict],
    *,
    snapshot_id: str = "",
    generated_at: str = "",
) -> dict[str, Any]:
    selected = list(read_model.selected_domains)
    references: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add_reference(reference: dict[str, Any]) -> None:
        key = (str(reference.get("source_label") or ""), str(reference.get("source_url") or ""))
        if not key[0] or key in seen or len(references) >= MAX_MACRO_REFERENCES:
            return
        seen.add(key)
        references.append(dict(reference))

    for domain in selected:
        for reference in packets.get(domain, {}).get("references", []) or []:
            if str(reference.get("source_label") or "").strip():
                add_reference(reference)
                break
    for domain in selected:
        for reference in packets.get(domain, {}).get("references", []) or []:
            add_reference(reference)
            if len(references) >= MAX_MACRO_REFERENCES:
                break
        if len(references) >= MAX_MACRO_REFERENCES:
            break

    fact_index = evidence_fact_index(packets)
    fact_ids: list[str] = []
    for sentence in [read_model.headline, *read_model.analysis]:
        for fact_id in sentence.fact_ids:
            if fact_id not in fact_ids:
                fact_ids.append(fact_id)
    evidence = [
        {
            "fact_id": fact_id,
            "label": str(fact_index.get(fact_id, {}).get("label") or fact_id),
            "value": str(fact_index.get(fact_id, {}).get("display") or "n/a"),
            "context": str(fact_index.get(fact_id, {}).get("context") or ""),
        }
        for fact_id in fact_ids[:3]
    ]
    sentences = [item.text for item in read_model.analysis]
    paragraphs = [
        " ".join(sentence.text for sentence in paragraph.sentences)
        for paragraph in read_model.paragraphs
    ]
    return {
        "domain": "macro",
        "label": DOMAIN_LABELS["macro"],
        "headline": read_model.headline.text,
        "analysis": " ".join(sentences),
        "analysis_sentences": sentences,
        "analysis_paragraphs": paragraphs,
        "selected_domains": selected,
        "references": references,
        "claim_support": _claim_rows(read_model),
        "evidence": evidence,
        "evidence_snapshot_id": str(snapshot_id or ""),
        "generated_at": str(generated_at or ""),
        "generator": "openai",
        "version": READ_SERVICE_VERSION,
    }


def _unavailable_read(domain: str, packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "domain": domain,
        "label": DOMAIN_LABELS.get(domain, domain.replace("_", " ").title()),
        "headline": UNAVAILABLE_HEADLINE,
        "analysis": UNAVAILABLE_ANALYSIS,
        "references": [],
        "claim_support": [],
        "generator": "unavailable",
        "version": READ_SERVICE_VERSION,
    }


def _utc_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def publication_lease_state(
    artifact: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    stored = dict(artifact or {})
    publication = dict(stored.get("publication") or {})
    published_at = _utc_datetime(
        publication.get("published_at") or stored.get("published_at") or stored.get("generated_at")
    )
    expires_at = published_at + timedelta(hours=COMMENTARY_PUBLICATION_LEASE_HOURS) if published_at else None
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "active": bool(published_at and expires_at and current < expires_at),
        "lease_hours": COMMENTARY_PUBLICATION_LEASE_HOURS,
        "published_at": published_at.isoformat() if published_at else "",
        "expires_at": expires_at.isoformat() if expires_at else "",
        "remaining_seconds": max(0, int((expires_at - current).total_seconds())) if expires_at else 0,
        "renewal_count": int(publication.get("renewal_count", 0) or 0),
        "source": str(publication.get("source") or ("legacy_generated_at" if published_at else "")),
        "current_evidence_snapshot_id": str(publication.get("current_evidence_snapshot_id") or ""),
        "materiality": dict(publication.get("materiality") or {}),
    }


def _artifact_is_validated(stored: dict[str, Any]) -> bool:
    return bool(
        stored
        and bool((stored.get("validation") or {}).get("passed"))
        and str(stored.get("service_version") or "") in READ_SERVICE_COMPATIBLE_VERSIONS
        and isinstance(stored.get("reads"), dict)
    )


def _artifact_is_publishable(stored: dict[str, Any]) -> bool:
    return bool(
        stored
        and str(stored.get("status") or "") in PUBLISHABLE_STATUSES
        and str(stored.get("service_version") or "") in READ_SERVICE_COMPATIBLE_VERSIONS
        and isinstance(stored.get("reads"), dict)
    )


def _with_publication_lease(
    artifact: dict[str, Any],
    *,
    source: str,
    now: datetime | None = None,
    current_evidence_snapshot_id: str = "",
    materiality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    previous = dict(artifact.get("publication") or {})
    output = dict(artifact)
    output["publication"] = {
        "lease_hours": COMMENTARY_PUBLICATION_LEASE_HOURS,
        "published_at": current.isoformat(),
        "expires_at": (current + timedelta(hours=COMMENTARY_PUBLICATION_LEASE_HOURS)).isoformat(),
        "renewal_count": int(previous.get("renewal_count", 0) or 0) + (0 if source == "generation" else 1),
        "source": source,
        "current_evidence_snapshot_id": str(
            current_evidence_snapshot_id or artifact.get("evidence_snapshot_id") or ""
        ),
        "materiality": dict(materiality or {}),
    }
    return output


def reapply_last_read(
    *,
    persist: bool = True,
    source: str = "manual_reapply",
    now: datetime | None = None,
    current_evidence_snapshot_id: str = "",
    materiality: dict[str, Any] | None = None,
    evidence_packets: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stored = load_read_artifact()
    if not stored:
        raise ValueError("No published commentary artifact is available to reapply.")
    if not _artifact_is_publishable(stored):
        raise ValueError("The most recent commentary artifact is not compatible with the current Reader schema.")
    renewed = _with_publication_lease(
        stored,
        source=source,
        now=now,
        current_evidence_snapshot_id=current_evidence_snapshot_id,
        materiality=materiality,
    )
    if evidence_packets is not None:
        current_snapshot = str(current_evidence_snapshot_id or "")
        generated_snapshot = str(stored.get("evidence_snapshot_id") or "")
        if not current_snapshot or current_snapshot != generated_snapshot:
            raise ValueError("Evidence packets may be backfilled only for the artifact's exact generated snapshot.")
        renewed["evidence_packets"] = dict(evidence_packets)
    if persist:
        persist_read_artifact(renewed)
    return renewed


def build_platform_reads(
    context: DashboardContext,
    *,
    artifact: dict | None = None,
) -> tuple[dict[str, dict], dict[str, Any]]:
    stored = dict(artifact if artifact is not None else load_read_artifact())
    evaluated = load_evaluated_state()
    artifact_validated = _artifact_is_validated(stored)
    artifact_publishable = _artifact_is_publishable(stored)
    publication = publication_lease_state(stored)

    if context.domain_states:
        packets = build_evidence_packets(context)
        packet_dicts = _packet_dicts(packets)
        snapshot = evidence_snapshot_id(packets)
    else:
        packet_dicts = dict(stored.get("evidence_packets") or {})
        snapshot = str(
            publication.get("current_evidence_snapshot_id")
            or stored.get("evidence_snapshot_id")
            or ""
        )

    generated_snapshot = str(stored.get("evidence_snapshot_id") or "")
    evaluated_snapshot = str(evaluated.get("evidence_snapshot_id") or "")
    evidence_current = bool(
        artifact_publishable and generated_snapshot and generated_snapshot == snapshot
    )
    publication_materiality = dict(publication.get("materiality") or {})
    model_retained = publication_materiality.get("model_decision") == "retain_prior"
    evidence_materially_current = bool(
        evidence_current
        or (
            artifact_publishable
            and str(publication.get("current_evidence_snapshot_id") or "") == snapshot
            and (publication_materiality.get("material") is False or model_retained)
        )
    )
    publication_fresh = bool(artifact_publishable and publication.get("active"))
    publication_active = bool(artifact_publishable)

    if publication_active:
        reads = {
            domain: dict(
                (stored.get("reads") or {}).get(domain)
                or _unavailable_read(domain, packet_dicts.get(domain, {}))
            )
            for domain in DOMAIN_ORDER
        }
        reads["macro"] = dict(
            (stored.get("reads") or {}).get("macro") or _unavailable_read("macro", {})
        )
        status_name = "validated" if artifact_validated else str(stored.get("status") or "published_with_warnings")
    else:
        reads = {
            domain: _unavailable_read(domain, packet_dicts.get(domain, {}))
            for domain in DOMAIN_ORDER
        }
        reads["macro"] = _unavailable_read("macro", {})
        status_name = "missing" if not stored else "stale"

    status = {
        "status": status_name,
        "artifact_present": bool(stored),
        "artifact_validated": artifact_validated,
        "artifact_publishable": artifact_publishable,
        "evidence_current": evidence_current,
        "evidence_materially_current": evidence_materially_current,
        "evaluation_current": bool(evaluated_snapshot and evaluated_snapshot == snapshot),
        "last_evaluation_status": str(evaluated.get("status") or ""),
        "last_evaluation_decision": str(evaluated.get("decision") or ""),
        "evaluated_evidence_snapshot_id": evaluated_snapshot,
        "publication_active": publication_active,
        "publication_fresh": publication_fresh,
        "publication": publication,
        "evidence_snapshot_id": snapshot,
        "artifact_evidence_snapshot_id": generated_snapshot,
        "generated_at": stored.get("generated_at", "") if stored else "",
        "model": stored.get("model", "") if stored else "",
        "prompt_versions": stored.get("prompt_versions", {}) if stored else {},
        "validation": stored.get("validation", {}) if stored else {},
        "generation": stored.get("generation", {}) if stored else {},
    }
    by_domain = (context.current_context or {}).get("by_domain", {}) or {}
    for domain in DOMAIN_ORDER:
        reads[domain] = attach_current_context(reads[domain], by_domain.get(domain, {}), limit=2)
    reads["macro"] = attach_current_context(reads["macro"], context.current_context or {}, limit=3)
    status["packets"] = packet_dicts
    return reads, status


def _attempt_base(
    *,
    attempt_id: str,
    snapshot: str,
    packets: dict[str, dict],
    capsules: dict[str, Any],
    required_domains: list[str],
    candidate_domains: list[str],
    bootstrap: bool,
    config: OpenAIConfig,
) -> dict[str, Any]:
    return {
        "attempt_id": attempt_id,
        "status": "started",
        "stage": "editorial_synthesis",
        "evidence_snapshot_id": snapshot,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "model": config.model,
        "reasoning_effort": config.reasoning_effort,
        "max_output_tokens": config.max_output_tokens,
        "prompt_versions": prompt_versions(),
        "evidence_packets": packets,
        "signal_capsules": {key: value for key, value in capsules.items() if key != "fact_history"},
        "required_update_domains": list(required_domains),
        "candidate_update_domains": list(candidate_domains),
        "bootstrap": bool(bootstrap),
        "generation": {},
        "generated_output": {},
        "raw_responses": {},
        "validation": {},
        "service_version": READ_SERVICE_VERSION,
        "api_call_contract": {"editorial_calls": 1, "retries": 0},
    }


def _save_attempt(attempt: dict[str, Any], *, persist: bool) -> None:
    if persist:
        persist_read_attempt(attempt, attempt_id=str(attempt.get("attempt_id") or ""))


def _store_stage(
    attempt: dict[str, Any],
    *,
    model: Any,
    metadata: Any,
    persist: bool,
) -> None:
    attempt["generated_output"] = {"editorial_synthesis": model.model_dump(mode="json")}
    attempt["generation"] = {"editorial_synthesis": metadata.to_dict()}
    attempt["raw_responses"] = {"editorial_synthesis": metadata.response_payload}
    attempt["stage_prompt_versions"] = {
        "editorial_synthesis": str((attempt.get("prompt_versions") or {}).get("editorial") or "")
    }
    attempt["status"] = "editorial_synthesis_generated"
    _save_attempt(attempt, persist=persist)


def _raw_output_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    value = payload.get("_ai_macro_output_text")
    return value if isinstance(value, str) else ""


def _record_failure(
    attempt: dict[str, Any],
    *,
    error: Exception,
    persist: bool,
) -> str:
    metadata = getattr(error, "metadata", None)
    if metadata is not None:
        attempt["generation"] = {"editorial_synthesis": metadata.to_dict()}
        attempt["raw_responses"] = {"editorial_synthesis": metadata.response_payload}
    response_payload = getattr(error, "response_payload", None)
    if response_payload is not None:
        attempt["raw_responses"] = {"editorial_synthesis": response_payload}
    attempt["error"] = {
        "type": type(error).__name__,
        "message": str(error),
        "paid_response_preserved": response_payload is not None,
    }
    _save_attempt(attempt, persist=persist)
    return _raw_output_text(response_payload)


def _call_stage(
    attempt: dict[str, Any],
    *,
    call: Callable[[], tuple[Any, Any]],
    persist: bool,
) -> tuple[Any | None, str]:
    try:
        model, metadata = call()
    except Exception as exc:
        return None, _record_failure(attempt, error=exc, persist=persist)
    _store_stage(attempt, model=model, metadata=metadata, persist=persist)
    return model, ""


def _generation_failure(
    attempt: dict[str, Any],
    *,
    status: str,
    persist: bool,
) -> dict[str, Any]:
    attempt["status"] = status
    attempt["finished_at"] = datetime.now(timezone.utc).isoformat()
    _save_attempt(attempt, persist=persist)
    return {
        "status": status,
        "stage": "editorial_synthesis",
        "attempt_id": str(attempt.get("attempt_id") or ""),
        "evidence_snapshot_id": str(attempt.get("evidence_snapshot_id") or ""),
        "error": dict(attempt.get("error") or {}),
        "validation": dict(attempt.get("validation") or {}),
        "generation": dict(attempt.get("generation") or {}),
        "generated_output": dict(attempt.get("generated_output") or {}),
        "raw_responses": dict(attempt.get("raw_responses") or {}),
    }


def _persist_completed_evaluation(
    *,
    attempt: dict[str, Any],
    snapshot: str,
    packets: dict[str, Any],
    capsules: dict[str, Any],
    decision: str,
    decision_reason: str,
    analytical_state: dict[str, Any] | None,
    validation: dict[str, Any],
    status: str,
    persist: bool,
) -> dict[str, Any]:
    state = build_evaluated_state(
        snapshot_id=snapshot,
        packets=packets,
        capsules=capsules,
        attempt_id=str(attempt.get("attempt_id") or ""),
        decision=decision,
        decision_reason=decision_reason,
        analytical_state=analytical_state,
        validation=validation,
        status=status,
    )
    if persist:
        persist_evaluated_state(state)
    return state


def _merge_reads(
    *,
    prior_artifact: dict[str, Any],
    synthesis: GeneratedEditorialSynthesis,
    packets: dict[str, dict],
    snapshot: str,
    generated_at: str,
) -> dict[str, dict]:
    reads = {
        key: dict(value)
        for key, value in dict(prior_artifact.get("reads") or {}).items()
        if isinstance(value, dict)
    }
    for model in synthesis.domain_reads:
        reads[model.domain] = _domain_public_read(
            model,
            packets[model.domain],
            snapshot_id=snapshot,
            generated_at=generated_at,
        )
    missing = [domain for domain in DOMAIN_ORDER if not reads.get(domain)]
    if missing:
        raise ValueError("Published synthesis lacks domain Reads: " + ", ".join(missing))
    if synthesis.macro_read is None:
        raise ValueError("Published synthesis lacks its Macro Read.")
    reads["macro"] = _macro_public_read(
        synthesis.macro_read,
        packets,
        snapshot_id=snapshot,
        generated_at=generated_at,
    )
    return reads


def _publish_artifact(
    *,
    attempt: dict[str, Any],
    reads: dict[str, dict],
    validation: dict[str, Any],
    analytical_state: dict[str, Any],
    config: OpenAIConfig,
    status: str,
    persist: bool,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    artifact = {
        "status": status,
        "attempt_id": str(attempt.get("attempt_id") or ""),
        "evidence_snapshot_id": str(attempt.get("evidence_snapshot_id") or ""),
        "evaluated_evidence_snapshot_id": str(attempt.get("evidence_snapshot_id") or ""),
        "generated_at": generated_at,
        "model": config.model,
        "reasoning_effort": config.reasoning_effort,
        "max_output_tokens": config.max_output_tokens,
        "prompt_versions": dict(attempt.get("prompt_versions") or prompt_versions()),
        "stage_prompt_versions": dict(attempt.get("stage_prompt_versions") or {}),
        "capsule_architecture_version": CAPSULE_ARCHITECTURE_VERSION,
        "validation": validation,
        "generation": dict(attempt.get("generation") or {}),
        "raw_responses": dict(attempt.get("raw_responses") or {}),
        "evidence_packets": dict(attempt.get("evidence_packets") or {}),
        "analytical_state": dict(analytical_state or {}),
        "reads": reads,
        "service_version": READ_SERVICE_VERSION,
    }
    attempt["status"] = "completed_unpublished"
    attempt["stage"] = "publication"
    attempt["validation"] = validation
    attempt["published_artifact"] = artifact
    attempt["finished_at"] = datetime.now(timezone.utc).isoformat()
    _save_attempt(attempt, persist=persist)
    if persist:
        artifact = _with_publication_lease(artifact, source="generation")
        persist_read_artifact(artifact)
        attempt["published_artifact"] = artifact
        attempt["status"] = "validated_published" if status == "validated" else status
        _save_attempt(attempt, persist=True)
    return artifact


def generate_validated_read_artifact(
    context: DashboardContext,
    config: OpenAIConfig,
    *,
    client: Any | None = None,
    persist: bool = True,
    materiality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one editorial call; never issue a validator- or stage-triggered retry."""
    packets = build_evidence_packets(context)
    packet_dicts = _packet_dicts(packets)
    snapshot = evidence_snapshot_id(packets)
    prior_artifact = load_read_artifact()
    prior_evaluated = load_evaluated_state()
    baseline = prior_evaluated if prior_evaluated.get("evidence_packets") else prior_artifact
    comparison = dict(materiality or compare_evidence_materiality(
        baseline.get("evidence_packets"),
        packet_dicts,
        previous_snapshot_id=str(baseline.get("evidence_snapshot_id") or ""),
        current_snapshot_id=snapshot,
    ))
    bootstrap = not _artifact_is_publishable(prior_artifact)
    publication_comparison = compare_evidence_materiality(
        prior_artifact.get("evidence_packets"),
        packet_dicts,
        previous_snapshot_id=str(prior_artifact.get("evidence_snapshot_id") or ""),
        current_snapshot_id=snapshot,
    )
    required = (
        list(DOMAIN_ORDER)
        if bootstrap
        else required_update_domains(prior_artifact, publication_comparison)
    )
    capsule_materiality = _editorial_materiality(
        comparison,
        publication_comparison,
        required_domains=required,
    )
    candidates = list(DOMAIN_ORDER) if bootstrap else materially_changed_domains(comparison)
    for domain in required:
        if domain not in candidates:
            candidates.append(domain)
    candidates = [domain for domain in DOMAIN_ORDER if domain in candidates]
    observed_at = datetime.now(timezone.utc).isoformat()
    capsules = build_signal_capsules(
        packet_dicts,
        snapshot_id=snapshot,
        materiality=capsule_materiality,
        prior_state=prior_evaluated,
        prior_artifact=prior_artifact,
        observed_at=observed_at,
    )
    previous = prior_publication_payload(
        prior_artifact,
        relevant_domains=list(dict.fromkeys([*required, *candidates])),
    )
    attempt = _attempt_base(
        attempt_id=new_attempt_id(evidence_snapshot_id=snapshot),
        snapshot=snapshot,
        packets=packet_dicts,
        capsules=capsules,
        required_domains=required,
        candidate_domains=candidates,
        bootstrap=bootstrap,
        config=config,
    )
    attempt["materiality"] = comparison
    attempt["publication_gap_materiality"] = publication_comparison
    attempt["editorial_materiality"] = capsule_materiality
    synthesis, raw_text = _call_stage(
        attempt,
        call=lambda: generate_editorial_synthesis(
            capsules=capsules,
            prior_publication=previous,
            prior_analytical_state=dict(
                prior_evaluated.get("analytical_state")
                or prior_artifact.get("analytical_state")
                or {}
            ),
            required_update_domains=required,
            candidate_update_domains=candidates,
            bootstrap=bootstrap,
            config=config,
            client=client,
        ),
        persist=persist,
    )
    if synthesis is None:
        if raw_text:
            validation = {
                "passed": False,
                "hard_errors": ["Completed response did not conform to the editorial schema."],
                "validator_version": EDITORIAL_VALIDATOR_VERSION,
            }
            attempt["validation"] = validation
            _persist_completed_evaluation(
                attempt=attempt,
                snapshot=snapshot,
                packets=packet_dicts,
                capsules=capsules,
                decision="",
                decision_reason="Completed response was not parseable.",
                analytical_state={},
                validation=validation,
                status="rejected_unparseable",
                persist=persist,
            )
            return _generation_failure(attempt, status="rejected_unparseable", persist=persist)
        return _generation_failure(attempt, status="generation_failed", persist=persist)

    validation = validate_editorial_synthesis(
        synthesis,
        packet_dicts,
        required_update_domains=required,
        candidate_update_domains=candidates,
        allowed_fact_ids={
            str(fact.get("fact_id") or "")
            for capsule in (capsules.get("capsules") or [])
            if isinstance(capsule, dict)
            for fact in (capsule.get("facts") or [])
            if isinstance(fact, dict) and fact.get("fact_id")
        },
        bootstrap=bootstrap,
    )
    attempt["validation"] = validation
    analytical_state = synthesis.analytical_state.model_dump(mode="json")
    evaluated_status = (
        "retained_prior"
        if validation.get("passed") and synthesis.decision == "retain_prior"
        else "publishable"
        if validation.get("passed")
        else "rejected_hard_validation"
    )
    _persist_completed_evaluation(
        attempt=attempt,
        snapshot=snapshot,
        packets=packet_dicts,
        capsules=capsules,
        decision=synthesis.decision,
        decision_reason=synthesis.decision_reason,
        analytical_state=analytical_state,
        validation=validation,
        status=evaluated_status,
        persist=persist,
    )

    if not validation.get("passed"):
        attempt["status"] = "rejected_hard_validation"
        attempt["finished_at"] = datetime.now(timezone.utc).isoformat()
        _save_attempt(attempt, persist=persist)
        return _generation_failure(attempt, status="rejected_hard_validation", persist=persist)

    if synthesis.decision == "retain_prior":
        decision_materiality = {
            **comparison,
            "model_decision": "retain_prior",
            "model_decision_reason": synthesis.decision_reason,
        }
        renewed = reapply_last_read(
            persist=persist,
            source="model_retain_prior",
            current_evidence_snapshot_id=snapshot,
            materiality=decision_materiality,
        )
        attempt["status"] = "completed_retain_prior"
        attempt["stage"] = "publication"
        attempt["finished_at"] = datetime.now(timezone.utc).isoformat()
        _save_attempt(attempt, persist=persist)
        return {
            "status": "retained_prior",
            "stage": "publication",
            "attempt_id": str(attempt.get("attempt_id") or ""),
            "evidence_snapshot_id": snapshot,
            "decision_reason": synthesis.decision_reason,
            "validation": validation,
            "generation": dict(attempt.get("generation") or {}),
            "publication": dict(renewed.get("publication") or {}),
            "reads": dict(renewed.get("reads") or {}),
        }

    generated_at = datetime.now(timezone.utc).isoformat()
    try:
        reads = _merge_reads(
            prior_artifact=prior_artifact,
            synthesis=synthesis,
            packets=packet_dicts,
            snapshot=snapshot,
            generated_at=generated_at,
        )
    except ValueError as exc:
        validation = dict(validation)
        validation["passed"] = False
        validation.setdefault("hard_errors", []).append(str(exc))
        attempt["validation"] = validation
        attempt["error"] = {"type": type(exc).__name__, "message": str(exc)}
        # The typed response completed, so the evidence snapshot remains
        # evaluated; correct the provisional state to record that publication
        # was rejected at the final structural merge gate.
        _persist_completed_evaluation(
            attempt=attempt,
            snapshot=snapshot,
            packets=packet_dicts,
            capsules=capsules,
            decision=synthesis.decision,
            decision_reason=synthesis.decision_reason,
            analytical_state=analytical_state,
            validation=validation,
            status="rejected_hard_validation",
            persist=persist,
        )
        return _generation_failure(attempt, status="rejected_hard_validation", persist=persist)

    status = "published_with_warnings" if validation.get("diagnostics") else "validated"
    return _publish_artifact(
        attempt=attempt,
        reads=reads,
        validation=validation,
        analytical_state=analytical_state,
        config=config,
        status=status,
        persist=persist,
    )


__all__ = [
    "COMMENTARY_PUBLICATION_LEASE_HOURS",
    "PUBLISHABLE_STATUSES",
    "READ_SERVICE_COMPATIBLE_VERSIONS",
    "READ_SERVICE_VERSION",
    "build_platform_reads",
    "generate_validated_read_artifact",
    "publication_lease_state",
    "reapply_last_read",
]
