"""Dependency-aware planning for unattended research refreshes.

The graph controls *when* upstream providers are contacted. Retained loaders
remain the continuity layer: a node that is not due still loads its published
state, so downstream deterministic analytics always receive a complete context.

Node state is durable publication state. A successful run records the latest
provider attempt, semantic output signature, and release trigger. Failed live
attempts keep the prior success boundary and become eligible for a short retry
window rather than suppressing the source until its normal cadence elapses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from config.deployment import PROJECT_ROOT
from helpers.atomic_io import atomic_write_json

REFRESH_GRAPH_VERSION = "1.0.0"
REFRESH_GRAPH_STATE_PATH = PROJECT_ROOT / "data" / "refresh_graph_state.json"
_VOLATILE_SIGNATURE_KEYS = {
    "elapsed_sec", "retrieved_at", "retrieved_at_utc", "load_report", "refresh_report",
    "source_mode", "error", "errors", "decision", "requested", "authorized", "executed",
    "refresh_token", "clock_token",
}


@dataclass(frozen=True, slots=True)
class RefreshNodeSpec:
    node_id: str
    interval_hours: float
    dependencies: tuple[str, ...] = ()
    retry_hours: float = 6.0
    description: str = ""


# High-velocity feeds remain daily. Slower structural sources are refreshed on
# multi-day cadences, while release-aware sources also carry explicit trigger
# tokens supplied by research_refresh (for example completed Energy week or the
# latest NY Fed monthly release). A dependency change may force a node earlier.
NODE_SPECS: tuple[RefreshNodeSpec, ...] = (
    RefreshNodeSpec("yfinance", 18.0, description="Public-equity market state"),
    RefreshNodeSpec("edgar", 18.0, description="SEC company facts"),
    RefreshNodeSpec("fred", 18.0, description="Shared FRED macro and power series"),
    RefreshNodeSpec("current_context", 18.0, description="Source-grounded current developments"),
    RefreshNodeSpec("power_supply", 192.0, description="Weekly/monthly Energy supply and prices"),
    RefreshNodeSpec("nyfed", 840.0, description="Monthly NY Fed debt-market release"),
    RefreshNodeSpec("construction", 42.0, description="Census construction history"),
    RefreshNodeSpec("compute", 42.0, description="Compute manufacturing evidence"),
    RefreshNodeSpec("data_centers", 42.0, description="Universal data-center registry inputs"),
    RefreshNodeSpec("grid_storage", 42.0, description="Grid and storage market evidence"),
    RefreshNodeSpec("water", 42.0, dependencies=("data_centers",), description="Water and drought evidence"),
    RefreshNodeSpec("adoption", 42.0, description="Business and consumer adoption evidence"),
    RefreshNodeSpec("workforce", 42.0, description="Labor-market evidence"),
    RefreshNodeSpec("economic_outcomes", 42.0, description="Productivity and economic-outcome evidence"),
    RefreshNodeSpec("commercialization", 120.0, description="Primary company commercialization disclosures"),
    RefreshNodeSpec(
        "connectivity",
        120.0,
        dependencies=("data_centers",),
        description="Connectivity evidence joined to the data-center registry",
    ),
)

NODE_INDEX = {spec.node_id: spec for spec in NODE_SPECS}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat()


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _truthy_env(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().casefold() in {
        "1", "true", "yes", "on", "full", "force",
    }


def force_full_refresh_requested() -> bool:
    return _truthy_env("AI_MACRO_FORCE_FULL_REFRESH")


def load_refresh_graph_state(path: Path = REFRESH_GRAPH_STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {
            "graph_version": REFRESH_GRAPH_VERSION,
            "updated_at_utc": "",
            "nodes": {},
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict) or payload.get("graph_version") != REFRESH_GRAPH_VERSION:
        return {
            "graph_version": REFRESH_GRAPH_VERSION,
            "updated_at_utc": "",
            "nodes": {},
        }
    payload.setdefault("nodes", {})
    return payload


def save_refresh_graph_state(
    state: dict[str, Any],
    *,
    path: Path = REFRESH_GRAPH_STATE_PATH,
    now: datetime | None = None,
) -> dict[str, Any]:
    payload = dict(state or {})
    payload["graph_version"] = REFRESH_GRAPH_VERSION
    payload["updated_at_utc"] = _iso(now or _utc_now())
    payload.setdefault("nodes", {})
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(payload, path)
    return payload


def _json_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item") and callable(value.item):
        try:
            return _json_scalar(value.item())
        except (TypeError, ValueError):
            pass
    if isinstance(value, str):
        return value
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def _normalize_frame(frame: pd.DataFrame) -> dict[str, Any]:
    """Return a deterministic, compact frame fingerprint payload."""
    if frame is None or frame.empty:
        return {"columns": [str(column) for column in getattr(frame, "columns", [])], "rows": 0, "hash": ""}
    normalized = frame.copy()
    normalized.columns = [str(column) for column in normalized.columns]
    for column in normalized.columns:
        series = normalized[column]
        if pd.api.types.is_datetime64_any_dtype(series):
            normalized[column] = pd.to_datetime(series, errors="coerce").astype("string")
        elif pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
            normalized[column] = series.map(
                lambda item: json.dumps(
                    _stable_payload(item), sort_keys=True, separators=(",", ":"), ensure_ascii=True
                )
            )
    try:
        row_hashes = pd.util.hash_pandas_object(normalized, index=False, categorize=False).to_numpy(dtype="uint64")
        digest = hashlib.sha256(row_hashes.tobytes()).hexdigest()
    except Exception:
        encoded = normalized.to_json(orient="split", date_format="iso", default_handler=str).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
    return {
        "columns": list(normalized.columns),
        "rows": int(len(normalized)),
        "hash": digest,
    }


def _stable_payload(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return _normalize_frame(value)
    if isinstance(value, pd.Series):
        return _normalize_frame(value.to_frame(name=str(value.name or "value")))
    if isinstance(value, dict):
        return {
            str(key): _stable_payload(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in _VOLATILE_SIGNATURE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_stable_payload(item) for item in value]
    if isinstance(value, set):
        return sorted((_stable_payload(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True, default=str))
    return _json_scalar(value)


def stable_signature(value: Any) -> str:
    payload = _stable_payload(value)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


@dataclass(slots=True)
class RefreshDecision:
    node_id: str
    refresh: bool
    reason: str
    trigger_token: str = ""


@dataclass(slots=True)
class RefreshPlan:
    state: dict[str, Any]
    now: datetime
    force_full: bool = False
    trigger_tokens: dict[str, str] = field(default_factory=dict)
    decisions: dict[str, RefreshDecision] = field(default_factory=dict)
    run_report: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.now.tzinfo is None:
            self.now = self.now.replace(tzinfo=timezone.utc)
        else:
            self.now = self.now.astimezone(timezone.utc)
        for spec in NODE_SPECS:
            self.decisions[spec.node_id] = self._initial_decision(spec)

    def _initial_decision(self, spec: RefreshNodeSpec) -> RefreshDecision:
        token = str(self.trigger_tokens.get(spec.node_id) or "")
        record = dict((self.state.get("nodes") or {}).get(spec.node_id) or {})
        if self.force_full:
            return RefreshDecision(spec.node_id, True, "forced_full_refresh", token)
        last_status = str(record.get("last_status") or "")
        last_attempt = _parse_time(record.get("last_attempt_at_utc"))
        if last_status in {"failed", "partial"} and last_attempt is not None:
            if self.now - last_attempt >= timedelta(hours=float(spec.retry_hours)):
                return RefreshDecision(spec.node_id, True, f"retry_after_{last_status}", token)
            return RefreshDecision(spec.node_id, False, f"retry_backoff_after_{last_status}", token)
        last_success = _parse_time(record.get("last_success_at_utc"))
        if last_success is None:
            return RefreshDecision(spec.node_id, True, "bootstrap", token)
        prior_token = str(record.get("last_success_trigger") or "")
        if token and token != prior_token:
            return RefreshDecision(spec.node_id, True, "release_trigger_changed", token)
        if self.now - last_success >= timedelta(hours=float(spec.interval_hours)):
            return RefreshDecision(spec.node_id, True, "cadence_elapsed", token)
        return RefreshDecision(spec.node_id, False, "retained_not_due", token)

    def should_refresh(self, node_id: str) -> bool:
        return bool(self.decisions[node_id].refresh)

    def reason(self, node_id: str) -> str:
        return str(self.decisions[node_id].reason)

    def force(self, node_id: str, *, reason: str) -> None:
        decision = self.decisions[node_id]
        if not decision.refresh:
            self.decisions[node_id] = RefreshDecision(
                node_id=node_id,
                refresh=True,
                reason=str(reason),
                trigger_token=decision.trigger_token,
            )

    def retain(self, node_id: str, *, reason: str) -> None:
        decision = self.decisions[node_id]
        self.decisions[node_id] = RefreshDecision(
            node_id=node_id,
            refresh=False,
            reason=str(reason),
            trigger_token=decision.trigger_token,
        )

    def force_dependents(self, node_id: str) -> list[str]:
        forced: list[str] = []
        for spec in NODE_SPECS:
            if node_id in spec.dependencies:
                before = self.should_refresh(spec.node_id)
                self.force(spec.node_id, reason=f"dependency_changed:{node_id}")
                if not before:
                    forced.append(spec.node_id)
        return forced

    def record(
        self,
        node_id: str,
        *,
        attempted_live: bool,
        status: str,
        output_signature: str,
        elapsed_sec: float,
        error: str = "",
    ) -> dict[str, Any]:
        if node_id not in NODE_INDEX:
            raise KeyError(f"Unknown refresh graph node: {node_id}")
        normalized_status = str(status or "retained")
        if normalized_status not in {"success", "partial", "failed", "retained"}:
            raise ValueError(f"Unsupported node status: {normalized_status}")
        nodes = self.state.setdefault("nodes", {})
        record = dict(nodes.get(node_id) or {})
        previous_signature = str(record.get("last_output_signature") or "")
        changed = bool(output_signature and previous_signature and output_signature != previous_signature)
        first_signature = bool(output_signature and not previous_signature)
        if output_signature:
            record["last_output_signature"] = output_signature
            if changed or first_signature:
                record["last_changed_at_utc"] = _iso(self.now)
        if attempted_live:
            record["last_attempt_at_utc"] = _iso(self.now)
            record["last_status"] = normalized_status
            record["last_error"] = str(error or "")
            if normalized_status == "success":
                record["last_success_at_utc"] = _iso(self.now)
                record["last_success_trigger"] = str(self.decisions[node_id].trigger_token or "")
                record["consecutive_failures"] = 0
            elif normalized_status == "partial":
                # Partial work is useful, but preserve the last complete success
                # boundary so the short retry policy remains active.
                record["consecutive_failures"] = int(record.get("consecutive_failures", 0) or 0) + 1
            elif normalized_status == "failed":
                record["consecutive_failures"] = int(record.get("consecutive_failures", 0) or 0) + 1
        else:
            record.setdefault("last_status", "retained")
        nodes[node_id] = record
        report = {
            "refresh": bool(self.decisions[node_id].refresh),
            "reason": self.decisions[node_id].reason,
            "attempted_live": bool(attempted_live),
            "status": normalized_status,
            "changed": bool(changed),
            "first_signature": bool(first_signature),
            "output_signature": str(output_signature or ""),
            "elapsed_sec": round(max(0.0, float(elapsed_sec)), 3),
            "error": str(error or ""),
        }
        self.run_report[node_id] = report
        return report

    def node_changed(self, node_id: str) -> bool:
        return bool((self.run_report.get(node_id) or {}).get("changed"))

    def compact_report(self) -> dict[str, Any]:
        refreshed = [node for node, row in self.run_report.items() if row.get("attempted_live")]
        changed = [node for node, row in self.run_report.items() if row.get("changed")]
        failed = [node for node, row in self.run_report.items() if row.get("status") == "failed"]
        partial = [node for node, row in self.run_report.items() if row.get("status") == "partial"]
        retained = [node for node, row in self.run_report.items() if not row.get("attempted_live")]
        return {
            "graph_version": REFRESH_GRAPH_VERSION,
            "force_full": bool(self.force_full),
            "refreshed_nodes": refreshed,
            "changed_nodes": changed,
            "failed_nodes": failed,
            "partial_nodes": partial,
            "retained_nodes": retained,
            "nodes": dict(self.run_report),
        }


def build_refresh_plan(
    *,
    now: datetime | None = None,
    state: dict[str, Any] | None = None,
    trigger_tokens: dict[str, str] | None = None,
    force_full: bool | None = None,
) -> RefreshPlan:
    current = (now or _utc_now()).astimezone(timezone.utc)
    return RefreshPlan(
        state=dict(state if state is not None else load_refresh_graph_state()),
        now=current,
        force_full=force_full_refresh_requested() if force_full is None else bool(force_full),
        trigger_tokens=dict(trigger_tokens or {}),
    )


def refresh_nodes_due(plan: RefreshPlan, node_ids: Iterable[str]) -> set[str]:
    return {node_id for node_id in node_ids if plan.should_refresh(node_id)}
