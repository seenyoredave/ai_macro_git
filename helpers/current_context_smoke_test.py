"""Regression tests for the auditable, single-owner Current Context layer."""

from __future__ import annotations

from pathlib import Path
import json
import tempfile
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config.current_context_policy import (
    DOMAIN_CONTEXT_POLICY,
    assess_source,
    recent_development_copy_issues,
)
import loaders.current_context_discovery as discovery
from loaders.current_context_discovery import evaluate_item
from loaders.weekly_context_loader import (
    DOMAIN_KEYS,
    _assign_live_event_owners,
    load_current_context,
)
from rendering.read_markup import build_domain_read_html


def _fresh_event(event_id: str, date: str, priority: int, fact: str, *, domain="data_center") -> dict:
    return {
        "event_id": event_id,
        "event_date": date,
        "domain": domain,
        "event_type": "regulatory_order",
        "priority": priority,
        "verified_fact": fact,
        "platform_relevance": "The action changes near-term project assumptions",
        "source_name": "Example Infrastructure Commission",
        "source_label": "Example commission order",
        "source_url": f"https://example.gov/{event_id}",
        "source_type": "primary",
        "verification_status": "confirmed",
        "expires_after_days": 7,
        "surface": "domain",
        "secondary_domains": "",
        "sectors": "",
        "tickers": "",
        "status": "Ordered",
        "legal_status": "Order issued",
        "resolution_status": "recent",
        "resolved_date": "",
        "source_tier": "primary",
        "evidence_role": "official_statement",
        "persistent": "false",
        "record_origin": "test_fixture",
        "retrieved_at": "",
        "discovery_provider": "fixture",
        "discovery_query": "",
    }


def _item(title: str, source: str, link: str, *, published="2026-08-04", description="") -> dict:
    return {
        "title": title,
        "source_name": source,
        "source_url": "https://" + link.split("/")[2],
        "link": link,
        "published": pd.Timestamp(published),
        "description": description,
        "provider": "fixture",
    }


