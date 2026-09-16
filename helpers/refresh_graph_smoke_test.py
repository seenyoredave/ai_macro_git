"""Smoke tests for the dependency-aware research refresh planner."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from automation.refresh_graph import (
    NODE_INDEX,
    build_refresh_plan,
    load_refresh_graph_state,
    save_refresh_graph_state,
    stable_signature,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    start = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    triggers = {
        "yfinance": "2026-09-15",
        "edgar": "2026-09-15",
        "fred": "2026-09-15",
        "current_context": "2026-09-15",
        "power_supply": "2026-09-11",
        "nyfed": "2026-09-02",
    }
    plan = build_refresh_plan(
        now=start,
        state={"graph_version": "1.0.0", "nodes": {}},
        trigger_tokens=triggers,
        force_full=False,
    )
    _assert(all(plan.should_refresh(node_id) for node_id in NODE_INDEX), "bootstrap must refresh every node")

    yframe = pd.DataFrame({"Ticker": ["A", "B"], "Price": [10.0, 20.0]})
    plan.record(
        "yfinance",
        attempted_live=True,
        status="success",
        output_signature=stable_signature(yframe),
        elapsed_sec=1.0,
    )
    plan.record(
        "data_centers",
        attempted_live=True,
        status="success",
        output_signature=stable_signature({"campuses": [1, 2]}),
        elapsed_sec=1.0,
    )
    plan.record(
        "connectivity",
        attempted_live=True,
        status="success",
        output_signature=stable_signature({"ixps": 3}),
        elapsed_sec=1.0,
    )

    plan.record(
        "water",
        attempted_live=True,
        status="success",
        output_signature=stable_signature({"counties": 10}),
        elapsed_sec=1.0,
    )

    with tempfile.TemporaryDirectory() as directory:
        state_path = Path(directory) / "refresh_graph_state.json"
        save_refresh_graph_state(plan.state, path=state_path, now=start)
        loaded = load_refresh_graph_state(state_path)
        _assert(bool((loaded.get("nodes") or {}).get("yfinance")), "state round-trip lost yfinance")

        same_day = build_refresh_plan(
            now=start + timedelta(hours=1),
            state=loaded,
            trigger_tokens=triggers,
            force_full=False,
        )
        _assert(not same_day.should_refresh("yfinance"), "same release trigger should reuse retained yfinance")
        _assert(not same_day.should_refresh("data_centers"), "fresh structural node should remain retained")

        next_day_triggers = dict(triggers)
        next_day_triggers["yfinance"] = "2026-09-16"
        next_day = build_refresh_plan(
            now=start + timedelta(hours=12),
            state=loaded,
            trigger_tokens=next_day_triggers,
            force_full=False,
        )
        _assert(next_day.should_refresh("yfinance"), "new daily trigger must refresh yfinance")

        cadence = build_refresh_plan(
            now=start + timedelta(hours=43),
            state=loaded,
            trigger_tokens=triggers,
            force_full=False,
        )
        _assert(cadence.should_refresh("data_centers"), "structural cadence must eventually refresh")

        changed_plan = build_refresh_plan(
            now=start + timedelta(hours=2),
            state=loaded,
            trigger_tokens=triggers,
            force_full=False,
        )
        changed_plan.record(
            "data_centers",
            attempted_live=False,
            status="retained",
            output_signature=stable_signature({"campuses": [1, 2, 3]}),
            elapsed_sec=0.1,
        )
        _assert(changed_plan.node_changed("data_centers"), "semantic retained-state change was not detected")
        forced_dependents = changed_plan.force_dependents("data_centers")
        _assert(set(forced_dependents) == {"connectivity", "water"}, "unexpected data-center dependents")
        _assert(changed_plan.should_refresh("connectivity"), "dependency change must force connectivity")
        _assert(changed_plan.should_refresh("water"), "data-center change must refresh campus water context")

        failure = build_refresh_plan(
            now=start + timedelta(hours=20),
            state=loaded,
            trigger_tokens=next_day_triggers,
            force_full=False,
        )
        failure.record(
            "yfinance",
            attempted_live=True,
            status="failed",
            output_signature=stable_signature(yframe),
            elapsed_sec=2.0,
            error="provider unavailable",
        )
        backoff = build_refresh_plan(
            now=start + timedelta(hours=21),
            state=failure.state,
            trigger_tokens=next_day_triggers,
            force_full=False,
        )
        _assert(not backoff.should_refresh("yfinance"), "failed node ignored retry backoff")
        retry = build_refresh_plan(
            now=start + timedelta(hours=27),
            state=failure.state,
            trigger_tokens=next_day_triggers,
            force_full=False,
        )
        _assert(retry.should_refresh("yfinance"), "failed node did not become retry-eligible")

        bootstrap_failure = build_refresh_plan(
            now=start,
            state={"graph_version": "1.0.0", "nodes": {}},
            trigger_tokens=triggers,
            force_full=False,
        )
        bootstrap_failure.record(
            "compute",
            attempted_live=True,
            status="failed",
            output_signature=stable_signature({"retained": True}),
            elapsed_sec=1.0,
            error="provider unavailable",
        )
        bootstrap_backoff = build_refresh_plan(
            now=start + timedelta(hours=1),
            state=bootstrap_failure.state,
            trigger_tokens=triggers,
            force_full=False,
        )
        _assert(not bootstrap_backoff.should_refresh("compute"), "bootstrap failure ignored retry backoff")

        forced = build_refresh_plan(
            now=start + timedelta(minutes=10),
            state=loaded,
            trigger_tokens=triggers,
            force_full=True,
        )
        _assert(all(forced.should_refresh(node_id) for node_id in NODE_INDEX), "full refresh did not force all nodes")

    _assert(
        stable_signature(pd.DataFrame({"a": [1, 2]})) == stable_signature(pd.DataFrame({"a": [1, 2]})),
        "stable signatures are not deterministic",
    )
    _assert(
        stable_signature(pd.DataFrame({"a": [1, 2]})) != stable_signature(pd.DataFrame({"a": [1, 3]})),
        "stable signatures failed to detect data change",
    )
    print("refresh graph smoke test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
