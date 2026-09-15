"""Minimal publication gate for AI Macro generated commentary.

The gate protects factual grounding and basic structural integrity.  Stylistic
patterns are recorded as diagnostics so early runs can be evaluated without
turning every historical model quirk into a publication rule.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any, Iterable

from analytics.read_briefing import briefing_event_ids, briefing_fact_ids
from analytics.editorial_quality import diagnose_passage
from analytics.read_evidence import evidence_fact_index
from analytics.read_models import GeneratedEditorialSynthesis, SupportedPassage

EDITORIAL_VALIDATOR_VERSION = "5.1.0"

_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
    r"(?:[xXkKmMbBtT]|\s*(?:times|thousand|million|billion|trillion))?"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_SCALE = {
    "k": Decimal("1000"),
    "thousand": Decimal("1000"),
    "m": Decimal("1000000"),
    "million": Decimal("1000000"),
    "b": Decimal("1000000000"),
    "billion": Decimal("1000000000"),
    "t": Decimal("1000000000000"),
    "trillion": Decimal("1000000000000"),
}
_NEGATIVE_DIRECTION_RE = re.compile(
    r"\b(?:fell|fallen|falling|falls?|decline|declined|declining|declines|decrease|decreased|decreasing|decreases|"
    r"drop|dropped|dropping|drops|contract|contracted|contracting|contracts|contraction|down|lower|below|negative|"
    r"reduce|reduced|reducing|reduction|lost|loss|weakened?|weakening)\b",
    re.IGNORECASE,
)
_CONSECUTIVE_REPEAT_RE = re.compile(r"\b([A-Za-z]{2,})\b(?:\s+\1\b){2,}", re.IGNORECASE)
def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+[\w'’-]*\b", str(text or "")))


def _normalized_number(raw: str) -> str | None:
    token = str(raw or "").strip().casefold().replace(",", "")
    match = re.fullmatch(
        r"([-+]?(?:\d+(?:\.\d+)?))(?:\s*(x|times|k|m|b|t|thousand|million|billion|trillion))?",
        token,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    try:
        value = Decimal(match.group(1))
    except InvalidOperation:
        return None
    suffix = (match.group(2) or "").casefold()
    if suffix and suffix not in {"x", "times"}:
        value *= _SCALE[suffix]
    if value == 0:
        return "0"
    normalized = format(value.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized


def _numeric_tokens(text: str) -> dict[str, str]:
    output: dict[str, str] = {}
    for match in _NUMBER_RE.finditer(str(text or "")):
        rendered = match.group(0).strip().lstrip("+")
        normalized = _normalized_number(rendered)
        if normalized is not None:
            output[rendered] = normalized
    return output


def _negative_direction_near_number(text: str, rendered: str) -> bool:
    source = str(text or "")
    for match in re.finditer(re.escape(rendered), source, flags=re.IGNORECASE):
        left = source[max(0, match.start() - 72):match.start()]
        right = source[match.end():min(len(source), match.end() + 24)]
        left = re.split(r"[.!?;]", left)[-1]
        right = re.split(r"[.!?;]", right)[0]
        if _NEGATIVE_DIRECTION_RE.search(left) or _NEGATIVE_DIRECTION_RE.search(right):
            return True
    return False


def _number_supported(text: str, rendered: str, normalized: str, allowed: set[str]) -> bool:
    if normalized in allowed:
        return True
    if normalized.startswith("-"):
        return False
    return f"-{normalized}" in allowed and _negative_direction_near_number(text, rendered)


def _allowed_numbers_from_fact(fact: dict[str, Any]) -> set[str]:
    allowed: set[str] = set()
    for field in ("label", "display", "context"):
        allowed.update(_numeric_tokens(str(fact.get(field) or "")).values())
    return allowed


def _event_index(briefing: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(event.get("event_id") or ""): dict(event)
        for event in briefing.get("recent_developments", []) or []
        if isinstance(event, dict) and event.get("event_id")
    }


def _allowed_numbers_from_event(event: dict[str, Any]) -> set[str]:
    allowed: set[str] = set()
    for field in ("date", "development"):
        allowed.update(_numeric_tokens(str(event.get(field) or "")).values())
    return allowed


def _failure(label: str, reason: str, message: str, **details: Any) -> dict[str, Any]:
    return {"label": label, "reason": reason, "message": message, **details}


def _validate_passage(
    passage: SupportedPassage,
    *,
    label: str,
    fact_index: dict[str, dict[str, Any]],
    event_index: dict[str, dict[str, Any]],
    supplied_fact_ids: set[str],
    supplied_event_ids: set[str],
    domain: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hard: list[dict[str, Any]] = []
    diagnostics = [issue.to_dict() for issue in diagnose_passage(passage, scope=label)]
    fact_ids = [str(value) for value in passage.fact_ids]
    event_ids = [str(value) for value in passage.event_ids]

    if not fact_ids and not event_ids:
        hard.append(_failure(label, "missing_support", "Passage contains no supporting fact_ids or event_ids."))

    unknown_facts = [fact_id for fact_id in fact_ids if fact_id not in supplied_fact_ids or fact_id not in fact_index]
    if unknown_facts:
        hard.append(_failure(label, "unknown_fact_ids", "Passage cites facts that were not supplied.", fact_ids=unknown_facts))
    unknown_events = [event_id for event_id in event_ids if event_id not in supplied_event_ids or event_id not in event_index]
    if unknown_events:
        hard.append(_failure(label, "unknown_event_ids", "Passage cites developments that were not supplied.", event_ids=unknown_events))

    if domain:
        wrong_facts = [fact_id for fact_id in fact_ids if not fact_id.startswith(f"{domain}.")]
        if wrong_facts:
            hard.append(_failure(label, "out_of_scope_fact_ids", "Domain Read cites facts from another domain.", fact_ids=wrong_facts))
        wrong_events = [
            event_id for event_id in event_ids
            if str(event_index.get(event_id, {}).get("domain") or "") not in {"", domain}
        ]
        if wrong_events:
            hard.append(_failure(label, "out_of_scope_event_ids", "Domain Read cites a development assigned to another domain.", event_ids=wrong_events))

    allowed_numbers: set[str] = set()
    for fact_id in fact_ids:
        fact = fact_index.get(fact_id)
        if fact:
            allowed_numbers.update(_allowed_numbers_from_fact(fact))
    for event_id in event_ids:
        event = event_index.get(event_id)
        if event:
            allowed_numbers.update(_allowed_numbers_from_event(event))

    unsupported = [
        rendered
        for rendered, normalized in _numeric_tokens(passage.text).items()
        if not _number_supported(passage.text, rendered, normalized, allowed_numbers)
    ]
    if unsupported:
        hard.append(_failure(
            label,
            "unsupported_numeric_tokens",
            "Passage contains numbers not present in its cited support.",
            numeric_tokens=unsupported,
        ))

    if _CONSECUTIVE_REPEAT_RE.search(passage.text):
        hard.append(_failure(label, "obviously_broken_prose", "Passage repeats the same word three or more times consecutively."))

    words = _word_count(passage.text)
    if words > 450:
        hard.append(_failure(label, "gross_length", f"Passage contains {words} words; output is clearly outside the product format."))
    return hard, diagnostics


def _iter_macro_passages(synthesis: GeneratedEditorialSynthesis) -> Iterable[tuple[str, SupportedPassage]]:
    yield "macro.headline", synthesis.macro_read.headline
    for index, paragraph in enumerate(synthesis.macro_read.paragraphs):
        yield f"macro.paragraphs[{index}]", paragraph


def validate_editorial_synthesis(
    synthesis: GeneratedEditorialSynthesis,
    packets: dict[str, dict[str, Any]],
    *,
    briefing: dict[str, Any],
    candidate_domains: Iterable[str],
    bootstrap: bool = False,
) -> dict[str, Any]:
    """Return a low-bar factual/sanity publication decision for one candidate."""
    candidates = [str(domain) for domain in candidate_domains]
    model_domains = [str(read.domain) for read in synthesis.domain_reads]
    hard: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    if len(model_domains) != len(set(model_domains)):
        hard.append(_failure("editorial_synthesis", "duplicate_domains", "Domain Reads contain duplicate domains."))
    if bootstrap:
        if model_domains != candidates:
            hard.append(_failure(
                "editorial_synthesis",
                "bootstrap_domain_mismatch",
                "The first publication must return every candidate domain in order.",
                candidate_domains=candidates,
                returned_domains=model_domains,
            ))
    else:
        unexpected = [domain for domain in model_domains if domain not in candidates]
        if unexpected:
            hard.append(_failure(
                "editorial_synthesis",
                "unexpected_domains",
                "Domain Reads may only replace sections identified as update candidates.",
                candidate_domains=candidates,
                returned_domains=model_domains,
                unexpected_domains=unexpected,
            ))

    fact_index = evidence_fact_index(packets)
    events = _event_index(briefing)
    supplied_facts = briefing_fact_ids(briefing)
    supplied_events = briefing_event_ids(briefing)

    checked = 0
    for read in synthesis.domain_reads:
        for field, passage in (("headline", read.headline), ("body", read.body)):
            checked += 1
            passage_hard, passage_diagnostics = _validate_passage(
                passage,
                label=f"{read.domain}.{field}",
                fact_index=fact_index,
                event_index=events,
                supplied_fact_ids=supplied_facts,
                supplied_event_ids=supplied_events,
                domain=read.domain,
            )
            hard.extend(passage_hard)
            diagnostics.extend(passage_diagnostics)

    macro_words = 0
    for label, passage in _iter_macro_passages(synthesis):
        checked += 1
        macro_words += _word_count(passage.text)
        passage_hard, passage_diagnostics = _validate_passage(
            passage,
            label=label,
            fact_index=fact_index,
            event_index=events,
            supplied_fact_ids=supplied_facts,
            supplied_event_ids=supplied_events,
        )
        hard.extend(passage_hard)
        diagnostics.extend(passage_diagnostics)
    if macro_words > 1000:
        hard.append(_failure("macro", "gross_length", f"Macro Read contains {macro_words} words; output is clearly outside the product format."))

    return {
        "passed": not hard,
        "hard_errors": [str(item.get("message") or item.get("reason") or "") for item in hard],
        "hard_failures": hard,
        "diagnostics": diagnostics,
        "checked_passages": checked,
        "publication_policy": "minimal_grounding_and_sanity_gate",
        "validator_version": EDITORIAL_VALIDATOR_VERSION,
    }


__all__ = ["EDITORIAL_VALIDATOR_VERSION", "validate_editorial_synthesis"]
