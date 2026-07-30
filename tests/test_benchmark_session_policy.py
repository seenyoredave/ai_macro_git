import importlib.util
import sys
import types
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def _load_service_module():
    streamlit = types.ModuleType("streamlit")

    class CacheData:
        def __call__(self, *args, **kwargs):
            if args and callable(args[0]) and not kwargs:
                return args[0]
            return lambda func: func

    streamlit.cache_data = CacheData()

    benchmark_loader = types.ModuleType("loaders.benchmark_loader")
    benchmark_loader.load_benchmark = lambda *args, **kwargs: pd.DataFrame()

    old_streamlit = sys.modules.get("streamlit")
    old_loader = sys.modules.get("loaders.benchmark_loader")
    sys.modules["streamlit"] = streamlit
    sys.modules["loaders.benchmark_loader"] = benchmark_loader
    try:
        spec = importlib.util.spec_from_file_location(
            "benchmark_service_policy_test",
            ROOT / "benchmarks" / "benchmark_service.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if old_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = old_streamlit
        if old_loader is None:
            sys.modules.pop("loaders.benchmark_loader", None)
        else:
            sys.modules["loaders.benchmark_loader"] = old_loader


def test_latest_compatible_benchmark_archive_is_selected():
    service = _load_service_module()
    service.load_benchmark_history = lambda: pd.DataFrame(
        [
            {
                "Date": "2026-07-25",
                "Benchmark": "QQQ",
                "Forward EV/EBIT": 18.1,
                "Forward EBIT Yield": 0.055,
                "Avg Return": 1.10,
                "Beta": 1.60,
                "Member Count": 10,
                "Benchmark Version": "3.0",
            },
            {
                "Date": "2026-07-29",
                "Benchmark": "QQQ",
                "Forward EV/EBIT": 17.9,
                "Forward EBIT Yield": 0.056,
                "Avg Return": 0.83,
                "Beta": 1.62,
                "Member Count": 10,
                "Benchmark Version": "3.0",
            },
        ]
    )

    metrics = service.get_archived_benchmark_metrics("QQQ", current_only=False)
    assert metrics["archive_date"] == "2026-07-29"
    assert metrics["forward_ev_ebit"] == 17.9


def test_closed_session_uses_benchmark_history_without_yfinance():
    service = _load_service_module()
    latest = {
        "forward_ev_ebit": 17.9,
        "forward_ebit_yield": 0.056,
        "avg_return": 0.83,
        "beta": 1.62,
        "member_count": 10,
        "version": "3.0",
        "source_mode": "archive",
        "archive_date": "2026-07-29",
    }
    service.get_archived_benchmark_metrics = (
        lambda benchmark, current_only=True: None if current_only else latest.copy()
    )
    service.is_market_hours = lambda: False

    def fail_live_load(*args, **kwargs):
        raise AssertionError("YFinance benchmark load should not run after hours")

    service.load_benchmark = fail_live_load
    metrics = service._get_benchmark_metrics_cached(
        "QQQ",
        force_refresh=False,
        refresh_token=0,
        clock_token="2026-07-30:closed",
    )

    assert metrics["source_mode"] == "archive_market_closed"
    assert metrics["archive_date"] == "2026-07-29"


def test_manual_yfinance_refresh_bypasses_benchmark_archive():
    service = _load_service_module()
    service.get_archived_benchmark_metrics = lambda *args, **kwargs: {
        "forward_ev_ebit": 17.9,
        "forward_ebit_yield": 0.056,
        "avg_return": 0.83,
        "beta": 1.62,
        "member_count": 10,
        "version": "3.0",
        "source_mode": "archive",
        "archive_date": "2026-07-29",
    }
    service.is_market_hours = lambda: False
    service.load_benchmark = lambda *args, **kwargs: pd.DataFrame(
        {
            "Ticker": ["A", "B"],
            "Benchmark Weight": [0.5, 0.5],
            "Enterprise Value": [100.0, 200.0],
            "Forward EBIT": [10.0, 20.0],
            "1Y Return": [0.2, 0.4],
            "Beta": [1.0, 1.2],
        }
    )

    metrics = service._get_benchmark_metrics_cached(
        "QQQ",
        force_refresh=True,
        refresh_token=1,
        clock_token="2026-07-30:closed",
    )

    assert metrics["source_mode"] == "live"
    assert metrics["refresh_trigger"] == "manual"
    assert metrics["member_count"] == 2


def test_archive_backed_market_data_is_not_rearchived_as_current():
    app = (ROOT / "ai_macro.py").read_text()
    assert 'if benchmark_source_mode == "live":' in app
    assert 'if yfinance_source_mode in {"live_complete", "live_with_archive_fallback"}:' in app
