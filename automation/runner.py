"""Run one bounded AI Macro automation transaction.

The Git repository is the publication boundary: this command updates only the
working tree.  The GitHub Actions workflow commits research state only when this
runner reports a fully validated, publish-ready result.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback
from typing import Any

from automation.config import (
    AUTOMATION_START_LOCAL,
    AUTOMATION_TIMEZONE,
    AutomationConfig,
    load_automation_config,
)
from automation.ledger import (
    AUTOMATION_ARTIFACT_ROOT,
    append_run,
    new_run_id,
    paid_calls_for_local_date,
    today_local_date,
    write_status,
)


def _install_headless_streamlit() -> None:
    from helpers.streamlit_runtime_stub import install_streamlit_stub

    install_streamlit_stub()


def _git_changed_paths(root: Path) -> list[str]:
    if not (root / ".git").exists():
        return []
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    paths: list[str] = []
    for line in proc.stdout.splitlines():
        raw = line[3:].strip()
        if " -> " in raw:
            raw = raw.split(" -> ", 1)[1]
        if raw:
            paths.append(raw)
    return paths


def _unexpected_changes(paths: list[str]) -> list[str]:
    allowed_prefixes = ("data/", "archive/", "automation_artifacts/")
    allowed_exact = {"openai_artifacts/current.json"}
    return [
        path for path in paths
        if path not in allowed_exact and not path.startswith(allowed_prefixes)
    ]


def _base_status(*, run_id: str, config: AutomationConfig, started_at: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "trigger": config.trigger,
        "schedule": {"time": AUTOMATION_START_LOCAL, "timezone": AUTOMATION_TIMEZONE},
        "started_at_utc": started_at,
        "finished_at_utc": "",
        "result": "running",
        "publish_ready": False,
        "automation_enabled": config.enabled,
        "openai_enabled": config.openai_enabled,
        "auto_publish": config.auto_publish,
        "paid_calls": {
            "this_run": 0,
            "today_before_run": paid_calls_for_local_date(today_local_date()),
            "run_ceiling": config.max_paid_calls_per_run,
            "daily_ceiling": config.max_paid_calls_per_day,
        },
        "phases": {},
        "errors": [],
    }


def _finish(status: dict[str, Any], *, result: str, publish_ready: bool = False) -> None:
    status["result"] = result
    status["publish_ready"] = bool(publish_ready)
    status["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    today = today_local_date()
    status["paid_calls"]["today_after_run"] = paid_calls_for_local_date(today)
    status["paid_calls"]["this_run"] = max(
        0,
        int(status["paid_calls"]["today_after_run"]) - int(status["paid_calls"]["today_before_run"]),
    )
    write_status(status)
    append_run(status)
    print(json.dumps(status, indent=2, sort_keys=True, default=str))


def _current_artifact_valid(context: Any) -> tuple[bool, str, dict[str, Any]]:
    from analytics.read_evidence import build_evidence_packets, evidence_snapshot_id
    from analytics.read_service import build_platform_reads

    packets = build_evidence_packets(context)
    snapshot = evidence_snapshot_id(packets)
    _, commentary = build_platform_reads(context)
    return commentary.get("status") == "validated", snapshot, dict(commentary)


def _runtime_configuration_errors() -> list[str]:
    errors: list[str] = []
    if not str(os.getenv("FRED_API_KEY", "") or "").strip():
        errors.append("FRED_API_KEY is not configured for the automation worker.")
    sec_user_agent = str(os.getenv("SEC_USER_AGENT", "") or "").strip()
    if not sec_user_agent:
        errors.append("SEC_USER_AGENT is not configured for the automation worker.")
    return errors


def _generate_commentary(context: Any, config: AutomationConfig, run_id: str) -> dict[str, Any]:
    from openai import OpenAI

    from analytics.read_service import generate_validated_read_artifact
    from automation.budget import BudgetedOpenAIClient, PaidCallGuard
    from config.openai_config import load_openai_config

    if config.max_paid_calls_per_run < 2:
        raise RuntimeError("Full unattended commentary generation requires a two-call run allowance.")
    used_today = paid_calls_for_local_date(today_local_date())
    if used_today + 2 > config.max_paid_calls_per_day:
        raise RuntimeError(
            f"Insufficient daily paid-call allowance for a complete generation: "
            f"{used_today}/{config.max_paid_calls_per_day} already reserved."
        )

    openai_config = load_openai_config()
    if not openai_config.configured:
        raise RuntimeError("OPENAI_API_KEY is not configured for the automation worker.")

    raw_client = OpenAI(
        api_key=openai_config.api_key,
        max_retries=0,
        timeout=config.openai_timeout_seconds,
    )
    guard = PaidCallGuard(
        run_id=run_id,
        max_per_run=config.max_paid_calls_per_run,
        max_per_day=config.max_paid_calls_per_day,
    )
    client = BudgetedOpenAIClient(raw_client, guard)
    return generate_validated_read_artifact(
        context,
        openai_config,
        client=client,
        persist=True,
    )


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    config = load_automation_config()
    run_id = new_run_id()
    started_at = datetime.now(timezone.utc).isoformat()
    status = _base_status(run_id=run_id, config=config, started_at=started_at)
    write_status(status)

    if not config.enabled:
        status["phases"]["automation"] = {"status": "disabled"}
        _finish(status, result="disabled")
        return 0

    if str(os.getenv("AI_MACRO_MODE", "")).strip().lower() != "automation":
        status["errors"].append("AI_MACRO_MODE must be automation for unattended writes.")
        _finish(status, result="configuration_failed")
        return 2

    runtime_errors = _runtime_configuration_errors()
    if runtime_errors:
        status["phases"]["configuration"] = {"status": "failed", "errors": runtime_errors}
        status["errors"].extend(runtime_errors)
        _finish(status, result="configuration_failed")
        return 2

    try:
        _install_headless_streamlit()
        from automation.research_refresh import blocking_refresh_errors, refresh_research_state, refresh_warnings

        status["phases"]["deterministic_refresh"] = {"status": "running"}
        bundle = refresh_research_state()
        warnings = refresh_warnings(bundle)
        if warnings:
            status["warnings"] = warnings
        refresh_failures = blocking_refresh_errors(bundle)
        if refresh_failures:
            status["phases"]["deterministic_refresh"] = {
                "status": "failed",
                "errors": refresh_failures,
            }
            status["errors"].extend(refresh_failures)
            _finish(status, result="deterministic_refresh_failed")
            return 2
        status["phases"]["deterministic_refresh"] = {"status": "passed"}
        status["current_context_snapshot_id"] = str(
            ((bundle.reports.get("current_context") or {}).get("snapshot_id") or "")
        )

        artifact_valid, evidence_snapshot, commentary = _current_artifact_valid(bundle.context)
        status["evidence_snapshot_id"] = evidence_snapshot
        status["phases"]["evidence"] = {
            "status": "passed",
            "artifact_current": artifact_valid,
            "artifact_status": str(commentary.get("status") or "unknown"),
        }

        if artifact_valid:
            status["phases"]["openai"] = {
                "status": "skipped",
                "reason": "evidence_snapshot_already_has_validated_artifact",
            }
        else:
            # Scheduled runs never spend money merely to create a draft that
            # automation is not authorized to publish.  Manual workflow runs
            # may explicitly opt into a paid validation-only rehearsal.
            if config.trigger == "schedule" and not config.auto_publish:
                status["phases"]["openai"] = {
                    "status": "blocked",
                    "reason": "scheduled_paid_generation_requires_AUTO_PUBLISH",
                }
                status["errors"].append(
                    "Analytical evidence changed, but scheduled publication is disabled; no OpenAI call was made."
                )
                _finish(status, result="scheduled_publish_disabled_for_changed_evidence")
                return 2

            if not config.openai_enabled:
                status["phases"]["openai"] = {
                    "status": "blocked",
                    "reason": "OPENAI_AUTOMATION_ENABLED is false or manual paid opt-in is absent",
                }
                status["errors"].append(
                    "Analytical evidence changed but autonomous OpenAI spending is disabled."
                )
                _finish(status, result="openai_disabled_for_changed_evidence")
                return 2

            status["phases"]["openai"] = {"status": "running"}
            generation = _generate_commentary(bundle.context, config, run_id)
            status["phases"]["openai"] = {
                "status": str(generation.get("status") or "unknown"),
                "stage": str(generation.get("stage") or ""),
                "attempt_id": str(generation.get("attempt_id") or ""),
                "validation": generation.get("validation") or {},
            }
            if generation.get("status") != "validated":
                status["errors"].append(
                    f"Commentary publication gate rejected the paid attempt at {generation.get('stage', 'unknown')} stage."
                )
                _finish(status, result="commentary_validation_failed")
                return 2

            artifact_valid, regenerated_snapshot, commentary = _current_artifact_valid(bundle.context)
            if not artifact_valid or regenerated_snapshot != evidence_snapshot:
                status["errors"].append(
                    "Validated generation did not produce a current artifact for the refreshed evidence snapshot."
                )
                _finish(status, result="publication_verification_failed")
                return 2

        changed = _git_changed_paths(root)
        unexpected = _unexpected_changes(changed)
        status["changed_paths"] = changed
        if unexpected:
            status["errors"].append("Unexpected working-tree changes: " + ", ".join(unexpected))
            _finish(status, result="unexpected_file_change")
            return 2

        if not config.auto_publish:
            status["phases"]["publication"] = {
                "status": "withheld",
                "reason": "AUTO_PUBLISH is false or manual publish opt-in is absent",
            }
            _finish(status, result="validated_publication_withheld")
            return 0

        status["phases"]["publication"] = {
            "status": "ready",
            "transaction_boundary": "git_commit",
        }
        _finish(status, result="validated_publish_ready", publish_ready=True)
        return 0
    except Exception as exc:
        status["errors"].append(f"{type(exc).__name__}: {exc}")
        status["traceback_tail"] = traceback.format_exc().splitlines()[-12:]
        _finish(status, result="exception")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
