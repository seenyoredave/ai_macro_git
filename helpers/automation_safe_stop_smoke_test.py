"""No-network contract for an intentional zero-paid automation dry-run stop."""
from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpers.streamlit_runtime_stub import install_streamlit_stub
install_streamlit_stub()

try:
    import yfinance  # noqa: F401
except ModuleNotFoundError:
    import types
    sys.modules["yfinance"] = types.ModuleType("yfinance")
try:
    import fredapi  # noqa: F401
except ModuleNotFoundError:
    import types
    module = types.ModuleType("fredapi")
    module.Fred = type("Fred", (), {})
    sys.modules["fredapi"] = module

from automation import runner
from automation.research_refresh import RefreshBundle
import automation.research_refresh as research_refresh


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    env_keys = (
        "AI_MACRO_MODE",
        "AI_MACRO_TRIGGER",
        "AI_MACRO_AUTOMATION_ENABLED",
        "OPENAI_AUTOMATION_ENABLED",
        "AUTO_PUBLISH",
        "AI_MACRO_MANUAL_ALLOW_PAID",
        "AI_MACRO_MANUAL_ALLOW_PUBLISH",
        "FRED_API_KEY",
        "SEC_USER_AGENT",
    )
    old_env = {key: os.environ.get(key) for key in env_keys}
    originals = {
        "refresh": research_refresh.refresh_research_state,
        "blocking": research_refresh.blocking_refresh_errors,
        "warnings": research_refresh.refresh_warnings,
        "artifact": runner._current_artifact_valid,
        "write": runner.write_status,
        "append": runner.append_run,
        "paid": runner.paid_calls_for_local_date,
    }
    captured: list[dict] = []
    try:
        os.environ.update({
            "AI_MACRO_MODE": "automation",
            "AI_MACRO_TRIGGER": "workflow_dispatch",
            "AI_MACRO_AUTOMATION_ENABLED": "true",
            "OPENAI_AUTOMATION_ENABLED": "true",
            "AUTO_PUBLISH": "false",
            "AI_MACRO_MANUAL_ALLOW_PAID": "false",
            "AI_MACRO_MANUAL_ALLOW_PUBLISH": "false",
            "FRED_API_KEY": "test-fred",
            "SEC_USER_AGENT": "AI Macro test@example.com",
        })
        research_refresh.refresh_research_state = lambda: RefreshBundle(
            context=object(),
            reports={"current_context": {"snapshot_id": "context-test"}},
            snapshot_write_report={"errors": {}},
            timings={"mock refresh": 0.01},
        )
        research_refresh.blocking_refresh_errors = lambda _bundle: []
        research_refresh.refresh_warnings = lambda _bundle: []
        runner._current_artifact_valid = lambda _context: (False, "evidence-test", {"status": "stale"})
        runner.write_status = lambda status: captured.append(dict(status))
        runner.append_run = lambda _status: None
        runner.paid_calls_for_local_date = lambda _date: 0

        code = runner.main()
        _check(code == 0, "Intentional zero-paid dry-run stop still returns a failing exit code.")
        _check(captured, "Dry-run status was not emitted.")
        final = captured[-1]
        _check(final.get("result") == "openai_disabled_for_changed_evidence", "Dry-run stop reason changed unexpectedly.")
        _check(not final.get("errors"), "Expected dry-run stop is still recorded as an error.")
        _check((final.get("warnings") or []), "Expected dry-run stop is not visible as a warning.")
        _check(int((final.get("paid_calls") or {}).get("this_run", -1)) == 0, "Zero-paid dry run recorded a paid call.")
    finally:
        research_refresh.refresh_research_state = originals["refresh"]
        research_refresh.blocking_refresh_errors = originals["blocking"]
        research_refresh.refresh_warnings = originals["warnings"]
        runner._current_artifact_valid = originals["artifact"]
        runner.write_status = originals["write"]
        runner.append_run = originals["append"]
        runner.paid_calls_for_local_date = originals["paid"]
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    print("PASS  automation dry run · changed evidence · zero paid calls · clean exit")


if __name__ == "__main__":
    main()
