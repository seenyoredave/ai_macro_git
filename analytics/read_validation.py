"""Deterministic publication gate for generated v7 commentary."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Iterable

from analytics.read_evidence import DOMAIN_ORDER, evidence_fact_index
from analytics.read_models import GeneratedDomainRead, GeneratedDomainReadSet, GeneratedMacroRead, SupportedSentence

VALIDATOR_VERSION = "2.6.1"
_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
    r"(?:[xXkKmMbBtT]|\s*(?:times|thousand|million|billion|trillion))?"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_INTERROGATIVE_RE = re.compile(r"(?:^|[.!?]\s+)(?:who|what|when|where|why|how)\b", re.IGNORECASE)
_NEGATIVE_DIRECTION_RE = re.compile(
    r"\b(?:fell|fallen|falling|falls?|decline|declined|declining|declines|decrease|decreased|decreasing|decreases|"
    r"drop|dropped|dropping|drops|contract|contracted|contracting|contracts|contraction|shr(?:ank|unk|inking)|"
    r"down|lower|below|negative|reduce|reduced|reducing|reduction|lost|loss|weakened?|weakening)\b",
    re.IGNORECASE,
)

MAX_ANALYSIS_SENTENCE_WORDS = 32
MAX_SENTENCE_COMMAS = 3
MAX_DISPLAYED_QUANTITIES = 3
MAX_DOMAIN_ANALYSIS_WORDS = 95
MAX_MACRO_ANALYSIS_WORDS = 120
MAX_MACRO_SENTENCE_DOMAINS = 2
MAX_MACRO_CLOSING_WORDS = 28

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


@dataclass(frozen=True, slots=True)
class ValidationResult:
    passed: bool
    errors: tuple[str, ...]
    checked_claims: int
    grounded_claims: int
    failures: tuple[dict[str, Any], ...] = ()
    version: str = VALIDATOR_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "errors": list(self.errors),
            "checked_claims": self.checked_claims,
            "grounded_claims": self.grounded_claims,
            "failures": [dict(item) for item in self.failures],
            "version": self.version,
        }


def _word_count(text: str) -> int:
    return len(str(text or "").split())


def _numeric_occurrence_count(text: str) -> int:
    """Count reader-visible quantities, treating a bounded range as one item.

    The editorial ceiling is about how many quantities a reader must hold in
    mind, not how many numeric tokens the regex can find.  A range such as
    ``18–64`` or ``2024 to 2026`` is one displayed quantity.  Ordinary lists
    and separate comparisons remain separate quantities.
    """
    rendered = str(text or "")
    matches = list(_NUMBER_RE.finditer(rendered))
    if not matches:
        return 0

    count = len(matches)
    range_separator = re.compile(r"^\s*(?:-|–|—|to|through)\s*$", re.IGNORECASE)
    for left, right in zip(matches, matches[1:]):
        if range_separator.fullmatch(rendered[left.end():right.start()]):
            count -= 1
    return count


def _read_numeric_occurrence_count(sentences: Iterable[SupportedSentence]) -> int:
    return sum(_numeric_occurrence_count(sentence.text) for sentence in sentences)


def _grammatical_comma_count(text: str) -> int:
    # Thousands separators are numeric formatting, not sentence structure.
    prose = re.sub(r"(?<=\d),(?=\d{3}(?:\D|$))", "", str(text or ""))
    return prose.count(",")


def _validate_prose_shape(sentence: SupportedSentence, *, label: str) -> tuple[list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    failures: list[dict[str, Any]] = []
    comma_count = _grammatical_comma_count(sentence.text)
    if comma_count > MAX_SENTENCE_COMMAS:
        message = f"{label}: sentence uses more than {MAX_SENTENCE_COMMAS} commas"
        errors.append(message)
        failures.append(_failure(label, "comma_density", sentence, message, comma_count=comma_count))
    if ";" in str(sentence.text or ""):
        message = f"{label}: semicolons are not allowed in Reader commentary"
        errors.append(message)
        failures.append(_failure(label, "semicolon", sentence, message))
    return errors, failures


def _canonical_number(raw: str) -> str | None:
    token = str(raw or "").strip().casefold().replace(",", "")
    if not token:
        return None
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
    """Return canonical numeric values keyed by the rendered token.

    Canonicalization treats formatting-equivalent forms such as ``300k`` and
    ``300,000`` as the same number while keeping materially different values
    distinct.  Dates and thresholds embedded in fact labels/context are still
    factual content and are therefore eligible only when that fact_id is cited.
    """
    tokens: dict[str, str] = {}
    for match in _NUMBER_RE.finditer(str(text or "")):
        rendered = match.group(0).strip().lstrip("+")
        canonical = _canonical_number(rendered)
        if canonical is not None:
            tokens[rendered] = canonical
    return tokens


def _allowed_numeric_tokens(facts: Iterable[dict[str, Any]]) -> set[str]:
    """Return numbers the model was actually allowed to see.

    Raw deterministic ``value`` fields intentionally do not participate in
    grounding.  The paid prompt exposes only label/display/context, so accepting
    a hidden raw ratio would create a validation backdoor around the model-facing
    evidence contract.
    """
    allowed: set[str] = set()
    for fact in facts:
        for field in ("label", "display", "context"):
            allowed.update(_numeric_tokens(str(fact.get(field) or "")).values())
    return allowed


def _negative_direction_near_number(text: str, rendered: str) -> bool:
    """Return True when prose encodes the negative sign linguistically.

    A cited fact displayed as ``-8.4%`` may naturally be written as ``fell
    8.4%``.  That is not a numeric hallucination: the verb carries the sign.
    Keep the allowance deliberately local to the numeric occurrence so a
    negative word elsewhere in a compound sentence cannot license an unrelated
    positive number.
    """
    source = str(text or "")
    for match in re.finditer(re.escape(rendered), source, flags=re.IGNORECASE):
        left = source[max(0, match.start() - 72):match.start()]
        right = source[match.end():min(len(source), match.end() + 24)]
        # Do not let direction leak across sentence/major-clause boundaries.
        left = re.split(r"[.!?;]", left)[-1]
        right = re.split(r"[.!?;]", right)[0]
        if _NEGATIVE_DIRECTION_RE.search(left) or _NEGATIVE_DIRECTION_RE.search(right):
            return True
    return False


def _numeric_token_supported(*, text: str, rendered: str, canonical: str, allowed_numbers: set[str]) -> bool:
    if canonical in allowed_numbers:
        return True
    if canonical.startswith("-"):
        return False
    negative_equivalent = f"-{canonical}"
    return negative_equivalent in allowed_numbers and _negative_direction_near_number(text, rendered)


def _failure(label: str, reason: str, sentence: SupportedSentence | None, message: str, **details: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "label": label,
        "reason": reason,
        "message": message,
    }
    if sentence is not None:
        payload["sentence"] = sentence.text
        payload["fact_ids"] = [str(item) for item in sentence.fact_ids]
    payload.update(details)
    return payload


def _validate_sentence(
    sentence: SupportedSentence,
    *,
    fact_index: dict[str, dict[str, Any]],
    allowed_prefixes: tuple[str, ...],
    label: str,
) -> tuple[list[str], list[dict[str, Any]], bool]:
    errors: list[str] = []
    failures: list[dict[str, Any]] = []
    fact_ids = [str(item) for item in sentence.fact_ids]
    unknown = [fact_id for fact_id in fact_ids if fact_id not in fact_index]
    if unknown:
        message = f"{label}: unknown fact_ids: {', '.join(unknown)}"
        errors.append(message)
        failures.append(_failure(label, "unknown_fact_ids", sentence, message, unknown_fact_ids=unknown))
    wrong_scope = [fact_id for fact_id in fact_ids if not fact_id.startswith(allowed_prefixes)]
    if wrong_scope:
        message = f"{label}: out-of-scope fact_ids: {', '.join(wrong_scope)}"
        errors.append(message)
        failures.append(_failure(label, "out_of_scope_fact_ids", sentence, message, out_of_scope_fact_ids=wrong_scope))
    prose_errors, prose_failures = _validate_prose_shape(sentence, label=label)
    errors.extend(prose_errors)
    failures.extend(prose_failures)
    known_facts = [fact_index[fact_id] for fact_id in fact_ids if fact_id in fact_index]
    used_numbers = _numeric_tokens(sentence.text)
    allowed_numbers = _allowed_numeric_tokens(known_facts)
    unsupported_rendered = [
        rendered
        for rendered, canonical in used_numbers.items()
        if not _numeric_token_supported(
            text=sentence.text,
            rendered=rendered,
            canonical=canonical,
            allowed_numbers=allowed_numbers,
        )
    ]
    if unsupported_rendered:
        message = f"{label}: unsupported numeric tokens: {', '.join(unsupported_rendered)}"
        errors.append(message)
        failures.append(
            _failure(
                label,
                "unsupported_numeric_tokens",
                sentence,
                message,
                unsupported_numeric_tokens=unsupported_rendered,
                cited_facts=[
                    {
                        "id": str(fact.get("id") or ""),
                        "label": str(fact.get("label") or ""),
                        "display": str(fact.get("display") or ""),
                        "context": str(fact.get("context") or ""),
                    }
                    for fact in known_facts
                ],
            )
        )
    if "?" in sentence.text or _INTERROGATIVE_RE.search(sentence.text.strip()):
        message = f"{label}: interrogative phrasing is not allowed"
        errors.append(message)
        failures.append(_failure(label, "interrogative", sentence, message))
    return errors, failures, not errors


def _validate_domain_read(read: GeneratedDomainRead, fact_index: dict[str, dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]], int, int]:
    errors: list[str] = []
    failures: list[dict[str, Any]] = []
    checked = grounded = 0
    prefix = (f"{read.domain}.",)
    if _word_count(read.headline.text) > 12:
        message = f"{read.domain}: headline exceeds 12 words"
        errors.append(message)
        failures.append(_failure(f"{read.domain}.headline", "word_limit", read.headline, message))
    analysis_words = _word_count(" ".join(item.text for item in read.analysis))
    if analysis_words > MAX_DOMAIN_ANALYSIS_WORDS:
        message = f"{read.domain}: analysis exceeds {MAX_DOMAIN_ANALYSIS_WORDS} words"
        errors.append(message)
        failures.append(_failure(f"{read.domain}.analysis", "word_limit", None, message, word_count=analysis_words))
    numeric_occurrences = _read_numeric_occurrence_count(read.analysis)
    if numeric_occurrences > MAX_DISPLAYED_QUANTITIES:
        message = f"{read.domain}: analysis uses more than {MAX_DISPLAYED_QUANTITIES} displayed quantities"
        errors.append(message)
        failures.append(_failure(f"{read.domain}.analysis", "numeric_density", None, message, numeric_occurrences=numeric_occurrences))
    for index, sentence in enumerate(read.analysis):
        words = _word_count(sentence.text)
        if words > MAX_ANALYSIS_SENTENCE_WORDS:
            message = f"{read.domain}.analysis[{index}]: sentence exceeds {MAX_ANALYSIS_SENTENCE_WORDS} words"
            errors.append(message)
            failures.append(_failure(f"{read.domain}.analysis[{index}]", "sentence_length", sentence, message, word_count=words))
    for field, sentence in [("headline", read.headline), *[(f"analysis[{i}]", item) for i, item in enumerate(read.analysis)]]:
        checked += 1
        sentence_errors, sentence_failures, ok = _validate_sentence(
            sentence,
            fact_index=fact_index,
            allowed_prefixes=prefix,
            label=f"{read.domain}.{field}",
        )
        errors.extend(sentence_errors)
        failures.extend(sentence_failures)
        grounded += int(ok)
    return errors, failures, checked, grounded


def validate_domain_read_set(read_set: GeneratedDomainReadSet, packets: dict[str, dict]) -> ValidationResult:
    fact_index = evidence_fact_index(packets)
    errors: list[str] = []
    failures: list[dict[str, Any]] = []
    checked = grounded = 0
    domains = [read.domain for read in read_set.reads]
    expected = set(DOMAIN_ORDER)
    found = set(domains)
    if found != expected:
        missing = [domain for domain in DOMAIN_ORDER if domain not in found]
        unexpected = [domain for domain in domains if domain not in expected]
        message = f"domain membership mismatch: missing={missing}, unexpected={unexpected}"
        errors.append(message)
        failures.append(_failure("domain_set", "domain_membership", None, message, missing=missing, unexpected=unexpected))
    if len(set(domains)) != len(domains):
        message = "domain Read set contains duplicate domains"
        errors.append(message)
        failures.append(_failure("domain_set", "duplicate_domains", None, message, domains=domains))
    for read in read_set.reads:
        read_errors, read_failures, read_checked, read_grounded = _validate_domain_read(read, fact_index)
        errors.extend(read_errors)
        failures.extend(read_failures)
        checked += read_checked
        grounded += read_grounded
    return ValidationResult(not errors, tuple(errors), checked, grounded, tuple(failures))


_MACRO_LIFECYCLE_STAGE = {
    "market": "capital_markets",
    "finance": "capital_markets",
    "compute": "physical_buildout",
    "data_center": "physical_buildout",
    "connectivity": "physical_buildout",
    "power": "physical_buildout",
    "grid_storage": "physical_buildout",
    "water": "physical_buildout",
    "adoption": "adoption",
    "workforce": "outcomes",
    "economic_impact": "outcomes",
}


def _sentence_domains(sentence: SupportedSentence) -> set[str]:
    domains: set[str] = set()
    for fact_id in sentence.fact_ids:
        prefix = str(fact_id).split(".", 1)[0]
        if prefix:
            domains.add(prefix)
    return domains


def _normalized_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", str(text or "").casefold())


def _domain_language_reuse(text: str, domain_texts: dict[str, list[str]] | None) -> tuple[str, str] | None:
    """Detect verbatim/near-verbatim reuse of already-published domain prose.

    Macro synthesis is intentionally independent.  Reject exact reuse and long
    copied word runs while allowing ordinary shared economic vocabulary.
    """
    if not domain_texts:
        return None
    macro_words = _normalized_words(text)
    if not macro_words:
        return None
    macro_norm = " ".join(macro_words)
    for domain, texts in domain_texts.items():
        for source in texts:
            source_words = _normalized_words(source)
            if not source_words:
                continue
            source_norm = " ".join(source_words)
            if macro_norm == source_norm:
                return domain, source
            if len(macro_words) >= 8 and len(source_words) >= 8:
                source_joined = " " + source_norm + " "
                for start in range(0, len(macro_words) - 7):
                    run = " ".join(macro_words[start:start + 8])
                    if f" {run} " in source_joined:
                        return domain, source
    return None


def validate_macro_read(
    read: GeneratedMacroRead,
    packets: dict[str, dict],
    *,
    domain_texts: dict[str, list[str]] | None = None,
) -> ValidationResult:
    fact_index = evidence_fact_index(packets)
    errors: list[str] = []
    failures: list[dict[str, Any]] = []
    checked = grounded = 0
    selected = list(read.selected_domains)
    if not 4 <= len(selected) <= 6 or len(selected) != len(set(selected)):
        message = "macro selected_domains must contain 4-6 distinct domains"
        errors.append(message)
        failures.append(_failure("macro.selected_domains", "domain_selection", None, message, selected_domains=selected))

    lifecycle_stages = {_MACRO_LIFECYCLE_STAGE.get(domain, "") for domain in selected}
    lifecycle_stages.discard("")
    if len(lifecycle_stages) < 3:
        message = "macro selected_domains must span at least three lifecycle stages"
        errors.append(message)
        failures.append(
            _failure(
                "macro.selected_domains",
                "lifecycle_coverage",
                None,
                message,
                selected_domains=selected,
                lifecycle_stages=sorted(lifecycle_stages),
            )
        )

    if _word_count(read.headline.text) > 16:
        message = "macro: headline exceeds 16 words"
        errors.append(message)
        failures.append(_failure("macro.headline", "word_limit", read.headline, message))
    macro_words = _word_count(" ".join(item.text for item in read.analysis))
    if macro_words > MAX_MACRO_ANALYSIS_WORDS:
        message = f"macro: analysis exceeds {MAX_MACRO_ANALYSIS_WORDS} words"
        errors.append(message)
        failures.append(_failure("macro.analysis", "word_limit", None, message, word_count=macro_words))
    numeric_occurrences = _read_numeric_occurrence_count(read.analysis)
    if numeric_occurrences > MAX_DISPLAYED_QUANTITIES:
        message = f"macro: analysis uses more than {MAX_DISPLAYED_QUANTITIES} displayed quantities"
        errors.append(message)
        failures.append(_failure("macro.analysis", "numeric_density", None, message, numeric_occurrences=numeric_occurrences))

    all_claims = [read.headline, *read.analysis]
    cited_domains: set[str] = set()
    for sentence in all_claims:
        cited_domains.update(_sentence_domains(sentence))
    missing_selected = [domain for domain in selected if domain not in cited_domains]
    if missing_selected:
        message = f"macro selected domains without supporting claims: {', '.join(missing_selected)}"
        errors.append(message)
        failures.append(
            _failure(
                "macro.selected_domains",
                "unused_selected_domains",
                None,
                message,
                selected_domains=selected,
                unused_domains=missing_selected,
            )
        )

    for index, sentence in enumerate(read.analysis):
        words = _word_count(sentence.text)
        if words > MAX_ANALYSIS_SENTENCE_WORDS:
            message = f"macro.analysis[{index}]: sentence exceeds {MAX_ANALYSIS_SENTENCE_WORDS} words"
            errors.append(message)
            failures.append(_failure(f"macro.analysis[{index}]", "sentence_length", sentence, message, word_count=words))
        sentence_domains = _sentence_domains(sentence)
        if len(sentence_domains) > MAX_MACRO_SENTENCE_DOMAINS:
            message = f"macro.analysis[{index}]: sentence spans more than {MAX_MACRO_SENTENCE_DOMAINS} domains"
            errors.append(message)
            failures.append(_failure(
                f"macro.analysis[{index}]",
                "sentence_scope",
                sentence,
                message,
                domains=sorted(sentence_domains),
            ))
    final_words = _word_count(read.analysis[-1].text) if read.analysis else 0
    if final_words > MAX_MACRO_CLOSING_WORDS:
        message = f"macro.analysis[3]: closing sentence exceeds {MAX_MACRO_CLOSING_WORDS} words"
        errors.append(message)
        failures.append(_failure("macro.analysis[3]", "closing_sentence_length", read.analysis[-1], message, word_count=final_words))

    cross_domain_sentences = sum(1 for sentence in read.analysis if len(_sentence_domains(sentence)) >= 2)
    if cross_domain_sentences < 2:
        message = "macro analysis must contain at least two cross-domain synthesis sentences"
        errors.append(message)
        failures.append(
            _failure(
                "macro.analysis",
                "insufficient_cross_domain_synthesis",
                None,
                message,
                cross_domain_sentences=cross_domain_sentences,
            )
        )

    prefixes = tuple(f"{domain}." for domain in selected)
    for field, sentence in [("headline", read.headline), *[(f"analysis[{i}]", item) for i, item in enumerate(read.analysis)]]:
        checked += 1
        sentence_errors, sentence_failures, ok = _validate_sentence(
            sentence,
            fact_index=fact_index,
            allowed_prefixes=prefixes,
            label=f"macro.{field}",
        )
        reuse = _domain_language_reuse(sentence.text, domain_texts)
        if reuse:
            source_domain, source_text = reuse
            message = f"macro.{field}: reuses domain Read language from {source_domain}"
            sentence_errors.append(message)
            sentence_failures.append(
                _failure(
                    f"macro.{field}",
                    "domain_language_reuse",
                    sentence,
                    message,
                    source_domain=source_domain,
                    source_text=source_text,
                )
            )
            ok = False
        errors.extend(sentence_errors)
        failures.extend(sentence_failures)
        grounded += int(ok)
    return ValidationResult(not errors, tuple(errors), checked, grounded, tuple(failures))
