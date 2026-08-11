"""Regression contract for batched official FRED history refreshes."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from loaders import official_series_refresh as series_refresh


class _Response:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    calls: list[dict] = []
    original_get = series_refresh.requests.get
    original_mode = os.environ.get("AI_MACRO_MODE")
    try:
        os.environ["AI_MACRO_MODE"] = "automation"

        csv_bytes = (
            b"observation_date,SERIES_A,SERIES_B,SERIES_C\n"
            b"2026-01-01,1.0,2.0,3.0\n"
            b"2026-02-01,1.5,2.5,3.5\n"
        )

        def fake_get(url, *, params, timeout, headers):
            calls.append({"url": url, "params": dict(params), "timeout": timeout, "headers": dict(headers)})
            return _Response(csv_bytes)

        series_refresh.requests.get = fake_get
        frames = series_refresh.fetch_fred_series_batch(["SERIES_A", "SERIES_B", "SERIES_C"])
        _check(len(calls) == 1, "Batched FRED fetch made more than one network request.")
        _check(calls[0]["params"]["id"] == "SERIES_A,SERIES_B,SERIES_C", "FRED batch IDs were not combined into one request.")
        _check(calls[0]["timeout"] == series_refresh.AUTOMATION_TIMEOUT == 12, "Automation FRED timeout is not bounded at 12 seconds.")
        _check(set(frames) == {"SERIES_A", "SERIES_B", "SERIES_C"}, "Batched FRED response did not preserve all series.")
        _check(float(frames["SERIES_B"].iloc[-1]["Value"]) == 2.5, "Batched FRED parser changed numeric observations.")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.csv"
            retained = pd.DataFrame(
                [
                    {"Series ID": sid, "Date": "2025-12-01", "Value": value, "Label": sid, "Unit": "Index"}
                    for sid, value in (("SERIES_A", 0.5), ("SERIES_B", 1.5), ("SERIES_C", 2.5))
                ]
            )
            retained.to_csv(path, index=False)
            calls.clear()
            combined, report = series_refresh.refresh_templated_history(
                path,
                required_columns=("Label", "Unit"),
            )
            _check(len(calls) == 1, "Templated history refresh reverted to one request per series.")
            _check(report.get("network_requests") == 1, "Templated history report does not expose its single batch request.")
            _check(report.get("source_mode") == "live_refresh", "Successful batch refresh did not report live_refresh.")
            _check(len(report.get("refreshed_series") or []) == 3, "Successful batch refresh did not retain per-series reporting.")
            _check(len(combined) == 6, "Batched history refresh did not replace chronology for all three series.")
    finally:
        series_refresh.requests.get = original_get
        if original_mode is None:
            os.environ.pop("AI_MACRO_MODE", None)
        else:
            os.environ["AI_MACRO_MODE"] = original_mode

    print("PASS  official FRED series refresh · one request per history · 12s automation timeout")


if __name__ == "__main__":
    main()
