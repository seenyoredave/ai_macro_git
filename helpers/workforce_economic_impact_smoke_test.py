"""Regression gate for the v6.8 Workforce and Economic Outcomes promotion."""
from __future__ import annotations

from pathlib import Path
import sys
import types

import numpy as np
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
from rendering.charts_workforce import (  # noqa: E402
    current_momentum,
    earnings_history,
    indexed_history,
    labor_flow_history,
    level_history,
    occupation_exposure_by_group,
    workforce_outcomes_matrix,
)
from rendering.charts_economic_impact import (  # noqa: E402
    current_outcomes,
    earnings_distribution_change,
    earnings_distribution_history,
    investment_vs_output,
    productivity_index,
    worker_capture_history,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _assert_current(frame: pd.DataFrame, date_column: str = "Date", *, latest_floor: str = "2026-01-01") -> None:
    dates = pd.to_datetime(frame[date_column], errors="coerce", format="mixed").dropna()
    require(not dates.empty, f"No usable dates in {date_column}.")
    require(dates.min() >= pd.Timestamp("2020-01-01"), f"Pre-2020 observations leaked into a current analytical dataset: {dates.min()}")
    require(dates.max() >= pd.Timestamp(latest_floor), f"Retained public evidence is stale: {dates.max()}")


def main() -> int:
    workforce = load_workforce_data()
    impact = load_economic_impact_data()

    for key in (
        "employment_history",
        "earnings_history",
        "real_earnings_history",
        "job_openings_history",
        "labor_flows_history",
        "cpi_history",
    ):
        frame = workforce.get(key)
        require(isinstance(frame, pd.DataFrame) and not frame.empty, f"Workforce dataset is missing: {key}")
        _assert_current(frame)

    exposure = workforce.get("occupation_exposure")
    exposure_groups = workforce.get("occupation_exposure_by_group")
    exposure_summary = workforce.get("exposure_summary", {}) or {}
    require(isinstance(exposure, pd.DataFrame) and len(exposure) >= 900, "Occupation-exposure benchmark contracted below 900 occupations.")
    require(isinstance(exposure_groups, pd.DataFrame) and len(exposure_groups) >= 20, "Major-group exposure summary is incomplete.")
    require(int(exposure_summary.get("occupations", 0)) == len(exposure), "Exposure summary count does not match the retained benchmark.")
    require(0 < float(exposure_summary.get("median_llm_software_exposure", np.nan)) < 100, "Median theoretical exposure is not finite and bounded.")
    require("not observed adoption" in str(exposure.iloc[0].get("Attribution boundary", "")), "Exposure benchmark lost its capability-versus-outcome boundary.")

    flows = workforce["labor_flows_history"]
    require(len(flows) >= 1200, "JOLTS labor-flow history is unexpectedly thin.")
    require(set(flows["Metric"].astype(str)) == {"Job openings rate", "Hires rate", "Quits rate", "Layoffs and discharges rate"}, "JOLTS flow contract lost a required measure.")
    require(flows["Series"].nunique() == 4, "JOLTS flow contract no longer covers four supporting labor markets.")
    require(pd.to_datetime(flows["Date"]).max() >= pd.Timestamp("2026-06-01"), "JOLTS labor flows are stale.")

    matrix = workforce.get("transmission_matrix")
    required_matrix = {
        "Channel", "Labor market", "Employment YoY", "Real earnings YoY", "Openings rate",
        "Hires rate", "Quits rate", "Layoffs rate", "Status",
    }
    require(isinstance(matrix, pd.DataFrame) and len(matrix) == 4, "Workforce transmission matrix no longer covers four channels.")
    require(required_matrix.issubset(matrix.columns), f"Workforce matrix is missing columns: {sorted(required_matrix - set(matrix.columns))}")
    for column in ["Employment YoY", "Real earnings YoY", "Openings rate", "Hires rate", "Quits rate", "Layoffs rate"]:
        require(pd.to_numeric(matrix[column], errors="coerce").notna().all(), f"Workforce matrix contains missing values in {column}.")
    require(matrix["Status"].astype(str).str.strip().ne("").all(), "Workforce matrix contains an unlabeled transmission state.")

    for key in (
        "productivity_history",
        "value_transmission_history",
        "earnings_distribution_history",
        "cpi_history",
    ):
        frame = impact.get(key)
        require(isinstance(frame, pd.DataFrame) and not frame.empty, f"Economic Outcomes dataset is missing: {key}")
        _assert_current(frame)

    transmission = impact["value_transmission_history"]
    require(set(transmission["Series"].astype(str)) == {"Labor productivity", "Real hourly compensation", "Labor share"}, "Value-transmission contract lost a required BLS series.")
    require(len(transmission) >= 72, "Value-transmission history is unexpectedly thin.")
    distribution = impact["earnings_distribution_history"]
    require(distribution["Series"].nunique() == 7, "Earnings-distribution contract no longer covers seven retained groups.")
    require(pd.to_datetime(distribution["Date"]).max() >= pd.Timestamp("2026-04-01"), "Earnings distribution is stale.")

    capture = impact.get("capture_summary", {}) or {}
    gap = pd.to_numeric(capture.get("productivity_real_comp_gap"), errors="coerce")
    labor_share_since = pd.to_numeric((capture.get("labor_share", {}) or {}).get("since_2020"), errors="coerce")
    median_yoy = pd.to_numeric((capture.get("median_real_earnings", {}) or {}).get("YoY"), errors="coerce")
    group_spread = pd.to_numeric(capture.get("group_growth_spread_ppts"), errors="coerce")
    require(pd.notna(gap) and gap > 0, "Productivity-to-real-compensation gap is unavailable or lost its retained signal.")
    require(pd.notna(labor_share_since), "Labor-share change is unavailable.")
    require(pd.notna(median_yoy), "Median real earnings growth is unavailable.")
    require(pd.notna(group_spread) and group_spread >= 0, "Broad-participation spread is unavailable.")

    figures = [
        occupation_exposure_by_group(exposure_groups),
        workforce_outcomes_matrix(matrix),
        indexed_history(workforce["employment_history"]),
        current_momentum(workforce["employment_latest"]),
        level_history(workforce["job_openings_history"]),
        labor_flow_history(flows, "Hires rate"),
        earnings_history(workforce["earnings_history"], workforce["cpi_history"], inflation_adjusted=False),
        earnings_history(workforce["earnings_history"], workforce["cpi_history"], inflation_adjusted=True),
        worker_capture_history(transmission),
        earnings_distribution_change(impact["earnings_distribution_summary"]),
        earnings_distribution_history(distribution, "Sex"),
        earnings_distribution_history(distribution, "Race and ethnicity"),
        productivity_index(impact["productivity_history"]),
        current_outcomes(impact["productivity_history"]),
        current_outcomes(impact["productivity_history"], inflation_yoy=impact["inflation"]["yoy"], inflation_adjusted=True),
        investment_vs_output(impact["investment_history"], impact["productivity_history"]),
    ]
    require(all(len(figure.data) > 0 for figure in figures), "A Phase 1 Workforce or Economic Outcomes chart has no retained evidence.")
    require(list(figures[0].layout.xaxis.range or []) == [0, 100], "Occupation exposure chart lost its bounded percentage scale.")
    require(str(figures[1].data[0].type) == "heatmap", "Observed workforce transmission is no longer a matrix.")
    require(len(figures[8].data) == 3, "Worker-capture history no longer shows productivity, real compensation, and labor share.")

    nominal_trace = pd.to_numeric(pd.Series(list(figures[6].data[0].y)), errors="coerce")
    real_trace = pd.to_numeric(pd.Series(list(figures[7].data[0].y)), errors="coerce")
    require(not nominal_trace.equals(real_trace), "Workforce nominal and CPI-adjusted earnings views are identical.")
    require(str(figures[7].layout.yaxis.title.text).startswith("Dollars per hour"), "Workforce real earnings chart lost its purchasing-power label.")

    workforce_source = (PROJECT_ROOT / "rendering" / "workforce.py").read_text(encoding="utf-8")
    impact_source = (PROJECT_ROOT / "rendering" / "economic_impact.py").read_text(encoding="utf-8")
    evidence_source = (PROJECT_ROOT / "rendering" / "evidence.py").read_text(encoding="utf-8")
    read_source = (PROJECT_ROOT / "analytics" / "read_architecture.py").read_text(encoding="utf-8")

    for phrase in (
        "Observed workforce outcomes",
        "Theoretical LLM task exposure",
        "Observed workforce transmission",
        "Workforce channels",
        "Workforce data",
    ):
        require(phrase in workforce_source, f"Workforce lost a Phase 1 boundary or surface: {phrase}")
    for phrase in (
        "value_realization_bridge_html",
        "Productivity versus worker capture",
        "Distribution of gains",
        "Commercial scale, production response, and distribution to workers",
        "Real median weekly earnings",
        "Economic-outcomes data",
    ):
        require(phrase in impact_source, f"Economic Outcomes lost a Phase 1 boundary or surface: {phrase}")
    for phrase in (
        "Occupation-level LLM task-exposure benchmark",
        "JOLTS labor-flow history",
        "Productivity, real compensation, and labor-share transmission",
        "Real median weekly earnings distribution",
    ):
        require(phrase in evidence_source, f"Evidence does not expose a Phase 1 retained layer: {phrase}")
    require("broad value capture still trails" in read_source, "AI Macro did not adopt the worker-capture framing.")
    for forbidden in ("AI caused these layoffs", "AI eliminated", "automation forecast"):
        require(forbidden.casefold() not in (workforce_source + impact_source).casefold(), f"Phase 1 crossed its causal boundary: {forbidden}")

    print(
        "PASS  v6.8 Workforce + Economic Outcomes · "
        f"{len(exposure):,} exposure occupations · {len(flows):,} JOLTS flow observations · "
        f"{len(transmission):,} worker-capture observations · {len(distribution):,} distribution observations"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
