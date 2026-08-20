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
from automation.budget import BudgetedOpenAIClient, PaidCallGuard  # noqa: E402
from automation.ledger import paid_calls_for_local_date, today_local_date  # noqa: E402
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
        capsules={"capsules": []},
        prior_publication={},
        prior_analytical_state={},
        required_update_domains=[],
        candidate_update_domains=[],
        bootstrap=False,
        config=OpenAIConfig(api_key="test", max_output_tokens=12000),
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

            try:
                _run(
                    _TerminalResponse(response_id="resp_partial", status="incomplete", output_text="{partial"),
                    run_id="budget-partial-output",
                )
            except GenerationStageError:
                pass
            else:
                raise AssertionError("Incomplete terminal response did not fail")
            _check(paid_calls_for_local_date(date) == 2, "Returned output did not consume the response allowance")

            rows = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
            completed = [row for row in rows if row.get("event") == "completed"]
            _check([row.get("status") for row in completed] == ["completed", "error", "completed"], "Journal outcomes changed")

    print(json.dumps({
        "status": "PASS",
        "usable_output_counted": True,
        "no_output_released": True,
        "partial_output_counted": True,
    }, indent=2))


if __name__ == "__main__":
    main()
