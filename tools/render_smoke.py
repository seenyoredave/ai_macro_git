"""Execute the real Macro, Finance, Infrastructure, Energy, Adaptation, and Evidence render paths without a browser.

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
            "headline": "Expansion with emerging constraints",
            "summary": "AI-related deployment continues to expand, while selected constraints are emerging.",
            "constraint_factors": ["Forward commitments remain elevated."],
            "expansion_factors": ["Internal funding remains adequate."],
            "pressure_factors": ["Forward commitments remain elevated."],
            "resilience_factors": ["Internal funding remains adequate."],
            "changes": ["No material change this week."],
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
        {
            "current_use": 21.5,
            "snapshot_date": "2026-07-30",
            "source": "Census BTOS Local History",
            "national_history": pd.DataFrame(
                {"Date": pd.to_datetime(["2026-07-16", "2026-07-30"]), "Current AI Use": [20.8, 21.5]}
            ),
        },
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
    infrastructure_history = pd.DataFrame(
        {
            "Observation Date": pd.to_datetime(["2025-06-01", "2026-06-01"]),
            "Data Center Construction": [25000.0, 32000.0],
            "Private Nonresidential Construction": [750000.0, 800000.0],
            "Computer, Electronic & Electrical Manufacturing Construction": [110000.0, 125000.0],
            "Private Manufacturing Construction": [210000.0, 230000.0],
            "Communication Construction": [26000.0, 28000.0],
            "Public Highway and Street Construction": [125000.0, 132000.0],
            "Public Transportation Construction": [58000.0, 61000.0],
            "Public Water Supply Construction": [34000.0, 37000.0],
        }
    )
    locations = pd.DataFrame(
        {
            "State": ["VA", "TX"],
            "County": ["Loudoun County", "Dallas County"],
            "Operator": ["Example One", "Example Two"],
            "Facility": ["Facility A", "Facility B"],
            "Square Feet": [100000.0, 200000.0],
            "Latitude": [39.0, 32.8],
            "Longitude": [-77.5, -96.8],
            "Type": ["point", "point"],
            "Status": ["Observed footprint", "Observed footprint"],
            "Evidence Grade": ["C", "C"],
            "Location Precision": ["Mapped centroid", "Mapped centroid"],
            "Evidence Type": ["Open geospatial inventory", "Open geospatial inventory"],
            "Source": ["IM3", "IM3"],
        }
    )
    infrastructure_data = {
        "construction_source": "Census Local History",
        "map_source": "IM3 Local History",
        "construction_history": infrastructure_history,
        "locations": locations,
        "facility_registry": locations,
        "facility_coverage": {
            "records": 2,
            "states": 2,
            "verified_project_records": 0,
            "fields": {
                "Square Feet": {"records": 2, "total": 2, "share": 1.0},
            },
        },
        "location_count": 2,
        "state_count": 2,
        "series": {
            name: {
                "value": float(infrastructure_history[name].iloc[-1]),
                "date": "2026-06-01",
                "yoy_growth": float(infrastructure_history[name].iloc[-1] / infrastructure_history[name].iloc[0] - 1.0),
                "source": "Census Local History",
            }
            for name in (
                "Data Center Construction",
                "Computer, Electronic & Electrical Manufacturing Construction",
                "Communication Construction",
                "Public Highway and Street Construction",
                "Public Transportation Construction",
                "Public Water Supply Construction",
            )
        },
    }
    adaptation_history = pd.DataFrame(
        {
            "Cycle": [202515, 202615],
            "Date": pd.to_datetime(["2025-07-31", "2026-07-30"]),
            "Current AI Use": [18.0, 21.5],
            "Expected AI Use": [21.0, 24.3],
            "Current AI Use SE": [0.4, 0.4],
            "Expected AI Use SE": [0.5, 0.5],
            "Expected Adoption Gap": [3.0, 2.8],
        }
    )
    sector_snapshot = pd.DataFrame(
        {
            "Sector Code": ["51", "54"],
            "Sector": ["Information", "Professional, Scientific, and Technical Services"],
            "Current AI Use": [41.9, 40.0],
            "Expected AI Use": [45.0, 43.0],
            "Current AI Use SE": [0.8, 0.9],
            "Expected AI Use SE": [0.9, 1.0],
            "Expected Adoption Gap": [3.1, 3.0],
            "Observation Date": pd.to_datetime(["2026-07-30", "2026-07-30"]),
        }
    )
    adaptation_data = {
        "source": "Census BTOS Local History",
        "snapshot_date": "2026-07-30",
        "national_history": adaptation_history,
        "sector_snapshot": sector_snapshot,
        "current_use": 21.5,
        "expected_use": 24.3,
        "expected_adoption_gap": 2.8,
        "annual_change": 3.5,
    }
    renderers.render_infrastructure_tab(infrastructure_data)
    renderers.render_adaptation_tab(adaptation_data)
    renderers.render_evidence_tab({}, {}, {}, {}, debt_data, infrastructure_data, adaptation_data)

    required_keys = {
        "finance-debt-market-sparkline",
        "finance-debt-ig-sparkline",
        "finance-debt-hy-sparkline",
        "finance-debt-market-history",
        "infrastructure-data-center-map",
        "infrastructure-core-construction-history",
        "infrastructure-supporting-history",
        "adaptation-national-history",
        "adaptation-sector-breadth",
    }
    missing = sorted(required_keys - set(st.plotly_keys))
    if missing:
        raise AssertionError(f"Render smoke did not reach required charts: {missing}")

    print(f"Macro/Finance/Infrastructure/Adaptation/Evidence render smoke passed ({len(st.plotly_keys)} Plotly elements).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
