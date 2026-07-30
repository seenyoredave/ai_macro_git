from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def _load_energy_loader():
    streamlit = types.ModuleType("streamlit")

    class CacheData:
        def __call__(self, *args, **kwargs):
            if args and callable(args[0]) and not kwargs:
                return args[0]
            return lambda function: function

    streamlit.cache_data = CacheData()
    old_streamlit = sys.modules.get("streamlit")
    sys.modules["streamlit"] = streamlit
    try:
        spec = importlib.util.spec_from_file_location(
            "energy_loader_policy_test",
            ROOT / "loaders" / "energy_loader.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if old_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = old_streamlit


def _fred_power_payload():
    return {
        "Electric Power Output": {
            "value": 110.0518,
            "date": "2026-06-01",
            "source": "FRED Archive",
        },
        "Electric Power Capacity": {
            "value": 159.8954,
            "date": "2026-06-01",
            "source": "FRED Archive",
        },
        "Electric Power Capacity Utilization": {
            "value": 68.8274,
            "date": "2026-06-01",
            "source": "FRED Archive",
        },
    }


def test_completed_energy_week_uses_friday_close_in_eastern_time():
    loader = _load_energy_loader()

    before_cutoff = datetime(2026, 7, 31, 19, 59, tzinfo=timezone.utc)
    assert loader.completed_energy_week(before_cutoff).isoformat() == "2026-07-24"

    at_cutoff = datetime(2026, 7, 31, 20, 0, tzinfo=timezone.utc)
    assert loader.completed_energy_week(at_cutoff).isoformat() == "2026-07-31"

    weekend = datetime(2026, 8, 1, 18, 0, tzinfo=timezone.utc)
    assert loader.completed_energy_week(weekend).isoformat() == "2026-07-31"


def test_energy_weekly_decision_matrix():
    loader = _load_energy_loader()
    assert loader.energy_load_decision(
        force_refresh=True,
        has_current_archive=True,
        has_any_archive=True,
    ) == "manual_live"
    assert loader.energy_load_decision(
        force_refresh=False,
        has_current_archive=True,
        has_any_archive=True,
    ) == "archive_current_week"
    assert loader.energy_load_decision(
        force_refresh=False,
        has_current_archive=False,
        has_any_archive=True,
    ) == "automatic_live"
    assert loader.energy_load_decision(
        force_refresh=False,
        has_current_archive=False,
        has_any_archive=False,
    ) == "bootstrap_live"


def test_energy_loader_uses_complete_current_week_archive_without_public_request():
    loader = _load_energy_loader()
    loader.completed_energy_week = lambda: pd.Timestamp("2026-07-24").date()
    loader.load_energy_history = lambda: pd.read_csv(ROOT / "archive" / "energy_history.csv")
    loader._load_local_history = lambda: pd.read_csv(
        ROOT / "data" / "energy_series_history.csv"
    ).assign(Date=lambda frame: pd.to_datetime(frame["Date"]))

    def fail_request():
        raise AssertionError("Current-week archive should suppress the public request")

    loader._fetch_public_energy_history = fail_request
    result = loader._load_energy_data_cached(
        force_refresh=False,
        refresh_token=0,
        clock_token="2026-07-24",
    )

    assert result["source_mode"] == "archive_current_week"
    assert result["series"]["Natural Gas Price"]["value"] == 2.86
    assert result["series"]["WTI Crude Oil"]["value"] == 88.58


def test_incomplete_current_week_archive_does_not_suppress_refresh():
    loader = _load_energy_loader()
    loader.completed_energy_week = lambda: pd.Timestamp("2026-07-31").date()
    loader.load_energy_history = lambda: pd.DataFrame(
        [{"Date": "2026-07-31", "Natural Gas Price": 3.25}]
    )
    loader._load_local_history = lambda: loader._empty_history()
    loader._persist_local_history = lambda frame: None
    called = {"value": False}

    def fetch():
        called["value"] = True
        return pd.DataFrame(
            [
                {"Date": "2026-07-31", "Series": name, "Value": 100.0}
                for name in loader.ENERGY_PUBLIC_SERIES
            ]
        )

    loader._fetch_public_energy_history = fetch
    result = loader._load_energy_data_cached(
        force_refresh=False,
        refresh_token=0,
        clock_token="2026-07-31",
    )
    assert called["value"] is True
    assert result["source_mode"] == "live_weekly"


def test_seeded_energy_history_and_existing_fred_power_data_populate_all_metrics():
    loader = _load_energy_loader()
    loader.completed_energy_week = lambda: pd.Timestamp("2026-07-24").date()
    result = loader.load_energy_data(
        fred_data=_fred_power_payload(),
        clock_token="2026-07-24",
    )

    assert set(result["series"]) == set(loader.ENERGY_SERIES)
    assert result["load_report"]["returned_series"] == 7
    for name, payload in result["series"].items():
        assert np.isfinite(float(payload["value"])), name
        assert payload["date"], name
    assert np.isfinite(result["series"]["Natural Gas Price"]["change_pct"])
    assert np.isfinite(result["series"]["Coal Production"]["change_pct"])
    assert np.isfinite(result["series"]["Electric Power Output"]["change_pct"])


def test_source_failure_uses_seeded_history_and_reports_the_exception():
    loader = _load_energy_loader()
    loader.completed_energy_week = lambda: pd.Timestamp("2026-07-31").date()
    loader.load_energy_history = lambda: pd.DataFrame()
    loader._fetch_public_energy_history = lambda: (_ for _ in ()).throw(
        RuntimeError("simulated source outage")
    )

    result = loader._load_energy_data_cached(
        force_refresh=False,
        refresh_token=0,
        clock_token="2026-07-31",
    )
    assert result["source_mode"] == "local_history_fallback"
    assert result["load_report"]["returned_series"] == 4
    assert result["load_report"]["error"] == "RuntimeError: simulated source outage"


def test_energy_tab_has_no_fake_weekly_metric_and_uses_refresh_button():
    app = (ROOT / "ai_macro.py").read_text()
    renderer = (ROOT / "research_overlay" / "renderers.py").read_text()
    definitions = (ROOT / "config" / "metric_definitions.py").read_text()

    assert '["AI MACRO", "FINANCE", "ENERGY", "SECTORS", "EVIDENCE"]' in app
    assert 'st.button("Refresh Energy"' in app
    assert "load_energy_data(" in app
    assert "fred_data=fred_data" in app
    assert "append_energy_history(energy_data)" in app
    assert 'render_tab_header(\n        "Energy"' in renderer
    for section in (
        "Energy supply",
        "Power production",
        "Grid capacity",
        "AI energy demand",
    ):
        assert f'render_section("{section}"' in renderer

    authored = "\n".join([app, renderer, definitions, (ROOT / "README.md").read_text()])
    retired = "trip" + "wire"
    assert retired not in authored.lower()


def test_energy_archive_has_seeded_current_values_and_no_retired_columns():
    archive = pd.read_csv(ROOT / "archive" / "energy_history.csv")
    assert not archive.empty
    assert archive.iloc[-1]["Date"] == "2026-07-24"
    assert archive.iloc[-1]["Natural Gas Price"] == 2.86
    assert archive.iloc[-1]["WTI Crude Oil"] == 88.58
    retired = "trip" + "wire"
    assert not any(retired in column.lower() for column in archive.columns)


def test_energy_renderer_executes_all_sections_without_runtime_error():
    streamlit = types.ModuleType("streamlit")

    class Context:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    streamlit.columns = lambda spec: [
        Context() for _ in range(spec if isinstance(spec, int) else len(spec))
    ]
    streamlit.container = lambda *args, **kwargs: Context()
    plotly_keys = set()

    def plotly_chart(*args, **kwargs):
        key = kwargs.get("key")
        if not key:
            raise AssertionError("Every Energy plotly_chart must have an explicit key")
        if key in plotly_keys:
            raise AssertionError(f"Duplicate Energy plotly_chart key: {key}")
        plotly_keys.add(key)

    streamlit.plotly_chart = plotly_chart
    streamlit.markdown = lambda *args, **kwargs: None
    streamlit.dataframe = lambda *args, **kwargs: None

    old_streamlit = sys.modules.get("streamlit")
    sys.modules["streamlit"] = streamlit
    try:
        spec = importlib.util.spec_from_file_location(
            "energy_renderer_smoke_test",
            ROOT / "research_overlay" / "renderers.py",
        )
        renderer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(renderer)

        renderer.render_tab_header = lambda *args, **kwargs: None
        renderer.render_line_break = lambda *args, **kwargs: None
        renderer._render_tab_metric_registry = lambda *args, **kwargs: None
        renderer.render_section = lambda *args, **kwargs: None
        renderer.render_statline = lambda *args, **kwargs: None
        renderer.render_static_table = lambda *args, **kwargs: None
        renderer.render_panel_heading = lambda *args, **kwargs: None

        history = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2026-06-01", "2026-07-01"]),
                "Value": [100.0, 102.0],
            }
        )
        energy_data = {
            "source_mode": "archive_current_week",
            "snapshot_date": "2026-07-24",
            "series": {
                name: {
                    "value": 100.0,
                    "date": "2026-07-01",
                    "change_pct": 2.0,
                    "history": history.copy(),
                }
                for name in renderer.ENERGY_SERIES
            },
        }
        energy_data["series"]["Natural Gas Price"]["value"] = 3.25
        energy_data["series"]["WTI Crude Oil"]["value"] = 72.0
        energy_data["series"]["Electric Power Utilization"]["value"] = 61.0

        regime_metrics = {
            "Power Stress Index": 4.0,
            "Power Capacity Gap": 8.0,
            "Power Capacity Gap Source": "FRED Archive",
            "Power Capacity Gap Components": {
                "components": {
                    "Delivered Power Growth": {
                        "raw": 0.013,
                        "score": 48.0,
                        "channel": "Power-System Response",
                    },
                    "Installed Capacity Growth": {
                        "raw": 0.039,
                        "score": 52.0,
                        "channel": "Power-System Response",
                    },
                    "Data Center Construction": {
                        "score": 70.0,
                        "channel": "Deployment Pressure",
                    },
                    "Capital Deployment": {
                        "score": 65.0,
                        "channel": "Deployment Pressure",
                    },
                }
            },
            "Power Stress Components": {
                "footprint_score": 58.0,
                "footprint_components": {
                    "Commercial Load Growth": {
                        "score": 58.0,
                        "raw": 3.0,
                    }
                },
            },
        }
        dashboard_data = {
            "trends": {
                "power_capacity_gap_trend": {
                    "history": history.copy(),
                }
            }
        }

        renderer.render_energy_tab({}, regime_metrics, energy_data, dashboard_data)
        assert len(plotly_keys) == 8
    finally:
        if old_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = old_streamlit


