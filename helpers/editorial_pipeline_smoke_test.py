"""Deterministic smoke test for the one-call editorial synthesis contract."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.language_layer import editorial_constitution_payload  # noqa: E402
from analytics.read_capsules import build_signal_capsules  # noqa: E402
from analytics.read_generation import generate_editorial_synthesis  # noqa: E402
from analytics.read_materiality import compare_evidence_materiality  # noqa: E402
from analytics.read_models import GeneratedEditorialSynthesis  # noqa: E402
from analytics.read_prompts import editorial_synthesis_input  # noqa: E402
from analytics.read_validation import validate_editorial_synthesis  # noqa: E402
from config.openai_config import OpenAIConfig  # noqa: E402


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _model_payload() -> dict:
    return {
        "decision": "publish",
        "decision_reason": "Market composition changed enough to alter the system interpretation.",
        "updated_domains": ["market"],
        "domain_reads": [{
            "domain": "market",
            "headline": {
                "text": "Participation broadens inside a concentrated market",
                "fact_ids": ["market.positive_breadth", "market.top_10_share"],
                "inference": "interpretation",
            },
            "analysis": [
                {
                    "text": "Positive returns extend across the covered company set.",
                    "fact_ids": ["market.positive_breadth"],
                    "inference": "observation",
                },
                {
                    "text": "The equity index strengthens as participation broadens beyond the largest firms.",
                    "fact_ids": ["market.aei", "market.positive_breadth"],
                    "inference": "interpretation",
                },
                {
                    "text": "The largest companies still dominate covered market value.",
                    "fact_ids": ["market.top_10_share"],
                    "inference": "interpretation",
                },
            ],
        }],
        "macro_read": {
            "selected_domains": ["market", "power", "adoption", "economic_impact"],
            "headline": {
                "text": "Broader capital participation still faces a narrow conversion path",
                "fact_ids": ["market.positive_breadth", "adoption.current_business_use_pct"],
                "inference": "interpretation",
            },
            "paragraphs": [
                {"sentences": [
                    {
                        "text": "Broader equity participation supports financing capacity, while planned generation remains distinct from delivered power.",
                        "fact_ids": ["market.positive_breadth", "power.planned_net_gw"],
                        "inference": "interpretation",
                    },
                    {
                        "text": "That separation keeps physical delivery central to the investment thesis.",
                        "fact_ids": ["power.planned_net_gw"],
                        "inference": "interpretation",
                    },
                ]},
                {"sentences": [
                    {
                        "text": "Available power can expand service capacity without establishing broad business use.",
                        "fact_ids": ["power.large_load_capacity_mw", "adoption.current_business_use_pct"],
                        "inference": "interpretation",
                    },
                    {
                        "text": "Current business use therefore remains the nearer test of diffusion.",
                        "fact_ids": ["adoption.current_business_use_pct"],
                        "inference": "interpretation",
                    },
                ]},
                {"sentences": [
                    {
                        "text": "Business use and aggregate productivity can rise together without proving that one caused the other.",
                        "fact_ids": ["adoption.current_business_use_pct", "economic_impact.productivity_growth"],
                        "inference": "interpretation",
                    },
                    {
                        "text": "Conversion strengthens only when diffusion and realized outcomes become jointly observable.",
                        "fact_ids": ["adoption.current_business_use_pct", "economic_impact.productivity_growth"],
                        "inference": "interpretation",
                    },
                ]},
            ],
        },
        "analytical_state": {
            "thesis": "Capital participation broadened, but physical delivery and business diffusion still govern conversion.",
            "selected_domains": ["market", "power", "adoption", "economic_impact"],
            "changed_since_prior": ["Market participation broadened."],
            "unresolved_tensions": ["Planned supply is not delivered power."],
            "confirming_signals": ["Broader business use with stronger productivity would support conversion."],
            "disconfirming_signals": ["Narrowing breadth would weaken the capital signal."],
        },
    }


class _Response:
    def __init__(self, parsed: GeneratedEditorialSynthesis) -> None:
        self.id = "resp_editorial_smoke"
        self.status = "completed"
        self.model = "gpt-5.6"
        self.output_parsed = parsed
        self.output_text = parsed.model_dump_json()
        self.usage = {"input_tokens": 100, "output_tokens": 200, "total_tokens": 300}

    def model_dump(self, **kwargs):
        return {
            "id": self.id,
            "status": self.status,
            "model": self.model,
            "output_text": self.output_text,
        }


class _Responses:
    def __init__(self, parsed: GeneratedEditorialSynthesis) -> None:
        self.parsed = parsed
        self.calls = 0
        self.kwargs = {}

    def parse(self, **kwargs):
        self.calls += 1
        self.kwargs = dict(kwargs)
        return _Response(self.parsed)

    def retrieve(self, response_id: str, **kwargs):
        raise AssertionError("A completed response must not be polled")


class _Client:
    def __init__(self, parsed: GeneratedEditorialSynthesis) -> None:
        self.responses = _Responses(parsed)


def main() -> None:
    artifact = json.loads((ROOT / "openai_artifacts" / "current.json").read_text(encoding="utf-8"))
    previous = artifact["evidence_packets"]
    current = deepcopy(previous)
    aei = next(fact for fact in current["market"]["facts"] if fact["id"] == "market.aei")
    aei["value"] = float(aei["value"]) + 3.6
    aei["display"] = f"{float(aei['value']):.1f}"
    materiality = compare_evidence_materiality(
        previous,
        current,
        previous_snapshot_id=str(artifact.get("evidence_snapshot_id") or ""),
        current_snapshot_id="editorial-smoke",
    )
    _check(materiality["material"], "A 3.6-point AEI move did not reach the point-scale materiality gate")
    capsules = build_signal_capsules(
        current,
        snapshot_id="editorial-smoke",
        materiality=materiality,
        prior_artifact=artifact,
        observed_at="2026-08-19T20:00:00+00:00",
    )
    facts_sent = sum(len(capsule["facts"]) for capsule in capsules["capsules"])
    _check(11 <= len(capsules["capsules"]) <= 15, "Capsule count escaped the 11-15 contract")
    _check(30 <= facts_sent <= 60, "Capsule fact count is not compact")
    market = next(capsule for capsule in capsules["capsules"] if capsule["capsule_id"] == "market.core")
    _check(market["role"] == "material_change", "Market capsule did not preserve material change status")
    _check(len(market["facts"][0]["trajectory"]) == 2, "Prior/current trajectory was not retained")

    prompt = editorial_synthesis_input(
        capsules=capsules,
        editorial_constitution=editorial_constitution_payload(),
        prior_publication={},
        prior_analytical_state={},
        required_update_domains=[],
        candidate_update_domains=["market"],
        bootstrap=False,
    )
    _check(len(prompt) < 30000, "Representative one-call prompt exceeded 30,000 characters")
    _check("architecture_library" not in prompt, "Complete legacy language layer leaked into the runtime prompt")

    synthesis = GeneratedEditorialSynthesis.model_validate(_model_payload())
    allowed = {
        str(fact["fact_id"])
        for capsule in capsules["capsules"]
        for fact in capsule["facts"]
    }
    validation = validate_editorial_synthesis(
        synthesis,
        current,
        candidate_update_domains=["market"],
        allowed_fact_ids=allowed,
    )
    _check(validation["passed"], f"Grounded synthesis failed: {validation['hard_errors']}")

    client = _Client(synthesis)
    parsed, metadata = generate_editorial_synthesis(
        capsules=capsules,
        prior_publication={},
        prior_analytical_state={},
        required_update_domains=[],
        candidate_update_domains=["market"],
        bootstrap=False,
        config=OpenAIConfig(api_key="test", max_output_tokens=12000),
        client=client,
    )
    _check(parsed.decision == "publish", "Structured result was not returned")
    _check(client.responses.calls == 1, "Editorial generation issued more than one API call")
    _check(client.responses.kwargs.get("background") is True, "Background mode was not retained")
    _check(client.responses.kwargs.get("max_output_tokens") == 12000, "Output ceiling was not applied")
    _check(metadata.total_tokens == 300, "Generation usage metadata changed")

    retain = GeneratedEditorialSynthesis.model_validate({
        "decision": "retain_prior",
        "decision_reason": "The movement does not change the interpretation.",
        "updated_domains": [],
        "domain_reads": [],
        "macro_read": None,
        "analytical_state": _model_payload()["analytical_state"],
    })
    _check(
        validate_editorial_synthesis(retain, current, candidate_update_domains=["market"])["passed"],
        "Valid retain-prior response was rejected",
    )
    _check(
        not validate_editorial_synthesis(
            retain,
            current,
            required_update_domains=["market"],
            candidate_update_domains=["market"],
        )["passed"],
        "Retain-prior response preserved a domain with stale cited facts",
    )
    print(json.dumps({
        "status": "PASS",
        "api_calls": client.responses.calls,
        "capsules": len(capsules["capsules"]),
        "facts_sent": facts_sent,
        "prompt_chars": len(prompt),
        "hard_validation_errors": len(validation["hard_errors"]),
    }, indent=2))


if __name__ == "__main__":
    main()