def main() -> None:
    context = load_current_context(as_of="2026-08-04", include_live=False)

    # Every substantive tab receives one compact row.  A real no-match is
    # permitted; a duplicated development is not.
    seen_event_ids: set[str] = set()
    seen_urls: set[str] = set()
    referenced_count = 0
    for domain in DOMAIN_KEYS:
        domain_context = context["by_domain"][domain]
        events = domain_context["events"]
        if len(events) != 1:
            raise AssertionError(f"{domain} should have exactly one compact Current Context row: {events}")
        event = events[0]
        if event.get("owner_domain") != domain:
            raise AssertionError(f"{domain} event lost explicit ownership: {event}")
        if event["event_id"] in seen_event_ids:
            raise AssertionError(f"An event is visible in more than one tab: {event['event_id']}")
        seen_event_ids.add(event["event_id"])
        source_url = str(event.get("source_url") or "")
        if source_url:
            referenced_count += 1
            if source_url in seen_urls:
                raise AssertionError(f"One source event is duplicated across tabs: {source_url}")
            seen_urls.add(source_url)
            if not domain_context["references"]:
                raise AssertionError(f"{domain} has a source URL but no rendered reference.")
    if referenced_count < 6:
        raise AssertionError("The retained snapshot is too sparse to demonstrate cross-domain coverage.")

    # Texas has one visible home: Data Center.  Secondary tags remain internal.
    texas = [
        event for event in context["by_domain"]["data_center"]["events"]
        if "texas" in str(event.get("verified_fact", "")).casefold()
    ]
    if texas:
        texas_event = texas[0]
        if texas_event.get("resolution_status") != "unresolved":
            raise AssertionError("The Texas audit does not separate announcement from pending implementation.")
        if not str(texas_event.get("source_url", "")).startswith("https://gov.texas.gov/"):
            raise AssertionError("The Texas audit is not grounded in its official referenced source.")
        if recent_development_copy_issues(texas_event.get("display", "")):
            raise AssertionError("The Texas audit lacks formal first-reference context.")
        if "Texas Governor Greg Abbott" not in str(texas_event.get("display", "")):
            raise AssertionError("The Texas audit lost jurisdiction and full-name context.")
        if "Public Utility Commission of Texas (PUCT)" not in str(texas_event.get("display", "")):
            raise AssertionError("PUCT is not expanded on first reference.")
        if "Electric Reliability Council of Texas (ERCOT)" not in str(texas_event.get("display", "")):
            raise AssertionError("ERCOT is not expanded on first reference.")
        for domain in ("power", "grid_storage", "water"):
            if any(event.get("event_id") == texas_event["event_id"] for event in context["by_domain"][domain]["events"]):
                raise AssertionError(f"The Texas event leaked into the {domain} read.")

    registry_text = (PROJECT_ROOT / "data" / "weekly_context_events.csv").read_text().casefold()
    if "power line" in registry_text or "scrap" in registry_text:
        raise AssertionError("An unverified transmission-line claim entered the retained event ledger.")
    if "record_origin" not in registry_text.splitlines()[0]:
        raise AssertionError("The retained event ledger does not disclose record provenance.")

    # Unresolved regulatory events remain eligible beyond an ordinary news window.
    if texas:
        later = load_current_context(as_of="2026-10-01", include_live=False)
        if later["by_domain"]["data_center"]["events"][0]["event_id"] != texas[0]["event_id"]:
            raise AssertionError("The unresolved Texas audit expired solely because it became older than seven days.")

    # A fresher, more material event can still displace an unresolved event.
    base = pd.read_csv(PROJECT_ROOT / "data" / "weekly_context_events.csv")
    extra = pd.DataFrame([
        _fresh_event("fresh-data-center-order", "2026-08-04", 180, "The commission ordered a new data-center interconnection standard"),
    ])
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.csv"
        pd.concat([base, extra], ignore_index=True).to_csv(path, index=False)
        displaced = load_current_context(as_of="2026-08-04", path=path, limit_per_domain=1, include_live=False)
        if displaced["by_domain"]["data_center"]["events"][0]["event_id"] != "fresh-data-center-order":
            raise AssertionError("A fresher material event did not displace the unresolved item.")

    # Source, relevance, and materiality gates produce explicit decisions—not
    # silent disappearance.
    current = pd.Timestamp("2026-08-04")
    accepted, accepted_audit = evaluate_item(
        _item(
            "Palantir reports earnings, raises annual revenue guidance as shares surge",
            "Reuters",
            "https://www.reuters.com/business/palantir-example-2026-08-04/",
            description="AI software revenue and market expectations changed after quarterly results.",
        ),
        domain="market",
        current=current,
        provider="fixture",
    )
    if accepted is None or accepted_audit["decision"] != "accepted":
        raise AssertionError(f"A material approved-source Market event was rejected: {accepted_audit}")

    for item, expected_reason in (
        (_item("AI company reports earnings and raises guidance", "Fox News", "https://www.foxnews.com/example"), "explicitly excluded"),
        (_item("AI company reports earnings and raises guidance", "The New York Times", "https://www.nytimes.com/example"), "requires corroboration"),
        (_item("Celebrity discusses artificial intelligence", "Reuters", "https://www.reuters.com/lifestyle/example"), "no domain relevance"),
        (_item("Investors debate the future of AI stocks", "Reuters", "https://www.reuters.com/business/example"), "no material action"),
    ):
        candidate, audit = evaluate_item(item, domain="market", current=current, provider="fixture")
        if candidate is not None or expected_reason not in audit["reason"]:
            raise AssertionError(f"Expected rejection containing {expected_reason!r}: {audit}")

    # Duplicate articles returned by several searches receive one owner.
    shared_url = "https://www.reuters.com/example-ai-results"
    assigned = _assign_live_event_owners({
        "market": [{
            "event_id": "shared", "domain": "market", "source_url": shared_url,
            "verified_fact": "Company reports earnings and raises guidance", "owner_score": 130,
            "rank_score": 130, "event_date": "2026-08-04",
        }],
        "adaptation": [{
            "event_id": "shared", "domain": "adaptation", "source_url": shared_url,
            "verified_fact": "Company reports earnings and raises guidance", "owner_score": 118,
            "rank_score": 118, "event_date": "2026-08-04",
        }],
    })
    if len(assigned["market"]) != 1 or assigned["adaptation"]:
        raise AssertionError("Live event ownership did not prevent cross-tab duplication.")

    # The refresh command writes a complete eleven-domain manifest and candidate
    # audit even when some domains legitimately return no qualifying event.
    original_discover = discovery.discover_domain
    try:
        def fake_discover(domain: str, *, as_of=None):
            if domain == "market":
                event = dict(accepted)
                event["domain"] = domain
                event["owner_domain"] = domain
                audit = dict(accepted_audit)
                audit["domain_query"] = domain
                return [event], [audit], [discovery.FetchStatus(domain, "fixture", "fixture query", 3, "ok", 1, "")]
            return [], [], [discovery.FetchStatus(domain, "fixture", "fixture query", 7, "ok", 0, "")]
        discovery.discover_domain = fake_discover
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = discovery.refresh_current_context(
                as_of="2026-08-04",
                audit_path=root / "audit.csv",
                manifest_path=root / "manifest.json",
                registry_path=root / "events.csv",
                merge_registry=False,
            )
            persisted = json.loads((root / "manifest.json").read_text())
            if set(persisted["domains"]) != set(DOMAIN_KEYS) or len(persisted["fetch_status"]) != len(DOMAIN_KEYS):
                raise AssertionError("Refresh manifest did not document every domain search.")
            if not (root / "audit.csv").exists() or manifest["selected"]["market"][0]["event_id"] != accepted["event_id"]:
                raise AssertionError("Refresh audit or selected provenance was not persisted.")
    finally:
        discovery.discover_domain = original_discover

    if recent_development_copy_issues("Governor Abbott directed ERCOT to review the queue") == []:
        raise AssertionError("Recent Developments accepted ambiguous official/regional shorthand.")
    if recent_development_copy_issues(
        "Texas Governor Greg Abbott directed the Electric Reliability Council of Texas (ERCOT) to review the queue"
    ):
        raise AssertionError("Recent Developments rejected properly contextualized first references.")

    if DOMAIN_CONTEXT_POLICY["market"]["cadence"] != "weekday" or DOMAIN_CONTEXT_POLICY["market"]["lookback_days"] > 3:
        raise AssertionError("Market Current Context is not tuned to weekday information cadence.")

    for blocked in ("Fox News", "MSNBC", "HuffPost"):
        if assess_source(blocked, f"https://{blocked.replace(' ', '').lower()}.com").auto_eligible:
            raise AssertionError(f"Blocked source became eligible: {blocked}")
    if assess_source("The New York Times", "https://www.nytimes.com").auto_eligible:
        raise AssertionError("The manual-review source path became unattendedly eligible.")
    for approved, url in (
        ("The Wall Street Journal", "https://www.wsj.com"),
        ("Reuters", "https://www.reuters.com"),
        ("Office of the Texas Governor", "https://gov.texas.gov"),
    ):
        if not assess_source(approved, url).auto_eligible:
            raise AssertionError(f"Approved source was rejected: {approved}")

    market_context = context["by_domain"]["market"]
    event = market_context["events"][0]
    read = {
        "headline": "Current results changed the market signal.",
        "summary": "The retained market data remain primary; the event layer explains why the latest return contribution moved.",
        "watchpoint": "Watch whether earnings-driven gains broaden beyond the leading names.",
        "confidence": "high",
        "current_context_items": [{
            "text": event["display"],
            "reference_number": event.get("reference_number"),
            "source_url": event.get("source_url", ""),
        }],
        "references": market_context["references"],
    }
    markup = build_domain_read_html(read, label="Market Read", accent_color="#a78bfa")
    if "Watchpoint" in markup:
        raise AssertionError("Watchpoint leaked back into the visible Read component.")
    if not (markup.index("Recent developments") < markup.index("References")):
        raise AssertionError("Current Context did not retain the compact read order.")
    if market_context["references"] and ('<a class="rm-domain-read-context-citation"' not in markup or "[1]" not in markup):
        raise AssertionError("Current Context is missing its inline source citation.")
    if "<ol" in markup or "<li" in markup:
        raise AssertionError("References regressed to a stacked list.")

    print(
        "PASS  Auditable Current Context · eleven-domain manifest · explicit rejection reasons · "
        "single-owner display · legitimate no-match supported"
    )


if __name__ == "__main__":
    main()
