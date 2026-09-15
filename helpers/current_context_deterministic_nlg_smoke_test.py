"""End-to-end fixtures for deterministic Current Context event composition.

These fixtures intentionally preserve the failure shapes observed in live
publisher output.  They exercise ground_candidate -> source qualification ->
semantic event extraction -> deterministic realization -> final domain gate.
No OpenAI/model call is involved.
"""
from __future__ import annotations

from pathlib import Path
import sys
import types

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

if "streamlit" not in sys.modules:
    fake_streamlit = types.ModuleType("streamlit")
    fake_streamlit.cache_data = lambda *args, **kwargs: (args[0] if args and callable(args[0]) else (lambda fn: fn))
    sys.modules["streamlit"] = fake_streamlit

import loaders.current_context_grounding as grounding
from loaders.current_context_composer import compose_development, strict_domain_fit
from loaders.current_context_discovery import (
    _cluster_all_grounding_candidates,
    _cluster_grounding_candidates,
    _ground_domain_candidates,
    _reader_renderable_assigned,
    _registry_row,
    _routine_grounding_candidates,
    _select_significant_events,
    discover_approved_sources,
    evaluate_item,
)
from loaders.current_context_registry import _automated_row_still_qualifies, _curated_events
from loaders.current_context_news import _assign_event_owners
from config.current_context_policy import (
    APPROVED_SOURCE_SWEEP_QUERIES,
    assess_source_for_qualification,
    domain_news_queries,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def candidate(title: str, url: str = "https://example.com/story") -> dict:
    return {
        "discovery_title": title,
        "source_url": url,
        "publisher_url": "https://example.com",
        "source_name": "fixture publisher",
        "event_date": "2026-08-11",
        "lookback_days": 10,
        "qualification_tier": "A",
        "priority": 90,
    }


def ground(domain: str, title: str, body: str, *, published: str = "2026-08-10"):
    doc = grounding.SourceDocument(
        "https://example.com/story",
        "https://example.com/story",
        title,
        "",
        body,
        "fixture",
        published_date=published,
    )
    item = candidate(title)
    item["event_date"] = published
    return grounding.ground_candidate(
        item, domain=domain, fetcher=lambda *args, **kwargs: doc
    )


def main() -> None:
    # MARKET: a quantified metric is evidence, not the event nucleus.
    palantir_title = "Palantir earnings beat expectations as AI demand drives outlook"
    palantir_body = (
        "Revenue in the three months ended June 30 increased 93% year over year, totaling $1.94 billion, compared with the $1.801 billion that analysts were expecting. "
        "Palantir blew past Wall Street's financial targets in its second quarter and forecast strong growth in the coming months, sending its stock surging 13% in after-hours trading on Monday. "
        "The company said demand for its artificial intelligence software remained strong across commercial and government customers."
    )
    row, result = ground("market", palantir_title, palantir_body, published="2026-08-03")
    require(result.accepted and row is not None, f"Palantir fixture failed grounding: {result.reason}")
    fact = row["verified_fact"]
    require(fact == "Palantir earnings beat expectations as AI demand drives outlook.", f"Clean Market headline was not preserved: {fact}")
    require(fact.count(".") == 1, f"Market development was not reduced to one self-contained sentence: {fact}")

    # COMPUTE: capacity statistic is support; actor/action statement is primary.
    compute_title = "Nvidia explores HBM capacity cuts for next-generation AI chips"
    compute_body = (
        "Configurations with up to 81% less memory than originally announced specifications are being tested, a strategic retreat driven by surging memory prices and supply shortages. "
        "Nvidia, the world's largest artificial intelligence semiconductor company, is reportedly exploring plans to significantly reduce the high-bandwidth memory (HBM) capacity in its next-generation AI chips. "
        "The change would affect memory configurations paired with future GPU accelerators."
    )
    row, result = ground("compute", compute_title, compute_body)
    require(result.accepted and row is not None, f"Compute fixture failed grounding: {result.reason}")
    fact = row["verified_fact"]
    require(fact == "Nvidia explores HBM capacity cuts for next-generation AI chips.", f"Clean Compute headline was not preserved: {fact}")
    require(fact.count(".") == 1, f"Compute development was not reduced to one self-contained sentence: {fact}")

    # DATA CENTERS: a corroborated publisher title is semantic evidence, not a
    # verbatim heading pasted in front of the article.
    palm_title = "Palm Beach County Zoning Commission Approves AI Data Center Moratorium | BIG 105.9"
    palm_body = (
        "During the one-year moratorium, county officials plan to draft regulations addressing noise, water consumption, electrical demand, land-use compatibility and where future facilities can be located. "
        "The moratorium applies to new large-scale data center projects while the county develops permanent zoning standards."
    )
    row, result = ground("data_center", palm_title, palm_body)
    require(result.accepted and row is not None, f"Palm Beach fixture failed grounding: {result.reason}")
    fact = row["verified_fact"]
    require(fact == "Palm Beach County Zoning Commission Approves AI Data Center Moratorium.", f"Corroborated publisher title was not preserved cleanly: {fact}")
    require("| BIG 105.9" not in fact, f"Publisher suffix leaked into Reader: {fact}")

    # CONNECTIVITY: duplicate title/body statements collapse to one event.
    verizon_title = "Verizon blames Sunday's network outage in Southern California on multiple fiber cuts"
    verizon_body = (
        "As vandals caused mobile and Internet disruption for 12,000 customers Verizon has blamed a network outage over the weekend on multiple fiber cuts. "
        "Service was restored after crews repaired the damaged fiber routes."
    )
    row, result = ground("connectivity", verizon_title, verizon_body)
    require(result.accepted and row is not None, f"Verizon fixture failed grounding: {result.reason}")
    fact = row["verified_fact"]
    require(fact == "Verizon blames Sunday's network outage in Southern California on multiple fiber cuts.", f"Clean publisher headline was not preserved: {fact}")

    # FINANCE: a generic I-bond explainer has financial vocabulary but is not an
    # AI Macro financing event. It must not be rehabilitated into a development.
    ibond_title = "I bonds and inflation protection: how the current rate works"
    ibond_body = (
        "Subsequent rate updates dropped the annualized rate to 6.89% and then 4.3%, but the current annualized rate for I bonds purchased through October 2026 is 4.26%. "
        "I bonds are U.S. savings bonds designed to protect household savings from inflation. "
        "The rate combines a fixed component with a component linked to consumer prices."
    )
    row, result = ground("finance", ibond_title, ibond_body)
    require(row is None and not result.accepted, f"Generic I-bond explainer remained Finance-eligible: {row and row.get('verified_fact')}")

    # WATER: an article may mention water elsewhere, but a zoning-permit event
    # cannot qualify as Water unless the realized event itself is about water.
    water_title = "Formal permit application filed for Tuckahoe Tech Park data center campus in Goochland"
    water_body = (
        "Unlike the rest of the district, where data center projects can be built by-right, projects proposed within TOD West must seek a conditional use permit and go through the related public hearing process. "
        "Developers said the proposed campus would use reclaimed water in a closed-loop cooling system. "
        "County planning staff will review the permit application before a public hearing."
    )
    row, result = ground("water", water_title, water_body)
    require(row is None and not result.accepted, f"Non-water permit event leaked into Water: {row and row.get('verified_fact')}")

    # ADOPTION: wire dateline/appositive furniture is removed while the actual
    # investment/partnership and a same-event scale fact survive.
    humain_title = "HUMAIN invests in MOZN and partners to co-build enterprise AI solutions"
    humain_body = (
        "RIYADH, Saudi Arabia, Aug. 3, 2026 /PRNewswire/ -- HUMAIN, a PIF company delivering full-stack artificial intelligence capabilities globally, today announced a strategic investment in and partnership with MOZN a global leader in enterprise AI for high-assurance domains, based in Saudi Arabia. "
        "The investment builds on MOZN's momentum as a regional enterprise AI provider serving more than 150 customers across financial services and the public sector. "
        "The companies plan to co-build enterprise AI products for regulated industries."
    )
    row, result = ground("adoption", humain_title, humain_body, published="2026-08-03")
    require(result.accepted and row is not None, f"HUMAIN fixture failed grounding: {result.reason}")
    fact = row["verified_fact"]
    require(fact == "HUMAIN invests in MOZN and partners to co-build enterprise AI solutions.", f"Clean Adoption headline was not preserved: {fact}")
    require("PRNewswire" not in fact and not fact.startswith("RIYADH"), f"Wire dateline leaked into Adoption: {fact}")

    # WORKFORCE: run-on extraction is repaired, but historical comparison and
    # anonymous-report fragments do not become an event nucleus. A weak source
    # is rejected rather than published as contextless statistics.
    workforce_title = "Report says worst AI-related labor fears are not materializing yet"
    workforce_body = (
        "The report stated that at this time last year, 806,383 layoffs had been announced compared to only 477,033 this year.However, at this point last year, DOGE had announced more than 275,000 layoffs, spiking the numbers.The Technology sector had the most announced layoffs at 9,867 in July. "
        "Hiring trends varied widely across industries."
    )
    parts = grounding._split_sentences(workforce_body)
    require(any(item.startswith("However,") for item in parts), f"No-space sentence boundary was not repaired: {parts}")
    row, result = ground("workforce", workforce_title, workforce_body)
    require(row is None and not result.accepted, f"Contextless Workforce statistics were published: {row and row.get('verified_fact')}")

    # LIVE FAILURE SHAPES: when the article body/extractor contains malformed
    # grammar but a corroborated publisher headline is clean, preserve the
    # human-edited headline instead of mechanically re-conjugating it.
    salvage_cases = [
        (
            "data_center",
            "Moffat County commissioners delay decision on data center moratorium in order to seek public input",
            "Moffat County commissioners delay decision on data center moratorium in ordered to seek public input. Commissioners considered a six-month moratorium on new data center applications.",
        ),
        (
            "power",
            "Google signs long-term power agreement for AI infrastructure",
            "Google to added that it has signed a 22-year power purchase agreement with Fortum for electricity supporting data centers.",
        ),
    ]
    for domain, title, body in salvage_cases:
        row, result = ground(domain, title, body)
        require(result.accepted and row is not None, f"Clean {domain} headline was lost because body extraction was damaged: {result.reason}")
        require(row["verified_fact"] == f"{title}.", f"{domain} headline was mechanically corrupted: {row['verified_fact']}")

    # A clean headline does not rescue an unquantified, low-specificity adoption
    # article. Source quality and domain materiality still have to be real.
    everpure_title = "Everpure report links dark data to enterprise AI deployment barriers"
    everpure_body = "Everpure reported links dark data to enterprise AI deployment barriers. The report surveyed enterprise technology leaders."
    row, result = ground("adoption", everpure_title, everpure_body)
    require(row is None and not result.accepted, f"Generic Adoption commentary became a Reader development: {row and row.get('verified_fact')}")

    repaired = grounding._split_sentences("Oracle announced another round of workforce reductions affecting several business units.According to the filing, headcount declined further across the company.")
    require(len(repaired) == 2 and repaired[1].startswith("According"), f"Generic no-space boundary was not repaired: {repaired}")


    # Source quality never relaxes merely to fill domain coverage. Unknown
    # Google News publishers remain discovery leads even at the loosest tier,
    # while approved national sources such as Axios are unattended-eligible.
    weak_sources = (
        ("Tech Times", "https://www.techtimes.com/example"),
        ("Quiver Quantitative", "https://www.quiverquant.com/news/example"),
        ("finchannel", "https://finchannel.com/example"),
        ("KLSE Screener", "https://www.klsescreener.com/example"),
    )
    for source_name, source_url in weak_sources:
        weak = assess_source_for_qualification(
            source_name,
            source_url.rsplit("/", 1)[0],
            source_url,
            provider="google_news_rss",
            tier_key="E",
        )
        require(not weak.auto_eligible, f"Unapproved Google News publisher became Reader-eligible: {source_name} · {weak}")
    axios = assess_source_for_qualification(
        "Axios",
        "https://www.axios.com",
        "https://www.axios.com/example",
        provider="google_news_rss",
        tier_key="A",
    )
    require(axios.auto_eligible and axios.tier == "preferred", f"Axios was not recognized as an approved national source: {axios}")


    # Selection is significance-first but the feed has a useful-output target.
    # Once an event has passed approved-source grounding, lower qualification
    # tiers are ranking signals rather than a second publication veto. Sparse
    # evidence still publishes what exists; a deep pool should yield 10-15.
    assigned = {domain: [] for domain in (
        "market", "finance", "compute", "data_center", "connectivity", "power",
        "grid_storage", "water", "adoption", "workforce", "economic_impact"
    )}
    assigned["market"] = [{
        "event_id": "market-a", "qualification_tier": "A", "rank_score": 120.0,
        "event_date": "2026-09-14", "verified_fact": "Major AI market event.",
    }]
    for index, domain in enumerate(("finance", "compute", "data_center", "connectivity", "power"), start=1):
        assigned[domain] = [{
            "event_id": f"tier-d-{index}", "qualification_tier": "D", "rank_score": 90.0 - index,
            "event_date": "2026-09-14", "verified_fact": f"Distinct approved {domain} development {index}.",
        }]
    selected, coverage = _select_significant_events(assigned)
    require(sum(len(items) for items in selected.values()) == 6, f"Sparse grounded pool was over-filtered: {selected}")
    require(coverage.get("selection_basis") == "significance_first", f"Wrong Current Context selection basis: {coverage}")

    deep_assigned = {domain: [] for domain in assigned}
    domains = list(deep_assigned)
    for index in range(20):
        domain = domains[index % len(domains)]
        deep_assigned[domain].append({
            "event_id": f"deep-{index}", "qualification_tier": "A", "rank_score": 200.0 - index,
            "event_date": "2026-09-14", "verified_fact": f"Distinct approved development {index}.",
        })
    deep_selected, deep_coverage = _select_significant_events(deep_assigned)
    require(sum(len(items) for items in deep_selected.values()) == 15, f"Deep approved pool did not produce the 15-item cap: {deep_selected}")
    require(deep_coverage.get("selection_target_min") == 10 and deep_coverage.get("selection_target_max") == 15, f"Selection target missing from diagnostics: {deep_coverage}")

    daily_source = (PROJECT_ROOT / "loaders" / "current_context_daily.py").read_text(encoding="utf-8")
    require("coverage_floor_not_met_retained_fallback" not in daily_source, "Daily Current Context still treats domain count as a publication gate")

    # Market discovery includes cross-cutting AI-lab leadership and development
    # shifts so a major Altman/Amodei slowdown story is discoverable before it
    # happens to fit a narrow earnings/capex query.
    market_queries = " ".join(domain_news_queries("market"))
    require("Sam Altman" in market_queries and "Dario Amodei" in market_queries, "Major AI-lab leadership query is missing from market discovery")


    # PRODUCTION MISS REGRESSION: the September 2026 Altman/Amodei slowdown
    # story is exactly the kind of cross-cutting AI development this layer must
    # discover and retain. Preserve the clean source headline and both named
    # organizations instead of reducing it to a generic safety fragment.
    slowdown_title = "Anthropic, OpenAI CEOs call for slowdown in AI development"
    slowdown_body = (
        "Anthropic CEO Dario Amodei called for slowing the pace of AI development. "
        "OpenAI CEO Sam Altman said he agreed that the industry should slow down and take more time to address safety risks."
    )
    row, result = ground("market", slowdown_title, slowdown_body, published="2026-09-12")
    require(result.accepted and row is not None, f"Altman/Amodei slowdown fixture was missed: {result.reason}")
    require(row["verified_fact"] == f"{slowdown_title}.", f"Major AI-lab slowdown headline was degraded: {row['verified_fact']}")
    require("Anthropic" in row["verified_fact"] and "OpenAI" in row["verified_fact"], "Cross-lab slowdown event lost its named subjects")

    # TOP-TIER TRANSPORT FALLBACK: an inaccessible Google News wrapper or
    # publisher page must not make the feed blind to a self-contained Reuters /
    # Axios development.  Preserve only the trusted publisher headline; do not
    # invent body details.  The resulting row must survive the retained Reader
    # contract even though it intentionally has no article-body character count.
    transport_candidate = candidate(
        slowdown_title,
        url="https://news.google.com/rss/articles/example-opaque-id",
    )
    transport_candidate.update({
        "domain": "market",
        "owner_domain": "market",
        "source_name": "Axios",
        "publisher_url": "https://www.axios.com",
        "event_date": "2026-09-12",
        "discovery_provider": "google_news_rss",
        "qualification_tier": "A",
        "qualification_tier_label": "Preferred",
        "rank_score": 130.0,
        "priority": 130.0,
    })
    transport_doc = grounding.SourceDocument(
        transport_candidate["source_url"],
        transport_candidate["source_url"],
        "",
        "",
        "",
        "",
        error="Google News wrapper did not expose decode parameters",
    )
    row, result = grounding.ground_candidate(
        transport_candidate,
        domain="market",
        fetcher=lambda *args, **kwargs: transport_doc,
    )
    require(result.accepted and row is not None, f"Top-tier headline fallback failed: {result.reason} / {result.error}")
    require(row["verified_fact"] == f"{slowdown_title}.", f"Headline fallback rewrote the publisher headline: {row['verified_fact']}")
    require(row.get("evidence_resolution_mode") == "trusted_headline_metadata", f"Wrong fallback provenance: {row.get('evidence_resolution_mode')}")
    require(row.get("source_text_method") == "trusted_publisher_headline", f"Wrong fallback source method: {row.get('source_text_method')}")

    # APPROVED HEADLINE IS FIRST-CLASS EVIDENCE EVEN WHEN THE PAGE LOADS. The
    # body may be sparse, paywall-truncated, or simply begin with consequences;
    # it no longer has to restate a clean Reuters/Axios headline before the
    # bounded headline claim can enter Current Context.
    loaded_candidate = candidate(
        "Microsoft signs new power agreement for Wisconsin AI data center",
        url="https://www.reuters.com/example/microsoft-wisconsin-power",
    )
    loaded_candidate.update({
        "domain": "power",
        "owner_domain": "power",
        "source_name": "Reuters",
        "publisher_url": "https://www.reuters.com",
        "event_date": "2026-09-12",
        "discovery_description": "Microsoft signed a power agreement supporting its Wisconsin AI data center.",
        "discovery_provider": "google_news_rss",
        "qualification_tier": "A",
        "qualification_tier_label": "Preferred",
        "rank_score": 121.0,
        "priority": 121.0,
    })
    loaded_doc = grounding.SourceDocument(
        loaded_candidate["source_url"], loaded_candidate["source_url"],
        loaded_candidate["discovery_title"], "", "Subscriber-only article body.", "html_paragraphs",
        published_date="2026-09-12",
    )
    loaded_row, loaded_result = grounding.ground_candidate(
        loaded_candidate, domain="power", fetcher=lambda *args, **kwargs: loaded_doc
    )
    require(loaded_result.accepted and loaded_row is not None, f"Approved loaded headline still depended on body restatement: {loaded_result.reason}")
    require(loaded_row.get("source_text_method") == "trusted_publisher_headline", f"Approved loaded headline used the wrong evidence mode: {loaded_row}")

    stale_doc = grounding.SourceDocument(
        loaded_candidate["source_url"], loaded_candidate["source_url"],
        loaded_candidate["discovery_title"], "", "Older article body.", "html_paragraphs",
        published_date="2026-08-01",
    )
    stale_row, stale_result = grounding.ground_candidate(
        loaded_candidate, domain="power", fetcher=lambda *args, **kwargs: stale_doc
    )
    require(stale_row is None and "predates the Current Context window" in stale_result.reason, f"Headline-first evidence bypassed stale-page protection: {stale_result.reason}")

    # REGRESSION: approved publisher headlines are not re-qualified by AI
    # Macro's body-prose event-frame or Market-significance heuristics. These
    # headlines already cleared discovery relevance/materiality and are bounded
    # claims from approved publishers.
    nominal_headline_candidate = candidate(
        "Microsoft's new Wisconsin data center power agreement",
        url="https://news.google.com/rss/articles/reuters-wisconsin-power-nominal",
    )
    nominal_headline_candidate.update({
        "domain": "power",
        "owner_domain": "power",
        "source_name": "Reuters",
        "publisher_url": "https://www.reuters.com",
        "event_date": "2026-09-12",
        "discovery_description": "Microsoft reached a new electricity agreement for its Wisconsin AI data center.",
        "discovery_provider": "google_news_rss",
        "qualification_tier": "A",
        "qualification_tier_label": "Preferred",
        "rank_score": 118.0,
        "priority": 118.0,
    })
    require(grounding.reader_development_event_frame_issues(nominal_headline_candidate["discovery_title"]), "Fixture no longer exercises the retired event-frame veto")
    nominal_row, nominal_result = grounding.ground_candidate(
        nominal_headline_candidate, domain="power", fetcher=lambda *args, **kwargs: transport_doc
    )
    require(nominal_result.accepted and nominal_row is not None, f"Approved nominal headline was still re-qualified by event framing: {nominal_result.reason}")
    nominal_retained = _registry_row(nominal_row, retrieved_at="2026-09-15T05:00:00+00:00")
    require(_automated_row_still_qualifies(nominal_retained), "Approved nominal headline was grounded but discarded by retained requalification")

    ordinary_market_candidate = candidate(
        "Nvidia unveils AI networking platform for enterprise data centers",
        url="https://news.google.com/rss/articles/reuters-nvidia-networking",
    )
    ordinary_market_candidate.update({
        "domain": "market",
        "owner_domain": "market",
        "source_name": "Reuters",
        "publisher_url": "https://www.reuters.com",
        "event_date": "2026-09-12",
        "discovery_description": "Nvidia unveiled a new AI networking platform aimed at enterprise data centers.",
        "discovery_provider": "google_news_rss",
        "qualification_tier": "B",
        "qualification_tier_label": "Strong",
        "rank_score": 109.0,
        "priority": 109.0,
    })
    require(not grounding.market_event_is_significant(ordinary_market_candidate["discovery_title"], ordinary_market_candidate["discovery_description"]), "Fixture no longer exercises the retired Market significance veto")
    market_row, market_result = grounding.ground_candidate(
        ordinary_market_candidate, domain="market", fetcher=lambda *args, **kwargs: transport_doc
    )
    require(market_result.accepted and market_row is not None, f"Approved Market headline was still re-qualified by Market significance: {market_result.reason}")
    market_retained = _registry_row(market_row, retrieved_at="2026-09-15T05:00:00+00:00")
    require(_automated_row_still_qualifies(market_retained), "Approved Market headline was grounded but discarded by retained Market requalification")

    retained = _registry_row(row, retrieved_at="2026-09-15T05:00:00+00:00")
    require(_automated_row_still_qualifies(retained), "Trusted headline fallback was discarded immediately by the retained Reader contract")

    weak_transport = dict(transport_candidate)
    weak_transport.update({"source_name": "Tech Times", "publisher_url": "https://www.techtimes.com"})
    row, result = grounding.ground_candidate(
        weak_transport,
        domain="market",
        fetcher=lambda *args, **kwargs: transport_doc,
    )
    require(row is None and not result.accepted, "Unapproved publisher acquired trusted-headline fallback privileges")

    # APPROVED SPECIALIST TRANSPORT FALLBACK: a curated specialist source is
    # already approved evidence. A blocked page must not erase a clean,
    # self-contained publisher headline merely because its source-quality score
    # is below the former arbitrary 90-point fallback threshold.
    specialist_candidate = candidate(
        "PowerHouse files for 300MW data center campus outside Dallas-Fort Worth",
        url="https://news.google.com/rss/articles/dcd-opaque-id",
    )
    specialist_candidate.update({
        "domain": "data_center",
        "owner_domain": "data_center",
        "source_name": "Data Center Dynamics",
        "publisher_url": "https://www.datacenterdynamics.com",
        "event_date": "2026-09-12",
        "discovery_provider": "google_news_rss",
        "qualification_tier": "A",
        "qualification_tier_label": "Preferred",
        "rank_score": 118.0,
        "priority": 118.0,
    })
    row, result = grounding.ground_candidate(
        specialist_candidate,
        domain="data_center",
        fetcher=lambda *args, **kwargs: transport_doc,
    )
    require(result.accepted and row is not None, f"Approved specialist headline fallback failed: {result.reason} / {result.error}")
    require(row.get("evidence_resolution_mode") == "trusted_headline_metadata", "Approved specialist did not use headline provenance")

    # APPROVED HEADLINES ARE ALREADY EDITED COPY. Transport fallback must not
    # discard a clean Utility Dive/Reuters headline merely because AI Macro
    # would expand a regional acronym or an official's jurisdiction in prose it
    # composed itself. These are house-style preferences, not evidence damage.
    acronym_candidate = candidate(
        "ERCOT approves new large-load interconnection rules for data centers",
        url="https://news.google.com/rss/articles/utility-dive-ercot",
    )
    acronym_candidate.update({
        "domain": "grid_storage",
        "owner_domain": "grid_storage",
        "source_name": "Utility Dive",
        "publisher_url": "https://www.utilitydive.com",
        "event_date": "2026-09-12",
        "discovery_description": "ERCOT approved grid interconnection rules for large data center loads in Texas.",
        "discovery_provider": "google_news_rss",
        "qualification_tier": "A",
        "qualification_tier_label": "Preferred",
        "rank_score": 119.0,
        "priority": 119.0,
    })
    row, result = grounding.ground_candidate(
        acronym_candidate,
        domain="grid_storage",
        fetcher=lambda *args, **kwargs: transport_doc,
    )
    require(result.accepted and row is not None, f"Approved acronym headline was over-filtered: {result.reason} / {result.error}")
    require(row["verified_fact"] == "ERCOT approves new large-load interconnection rules for data centers.", f"Approved headline was rewritten: {row['verified_fact']}")
    retained = _registry_row(row, retrieved_at="2026-09-15T05:00:00+00:00")
    require(_automated_row_still_qualifies(retained), "Approved acronym headline did not survive retained Reader revalidation")
    retained_frame = __import__("pandas").DataFrame([retained])
    retained_frame["event_date"] = __import__("pandas").to_datetime(retained_frame["event_date"], errors="coerce").dt.normalize()
    retained_frame["expires_after_days"] = __import__("pandas").to_numeric(retained_frame["expires_after_days"], errors="coerce")
    retained_frame["priority"] = __import__("pandas").to_numeric(retained_frame["priority"], errors="coerce")
    require(
        len(_curated_events(retained_frame, __import__("pandas").Timestamp("2026-09-15"))) == 1,
        "Approved acronym headline passed qualification but disappeared on Reader registry load",
    )

    official_candidate = candidate(
        "Governor Abbott signs law streamlining permits for large data center projects",
        url="https://news.google.com/rss/articles/reuters-abbott-data-centers",
    )
    official_candidate.update({
        "domain": "data_center",
        "owner_domain": "data_center",
        "source_name": "Reuters",
        "publisher_url": "https://www.reuters.com",
        "event_date": "2026-09-12",
        "discovery_description": "Texas Governor Greg Abbott signed legislation affecting large data center permitting.",
        "discovery_provider": "google_news_rss",
        "qualification_tier": "A",
        "qualification_tier_label": "Preferred",
        "rank_score": 119.0,
        "priority": 119.0,
    })
    row, result = grounding.ground_candidate(
        official_candidate,
        domain="data_center",
        fetcher=lambda *args, **kwargs: transport_doc,
    )
    require(result.accepted and row is not None, f"Approved official headline was over-filtered: {result.reason} / {result.error}")

    damaged_candidate = candidate(
        "Google to added that it has signed a new data center power agreement",
        url="https://news.google.com/rss/articles/reuters-damaged-headline",
    )
    damaged_candidate.update({
        "domain": "power",
        "owner_domain": "power",
        "source_name": "Reuters",
        "publisher_url": "https://www.reuters.com",
        "event_date": "2026-09-12",
        "discovery_description": "Google signed a power agreement supporting a data center project.",
        "discovery_provider": "google_news_rss",
        "qualification_tier": "A",
        "qualification_tier_label": "Preferred",
        "rank_score": 119.0,
        "priority": 119.0,
    })
    row, result = grounding.ground_candidate(
        damaged_candidate,
        domain="power",
        fetcher=lambda *args, **kwargs: transport_doc,
    )
    require(row is None and not result.accepted, "Malformed approved headline bypassed hard-copy damage checks")
    require("hard copy damage" in result.reason, f"Malformed headline failed for the wrong reason: {result.reason}")

    # APPROVED METADATA MAY CARRY DOMAIN CONTEXT. A clean publisher headline
    # does not have to repeat the exact domain noun if the already-qualified
    # Google News metadata establishes it. Transport failure should not turn
    # that presentation choice into a source-grounding rejection.
    metadata_context_candidate = candidate(
        "Meta buys 1,500 acres near Monroe for major new campus",
        url="https://news.google.com/rss/articles/reuters-meta-campus",
    )
    metadata_context_candidate.update({
        "domain": "data_center",
        "owner_domain": "data_center",
        "source_name": "Reuters",
        "publisher_url": "https://www.reuters.com",
        "event_date": "2026-09-12",
        "discovery_description": "The land purchase is for a large AI data center campus in Louisiana.",
        "discovery_provider": "google_news_rss",
        "qualification_tier": "A",
        "qualification_tier_label": "Preferred",
        "rank_score": 121.0,
        "priority": 121.0,
    })
    row, result = grounding.ground_candidate(
        metadata_context_candidate,
        domain="data_center",
        fetcher=lambda *args, **kwargs: transport_doc,
    )
    require(result.accepted and row is not None, f"Qualified metadata context did not rescue approved headline transport failure: {result.reason}")
    require(row["verified_fact"] == "Meta buys 1,500 acres near Monroe for major new campus.", f"Metadata fallback altered clean publisher headline: {row['verified_fact']}")

    # DISCOVERY LEADS ARE LEADS, NOT EVIDENCE. An unapproved publisher may
    # nominate a highly material event so the resolver can search for approved
    # corroboration. Its own page must never be called as evidence, and the
    # resulting grounded row must point to the approved source.
    lead_item = {
        "title": "Samsung Foundry Pivots Half of 4nm Capacity to HBM4",
        "link": "https://www.techtimes.com/example-hbm4",
        "published": __import__("pandas").Timestamp("2026-09-12"),
        "source_name": "Tech Times",
        "source_url": "https://www.techtimes.com",
        "description": "Samsung is shifting foundry capacity toward HBM4 production for AI chips.",
    }
    lead_candidate, lead_audit = evaluate_item(
        lead_item,
        domain="compute",
        current=__import__("pandas").Timestamp("2026-09-15"),
        provider="google_news_rss",
    )
    require(lead_candidate is not None, f"Material unapproved discovery lead was discarded at metadata: {lead_audit.get('reason')}")
    require(bool(lead_candidate.get("requires_approved_evidence")), "Unapproved discovery lead was mistakenly marked as evidence")

    approved_item = {
        "title": "Samsung shifts foundry capacity toward HBM4 for AI chips",
        "link": "https://news.google.com/rss/articles/reuters-hbm4",
        "published": __import__("pandas").Timestamp("2026-09-12"),
        "source_name": "Reuters",
        "source_url": "https://www.reuters.com",
        "description": "Samsung is reallocating semiconductor foundry capacity toward HBM4 production used in AI accelerators.",
    }
    ground_calls = []
    def _lead_grounder(item, *, domain):
        ground_calls.append(str(item.get("source_name") or ""))
        require(str(item.get("source_name") or "") == "Reuters", "Unapproved discovery lead was fetched as evidence")
        grounded = dict(item)
        grounded.update({
            "verified_fact": "Samsung shifts foundry capacity toward HBM4 for AI chips.",
            "display": "Samsung shifts foundry capacity toward HBM4 for AI chips.",
            "grounding_status": "grounded",
            "source_text_method": "fixture",
            "source_text_chars": 500,
            "source_evidence_hash": "approvedfixture",
            "source_title": approved_item["title"],
            "source_published_date": "2026-09-12",
        })
        return grounded, grounding.GroundingResult(
            True,
            fact=grounded["verified_fact"],
            resolved_url=str(item.get("source_url") or ""),
            extraction_method="fixture",
            text_chars=500,
            evidence_hash="approvedfixture",
            reason="fixture approved evidence",
        )
    resolved = _ground_domain_candidates(
        [lead_candidate],
        [lead_audit],
        domain="compute",
        target_grounded=1,
        max_attempts=1,
        current=__import__("pandas").Timestamp("2026-09-15"),
        discovery_items=[approved_item],
        statuses=[],
        grounder=_lead_grounder,
        event_searcher=lambda *args, **kwargs: ([], ""),
    )
    require(len(resolved) == 1 and resolved[0].get("source_name") == "Reuters", "Discovery lead did not resolve through approved evidence")
    require(ground_calls == ["Reuters"], f"Unexpected discovery-lead evidence calls: {ground_calls}")

    # ROUTINE DISCOVERY IS SOURCE-FIRST. Hundreds of weak-source Google News
    # hits may remain in the audit, but they do not consume the daily grounding
    # budget. Important stories are acquired independently through the approved
    # publisher sweep instead of rehabilitating questionable URLs one by one.
    lead_audit_copy = dict(lead_audit)
    routine = _routine_grounding_candidates([lead_candidate], [lead_audit_copy])
    require(not routine, "Unapproved discovery lead still entered routine grounding")
    require(lead_audit_copy.get("decision") == "discovery_lead_observed", f"Weak-source lead was not preserved as audit-only: {lead_audit_copy}")

    require(APPROVED_SOURCE_SWEEP_QUERIES and all("site:" in query for _, query in APPROVED_SOURCE_SWEEP_QUERIES), "Approved-source sweep is not publisher-restricted")
    sweep_items = [
        {
            "title": "AI's most powerful CEOs hit the brakes - Axios",
            "link": "https://news.google.com/rss/articles/axios-brakes",
            "published": __import__("pandas").Timestamp("2026-09-13"),
            "source_name": "Axios",
            "source_url": "https://www.axios.com",
            "description": "Anthropic CEO Dario Amodei and OpenAI CEO Sam Altman supported slowing AI development and prioritizing safety over growth.",
        },
        {
            "title": "Nvidia partners with Aussie companies to bring 2GW online by 2027 - Data Center Dynamics",
            "link": "https://news.google.com/rss/articles/dcd-nvidia-australia",
            "published": __import__("pandas").Timestamp("2026-09-10"),
            "source_name": "Data Center Dynamics",
            "source_url": "https://www.datacenterdynamics.com",
            "description": "Nvidia is partnering with cloud providers and data center operators to expand AI infrastructure capacity, land, power and shell capacity.",
        },
        {
            "title": "Google, Xcel, others back MISO's zero-injection large-load proposal - Utility Dive",
            "link": "https://news.google.com/rss/articles/utility-miso",
            "published": __import__("pandas").Timestamp("2026-09-09"),
            "source_name": "Utility Dive",
            "source_url": "https://www.utilitydive.com",
            "description": "MISO's proposal would fast-track reviews for generating projects that supply large loads at the same substation, including colocated data centers.",
        },
    ]
    def _sweep_fetcher(query, *, days):
        return [dict(item) for item in sweep_items], ""
    def _sweep_grounder(item, *, domain):
        grounded = dict(item)
        fact = str(item.get("verified_fact") or item.get("discovery_title") or "").strip()
        if not fact.endswith("."):
            fact += "."
        grounded.update({
            "verified_fact": fact,
            "display": fact,
            "grounding_status": "grounded",
            "source_text_method": "fixture",
            "source_text_chars": 500,
            "source_evidence_hash": "sweepfixture",
            "source_title": str(item.get("discovery_title") or ""),
            "source_published_date": str(item.get("event_date") or ""),
        })
        return grounded, grounding.GroundingResult(
            True, fact=fact, resolved_url=str(item.get("source_url") or ""),
            extraction_method="fixture", text_chars=500, evidence_hash="sweepfixture",
            reason="fixture approved-source sweep",
        )
    sweep_grounded, sweep_audit, _ = discover_approved_sources(
        as_of=__import__("pandas").Timestamp("2026-09-15"),
        fetcher=_sweep_fetcher,
        grounder=_sweep_grounder,
    )
    sweep_events = [event for events in sweep_grounded.values() for event in events]
    require(len(sweep_events) >= 3, f"Publisher-first sweep failed to retain known important approved-source stories: {sweep_grounded}")
    require(len({event.get("domain") for event in sweep_events}) >= 3, f"Publisher-first sweep collapsed distinct stories into too few domains: {sweep_grounded}")
    require(all(not event.get("requires_approved_evidence") for event in sweep_events), "Publisher-first sweep emitted an unapproved evidence row")

    # PRE-GROUND EVENT CLUSTERING: three URLs about two developments must
    # consume two event slots, not three URL slots.  If the strongest source
    # cannot be fetched, another approved publisher in the same cluster gets an
    # immediate chance before any wider event search.
    clustered_candidates = [
        {
            "event_id": "slow-reuters", "event_date": "2026-09-13", "domain": "market",
            "owner_domain": "market", "verified_fact": "OpenAI and Anthropic leaders call for slower AI development",
            "discovery_title": "OpenAI and Anthropic leaders call for slower AI development",
            "discovery_description": "Sam Altman and Dario Amodei called for slowing the pace of frontier AI development.",
            "source_name": "Reuters", "source_url": "https://www.reuters.com/example/slow-ai",
            "publisher_url": "https://www.reuters.com", "rank_score": 120.0, "owner_score": 20.0,
            "qualification_tier": "A", "lookback_days": 7, "requires_approved_evidence": False,
        },
        {
            "event_id": "slow-axios", "event_date": "2026-09-13", "domain": "market",
            "owner_domain": "market", "verified_fact": "AI's most powerful CEOs hit the brakes",
            "discovery_title": "AI's most powerful CEOs hit the brakes",
            "discovery_description": "Anthropic CEO Dario Amodei and OpenAI CEO Sam Altman support slowing AI development.",
            "source_name": "Axios", "source_url": "https://www.axios.com/example/ai-brakes",
            "publisher_url": "https://www.axios.com", "rank_score": 118.0, "owner_score": 20.0,
            "qualification_tier": "A", "lookback_days": 7, "requires_approved_evidence": False,
        },
        {
            "event_id": "nvidia-link", "event_date": "2026-09-10", "domain": "market",
            "owner_domain": "market", "verified_fact": "d-Matrix adopts Nvidia NVLink Fusion for AI inference servers",
            "discovery_title": "d-Matrix adopts Nvidia NVLink Fusion for AI inference servers",
            "discovery_description": "The startup will integrate its Raptor processors into Nvidia data-center systems.",
            "source_name": "Reuters", "source_url": "https://www.reuters.com/example/dmatrix",
            "publisher_url": "https://www.reuters.com", "rank_score": 100.0, "owner_score": 16.0,
            "qualification_tier": "A", "lookback_days": 7, "requires_approved_evidence": False,
        },
    ]
    cluster_audit = [
        {"event_id": item["event_id"], "decision": "metadata_qualified", "grounding_status": "not_attempted"}
        for item in clustered_candidates
    ]
    clustered = _cluster_grounding_candidates(clustered_candidates, cluster_audit, domain="market")
    require(len(clustered) == 2, f"Duplicate event nominations were not clustered before grounding: {clustered}")
    slowdown_rep = next(item for item in clustered if "slow" in str(item.get("event_id")))
    require(int(slowdown_rep.get("_cluster_size", 0) or 0) == 2, f"Slowdown cluster size was not retained: {slowdown_rep}")
    require(sum(1 for row in cluster_audit if row.get("preground_clustered")) == 1, f"Clustered duplicate was not visible in audit: {cluster_audit}")

    cluster_calls = []
    def _cluster_grounder(item, *, domain):
        cluster_calls.append(str(item.get("source_name") or ""))
        if str(item.get("source_name") or "") == "Reuters" and "slow" in str(item.get("event_id") or ""):
            return None, grounding.GroundingResult(False, reason="fixture transport failure")
        grounded = dict(item)
        grounded.update({
            "verified_fact": str(item.get("verified_fact") or "") + ".",
            "display": str(item.get("verified_fact") or "") + ".",
            "grounding_status": "grounded", "source_text_method": "fixture",
            "source_text_chars": 500, "source_evidence_hash": "clusterfixture",
        })
        return grounded, grounding.GroundingResult(
            True, fact=grounded["verified_fact"], resolved_url=str(item.get("source_url") or ""),
            extraction_method="fixture", text_chars=500, evidence_hash="clusterfixture", reason="fixture cluster evidence",
        )
    cluster_grounded = _ground_domain_candidates(
        clustered, cluster_audit, domain="market", target_grounded=2, max_attempts=2,
        current=__import__("pandas").Timestamp("2026-09-15"), discovery_items=[], statuses=[],
        grounder=_cluster_grounder, event_searcher=lambda *args, **kwargs: ([], ""),
    )
    require(len(cluster_grounded) == 2, f"Distinct event bench did not survive clustered-source failover: {cluster_grounded}")
    require("Axios" in cluster_calls, f"Clustered approved alternate was not tried after representative transport failure: {cluster_calls}")

    # CENTRAL DISCOVERY-LANE MERGE: the same event nominated by different
    # lanes/domains is clustered before any source fetch.  A development that
    # is already current in the retained Reader is skipped rather than wasting
    # a fresh grounding slot.
    central_audit = [
        {"event_id": item["event_id"], "decision": "metadata_qualified", "grounding_status": "not_attempted", "domain_query": item["domain"]}
        for item in clustered_candidates
    ]
    central = _cluster_all_grounding_candidates(
        {
            "market": [clustered_candidates[0], clustered_candidates[2]],
            "finance": [clustered_candidates[1]],
        },
        central_audit,
        retained_events=[{
            "event_id": "retained-slow", "event_date": "2026-09-13", "domain": "market",
            "owner_domain": "market", "verified_fact": "Anthropic and OpenAI leaders call for slower AI development.",
            "source_url": "https://www.reuters.com/example/retained-slow",
        }],
    )
    require(sum(len(items) for items in central.values()) == 1, f"Central pre-ground merge did not skip retained duplicate / cluster lanes: {central}")
    require(central["market"] and central["market"][0].get("event_id") == "nvidia-link", f"Distinct non-retained event was lost during central clustering: {central}")
    require(sum(1 for row in central_audit if row.get("preground_retained_duplicate")) == 2, f"Already-current event nominations were not skipped before grounding: {central_audit}")

    # POST-GROUND OWNERSHIP MUST NOT RE-CLUSTER DISTINCT EVENTS. Discovery has
    # already clustered semantic duplicates before fetching. Compact grounded
    # summaries from the same company/domain can share most words while still
    # describe separate projects; ownership now removes only exact/near-exact
    # rewrites rather than running the broad discovery matcher again.
    distinct_grounded = {
        "data_center": [
            {
                "event_id": "google-texas-campus",
                "event_date": "2026-09-12",
                "domain": "data_center",
                "owner_domain": "data_center",
                "event_type": "reported_development",
                "verified_fact": "Google opens a new AI data center campus in Texas.",
                "source_title": "Google opens a new AI data center campus in Texas",
                "source_url": "https://www.reuters.com/example/google-texas",
                "owner_score": 18.0,
                "rank_score": 120.0,
            },
            {
                "event_id": "google-virginia-campus",
                "event_date": "2026-09-12",
                "domain": "data_center",
                "owner_domain": "data_center",
                "event_type": "reported_development",
                "verified_fact": "Google opens a new AI data center campus in Virginia.",
                "source_title": "Google opens a new AI data center campus in Virginia",
                "source_url": "https://www.reuters.com/example/google-virginia",
                "owner_score": 18.0,
                "rank_score": 119.0,
            },
        ]
    }
    owned_distinct = _assign_event_owners(distinct_grounded)
    require(len(owned_distinct["data_center"]) == 2, f"Post-ground ownership collapsed distinct grounded events: {owned_distinct}")

    # EMPIRICAL DOMAIN GATE: evidence may be quantitative even when the clean
    # Reader sentence does not mechanically repeat a number.
    econ_title = "BLS reports productivity accelerated as AI investment remained elevated"
    econ_body = (
        "The Bureau of Labor Statistics reported that nonfarm business sector labor productivity increased 2.2 percent in the second quarter as technology and AI investment remained elevated. "
        "Real output increased 2.5 percent and hours worked increased 0.3 percent."
    )
    row, result = ground("economic_impact", econ_title, econ_body, published="2026-09-12")
    require(result.accepted and row is not None, f"Quantified empirical release was rejected because compact Reader copy omitted a number: {result.reason}")

    # FINAL READER CONTRACT: materiality belongs to discovery/source
    # qualification, not to the wording of the compact display sentence.  A
    # fully grounded event must not disappear merely because its concise Reader
    # copy omits the extra keywords that helped the article metadata rank.
    compact_event = {
        "event_id": "fixture-power-materiality-decoupled",
        "event_date": "2026-09-12",
        "domain": "power",
        "owner_domain": "power",
        "event_type": "reported_development",
        "priority": 120.0,
        "rank_score": 120.0,
        "verified_fact": "Google announces new generation plan for AI infrastructure.",
        "source_name": "Reuters",
        "source_label": "Reuters",
        "source_url": "https://www.reuters.com/example-ai-power-agreement",
        "source_type": "news",
        "source_tier": "preferred",
        "evidence_role": "secondary",
        "verification_status": "reported",
        "status": "Reported",
        "grounding_version": grounding.GROUNDING_VERSION,
        "grounding_status": "grounded",
        "source_text_method": "html_paragraphs",
        "source_text_chars": 800,
        "source_evidence_hash": "fixturehash",
        "source_title": "Google announces new generation plan for AI infrastructure",
        "source_published_date": "2026-09-12",
        "source_modified_date": "",
        "evidence_resolution_mode": "direct_source",
        "qualification_tier": "A",
        "qualification_tier_label": "Preferred",
        "discovery_provider": "google_news_rss",
    }
    retained = _registry_row(compact_event, retrieved_at="2026-09-15T05:00:00+00:00")
    require(_automated_row_still_qualifies(retained), "Final Reader contract re-scored compact display prose as if it were discovery metadata")

    # LIVE-SPARSITY REGRESSION: once a fresh event is grounded, the retained
    # Reader contract must not silently turn a healthy 12-event pool back into
    # two or three stories. Provenance/freshness/copy integrity remain hard;
    # semantic qualification belongs upstream and happens once.
    batch_assigned = {domain: [] for domain in (
        "market", "finance", "compute", "data_center", "connectivity", "power",
        "grid_storage", "water", "adoption", "workforce", "economic_impact"
    )}
    batch_titles = [
        ("market", "Nvidia AI networking expansion for enterprise data centers"),
        ("market", "Microsoft AI infrastructure financing plans in focus"),
        ("finance", "Oracle's new financing package for cloud infrastructure"),
        ("compute", "AMD's next accelerator production program in Arizona"),
        ("data_center", "Google's new Virginia data center campus plan"),
        ("connectivity", "Lumen's expanded fiber capacity for AI campuses"),
        ("power", "Microsoft's new Wisconsin data center power agreement"),
        ("grid_storage", "ERCOT's new large-load interconnection framework"),
        ("water", "Phoenix reclaimed-water plan for new data center projects"),
        ("adoption", "Enterprise AI deployment growth across large companies"),
        ("workforce", "Technology hiring changes tied to AI deployment"),
        ("economic_impact", "Productivity gains alongside rising AI investment"),
    ]
    for idx, (domain, title) in enumerate(batch_titles):
        batch_assigned[domain].append({
            "event_id": f"fixture-grounded-{idx}",
            "event_date": "2026-09-14",
            "domain": domain,
            "owner_domain": domain,
            "event_type": "reported_development",
            "priority": 120.0 - idx,
            "rank_score": 120.0 - idx,
            "verified_fact": f"{title}.",
            "source_name": "Reuters",
            "source_label": "Reuters",
            "source_url": f"https://www.reuters.com/example/grounded-{idx}",
            "source_type": "news",
            "source_tier": "preferred",
            "evidence_role": "secondary",
            "verification_status": "reported",
            "status": "Reported",
            "grounding_version": grounding.GROUNDING_VERSION,
            "grounding_status": "grounded",
            "source_text_method": "trusted_publisher_headline",
            "source_text_chars": len(title),
            "source_evidence_hash": f"fixturehash{idx}",
            "source_title": title,
            "source_published_date": "2026-09-14",
            "source_modified_date": "",
            "evidence_resolution_mode": "trusted_headline_metadata",
            "qualification_tier": "B",
            "qualification_tier_label": "Strong",
            "discovery_provider": "google_news_rss",
        })
    renderable_batch = _reader_renderable_assigned(
        batch_assigned,
        current=__import__("pandas").Timestamp("2026-09-15"),
        retrieved_at="2026-09-15T05:00:00+00:00",
        audit_rows=[],
    )
    require(sum(len(items) for items in renderable_batch.values()) == 12, f"Grounded Reader pool was silently requalified down from 12: {renderable_batch}")
    batch_selected, _ = _select_significant_events(renderable_batch)
    require(sum(len(items) for items in batch_selected.values()) == 12, f"12 grounded approved events did not survive selection: {batch_selected}")


    # The broader Axios framing used a catchy headline and one body sentence
    # with a modal construction. The composer must fall back to the clean,
    # explicit Amodei event rather than manufacturing "should slowed down".
    brakes_title = "AI's most powerful CEOs hit the brakes"
    brakes_body = (
        "Anthropic CEO Dario Amodei called for slowing the pace of AI development. "
        "OpenAI CEO Sam Altman said he agreed the industry should slow down, joining other lab leaders in prioritizing safety over growth."
    )
    row, result = ground("market", brakes_title, brakes_body, published="2026-09-13")
    require(result.accepted and row is not None, f"Cross-lab braking story was lost: {result.reason}")
    require("should slowed" not in row["verified_fact"].casefold(), f"Modal conjugation corruption reached Reader copy: {row['verified_fact']}")
    require(row["verified_fact"].startswith("Anthropic CEO Dario Amodei called for"), f"Explicit actor was not retained from the source body: {row['verified_fact']}")

    # The composer module itself must remain deterministic/local. This is a
    # crude but explicit guard against accidentally turning Current Context into
    # another paid language-model call path.
    composer_source = (PROJECT_ROOT / "loaders" / "current_context_composer.py").read_text(encoding="utf-8").casefold()
    require("import openai" not in composer_source and "from openai" not in composer_source and "requests." not in composer_source, "Deterministic composer acquired an API/network dependency")

    # Final-copy semantic domain checks are intentionally stricter than broad
    # discovery vocabularies.
    require(strict_domain_fit("water", "A closed-loop cooling system would use reclaimed water."), "Water semantic fit rejected real Water copy")
    require(not strict_domain_fit("water", "The project requires a conditional use permit and public hearing."), "Generic permit language still qualifies as Water")

    print("PASS  Current Context deterministic NLG · end-to-end event frames · single-sentence event framing · domain semantics · zero model/API calls")


if __name__ == "__main__":
    main()
