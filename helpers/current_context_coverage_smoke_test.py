"""Focused regression contract for v7.3 Current Context coverage and provenance."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.read_context import attach_current_context
from config.current_context_policy import (
    CURRENT_CONTEXT_COVERAGE_TARGET,
    CURRENT_CONTEXT_HARD_WINDOW_DAYS,
    CURRENT_CONTEXT_PREFERRED_WINDOW_DAYS,
    CURRENT_CONTEXT_QUALIFICATION_TIERS,
    current_context_max_lookback_days,
)
from loaders.current_context_discovery import _merged_registry_frame, _select_progressive_coverage, evaluate_item
from loaders.current_context_loader import _context_window_start, _macro_ranked_events
from loaders.current_context_registry import _curated_source_allowed


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def event(event_id: str, domain: str, score: float, *, tier: str = "A", date: str = "2026-08-11") -> dict:
    return {
        "event_id": event_id,
        "event_date": date,
        "domain": domain,
        "owner_domain": domain,
        "rank_score": score,
        "priority": score,
        "qualification_tier": tier,
        "verification_status": "reported",
        "status": "Reported",
        "verified_fact": f"{domain} current development {event_id}",
        "display": f"{domain} current development {event_id}",
        "source_name": "Reuters",
        "source_label": "Reuters",
        "source_url": f"https://www.reuters.com/{event_id}",
    }


def main() -> None:
    require(CURRENT_CONTEXT_PREFERRED_WINDOW_DAYS == 7, "Preferred Current Context window is not seven days.")
    require(CURRENT_CONTEXT_HARD_WINDOW_DAYS == 10, "Hard Current Context window is not ten days.")
    tier_days = {tier.key: tier.lookback_days for tier in CURRENT_CONTEXT_QUALIFICATION_TIERS}
    require(tier_days == {"A": 7, "B": 7, "C": 10, "D": 10, "E": 10}, f"Qualification windows drifted: {tier_days}")
    for domain in ("market", "finance", "compute", "data_center", "connectivity", "power", "grid_storage", "water", "adoption", "workforce", "economic_impact"):
        require(current_context_max_lookback_days(domain) == 10, f"{domain} exceeds or misses the ten-day hard ceiling.")

    current = pd.Timestamp("2026-08-11")
    recent, recent_audit = evaluate_item(
        {
            "title": "Microsoft launches $10 billion bond offering to finance AI data centers",
            "source_name": "Reuters",
            "source_url": "https://www.reuters.com",
            "link": "https://www.reuters.com/business/example-recent",
            "published": pd.Timestamp("2026-08-05"),
            "description": "The financing supports artificial-intelligence infrastructure and data-center investment.",
        },
        domain="finance",
        current=current,
        provider="google_news_rss",
    )
    require(recent is not None and recent.get("qualification_tier") == "A", f"Six-day candidate did not clear preferred tier: {recent_audit}")

    expanded, expanded_audit = evaluate_item(
        {
            "title": "Microsoft launches $10 billion bond offering to finance AI data centers",
            "source_name": "Reuters",
            "source_url": "https://www.reuters.com",
            "link": "https://www.reuters.com/business/example-expanded",
            "published": pd.Timestamp("2026-08-02"),
            "description": "The financing supports artificial-intelligence infrastructure and data-center investment.",
        },
        domain="finance",
        current=current,
        provider="google_news_rss",
    )
    require(expanded is not None and expanded.get("qualification_tier") in {"C", "D", "E"}, f"Nine-day candidate did not enter the expanded ladder: {expanded_audit}")

    expired, expired_audit = evaluate_item(
        {
            "title": "Microsoft launches $10 billion bond offering to finance AI data centers",
            "source_name": "Reuters",
            "source_url": "https://www.reuters.com",
            "link": "https://www.reuters.com/business/example-expired",
            "published": pd.Timestamp("2026-08-01"),
            "description": "The financing supports artificial-intelligence infrastructure and data-center investment.",
        },
        domain="finance",
        current=current,
        provider="google_news_rss",
    )
    require(expired is None, f"Ten-day-old candidate escaped the hard window: {expired_audit}")

    domains = ("market", "finance", "compute", "data_center", "power", "water")
    tiers = ("A", "A", "B", "C", "D", "E")
    assigned = {domain: [event(f"evt-{domain}", domain, 100 - idx, tier=tiers[idx])] for idx, domain in enumerate(domains)}
    for domain in ("connectivity", "grid_storage", "adoption", "workforce", "economic_impact"):
        assigned[domain] = []
    selected, coverage = _select_progressive_coverage(assigned)
    require(coverage.get("target_met") is True, f"Six-domain floor was not met: {coverage}")
    require(coverage.get("selected_domain_count") == CURRENT_CONTEXT_COVERAGE_TARGET, f"Coverage count drifted: {coverage}")
    require(coverage.get("tier_reached") == "E", f"Ladder did not relax progressively to the required tier: {coverage}")
    require(sum(bool(selected.get(domain)) for domain in selected) == 6, "Progressive selection did not retain six domains.")

    sparse_assigned = {domain: events for domain, events in assigned.items() if domain != "water"}
    sparse_assigned["water"] = []
    _, sparse_coverage = _select_progressive_coverage(sparse_assigned)
    require(sparse_coverage.get("target_met") is False, "Coverage contract falsely reported six domains.")

    macro_candidates = [
        event("f1", "finance", 110),
        event("f2", "finance", 109),
        event("m1", "market", 108),
        event("m2", "market", 107),
        event("p1", "power", 106),
        event("g1", "grid_storage", 105),
    ]
    macro = _macro_ranked_events(macro_candidates, limit=3)
    require(len(macro) == 3, f"Macro Current Context did not produce three headlines: {macro}")
    counts: dict[str, int] = {}
    mf = 0
    for item in macro:
        domain = str(item.get("domain") or "")
        counts[domain] = counts.get(domain, 0) + 1
        if domain in {"market", "finance"}:
            mf += 1
    require(max(counts.values()) <= 2, f"One domain monopolized the macro top three: {counts}")
    require(mf <= 2, f"Market/Finance monopolized the macro top three: {macro}")
    require(any(str(item.get("domain")) not in {"market", "finance"} for item in macro), "Macro top three lacks a non-Market/Finance development.")

    packet = {"events": macro, "references": []}
    attached = attach_current_context({"references": []}, packet, limit=3)
    require(len(attached.get("current_context_items") or []) == 3, "Read attachment truncated the macro top three.")
    require(_context_window_start([event("old", "power", 1, date="2026-08-03")], current) == "2026-08-03", "Packet window does not reflect its oldest retained event.")

    legacy_ok, legacy_tier, _ = _curated_source_allowed({
        "record_origin": "retained_verified_snapshot",
        "source_name": "Reuters",
        "source_url": "https://www.reuters.com/legacy",
        "source_type": "news",
        "verification_status": "confirmed",
    })
    require(not legacy_ok and legacy_tier == "legacy_unproven", "Unproven legacy Current Context remained Reader-eligible.")

    with tempfile.TemporaryDirectory() as tmp:
        registry = Path(tmp) / "weekly_context_events.csv"
        pd.DataFrame([{
            "event_id": "legacy-1",
            "event_date": "2026-08-05",
            "domain": "water",
            "priority": 50,
            "verified_fact": "Legacy Water sentence.",
            "source_name": "Reuters",
            "source_label": "Reuters",
            "source_url": "https://www.reuters.com/legacy-water",
            "source_type": "news",
            "verification_status": "confirmed",
            "record_origin": "retained_verified_snapshot",
        }]).to_csv(registry, index=False)
        modern = event("modern-1", "water", 95, tier="D")
        modern.update({
            "verified_fact": "A source-grounded Water development is current.",
            "source_name": "Reuters",
            "source_label": "Reuters",
            "source_url": "https://www.reuters.com/modern-water",
            "source_type": "news",
            "verification_status": "reported",
            "grounding_status": "grounded",
            "grounding_version": "3.0",
            "source_text_method": "article_body",
            "source_text_chars": 500,
            "source_evidence_hash": "abcdef1234567890",
            "retrieved_at": "2026-08-11T18:00:00+00:00",
        })
        combined, _ = _merged_registry_frame({**{domain: [] for domain in ("market", "finance", "compute", "data_center", "connectivity", "power", "grid_storage", "water", "adoption", "workforce", "economic_impact")}, "water": [modern]}, path=registry, retrieved_at="2026-08-11T18:00:00+00:00")
        require(combined is not None, "Qualified registry merge produced no frame.")
        require("legacy-1" not in set(combined["event_id"].astype(str)), "Successful v3 registry publication retained an unproven legacy row.")
        require("modern-1" in set(combined["event_id"].astype(str)), "Qualified modern row disappeared during provenance cleanup.")

    evidence_text = (ROOT / "rendering" / "evidence.py").read_text(encoding="utf-8")
    for phrase in (
        "independently discovers and source-grounds recent developments",
        "progressive quality ladder",
        "ten-day window",
        "at least six analytical domains",
        "strongest seven-day candidates are preferred",
    ):
        require(phrase in evidence_text, f"Evidence statement lost active Current Context policy: {phrase}")

    print("PASS  Current Context · 7-day preferred · 10-day hard window · six-domain floor · diverse macro top three · proven-source Reader gate")


if __name__ == "__main__":
    main()
