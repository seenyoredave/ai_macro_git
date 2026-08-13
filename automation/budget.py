"""Hard paid-call guard and zero-retry OpenAI client wrapper."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from automation.ledger import (
    complete_paid_call,
    mark_paid_call_submitted,
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

    def release(self) -> None:
        """Release an in-run slot when a call returns no response."""
        self.calls_this_run = max(0, self.calls_this_run - 1)


class _BudgetedResponses:
    def __init__(self, inner: Any, guard: PaidCallGuard) -> None:
        self._inner = inner
        self._guard = guard
        self._pending: dict[str, tuple[str, str]] = {}

    @staticmethod
    def _status(response: Any) -> str:
        raw = getattr(response, "status", "")
        return str(getattr(raw, "value", raw) or "").strip().lower()

    def _release_call(self, *, call_id: str, stage: str, detail: str) -> None:
        complete_paid_call(
            call_id=call_id,
            run_id=self._guard.run_id,
            stage=stage,
            status="error",
            detail=detail,
        )
        self._guard.release()

    def parse(self, *args: Any, **kwargs: Any) -> Any:
        format_name = str(getattr(kwargs.get("text_format"), "__name__", ""))
        stage = "domain" if "Domain" in format_name else "macro" if "Macro" in format_name else "responses.parse"
        call_id = self._guard.reserve(stage)
        try:
            response = self._inner.parse(*args, **kwargs)
        except Exception as exc:
            self._release_call(
                call_id=call_id,
                stage=stage,
                detail=f"{type(exc).__name__}: {exc}",
            )
            raise

        response_id = str(getattr(response, "id", "") or "").strip()
        if not response_id:
            self._release_call(
                call_id=call_id,
                stage=stage,
                detail="OpenAI background submission returned no response ID.",
            )
            raise RuntimeError("OpenAI background submission returned no response ID.")

        self._pending[response_id] = (call_id, stage)
        mark_paid_call_submitted(
            call_id=call_id,
            run_id=self._guard.run_id,
            stage=stage,
            response_id=response_id,
            response_status=self._status(response),
        )
        return response

    def retrieve(self, response_id: str, *args: Any, **kwargs: Any) -> Any:
        """Retrieve the same background response without reserving a new call."""
        return self._inner.retrieve(response_id, *args, **kwargs)

    def cancel(self, response_id: str, *args: Any, **kwargs: Any) -> Any:
        """Forward cancellation; allowance accounting is finalized by abandon()."""
        return self._inner.cancel(response_id, *args, **kwargs)

    def commit(self, response_id: str) -> None:
        """Consume the allowance only after usable model output exists."""
        pending = self._pending.pop(str(response_id), None)
        if pending is None:
            return
        call_id, stage = pending
        complete_paid_call(
            call_id=call_id,
            run_id=self._guard.run_id,
            stage=stage,
            status="completed",
            detail=f"response_id={response_id}",
        )

    def abandon(self, response_id: str, *, detail: str = "") -> None:
        """Release a reservation when no usable model output was produced."""
        pending = self._pending.pop(str(response_id), None)
        if pending is None:
            return
        call_id, stage = pending
        self._release_call(
            call_id=call_id,
            stage=stage,
            detail=f"response_id={response_id}; {detail}"[:500],
        )


class BudgetedOpenAIClient:
    """Expose only the Responses surface used by AI Macro generation."""

    def __init__(self, inner: Any, guard: PaidCallGuard) -> None:
        self.responses = _BudgetedResponses(inner.responses, guard)
