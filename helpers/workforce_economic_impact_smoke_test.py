"""Regression for the v6.5 Workforce and Economic Impact tabs."""

from __future__ import annotations

from pathlib import Path
import sys
import types

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


class _FakeStreamlit(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state = {}
        self.secrets = {}
    def cache_data(self, *args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda function: function


sys.modules.setdefault("streamlit", _FakeStreamlit())

from loaders.workforce_loader import load_workforce_data  # noqa: E402
from loaders.economic_impact_loader import load_economic_impact_data  # noqa: E402
from rendering.charts_workforce import indexed_history, current_momentum, level_history  # noqa: E402
from rendering.charts_economic_impact import productivity_index, current_outcomes, investment_vs_output  # noqa: E402


def _assert_current(frame: pd.DataFrame, date_column: str = "Date") -> None:
    dates = pd.to_datetime(frame[date_column], errors="coerce", format="mixed").dropna()
    if dates.empty or dates.min() < pd.Timestamp("2020-01-01"):
        raise AssertionError(f"Pre-2020 observations leaked into a current analytical dataset: {dates.min()}")
    if dates.max() < pd.Timestamp("2026-01-01"):
        raise AssertionError(f"Retained public evidence is stale: {dates.max()}")


def main() -> None:
    workforce = load_workforce_data()
    impact = load_economic_impact_data()

    for key in ("employment_history", "earnings_history", "job_openings_history"):
        frame = workforce.get(key)
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            raise AssertionError(f"Workforce dataset is missing: {key}")
        _assert_current(frame)
    for key in ("productivity_history", "cpi_history"):
        frame = impact.get(key)
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            raise AssertionError(f"Economic Impact dataset is missing: {key}")
        _assert_current(frame)

    if len(workforce.get("employment_latest", [])) != 4 or len(workforce.get("job_openings_latest", [])) != 4:
        raise AssertionError("Workforce latest summaries no longer cover four intended channels.")
    if not all((impact.get(key) or {}).get("date") is not None for key in ("nonfarm_productivity", "nonfarm_output", "nonfarm_compensation", "nonfarm_unit_labor_cost", "manufacturing_output")):
        raise AssertionError("Economic Impact latest realized outcomes are incomplete.")
    if pd.isna(pd.to_numeric((impact.get("inflation") or {}).get("yoy"), errors="coerce")):
        raise AssertionError("Economic Impact is missing the retained CPI normalization basis.")
    manufacturing_output = pd.to_numeric((impact.get("manufacturing_output") or {}).get("value"), errors="coerce")
    if pd.isna(manufacturing_output):
        raise AssertionError("Manufacturing real output did not load a finite retained observation.")
    manufacturing_history = impact["productivity_history"]
    manufacturing_yoy = manufacturing_history.loc[
        manufacturing_history.get("sector_name", "").astype(str).eq("Manufacturing")
        & manufacturing_history.get("measure_text", "").astype(str).eq("Real value-added output")
        & manufacturing_history.get("Metric", "").astype(str).eq("Year-over-year change"),
        "Value",
    ]
    if not (pd.to_numeric(manufacturing_yoy, errors="coerce") < 0).any():
        raise AssertionError("Manufacturing real output history lost support for negative observations.")

    figures = [
        indexed_history(workforce["employment_history"]),
        current_momentum(workforce["employment_latest"]),
        level_history(workforce["job_openings_history"]),
        level_history(workforce["earnings_history"]),
        productivity_index(impact["productivity_history"]),
        current_outcomes(impact["productivity_history"]),
        current_outcomes(impact["productivity_history"], inflation_yoy=impact["inflation"]["yoy"], inflation_adjusted=True),
        investment_vs_output(impact["investment_history"], impact["productivity_history"]),
    ]
    if any(len(figure.data) == 0 for figure in figures):
        raise AssertionError("A Workforce or Economic Impact chart has no retained evidence.")

    momentum_range = list(figures[1].layout.xaxis.range or [])
    if len(momentum_range) != 2 or momentum_range[0] > -5 or momentum_range[1] < 5:
        raise AssertionError(f"Employment momentum no longer shows the intended −5%, 0, 5% frame: {momentum_range}")
    adjusted_values = pd.to_numeric(pd.Series(list(figures[6].data[0].x)), errors="coerce")
    if not (adjusted_values < 0).any():
        raise AssertionError("Inflation-adjusted realized growth no longer preserves negative outcomes.")

    workforce_source = (PROJECT_ROOT / "rendering" / "workforce.py").read_text(encoding="utf-8")
    impact_source = (PROJECT_ROOT / "rendering" / "economic_impact.py").read_text(encoding="utf-8")
    dashboard_source = (PROJECT_ROOT / "rendering" / "dashboard.py").read_text(encoding="utf-8")

    for phrase in (
        "not a count of jobs caused by AI",
        "do not isolate AI-specific vacancies",
        "Workforce evidence ledger",
    ):
        if phrase not in workforce_source:
            raise AssertionError(f"Workforce lost its attribution boundary: {phrase}")
    for phrase in (
        "not market expectations",
        "do not prove that AI caused",
        "Co-movement is descriptive",
        "CPI-adjusted growth",
        "Economic-impact evidence ledger",
    ):
        if phrase not in impact_source:
            raise AssertionError(f"Economic Impact lost its realized-economy boundary: {phrase}")
    for forbidden in ("stock", "share price", "valuation", "equity return"):
        if forbidden in impact_source.casefold():
            raise AssertionError(f"Economic Impact crossed into Market ownership: {forbidden}")
    if 'render_workforce_tab' not in dashboard_source or 'render_economic_impact_tab' not in dashboard_source:
        raise AssertionError("The new tabs are not wired into the dashboard.")

    print(
        "PASS  v6.5.1 Workforce + Economic Impact · "
        f"{len(workforce['employment_history'])} employment observations · "
        f"{len(impact['productivity_history'])} realized-outcome observations"
    )


if __name__ == "__main__":
    main()
