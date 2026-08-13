"""Stop-the-line contract for the two-call OpenAI language-layer pipeline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import types
import warnings

from pydantic import BaseModel

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
from analytics.language_layer import language_layer_identity, language_layer_payload  # noqa: E402
from analytics.read_evidence import DOMAIN_ORDER, EvidenceFact, EvidencePacket, evidence_snapshot_id, model_evidence_packets  # noqa: E402
from analytics.read_models import GeneratedDomainRead, GeneratedDomainReadSet, GeneratedMacroParagraph, GeneratedMacroRead, SupportedSentence  # noqa: E402
from analytics.read_prompts import domain_read_input, macro_read_input  # noqa: E402
import analytics.read_service as read_service  # noqa: E402
import analytics.read_generation as read_generation  # noqa: E402
import analytics.read_validation as read_validation  # noqa: E402
import analytics.read_store as read_store  # noqa: E402
import analytics.reader_snapshot as reader_snapshot  # noqa: E402
from config.openai_config import OpenAIConfig  # noqa: E402
from rendering.read_markup import build_domain_read_html  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _packets() -> dict[str, EvidencePacket]:
    return {
        domain: EvidencePacket(
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
        for index, domain in enumerate(DOMAIN_ORDER, start=1)
    }


def _sentence(text: str, *fact_ids: str) -> SupportedSentence:
    return SupportedSentence(text=text, fact_ids=list(fact_ids), inference="interpretation")


def _domain_set(*, invalid_number: bool = False) -> GeneratedDomainReadSet:
    reads = []
    for domain in DOMAIN_ORDER:
        first = "The retained evidence identifies the domain's main constraint."
        if invalid_number and domain == "market":
            first = "The retained value is 999."
        reads.append(GeneratedDomainRead(
            domain=domain,
            headline=_sentence(f"{domain.replace('_', ' ').title()} evidence defines the current position", f"{domain}.anchor"),
            analysis=[
                _sentence(first, f"{domain}.anchor"),
                _sentence("That constraint shapes how capacity can move into practical use.", f"{domain}.anchor"),
                _sentence("The same evidence locates this domain within the wider system.", f"{domain}.anchor"),
            ],
        ))
    return GeneratedDomainReadSet(reads=reads)


def _macro() -> GeneratedMacroRead:
    return GeneratedMacroRead(
        selected_domains=["market", "finance", "compute", "adoption", "economic_impact"],
        headline=_sentence(
            "Investment is moving faster than useful capacity and broad economic gains",
            "finance.anchor", "compute.anchor", "adoption.anchor", "economic_impact.anchor",
        ),
        paragraphs=[
            GeneratedMacroParagraph(sentences=[
                _sentence("Companies are funding new infrastructure, and market pricing shows that investors still assign substantial value to the wider buildout.", "market.anchor", "finance.anchor"),
                _sentence("That financial support matters because computing systems cannot expand until manufacturers turn planned investment into equipment that customers can actually deploy.", "finance.anchor", "compute.anchor"),
                _sentence("The evidence starts with available capital, but the economic story depends on what later stages do with the resulting capacity.", "finance.anchor", "compute.anchor"),
            ]),
            GeneratedMacroParagraph(sentences=[
                _sentence("Manufacturers are increasing output across the supply chain, which gives businesses more hardware options than they had during earlier shortages.", "compute.anchor"),
                _sentence("More equipment does not create value by itself because organizations must connect it to data, workflows, and decisions throughout their operations.", "compute.anchor", "adoption.anchor"),
                _sentence("Routine use is the bridge between delivered systems and the improvements that managers, workers, and customers can observe in practice.", "adoption.anchor", "economic_impact.anchor"),
            ]),
            GeneratedMacroParagraph(sentences=[
                _sentence("Adoption remains uneven, so current business surveys describe a transition that has started without reaching most firms at the same depth.", "adoption.anchor"),
                _sentence("Until regular use becomes broader, aggregate productivity measures cannot isolate how much of their movement comes from artificial intelligence.", "adoption.anchor", "economic_impact.anchor"),
                _sentence("The present evidence supports continued investment and expanding capability, while leaving the economy-wide payoff as an outcome that still must be demonstrated.", "market.anchor", "economic_impact.anchor"),
            ]),
        ],
    )


class _Responses:
    def __init__(self, *, invalid_domain: bool = False, raw_domain: bool = False, raw_macro: bool = False):
        self.calls = 0
        self.inputs: list[str] = []
        self.invalid_domain = invalid_domain
        self.raw_domain = raw_domain
        self.raw_macro = raw_macro

    def parse(self, **kwargs):
        self.calls += 1
        self.inputs.append(str(kwargs.get("input") or ""))
        format_name = getattr(kwargs.get("text_format"), "__name__", "")
        if format_name == "GeneratedDomainReadSet" and self.raw_domain:
            parsed = None
            output_text = "Raw Domain response from OpenAI."
        elif format_name == "GeneratedDomainReadSet":
            parsed = _domain_set(invalid_number=self.invalid_domain)
            output_text = parsed.model_dump_json()
        elif format_name == "GeneratedMacroRead" and self.raw_macro:
            parsed = None
            output_text = "Raw Macro response from OpenAI."
        elif format_name == "GeneratedMacroRead":
            parsed = _macro()
            output_text = parsed.model_dump_json()
        else:
            raise AssertionError(f"Unexpected structured output contract: {format_name}")
        return SimpleNamespace(
            id=f"resp_test_{self.calls}",
            model="gpt-5.6-sol",
            status="completed",
            output_parsed=parsed,
            output_text=output_text,
            usage=SimpleNamespace(input_tokens=100, output_tokens=20, total_tokens=120),
        )


class _Client:
    def __init__(self, **kwargs):
        self.responses = _Responses(**kwargs)


class _ParsedResponseWrapper(BaseModel):
    """Reproduce the SDK generic-wrapper mismatch that used to warn on dump."""

    parsed: None = None
    output_text: str = ""


def main() -> None:
    packets = _packets()
    packet_dicts = {domain: packet.to_dict() for domain, packet in packets.items()}
    model_packets = model_evidence_packets(packets)
    require(len(DOMAIN_ORDER) == 11, "Canonical domain set changed.")
    require(evidence_snapshot_id(packets) == evidence_snapshot_id(packets), "Evidence snapshot hashing is unstable.")
    model_blob = str(model_packets)
    require("source_url" not in model_blob and "https://" not in model_blob, "Source URLs leaked into the model projection.")
    require(all("value" not in fact for packet in model_packets.values() for fact in packet["facts"]), "Raw numeric values leaked into the model projection.")

    domain_layer = language_layer_payload(phase="domain")
    macro_layer = language_layer_payload(phase="macro")
    require(domain_layer["guidance"] == macro_layer["guidance"], "The two calls do not receive the same complete language layer.")
    domain_prompt = domain_read_input(model_packets, domain_layer)
    macro_prompt = macro_read_input(model_packets, _domain_set().model_dump(mode="json"), macro_layer)
    require('"language_layer"' in domain_prompt and '"profiles"' in domain_prompt, "Domain call lost the compiled language layer.")
    require('"completed_domain_reads"' in macro_prompt, "Macro call did not receive the complete domain Reads.")
    require("The retained evidence identifies the domain's main constraint." in macro_prompt, "Macro call received only a headline orientation instead of full domain prose.")
    identity = language_layer_identity()
    require(read_service.prompt_versions()["language_layer_sha256"] == identity["payload_sha256"], "Attempt provenance lost the layer digest.")

    typed_macro = _macro()
    response_wrapper = _ParsedResponseWrapper.model_construct(parsed=typed_macro, output_text=typed_macro.model_dump_json())
    with warnings.catch_warnings(record=True) as serializer_warnings:
        warnings.simplefilter("always")
        response_payload = read_generation._response_payload(response_wrapper)
    require(not serializer_warnings, "Parsed SDK response serialization emitted a Pydantic warning.")
    require(
        response_payload.get("parsed", {}).get("headline", {}).get("text") == typed_macro.headline.text,
        "Parsed SDK response serialization lost the concrete structured output.",
    )
    require(
        read_validation._alliterative_run("Covered companies can fund today's capital spending") == ["Covered", "companies", "can"],
        "Three-word same-initial sequence escaped the sound diagnostic.",
    )
    require(
        not read_validation._alliterative_run("Future commitments are about five times current capital spending"),
        "Ordinary repeated initials were mislabeled as a consecutive alliterative run.",
    )
    require(
        read_validation._UNDEFINED_COHORT_RE.search("Covered issuers can finance the buildout") is not None,
        "Undefined internal cohort label escaped the reader-context diagnostic.",
    )
    require(
        read_validation._UNDEFINED_COHORT_RE.search("The companies tracked in this analysis can finance the buildout") is None,
        "A reader-sufficient cohort description was mislabeled as internal shorthand.",
    )
    cohort_errors, cohort_failures = read_validation._validate_prose_shape(
        _sentence("Covered issuers finance the buildout.", "finance.anchor"),
        label="macro.analysis[0]",
    )
    require(cohort_errors and cohort_failures[0]["reason"] == "undefined_cohort", "Undefined cohort did not become a publication diagnostic.")
    proportion_errors, proportion_failures = read_validation._validate_prose_shape(
        _sentence("Minority current business use leaves the economic effect unresolved.", "adoption.anchor"),
        label="macro.analysis[0]",
    )
    require(
        any(item["reason"] == "ambiguous_proportion" for item in proportion_failures),
        "Malformed minority/majority proportion did not become a sentence-construction diagnostic.",
    )
    neutral_errors, neutral_failures = read_validation._validate_prose_shape(
        _sentence("Fewer than half of businesses currently report AI use.", "adoption.anchor"),
        label="macro.analysis[0]",
    )
    require(
        not any(item["reason"] == "ambiguous_proportion" for item in neutral_failures),
        "Clear population-first proportional language was rejected.",
    )
    require(
        len(GeneratedMacroParagraph(sentences=[
            _sentence("The first sentence advances the argument.", "finance.anchor"),
            _sentence("The second sentence completes the paragraph.", "finance.anchor"),
        ]).sentences) == 2,
        "Macro schema still forces three sentences into every paragraph.",
    )

    prompt_source = (ROOT / "analytics" / "read_prompts.py").read_text(encoding="utf-8")
    require("There is no minimum word count." in prompt_source, "Macro prompt still pressures the model to pad to a word floor.")
    require("adopt a classroom tone" in prompt_source, "Sophisticated non-specialist audience rule is missing from the prompt.")
    validator_source = (ROOT / "analytics" / "read_validation.py").read_text(encoding="utf-8")
    require("MIN_MACRO_ANALYSIS_WORDS" not in validator_source, "Macro word minimum survived the recalibration.")

    source = (ROOT / "analytics" / "read_generation.py").read_text(encoding="utf-8")
    for forbidden in ("revise_domain", "assess_domain", "revise_macro", "assess_macro", "repair_domain", "repair_macro"):
        require(forbidden not in source, f"Retired paid stage survived: {forbidden}")
    require("max_retries=0" in source, "Direct OpenAI client permits SDK retries.")
    runner_source = (ROOT / "automation" / "runner.py").read_text(encoding="utf-8")
    config_source = (ROOT / "automation" / "config.py").read_text(encoding="utf-8")
    require('HARD_MAX_PAID_CALLS_PER_RUN = 2' in config_source, "Automation per-run ceiling changed from the approved two calls.")
    require('HARD_MAX_PAID_CALLS_PER_DAY = 4' in config_source, "Automation daily ceiling changed from four calls.")
    require('"published_with_warnings", "published_raw_response"' in runner_source, "Automation still rejects completed warned or raw responses.")
    require("max_retries=0" in runner_source, "Automation OpenAI client permits SDK retries.")

    original_builder = read_service.build_evidence_packets
    original_artifact_loader = read_service.load_read_artifact
    original_attempt_writer = read_service.persist_read_attempt
    original_artifact_writer = read_service.persist_read_artifact
    saved_attempts: list[dict] = []
    published: list[dict] = []
    context = DashboardContext(current_context={"by_domain": {}})
    config = OpenAIConfig(api_key="test", model="gpt-5.6-sol", reasoning_effort="medium")
    try:
        read_service.build_evidence_packets = lambda context: packets
        read_service.persist_read_attempt = lambda payload, attempt_id=None: saved_attempts.append(dict(payload)) or str(attempt_id or "test")
        read_service.persist_read_artifact = lambda payload: published.append(dict(payload))

        client = _Client()
        artifact = read_service.generate_validated_read_artifact(context, config, client=client, persist=True)
        require(client.responses.calls == 2, f"Full generation used {client.responses.calls} calls instead of two.")
        require(artifact["status"] == "validated", f"Valid two-call result did not validate: {artifact['status']}")
        require("completed_domain_reads" in client.responses.inputs[1], "Second call did not receive completed domain Reads.")
        require(len(artifact.get("raw_responses") or {}) == 2, "Exact OpenAI response objects were not retained for both calls.")
        require(
            len((artifact.get("reads") or {}).get("macro", {}).get("analysis_paragraphs") or []) == 3,
            "Macro paragraph boundaries were not preserved in the public Read.",
        )
        require(any(item.get("status") == "domain_reads_generated" for item in saved_attempts), "Domain response was not persisted before the Macro call.")
        require(artifact["reads"]["market"]["headline"] == _domain_set().reads[0].headline.text, "Returned domain prose was rewritten after OpenAI.")

        warning_client = _Client(invalid_domain=True)
        warned = read_service.generate_validated_read_artifact(context, config, client=warning_client, persist=False)
        require(warning_client.responses.calls == 2, "A validator warning changed the paid call count.")
        require(warned["status"] == "published_with_warnings", "Validator diagnostics suppressed or mislabeled the paid response.")
        require("999" in warned["reads"]["market"]["analysis"], "Warned OpenAI prose was replaced.")

        raw_client = _Client(raw_macro=True)
        raw = read_service.generate_validated_read_artifact(context, config, client=raw_client, persist=False)
        require(raw_client.responses.calls == 2, "Raw-response publication changed the two-call contract.")
        require(raw["status"] == "published_raw_response", "Unparsed paid response was hidden.")
        require(raw["reads"]["macro"]["analysis"] == "Raw Macro response from OpenAI.", "Raw OpenAI text was altered or replaced.")

        raw_domain_client = _Client(raw_domain=True)
        raw_domain = read_service.generate_validated_read_artifact(context, config, client=raw_domain_client, persist=False)
        require(raw_domain_client.responses.calls == 2, "An unparsed domain response prevented the approved Macro call.")
        require(raw_domain["status"] == "published_raw_response", "Unparsed domain response was hidden.")
        require(
            (raw_domain["reads"]["macro"].get("unparsed_openai_responses") or [])[0]["text"] == "Raw Domain response from OpenAI.",
            "Exact unparsed domain text was not carried into the Reader payload.",
        )
        raw_html = build_domain_read_html(raw_domain["reads"]["macro"], label="AI Macro Read", accent_color="#000", macro=True)
        require("Raw Domain response from OpenAI." in raw_html, "Reader markup hid the unparsed paid domain response.")

        read_service.load_read_artifact = lambda: artifact
        macro_client = _Client()
        refreshed = read_service.regenerate_macro_read(context, config, client=macro_client, persist=False)
        require(macro_client.responses.calls == 1, "Macro-only action used more than one call.")
        require(refreshed["reads"]["market"] == artifact["reads"]["market"], "Macro-only action rewrote domain prose.")

        future = datetime.now(timezone.utc) + timedelta(hours=25)
        expired = read_service.publication_lease_state(artifact, now=future)
        require(not expired["active"], "Publication lease exceeds 24 hours.")
        require(
            reader_snapshot._cached_snapshot_usable({"commentary": {"status": "published_with_warnings", "publication": artifact["publication"]}}),
            "Active warned publication was treated as unusable.",
        )
        old_publication = dict(artifact["publication"])
        old_publication["published_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        require(
            not reader_snapshot._cached_snapshot_usable({"commentary": {"status": "published_raw_response", "publication": old_publication}}),
            "Expired raw publication bypassed the lease.",
        )
    finally:
        read_service.build_evidence_packets = original_builder
        read_service.load_read_artifact = original_artifact_loader
        read_service.persist_read_attempt = original_attempt_writer
        read_service.persist_read_artifact = original_artifact_writer

    original_gate = read_store.repository_writes_enabled
    original_dir = read_store.READ_ATTEMPT_DIR
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            read_store.repository_writes_enabled = lambda: True
            read_store.READ_ATTEMPT_DIR = Path(temp_dir) / "attempts"
            attempt_id = read_store.persist_read_attempt({
                "status": "generation_failed",
                "evidence_snapshot_id": "snapshot123",
                "prompt_versions": {"domain": read_service.prompt_versions()["domain"], "language_layer_sha256": "layer123"},
                "generated_output": {"domain_reads": _domain_set().model_dump(mode="json")},
            })
            recovered = read_store.latest_recoverable_attempt(
                evidence_snapshot_id="snapshot123",
                domain_prompt_version=read_service.prompt_versions()["domain"],
                language_layer_sha256="layer123",
            )
            require(recovered.get("attempt_id") == attempt_id, "Recoverable typed domain response was not discovered.")
    finally:
        read_store.repository_writes_enabled = original_gate
        read_store.READ_ATTEMPT_DIR = original_dir

    print("PASS two-call commentary · full layer in both calls · domains feed Macro · warnings publish · raw response visible · zero retries")


if __name__ == "__main__":
    main()
