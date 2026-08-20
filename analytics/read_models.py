"""Typed OpenAI output contracts for AI Macro editorial synthesis."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from analytics.read_evidence import DOMAIN_ORDER

InferenceKind = Literal["observation", "interpretation"]
DomainName = Literal[
    "market", "finance", "compute", "data_center", "connectivity", "power",
    "grid_storage", "water", "adoption", "workforce", "economic_impact",
]


class SupportedSentence(BaseModel):
    text: str = Field(min_length=1)
    fact_ids: list[str] = Field(min_length=1)
    inference: InferenceKind


class GeneratedDomainRead(BaseModel):
    domain: DomainName
    headline: SupportedSentence
    analysis: list[SupportedSentence] = Field(min_length=3, max_length=4)


class GeneratedDomainReadSet(BaseModel):
    reads: list[GeneratedDomainRead] = Field(min_length=len(DOMAIN_ORDER), max_length=len(DOMAIN_ORDER))


class GeneratedMacroParagraph(BaseModel):
    sentences: list[SupportedSentence] = Field(min_length=2, max_length=4)


class GeneratedMacroRead(BaseModel):
    selected_domains: list[DomainName] = Field(min_length=3, max_length=5)
    headline: SupportedSentence
    paragraphs: list[GeneratedMacroParagraph] = Field(min_length=3, max_length=4)

    @property
    def analysis(self) -> list[SupportedSentence]:
        """Flatten paragraph sentences for grounding and editorial audits."""
        return [sentence for paragraph in self.paragraphs for sentence in paragraph.sentences]


class GeneratedAnalyticalState(BaseModel):
    """Compact continuity state retained for the next editorial call."""

    thesis: str = Field(min_length=1, max_length=500)
    selected_domains: list[DomainName] = Field(max_length=5)
    changed_since_prior: list[str] = Field(max_length=5)
    unresolved_tensions: list[str] = Field(max_length=4)
    confirming_signals: list[str] = Field(max_length=4)
    disconfirming_signals: list[str] = Field(max_length=4)


class GeneratedEditorialSynthesis(BaseModel):
    """One-call decision, incremental domain updates, and Macro synthesis."""

    decision: Literal["publish", "retain_prior"]
    decision_reason: str = Field(min_length=1, max_length=500)
    updated_domains: list[DomainName] = Field(max_length=len(DOMAIN_ORDER))
    domain_reads: list[GeneratedDomainRead] = Field(max_length=len(DOMAIN_ORDER))
    macro_read: GeneratedMacroRead | None
    analytical_state: GeneratedAnalyticalState
