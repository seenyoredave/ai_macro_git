"""Typed OpenAI output contracts for the AI Macro language-layer pipeline."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from analytics.read_evidence import DOMAIN_ORDER

InferenceKind = Literal["observation", "interpretation"]


class SupportedSentence(BaseModel):
    text: str = Field(min_length=1)
    fact_ids: list[str] = Field(min_length=1)
    inference: InferenceKind


class GeneratedDomainRead(BaseModel):
    domain: Literal[
        "market", "finance", "compute", "data_center", "connectivity", "power",
        "grid_storage", "water", "adoption", "workforce", "economic_impact"
    ]
    headline: SupportedSentence
    analysis: list[SupportedSentence] = Field(min_length=3, max_length=4)


class GeneratedDomainReadSet(BaseModel):
    reads: list[GeneratedDomainRead] = Field(min_length=len(DOMAIN_ORDER), max_length=len(DOMAIN_ORDER))


class GeneratedMacroParagraph(BaseModel):
    sentences: list[SupportedSentence] = Field(min_length=2, max_length=4)


class GeneratedMacroRead(BaseModel):
    selected_domains: list[Literal[
        "market", "finance", "compute", "data_center", "connectivity", "power",
        "grid_storage", "water", "adoption", "workforce", "economic_impact"
    ]] = Field(min_length=3, max_length=5)
    headline: SupportedSentence
    paragraphs: list[GeneratedMacroParagraph] = Field(min_length=3, max_length=4)

    @property
    def analysis(self) -> list[SupportedSentence]:
        """Flatten paragraph sentences for grounding and editorial audits."""
        return [sentence for paragraph in self.paragraphs for sentence in paragraph.sentences]
