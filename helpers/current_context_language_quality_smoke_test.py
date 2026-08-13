"""Regression tests for Current Context source/article and Reader-copy quality."""

from __future__ import annotations

from pathlib import Path
import sys
import types
import warnings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

if "streamlit" not in sys.modules:
    fake_streamlit = types.ModuleType("streamlit")
    fake_streamlit.cache_data = lambda *args, **kwargs: (args[0] if args and callable(args[0]) else (lambda fn: fn))
    sys.modules["streamlit"] = fake_streamlit
if "requests" not in sys.modules:
    try:
        import requests  # noqa: F401
    except ModuleNotFoundError:
        sys.modules["requests"] = types.ModuleType("requests")

from config.current_context_policy import recent_development_copy_issues
import loaders.current_context_grounding as grounding
from loaders.current_context_grounding import SourceDocument, source_content_quality_issues
from loaders.current_context_registry import _dedupe_events


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    # HTML/entity furniture must never leak into Reader copy.
    require(grounding._spaces("&quot;Deployment Inc&quot;") == '"Deployment Inc"', "HTML entities were not normalized")

    # Plain URL-shaped JSON-LD values and publisher timezone abbreviations are
    # parsed deliberately; neither may leak third-party parser warnings.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        grounding._clean_paragraph("https://example.com/articles/a-very-long-url-shaped-jsonld-value-that-is-not-html")
        terminal_date = grounding._date_only("Thu Aug 6, 11:56AM CDT")
    require(terminal_date.endswith("-08-06"), f"CDT publication date parsed incorrectly: {terminal_date}")
    require(not caught, "Current Context emitted parser warnings: " + "; ".join(str(item.message) for item in caught))

    # The old v7.3 failure mode mechanically chopped at word 36. A complete
    # source sentence inside the new 70-word ceiling must survive intact.
    long_sentence = (
        "Palm Beach County's zoning commission approved a proposed definition of a large-scale data center, "
        "making a pending moratorium apply to new facilities expected to use at least 50 megawatts of power "
        "while county officials consider permanent zoning rules for future projects."
    )
    compressed = grounding._compress_fact(long_sentence)
    require("50 megawatts of power" in compressed, f"Complete source sentence was damaged: {compressed}")
    require(len(compressed.split()) <= 70, "Reader fact exceeded the 70-word hard ceiling")

    chopped = "The moratorium would apply to data centers expected to use 50 megawatts of."
    require(recent_development_copy_issues(chopped), "Dangling grammatical cutoff was not rejected")

    # Synthetic thematic series pages are poor Current Context material even
    # when the publisher is legitimate and the page is full of plausible facts.
    synthetic = SourceDocument(
        "https://example.com/series", "https://example.com/series",
        "Future of data centre funding: private credit and institutional capital",
        "", (
            "Key takeaways. AI-focused data centres serving neocloud counterparties exhibit risk profiles that diverge from traditional infrastructure. "
            "Private credit has become a structural feature of this segment across several financing layers. "
            "In our previous article, we examined how banks continue to underpin data centre financing. "
            "This article is part of a thought leadership series on financing the data centre sector. "
            "Looking for deeper insights, explore our other articles in the series."
        ), "fixture",
    )
    require(source_content_quality_issues(synthetic), "Synthetic thematic series page was not rejected")

    # A professional/legal publisher reporting a discrete action remains usable;
    # the detector is format-aware, not a publisher blacklist.
    discrete = SourceDocument(
        "https://example.com/alert", "https://example.com/alert",
        "Virginia regulators order new transmission cost allocation for data centers",
        "", (
            "The Virginia State Corporation Commission ordered Dominion Energy to create a separate rate class for large data-center customers. "
            "The order directs certain transmission costs to qualifying customers and cites the proposed Valley Link project as one example."
        ), "fixture",
    )
    require(not source_content_quality_issues(discrete), "Discrete event alert was incorrectly treated as synthetic analysis")

    # Cross-publisher rewrites of one event should not consume both domain slots.
    duplicate_events = [
        {
            "event_id": "cars24-a", "event_date": "2026-08-11", "domain": "adoption", "priority": 90,
            "source_title": "Cars24 launches Deployment Inc with $5 million investment",
            "verified_fact": "Cars24 launched Deployment Inc, an enterprise AI company, with an initial $5 million investment.",
            "source_url": "https://publisher-a.example/cars24",
        },
        {
            "event_id": "cars24-b", "event_date": "2026-08-11", "domain": "adoption", "priority": 89,
            "source_title": "Cars24 launches enterprise AI company Deployment Inc, invests $5 Mn",
            "verified_fact": "Deployment Inc raised $5 million in seed funding from Cars24 after the used-car marketplace launched the enterprise AI venture.",
            "source_url": "https://publisher-b.example/deployment",
        },
    ]
    require(len(_dedupe_events(duplicate_events)) == 1, "Same-event cross-publisher coverage was not deduplicated")

    # Exact v7.3 failure classes must fail the retained Reader gate, while a
    # clean empirical outcome remains eligible.
    bad_examples = {
        "finance": "Private credit has become a significant structural feature of this segment.",
        "data_center": "During a public hearing yesterday, they approved a proposed definition making the moratorium apply to facilities expected to use 50 megawatts of.",
        "connectivity": "Over the past 18 months, the company has launched new construction and network-overbuild projects spanning more than 15,000 route miles across North America.",
        "grid_storage": "The Virginia State Corporation Commission cited the proposed Valley Link transmission project as an example of infrastructure that could be assigned to the rate class.",
        "workforce": '"Hiring has also increased over last year by 25%, so while AI is shifting the labor market, it is not dismantling it," said Andy Challenger.',
    }
    for domain, text in bad_examples.items():
        ok, reason = grounding.retained_reader_quality_gate(domain, text, "", event_date="2026-08-11", lookback_days=10)
        require(not ok, f"Known v7.3 Reader failure remained eligible for {domain}: {text} / {reason}")
    ok, reason = grounding.retained_reader_quality_gate(
        "economic_impact",
        "Singapore's economy grew 5.9% year-on-year in the second quarter of 2026, easing from 6.3% growth in the previous quarter.",
        "", event_date="2026-08-11", lookback_days=10,
    )
    require(ok, f"Clean empirical development was incorrectly rejected: {reason}")

    # Presentation ranking should prefer an event frame over a quote/detail.
    anchors = [
        (20.0, '"Hiring has also increased over last year by 25%," said Andy Challenger, workplace expert at Challenger, Gray & Christmas.'),
        (18.0, 'Challenger, Gray & Christmas reported that U.S. employers announced fewer layoffs in July while hiring increased from a year earlier.'),
    ]
    fact, _ = grounding._assemble_reader_development(
        anchors,
        headline="Challenger report: layoffs fall as hiring picks up",
        source_text=" ".join(item[1] for item in anchors),
        domain="workforce",
        qualification_tier="D",
    )
    require(fact and not fact.startswith(('"', '“')), f"Quote-led copy outranked the event frame: {fact}")
    require(len(fact.split()) <= 70, "Assembled development exceeded hard ceiling")


    # v7.4 showed that event evidence can be correct but displayed in the wrong
    # order. Context-dependent detail must yield to the nearby explicit event.
    finance_anchors = [
        (24.0, "The financing push comes after a July swoon in global markets in which investors began asking whether Big Tech's AI investments would pay off."),
        (18.0, "Nvidia signed memorandums of understanding with Apollo Global Management, Blackstone, BlackRock, Brookfield Asset Management, Goldman Sachs and KKR to establish financing platforms for Nvidia customers."),
    ]
    finance_fact, _ = grounding._assemble_reader_development(
        finance_anchors, headline="Nvidia lines up Wall Street asset managers for AI financing push",
        source_text=" ".join(item[1] for item in finance_anchors), domain="finance", qualification_tier="D",
    )
    require(finance_fact.startswith("Nvidia signed"), f"Finance context outranked the actual transaction: {finance_fact}")

    power_anchors = [
        (26.0, "If built, it could be the largest natural gas plant in the US at 7.65GW."),
        (20.0, "Amazon has acquired an 8,000-acre plot of land in Texas, where it plans to develop a data center powered by what could become the largest natural gas power plant in the US."),
    ]
    power_fact, _ = grounding._assemble_reader_development(
        power_anchors, headline="Amazon acquires Texas site for natural-gas-powered data center",
        source_text=" ".join(item[1] for item in power_anchors), domain="power", qualification_tier="D",
    )
    require(power_fact.startswith("Amazon has acquired"), f"Conditional detail outranked Amazon's event frame: {power_fact}")

    grid_anchors = [
        (26.0, "The directive, issued in an Aug. 3 letter to state regulators, arrives as the ERCOT large-load interconnection queue has surged to 474 GW, of which approximately 90% is data centers."),
        (20.0, "Texas Governor Greg Abbott directed the Public Utility Commission of Texas and the Electric Reliability Council of Texas to conduct a comprehensive audit of every data center advancing through the state's interconnection queue."),
    ]
    grid_fact, _ = grounding._assemble_reader_development(
        grid_anchors, headline="Abbott orders full audit of Texas data center interconnection queue",
        source_text=" ".join(item[1] for item in grid_anchors), domain="grid_storage", qualification_tier="D",
    )
    require(grid_fact.startswith("Texas Governor Greg Abbott directed"), f"Grid detail outranked governing action: {grid_fact}")

    workforce_anchors = [
        (24.0, "The July figures were also the lowest announced layoff total for a month in the last two years, while announced layoffs are down 41 percent in 2026 compared with 2025."),
        (19.0, "Challenger, Gray & Christmas reported that U.S. employers announced fewer layoffs in July while hiring increased from a year earlier as companies continued to adjust staffing around AI investment."),
    ]
    workforce_fact, _ = grounding._assemble_reader_development(
        workforce_anchors, headline="Challenger report says layoffs fell while hiring picked up",
        source_text=" ".join(item[1] for item in workforce_anchors), domain="workforce", qualification_tier="D",
    )
    require(workforce_fact.startswith("Challenger, Gray & Christmas reported"), f"Workforce detail outranked release frame: {workforce_fact}")

    # A title/section heading accidentally concatenated onto article prose can
    # be removed only when a complete actor/action sentence remains.
    heading_slop = (
        "Why Customers Now Buy Connectivity As A Platform Logix Fiber Networks, Texas' leading business fiber provider, "
        "announced that it has deployed multiple 400G wavelength services to one of the nation's largest wireless carriers."
    )
    cleaned_heading = grounding._compress_fact(heading_slop, headline="Logix Fiber Networks deploys 400G wavelength services")
    require(cleaned_heading.startswith("Logix Fiber Networks"), f"Embedded heading was not stripped: {cleaned_heading}")

    # Event/webinar listings are not developments, even when related-news text
    # elsewhere on the page contains an otherwise qualifying fact.
    webinar = SourceDocument(
        "https://example.org/event/data-center-series-water-use-and-cooling",
        "https://example.org/event/data-center-series-water-use-and-cooling",
        "Data Center Series: Water Use and Cooling", "",
        "This event will take place on Zoom Webinar. As the third session in the series, this call will focus on understanding water use and cooling of data centers.",
        "fixture",
    )
    require(grounding.is_event_listing_page(webinar), "Future webinar/event page was not rejected")

    # Human-visible relative dates must close the RSS recrawl loophole.
    stale_html = "<html><body><div><h1>Logix Fiber Expands Backbone</h1><span>9 months ago</span></div></body></html>"
    visible_date, _ = grounding._page_dates(grounding.BeautifulSoup(stale_html, "lxml"))
    require(bool(visible_date), "Visible relative publication age was not recovered")

    # v7.5 sentence segmentation broke ``Aug. 3 letter`` into an orphaned
    # sentence beginning with the numeral 3. Month abbreviations and U.S.
    # initialisms must survive segmentation intact.
    texas_text = (
        "The directive, issued in an Aug. 3 letter to Public Utility Commission of Texas Chairman Thomas Gleeson, "
        "arrives as the ERCOT large-load interconnection queue has surged to 474 GW. "
        "U.S. data-center demand has increased sharply."
    )
    texas_sentences = grounding._split_sentences(texas_text)
    require(texas_sentences and texas_sentences[0].startswith("The directive, issued in an Aug. 3 letter"), f"Month abbreviation split incorrectly: {texas_sentences}")
    require(not any(sentence.startswith("3 letter") for sentence in texas_sentences), f"Orphaned date fragment survived: {texas_sentences}")

    # Wire-service datelines are stripped without damaging the event.
    prwire = "Aug. 3, 2026 /PRNewswire/ -- HUMAIN, a PIF company, announced a strategic investment in enterprise AI company MOZN."
    cleaned_prwire = grounding._compress_fact(prwire)
    require(cleaned_prwire.startswith("HUMAIN"), f"Wire dateline was not removed: {cleaned_prwire}")

    # A corroborated publisher headline is the preferred event nucleus; body
    # detail may follow it, but may not replace it.
    ppl_title = "PPL-Blackstone joint venture secures 5 GW of gas turbines for data centers"
    ppl_body = (
        "The PPL-Blackstone joint venture has secured sites in Pennsylvania that could support up to 14 GW of new generation for data-center demand. "
        "The venture entered reservation agreements for more than 5 GW of combined-cycle gas turbines, and PJM accepted about 5 GW of its generating projects into the interconnection queue."
    )
    ppl_anchors = [(26.0, item) for item in grounding._split_sentences(ppl_body)]
    ppl_fact, _ = grounding._assemble_reader_development(
        ppl_anchors, headline=ppl_title, source_title=ppl_title, source_text=ppl_body,
        domain="power", qualification_tier="C",
    )
    require(ppl_fact.startswith("The PPL-Blackstone joint venture has secured"), f"Natural body event frame was not preferred: {ppl_fact}")

    malbec_title = "Malbec submarine cable system reaches shore in southern Brazil"
    malbec_body = (
        "The Malbec submarine cable system reached the coast of southern Brazil this week as crews completed the landing phase. "
        "Built with Alcatel Submarine Networks technology, the system will provide up to 20 Tbps per fiber pair and support circuits of up to 800 Gbps between Porto Alegre, Buenos Aires, and São Paulo."
    )
    malbec_anchors = [(24.0, item) for item in grounding._split_sentences(malbec_body)]
    malbec_fact, _ = grounding._assemble_reader_development(
        malbec_anchors, headline=malbec_title, source_title=malbec_title, source_text=malbec_body,
        domain="connectivity", qualification_tier="D",
    )
    require(malbec_fact.startswith("The Malbec submarine cable system reached"), f"Natural Connectivity body frame was not preferred: {malbec_fact}")

    humain_title = "HUMAIN invests in enterprise AI company MOZN and forms strategic partnership"
    humain_body = (
        "HUMAIN announced a strategic investment in and partnership with MOZN, a Saudi enterprise AI company focused on high-assurance domains. "
        "The companies said they will co-build enterprise AI solutions for customers in Saudi Arabia and international markets."
    )
    humain_anchors = [(24.0, item) for item in grounding._split_sentences(humain_body)]
    humain_fact, _ = grounding._assemble_reader_development(
        humain_anchors, headline=humain_title, source_title=humain_title, source_text=humain_body,
        domain="adoption", qualification_tier="D",
    )
    require(humain_fact.startswith("HUMAIN announced"), f"Natural Adoption body frame was not preferred: {humain_fact}")

    # A resolved page whose title is about F5/Nvidia cannot donate a Logix
    # development from related-content/page furniture.
    mismatch = grounding._source_identity_coherence_issue(
        "Logix Fiber Networks deploys 400G wavelength services for wireless carrier",
        "F5 integrates AI guardrails with Nvidia NeMo Guardrails",
        "Logix Fiber Networks announced that it deployed multiple 400G wavelength services to a large wireless carrier.",
        domain="connectivity",
    )
    require(bool(mismatch), "Cross-article source/title mismatch was not rejected")

    # Subtitle/headline fragments may be removed when a complete event nucleus
    # follows immediately.
    virginia_slop = (
        "Follows growing scrutiny from state regulators Regulators in Virginia have directed Dominion Energy to develop a new transmission cost allocation policy for data centers."
    )
    cleaned_virginia = grounding._compress_fact(virginia_slop)
    require(cleaned_virginia.startswith("Regulators in Virginia have directed"), f"Subtitle prefix was not stripped: {cleaned_virginia}")

    # Repeated source-side acronym expansions collapse rather than nesting.
    nested = "Electric Reliability Council of Texas (Electric Reliability Council of Texas (ERCOT)) reported that the queue reached 474 GW."
    collapsed = grounding._collapse_duplicate_acronym_expansions(nested)
    require("Electric Reliability Council of Texas (ERCOT)" in collapsed and "(Electric Reliability" not in collapsed, f"Nested acronym expansion survived: {collapsed}")


    # v7.7.3 live-run fixtures: presentation must clean page furniture and put
    # the reported event ahead of supporting detail.
    wsj_widget = (
        "https://www.wsj.com/business/deals/example Nvidia NVDA -2.86 % decrease; down pointing triangle "
        "reached deals with some of Wall Street's largest firms aimed at raising massive amounts of capital to help "
        "the chip maker's customers finance the cost of computing power."
    )
    cleaned_wsj = grounding._compress_fact(wsj_widget, headline="Nvidia reaches AI financing deals with Wall Street firms")
    require(cleaned_wsj.startswith("Nvidia reached deals"), f"Ticker/URL furniture survived Finance cleanup: {cleaned_wsj}")
    require("pointing triangle" not in cleaned_wsj and "http" not in cleaned_wsj, f"Finance widget debris survived: {cleaned_wsj}")

    require(
        grounding._clean_source_title("Palm Beach County Zoning Commission Approves AI Data Center Moratorium | BIG 105.9")
        == "Palm Beach County Zoning Commission Approves AI Data Center Moratorium",
        "Publisher suffix was not stripped from Data Centers title",
    )

    opinion_water = SourceDocument(
        "https://example.com/opinions/efficient-data-center-water-cooling",
        "https://example.com/opinions/efficient-data-center-water-cooling",
        "Efficient data center water cooling for Australia's market", "",
        "As AI workloads push rack densities higher, improving water efficiency requires evaluating cooling architecture and future expansion plans. "
        "Decisions made early in the design process can affect operational efficiency and sustainability reporting.",
        "fixture",
    )
    require(source_content_quality_issues(opinion_water), "Opinion/advisory Water page remained Current Context eligible")

    humain_dateline = (
        "RIYADH, Saudi Arabia, Aug. 3, 2026 /PRNewswire/ -- HUMAIN, a PIF company delivering full-stack artificial intelligence capabilities globally, "
        "today announced a strategic investment in and partnership with MOZN, a Saudi enterprise AI company."
    )
    cleaned_humain = grounding._compress_fact(humain_dateline, headline="HUMAIN invests in MOZN")
    require(cleaned_humain.startswith("HUMAIN"), f"City/wire dateline survived: {cleaned_humain}")
    require("PRNewswire" not in cleaned_humain and not cleaned_humain.startswith("RIYADH"), f"Wire furniture survived: {cleaned_humain}")

    malformed_coreweave = "CoreWeave shares jumped 14% after the AI infrastructure provider reported results than topped Wall Street expectations."
    require(recent_development_copy_issues(malformed_coreweave), "Malformed source comparison was not rejected")

    # Body event sentences outrank statistics/context and raw publisher titles.
    palantir_title = "Palantir earnings beat expectations as AI demand drives outlook"
    palantir_body = (
        "Revenue in the three months ended June 30 increased 93% year over year, totaling $1.94 billion. "
        "Palantir blew past Wall Street's financial targets in its second quarter and forecast strong growth in the coming months, sending its stock surging 13% in after-hours trading on Monday."
    )
    palantir_anchors = [(28.0, item) for item in grounding._split_sentences(palantir_body)]
    palantir_fact, _ = grounding._assemble_reader_development(
        palantir_anchors, headline=palantir_title, source_title=palantir_title,
        source_text=palantir_body, domain="market", qualification_tier="A",
    )
    require(palantir_fact.startswith("Palantir blew past"), f"Market statistic still outranked the event: {palantir_fact}")

    # A support/detail-only Power sentence cannot become the event frame.
    amazon_title = "Amazon plans Texas data center powered by 7.65 GW gas plant"
    amazon_body = (
        "Most of this capacity is planned to be directed to Amazon's data center in West Texas. "
        "Amazon acquired an 8,000-acre site in Texas for a data center that could be powered by the planned 7.65 GW GW Ranch natural gas power plant."
    )
    amazon_anchors = [(25.0, item) for item in grounding._split_sentences(amazon_body)]
    amazon_fact, _ = grounding._assemble_reader_development(
        amazon_anchors, headline=amazon_title, source_title=amazon_title,
        source_text=amazon_body, domain="power", qualification_tier="C",
    )
    require(amazon_fact.startswith("Amazon acquired"), f"Power context still outranked the event: {amazon_fact}")

    # Inline navigation may be discarded, but it must not manufacture context.
    also_read = (
        "Also Read | Why Silicon Valley says an AI bubble could be good for innovation "
        "Product and Design teams also reported heightened concerns, with 65 per cent of respondents saying they expect layoffs or significant team cuts."
    )
    cleaned_also_read = grounding._compress_fact(also_read, headline="AI workers expect layoffs in Blind survey")
    require(cleaned_also_read == "", f"Contaminated inline-navigation sentence was not rejected: {cleaned_also_read}")

    print("PASS  Current Context language quality · event nucleus · title/body coherence · sentence segmentation · <=70 words · stale/event-page filter · event deduplication")


if __name__ == "__main__":
    main()
