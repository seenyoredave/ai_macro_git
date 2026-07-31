from pathlib import Path

import pandas as pd

from analytics.macro_interpretation import build_macro_interpretation
from loaders.weekly_context_loader import load_weekly_context


ROOT = Path(__file__).resolve().parents[1]


def _write_registry(path):
    pd.DataFrame(
        [
            {
                "event_id": "finance-a",
                "event_date": "2026-07-29",
                "domain": "finance",
                "event_type": "policy",
                "priority": 100,
                "verified_fact": "The policy rate was unchanged",
                "platform_relevance": "The financing backdrop did not ease",
                "source_name": "Agency A",
                "source_label": "Policy decision",
                "source_url": "https://agency.example/policy",
                "source_type": "primary",
                "verification_status": "confirmed",
                "expires_after_days": 7,
            },
            {
                "event_id": "finance-b",
                "event_date": "2026-07-30",
                "domain": "finance",
                "event_type": "credit",
                "priority": 95,
                "verified_fact": "A credit measure changed",
                "platform_relevance": "Financing conditions remained mixed",
                "source_name": "Agency B",
                "source_label": "Credit release",
                "source_url": "https://agency.example/credit",
                "source_type": "primary",
                "verification_status": "confirmed",
                "expires_after_days": 7,
            },
            {
                "event_id": "validation-a",
                "event_date": "2026-07-30",
                "domain": "validation",
                "event_type": "macro_release",
                "priority": 80,
                "verified_fact": "A macro estimate was released",
                "platform_relevance": "Measured demand remained positive",
                "source_name": "Agency C",
                "source_label": "Macro release",
                "source_url": "https://agency.example/macro",
                "source_type": "primary",
                "verification_status": "confirmed",
                "expires_after_days": 7,
            },
            {
                "event_id": "secondary",
                "event_date": "2026-07-30",
                "domain": "market",
                "event_type": "story",
                "priority": 120,
                "verified_fact": "A story was published",
                "platform_relevance": "It should not enter the registry",
                "source_name": "Publisher",
                "source_label": "Story",
                "source_url": "https://publisher.example/story",
                "source_type": "secondary",
                "verification_status": "confirmed",
                "expires_after_days": 7,
            },
        ]
    ).to_csv(path, index=False)


def _regime():
    return {
        "AI Equity Index": 60.0,
        "AI Development Intensity": 80.0,
        "Economic Validation Gap": -30.0,
        "Power Stress Index": 0.0,
        "Power Capacity Gap": 5.0,
        "Borrower Strain": 0.0,
        "Lender Strain": 0.0,
        "Speculation Gap": -10.0,
        "AEI Version": "3.1",
        "ADI Version": "1.0",
        "EVG Version": "2.0",
        "Power Stress Version": "3.0",
        "Power Capacity Gap Version": "1.0",
        "Borrower Strain Version": "3.0",
        "Lender Strain Version": "3.0",
        "Deployment Funding Mix": {
            "current": {
                "internal_funding_coverage": 1.5,
                "cash_reserve_coverage_years": 1.2,
                "debt_financing_pulse": 0.1,
                "forward_commitment_load": 1.0,
            },
            "series": {},
        },
    }


def test_weekly_context_prefers_domain_diversity_and_builds_references(tmp_path):
    registry = tmp_path / "events.csv"
    _write_registry(registry)

    result = load_weekly_context(as_of="2026-07-30", path=registry, limit=2)

    assert [event["event_id"] for event in result["events"]] == [
        "finance-a",
        "validation-a",
    ]
    assert [reference["reference_number"] for reference in result["references"]] == [1, 2]
    assert result["events"][0]["display"] == (
        "The policy rate was unchanged. The financing backdrop did not ease."
    )
    assert all(event["source_type"] == "primary" for event in result["events"])


def test_weekly_context_leads_snapshot_and_exposes_only_used_sources(tmp_path):
    registry = tmp_path / "events.csv"
    _write_registry(registry)
    context = load_weekly_context(as_of="2026-07-30", path=registry, limit=2)

    result = build_macro_interpretation(
        regime_metrics=_regime(),
        macro_history=pd.DataFrame(),
        weekly_context=context,
    )

    assert result["summary"] == ""
    assert result["changes"][0].endswith("[1]")
    assert result["changes"][1].endswith("[2]")
    assert len(result["weekly_references"]) == 2
    assert result["weekly_references"][0]["source_label"] == "Policy decision"
    assert result["weekly_context"]["version"] == "1.0"


def test_snapshot_renderer_uses_this_week_and_source_links_below_columns():
    source = (ROOT / "research_overlay" / "renderers.py").read_text()
    block = source.split("def _render_weekly_references", 1)[1].split(
        "def _render_primary_macro_cards", 1
    )[0]

    assert '"This week"' in block
    assert 'class="rm-state-summary"' not in block
    assert "_render_weekly_references(interpretation.get(\"weekly_references\"))" in block
    assert 'target="_blank"' in block
    assert "References" in block


def test_bundled_weekly_registry_uses_confirmed_primary_sources():
    frame = pd.read_csv(ROOT / "data" / "weekly_context_events.csv")

    assert not frame.empty
    assert frame["source_type"].eq("primary").all()
    assert frame["verification_status"].eq("confirmed").all()
    assert frame["source_url"].str.startswith("https://").all()
    assert frame["source_label"].astype(str).str.strip().ne("").all()
