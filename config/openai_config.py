"""OpenAI configuration for owner-triggered and bounded automation commentary workflows."""

from __future__ import annotations

from dataclasses import dataclass
import os

DEFAULT_OPENAI_MODEL = "gpt-5.6"
DEFAULT_REASONING_EFFORT = "medium"


def _streamlit_secret(name: str) -> str:
    try:
        import streamlit as st
        value = st.secrets.get(name, "")
    except Exception:
        return ""
    return str(value or "").strip()


@dataclass(frozen=True, slots=True)
class OpenAIConfig:
    api_key: str
    model: str = DEFAULT_OPENAI_MODEL
    reasoning_effort: str = DEFAULT_REASONING_EFFORT
    max_output_tokens: int | None = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


def load_openai_config() -> OpenAIConfig:
    key = str(os.getenv("OPENAI_API_KEY", "") or "").strip() or _streamlit_secret("OPENAI_API_KEY")
    model = str(os.getenv("AI_MACRO_OPENAI_MODEL", DEFAULT_OPENAI_MODEL) or DEFAULT_OPENAI_MODEL).strip()
    effort = str(os.getenv("AI_MACRO_OPENAI_REASONING", DEFAULT_REASONING_EFFORT) or DEFAULT_REASONING_EFFORT).strip().lower()
    if effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
        effort = DEFAULT_REASONING_EFFORT
    raw_output_limit = str(os.getenv("AI_MACRO_OPENAI_MAX_OUTPUT_TOKENS", "") or "").strip()
    max_output_tokens: int | None = None
    if raw_output_limit:
        try:
            max_output_tokens = max(2000, int(raw_output_limit))
        except (TypeError, ValueError):
            max_output_tokens = None
    return OpenAIConfig(
        api_key=key,
        model=model,
        reasoning_effort=effort,
        max_output_tokens=max_output_tokens,
    )
