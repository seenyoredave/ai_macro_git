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

from analytics.dashboard_context import DashboardContext  # noqa: E402
from analytics.domain_state import with_domain_state  # noqa: E402
from analytics.read_evidence import EVIDENCE_ARCHITECTURE_VERSION, build_economic_impact_evidence, build_workforce_evidence  # noqa: E402
from analytics.read_prompts import BASE_INSTRUCTIONS  # noqa: E402
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
    require(EVIDENCE_ARCHITECTURE_VERSION == "1.1.0", "v7 evidence architecture version drifted.")
    require(readme.startswith("# AI Macro\n"), "README no longer opens with the project overview.")
    require("## v" not in readme and "review build" not in readme.casefold(), "README has drifted back into release-note copy.")

    workforce_tool = signature_tool("workforce_outcomes_matrix")
    outcomes_tool = signature_tool("realized_value_transmission")
    require(workforce_tool.status == "current" and workforce_tool.key_pattern == "workforce-outcomes-matrix", "Workforce signature tool is not current or correctly keyed.")
    require(outcomes_tool.status == "current" and outcomes_tool.key_pattern == "economic-impact-panel-value-transmission", "Economic Outcomes signature tool is not current or correctly keyed.")

    workforce_data = load_workforce_data()
    outcomes_data = load_economic_impact_data()
    workforce_packet = build_workforce_evidence(with_domain_state(DashboardContext(workforce_data=workforce_data), "workforce")).to_dict()
    outcomes_packet = build_economic_impact_evidence(with_domain_state(DashboardContext(economic_impact_data=outcomes_data), "economic_impact")).to_dict()
    workforce_ids = {str(item.get("id") or "").split(".", 1)[-1] for item in workforce_packet.get("facts", [])}
    outcomes_facts = {str(item.get("id") or "").split(".", 1)[-1]: item for item in outcomes_packet.get("facts", [])}
    require("occupation_exposure_count" in workforce_ids, "Workforce evidence lost its occupation-exposure fact.")
    require(any("Task-exposure" in boundary or "task exposure" in boundary for boundary in workforce_packet.get("boundaries", [])), "Workforce evidence lost the observed-outcomes boundary.")
    for fact_id in ("productivity_real_comp_gap", "labor_share_since_2020", "median_real_earnings_growth", "group_growth_spread_ppts"):
        fact = outcomes_facts.get(fact_id, {})
        require(pd.notna(pd.to_numeric(fact.get("value"), errors="coerce")), f"Economic Outcomes evidence is missing: {fact_id}")
    require("supplied evidence is the exclusive factual record" in BASE_INSTRUCTIONS.casefold(), "v7 prompt no longer makes deterministic evidence authoritative.")
    require("separate observation from interpretation" in BASE_INSTRUCTIONS.casefold(), "v7 prompt lost the observation-versus-interpretation boundary.")

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
        "PASS  v7 value-transmission evidence · "
        f"{len(workforce_packet.get('facts', []))} Workforce facts · "
        f"{len(outcomes_packet.get('facts', []))} Economic Outcomes facts"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
