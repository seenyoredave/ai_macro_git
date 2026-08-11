"""Regression tests for the auditable, single-owner Current Context layer."""

from __future__ import annotations

from pathlib import Path
import json
import tempfile
import sys
import types

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

if "streamlit" not in sys.modules:
    fake_streamlit = types.ModuleType("streamlit")
    def _cache_data(*args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda function: function
    fake_streamlit.cache_data = _cache_data
    sys.modules["streamlit"] = fake_streamlit

from config.current_context_policy import (
    DOMAIN_CONTEXT_POLICY,
    DOMAIN_VOCABULARY,
    assess_source,
    domain_news_queries,
    domain_owner_terms,
    domain_relevance_terms,
    domain_synthesis_terms,
    domain_topic_anchors,
    recent_development_copy_issues,
)
import helpers.atomic_io as atomic_io
import loaders.current_context_discovery as discovery
from loaders.current_context_discovery import evaluate_item
import loaders.current_context_grounding as grounding
import loaders.current_context_registry as context_registry
from loaders.current_context_grounding import GROUNDING_VERSION, SourceDocument, fetch_source_document, ground_candidate
from loaders.current_context_daily import (
    context_packet_id,
    finalize_context_report,
    load_retained_context_snapshot,
)
from loaders.current_context_news import DOMAIN_KEYS, _assign_event_owners
from loaders.current_context_loader import load_current_context
from rendering.read_markup import build_domain_read_html, domain_read_label
from analytics.read_context import attach_current_context as _attach_current_context


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
    # Multi-file Current Context publication is one application transaction:
    # an exception after the first replacement must restore every prior target.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        first = root / "first.txt"
        second = root / "second.txt"
        first.write_bytes(b"old-first")
        second.write_bytes(b"old-second")
        original_commit = atomic_io._commit
        commit_calls = {"count": 0}

        def fail_second_commit(temp_path, target):
            commit_calls["count"] += 1
            if commit_calls["count"] == 2:
                raise OSError("fixture commit failure")
            return original_commit(temp_path, target)

        atomic_io._commit = fail_second_commit
        try:
            try:
                atomic_io.atomic_write_bundle(
                    {first: b"new-first", second: b"new-second"},
                    transaction_key=root / ".current_context_refresh",
                )
            except OSError as exc:
                if "fixture commit failure" not in str(exc):
                    raise
            else:
                raise AssertionError("Atomic bundle fixture did not exercise rollback.")
        finally:
            atomic_io._commit = original_commit
        if first.read_bytes() != b"old-first" or second.read_bytes() != b"old-second":
            raise AssertionError("Current Context bundle rollback left a partial commit.")

    context = load_current_context(as_of="2026-08-04")

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
        later = load_current_context(as_of="2026-10-01")
        if later["by_domain"]["data_center"]["events"][0]["event_id"] != texas[0]["event_id"]:
            raise AssertionError("The unresolved Texas audit expired solely because it became older than seven days.")

    # A fresher, more material event can still displace an unresolved event.
    base = pd.read_csv(PROJECT_ROOT / "data" / "weekly_context_events.csv")
    extra = pd.DataFrame([
        _fresh_event("fresh-data-center-order", "2026-08-04", 180, "Example Infrastructure Commission ordered a new data-center interconnection standard"),
    ])
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.csv"
        pd.concat([base, extra], ignore_index=True).to_csv(path, index=False)
        displaced = load_current_context(as_of="2026-08-04", path=path, limit_per_domain=1)
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
    if accepted is None or accepted_audit["decision"] != "metadata_qualified":
        raise AssertionError(f"A material approved-source Market event was rejected: {accepted_audit}")

    for item, expected_reason in (
        (_item("AI company reports earnings and raises guidance", "Fox News", "https://www.foxnews.com/example"), "explicitly excluded"),
        (_item("AI company reports earnings and raises guidance", "The New York Times", "https://www.nytimes.com/example"), "requires corroboration"),
        (_item("Celebrity discusses artificial intelligence", "Reuters", "https://www.reuters.com/lifestyle/example"), "no domain relevance"),
        (_item("Investors debate the future of AI stocks", "Reuters", "https://www.reuters.com/business/example"), "insufficient domain materiality"),
    ):
        candidate, audit = evaluate_item(item, domain="market", current=current, provider="fixture")
        if candidate is not None or expected_reason not in audit["reason"]:
            raise AssertionError(f"Expected rejection containing {expected_reason!r}: {audit}")

    # Representative Market/Finance business-news fixtures clear the revised
    # domain rules, while a generic market recap does not become AI context.
    onsemi, onsemi_audit = evaluate_item(
        _item(
            "ON Semiconductor reports higher profit and revenue on growing AI data center business",
            "The Wall Street Journal",
            "https://www.wsj.com/business/earnings/on-semiconductor-example",
        ),
        domain="market", current=current, provider="fixture",
    )
    if onsemi is None or onsemi_audit["decision"] != "metadata_qualified":
        raise AssertionError(f"AI-linked semiconductor earnings should qualify for Market: {onsemi_audit}")

    financing, financing_audit = evaluate_item(
        _item(
            "Banks to offload $15bn of debt for Anthropic data centre backed by Google",
            "Financial Times",
            "https://www.ft.com/content/anthropic-data-centre-example",
        ),
        domain="finance", current=current, provider="fixture",
    )
    if financing is None or financing_audit["decision"] != "metadata_qualified":
        raise AssertionError(f"Material AI infrastructure financing should qualify for Finance: {financing_audit}")

    generic, generic_audit = evaluate_item(
        _item(
            "Stock market rallies on oil, yields and big earnings",
            "Investor's Business Daily",
            "https://www.investors.com/market-trend/generic-weekly-review",
        ),
        domain="market", current=current, provider="fixture",
    )
    if generic is not None or "domain anchor" not in generic_audit["reason"]:
        raise AssertionError(f"Generic market recap leaked into AI Macro Market context: {generic_audit}")

    preview, preview_audit = evaluate_item(
        _item(
            "Wall St Week Ahead Inflation data to test record-setting US stocks, Fed rate views",
            "Reuters",
            "https://www.reuters.com/markets/week-ahead-example",
        ),
        domain="finance", current=current, provider="fixture",
    )
    if preview is not None or "preview/calendar" not in preview_audit["reason"]:
        raise AssertionError(f"Week-ahead preview leaked into Finance Current Context: {preview_audit}")

    unrelated_private_credit, unrelated_audit = evaluate_item(
        _item(
            "Star Mountain Capital closes collateralized fund obligation for lower middle-market private credit",
            "Business Wire",
            "https://www.businesswire.com/news/home/private-credit-example",
        ),
        domain="finance", current=current, provider="fixture",
    )
    if unrelated_private_credit is not None or "domain anchor" not in unrelated_audit["reason"]:
        raise AssertionError(f"Unrelated private-credit transaction leaked into AI Macro Finance: {unrelated_audit}")

    # Clump C applies the same transparent 7-day/materiality grammar to every
    # remaining domain.  Each fixture must clear its own vocabulary rather than
    # a universal action-word score.
    domain_fixtures = {
        "compute": "Nvidia secures additional HBM capacity for AI accelerators",
        "data_center": "Virginia approves permit for 1.2 GW data center campus",
        "connectivity": "Google begins construction of submarine cable linking new data center markets",
        "power": "Utility signs power purchase agreement to serve new AI data center load",
        "grid_storage": "Regional grid operator approves transmission upgrade for data center interconnection",
        "water": "Arizona approves water reuse permit for new data center campus",
        "adoption": "Survey shows enterprise AI adoption moved into production deployment",
        "workforce": "AI infrastructure hiring accelerates as data center operators add jobs",
        "economic_impact": "Study finds AI investment lifted labor productivity at software firms",
    }
    for domain, title in domain_fixtures.items():
        candidate, audit = evaluate_item(
            _item(title, "Reuters", f"https://www.reuters.com/business/{domain}-example"),
            domain=domain,
            current=current,
            provider="fixture",
        )
        if candidate is None or audit["decision"] != "metadata_qualified":
            raise AssertionError(f"{domain} did not inherit the Clump C evidence grammar: {audit}")
        policy = DOMAIN_CONTEXT_POLICY[domain]
        if int(policy.get("lookback_days") or 0) != 7 or "minimum_score" in policy or int(policy.get("max_items") or 0) != 2:
            raise AssertionError(f"{domain} retained old score/window behavior: {policy}")

    # Metadata qualification is only a nomination.  Reader-facing copy must be
    # grounded in the underlying source body and must add evidence beyond the
    # headline itself.  Generic/topic pieces and irrelevant physical projects
    # fail here even if their titles matched the discovery vocabulary.
    def _doc(title: str, body: str, *, published_date="2026-08-04", modified_date="", url="https://www.reuters.com/business/source-grounding"):
        return SourceDocument(
            url, url, title, "", body, "fixture_body", "", published_date, modified_date
        )

    grid_meta, _ = evaluate_item(
        _item(
            "California renewable curtailment rises as transmission constraints deepen",
            "Reuters",
            "https://www.reuters.com/business/grid-grounding",
            description="Renewable curtailment and grid congestion in California.",
        ),
        domain="grid_storage", current=current, provider="fixture",
    )
    grounded_grid, grid_grounding = ground_candidate(
        grid_meta, domain="grid_storage",
        fetcher=lambda *a, **k: _doc(
            "California renewable curtailment rises as transmission constraints deepen",
            "California curtailed 4.5 million MWh of renewable generation in the first half of 2026, already exceeding the total curtailed during 2025. Grid operators reported that transmission bottlenecks and insufficient storage contributed to the losses.",
        ),
    )
    if grounded_grid is None or "4.5 million MWh" not in grounded_grid.get("verified_fact", ""):
        raise AssertionError(f"Source-grounded Grid fact was not built from source evidence: {grid_grounding}")
    if grounded_grid.get("verified_fact") == grid_meta.get("discovery_title"):
        raise AssertionError("Reader-facing Grid copy merely repeated the discovery headline.")
    if "transmission and storage" not in grounded_grid.get("platform_relevance", ""):
        raise AssertionError("Source-grounded Grid synthesis lost the fact -> consequence grammar.")

    # Materiality precedes extraction. A Market article can be genuinely AI-
    # relevant and still fail the Market significance boundary. Axon is the
    # regression case: valid company evidence, insufficient broad-market weight
    # absent a major repricing or systemically important issuer/read-through.
    axon_meta, axon_audit = evaluate_item(
        _item(
            "Axon tops Q2 earnings forecasts and raises outlook on AI software demand",
            "Investor's Business Daily",
            "https://www.investors.com/news/axon-market-significance-example/",
            description="Axon earnings, guidance and AI software revenue growth.",
        ),
        domain="market", current=current, provider="fixture",
    )
    if axon_meta is None:
        raise AssertionError(f"Axon should clear AI/Market metadata before the significance gate: {axon_audit}")
    axon_event, axon_grounding = ground_candidate(
        axon_meta, domain="market",
        fetcher=lambda *a, **k: _doc(
            "Axon tops Q2 earnings forecasts and raises outlook on AI software demand",
            "Axon Enterprise, an S&P 500 maker of public-safety equipment and software, topped second-quarter earnings forecasts and raised its full-year outlook as revenue increased 35% amid stronger demand for its AI Era software bundle. Shares fell 6% after the report as investors weighed the growth against lower gross margins.",
            url="https://www.investors.com/news/axon-market-significance-example/",
        ),
    )
    if axon_event is not None or "Market-level significance" not in axon_grounding.reason:
        raise AssertionError(f"AI-relevant but non-market-moving company news consumed a Market slot: {axon_grounding}")

    # A large public-market reaction can elevate a non-megacap company event to
    # Market significance when the source ties that reaction to realized AI-linked
    # operating results. This protects the Airbnb proof-of-concept behavior.
    airbnb_meta, airbnb_audit = evaluate_item(
        _item(
            "Airbnb shares surge after stronger growth and raised outlook tied to AI",
            "CNBC",
            "https://www.cnbc.com/2026/08/07/chesky-airbnb-ai-earnings.html",
            description="Airbnb earnings, guidance and a large share-price reaction tied to AI-driven growth.",
        ),
        domain="market", current=current, provider="fixture",
    )
    if airbnb_meta is None:
        raise AssertionError(f"Airbnb Market metadata unexpectedly failed: {airbnb_audit}")
    airbnb_event, airbnb_grounding = ground_candidate(
        airbnb_meta, domain="market",
        fetcher=lambda *a, **k: _doc(
            "Airbnb shares surge after stronger growth and raised outlook tied to AI",
            "Airbnb shares surged 15% Friday after the company delivered one of its strongest growth quarters in years and raised its full-year outlook. Chief Executive Brian Chesky said artificial intelligence helped improve product development and operating execution as revenue accelerated.",
            url="https://www.cnbc.com/2026/08/07/chesky-airbnb-ai-earnings.html",
        ),
    )
    if airbnb_event is None or "15%" not in airbnb_event.get("verified_fact", ""):
        raise AssertionError(f"Large AI-linked Market repricing no longer survives the significance gate: {airbnb_grounding}")
    bad_reader_phrases = ("because the evidence", "direct test of whether", "selection threshold", "qualifies because")
    if any(phrase in airbnb_event.get("platform_relevance", "").casefold() for phrase in bad_reader_phrases):
        raise AssertionError(f"Selection rationale leaked into Market Reader prose: {airbnb_event.get('platform_relevance')}")

    # A recent article is not enough; the chosen development itself must be
    # current. Historical context may support a current event, but a 1989-2021
    # rate move cannot become a 2026 Recent Development merely because the page
    # was published this week.
    fossil_meta, fossil_audit = evaluate_item(
        _item(
            "The Fed's new philosophy could be a recipe for interest-rate volatility",
            "Morningstar",
            "https://www.morningstar.com/economy/feds-new-philosophy-example",
            description="Federal Reserve rates and long-term Treasury yields.",
        ),
        domain="finance", current=current, provider="fixture",
    )
    if fossil_meta is None:
        raise AssertionError(f"Historical-context fixture should reach source grounding: {fossil_audit}")
    fossil_event, fossil_grounding = ground_candidate(
        fossil_meta, domain="finance",
        fetcher=lambda *a, **k: _doc(
            "The Fed's new philosophy could be a recipe for interest-rate volatility",
            "From June 1989 to June 2021, the 10-year Treasury yield fell from about 8.5% to 1.5%. Investors are debating whether the Federal Reserve's evolving philosophy could produce more rate volatility in coming years.",
            url="https://www.morningstar.com/economy/feds-new-philosophy-example",
        ),
    )
    if fossil_event is not None or "historical context" not in fossil_grounding.reason:
        raise AssertionError(f"Historical Treasury context was promoted into a current Finance development: {fossil_grounding}")

    # A current interview can contain individually plausible historical and
    # financing claims without containing a material Current Context event. The
    # engine should back out rather than salvage a convenient number from a
    # commentary minefield.
    paulson_minefield_meta, paulson_minefield_audit = evaluate_item(
        _item(
            "Paulson compares today's market with earlier speculative periods",
            "CNBC",
            "https://www.cnbc.com/2026/08/03/paulson-market-interview-example.html",
            description="Market valuation, margin trading, AI bond issuance and Treasury yields.",
        ),
        domain="finance", current=current, provider="fixture",
    )
    if paulson_minefield_meta is None:
        raise AssertionError(f"Minefield fixture should reach source grounding before being rejected: {paulson_minefield_audit}")
    paulson_minefield_event, paulson_minefield_grounding = ground_candidate(
        paulson_minefield_meta, domain="finance",
        fetcher=lambda *a, **k: _doc(
            "Paulson compares today's market with earlier speculative periods",
            "Hank Paulson said in an interview that current market fundamentals reminded him of November 1999 and cautioned about retail margin trading. He discussed growing corporate bond issuance by Google, OpenAI, Meta and Haagen Daas to finance AI expansion. Paulson also said he had not seen a yield curve like this since before June 1989, when the 10-year Treasury yield approached 9%.",
            url="https://www.cnbc.com/2026/08/03/paulson-market-interview-example.html",
        ),
    )
    if paulson_minefield_event is not None:
        raise AssertionError(f"Commentary minefield was mined for a convenient Finance fact: {paulson_minefield_event}")

    current_yield_meta, current_yield_audit = evaluate_item(
        _item(
            "10-year Treasury yield rises sharply as financing conditions tighten",
            "Reuters",
            "https://www.reuters.com/markets/rates/current-yield-example",
            description="Treasury yields and financing conditions moved sharply this week.",
        ),
        domain="finance", current=current, provider="fixture",
    )
    if current_yield_meta is None:
        raise AssertionError(f"Current Treasury financing event failed metadata: {current_yield_audit}")
    current_yield_event, current_yield_grounding = ground_candidate(
        current_yield_meta, domain="finance",
        fetcher=lambda *a, **k: _doc(
            "10-year Treasury yield rises sharply as financing conditions tighten",
            "The 10-year Treasury yield rose 35 basis points this week to 4.6% as investors repriced the path of inflation and Federal Reserve policy. Higher benchmark yields pushed long-duration corporate borrowing costs upward across technology and data-center financing markets.",
            url="https://www.reuters.com/markets/rates/current-yield-example",
        ),
    )
    if current_yield_event is None or "35 basis points" not in current_yield_event.get("verified_fact", ""):
        raise AssertionError(f"Current Treasury financing change was lost while historical context was rejected: {current_yield_grounding}")

    # Durable rows survive engine-version changes, but universal Reader-quality
    # invariants still apply. A previously grounded fossil or a company-specific
    # Market item that lacks market significance must not be grandfathered merely
    # because an older selector admitted it.
    retained_fossil = {
        "record_origin": "automated_discovery",
        "grounding_status": "grounded",
        "source_evidence_hash": "old-but-grounded",
        "source_text_chars": 900,
        "domain": "finance",
        "event_date": pd.Timestamp("2026-08-04"),
        "verified_fact": "From June 1989 to June 2021, the 10-year Treasury yield fell from about 8.5% to 1.5%.",
        "platform_relevance": "The 8.5% move changes the cost of capital for long-duration AI infrastructure.",
    }
    if context_registry._automated_row_still_qualifies(retained_fossil):
        raise AssertionError("Historical-context Finance fossil survived retained Reader-quality revalidation.")
    retained_axon = {
        "record_origin": "automated_discovery",
        "grounding_status": "grounded",
        "source_evidence_hash": "axon-grounded",
        "source_text_chars": 900,
        "domain": "market",
        "event_date": pd.Timestamp("2026-08-04"),
        "verified_fact": "Axon Enterprise raised its annual outlook after stronger demand for its AI software bundle.",
        "platform_relevance": "The reported results show AI-linked demand reaching revenue and earnings.",
    }
    if context_registry._automated_row_still_qualifies(retained_axon):
        raise AssertionError("AI-relevant but non-market-significant Axon row survived retained revalidation.")

    connectivity_meta, _ = evaluate_item(
        _item(
            "China Unicom lands SHV-HK submarine cable connecting Hong Kong to Cambodia",
            "Data Center Dynamics",
            "https://www.datacenterdynamics.com/en/news/shv-hk-example",
            description="Submarine cable route between Hong Kong and Cambodia.",
        ),
        domain="connectivity", current=current, provider="fixture",
    )
    rejected_connectivity, connectivity_grounding = ground_candidate(
        connectivity_meta, domain="connectivity",
        fetcher=lambda *a, **k: _doc(
            "China Unicom lands SHV-HK submarine cable connecting Hong Kong to Cambodia",
            "China Unicom commissioned a new submarine cable between Hong Kong and Cambodia this week. The route adds international telecom capacity between the two markets.",
            url="https://www.datacenterdynamics.com/en/news/shv-hk-example",
        ),
    )
    if rejected_connectivity is not None or "compute market" not in connectivity_grounding.reason:
        raise AssertionError(f"Globally interesting but AI-Macro-irrelevant connectivity project leaked through: {connectivity_grounding}")

    workforce_meta, _ = evaluate_item(
        _item(
            "AI’s Impact on Labor and Hiring",
            "newyorkfed.org",
            "https://libertystreeteconomics.newyorkfed.org/2026/08/ais-impact-on-labor-and-hiring/",
            description="Discussion of AI and labor markets.",
        ),
        domain="workforce", current=current, provider="fixture",
    )
    rejected_workforce, workforce_grounding = ground_candidate(
        workforce_meta, domain="workforce",
        fetcher=lambda *a, **k: _doc(
            "AI’s Impact on Labor and Hiring",
            "Economists discussed how artificial intelligence could affect labor and hiring over time. Some employers may change entry-level recruiting while other occupations may expand.",
            url="https://libertystreeteconomics.newyorkfed.org/2026/08/ais-impact-on-labor-and-hiring/",
        ),
    )
    if rejected_workforce is not None or "commentary" not in workforce_grounding.reason:
        raise AssertionError(f"Topic commentary was promoted into a Workforce development: {workforce_grounding}")

    # Routine central-bank remarks are not Finance developments.  The discovery
    # headline may use surname shorthand, but a Reader item requires an actual
    # policy action or empirical release; commentary about the outlook is rejected.
    paulson_meta, _ = evaluate_item(
        _item(
            "Fed's Paulson keeps 'open mind' on rate policy outlook amid high inflation",
            "Reuters",
            "https://www.reuters.com/business/feds-paulson-example-2026-08-04/",
            description="Federal Reserve policy outlook and inflation.",
        ),
        domain="finance", current=current, provider="fixture",
    )
    paulson, paulson_grounding = ground_candidate(
        paulson_meta, domain="finance",
        fetcher=lambda *a, **k: _doc(
            "Fed's Paulson keeps 'open mind' on rate policy outlook amid high inflation",
            "Federal Reserve Bank of Philadelphia President Anna Paulson said she was keeping an open mind about the monetary-policy outlook. Paulson said underlying inflation remained elevated and that future policy could require higher rates or a longer hold.",
            url="https://www.reuters.com/business/feds-paulson-example-2026-08-04/",
        ),
    )
    if paulson is not None or "commentary" not in paulson_grounding.reason:
        raise AssertionError(f"Routine Fed-official commentary leaked into Finance Current Context: {paulson_grounding}")

    identity_meta, _ = evaluate_item(
        _item(
            "Fed's Paulson votes to raise policy rate by 25 basis points",
            "Reuters",
            "https://www.reuters.com/business/fed-action-identity-example/",
            description="Federal Reserve policy action and rates.",
        ),
        domain="finance", current=current, provider="fixture",
    )
    identity_event, identity_grounding = ground_candidate(
        identity_meta, domain="finance",
        fetcher=lambda *a, **k: _doc(
            "Fed's Paulson votes to raise policy rate by 25 basis points",
            "Federal Reserve Bank of Philadelphia President Anna Paulson spoke after the meeting. Paulson voted to raise the policy rate by 25 basis points and cited persistent inflation.",
            url="https://www.reuters.com/business/fed-action-identity-example/",
        ),
    )
    if identity_event is None or not identity_event.get("verified_fact", "").startswith("Federal Reserve Bank of Philadelphia President Anna Paulson"):
        raise AssertionError(f"Source-established full identity was not restored from headline shorthand: {identity_grounding}")

    # Interview/pundit framing is not a substitute for a new empirical release.
    kearney_meta, _ = evaluate_item(
        _item(
            "No evidence of productivity boom or large labor disruption from AI: Notre Dame's Melissa Kearney",
            "CNBC",
            "https://www.cnbc.com/2026/08/04/ai-productivity-kearney-example.html",
            description="Discussion of AI productivity and labor-market effects.",
        ),
        domain="economic_impact", current=current, provider="fixture",
    )
    kearney, kearney_grounding = ground_candidate(
        kearney_meta, domain="economic_impact",
        fetcher=lambda *a, **k: _doc(
            "No evidence of productivity boom or large labor disruption from AI: Notre Dame's Melissa Kearney",
            "Economist Melissa Kearney said she had not yet seen convincing evidence of a broad productivity boom from artificial intelligence. She discussed recent productivity statistics and possible future labor-market effects.",
            url="https://www.cnbc.com/2026/08/04/ai-productivity-kearney-example.html",
        ),
    )
    if kearney is not None or "commentary" not in kearney_grounding.reason:
        raise AssertionError(f"Pundit/interview framing leaked into Economic Outcomes: {kearney_grounding}")

    # A nonbinding roadmap is not automatically a Grid & Storage development.
    roadmap_meta, _ = evaluate_item(
        _item(
            "DOE Distributed Energy Resource Interconnection Roadmap",
            "energy.gov",
            "https://www.energy.gov/oe/der-interconnection-roadmap-example",
            description="DOE roadmap for distributed energy resource interconnection.",
        ),
        domain="grid_storage", current=current, provider="fixture",
    )
    roadmap, roadmap_grounding = ground_candidate(
        roadmap_meta, domain="grid_storage",
        fetcher=lambda *a, **k: _doc(
            "DOE Distributed Energy Resource Interconnection Roadmap",
            "The Department of Energy published a roadmap recommending practices that states and utilities could consider for distributed energy resource interconnection. The roadmap does not itself adopt a tariff, order construction, or change an interconnection rule.",
            url="https://www.energy.gov/oe/der-interconnection-roadmap-example",
        ),
    )
    if roadmap is not None or not any(token in roadmap_grounding.reason for token in ("roadmap", "commentary", "concrete development", "concrete measured")):
        raise AssertionError(f"Nonbinding Grid roadmap was promoted into a development: {roadmap_grounding}")

    stale_power_meta, _ = evaluate_item(
        _item(
            "Clean Energy Resources to Meet Data Center Electricity Demand",
            "energy.gov",
            "https://www.energy.gov/oe/clean-energy-resources-meet-data-center-electricity-demand",
            published="2026-08-04",
            description="DOE resources for data-center electricity demand.",
        ),
        domain="power", current=current, provider="fixture",
    )
    stale_power, stale_grounding = ground_candidate(
        stale_power_meta, domain="power",
        fetcher=lambda *a, **k: _doc(
            "Clean Energy Resources to Meet Data Center Electricity Demand",
            "The Department of Energy published resources describing ways clean generation and storage can help meet data-center electricity demand.",
            published_date="2024-08-16",
            url="https://www.energy.gov/oe/clean-energy-resources-meet-data-center-electricity-demand",
        ),
    )
    if stale_power is not None or "predates" not in stale_grounding.reason:
        raise AssertionError(f"A stale source recrawl was treated as a new Power development: {stale_grounding}")

    # A recently modified timestamp must not launder an old publication into the
    # seven-day window when the publisher exposes both dates.
    stale_modified, stale_modified_grounding = ground_candidate(
        stale_power_meta, domain="power",
        fetcher=lambda *a, **k: _doc(
            "Clean Energy Resources to Meet Data Center Electricity Demand",
            "The Department of Energy published resources describing ways clean generation and storage can help meet data-center electricity demand.",
            published_date="2024-08-16", modified_date="2026-08-04",
            url="https://www.energy.gov/oe/clean-energy-resources-meet-data-center-electricity-demand",
        ),
    )
    if stale_modified is not None or "predates" not in stale_modified_grounding.reason:
        raise AssertionError("A recent modified timestamp overrode the publisher's stale publication date.")

    # Google News is discovery metadata only.  The grounding layer must resolve
    # the actual eligible publisher page, fetch its body, and reject a trusted
    # source label that ultimately redirects onto an unrelated host.
    wrapper_html = '<html><body><c-wiz><div jscontroller="abc" data-n-a-sg="fixture-signature" data-n-a-ts="1722792000"></div></c-wiz></body></html>'
    publisher_html = '<html><head><meta property="og:title" content="Resolved source"><meta property="article:published_time" content="2026-08-04T12:00:00Z"></head><body><article><p>Reuters reported that a technology company signed a 1,500 MW power purchase agreement for planned data-center campuses.</p><p>The contracts begin supplying electricity in 2028 and cover two sites.</p><p>The agreement converts a forecast load requirement into contracted power supply for the projects.</p></article></body></html>'
    calls = []
    original_request = grounding._request_html
    original_decode = grounding._google_news_decode_rpc
    try:
        def _fixture_request(url):
            calls.append(url)
            if "news.google.com" in url:
                return wrapper_html, "https://news.google.com/rss/articles/example", ""
            if "reuters.com" in url:
                return publisher_html, "https://www.reuters.com/business/resolved-grounding", ""
            return "", url, "unexpected fixture URL"
        grounding._request_html = _fixture_request
        grounding._google_news_decode_rpc = lambda article_id, signature, timestamp: (
            "https://www.reuters.com/business/resolved-grounding", ""
        )
        resolved_doc = fetch_source_document(
            "https://news.google.com/rss/articles/example",
            publisher_url="https://www.reuters.com",
            source_name="Reuters",
        )
    finally:
        grounding._request_html = original_request
        grounding._google_news_decode_rpc = original_decode
    if resolved_doc.error or resolved_doc.resolved_url != "https://www.reuters.com/business/resolved-grounding" or "1,500 MW" not in resolved_doc.body_text:
        raise AssertionError(f"Google News nomination did not resolve to source body evidence: {resolved_doc}")
    if len(calls) < 2:
        raise AssertionError("Source grounding never left the Google News wrapper.")

    # Grounding must continue past early source-access failures instead of
    # starving a high-volume domain after an arbitrary first-six shortlist.
    adaptive_candidates = [
        {"event_id": f"adaptive-{index}", "rank_score": 100 - index}
        for index in range(8)
    ]
    adaptive_audit = [
        {"event_id": row["event_id"], "domain_query": "market", "decision": "metadata_qualified", "grounding_status": "not_attempted"}
        for row in adaptive_candidates
    ]
    original_ground_candidate = discovery.ground_candidate
    try:
        def _adaptive_ground(candidate, *, domain):
            index = int(str(candidate["event_id"]).rsplit("-", 1)[-1])
            if index < 6:
                return None, grounding.GroundingResult(False, reason="fixture source unavailable")
            accepted = dict(candidate)
            accepted.update({
                "source_url": "https://www.reuters.com/business/adaptive-grounding",
                "grounding_status": "grounded",
                "grounding_version": GROUNDING_VERSION,
            })
            return accepted, grounding.GroundingResult(
                True, resolved_url=accepted["source_url"], reason="fixture grounded"
            )
        discovery.ground_candidate = _adaptive_ground
        adaptive_grounded = discovery._ground_domain_candidates(
            adaptive_candidates, adaptive_audit, domain="market", target_grounded=1, max_attempts=8
        )
    finally:
        discovery.ground_candidate = original_ground_candidate
    if len(adaptive_grounded) != 1 or adaptive_grounded[0]["event_id"] != "adaptive-6":
        raise AssertionError("Source grounding still stops before a valid lower-ranked Market/Finance candidate.")

    # A discovery URL nominates an event; it is not allowed to veto the event.
    # If Reuters (or another eligible source) is inaccessible, the resolver must
    # search for the same event through another eligible source and run that
    # source through the identical body-grounding contract.
    seed_item = _item(
        "AI data-centre race builds $1 trillion lease burden for Big Tech",
        "Reuters",
        "https://news.google.com/rss/articles/reuters-lease-seed",
        description="Microsoft, Meta, Oracle, Amazon and Alphabet report large future lease commitments for AI data centers.",
    )
    seed_item["source_url"] = "https://www.reuters.com"
    seed_candidate, seed_audit = evaluate_item(
        seed_item, domain="finance", current=current, provider="fixture"
    )
    if seed_candidate is None:
        raise AssertionError(f"Finance event-resolution seed did not clear metadata: {seed_audit}")
    alternate_item = _item(
        "Big Tech AI spending spree tops $1tn",
        "Financial Times",
        "https://news.google.com/rss/articles/ft-lease-alternate",
        published="2026-08-04",
        description="Google, Amazon, Microsoft and Meta have signed more than $900 billion in AI-related financial obligations including data-center leases and long-term purchase agreements.",
    )
    alternate_item["source_url"] = "https://www.ft.com"
    resolver_statuses = []
    ground_calls = []
    def _event_resolver_ground(candidate, *, domain):
        ground_calls.append(candidate.get("source_name"))
        if candidate.get("source_name") == "Reuters":
            return None, grounding.GroundingResult(
                False,
                reason="underlying source could not be established",
                error="HTTPError: 401 Client Error: HTTP Forbidden",
            )
        if candidate.get("source_name") == "Financial Times":
            accepted = dict(candidate)
            accepted.update({
                "verified_fact": "Microsoft, Meta, Oracle, Amazon and Alphabet committed about $1.09 trillion to future lease payments, mostly for AI data centers.",
                "platform_relevance": "The commitments are fixed claims on future cash flow and therefore consume funding capacity even though they are not funded debt.",
                "display": "Microsoft, Meta, Oracle, Amazon and Alphabet committed about $1.09 trillion to future lease payments, mostly for AI data centers. The commitments are fixed claims on future cash flow and therefore consume funding capacity even though they are not funded debt.",
                "source_url": "https://www.ft.com/content/alternate-lease-evidence",
                "source_name": "Financial Times",
                "source_label": "Financial Times",
                "grounding_status": "grounded",
                "grounding_version": GROUNDING_VERSION,
                "source_text_method": "fixture_body",
                "source_text_chars": 900,
                "source_evidence_hash": "alternate-evidence-hash",
            })
            return accepted, grounding.GroundingResult(
                True,
                resolved_url=accepted["source_url"],
                extraction_method="fixture_body",
                text_chars=900,
                evidence_hash="alternate-evidence-hash",
                reason="source-grounded development",
            )
        return None, grounding.GroundingResult(False, reason="fixture rejected")
    def _event_search(query, *, days):
        return [alternate_item], ""
    resolver_audit = [dict(seed_audit)]
    resolved = discovery._ground_domain_candidates(
        [seed_candidate],
        resolver_audit,
        domain="finance",
        target_grounded=1,
        max_attempts=3,
        current=current,
        discovery_items=[],
        statuses=resolver_statuses,
        grounder=_event_resolver_ground,
        event_searcher=_event_search,
    )
    if len(resolved) != 1 or resolved[0].get("source_name") != "Financial Times":
        raise AssertionError(f"Event-level evidence resolver let one inaccessible URL veto the Finance event: {resolved}")
    if resolved[0].get("event_id") != seed_candidate.get("event_id"):
        raise AssertionError("Alternate evidence changed the nominated event identity instead of only replacing its evidence endpoint.")
    if resolver_audit[0].get("evidence_resolution_status") != "alternate_source_grounded":
        raise AssertionError(f"Alternate evidence path was not exposed in the candidate audit: {resolver_audit[0]}")
    if not any(status.provider == "event_evidence_search" for status in resolver_statuses):
        raise AssertionError("Event-level evidence retrieval was not surfaced as an auditable provider step.")
    if ground_calls[:2] != ["Reuters", "Financial Times"]:
        raise AssertionError(f"Resolver did not try discovered evidence first and alternate evidence second: {ground_calls}")

    # Event-level rescue must not turn into a generic approved-source fallback.
    # An unrelated eligible article is not evidence for the nominated event.
    unrelated_item = _item(
        "Nvidia launches new gaming graphics card for holiday season",
        "CNBC",
        "https://www.cnbc.com/2026/08/04/nvidia-gaming-gpu.html",
        description="The company introduced a consumer graphics card aimed at PC gamers.",
    )
    unrelated_calls = []
    def _unrelated_ground(candidate, *, domain):
        unrelated_calls.append(candidate.get("source_name"))
        return None, grounding.GroundingResult(False, reason="underlying source could not be established")
    unrelated_audit = [dict(seed_audit)]
    unrelated = discovery._ground_domain_candidates(
        [seed_candidate],
        unrelated_audit,
        domain="finance",
        target_grounded=1,
        max_attempts=3,
        current=current,
        discovery_items=[],
        statuses=[],
        grounder=_unrelated_ground,
        event_searcher=lambda query, *, days: ([unrelated_item], ""),
    )
    if unrelated:
        raise AssertionError(f"Event resolver accepted unrelated approved reporting as alternate evidence: {unrelated}")
    if unrelated_calls != ["Reuters"]:
        raise AssertionError(f"Low-similarity alternate reporting should not reach source grounding: {unrelated_calls}")

    original_request = grounding._request_html
    try:
        grounding._request_html = lambda url: (publisher_html, "https://example.com/spoofed", "")
        spoofed = fetch_source_document(
            "https://www.reuters.com/business/apparently-trusted",
            publisher_url="https://www.reuters.com",
            source_name="Reuters",
        )
    finally:
        grounding._request_html = original_request
    if not spoofed.error or "not eligible evidence" not in spoofed.error:
        raise AssertionError("Trusted discovery metadata blessed an unrelated resolved source host.")

    power_meta, _ = evaluate_item(
        _item(
            "Constellation signs long-term power deals for data-center demand",
            "RTO Insider",
            "https://www.rtoinsider.com/constellation-source-grounding",
            description="Nuclear power purchase agreements for data-center operators.",
        ),
        domain="power", current=current, provider="fixture",
    )
    grounded_power, power_grounding = ground_candidate(
        power_meta, domain="power",
        fetcher=lambda *a, **k: _doc(
            "Constellation signs long-term power deals for data-center demand",
            "Constellation signed power purchase agreements for 1,500 MW of nuclear generation with two data-center operators in Pennsylvania. The contracts will supply electricity for planned campuses beginning in 2028.",
            url="https://www.rtoinsider.com/constellation-source-grounding",
        ),
    )
    if grounded_power is None or "1,500 MW" not in grounded_power.get("verified_fact", ""):
        raise AssertionError(f"Concrete Power source evidence failed grounding: {power_grounding}")
    if "dated supply commitment" not in grounded_power.get("platform_relevance", ""):
        raise AssertionError("Power synthesis did not explain the analytical consequence of the actual contract.")
    if "The change affects" in grounded_power.get("platform_relevance", ""):
        raise AssertionError("Power synthesis regressed to generic domain boilerplate.")

    # There is one Current Context architecture.  Registry loading is provider-
    # free, and the retired score-gated/GDELT/live-loader branches must not be
    # allowed to reappear behind compatibility flags.
    context_loader_source = (PROJECT_ROOT / "loaders" / "current_context_loader.py").read_text()
    discovery_source = (PROJECT_ROOT / "loaders" / "current_context_discovery.py").read_text()
    if any(token in context_loader_source for token in ("include_live", "_fetch_live_", "ThreadPoolExecutor", "urlopen")):
        raise AssertionError("Retired live Current Context path remains reachable from the registry loader.")
    if any(token in discovery_source for token in ("GDELT_ENDPOINT", "fetch_gdelt", "minimum_score")):
        raise AssertionError("Retired Current Context provider/score-gate code remains in the canonical discovery engine.")
    if any("minimum_score" in policy for policy in DOMAIN_CONTEXT_POLICY.values()):
        raise AssertionError("A retired aggregate acceptance threshold remains in domain policy.")

    # Every domain has one canonical semantic record.  The active engine must
    # not maintain stage-specific shadow vocabularies that can drift apart.
    if set(DOMAIN_VOCABULARY) != set(DOMAIN_KEYS) or set(DOMAIN_VOCABULARY) != set(DOMAIN_CONTEXT_POLICY):
        raise AssertionError("Canonical domain vocabulary does not cover exactly the active Current Context domains.")
    semantic_signatures = set()
    for domain in DOMAIN_KEYS:
        profile = DOMAIN_VOCABULARY[domain]
        if len(domain_news_queries(domain)) < 2:
            raise AssertionError(f"{domain} does not have domain-specific targeted discovery queries.")
        if not domain_relevance_terms(domain) or not domain_topic_anchors(domain) or not domain_owner_terms(domain):
            raise AssertionError(f"{domain} is missing qualification/anchor/ownership vocabulary.")
        if not profile.materiality_weights or not profile.synthesis_terms:
            raise AssertionError(f"{domain} is missing materiality or synthesis vocabulary.")
        if any(not domain_synthesis_terms(domain, category) for category in profile.synthesis_terms):
            raise AssertionError(f"{domain} contains an empty synthesis category.")
        signature = (profile.queries, profile.anchors, profile.relevance_terms, profile.owner_terms)
        if signature in semantic_signatures:
            raise AssertionError(f"{domain} duplicated another domain's semantic vocabulary instead of defining its own.")
        semantic_signatures.add(signature)

    # v7.0.8 deliberately triples the deterministic Current Context expression
    # vocabulary.  Count semantic phrases, not cosmetic sentence variants: the
    # engine should recognize materially more mechanisms before it ever needs a
    # generic fallback.
    v707_term_counts = {
        "market": 52, "finance": 50, "compute": 19, "data_center": 21,
        "connectivity": 9, "power": 14, "grid_storage": 14, "water": 11,
        "adoption": 5, "workforce": 11, "economic_impact": 7,
    }
    for domain, old_count in v707_term_counts.items():
        expanded_count = sum(len(terms) for terms in DOMAIN_VOCABULARY[domain].synthesis_terms.values())
        if expanded_count < old_count * 3:
            raise AssertionError(
                f"{domain} deterministic synthesis vocabulary did not triple: "
                f"old={old_count}, expanded={expanded_count}"
            )

    mechanism_examples = {
        "market": (
            ("guidance_down", "Company cut guidance after weaker demand"),
            ("demand_signals", "Company reported a larger backlog"),
            ("margin_profitability", "Gross margin expanded during the quarter"),
            ("capex_investment", "Company raised its capital spending plan"),
            ("ipo_equity_raise", "Company launched an initial public offering"),
            ("antitrust_regulatory", "Regulators opened an antitrust investigation"),
            ("concentration_breadth", "Market breadth improved across the sector"),
            ("share_repurchase", "Company expanded its share repurchase program"),
        ),
        "finance": (
            ("private_credit", "A private credit fund provided direct lending"),
            ("venture_funding", "The company closed a venture funding round"),
            ("liquidity", "The company increased its cash reserves"),
            ("maturity", "The borrower extended a debt maturity"),
            ("covenant", "Lenders granted a covenant waiver"),
            ("project_finance", "The project secured construction financing"),
            ("financing_platform", "Nvidia established financing platforms with asset managers"),
            ("fund_distributions", "The fund made cash distributions to investors"),
            ("secondaries", "Investors completed a secondary transaction"),
            ("restructuring", "The borrower began a debt restructuring"),
            ("securitization", "The operator completed a data center securitization"),
        ),
        "compute": (
            ("advanced_packaging", "Advanced packaging capacity expanded"),
            ("memory_supply", "HBM supply increased"),
            ("fab_investment", "The company announced a new fab"),
            ("foundry_capacity", "Leading-edge foundry capacity expanded"),
            ("supply_agreement", "The companies signed a long-term supply agreement"),
            ("compute_leasing", "The provider will rent excess compute capacity"),
        ),
        "data_center": (
            ("land_site", "The developer completed a land purchase"),
            ("construction_start", "Construction began on the campus"),
            ("commissioning", "The first building entered commissioning"),
            ("prelease", "The operator signed an anchor tenant"),
            ("cancellation", "The developer canceled the project"),
            ("tax_incentive", "The county approved a tax abatement"),
            ("power_readiness", "The campus secured a utility agreement"),
        ),
        "connectivity": (
            ("capacity_upgrade", "The carrier completed a network upgrade"),
            ("landing_station", "A new cable landing station opened"),
            ("outage_resilience", "The operator added route diversity after a fiber cut"),
            ("peering_expansion", "A new internet exchange point opened"),
            ("fiber_build", "The company began a middle-mile fiber build"),
            ("permit_right_of_way", "The city approved a right-of-way permit"),
        ),
        "power": (
            ("load_forecast", "The utility raised its data center load forecast"),
            ("generation_addition", "The utility approved a new power plant"),
            ("generation_retirement", "The utility delayed a plant retirement"),
            ("fuel_supply", "The plant secured a natural gas supply contract"),
            ("nuclear_restart", "The operator announced a nuclear restart"),
            ("demand_response", "The utility created an interruptible load program"),
            ("utility_capex", "The utility increased its capital plan"),
        ),
        "grid_storage": (
            ("transmission_build", "The utility approved a new transmission line"),
            ("queue_reform", "The regulator adopted interconnection reform"),
            ("transformer_substation", "The utility ordered large power transformers"),
            ("congestion", "Transmission congestion costs increased"),
            ("cost_allocation", "The regulator created a large-load tariff for transmission costs"),
            ("reliability", "NERC reported a tighter reserve margin"),
        ),
        "water": (
            ("cooling_technology", "The campus adopted closed-loop cooling"),
            ("groundwater", "The state restricted groundwater pumping"),
            ("allocation_policy", "The government proposed new river operating rules"),
            ("infrastructure_expansion", "The utility approved a new water treatment plant"),
            ("wastewater_capacity", "The city expanded wastewater treatment capacity"),
            ("drought_emergency", "The state declared a drought emergency"),
        ),
        "adoption": (
            ("enterprise_rollout", "The company began an enterprise rollout"),
            ("agent_deployment", "The company deployed AI agents"),
            ("production_integration", "The tool moved into production use"),
            ("paid_usage", "The provider reported more paid seats"),
            ("governance_constraint", "The company adopted an AI usage policy"),
            ("workflow_automation", "The company expanded workflow automation"),
        ),
        "workforce": (
            ("layoffs", "The company announced job cuts"),
            ("job_postings", "AI-related job openings increased"),
            ("wage_compensation", "Wage growth accelerated"),
            ("skills_training", "The employer launched an AI training program"),
            ("automation_task_change", "The company automated more routine tasks"),
            ("union_bargaining", "The union negotiated new AI work rules"),
            ("occupational_shift", "Workers moved into different occupations"),
        ),
        "economic_impact": (
            ("inflation_prices", "Core inflation slowed"),
            ("investment", "Business investment growth accelerated"),
            ("labor_share_distribution", "The labor share declined"),
            ("gdp_revision", "The government revised GDP higher"),
            ("unit_labor_cost", "Unit labor cost growth slowed"),
            ("consumer_spending", "Consumer spending growth increased"),
            ("sector_output", "Technology-sector output increased"),
        ),
    }
    for domain, examples in mechanism_examples.items():
        for category, fact_text in examples:
            if not grounding._synthesis_match(domain, category, fact_text.casefold()):
                raise AssertionError(f"{domain}.{category} fixture no longer matches its canonical vocabulary.")
            consequence = grounding._specific_relevance(domain, fact_text, fact_text)
            if not consequence:
                raise AssertionError(f"{domain}.{category} has vocabulary but no deterministic Reader consequence.")

    # Market and Finance are high-cadence anchor domains.  Once a development
    # clears the evidence gates, lack of a bespoke wording template must never
    # be the reason it disappears from Reader mode.
    for domain, generic_fact in (
        ("market", "A major AI-linked company reported a material strategic development"),
        ("finance", "A major AI-linked company completed a material capital-structure action"),
    ):
        if not grounding._specific_relevance(domain, generic_fact, generic_fact):
            raise AssertionError(f"{domain} still allows a grounded event to die solely for lack of deterministic phrasing.")

    policy_source = (PROJECT_ROOT / "config" / "current_context_policy.py").read_text()
    active_sources = "\n".join(
        (PROJECT_ROOT / path).read_text()
        for path in (
            "loaders/current_context_discovery.py",
            "loaders/current_context_grounding.py",
            "loaders/current_context_news.py",
            "loaders/current_context_registry.py",
        )
    )
    for retired_name in (
        "DOMAIN_NEWS_QUERIES", "DOMAIN_NEWS_TERMS", "DOMAIN_TOPIC_ANCHORS",
        "DOMAIN_OWNER_TERMS", "DOMAIN_MATERIAL_EVENT_WEIGHTS",
    ):
        if retired_name in policy_source or retired_name in active_sources:
            raise AssertionError(f"Shadow semantic registry {retired_name} survived the canonical-vocabulary renovation.")

    # Finance is the regression that exposed the drift: bond/lease/rating terms
    # must be known to ownership as well as qualification and synthesis.
    for term in (
        "bond", "lease", "rating", "refinancing", "private credit", "project finance",
        "financing platform", "liquidity", "maturity", "covenant", "distribution",
        "secondary", "securitization", "restructuring",
    ):
        if term not in domain_owner_terms("finance"):
            raise AssertionError(f"Finance ownership vocabulary lost {term!r}.")
    if not any("lease" in term for term in domain_synthesis_terms("finance", "lease_obligation")):
        raise AssertionError("Finance synthesis vocabulary lost lease obligations.")

    # Duplicate articles returned by several searches receive one owner.
    shared_url = "https://www.reuters.com/example-ai-results"
    assigned = _assign_event_owners({
        "market": [{
            "event_id": "shared", "domain": "market", "source_url": shared_url,
            "verified_fact": "Company reports earnings and raises guidance", "owner_score": 130,
            "rank_score": 130, "event_date": "2026-08-04",
        }],
        "adoption": [{
            "event_id": "shared", "domain": "adoption", "source_url": shared_url,
            "verified_fact": "Company reports earnings and raises guidance", "owner_score": 118,
            "rank_score": 118, "event_date": "2026-08-04",
        }],
    })
    if len(assigned["market"]) != 1 or assigned["adoption"]:
        raise AssertionError("Live event ownership did not prevent cross-tab duplication.")

    finance_owner_item, finance_owner_audit = evaluate_item(
        _item(
            "Alphabet launches $25 billion bond offering for AI investment",
            "Reuters",
            "https://www.reuters.com/business/alphabet-bond-offering",
            description="Alphabet launched a $25 billion bond offering as artificial-intelligence capital spending rises.",
        ),
        domain="finance", current=current, provider="fixture",
    )
    if finance_owner_item is None or float(finance_owner_item.get("owner_score", 0)) != float(finance_owner_audit.get("domain_fit_score", -1)):
        raise AssertionError("Domain ownership is not using semantic domain fit independently from ranking score.")
    if float(finance_owner_item.get("owner_score", 0)) <= 0:
        raise AssertionError("Finance ownership vocabulary still does not recognize bond/financing language.")

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
            if len(str(persisted.get("snapshot_id") or "")) != 16:
                raise AssertionError("Current Context refresh did not fingerprint the selected snapshot.")
            if persisted.get("audit_path") != "audit.csv" or persisted.get("registry_path") != "events.csv":
                raise AssertionError(f"Current Context manifest persisted a machine-specific path: {persisted}")
    finally:
        discovery.discover_domain = original_discover

    daily_source = (PROJECT_ROOT / "loaders" / "current_context_daily.py").read_text()
    app_source = (PROJECT_ROOT / "ai_macro.py").read_text()
    if "load_public_shared_context_snapshot" in daily_source or "@st.cache_data" in daily_source:
        raise AssertionError("Public Current Context live-refresh/cache machinery returned.")
    if "load_retained_context_snapshot(as_of=market_date())" not in app_source:
        raise AssertionError("Public Reader mode is not bound to retained Current Context.")
    if "load_public_shared_context_snapshot" in app_source:
        raise AssertionError("Public Reader still contains the retired live Current Context path.")
    if "build_reader_snapshot(" not in app_source:
        raise AssertionError("Current Context is not bound to one completed Read pair.")
    packet_report = finalize_context_report(
        {"discovery_version": discovery.DISCOVERY_VERSION, "retrieved_at": "2026-08-04T12:00:00+00:00"},
        context,
    )
    packet_id = str(packet_report.get("snapshot_id") or "")
    if len(packet_id) != 16 or packet_id != context_packet_id(packet_report, context):
        raise AssertionError("Context packet ID does not deterministically identify the rendered domain packet.")

    if recent_development_copy_issues("Governor Abbott directed ERCOT to review the queue") == []:
        raise AssertionError("Recent Developments accepted ambiguous official/regional shorthand.")
    if recent_development_copy_issues(
        "Texas Governor Greg Abbott directed the Electric Reliability Council of Texas (ERCOT) to review the queue"
    ):
        raise AssertionError("Recent Developments rejected properly contextualized first references.")
    if recent_development_copy_issues("The chipmaker signed financing memorandums with outside capital providers") == []:
        raise AssertionError("Recent Developments accepted a mystery-company first reference.")
    if recent_development_copy_issues("Leading up to their IPO they signed several infrastructure deals") == []:
        raise AssertionError("Recent Developments accepted a dangling pronoun lead.")
    nvidia_fact = grounding._resolve_first_reference_identity(
        grounding._compress_fact("The chipmaker signed memorandums of understanding with Apollo Global Management."),
        "Nvidia lines up Wall Street asset managers for $500 billion AI push",
        "Nvidia said Monday it had signed financing memorandums. Nvidia is a chipmaker.",
    )
    if not nvidia_fact.startswith("Nvidia signed") or recent_development_copy_issues(nvidia_fact):
        raise AssertionError(f"Headline-grounded company identity was not restored: {nvidia_fact}")
    colon_fact = grounding._compress_fact(
        "Leading up to their recent IPO they did multiple infrastructure deals with excess capacity: "
        "Meta recently announced it will rent excess AI computing power in a potential $10 billion deal with Anthropic."
    )
    if not colon_fact.startswith("Meta recently announced") or recent_development_copy_issues(colon_fact):
        raise AssertionError(f"Self-contained event clause was not recovered from a dangling lead: {colon_fact}")
    scc_fact = grounding._resolve_first_reference_identity(
        grounding._compress_fact("The SCC cited the proposed Valley Link transmission project as an example."),
        "Virginia regulators order Dominion Energy to directly assign transmission costs to data centers",
        "The Virginia State Corporation Commission (SCC) ordered Dominion Energy to create a new rate class. "
        "The SCC cited the proposed Valley Link transmission project as an example.",
    )
    if "Virginia State Corporation Commission (SCC)" not in scc_fact or recent_development_copy_issues(scc_fact):
        raise AssertionError(f"Source-defined regional acronym was not restored on first reference: {scc_fact}")

    monday_fragment = (
        "For the quarter ending June 30, the maker of project management software reported a profit of $1.48 "
        "a share on an adjusted basis, up 36% from a year earlier.… 2/09/2026 Monday.com topped Q4 estimates "
        "but shares. The reported results show whether AI-linked demand is turning into realized revenue and "
        "profit rather than remaining an expectation."
    )
    if not recent_development_copy_issues(monday_fragment):
        raise AssertionError("Recent Developments accepted an ellipsis/date-spliced article fragment.")

    broken_quote = (
        "“Power generation and infrastructure investors financing transmission, generation, or grid "
        "infrastructure tied to large-load projects should assess project viability —"
    )
    if not recent_development_copy_issues(broken_quote):
        raise AssertionError("Recent Developments accepted an incomplete quoted extraction fragment.")

    clean_grid = (
        "California curtailed 4.5 million MWh of renewable generation in the first half of 2026, already "
        "exceeding the total curtailed during 2025. The losses show that generation additions alone do not "
        "guarantee delivered supply when transmission and storage capacity lag the buildout."
    )
    clean_water = (
        "The federal government proposed Colorado River operating rules that could cut Lower Basin deliveries "
        "by as much as 3 million acre-feet per year. The proposal raises the value of location-specific water "
        "exposure and reuse capacity for industrial and data-center development in the Southwest."
    )
    for label, copy in (("grid", clean_grid), ("water", clean_water)):
        issues = recent_development_copy_issues(copy)
        if issues:
            raise AssertionError(f"Recent Developments rejected clean {label} Reader copy: {issues}")

    if (
        DOMAIN_CONTEXT_POLICY["market"]["cadence"] != "weekday"
        or DOMAIN_CONTEXT_POLICY["market"]["lookback_days"] != 7
        or "minimum_score" in DOMAIN_CONTEXT_POLICY["market"]
        or DOMAIN_CONTEXT_POLICY["market"].get("max_items") != 2
    ):
        raise AssertionError("Market Current Context did not retain the 7-day / transparent-gate / max-two policy.")
    if "minimum_score" in DOMAIN_CONTEXT_POLICY["finance"] or DOMAIN_CONTEXT_POLICY["finance"].get("max_items") != 2:
        raise AssertionError("Finance Current Context regressed to aggregate score-gating or one-item retention.")

    for blocked in ("Fox News", "MSNBC", "HuffPost", "Associated Press"):
        if assess_source(blocked, f"https://{blocked.replace(' ', '').lower()}.com").auto_eligible:
            raise AssertionError(f"Blocked source became eligible: {blocked}")
    for social_name, social_url in (
        ("Reddit", "https://www.reddit.com/r/investing"),
        ("X", "https://x.com/example/status/1"),
        ("Facebook", "https://www.facebook.com/example"),
        ("YouTube", "https://www.youtube.com/watch?v=example"),
        ("LinkedIn", "https://www.linkedin.com/posts/example"),
    ):
        social = assess_source(social_name, social_url)
        if social.auto_eligible or social.tier != "blocked_social":
            raise AssertionError(f"Social-media source escaped the hard exclusion: {social_name}")
    if assess_source("The New York Times", "https://www.nytimes.com").auto_eligible:
        raise AssertionError("The manual-review source path became unattendedly eligible.")
    finance_queries = domain_news_queries("finance")
    if not any("Alphabet" in query and "bond" in query for query in finance_queries):
        raise AssertionError("Finance discovery lost the named-borrower capital-markets query.")

    for approved, url in (
        ("The Wall Street Journal", "https://www.wsj.com"),
        ("Reuters", "https://www.reuters.com"),
        ("Investor's Business Daily", "https://www.investors.com"),
        ("Morningstar", "https://www.morningstar.com"),
        ("CNBC", "https://www.cnbc.com"),
        ("Office of the Texas Governor", "https://gov.texas.gov"),
    ):
        if not assess_source(approved, url).auto_eligible:
            raise AssertionError(f"Approved source was rejected: {approved}")



    # Finance must treat disclosed contractual claims on future cash as finance
    # developments even when the headline does not use the word debt.
    lease_item = _item(
        "AI data-centre race builds $1 trillion lease burden for Big Tech",
        "Reuters",
        "https://www.reuters.com/business/ai-data-centre-lease-burden",
        description="Microsoft, Meta, Oracle, Amazon and Alphabet report large future lease commitments for AI data centers.",
    )
    lease_candidate, lease_audit = evaluate_item(lease_item, domain="finance", current=current, provider="fixture")
    if lease_candidate is None or "lease" not in str(lease_audit.get("relevance_terms") or ""):
        raise AssertionError(f"Finance rejected material lease/commitment evidence: {lease_audit}")

    # Metadata qualification is not enough: the source-grounding layer must also
    # recognize a concrete lease commitment as a financing event.  This protects
    # against silently rejecting real contractual obligations because the source
    # uses "committed" rather than the narrower verbs "issued" or "raised".
    lease_grounded, lease_grounding = ground_candidate(
        lease_candidate, domain="finance",
        fetcher=lambda *a, **k: _doc(
            "AI data-centre race builds $1 trillion lease burden for Big Tech",
            "Microsoft, Meta, Oracle, Amazon and Alphabet have committed about $1.09 trillion in future payments under leases that have not yet begun, mostly for data centers needed for artificial intelligence. The obligations represent fixed future cash claims even though they are not funded debt.",
            url="https://www.reuters.com/business/ai-data-centre-lease-burden",
        ),
    )
    if lease_grounded is None or "$1.09 trillion" not in lease_grounded.get("verified_fact", ""):
        raise AssertionError(f"Finance source grounding rejected a concrete lease commitment: {lease_grounding}")
    if not any(term in lease_grounded.get("platform_relevance", "") for term in ("fixed future cash claims", "external capital")):
        raise AssertionError("Finance lease grounding lost the funding-capacity implication of the source fact.")

    # Reuters and issuer filings often describe the same economics as future
    # lease payments rather than the exact phrase 'lease commitment'. The
    # grounding contract must understand that language without falling back to
    # generic debt prose.
    future_lease_grounded, future_lease_result = ground_candidate(
        lease_candidate, domain="finance",
        fetcher=lambda *a, **k: _doc(
            "AI data-centre race builds $1 trillion lease burden for Big Tech",
            "Microsoft, Meta, Oracle, Amazon and Alphabet have collectively committed around $1.09 trillion to future lease payments, largely for data centers needed to sustain artificial intelligence growth. The commitments are not yet reflected as balance-sheet liabilities and exceed about $285 billion in lease liabilities already reported.",
            url="https://www.reuters.com/business/ai-data-centre-lease-burden",
        ),
    )
    if future_lease_grounded is None:
        raise AssertionError(f"Finance rejected the source's 'future lease payments' wording: {future_lease_result}")
    if "fixed future cash claims" not in future_lease_grounded.get("platform_relevance", ""):
        raise AssertionError("Future-lease wording was not classified as a contractual funding-capacity claim.")

    # A financing process is already a concrete Finance development before final
    # pricing when the source establishes the instrument, magnitude, and active
    # transaction. The real FT failure used "preparing to offload" language.
    in_motion_item = _item(
        "Banks to offload $15bn of debt for Anthropic data centre backed by Google",
        "Financial Times",
        "https://www.ft.com/content/anthropic-financing",
        description="Banks are preparing a refinancing for a Google-backed AI data-center project.",
    )
    in_motion_candidate, in_motion_audit = evaluate_item(
        in_motion_item, domain="finance", current=current, provider="fixture"
    )
    if in_motion_candidate is None:
        raise AssertionError(f"Finance metadata rejected active Anthropic financing: {in_motion_audit}")
    in_motion_grounded, in_motion_result = ground_candidate(
        in_motion_candidate, domain="finance",
        fetcher=lambda *a, **k: _doc(
            "Banks to offload $15bn of debt for Anthropic data centre backed by Google",
            "Banks led by Morgan Stanley are preparing to offload $15 billion in debt linked to a Google-backed data center project in Texas that is leased to Anthropic. The debt is set to be refinanced through bond sales as construction milestones are reached.",
            url="https://www.ft.com/content/anthropic-financing",
        ),
    )
    if in_motion_grounded is None or "$15 billion" not in in_motion_grounded.get("verified_fact", ""):
        raise AssertionError(f"Finance rejected a quantified financing already in market: {in_motion_result}")
    if not any(
        phrase in in_motion_grounded.get("platform_relevance", "")
        for phrase in ("outside investors", "refinancing", "external capital")
    ):
        raise AssertionError("Active Anthropic financing lost its financing-capacity implication.")

    # Finance synthesis is fact-first: a ratings sentence in an article that
    # also discusses leases must retain the ratings implication rather than
    # borrowing a consequence from another paragraph.
    rating_grounded, rating_result = ground_candidate(
        lease_candidate, domain="finance",
        fetcher=lambda *a, **k: _doc(
            "Oracle Corp goes for high-stakes ratings gamble in AI strategy",
            "S&P downgraded Oracle to BBB- as debt reached $129.5 billion and leverage rose. Oracle also has about $260 billion in future data-center lease commitments tied to artificial intelligence infrastructure.",
            url="https://www.reuters.com/business/oracle-ratings-ai",
        ),
    )
    if rating_grounded is None or "borrowing-cost pressure" not in rating_grounded.get("platform_relevance", ""):
        raise AssertionError(f"Finance synthesis let article-wide lease language overwrite the chosen ratings fact: {rating_result}")

    # The auditable Google path must preserve transport failures rather than
    # reporting a misleading successful zero-result query.
    original_fetch_bytes = discovery._fetch_bytes
    try:
        discovery._fetch_bytes = lambda url: (b"", "URLError: fixture transport failure")
        google_items, google_error = discovery.fetch_google_news("AI earnings", days=7)
        if google_items or "fixture transport failure" not in google_error:
            raise AssertionError("Google News transport failure was swallowed by the auditable discovery path.")
    finally:
        discovery._fetch_bytes = original_fetch_bytes

    # Publisher HTML retrieval must behave like a normal browser navigation.
    # Reuters rejected the identifying RSS/app User-Agent with HTTP 401 in the
    # captured Finance audit, so source grounding must not reuse that UA.
    original_requests_get = grounding.requests.get
    seen_source_headers = {}
    class _SourceResponse:
        def __init__(self, url, headers):
            self.url = url
            self.headers = {"content-type": "text/html; charset=utf-8"}
            self.content = b"<html><body><article><p>This is a sufficiently long source paragraph about a $15 billion debt financing transaction for an AI data center project.</p><p>The financing is being prepared for sale to outside investors through bond markets.</p></article></body></html>"
            self.text = self.content.decode("utf-8")
            self.encoding = "utf-8"
            self.apparent_encoding = "utf-8"
            self.status_code = 200
            seen_source_headers.update(headers or {})
        def raise_for_status(self):
            if not str(seen_source_headers.get("User-Agent", "")).startswith("Mozilla/"):
                raise RuntimeError("non-browser source UA")
    try:
        grounding.requests.get = lambda url, headers=None, timeout=None, allow_redirects=True: _SourceResponse(url, headers)
        html, resolved, error = grounding._request_html("https://www.reuters.com/business/example")
        if error or not html or not str(seen_source_headers.get("User-Agent", "")).startswith("Mozilla/"):
            raise AssertionError(f"Publisher HTML fetch did not use the browser source profile: {error} / {seen_source_headers}")
    finally:
        grounding.requests.get = original_requests_get

    expected_read_labels = {
        "macro": "AI Macro Read",
        "market": "Market Read",
        "finance": "Finance Read",
        "compute": "Compute Read",
        "data_centers": "Data Centers Read",
        "connectivity": "Connectivity Read",
        "power": "Power Read",
        "grid_storage": "Grid & Storage Read",
        "water": "Water Read",
        "adoption": "Adoption Read",
        "workforce": "Workforce Read",
        "economic_outcomes": "Economic Outcomes Read",
    }
    for domain, expected in expected_read_labels.items():
        actual = domain_read_label(domain, "Read")
        if actual != expected:
            raise AssertionError(f"Named Read label mismatch for {domain}: {actual!r} != {expected!r}")

    # Tier-2 feed adapters may harvest eligible outbound evidence, but must not
    # leak the intermediary itself or social/unknown links into the evidence set.
    original_fetch_bytes = discovery._fetch_bytes
    try:
        tier2_fixture = b"""<?xml version='1.0'?><rss><channel><item>
        <title>Daily finance links</title><link>https://abnormalreturns.com/example</link>
        <pubDate>Tue, 04 Aug 2026 12:00:00 GMT</pubDate>
        <description><![CDATA[
          <a href='https://www.reuters.com/business/ai-bond-example'>AI bond issuance expands</a>
          <a href='https://www.zerohedge.com/opinion/example'>hot take</a>
          <a href='https://x.com/example/status/1'>social post</a>
        ]]></description></item></channel></rss>"""
        discovery._fetch_bytes = lambda url: (tier2_fixture, "")
        outbound, error = discovery.fetch_tier2_outbound("Abnormal Returns", "https://abnormalreturns.com/feed")
        if error or len(outbound) != 1 or "reuters.com" not in outbound[0]["link"]:
            raise AssertionError(f"Tier-2 outbound evidence filtering failed: {outbound} / {error}")
        if outbound[0].get("discovered_via") != "Abnormal Returns":
            raise AssertionError("Tier-2 provenance was not retained for Developer auditability.")

        primary_fixture = b"""<?xml version='1.0'?><rss><channel><item>
        <title>SEC announces market-structure action</title>
        <link>https://www.sec.gov/newsroom/press-releases/example</link>
        <pubDate>Tue, 04 Aug 2026 12:00:00 GMT</pubDate>
        <description>Official release</description></item></channel></rss>"""
        discovery._fetch_bytes = lambda url: (primary_fixture, "")
        primary, error = discovery.fetch_primary_feed("U.S. Securities and Exchange Commission", "https://www.sec.gov/news/pressreleases.rss")
        if error or len(primary) != 1 or not primary[0]["link"].startswith("https://www.sec.gov/"):
            raise AssertionError(f"Primary-feed discovery failed: {primary} / {error}")
    finally:
        discovery._fetch_bytes = original_fetch_bytes

    # A Tier-2 lead that lands only on approved secondary reporting must also
    # be found outside the curator bibliography. Primary/company evidence may
    # stand on its own, and one curator may not occupy both visible slots.
    tier2_item = _item(
        "Banks arrange major AI data center debt financing for Anthropic",
        "Reuters",
        "https://www.reuters.com/business/anthropic-financing-tier2",
        description="AI infrastructure financing and debt for a data center project.",
    )
    tier2_item["discovered_via"] = "Abnormal Returns"
    tier2_candidate, tier2_audit = evaluate_item(tier2_item, domain="finance", current=current, provider="tier2_outbound")
    if tier2_candidate is None:
        raise AssertionError(f"Tier-2 approved outbound fixture failed initial qualification: {tier2_audit}")
    rejected = discovery._enforce_tier2_evidence_boundary([(tier2_candidate, tier2_audit)])
    if rejected or tier2_audit.get("decision") != "rejected_tier2_unverified":
        raise AssertionError(f"Unverified Tier-2 secondary lead crossed the bibliography boundary: {tier2_audit}")

    independent_item = _item(
        "Banks arrange major AI data center debt financing for Anthropic",
        "Financial Times",
        "https://www.ft.com/content/anthropic-financing-independent",
        description="AI infrastructure financing and debt for a data center project.",
    )
    independent_candidate, independent_audit = evaluate_item(independent_item, domain="finance", current=current, provider="google_news_rss")
    tier2_candidate, tier2_audit = evaluate_item(tier2_item, domain="finance", current=current, provider="tier2_outbound")
    verified = discovery._enforce_tier2_evidence_boundary([
        (independent_candidate, independent_audit),
        (tier2_candidate, tier2_audit),
    ])
    if len(verified) != 2 or tier2_candidate.get("verification_status") != "independently_retrieved":
        raise AssertionError(f"Independently retrieved Tier-2 lead did not clear verification: {tier2_audit}")

    tier2_ranked = [
        {"event_id": "tier2-a", "rank_score": 150, "discovery_provider": "tier2_outbound"},
        {"event_id": "tier2-b", "rank_score": 145, "discovery_provider": "tier2_outbound"},
        {"event_id": "direct-a", "rank_score": 140, "discovery_provider": "google_news_rss"},
    ]
    tier2_selection = discovery._select_ranked_domain_events(tier2_ranked, 2)
    if [item["event_id"] for item in tier2_selection] != ["tier2-a", "direct-a"]:
        raise AssertionError(f"Tier-2 discovery source monopolized the visible context surface: {tier2_selection}")

    discovery_only = assess_source("Techmeme", "https://www.techmeme.com")
    if discovery_only.auto_eligible or discovery_only.evidence_role != "discovery":
        raise AssertionError("Tier-2 discovery source became Reader-facing evidence.")
    company_release = assess_source("Business Wire", "https://www.businesswire.com")
    if not company_release.auto_eligible or company_release.evidence_role != "company_statement":
        raise AssertionError("Company-issued release path lost its explicit non-independent evidence role.")

    # Selected source-grounded automated events must survive the full persistence
    # boundary. Pre-grounding automated rows are intentionally ineligible.
    # confirmed/corroborated rows.  Exercise select -> persist -> reload ->
    # attach -> render so that failure cannot recur invisibly.
    automated_market = {
        "event_id": "roundtrip-market-reported",
        "event_date": "2026-08-04",
        "domain": "market",
        "event_type": "reported_development",
        "priority": 180.0,
        "rank_score": 180.0,
        "verified_fact": "Airbnb shares surged 15% after the company raised annual guidance following stronger AI-linked operating results.",
        "platform_relevance": "The stronger outlook and share-price reaction show investors repricing realized AI-linked growth outside the core infrastructure suppliers.",
        "source_name": "Reuters",
        "source_label": "Reuters",
        "source_url": "https://www.reuters.com/business/roundtrip-market-2026-08-04/",
        "source_type": "news",
        "source_tier": "preferred",
        "evidence_role": "secondary",
        "verification_status": "reported",
        "status": "Reported",
        "discovery_provider": "google_news_rss",
        "discovery_query": "AI earnings guidance",
        "discovered_via": "google_news_rss",
        "grounding_version": GROUNDING_VERSION,
        "grounding_status": "grounded",
        "source_text_method": "fixture_body",
        "source_text_chars": 900,
        "source_evidence_hash": "grounded-market-fixture",
    }
    automated_finance = {
        "event_id": "roundtrip-finance-independent",
        "event_date": "2026-08-04",
        "domain": "finance",
        "event_type": "reported_development",
        "priority": 175.0,
        "rank_score": 175.0,
        "verified_fact": "Banks arranged a large refinancing for an AI data-center project backed by a major technology company.",
        "platform_relevance": "The refinancing puts a market price on a large AI-infrastructure exposure and shows the terms on which outside investors are willing to fund it.",
        "source_name": "Financial Times",
        "source_label": "Financial Times",
        "source_url": "https://www.ft.com/content/roundtrip-finance",
        "source_type": "news",
        "source_tier": "preferred",
        "evidence_role": "secondary",
        "verification_status": "independently_retrieved",
        "status": "Independently reported",
        "discovery_provider": "tier2_outbound",
        "discovery_query": "AI data center debt financing",
        "discovered_via": "Abnormal Returns",
        "grounding_version": GROUNDING_VERSION,
        "grounding_status": "grounded",
        "source_text_method": "fixture_body",
        "source_text_chars": 900,
        "source_evidence_hash": "grounded-finance-fixture",
        "evidence_resolution_mode": "alternate_source",
        "evidence_seed_source_name": "Reuters",
        "evidence_seed_source_url": "https://www.reuters.com/business/seed-finance",
        "evidence_resolution_query": "AI data center debt refinancing 15 billion",
        "evidence_resolution_similarity": 0.91,
    }
    automated_primary = {
        "event_id": "roundtrip-primary",
        "event_date": "2026-08-04",
        "domain": "finance",
        "event_type": "reported_development",
        "priority": 160.0,
        "rank_score": 160.0,
        "verified_fact": "Federal Reserve FOMC cut interest rates by 25 basis points.",
        "platform_relevance": "The policy change lowers borrowing costs and discount-rate pressure for long-duration AI infrastructure.",
        "source_name": "Federal Reserve",
        "source_label": "Federal Reserve",
        "source_url": "https://www.federalreserve.gov/newsevents/pressreleases/roundtrip.htm",
        "source_type": "official_statement",
        "source_tier": "primary",
        "evidence_role": "official_statement",
        "verification_status": "primary",
        "status": "Primary record",
        "discovery_provider": "primary_feed",
        "discovery_query": "Federal Reserve releases",
        "discovered_via": "primary_feed",
        "grounding_version": GROUNDING_VERSION,
        "grounding_status": "grounded",
        "source_text_method": "fixture_body",
        "source_text_chars": 900,
        "source_evidence_hash": "grounded-primary-fixture",
    }
    automated_company = {
        "event_id": "roundtrip-company",
        "event_date": "2026-08-04",
        "domain": "market",
        "event_type": "reported_development",
        "priority": 150.0,
        "rank_score": 150.0,
        "verified_fact": "Microsoft announced the acquisition of an optical-networking supplier serving data-center customers.",
        "platform_relevance": "The transaction shifts control of a network capability used in large data-center deployments and can redirect future growth and pricing power.",
        "source_name": "Business Wire",
        "source_label": "Business Wire",
        "source_url": "https://www.businesswire.com/news/home/roundtrip",
        "source_type": "company_statement",
        "source_tier": "company_release",
        "evidence_role": "company_statement",
        "verification_status": "company_statement",
        "status": "Company statement",
        "discovery_provider": "google_news_rss",
        "discovery_query": "AI company guidance",
        "discovered_via": "google_news_rss",
        "grounding_version": GROUNDING_VERSION,
        "grounding_status": "grounded",
        "source_text_method": "fixture_body",
        "source_text_chars": 900,
        "source_evidence_hash": "grounded-company-fixture",
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.csv"
        added = discovery.merge_selected_into_registry(
            {
                "market": [automated_market, automated_company],
                "finance": [automated_finance, automated_primary],
            },
            path=path,
            retrieved_at="2026-08-04T12:00:00+00:00",
        )
        if added != 4:
            raise AssertionError(f"Automated Current Context round-trip did not persist all fixtures: {added}")
        persisted = pd.read_csv(path)
        forbidden_body_columns = {"source_body", "article_body", "body_text", "source_text"}.intersection(persisted.columns)
        if forbidden_body_columns:
            raise AssertionError(f"Full fetched source text leaked into the Current Context ledger: {sorted(forbidden_body_columns)}")
        if "source_evidence_hash" not in persisted.columns or not persisted["source_evidence_hash"].fillna("").astype(str).str.strip().all():
            raise AssertionError("Grounded automated rows lost their non-reversible source evidence hash.")
        reloaded = load_current_context(as_of="2026-08-04", path=path, limit_per_domain=2)
        market_events = [event for event in reloaded["by_domain"]["market"]["events"] if event.get("verification_status") != "no_match"]
        finance_events = [event for event in reloaded["by_domain"]["finance"]["events"] if event.get("verification_status") != "no_match"]
        if len(market_events) != 2 or len(finance_events) != 2:
            raise AssertionError(
                "Selected automated Market/Finance events were lost across retained reload: "
                f"market={market_events}, finance={finance_events}"
            )
        observed_statuses = {event.get("verification_status") for event in [*market_events, *finance_events]}
        if observed_statuses != {"reported", "company_statement", "independently_retrieved", "primary"}:
            raise AssertionError(f"Retained reload changed automated evidence-status semantics: {observed_statuses}")
        reloaded_alt = next(event for event in finance_events if event.get("event_id") == "roundtrip-finance-independent")
        if reloaded_alt.get("evidence_resolution_mode") != "alternate_source":
            raise AssertionError(f"Alternate-evidence provenance was lost across retained reload: {reloaded_alt}")
        if reloaded_alt.get("evidence_seed_source_name") != "Reuters" or reloaded_alt.get("source_name") != "Financial Times":
            raise AssertionError(f"Discovery-to-evidence lineage was not preserved across retained reload: {reloaded_alt}")
        attached = _attach_current_context(
            {
                "headline": "Financing conditions changed.",
                "summary": "Retained fundamentals remain the analytical base.",
                "references": [],
            },
            reloaded["by_domain"]["finance"],
        )
        roundtrip_markup = build_domain_read_html(attached, label="Finance Read", accent_color="#a78bfa")
        if "Recent developments" not in roundtrip_markup or "Financial Times reports" in roundtrip_markup:
            raise AssertionError("Persisted Finance context failed to reach the shared Recent developments renderer.")
        if "Banks arranged a large refinancing for an AI data-center project" not in roundtrip_markup:
            raise AssertionError("Source-grounded Finance copy was lost across retained reload.")
        if "The development may change" in roundtrip_markup:
            raise AssertionError("Generic Current Context consequence boilerplate entered a grounded row.")

        # Grounding version is provenance, not a freshness kill switch. A row
        # that cleared the durable source-grounded evidence contract must remain
        # eligible until its time window expires.
        older_grounded = dict(automated_finance)
        older_grounded["event_id"] = "durable-grounded-finance"
        older_grounded["grounding_version"] = "2.3"
        older_grounded["verified_fact"] = "Banks arranged a $15 billion refinancing for an AI data-center project."
        older_grounded["source_text_chars"] = 689
        older_grounded["source_evidence_hash"] = "durable-evidence-hash"
        durable_path = Path(tmp) / "durable.csv"
        if discovery.merge_selected_into_registry(
            {"finance": [older_grounded]},
            path=durable_path,
            retrieved_at="2026-08-04T10:00:00+00:00",
        ) != 1:
            raise AssertionError("Durable grounded row was not written.")
        durable_context = load_current_context(as_of="2026-08-09", path=durable_path, limit_per_domain=2)
        durable_finance = [
            event for event in durable_context["by_domain"]["finance"]["events"]
            if event.get("verification_status") != "no_match"
        ]
        if not durable_finance or durable_finance[0].get("event_id") != "durable-grounded-finance":
            raise AssertionError("A still-fresh grounded row was invalidated solely by grounding-version drift.")

        # Rediscovering the same event must replace the current registry row
        # with newer vetted provenance rather than silently discarding it.
        newer_grounded = dict(older_grounded)
        newer_grounded["grounding_version"] = GROUNDING_VERSION
        newer_grounded["verified_fact"] = "Banks began marketing the $15 billion refinancing to bond investors."
        newer_grounded["source_evidence_hash"] = "newer-evidence-hash"
        if discovery.merge_selected_into_registry(
            {"finance": [newer_grounded]},
            path=durable_path,
            retrieved_at="2026-08-09T12:00:00+00:00",
        ) != 1:
            raise AssertionError("Current Context registry did not upsert rediscovered vetted event.")
        durable_rows = pd.read_csv(durable_path)
        same_event = durable_rows[durable_rows["event_id"].astype(str) == "durable-grounded-finance"]
        if len(same_event) != 1 or "began marketing" not in str(same_event.iloc[0]["verified_fact"]):
            raise AssertionError(f"Registry kept stale duplicate instead of the most recent vetted row: {same_event.to_dict('records')}")
        if "References" not in roundtrip_markup:
            raise AssertionError("Persisted Finance context lost its references during Read attachment.")

    # Market/Finance may show two qualified developments, but never more.
    dual = pd.DataFrame([
        _fresh_event("market-one", "2026-08-04", 180, "Reuters reports earnings and raises guidance", domain="market"),
        _fresh_event("market-two", "2026-08-03", 170, "Bloomberg reports a large technology acquisition", domain="market"),
    ])
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.csv"
        pd.concat([base, dual], ignore_index=True).to_csv(path, index=False)
        two = load_current_context(as_of="2026-08-04", path=path, limit_per_domain=2)
        visible = [event for event in two["by_domain"]["market"]["events"] if event.get("verification_status") != "no_match"]
        if len(visible) != 2:
            raise AssertionError(f"Market did not retain exactly two qualified developments when two were available: {visible}")

    market_context = context["by_domain"]["market"]
    event = market_context["events"][0]
    read = {
        "headline": "Current results changed the market signal.",
        "analysis": "The retained market data remain primary; the event layer explains why the latest return contribution moved.",
        "confidence": "high",
        "current_context_items": [{
            "text": event["display"],
            "reference_number": event.get("reference_number"),
            "source_url": event.get("source_url", ""),
        }],
        "references": market_context["references"],
    }
    markup = build_domain_read_html(read, label="Market Read", accent_color="#a78bfa")
    if ">Watch<" in markup or "watchpoint" in markup.casefold():
        raise AssertionError("Retired Watch UI leaked back into the visible Read component.")
    if not (markup.index("Recent developments") < markup.index("References")):
        raise AssertionError("Current Context did not retain the compact read order.")
    if market_context["references"] and ('<a class="rm-domain-read-context-citation"' not in markup or "[1]" not in markup):
        raise AssertionError("Current Context is missing its inline source citation.")
    if "<ol" in markup or "<li" in markup:
        raise AssertionError("References regressed to a stacked list.")

    print(
        "PASS  Auditable Current Context · eleven-domain manifest · explicit rejection reasons · "
        "source-grounded synthesis · single-owner display · legitimate no-match supported"
    )


if __name__ == "__main__":
    main()
