from __future__ import annotations

import ast
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import sys
import types

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


class _CacheData:
    def __call__(self, *args, **kwargs):
        if args and callable(args[0]) and not kwargs:
            return args[0]
        return lambda function: function


def _load_module():
    streamlit = types.ModuleType("streamlit")
    streamlit.cache_data = _CacheData()
    previous = sys.modules.get("streamlit")
    sys.modules["streamlit"] = streamlit
    try:
        spec = importlib.util.spec_from_file_location(
            "debt_markets_loader_test_module",
            ROOT / "loaders" / "debt_markets_loader.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = previous


def test_cmdi_release_gate_uses_last_wednesday_at_10am_eastern():
    module = _load_module()
    before = datetime.fromisoformat("2026-07-29T09:59:00-04:00")
    after = datetime.fromisoformat("2026-07-29T10:00:00-04:00")

    assert module.completed_debt_market_release(before).isoformat() == "2026-06-24"
    assert module.completed_debt_market_release(after).isoformat() == "2026-07-29"


def test_bundled_cmdi_history_is_complete_and_current_for_release():
    history = pd.read_csv(ROOT / "data" / "debt_markets_history.csv")
    metadata = json.loads((ROOT / "data" / "debt_markets_metadata.json").read_text())

    assert len(history) >= 1100
    assert pd.to_datetime(history["Date"]).min() <= pd.Timestamp("2005-01-07")
    assert pd.to_datetime(history["Date"]).max() >= pd.Timestamp("2026-07-24")
    assert metadata["release_date"] == "2026-07-29"
    for column in (
        "Corporate Bond Market Distress",
        "Investment-Grade Bond Distress",
        "High-Yield Bond Distress",
    ):
        assert pd.to_numeric(history[column], errors="coerce").notna().sum() >= 1100


def test_current_release_uses_archive_without_network(monkeypatch, tmp_path):
    module = _load_module()
    history_path = tmp_path / "debt_markets_history.csv"
    metadata_path = tmp_path / "debt_markets_metadata.json"
    pd.DataFrame(
        {
            "Date": ["2026-07-24"],
            "Corporate Bond Market Distress": [0.15],
            "Investment-Grade Bond Distress": [0.30],
            "High-Yield Bond Distress": [0.10],
        }
    ).to_csv(history_path, index=False)
    metadata_path.write_text(json.dumps({"release_date": "2026-07-29"}))

    monkeypatch.setattr(module, "DEBT_MARKETS_HISTORY_PATH", history_path)
    monkeypatch.setattr(module, "DEBT_MARKETS_METADATA_PATH", metadata_path)
    monkeypatch.setattr(
        module,
        "completed_debt_market_release",
        lambda now=None: pd.Timestamp("2026-07-29").date(),
    )
    monkeypatch.setattr(
        module,
        "_fetch_history",
        lambda: (_ for _ in ()).throw(AssertionError("network should not be called")),
    )

    payload = module.load_debt_markets_data(clock_token="2026-07-29")

    assert payload["source_mode"] == "archive_current_release"
    assert payload["load_report"]["returned_series"] == 3
    assert payload["series"]["Corporate Bond Market Distress"]["value"] == 0.15


def test_manual_refresh_bypasses_release_gate(monkeypatch, tmp_path):
    module = _load_module()
    history_path = tmp_path / "debt_markets_history.csv"
    metadata_path = tmp_path / "debt_markets_metadata.json"
    pd.DataFrame(
        {
            "Date": ["2026-07-24"],
            "Corporate Bond Market Distress": [0.15],
            "Investment-Grade Bond Distress": [0.30],
            "High-Yield Bond Distress": [0.10],
        }
    ).to_csv(history_path, index=False)
    metadata_path.write_text(json.dumps({"release_date": "2026-07-29"}))

    refreshed = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-07-31"]),
            "Corporate Bond Market Distress": [0.20],
            "Investment-Grade Bond Distress": [0.31],
            "High-Yield Bond Distress": [0.16],
        }
    )
    calls = {"count": 0}

    def fetch():
        calls["count"] += 1
        return refreshed

    monkeypatch.setattr(module, "DEBT_MARKETS_HISTORY_PATH", history_path)
    monkeypatch.setattr(module, "DEBT_MARKETS_METADATA_PATH", metadata_path)
    monkeypatch.setattr(
        module,
        "completed_debt_market_release",
        lambda now=None: pd.Timestamp("2026-07-29").date(),
    )
    monkeypatch.setattr(module, "_fetch_history", fetch)

    payload = module.load_debt_markets_data(
        force_refresh=True,
        refresh_token=1,
        clock_token="2026-07-29",
    )

    assert calls["count"] == 1
    assert payload["source_mode"] == "live_manual"
    assert payload["series"]["Corporate Bond Market Distress"]["value"] == 0.20
    assert json.loads(metadata_path.read_text())["release_date"] == "2026-07-29"


def test_every_registry_entry_has_one_definition_and_no_section_titles():
    definitions_module = {}
    exec((ROOT / "config" / "metric_definitions.py").read_text(), definitions_module)
    definitions = definitions_module["METRIC_DEFINITIONS"]

    tree = ast.parse((ROOT / "research_overlay" / "renderers.py").read_text())
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "TAB_METRIC_REGISTRIES" for target in node.targets)
    )
    registries = ast.literal_eval(assignment.value)
    entries = [name for registry in registries.values() for name in registry]

    for registry in registries.values():
        assert len(registry) == len(set(registry))
    assert set(entries) == set(definitions) - {"Purpose Statement"}
    for forbidden in (
        "AI Economy Snapshot",
        "Gap Scores",
        "Current Sector Assessment",
        "Credit Conditions",
        "Debt Markets",
        "Financial Conditions Confirmation",
    ):
        assert forbidden not in entries
        assert forbidden not in definitions
    for name in entries:
        assert "How to read it" in definitions[name]


def test_finance_source_metadata_is_horizontal_and_nfci_schedule_is_clean():
    source = (ROOT / "research_overlay" / "renderers.py").read_text()
    source_helper = source.split(
        "def _financial_condition_source_stat", 1
    )[1].split("def _render_primary_macro_cards", 1)[0]

    assert 'f"{live_sources} · {date_text}"' in source_helper
    assert "\\n" not in source_helper
    assert '"updated Wednesday at 8:30am ET"' in source
    assert "updated every Wednesday" not in source
