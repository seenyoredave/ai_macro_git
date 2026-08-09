"""Source and materiality policy for automated Current Context selection.

The policy is intentionally conservative.  Live retrieval is a discovery layer,
not a license to repeat every headline.  Only named, reputable publishers or
primary institutional sources are eligible for automatic display.  Commentary-
first outlets and sources requiring manual corroboration are excluded from the
automated path.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlparse


@dataclass(frozen=True)
class SourceAssessment:
    tier: str
    score: float
    auto_eligible: bool
    evidence_role: str
    reason: str



# Social media is excluded from the research pipeline entirely.  These sources
# are not eligible for discovery, corroboration, evidence, or citation even
# when the account belongs to an otherwise authoritative institution.
SOCIAL_MEDIA_SOURCE_NAMES = {
    "reddit",
    "x",
    "twitter",
    "facebook",
    "instagram",
    "threads",
    "tiktok",
    "linkedin",
    "youtube",
    "bluesky",
    "mastodon",
    "truth social",
    "telegram",
    "discord",
    "snapchat",
}

SOCIAL_MEDIA_DOMAINS = {
    "reddit.com",
    "redd.it",
    "x.com",
    "twitter.com",
    "facebook.com",
    "fb.com",
    "instagram.com",
    "threads.net",
    "tiktok.com",
    "linkedin.com",
    "youtube.com",
    "youtu.be",
    "bsky.app",
    "mastodon.social",
    "truthsocial.com",
    "t.me",
    "telegram.me",
    "discord.com",
    "discord.gg",
    "snapchat.com",
}

# Hard exclusions requested for the automated product surface.
BLOCKED_SOURCE_NAMES = {
    "fox news",
    "msnbc",
    "huffpost",
    "the huffington post",
    "huffington post",
}

# These sources may be used only in a curated record with explicit
# corroboration; they are not eligible for unattended live selection.
MANUAL_REVIEW_SOURCE_NAMES = {
    "the new york times",
    "new york times",
    "nyt",
}

PREFERRED_NEWS_SOURCES = {
    "the wall street journal": 98.0,
    "wall street journal": 98.0,
    "reuters": 96.0,
    "associated press": 94.0,
    "ap news": 94.0,
    "bloomberg": 92.0,
    "financial times": 92.0,
    "barron's": 88.0,
}

SPECIALIST_NEWS_SOURCES = {
    "utility dive": 87.0,
    "data center dynamics": 87.0,
    "rto insider": 87.0,
    "s&p global": 86.0,
    "s&p global commodity insights": 86.0,
    "construction dive": 84.0,
    "semiconductor engineering": 84.0,
    "ee times": 82.0,
    "the register": 78.0,
}

REPUTABLE_LOCAL_SOURCES = {
    "the texas tribune": 84.0,
    "texas tribune": 84.0,
    "houston chronicle": 80.0,
    "dallas morning news": 80.0,
    "austin american-statesman": 78.0,
    "san antonio express-news": 78.0,
}

PRIMARY_DOMAINS = {
    "sec.gov",
    "federalreserve.gov",
    "newyorkfed.org",
    "chicagofed.org",
    "eia.gov",
    "energy.gov",
    "ferc.gov",
    "census.gov",
    "bea.gov",
    "bls.gov",
    "usgs.gov",
    "puc.texas.gov",
    "ercot.com",
    "gov.texas.gov",
    "capitol.texas.gov",
}

APPROVED_NEWS_DOMAINS = {
    "wsj.com": 98.0,
    "reuters.com": 96.0,
    "apnews.com": 94.0,
    "bloomberg.com": 92.0,
    "ft.com": 92.0,
    "barrons.com": 88.0,
    "utilitydive.com": 87.0,
    "datacenterdynamics.com": 87.0,
    "rtoinsider.com": 87.0,
    "spglobal.com": 86.0,
    "constructiondive.com": 84.0,
    "semiengineering.com": 84.0,
    "eetimes.com": 82.0,
    "texastribune.org": 84.0,
    "houstonchronicle.com": 80.0,
    "dallasnews.com": 80.0,
    "statesman.com": 78.0,
    "expressnews.com": 78.0,
}

BLOCKED_DOMAINS = {
    "foxnews.com",
    "msnbc.com",
    "huffpost.com",
    "huffingtonpost.com",
}

MANUAL_REVIEW_DOMAINS = {
    "nytimes.com",
}

DOMAIN_CONTEXT_POLICY = {
    "market": {"lookback_days": 3, "minimum_score": 104.0, "cadence": "weekday"},
    "finance": {"lookback_days": 7, "minimum_score": 106.0, "cadence": "several_per_week"},
    "compute": {"lookback_days": 10, "minimum_score": 106.0, "cadence": "several_per_week"},
    "data_center": {"lookback_days": 14, "minimum_score": 106.0, "cadence": "event_driven"},
    "connectivity": {"lookback_days": 14, "minimum_score": 106.0, "cadence": "event_driven"},
    "power": {"lookback_days": 7, "minimum_score": 106.0, "cadence": "several_per_week"},
    "grid_storage": {"lookback_days": 10, "minimum_score": 106.0, "cadence": "event_driven"},
    "water": {"lookback_days": 14, "minimum_score": 106.0, "cadence": "event_driven"},
    "adaptation": {"lookback_days": 14, "minimum_score": 106.0, "cadence": "event_driven"},
    "workforce": {"lookback_days": 14, "minimum_score": 106.0, "cadence": "event_driven"},
    "economic_impact": {"lookback_days": 14, "minimum_score": 106.0, "cadence": "release_driven"},
}

# Domain-specific ownership terms prevent one event from being rendered across
# several tab reads.  Secondary tags may still be retained in the event ledger
# for analysis, but exactly one primary owner controls visible placement.
DOMAIN_OWNER_TERMS = {
    "market": ("earnings", "revenue", "guidance", "shares", "stock", "market cap", "valuation", "index"),
    "finance": ("federal reserve", "interest rate", "credit", "debt", "financing", "funding", "private equity", "venture"),
    "compute": ("semiconductor", "chip", "gpu", "foundry", "fab", "photonics", "advanced packaging"),
    "data_center": ("data center", "datacenter", "campus", "permit", "moratorium", "audit"),
    "connectivity": ("submarine cable", "cable landing", "internet exchange", "peering", "interconnection facility", "middle mile", "fiber backbone", "route diversity"),
    "power": ("electricity demand", "generation", "power plant", "capacity addition", "retail electricity", "natural gas"),
    "grid_storage": ("transmission", "interconnection", "substation", "transformer", "grid", "curtailment", "battery storage"),
    "water": ("water", "wastewater", "river", "reservoir", "drought", "aquifer", "withdrawal", "cooling"),
    "adaptation": ("adoption", "business use", "survey", "deployment", "enterprise ai"),
    "workforce": ("employment", "jobs", "layoffs", "hiring", "wages", "skills", "occupation", "labor"),
    "economic_impact": ("productivity", "output", "value added", "unit labor cost", "gdp", "compensation"),
}

DOMAIN_CONTEXT_FALLBACK = {
    domain: "No material development was identified for this period."
    for domain in DOMAIN_CONTEXT_POLICY
}

DOMAIN_NEWS_QUERIES = {
    "market": '(AI earnings OR AI stocks OR semiconductor earnings OR cloud earnings OR AI software guidance)',
    "finance": '(AI financing OR private equity AI OR venture capital AI OR private credit OR interest rates technology investment)',
    "compute": '(AI chips OR semiconductor manufacturing OR chip export controls OR semiconductor fab OR GPU supply)',
    "data_center": '(data center moratorium OR data center permits OR data center construction OR data center campus)',
    "connectivity": '(submarine cable OR cable landing station OR internet exchange OR peering facility OR middle mile fiber OR long-haul fiber backbone)',
    "power": '(data center electricity demand OR power generation capacity OR electricity prices OR natural gas generation)',
    "grid_storage": '(transmission project OR interconnection queue OR power grid OR battery storage OR transformer shortage OR curtailment)',
    "water": '(data center water OR wastewater infrastructure OR industrial water permit OR drought water supply)',
    "adaptation": '(business AI adoption OR enterprise AI use OR AI deployment survey)',
    "workforce": '(AI employment OR technology hiring OR semiconductor jobs OR data center jobs OR AI workforce wages)',
    "economic_impact": '(AI productivity OR labor productivity release OR GDP industry technology investment OR economic output AI)',
}

DOMAIN_NEWS_TERMS = {
    "market": ("earnings", "revenue", "market", "stock", "antitrust", "merger", "acquisition", "ipo"),
    "finance": ("financing", "funding", "private equity", "venture", "credit", "rates", "debt", "distribution"),
    "compute": ("chip", "semiconductor", "gpu", "fab", "export", "foundry", "manufacturing"),
    "data_center": ("data center", "datacenter", "campus", "permit", "moratorium", "audit"),
    "connectivity": ("submarine cable", "cable landing", "internet exchange", "peering", "interconnection facility", "middle mile", "fiber backbone", "route diversity"),
    "power": ("electricity", "generation", "power plant", "capacity", "retail price", "natural gas"),
    "grid_storage": ("grid", "transmission", "interconnection", "curtailment", "storage", "transformer", "substation"),
    "water": ("water", "wastewater", "drought", "aquifer", "cooling", "withdrawal", "reuse", "permit"),
    "adaptation": ("adoption", "business use", "survey", "deployment", "enterprise ai"),
    "workforce": ("employment", "jobs", "hiring", "layoff", "wage", "occupation", "labor"),
    "economic_impact": ("productivity", "output", "gdp", "value added", "unit labor cost", "compensation"),
}

# A live headline must describe an action, release, result, or status change—not
# merely commentary about a topic.
MATERIAL_EVENT_TERMS = (
    "announces",
    "announced",
    "approves",
    "approved",
    "orders",
    "ordered",
    "directs",
    "directed",
    "halts",
    "halted",
    "pauses",
    "paused",
    "moratorium",
    "audit",
    "files",
    "filed",
    "rule",
    "regulation",
    "permit",
    "permitted",
    "rejects",
    "rejected",
    "withdraws",
    "withdrew",
    "cancels",
    "cancelled",
    "delays",
    "delayed",
    "construction",
    "investment",
    "funding",
    "financing",
    "earnings",
    "results",
    "revenue",
    "capacity",
    "contract",
    "acquisition",
    "merger",
    "tariff",
    "export controls",
    "bankruptcy",
    "default",
    "survey",
    "release",
)

DOMAIN_LIVE_RELEVANCE = {
    "market": "The development may change market leadership, valuation, or return expectations.",
    "finance": "The development may change capital availability, financing costs, or realization conditions.",
    "compute": "The development may change semiconductor supply, manufacturing capacity, or deployment timing.",
    "data_center": "The development may change project timing, permitting, or the viable capacity pipeline.",
    "power": "The development may change electricity demand, generation supply, fuel costs, or retail prices.",
    "grid_storage": "The development may change interconnection, transmission, storage, congestion, or deliverability assumptions.",
    "water": "The development may change water or wastewater availability, permitting, cooling choices, or community exposure.",
    "adaptation": "The development may change measured business adoption or deployment breadth.",
    "workforce": "The development may change employment, hiring, wages, skills demand, or worker exposure.",
    "economic_impact": "The development may change measured productivity, output, labor costs, or realized value.",
}


def _host(value: str) -> str:
    try:
        host = urlparse(str(value or "").strip()).hostname or ""
    except ValueError:
        return ""
    host = host.casefold().removeprefix("www.")
    return host


def _domain_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def assess_source(source_name: str, source_url: str = "", article_url: str = "") -> SourceAssessment:
    """Classify whether a source is eligible for unattended display."""
    name = " ".join(str(source_name or "").split()).casefold()
    hosts = [_host(source_url), _host(article_url)]

    if name in SOCIAL_MEDIA_SOURCE_NAMES or any(
        any(_domain_matches(host, domain) for domain in SOCIAL_MEDIA_DOMAINS)
        for host in hosts if host
    ):
        return SourceAssessment(
            "blocked_social",
            0.0,
            False,
            "none",
            "social media is excluded from discovery, corroboration, evidence, and citation",
        )

    if name in BLOCKED_SOURCE_NAMES or any(
        any(_domain_matches(host, domain) for domain in BLOCKED_DOMAINS)
        for host in hosts if host
    ):
        return SourceAssessment("blocked", 0.0, False, "none", "explicitly excluded")

    if name in MANUAL_REVIEW_SOURCE_NAMES or any(
        any(_domain_matches(host, domain) for domain in MANUAL_REVIEW_DOMAINS)
        for host in hosts if host
    ):
        return SourceAssessment(
            "manual_review",
            35.0,
            False,
            "secondary",
            "requires corroboration before use",
        )

    for host in hosts:
        if not host:
            continue
        if host.endswith(".gov") or any(_domain_matches(host, domain) for domain in PRIMARY_DOMAINS):
            return SourceAssessment(
                "primary",
                100.0,
                True,
                "official_statement",
                "primary institutional source",
            )

    if name in PREFERRED_NEWS_SOURCES:
        return SourceAssessment("preferred", PREFERRED_NEWS_SOURCES[name], True, "secondary", "preferred general news source")
    if name in SPECIALIST_NEWS_SOURCES:
        return SourceAssessment("specialist", SPECIALIST_NEWS_SOURCES[name], True, "secondary", "approved specialist source")
    if name in REPUTABLE_LOCAL_SOURCES:
        return SourceAssessment("local", REPUTABLE_LOCAL_SOURCES[name], True, "secondary", "approved local source")

    for host in hosts:
        if not host:
            continue
        for domain, score in APPROVED_NEWS_DOMAINS.items():
            if _domain_matches(host, domain):
                tier = "preferred" if score >= 90 else "specialist" if score >= 82 else "local"
                return SourceAssessment(tier, score, True, "secondary", "approved publisher domain")

    return SourceAssessment("unapproved", 0.0, False, "none", "not on automated source allowlist")


def materiality_score(text: str) -> float:
    haystack = " ".join(str(text or "").split()).casefold()
    matches = sum(1 for term in MATERIAL_EVENT_TERMS if term in haystack)
    return min(24.0, matches * 6.0)


RECENT_DEVELOPMENTS_ACRONYMS = {
    "PUCT": "Public Utility Commission of Texas",
    "ERCOT": "Electric Reliability Council of Texas",
    "FERC": "Federal Energy Regulatory Commission",
    "NERC": "North American Electric Reliability Corporation",
    "MISO": "Midcontinent Independent System Operator",
    "CAISO": "California Independent System Operator",
    "SPP": "Southwest Power Pool",
}

_BARE_OFFICE_FIRST_REFERENCE = re.compile(
    r"(?:^|[.!?]\s+|:\s+)(?:the\s+)?"
    r"(?:Governor|Mayor|Senator|Representative|Secretary|Commissioner|President)\b",
    flags=re.IGNORECASE,
)


def recent_development_copy_issues(text: object) -> list[str]:
    """Return first-reference context problems in Recent Developments copy.

    Recent Developments must stand on its own for a national reader.  Public
    officials need jurisdiction and full identity on first reference, and
    specialized regional institutions must be expanded before shorthand is used.
    """

    value = " ".join(str(text or "").split()).strip()
    if not value:
        return []

    issues: list[str] = []
    if _BARE_OFFICE_FIRST_REFERENCE.search(value):
        issues.append(
            "public official lacks jurisdiction/full first-reference context"
        )

    lowered = value.casefold()
    for acronym, expansion in RECENT_DEVELOPMENTS_ACRONYMS.items():
        match = re.search(rf"\b{re.escape(acronym)}\b", value)
        if not match:
            continue
        if expansion.casefold() not in lowered[: match.end()]:
            issues.append(f"{acronym} is not expanded on first reference")

    return issues
