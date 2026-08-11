"""Contracts for bounded unattended publication."""

from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpers.streamlit_runtime_stub import install_streamlit_stub
install_streamlit_stub()

# This contract inspects automation policy only; provider SDKs are not exercised.
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

from automation import budget
from automation.budget import BudgetedOpenAIClient, PaidCallBudgetExceeded, PaidCallGuard
from automation.config import (
    AUTOMATION_START_LOCAL,
    AUTOMATION_TIMEZONE,
    HARD_MAX_PAID_CALLS_PER_DAY,
    HARD_MAX_PAID_CALLS_PER_RUN,
    load_automation_config,
)
from config.deployment import current_context_paths, repository_writes_enabled
from automation.research_refresh import RefreshBundle, blocking_refresh_errors, refresh_warnings
import loaders.current_context_daily as daily


class _Responses:
    def __init__(self) -> None:
        self.calls = 0

    def parse(self, *args, **kwargs):
        self.calls += 1
        return {"ok": True}


class _Client:
    def __init__(self) -> None:
        self.responses = _Responses()


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ai_macro_automation.yml").read_text(encoding="utf-8")
    runner = (ROOT / "automation" / "runner.py").read_text(encoding="utf-8")
    app = (ROOT / "ai_macro.py").read_text(encoding="utf-8")
    daily_source = (ROOT / "loaders" / "current_context_daily.py").read_text(encoding="utf-8")

    _check(AUTOMATION_TIMEZONE == "America/New_York", "Automation timezone drifted from Eastern Time.")
    _check(AUTOMATION_START_LOCAL == "09:00", "Automation start time drifted from 09:00 Eastern.")
    _check("cron: '0 9 * * *'" in workflow and "timezone: 'America/New_York'" in workflow, "Scheduled workflow is not 09:00 Eastern daily.")
    _check("workflow_dispatch:" in workflow and "allow_paid:" in workflow and "publish:" in workflow, "Manual workflow lacks explicit paid/publish opt-ins.")
    _check("concurrency:" in workflow and "cancel-in-progress: false" in workflow, "Automation workflow can overlap or cancel active publication work.")
    _check("permissions:" in workflow and "contents: write" in workflow, "Workflow lacks explicit publication permission.")
    _check("FRED_API_KEY: ${{ secrets.FRED_API_KEY }}" in workflow, "Workflow does not pass the FRED repository secret into the automation worker.")
    _check("SEC_USER_AGENT: ${{ vars.SEC_USER_AGENT }}" in workflow, "Workflow does not pass the SEC user-agent repository variable into the automation worker.")
    _check("_runtime_configuration_errors" in runner and "FRED_API_KEY is not configured for the automation worker." in runner, "Automation worker does not fail closed when FRED credentials are missing.")
    _check("SEC_USER_AGENT is not configured for the automation worker." in runner, "Automation worker does not fail closed when SEC identification is missing.")
    action_lines = [line.strip() for line in workflow.splitlines() if line.strip().startswith("uses: actions/")]
    _check(len(action_lines) == 3, "Automation workflow action dependency count changed unexpectedly.")
    _check(all("@" in line and len(line.split("@", 1)[1].split()[0]) == 40 for line in action_lines), "GitHub-owned actions are not pinned to full immutable commit SHAs.")
    _check("max_retries=0" in runner, "Automation OpenAI client does not explicitly disable SDK retries.")
    _check("_configure_runtime_warnings" in runner and "Cannot parse header or footer" in runner, "Automation logs do not suppress the known non-data openpyxl warning.")
    _check("subphases" in runner and "bundle.timings" in runner, "Automation status does not retain refresh phase timings.")
    _check("Refresh timings" in workflow, "GitHub run summary does not surface refresh phase timings.")
    _check("scheduled_paid_generation_requires_AUTO_PUBLISH" in runner, "Scheduled automation can spend on an unpublished draft.")
    _check("result=\"openai_disabled_for_changed_evidence\"" in runner and "return 0" in runner, "Expected zero-paid dry-run stop is still treated as a workflow failure.")
    _check("steps.decision.outputs.result != 'disabled'" in workflow, "Disabled scheduled runs can create no-op ledger commits.")
    _check("generate_validated_read_artifact" in runner, "Automation bypasses the validated commentary service.")
    _check("publish_ready" in runner and "transaction_boundary" in runner, "Runner lacks an explicit publication decision boundary.")

    _check("load_public_shared_context_snapshot" not in app, "Public app still contains live Current Context refresh logic.")
    _check("load_public_shared_context_snapshot" not in daily_source, "Retired public Current Context refresher still exists.")
    _check("@st.cache_data" not in daily_source, "Current Context public cache can still execute discovery providers.")

    old_mode = os.environ.get("AI_MACRO_MODE")
    try:
        os.environ["AI_MACRO_MODE"] = "public"
        _check(not repository_writes_enabled(), "Public Reader can write retained research state.")
        _check(current_context_paths()["registry"] == ROOT / "data" / "weekly_context_events.csv", "Public Reader is not reading the canonical retained Current Context registry.")
        original_refresh = daily.refresh_current_context
        daily.refresh_current_context = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider call"))
        snapshot = daily.load_retained_context_snapshot(as_of="2026-08-10")
        _check(isinstance(snapshot.get("current_context"), dict), "Retained public Current Context snapshot did not load.")
        daily.refresh_current_context = original_refresh

        os.environ["AI_MACRO_MODE"] = "automation"
        _check(repository_writes_enabled(), "Automation worker cannot write retained state.")
    finally:
        if old_mode is None:
            os.environ.pop("AI_MACRO_MODE", None)
        else:
            os.environ["AI_MACRO_MODE"] = old_mode

    old_run = os.environ.get("AI_MACRO_MAX_PAID_CALLS_PER_RUN")
    old_day = os.environ.get("AI_MACRO_MAX_PAID_CALLS_PER_DAY")
    try:
        os.environ["AI_MACRO_MAX_PAID_CALLS_PER_RUN"] = "999"
        os.environ["AI_MACRO_MAX_PAID_CALLS_PER_DAY"] = "999"
        cfg = load_automation_config()
        _check(cfg.max_paid_calls_per_run == HARD_MAX_PAID_CALLS_PER_RUN == 2, "Run call ceiling can be raised above the hard limit.")
        _check(cfg.max_paid_calls_per_day == HARD_MAX_PAID_CALLS_PER_DAY == 4, "Daily call ceiling can be raised above the hard limit.")
    finally:
        if old_run is None:
            os.environ.pop("AI_MACRO_MAX_PAID_CALLS_PER_RUN", None)
        else:
            os.environ["AI_MACRO_MAX_PAID_CALLS_PER_RUN"] = old_run
        if old_day is None:
            os.environ.pop("AI_MACRO_MAX_PAID_CALLS_PER_DAY", None)
        else:
            os.environ["AI_MACRO_MAX_PAID_CALLS_PER_DAY"] = old_day

    degraded = RefreshBundle(
        context=None,
        reports={
            "finance": {"source_mode": "retained_fallback", "error": "provider unavailable"},
            "adoption": {"source_mode": "partial_refresh", "errors": {"consumer": "temporary miss"}},
            "current_context": {"source_mode": "retained", "refresh_status": "retained"},
            "snapshot_write": {},
        },
        snapshot_write_report={"errors": {}},
    )
    _check(not blocking_refresh_errors(degraded), "Valid retained/partial fallbacks block the entire automation release.")
    warning_text = " | ".join(refresh_warnings(degraded))
    _check("provider unavailable" in warning_text and "temporary miss" in warning_text, "Fallback degradation is not visible in the automation ledger.")
    unavailable = RefreshBundle(
        context=None,
        reports={"finance": {"source_mode": "unavailable", "error": "no valid retained state"}},
        snapshot_write_report={"errors": {}},
    )
    _check(blocking_refresh_errors(unavailable), "Unavailable required research state did not block publication.")
    broken_write = RefreshBundle(
        context=None,
        reports={},
        snapshot_write_report={"errors": {"archive": "atomic write failed"}},
    )
    _check(blocking_refresh_errors(broken_write), "Snapshot transaction failure did not block publication.")

    original_daily = budget.paid_calls_for_local_date
    original_reserve = budget.reserve_paid_call
    original_complete = budget.complete_paid_call
    try:
        budget.paid_calls_for_local_date = lambda _date: 0
        counter = {"value": 0}
        def fake_reserve(**kwargs):
            counter["value"] += 1
            return f"call-{counter['value']}"
        budget.reserve_paid_call = fake_reserve
        budget.complete_paid_call = lambda **kwargs: None
        guard = PaidCallGuard("test-run", 2, 4)
        client = BudgetedOpenAIClient(_Client(), guard)
        client.responses.parse(text_format=type("GeneratedDomainReadSet", (), {}))
        client.responses.parse(text_format=type("GeneratedMacroRead", (), {}))
        try:
            client.responses.parse(text_format=type("GeneratedMacroRead", (), {}))
        except PaidCallBudgetExceeded:
            pass
        else:
            raise AssertionError("A third paid call was allowed inside one automation run.")
    finally:
        budget.paid_calls_for_local_date = original_daily
        budget.reserve_paid_call = original_reserve
        budget.complete_paid_call = original_complete

    print("PASS  automation · retained-only public Reader · 09:00 Eastern · 2/run · 4/day · zero SDK retries")


if __name__ == "__main__":
    main()
