"""Execute the complete application with real bundled data and no network.

A lightweight Streamlit stand-in exercises the actual loaders, analytics,
archive fallbacks, and all seven render paths. Network calls are forced to fail
so the smoke test proves that the packaged archives can support a complete
closed-session startup without mutating source data.
"""

from __future__ import annotations

import runpy
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class _SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class _CacheData:
    def __call__(self, *args, **kwargs):
        if args and callable(args[0]) and not kwargs:
            return args[0]
        return lambda function: function

    def clear(self):
        return None


class _Streamlit(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.cache_data = _CacheData()
        self.session_state = _SessionState(archive_suspended=True)
        self.sidebar = _Context()
        self.secrets = {}
        self.plotly_keys = set()

    def set_page_config(self, *args, **kwargs):
        return None

    def tabs(self, labels):
        return [_Context() for _ in labels]

    def columns(self, spec, *args, **kwargs):
        count = spec if isinstance(spec, int) else len(spec)
        return [_Context() for _ in range(count)]

    def container(self, *args, **kwargs):
        return _Context()

    def expander(self, *args, **kwargs):
        return _Context()

    def selectbox(self, label, options, *args, **kwargs):
        return list(options)[0]

    def text_input(self, *args, **kwargs):
        return ""

    def button(self, *args, **kwargs):
        return False

    def plotly_chart(self, figure, *args, **kwargs):
        key = kwargs.get("key")
        if not key:
            raise AssertionError("Plotly chart is missing an explicit key")
        if key in self.plotly_keys:
            raise AssertionError(f"Duplicate Plotly key: {key}")
        self.plotly_keys.add(key)
        return None

    def rerun(self):
        raise AssertionError("Unexpected rerun during startup smoke")

    def __getattr__(self, name):
        if name in {
            "markdown",
            "caption",
            "dataframe",
            "write",
            "subheader",
            "header",
            "title",
            "metric",
            "error",
            "info",
            "warning",
            "bar_chart",
        }:
            return lambda *args, **kwargs: None
        raise AttributeError(name)


def _install_dependency_stubs():
    st = _Streamlit()
    sys.modules["streamlit"] = st

    yfinance = types.ModuleType("yfinance")

    def unexpected_ticker(*args, **kwargs):
        raise AssertionError("Closed-session startup unexpectedly called YFinance")

    yfinance.Ticker = unexpected_ticker
    sys.modules["yfinance"] = yfinance

    fredapi = types.ModuleType("fredapi")

    class Fred:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Startup smoke unexpectedly created a live FRED client")

    fredapi.Fred = Fred
    sys.modules["fredapi"] = fredapi

    import requests

    def offline(*args, **kwargs):
        raise requests.ConnectionError("offline startup smoke")

    requests.get = offline
    return st


def main() -> int:
    sys.path.insert(0, str(ROOT))
    st = _install_dependency_stubs()
    namespace = runpy.run_path(str(ROOT / "ai_macro.py"), run_name="__main__")

    interpretation = st.session_state.regime_metrics.get("Macro Interpretation", {})
    if not interpretation.get("headline"):
        raise AssertionError("Macro interpretation did not produce a headline")
    if not interpretation.get("expansion_factors"):
        raise AssertionError("Macro interpretation did not produce expansion factors")
    if not interpretation.get("constraint_factors"):
        raise AssertionError("Macro interpretation did not produce constraint factors")
    if not interpretation.get("changes"):
        raise AssertionError("Macro interpretation did not produce a weekly rollup")
    if namespace.get("APP_VERSION") != "v4.14-dev":
        raise AssertionError(f"Unexpected build: {namespace.get('APP_VERSION')}")
    if not st.plotly_keys:
        raise AssertionError("The application did not reach the rendered dashboard")

    from archive import archive as archive_module
    captured = {}

    def capture_snapshot(frame, spec):
        captured["frame"] = frame.copy()
        captured["spec"] = spec

    archive_module.write_archive_snapshot = capture_snapshot
    archive_module.append_macro_history(
        st.session_state.regime_metrics,
        st.session_state.fred_data,
    )
    archived = captured.get("frame")
    if archived is None or archived.empty:
        raise AssertionError("Macro interpretation archive row was not produced")
    required_archive_fields = {
        "Macro State",
        "Macro State Summary",
        "Macro Pressure Factors",
        "Macro Resilience Factors",
        "Macro Change Factors",
        "Macro Metric Changes",
        "Macro Weekly References",
        "Macro Weekly Context",
        "Macro Interpretation Version",
        "Macro Domain States",
    }
    missing_fields = required_archive_fields - set(archived.columns)
    if missing_fields:
        raise AssertionError(f"Macro archive row is missing: {sorted(missing_fields)}")

    print(
        "Full startup smoke passed: "
        f"{interpretation['headline']} · {len(st.plotly_keys)} Plotly elements."
    )
    print("Expansion:", " | ".join(interpretation.get("expansion_factors", [])))
    print("Constraints:", " | ".join(interpretation.get("constraint_factors", [])))
    print("This week:", " | ".join(interpretation.get("changes", [])))
    print("References:", len(interpretation.get("weekly_references", [])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
