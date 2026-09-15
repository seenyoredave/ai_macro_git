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


def _append_jsonl_unlocked(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str) + "\n")
        handle.flush()


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with synchronized_path(path):
        _append_jsonl_unlocked(path, payload)


def _journal_rows_unlocked() -> list[dict[str, Any]]:
    if not CALL_JOURNAL_PATH.exists():
        return []
    try:
        lines = CALL_JOURNAL_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines:
        try:
            row = json.loads(line)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(row, dict) and row.get("call_id"):
            rows.append(row)
    return rows


def _allowance_calls(
    rows: list[dict[str, Any]],
    *,
    local_date: str | None = None,
    run_id: str | None = None,
) -> int:
    reservations: dict[str, dict[str, Any]] = {}
    completion_statuses: dict[str, str] = {}
    for row in rows:
        call_id = str(row.get("call_id") or "")
        event = str(row.get("event") or "")
        if event == "reserved":
            reservations[call_id] = row
        elif event == "completed":
            completion_statuses[call_id] = str(row.get("status") or "")

    count = 0
    for call_id, reservation in reservations.items():
        if local_date is not None and str(reservation.get("local_date") or "") != local_date:
            continue
        if run_id is not None and str(reservation.get("run_id") or "") != run_id:
            continue
        status = completion_statuses.get(call_id)
        if status is None or status == "completed":
            count += 1
    return count


def write_status(payload: dict[str, Any]) -> None:
    AUTOMATION_ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    atomic_write_json(payload, STATUS_PATH)


def append_run(payload: dict[str, Any]) -> None:
    _append_jsonl(RUNS_PATH, payload)


def reserve_paid_call(
    *,
    run_id: str,
    stage: str,
    max_per_day: int | None = None,
    now: datetime | None = None,
) -> str:
    """Atomically hold one daily allowance slot before a provider request."""
    moment = now or utc_now()
    local_date = moment.astimezone(ZoneInfo(AUTOMATION_TIMEZONE)).date().isoformat()
    call_id = f"{run_id}_{stage}_{uuid4().hex[:8]}"
    with synchronized_path(CALL_JOURNAL_PATH):
        rows = _journal_rows_unlocked()
        daily = _allowance_calls(rows, local_date=local_date)
        if max_per_day is not None and daily >= int(max_per_day):
            raise RuntimeError(
                f"Paid-call daily ceiling reached ({daily}/{int(max_per_day)}) for {local_date}."
            )
        _append_jsonl_unlocked(CALL_JOURNAL_PATH, {
            "event": "reserved",
            "call_id": call_id,
            "run_id": run_id,
            "stage": stage,
            "at_utc": moment.isoformat(),
            "local_date": local_date,
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
    """Count in-flight reservations and completed responses that consume allowance."""
    with synchronized_path(CALL_JOURNAL_PATH):
        return _allowance_calls(_journal_rows_unlocked(), local_date=local_date)


def paid_calls_for_run(run_id: str) -> int:
    """Count allowance-consuming calls attributable to one automation run."""
    with synchronized_path(CALL_JOURNAL_PATH):
        return _allowance_calls(_journal_rows_unlocked(), run_id=str(run_id))


def request_attempts_for_run(run_id: str) -> int:
    """Count provider request attempts, including attempts that consumed no allowance."""
    with synchronized_path(CALL_JOURNAL_PATH):
        return len({
            str(row.get("call_id") or "")
            for row in _journal_rows_unlocked()
            if row.get("event") == "reserved" and str(row.get("run_id") or "") == str(run_id)
        })


def submitted_requests_for_run(run_id: str) -> int:
    """Count attempts for which the provider returned a response identifier."""
    with synchronized_path(CALL_JOURNAL_PATH):
        return len({
            str(row.get("call_id") or "")
            for row in _journal_rows_unlocked()
            if row.get("event") == "submitted" and str(row.get("run_id") or "") == str(run_id)
        })


def today_local_date(now: datetime | None = None) -> str:
    return (now or utc_now()).astimezone(ZoneInfo(AUTOMATION_TIMEZONE)).date().isoformat()
