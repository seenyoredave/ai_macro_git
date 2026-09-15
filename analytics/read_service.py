"""One-call incremental commentary orchestration and publication control."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from analytics.dashboard_context import DashboardContext
from analytics.read_briefing import build_editorial_briefing, editorial_refresh_plan
from analytics.read_context import attach_current_context
from analytics.read_evidence import (
    DOMAIN_LABELS,
    DOMAIN_ORDER,
    EvidencePacket,
    build_evidence_packets,
    evidence_snapshot_id,
)
from analytics.read_generation import (
    generate_editorial_synthesis,
    prompt_versions,
)
from analytics.read_materiality import compare_evidence_materiality
from analytics.read_models import GeneratedDomainRead, GeneratedEditorialSynthesis, GeneratedMacroRead
from analytics.read_store import (
    load_read_artifact,
    new_attempt_id,
    persist_read_artifact,
    persist_read_attempt,
)
from analytics.read_validation import EDITORIAL_VALIDATOR_VERSION, validate_editorial_synthesis
from config.openai_config import OpenAIConfig

READ_SERVICE_VERSION = "6.1.0"
READ_SERVICE_COMPATIBLE_VERSIONS = {
    READ_SERVICE_VERSION,
    "6.0.0", "5.1.0", "5.0.0", "4.5.0", "4.4.0", "4.3.0", "4.2.0", "4.1.0", "3.2.0", "3.0.0",
}
COMMENTARY_PUBLICATION_LEASE_HOURS = 24
UNAVAILABLE_HEADLINE = "Commentary temporarily unavailable."
UNAVAILABLE_ANALYSIS = "The analyst has wandered off. The data have not."
MAX_MACRO_REFERENCES = 6
PUBLISHABLE_STATUSES = {"validated", "published_with_warnings"}


def _packet_dicts(packets: dict[str, EvidencePacket]) -> dict[str, dict]:
    return {domain: packet.to_dict() for domain, packet in packets.items()}


def _split_sentences(text: str) -> list[str]:
    import re
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", str(text or "").strip()) if part.strip()]


def _support_row(field: str, passage: Any) -> dict[str, Any]:
    return {
        "field": field,
        "text": str(passage.text or ""),
        "fact_ids": [str(item) for item in passage.fact_ids],
        "event_ids": [str(item) for item in passage.event_ids],
    }



def _event_reference_index(current_context: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    payload = dict(current_context or {})
    index: dict[str, dict[str, Any]] = {}

    def add(event: Any) -> None:
        if not isinstance(event, dict):
            return
        event_id = str(event.get("event_id") or "").strip()
        if not event_id:
            return
        label = str(event.get("source_label") or event.get("source_name") or "").strip()
        url = str(event.get("source_url") or "").strip()
        if label:
            index[event_id] = {"source_label": label, "source_url": url}

    for event in payload.get("events", []) or []:
        add(event)
    for domain_payload in (payload.get("by_domain") or {}).values():
        if isinstance(domain_payload, dict):
            for event in domain_payload.get("events", []) or []:
                add(event)
    return index


def _merge_references(base: list[dict[str, Any]], event_ids: list[str], event_references: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for reference in [*base, *[event_references.get(event_id, {}) for event_id in event_ids]]:
        if not isinstance(reference, dict):
            continue
        key = (str(reference.get("source_label") or ""), str(reference.get("source_url") or ""))
        if not key[0] or key in seen:
            continue
        seen.add(key)
        output.append(dict(reference))
    return output

def _domain_public_read(
    read_model: GeneratedDomainRead,
    packet: dict[str, Any],
    *,
    event_references: dict[str, dict[str, Any]] | None = None,
    snapshot_id: str = "",
    generated_at: str = "",
) -> dict[str, Any]:
    body = str(read_model.body.text or "").strip()
    cited_events = [*read_model.headline.event_ids, *read_model.body.event_ids]
    references = _merge_references(
        [dict(item) for item in packet.get("references", []) or []],
        [str(item) for item in cited_events],
        dict(event_references or {}),
    )
    return {
        "domain": read_model.domain,
        "label": DOMAIN_LABELS[read_model.domain],
        "headline": read_model.headline.text,
        "analysis": body,
        "analysis_sentences": _split_sentences(body),
        "references": references,
        "claim_support": [
            _support_row("headline", read_model.headline),
            _support_row("body", read_model.body),
        ],
        "evidence_snapshot_id": str(snapshot_id or ""),
        "generated_at": str(generated_at or ""),
        "generator": "openai",
        "version": READ_SERVICE_VERSION,
    }


def _macro_public_read(
    read_model: GeneratedMacroRead,
    packets: dict[str, dict],
    *,
    event_references: dict[str, dict[str, Any]] | None = None,
    snapshot_id: str = "",
    generated_at: str = "",
) -> dict[str, Any]:
    passages = [read_model.headline, *read_model.paragraphs]
    fact_ids: list[str] = []
    for passage in passages:
        for fact_id in passage.fact_ids:
            if fact_id not in fact_ids:
                fact_ids.append(str(fact_id))
    selected = [
        domain for domain in DOMAIN_ORDER
        if any(fact_id.startswith(f"{domain}.") for fact_id in fact_ids)
    ]

    references: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for domain in selected:
        for reference in packets.get(domain, {}).get("references", []) or []:
            key = (str(reference.get("source_label") or ""), str(reference.get("source_url") or ""))
            if not key[0] or key in seen:
                continue
            seen.add(key)
            references.append(dict(reference))
            if len(references) >= MAX_MACRO_REFERENCES:
                break
        if len(references) >= MAX_MACRO_REFERENCES:
            break

    cited_events = [str(event_id) for passage in passages for event_id in passage.event_ids]
    references = _merge_references(references, cited_events, dict(event_references or {}))[:MAX_MACRO_REFERENCES]

    fact_index: dict[str, dict[str, Any]] = {}
    for packet in packets.values():
        for fact in packet.get("facts", []) or []:
            if isinstance(fact, dict) and fact.get("id"):
                fact_index[str(fact["id"])] = dict(fact)
    evidence = [
        {
            "fact_id": fact_id,
            "label": str(fact_index.get(fact_id, {}).get("label") or fact_id),
            "value": str(fact_index.get(fact_id, {}).get("display") or "n/a"),
            "context": str(fact_index.get(fact_id, {}).get("context") or ""),
        }
        for fact_id in fact_ids[:3]
    ]
    paragraphs = [str(paragraph.text or "").strip() for paragraph in read_model.paragraphs]
    analysis = " ".join(paragraphs)
    sentences = [sentence for paragraph in paragraphs for sentence in _split_sentences(paragraph)]
    return {
        "domain": "macro",
        "label": DOMAIN_LABELS["macro"],
        "headline": read_model.headline.text,
        "analysis": analysis,
        "analysis_sentences": sentences,
        "analysis_paragraphs": paragraphs,
        "selected_domains": selected,
        "references": references,
        "claim_support": [
            _support_row("headline", read_model.headline),
            *[_support_row(f"paragraphs[{index}]", paragraph) for index, paragraph in enumerate(read_model.paragraphs)],
        ],
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
    artifact_validated = _artifact_is_validated(stored)
    artifact_publishable = _artifact_is_publishable(stored)
    publication = publication_lease_state(stored)

    if context.domain_states:
        packets = build_evidence_packets(context)
        packet_dicts = _packet_dicts(packets)
        snapshot = evidence_snapshot_id(packets)
    else:
        packet_dicts = dict(stored.get("evidence_packets") or {})
        snapshot = str(publication.get("current_evidence_snapshot_id") or stored.get("evidence_snapshot_id") or "")

    generated_snapshot = str(stored.get("evidence_snapshot_id") or "")
    evidence_current = bool(artifact_publishable and generated_snapshot and generated_snapshot == snapshot)
    publication_materiality = dict(publication.get("materiality") or {})
    evidence_materially_current = bool(
        evidence_current
        or (
            artifact_publishable
            and str(publication.get("current_evidence_snapshot_id") or "") == snapshot
            and publication_materiality.get("material") is False
        )
    )
    publication_fresh = bool(artifact_publishable and publication.get("active"))

    if artifact_publishable:
        reads = {
            domain: dict((stored.get("reads") or {}).get(domain) or _unavailable_read(domain, packet_dicts.get(domain, {})))
            for domain in DOMAIN_ORDER
        }
        reads["macro"] = dict((stored.get("reads") or {}).get("macro") or _unavailable_read("macro", {}))
        status_name = "validated" if artifact_validated else str(stored.get("status") or "published_with_warnings")
    else:
        reads = {domain: _unavailable_read(domain, packet_dicts.get(domain, {})) for domain in DOMAIN_ORDER}
        reads["macro"] = _unavailable_read("macro", {})
        status_name = "missing" if not stored else "stale"

    status = {
        "status": status_name,
        "artifact_present": bool(stored),
        "artifact_validated": artifact_validated,
        "artifact_publishable": artifact_publishable,
        "evidence_current": evidence_current,
        "evidence_materially_current": evidence_materially_current,
        "evaluation_current": False,
        "evaluation_contract_current": False,
        "last_evaluation_status": "",
        "last_evaluation_decision": "",
        "evaluated_evidence_snapshot_id": "",
        "publication_active": artifact_publishable,
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
    briefing: dict[str, Any],
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
        "editorial_briefing": briefing,
        "candidate_domains": list(candidate_domains),
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
    generated = model.model_dump(mode="json")
    attempt["generated_output"] = {"editorial_synthesis": generated}
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
        "refresh_plan": dict(attempt.get("refresh_plan") or {}),
    }


def _merge_reads(
    *,
    prior_artifact: dict[str, Any],
    synthesis: GeneratedEditorialSynthesis,
    packets: dict[str, dict],
    current_context: dict[str, Any] | None,
    snapshot: str,
    generated_at: str,
) -> dict[str, dict]:
    reads = {
        key: dict(value)
        for key, value in dict(prior_artifact.get("reads") or {}).items()
        if isinstance(value, dict)
    }
    event_references = _event_reference_index(current_context)
    for model in synthesis.domain_reads:
        reads[model.domain] = _domain_public_read(
            model,
            packets[model.domain],
            event_references=event_references,
            snapshot_id=snapshot,
            generated_at=generated_at,
        )
    missing = [domain for domain in DOMAIN_ORDER if not reads.get(domain)]
    if missing:
        raise ValueError("Published synthesis lacks domain Reads: " + ", ".join(missing))
    reads["macro"] = _macro_public_read(
        synthesis.macro_read,
        packets,
        event_references=event_references,
        snapshot_id=snapshot,
        generated_at=generated_at,
    )
    return reads


def _publish_artifact(
    *,
    attempt: dict[str, Any],
    reads: dict[str, dict],
    validation: dict[str, Any],
    config: OpenAIConfig,
    status: str,
    persist: bool,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    artifact = {
        "status": status,
        "attempt_id": str(attempt.get("attempt_id") or ""),
        "evidence_snapshot_id": str(attempt.get("evidence_snapshot_id") or ""),
        "generated_at": generated_at,
        "model": config.model,
        "reasoning_effort": config.reasoning_effort,
        "max_output_tokens": config.max_output_tokens,
        "prompt_versions": dict(attempt.get("prompt_versions") or prompt_versions()),
        "stage_prompt_versions": dict(attempt.get("stage_prompt_versions") or {}),
        "validation": validation,
        "generation": dict(attempt.get("generation") or {}),
        "raw_responses": dict(attempt.get("raw_responses") or {}),
        "evidence_packets": dict(attempt.get("evidence_packets") or {}),
        "editorial_briefing_version": str((attempt.get("prompt_versions") or {}).get("briefing") or ""),
        "editorial_context_event_ids": [
            str(event.get("event_id") or "")
            for event in (attempt.get("editorial_briefing") or {}).get("recent_developments", []) or []
            if isinstance(event, dict) and event.get("event_id")
        ],
        "editorial_candidate_domains": list(attempt.get("candidate_domains") or []),
        "editorial_update_domains": [
            str(item.get("domain") or "")
            for item in (((attempt.get("generated_output") or {}).get("editorial_synthesis") or {}).get("domain_reads") or [])
            if isinstance(item, dict) and item.get("domain")
        ],
        "editorial_refresh_plan": dict(attempt.get("refresh_plan") or {}),
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
    force_preview: bool = False,
) -> dict[str, Any]:
    """Generate one publication candidate; reject bad output without retrying or replacing the prior Read."""
    packets = build_evidence_packets(context)
    packet_dicts = _packet_dicts(packets)
    snapshot = evidence_snapshot_id(packets)
    prior_artifact = load_read_artifact()
    bootstrap = not _artifact_is_publishable(prior_artifact)
    comparison = dict(materiality or compare_evidence_materiality(
        prior_artifact.get("evidence_packets"),
        packet_dicts,
        previous_snapshot_id=str(prior_artifact.get("evidence_snapshot_id") or ""),
        current_snapshot_id=snapshot,
    ))
    refresh_plan = editorial_refresh_plan(
        comparison,
        current_context=context.current_context,
        prior_artifact=prior_artifact,
        bootstrap=bootstrap,
    )
    candidates = [
        domain for domain in DOMAIN_ORDER
        if domain in set(refresh_plan.get("candidate_domains") or [])
    ]
    if force_preview and not bootstrap:
        if not candidates:
            candidates = list(DOMAIN_ORDER)
        refresh_plan = {
            **refresh_plan,
            "refresh_needed": True,
            "candidate_domains": list(candidates),
            "reason": "owner_preview",
        }

    if not refresh_plan.get("refresh_needed") and not bootstrap:
        renewed = reapply_last_read(
            persist=persist,
            source="service_no_editorial_change_reapply",
            current_evidence_snapshot_id=snapshot,
            materiality=comparison,
        )
        return {
            "status": "retained_prior",
            "stage": "publication",
            "attempt_id": "",
            "evidence_snapshot_id": snapshot,
            "validation": {},
            "refresh_plan": refresh_plan,
            "publication": dict(renewed.get("publication") or {}),
            "reads": dict(renewed.get("reads") or {}),
        }

    briefing = build_editorial_briefing(
        packet_dicts,
        current_context=context.current_context,
        materiality=comparison,
        prior_artifact=prior_artifact,
        candidate_domains=candidates,
        bootstrap=bootstrap,
        new_event_ids=list(refresh_plan.get("new_event_ids") or []),
    )
    attempt = _attempt_base(
        attempt_id=new_attempt_id(evidence_snapshot_id=snapshot),
        snapshot=snapshot,
        packets=packet_dicts,
        briefing=briefing,
        candidate_domains=candidates,
        bootstrap=bootstrap,
        config=config,
    )
    attempt["materiality"] = comparison
    attempt["refresh_plan"] = refresh_plan
    synthesis, raw_text = _call_stage(
        attempt,
        call=lambda: generate_editorial_synthesis(
            briefing=briefing,
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
                "hard_failures": [{
                    "label": "editorial_synthesis",
                    "reason": "unparseable",
                    "message": "Completed response did not conform to the editorial schema.",
                }],
                "diagnostics": [],
                "validator_version": EDITORIAL_VALIDATOR_VERSION,
            }
            attempt["validation"] = validation
            return _generation_failure(attempt, status="rejected_unparseable", persist=persist)
        return _generation_failure(attempt, status="generation_failed", persist=persist)

    validation = validate_editorial_synthesis(
        synthesis,
        packet_dicts,
        briefing=briefing,
        candidate_domains=candidates,
        bootstrap=bootstrap,
    )
    attempt["validation"] = validation
    if not validation.get("passed"):
        return _generation_failure(attempt, status="rejected_hard_validation", persist=persist)

    generated_at = datetime.now(timezone.utc).isoformat()
    try:
        reads = _merge_reads(
            prior_artifact=prior_artifact,
            synthesis=synthesis,
            packets=packet_dicts,
            current_context=context.current_context,
            snapshot=snapshot,
            generated_at=generated_at,
        )
    except ValueError as exc:
        validation = dict(validation)
        validation["passed"] = False
        validation.setdefault("hard_errors", []).append(str(exc))
        validation.setdefault("hard_failures", []).append({
            "label": "publication",
            "reason": "structural_merge",
            "message": str(exc),
        })
        attempt["validation"] = validation
        attempt["error"] = {"type": type(exc).__name__, "message": str(exc)}
        return _generation_failure(attempt, status="rejected_hard_validation", persist=persist)

    status = "published_with_warnings" if validation.get("diagnostics") else "validated"
    return _publish_artifact(
        attempt=attempt,
        reads=reads,
        validation=validation,
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
