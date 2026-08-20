"""Exercise publish, retain, and hard-rejection branches without network or writes."""

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
    evaluated_state: dict | None = None,
) -> dict:
    packet_payload = packet_payload or prior["evidence_packets"]
    packets = {
        domain: _Packet(packet)
        for domain, packet in packet_payload.items()
    }
    with (
        patch.object(service, "build_evidence_packets", return_value=packets),
        patch.object(service, "evidence_snapshot_id", return_value="service-smoke-snapshot"),
        patch.object(service, "load_read_artifact", return_value=deepcopy(prior)),
        patch.object(service, "load_evaluated_state", return_value=deepcopy(evaluated_state or {})),
    ):
        return service.generate_validated_read_artifact(
            service.DashboardContext(),
            OpenAIConfig(api_key="test"),
            client=_Client(model),
            persist=False,
            materiality=materiality,
        )


def main() -> None:
    prior = json.loads((ROOT / "openai_artifacts" / "current.json").read_text(encoding="utf-8"))
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
            "old_value": 41.2,
            "new_value": 44.8,
            "relative_change": 0.0874,
            "percentage_point_change": 3.6,
            "material": True,
        }],
    }

    publish_model = GeneratedEditorialSynthesis.model_validate(_model_payload())
    published = _run(publish_model, prior, materiality)
    _check(published["status"] in service.PUBLISHABLE_STATUSES, "Grounded publish result was not publishable")
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

    retain_payload = {
        "decision": "retain_prior",
        "decision_reason": "The evidence moved without changing the material interpretation.",
        "updated_domains": [],
        "domain_reads": [],
        "macro_read": None,
        "analytical_state": _model_payload()["analytical_state"],
    }
    retained = _run(GeneratedEditorialSynthesis.model_validate(retain_payload), prior, materiality)
    _check(retained["status"] == "retained_prior", "Valid abstention did not retain prior prose")
    _check(
        retained["publication"]["materiality"]["model_decision"] == "retain_prior",
        "Abstention decision was not recorded in publication metadata",
    )

    rejected_payload = _model_payload()
    rejected_payload["domain_reads"][0]["headline"]["fact_ids"] = ["market.not_in_capsules"]
    rejected = _run(GeneratedEditorialSynthesis.model_validate(rejected_payload), prior, materiality)
    _check(rejected["status"] == "rejected_hard_validation", "Unsupplied fact did not trigger the hard gate")
    _check(prior["reads"]["market"]["headline"] != "Participation broadens inside a concentrated market", "Test fixture mutated prior publication")

    # A rejected evaluation advances the paid-call baseline, but it must not
    # erase the gap between last-good published prose and current facts.  On a
    # later material call in another domain, retaining stale cited prose is a
    # hard failure rather than a silent publication leak.
    rejected_packets = deepcopy(prior["evidence_packets"])
    current_packets = deepcopy(rejected_packets)
    for fact in rejected_packets["market"]["facts"]:
        if fact["id"] == "market.positive_breadth":
            fact["value"] = float(fact["value"]) + 5.0
            fact["display"] = f"{fact['value']:.1f}%"
    current_packets = deepcopy(rejected_packets)
    for fact in current_packets["finance"]["facts"]:
        if fact["id"] == "finance.internal_funding_coverage":
            fact["value"] = float(fact["value"]) + 0.5
            fact["display"] = f"{fact['value']:.2f}x"
    later_materiality = {
        **materiality,
        "previous_snapshot_id": "rejected-evaluation-snapshot",
        "changes": [{
            "kind": "numeric_change",
            "fact_id": "finance.internal_funding_coverage",
            "domain": "finance",
            "old_value": 1.0,
            "new_value": 1.5,
            "relative_change": 0.5,
            "percentage_point_change": None,
            "material": True,
        }],
    }
    stale_retain = _run(
        GeneratedEditorialSynthesis.model_validate(retain_payload),
        prior,
        later_materiality,
        packet_payload=current_packets,
        evaluated_state={
            "status": "rejected_hard_validation",
            "evidence_snapshot_id": "rejected-evaluation-snapshot",
            "evidence_packets": rejected_packets,
            "prompt_versions": service.prompt_versions(),
        },
    )
    _check(
        stale_retain["status"] == "rejected_hard_validation",
        "A later call was allowed to retain prose made stale by an earlier rejected evaluation",
    )

    print(json.dumps({
        "status": "PASS",
        "publish_status": published["status"],
        "retain_status": retained["status"],
        "reject_status": rejected["status"],
        "stale_retain_status": stale_retain["status"],
        "read_count": len(published["reads"]),
    }, indent=2))


if __name__ == "__main__":
    main()
