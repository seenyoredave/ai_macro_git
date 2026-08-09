"""Typed application payload shared by analytics orchestration and rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class DashboardContext:
    """One explicit boundary object for the dashboard's assembled state.

    Source loaders and domain engines remain free to use their native data
    structures.  This object only replaces long orchestration call signatures.
    """

    sector_data: dict = field(default_factory=dict)
    sector_metrics: dict = field(default_factory=dict)
    fred_data: dict = field(default_factory=dict)
    regime_metrics: dict = field(default_factory=dict)
    nfci_history: Any = None
    energy_data: dict = field(default_factory=dict)
    debt_markets_data: dict = field(default_factory=dict)
    infrastructure_data: dict = field(default_factory=dict)
    connectivity_data: dict = field(default_factory=dict)
    water_data: dict = field(default_factory=dict)
    adaptation_data: dict = field(default_factory=dict)
    workforce_data: dict = field(default_factory=dict)
    economic_impact_data: dict = field(default_factory=dict)
    commercialization_data: dict = field(default_factory=dict)
    current_context: dict = field(default_factory=dict)
    market_universe_summary: dict = field(default_factory=dict)
    sector_weekly_context: dict = field(default_factory=dict)
    dashboard_data: dict | None = None
    platform_reads: dict = field(default_factory=dict)
