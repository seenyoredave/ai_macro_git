"""Validate and score the local AI Macro editorial evaluation suite.

This harness never calls OpenAI. Candidate responses and human scores are
supplied explicitly so evaluation spending remains a separate owner decision.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import statistics
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUITE = ROOT / "evaluation" / "editorial_eval_cases_v1.0.json"
DIMENSIONS = (
    "factual_fidelity",
    "coherence",
    "relevance",
    "readability",
    "material_usefulness",
)


def load_suite(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError("Editorial evaluation suite must contain a cases array.")
    return payload


def validate_suite(payload: dict[str, Any]) -> dict[str, Any]:
    cases = payload["cases"]
    ids = [str(case.get("case_id") or "") for case in cases if isinstance(case, dict)]
    errors: list[str] = []
    if len(cases) != 25:
        errors.append(f"expected 25 cases, found {len(cases)}")
    duplicates = [case_id for case_id, count in Counter(ids).items() if count > 1]
    if duplicates:
        errors.append("duplicate case IDs: " + ", ".join(duplicates))
    pairs: dict[str, list[str]] = defaultdict(list)
    for case in cases:
        if not isinstance(case, dict):
            errors.append("case is not an object")
            continue
        for field in ("case_id", "category", "expected_decision", "setup", "signals", "must_address", "must_not_claim"):
            if not case.get(field):
                errors.append(f"{case.get('case_id', '<unknown>')} lacks {field}")
        if case.get("expected_decision") not in {"publish", "retain_prior"}:
            errors.append(f"{case.get('case_id')} has invalid expected_decision")
        if case.get("pair_id"):
            pairs[str(case["pair_id"])].append(str(case.get("case_id") or ""))
    malformed_pairs = {pair: members for pair, members in pairs.items() if len(members) != 2}
    if malformed_pairs:
        errors.append(f"paired cases must have exactly two members: {malformed_pairs}")
    return {
        "passed": not errors,
        "suite_version": payload.get("suite_version"),
        "case_count": len(cases),
        "paired_case_sets": len(pairs),
        "decision_counts": dict(Counter(str(case.get("expected_decision")) for case in cases)),
        "category_counts": dict(Counter(str(case.get("category")) for case in cases)),
        "errors": errors,
    }


def blank_scorecard(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "suite_version": payload.get("suite_version"),
        "instructions": "Blind candidate identity before scoring. Use integer scores from 1 to 5.",
        "responses": [
            {
                "case_id": case["case_id"],
                "candidate": "",
                "decision": "",
                "scores": {dimension: None for dimension in DIMENSIONS},
                "publish_without_edit": None,
                "unsupported_numeric_claims": None,
                "paired_distinction_correct": None if not case.get("pair_id") else False,
                "notes": "",
            }
            for case in payload["cases"]
        ],
    }


def score_responses(payload: dict[str, Any], scorecard: dict[str, Any]) -> dict[str, Any]:
    cases = {str(case["case_id"]): case for case in payload["cases"]}
    rows = [row for row in (scorecard.get("responses") or []) if isinstance(row, dict)]
    errors: list[str] = []
    dimension_values: dict[str, list[float]] = {dimension: [] for dimension in DIMENSIONS}
    publishable: list[bool] = []
    unsupported = 0
    decision_correct = 0
    paired: list[bool] = []
    for row in rows:
        case_id = str(row.get("case_id") or "")
        case = cases.get(case_id)
        if case is None:
            errors.append(f"unknown case_id: {case_id}")
            continue
        decision_correct += int(str(row.get("decision") or "") == str(case.get("expected_decision") or ""))
        scores = dict(row.get("scores") or {})
        for dimension in DIMENSIONS:
            value = scores.get(dimension)
            if not isinstance(value, (int, float)) or not 1 <= float(value) <= 5:
                errors.append(f"{case_id} has invalid {dimension} score")
                continue
            dimension_values[dimension].append(float(value))
        if isinstance(row.get("publish_without_edit"), bool):
            publishable.append(bool(row["publish_without_edit"]))
        else:
            errors.append(f"{case_id} lacks publish_without_edit")
        try:
            unsupported += int(row.get("unsupported_numeric_claims"))
        except (TypeError, ValueError):
            errors.append(f"{case_id} lacks unsupported_numeric_claims")
        if case.get("pair_id"):
            paired.append(bool(row.get("paired_distinction_correct")))
    medians = {
        dimension: statistics.median(values) if values else 0.0
        for dimension, values in dimension_values.items()
    }
    completed = len(rows)
    return {
        "passed": bool(
            not errors
            and completed == len(cases)
            and unsupported == 0
            and all(value >= 4 for value in medians.values())
            and (sum(publishable) / len(publishable) if publishable else 0) >= 0.8
            and (sum(paired) / len(paired) if paired else 0) >= 0.9
        ),
        "completed_cases": completed,
        "decision_accuracy": decision_correct / completed if completed else 0.0,
        "median_scores": medians,
        "publish_without_edit_rate": sum(publishable) / len(publishable) if publishable else 0.0,
        "paired_distinction_rate": sum(paired) / len(paired) if paired else 0.0,
        "unsupported_numeric_claims": unsupported,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--write-scorecard", type=Path)
    parser.add_argument("--score", type=Path)
    args = parser.parse_args()
    suite = load_suite(args.suite)
    report = validate_suite(suite)
    if args.write_scorecard:
        args.write_scorecard.write_text(
            json.dumps(blank_scorecard(suite), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        report["scorecard_path"] = str(args.write_scorecard)
    if args.score:
        report["score"] = score_responses(
            suite,
            json.loads(args.score.read_text(encoding="utf-8")),
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("passed") and (not args.score or report["score"].get("passed")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
