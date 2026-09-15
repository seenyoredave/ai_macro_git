"""Verify the demonstrated response-only safety-allowance rule without network."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.read_generation import GenerationStageError, generate_editorial_synthesis  # noqa: E402
from analytics.read_models import GeneratedEditorialSynthesis  # noqa: E402
from automation.budget import BudgetedOpenAIClient, PaidCallBudgetExceeded, PaidCallGuard  # noqa: E402
from automation.ledger import (  # noqa: E402
    complete_paid_call,
    paid_calls_for_local_date,
    paid_calls_for_run,
    request_attempts_for_run,
    submitted_requests_for_run,
    today_local_date,
)
from config.openai_config import OpenAIConfig  # noqa: E402
from helpers.editorial_pipeline_smoke_test import _Response, _model_payload  # noqa: E402


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class _TerminalResponse:
    def __init__(self, *, response_id: str, status: str, output_text: str) -> None:
        self.id = response_id
        self.status = status
        self.model = "gpt-5.6"
        self.output_parsed = None
        self.output_text = output_text
        self.usage = {"input_tokens": 10, "output_tokens": int(bool(output_text)), "total_tokens": 11}

    def model_dump(self, **kwargs):
        return {
            "id": self.id,
            "status": self.status,
            "model": self.model,
            "output_text": self.output_text,
        }


class _InnerResponses:
    def __init__(self, response) -> None:
        self.response = response
        self.calls = 0

    def parse(self, **kwargs):
        self.calls += 1
        return self.response

    def retrieve(self, response_id: str, **kwargs):
        raise AssertionError("Terminal smoke responses must not be polled")

    def cancel(self, response_id: str, **kwargs):
        return None


class _InnerClient:
    def __init__(self, response) -> None:
        self.responses = _InnerResponses(response)


def _run(response, *, run_id: str) -> None:
    client = BudgetedOpenAIClient(
        _InnerClient(response),
        PaidCallGuard(run_id=run_id, max_per_run=1, max_per_day=3),
    )
    generate_editorial_synthesis(
        briefing={"candidate_domains": [], "findings": [], "recent_developments": []},
        config=OpenAIConfig(api_key="test"),
        client=client,
    )


def main() -> None:
    model = GeneratedEditorialSynthesis.model_validate(_model_payload())
    date = today_local_date()
    with TemporaryDirectory(prefix="ai_macro_budget_") as temp:
        journal = Path(temp) / "call_journal.jsonl"
        with patch("automation.ledger.CALL_JOURNAL_PATH", journal):
            _run(_Response(model), run_id="budget-success")
            _check(paid_calls_for_local_date(date) == 1, "Usable response did not consume one allowance")
            _check(paid_calls_for_run("budget-success") == 1, "Run-level allowance accounting changed")
            _check(request_attempts_for_run("budget-success") == 1, "Successful request attempt was not recorded")
            _check(submitted_requests_for_run("budget-success") == 1, "Successful provider submission was not recorded")

            try:
                _run(
                    _TerminalResponse(response_id="resp_no_output", status="failed", output_text=""),
                    run_id="budget-no-output",
                )
            except GenerationStageError:
                pass
            else:
                raise AssertionError("No-output terminal response did not fail")
            _check(paid_calls_for_local_date(date) == 1, "No-output call consumed the response allowance")
            _check(paid_calls_for_run("budget-no-output") == 0, "No-output response consumed run allowance")
            _check(request_attempts_for_run("budget-no-output") == 1, "Failed request attempt disappeared from audit history")
            _check(submitted_requests_for_run("budget-no-output") == 1, "Failed terminal response lost its provider submission record")

            try:
                _run(
                    _TerminalResponse(response_id="resp_partial", status="incomplete", output_text="{partial"),
                    run_id="budget-partial-output",
                )
            except GenerationStageError:
                pass
            else:
                raise AssertionError("Incomplete terminal response did not fail")
            _check(paid_calls_for_local_date(date) == 1, "Incomplete response consumed the completed-response allowance")
            _check(paid_calls_for_run("budget-partial-output") == 0, "Incomplete response consumed run allowance")
            _check(request_attempts_for_run("budget-partial-output") == 1, "Incomplete request attempt disappeared from audit history")
            _check(submitted_requests_for_run("budget-partial-output") == 1, "Incomplete response lost its provider submission record")

            try:
                _run(
                    _TerminalResponse(response_id="resp_unparseable", status="completed", output_text="{not-json"),
                    run_id="budget-unparseable",
                )
            except GenerationStageError:
                pass
            else:
                raise AssertionError("Unparseable completed response did not fail")
            _check(paid_calls_for_local_date(date) == 1, "Unparseable response consumed the usable-response allowance")
            _check(paid_calls_for_run("budget-unparseable") == 0, "Unparseable response consumed run allowance")
            _check(request_attempts_for_run("budget-unparseable") == 1, "Unparseable request attempt disappeared from audit history")

            # Releasing the response allowance must never create a second
            # OpenAI request opportunity inside the same automation run.
            one_request_client = BudgetedOpenAIClient(
                _InnerClient(_TerminalResponse(response_id="resp_one_request", status="failed", output_text="")),
                PaidCallGuard(run_id="one-request-only", max_per_run=1, max_per_day=3),
            )
            try:
                generate_editorial_synthesis(
                    briefing={"candidate_domains": [], "findings": [], "recent_developments": []},
                    config=OpenAIConfig(api_key="test"),
                    client=one_request_client,
                )
            except GenerationStageError:
                pass
            else:
                raise AssertionError("No-output request did not fail")
            try:
                generate_editorial_synthesis(
                    briefing={"candidate_domains": [], "findings": [], "recent_developments": []},
                    config=OpenAIConfig(api_key="test"),
                    client=one_request_client,
                )
            except PaidCallBudgetExceeded:
                pass
            else:
                raise AssertionError("A released allowance slot permitted a second OpenAI request in one run")

            # The daily allowance check and reservation are one journal-locked
            # transaction. A second run cannot reserve the same final slot.
            holder = PaidCallGuard(run_id="daily-holder", max_per_run=1, max_per_day=2)
            held_call = holder.reserve("editorial_synthesis")
            challenger = PaidCallGuard(run_id="daily-challenger", max_per_run=1, max_per_day=2)
            try:
                challenger.reserve("editorial_synthesis")
            except PaidCallBudgetExceeded:
                pass
            else:
                raise AssertionError("Daily allowance reservation was not atomic")
            complete_paid_call(
                call_id=held_call,
                run_id="daily-holder",
                stage="editorial_synthesis",
                status="error",
                detail="smoke-test release",
            )

            rows = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
            completed = [row for row in rows if row.get("event") == "completed"]
            _check(
                [row.get("status") for row in completed] == ["completed", "error", "error", "error", "error", "error"],
                "Journal outcomes changed",
            )

    print(json.dumps({
        "status": "PASS",
        "usable_output_counted": True,
        "no_output_released": True,
        "partial_output_released": True,
        "unparseable_output_released": True,
        "attempts_audited": True,
        "one_request_per_run": True,
        "daily_reservation_atomic": True,
    }, indent=2))


if __name__ == "__main__":
    main()
