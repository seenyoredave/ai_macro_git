"""v7 commentary orchestration: evidence -> OpenAI -> validation -> publication."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from analytics.dashboard_context import DashboardContext
from analytics.read_context import attach_current_context
from analytics.read_evidence import DOMAIN_LABELS, DOMAIN_ORDER, EvidencePacket, build_evidence_packets, evidence_fact_index, evidence_snapshot_id, model_evidence_packets
from analytics.read_generation import generate_domain_reads, generate_macro_read, prompt_versions
from analytics.read_models import GeneratedDomainReadSet, GeneratedMacroRead
from analytics.read_store import load_read_artifact, load_read_attempt, new_attempt_id, persist_read_artifact, persist_read_attempt
from analytics.read_validation import VALIDATOR_VERSION, validate_domain_read_set, validate_macro_read
from config.openai_config import OpenAIConfig

READ_SERVICE_VERSION = "2.1.0"
UNAVAILABLE_HEADLINE = "Commentary temporarily unavailable."
UNAVAILABLE_ANALYSIS = "The analyst has wandered off. The data have not."
MAX_MACRO_REFERENCES = 6


def _packet_dicts(packets: dict[str, EvidencePacket]) -> dict[str, dict]:
    return {domain: packet.to_dict() for domain, packet in packets.items()}


def _model_packet_dicts(packets: dict[str, EvidencePacket]) -> dict[str, dict]:
    return model_evidence_packets(packets)


def _claim_rows(read_model) -> list[dict[str, Any]]:
    rows = [{"field": "headline", **read_model.headline.model_dump()}]
    rows.extend({"field": f"analysis[{index}]", **item.model_dump()} for index, item in enumerate(read_model.analysis))
    return rows


def _domain_public_read(read_model, packet: dict) -> dict[str, Any]:
    return {
        "domain": read_model.domain,
        "label": DOMAIN_LABELS[read_model.domain],
        "headline": read_model.headline.text.strip(),
        "analysis": " ".join(item.text.strip() for item in read_model.analysis if item.text.strip()),
        "references": [dict(item) for item in packet.get("references", []) or []],
        "claim_support": _claim_rows(read_model),
        "generator": "openai",
        "version": READ_SERVICE_VERSION,
    }


def _macro_public_read(read_model, packets: dict[str, dict]) -> dict[str, Any]:
    selected = list(read_model.selected_domains)
    references: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add_reference(reference: dict[str, Any]) -> None:
        key = (str(reference.get("source_label") or ""), str(reference.get("source_url") or ""))
        if not key[0] or key in seen or len(references) >= MAX_MACRO_REFERENCES:
            return
        seen.add(key)
        references.append(dict(reference))

    # Preserve cross-domain provenance: every selected domain contributes a
    # source before any one domain can fill the remaining reference slots.
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
    analysis_sentences = [item.text.strip() for item in read_model.analysis if item.text.strip()]
    analysis_paragraphs = [
        " ".join(analysis_sentences[:2]).strip(),
        " ".join(analysis_sentences[2:4]).strip(),
    ]
    analysis_paragraphs = [item for item in analysis_paragraphs if item]
    return {
        "domain": "macro",
        "label": DOMAIN_LABELS["macro"],
        "headline": read_model.headline.text.strip(),
        "analysis": " ".join(analysis_sentences),
        "analysis_paragraphs": analysis_paragraphs,
        "selected_domains": selected,
        "references": references,
        "claim_support": _claim_rows(read_model),
        "evidence": evidence,
        "generator": "openai",
        "version": READ_SERVICE_VERSION,
    }


def _unavailable_read(domain: str, packet: dict) -> dict[str, Any]:
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


def build_platform_reads(context: DashboardContext, *, artifact: dict | None = None) -> tuple[dict[str, dict], dict[str, Any]]:
    """Load only a validated artifact matching the current analytical evidence."""
    packets = build_evidence_packets(context)
    packet_dicts = _packet_dicts(packets)
    snapshot = evidence_snapshot_id(packets)
    stored = dict(artifact if artifact is not None else load_read_artifact())
    valid_artifact = (
        bool(stored)
        and str(stored.get("evidence_snapshot_id") or "") == snapshot
        and bool((stored.get("validation") or {}).get("passed"))
        and str(stored.get("service_version") or "") == READ_SERVICE_VERSION
        and isinstance(stored.get("reads"), dict)
    )
    if valid_artifact:
        reads = {domain: dict((stored.get("reads") or {}).get(domain) or _unavailable_read(domain, packet_dicts[domain])) for domain in DOMAIN_ORDER}
        reads["macro"] = dict((stored.get("reads") or {}).get("macro") or _unavailable_read("macro", {}))
        status = {
            "status": "validated",
            "artifact_present": True,
            "evidence_snapshot_id": snapshot,
            "artifact_evidence_snapshot_id": stored.get("evidence_snapshot_id", ""),
            "generated_at": stored.get("generated_at", ""),
            "model": stored.get("model", ""),
            "prompt_versions": stored.get("prompt_versions", {}),
            "validation": stored.get("validation", {}),
            "generation": stored.get("generation", {}),
        }
    else:
        reads = {domain: _unavailable_read(domain, packet_dicts[domain]) for domain in DOMAIN_ORDER}
        reads["macro"] = _unavailable_read("macro", {})
        status = {
            "status": "stale" if stored else "missing",
            "artifact_present": bool(stored),
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
        reads[domain] = attach_current_context(reads[domain], by_domain.get(domain, {}))
    # Macro gets the top verified event across the complete Current Context packet.
    macro_context = context.current_context or {}
    reads["macro"] = attach_current_context(reads["macro"], macro_context)
    status["packets"] = packet_dicts
    return reads, status


def _attempt_base(*, attempt_id: str, snapshot: str, packets: dict[str, dict], model_packets: dict[str, dict], config: OpenAIConfig) -> dict[str, Any]:
    return {
        "attempt_id": attempt_id,
        "status": "started",
        "stage": "domain",
        "evidence_snapshot_id": snapshot,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "model": config.model,
        "reasoning_effort": config.reasoning_effort,
        "prompt_versions": prompt_versions(),
        "evidence_packets": packets,
        "model_evidence_packets": model_packets,
        "generation": {},
        "generated_output": {},
        "validation": {},
        "service_version": READ_SERVICE_VERSION,
    }


def _save_attempt(attempt: dict[str, Any], *, persist: bool) -> None:
    if persist:
        persist_read_attempt(attempt, attempt_id=str(attempt.get("attempt_id") or ""))


def _domain_orientation_for_macro(domain_set: GeneratedDomainReadSet) -> dict[str, dict[str, Any]]:
    """Expose domain conclusions to Macro without exposing reusable prose paragraphs."""
    orientation: dict[str, dict[str, Any]] = {}
    for read in domain_set.reads:
        fact_ids: list[str] = []
        for sentence in [read.headline, *read.analysis]:
            for fact_id in sentence.fact_ids:
                if fact_id not in fact_ids:
                    fact_ids.append(fact_id)
        orientation[read.domain] = {
            "headline": read.headline.text.strip(),
            "fact_ids_used": fact_ids,
        }
    return orientation


def _domain_texts_from_models(domain_set: GeneratedDomainReadSet) -> dict[str, list[str]]:
    return {
        read.domain: [read.headline.text, *[item.text for item in read.analysis]]
        for read in domain_set.reads
    }


def _domain_orientation_from_public_reads(reads: dict[str, Any]) -> dict[str, dict[str, Any]]:
    orientation: dict[str, dict[str, Any]] = {}
    for domain in DOMAIN_ORDER:
        read = dict(reads.get(domain) or {})
        headline = str(read.get("headline") or "").strip()
        fact_ids: list[str] = []
        for claim in read.get("claim_support") or []:
            if not isinstance(claim, dict):
                continue
            for fact_id in claim.get("fact_ids") or []:
                fact_id = str(fact_id)
                if fact_id and fact_id not in fact_ids:
                    fact_ids.append(fact_id)
        if not headline or not fact_ids:
            raise ValueError(f"Published {domain} Read lacks grounded orientation data for Macro regeneration.")
        orientation[domain] = {"headline": headline, "fact_ids_used": fact_ids}
    return orientation


def _domain_texts_from_public_reads(reads: dict[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for domain in DOMAIN_ORDER:
        read = dict(reads.get(domain) or {})
        texts: list[str] = []
        headline = str(read.get("headline") or "").strip()
        if headline:
            texts.append(headline)
        for claim in read.get("claim_support") or []:
            if isinstance(claim, dict):
                text = str(claim.get("text") or "").strip()
                if text and text not in texts:
                    texts.append(text)
        result[domain] = texts
    return result


def _publish_validated_attempt(
    *,
    attempt: dict[str, Any],
    domain_set: GeneratedDomainReadSet,
    macro_model: GeneratedMacroRead,
    domain_validation,
    macro_validation,
    packet_dicts: dict[str, dict],
    config: OpenAIConfig,
    persist: bool,
) -> dict[str, Any]:
    domain_models = {read.domain: read for read in domain_set.reads}
    reads = {domain: _domain_public_read(domain_models[domain], packet_dicts[domain]) for domain in DOMAIN_ORDER}
    reads["macro"] = _macro_public_read(macro_model, packet_dicts)
    validation = {
        "passed": True,
        "validator_version": VALIDATOR_VERSION,
        "domain": domain_validation.to_dict(),
        "macro": macro_validation.to_dict(),
        "checked_claims": domain_validation.checked_claims + macro_validation.checked_claims,
        "grounded_claims": domain_validation.grounded_claims + macro_validation.grounded_claims,
    }
    artifact = {
        "status": "validated",
        "attempt_id": str(attempt.get("attempt_id") or ""),
        "evidence_snapshot_id": str(attempt.get("evidence_snapshot_id") or ""),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": config.model,
        "reasoning_effort": config.reasoning_effort,
        "prompt_versions": attempt.get("prompt_versions") or prompt_versions(),
        "validation": validation,
        "generation": dict(attempt.get("generation") or {}),
        "reads": reads,
        "service_version": READ_SERVICE_VERSION,
    }

    attempt["status"] = "validated_unpublished"
    attempt["stage"] = "publication"
    attempt["validation"] = validation
    attempt["validated_artifact"] = artifact
    attempt["finished_at"] = datetime.now(timezone.utc).isoformat()
    _save_attempt(attempt, persist=persist)
    if persist:
        persist_read_artifact(artifact)
        attempt["status"] = "validated_published"
        attempt["published_at"] = datetime.now(timezone.utc).isoformat()
        _save_attempt(attempt, persist=True)
    return artifact


def _finish_after_domain_validation(
    *,
    attempt: dict[str, Any],
    domain_set: GeneratedDomainReadSet,
    domain_validation,
    packet_dicts: dict[str, dict],
    model_packet_dicts: dict[str, dict],
    config: OpenAIConfig,
    client: Any | None,
    persist: bool,
) -> dict[str, Any]:
    current_versions = prompt_versions()
    saved_macro = ((attempt.get("generated_output") or {}).get("macro"))
    saved_macro_version = str((attempt.get("prompt_versions") or {}).get("macro") or "")
    if saved_macro and saved_macro_version == current_versions["macro"]:
        macro_model = GeneratedMacroRead.model_validate(saved_macro)
    else:
        macro_model, macro_meta = generate_macro_read(
            model_packet_dicts,
            _domain_orientation_for_macro(domain_set),
            config,
            client=client,
        )
        attempt["status"] = "macro_generated"
        attempt["stage"] = "macro_validation"
        versions = dict(attempt.get("prompt_versions") or {})
        versions["macro"] = current_versions["macro"]
        versions["generator"] = current_versions["generator"]
        attempt["prompt_versions"] = versions
        generation = dict(attempt.get("generation") or {})
        generation["macro"] = macro_meta.to_dict()
        attempt["generation"] = generation
        generated = dict(attempt.get("generated_output") or {})
        generated["macro"] = macro_model.model_dump(mode="json")
        attempt["generated_output"] = generated
        # The paid Macro response is durable before validation.
        _save_attempt(attempt, persist=persist)

    macro_validation = validate_macro_read(macro_model, packet_dicts, domain_texts=_domain_texts_from_models(domain_set))
    attempt["validation"] = {
        "domain": domain_validation.to_dict(),
        "macro": macro_validation.to_dict(),
    }
    if not macro_validation.passed:
        attempt["status"] = "validation_failed"
        attempt["stage"] = "macro"
        attempt["finished_at"] = datetime.now(timezone.utc).isoformat()
        _save_attempt(attempt, persist=persist)
        return {
            "status": "validation_failed",
            "stage": "macro",
            "attempt_id": str(attempt.get("attempt_id") or ""),
            "evidence_snapshot_id": str(attempt.get("evidence_snapshot_id") or ""),
            "validation": {
                "passed": False,
                "domain": domain_validation.to_dict(),
                "macro": macro_validation.to_dict(),
            },
            "generation": dict(attempt.get("generation") or {}),
            "generated_output": dict(attempt.get("generated_output") or {}),
        }

    return _publish_validated_attempt(
        attempt=attempt,
        domain_set=domain_set,
        macro_model=macro_model,
        domain_validation=domain_validation,
        macro_validation=macro_validation,
        packet_dicts=packet_dicts,
        config=config,
        persist=persist,
    )


def generate_validated_read_artifact(context: DashboardContext, config: OpenAIConfig, *, client: Any | None = None, persist: bool = True) -> dict[str, Any]:
    """Generate, preserve, validate, and optionally publish one commentary attempt."""
    packets = build_evidence_packets(context)
    packet_dicts = _packet_dicts(packets)
    model_packet_dicts = _model_packet_dicts(packets)
    snapshot = evidence_snapshot_id(packets)
    attempt_id = new_attempt_id(evidence_snapshot_id=snapshot)
    attempt = _attempt_base(
        attempt_id=attempt_id,
        snapshot=snapshot,
        packets=packet_dicts,
        model_packets=model_packet_dicts,
        config=config,
    )

    domain_set, domain_meta = generate_domain_reads(model_packet_dicts, config, client=client)
    attempt["status"] = "domain_generated"
    attempt["stage"] = "domain_validation"
    attempt["generation"] = {"domain": domain_meta.to_dict()}
    attempt["generated_output"] = {"domain": domain_set.model_dump(mode="json")}
    # Durability boundary: the paid domain response is on disk before validation.
    _save_attempt(attempt, persist=persist)

    domain_validation = validate_domain_read_set(domain_set, packet_dicts)
    attempt["validation"] = {"domain": domain_validation.to_dict()}
    if not domain_validation.passed:
        attempt["status"] = "validation_failed"
        attempt["stage"] = "domain"
        attempt["finished_at"] = datetime.now(timezone.utc).isoformat()
        _save_attempt(attempt, persist=persist)
        return {
            "status": "validation_failed",
            "stage": "domain",
            "attempt_id": attempt_id,
            "evidence_snapshot_id": snapshot,
            "validation": domain_validation.to_dict(),
            "generation": {"domain": domain_meta.to_dict()},
            "generated_output": {"domain": domain_set.model_dump(mode="json")},
        }

    return _finish_after_domain_validation(
        attempt=attempt,
        domain_set=domain_set,
        domain_validation=domain_validation,
        packet_dicts=packet_dicts,
        model_packet_dicts=model_packet_dicts,
        config=config,
        client=client,
        persist=persist,
    )


def resume_saved_read_attempt(
    context: DashboardContext,
    config: OpenAIConfig,
    attempt_id: str,
    *,
    client: Any | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Revalidate preserved paid output and continue only from the missing stage.

    A domain-only failed attempt spends at most one new API call (Macro).  An
    attempt that already contains both paid responses can be revalidated and
    published without another API call.  Replay is refused when the current
    evidence snapshot differs from the snapshot that produced the saved output.
    """
    packets = build_evidence_packets(context)
    packet_dicts = _packet_dicts(packets)
    model_packet_dicts = _model_packet_dicts(packets)
    snapshot = evidence_snapshot_id(packets)
    attempt = load_read_attempt(attempt_id)
    if not attempt:
        raise ValueError(f"Saved OpenAI attempt not found: {attempt_id}")
    if str(attempt.get("evidence_snapshot_id") or "") != snapshot:
        raise ValueError("Saved OpenAI attempt targets a different evidence snapshot and cannot be resumed.")
    if str(attempt.get("model") or config.model) != config.model:
        raise ValueError("Saved OpenAI attempt was generated with a different model and cannot be mixed with the current model configuration.")
    if str(attempt.get("reasoning_effort") or config.reasoning_effort) != config.reasoning_effort:
        raise ValueError("Saved OpenAI attempt used a different reasoning effort and cannot be mixed with the current model configuration.")
    current_versions = prompt_versions()
    saved_domain_version = str((attempt.get("prompt_versions") or {}).get("domain") or "")
    if saved_domain_version != current_versions["domain"]:
        raise ValueError("Saved OpenAI attempt uses an incompatible domain commentary schema and cannot be resumed under the current prompt version.")

    domain_payload = ((attempt.get("generated_output") or {}).get("domain"))
    if not domain_payload:
        raise ValueError("Saved OpenAI attempt does not contain a domain response to revalidate.")
    domain_set = GeneratedDomainReadSet.model_validate(domain_payload)
    domain_validation = validate_domain_read_set(domain_set, packet_dicts)
    attempt["resumed_at"] = datetime.now(timezone.utc).isoformat()
    attempt["resumed_validator_version"] = VALIDATOR_VERSION
    attempt["validation"] = {"domain": domain_validation.to_dict()}
    if not domain_validation.passed:
        attempt["status"] = "validation_failed"
        attempt["stage"] = "domain"
        _save_attempt(attempt, persist=persist)
        return {
            "status": "validation_failed",
            "stage": "domain",
            "attempt_id": str(attempt.get("attempt_id") or attempt_id),
            "evidence_snapshot_id": snapshot,
            "validation": domain_validation.to_dict(),
            "generation": dict(attempt.get("generation") or {}),
            "generated_output": {"domain": domain_set.model_dump(mode="json")},
            "resumed": True,
        }

    return _finish_after_domain_validation(
        attempt=attempt,
        domain_set=domain_set,
        domain_validation=domain_validation,
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
    """Regenerate only AI Macro from the current validated domain Reads.

    This is the cost-aware editorial iteration path: validated domain commentary
    remains unchanged, while Macro is independently regenerated from current
    evidence plus compact domain orientation.  Exactly one paid API call is made.
    """
    packets = build_evidence_packets(context)
    packet_dicts = _packet_dicts(packets)
    model_packet_dicts = _model_packet_dicts(packets)
    snapshot = evidence_snapshot_id(packets)
    stored = load_read_artifact()
    if not stored:
        raise ValueError("No validated commentary artifact is available for Macro-only regeneration.")
    if str(stored.get("evidence_snapshot_id") or "") != snapshot:
        raise ValueError("Published commentary targets a different evidence snapshot; regenerate all commentary instead.")
    validation = dict(stored.get("validation") or {})
    domain_validation = dict(validation.get("domain") or {})
    if not domain_validation.get("passed"):
        raise ValueError("Published domain Reads do not carry a passing domain validation record.")
    reads = dict(stored.get("reads") or {})
    if any(not isinstance(reads.get(domain), dict) for domain in DOMAIN_ORDER):
        raise ValueError("Published artifact is missing one or more domain Reads required for Macro synthesis.")

    orientation = _domain_orientation_from_public_reads(reads)
    domain_texts = _domain_texts_from_public_reads(reads)
    attempt_id = new_attempt_id(evidence_snapshot_id=snapshot)
    versions = dict(stored.get("prompt_versions") or {})
    current_versions = prompt_versions()
    versions["macro"] = current_versions["macro"]
    versions["generator"] = current_versions["generator"]

    macro_model, macro_meta = generate_macro_read(model_packet_dicts, orientation, config, client=client)
    attempt: dict[str, Any] = {
        "attempt_id": attempt_id,
        "status": "macro_generated",
        "stage": "macro_validation",
        "mode": "macro_only",
        "evidence_snapshot_id": snapshot,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "model": config.model,
        "reasoning_effort": config.reasoning_effort,
        "prompt_versions": versions,
        "evidence_packets": packet_dicts,
        "model_evidence_packets": model_packet_dicts,
        "domain_orientation": orientation,
        "source_artifact_attempt_id": str(stored.get("attempt_id") or ""),
        "generation": {"macro": macro_meta.to_dict()},
        "generated_output": {"macro": macro_model.model_dump(mode="json")},
        "validation": {},
        "service_version": READ_SERVICE_VERSION,
    }
    # Preserve the paid Macro response before validating it.
    _save_attempt(attempt, persist=persist)

    macro_validation = validate_macro_read(macro_model, packet_dicts, domain_texts=domain_texts)
    attempt["validation"] = {"domain": domain_validation, "macro": macro_validation.to_dict()}
    if not macro_validation.passed:
        attempt["status"] = "validation_failed"
        attempt["stage"] = "macro"
        attempt["finished_at"] = datetime.now(timezone.utc).isoformat()
        _save_attempt(attempt, persist=persist)
        return {
            "status": "validation_failed",
            "stage": "macro",
            "attempt_id": attempt_id,
            "evidence_snapshot_id": snapshot,
            "validation": {
                "passed": False,
                "domain": domain_validation,
                "macro": macro_validation.to_dict(),
            },
            "generation": {"macro": macro_meta.to_dict()},
            "generated_output": {"macro": macro_model.model_dump(mode="json")},
            "mode": "macro_only",
        }

    updated_reads = dict(reads)
    updated_reads["macro"] = _macro_public_read(macro_model, packet_dicts)
    combined_validation = {
        "passed": True,
        "validator_version": VALIDATOR_VERSION,
        "domain": domain_validation,
        "macro": macro_validation.to_dict(),
        "checked_claims": int(domain_validation.get("checked_claims", 0) or 0) + macro_validation.checked_claims,
        "grounded_claims": int(domain_validation.get("grounded_claims", 0) or 0) + macro_validation.grounded_claims,
    }
    generation = dict(stored.get("generation") or {})
    generation["macro"] = macro_meta.to_dict()
    artifact = dict(stored)
    artifact.update({
        "status": "validated",
        "attempt_id": attempt_id,
        "evidence_snapshot_id": snapshot,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": config.model,
        "reasoning_effort": config.reasoning_effort,
        "prompt_versions": versions,
        "validation": combined_validation,
        "generation": generation,
        "reads": updated_reads,
        "service_version": READ_SERVICE_VERSION,
        "macro_refreshed_from_attempt_id": str(stored.get("attempt_id") or ""),
    })

    attempt["status"] = "validated_unpublished"
    attempt["stage"] = "publication"
    attempt["validation"] = combined_validation
    attempt["validated_artifact"] = artifact
    attempt["finished_at"] = datetime.now(timezone.utc).isoformat()
    _save_attempt(attempt, persist=persist)
    if persist:
        persist_read_artifact(artifact)
        attempt["status"] = "validated_published"
        attempt["published_at"] = datetime.now(timezone.utc).isoformat()
        _save_attempt(attempt, persist=True)
    return artifact