def test_evidence_tab_executes_energy_source_table_without_runtime_error():
    streamlit = types.ModuleType("streamlit")

    class Context:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    streamlit.expander = lambda *args, **kwargs: Context()
    streamlit.markdown = lambda *args, **kwargs: None
    streamlit.caption = lambda *args, **kwargs: None

    old_streamlit = sys.modules.get("streamlit")
    sys.modules["streamlit"] = streamlit
    try:
        spec = importlib.util.spec_from_file_location(
            "energy_evidence_renderer_smoke_test",
            ROOT / "research_overlay" / "renderers.py",
        )
        renderer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(renderer)

        renderer.render_tab_header = lambda *args, **kwargs: None
        renderer.render_line_break = lambda *args, **kwargs: None
        renderer.render_section = lambda *args, **kwargs: None
        renderer.render_definition = lambda *args, **kwargs: None
        renderer.render_macro_data = lambda *args, **kwargs: None
        renderer.render_edgar_data = lambda *args, **kwargs: None

        rendered_tables = []
        renderer.render_static_table = lambda frame, **kwargs: rendered_tables.append(frame)

        energy_data = {
            "source_mode": "archive_current_week",
            "series": {
                name: {
                    "value": 100.0,
                    "date": "2026-07-24",
                    "change_pct": 2.5,
                    "unit": spec["unit"],
                    "source": "Energy archive",
                }
                for name, spec in renderer.ENERGY_SERIES.items()
            },
        }

        renderer.render_evidence_tab({}, {}, {}, energy_data, {})

        assert rendered_tables
        source_table = rendered_tables[0]
        assert len(source_table) == len(renderer.ENERGY_SERIES)
        assert list(source_table.columns) == [
            "Series",
            "Reading",
            "Change",
            "Observation Date",
            "Source",
        ]
    finally:
        if old_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = old_streamlit


