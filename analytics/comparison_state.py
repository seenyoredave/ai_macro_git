"""Global point-in-time comparison selection for canonical analytical snapshots.

This module is intentionally independent of Streamlit.  It resolves one head
publication and one optional baseline publication so every future rendering
surface can consume the same comparison state instead of implementing its own
snapshot-selection rules.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

import pandas as pd

from config.deployment import PROJECT_ROOT


COMPARISON_STATE_VERSION = "1.0.0"
DEFAULT_LOOKBACK_DAYS = 7


class ComparisonMode(StrEnum):
    CURRENT_ONLY = "current_only"
    PREVIOUS_PUBLICATION = "previous_publication"
    LOOKBACK_DAYS = "lookback_days"
    AS_OF = "as_of"
    SNAPSHOT = "snapshot"


@dataclass(frozen=True, slots=True)
class ComparisonRequest:
    """Declarative selection request used to resolve global comparison state."""

    head_snapshot_id: str = ""
    head_as_of: Any = None
    mode: ComparisonMode | str = ComparisonMode.PREVIOUS_PUBLICATION
    baseline_snapshot_id: str = ""
    baseline_as_of: Any = None
    lookback_days: int = DEFAULT_LOOKBACK_DAYS


@dataclass(frozen=True, slots=True)
class SnapshotRef:
    snapshot_id: str
    schema_version: str
    evidence_snapshot_id: str
    observation_date: str
    created_at_utc: str
    run_id: str
    publication_source: str
    context_snapshot_id: str
    metric_count: int
    domain_count: int
    state_hash: str
    sequence: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ComparisonState:
    version: str
    mode: str
    status: str
    head: SnapshotRef | None
    baseline: SnapshotRef | None
    requested_head_as_of: str
    requested_baseline_as_of: str
    requested_lookback_days: int
    comparison_available: bool
    same_snapshot: bool
    fallback_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "mode": self.mode,
            "status": self.status,
            "head": self.head.to_dict() if self.head is not None else None,
            "baseline": self.baseline.to_dict() if self.baseline is not None else None,
            "requested_head_as_of": self.requested_head_as_of,
            "requested_baseline_as_of": self.requested_baseline_as_of,
            "requested_lookback_days": self.requested_lookback_days,
            "comparison_available": self.comparison_available,
            "same_snapshot": self.same_snapshot,
            "fallback_codes": list(self.fallback_codes),
        }


def _mode(value: ComparisonMode | str) -> ComparisonMode:
    try:
        return ComparisonMode(str(value))
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ComparisonMode)
        raise ValueError(f"Unknown comparison mode {value!r}; expected one of {allowed}.") from exc


def _date_text(value: Any) -> str:
    if value is None or str(value).strip() == "":
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    parsed = pd.to_datetime(value, errors="coerce", format="mixed")
    if pd.isna(parsed):
        raise ValueError(f"Invalid comparison date: {value!r}")
    return parsed.date().isoformat()


def _history_frame(
    *,
    root: Path,
    snapshot_history: pd.DataFrame | None,
) -> pd.DataFrame:
    if snapshot_history is None:
        from analytics.canonical_store import canonical_snapshot_history

        history = canonical_snapshot_history(root=root, ascending=True)
    else:
        history = snapshot_history.copy()
    if history is None or history.empty:
        return pd.DataFrame()
    required = {"snapshot_id", "observation_date", "created_at_utc"}
    missing = required - set(history.columns)
    if missing:
        raise ValueError(f"Comparison snapshot history is missing columns: {sorted(missing)}")
    ordered = history.copy()
    ordered["snapshot_id"] = ordered["snapshot_id"].astype(str)
    ordered["observation_date"] = ordered["observation_date"].astype(str)
    ordered["created_at_utc"] = ordered["created_at_utc"].astype(str)
    ordered = ordered.sort_values(
        ["observation_date", "created_at_utc", "snapshot_id"],
        kind="stable",
    ).reset_index(drop=True)
    ordered["_sequence"] = range(len(ordered))
    return ordered


def _int_value(value: Any) -> int:
    numeric = pd.to_numeric(value, errors="coerce")
    return int(numeric) if pd.notna(numeric) else 0


def _snapshot_ref(row: pd.Series) -> SnapshotRef:
    return SnapshotRef(
        snapshot_id=str(row.get("snapshot_id") or ""),
        schema_version=str(row.get("schema_version") or ""),
        evidence_snapshot_id=str(row.get("evidence_snapshot_id") or ""),
        observation_date=str(row.get("observation_date") or ""),
        created_at_utc=str(row.get("created_at_utc") or ""),
        run_id=str(row.get("run_id") or ""),
        publication_source=str(row.get("publication_source") or ""),
        context_snapshot_id=str(row.get("context_snapshot_id") or ""),
        metric_count=_int_value(row.get("metric_count")),
        domain_count=_int_value(row.get("domain_count")),
        state_hash=str(row.get("state_hash") or ""),
        sequence=int(row.get("_sequence", 0)),
    )


def _row_by_snapshot(history: pd.DataFrame, snapshot_id: str) -> pd.Series | None:
    chosen = str(snapshot_id or "").strip()
    if not chosen:
        return None
    matches = history.loc[history["snapshot_id"].eq(chosen)]
    if matches.empty:
        return None
    if len(matches) > 1:
        raise ValueError(f"Canonical snapshot {chosen} appears more than once in comparison history.")
    return matches.iloc[0]


def _row_as_of(history: pd.DataFrame, target: str, *, max_sequence: int | None = None) -> pd.Series | None:
    eligible = history.loc[history["observation_date"].le(target)]
    if max_sequence is not None:
        eligible = eligible.loc[eligible["_sequence"].le(int(max_sequence))]
    if eligible.empty:
        return None
    return eligible.iloc[-1]


def resolve_comparison_state(
    request: ComparisonRequest | None = None,
    *,
    root: Path = PROJECT_ROOT,
    snapshot_history: pd.DataFrame | None = None,
) -> ComparisonState:
    """Resolve a stable head/baseline pair without making any provider calls.

    ``snapshot_history`` is injectable for deterministic tests. Production calls
    omit it and read only retained canonical snapshot metadata.
    """

    selection = request or ComparisonRequest()
    mode = _mode(selection.mode)
    requested_head_as_of = _date_text(selection.head_as_of)
    requested_baseline_as_of = _date_text(selection.baseline_as_of)
    lookback_days = max(1, int(selection.lookback_days or DEFAULT_LOOKBACK_DAYS))
    fallbacks: list[str] = []

    history = _history_frame(root=root, snapshot_history=snapshot_history)
    if history.empty:
        return ComparisonState(
            version=COMPARISON_STATE_VERSION,
            mode=mode.value,
            status="unavailable",
            head=None,
            baseline=None,
            requested_head_as_of=requested_head_as_of,
            requested_baseline_as_of=requested_baseline_as_of,
            requested_lookback_days=lookback_days,
            comparison_available=False,
            same_snapshot=False,
            fallback_codes=("canonical_history_unavailable",),
        )

    head_row: pd.Series | None = None
    if str(selection.head_snapshot_id or "").strip():
        head_row = _row_by_snapshot(history, selection.head_snapshot_id)
        if head_row is None:
            fallbacks.append("head_snapshot_not_found_latest_used")
            head_row = history.iloc[-1]
    elif requested_head_as_of:
        head_row = _row_as_of(history, requested_head_as_of)
        if head_row is None:
            return ComparisonState(
                version=COMPARISON_STATE_VERSION,
                mode=mode.value,
                status="unavailable",
                head=None,
                baseline=None,
                requested_head_as_of=requested_head_as_of,
                requested_baseline_as_of=requested_baseline_as_of,
                requested_lookback_days=lookback_days,
                comparison_available=False,
                same_snapshot=False,
                fallback_codes=("head_as_of_precedes_canonical_history",),
            )
    else:
        head_row = history.iloc[-1]

    head = _snapshot_ref(head_row)
    if mode == ComparisonMode.CURRENT_ONLY:
        return ComparisonState(
            version=COMPARISON_STATE_VERSION,
            mode=mode.value,
            status="current_only",
            head=head,
            baseline=None,
            requested_head_as_of=requested_head_as_of,
            requested_baseline_as_of=requested_baseline_as_of,
            requested_lookback_days=lookback_days,
            comparison_available=False,
            same_snapshot=False,
            fallback_codes=tuple(fallbacks),
        )

    base_row: pd.Series | None = None
    if mode == ComparisonMode.PREVIOUS_PUBLICATION:
        prior = history.loc[history["_sequence"].lt(head.sequence)]
        if not prior.empty:
            base_row = prior.iloc[-1]
        else:
            fallbacks.append("previous_publication_unavailable")
    elif mode == ComparisonMode.LOOKBACK_DAYS:
        target = (date.fromisoformat(head.observation_date) - timedelta(days=lookback_days)).isoformat()
        requested_baseline_as_of = target
        base_row = _row_as_of(history, target, max_sequence=head.sequence)
        if base_row is None:
            fallbacks.append("lookback_precedes_canonical_history")
    elif mode == ComparisonMode.AS_OF:
        if not requested_baseline_as_of:
            fallbacks.append("baseline_as_of_not_provided")
        else:
            base_row = _row_as_of(
                history,
                requested_baseline_as_of,
                max_sequence=head.sequence,
            )
            if base_row is None:
                fallbacks.append("baseline_as_of_precedes_canonical_history")
    elif mode == ComparisonMode.SNAPSHOT:
        if not str(selection.baseline_snapshot_id or "").strip():
            fallbacks.append("baseline_snapshot_not_provided")
        else:
            candidate = _row_by_snapshot(history, selection.baseline_snapshot_id)
            if candidate is None:
                fallbacks.append("baseline_snapshot_not_found")
            elif int(candidate["_sequence"]) > head.sequence:
                fallbacks.append("baseline_snapshot_newer_than_head")
            else:
                base_row = candidate

    baseline = _snapshot_ref(base_row) if base_row is not None else None
    same_snapshot = bool(baseline and baseline.snapshot_id == head.snapshot_id)
    comparison_available = baseline is not None
    status = "ready" if comparison_available else "baseline_unavailable"
    return ComparisonState(
        version=COMPARISON_STATE_VERSION,
        mode=mode.value,
        status=status,
        head=head,
        baseline=baseline,
        requested_head_as_of=requested_head_as_of,
        requested_baseline_as_of=requested_baseline_as_of,
        requested_lookback_days=lookback_days,
        comparison_available=comparison_available,
        same_snapshot=same_snapshot,
        fallback_codes=tuple(fallbacks),
    )


__all__ = [
    "COMPARISON_STATE_VERSION",
    "DEFAULT_LOOKBACK_DAYS",
    "ComparisonMode",
    "ComparisonRequest",
    "ComparisonState",
    "SnapshotRef",
    "resolve_comparison_state",
]
