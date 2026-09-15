"""Regression guard for the simplified AI Macro writing assignment."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.read_briefing import STYLE_REFERENCE  # noqa: E402
from analytics.read_prompts import EDITORIAL_INSTRUCTIONS  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    prompt = EDITORIAL_INSTRUCTIONS.casefold()
    require("prioritize significance over coverage" in prompt, "Editorial objective is missing")
    require("clear, natural english" in prompt, "Plain-language objective is missing")
    require("do not force unrelated facts into one story" in prompt, "Mixed-evidence instruction is missing")
    require("update only the domain reads" in prompt, "Selective domain-update instruction is missing")
    require("you may return no domain reads" in prompt, "The model is still being forced to manufacture domain coverage")
    require("analytical state" not in prompt, "Legacy analytical-state task returned")
    require("conversion chain" not in prompt, "Legacy conversion-chain framing returned")
    require("exactly three" not in prompt, "Exact sentence-count micromanagement returned")
    require("semicolon" not in prompt, "Punctuation micromanagement returned")
    require("alliteration" not in prompt, "Pathology-specific rule leaked into the writing brief")
    require(STYLE_REFERENCE.startswith("AI Macro is a research platform that examines"), "Owner style reference changed")
    print("PASS  editorial prompt reset · simple assignment · owner style reference · no rule litany")


if __name__ == "__main__":
    main()
