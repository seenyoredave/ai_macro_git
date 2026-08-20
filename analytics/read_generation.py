"""Exactly one explicit OpenAI call for AI Macro editorial synthesis."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import time
from typing import Any

from analytics.language_layer import (
    editorial_constitution_identity,
    editorial_constitution_payload,
    language_layer_identity,
)
from analytics.read_models import GeneratedEditorialSynthesis
from analytics.read_prompts import (
    EDITORIAL_INSTRUCTIONS,
    EDITORIAL_PROMPT_VERSION,
    editorial_synthesis_input,
)
from config.openai_config import OpenAIConfig

GENERATOR_VERSION = "6.1.0"

DEFAULT_BACKGROUND_DEADLINE_SECONDS = 1200.0
DEFAULT_BACKGROUND_POLL_INTERVAL_SECONDS = 2.0
DEFAULT_OPENAI_REQUEST_TIMEOUT_SECONDS = 60.0
ACTIVE_BACKGROUND_STATUSES = frozenset({"queued", "in_progress"})


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
    terminal_status: str
    poll_attempts: int
    poll_errors: tuple[str, ...]
    response_payload: dict[str, Any] = field(repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "response_id": self.response_id,
            "model": self.model,
            "elapsed_sec": self.elapsed_sec,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "terminal_status": self.terminal_status,
            "poll_attempts": self.poll_attempts,
            "poll_errors": list(self.poll_errors),
        }


def _positive_float_env(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _status(response: Any) -> str:
    raw = getattr(response, "status", "")
    return str(getattr(raw, "value", raw) or "").strip().lower()


def _response_id(response: Any) -> str:
    return str(getattr(response, "id", "") or "").strip()


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


def _commit_allowance(api: Any, response_id: str) -> None:
    commit = getattr(api.responses, "commit", None)
    if callable(commit):
        commit(response_id)


def _release_allowance(api: Any, response_id: str, detail: str) -> None:
    abandon = getattr(api.responses, "abandon", None)
    if callable(abandon):
        abandon(response_id, detail=detail)


def _cancel_background(api: Any, response_id: str, request_timeout: float) -> str:
    cancel = getattr(api.responses, "cancel", None)
    if not callable(cancel):
        return "cancel unavailable"
    try:
        cancel(response_id, timeout=request_timeout)
        return "cancel requested"
    except Exception as exc:
        return f"cancel failed: {type(exc).__name__}: {exc}"[:500]


def _parsed_output(response: Any, text_format: Any) -> tuple[Any | None, str]:
    parsed = getattr(response, "output_parsed", None)
    output_text = str(getattr(response, "output_text", "") or "").strip()
    if parsed is not None:
        return parsed, output_text
    if not output_text:
        return None, ""
    validator = getattr(text_format, "model_validate_json", None)
    if not callable(validator):
        return None, output_text
    return validator(output_text), output_text


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
    request_timeout = _positive_float_env(
        "AI_MACRO_OPENAI_REQUEST_TIMEOUT_SECONDS",
        DEFAULT_OPENAI_REQUEST_TIMEOUT_SECONDS,
    )
    deadline_seconds = _positive_float_env(
        "AI_MACRO_OPENAI_BACKGROUND_DEADLINE_SECONDS",
        DEFAULT_BACKGROUND_DEADLINE_SECONDS,
    )
    poll_interval = _positive_float_env(
        "AI_MACRO_OPENAI_POLL_INTERVAL_SECONDS",
        DEFAULT_BACKGROUND_POLL_INTERVAL_SECONDS,
    )
    request: dict[str, Any] = {
        "model": config.model,
        "reasoning": {"effort": config.reasoning_effort},
        "instructions": instructions,
        "input": input_payload,
        "text_format": text_format,
        "background": True,
        "store": False,
        "timeout": request_timeout,
    }
    if config.max_output_tokens is not None:
        request["max_output_tokens"] = config.max_output_tokens
    response = api.responses.parse(
        **request,
    )
    response_id = _response_id(response)
    if not response_id:
        raise GenerationStageError(
            "OpenAI accepted a background request without returning a response ID.",
            response_payload=_response_payload(response),
        )

    poll_attempts = 0
    poll_errors: list[str] = []
    deadline = started + deadline_seconds
    while _status(response) in ACTIVE_BACKGROUND_STATUSES:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            cancel_detail = _cancel_background(api, response_id, request_timeout)
            detail = f"background deadline exceeded after {deadline_seconds:.1f}s; {cancel_detail}"
            _release_allowance(api, response_id, detail)
            raw = _response_payload(response)
            raw["_ai_macro_background"] = {
                "response_id": response_id,
                "terminal_status": _status(response),
                "poll_attempts": poll_attempts,
                "poll_errors": poll_errors,
                "deadline_seconds": deadline_seconds,
                "detail": detail,
            }
            raise GenerationStageError(
                f"OpenAI background response {response_id} exceeded its {deadline_seconds:.0f}s deadline.",
                response_payload=raw,
            )
        time.sleep(min(poll_interval, remaining))
        try:
            response = api.responses.retrieve(response_id, timeout=request_timeout)
            poll_attempts += 1
        except Exception as exc:
            # Retrieval is idempotent: a transport failure does not create a
            # second paid generation. Keep polling the same response ID.
            poll_errors.append(f"{type(exc).__name__}: {exc}"[:500])
            poll_errors = poll_errors[-20:]

    elapsed = time.perf_counter() - started
    input_tokens, output_tokens, total_tokens = _usage(response)
    raw = _response_payload(response)
    terminal_status = _status(response)
    raw["_ai_macro_background"] = {
        "response_id": response_id,
        "terminal_status": terminal_status,
        "poll_attempts": poll_attempts,
        "poll_errors": poll_errors,
        "deadline_seconds": deadline_seconds,
        "request_timeout_seconds": request_timeout,
    }
    metadata = GenerationMetadata(
        response_id=response_id,
        model=str(getattr(response, "model", "") or config.model),
        elapsed_sec=elapsed,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        terminal_status=terminal_status,
        poll_attempts=poll_attempts,
        poll_errors=tuple(poll_errors),
        response_payload=raw,
    )

    if terminal_status != "completed":
        detail = f"background response ended with status={terminal_status or 'unknown'}"
        if str(getattr(response, "output_text", "") or "").strip():
            _commit_allowance(api, response_id)
        else:
            _release_allowance(api, response_id, detail)
        raise GenerationStageError(
            f"OpenAI {detail}.",
            metadata=metadata,
            response_payload=raw,
        )

    try:
        parsed, output_text = _parsed_output(response, text_format)
    except Exception as exc:
        # A completed response containing model output consumes the allowance,
        # even if local schema validation rejects that output. The raw response
        # remains available to the existing preservation/publication path.
        if str(getattr(response, "output_text", "") or "").strip():
            _commit_allowance(api, response_id)
        else:
            _release_allowance(api, response_id, "completed response contained no output text")
        raise GenerationStageError(
            f"{empty_error} {type(exc).__name__}: {exc}",
            metadata=metadata,
            response_payload=raw,
        ) from exc

    if parsed is None:
        _release_allowance(api, response_id, "completed response contained no usable output")
        raise GenerationStageError(empty_error, metadata=metadata, response_payload=raw)

    # Only a completed response with usable output consumes the safety slot.
    # Poll requests never reserve or consume additional slots.
    _commit_allowance(api, response_id)
    return parsed, metadata


def generate_editorial_synthesis(
    *,
    capsules: dict[str, Any],
    prior_publication: dict[str, Any],
    prior_analytical_state: dict[str, Any],
    required_update_domains: list[str],
    candidate_update_domains: list[str],
    bootstrap: bool,
    config: OpenAIConfig,
    client: Any | None = None,
) -> tuple[GeneratedEditorialSynthesis, GenerationMetadata]:
    constitution = editorial_constitution_payload()
    return _parse(
        api=_client(config, client),
        config=config,
        instructions=EDITORIAL_INSTRUCTIONS,
        input_payload=editorial_synthesis_input(
            capsules=capsules,
            editorial_constitution=constitution,
            prior_publication=prior_publication,
            prior_analytical_state=prior_analytical_state,
            required_update_domains=required_update_domains,
            candidate_update_domains=candidate_update_domains,
            bootstrap=bootstrap,
        ),
        text_format=GeneratedEditorialSynthesis,
        empty_error="OpenAI returned no parsed editorial synthesis.",
    )


def prompt_versions() -> dict[str, str]:
    source_identity = language_layer_identity()
    constitution = editorial_constitution_identity()
    return {
        "editorial": EDITORIAL_PROMPT_VERSION,
        "generator": GENERATOR_VERSION,
        "editorial_constitution": constitution["constitution_version"],
        "editorial_constitution_sha256": constitution["sha256"],
        "source_language_layer": source_identity["layer_version"],
        "source_language_layer_sha256": source_identity["payload_sha256"],
    }
