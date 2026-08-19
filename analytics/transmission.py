"""Deterministic cross-domain state for the AI Macro flagship view.

This module does not create a new composite score. It reads finished analytical
outputs that already have defined economic meaning and summarizes the direction
of the AI economy's transmission chain: expectations, funding, buildout,
deliverability, adoption, and outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from analytics.dashboard_context import DashboardContext

TRANSMISSION_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class TransmissionStage:
    key: str
    label: str
    value: str
    note: str


@dataclass(frozen=True, slots=True)
class MacroTransmissionState:
    headline: str
    breakpoints: tuple[str, ...]
    measurement_gaps: tuple[str, ...]
    stages: tuple[TransmissionStage, ...]
    version: str = TRANSMISSION_VERSION


def _num(value: Any) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    return float(numeric) if pd.notna(numeric) and np.isfinite(numeric) else np.nan


def _fmt(value: Any, digits: int = 1, *, signed: bool = False, suffix: str = "") -> str:
    numeric = _num(value)
    if pd.isna(numeric):
        return "n/a"
    spec = f"+.{digits}f" if signed else f".{digits}f"
    return f"{numeric:{spec}}{suffix}"


def _relationship(value: Any, *, positive: str, negative: str, aligned: str) -> str:
    numeric = _num(value)
    if pd.isna(numeric):
        return "Unresolved"
    if numeric > 0:
        return positive
    if numeric < 0:
        return negative
    return aligned


def _headline(speculation_gap: float, power_gap: float, validation_gap: float) -> str:
    buildout_ahead: list[str] = []
    if pd.notna(speculation_gap) and speculation_gap < 0:
        buildout_ahead.append("pricing")
    if pd.notna(power_gap) and power_gap > 0:
        buildout_ahead.append("power-system response")
    if pd.notna(validation_gap) and validation_gap > 0:
        buildout_ahead.append("measurable economic validation")

    if len(buildout_ahead) == 3:
        return "Buildout is running ahead of pricing, power-system response, and measurable economic validation."
    if len(buildout_ahead) == 2:
        return f"Buildout is running ahead of {buildout_ahead[0]} and {buildout_ahead[1]}."
    if len(buildout_ahead) == 1:
        return f"Buildout is running ahead of {buildout_ahead[0]}."

    if pd.notna(speculation_gap) and speculation_gap > 0:
        return "Pricing is running ahead of observable AI development."
    if pd.notna(validation_gap) and validation_gap < 0:
        return "Measured operating validation is keeping pace with or exceeding observable AI development."
    return "Transmission signals are mixed across pricing, infrastructure response, adoption, and economic outcomes."


def build_macro_transmission(context: DashboardContext) -> MacroTransmissionState:
    """Build the flagship transmission state from existing deterministic outputs."""
    regime = context.regime_metrics or {}
    funding = (regime.get("Deployment Funding Mix", {}) or {}).get("current", {}) or {}

    aei = _num(regime.get("AI Equity Index"))
    adi = _num(regime.get("AI Development Intensity"))
    speculation_gap = _num(regime.get("Speculation Gap"))
    power_gap = _num(regime.get("Power Capacity Gap"))
    validation_gap = _num(regime.get("Economic Validation Gap"))

    internal_coverage = _num(funding.get("internal_funding_coverage"))
    cash_runway = _num(funding.get("cash_reserve_coverage_years"))
    forward_commitments = _num(funding.get("forward_commitment_load"))

    adoption = context.adoption_data or {}
    current_use = _num(adoption.get("current_use"))
    expected_use = _num(adoption.get("expected_use"))

    economic = context.economic_impact_data or {}
    productivity = _num((economic.get("nonfarm_productivity", {}) or {}).get("value"))
    output = _num((economic.get("nonfarm_output", {}) or {}).get("value"))

    inventory = ((context.infrastructure_data or {}).get("data_center_inventory") or {}).get("open_tracker_summary", {}) or {}
    pipeline_sites = int(inventory.get("active_pipeline", 0) or 0)
    pipeline_mw = _num(inventory.get("active_pipeline_published_mw"))

    expectation_value = _relationship(
        speculation_gap,
        positive="Pricing leads buildout",
        negative="Buildout leads pricing",
        aligned="Pricing and buildout aligned",
    )
    expectation_note = (
        f"AEI {_fmt(aei)} vs ADI {_fmt(adi)}; Speculation Gap {_fmt(speculation_gap, signed=True)}."
        if pd.notna(aei) and pd.notna(adi) and pd.notna(speculation_gap)
        else "The pricing-versus-development comparison is unavailable."
    )

    if pd.notna(internal_coverage):
        if internal_coverage >= 1 and pd.notna(cash_runway) and pd.notna(forward_commitments) and forward_commitments > cash_runway:
            funding_value = "Covered now; duration exposed"
        elif internal_coverage >= 1:
            funding_value = "Current CapEx internally covered"
        else:
            funding_value = "Current CapEx needs external funding"
    else:
        funding_value = "Funding unresolved"
    funding_parts = []
    if pd.notna(internal_coverage):
        funding_parts.append(f"operating cash flow {_fmt(internal_coverage, 2)}x current CapEx")
    if pd.notna(cash_runway):
        funding_parts.append(f"cash {_fmt(cash_runway, 2)} years")
    if pd.notna(forward_commitments):
        funding_parts.append(f"forward commitments {_fmt(forward_commitments, 2)}x current CapEx")
    funding_note = "; ".join(funding_parts) + "." if funding_parts else "Funding coverage is unavailable."

    buildout_value = f"ADI {_fmt(adi)} / 100" if pd.notna(adi) else "Buildout unresolved"
    if pipeline_sites and pd.notna(pipeline_mw):
        buildout_note = f"{pipeline_sites:,} tracked active pipeline sites; {_fmt(pipeline_mw / 1000)} GW of published project capacity."
    elif pipeline_sites:
        buildout_note = f"{pipeline_sites:,} tracked active pipeline sites."
    else:
        buildout_note = "Physical-project pipeline evidence is unavailable."

    deliverability_value = _relationship(
        power_gap,
        positive="Power response trails deployment",
        negative="Power response leads deployment",
        aligned="Power response aligned",
    )
    deliverability_note = (
        f"Power Capacity Gap {_fmt(power_gap, signed=True)}. National proxy; local transmission, interconnection, network, and water delivery remain site-specific."
        if pd.notna(power_gap)
        else "Measured power-system response is unavailable; local deliverability remains site-specific."
    )

    adoption_value = f"{_fmt(current_use, suffix='%')} current business use" if pd.notna(current_use) else "Adoption unresolved"
    if pd.notna(expected_use):
        adoption_note = f"{_fmt(expected_use, suffix='%')} expected use within six months; workflow depth and intensity are not yet measured."
    else:
        adoption_note = "Workflow depth and intensity are not yet measured."

    outcome_value = _relationship(
        validation_gap,
        positive="Deployment leads validation",
        negative="Validation keeps pace with deployment",
        aligned="Deployment and validation aligned",
    )
    outcome_parts = []
    if pd.notna(productivity):
        outcome_parts.append(f"nonfarm productivity {_fmt(productivity, signed=True, suffix='%')}")
    if pd.notna(output):
        outcome_parts.append(f"real output {_fmt(output, signed=True, suffix='%')}")
    outcome_note = "; ".join(outcome_parts)
    if outcome_note:
        outcome_note += ". These economy-wide outcomes do not identify AI as the cause."
    else:
        outcome_note = "Economy-wide AI attribution remains unresolved."

    breakpoints: list[str] = []
    if pd.notna(internal_coverage) and internal_coverage < 1:
        breakpoints.append("Funding → Buildout")
    if pd.notna(power_gap) and power_gap > 0:
        breakpoints.append("Buildout → Deliverability")
    if pd.notna(validation_gap) and validation_gap > 0:
        breakpoints.append("Deployment → Economic validation")

    return MacroTransmissionState(
        headline=_headline(speculation_gap, power_gap, validation_gap),
        breakpoints=tuple(breakpoints),
        measurement_gaps=("Adoption depth → Economic outcomes",),
        stages=(
            TransmissionStage("expectations", "Expectations", expectation_value, expectation_note),
            TransmissionStage("funding", "Funding", funding_value, funding_note),
            TransmissionStage("buildout", "Buildout", buildout_value, buildout_note),
            TransmissionStage("deliverability", "Deliverability", deliverability_value, deliverability_note),
            TransmissionStage("adoption", "Adoption", adoption_value, adoption_note),
            TransmissionStage("outcomes", "Economic return", outcome_value, outcome_note),
        ),
    )
