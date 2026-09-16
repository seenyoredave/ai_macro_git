"""Deterministic smoke test for the canonical analytical observation store."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.canonical_store import (  # noqa: E402
    CANONICAL_SCHEMA_VERSION,
    canonical_metric_history,
    canonical_metric_sources,
    canonical_snapshot_as_of,
    canonical_snapshot_by_id,
    canonical_snapshot_diff,
    canonical_snapshot_history,
    canonical_snapshot_source_status,
    latest_canonical_snapshot,
    load_canonical_domain_states,
    persist_canonical_snapshot,
)
from analytics.dashboard_context import DashboardContext  # noqa: E402
from analytics.domain_state import DOMAIN_ORDER, DomainState  # noqa: E402
from analytics.read_evidence import EvidenceFact  # noqa: E402


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _context(value: float = 1.0) -> DashboardContext:
    states = {
        domain: DomainState(
            metrics={"smoke_value": value if domain == "market" else float(index + 1)},
            importance=float(10 + index),
        )
        for index, domain in enumerate(DOMAIN_ORDER)
    }
    return DashboardContext(
        domain_states=states,
        current_context={"snapshot_id": "context-smoke"},
    )


def main() -> None:
    # Canonical-only metadata must not perturb the established evidence packet
    # contract used by materiality and the persisted OpenAI artifact.
    fact = EvidenceFact(
        "market.example",
        "Example",
        0.5,
        "50.0%",
        unit="%",
        scale=100.0,
        digits=1,
    )
    _check(
        set(fact.to_dict()) == {"id", "label", "value", "display", "context"},
        "Canonical metric metadata leaked into the evidence artifact contract",
    )

    with tempfile.TemporaryDirectory(prefix="ai-macro-canonical-smoke-") as directory:
        root = Path(directory)
        first_context, first = persist_canonical_snapshot(
            _context(),
            observation_date="2026-09-15",
            run_id="smoke-1",
            publication_source="smoke_test",
            source_status={"market": {"source_mode": "test"}},
            root=root,
        )
        _check(first["status"] == "written", f"First canonical write failed: {first}")
        _check(first["schema_version"] == CANONICAL_SCHEMA_VERSION, "Canonical schema version changed")
        _check(first["metric_count"] == len(DOMAIN_ORDER), "Canonical metric count changed")
        _check(first_context.canonical_snapshot_id == first["snapshot_id"], "Context lost canonical snapshot identity")
        _check(set(first_context.domain_states) == set(DOMAIN_ORDER), "Canonical round trip lost a domain")

        paths = root / "data" / "canonical"
        expected_registries = {
            "metrics.parquet",
            "sources.parquet",
            "metric_sources.parquet",
        }
        _check(
            expected_registries.issubset({path.name for path in paths.iterdir()}),
            "Canonical registry Parquet set is incomplete",
        )
        observation_files = sorted((paths / "observations").rglob("*.parquet"))
        snapshot_files = sorted((paths / "snapshots").rglob("*.parquet"))
        _check(len(observation_files) == 1, "Canonical observation partition was not created")
        _check(len(snapshot_files) == 1, "Canonical snapshot partition was not created")

        _, duplicate = persist_canonical_snapshot(
            _context(),
            observation_date="2026-09-15",
            run_id="smoke-duplicate",
            publication_source="smoke_test",
            root=root,
        )
        _check(duplicate["status"] == "unchanged", "Same-day identical state was not idempotent")
        _check(duplicate["snapshot_id"] == first["snapshot_id"], "Idempotent snapshot identity changed")
        _check(
            len(list((paths / "observations").rglob("*.parquet"))) == 1,
            "Idempotent write created a duplicate observation partition",
        )
        _check(
            len(list((paths / "snapshots").rglob("*.parquet"))) == 1,
            "Idempotent write created a duplicate snapshot partition",
        )

        changed = _context(2.0)
        changed, second = persist_canonical_snapshot(
            changed,
            observation_date="2026-09-16",
            run_id="smoke-2",
            publication_source="smoke_test",
            root=root,
        )
        _check(second["status"] == "written", f"Second canonical write failed: {second}")
        _check(second["snapshot_id"] != first["snapshot_id"], "Point-in-time snapshot identity failed to advance")
        _check(
            len(list((paths / "observations").rglob("*.parquet"))) == 2,
            "Second state did not append an immutable observation partition",
        )
        _check(
            len(list((paths / "snapshots").rglob("*.parquet"))) == 2,
            "Second state did not append an immutable snapshot partition",
        )

        latest = latest_canonical_snapshot(root=root)
        _check(latest.get("snapshot_id") == second["snapshot_id"], "Latest canonical snapshot lookup is wrong")
        history_rows = canonical_snapshot_history(root=root, ascending=True)
        _check(
            history_rows["snapshot_id"].tolist() == [first["snapshot_id"], second["snapshot_id"]],
            "Canonical snapshot history ordering changed",
        )
        exact = canonical_snapshot_by_id(first["snapshot_id"], root=root)
        _check(exact.get("snapshot_id") == first["snapshot_id"], "Exact canonical snapshot lookup failed")
        source_status = canonical_snapshot_source_status(first["snapshot_id"], root=root)
        _check(
            (source_status.get("market") or {}).get("source_mode") == "test",
            "Canonical snapshot source-status payload changed",
        )
        metric_sources = canonical_metric_sources("market.smoke_value", root=root)
        _check(
            {"YFinance", "SEC EDGAR"}.issubset(set(metric_sources["source_label"].astype(str))),
            "Canonical metric source registry lookup failed",
        )
        states = load_canonical_domain_states(snapshot_id=second["snapshot_id"], root=root)
        _check(float(states["market"].metrics["smoke_value"]) == 2.0, "Canonical state round trip changed a numeric metric")

        history = canonical_metric_history("market.smoke_value", root=root)
        _check(len(history) == 2, f"Canonical metric history expected 2 snapshots, received {len(history)}")
        _check(set(history["display_value"].astype(str)) == {"1", "2"}, "Canonical display history changed")

        as_of = canonical_snapshot_as_of("2026-09-15", root=root)
        _check(as_of.get("snapshot_id") == first["snapshot_id"], "Point-in-time snapshot lookup changed")
        diff = canonical_snapshot_diff(first["snapshot_id"], second["snapshot_id"], root=root)
        market_change = diff.loc[diff["metric_id"].eq("market.smoke_value")].iloc[0]
        _check(bool(market_change["changed"]), "Canonical snapshot diff missed a changed metric")
        _check(float(market_change["delta_numeric"]) == 1.0, "Canonical numeric delta changed")

    print({
        "status": "PASS",
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "domains": len(DOMAIN_ORDER),
    })


if __name__ == "__main__":
    main()
