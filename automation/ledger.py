"""Persistent, non-secret automation run and paid-call ledger."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from config.deployment import PROJECT_ROOT
from helpers.atomic_io import atomic_write_json, synchronized_path
from automation.config import AUTOMATION_TIMEZONE

AUTOMATION_ARTIFACT_ROOT = PROJECT_ROOT / "automation_artifacts"
STATUS_PATH = AUTOMATION_ARTIFACT_ROOT / "status.json"
RUNS_PATH = AUTOMATION_ARTIFACT_ROOT / "runs.jsonl"
CALL_JOURNAL_PATH = AUTOMATION_ARTIFACT_ROOT / "call_journal.jsonl"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_run_id(now: datetime | None = None) -> str:
    stamp = (now or utc_now()).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_{uuid4().hex[:8]}"


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with synchronized_path(path):
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str) + "\n")
            handle.flush()


def write_status(payload: dict[str, Any]) -> None:
    AUTOMATION_ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    atomic_write_json(payload, STATUS_PATH)


def append_run(payload: dict[str, Any]) -> None:
    _append_jsonl(RUNS_PATH, payload)


def reserve_paid_call(*, run_id: str, stage: str, now: datetime | None = None) -> str:
    moment = now or utc_now()
    call_id = f"{run_id}_{stage}_{uuid4().hex[:8]}"
    _append_jsonl(CALL_JOURNAL_PATH, {
        "event": "reserved",
        "call_id": call_id,
        "run_id": run_id,
        "stage": stage,
        "at_utc": moment.isoformat(),
        "local_date": moment.astimezone(ZoneInfo(AUTOMATION_TIMEZONE)).date().isoformat(),
    })
    return call_id


def mark_paid_call_submitted(
    *,
    call_id: str,
    run_id: str,
    stage: str,
    response_id: str,
    response_status: str,
) -> None:
    """Persist the provider response ID before the first poll begins."""
    _append_jsonl(CALL_JOURNAL_PATH, {
        "event": "submitted",
        "call_id": call_id,
        "run_id": run_id,
        "stage": stage,
        "response_id": str(response_id or ""),
        "response_status": str(response_status or ""),
        "at_utc": utc_now().isoformat(),
    })


def complete_paid_call(*, call_id: str, run_id: str, stage: str, status: str, detail: str = "") -> None:
    _append_jsonl(CALL_JOURNAL_PATH, {
        "event": "completed",
        "call_id": call_id,
        "run_id": run_id,
        "stage": stage,
        "status": status,
        "detail": str(detail or "")[:500],
        "at_utc": utc_now().isoformat(),
    })


def paid_calls_for_local_date(local_date: str) -> int:
    """Count in-flight calls and calls that successfully returned a response.

    A reservation temporarily holds a safety slot while its request is in
    flight. Once the call completes, only status="completed" continues to
    consume the allowance. Calls completed with status="error" do not count.
    """
    if not CALL_JOURNAL_PATH.exists():
        return 0
    reservations: dict[str, str] = {}
    completion_statuses: dict[str, str] = {}
    with synchronized_path(CALL_JOURNAL_PATH):
        try:
            lines = CALL_JOURNAL_PATH.read_text(encoding="utf-8").splitlines()
        except OSError:
            return 0
    for line in lines:
        try:
            row = json.loads(line)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(row, dict) or not row.get("call_id"):
            continue

        call_id = str(row["call_id"])
        event = str(row.get("event") or "")
        if event == "reserved":
            reservations[call_id] = str(row.get("local_date") or "")
        elif event == "completed":
            completion_statuses[call_id] = str(row.get("status") or "")

    return sum(
        1
        for call_id, reservation_date in reservations.items()
        if reservation_date == local_date
        and (
            call_id not in completion_statuses
            or completion_statuses[call_id] == "completed"
        )
    )


def today_local_date(now: datetime | None = None) -> str:
    return (now or utc_now()).astimezone(ZoneInfo(AUTOMATION_TIMEZONE)).date().isoformat()
