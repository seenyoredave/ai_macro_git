"""Import the complete public rendering graph under a minimal Streamlit shim."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys
import types

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class _FakeStreamlit(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("streamlit")
        self.session_state = {}
        self.secrets = {}

    def cache_data(self, *args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda function: function

    def cache_resource(self, *args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda function: function


sys.modules["streamlit"] = _FakeStreamlit()


def main() -> None:
    module = importlib.import_module("rendering.dashboard")
    renderer = getattr(module, "render_research_dashboard", None)
    if not callable(renderer):
        raise AssertionError("Dashboard renderer did not import cleanly.")

    evidence = importlib.import_module("rendering.evidence")
    payload = getattr(evidence, "_water_evidence_payload", None)
    if not callable(payload) or payload(None) != {}:
        raise AssertionError("Evidence Water payload normalization is unavailable.")

    economic = importlib.import_module("rendering.charts_economic_impact")
    history_chart = getattr(economic, "earnings_distribution_history", None)
    if not callable(history_chart):
        raise AssertionError("Economic-impact earnings history chart is unavailable.")
    zero_base = pd.DataFrame({
        "Date": pd.date_range("2025-03-31", periods=4, freq="QE"),
        "Series": ["All workers"] * 4,
        "Value": [0.0] * 4,
        "Dimension": ["All"] * 4,
        "Seasonality": ["Not seasonally adjusted"] * 4,
    })
    history_chart(zero_base, "All")

    print("PASS  complete rendering import graph")
    print("PASS  economic-impact earnings history handles a zero index base")


if __name__ == "__main__":
    main()
