"""Deterministic smoke test for the reset one-call editorial contract."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.read_briefing import STYLE_REFERENCE, build_editorial_briefing, editorial_refresh_plan  # noqa: E402
from analytics.read_generation import generate_editorial_synthesis, prompt_versions  # noqa: E402
from analytics.read_materiality import compare_evidence_materiality  # noqa: E402
from analytics.read_models import GeneratedEditorialSynthesis  # noqa: E402
from analytics.read_prompts import EDITORIAL_INSTRUCTIONS, editorial_synthesis_input  # noqa: E402
from analytics.read_validation import validate_editorial_synthesis  # noqa: E402
from config.openai_config import OpenAIConfig  # noqa: E402


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _model_payload() -> dict:
    return {
        "domain_reads": [{
            "domain": "market",
            "headline": {
                "text": "AI equities remain strong as participation broadens",
                "fact_ids": ["market.aei", "market.positive_breadth"],
                "event_ids": [],
            },
            "body": {
                "text": "The market signal strengthened as gains spread across more of the tracked companies. Sector pressure remains elevated enough that broader participation matters more than another move in a handful of names.",
                "fact_ids": ["market.aei", "market.positive_breadth", "market.pressure"],
                "event_ids": [],
            },
        }],
        "macro_read": {
            "headline": {
                "text": "Investment remains ahead of broad economic conversion",
                "fact_ids": ["finance.internal_funding_coverage", "economic_impact.productivity_growth"],
                "event_ids": [],
            },
            "paragraphs": [
                {
                    "text": "Corporate funding capacity remains supportive while power and compute investment continue to expand. That keeps the physical buildout moving even when individual market signals become less uniform.",
                    "fact_ids": ["finance.internal_funding_coverage", "power.planned_net_gw", "market.aei"],
                    "event_ids": [],
                },
                {
                    "text": "Business adoption and productivity are improving on a slower timetable than infrastructure investment. The current evidence therefore points to an economy still translating heavy capital spending into wider operating and labor-market effects.",
                    "fact_ids": ["adoption.current_business_use_pct", "economic_impact.productivity_growth", "economic_impact.real_compensation_growth"],
                    "event_ids": [],
                },
            ],
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


def _briefing(current: dict, materiality: dict, artifact: dict) -> dict:
    return build_editorial_briefing(
        current,
        current_context={
            "events": [{
                "event_id": "event-market-1",
                "event_date": "2026-09-14",
                "domain": "market",
                "display": "A major semiconductor company raised its revenue outlook after stronger AI demand.",
                "source_label": "Example Wire",
                "source_url": "https://example.com/story",
                "priority": 100,
            }],
            "by_domain": {},
        },
        materiality=materiality,
        prior_artifact=artifact,
        candidate_domains=["market"],
        bootstrap=False,
        new_event_ids=["event-market-1"],
    )


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
    _check(materiality["material"], "Material market movement was not detected")

    metadata_only = deepcopy(previous)
    metadata_only["market"]["references"] = [*(metadata_only["market"].get("references") or []), {"source_label": "Metadata only", "source_url": "https://example.com/metadata"}]
    metadata_materiality = compare_evidence_materiality(
        previous,
        metadata_only,
        previous_snapshot_id="previous",
        current_snapshot_id="metadata-only",
    )
    _check(not metadata_materiality["material"], "Reference metadata churn still triggers a paid editorial rewrite")
    _check(
        any(change.get("kind") == "evidence_metadata_changed" for change in metadata_materiality["changes"]),
        "Metadata-only evidence changes are no longer visible for audit",
    )

    plan = editorial_refresh_plan(
        materiality,
        current_context={
            "events": [{
                "event_id": "event-market-1",
                "event_date": "2026-09-14",
                "domain": "market",
                "display": "A major semiconductor company raised its revenue outlook after stronger AI demand.",
                "source_label": "Example Wire",
                "priority": 100,
            }],
            "by_domain": {},
        },
        prior_artifact={**artifact, "editorial_context_event_ids": []},
        bootstrap=False,
    )
    _check(plan["refresh_needed"], "Material findings and new developments did not trigger an editorial attempt")
    _check(plan["candidate_domains"] == ["market"], "Editorial candidate-domain plan changed")

    no_change_plan = editorial_refresh_plan(
        {"material": False, "changes": []},
        current_context={
            "events": [],
            "by_domain": {
                "market": {
                    "events": [{
                        "event_id": "no-context-market-2026-09-14",
                        "event_date": "2026-09-14",
                        "domain": "market",
                        "event_type": "context_status",
                        "verification_status": "no_match",
                        "display": "No material market development met the evidence threshold.",
                        "priority": 0,
                    }]
                }
            },
        },
        prior_artifact=artifact,
        bootstrap=False,
    )
    _check(not no_change_plan["refresh_needed"], "No-context fallback rows incorrectly trigger a paid editorial attempt")

    briefing = _briefing(current, materiality, artifact)
    _check(briefing["style_reference"] == STYLE_REFERENCE, "Owner style reference changed")
    _check(briefing["candidate_domains"] == ["market"], "Candidate-domain briefing changed")
    _check(briefing["recent_developments"], "Qualified recent developments were omitted from the writing briefing")
    prompt = editorial_synthesis_input(briefing=briefing)
    _check(len(prompt) < 24000, "Reset writing briefing is unexpectedly large")
    _check("editorial_constitution" not in prompt, "Legacy editorial constitution leaked into the reset prompt")
    _check("analytical_state" not in prompt, "Legacy analytical-state homework leaked into the reset prompt")
    _check("retain_prior" not in prompt, "Publication-decision homework leaked into the writing prompt")
    _check("prioritize significance over coverage" in EDITORIAL_INSTRUCTIONS.casefold(), "Simple editorial objective is missing")

    synthesis = GeneratedEditorialSynthesis.model_validate(_model_payload())
    validation = validate_editorial_synthesis(
        synthesis,
        current,
        briefing=briefing,
        candidate_domains=["market"],
    )
    _check(validation["passed"], f"Grounded reset synthesis failed: {validation['hard_errors']}")

    selective = deepcopy(_model_payload())
    selective["domain_reads"] = []
    selective_validation = validate_editorial_synthesis(
        GeneratedEditorialSynthesis.model_validate(selective),
        current,
        briefing=briefing,
        candidate_domains=["market"],
    )
    _check(selective_validation["passed"], "Normal updates still force the model to manufacture candidate-domain prose")

    weird = deepcopy(_model_payload())
    weird["domain_reads"][0]["body"]["text"] = "Capital capacity conditions continue constraining corporate choices."
    weird_validation = validate_editorial_synthesis(
        GeneratedEditorialSynthesis.model_validate(weird),
        current,
        briefing=briefing,
        candidate_domains=["market"],
    )
    _check(weird_validation["passed"], "Style diagnostic incorrectly became a hard publication rule")
    _check(any(item.get("reason") == "alliterative_run" for item in weird_validation["diagnostics"]), "Known alliteration pathology was not observable as a diagnostic")

    bad = deepcopy(_model_payload())
    bad["domain_reads"][0]["body"]["text"] += " Revenue reached 999 billion."
    bad_validation = validate_editorial_synthesis(
        GeneratedEditorialSynthesis.model_validate(bad),
        current,
        briefing=briefing,
        candidate_domains=["market"],
    )
    _check(not bad_validation["passed"], "Invented displayed number passed the factual gate")

    client = _Client(synthesis)
    parsed, metadata = generate_editorial_synthesis(
        briefing=briefing,
        config=OpenAIConfig(api_key="test"),
        client=client,
    )
    _check(parsed.domain_reads[0].domain == "market", "Structured result was not returned")
    _check(client.responses.calls == 1, "Editorial generation issued more than one API call")
    _check(client.responses.kwargs.get("background") is True, "Background mode was not retained")
    _check(metadata.total_tokens == 300, "Generation usage metadata changed")
    _check(set(prompt_versions()) == {"editorial", "generator", "briefing"}, "Legacy prompt-version dependencies remain active")

    print(json.dumps({
        "status": "PASS",
        "api_calls": client.responses.calls,
        "candidate_domains": briefing["candidate_domains"],
        "recent_developments": len(briefing["recent_developments"]),
        "hard_validation_errors": len(validation["hard_errors"]),
        "style_diagnostics_are_nonblocking": True,
        "prompt_chars": len(prompt),
    }, indent=2))


if __name__ == "__main__":
    main()
