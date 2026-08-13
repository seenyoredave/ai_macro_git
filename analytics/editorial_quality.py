"""Deterministic, comparative editorial gate for Reader prose."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
from statistics import pstdev
from typing import Any, Iterable

from analytics.read_models import GeneratedDomainReadSet, GeneratedMacroRead, SupportedSentence

EDITORIAL_QUALITY_VERSION = "1.0.0"
MIN_READ_SCORE = 80
MIN_FAILED_DRAFT_IMPROVEMENT = 8
MAX_SENTENCE_WORDS = 25
MAX_CONNECTORS = 2
MIN_CADENCE_SPREAD = 4
_CONNECTOR_RE = re.compile(r"\b(?:and|but|while|although|though|yet|where|because|so|which|whereas)\b", re.IGNORECASE)
_NEGATIVE_FRAME_RE = re.compile(r"\b(?:is|are|was|were|do|does|did|can|cannot|could|will|would)\s+(?:not|n't)\b", re.IGNORECASE)
_OPENING_RE = re.compile(r"^[^A-Za-z0-9]*([A-Za-z]+(?:\s+[A-Za-z]+)?)", re.IGNORECASE)
_NOMINALIZATION_RE = re.compile(r"\b[A-Za-z]{5,}(?:tion|sion|ment|ments|ity|ities|ance|ence|ness|ship|ships)\b", re.IGNORECASE)
_CONTRAST_RE = re.compile(r"\b(?:but|although|though|yet|while|whereas)\b", re.IGNORECASE)
_TEMPORAL_LOAD_RE = re.compile(r"\b(?:current|currently|present|presently|today|today's|future|forward|beyond|longer-term)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class EditorialIssue:
    scope: str
    reason: str
    message: str
    penalty: int
    text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "reason": self.reason,
            "message": self.message,
            "penalty": self.penalty,
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class EditorialScore:
    score: int
    passed: bool
    issues: tuple[EditorialIssue, ...]
    sentence_words: tuple[int, ...]
    version: str = EDITORIAL_QUALITY_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "passed": self.passed,
            "issues": [issue.to_dict() for issue in self.issues],
            "sentence_words": list(self.sentence_words),
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class ComparativeEditorialResult:
    passed: bool
    draft_score: int
    final_score: int
    required_improvement: int
    actual_improvement: int
    draft: EditorialScore
    final: EditorialScore
    failures: tuple[str, ...]
    version: str = EDITORIAL_QUALITY_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "draft_score": self.draft_score,
            "final_score": self.final_score,
            "required_improvement": self.required_improvement,
            "actual_improvement": self.actual_improvement,
            "draft": self.draft.to_dict(),
            "final": self.final.to_dict(),
            "failures": list(self.failures),
            "version": self.version,
        }


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(text or "").casefold()))


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+(?:['’][A-Za-z]+)?", str(text or ""))


def _failed_prose() -> tuple[list[str], list[str], list[str]]:
    # Offline regression evaluation only. This file is never included in the
    # production language-layer payload sent to OpenAI.
    path = Path(__file__).resolve().parents[1] / "language" / "editorial_regression_cases.json"
    memory = json.loads(path.read_text(encoding="utf-8"))
    cases = [str(item.get("text") or "") for item in memory.get("cases") or []]
    abstract = [str(item).casefold() for item in memory.get("abstract_phrases") or []]
    mechanical = [str(item).casefold() for item in memory.get("mechanical_distinction_phrases") or []]
    return cases, abstract, mechanical


def _historical_match(text: str, failures: Iterable[str]) -> tuple[str, float] | None:
    normalized = _normalize(text)
    if len(normalized.split()) < 8:
        return None
    for failure in failures:
        candidate = _normalize(failure)
        ratio = SequenceMatcher(None, normalized, candidate).ratio()
        if ratio >= 0.86:
            return failure, ratio
        failure_words = candidate.split()
        for start in range(max(0, len(failure_words) - 7)):
            run = " ".join(failure_words[start:start + 8])
            if run and run in normalized:
                return failure, ratio
    return None


def _sentences(read: Any) -> list[tuple[str, SupportedSentence]]:
    return [("headline", read.headline), *[(f"analysis[{index}]", sentence) for index, sentence in enumerate(read.analysis)]]


def assess_read_quality(read: Any, *, scope: str) -> EditorialScore:
    historical, abstract_phrases, mechanical_phrases = _failed_prose()
    issues: list[EditorialIssue] = []
    sentence_lengths: list[int] = []
    negative_frames = 0
    openings: list[str] = []

    for field, sentence in _sentences(read):
        text = str(sentence.text or "").strip()
        words = _words(text)
        sentence_lengths.append(len(words))
        match = _historical_match(text, historical)
        if match:
            issues.append(EditorialIssue(f"{scope}.{field}", "historical_failure_reuse", f"Sentence reproduces or closely paraphrases a recorded production failure ({match[1]:.2f} similarity).", 35, text))
        abstract_hits = [phrase for phrase in abstract_phrases if phrase in text.casefold()]
        if abstract_hits:
            issues.append(EditorialIssue(f"{scope}.{field}", "abstract_phrase", "Sentence uses abstract language previously shown to obscure the mechanism: " + ", ".join(abstract_hits), 8 * len(abstract_hits), text))
        mechanical_hits = [phrase for phrase in mechanical_phrases if phrase in text.casefold()]
        if mechanical_hits:
            issues.append(EditorialIssue(f"{scope}.{field}", "mechanical_distinction", "Sentence substitutes a mechanical negation for an explained transition: " + ", ".join(mechanical_hits), 10 * len(mechanical_hits), text))
        connectors = len(_CONNECTOR_RE.findall(text))
        if connectors > MAX_CONNECTORS:
            issues.append(EditorialIssue(f"{scope}.{field}", "clause_load", f"Sentence carries {connectors} connective clauses; maximum is {MAX_CONNECTORS}.", 8 + 4 * (connectors - MAX_CONNECTORS), text))
        if len(words) > MAX_SENTENCE_WORDS:
            issues.append(EditorialIssue(f"{scope}.{field}", "spoken_length", f"Sentence has {len(words)} words; spoken-prose ceiling is {MAX_SENTENCE_WORDS}.", 2 * (len(words) - MAX_SENTENCE_WORDS), text))
        nominalizations = _NOMINALIZATION_RE.findall(text)
        if len(nominalizations) >= 3:
            penalty = 30 if len(nominalizations) >= 4 else 16
            issues.append(EditorialIssue(f"{scope}.{field}", "abstract_noun_stack", "Sentence stacks abstract nouns instead of carrying the relationship through concrete verbs: " + ", ".join(nominalizations), penalty, text))
        temporal_load = len(_TEMPORAL_LOAD_RE.findall(text))
        if _CONTRAST_RE.search(text) and temporal_load >= 2 and len(words) >= 18:
            issues.append(EditorialIssue(f"{scope}.{field}", "overloaded_time_contrast", "A long contrast sentence compresses present capacity and future burden instead of giving each stage a clear sentence.", 22, text))
        negative_frames += len(_NEGATIVE_FRAME_RE.findall(text))
        opening = _OPENING_RE.search(text)
        if opening:
            openings.append(opening.group(1).casefold())

    analysis_lengths = sentence_lengths[1:]
    if len(analysis_lengths) >= 3 and max(analysis_lengths) - min(analysis_lengths) < MIN_CADENCE_SPREAD:
        issues.append(EditorialIssue(scope, "flat_cadence", "Analysis sentences have nearly identical length and produce mechanical cadence.", 12))
    if negative_frames > 1:
        issues.append(EditorialIssue(scope, "negative_frame_repetition", f"Read relies on {negative_frames} negative frames instead of explaining transitions directly.", 8 * (negative_frames - 1)))
    if len(openings) != len(set(openings)):
        issues.append(EditorialIssue(scope, "repeated_opening", "Read repeats a sentence opening and sounds templated.", 8))
    if len(analysis_lengths) >= 3 and pstdev(analysis_lengths) < 2:
        issues.append(EditorialIssue(scope, "low_rhythm_variation", "Sentence-length variation is too low for natural spoken rhythm.", 6))

    score = max(0, 100 - sum(issue.penalty for issue in issues))
    return EditorialScore(score, score >= MIN_READ_SCORE and not any(issue.penalty >= 30 for issue in issues), tuple(issues), tuple(sentence_lengths))


def compare_read_quality(draft: Any, final: Any, *, scope: str) -> ComparativeEditorialResult:
    draft_score = assess_read_quality(draft, scope=f"{scope}.draft")
    final_score = assess_read_quality(final, scope=f"{scope}.final")
    required = MIN_FAILED_DRAFT_IMPROVEMENT if not draft_score.passed else 0
    actual = final_score.score - draft_score.score
    failures: list[str] = []
    if not final_score.passed:
        failures.append(f"Final editorial score {final_score.score} is below the publication floor {MIN_READ_SCORE} or retains a hard failure.")
    if actual < required:
        failures.append(f"Revision improved by {actual} points; at least {required} points were required.")
    return ComparativeEditorialResult(not failures, draft_score.score, final_score.score, required, actual, draft_score, final_score, tuple(failures))


def compare_domain_read_sets(draft: GeneratedDomainReadSet, final: GeneratedDomainReadSet) -> dict[str, Any]:
    drafts = {read.domain: read for read in draft.reads}
    finals = {read.domain: read for read in final.reads}
    results = {
        domain: compare_read_quality(drafts[domain], finals[domain], scope=domain)
        for domain in drafts.keys() & finals.keys()
    }
    missing = sorted(set(drafts) ^ set(finals))
    passed = not missing and len(results) == len(drafts) and all(result.passed for result in results.values())
    return {
        "passed": passed,
        "missing_domains": missing,
        "domains": {domain: result.to_dict() for domain, result in sorted(results.items())},
        "version": EDITORIAL_QUALITY_VERSION,
    }


def compare_macro_reads(draft: GeneratedMacroRead, final: GeneratedMacroRead) -> dict[str, Any]:
    result = compare_read_quality(draft, final, scope="macro")
    return {"passed": result.passed, "macro": result.to_dict(), "version": EDITORIAL_QUALITY_VERSION}
