"""Targeted regression for the Power / Grid & Storage evidence boundary."""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
import sys
import types

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


class _Block(AbstractContextManager):
    def __init__(self, fake, *, expander=False):
        self.fake = fake
        self.expander = expander
    def __enter__(self):
        if self.expander:
            self.fake.expander_depth += 1
        return self
    def __exit__(self, exc_type, exc, traceback):
        if self.expander:
            self.fake.expander_depth -= 1
        return False


class _FakeStreamlit(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.expander_depth = 0
        self.charts = []
        self.radio_options = {}
        self.session_state = {}
        self.secrets = {}
    def cache_data(self, *args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda function: function
    def markdown(self, *args, **kwargs): return None
    def caption(self, *args, **kwargs): return None
    def info(self, *args, **kwargs): return None
    def error(self, *args, **kwargs): return None
    def dataframe(self, *args, **kwargs): return None
    def columns(self, spec, *args, **kwargs):
        count = int(spec) if isinstance(spec, int) else len(spec)
        return [_Block(self) for _ in range(count)]
    def container(self, *args, **kwargs): return _Block(self)
    def expander(self, *args, **kwargs): return _Block(self, expander=True)
    def radio(self, label, options, *, key=None, **kwargs):
        values = list(options)
        self.radio_options[str(key or label)] = values
        return values[0]
    def plotly_chart(self, figure, *, key=None, **kwargs):
        self.charts.append({"key": key, "hidden": self.expander_depth > 0, "traces": len(getattr(figure, "data", ()))})


FAKE_ST = _FakeStreamlit()
sys.modules["streamlit"] = FAKE_ST

from analytics.dashboard_context import DashboardContext  # noqa: E402
from analytics.read_evidence import build_power_evidence  # noqa: E402
from rendering.power import (  # noqa: E402
    _power_context,
    _render_buildout,
    _render_demand,
    _render_power_pulse,
    _render_power_ledger,
    _render_prices,
    _render_supply,
)
from rendering.grid_storage import _context as grid_context  # noqa: E402
from rendering.charts_grid_storage import storage_pipeline_by_region, grid_construction_history  # noqa: E402
from rendering.charts_energy import generation_mix  # noqa: E402


def _read_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(PROJECT_ROOT / "data" / name)


def _power_data() -> dict:
    history = _read_csv("energy_series_history.csv")
    history["Date"] = pd.to_datetime(history["Date"], errors="coerce", format="mixed")
    gas = history.loc[history["Series"].eq("Natural Gas Price")].sort_values("Date", kind="stable")
    return {
        "retail_history": _read_csv("energy_retail_market_history.csv"),
        "generation_history": _read_csv("energy_generation_history.csv"),
        "capacity_snapshot": _read_csv("energy_capacity_snapshot.csv"),
        "capacity_changes": _read_csv("energy_capacity_changes_2026.csv"),
        "generator_pipeline": _read_csv("energy_generator_pipeline.csv"),
        "interconnection_queue": _read_csv("energy_interconnection_queue.csv"),
        "interconnection_queue_summary": _read_csv("energy_interconnection_queue_summary.csv"),
        "wholesale_prices": _read_csv("energy_wholesale_prices.csv"),
        "gas_pipeline_source": _read_csv("energy_natural_gas_pipeline_projects.csv"),
        "gas_pipeline_projects": _read_csv("energy_natural_gas_pipeline_analysis.csv"),
        "lng_projects": _read_csv("energy_lng_projects.csv"),
        "gas_storage_projects": _read_csv("energy_natural_gas_storage_projects.csv"),
        "series": {"Natural Gas Price": {"value": gas.iloc[-1]["Value"], "date": gas.iloc[-1]["Date"], "history": gas[["Date", "Value"]]}},
    }


def main() -> None:
    power_data = _power_data()
    infrastructure = {
        "construction_history": _read_csv("infrastructure_construction_history.csv"),
        "series": {},
        "data_center_registry": pd.DataFrame(),
    }
    history = infrastructure["construction_history"]
    history["Observation Date"] = pd.to_datetime(history["Observation Date"], errors="coerce", format="mixed")
    latest = history.sort_values("Observation Date").iloc[-1]
    prior = history.sort_values("Observation Date").iloc[-13]
    value = pd.to_numeric(latest["Electric Power Construction"], errors="coerce")
    base = pd.to_numeric(prior["Electric Power Construction"], errors="coerce")
    infrastructure["series"]["Electric Power Construction"] = {"value": value, "yoy_growth": value / base - 1.0}

    power = _power_context(power_data, infrastructure)
    if "queue" in power or "queue_summary" in power:
        raise AssertionError("Power context still owns interconnection data.")
    if not np.isclose(power["demand"]["total_growth"], 1.2007350328539612, atol=1e-9):
        raise AssertionError("Trailing electricity-demand growth changed unexpectedly.")
    if not np.isclose(power["development"]["planned_net_gw"], 227.0018, atol=1e-4):
        raise AssertionError("Planned generation balance changed unexpectedly.")
    power_evidence = build_power_evidence(
        DashboardContext(energy_data=power_data, infrastructure_data=infrastructure)
    )
    fact_ids = {fact.id for fact in power_evidence.facts}
    if any("queue" in fact_id or "interconnection" in fact_id for fact_id in fact_ids):
        raise AssertionError("Power evidence crossed into Grid & Storage ownership.")
    if "power.planned_net_gw" not in fact_ids or "power.demand_growth" not in fact_ids:
        raise AssertionError("Power evidence lost its generation/demand boundary facts.")

    FAKE_ST.charts.clear()
    FAKE_ST.radio_options.clear()
    _render_power_pulse(power)
    _render_demand(power)
    _render_supply(power)
    _render_buildout(power)
    _render_prices(power, power_data)
    _render_power_ledger(power, power_data)
    visible = [item for item in FAKE_ST.charts if not item["hidden"]]
    hidden = [item for item in FAKE_ST.charts if item["hidden"]]
    if len(visible) != 4:
        raise AssertionError(f"Power should have four default-visible charts, found {len(visible)}")
    if FAKE_ST.radio_options.get("power-view-supply") != ["Generation mix", "Generation change", "Fleet changes"]:
        raise AssertionError("Power supply selector changed unexpectedly.")
    if FAKE_ST.radio_options.get("power-view-prices") != ["Retail prices", "Wholesale hubs", "Fuel infrastructure"]:
        raise AssertionError("Power price selector changed unexpectedly.")
    if any(item["traces"] == 0 for item in visible):
        raise AssertionError("A default-visible Power chart is empty.")
    mix_figure = generation_mix(power["generation"])
    years = [int(value) for trace in mix_figure.data for value in list(trace.x)]
    if not years or min(years) < 2020:
        raise AssertionError(f"Power generation mix leaked stale pre-2020 evidence: {min(years) if years else 'none'}")

    grid = grid_context(power_data, infrastructure)
    development = grid["development"]
    if not 20.0 < float(development["advanced_share"]) < 30.0:
        raise AssertionError("Grid queue maturity is outside the retained-data range.")
    if pd.isna(grid["storage_queue_gw"]) or grid["storage_queue_gw"] <= 0:
        raise AssertionError("Grid & Storage lost submitted storage capacity.")
    if len(storage_pipeline_by_region(development["active_queue"]).data) != 1:
        raise AssertionError("Storage regional pipeline chart is unavailable.")
    if len(grid_construction_history(history).data) != 1:
        raise AssertionError("Grid construction chronology is unavailable.")

    power_source = (PROJECT_ROOT / "rendering" / "power.py").read_text(encoding="utf-8")
    if "Queue by technology" in power_source or "Queue by region" in power_source:
        raise AssertionError("Queue views remain on Power.")
    grid_source = (PROJECT_ROOT / "rendering" / "grid_storage.py").read_text(encoding="utf-8")
    if "Planned generation" not in power_source or "Queue outcomes" not in grid_source:
        raise AssertionError("Power and Grid & Storage no longer retain distinct analytical surfaces.")

    print(
        "PASS  Power + Grid evidence boundary · "
        f"{len(visible)} visible Power charts · {len(hidden)} collapsed Power charts · "
        f"{development['headline_queue_gw']:.0f} GW active queue"
    )


if __name__ == "__main__":
    main()
