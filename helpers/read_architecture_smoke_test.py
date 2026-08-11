"""Stop-the-line contract for the v7 evidence -> OpenAI -> validation architecture."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class _FakeStreamlit(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state = {}
        self.secrets = {}

    def cache_data(self, *args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda function: function


sys.modules.setdefault("streamlit", _FakeStreamlit())

from analytics.dashboard_context import DashboardContext  # noqa: E402
from analytics.read_evidence import DOMAIN_ORDER, EvidenceFact, EvidencePacket, evidence_snapshot_id, model_evidence_packets  # noqa: E402
from analytics.read_models import GeneratedDomainRead, GeneratedDomainReadSet, GeneratedMacroRead, SupportedSentence  # noqa: E402
from analytics.read_prompts import MACRO_PROMPT_VERSION, macro_read_input  # noqa: E402
import analytics.read_service as read_service  # noqa: E402
import analytics.read_store as read_store  # noqa: E402
from analytics.read_validation import validate_domain_read_set, validate_macro_read  # noqa: E402
from config.openai_config import OpenAIConfig  # noqa: E402
from rendering.read_markup import build_domain_read_html  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _packets() -> dict[str, EvidencePacket]:
    packets = {}
    for index, domain in enumerate(DOMAIN_ORDER, start=1):
        packets[domain] = EvidencePacket(
            domain=domain,
            label=domain.replace("_", " ").title(),
            facts=(EvidenceFact(
                id=f"{domain}.anchor",
                label=f"{domain.replace('_', ' ').title()} anchor",
                value=index,
                display=str(index),
                context="Retained test evidence",
            ),),
            importance=float(100 - index),
            boundaries=("Use only the supplied evidence.",),
            references=({"source_label": f"{domain} source", "source_url": f"https://example.com/{domain}"},),
            version="test",
        )
    return packets


def _sentence(text: str, *fact_ids: str, inference: str = "interpretation") -> SupportedSentence:
    return SupportedSentence(text=text, fact_ids=list(fact_ids), inference=inference)


def _domain_set() -> GeneratedDomainReadSet:
    return GeneratedDomainReadSet(reads=[
        GeneratedDomainRead(
            domain=domain,
            headline=_sentence(f"{domain.replace('_', ' ').title()} evidence is material.", f"{domain}.anchor"),
            analysis=[
                _sentence("The retained evidence establishes the current condition.", f"{domain}.anchor"),
                _sentence("Its significance comes from the constraint represented by the same evidence.", f"{domain}.anchor"),
                _sentence("That makes the domain evidence useful as an analytical signal rather than a standalone statistic.", f"{domain}.anchor"),
            ],
        )
        for domain in DOMAIN_ORDER
    ])


def _macro() -> GeneratedMacroRead:
    selected = ["market", "finance", "compute", "adoption", "economic_impact"]
    return GeneratedMacroRead(
        selected_domains=selected,
        headline=_sentence(
            "Investment capacity is outrunning realized diffusion and outcomes.",
            "finance.anchor", "compute.anchor", "adoption.anchor", "economic_impact.anchor",
        ),
        analysis=[
            _sentence(
                "Capital and compute evidence point to continued buildout capacity, but that supply-side momentum is only one part of the system.",
                "finance.anchor", "compute.anchor",
            ),
            _sentence(
                "Adoption evidence shows that deployment is progressing on a different track from the resources being committed upstream.",
                "compute.anchor", "adoption.anchor",
            ),
            _sentence(
                "Market evidence adds a financing and valuation backdrop without establishing that infrastructure spending has already translated into broad economic gains.",
                "market.anchor", "finance.anchor", "economic_impact.anchor",
            ),
            _sentence(
                "Taken together, the lifecycle is better described as a large buildout moving through uneven diffusion than as a completed productivity transformation.",
                "adoption.anchor", "economic_impact.anchor",
            ),
        ],
    )



class _FakeResponses:
    def __init__(self):
        self.calls = 0
        self.inputs = []

    def parse(self, **kwargs):
        self.calls += 1
        self.inputs.append(str(kwargs.get("input") or ""))
        parsed = _domain_set() if self.calls == 1 else _macro()
        return SimpleNamespace(
            id=f"resp_test_{self.calls}",
            output_parsed=parsed,
            usage=SimpleNamespace(input_tokens=100 * self.calls, output_tokens=20 * self.calls, total_tokens=120 * self.calls),
        )


class _FakeClient:
    def __init__(self):
        self.responses = _FakeResponses()


class _BadDomainResponses:
    def __init__(self):
        self.calls = 0

    def parse(self, **kwargs):
        self.calls += 1
        bad = _domain_set().model_copy(deep=True)
        bad.reads[0].analysis[0].text = "The retained value is 999."
        return SimpleNamespace(
            id="resp_bad_domain",
            output_parsed=bad,
            usage=SimpleNamespace(input_tokens=111, output_tokens=22, total_tokens=133),
        )


class _BadDomainClient:
    def __init__(self):
        self.responses = _BadDomainResponses()


class _MacroOnlyResponses:
    def __init__(self):
        self.calls = 0

    def parse(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(
            id="resp_resumed_macro",
            output_parsed=_macro(),
            usage=SimpleNamespace(input_tokens=77, output_tokens=18, total_tokens=95),
        )


class _MacroOnlyClient:
    def __init__(self):
        self.responses = _MacroOnlyResponses()


def main() -> None:
    packets = _packets()
    packet_dicts = {domain: packet.to_dict() for domain, packet in packets.items()}
    model_packet_dicts = model_evidence_packets(packets)
    require(len(DOMAIN_ORDER) == 11, "The v7 domain evidence order changed.")
    require("adoption" in DOMAIN_ORDER and "adaptation" not in DOMAIN_ORDER, "Historical adaptation domain naming survived the v7.0.2 adoption migration.")
    projected = EvidenceFact(
        id="market.percentage",
        label="Covered companies with positive one-year returns",
        value=0.681372549,
        display="68.1%",
        context="",
    ).to_model_dict()
    require(set(projected) == {"id", "label", "display"}, f"Model fact leaked raw/redundant fields: {projected}")
    require(projected["display"] == "68.1%", "Model fact did not preserve the canonical human-scale display.")
    model_blob = str(model_packet_dicts)
    require("source_url" not in model_blob and "https://" not in model_blob, "Source URLs leaked into the paid model evidence payload.")
    require(all("version" not in packet for packet in model_packet_dicts.values()), "Packet version leaked into the paid model evidence payload.")
    require(all("value" not in fact for packet in model_packet_dicts.values() for fact in packet.get("facts", [])), "Raw numeric values leaked into the paid model evidence payload.")
    require(evidence_snapshot_id(packets) == evidence_snapshot_id(packets), "Evidence snapshot hashing is not deterministic.")
    require(read_store.READ_ARTIFACT_PATH.parent.name == "openai_artifacts", "Validated commentary did not move to the permanent OpenAI artifact root.")
    require(read_store.READ_ATTEMPT_DIR.parent.name == "openai_artifacts", "Paid attempt history did not move to the permanent OpenAI artifact root.")
    require("generated_reads" not in str(read_store.READ_ARTIFACT_PATH), "Legacy data/generated_reads path survived the v7.0.2 cutover.")

    original_write_gate = read_store.repository_writes_enabled
    original_attempt_dir = read_store.READ_ATTEMPT_DIR
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            read_store.repository_writes_enabled = lambda: True
            read_store.READ_ATTEMPT_DIR = Path(temp_dir) / "openai_artifacts" / "attempts"
            attempt_id = read_store.persist_read_attempt({"status": "domain_generated", "evidence_snapshot_id": "abc123"})
            saved_path = read_store.attempt_path(attempt_id)
            require(saved_path.exists(), "Paid attempt persistence did not create its durable JSON artifact.")
            require("domain_generated" in saved_path.read_text(encoding="utf-8"), "Paid attempt artifact lost the generated stage payload.")
    finally:
        read_store.repository_writes_enabled = original_write_gate
        read_store.READ_ATTEMPT_DIR = original_attempt_dir

    domain_set = _domain_set()
    domain_validation = validate_domain_read_set(domain_set, packet_dicts)
    require(domain_validation.passed, f"Valid domain commentary failed validation: {domain_validation.errors}")

    reordered = GeneratedDomainReadSet(reads=list(reversed(_domain_set().reads)))
    reordered_validation = validate_domain_read_set(reordered, packet_dicts)
    require(reordered_validation.passed, "Domain output ordering is incorrectly treated as publication truth.")

    label_packets = _packets()
    label_packet_dicts = {domain: packet.to_dict() for domain, packet in label_packets.items()}
    label_packet_dicts["adoption"]["facts"][0]["label"] = "Adults age 18–64 reporting use"
    label_packet_dicts["connectivity"]["facts"][0]["label"] = "Population centers over 300k assessed"
    label_reads = _domain_set().model_copy(deep=True)
    for read in label_reads.reads:
        if read.domain == "adoption":
            read.analysis[0].text = "Use is measured among adults age 18–64."
        elif read.domain == "connectivity":
            read.analysis[0].text = "The screen covers population centers over 300,000."
    label_validation = validate_domain_read_set(label_reads, label_packet_dicts)
    require(label_validation.passed, f"Label-grounded or formatting-equivalent numbers were rejected: {label_validation.errors}")

    ratio_packets = _packets()
    ratio_dicts = {domain: packet.to_dict() for domain, packet in ratio_packets.items()}
    ratio_dicts["finance"]["facts"][0]["display"] = "1.46x"
    ratio_reads = _domain_set().model_copy(deep=True)
    finance_ratio = next(read for read in ratio_reads.reads if read.domain == "finance")
    finance_ratio.analysis[0].text = "Operating cash flow equals 1.46 times current capital expenditure."
    ratio_validation = validate_domain_read_set(ratio_reads, ratio_dicts)
    require(ratio_validation.passed, f"Ratio display expressed as natural-language times was rejected: {ratio_validation.errors}")

    question_reads = _domain_set().model_copy(deep=True)
    question_reads.reads[0].analysis[0].text = "What does the retained evidence mean?"
    question_validation = validate_domain_read_set(question_reads, packet_dicts)
    require(not question_validation.passed and any("interrogative" in error for error in question_validation.errors), "Actual interrogative analysis was not rejected.")

    signed_packets = _packets()
    signed_dicts = {domain: packet.to_dict() for domain, packet in signed_packets.items()}
    signed_dicts["economic_impact"]["facts"][0]["display"] = "-8.4%"
    signed_reads = _domain_set().model_copy(deep=True)
    economic = next(read for read in signed_reads.reads if read.domain == "economic_impact")
    economic.analysis[0].text = "The labor-share measure fell 8.4%."
    signed_validation = validate_domain_read_set(signed_reads, signed_dicts)
    require(signed_validation.passed, f"Negative fact expressed with directional prose was rejected: {signed_validation.errors}")

    contracting_reads = _domain_set().model_copy(deep=True)
    economic_contracting = next(read for read in contracting_reads.reads if read.domain == "economic_impact")
    economic_contracting.analysis[0].text = "The labor-share measure is contracting by 8.4%."
    contracting_validation = validate_domain_read_set(contracting_reads, signed_dicts)
    require(contracting_validation.passed, f"Negative fact expressed as contracting by its magnitude was rejected: {contracting_validation.errors}")

    wrong_direction_reads = _domain_set().model_copy(deep=True)
    economic_wrong = next(read for read in wrong_direction_reads.reads if read.domain == "economic_impact")
    economic_wrong.analysis[0].text = "The labor-share measure rose 8.4%."
    wrong_direction_validation = validate_domain_read_set(wrong_direction_reads, signed_dicts)
    require(not wrong_direction_validation.passed and any("unsupported numeric" in error for error in wrong_direction_validation.errors), "Negative evidence incorrectly licensed a positive-direction magnitude.")

    domain_texts = {
        read.domain: [read.headline.text, *[item.text for item in read.analysis]]
        for read in _domain_set().reads
    }
    macro_validation = validate_macro_read(_macro(), packet_dicts, domain_texts=domain_texts)
    require(macro_validation.passed, f"Valid macro commentary failed validation: {macro_validation.errors}")
    require(4 <= len(_macro().selected_domains) <= 6, "Macro synthesis is not broad enough to represent the platform lifecycle.")
    require(MACRO_PROMPT_VERSION == "macro-read-3.2", "Macro prompt version did not advance with the plain-language editorial contract.")
    macro_prompt = macro_read_input(model_packet_dicts, {
        domain: {"headline": f"{domain} thesis", "fact_ids_used": [f"{domain}.anchor"]}
        for domain in DOMAIN_ORDER
    })
    for phrase in (
        "smart non-specialist",
        "Simplify the language, not the analysis",
        "Do not define technical terms inside the Read",
        "95-125 words",
        "no more than two displayed quantities",
    ):
        require(phrase in macro_prompt, f"Macro prompt lost the plain-language reader contract: {phrase!r}")

    copied_macro = _macro().model_copy(deep=True)
    copied_macro.analysis[0].text = _domain_set().reads[0].analysis[0].text
    copied_macro.analysis[0].fact_ids = ["market.anchor"]
    copied_validation = validate_macro_read(copied_macro, packet_dicts, domain_texts=domain_texts)
    require(
        not copied_validation.passed and any("reuses domain Read language" in error for error in copied_validation.errors),
        "Macro validator did not reject copied domain prose.",
    )

    narrow_macro = _macro().model_copy(deep=True)
    narrow_macro.selected_domains = ["compute", "data_center", "connectivity", "power"]
    narrow_validation = validate_macro_read(narrow_macro, packet_dicts)
    require(
        not narrow_validation.passed and any("lifecycle stages" in error for error in narrow_validation.errors),
        "Macro validator allowed a broad-looking selection that covered only one lifecycle stage.",
    )

    bad = _domain_set().model_copy(deep=True)
    bad.reads[0].analysis[0].text = "The retained value is 999."
    bad_validation = validate_domain_read_set(bad, packet_dicts)
    require(not bad_validation.passed and any("unsupported numeric" in error for error in bad_validation.errors), "Unsupported numbers are not rejected.")
    require(any(item.get("sentence") and item.get("fact_ids") for item in bad_validation.failures), "Rejected claims do not expose sentence + fact IDs for diagnostics.")

    hidden_raw_packets = _packets()
    hidden_raw_dicts = {domain: packet.to_dict() for domain, packet in hidden_raw_packets.items()}
    hidden_raw_dicts["market"]["facts"][0]["value"] = 0.681
    hidden_raw_dicts["market"]["facts"][0]["display"] = "68.1%"
    hidden_raw_reads = _domain_set().model_copy(deep=True)
    hidden_raw_reads.reads[0].analysis[0].text = "The hidden raw ratio is 0.681."
    hidden_raw_validation = validate_domain_read_set(hidden_raw_reads, hidden_raw_dicts)
    require(not hidden_raw_validation.passed, "Validator accepted a numeric value that was hidden from the paid model prompt.")

    original_builder = read_service.build_evidence_packets
    original_attempt_loader = read_service.load_read_attempt
    original_artifact_loader = read_service.load_read_artifact
    original_attempt_writer = read_service.persist_read_attempt
    original_current_writer = read_service.persist_read_artifact
    saved_attempts = []
    published = []
    try:
        read_service.build_evidence_packets = lambda context: packets
        read_service.persist_read_attempt = lambda payload, attempt_id=None: saved_attempts.append(dict(payload)) or str(attempt_id or "test-attempt")
        read_service.persist_read_artifact = lambda payload: published.append(dict(payload))
        context = DashboardContext(current_context={
            "by_domain": {
                "market": {
                    "events": [{
                        "event_id": "test-market-event",
                        "verification_status": "primary",
                        "display": "A verified market development is available.",
                        "source_name": "Primary source",
                        "source_url": "https://example.com/current",
                    }],
                    "references": [{
                        "source_name": "Primary source",
                        "source_url": "https://example.com/current",
                    }],
                }
            }
        })
        missing_reads, missing_status = read_service.build_platform_reads(context, artifact={})
        require(missing_status["status"] == "missing", "Missing commentary artifact is not labeled missing.")
        require(len(missing_reads) == len(DOMAIN_ORDER) + 1, "Unavailable state does not cover every Read surface.")
        require(missing_reads["finance"]["headline"] == read_service.UNAVAILABLE_HEADLINE, "Unavailable headline drifted.")
        require(missing_reads["finance"]["analysis"] == read_service.UNAVAILABLE_ANALYSIS, "Unavailable copy drifted.")

        client = _FakeClient()
        artifact = read_service.generate_validated_read_artifact(
            context,
            OpenAIConfig(api_key="test", model="gpt-5.6-sol", reasoning_effort="medium"),
            client=client,
            persist=True,
        )
        require(client.responses.calls == 2, "v7 commentary generation must use one domain call and one macro call.")
        require(client.responses.inputs and "source_url" not in client.responses.inputs[0], "Service sent source URLs to the paid domain prompt.")
        require("domain_orientation" in client.responses.inputs[1], "Macro request did not receive the compact domain-orientation contract.")
        require(
            "The retained evidence establishes the current condition." not in client.responses.inputs[1],
            "Macro request still contains reusable domain analysis prose.",
        )
        require('"value"' not in client.responses.inputs[0], "Service sent raw deterministic values to the paid domain prompt.")
        require('"version"' not in client.responses.inputs[0], "Service sent packet version metadata to the paid domain prompt.")
        require(saved_attempts and saved_attempts[0].get("status") == "domain_generated", "Paid domain output was not persisted before validation.")
        require(saved_attempts[0].get("model_evidence_packets"), "Paid attempt did not preserve the exact compact evidence projection sent to the model.")
        require(any(item.get("status") == "macro_generated" for item in saved_attempts), "Paid Macro output was not persisted before Macro validation.")
        require(len(published) == 1, "Validated commentary was not promoted exactly once.")
        require(artifact.get("status") == "validated", f"Fake API artifact did not validate: {artifact}")
        macro_public = artifact["reads"]["macro"]
        require(len(macro_public.get("analysis_paragraphs") or []) == 2, "AI Macro is not published as two short paragraphs.")
        require(
            all(str(item).strip() for item in macro_public.get("analysis_paragraphs") or []),
            "AI Macro published an empty analytical paragraph.",
        )
        artifact_blob = str(artifact)
        require("watchpoint" not in artifact_blob, "Retired watchpoint field survived in the v7 public artifact.")
        require("'summary':" not in artifact_blob, "Retired commentary summary field survived in the v7 public artifact.")

        # Macro is a separately iterable synthesis layer: regenerating it must
        # preserve validated domain Reads and spend exactly one API call.
        saved_attempts.clear()
        published.clear()
        read_service.load_read_artifact = lambda: dict(artifact)
        macro_refresh_client = _MacroOnlyClient()
        refreshed = read_service.regenerate_macro_read(
            context,
            OpenAIConfig(api_key="test", model="gpt-5.6-sol", reasoning_effort="medium"),
            client=macro_refresh_client,
            persist=True,
        )
        require(macro_refresh_client.responses.calls == 1, "Macro-only regeneration spent more than one API call.")
        require(refreshed.get("status") == "validated", f"Macro-only regeneration did not validate: {refreshed}")
        require(
            refreshed["reads"]["market"]["analysis"] == artifact["reads"]["market"]["analysis"],
            "Macro-only regeneration rewrote a validated domain Read.",
        )
        require(len(published) == 1, "Macro-only validated artifact was not promoted exactly once.")
        require(len(refreshed["reads"]["macro"].get("analysis_paragraphs") or []) == 2, "Macro-only refresh did not preserve the two-paragraph Reader shape.")

        # Macro validation must prevent a single overloaded sentence from doing
        # the work of an entire platform overview.
        overloaded = _macro().model_copy(deep=True)
        overloaded.analysis[3].text = (
            "Taken together, the lifecycle is better described as a large buildout moving through uneven diffusion, "
            "with capital, compute, adoption, workforce, and economic outcomes all contributing separate signals that "
            "must be reconciled before the platform can describe the transformation as mature or broadly distributed."
        )
        overloaded.analysis[3].fact_ids = [
            "market.anchor", "finance.anchor", "compute.anchor", "adoption.anchor", "economic_impact.anchor"
        ]
        overloaded_result = validate_macro_read(overloaded, {domain: packet.to_dict() for domain, packet in packets.items()}, domain_texts={})
        require(not overloaded_result.passed, "Macro validator accepted an overloaded closing sentence spanning more than three domains.")

        saved_attempts.clear()
        published.clear()
        bad_client = _BadDomainClient()
        rejected = read_service.generate_validated_read_artifact(
            context,
            OpenAIConfig(api_key="test", model="gpt-5.6-sol", reasoning_effort="medium"),
            client=bad_client,
            persist=True,
        )
        require(bad_client.responses.calls == 1, "Domain validation failure incorrectly spent a Macro API call.")
        require(rejected.get("status") == "validation_failed" and rejected.get("stage") == "domain", "Rejected paid attempt did not fail closed at the domain gate.")
        require(saved_attempts and saved_attempts[0].get("status") == "domain_generated", "Rejected paid response was not saved before validation.")
        require(saved_attempts[-1].get("status") == "validation_failed", "Rejected paid attempt did not persist its validation result.")
        require(not published, "Rejected paid attempt was incorrectly promoted to current.json.")
        require((rejected.get("generated_output") or {}).get("domain"), "Rejected paid output is missing from the diagnostic result.")

        # A validator-only fix must be able to reuse the already-paid domain
        # response and spend only the missing Macro call.
        saved_attempts.clear()
        published.clear()
        resumable_attempt = {
            "attempt_id": "saved-domain-attempt",
            "status": "validation_failed",
            "stage": "domain",
            "evidence_snapshot_id": evidence_snapshot_id(packets),
            "model": "gpt-5.6-sol",
            "reasoning_effort": "medium",
            "prompt_versions": read_service.prompt_versions(),
            "generation": {"domain": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}},
            "generated_output": {"domain": _domain_set().model_dump(mode="json")},
            "validation": {},
        }
        read_service.load_read_attempt = lambda attempt_id: dict(resumable_attempt)
        macro_only_client = _MacroOnlyClient()
        resumed = read_service.resume_saved_read_attempt(
            context,
            OpenAIConfig(api_key="test", model="gpt-5.6-sol", reasoning_effort="medium"),
            "saved-domain-attempt",
            client=macro_only_client,
            persist=True,
        )
        require(macro_only_client.responses.calls == 1, "Resuming a saved domain response spent more than the missing Macro API call.")
        require(resumed.get("status") == "validated", f"Saved paid domain response did not resume cleanly: {resumed}")
        require(len(published) == 1, "Resumed validated attempt was not promoted exactly once.")

        # If both paid responses already exist, a validator-only recovery must
        # publish without touching the API at all.
        saved_attempts.clear()
        published.clear()
        complete_attempt = dict(resumable_attempt)
        complete_attempt["attempt_id"] = "saved-complete-attempt"
        complete_attempt["generated_output"] = {
            "domain": _domain_set().model_dump(mode="json"),
            "macro": _macro().model_dump(mode="json"),
        }
        complete_attempt["prompt_versions"] = read_service.prompt_versions()
        read_service.load_read_attempt = lambda attempt_id: dict(complete_attempt)

        class _NoCallResponses:
            def parse(self, **kwargs):
                raise AssertionError("Recovered complete attempt unexpectedly called OpenAI.")

        no_call_client = SimpleNamespace(responses=_NoCallResponses())
        recovered = read_service.resume_saved_read_attempt(
            context,
            OpenAIConfig(api_key="test", model="gpt-5.6-sol", reasoning_effort="medium"),
            "saved-complete-attempt",
            client=no_call_client,
            persist=True,
        )
        require(recovered.get("status") == "validated", f"Complete saved attempt was not revalidated and published: {recovered}")
        require(len(published) == 1, "Recovered complete attempt was not promoted exactly once.")

        # Restore the valid artifact for Reader publication checks below.
        published.append(dict(artifact))
        require((artifact.get("validation") or {}).get("passed") is True, "Validated artifact lost its publication gate.")

        reads, status = read_service.build_platform_reads(context, artifact=artifact)
        require(status["status"] == "validated", "Evidence-matched artifact was not accepted.")
        require(all(reads[domain].get("generator") == "openai" for domain in DOMAIN_ORDER), "A domain Read bypassed the OpenAI artifact.")
        require(reads["macro"].get("generator") == "openai", "Macro Read bypassed the OpenAI artifact.")
        market_markup = build_domain_read_html(reads["market"], label="Market Read", accent_color="#a78bfa")
        require("Recent developments" in market_markup, "Current Context was not attached after commentary publication.")
        require(">Watch<" not in market_markup and "watchpoint" not in market_markup.casefold(), "Retired Watch UI survived the commentary cutover.")

        incompatible = dict(artifact)
        incompatible["service_version"] = "1.3.0"
        incompatible_reads, incompatible_status = read_service.build_platform_reads(context, artifact=incompatible)
        require(incompatible_status["status"] == "stale", "Pre-analytical commentary artifact was not rejected as schema-incompatible.")
        require(incompatible_reads["market"]["generator"] == "unavailable", "Schema-incompatible commentary reached the Reader.")

        stale = dict(artifact)
        stale["evidence_snapshot_id"] = "stale-snapshot"
        stale_reads, stale_status = read_service.build_platform_reads(context, artifact=stale)
        require(stale_status["status"] == "stale", "Evidence-mismatched commentary is not rejected as stale.")
        require(stale_reads["market"]["generator"] == "unavailable", "Stale commentary reached the Reader.")
    finally:
        read_service.build_evidence_packets = original_builder
        read_service.load_read_attempt = original_attempt_loader
        read_service.load_read_artifact = original_artifact_loader
        read_service.persist_read_attempt = original_attempt_writer
        read_service.persist_read_artifact = original_current_writer

    app = (ROOT / "ai_macro.py").read_text(encoding="utf-8")
    require("analytics.read_architecture" not in app, "Application still imports the retired deterministic commentary engine.")
    require("Macro Interpretation" not in app, "Commentary still leaks into regime_metrics.")
    require(not (ROOT / "analytics" / "read_architecture.py").exists(), "Retired deterministic analytical Read engine returned to the source tree.")
    live_commentary_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for directory in (ROOT / "analytics", ROOT / "rendering")
        for path in directory.glob("*.py")
    )
    for retired_token in ("_fallback_read", "build_energy_read", "Sector read"):
        require(retired_token not in live_commentary_sources, f"Retired deterministic analytical commentary path survived: {retired_token}")

    print(
        "PASS  v7.0.8 plain-language Macro synthesis architecture · "
        f"{len(DOMAIN_ORDER)} evidence domains · 2 mocked API calls · durable paid-attempt gate"
    )


if __name__ == "__main__":
    main()
