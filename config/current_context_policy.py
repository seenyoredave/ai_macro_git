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
    "associated press",
    "ap news",
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
    "bloomberg": 94.0,
    "financial times": 94.0,
    "barron's": 92.0,
    "investor's business daily": 91.0,
    "investors business daily": 91.0,
    "morningstar": 90.0,
    "cnbc": 86.0,
}

# Company-issued releases distributed through these services may establish that
# the issuer formally announced, priced, filed, or completed an action.  They
# are not treated as independent journalism and are labeled accordingly.
COMPANY_RELEASE_SOURCES = {
    "business wire": 88.0,
}

# These sites are discovery infrastructure only.  Their prose never becomes
# evidence or Reader-facing citation merely because it surfaced a useful lead.
DISCOVERY_ONLY_SOURCES = {
    "techmeme",
    "abnormal returns",
    "data center richness",
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
    "bloomberg.com": 94.0,
    "ft.com": 94.0,
    "barrons.com": 92.0,
    "investors.com": 91.0,
    "morningstar.com": 90.0,
    "cnbc.com": 86.0,
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
    "apnews.com",
}

COMPANY_RELEASE_DOMAINS = {
    "businesswire.com",
}

DISCOVERY_ONLY_DOMAINS = {
    "techmeme.com",
    "abnormalreturns.com",
    "datacenterrichness.substack.com",
}

MANUAL_REVIEW_DOMAINS = {
    "nytimes.com",
}

DOMAIN_CONTEXT_POLICY = {
    # One canonical editorial grammar applies to every domain: eligible
    # evidence + seven-day recency + domain relevance + a domain-specific
    # material development.  Materiality and domain fit rank qualified items;
    # rank score never acts as an acceptance threshold.  Zero, one, or two
    # visible developments are all valid.
    "market": {"lookback_days": 7, "minimum_materiality": 5.0, "cadence": "weekday", "max_items": 2},
    "finance": {"lookback_days": 7, "minimum_materiality": 7.0, "cadence": "several_per_week", "max_items": 2},
    "compute": {"lookback_days": 7, "minimum_materiality": 7.0, "cadence": "several_per_week", "max_items": 2},
    "data_center": {"lookback_days": 7, "minimum_materiality": 8.0, "cadence": "event_driven", "max_items": 2},
    "connectivity": {"lookback_days": 7, "minimum_materiality": 7.0, "cadence": "event_driven", "max_items": 2},
    "power": {"lookback_days": 7, "minimum_materiality": 8.0, "cadence": "several_per_week", "max_items": 2},
    "grid_storage": {"lookback_days": 7, "minimum_materiality": 8.0, "cadence": "event_driven", "max_items": 2},
    "water": {"lookback_days": 7, "minimum_materiality": 8.0, "cadence": "event_driven", "max_items": 2},
    "adaptation": {"lookback_days": 7, "minimum_materiality": 7.0, "cadence": "event_driven", "max_items": 2},
    "workforce": {"lookback_days": 7, "minimum_materiality": 8.0, "cadence": "event_driven", "max_items": 2},
    "economic_impact": {"lookback_days": 7, "minimum_materiality": 8.0, "cadence": "release_driven", "max_items": 2},
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
    # Multiple narrow searches are intentional.  Search engines are discovery
    # sensors, not editors; splitting the economic questions improves the
    # candidate pool before the evidence gates see it.
    "market": (
        '(AI earnings OR AI guidance OR semiconductor earnings OR cloud earnings)',
        '(hyperscaler capex OR AI spending OR data center capex)',
        '(semiconductor revenue OR cloud revenue OR AI bookings)',
        '(AI acquisition OR technology IPO OR technology antitrust)',
        '(AI stocks rally OR AI stocks selloff OR AI valuation OR market breadth technology)',
    ),
    "finance": (
        '(data center debt OR AI infrastructure financing OR project finance data center)',
        '(AI data center leases OR uncommenced leases OR contractual commitments OR forward commitments)',
        '(private credit technology OR private credit data center)',
        '(AI venture funding OR AI private equity OR AI fundraise)',
        '(technology bond issuance OR AI credit ratings OR technology credit spreads)',
        '(private equity fund close OR technology exits OR private equity distributions)',
        '(Federal Reserve rates OR interest rates technology investment)',
    ),
    "compute": (
        '(AI chips OR GPU supply OR AI accelerator supply OR HBM AI)',
        '(semiconductor fab AI OR advanced packaging AI OR foundry AI)',
        '(AI chip export controls OR semiconductor export restrictions)',
        '(Nvidia AMD Broadcom TSMC AI capacity OR semiconductor capacity AI)',
    ),
    "data_center": (
        '(data center construction OR data center campus OR hyperscale campus)',
        '(data center permit OR data center moratorium OR data center zoning)',
        '(data center capacity OR colocation capacity OR hyperscaler campus)',
        '(data center project delay OR data center cancellation OR data center approval)',
    ),
    "connectivity": (
        '(data center fiber OR AI fiber backbone OR cloud fiber network)',
        '(submarine cable cloud OR submarine cable data center OR cable landing station)',
        '(internet exchange data center OR peering facility OR interconnection facility)',
        '(long-haul fiber OR middle mile fiber data center OR route diversity cloud)',
    ),
    "power": (
        '(data center electricity demand OR AI electricity demand OR utility load forecast data center)',
        '(data center power purchase agreement OR AI power contract OR hyperscaler power)',
        '(power generation data center OR gas turbine data center OR nuclear data center)',
        '(electricity price data center OR power price industrial load)',
    ),
    "grid_storage": (
        '(data center interconnection OR AI interconnection queue OR large load interconnection)',
        '(transmission data center OR grid upgrade data center OR substation data center)',
        '(battery storage data center OR grid storage AI load)',
        '(transformer shortage OR transmission congestion OR renewable curtailment)',
    ),
    "water": (
        '(data center water OR data center wastewater OR data center cooling water)',
        '(industrial water permit data center OR water reuse data center)',
        '(drought data center OR water shortage industrial development)',
        '(water utility data center OR wastewater capacity data center)',
    ),
    "adaptation": (
        '(enterprise AI adoption OR business AI use OR generative AI adoption)',
        '(AI deployment survey business OR enterprise AI survey)',
        '(AI agents enterprise deployment OR AI copilots business use)',
        '(company AI rollout OR AI implementation enterprise)',
    ),
    "workforce": (
        '(AI jobs OR AI employment OR AI layoffs OR AI hiring)',
        '(semiconductor jobs OR data center jobs OR AI infrastructure workforce)',
        '(AI wages OR AI skills OR AI occupations OR labor market AI)',
        '(automation jobs AI OR generative AI labor market)',
    ),
    "economic_impact": (
        '(AI productivity OR generative AI productivity OR labor productivity AI)',
        '(AI GDP OR AI economic output OR AI value added)',
        '(AI investment productivity OR software investment productivity)',
        '(AI unit labor cost OR AI compensation OR AI income)',
    ),
}