def test_power_history_is_backfilled_for_multi_year_energy_charts():
    history = pd.read_csv(ROOT / "data" / "power_series_history.csv")
    dates = pd.to_datetime(history["Observation Date"], errors="coerce")

    assert len(history) >= 130
    assert dates.min() <= pd.Timestamp("2015-01-01")
    assert dates.max() >= pd.Timestamp("2026-06-01")
    for column in (
        "Electric Power Output",
        "Electric Power Capacity",
        "Electric Power Capacity Utilization",
    ):
        assert pd.to_numeric(history[column], errors="coerce").notna().sum() >= 130


def test_energy_grid_capacity_uses_concrete_response_readings_and_growth_history():
    renderer_source = (ROOT / "research_overlay" / "renderers.py").read_text()

    assert '"Output growth"' in renderer_source
    assert '"Capacity growth"' in renderer_source
    assert '"Capacity utilization"' in renderer_source
    assert 'render_panel_heading("Power-system response", "12-month change")' in renderer_source
    assert 'key="energy-grid-capacity-growth"' in renderer_source
    assert 'value_suffix="%"' in renderer_source


def test_year_over_year_power_history_spans_multiple_cycles():
    streamlit = types.ModuleType("streamlit")
    old_streamlit = sys.modules.get("streamlit")
    sys.modules["streamlit"] = streamlit
    try:
        spec = importlib.util.spec_from_file_location(
            "energy_growth_history_test",
            ROOT / "research_overlay" / "renderers.py",
        )
        renderer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(renderer)

        raw = pd.read_csv(ROOT / "data" / "power_series_history.csv")
        item = {
            "history": raw[["Observation Date", "Electric Power Output"]].rename(
                columns={"Observation Date": "Date", "Electric Power Output": "Value"}
            )
        }
        growth = renderer._year_over_year_history(item)

        assert not growth.empty
        assert growth["Date"].min() <= pd.Timestamp("2016-01-01")
        assert growth["Date"].max() >= pd.Timestamp("2026-06-01")
        assert np.isfinite(growth["Value"]).all()
    finally:
        if old_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = old_streamlit
