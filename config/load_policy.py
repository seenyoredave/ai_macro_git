"""Central data-access policy for application rebuilds and explicit refreshes.

A dashboard rebuild and a provider refresh are intentionally different actions:

* ``retained`` rebuilds may read retained files and recompute derived outputs, but
  may not contact upstream providers or mutate retained repository data.
* ``refresh`` rebuilds may contact only the provider or domain explicitly selected
  by the developer. Repository snapshot writes are permitted only for that explicit
  refresh transaction.

Keeping this decision in one immutable object prevents freshness checks inside an
individual loader from silently escalating a normal page load into network work.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from config.deployment import repository_writes_enabled


class RefreshSource(StrEnum):
    YFINANCE = "yfinance"
    EDGAR = "edgar"
    FRED = "fred"
    NYFED = "nyfed"
    CURRENT_CONTEXT = "current_context"
    COMPUTE = "compute"
    DATA_CENTERS = "data_centers"
    CONNECTIVITY = "connectivity"
    POWER = "power"
    GRID_STORAGE = "grid_storage"
    WATER = "water"
    ADOPTION = "adoption"
    WORKFORCE = "workforce"
    ECONOMIC_OUTCOMES = "economic_outcomes"


@dataclass(frozen=True, slots=True)
class LoadPolicy:
    """Immutable source authorization for one application rebuild."""

    refresh_sources: frozenset[RefreshSource] = frozenset()

    @classmethod
    def retained(cls) -> "LoadPolicy":
        return cls()

    @classmethod
    def refresh(cls, sources: Iterable[RefreshSource | str]) -> "LoadPolicy":
        normalized = frozenset(RefreshSource(str(source)) for source in sources)
        return cls(refresh_sources=normalized)

    @property
    def is_read_mode(self) -> bool:
        return not self.refresh_sources

    @property
    def is_explicit_refresh(self) -> bool:
        return bool(self.refresh_sources)

    def allows_live(self, source: RefreshSource | str) -> bool:
        return RefreshSource(str(source)) in self.refresh_sources

    def describe(self) -> dict:
        return {
            "mode": "retained" if self.is_read_mode else "explicit_refresh",
            "refresh_sources": sorted(source.value for source in self.refresh_sources),
            "network_allowed": self.is_explicit_refresh,
            "repository_snapshot_writes_allowed": self.is_explicit_refresh,
        }


def build_load_policy(
    *,
    force_yfinance_refresh: bool = False,
    force_edgar_refresh: bool = False,
    force_fred_refresh: bool = False,
    force_nyfed_refresh: bool = False,
    refresh_domain: str | None = None,
    refresh_domains: Iterable[str] | None = None,
) -> LoadPolicy:
    """Build the policy from explicit authorized refresh controls only.

    ``force_rebuild`` is deliberately absent: clearing caches or rebuilding the
    dashboard must never grant network access.
    """

    # Public deployments are immutable readers. Hidden controls, forged
    # session-state values, or a future caller must not be able to turn a
    # viewer request into provider traffic or repository writes.
    if not repository_writes_enabled():
        return LoadPolicy.retained()

    sources: set[RefreshSource] = set()
    if force_yfinance_refresh:
        sources.add(RefreshSource.YFINANCE)
    if force_edgar_refresh:
        sources.add(RefreshSource.EDGAR)
    if force_fred_refresh:
        sources.add(RefreshSource.FRED)
    if force_nyfed_refresh:
        sources.add(RefreshSource.NYFED)
    domain_requests = set(refresh_domains or ())
    if refresh_domain:
        domain_requests.add(refresh_domain)
    for domain in domain_requests:
        sources.add(RefreshSource(str(domain)))
    return LoadPolicy.refresh(sources) if sources else LoadPolicy.retained()
