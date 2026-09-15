"""Build the compact research briefing used for one-call editorial synthesis.

Deterministic code owns measurement, source qualification, arithmetic, change
tracking, and provenance.  The model receives a concise briefing of finished
findings, qualified recent developments, and the last published prose for
continuity.  It is asked to write, not to operate the publication system.
"""

from __future__ import annotations

from typing import Any

from analytics.read_evidence import DOMAIN_LABELS, DOMAIN_ORDER

BRIEFING_VERSION = "1.1.0"
MAX_FACTS_PER_DOMAIN = 4
MAX_RECENT_DEVELOPMENTS = 15

STYLE_REFERENCE = (
    "AI Macro is a research platform that examines the development of the U.S. AI economy from capital investment "
    "and physical construction through deployment, adoption, and economic results. It uses publicly available data "
    "to relate corporate and market activity to the physical systems required to support the buildout. It evaluates "
    "the extent to which that investment produces durable economic value and how its effects are transmitted through "
    "the broader U.S. economy."
)


def _change_index(materiality: dict[str, Any]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for change in materiality.get("changes", []) or []:
        if not isinstance(change, dict):
            continue
        fact_id = str(change.get("fact_id") or "").strip()
        if fact_id:
            output[fact_id] = dict(change)
    return output


def _change_description(change: dict[str, Any] | None) -> str:
    if not change:
        return ""
    kind = str(change.get("kind") or "")
    if kind == "fact_added":
        return "newly available"
    if kind == "fact_removed":
        return "no longer available"
    if kind == "categorical_change":
        return "changed"
    if kind == "numeric_change":
        try:
            old = float(change.get("old_value"))
            new = float(change.get("new_value"))
        except (TypeError, ValueError):
            return "changed materially" if change.get("material") else "changed slightly"
        if new > old:
            return "increased materially" if change.get("material") else "increased slightly"
        if new < old:
            return "decreased materially" if change.get("material") else "decreased slightly"
        return "little changed"
    return "changed materially" if change.get("material") else "changed"


def _fact_rows(
    packet: dict[str, Any],
    *,
    changes: dict[str, dict[str, Any]],
    limit: int = MAX_FACTS_PER_DOMAIN,
) -> list[dict[str, Any]]:
    facts = [dict(item) for item in packet.get("facts", []) or [] if isinstance(item, dict) and item.get("id")]
    changed_ids = {fact_id for fact_id in changes if fact_id.startswith(f"{packet.get('domain')}.")}
    changed = [fact for fact in facts if str(fact.get("id")) in changed_ids]
    unchanged = [fact for fact in facts if str(fact.get("id")) not in changed_ids]
    ordered = [*changed, *unchanged]
    selected: list[dict[str, Any]] = []
    for fact in ordered:
        fact_id = str(fact.get("id") or "")
        row = {
            "fact_id": fact_id,
            "finding": f"{str(fact.get('label') or fact_id)}: {str(fact.get('display') or 'n/a')}",
        }
        context = str(fact.get("context") or "").strip()
        if context:
            row["context"] = context
        movement = _change_description(changes.get(fact_id))
        if movement:
            row["change"] = movement
        selected.append(row)
        if len(selected) >= max(1, int(limit)):
            break
    return selected


def recent_development_rows(current_context: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return the highest-priority qualified developments available to the writer."""
    payload = dict(current_context or {})
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(event: Any, *, fallback_domain: str = "") -> None:
        if not isinstance(event, dict):
            return
        verification = str(event.get("verification_status") or event.get("status") or "").strip().casefold()
        if verification in {"no_match", "no qualifying event"} or str(event.get("event_type") or "").strip().casefold() == "context_status":
            return
        event_id = str(event.get("event_id") or "").strip()
        if not event_id or event_id in seen:
            return
        text = str(event.get("display") or event.get("verified_fact") or "").strip()
        if not text:
            return
        seen.add(event_id)
        candidates.append({
            "event_id": event_id,
            "domain": str(event.get("owner_domain") or event.get("domain") or fallback_domain).strip(),
            "date": str(event.get("event_date") or "").strip(),
            "development": text,
            "source": str(event.get("source_label") or event.get("source_name") or "").strip(),
            "priority": float(event.get("priority", 0) or 0),
        })

    for event in payload.get("events", []) or []:
        add(event)
    for domain, domain_payload in (payload.get("by_domain") or {}).items():
        if not isinstance(domain_payload, dict):
            continue
        for event in domain_payload.get("events", []) or []:
            add(event, fallback_domain=str(domain))

    candidates.sort(key=lambda item: (item["priority"], item["date"]), reverse=True)
    return candidates[:MAX_RECENT_DEVELOPMENTS]


def materially_changed_domains(materiality: dict[str, Any]) -> list[str]:
    """Return domains with material fact changes, ignoring metadata-only churn."""
    domains: set[str] = set()
    for change in materiality.get("changes", []) or []:
        if not isinstance(change, dict) or not change.get("material"):
            continue
        fact_id = str(change.get("fact_id") or "").strip()
        if not fact_id:
            continue
        domain = str(change.get("domain") or fact_id.split(".", 1)[0]).strip()
        if domain in DOMAIN_ORDER:
            domains.add(domain)
    return [domain for domain in DOMAIN_ORDER if domain in domains]


def editorial_refresh_plan(
    materiality: dict[str, Any],
    *,
    current_context: dict[str, Any] | None,
    prior_artifact: dict[str, Any] | None,
    bootstrap: bool,
) -> dict[str, Any]:
    """Decide whether fresh evidence merits one editorial attempt.

    A successful publication records the recent event IDs that were available to
    that call.  Rejected drafts never update that record, so the same unresolved
    evidence remains eligible for a later authorized attempt.
    """
    if bootstrap:
        return {
            "refresh_needed": True,
            "candidate_domains": list(DOMAIN_ORDER),
            "material_domains": list(DOMAIN_ORDER),
            "new_event_domains": [],
            "new_event_ids": [],
            "current_event_ids": [row["event_id"] for row in recent_development_rows(current_context)],
            "reason": "bootstrap",
        }

    prior = dict(prior_artifact or {})
    events = recent_development_rows(current_context)
    current_event_ids = [str(row.get("event_id") or "") for row in events if row.get("event_id")]
    previously_considered = {
        str(event_id)
        for event_id in prior.get("editorial_context_event_ids", []) or []
        if str(event_id).strip()
    }
    new_events = [row for row in events if str(row.get("event_id") or "") not in previously_considered]
    event_domains = {
        str(row.get("domain") or "").strip()
        for row in new_events
        if str(row.get("domain") or "").strip() in DOMAIN_ORDER
    }
    material_domains = materially_changed_domains(materiality)
    candidates = [
        domain for domain in DOMAIN_ORDER
        if domain in set(material_domains) | event_domains
    ]
    reasons: list[str] = []
    if material_domains:
        reasons.append("material_findings")
    if new_events:
        reasons.append("new_developments")
    return {
        "refresh_needed": bool(material_domains or new_events),
        "candidate_domains": candidates,
        "material_domains": material_domains,
        "new_event_domains": [domain for domain in DOMAIN_ORDER if domain in event_domains],
        "new_event_ids": [str(row.get("event_id") or "") for row in new_events],
        "current_event_ids": current_event_ids,
        "reason": "+".join(reasons) if reasons else "no_material_editorial_change",
    }


def _prior_read(prior_artifact: dict[str, Any], domain: str) -> dict[str, str]:
    read = dict((prior_artifact.get("reads") or {}).get(domain) or {})
    if not read:
        return {}
    return {
        "headline": str(read.get("headline") or ""),
        "body": str(read.get("analysis") or ""),
    }


def build_editorial_briefing(
    packets: dict[str, dict[str, Any]],
    *,
    current_context: dict[str, Any] | None,
    materiality: dict[str, Any],
    prior_artifact: dict[str, Any] | None,
    candidate_domains: list[str],
    bootstrap: bool,
    new_event_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Return the concise model-facing research packet for one editorial call."""
    prior = dict(prior_artifact or {})
    changes = _change_index(materiality)
    candidates = [domain for domain in DOMAIN_ORDER if domain in set(candidate_domains)]
    findings: list[dict[str, Any]] = []
    for domain in DOMAIN_ORDER:
        packet = dict(packets.get(domain) or {})
        if not packet:
            continue
        findings.append({
            "domain": domain,
            "label": str(packet.get("label") or DOMAIN_LABELS.get(domain, domain.replace("_", " ").title())),
            "update_candidate": domain in candidates,
            "facts": _fact_rows(packet, changes=changes),
        })

    prior_domains = list(DOMAIN_ORDER) if bootstrap else candidates
    prior_reads = {
        domain: _prior_read(prior, domain)
        for domain in [*prior_domains, "macro"]
        if _prior_read(prior, domain)
    }
    new_ids = {str(event_id) for event_id in (new_event_ids or []) if str(event_id).strip()}
    developments = recent_development_rows(current_context)
    for event in developments:
        event["new_since_prior_publication"] = str(event.get("event_id") or "") in new_ids

    return {
        "briefing_version": BRIEFING_VERSION,
        "assignment": (
            "Write the first published AI Macro Read from the briefing."
            if bootstrap
            else "Write a current AI Macro update from the briefing. Update only domain Reads that materially improve on the prior publication."
        ),
        "candidate_domains": candidates,
        "style_reference": STYLE_REFERENCE,
        "findings": findings,
        "recent_developments": developments,
        "prior_publication": prior_reads,
    }


def briefing_fact_ids(briefing: dict[str, Any]) -> set[str]:
    return {
        str(fact.get("fact_id") or "")
        for domain in briefing.get("findings", []) or []
        if isinstance(domain, dict)
        for fact in domain.get("facts", []) or []
        if isinstance(fact, dict) and fact.get("fact_id")
    }


def briefing_event_ids(briefing: dict[str, Any]) -> set[str]:
    return {
        str(event.get("event_id") or "")
        for event in briefing.get("recent_developments", []) or []
        if isinstance(event, dict) and event.get("event_id")
    }


__all__ = [
    "BRIEFING_VERSION",
    "STYLE_REFERENCE",
    "briefing_event_ids",
    "briefing_fact_ids",
    "build_editorial_briefing",
    "editorial_refresh_plan",
    "materially_changed_domains",
    "recent_development_rows",
]
