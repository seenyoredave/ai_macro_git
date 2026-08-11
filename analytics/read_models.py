"""Typed model-output contracts for v7 commentary generation."""

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
    analysis: list[SupportedSentence] = Field(min_length=3, max_length=5)


class GeneratedDomainReadSet(BaseModel):
    reads: list[GeneratedDomainRead] = Field(min_length=len(DOMAIN_ORDER), max_length=len(DOMAIN_ORDER))


class GeneratedMacroRead(BaseModel):
    selected_domains: list[Literal[
        "market", "finance", "compute", "data_center", "connectivity", "power",
        "grid_storage", "water", "adoption", "workforce", "economic_impact"
    ]] = Field(min_length=4, max_length=6)
    headline: SupportedSentence
    analysis: list[SupportedSentence] = Field(min_length=4, max_length=4)
