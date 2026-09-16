"""Conservative one-time migration of retained legacy analytical history.

Older AI Macro releases persisted a complete cross-domain metric payload inside
``archive/macro_history.csv`` under ``Macro Snapshot Context``.  Canonical
Parquet snapshots did not exist yet.  This module imports only those legacy rows
that contain a complete deterministic domain-state payload; ordinary macro rows
are never promoted into canonical history.

The migration is intentionally owner-invoked.  Application startup, public
Reader sessions, and scheduled automation do not call it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


BOOTSTRAP_VERSION = "1.0.0"
LEGACY_ARCHIVE_RELATIVE = Path("archive") / "macro_history.csv"
LEGACY_CONTEXT_COLUMN = "Macro Snapshot Context"
LEGACY_PUBLICATION_SOURCE = "legacy_macro_snapshot_context"
LEGACY_DOMAIN_ALIASES = {"adaptation": "adoption"}


@dataclass(frozen=True, slots=True)
class LegacyCanonicalCandidate:
    observation_date: str
    row_number: int
    state_hash: str
    domain_metrics: dict[str, dict[str, Any]]

    def to_dict(self, *, include_metrics: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "observation_date": self.observation_date,
            "row_number": self.row_number,
            "state_hash": self.state_hash,
            "domains": sorted(self.domain_metrics),
        }
        if include_metrics:
            payload["domain_metrics"] = self.domain_metrics
        return payload


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _domain_order(domain_order: Iterable[str] | None = None) -> tuple[str, ...]:
    if domain_order is not None:
        return tuple(str(domain) for domain in domain_order)
    from analytics.domain_state import DOMAIN_ORDER

    return tuple(DOMAIN_ORDER)


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _date_text(value: Any) -> str:
    parsed = pd.to_datetime(value, errors="coerce", format="mixed")
    if pd.isna(parsed):
        raise ValueError(f"Invalid legacy observation date: {value!r}")
    return parsed.date().isoformat()


def _clean_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, (np.floating, float)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if isinstance(value, dict):
        return {str(key): _clean_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean_value(item) for item in value]
    return value


def _usable_metric_payload(metrics: dict[str, Any]) -> bool:
    if not metrics:
        return False
    for value in metrics.values():
        cleaned = _clean_value(value)
        if cleaned is None:
            continue
        if isinstance(cleaned, str) and not cleaned.strip():
            continue
        if isinstance(cleaned, (dict, list)) and not cleaned:
            continue
        return True
    return False


def _state_hash(domain_metrics: dict[str, dict[str, Any]]) -> str:
    raw = json.dumps(
        domain_metrics,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def _parse_legacy_context(
    raw: Any,
    *,
    domain_order: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    text = _text(raw)
    if not text:
        raise ValueError("legacy snapshot context is blank")
    try:
        payload = json.loads(text, parse_constant=lambda _value: None)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"legacy snapshot context is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("legacy snapshot context is not an object")

    normalized: dict[str, dict[str, Any]] = {}
    for raw_domain, raw_metrics in payload.items():
        domain = LEGACY_DOMAIN_ALIASES.get(str(raw_domain), str(raw_domain))
        if domain in normalized:
            raise ValueError(f"legacy snapshot context has duplicate domain after aliasing: {domain}")
        if not isinstance(raw_metrics, dict):
            raise ValueError(f"legacy domain {raw_domain!r} is not a metric object")
        metrics = {
            str(key): _clean_value(value)
            for key, value in raw_metrics.items()
        }
        if not _usable_metric_payload(metrics):
            raise ValueError(f"legacy domain {raw_domain!r} has no usable metrics")
        normalized[domain] = metrics

    expected = set(domain_order)
    actual = set(normalized)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing or unknown:
        detail = []
        if missing:
            detail.append(f"missing={missing}")
        if unknown:
            detail.append(f"unknown={unknown}")
        raise ValueError("legacy snapshot context is not a complete current domain set; " + ", ".join(detail))
    return {domain: normalized[domain] for domain in domain_order}


def discover_legacy_snapshot_candidates(
    *,
    root: Path | None = None,
    archive_path: Path | None = None,
    domain_order: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Find complete legacy cross-domain states without writing anything."""
    project_root = Path(root or _project_root())
    path = Path(archive_path) if archive_path is not None else project_root / LEGACY_ARCHIVE_RELATIVE
    order = _domain_order(domain_order)
    if not path.exists():
        return {
            "status": "archive_unavailable",
            "archive_path": str(path),
            "legacy_rows": 0,
            "context_rows": 0,
            "candidates": [],
            "invalid": [{"reason": "legacy_macro_history_unavailable"}],
        }

    frame = pd.read_csv(path, low_memory=False)
    required = {"Date", LEGACY_CONTEXT_COLUMN}
    missing_columns = sorted(required - set(frame.columns))
    if missing_columns:
        return {
            "status": "archive_incompatible",
            "archive_path": str(path),
            "legacy_rows": int(len(frame)),
            "context_rows": 0,
            "candidates": [],
            "invalid": [{"reason": f"missing_columns:{','.join(missing_columns)}"}],
        }

    raw_candidates: list[LegacyCanonicalCandidate] = []
    invalid: list[dict[str, Any]] = []
    context_rows = 0
    for zero_index, row in frame.iterrows():
        raw_context = row.get(LEGACY_CONTEXT_COLUMN)
        if not _text(raw_context):
            continue
        context_rows += 1
        row_number = int(zero_index) + 2  # CSV header is line 1.
        raw_date = row.get("Date")
        try:
            observation_date = _date_text(raw_date)
            metrics = _parse_legacy_context(raw_context, domain_order=order)
        except ValueError as exc:
            invalid.append({
                "row_number": row_number,
                "observation_date": _text(raw_date),
                "reason": str(exc),
            })
            continue
        raw_candidates.append(
            LegacyCanonicalCandidate(
                observation_date=observation_date,
                row_number=row_number,
                state_hash=_state_hash(metrics),
                domain_metrics=metrics,
            )
        )

    # A date is safe to reconstruct only when its retained payload is
    # unambiguous. Exact duplicate rows collapse to one; conflicting same-date
    # payloads are rejected rather than guessed through.
    candidates: list[LegacyCanonicalCandidate] = []
    by_date: dict[str, list[LegacyCanonicalCandidate]] = {}
    for candidate in raw_candidates:
        by_date.setdefault(candidate.observation_date, []).append(candidate)
    for observation_date in sorted(by_date):
        dated = by_date[observation_date]
        hashes = {item.state_hash for item in dated}
        if len(hashes) > 1:
            invalid.append({
                "observation_date": observation_date,
                "row_numbers": [item.row_number for item in dated],
                "reason": "ambiguous_same_date_legacy_states",
            })
            continue
        candidates.append(dated[-1])

    return {
        "status": "ready" if candidates else "no_complete_candidates",
        "archive_path": str(path),
        "legacy_rows": int(len(frame)),
        "context_rows": int(context_rows),
        "candidates": candidates,
        "invalid": invalid,
    }


