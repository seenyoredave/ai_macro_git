"""Optional editorial diagnostics for generated Reader prose.

These checks are observational only.  They are intentionally separate from the
hard publication gate so a stylistic preference cannot block grounded prose.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable

from analytics.read_models import GeneratedDomainRead, GeneratedMacroRead, SupportedPassage

EDITORIAL_QUALITY_VERSION = "2.0.0"

_IGNORED_ALLITERATION_WORDS = {
    "a", "an", "the", "and", "or", "but", "nor", "for", "so", "yet",
    "as", "at", "by", "in", "of", "on", "per", "to", "up", "via", "with",
}


@dataclass(frozen=True, slots=True)
class EditorialIssue:
    scope: str
    reason: str
    message: str
    text: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "scope": self.scope,
            "reason": self.reason,
            "message": self.message,
            "text": self.text,
        }


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+[\w'’-]*\b", str(text or "")))


def _alliterative_run(text: str, *, minimum: int = 4) -> list[str]:
    run: list[str] = []
    initial = ""
    for word in re.findall(r"[A-Za-z]+(?:['’][A-Za-z]+)?", str(text or "")):
        if word.casefold() in _IGNORED_ALLITERATION_WORDS:
            continue
        current = word[0].casefold()
        if current == initial:
            run.append(word)
        else:
            initial = current
            run = [word]
        if len(run) >= minimum:
            return run
    return []


def diagnose_passage(passage: SupportedPassage, *, scope: str) -> list[EditorialIssue]:
    text = str(passage.text or "").strip()
    issues: list[EditorialIssue] = []
    run = _alliterative_run(text)
    if run:
        issues.append(EditorialIssue(
            scope,
            "alliterative_run",
            "Conspicuous same-initial word run detected: " + " ".join(run),
            text,
        ))
    if ";" in text:
        issues.append(EditorialIssue(scope, "semicolon", "Semicolon present; review for clause stacking.", text))
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        words = _word_count(sentence)
        if words > 60:
            issues.append(EditorialIssue(scope, "long_sentence", f"Sentence contains {words} words.", sentence))
            break
    return issues


def diagnose_domain_read(read: GeneratedDomainRead) -> list[EditorialIssue]:
    return [
        *diagnose_passage(read.headline, scope=f"{read.domain}.headline"),
        *diagnose_passage(read.body, scope=f"{read.domain}.body"),
    ]


def diagnose_macro_read(read: GeneratedMacroRead) -> list[EditorialIssue]:
    issues = diagnose_passage(read.headline, scope="macro.headline")
    for index, paragraph in enumerate(read.paragraphs):
        issues.extend(diagnose_passage(paragraph, scope=f"macro.paragraphs[{index}]"))
    return issues


def diagnostics_payload(
    domain_reads: Iterable[GeneratedDomainRead],
    macro_read: GeneratedMacroRead,
) -> dict[str, Any]:
    issues = [issue for read in domain_reads for issue in diagnose_domain_read(read)]
    issues.extend(diagnose_macro_read(macro_read))
    return {
        "version": EDITORIAL_QUALITY_VERSION,
        "issue_count": len(issues),
        "issues": [issue.to_dict() for issue in issues],
        "publication_blocking": False,
    }


__all__ = [
    "EDITORIAL_QUALITY_VERSION",
    "EditorialIssue",
    "diagnose_domain_read",
    "diagnose_macro_read",
    "diagnose_passage",
    "diagnostics_payload",
]