# Market must remain tied to the AI/technology investment universe rather than
# becoming a generic S&P 500 news strip.  Finance is allowed a broader macro/
# credit backdrop because rates, spreads, and private-credit conditions can
# matter even when a headline does not name AI explicitly.
DOMAIN_TOPIC_ANCHORS = {
    "market": (
        "ai", "artificial intelligence", "semiconductor", "chip", "gpu",
        "cloud", "hyperscaler", "data center", "datacenter", "technology",
        "tech", "software", "nvidia", "amd", "broadcom", "arista",
        "microsoft", "amazon", "aws", "alphabet", "google", "meta",
        "oracle", "palantir",
    ),
    # Finance may use a system-wide rates/credit event even when a headline
    # does not name AI, but ordinary unrelated financing deals do not qualify.
    "finance": (
        "ai", "artificial intelligence", "data center", "datacenter",
        "technology", "tech", "software", "semiconductor", "chip", "gpu",
        "cloud", "hyperscaler", "compute", "nvidia", "amd", "broadcom",
        "microsoft", "amazon", "aws", "alphabet", "google", "meta",
        "oracle", "palantir", "anthropic", "openai", "xai", "coreweave",
        "federal reserve", "fomc", "monetary policy", "interest rate",
        "treasury yield", "credit spread", "inflation", "cpi", "pce",
        "financial conditions",
    ),
    "compute": (
        "ai", "artificial intelligence", "gpu", "accelerator", "hbm",
        "semiconductor", "chip", "foundry", "fab", "advanced packaging",
        "data center", "datacenter", "nvidia", "amd", "broadcom", "tsmc",
        "intel", "micron", "sk hynix", "samsung", "asml",
    ),
    "data_center": (
        "data center", "datacenter", "hyperscale", "hyperscaler", "colocation",
        "campus", "ai infrastructure", "cloud infrastructure", "server campus",
    ),
    "connectivity": (
        "data center", "datacenter", "ai", "cloud", "fiber", "fibre",
        "submarine cable", "cable landing", "internet exchange", "peering",
        "interconnection facility", "middle mile", "backbone", "route diversity",
    ),
    "power": (
        "data center", "datacenter", "ai", "hyperscaler", "cloud",
        "electricity demand", "load forecast", "power purchase agreement",
        "utility", "generation", "power plant", "gas turbine", "nuclear",
        "electricity price", "power price",
    ),
    "grid_storage": (
        "data center", "datacenter", "ai", "large load", "interconnection",
        "transmission", "substation", "transformer", "grid", "curtailment",
        "battery storage", "congestion", "queue",
    ),
    "water": (
        "data center", "datacenter", "industrial", "water", "wastewater",
        "cooling", "reuse", "drought", "aquifer", "river", "reservoir",
        "water supply", "water utility",
    ),
    "adaptation": (
        "ai", "artificial intelligence", "generative ai", "enterprise ai",
        "business ai", "ai agent", "ai agents", "copilot", "copilots",
        "automation", "machine learning",
    ),
    "workforce": (
        "ai", "artificial intelligence", "generative ai", "automation",
        "technology", "tech", "semiconductor", "chip", "data center",
        "datacenter", "software", "ai infrastructure",
    ),
    "economic_impact": (
        "ai", "artificial intelligence", "generative ai", "automation",
        "technology investment", "software investment", "digital investment",
        "ai investment", "ai capital", "ai productivity",
    ),
}

