"""OpenAI Responses API client for v7 commentary generation."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

from analytics.read_models import GeneratedDomainReadSet, GeneratedMacroRead
from analytics.read_prompts import BASE_INSTRUCTIONS, DOMAIN_PROMPT_VERSION, MACRO_PROMPT_VERSION, domain_read_input, macro_read_input
from config.openai_config import OpenAIConfig

GENERATOR_VERSION = "1.3.0"


@dataclass(frozen=True, slots=True)
class GenerationMetadata:
    response_id: str
    model: str
    elapsed_sec: float
    input_tokens: int
    output_tokens: int
    total_tokens: int

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
        if isinstance(usage, dict):
            raw = usage.get(name, 0)
        else:
            raw = getattr(usage, name, 0)
        try:
            return int(raw or 0)
        except (TypeError, ValueError):
            return 0
    return value("input_tokens"), value("output_tokens"), value("total_tokens")


def _client(config: OpenAIConfig, client: Any | None = None):
    if client is not None:
        return client
    if not config.configured:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    from openai import OpenAI
    return OpenAI(api_key=config.api_key)


def generate_domain_reads(packets: dict[str, dict], config: OpenAIConfig, *, client: Any | None = None) -> tuple[GeneratedDomainReadSet, GenerationMetadata]:
    api = _client(config, client)
    started = time.perf_counter()
    response = api.responses.parse(
        model=config.model,
        reasoning={"effort": config.reasoning_effort},
        instructions=BASE_INSTRUCTIONS,
        input=domain_read_input(packets),
        text_format=GeneratedDomainReadSet,
        store=False,
    )
    elapsed = time.perf_counter() - started
    parsed = getattr(response, "output_parsed", None)
    if parsed is None:
        raise RuntimeError("OpenAI returned no parsed domain Read payload.")
    input_tokens, output_tokens, total_tokens = _usage(response)
    metadata = GenerationMetadata(str(getattr(response, "id", "") or ""), config.model, elapsed, input_tokens, output_tokens, total_tokens)
    return parsed, metadata


def generate_macro_read(packets: dict[str, dict], domain_orientation: dict[str, dict], config: OpenAIConfig, *, client: Any | None = None) -> tuple[GeneratedMacroRead, GenerationMetadata]:
    api = _client(config, client)
    started = time.perf_counter()
    response = api.responses.parse(
        model=config.model,
        reasoning={"effort": config.reasoning_effort},
        instructions=BASE_INSTRUCTIONS,
        input=macro_read_input(packets, domain_orientation),
        text_format=GeneratedMacroRead,
        store=False,
    )
    elapsed = time.perf_counter() - started
    parsed = getattr(response, "output_parsed", None)
    if parsed is None:
        raise RuntimeError("OpenAI returned no parsed AI Macro Read payload.")
    input_tokens, output_tokens, total_tokens = _usage(response)
    metadata = GenerationMetadata(str(getattr(response, "id", "") or ""), config.model, elapsed, input_tokens, output_tokens, total_tokens)
    return parsed, metadata


def prompt_versions() -> dict[str, str]:
    return {"domain": DOMAIN_PROMPT_VERSION, "macro": MACRO_PROMPT_VERSION, "generator": GENERATOR_VERSION}
