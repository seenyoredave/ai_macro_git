from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from config.deployment import PROJECT_ROOT, current_context_paths, developer_mode
from helpers.atomic_io import atomic_write_bytes, atomic_write_json, synchronized_path
from loaders.current_context_discovery import DISCOVERY_VERSION, refresh_current_context
from loaders.current_context_loader import load_current_context

RETAINED_REGISTRY = PROJECT_ROOT / "data" / "weekly_context_events.csv"
CURRENT_CONTEXT_SHARED_TTL_SECONDS = 15 * 60
CONTEXT_READ_SNAPSHOT_VERSION = "1.1"


def _read_manifest(path: Path) -> dict:
    with synchronized_path(path.parent / ".current_context_refresh"):
        if not path.exists() or path.stat().st_size == 0:
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, ValueError, json.JSONDecodeError):
            return {}


def _seed_public_registry(path: Path) -> None:
    with synchronized_path(path.parent / ".current_context_refresh"):
        if path.exists() and path.stat().st_size > 0:
            return
        if RETAINED_REGISTRY.exists():
            atomic_write_bytes(RETAINED_REGISTRY.read_bytes(), path, lock=False)
        else:
            atomic_write_bytes(b"", path, lock=False)


def _fallback_snapshot_id(manifest: dict) -> str:
    material = {
        "discovery_version": str(manifest.get("discovery_version") or ""),
        "as_of": str(manifest.get("as_of") or ""),
        "retrieved_at": str(manifest.get("retrieved_at") or ""),
        "selected": manifest.get("selected") if isinstance(manifest.get("selected"), dict) else {},
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()[:16]


def context_packet_id(manifest: dict, current_context: dict | None) -> str:
    """Fingerprint the exact Current Context packet attached to the Reads."""
    by_domain = (current_context or {}).get("by_domain", {}) or {}
    material = {
        "architecture_version": CONTEXT_READ_SNAPSHOT_VERSION,
        "discovery_version": str(manifest.get("discovery_version") or manifest.get("engine_version") or DISCOVERY_VERSION),
        "as_of": str((current_context or {}).get("as_of") or manifest.get("as_of") or ""),
        "retrieved_at": str(manifest.get("retrieved_at") or ""),
        "events": {
            str(domain): [
                {
                    "event_id": str(event.get("event_id") or ""),
                    "event_date": str(event.get("event_date") or ""),
                    "source_url": str(event.get("source_url") or ""),
                    "display": str(event.get("display") or ""),
                }
                for event in (payload.get("events", []) if isinstance(payload, dict) else [])
                if isinstance(event, dict)
                and str(event.get("verification_status") or event.get("status") or "").strip().lower() != "no_match"
            ]
            for domain, payload in sorted(by_domain.items())
        },
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()[:16]


def _decorate_manifest(manifest: dict, *, refresh_status: str, registry_path: Path) -> dict:
    payload = dict(manifest or {})
    selected = payload.get("selected") if isinstance(payload.get("selected"), dict) else {}
    fetch_status = payload.get("fetch_status") if isinstance(payload.get("fetch_status"), list) else []
    engine_mismatch = bool(payload.get("discovery_version") and str(payload.get("discovery_version")) != DISCOVERY_VERSION)
    explicit_refresh_required = bool(payload.get("refresh_required", False))
    payload.update({
        "source_mode": "manual_live" if refresh_status == "refreshed" and developer_mode() else (
            "shared_live" if refresh_status == "refreshed" else "retained"
        ),
        "refresh_status": refresh_status,
        "engine_version": DISCOVERY_VERSION,
        "retained_discovery_version": str(payload.get("discovery_version") or "unknown"),
        "engine_mismatch": engine_mismatch,
        "refresh_required": bool(engine_mismatch or explicit_refresh_required),
        "selected_counts": {
            str(domain): len(items) if isinstance(items, list) else 0
            for domain, items in selected.items()
        },
        "fetch_errors": [
            {
                "domain": str(row.get("domain") or ""),
                "provider": str(row.get("provider") or ""),
                "query": str(row.get("query") or ""),
                "error": str(row.get("error") or ""),
            }
            for row in fetch_status
            if isinstance(row, dict) and str(row.get("error") or "").strip()
        ],
        "registry_path": str(registry_path),
        "snapshot_id": str(payload.get("snapshot_id") or _fallback_snapshot_id(payload)),
        "snapshot_ttl_seconds": CURRENT_CONTEXT_SHARED_TTL_SECONDS,
        "snapshot_architecture_version": CONTEXT_READ_SNAPSHOT_VERSION,
    })
    return payload


def finalize_context_report(manifest: dict, current_context: dict | None) -> dict:
    """Attach the exact packet ID and final rendered-domain counts to a report."""
    payload = dict(manifest or {})
    payload["snapshot_id"] = context_packet_id(payload, current_context)
    payload["context_packet_id"] = payload["snapshot_id"]
    by_domain = (current_context or {}).get("by_domain", {}) or {}
    payload["rendered_context_counts"] = {
        str(domain): sum(
            1
            for event in (domain_payload.get("events", []) if isinstance(domain_payload, dict) else [])
            if isinstance(event, dict)
            and str(event.get("verification_status") or event.get("status") or "").strip().lower() != "no_match"
        )
        for domain, domain_payload in by_domain.items()
    }
    return payload


def refresh_current_context_once_daily(*, as_of=None, force: bool = False) -> dict:
    """Developer/manual refresh path; retained startup never calls providers."""
    current = pd.Timestamp(as_of or pd.Timestamp.now()).normalize()
    expected_date = current.date().isoformat()
    paths = current_context_paths()
    paths["base"].mkdir(parents=True, exist_ok=True)

    with synchronized_path(paths["daily_lock"]):
        manifest = _read_manifest(paths["manifest"])
        if not force and manifest.get("as_of") == expected_date:
            return _decorate_manifest(manifest, refresh_status="already_current", registry_path=paths["registry"])

        if not developer_mode():
            _seed_public_registry(paths["registry"])

        try:
            manifest = refresh_current_context(
                as_of=current,
                audit_path=paths["audit"],
                manifest_path=paths["manifest"],
                registry_path=paths["registry"],
                merge_registry=True,
            )
            return _decorate_manifest(manifest, refresh_status="refreshed", registry_path=paths["registry"])
        except Exception as exc:
            failure = {
                "as_of": expected_date,
                "refresh_status": "failed_retained_fallback",
                "error": f"{type(exc).__name__}: {exc}",
                "registry_path": str(paths["registry"]),
            }
            persisted_failure = dict(failure)
            persisted_failure["registry_path"] = paths["registry"].name
            with synchronized_path(paths["manifest"].parent / ".current_context_refresh"):
                atomic_write_json(persisted_failure, paths["manifest"], lock=False)
            return failure


@st.cache_data(ttl=CURRENT_CONTEXT_SHARED_TTL_SECONDS, show_spinner=False)
def _load_public_shared_snapshot_cached(as_of_iso: str, engine_version: str) -> dict:
    """Build the shared public Context packet once per ~15-minute cache window.

    Public writes are confined to the ephemeral runtime directory.  Repository
    archives remain immutable.  Streamlit's shared cache means readers inside
    the same window receive the same completed Context packet.
    """
    del engine_version  # part of the cache key; forces refresh after an engine upgrade
    current = pd.Timestamp(as_of_iso).normalize()
    paths = current_context_paths()
    paths["base"].mkdir(parents=True, exist_ok=True)
    _seed_public_registry(paths["registry"])

    try:
        with synchronized_path(paths["daily_lock"]):
            manifest = refresh_current_context(
                as_of=current,
                audit_path=paths["audit"],
                manifest_path=paths["manifest"],
                registry_path=paths["registry"],
                merge_registry=True,
            )
        report = _decorate_manifest(manifest, refresh_status="refreshed", registry_path=paths["registry"])
    except Exception as exc:
        retained = _read_manifest(paths["manifest"])
        report = _decorate_manifest(retained, refresh_status="failed_retained_fallback", registry_path=paths["registry"])
        report["error"] = f"{type(exc).__name__}: {exc}"

    current_context = load_current_context(
        as_of=current,
        path=paths["registry"],
        limit_per_domain=2,
    )
    report = finalize_context_report(report, current_context)
    current_context = dict(current_context)
    current_context["snapshot_id"] = report["snapshot_id"]
    current_context["snapshot_retrieved_at"] = report.get("retrieved_at", "")
    current_context["snapshot_ttl_seconds"] = CURRENT_CONTEXT_SHARED_TTL_SECONDS
    return {
        "report": report,
        "current_context": current_context,
    }


def load_public_shared_context_snapshot(*, as_of=None) -> dict:
    """Return the globally shared public Context packet for the current window."""
    current = pd.Timestamp(as_of or pd.Timestamp.now()).normalize()
    return _load_public_shared_snapshot_cached(current.date().isoformat(), DISCOVERY_VERSION)


def describe_current_context_state() -> dict:
    """Describe the retained Current Context snapshot without network access."""
    paths = current_context_paths()
    manifest = _read_manifest(paths["manifest"])
    retained_version = str(manifest.get("discovery_version") or "").strip()
    selected = manifest.get("selected") if isinstance(manifest.get("selected"), dict) else {}
    selected_counts = {
        str(domain): len(items) if isinstance(items, list) else 0
        for domain, items in selected.items()
    }
    fetch_status = manifest.get("fetch_status") if isinstance(manifest.get("fetch_status"), list) else []
    fetch_errors = [
        {
            "domain": str(row.get("domain") or ""),
            "provider": str(row.get("provider") or ""),
            "query": str(row.get("query") or ""),
            "error": str(row.get("error") or ""),
        }
        for row in fetch_status
        if isinstance(row, dict) and str(row.get("error") or "").strip()
    ]
    engine_mismatch = bool(retained_version and retained_version != DISCOVERY_VERSION)
    explicit_refresh_required = bool(manifest.get("refresh_required", False))
    return {
        "source_mode": "retained",
        "refresh_status": "retained",
        "engine_version": DISCOVERY_VERSION,
        "retained_discovery_version": retained_version or "unknown",
        "engine_mismatch": engine_mismatch,
        "refresh_required": bool(engine_mismatch or explicit_refresh_required),
        "as_of": manifest.get("as_of", ""),
        "retrieved_at": manifest.get("retrieved_at", ""),
        "candidate_count": int(manifest.get("candidate_count", 0) or 0),
        "qualified_count": int(manifest.get("qualified_count", 0) or 0),
        "grounding": dict(manifest.get("grounding") or {}),
        "selected_counts": selected_counts,
        "fetch_errors": fetch_errors,
        "registry_path": str(paths["registry"]),
        "manifest_path": str(paths["manifest"]),
        "snapshot_id": str(manifest.get("snapshot_id") or _fallback_snapshot_id(manifest)),
        "snapshot_ttl_seconds": CURRENT_CONTEXT_SHARED_TTL_SECONDS,
        "snapshot_architecture_version": CONTEXT_READ_SNAPSHOT_VERSION,
    }
