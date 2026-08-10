"""Stop-the-line contracts for the v6.8 Phase 1 value-transmission release."""
from __future__ import annotations

from pathlib import Path
import re
import sys
import types

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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

from analytics.read_architecture import (  # noqa: E402
    READ_ARCHITECTURE_VERSION,
    _macro_headline,
    build_economic_impact_read,
    build_workforce_read,
)
from config.visual_design import signature_tool  # noqa: E402
from loaders.economic_impact_loader import load_economic_impact_data  # noqa: E402
from loaders.workforce_loader import load_workforce_data  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    app = (ROOT / "ai_macro.py").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    require(
        re.search(r'APP_VERSION = "v\d+\.\d+\.\d+"', app) is not None,
        "Application version is missing or not semantic-versioned.",
    )
    require(
        re.search(r'APP_STATE_SCHEMA_VERSION = "\d+\.\d+-[^"]+"', app) is not None,
        "Application state schema is missing or malformed.",
    )
    runtime_contract = (ROOT / "docs" / "RUNTIME_DATA_CONTRACT.md").read_text(encoding="utf-8")
    require(
        "developer retained startup performs zero provider calls" in runtime_contract.casefold(),
        "State-schema bump lost the retained-loader policy contract.",
    )
    require(READ_ARCHITECTURE_VERSION == "7.2.0", "Read architecture version does not match the v7.2.0 evidence-language contract.")
    require(readme.startswith("# AI Macro\n"), "README no longer opens with the project overview.")
    require("## v" not in readme and "review build" not in readme.casefold(), "README has drifted back into release-note copy.")

    workforce_tool = signature_tool("workforce_outcomes_matrix")
    outcomes_tool = signature_tool("realized_value_transmission")
    require(workforce_tool.status == "current" and workforce_tool.key_pattern == "workforce-outcomes-matrix", "Workforce signature tool is not current or correctly keyed.")
    require(outcomes_tool.status == "current" and outcomes_tool.key_pattern == "economic-impact-panel-value-transmission", "Economic Outcomes signature tool is not current or correctly keyed.")

    workforce_data = load_workforce_data()
    outcomes_data = load_economic_impact_data()
    workforce_read = build_workforce_read(workforce_data)
    outcomes_read = build_economic_impact_read(outcomes_data, commercialization_data=None)
    require(workforce_read.get("confidence") in {"moderate", "high"}, "Workforce Read confidence is unexpectedly low.")
    require("do not measure jobs actually lost or automated" in str(workforce_read.get("summary")), "Workforce Read does not distinguish potential task exposure from observed outcomes.")
    require("occupation_exposure_count" in (workforce_read.get("signals") or {}), "Workforce Read lost its exposure signal.")
    require("productivity" in str(outcomes_read.get("headline")).casefold(), "Economic Outcomes Read no longer centers the productivity-to-capture test.")
    for signal in ("productivity_real_comp_gap", "labor_share_since_2020", "median_real_earnings_growth", "group_growth_spread_ppts"):
        require(pd.notna(pd.to_numeric((outcomes_read.get("signals") or {}).get(signal), errors="coerce")), f"Economic Outcomes Read signal is missing: {signal}")

    macro_headline = _macro_headline({
        "market": {"signals": {"aei": 65}},
        "data_center": {"signals": {"tracked_pipeline_capacity_gw": 280}},
        "connectivity": {"signals": {}},
        "grid_storage": {"signals": {"advanced_share": 35}},
        "adaptation": {"signals": {"consumer_active": 50}},
        "economic_impact": {"signals": {
            "microsoft_ai_arr_b": 37,
            "openai_arr_b": 20,
            "productivity_growth": 2.8,
            "productivity_real_comp_gap": 9.6,
            "labor_share_since_2020": -7.0,
            "median_real_earnings_growth": 0.8,
        }},
    })
    require(macro_headline == "AI use and provider revenue are growing, but worker gains still lag productivity.", "AI Macro overstates economic confirmation after Phase 1.")

    workforce_loader_source = (ROOT / "loaders" / "workforce_loader.py").read_text(encoding="utf-8")
    outcomes_loader_source = (ROOT / "loaders" / "economic_impact_loader.py").read_text(encoding="utf-8")
    require("refresh_templated_history(\n            FLOW_PATH" in workforce_loader_source, "Workforce refresh does not own the JOLTS labor-flow history.")
    require("EXPOSURE_PATH" in workforce_loader_source and "_read_exposure(EXPOSURE_PATH)" in workforce_loader_source, "Workforce lost the fixed exposure benchmark contract.")
    require("refresh_templated_history(\n            TRANSMISSION_PATH" in outcomes_loader_source, "Economic Outcomes refresh does not own worker-capture transmission.")
    require("refresh_templated_history(\n            DISTRIBUTION_PATH" in outcomes_loader_source, "Economic Outcomes refresh does not own earnings distribution.")

    evidence = (ROOT / "rendering" / "evidence.py").read_text(encoding="utf-8")
    for retained_key in ("occupation_exposure", "labor_flows_history", "value_transmission_history", "earnings_distribution_history"):
        require(retained_key in evidence, f"Evidence does not expose {retained_key}.")

    print(
        "PASS  v6.8 Phase 1 value transmission · "
        f"Workforce: {workforce_read['headline']} · Economic Outcomes: {outcomes_read['headline']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