def _canonical_era_start(history: pd.DataFrame) -> str:
    if history is None or history.empty or "observation_date" not in history.columns:
        return ""
    sources = (
        history["publication_source"].fillna("").astype(str)
        if "publication_source" in history.columns
        else pd.Series("", index=history.index, dtype=str)
    )
    # Blank/unknown provenance is treated as native canonical state. This is
    # deliberately conservative: a legacy migration never gets to overwrite or
    # interleave with an existing publication whose origin is unclear.
    native = history.loc[~sources.eq(LEGACY_PUBLICATION_SOURCE)].copy()
    if native.empty:
        return ""
    dates = pd.to_datetime(native["observation_date"], errors="coerce", format="mixed").dropna()
    return dates.min().date().isoformat() if not dates.empty else ""


def plan_canonical_history_bootstrap(
    *,
    root: Path | None = None,
    archive_path: Path | None = None,
    domain_order: Iterable[str] | None = None,
    canonical_history: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Build an idempotent migration plan; no canonical files are written."""
    project_root = Path(root or _project_root())
    discovery = discover_legacy_snapshot_candidates(
        root=project_root,
        archive_path=archive_path,
        domain_order=domain_order,
    )
    candidates: list[LegacyCanonicalCandidate] = list(discovery.get("candidates") or [])

    if canonical_history is None:
        from analytics.canonical_store import canonical_snapshot_history

        history = canonical_snapshot_history(root=project_root, ascending=True)
    else:
        history = canonical_history.copy()
    if history is None:
        history = pd.DataFrame()

    existing_dates: set[str] = set()
    if not history.empty and "observation_date" in history.columns:
        parsed = pd.to_datetime(history["observation_date"], errors="coerce", format="mixed").dropna()
        existing_dates = {value.date().isoformat() for value in parsed}
    era_start = _canonical_era_start(history)

    eligible: list[LegacyCanonicalCandidate] = []
    skipped: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: (item.observation_date, item.row_number)):
        if candidate.observation_date in existing_dates:
            skipped.append({
                "observation_date": candidate.observation_date,
                "reason": "canonical_date_already_exists",
            })
            continue
        if era_start and candidate.observation_date >= era_start:
            skipped.append({
                "observation_date": candidate.observation_date,
                "reason": "at_or_after_native_canonical_era",
            })
            continue
        eligible.append(candidate)

    return {
        "version": BOOTSTRAP_VERSION,
        "status": "ready" if eligible else "nothing_to_write",
        "archive_path": discovery.get("archive_path", ""),
        "legacy_rows": int(discovery.get("legacy_rows") or 0),
        "context_rows": int(discovery.get("context_rows") or 0),
        "complete_candidate_count": int(len(candidates)),
        "invalid_candidate_count": int(len(discovery.get("invalid") or [])),
        "canonical_snapshot_count": int(len(history)),
        "native_canonical_era_start": era_start,
        "eligible": eligible,
        "eligible_dates": [item.observation_date for item in eligible],
        "skipped": skipped,
        "invalid": list(discovery.get("invalid") or []),
    }


def _historical_context(candidate: LegacyCanonicalCandidate):
    from analytics.dashboard_context import DashboardContext
    from analytics.domain_state import DomainState

    # Legacy snapshots retained the finished metric dictionaries but did not
    # retain the domain-importance scalar introduced later. Use neutral zero
    # rather than reconstructing a historical ranking with today's formulas.
    states = {
        domain: DomainState(metrics=dict(metrics), importance=0.0)
        for domain, metrics in candidate.domain_metrics.items()
    }
    return DashboardContext(domain_states=states)


def bootstrap_legacy_canonical_history(
    *,
    write: bool = False,
    root: Path | None = None,
    archive_path: Path | None = None,
    domain_order: Iterable[str] | None = None,
    canonical_history: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Dry-run or write the conservative legacy-to-canonical history migration."""
    project_root = Path(root or _project_root())
    plan = plan_canonical_history_bootstrap(
        root=project_root,
        archive_path=archive_path,
        domain_order=domain_order,
        canonical_history=canonical_history,
    )
    report = {
        key: value
        for key, value in plan.items()
        if key != "eligible"
    }
    report.update({
        "write_requested": bool(write),
        "written": [],
        "unchanged": [],
        "errors": [],
    })
    eligible: list[LegacyCanonicalCandidate] = list(plan.get("eligible") or [])
    if not write:
        report["status"] = "dry_run"
        return report
    if not eligible:
        report["status"] = "nothing_to_write"
        return report

    from config.deployment import developer_mode, repository_writes_enabled

    if not developer_mode() or not repository_writes_enabled():
        raise PermissionError(
            "Canonical history bootstrap writes require AI_MACRO_MODE=developer."
        )

    from analytics.canonical_store import persist_canonical_snapshot

    for candidate in eligible:
        try:
            _context, item = persist_canonical_snapshot(
                _historical_context(candidate),
                observation_date=candidate.observation_date,
                run_id=f"history-bootstrap-{candidate.observation_date.replace('-', '')}",
                publication_source=LEGACY_PUBLICATION_SOURCE,
                source_status={
                    "history_bootstrap": {
                        "status": "historical_reconstruction",
                        "source_mode": "retained_legacy_snapshot_context",
                        "source_file": LEGACY_ARCHIVE_RELATIVE.as_posix(),
                        "legacy_row_number": candidate.row_number,
                        "legacy_state_hash": candidate.state_hash,
                        "domain_importance": "not_retained_in_legacy_snapshot",
                    }
                },
                root=project_root,
            )
            destination = report["unchanged"] if item.get("status") == "unchanged" else report["written"]
            destination.append({
                "observation_date": candidate.observation_date,
                "snapshot_id": str(item.get("snapshot_id") or ""),
                "status": str(item.get("status") or ""),
            })
        except Exception as exc:
            report["errors"].append({
                "observation_date": candidate.observation_date,
                "error": f"{type(exc).__name__}: {exc}",
            })

    report["written_count"] = len(report["written"])
    report["unchanged_count"] = len(report["unchanged"])
    report["error_count"] = len(report["errors"])
    report["status"] = (
        "written"
        if report["written"] and not report["errors"]
        else "partial"
        if report["written"] or report["unchanged"]
        else "failed"
    )
    return report


__all__ = [
    "BOOTSTRAP_VERSION",
    "LEGACY_ARCHIVE_RELATIVE",
    "LEGACY_CONTEXT_COLUMN",
    "LEGACY_DOMAIN_ALIASES",
    "LEGACY_PUBLICATION_SOURCE",
    "LegacyCanonicalCandidate",
    "bootstrap_legacy_canonical_history",
    "discover_legacy_snapshot_candidates",
    "plan_canonical_history_bootstrap",
]
