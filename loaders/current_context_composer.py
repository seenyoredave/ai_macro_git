"""Deterministic event extraction and surface realization for Current Context.

The source article is evidence, not Reader prose.  This module converts cleaned
source/title sentences into a small event representation and then composes one
compact factual development from that representation.  It performs no network
calls and no model/API calls.

The design follows the classical NLG split used by rule-based data-to-text
systems: semantic extraction -> content planning -> surface realization.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Iterable, Sequence


MAX_WORDS = 70


def _spaces(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _sentence(value: object) -> str:
    text = _spaces(value).strip(" ;,:—–-")
    if not text:
        return ""
    return text if text[-1] in ".!?" else text + "."


_STOPWORDS = {
    "about", "after", "against", "among", "been", "being", "could", "from", "have",
    "into", "more", "over", "said", "says", "than", "that", "their", "there", "these",
    "they", "this", "through", "under", "were", "which", "with", "would", "year", "years",
    "company", "companies", "data", "center", "centers", "centre", "centres", "artificial",
    "intelligence", "project", "projects", "reported", "announced", "plans", "planned",
}


def _tokens(text: object) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", _spaces(text).casefold())
        if len(token) >= 3 and token not in _STOPWORDS
    }


def _similarity(left: str, right: str) -> float:
    a = " ".join(sorted(_tokens(left)))
    b = " ".join(sorted(_tokens(right)))
    if not a or not b:
        return 0.0
    return float(SequenceMatcher(None, a, b).ratio())


# Trigger order matters. Multiword/auxiliary forms are evaluated before their
# shorter components.  The normalized past form is used only for headline
# realization; natural body prose remains source-authored when it is already
# grammatical.
_ACTIONS: tuple[tuple[str, str, str], ...] = (
    (r"\b(?:has|have|had)\s+directed\b", "directed", "regulatory_action"),
    (r"\b(?:has|have|had)\s+ordered\b", "ordered", "regulatory_action"),
    (r"\b(?:has|have|had)\s+approved\b", "approved", "regulatory_action"),
    (r"\b(?:has|have|had)\s+filed\b", "filed", "infrastructure_project"),
    (r"\b(?:has|have|had)\s+acquired\b", "acquired", "transaction"),
    (r"\b(?:has|have|had)\s+secured\b", "secured", "transaction"),
    (r"\b(?:has|have|had)\s+raised\b", "raised", "financing"),
    (r"\b(?:has|have|had)\s+invested\b", "invested", "investment"),
    (r"\b(?:has|have|had)\s+announced\b", "announced", "announcement"),
    (r"\b(?:has|have|had)\s+reported\b", "reported", "report"),
    (r"\b(?:has|have|had)\s+launched\b", "launched", "deployment"),
    (r"\b(?:has|have|had)\s+deployed\b", "deployed", "deployment"),
    (r"\b(?:has|have|had)\s+completed\b", "completed", "infrastructure_project"),
    (r"\b(?:has|have|had)\s+commissioned\b", "commissioned", "infrastructure_project"),
    (r"\b(?:has|have|had)\s+reached\b", "reached", "infrastructure_project"),
    (r"\b(?:has|have|had)\s+entered\b", "entered", "transaction"),
    (r"\b(?:has|have|had)\s+signed\b", "signed", "transaction"),
    (r"\b(?:has|have|had)\s+partnered\b", "partnered", "partnership"),
    (r"\b(?:has|have|had)\s+unveiled\b", "unveiled", "technology_release"),
    (r"\b(?:has|have|had)\s+cut\b", "cut", "workforce_action"),
    (r"\b(?:has|have|had)\s+upgraded\b", "upgraded", "forecast_revision"),
    (r"\b(?:has|have|had)\s+downgraded\b", "downgraded", "forecast_revision"),
    (r"\b(?:is|are|was|were)\s+(?:reportedly\s+)?exploring\s+plans?\s+to\s+reduce\b", "plans to reduce", "technology_change"),
    (r"\bplans?\s+to\s+reduce\b", "plans to reduce", "technology_change"),
    (r"\bplans?\s+to\s+(?:develop|build|construct)\b", "plans to develop", "infrastructure_project"),
    (r"\bplans?\s+to\s+(?:sell|divest)\b", "plans to sell", "transaction"),
    (r"\bplans?\s+to\s+(?:raise|issue)\b", "plans to raise", "financing"),
    (r"\bplans?\s+to\s+(?:deploy|expand)\b", "plans to deploy", "deployment"),
    (r"\b(?:is|are)\s+preparing\s+to\s+(?:offload|sell)\b", "is preparing to sell", "financing"),
    (r"\bpreparing\s+to\s+(?:offload|sell)\b", "preparing to sell", "financing"),
    (r"\bseeks?\s+to\s+(?:raise|refinance|sell|offload)\b", "seeks financing", "financing"),
    (r"\b(?:is|are)\s+set\s+to\s+(?:develop|build|construct)\b", "plans to develop", "infrastructure_project"),
    (r"\b(?:is|are)\s+set\s+to\s+(?:sell|divest)\b", "plans to sell", "transaction"),
    (r"\b(?:is|are)\s+set\s+to\s+(?:deploy|launch|expand)\b", "plans to deploy", "deployment"),
    (r"\bdirected\b", "directed", "regulatory_action"),
    (r"\bordered\b", "ordered", "regulatory_action"),
    (r"\bapproved\b", "approved", "regulatory_action"),
    (r"\badopted\b", "adopted", "regulatory_action"),
    (r"\bvoted\b", "voted", "regulatory_action"),
    (r"\bfiled\b", "filed", "infrastructure_project"),
    (r"\bacquired\b", "acquired", "transaction"),
    (r"\bbought\b", "bought", "transaction"),
    (r"\bpurchased\b", "purchased", "transaction"),
    (r"\bsold\b", "sold", "transaction"),
    (r"\binvested\b", "invested", "investment"),
    (r"\braised\b", "raised", "financing"),
    (r"\bsecured\b", "secured", "transaction"),
    (r"\bfinanced\b", "financed", "financing"),
    (r"\bfunded\b", "funded", "financing"),
    (r"\brefinanced\b", "refinanced", "financing"),
    (r"\bannounced\b", "announced", "announcement"),
    (r"\breported\b", "reported", "report"),
    (r"\bpublished\b", "published", "report"),
    (r"\breleased\b", "released", "report"),
    (r"\blaunched\b", "launched", "deployment"),
    (r"\bdeployed\b", "deployed", "deployment"),
    (r"\bcompleted\b", "completed", "infrastructure_project"),
    (r"\bcommissioned\b", "commissioned", "infrastructure_project"),
    (r"\breached\b", "reached", "infrastructure_project"),
    (r"\bopened\b", "opened", "infrastructure_project"),
    (r"\bbegan\b", "began", "infrastructure_project"),
    (r"\bstarted\b", "started", "infrastructure_project"),
    (r"\bexpanded\b", "expanded", "infrastructure_project"),
    (r"\bentered\b", "entered", "transaction"),
    (r"\bsigned\b", "signed", "transaction"),
    (r"\bpartnered\b", "partnered", "partnership"),
    (r"\bunveiled\b", "unveiled", "technology_release"),
    (r"\breduced\b", "reduced", "technology_change"),
    (r"\bcut\b", "cut", "workforce_action"),
    (r"\bupgraded\b", "upgraded", "forecast_revision"),
    (r"\bdowngraded\b", "downgraded", "forecast_revision"),
    (r"\bcommitted\b", "committed", "financing"),
    (r"\bsurged\b", "surged", "market_move"),
    (r"\bjumped\b", "jumped", "market_move"),
    (r"\brallied\b", "rallied", "market_move"),
    (r"\brose\b", "rose", "market_move"),
    (r"\bfell\b", "fell", "market_move"),
    (r"\bdropped\b", "dropped", "market_move"),
    (r"\bdeclined\b", "declined", "market_move"),
    (r"\bplunged\b", "plunged", "market_move"),
    (r"\bclimbed\b", "climbed", "market_move"),
    (r"\bblew\s+past\b", "beat", "earnings_result"),
    (r"\bbeat\b", "beat", "earnings_result"),
    (r"\btopped\b", "topped", "earnings_result"),
    (r"\bforecast\b", "forecast", "forecast_revision"),
    (r"\bblames?\b", "blamed", "network_incident"),
    (r"\bapproves?\b", "approved", "regulatory_action"),
    (r"\borders?\b", "ordered", "regulatory_action"),
    (r"\bdirects?\b", "directed", "regulatory_action"),
    (r"\badopts?\b", "adopted", "regulatory_action"),
    (r"\bvotes?\b", "voted", "regulatory_action"),
    (r"\bfiles?\b", "filed", "infrastructure_project"),
    (r"\bacquires?\b", "acquired", "transaction"),
    (r"\bbuys?\b", "bought", "transaction"),
    (r"\bpurchases?\b", "purchased", "transaction"),
    (r"\bsells?\b", "sold", "transaction"),
    (r"\binvests?\b", "invested", "investment"),
    (r"\braises?\b", "raised", "financing"),
    (r"\bsecures?\b", "secured", "transaction"),
    (r"\bfinances?\b", "financed", "financing"),
    (r"\bfunds?\b", "funded", "financing"),
    (r"\brefinances?\b", "refinanced", "financing"),
    (r"\bannounces?\b", "announced", "announcement"),
    (r"\breports?\b", "reported", "report"),
    (r"\bpublishes?\b", "published", "report"),
    (r"\breleases?\b", "released", "report"),
    (r"\blaunches?\b", "launched", "deployment"),
    (r"\bdeploys?\b", "deployed", "deployment"),
    (r"\bcompletes?\b", "completed", "infrastructure_project"),
    (r"\breaches?\b", "reached", "infrastructure_project"),
    (r"\bopens?\b", "opened", "infrastructure_project"),
    (r"\bbegins?\b", "began", "infrastructure_project"),
    (r"\bstarts?\b", "started", "infrastructure_project"),
    (r"\bexpands?\b", "expanded", "infrastructure_project"),
    (r"\benters?\b", "entered", "transaction"),
    (r"\bsigns?\b", "signed", "transaction"),
    (r"\bpartners?\b", "partnered", "partnership"),
    (r"\bunveils?\b", "unveiled", "technology_release"),
    (r"\breduces?\b", "reduced", "technology_change"),
    (r"\bcuts?\b", "cut", "workforce_action"),
    (r"\bupgrades?\b", "upgraded", "forecast_revision"),
    (r"\bdowngrades?\b", "downgraded", "forecast_revision"),
    (r"\bcommits?\b", "committed", "financing"),
    (r"\bjumps?\b", "jumped", "market_move"),
    (r"\bsurges?\b", "surged", "market_move"),
    (r"\brallies?\b", "rallied", "market_move"),
    (r"\brises?\b|\brose\b", "rose", "market_move"),
    (r"\bfalls?\b|\bfell\b", "fell", "market_move"),
    (r"\bdrops?\b|\bdropped\b", "dropped", "market_move"),
    (r"\bdeclines?\b|\bdeclined\b", "declined", "market_move"),
)


_GENERIC_ACTOR_OPENINGS = re.compile(
    r"^(?:"
    r"revenue|sales|profit|profits|earnings|configurations?|capacity|most of (?:this|the)|"
    r"subsequent rate updates?|the (?:january|february|march|april|may|june|july|august|september|october|november|december) (?:figures|results)|"
    r"the figures|these figures|the results|these results|once approved|if approved|if built|"
    r"unlike the rest|among major|based on the description|but based on|as ai workloads|"
    r"the financing push|the directive|the letter|the order|the proposal|the measure|the report|the study|the survey"
    r")\b",
    flags=re.I,
)

_CONTEXT_OPENING = re.compile(
    r"^(?:once|if|although|while|whereas|because|since|as|unlike|among|based on|but based on|most of|subsequent|however|overall|meanwhile|separately)\b",
    flags=re.I,
)


@dataclass(frozen=True)
class EventFrame:
    event_type: str
    actor: str
    action: str
    object_text: str
    sentence: str
    source_kind: str
    index: int
    score: float
    lead_eligible: bool

    @property
    def identity_tokens(self) -> set[str]:
        return _tokens(f"{self.actor} {self.object_text}")


@dataclass(frozen=True)
class CompositionResult:
    text: str
    evidence_text: str
    event_type: str
    actor: str
    used_title: bool
    support_count: int
    reason: str


_EVENT_PRIORITY = {
    "regulatory_action": 18.0,
    "financing": 18.0,
    "investment": 17.0,
    "transaction": 17.0,
    "earnings_result": 17.0,
    "economic_release": 17.0,
    "workforce_report": 16.0,
    "infrastructure_project": 16.0,
    "technology_release": 16.0,
    "technology_change": 15.0,
    "deployment": 15.0,
    "partnership": 15.0,
    "network_incident": 15.0,
    "forecast_revision": 14.0,
    "report": 12.0,
    "announcement": 11.0,
    "market_move": 10.0,
    "workforce_action": 14.0,
    "corporate_action": 9.0,
}


_DOMAIN_STRICT_PATTERNS: dict[str, tuple[str, ...]] = {
    "market": (
        r"\bshares?\b", r"\bstock\b", r"\bearnings\b", r"\brevenue\b", r"\bguidance\b",
        r"\bwall street\b", r"\bafter-hours\b", r"\btrading\b", r"\bvaluation\b", r"\bindex\b",
    ),
    "finance": (
        r"\bfinanc(?:e|ed|ing)\b", r"\bcapital\b", r"\bdebt\b", r"\bloan(?:s)?\b", r"\bcredit\b",
        r"\bbond(?:s)?\b", r"\binvest(?:ed|ment|ments)\b", r"\bfund(?:ed|ing|s)?\b", r"\blender(?:s)?\b",
        r"\bprivate credit\b", r"\bBDC\b", r"\brealized loss\b", r"\bportfolio\b", r"\basset managers?\b",
        r"\bpolicy rate\b", r"\bfederal funds rate\b", r"\bbasis points?\b", r"\brate (?:hike|cut)\b",
        r"\blease(?:s|d| payments?| commitments?)?\b", r"\bcommitments?\b", r"\bobligations?\b",
    ),
    "compute": (
        r"\bGPU(?:s)?\b", r"\bchip(?:s)?\b", r"\bsemiconductor(?:s)?\b", r"\bHBM\b", r"\bmemory\b",
        r"\baccelerator(?:s)?\b", r"\bwafer(?:s)?\b", r"\bfoundr(?:y|ies)\b", r"\bcompute\b",
    ),
    "data_center": (
        r"\bdata cent(?:er|re)s?\b", r"\bcampus\b", r"\bhyperscal(?:e|er)\b", r"\bserver farm\b",
        r"\bmegawatt(?:s)?\b", r"\b\d+(?:\.\d+)?\s*(?:MW|GW)\b", r"\bmoratorium\b",
    ),
    "connectivity": (
        r"\bfib(?:er|re)\b", r"\bsubmarine cable\b", r"\bsubsea cable\b", r"\bwavelength\b",
        r"\bbackhaul\b", r"\bcable landing\b", r"\broute miles?\b", r"\bTbps\b", r"\bGbps\b",
        r"\bnetwork outage\b", r"\bfiber cuts?\b",
    ),
    "power": (
        r"\bpower plant\b", r"\bgeneration\b", r"\belectricity\b", r"\bnatural gas\b", r"\bturbine(?:s)?\b",
        r"\bpower purchase agreement\b", r"\bPPA\b", r"\bnuclear\b", r"\b\d+(?:\.\d+)?\s*(?:MW|GW)\b",
    ),
    "grid_storage": (
        r"\bgrid\b", r"\btransmission\b", r"\binterconnection\b", r"\bERCOT\b", r"\bPJM\b",
        r"\butility\b", r"\brate class\b", r"\bbatter(?:y|ies)\b", r"\bstorage\b", r"\bload queue\b",
    ),
    "water": (
        r"\bwater\b", r"\bcooling\b", r"\baquifer\b", r"\bwastewater\b", r"\bgallons?\b",
        r"\bclosed[- ]loop\b", r"\bpotable\b", r"\bdrinking water\b", r"\bwater source\b",
    ),
    "adoption": (
        r"\benterprise AI\b", r"\bartificial intelligence\b", r"\bAI agents?\b", r"\bAI systems?\b",
        r"\bAI company\b", r"\bAI solutions?\b", r"\bmodels?\b", r"\bforward-deployed\b",
    ),
    "workforce": (
        r"\blayoffs?\b", r"\bhiring\b", r"\bjobs?\b", r"\bworkers?\b", r"\bemployees?\b",
        r"\bheadcount\b", r"\bworkforce\b", r"\bstaffing\b", r"\bjob cuts?\b",
    ),
    "economic_impact": (
        r"\bGDP\b", r"\bgross domestic product\b", r"\bproductivity\b", r"\binflation\b", r"\bwages?\b",
        r"\beconomic growth\b", r"\beconomy\b", r"\bCPI\b", r"\boutput\b",
    ),
}


def strict_domain_fit(domain: str, text: str) -> bool:
    """Require the *Reader copy itself* to contain semantic domain evidence."""
    value = _spaces(text)
    patterns = _DOMAIN_STRICT_PATTERNS.get(str(domain or "").strip().casefold(), ())
    if not patterns:
        return True
    return any(re.search(pattern, value, flags=re.I) for pattern in patterns)


def _action_match(text: str) -> tuple[re.Match[str] | None, str, str]:
    """Return the earliest event trigger in surface order.

    Lexicon order must never decide semantics.  A sentence such as
    ``Airbnb shares surged ... and raised its outlook`` is primarily a market
    move at the first trigger; choosing ``raised`` merely because that pattern
    appears earlier in the rule table recreates the old sentence-scoring bug.
    """
    best: tuple[int, int, re.Match[str], str, str] | None = None
    for pattern, action, event_type in _ACTIONS:
        match = re.search(pattern, text, flags=re.I)
        if not match:
            continue
        candidate = (match.start(), -len(match.group(0)), match, action, event_type)
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    if best is None:
        return None, "", ""
    return best[2], best[3], best[4]


def _clean_actor(prefix: str) -> str:
    actor = _spaces(prefix).strip(" ,:;—–-")
    # Remove a short scene-setting clause if a named actor follows it.
    actor = re.sub(r"^(?:on|after|during|before)\s+[^,]{1,70},\s+", "", actor, flags=re.I)
    actor = re.sub(r"^(?:today|yesterday|this week|on monday|on tuesday|on wednesday|on thursday|on friday),?\s+", "", actor, flags=re.I)
    # Remove one bounded appositive from the actor span.
    app = re.match(r"^([^,]{2,80}),\s+(?:an?|the)\s+[^,]{3,100},\s*$", actor, flags=re.I)
    if app:
        actor = _spaces(app.group(1))
    return actor


def _actor_is_explicit(actor: str) -> bool:
    value = _spaces(actor)
    if not value or len(value.split()) > 16:
        return False
    if _GENERIC_ACTOR_OPENINGS.search(value):
        return False
    if _CONTEXT_OPENING.search(value):
        return False
    if re.match(r"^(?:the|these|those)\s+(?:figures|results|capacity|rate|rates|increase|decline|growth)\b", value, flags=re.I):
        return False
    if not re.search(r"[A-Za-z]", value):
        return False
    # Named entities, institutions and explicit governmental actors generally
    # contain a proper-cased token or an acronym.  Reject lower-case metric
    # phrases masquerading as subjects.
    words = re.findall(r"[A-Za-z][A-Za-z0-9.&'’\-]*", value)
    return any(word[:1].isupper() or (len(word) >= 2 and word.isupper()) for word in words)


def _refine_event_type(base: str, sentence: str, actor: str) -> str:
    lower = sentence.casefold()
    if any(term in lower for term in ("earnings", "quarter", "wall street", "revenue", "guidance")) and base in {"report", "earnings_result", "forecast_revision", "market_move"}:
        return "earnings_result"
    if any(term in lower for term in ("survey", "respondents", "layoff", "hiring", "workforce", "headcount")) and base in {"report", "announcement"}:
        return "workforce_report"
    if any(term in lower for term in ("gdp", "gross domestic product", "economy grew", "economic growth", "inflation", "productivity")) and base in {"report", "forecast_revision", "announcement"}:
        return "economic_release"
    if any(term in lower for term in ("commission", "regulator", "regulators", "governor", "public utility", "department of justice", "doj")) and base in {"regulatory_action", "announcement"}:
        return "regulatory_action"
    if any(term in lower for term in ("hbm", "gpu", "semiconductor", "chip", "memory", "accelerator")) and base in {"announcement", "technology_change", "deployment"}:
        return "technology_release"
    if any(term in lower for term in ("outage", "fiber cut", "fibre cut")):
        return "network_incident"
    if any(term in lower for term in ("deal", "deals", "agreement", "agreements", "memorandum", "memorandums")) and base in {"infrastructure_project", "transaction", "announcement"}:
        return "transaction"
    if any(term in lower for term in ("data center", "data centre", "campus", "power plant", "submarine cable", "cable landing", "interconnection")) and base in {"deployment", "infrastructure_project", "transaction"}:
        return "infrastructure_project"
    return base or "corporate_action"


def _frame_from_sentence(sentence: str, *, source_kind: str, index: int) -> EventFrame | None:
    value = _sentence(sentence)
    if not value or len(value.split()) < 6 or len(value.split()) > MAX_WORDS:
        return None
    if _GENERIC_ACTOR_OPENINGS.search(value) or _CONTEXT_OPENING.search(value):
        lead_hint = False
    else:
        lead_hint = True
    match, action, base_type = _action_match(value)
    if not match:
        return None
    actor = _clean_actor(value[: match.start()])
    object_text = _spaces(value[match.end() :]).strip(" ,:;—–-.")
    explicit_actor = _actor_is_explicit(actor)
    event_type = _refine_event_type(base_type, value, actor)
    lead_eligible = bool(lead_hint and explicit_actor and object_text)

    # Quantified metric sentences are valuable support, but are not event
    # nuclei when their grammatical subject is the metric itself.
    if re.match(r"^(?:Revenue|Sales|Profit|Profits|Earnings|Configurations?|Capacity|Rates?)\b", actor, flags=re.I):
        lead_eligible = False

    score = _EVENT_PRIORITY.get(event_type, 8.0)
    score += 5.0 if explicit_actor else -8.0
    score += 2.0 if re.search(r"\d", value) else 0.0
    score += max(0.0, 4.0 - index * 0.35)
    if source_kind == "title":
        score -= 2.5
    if value.startswith(('"', '“')):
        score -= 8.0
    if len(value.split()) >= 18:
        score += 1.5
    return EventFrame(event_type, actor, action, object_text, value, source_kind, index, score, lead_eligible)


def _title_case_object_to_sentence(text: str) -> str:
    """Lower generic title-case words while preserving acronyms/proper tokens."""
    words = text.split()
    if not words:
        return ""
    keep_upper = {"AI", "GPU", "HBM", "ERCOT", "PJM", "SCC", "PPA", "US", "U.S.", "MOZN", "HUMAIN"}
    lowerable = {
        "Data", "Center", "Centre", "Centers", "Centres", "Moratorium", "Network", "Outage", "Fiber", "Fibre",
        "Cuts", "Audit", "Interconnection", "Queue", "Investment", "Partnership", "Solutions", "Enterprise",
        "Systems", "Campus", "Power", "Plant", "Submarine", "Cable", "System", "Shore", "Transmission", "Costs",
        "Customers", "Financing", "Deal", "Deals", "Revenue", "Growth", "Forecast", "Results", "Services",
    }
    output: list[str] = []
    for word in words:
        stripped = word.strip(".,:;!?()[]{}")
        if stripped in keep_upper or (len(stripped) > 1 and stripped.isupper()):
            output.append(word)
        elif stripped in lowerable:
            output.append(word.replace(stripped, stripped.lower(), 1))
        else:
            output.append(word)
    return " ".join(output)


def _realize_title_frame(frame: EventFrame) -> str:
    actor = _spaces(frame.actor)
    obj = _title_case_object_to_sentence(frame.object_text)
    if not actor or not obj:
        return ""
    # Drop headline punctuation/colon fragments that often act as subtitles.
    obj = re.split(r"\s+[|]\s+|\s+[—–]\s+", obj, maxsplit=1)[0].strip()
    if frame.action in {"approved", "adopted"} and re.match(r"^AI\s+data\s+cent(?:er|re)\s+moratorium\b", obj, flags=re.I):
        obj = "an " + obj
    return _sentence(f"{actor} {frame.action} {obj}")


def _frame_surface(frame: EventFrame) -> str:
    if frame.source_kind == "title":
        return _realize_title_frame(frame)
    return _sentence(frame.sentence)


def _title_is_corroborated(frame: EventFrame, body_frames: Sequence[EventFrame], body_sentences: Sequence[str]) -> bool:
    title_tokens = frame.identity_tokens
    if not title_tokens:
        return False
    for body in body_frames:
        overlap = title_tokens.intersection(body.identity_tokens)
        if len(overlap) >= 2 or _similarity(frame.sentence, body.sentence) >= 0.55:
            return True
    for sentence in body_sentences[:10]:
        overlap = title_tokens.intersection(_tokens(sentence))
        if len(overlap) >= 2:
            return True
    return False


def _support_candidate(frame: EventFrame, sentence: str, *, index: int, domain: str) -> tuple[float, str] | None:
    value = _sentence(sentence)
    if not value or len(value.split()) < 7 or len(value.split()) > 42:
        return None
    if value.startswith(('"', '“')):
        return None
    if _similarity(frame.sentence, value) >= 0.72:
        return None
    frame_tokens = _tokens(frame.sentence)
    support_tokens = _tokens(value)
    if frame_tokens and support_tokens:
        overlap_ratio = len(frame_tokens.intersection(support_tokens)) / max(1, min(len(frame_tokens), len(support_tokens)))
        if overlap_ratio >= 0.58:
            return None
    # Avoid attaching a second unrelated event.  Supporting facts either share
    # event identity or provide a quantified metric adjacent to the frame.
    overlap = len(frame.identity_tokens.intersection(_tokens(value)))
    quantified = bool(re.search(r"(?:\$?\d[\d,.]*\s*(?:%|percent|billion|million|trillion|GW|MW|Tbps|Gbps|jobs?|customers?)?)", value, flags=re.I))
    if overlap < 2 and not quantified:
        return None
    if not strict_domain_fit(domain, f"{frame.sentence} {value}"):
        return None
    score = overlap * 2.5 + (5.0 if quantified else 0.0)
    score += max(0.0, 3.0 - abs(index - frame.index) * 0.8)
    # Metric/context openings are preferred as *support* once a true event has
    # already been established.
    if _GENERIC_ACTOR_OPENINGS.search(value) or _CONTEXT_OPENING.search(value):
        score += 1.5
    return score, value


def compose_development(
    *,
    domain: str,
    source_title: str,
    body_sentences: Sequence[str],
) -> CompositionResult | None:
    """Extract one semantic event and deterministically realize Reader copy.

    The body is authoritative.  A title frame is available only as a fallback
    when its actor/event identity is corroborated by the body.  A quantified or
    contextual sentence may support the event but can never replace it.
    """
    body = [_sentence(item) for item in body_sentences if _sentence(item)]
    if not body:
        return None

    body_frames = [
        frame for idx, sentence in enumerate(body[:24])
        if (frame := _frame_from_sentence(sentence, source_kind="body", index=idx)) is not None
    ]
    lead_frames = [frame for frame in body_frames if frame.lead_eligible and strict_domain_fit(domain, frame.sentence)]

    title_frame = _frame_from_sentence(source_title, source_kind="title", index=0) if source_title else None
    if title_frame and not strict_domain_fit(domain, title_frame.sentence):
        title_frame = None
    if title_frame and not _title_is_corroborated(title_frame, body_frames, body):
        title_frame = None

    candidates = list(lead_frames)
    if title_frame and title_frame.lead_eligible:
        candidates.append(title_frame)
    if not candidates:
        return None

    # Prefer explicit semantic event classes and body evidence.  Similarity to
    # the publisher title is a tie-breaker, not the organizing principle.
    title_tokens = _tokens(source_title)
    ranked: list[tuple[float, EventFrame]] = []
    for frame in candidates:
        score = frame.score
        identity_overlap = len(title_tokens.intersection(frame.identity_tokens))
        score += min(7.0, identity_overlap * 1.8)
        if frame.source_kind == "body":
            score += 2.0
        # A standalone market-move sentence is weaker than the company event
        # that caused it when both exist.
        if frame.event_type == "market_move" and any(f.event_type == "earnings_result" for f in lead_frames):
            score -= 6.0
        ranked.append((score, frame))
    ranked.sort(key=lambda item: item[0], reverse=True)
    frame = ranked[0][1]
    primary = _frame_surface(frame)
    if not primary or not strict_domain_fit(domain, primary):
        return None

    support_options: list[tuple[float, str]] = []
    for idx, sentence in enumerate(body[:24]):
        if idx == frame.index and frame.source_kind == "body":
            continue
        option = _support_candidate(frame, sentence, index=idx, domain=domain)
        if option:
            support_options.append(option)
    support_options.sort(key=lambda item: item[0], reverse=True)

    text = primary
    evidence = frame.sentence
    support_count = 0
    if support_options and len(primary.split()) < 42:
        support = support_options[0][1]
        combined = _spaces(f"{primary} {support}")
        if len(combined.split()) <= MAX_WORDS:
            text = combined
            evidence = _spaces(f"{frame.sentence} {support}")
            support_count = 1

    if len(text.split()) > MAX_WORDS or not strict_domain_fit(domain, text):
        return None
    return CompositionResult(
        text=_spaces(text),
        evidence_text=evidence,
        event_type=frame.event_type,
        actor=frame.actor,
        used_title=frame.source_kind == "title",
        support_count=support_count,
        reason="deterministic semantic event frame composed from grounded source evidence",
    )


__all__ = [
    "CompositionResult",
    "EventFrame",
    "compose_development",
    "strict_domain_fit",
]
