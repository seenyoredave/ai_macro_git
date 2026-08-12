"""Regression contract for Current Context Reader-floor and continuity state."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import loaders.current_context_discovery as discovery
from loaders.current_context_news import DOMAIN_KEYS


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _fake_event(domain: str, index: int) -> dict:
    return {
        "event_id": f"reader-floor-{domain}-{index}",
        "event_date": "2026-08-11",
        "domain": domain,
        "owner_domain": domain,
        "event_type": "reported_development",
        "priority": 100 - index,
        "rank_score": 100 - index,
        "owner_score": 100 - index,
        "qualification_tier": "A",
        "qualification_tier_label": "Preferred",
        "verified_fact": f"{domain.title()} firm UniqueActor{index} announced a distinct current development involving $10 billion and Project{index}.",
        "source_name": "Reuters",
        "source_label": "Reuters",
        "source_url": f"https://www.reuters.com/business/{domain}-{index}",
        "source_type": "news",
        "verification_status": "reported",
        "grounding_status": "grounded",
        "grounding_version": discovery.GROUNDING_VERSION,
        "source_text_method": "fixture_body",
        "source_text_chars": 800,
        "source_evidence_hash": f"fixture-{domain}-{index}",
        "retrieved_at": "2026-08-11T18:00:00+00:00",
        "discovery_provider": "fixture",
    }


def main() -> None:
    # The production registry is stored as CSV, so its dates arrive as strings.
    # Coverage evaluation must normalize that storage representation before it
    # applies the Reader temporal gate.  This reproduces the v7.7.0 failure path.
    shipped_registry = ROOT / "data" / "weekly_context_events.csv"
    shipped_domains = discovery._retained_reader_domains(
        shipped_registry, current=pd.Timestamp("2026-08-11")
    )
    require(isinstance(shipped_domains, set), "Raw CSV retained-domain evaluation did not return a domain set.")

    # Coverage may not be declared from a pre-Reader intermediate population.
    domains = ["market", "finance", "power", "grid_storage", "adoption", "workforce"]
    original_discover = discovery.discover_domain
    original_reader_gate = discovery._event_survives_reader_contract
    try:
        def fake_discover(domain: str, *, as_of=None):
            if domain not in domains:
                return [], [], [discovery.FetchStatus(domain, "fixture", "fixture", 7, "ok", 0, "")]
            event = _fake_event(domain, domains.index(domain))
            audit = {
                "event_id": event["event_id"],
                "domain_query": domain,
                "decision": "accepted",
                "grounding_status": "grounded",
                "reason": "fixture",
            }
            return [event], [audit], [discovery.FetchStatus(domain, "fixture", "fixture", 7, "ok", 1, "")]

        discovery.discover_domain = fake_discover
        discovery._event_survives_reader_contract = lambda event, **kwargs: event.get("domain") != "workforce"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = discovery.refresh_current_context(
                as_of="2026-08-11",
                audit_path=root / "audit.csv",
                manifest_path=root / "manifest.json",
                registry_path=root / "events.csv",
                merge_registry=False,
            )
            require(manifest["coverage"]["target_met"] is False, f"Pre-Reader six-domain selection falsely satisfied the floor: {manifest['coverage']}")
            persisted = json.loads((root / "manifest.json").read_text())
            rejected = pd.read_csv(root / "audit.csv")
            row = rejected.loc[rejected["event_id"] == "reader-floor-workforce-5"].iloc[0]
            require(row["decision"] == "rejected_reader_contract", f"Final Reader rejection was not auditable: {row.to_dict()}")
            require(persisted["coverage"]["target_met"] is False, "Persisted manifest disagreed with final Reader coverage.")
    finally:
        discovery.discover_domain = original_discover
        discovery._event_survives_reader_contract = original_reader_gate

    # Retained continuity uses older rows only as discovery leads.  Current
    # rows do not incur another fetch, and the ten-day ceiling still applies.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        registry = root / "registry.csv"
        retrospective = root / "retrospective.csv"
        pd.DataFrame([
            {
                "event_id": "current-live",
                "event_date": "2026-08-10",
                "domain": "market",
                "priority": 120,
                "verified_fact": "Current live event.",
                "source_name": "Reuters",
                "source_url": "https://www.reuters.com/current-live",
                "record_origin": "automated_discovery",
                "grounding_status": "grounded",
                "grounding_version": discovery.GROUNDING_VERSION,
            },
            {
                "event_id": "older-engine",
                "event_date": "2026-08-04",
                "domain": "market",
                "priority": 119,
                "verified_fact": "Older engine event.",
                "source_name": "Reuters",
                "source_url": "https://www.reuters.com/older-engine",
                "record_origin": "automated_discovery",
                "grounding_status": "grounded",
                "grounding_version": "2.9",
            },
        ]).to_csv(registry, index=False)
        pd.DataFrame([
            {
                "event_id": "retrospective-current",
                "event_date": "2026-08-03",
                "domain": "grid_storage",
                "priority": 118,
                "verified_fact": "Retrospective event inside hard window.",
                "source_name": "Reuters",
                "source_url": "https://www.reuters.com/retrospective-current",
            },
            {
                "event_id": "retrospective-expired",
                "event_date": "2026-07-30",
                "domain": "finance",
                "priority": 117,
                "verified_fact": "Expired retrospective event.",
                "source_name": "Reuters",
                "source_url": "https://www.reuters.com/retrospective-expired",
            },
        ]).to_csv(retrospective, index=False)
        seeds = discovery._retained_continuity_seeds(
            current=pd.Timestamp("2026-08-11"),
            registry_path=registry,
            retrospective_path=retrospective,
        )
        ids = {item["event_id"] for items in seeds.values() for item in items}
        require("current-live" not in ids, "Current-version retained event was needlessly scheduled for re-grounding.")
        require("older-engine" in ids, "Older reconstruction event was not offered for source re-grounding.")
        require("retrospective-current" in ids, "Still-current retrospective event was not offered for source re-grounding.")
        require("retrospective-expired" not in ids, "Ten-day hard window was bypassed by continuity recovery.")

    # The shipped retrospective corpus specifically retains Palantir Q2 as a
    # candidate identity; v7.7 must give that event a source-grounded path back.
    shipped_retrospective = ROOT / "audit" / "current_context_retrospective" / "retired_unproven_registry_rows_v730.csv"
    with tempfile.TemporaryDirectory() as tmp:
        empty_registry = Path(tmp) / "empty.csv"
        seeds = discovery._retained_continuity_seeds(
            current=pd.Timestamp("2026-08-11"),
            registry_path=empty_registry,
            retrospective_path=shipped_retrospective,
        )
        ids = {item["event_id"] for items in seeds.values() for item in items}
        require("palantir-q2-2026-08-03" in ids, "Palantir Q2 lacks a continuity revalidation path.")

    # Retained domains satisfy the same six-domain operating floor as newly
    # acquired domains; the engine need not replace six domains every morning.
    assigned = {domain: [] for domain in DOMAIN_KEYS}
    for idx, domain in enumerate(("power", "grid_storage")):
        assigned[domain] = [_fake_event(domain, idx)]
    _, coverage = discovery._select_progressive_coverage(
        assigned,
        retained_domains={"market", "finance", "adoption", "workforce"},
    )
    require(coverage["target_met"] is True, f"Valid retained coverage was ignored: {coverage}")
    require(coverage["selected_domain_count"] == 6, f"Reader coverage did not reach six domains: {coverage}")
    require(coverage["new_selected_domain_count"] == 2, f"Fresh-selection visibility is incorrect: {coverage}")

    print("PASS  Current Context state contract · raw-CSV normalization · Reader-final 6-domain floor · retained continuity revalidation · Palantir recovery path")


if __name__ == "__main__":
    main()
