"""Two-call commentary orchestration and nonblocking publication diagnostics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from analytics.dashboard_context import DashboardContext
from analytics.read_context import attach_current_context
from analytics.read_evidence import (
    DOMAIN_LABELS,
    DOMAIN_ORDER,
    EvidencePacket,
    build_evidence_packets,
    evidence_fact_index,
    evidence_snapshot_id,
    model_evidence_packets,
)
from analytics.read_generation import (
    GenerationStageError,
    generate_domain_reads,
    generate_macro_read,
    prompt_versions,
)
from analytics.read_models import GeneratedDomainRead, GeneratedDomainReadSet, GeneratedMacroRead, SupportedSentence
from analytics.read_store import (
    load_read_artifact,
    load_read_attempt,
    new_attempt_id,
    persist_read_artifact,
    persist_read_attempt,
)
from analytics.read_validation import VALIDATOR_VERSION, validate_domain_read_set, validate_macro_read
from config.openai_config import OpenAIConfig

READ_SERVICE_VERSION = "4.5.0"
READ_SERVICE_COMPATIBLE_VERSIONS = {READ_SERVICE_VERSION, "4.4.0", "4.3.0", "4.2.0", "4.1.0", "3.2.0", "3.0.0"}
# The 24-hour lease is a freshness diagnostic, not a visibility cutoff. A
# publishable artifact remains the last-known-good commentary until a newer
# artifact successfully replaces it.
COMMENTARY_PUBLICATION_LEASE_HOURS = 24
UNAVAILABLE_HEADLINE = "Commentary temporarily unavailable."
UNAVAILABLE_ANALYSIS = "The analyst has wandered off. The data have not."
MAX_MACRO_REFERENCES = 6
PUBLISHABLE_STATUSES = {"validated", "published_with_warnings", "published_raw_response"}
_PAID_PIPELINE_STAGES = ("domain_reads", "macro_read")


def _packet_dicts(packets: dict[str, EvidencePacket]) -> dict[str, dict]:
    return {domain: packet.to_dict() for domain, packet in packets.items()}


def _model_packet_dicts(packets: dict[str, EvidencePacket]) -> dict[str, dict]:
    return model_evidence_packets(packets)


def _claim_rows(read_model: Any) -> list[dict[str, Any]]:
    rows = [{"field": "headline", **read_model.headline.model_dump()}]
    rows.extend({"field": f"analysis[{index}]", **item.model_dump()} for index, item in enumerate(read_model.analysis))
    return rows


def _domain_public_read(read_model: GeneratedDomainRead, packet: dict[str, Any]) -> dict[str, Any]:
    sentences = [item.text for item in read_model.analysis]
    return {
        "domain": read_model.domain,
        "label": DOMAIN_LABELS[read_model.domain],
        "headline": read_model.headline.text,
        "analysis": " ".join(sentences),
        "analysis_sentences": sentences,
        "references": [dict(item) for item in packet.get("references", []) or []],
        "claim_support": _claim_rows(read_model),
        "generator": "openai",
        "version": READ_SERVICE_VERSION,
    }


def _macro_public_read(read_model: GeneratedMacroRead, packets: dict[str, dict]) -> dict[str, Any]:
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
    evidence = []
    for fact_id in fact_ids[:3]:
        fact = fact_index.get(fact_id, {})
        evidence.append({
            "fact_id": fact_id,
            "label": str(fact.get("label") or fact_id),
            "value": str(fact.get("display") or "n/a"),
            "context": str(fact.get("context") or ""),
        })

    sentences = [item.text for item in read_model.analysis]
    paragraphs = [" ".join(sentence.text for sentence in paragraph.sentences) for paragraph in read_model.paragraphs]
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
        "generator": "openai",
        "version": READ_SERVICE_VERSION,
    }


def _raw_public_read(text: str) -> dict[str, Any]:
    return {
        "domain": "macro",
        "label": DOMAIN_LABELS["macro"],
        "headline": "OpenAI response",
        "analysis": text,
        "analysis_sentences": [text],
        "analysis_paragraphs": [text],
        "selected_domains": [],
        "references": [],
        "claim_support": [],
        "evidence": [],
        "generator": "openai_raw",
        "raw_response": True,
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


def publication_lease_state(artifact: dict[str, Any] | None, *, now: datetime | None = None) -> dict[str, Any]:
    stored = dict(artifact or {})
    publication = dict(stored.get("publication") or {})
    published_at = _utc_datetime(publication.get("published_at") or stored.get("published_at") or stored.get("generated_at"))
    expires_at = published_at + timedelta(hours=COMMENTARY_PUBLICATION_LEASE_HOURS) if published_at else None
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    active = bool(published_at and expires_at and current < expires_at)
    return {
        "active": active,
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
    renewal = source in {"manual_reapply", "automation_reapply", "automation_immaterial_reapply"}
    output = dict(artifact)
    output["publication"] = {
        "lease_hours": COMMENTARY_PUBLICATION_LEASE_HOURS,
        "published_at": current.isoformat(),
        "expires_at": (current + timedelta(hours=COMMENTARY_PUBLICATION_LEASE_HOURS)).isoformat(),
        "renewal_count": int(previous.get("renewal_count", 0) or 0) + (1 if renewal else 0) if renewal else 0,
        "source": source,
        "current_evidence_snapshot_id": str(current_evidence_snapshot_id or artifact.get("evidence_snapshot_id") or ""),
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


def build_platform_reads(context: DashboardContext, *, artifact: dict | None = None) -> tuple[dict[str, dict], dict[str, Any]]:
    packets = build_evidence_packets(context)
    packet_dicts = _packet_dicts(packets)
    snapshot = evidence_snapshot_id(packets)
    stored = dict(artifact if artifact is not None else load_read_artifact())
    artifact_validated = _artifact_is_validated(stored)
    artifact_publishable = _artifact_is_publishable(stored)
    evidence_current = bool(artifact_publishable and str(stored.get("evidence_snapshot_id") or "") == snapshot)
    publication = publication_lease_state(stored)
    publication_materiality = dict(publication.get("materiality") or {})
    evidence_materially_current = bool(
        evidence_current
        or (
            artifact_publishable
            and str(publication.get("current_evidence_snapshot_id") or "") == snapshot
            and publication_materiality.get("material") is False
        )
    )

    # Visibility is last-known-good, not lease-based. The nested publication
    # lease still tells callers whether the artifact was refreshed within the
    # nominal 24-hour freshness window, but expiration alone never hides a
    # publishable read. This lets Friday remain visible until Monday (or any
    # later successful run) actually publishes a replacement.
    publication_fresh = bool(artifact_publishable and publication.get("active"))
    publication_active = bool(artifact_publishable)

    if publication_active:
        reads = {
            domain: dict((stored.get("reads") or {}).get(domain) or _unavailable_read(domain, packet_dicts[domain]))
            for domain in DOMAIN_ORDER
        }
        reads["macro"] = dict((stored.get("reads") or {}).get("macro") or _unavailable_read("macro", {}))
        status_name = "validated" if artifact_validated else str(stored.get("status") or "published_with_warnings")
    else:
        reads = {domain: _unavailable_read(domain, packet_dicts[domain]) for domain in DOMAIN_ORDER}
        reads["macro"] = _unavailable_read("macro", {})
        if not stored:
            status_name = "missing"
        else:
            status_name = "stale"

    status = {
        "status": status_name,
        "artifact_present": bool(stored),
        "artifact_validated": artifact_validated,
        "artifact_publishable": artifact_publishable,
        "evidence_current": evidence_current,
        "evidence_materially_current": evidence_materially_current,
        "publication_active": publication_active,
        "publication_fresh": publication_fresh,
        "publication": publication,
        "evidence_snapshot_id": snapshot,
        "artifact_evidence_snapshot_id": stored.get("evidence_snapshot_id", "") if stored else "",
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


def _attempt_base(*, attempt_id: str, snapshot: str, packets: dict[str, dict], model_packets: dict[str, dict], config: OpenAIConfig) -> dict[str, Any]:
    return {
        "attempt_id": attempt_id,
        "status": "started",
        "stage": "domain_reads",
        "evidence_snapshot_id": snapshot,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "model": config.model,
        "reasoning_effort": config.reasoning_effort,
        "prompt_versions": prompt_versions(),
        "stage_prompt_versions": {},
        "evidence_packets": packets,
        "model_evidence_packets": model_packets,
        "generation": {},
        "generated_output": {},
        "raw_responses": {},
        "validation": {},
        "service_version": READ_SERVICE_VERSION,
        "api_call_contract": {"domain_calls": 1, "macro_calls": 1, "retries": 0},
    }


def _save_attempt(attempt: dict[str, Any], *, persist: bool) -> None:
    if persist:
        persist_read_attempt(attempt, attempt_id=str(attempt.get("attempt_id") or ""))


def _store_stage(attempt: dict[str, Any], *, key: str, model: Any, metadata: Any, persist: bool) -> None:
    generated = dict(attempt.get("generated_output") or {})
    generated[key] = model.model_dump(mode="json")
    attempt["generated_output"] = generated
    generation = dict(attempt.get("generation") or {})
    generation[key] = metadata.to_dict()
    attempt["generation"] = generation
    raw = dict(attempt.get("raw_responses") or {})
    raw[key] = metadata.response_payload
    attempt["raw_responses"] = raw
    attempt["stage_prompt_versions"] = {
        **dict(attempt.get("stage_prompt_versions") or {}),
        key: str((attempt.get("prompt_versions") or {}).get("domain" if key == "domain_reads" else "macro") or ""),
    }
    attempt["status"] = f"{key}_generated"
    attempt["stage"] = key
    _save_attempt(attempt, persist=persist)


def _record_failure(attempt: dict[str, Any], *, stage: str, error: Exception, persist: bool) -> str:
    metadata = getattr(error, "metadata", None)
    if metadata is not None:
        attempt["generation"] = {**dict(attempt.get("generation") or {}), stage: metadata.to_dict()}
        attempt["raw_responses"] = {**dict(attempt.get("raw_responses") or {}), stage: metadata.response_payload}
    response_payload = getattr(error, "response_payload", None)
    if response_payload is not None:
        attempt["raw_responses"] = {**dict(attempt.get("raw_responses") or {}), stage: response_payload}
    attempt["stage"] = stage
    attempt["error"] = {
        "type": type(error).__name__,
        "message": str(error),
        "paid_response_preserved": response_payload is not None,
    }
    _save_attempt(attempt, persist=persist)
    return _raw_output_text(response_payload)


def _raw_output_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    value = payload.get("_ai_macro_output_text")
    return value if isinstance(value, str) else ""


def _generation_failure(attempt: dict[str, Any], *, stage: str, persist: bool) -> dict[str, Any]:
    attempt["status"] = "generation_failed"
    attempt["stage"] = stage
    attempt["finished_at"] = datetime.now(timezone.utc).isoformat()
    _save_attempt(attempt, persist=persist)
    return {
        "status": "generation_failed",
        "stage": stage,
        "attempt_id": str(attempt.get("attempt_id") or ""),
        "evidence_snapshot_id": str(attempt.get("evidence_snapshot_id") or ""),
        "error": dict(attempt.get("error") or {}),
        "validation": dict(attempt.get("validation") or {}),
        "generation": dict(attempt.get("generation") or {}),
        "generated_output": dict(attempt.get("generated_output") or {}),
        "raw_responses": dict(attempt.get("raw_responses") or {}),
    }


def _call_stage(
    attempt: dict[str, Any],
    *,
    key: str,
    call: Callable[[], tuple[Any, Any]],
    persist: bool,
) -> tuple[Any | None, str]:
    try:
        model, metadata = call()
    except Exception as exc:
        return None, _record_failure(attempt, stage=key, error=exc, persist=persist)
    _store_stage(attempt, key=key, model=model, metadata=metadata, persist=persist)
    return model, ""


def _domain_texts_from_models(domain_set: GeneratedDomainReadSet) -> dict[str, list[str]]:
    return {read.domain: [read.headline.text, *[item.text for item in read.analysis]] for read in domain_set.reads}


def _domain_models_from_public_reads(reads: dict[str, Any]) -> GeneratedDomainReadSet:
    models: list[GeneratedDomainRead] = []
    for domain in DOMAIN_ORDER:
        read = dict(reads.get(domain) or {})
        claims = [item for item in (read.get("claim_support") or []) if isinstance(item, dict)]
        headline = next((item for item in claims if item.get("field") == "headline"), None)
        analysis = [item for item in claims if str(item.get("field") or "").startswith("analysis[")]
        if headline is None or len(analysis) not in {3, 4}:
            raise ValueError(f"Published {domain} Read lacks its complete typed OpenAI output.")
        models.append(GeneratedDomainRead(
            domain=domain,
            headline=SupportedSentence.model_validate({key: headline[key] for key in ("text", "fact_ids", "inference")}),
            analysis=[SupportedSentence.model_validate({key: item[key] for key in ("text", "fact_ids", "inference")}) for item in analysis],
        ))
    return GeneratedDomainReadSet(reads=models)


def _validation_summary(domain_report: dict[str, Any] | None, macro_report: dict[str, Any] | None, *, raw_stage: str = "") -> dict[str, Any]:
    domain = dict(domain_report or {})
    macro = dict(macro_report or {})
    gates = {
        "domain_grounding": bool(domain.get("passed")) if domain else False,
        "macro_grounding": bool(macro.get("passed")) if macro else False,
    }
    checked = int(domain.get("checked_claims", 0) or 0) + int(macro.get("checked_claims", 0) or 0)
    grounded = int(domain.get("grounded_claims", 0) or 0) + int(macro.get("grounded_claims", 0) or 0)
    return {
        "domain": domain,
        "macro": macro,
        "gate_results": gates,
        "passed": bool(gates["domain_grounding"] and gates["macro_grounding"] and not raw_stage),
        "checked_claims": checked,
        "grounded_claims": grounded,
        "raw_stage": raw_stage,
        "publication_policy": "publish_every_completed_openai_response_with_diagnostics",
        "validator_version": VALIDATOR_VERSION,
    }


def _publish_artifact(
    *,
    attempt: dict[str, Any],
    reads: dict[str, dict],
    validation: dict[str, Any],
    config: OpenAIConfig,
    status: str,
    source: str,
    persist: bool,
    base: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact = dict(base or {})
    artifact.update({
        "status": status,
        "attempt_id": str(attempt.get("attempt_id") or ""),
        "evidence_snapshot_id": str(attempt.get("evidence_snapshot_id") or ""),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": config.model,
        "reasoning_effort": config.reasoning_effort,
        "prompt_versions": dict(attempt.get("prompt_versions") or prompt_versions()),
        "stage_prompt_versions": dict(attempt.get("stage_prompt_versions") or {}),
        "validation": validation,
        "generation": dict(attempt.get("generation") or {}),
        "raw_responses": dict(attempt.get("raw_responses") or {}),
        "evidence_packets": dict(attempt.get("evidence_packets") or {}),
        "reads": reads,
        "service_version": READ_SERVICE_VERSION,
    })
    attempt["status"] = "completed_unpublished"
    attempt["stage"] = "publication"
    attempt["validation"] = validation
    attempt["published_artifact"] = artifact
    attempt["finished_at"] = datetime.now(timezone.utc).isoformat()
    _save_attempt(attempt, persist=persist)
    if persist:
        artifact = _with_publication_lease(artifact, source=source)
        persist_read_artifact(artifact)
        attempt["published_artifact"] = artifact
        attempt["status"] = "validated_published" if status == "validated" else status
        _save_attempt(attempt, persist=True)
    return artifact


def _execute_two_call_pipeline(
    *,
    attempt: dict[str, Any],
    packet_dicts: dict[str, dict],
    model_packet_dicts: dict[str, dict],
    config: OpenAIConfig,
    client: Any | None,
    persist: bool,
) -> dict[str, Any]:
    generated = dict(attempt.get("generated_output") or {})
    domain_set: GeneratedDomainReadSet | None = None
    domain_raw = ""
    if generated.get("domain_reads"):
        domain_set = GeneratedDomainReadSet.model_validate(generated["domain_reads"])
    else:
        domain_set, domain_raw = _call_stage(
            attempt,
            key="domain_reads",
            call=lambda: generate_domain_reads(model_packet_dicts, config, client=client),
            persist=persist,
        )
    if domain_set is None and not domain_raw:
        return _generation_failure(attempt, stage="domain_reads", persist=persist)

    domain_report = validate_domain_read_set(domain_set, packet_dicts).to_dict() if domain_set is not None else {}
    attempt["validation"] = {"domain": domain_report}
    macro_input: GeneratedDomainReadSet | dict[str, Any]
    macro_input = domain_set if domain_set is not None else {"raw_openai_domain_response": domain_raw}

    generated = dict(attempt.get("generated_output") or {})
    macro_model: GeneratedMacroRead | None = None
    macro_raw = ""
    if generated.get("macro_read"):
        macro_model = GeneratedMacroRead.model_validate(generated["macro_read"])
    else:
        macro_model, macro_raw = _call_stage(
            attempt,
            key="macro_read",
            call=lambda: generate_macro_read(model_packet_dicts, macro_input, config, client=client),
            persist=persist,
        )
    if macro_model is None and not macro_raw:
        return _generation_failure(attempt, stage="macro_read", persist=persist)

    macro_report = (
        validate_macro_read(
            macro_model,
            packet_dicts,
            domain_texts=_domain_texts_from_models(domain_set) if domain_set is not None else {},
        ).to_dict()
        if macro_model is not None
        else {}
    )
    raw_stage = "domain_reads" if domain_set is None else "macro_read" if macro_model is None else ""
    validation = _validation_summary(domain_report, macro_report, raw_stage=raw_stage)

    if domain_set is not None:
        domain_models = {read.domain: read for read in domain_set.reads}
        reads = {domain: _domain_public_read(domain_models[domain], packet_dicts[domain]) for domain in DOMAIN_ORDER}
    else:
        reads = {domain: _unavailable_read(domain, packet_dicts[domain]) for domain in DOMAIN_ORDER}
    reads["macro"] = _macro_public_read(macro_model, packet_dicts) if macro_model is not None else _raw_public_read(macro_raw)
    unparsed_outputs: list[dict[str, str]] = []
    if domain_raw:
        unparsed_outputs.append({"stage": "Domain", "text": domain_raw})
    if macro_raw and macro_model is not None:
        unparsed_outputs.append({"stage": "AI Macro", "text": macro_raw})
    if unparsed_outputs:
        reads["macro"]["unparsed_openai_responses"] = unparsed_outputs
    status = "published_raw_response" if raw_stage else "validated" if validation["passed"] else "published_with_warnings"
    return _publish_artifact(
        attempt=attempt,
        reads=reads,
        validation=validation,
        config=config,
        status=status,
        source="generation",
        persist=persist,
    )


def generate_validated_read_artifact(
    context: DashboardContext,
    config: OpenAIConfig,
    *,
    client: Any | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Run exactly one domain call followed by exactly one Macro call."""
    packets = build_evidence_packets(context)
    packet_dicts = _packet_dicts(packets)
    model_packet_dicts = _model_packet_dicts(packets)
    snapshot = evidence_snapshot_id(packets)
    attempt = _attempt_base(
        attempt_id=new_attempt_id(evidence_snapshot_id=snapshot),
        snapshot=snapshot,
        packets=packet_dicts,
        model_packets=model_packet_dicts,
        config=config,
    )
    return _execute_two_call_pipeline(
        attempt=attempt,
        packet_dicts=packet_dicts,
        model_packet_dicts=model_packet_dicts,
        config=config,
        client=client,
        persist=persist,
    )


