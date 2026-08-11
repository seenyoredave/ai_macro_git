"""Hard paid-call guard and zero-retry OpenAI client wrapper."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from automation.ledger import (
    complete_paid_call,
    paid_calls_for_local_date,
    reserve_paid_call,
    today_local_date,
)


class PaidCallBudgetExceeded(RuntimeError):
    pass


@dataclass(slots=True)
class PaidCallGuard:
    run_id: str
    max_per_run: int
    max_per_day: int
    calls_this_run: int = 0

    def reserve(self, stage: str) -> str:
        if self.calls_this_run >= self.max_per_run:
            raise PaidCallBudgetExceeded(
                f"Paid-call run ceiling reached ({self.calls_this_run}/{self.max_per_run})."
            )
        local_date = today_local_date()
        daily = paid_calls_for_local_date(local_date)
        if daily >= self.max_per_day:
            raise PaidCallBudgetExceeded(
                f"Paid-call daily ceiling reached ({daily}/{self.max_per_day}) for {local_date}."
            )
        call_id = reserve_paid_call(run_id=self.run_id, stage=stage)
        self.calls_this_run += 1
        return call_id


class _BudgetedResponses:
    def __init__(self, inner: Any, guard: PaidCallGuard) -> None:
        self._inner = inner
        self._guard = guard

    def parse(self, *args: Any, **kwargs: Any) -> Any:
        format_name = str(getattr(kwargs.get("text_format"), "__name__", ""))
        stage = "domain" if "Domain" in format_name else "macro" if "Macro" in format_name else "responses.parse"
        call_id = self._guard.reserve(stage)
        try:
            response = self._inner.parse(*args, **kwargs)
        except Exception as exc:
            complete_paid_call(
                call_id=call_id,
                run_id=self._guard.run_id,
                stage=stage,
                status="error",
                detail=f"{type(exc).__name__}: {exc}",
            )
            raise
        complete_paid_call(
            call_id=call_id,
            run_id=self._guard.run_id,
            stage=stage,
            status="completed",
        )
        return response


class BudgetedOpenAIClient:
    """Expose only the Responses surface used by AI Macro generation."""

    def __init__(self, inner: Any, guard: PaidCallGuard) -> None:
        self.responses = _BudgetedResponses(inner.responses, guard)
