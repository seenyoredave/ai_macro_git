"""Execute the real Finance and Evidence render paths without a browser.

The test uses a narrow Streamlit stand-in but imports the actual renderer,
components, figures, and data tables. It catches missing helpers, duplicate
Plotly keys, mismatched function signatures, and first-render NameErrors.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sys
import types

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


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


class _Streamlit(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.cache_data = _CacheData()
        self.secrets = {}
        self.plotly_keys = []

    def columns(self, spec, *args, **kwargs):
        count = spec if isinstance(spec, int) else len(spec)
        return [_Context() for _ in range(count)]

    def container(self, *args, **kwargs):
        return _Context()

    def expander(self, *args, **kwargs):
        return _Context()

    def selectbox(self, label, options, *args, **kwargs):
        return list(options)[0]

    def plotly_chart(self, figure, *args, **kwargs):
        key = kwargs.get("key")
        if not key:
            raise AssertionError("Plotly chart is missing an explicit key")
        if key in self.plotly_keys:
            raise AssertionError(f"Duplicate Plotly key: {key}")
        self.plotly_keys.append(key)
        return None

    def __getattr__(self, name):
        if name in {
            "markdown",
            "caption",
            "dataframe",
            "write",
            "subheader",
            "title",
            "metric",
            "error",
            "info",
            "warning",
        }:
            return lambda *args, **kwargs: None
        raise AttributeError(name)


def _clear_modules():
    prefixes = (
        "research_overlay",
        "helpers.macro_dashboard",
        "helpers.render_sector",
    )
    for name in list(sys.modules):
        if name == "streamlit" or any(
            name == prefix or name.startswith(f"{prefix}.")
            for prefix in prefixes
        ):
            sys.modules.pop(name, None)


def main() -> int:
    _clear_modules()
    st = _Streamlit()
    sys.modules["streamlit"] = st
    sys.path.insert(0, str(ROOT))

    from research_overlay import renderers

    debt_history = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-07-17", "2026-07-24"]),
            "Corporate Bond Market Distress": [0.18, 0.15],
            "Investment-Grade Bond Distress": [0.33, 0.30],
            "High-Yield Bond Distress": [0.11, 0.10],
        }
    )
    debt_data = {
        "source_mode": "archive_current_release",
        "history": debt_history,
        "series": {
            name: {
                "value": float(debt_history[name].iloc[-1]),
                "date": "2026-07-24",
                "source": "New York Fed archive",
                "history": debt_history[["Date", name]].rename(
                    columns={name: "Value"}
                ),
            }
            for name in (
                "Corporate Bond Market Distress",
                "Investment-Grade Bond Distress",
                "High-Yield Bond Distress",
            )
        },
    }
    dashboard_data = {
        "trends": {
            "aei_trend": {"history": pd.DataFrame()},
            "adi_trend": {"history": pd.DataFrame()},
            "power_stress_trend": {"history": pd.DataFrame()},
            "concentration_trend": {"history": pd.DataFrame()},
            "borrower_strain_trend": {"history": pd.DataFrame()},
            "lender_strain_trend": {"history": pd.DataFrame()},
            "power_capacity_gap_trend": {"history": pd.DataFrame()},
        }
    }
    macro_regime = {
        "AI Equity Index": 45.0,
        "AI Development Intensity": 80.0,
        "Power Stress Index": -4.0,
        "Power Capacity Gap": 12.0,
        "Concentration HHI": 21.0,
        "Speculation Gap": -35.0,
        "Economic Validation Gap": -53.0,
        "Macro Interpretation": {
            "headline": "Resilient under rising pressure",
            "summary": "The buildout remains financeable while selected pressures are increasing.",
            "pressure_factors": ["Forward commitments remain elevated."],
            "resilience_factors": ["Internal funding remains adequate."],
            "changes": ["Borrower strain increased."],
            "confidence": "high",
        },
        "ADI Components": {"components": {}},
        "Economic Validation Gap Components": {"components": {}},
        "Power Stress Components": {"components": {}},
        "Power Capacity Gap Components": {"components": {}},
    }
    macro_sector_data = {
        "Compute": pd.DataFrame(
            {
                "Ticker": ["AAA", "BBB"],
                "Market Cap": [100.0, 50.0],
            }
        )
    }

    renderers.render_macro_tab(
        {},
        macro_sector_data,
        {"Industrial Production YoY": {"value": 1.0}},
        macro_regime,
        dashboard_data,
    )
    renderers.render_finance_tab(
        {},
        {},
        {},
        {},
        pd.DataFrame(),
        debt_data,
        dashboard_data,
    )
    renderers.render_evidence_tab({}, {}, {}, {}, debt_data)

    required_keys = {
        "finance-debt-market-sparkline",
        "finance-debt-ig-sparkline",
        "finance-debt-hy-sparkline",
        "finance-debt-market-history",
    }
    missing = sorted(required_keys - set(st.plotly_keys))
    if missing:
        raise AssertionError(f"Finance render did not reach required charts: {missing}")

    print(f"Macro/Finance/Evidence render smoke passed ({len(st.plotly_keys)} Plotly elements).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
