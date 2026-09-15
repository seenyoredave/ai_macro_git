"""Verify last-good fallback and retry semantics for the reset editorial service."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import analytics.read_service as service  # noqa: E402
from analytics.read_models import GeneratedEditorialSynthesis  # noqa: E402
from automation.runner import _publication_phase  # noqa: E402
from config.openai_config import OpenAIConfig  # noqa: E402
from helpers.editorial_pipeline_smoke_test import _Client, _model_payload  # noqa: E402


class _Packet:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def to_dict(self) -> dict:
        return deepcopy(self.payload)


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _run(
    model: GeneratedEditorialSynthesis,
    prior: dict,
    materiality: dict,
    *,
    packet_payload: dict | None = None,
    current_context: dict | None = None,
    force_preview: bool = False,
) -> dict:
    packet_payload = packet_payload or prior["evidence_packets"]
    packets = {domain: _Packet(packet) for domain, packet in packet_payload.items()}
    context = service.DashboardContext(current_context=current_context or {
        "events": [],
        "by_domain": {},
    })
    with (
        patch.object(service, "build_evidence_packets", return_value=packets),
        patch.object(service, "evidence_snapshot_id", return_value="service-smoke-snapshot"),
        patch.object(service, "load_read_artifact", return_value=deepcopy(prior)),
    ):
        return service.generate_validated_read_artifact(
            context,
            OpenAIConfig(api_key="test"),
            client=_Client(model),
            persist=False,
            materiality=materiality,
            force_preview=force_preview,
        )


def main() -> None:
    prior = json.loads((ROOT / "openai_artifacts" / "current.json").read_text(encoding="utf-8"))
    current = deepcopy(prior["evidence_packets"])
    market = next(fact for fact in current["market"]["facts"] if fact["id"] == "market.aei")
    market["value"] = float(market["value"]) + 3.6
    market["display"] = f"{market['value']:.1f}"
    materiality = {
        "version": "smoke",
        "previous_snapshot_id": str(prior.get("evidence_snapshot_id") or ""),
        "current_snapshot_id": "service-smoke-snapshot",
        "baseline_available": True,
        "exact_match": False,
        "material": True,
        "decision": "generate_material_change",
        "change_count": 1,
        "material_change_count": 1,
        "changes": [{
            "kind": "numeric_change",
            "fact_id": "market.aei",
            "domain": "market",
            "old_value": float(market["value"]) - 3.6,
            "new_value": float(market["value"]),
            "relative_change": 0.08,
            "percentage_point_change": 3.6,
            "material": True,
        }],
    }

    publish_model = GeneratedEditorialSynthesis.model_validate(_model_payload())
    published = _run(publish_model, prior, materiality, packet_payload=current)
    _check(published["status"] in service.PUBLISHABLE_STATUSES, "Grounded publication candidate was not publishable")
    _check(published["service_version"] == service.READ_SERVICE_VERSION, "Service version did not advance")
    _check(set(published["reads"]) == {*service.DOMAIN_ORDER, "macro"}, "Incremental merge lost a Read")
    _check(
        published["reads"]["market"]["evidence_snapshot_id"] == "service-smoke-snapshot",
        "Updated domain did not receive the new evidence identity",
    )
    _check(
        published["reads"]["finance"]["headline"] == prior["reads"]["finance"]["headline"],
        "Unchanged domain prose was regenerated",
    )

    rejected_payload = deepcopy(_model_payload())
    rejected_payload["domain_reads"][0]["body"]["fact_ids"] = ["market.not_supplied"]
    rejected = _run(GeneratedEditorialSynthesis.model_validate(rejected_payload), prior, materiality, packet_payload=current)
    _check(rejected["status"] == "rejected_hard_validation", "Unknown support ID did not trigger the minimal gate")
    _check("published_artifact" not in rejected, "Rejected draft leaked into publication output")

    # The same material gap can be attempted again on a later authorized run.
    retried = _run(publish_model, prior, materiality, packet_payload=current)
    _check(retried["status"] in service.PUBLISHABLE_STATUSES, "A prior rejection suppressed a later valid attempt")

    context_only_materiality = {
        "version": "smoke",
        "previous_snapshot_id": str(prior.get("evidence_snapshot_id") or ""),
        "current_snapshot_id": str(prior.get("evidence_snapshot_id") or ""),
        "baseline_available": True,
        "exact_match": True,
        "material": False,
        "decision": "reuse_exact_evidence",
        "changes": [],
    }
    context_prior = deepcopy(prior)
    context_prior["editorial_context_event_ids"] = ["event-old"]
    context_event = {
        "events": [{
            "event_id": "event-market-new",
            "event_date": "2026-09-14",
            "domain": "market",
            "display": "A major chip supplier raised its revenue outlook after stronger AI demand.",
            "source_label": "Example Wire",
            "source_url": "https://example.com/new",
            "priority": 100,
        }],
        "by_domain": {},
    }
    context_only = _run(
        publish_model,
        context_prior,
        context_only_materiality,
        packet_payload=prior["evidence_packets"],
        current_context=context_event,
    )
    _check(context_only["status"] in service.PUBLISHABLE_STATUSES, "A new qualified development did not trigger an editorial attempt")
    _check("event-market-new" in context_only.get("editorial_context_event_ids", []), "Published artifact did not record developments considered by the call")

    preview_materiality = {
        "version": "smoke",
        "previous_snapshot_id": str(prior.get("evidence_snapshot_id") or ""),
        "current_snapshot_id": str(prior.get("evidence_snapshot_id") or ""),
        "baseline_available": True,
        "exact_match": True,
        "material": False,
        "decision": "reuse_exact_evidence",
        "changes": [],
    }
    preview = _run(
        publish_model,
        prior,
        preview_materiality,
        packet_payload=prior["evidence_packets"],
        force_preview=True,
    )
    _check(preview["status"] in service.PUBLISHABLE_STATUSES, "Owner preview did not force one fresh synthesis")
    _check((preview.get("editorial_refresh_plan") or {}).get("reason") == "owner_preview", "Owner preview reason was not preserved")

    rejected_phase, rejected_result = _publication_phase({"status": "rejected_hard_validation"})
    _check(
        rejected_phase["status"] == "ready_with_editorial_rejection"
        and rejected_phase["read_status"] == "last_good_read_retained_after_rejection"
        and rejected_result == "publish_ready_with_editorial_fallback",
        "Rejected editorial output was not treated as last-good fallback",
    )

    print(json.dumps({
        "status": "PASS",
        "publish_status": published["status"],
        "reject_status": rejected["status"],
        "retry_status": retried["status"],
        "rejected_publication_status": rejected_phase["status"],
        "context_only_refresh_status": context_only["status"],
        "preview_status": preview["status"],
        "read_count": len(published["reads"]),
    }, indent=2))


if __name__ == "__main__":
    main()
