"""Run one bounded AI Macro automation transaction.

The Git repository is the publication boundary: this command updates only the
working tree.  The GitHub Actions workflow commits research state only when this
runner reports a completed, publishable result.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import warnings
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


def _configure_runtime_warnings() -> None:
    # Several official XLSX files contain print-header/footer markup that
    # openpyxl cannot parse. AI Macro does not consume that print metadata, so
    # suppress only this known non-data warning in unattended logs.
    warnings.filterwarnings(
        "ignore",
        message=r"Cannot parse header or footer so it will be ignored",
        category=UserWarning,
        module=r"openpyxl\.worksheet\.header_footer",
    )


def _log(label: str) -> None:
    print(f"[automation] {label}", flush=True)


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
    print(json.dumps(status, indent=2, sort_keys=True, default=str), flush=True)


def _current_artifact_valid(context: Any) -> tuple[bool, str, dict[str, Any]]:
    from analytics.read_evidence import build_evidence_packets, evidence_snapshot_id
    from analytics.read_service import build_platform_reads

    packets = build_evidence_packets(context)
    snapshot = evidence_snapshot_id(packets)
    _, commentary = build_platform_reads(context)
    strict_evidence_match = bool(commentary.get("artifact_publishable") and commentary.get("evidence_current"))
    return strict_evidence_match, snapshot, dict(commentary)


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
        _configure_runtime_warnings()
        _install_headless_streamlit()
        _log(f"run {run_id} · trigger={config.trigger} · paid={config.openai_enabled} · publish={config.auto_publish}")
        from automation.research_refresh import blocking_refresh_errors, refresh_research_state, refresh_warnings

        status["phases"]["deterministic_refresh"] = {"status": "running"}
        refresh_started = time.perf_counter()
        bundle = refresh_research_state()
        refresh_elapsed = max(0.0, time.perf_counter() - refresh_started)
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
        status["phases"]["deterministic_refresh"] = {
            "status": "passed",
            "elapsed_sec": round(refresh_elapsed, 3),
            "subphases": dict(bundle.timings),
        }
        _log(f"deterministic refresh complete · {refresh_elapsed:.1f}s")
        status["current_context_snapshot_id"] = str(
            ((bundle.reports.get("current_context") or {}).get("snapshot_id") or "")
        )

        # Retained-state freshness advances only for files whose content hash
        # actually changed during this deterministic refresh.  This ledger is
        # later used by desktop-to-Git reconciliation; it never authorizes I/O.
        from automation.retained_state import refresh_retained_state_manifest
        refresh_retained_state_manifest(source="automation_refresh", run_id=run_id)

        # The release fingerprint includes critical retained data.  Keep it in
        # lock-step with every publishable automation refresh.
        from helpers.build_release_manifest import build_manifest
        from helpers.atomic_io import atomic_write_json
        atomic_write_json(build_manifest(), root / "data" / "release_manifest.json")

        _log("START evidence comparison")
        evidence_started = time.perf_counter()
        artifact_valid, evidence_snapshot, commentary = _current_artifact_valid(bundle.context)
        from analytics.read_materiality import compare_evidence_materiality
        from analytics.read_store import load_read_artifact

        stored_artifact = load_read_artifact()
        materiality = compare_evidence_materiality(
            stored_artifact.get("evidence_packets"),
            commentary.get("packets"),
            previous_snapshot_id=str(stored_artifact.get("evidence_snapshot_id") or ""),
            current_snapshot_id=evidence_snapshot,
        )
        reusable_artifact = bool(
            commentary.get("artifact_publishable")
            and not materiality.get("material")
        )
        evidence_elapsed = max(0.0, time.perf_counter() - evidence_started)
        status["evidence_snapshot_id"] = evidence_snapshot
        status["phases"]["evidence"] = {
            "status": "passed",
            "artifact_current": artifact_valid,
            "artifact_materially_current": reusable_artifact,
            "artifact_status": str(commentary.get("status") or "unknown"),
            "materiality": materiality,
            "elapsed_sec": round(evidence_elapsed, 3),
        }
        _log(
            f"DONE  evidence comparison · {evidence_elapsed:.1f}s · "
            f"exact={artifact_valid} · material={bool(materiality.get('material'))}"
        )

        if reusable_artifact:
            reuse_reason = (
                "evidence_snapshot_already_has_publishable_artifact"
                if artifact_valid
                else "evidence_change_below_materiality_threshold"
            )
            status["phases"]["openai"] = {
                "status": "skipped",
                "reason": reuse_reason,
            }
            if config.auto_publish:
                from analytics.read_service import reapply_last_read

                renewal_source = "automation_reapply" if artifact_valid else "automation_immaterial_reapply"
                renewed = reapply_last_read(
                    persist=True,
                    source=renewal_source,
                    current_evidence_snapshot_id=evidence_snapshot,
                    materiality=materiality,
                    evidence_packets=commentary.get("packets") if artifact_valid else None,
                )
                publication = dict(renewed.get("publication") or {})
                status["phases"]["publication_lease"] = {
                    "status": "renewed",
                    "reason": (
                        "publishable_evidence_unchanged_no_paid_call"
                        if artifact_valid
                        else "publishable_evidence_change_immaterial_no_paid_call"
                    ),
                    "published_at": str(publication.get("published_at") or ""),
                    "expires_at": str(publication.get("expires_at") or ""),
                }
                _log(f"publication lease renewed · no OpenAI call · {reuse_reason}")
            else:
                status["phases"]["publication_lease"] = {
                    "status": "withheld",
                    "reason": "AUTO_PUBLISH is false or manual publish opt-in is absent",
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
                status.setdefault("warnings", []).append(
                    "Analytical evidence changed, but scheduled publication is disabled; no OpenAI call was made."
                )
                _finish(status, result="scheduled_publish_disabled_for_changed_evidence")
                return 0

            if not config.openai_enabled:
                status["phases"]["openai"] = {
                    "status": "blocked",
                    "reason": "OPENAI_AUTOMATION_ENABLED is false or manual paid opt-in is absent",
                }
                status.setdefault("warnings", []).append(
                    "Analytical evidence changed but autonomous OpenAI spending is disabled."
                )
                _finish(status, result="openai_disabled_for_changed_evidence")
                return 0

            status["phases"]["openai"] = {"status": "running"}
            _log("START bounded OpenAI generation")
            openai_started = time.perf_counter()
            generation = _generate_commentary(bundle.context, config, run_id)
            openai_elapsed = max(0.0, time.perf_counter() - openai_started)
            status["phases"]["openai"] = {
                "status": str(generation.get("status") or "unknown"),
                "stage": str(generation.get("stage") or ""),
                "attempt_id": str(generation.get("attempt_id") or ""),
                "validation": generation.get("validation") or {},
                "elapsed_sec": round(openai_elapsed, 3),
            }
            _log(f"DONE  bounded OpenAI generation · {openai_elapsed:.1f}s · status={generation.get('status')}")
            if generation.get("status") not in {"validated", "published_with_warnings", "published_raw_response"}:
                status["errors"].append(
                    f"OpenAI generation did not return a publishable response at {generation.get('stage', 'unknown')} stage."
                )
                _finish(status, result="commentary_generation_failed")
                return 2

            artifact_valid, regenerated_snapshot, commentary = _current_artifact_valid(bundle.context)
            if not artifact_valid or regenerated_snapshot != evidence_snapshot:
                status["errors"].append(
                    "Generation did not produce a current publishable artifact for the refreshed evidence snapshot."
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
            _finish(status, result="publication_withheld")
            return 0

        status["phases"]["publication"] = {
            "status": "ready",
            "transaction_boundary": "git_commit",
        }
        _finish(status, result="publish_ready", publish_ready=True)
        return 0
    except Exception as exc:
        status["errors"].append(f"{type(exc).__name__}: {exc}")
        status["traceback_tail"] = traceback.format_exc().splitlines()[-12:]
        _finish(status, result="exception")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
