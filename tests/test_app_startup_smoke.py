"""Execute the complete app entry point with deterministic source stubs.

This is intentionally a top-level smoke test rather than a source-text assertion.
It catches runtime ordering failures such as referencing a value before the
function that creates it has returned.
"""

from __future__ import annotations

import runpy
import sys
import types
from datetime import date
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


class _SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class _CacheData:
    def __call__(self, *args, **kwargs):
        if args and callable(args[0]) and not kwargs:
            return args[0]
        return lambda function: function

    def clear(self):
        return None


def _streamlit_stub():
    module = types.ModuleType("streamlit")
    module.session_state = _SessionState()
    module.sidebar = _Context()
    module.cache_data = _CacheData()
    module.secrets = {}
    module.set_page_config = lambda *args, **kwargs: None
    module.markdown = lambda *args, **kwargs: None
    module.caption = lambda *args, **kwargs: None
    module.write = lambda *args, **kwargs: None
    module.button = lambda *args, **kwargs: False
    module.rerun = lambda: None
    module.tabs = lambda labels: [_Context() for _ in labels]
    return module


def _module(name, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def test_streamlit_entry_point_completes_first_render(monkeypatch):
    sector_frame = pd.DataFrame({"Ticker": ["AAA"]})
    raw_universe = {
        "_load_report": {
            "total_elapsed_sec": 0.0,
            "yfinance": {"source_mode": "archive_current"},
            "edgar": {"source_mode": "archive_current"},
        },
        "edgar": {},
    }
    benchmark = {
        "source_mode": "archive_market_closed",
        "archive_date": "2026-07-29",
    }

    st = _streamlit_stub()
    stubs = {
        "streamlit": st,
        "analytics.factor_engine": _module(
            "analytics.factor_engine",
            calc_sector_factors=lambda **kwargs: pd.DataFrame(),
        ),
        "analytics.macro_interpretation": _module(
            "analytics.macro_interpretation",
            build_macro_interpretation=lambda **kwargs: {
                "headline": "Resilient",
                "summary": "Deterministic startup state.",
                "pressure_factors": [],
                "resilience_factors": [],
                "changes": [],
                "domains": {},
                "confidence": "high",
                "version": "1.0",
            },
        ),
        "analytics.regime_engine": _module(
            "analytics.regime_engine",
            build_regime_metrics=lambda **kwargs: {},
        ),
        "analytics.sector_engine": _module(
            "analytics.sector_engine",
            build_sector_metrics=lambda *args, **kwargs: {},
        ),
        "archive.archive": _module(
            "archive.archive",
            append_benchmark_history=lambda *args, **kwargs: None,
            append_edgar_history=lambda *args, **kwargs: None,
            append_energy_history=lambda *args, **kwargs: None,
            append_fred_history=lambda *args, **kwargs: None,
            append_macro_history=lambda *args, **kwargs: None,
            append_sector_history=lambda *args, **kwargs: None,
            append_yf_history=lambda *args, **kwargs: None,
        ),
        "archive.archive_reader": _module(
            "archive.archive_reader",
            load_fred_history=lambda: pd.DataFrame(),
            load_macro_history=lambda: pd.DataFrame(),
        ),
        "benchmarks.benchmark_service": _module(
            "benchmarks.benchmark_service",
            get_benchmark_metrics=lambda *args, **kwargs: benchmark.copy(),
        ),
        "config.market_clock": _module(
            "config.market_clock",
            market_date=lambda *args, **kwargs: date(2026, 7, 29),
        ),
        "config.sector_config": _module(
            "config.sector_config",
            SECTOR_CONFIG={"Compute": {"basket": ["AAA"]}},
        ),
        "helpers.render_sector": _module(
            "helpers.render_sector",
            render_basket_tier_developer_tool=lambda *args, **kwargs: None,
        ),
        "loaders.construction_loader": _module(
            "loaders.construction_loader",
            load_data_center_construction=lambda: pd.DataFrame(),
        ),
        "loaders.debt_markets_loader": _module(
            "loaders.debt_markets_loader",
            load_debt_markets_data=lambda *args, **kwargs: {
                "source_mode": "archive_current_release",
                "snapshot_date": "2026-07-24",
                "series": {},
                "history": pd.DataFrame(),
                "load_report": {
                    "source_mode": "archive_current_release",
                    "elapsed_sec": 0.0,
                    "returned_series": 0,
                },
            },
        ),
        "loaders.edgar_loader": _module(
            "loaders.edgar_loader",
            build_edgar_archive_snapshot=lambda *args, **kwargs: {},
        ),
        "loaders.energy_loader": _module(
            "loaders.energy_loader",
            load_energy_data=lambda *args, **kwargs: {
                "source_mode": "archive_current_week",
                "snapshot_date": "2026-07-25",
                "series": {},
                "load_report": {
                    "source_mode": "archive_current_week",
                    "decision": "archive_current_week",
                    "elapsed_sec": 0.0,
                    "returned_series": 0,
                },
            },
        ),
        "loaders.fred_loader": _module(
            "loaders.fred_loader",
            load_fred=lambda: {},
        ),
        "loaders.market_loader": _module(
            "loaders.market_loader",
            load_market_universe=lambda *args, **kwargs: raw_universe.copy(),
        ),
        "loaders.nfci_loader": _module(
            "loaders.nfci_loader",
            load_nfci_history=lambda: pd.DataFrame(),
        ),
        "research_overlay.components": _module(
            "research_overlay.components",
            render_masthead=lambda *args, **kwargs: None,
        ),
        "research_overlay.renderers": _module(
            "research_overlay.renderers",
            render_research_dashboard=lambda *args, **kwargs: None,
        ),
        "research_overlay.theme": _module(
            "research_overlay.theme",
            inject_research_theme=lambda: None,
        ),
        "sectors.sector_builder": _module(
            "sectors.sector_builder",
            get_sector_data=lambda *args, **kwargs: sector_frame.copy(),
        ),
    }

    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)

    namespace = runpy.run_path(str(ROOT / "ai_macro.py"), run_name="__main__")

    assert namespace["APP_VERSION"] == "v4.09"
    assert namespace["benchmark_metrics"]["source_mode"] == "archive_market_closed"
    assert st.session_state.force_rebuild is False
    assert "sector_data" in st.session_state
    assert "regime_metrics" in st.session_state
    assert "energy_data" in st.session_state
    assert "debt_markets_data" in st.session_state