DOMAIN_NEWS_TERMS = {
    "market": (
        "earnings", "guidance", "revenue", "margin", "bookings", "capex",
        "estimate", "beat", "miss", "outlook", "valuation", "multiple",
        "upgrade", "downgrade", "rally", "selloff", "index", "concentration",
        "breadth", "stock", "stocks", "shares", "market", "antitrust", "merger",
        "acquisition", "ipo", "stake",
    ),
    "finance": (
        "bond", "bonds", "debt", "loan", "loans", "financing", "private credit", "funding",
        "fundraise", "fund close", "venture", "private equity", "project finance",
        "spread", "spreads", "yield", "yields", "rating", "ratings", "downgrade", "upgrade", "refinancing",
        "maturity", "covenant", "liquidity", "distribution", "distributions", "dpi", "exit", "exits",
        "secondary", "secondaries", "acquisition financing", "credit", "rate", "rates",
        "interest rate", "federal reserve", "fomc", "monetary policy",
        "lease", "leases", "lease commitment", "lease commitments",
        "uncommenced lease", "uncommenced leases", "contractual commitment",
        "contractual commitments", "purchase commitment", "purchase commitments",
        "capital commitment", "capital commitments", "forward commitment",
        "forward commitments", "obligation", "obligations",
    ),
    "compute": (
        "chip", "chips", "semiconductor", "gpu", "accelerator", "hbm", "fab",
        "foundry", "advanced packaging", "export control", "export controls",
        "license", "production", "capacity", "supply", "shipment", "manufacturing",
    ),
    "data_center": (
        "data center", "datacenter", "campus", "permit", "permitting", "moratorium",
        "zoning", "construction", "capacity", "lease", "energization", "approval",
        "delay", "cancellation", "cancelled", "operating", "opens", "opened",
    ),
    "connectivity": (
        "submarine cable", "cable landing", "internet exchange", "peering",
        "interconnection facility", "middle mile", "fiber", "fibre", "backbone",
        "route diversity", "network capacity", "outage", "construction", "permit",
    ),
    "power": (
        "electricity demand", "load forecast", "power purchase agreement", "power contract",
        "generation", "power plant", "capacity", "electricity price", "power price",
        "natural gas", "gas turbine", "nuclear", "utility", "tariff", "contract",
    ),
    "grid_storage": (
        "grid", "transmission", "interconnection", "queue", "curtailment", "storage",
        "battery storage", "transformer", "substation", "congestion", "upgrade", "delay",
    ),
    "water": (
        "water", "wastewater", "drought", "aquifer", "cooling", "withdrawal", "reuse",
        "permit", "water supply", "shortage", "restriction", "river", "reservoir",
        "emergency", "allocation", "capacity",
    ),
    "adaptation": (
        "adoption", "business use", "survey", "deployment", "enterprise ai", "rollout",
        "implementation", "production use", "ai agents", "copilot", "automation",
    ),
    "workforce": (
        "employment", "jobs", "hiring", "layoff", "layoffs", "wage", "wages",
        "skills", "occupation", "labor", "headcount", "automation", "training",
    ),
    "economic_impact": (
        "productivity", "output", "gdp", "value added", "unit labor cost", "compensation",
        "income", "economic growth", "investment", "revision", "growth",
    ),
}

