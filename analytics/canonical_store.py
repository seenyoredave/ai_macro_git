"""Canonical analytical observation store backed by Parquet and DuckDB.

Provider-specific retained files remain the source layer. This module is the
normalized boundary for completed deterministic domain metrics: stable metric
ids, point-in-time observations, explicit display semantics, source links, and
immutable publication snapshots.

Snapshot Parquet files are partitioned and append-only. That matters because Git
is the publication boundary: a new research state adds small immutable files
instead of rewriting one growing compressed database artifact on every run.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import tempfile
from typing import Any, Iterable

import duckdb
import numpy as np
import pandas as pd

from analytics.dashboard_context import DashboardContext
from analytics.domain_state import DOMAIN_ORDER, DomainState, with_domain_states
from analytics.read_evidence import (
    DOMAIN_REFERENCES,
    EvidenceFact,
    EvidencePacket,
    build_evidence_packets,
    evidence_snapshot_id,
)
from config.deployment import PROJECT_ROOT
from config.market_clock import market_date
from config.metric_definitions import METRIC_DEFINITIONS
from helpers.atomic_io import atomic_write_bundle

CANONICAL_SCHEMA_VERSION = "1.0.0"
CANONICAL_ROOT = PROJECT_ROOT / "data" / "canonical"
CANONICAL_METRICS_PATH = CANONICAL_ROOT / "metrics.parquet"
CANONICAL_SOURCES_PATH = CANONICAL_ROOT / "sources.parquet"
CANONICAL_METRIC_SOURCES_PATH = CANONICAL_ROOT / "metric_sources.parquet"
CANONICAL_OBSERVATIONS_ROOT = CANONICAL_ROOT / "observations"
CANONICAL_SNAPSHOTS_ROOT = CANONICAL_ROOT / "snapshots"

_METRIC_COLUMNS = (
    "schema_version",
    "metric_id",
    "domain",
    "metric_key",
    "label",
    "description",
    "unit",
    "display_scale",
    "display_digits",
    "value_type",
    "evidence_fact",
    "first_seen_snapshot_id",
)
_OBSERVATION_COLUMNS = (
    "schema_version",
    "snapshot_id",
    "metric_id",
    "domain",
    "entity_id",
    "geography",
    "frequency",
    "observation_date",
    "period_start",
    "period_end",
    "vintage",
    "value_double",
    "value_text",
    "value_type",
    "display_value",
    "context",
    "importance",
    "quality_status",
    "transformation_id",
    "retrieved_at_utc",
    "run_id",
    "publication_source",
)
_SNAPSHOT_COLUMNS = (
    "schema_version",
    "snapshot_id",
    "evidence_snapshot_id",
    "observation_date",
    "created_at_utc",
    "run_id",
    "publication_source",
    "context_snapshot_id",
    "metric_count",
    "domain_count",
    "state_hash",
    "domains_json",
    "source_status_json",
)
_SOURCE_COLUMNS = (
    "schema_version",
    "source_id",
    "source_label",
    "source_url",
    "first_seen_snapshot_id",
)
_METRIC_SOURCE_COLUMNS = (
    "schema_version",
    "metric_id",
    "source_id",
    "provenance_scope",
    "first_seen_snapshot_id",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat()


def _as_date_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    if not text:
        return market_date().isoformat()
    parsed = pd.to_datetime(text, errors="coerce", format="mixed")
    if pd.isna(parsed):
        raise ValueError(f"Invalid canonical observation date: {value!r}")
    return parsed.date().isoformat()


def _root_paths(root: Path) -> dict[str, Path]:
    base = root / "data" / "canonical"
    return {
        "root": base,
        "metrics": base / "metrics.parquet",
        "sources": base / "sources.parquet",
        "metric_sources": base / "metric_sources.parquet",
        "observations": base / "observations",
        "snapshots": base / "snapshots",
        "transaction": base / ".canonical-transaction",
    }


def _partition_path(base: Path, observation_date: str, snapshot_id: str) -> Path:
    year, month, _ = observation_date.split("-", 2)
    return base / year / month / f"{snapshot_id}.parquet"


def _snapshot_paths(root: Path, observation_date: str, snapshot_id: str) -> tuple[Path, Path]:
    paths = _root_paths(root)
    return (
        _partition_path(paths["observations"], observation_date, snapshot_id),
        _partition_path(paths["snapshots"], observation_date, snapshot_id),
    )


def _all_partition_files(root: Path, kind: str) -> list[Path]:
    base = _root_paths(root)[kind]
    if not base.exists():
        return []
    return sorted(path for path in base.rglob("*.parquet") if path.is_file())


def _find_partition_file(root: Path, kind: str, snapshot_id: str) -> Path | None:
    base = _root_paths(root)[kind]
    if not base.exists():
        return None
    matches = list(base.rglob(f"{snapshot_id}.parquet"))
    if len(matches) > 1:
        raise ValueError(f"Canonical snapshot {snapshot_id} is duplicated in {kind}.")
    return matches[0] if matches else None


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, pd.DataFrame):
        return {
            "rows": int(len(value)),
            "columns": [str(column) for column in value.columns],
        }
    if isinstance(value, pd.Series):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, (np.floating, float)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if hasattr(value, "item") and callable(value.item):
        try:
            return _json_safe(value.item())
        except (TypeError, ValueError):
            pass
    if hasattr(value, "isoformat") and callable(value.isoformat):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return str(value)
    return value


def _hash_value(value: Any) -> Any:
    """Normalize semantic state so integer/float round trips hash identically."""
    if value is None:
        return None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int, np.floating, float)) and not isinstance(value, bool):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if isinstance(value, dict):
        return {
            str(key): _hash_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple, set)):
        return [_hash_value(item) for item in value]
    return _json_safe(value)


def _normalized_state_payload(context: DashboardContext, *, observation_date: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "observation_date": observation_date,
        "domains": {},
    }
    for domain in DOMAIN_ORDER:
        state = (context.domain_states or {}).get(domain)
        if not isinstance(state, DomainState):
            raise ValueError(f"Canonical store requires deterministic domain state for {domain}.")
        payload["domains"][domain] = {
            "importance": _hash_value(state.importance),
            "metrics": {
                str(key): _hash_value(value)
                for key, value in sorted((state.metrics or {}).items())
            },
        }
    return payload


def canonical_snapshot_id(context: DashboardContext, *, observation_date: Any = None) -> str:
    prepared = with_domain_states(context)
    date_text = _as_date_text(observation_date)
    payload = _normalized_state_payload(prepared, observation_date=date_text)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def _source_id(label: str, url: str) -> str:
    encoded = f"{label.strip()}\n{url.strip()}".encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:20]


def _human_label(metric_key: str) -> str:
    return str(metric_key).replace("_", " ").strip().title()


def _classify_value(value: Any) -> tuple[str, float | None, str, str]:
    """Return value type, numeric value, text value, and quality status."""
    if value is None:
        return "missing", None, "", "missing"
    if isinstance(value, (np.bool_, bool)):
        return "text", None, "true" if bool(value) else "false", "valid"
    if isinstance(value, (np.integer, int, np.floating, float)) and not isinstance(value, bool):
        numeric = float(value)
        if math.isfinite(numeric):
            return "numeric", numeric, "", "valid"
        return "missing", None, "", "missing"
    if isinstance(value, str):
        text = value.strip()
        return ("text", None, text, "valid") if text else ("missing", None, "", "missing")
    safe = _json_safe(value)
    if safe is None:
        return "missing", None, "", "missing"
    if isinstance(safe, (dict, list)):
        return (
            "json",
            None,
            json.dumps(safe, sort_keys=True, separators=(",", ":")),
            "valid",
        )
    text = str(safe).strip()
    return ("text", None, text, "valid") if text else ("missing", None, "", "missing")


def _display_value(
    value_type: str,
    numeric: float | None,
    text: str,
    fact: EvidenceFact | None,
) -> str:
    if fact is not None:
        return str(fact.display or "").strip()
    if value_type == "numeric" and numeric is not None:
        return f"{numeric:g}"
    if value_type in {"text", "json"}:
        return text
    return ""


def _fact_index(packets: dict[str, EvidencePacket]) -> dict[str, EvidenceFact]:
    return {
        fact.id: fact
        for packet in packets.values()
        for fact in packet.facts
    }


def _definition_for(label: str) -> str:
    value = METRIC_DEFINITIONS.get(label)
    return str(value).strip() if value is not None else ""


def build_canonical_frames(
    context: DashboardContext,
    *,
    observation_date: Any = None,
    run_id: str = "",
    publication_source: str,
    retrieved_at: datetime | None = None,
    source_status: dict[str, Any] | None = None,
) -> tuple[DashboardContext, dict[str, pd.DataFrame], dict[str, Any]]:
    """Normalize one completed deterministic research state into canonical rows."""
    prepared = with_domain_states(context)
    date_text = _as_date_text(observation_date)
    created_at = _iso(retrieved_at or _utc_now())
    packets = build_evidence_packets(prepared)
    evidence_id = evidence_snapshot_id(packets)
    snapshot_id = canonical_snapshot_id(prepared, observation_date=date_text)
    facts = _fact_index(packets)

    metric_rows: list[dict[str, Any]] = []
    observation_rows: list[dict[str, Any]] = []
    source_rows: dict[str, dict[str, Any]] = {}
    metric_source_rows: dict[tuple[str, str], dict[str, Any]] = {}

    for domain in DOMAIN_ORDER:
        state = prepared.domain_states[domain]
        domain_sources = [dict(item) for item in DOMAIN_REFERENCES.get(domain, ())]
        for metric_key, raw_value in sorted((state.metrics or {}).items()):
            metric_id = f"{domain}.{metric_key}"
            fact = facts.get(metric_id)
            label = str(fact.label if fact is not None else _human_label(metric_key))
            unit = str(getattr(fact, "unit", "") or "") if fact is not None else ""
            value_type, numeric, text, quality = _classify_value(raw_value)
            display = _display_value(value_type, numeric, text, fact)
            context_text = str(fact.context or "").strip() if fact is not None else ""
            metric_rows.append({
                "schema_version": CANONICAL_SCHEMA_VERSION,
                "metric_id": metric_id,
                "domain": domain,
                "metric_key": str(metric_key),
                "label": label,
                "description": _definition_for(label),
                "unit": unit,
                "display_scale": float(getattr(fact, "scale", 1.0)) if fact is not None else 1.0,
                "display_digits": int(getattr(fact, "digits", 1)) if fact is not None else 1,
                "value_type": value_type,
                "evidence_fact": bool(fact is not None),
                "first_seen_snapshot_id": snapshot_id,
            })
            observation_rows.append({
                "schema_version": CANONICAL_SCHEMA_VERSION,
                "snapshot_id": snapshot_id,
                "metric_id": metric_id,
                "domain": domain,
                "entity_id": f"{domain}:aggregate",
                "geography": "US",
                "frequency": "snapshot",
                "observation_date": date_text,
                "period_start": "",
                "period_end": "",
                "vintage": "",
                "value_double": numeric,
                "value_text": text,
                "value_type": value_type,
                "display_value": display,
                "context": context_text,
                "importance": float(state.importance),
                "quality_status": quality,
                "transformation_id": f"domain_state:{domain}",
                "retrieved_at_utc": created_at,
                "run_id": str(run_id or ""),
                "publication_source": str(publication_source or "unknown"),
            })

            for reference in domain_sources:
                source_label = str(reference.get("source_label") or "").strip()
                source_url = str(reference.get("source_url") or "").strip()
                if not source_label:
                    continue
                source_id = _source_id(source_label, source_url)
                source_rows[source_id] = {
                    "schema_version": CANONICAL_SCHEMA_VERSION,
                    "source_id": source_id,
                    "source_label": source_label,
                    "source_url": source_url,
                    "first_seen_snapshot_id": snapshot_id,
                }
                metric_source_rows[(metric_id, source_id)] = {
                    "schema_version": CANONICAL_SCHEMA_VERSION,
                    "metric_id": metric_id,
                    "source_id": source_id,
                    "provenance_scope": "domain_reference",
                    "first_seen_snapshot_id": snapshot_id,
                }

    context_snapshot_id = str(
        (prepared.current_context or {}).get("snapshot_id")
        or (prepared.current_context or {}).get("context_packet_id")
        or ""
    ).strip()
    source_status_json = json.dumps(
        _json_safe(source_status or {}),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    snapshot_row = {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "evidence_snapshot_id": evidence_id,
        "observation_date": date_text,
        "created_at_utc": created_at,
        "run_id": str(run_id or ""),
        "publication_source": str(publication_source or "unknown"),
        "context_snapshot_id": context_snapshot_id,
        "metric_count": len(observation_rows),
        "domain_count": len(DOMAIN_ORDER),
        "state_hash": snapshot_id,
        "domains_json": json.dumps(list(DOMAIN_ORDER), separators=(",", ":")),
        "source_status_json": source_status_json,
    }

    frames = {
        "metrics": pd.DataFrame(metric_rows, columns=_METRIC_COLUMNS),
        "observations": pd.DataFrame(observation_rows, columns=_OBSERVATION_COLUMNS),
        "snapshots": pd.DataFrame([snapshot_row], columns=_SNAPSHOT_COLUMNS),
        "sources": pd.DataFrame(list(source_rows.values()), columns=_SOURCE_COLUMNS),
        "metric_sources": pd.DataFrame(
            list(metric_source_rows.values()),
            columns=_METRIC_SOURCE_COLUMNS,
        ),
    }
    report = {
        "status": "prepared",
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "evidence_snapshot_id": evidence_id,
        "observation_date": date_text,
        "metric_count": len(observation_rows),
        "domain_count": len(DOMAIN_ORDER),
        "source_count": len(source_rows),
    }
    return prepared, frames, report


def _empty(columns: tuple[str, ...]) -> pd.DataFrame:
    return pd.DataFrame(columns=list(columns))


def _read_parquet_paths(paths: Iterable[Path], columns: tuple[str, ...]) -> pd.DataFrame:
    files = [Path(path) for path in paths if Path(path).exists()]
    if not files:
        return _empty(columns)
    con = duckdb.connect(database=":memory:")
    try:
        frame = con.read_parquet(
            [str(path) for path in files],
            union_by_name=True,
        ).to_df()
    finally:
        con.close()
    for column in columns:
        if column not in frame.columns:
            frame[column] = None
    return frame[list(columns)].copy()


def _read_parquet(path: Path, columns: tuple[str, ...]) -> pd.DataFrame:
    return _read_parquet_paths([path], columns)


def _merge_registry(
    existing: pd.DataFrame,
    incoming: pd.DataFrame,
    *,
    keys: list[str],
    first_seen_column: str = "first_seen_snapshot_id",
) -> pd.DataFrame:
    """Merge stable registry metadata while preserving original first-seen ids."""
    if existing.empty:
        combined = incoming.copy()
    elif incoming.empty:
        combined = existing.copy()
    else:
        old = existing.copy()
        old["__registry_order"] = 0
        new = incoming.copy()
        new["__registry_order"] = 1
        stacked = pd.concat([old, new], ignore_index=True, sort=False)
        rows: list[pd.Series] = []
        for _, group in stacked.groupby(keys, sort=False, dropna=False):
            group = group.sort_values("__registry_order", kind="stable")
            first = group.iloc[0]
            last = group.iloc[-1].copy()
            if first_seen_column in group.columns:
                last[first_seen_column] = first.get(first_seen_column)
            rows.append(last)
        combined = pd.DataFrame(rows).drop(columns=["__registry_order"], errors="ignore")
    if combined.empty:
        return combined
    return combined.sort_values(keys, kind="stable").reset_index(drop=True)


def _stabilize_metric_registry(
    existing: pd.DataFrame,
    merged: pd.DataFrame,
) -> pd.DataFrame:
    """Do not let a temporarily missing metric degrade durable registry metadata."""
    if existing.empty or merged.empty:
        return merged
    prior = existing.drop_duplicates("metric_id", keep="last").set_index("metric_id")
    output = merged.copy()
    descriptive = (
        "label",
        "description",
        "unit",
        "display_scale",
        "display_digits",
        "value_type",
        "evidence_fact",
    )
    for index, row in output.iterrows():
        metric_id = str(row.get("metric_id") or "")
        if metric_id not in prior.index:
            continue
        current_type = str(row.get("value_type") or "").strip().casefold()
        current_fact = bool(row.get("evidence_fact"))
        if current_fact or current_type not in {"", "missing", "unknown"}:
            continue
        old = prior.loc[metric_id]
        if isinstance(old, pd.DataFrame):
            old = old.iloc[-1]
        for column in descriptive:
            old_value = old.get(column)
            if pd.notna(old_value):
                output.at[index, column] = old_value
    return output


def _frame_signature(frame: pd.DataFrame, columns: tuple[str, ...]) -> str:
    if frame.empty:
        return "empty"
    normalized = frame[list(columns)].copy().reset_index(drop=True)
    records = [
        {column: _json_safe(row.get(column)) for column in columns}
        for _, row in normalized.iterrows()
    ]
    raw = json.dumps(records, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _parquet_bytes(frame: pd.DataFrame) -> bytes:
    with tempfile.TemporaryDirectory(prefix="ai-macro-canonical-") as directory:
        path = Path(directory) / "payload.parquet"
        con = duckdb.connect(database=":memory:")
        try:
            con.from_df(frame).to_parquet(
                str(path),
                compression="zstd",
                row_group_size=100000,
            )
        finally:
            con.close()
        return path.read_bytes()


def _round_trip_context(
    context: DashboardContext,
    *,
    snapshot_id: str,
    root: Path,
) -> DashboardContext:
    persisted_states = load_canonical_domain_states(snapshot_id=snapshot_id, root=root)
    if set(persisted_states) != set(DOMAIN_ORDER):
        raise ValueError("Canonical snapshot is incomplete and cannot be used as the analytical boundary.")
    return replace(
        context,
        domain_states=persisted_states,
        canonical_snapshot_id=snapshot_id,
        canonical_schema_version=CANONICAL_SCHEMA_VERSION,
    )


def persist_canonical_snapshot(
    context: DashboardContext,
    *,
    observation_date: Any = None,
    run_id: str = "",
    publication_source: str,
    retrieved_at: datetime | None = None,
    source_status: dict[str, Any] | None = None,
    root: Path = PROJECT_ROOT,
) -> tuple[DashboardContext, dict[str, Any]]:
    """Persist one idempotent point-in-time canonical analytical snapshot."""
    prepared, frames, report = build_canonical_frames(
        context,
        observation_date=observation_date,
        run_id=run_id,
        publication_source=publication_source,
        retrieved_at=retrieved_at,
        source_status=source_status,
    )
    paths = _root_paths(root)
    observation_path, snapshot_path = _snapshot_paths(
        root,
        report["observation_date"],
        report["snapshot_id"],
    )

    if observation_path.exists() != snapshot_path.exists():
        raise ValueError(
            f"Canonical snapshot {report['snapshot_id']} has an incomplete partition pair."
        )
    if observation_path.exists():
        prepared = _round_trip_context(
            prepared,
            snapshot_id=report["snapshot_id"],
            root=root,
        )
        report["status"] = "unchanged"
        report["paths"] = {
            "observations": observation_path.relative_to(root).as_posix(),
            "snapshot": snapshot_path.relative_to(root).as_posix(),
        }
        return prepared, report

    existing_metrics = _read_parquet(paths["metrics"], _METRIC_COLUMNS)
    existing_sources = _read_parquet(paths["sources"], _SOURCE_COLUMNS)
    existing_metric_sources = _read_parquet(
        paths["metric_sources"],
        _METRIC_SOURCE_COLUMNS,
    )

    metrics = _merge_registry(
        existing_metrics,
        frames["metrics"],
        keys=["metric_id"],
    )
    metrics = _stabilize_metric_registry(existing_metrics, metrics)
    sources = _merge_registry(
        existing_sources,
        frames["sources"],
        keys=["source_id"],
    )
    metric_sources = _merge_registry(
        existing_metric_sources,
        frames["metric_sources"],
        keys=["metric_id", "source_id"],
    )

    payloads: dict[Path, bytes] = {
        observation_path: _parquet_bytes(frames["observations"][list(_OBSERVATION_COLUMNS)]),
        snapshot_path: _parquet_bytes(frames["snapshots"][list(_SNAPSHOT_COLUMNS)]),
    }
    if _frame_signature(existing_metrics, _METRIC_COLUMNS) != _frame_signature(metrics, _METRIC_COLUMNS):
        payloads[paths["metrics"]] = _parquet_bytes(metrics[list(_METRIC_COLUMNS)])
    if _frame_signature(existing_sources, _SOURCE_COLUMNS) != _frame_signature(sources, _SOURCE_COLUMNS):
        payloads[paths["sources"]] = _parquet_bytes(sources[list(_SOURCE_COLUMNS)])
    if _frame_signature(existing_metric_sources, _METRIC_SOURCE_COLUMNS) != _frame_signature(
        metric_sources,
        _METRIC_SOURCE_COLUMNS,
    ):
        payloads[paths["metric_sources"]] = _parquet_bytes(
            metric_sources[list(_METRIC_SOURCE_COLUMNS)]
        )

    atomic_write_bundle(payloads, transaction_key=paths["transaction"])
    prepared = _round_trip_context(
        prepared,
        snapshot_id=report["snapshot_id"],
        root=root,
    )
    report["status"] = "written"
    report["paths"] = {
        "observations": observation_path.relative_to(root).as_posix(),
        "snapshot": snapshot_path.relative_to(root).as_posix(),
        "metrics": paths["metrics"].relative_to(root).as_posix(),
        "sources": paths["sources"].relative_to(root).as_posix(),
        "metric_sources": paths["metric_sources"].relative_to(root).as_posix(),
    }
    return prepared, report


def _snapshot_frame(*, root: Path) -> pd.DataFrame:
    return _read_parquet_paths(
        _all_partition_files(root, "snapshots"),
        _SNAPSHOT_COLUMNS,
    )


def latest_canonical_snapshot(*, root: Path = PROJECT_ROOT) -> dict[str, Any]:
    snapshots = _snapshot_frame(root=root)
    if snapshots.empty:
        return {}
    ordered = snapshots.sort_values(
        ["observation_date", "created_at_utc"],
        kind="stable",
    )
    row = ordered.iloc[-1]
    return {column: _json_safe(row.get(column)) for column in _SNAPSHOT_COLUMNS}


def load_canonical_domain_states(
    *,
    snapshot_id: str | None = None,
    root: Path = PROJECT_ROOT,
) -> dict[str, DomainState]:
    """Reconstruct deterministic domain state from one immutable snapshot."""
    chosen = str(snapshot_id or "").strip()
    if not chosen:
        chosen = str(latest_canonical_snapshot(root=root).get("snapshot_id") or "")
    if not chosen:
        return {}
    path = _find_partition_file(root, "observations", chosen)
    if path is None:
        return {}
    rows = _read_parquet(path, _OBSERVATION_COLUMNS)
    if rows.empty:
        return {}

    states: dict[str, DomainState] = {}
    for domain in DOMAIN_ORDER:
        domain_rows = rows.loc[rows["domain"].astype(str).eq(domain)]
        if domain_rows.empty:
            continue
        metrics: dict[str, Any] = {}
        for _, row in domain_rows.iterrows():
            metric_id = str(row.get("metric_id") or "")
            key = metric_id.split(".", 1)[1] if "." in metric_id else metric_id
            quality_status = str(row.get("quality_status") or "")
            stored_type = str(row.get("value_type") or "")
            if quality_status == "missing" or stored_type == "missing":
                value: Any = math.nan
            elif stored_type == "numeric":
                numeric = pd.to_numeric(row.get("value_double"), errors="coerce")
                value = float(numeric) if pd.notna(numeric) else math.nan
            elif stored_type == "json":
                text = str(row.get("value_text") or "")
                try:
                    value = json.loads(text)
                except (ValueError, json.JSONDecodeError):
                    value = text
            else:
                value = str(row.get("value_text") or "")
            metrics[key] = value
        importance = pd.to_numeric(domain_rows["importance"], errors="coerce").dropna()
        states[domain] = DomainState(
            metrics=metrics,
            importance=float(importance.iloc[-1]) if not importance.empty else 0.0,
        )
    return states


def canonical_metric_history(
    metric_id: str,
    *,
    root: Path = PROJECT_ROOT,
    limit: int | None = None,
) -> pd.DataFrame:
    """Return point-in-time canonical history for one stable metric id."""
    observations = _read_parquet_paths(
        _all_partition_files(root, "observations"),
        _OBSERVATION_COLUMNS,
    )
    if observations.empty:
        return pd.DataFrame()
    rows = observations.loc[
        observations["metric_id"].astype(str).eq(str(metric_id))
    ].copy()
    if rows.empty:
        return pd.DataFrame()
    metrics = _read_parquet(
        _root_paths(root)["metrics"],
        _METRIC_COLUMNS,
    )
    labels = metrics[[
        "metric_id",
        "label",
        "unit",
        "display_scale",
        "display_digits",
    ]].drop_duplicates("metric_id", keep="last")
    rows = rows.merge(labels, on="metric_id", how="left")
    rows = rows.sort_values(
        ["observation_date", "retrieved_at_utc"],
        ascending=[False, False],
        kind="stable",
    )
    if limit is not None:
        rows = rows.head(max(1, int(limit)))
    columns = [
        "snapshot_id",
        "entity_id",
        "geography",
        "frequency",
        "observation_date",
        "period_start",
        "period_end",
        "vintage",
        "metric_id",
        "label",
        "unit",
        "display_scale",
        "display_digits",
        "value_double",
        "value_text",
        "display_value",
        "quality_status",
        "retrieved_at_utc",
        "run_id",
        "publication_source",
    ]
    return rows[columns].reset_index(drop=True)


def canonical_snapshot_as_of(
    as_of: Any,
    *,
    root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    """Return the latest canonical snapshot available on or before ``as_of``."""
    target = _as_date_text(as_of)
    snapshots = _snapshot_frame(root=root)
    if snapshots.empty:
        return {}
    eligible = snapshots.loc[
        snapshots["observation_date"].astype(str).le(target)
    ].copy()
    if eligible.empty:
        return {}
    ordered = eligible.sort_values(
        ["observation_date", "created_at_utc"],
        kind="stable",
    )
    row = ordered.iloc[-1]
    return {column: _json_safe(row.get(column)) for column in _SNAPSHOT_COLUMNS}


def canonical_snapshot_diff(
    base_snapshot_id: str,
    head_snapshot_id: str,
    *,
    root: Path = PROJECT_ROOT,
) -> pd.DataFrame:
    """Return a metric-aligned point-in-time diff between two snapshots."""
    base_path = _find_partition_file(root, "observations", str(base_snapshot_id))
    head_path = _find_partition_file(root, "observations", str(head_snapshot_id))
    if base_path is None or head_path is None:
        return pd.DataFrame()
    base = _read_parquet(base_path, _OBSERVATION_COLUMNS)
    head = _read_parquet(head_path, _OBSERVATION_COLUMNS)
    if base.empty or head.empty:
        return pd.DataFrame()

    keep = [
        "metric_id",
        "domain",
        "entity_id",
        "geography",
        "value_double",
        "value_text",
        "value_type",
        "display_value",
        "quality_status",
    ]
    merged = base[keep].merge(
        head[keep],
        on=["metric_id", "domain", "entity_id", "geography"],
        how="outer",
        suffixes=("_base", "_head"),
    )
    metrics = _read_parquet(
        _root_paths(root)["metrics"],
        _METRIC_COLUMNS,
    )
    labels = metrics[[
        "metric_id",
        "label",
        "unit",
        "display_scale",
        "display_digits",
    ]].drop_duplicates("metric_id", keep="last")
    merged = merged.merge(labels, on="metric_id", how="left")

    base_numeric = pd.to_numeric(merged["value_double_base"], errors="coerce")
    head_numeric = pd.to_numeric(merged["value_double_head"], errors="coerce")
    numeric_pair = (
        merged["value_type_base"].astype(str).eq("numeric")
        & merged["value_type_head"].astype(str).eq("numeric")
        & base_numeric.notna()
        & head_numeric.notna()
    )
    merged["delta_numeric"] = np.where(
        numeric_pair,
        head_numeric - base_numeric,
        np.nan,
    )
    merged["changed"] = (
        merged["display_value_base"].fillna("").astype(str)
        != merged["display_value_head"].fillna("").astype(str)
    ) | (
        merged["quality_status_base"].fillna("").astype(str)
        != merged["quality_status_head"].fillna("").astype(str)
    )
    columns = [
        "metric_id",
        "domain",
        "entity_id",
        "geography",
        "label",
        "unit",
        "display_scale",
        "display_digits",
        "display_value_base",
        "display_value_head",
        "value_double_base",
        "value_double_head",
        "delta_numeric",
        "quality_status_base",
        "quality_status_head",
        "changed",
    ]
    return merged[columns].sort_values(
        ["domain", "metric_id"],
        kind="stable",
    ).reset_index(drop=True)