def recovery_call_plan(attempt: dict[str, Any], packet_dicts: dict[str, dict] | None = None) -> dict[str, Any]:
    generated = dict(attempt.get("generated_output") or {})
    reusable: list[str] = []
    for key, contract in (("domain_reads", GeneratedDomainReadSet), ("macro_read", GeneratedMacroRead)):
        if not generated.get(key):
            break
        try:
            contract.model_validate(generated[key])
        except (TypeError, ValueError):
            break
        reusable.append(key)
    return {
        "reused_outputs": reusable,
        "discarded_outputs": [key for key in _PAID_PIPELINE_STAGES if generated.get(key) and key not in reusable],
        "api_calls_required": len(_PAID_PIPELINE_STAGES) - len(reusable),
        "source_attempt_id": str(attempt.get("attempt_id") or ""),
    }


def resume_saved_read_attempt(
    context: DashboardContext,
    config: OpenAIConfig,
    attempt_id: str,
    *,
    client: Any | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    packets = build_evidence_packets(context)
    packet_dicts = _packet_dicts(packets)
    model_packet_dicts = _model_packet_dicts(packets)
    snapshot = evidence_snapshot_id(packets)
    source = load_read_attempt(attempt_id)
    if not source:
        raise ValueError(f"Saved OpenAI attempt not found: {attempt_id}")
    if str(source.get("evidence_snapshot_id") or "") != snapshot:
        raise ValueError("Saved OpenAI attempt targets a different evidence snapshot.")
    versions = dict(source.get("prompt_versions") or {})
    current = prompt_versions()
    if str(versions.get("language_layer_sha256") or "") != str(current.get("language_layer_sha256") or ""):
        raise ValueError("Saved OpenAI attempt uses a different language layer.")
    if str(source.get("model") or config.model) != config.model or str(source.get("reasoning_effort") or config.reasoning_effort) != config.reasoning_effort:
        raise ValueError("Saved OpenAI attempt uses a different model configuration.")

    plan = recovery_call_plan(source)
    attempt = _attempt_base(
        attempt_id=new_attempt_id(evidence_snapshot_id=snapshot),
        snapshot=snapshot,
        packets=packet_dicts,
        model_packets=model_packet_dicts,
        config=config,
    )
    source_output = dict(source.get("generated_output") or {})
    source_generation = dict(source.get("generation") or {})
    source_raw = dict(source.get("raw_responses") or {})
    attempt["generated_output"] = {key: source_output[key] for key in plan["reused_outputs"]}
    attempt["generation"] = {key: source_generation[key] for key in plan["reused_outputs"] if key in source_generation}
    attempt["raw_responses"] = {key: source_raw[key] for key in plan["reused_outputs"] if key in source_raw}
    attempt["recovery"] = {**plan, "source_attempt_preserved": True}
    attempt["resumed_at"] = datetime.now(timezone.utc).isoformat()
    _save_attempt(attempt, persist=persist)
    return _execute_two_call_pipeline(
        attempt=attempt,
        packet_dicts=packet_dicts,
        model_packet_dicts=model_packet_dicts,
        config=config,
        client=client,
        persist=persist,
    )


def regenerate_macro_read(
    context: DashboardContext,
    config: OpenAIConfig,
    *,
    client: Any | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Run one explicit Macro call using the complete published domain Reads."""
    packets = build_evidence_packets(context)
    packet_dicts = _packet_dicts(packets)
    model_packet_dicts = _model_packet_dicts(packets)
    snapshot = evidence_snapshot_id(packets)
    stored = load_read_artifact()
    if not _artifact_is_publishable(stored):
        raise ValueError("No compatible published commentary artifact is available.")
    if str(stored.get("evidence_snapshot_id") or "") != snapshot:
        raise ValueError("Published commentary targets a different evidence snapshot.")
    domain_set = _domain_models_from_public_reads(dict(stored.get("reads") or {}))
    attempt = _attempt_base(
        attempt_id=new_attempt_id(evidence_snapshot_id=snapshot),
        snapshot=snapshot,
        packets=packet_dicts,
        model_packets=model_packet_dicts,
        config=config,
    )
    attempt["mode"] = "macro_only"
    attempt["stage"] = "macro_read"
    attempt["source_artifact_attempt_id"] = str(stored.get("attempt_id") or "")

    macro_model, macro_raw = _call_stage(
        attempt,
        key="macro_read",
        call=lambda: generate_macro_read(model_packet_dicts, domain_set, config, client=client),
        persist=persist,
    )
    if macro_model is None and not macro_raw:
        return _generation_failure(attempt, stage="macro_read", persist=persist)

    domain_report = validate_domain_read_set(domain_set, packet_dicts).to_dict()
    macro_report = (
        validate_macro_read(macro_model, packet_dicts, domain_texts=_domain_texts_from_models(domain_set)).to_dict()
        if macro_model is not None
        else {}
    )
    raw_stage = "macro_read" if macro_model is None else ""
    validation = _validation_summary(domain_report, macro_report, raw_stage=raw_stage)
    reads = dict(stored.get("reads") or {})
    reads["macro"] = _macro_public_read(macro_model, packet_dicts) if macro_model is not None else _raw_public_read(macro_raw)
    status = "published_raw_response" if raw_stage else "validated" if validation["passed"] else "published_with_warnings"
    return _publish_artifact(
        attempt=attempt,
        reads=reads,
        validation=validation,
        config=config,
        status=status,
        source="macro_regeneration",
        persist=persist,
        base=stored,
    )