# Domain-specific development vocabulary for the two high-cadence proof domains.
# Weights express materiality for ranking only; a development still must clear
# the transparent hard gates in evaluate_item().
DOMAIN_MATERIAL_EVENT_WEIGHTS = {
    "market": {
        "earnings": 10.0, "guidance": 10.0, "raises guidance": 12.0,
        "cuts guidance": 12.0, "revenue": 7.0, "margin": 6.0, "bookings": 8.0,
        "capex": 8.0, "beat": 7.0, "miss": 7.0, "outlook": 8.0,
        "acquisition": 12.0, "merger": 12.0, "ipo": 10.0, "antitrust": 10.0,
        "upgrade": 5.0, "downgrade": 6.0, "rally": 5.0, "selloff": 6.0,
        "valuation": 5.0, "multiple": 4.0, "index": 5.0, "breadth": 5.0,
        "concentration": 5.0, "stake sale": 8.0, "in talks": 6.0,
    },
    "finance": {
        "bond": 8.0, "bonds": 8.0, "debt": 7.0, "loan": 7.0, "loans": 7.0, "financing": 8.0,
        "private credit": 9.0, "funding": 7.0, "fundraise": 7.0,
        "fund close": 8.0, "venture": 6.0, "private equity": 6.0,
        "project finance": 10.0, "spread": 7.0, "spreads": 7.0, "yield": 7.0, "yields": 7.0, "rating": 7.0, "ratings": 7.0,
        "downgrade": 9.0, "upgrade": 7.0, "refinancing": 9.0,
        "maturity": 7.0, "covenant": 8.0, "liquidity": 8.0,
        "distribution": 7.0, "distributions": 7.0, "dpi": 7.0, "exit": 7.0, "exits": 7.0, "secondary": 7.0, "secondaries": 7.0,
        "acquisition financing": 10.0, "default": 14.0, "bankruptcy": 14.0,
        "offering": 8.0, "credit ratings": 8.0, "rate": 8.0, "rates": 8.0,
        "interest rate": 10.0, "fomc": 10.0, "monetary policy": 10.0,
        "lease": 7.0, "leases": 7.0, "lease commitment": 9.0,
        "lease commitments": 9.0, "uncommenced lease": 10.0,
        "uncommenced leases": 10.0, "contractual commitment": 9.0,
        "contractual commitments": 9.0, "purchase commitment": 8.0,
        "purchase commitments": 8.0, "capital commitment": 8.0,
        "capital commitments": 8.0, "forward commitment": 10.0,
        "forward commitments": 10.0, "obligation": 7.0, "obligations": 7.0,
    },
    "compute": {
        "export controls": 12.0, "export control": 12.0, "license": 9.0,
        "advanced packaging": 9.0, "foundry": 8.0, "fab": 8.0, "hbm": 8.0,
        "gpu": 7.0, "accelerator": 7.0, "capacity": 7.0, "production": 7.0,
        "manufacturing": 7.0, "shipment": 7.0, "supply": 7.0, "delay": 9.0,
        "investment": 7.0, "contract": 7.0,
    },
    "data_center": {
        "moratorium": 14.0, "permit": 10.0, "permitting": 10.0, "zoning": 10.0,
        "approved": 9.0, "approval": 9.0, "construction": 9.0, "energization": 11.0,
        "delay": 10.0, "delayed": 10.0, "cancellation": 12.0, "cancelled": 12.0,
        "campus": 7.0, "capacity": 7.0, "lease": 7.0, "operating": 8.0,
        "opened": 8.0, "investment": 7.0,
    },
    "connectivity": {
        "submarine cable": 11.0, "cable landing": 11.0, "internet exchange": 10.0,
        "interconnection facility": 10.0, "peering": 8.0, "fiber": 7.0, "fibre": 7.0,
        "backbone": 8.0, "route diversity": 8.0, "network capacity": 8.0,
        "outage": 12.0, "construction": 8.0, "permit": 8.0, "contract": 7.0,
    },
    "power": {
        "power purchase agreement": 11.0, "power contract": 10.0,
        "electricity demand": 9.0, "load forecast": 10.0, "generation": 7.0,
        "power plant": 9.0, "capacity": 7.0, "gas turbine": 8.0, "nuclear": 8.0,
        "electricity price": 8.0, "power price": 8.0, "tariff": 9.0,
        "utility": 5.0, "contract": 7.0,
    },
    "grid_storage": {
        "interconnection": 10.0, "transmission": 9.0, "substation": 9.0,
        "transformer": 9.0, "curtailment": 12.0, "battery storage": 9.0,
        "queue": 8.0, "congestion": 9.0, "upgrade": 8.0, "delay": 10.0,
        "approved": 8.0, "construction": 8.0,
    },
    "water": {
        "shortage": 12.0, "emergency": 12.0, "restriction": 10.0, "drought": 10.0,
        "permit": 9.0, "water supply": 9.0, "wastewater": 8.0, "reuse": 8.0,
        "allocation": 9.0, "aquifer": 8.0, "river": 7.0, "reservoir": 7.0,
        "cooling": 7.0, "capacity": 7.0,
    },
    "adaptation": {
        "adoption": 8.0, "business use": 9.0, "deployment": 9.0, "rollout": 8.0,
        "implementation": 8.0, "production use": 10.0, "enterprise ai": 8.0,
        "survey": 7.0, "ai agents": 7.0, "copilot": 6.0, "automation": 6.0,
    },
    "workforce": {
        "layoff": 11.0, "layoffs": 11.0, "employment": 9.0, "jobs": 8.0,
        "hiring": 8.0, "headcount": 8.0, "wage": 8.0, "wages": 8.0,
        "skills": 7.0, "occupation": 7.0, "labor": 6.0, "automation": 8.0,
        "training": 6.0,
    },
    "economic_impact": {
        "productivity": 11.0, "gdp": 10.0, "value added": 10.0,
        "unit labor cost": 10.0, "output": 9.0, "compensation": 8.0,
        "income": 8.0, "revision": 8.0, "economic growth": 8.0,
        "investment": 6.0, "growth": 5.0,
    },
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

    if name in DISCOVERY_ONLY_SOURCES or any(
        any(_domain_matches(host, domain) for domain in DISCOVERY_ONLY_DOMAINS)
        for host in hosts if host
    ):
        return SourceAssessment(
            "discovery_only",
            0.0,
            False,
            "discovery",
            "discovery-only intermediary; follow outbound evidence instead",
        )

    if name in COMPANY_RELEASE_SOURCES or any(
        any(_domain_matches(host, domain) for domain in COMPANY_RELEASE_DOMAINS)
        for host in hosts if host
    ):
        score = COMPANY_RELEASE_SOURCES.get(name, 88.0)
        return SourceAssessment(
            "company_release",
            score,
            True,
            "company_statement",
            "company-issued release distribution",
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


def term_present(text: str, term: str) -> bool:
    haystack = " ".join(str(text or "").split()).casefold()
    needle = " ".join(str(term or "").split()).casefold()
    if not needle:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack) is not None


def materiality_score(text: str, domain: str) -> float:
    """Score materiality using the canonical vocabulary for one known domain."""
    weights = DOMAIN_MATERIAL_EVENT_WEIGHTS.get(str(domain or "").strip().lower())
    if not weights:
        return 0.0
    score = sum(weight for term, weight in weights.items() if term_present(text, term))
    return min(36.0, float(score))


def domain_news_queries(domain: str) -> tuple[str, ...]:
    value = DOMAIN_NEWS_QUERIES.get(domain, domain.replace("_", " "))
    if isinstance(value, (tuple, list)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    text = str(value or "").strip()
    return (text,) if text else (domain.replace("_", " "),)


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
