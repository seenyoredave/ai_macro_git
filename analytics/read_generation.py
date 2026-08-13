"""Exactly two explicit OpenAI calls for AI Macro commentary generation."""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any

from analytics.language_layer import language_layer_identity, language_layer_payload
from analytics.read_models import GeneratedDomainReadSet, GeneratedMacroRead
from analytics.read_prompts import (
    DOMAIN_INSTRUCTIONS,
    DOMAIN_PROMPT_VERSION,
    MACRO_INSTRUCTIONS,
    MACRO_PROMPT_VERSION,
    domain_read_input,
    macro_read_input,
)
from config.openai_config import OpenAIConfig

GENERATOR_VERSION = "4.3.0"


class GenerationStageError(RuntimeError):
    """A request returned without a usable structured object."""

    def __init__(self, message: str, *, metadata: GenerationMetadata | None = None, response_payload: Any = None):
        super().__init__(message)
        self.metadata = metadata
        self.response_payload = response_payload


@dataclass(frozen=True, slots=True)
class GenerationMetadata:
    response_id: str
    model: str
    elapsed_sec: float
    input_tokens: int
    output_tokens: int
    total_tokens: int
    response_payload: dict[str, Any] = field(repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "response_id": self.response_id,
            "model": self.model,
            "elapsed_sec": self.elapsed_sec,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


def _usage(response: Any) -> tuple[int, int, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0, 0

    def value(name: str) -> int:
        raw = usage.get(name, 0) if isinstance(usage, dict) else getattr(usage, name, 0)
        try:
            return int(raw or 0)
        except (TypeError, ValueError):
            return 0

    return value("input_tokens"), value("output_tokens"), value("total_tokens")


def _response_payload(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        try:
            # responses.parse() specializes the SDK's generic response wrapper
            # with our Pydantic output model at runtime.  Duck-typed serialization
            # preserves that concrete parsed model instead of asking Pydantic to
            # force it through the wrapper's unspecialized union annotations.
            payload = response.model_dump(mode="json", serialize_as_any=True)
        except TypeError:
            payload = response.model_dump()
    elif hasattr(response, "to_dict"):
        payload = response.to_dict()
    else:
        payload = {
            "id": str(getattr(response, "id", "") or ""),
            "status": str(getattr(response, "status", "") or ""),
        }
    if not isinstance(payload, dict):
        payload = {"response": payload}
    output_text = getattr(response, "output_text", None)
    if output_text is not None:
        payload["_ai_macro_output_text"] = output_text
    return payload


def _client(config: OpenAIConfig, client: Any | None = None):
    if client is not None:
        return client
    if not config.configured:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    from openai import OpenAI

    # The SDK may not retry a paid request. A new call occurs only when the
    # owner or the existing approved scheduled worker invokes this pipeline.
    return OpenAI(api_key=config.api_key, max_retries=0)


def _parse(
    *,
    api: Any,
    config: OpenAIConfig,
    instructions: str,
    input_payload: str,
    text_format: Any,
    empty_error: str,
) -> tuple[Any, GenerationMetadata]:
    started = time.perf_counter()
    response = api.responses.parse(
        model=config.model,
        reasoning={"effort": config.reasoning_effort},
        instructions=instructions,
        input=input_payload,
        text_format=text_format,
        store=False,
    )
    elapsed = time.perf_counter() - started
    input_tokens, output_tokens, total_tokens = _usage(response)
    raw = _response_payload(response)
    metadata = GenerationMetadata(
        response_id=str(getattr(response, "id", "") or ""),
        model=str(getattr(response, "model", "") or config.model),
        elapsed_sec=elapsed,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        response_payload=raw,
    )
    parsed = getattr(response, "output_parsed", None)
    if parsed is None:
        raise GenerationStageError(empty_error, metadata=metadata, response_payload=raw)
    return parsed, metadata


def generate_domain_reads(
    packets: dict[str, dict],
    config: OpenAIConfig,
    *,
    client: Any | None = None,
) -> tuple[GeneratedDomainReadSet, GenerationMetadata]:
    layer = language_layer_payload(phase="domain")
    return _parse(
        api=_client(config, client),
        config=config,
        instructions=DOMAIN_INSTRUCTIONS,
        input_payload=domain_read_input(packets, layer),
        text_format=GeneratedDomainReadSet,
        empty_error="OpenAI returned no parsed domain Read set.",
    )


def generate_macro_read(
    packets: dict[str, dict],
    domain_reads: GeneratedDomainReadSet | dict[str, Any],
    config: OpenAIConfig,
    *,
    client: Any | None = None,
) -> tuple[GeneratedMacroRead, GenerationMetadata]:
    layer = language_layer_payload(phase="macro")
    completed = domain_reads.model_dump(mode="json") if hasattr(domain_reads, "model_dump") else dict(domain_reads)
    return _parse(
        api=_client(config, client),
        config=config,
        instructions=MACRO_INSTRUCTIONS,
        input_payload=macro_read_input(packets, completed, layer),
        text_format=GeneratedMacroRead,
        empty_error="OpenAI returned no parsed AI Macro Read.",
    )


def prompt_versions() -> dict[str, str]:
    identity = language_layer_identity()
    return {
        "domain": DOMAIN_PROMPT_VERSION,
        "macro": MACRO_PROMPT_VERSION,
        "generator": GENERATOR_VERSION,
        "language_layer": identity["layer_version"],
        "language_layer_sha256": identity["payload_sha256"],
    }
