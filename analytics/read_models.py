"""Minimal structured output contract for AI Macro editorial synthesis."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DomainName = Literal[
    "market", "finance", "compute", "data_center", "connectivity", "power",
    "grid_storage", "water", "adoption", "workforce", "economic_impact",
]


class SupportedPassage(BaseModel):
    """One natural-language block plus the deterministic evidence used to support it."""

    text: str = Field(min_length=1)
    fact_ids: list[str] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)


class GeneratedDomainRead(BaseModel):
    domain: DomainName
    headline: SupportedPassage
    body: SupportedPassage


class GeneratedMacroRead(BaseModel):
    headline: SupportedPassage
    paragraphs: list[SupportedPassage] = Field(min_length=2, max_length=4)


class GeneratedEditorialSynthesis(BaseModel):
    """One publication candidate. The model writes; deterministic code decides whether it is safe to publish."""

    domain_reads: list[GeneratedDomainRead]
    macro_read: GeneratedMacroRead
