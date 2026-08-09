"""Render the changed tabs under a Streamlit shim using retained data."""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class _Block(AbstractContextManager):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class _FakeStreamlit(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state = {}
        self.secrets = {}
        self.charts: list[str | None] = []
        self.markup: list[str] = []

    def cache_data(self, *args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda function: function

    def cache_resource(self, *args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda function: function

    def markdown(self, body, *args, **kwargs):
        self.markup.append(str(body))
        return None

    def caption(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def dataframe(self, *args, **kwargs):
        return None

    def container(self, *args, **kwargs):
        return _Block()

    def expander(self, *args, **kwargs):
        return _Block()

    def popover(self, *args, **kwargs):
        return _Block()

    def columns(self, spec, *args, **kwargs):
        count = int(spec) if isinstance(spec, int) else len(spec)
        return [_Block() for _ in range(count)]

    def radio(self, label, options, **kwargs):
        return list(options)[0]

    def selectbox(self, label, options, **kwargs):
        values = list(options)
        return values[0] if values else None

    def text_input(self, *args, **kwargs):
        return kwargs.get("value", "")

    def plotly_chart(self, figure, *, key=None, **kwargs):
        if not getattr(figure, "data", None):
            raise AssertionError(f"Rendered chart has no traces: {key}")
        self.charts.append(key)
        return None


FAKE_ST = _FakeStreamlit()
sys.modules["streamlit"] = FAKE_ST

from loaders.adaptation_loader import load_adaptation_data  # noqa: E402
from loaders.commercialization_loader import load_commercialization_data  # noqa: E402
from loaders.economic_impact_loader import load_economic_impact_data  # noqa: E402
from loaders.infrastructure_loader import load_infrastructure_data  # noqa: E402
from rendering.adaptation import render_adaptation_tab  # noqa: E402
from rendering.compute import render_compute_tab  # noqa: E402
from rendering.economic_impact import render_economic_impact_tab  # noqa: E402


def main() -> None:
    infrastructure = load_infrastructure_data()
    commercialization = load_commercialization_data()
    adaptation = load_adaptation_data()
    outcomes = load_economic_impact_data()

    FAKE_ST.charts.clear()
    render_compute_tab(infrastructure, commercialization_data=commercialization, tab_read=None)
    compute_keys = set(FAKE_ST.charts)
    required_compute = {"compute-output-history", "compute-utilization-history", "compute-critical-supply-chain", "compute-layer-sites"}
    if not required_compute.issubset(compute_keys):
        raise AssertionError(f"Compute default rollout charts changed: {sorted(compute_keys)}")

    FAKE_ST.charts.clear()
    render_adaptation_tab(adaptation, commercialization_data=commercialization, tab_read=None)
    adoption_keys = set(FAKE_ST.charts)
    required_adoption = {"adoption-consumer-history", "adaptation-sector-breadth"}
    if required_adoption != adoption_keys:
        raise AssertionError(f"Adoption default chart set changed: {sorted(adoption_keys)}")

    FAKE_ST.charts.clear()
    FAKE_ST.markup.clear()
    render_economic_impact_tab(outcomes, commercialization_data=commercialization, tab_read=None)
    economic_keys = set(FAKE_ST.charts)
    required_economic = {
        "economic-impact-index-history",
        "economic-impact-worker-capture-history",
        "economic-impact-earnings-distribution-change",
        "economic-impact-investment-validation",
    }
    if required_economic != economic_keys:
        raise AssertionError(f"Economic Outcomes default chart set changed: {sorted(economic_keys)}")
    if not any("rm-value-bridge" in markup for markup in FAKE_ST.markup):
        raise AssertionError("Economic Outcomes did not render the value-realization bridge.")

    print(
        "PASS  rollout render smoke · "
        f"{len(compute_keys)} Compute charts · {len(adoption_keys)} Adoption charts · "
        f"{len(economic_keys)} Economic Outcomes charts"
    )


if __name__ == "__main__":
    main()
