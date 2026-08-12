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
    return grounding.ground_candidate(
        candidate(title), domain=domain, fetcher=lambda *args, **kwargs: doc
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
    require(fact.startswith("Palantir blew past"), f"Metric still outranked Market event: {fact}")
    require(fact.find("Revenue in the three months") > fact.find("Palantir blew past"), f"Supporting revenue was not sequenced after event: {fact}")

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
    require(fact.startswith("Nvidia,"), f"Compute metric still outranked company action: {fact}")
    require("81% less memory" in fact, f"Useful quantified Compute support was lost: {fact}")

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
    require(fact.startswith("Palm Beach County Zoning Commission approved an AI data center moratorium."), f"Title was not deterministically realized: {fact}")
    require("| BIG 105.9" not in fact and "Approves AI Data Center Moratorium" not in fact, f"Publisher heading leaked into Reader: {fact}")

    # CONNECTIVITY: duplicate title/body statements collapse to one event.
    verizon_title = "Verizon blames Sunday's network outage in Southern California on multiple fiber cuts"
    verizon_body = (
        "As vandals caused mobile and Internet disruption for 12,000 customers Verizon has blamed a network outage over the weekend on multiple fiber cuts. "
        "Service was restored after crews repaired the damaged fiber routes."
    )
    row, result = ground("connectivity", verizon_title, verizon_body)
    require(result.accepted and row is not None, f"Verizon fixture failed grounding: {result.reason}")
    fact = row["verified_fact"]
    require(fact == "Verizon blamed Sunday's network outage in Southern California on multiple fiber cuts.", f"Redundant Connectivity restatement survived: {fact}")

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
    require(fact.startswith("HUMAIN announced"), f"Adoption event frame was not recovered: {fact}")
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

    # The composer module itself must remain deterministic/local. This is a
    # crude but explicit guard against accidentally turning Current Context into
    # another paid language-model call path.
    composer_source = (PROJECT_ROOT / "loaders" / "current_context_composer.py").read_text(encoding="utf-8").casefold()
    require("openai" not in composer_source and "requests." not in composer_source, "Deterministic composer acquired an API/network dependency")

    # Final-copy semantic domain checks are intentionally stricter than broad
    # discovery vocabularies.
    require(strict_domain_fit("water", "A closed-loop cooling system would use reclaimed water."), "Water semantic fit rejected real Water copy")
    require(not strict_domain_fit("water", "The project requires a conditional use permit and public hearing."), "Generic permit language still qualifies as Water")

    print("PASS  Current Context deterministic NLG · end-to-end event frames · support ordering · domain semantics · zero model/API calls")


if __name__ == "__main__":
    main()
