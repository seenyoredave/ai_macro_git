"""Regression test for the v7.2.0 thirteen-tab read architecture."""

from __future__ import annotations

from pathlib import Path
import json
import re
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

from analytics.read_architecture import (  # noqa: E402
    DOMAIN_ORDER,
    _attach_current_context,
    build_platform_reads,
)
from analytics.spatial_context import infrastructure_attribution  # noqa: E402
from loaders.workforce_loader import load_workforce_data  # noqa: E402
from loaders.connectivity_loader import load_connectivity_data  # noqa: E402
from loaders.economic_impact_loader import load_economic_impact_data  # noqa: E402
from rendering.snapshot_status import market_snapshot_label  # noqa: E402
from loaders.facility_registry_loader import (  # noqa: E402
    build_campus_registry,
    canonicalize_facility_observations,
    load_curated_facility_records,
    load_gigawatt_facility_records,
)


def _latest_sector_data() -> dict[str, pd.DataFrame]:
    history = pd.read_csv(PROJECT_ROOT / "archive" / "yf_history.csv")
    history["Date"] = pd.to_datetime(history["Date"], errors="coerce", format="mixed")
    current = history.loc[history["Date"].eq(history["Date"].max())].copy()
    return {str(sector): frame.reset_index(drop=True) for sector, frame in current.groupby("Sector")}


def _macro_frame() -> pd.DataFrame:
    history = pd.read_csv(PROJECT_ROOT / "archive" / "sector_history.csv")
    history["Date"] = pd.to_datetime(history["Date"], errors="coerce", format="mixed")
    current = history.loc[history["Date"].eq(history["Date"].max())].copy()
    if "AEI Score" in current and "Sector Score" not in current:
        current = current.rename(columns={"AEI Score": "Sector Score"})
    if "Sector Pressure" in current and "Pressure" not in current:
        current = current.rename(columns={"Sector Pressure": "Pressure"})
    return current


def _regime_metrics() -> dict:
    history = pd.read_csv(PROJECT_ROOT / "archive" / "macro_history.csv")
    row = history.iloc[-1].to_dict()
    metrics = {key: value for key, value in row.items() if pd.notna(value)}
    market = pd.read_csv(PROJECT_ROOT / "archive" / "yf_history.csv")
    market["Date"] = pd.to_datetime(market["Date"], errors="coerce", format="mixed")
    current = market.loc[market["Date"].eq(market["Date"].max())].copy()
    capex = pd.to_numeric(current.get("CapEx"), errors="coerce").where(lambda values: values > 0)
    ocf = pd.to_numeric(current.get("Operating Cash Flow"), errors="coerce")
    cash = pd.to_numeric(current.get("Cash"), errors="coerce")
    valid = capex.notna() & ocf.notna()
    cash_valid = capex.notna() & cash.notna()
    metrics["Deployment Funding Mix"] = {
        "current": {
            "internal_funding_coverage": float(ocf.loc[valid].sum() / capex.loc[valid].sum()) if valid.any() else np.nan,
            "cash_reserve_coverage_years": float(cash.loc[cash_valid].sum() / capex.loc[cash_valid].sum()) if cash_valid.any() else np.nan,
        }
    }
    return metrics


def _financial_conditions() -> tuple[dict, pd.DataFrame]:
    history = pd.read_csv(PROJECT_ROOT / "archive" / "fred_history.csv")
    date = pd.to_datetime(history.get("Date"), errors="coerce", format="mixed")
    value = pd.to_numeric(history.get("Financial Conditions NFCI"), errors="coerce")
    anfci = pd.to_numeric(history.get("Adjusted Financial Conditions ANFCI"), errors="coerce")
    frame = pd.DataFrame({"Date": date, "Value": value, "ANFCI": anfci}).dropna(subset=["Date", "Value"])
    latest = frame.sort_values("Date", kind="stable").iloc[-1]
    fred_data = {
        "Financial Conditions NFCI": {
            "value": float(latest["Value"]),
            "date": pd.Timestamp(latest["Date"]).date().isoformat(),
            "source": "Chicago Fed / FRED",
        }
    }
    return fred_data, frame


def _energy_data() -> dict:
    mapping = {
        "retail_history": "energy_retail_market_history.csv",
        "generation_history": "energy_generation_history.csv",
        "capacity_snapshot": "energy_capacity_snapshot.csv",
        "capacity_changes": "energy_capacity_changes_2026.csv",
        "generator_pipeline": "energy_generator_pipeline.csv",
        "interconnection_queue": "energy_interconnection_queue.csv",
        "interconnection_queue_summary": "energy_interconnection_queue_summary.csv",
        "wholesale_prices": "energy_wholesale_prices.csv",
    }
    data = {key: pd.read_csv(PROJECT_ROOT / "data" / name) for key, name in mapping.items()}
    history = pd.read_csv(PROJECT_ROOT / "data" / "energy_series_history.csv")
    history["Date"] = pd.to_datetime(history["Date"], errors="coerce", format="mixed")
    gas = history.loc[history["Series"].eq("Natural Gas Price")].sort_values("Date", kind="stable")
    data["series"] = {
        "Natural Gas Price": {
            "value": gas.iloc[-1]["Value"],
            "date": gas.iloc[-1]["Date"],
            "history": gas[["Date", "Value"]].copy(),
        }
    }
    data["queue_outcomes_summary"] = pd.read_csv(
        PROJECT_ROOT / "data" / "grid_storage" / "queue_outcomes_summary.csv"
    )
    data["reliability_reserve_margins"] = pd.read_csv(
        PROJECT_ROOT / "data" / "grid_storage" / "nerc_2026_summer_reserve_margins.csv"
    )
    data["operating_generators"] = pd.read_csv(
        PROJECT_ROOT / "data" / "energy_operating_generators.csv"
    )
    return data


def _infrastructure_data() -> dict:
    records = pd.concat(
        [load_curated_facility_records(), load_gigawatt_facility_records()],
        ignore_index=True,
        sort=False,
    )
    registry = canonicalize_facility_observations(records)
    campuses = build_campus_registry(registry)

    history = pd.read_csv(PROJECT_ROOT / "data" / "infrastructure" / "derived" / "compute_manufacturing_history.csv")
    history["Observation Date"] = pd.to_datetime(history["Observation Date"], errors="coerce", format="mixed")
    history = history.sort_values("Observation Date", kind="stable")
    latest = history.iloc[-1]
    prior = history.iloc[-13] if len(history) >= 13 else history.iloc[0]
    names = [
        "Computer and Peripheral Equipment Output",
        "Communications Equipment Output",
        "Semiconductor and Electronic Component Output",
        "Computer and Peripheral Equipment Capacity Utilization",
        "Semiconductor and Electronic Component Capacity Utilization",
    ]
    compute_series = {}
    for name in names:
        value = float(latest[name])
        base = float(prior[name])
        compute_series[name] = {
            "value": value,
            "date": latest["Observation Date"],
            "yoy_growth": value / base - 1.0 if base else np.nan,
        }
    compute_series["Info Processing Investment Level"] = {"value": np.nan, "yoy_growth": np.nan}

    projects = pd.read_csv(PROJECT_ROOT / "data" / "infrastructure" / "derived" / "compute_project_ledger.csv")
    project_summary = {
        "projects": int(len(projects)),
        "expected_capex_usd_b": pd.to_numeric(projects["Expected CapEx USD B"], errors="coerce").sum(min_count=1),
        "direct_funding_usd_b": pd.to_numeric(projects["Direct Funding USD B"], errors="coerce").sum(min_count=1),
    }

    construction = pd.read_csv(PROJECT_ROOT / "data" / "infrastructure_construction_history.csv")
    construction["Observation Date"] = pd.to_datetime(construction["Observation Date"], errors="coerce", format="mixed")
    construction = construction.sort_values("Observation Date", kind="stable")
    current = construction.iloc[-1]
    prior = construction.iloc[-13]
    construction_series = {}
    for name in [
        "Data Center Construction",
        "Computer, Electronic & Electrical Manufacturing Construction",
        "Electric Power Construction",
        "Communication Construction",
        "Public Highway and Street Construction",
        "Public Transportation Construction",
        "Public Water Supply Construction",
    ]:
        value = pd.to_numeric(current.get(name), errors="coerce")
        base = pd.to_numeric(prior.get(name), errors="coerce")
        construction_series[name] = {
            "value": value,
            "date": current["Observation Date"],
            "yoy_growth": value / base - 1.0 if pd.notna(value) and pd.notna(base) and base else np.nan,
        }

    return {
        "facility_registry": registry,
        "campus_registry": campuses,
        "compute_manufacturing": {
            "series": compute_series,
            "project_summary": project_summary,
            "projects": projects,
        },
        "series": construction_series,
        "construction_history": construction,
        "infrastructure_attribution": infrastructure_attribution(construction),
    }


def _water_data(infrastructure_data: dict) -> dict:
    summary = json.loads(
        (PROJECT_ROOT / "data" / "water" / "derived" / "water_national_summary.json").read_text()
    )
    registry = infrastructure_data["facility_registry"].copy()
    drought = pd.read_csv(PROJECT_ROOT / "data" / "water" / "derived" / "usdm_state_drought_snapshot.csv")
    drought_columns = ["State", "D1+ Area Percent", "D2+ Area Percent", "D3+ Area Percent", "D4 Area Percent", "Snapshot Date"]
    registry = registry.merge(drought[drought_columns], on="State", how="left")
    evidence = registry.get("Water Evidence Grade", pd.Series("", index=registry.index)).fillna("").astype(str)
    return {
        "summary": summary,
        "usgs_2020_top_withdrawals": pd.read_csv(PROJECT_ROOT / "data" / "water" / "derived" / "usgs_2020_top_withdrawals.csv"),
        "usgs_state_categories": pd.read_csv(PROJECT_ROOT / "data" / "water" / "derived" / "usgs_2015_state_category_summary.csv"),
        "facility_context": registry,
        "facility_context_summary": {
            "facilities": int(len(registry)),
            "state_identified_records": int(registry.get("State", pd.Series("", index=registry.index)).fillna("").astype(str).str.strip().ne("").sum()),
            "direct_water_evidence_records": int(evidence.ne("").sum()),
            "quantified_withdrawal_records": 0,
            "quantified_consumption_records": 0,
        },
    }


def _adaptation_data() -> dict:
    history = pd.read_csv(PROJECT_ROOT / "data" / "adaptation_national_history.csv")
    history["Date"] = pd.to_datetime(history["Date"], errors="coerce", format="mixed")
    history = history.sort_values("Date", kind="stable")
    latest = history.iloc[-1]
    prior = history.iloc[-13] if len(history) >= 13 else history.iloc[0]
    consumer = pd.read_csv(PROJECT_ROOT / "data" / "adoption_consumer_history.csv")
    consumer["Date"] = pd.to_datetime(consumer["Date"], errors="coerce", format="mixed")
    consumer["Value"] = pd.to_numeric(consumer["Value"], errors="coerce")

    def latest_consumer(series: str) -> dict:
        rows = consumer.loc[consumer["Series"].astype(str).eq(series)].sort_values("Date", kind="stable")
        row = rows.iloc[-1]
        return {"value": float(row["Value"]), "date": row["Date"], "series_id": row["Series ID"]}

    return {
        "current_use": latest["Current AI Use"],
        "expected_use": latest["Expected AI Use"],
        "expected_adoption_gap": latest["Expected Adoption Gap"],
        "annual_change": latest["Current AI Use"] - prior["Current AI Use"],
        "sector_snapshot": pd.read_csv(PROJECT_ROOT / "data" / "adaptation_sector_snapshot.csv"),
        "snapshot_date": latest["Date"],
        "consumer_history": consumer,
        "consumer_overall": latest_consumer("Overall use"),
        "consumer_personal": latest_consumer("Personal / outside work"),
        "consumer_work": latest_consumer("Work use"),
        "consumer_active": latest_consumer("Used last week"),
        "consumer_daily": latest_consumer("Daily use"),
    }


def main() -> None:
    infrastructure = _infrastructure_data()
    connectivity = load_connectivity_data(infrastructure.get("campus_registry"))
    infrastructure["connectivity"] = connectivity
    context_event = {
        "event_id": "test-context",
        "priority": 100,
        "display": "A confirmed primary-source event adds current context without displacing the underlying data read.",
        "source_name": "Primary source",
        "source_label": "Primary source",
        "source_url": "https://example.com/source",
        "status": "Ordered",
        "resolution_status": "unresolved",
    }
    context_reference = {
        "reference_number": 1,
        "event_id": "test-context",
        "source_label": "Primary source",
        "source_url": "https://example.com/source",
    }
    current_context = {
        "events": [context_event],
        "references": [context_reference],
        "by_domain": {
            "data_center": {
                "events": [context_event],
                "references": [context_reference],
            }
        },
    }
    fred_data, nfci_history = _financial_conditions()
    reads = build_platform_reads(
        sector_data=_latest_sector_data(),
        dashboard_data={"macro_df": _macro_frame()},
        regime_metrics=_regime_metrics(),
        fred_data=fred_data,
        nfci_history=nfci_history,
        energy_data=_energy_data(),
        debt_markets_data={"series": {}},
        infrastructure_data=infrastructure,
        connectivity_data=connectivity,
        water_data=_water_data(infrastructure),
        adaptation_data=_adaptation_data(),
        workforce_data=load_workforce_data(),
        economic_impact_data=load_economic_impact_data(),
        current_context=current_context,
    )

    expected = set(DOMAIN_ORDER) | {"macro"}
    if set(reads) != expected:
        raise AssertionError(f"Unexpected read surfaces: {sorted(reads)}")
    adoption_signals = reads["adaptation"].get("signals", {})
    for key in ("consumer_overall", "consumer_personal", "consumer_work", "consumer_active", "consumer_daily"):
        if pd.isna(pd.to_numeric(adoption_signals.get(key), errors="coerce")):
            raise AssertionError(f"Adoption Read is missing the retained societal signal: {key}")
    adoption_refs = {str(item.get("source_label")) for item in reads["adaptation"].get("references", [])}
    if not {"Real-Time Population Survey via FRED", "U.S. Census BTOS"}.issubset(adoption_refs):
        raise AssertionError("Adoption Read should retain both RPS/FRED and Census BTOS references.")
    for domain in expected:
        read = reads[domain]
        required = {"headline", "summary", "watchpoint", "confidence", "importance", "signals", "highlights", "version"}
        if not required.issubset(read):
            raise AssertionError(f"{domain} read is missing contract fields: {sorted(required - set(read))}")
        headline_limit = 15 if domain == "macro" else 12
        if len(str(read["headline"]).split()) > headline_limit:
            raise AssertionError(f"{domain} headline exceeds the compact budget: {read['headline']}")
        summary_limit = 100 if domain == "macro" else 90
        if len(str(read["summary"]).split()) > summary_limit:
            raise AssertionError(f"{domain} summary exceeds its {summary_limit}-word budget")
        if len(str(read["watchpoint"]).split()) > 30:
            raise AssertionError(f"{domain} watchpoint is too long")
        interrogative_start = re.compile(r"(?:^|[.!?]\s+)(?:who|what|when|where|why|how|whether)\b", re.IGNORECASE)
        for field in ("headline", "summary"):
            if interrogative_start.search(str(read[field]).strip()):
                raise AssertionError(f"{domain} {field} starts a sentence with a 5W/H interrogative: {read[field]}")

    water = reads["water"]
    if water["signals"].get("quantified_use_records") != 0:
        raise AssertionError("Water Read must retain the current zero quantified-use evidence boundary.")
    for signal in ("states_with_d2_area", "published_capacity_in_25pct_d2_states_gw", "direct_evidence_share_pct"):
        if pd.isna(pd.to_numeric(water["signals"].get(signal), errors="coerce")):
            raise AssertionError(f"Water Read is missing the Phase 2 exposure signal: {signal}")
    if not any(token in water["headline"].casefold() for token in ("water", "drought", "disclosure")):
        raise AssertionError("Water Read no longer centers local exposure and disclosure.")

    data_center_read = reads["data_center"]
    if not str(data_center_read.get("summary") or "").strip():
        raise AssertionError("Data Centers Read regressed to an empty statistical fallback.")
    if "not for estimating the total U.S. data-center fleet" not in data_center_read.get("summary", ""):
        raise AssertionError("Data Centers Read lost the project-registry versus national-census boundary.")
    if not int(data_center_read.get("signals", {}).get("broad_operating") or 0) or not int(data_center_read.get("signals", {}).get("broad_development") or 0):
        raise AssertionError("Data Centers Read is not interpreting the available operating/development records.")

    power_read = reads["power"]
    if "advanced_share" in power_read.get("signals", {}):
        raise AssertionError("Power Read retained the Grid & Storage queue-maturity signal.")
    if "queue" in power_read.get("watchpoint", "").casefold():
        raise AssertionError("Power watchpoint crossed into Grid & Storage ownership.")

    grid_read = reads["grid_storage"]
    for signal in ("queue_gw", "historical_operational_pct", "median_request_to_cod_years", "lowest_extreme_margin_pct", "operating_storage_weighted_duration_hours"):
        if pd.isna(pd.to_numeric(grid_read["signals"].get(signal), errors="coerce")):
            raise AssertionError(f"Grid & Storage Read is missing the Phase 2 deliverability signal: {signal}")

    workforce_read = reads["workforce"]
    if "employment" not in workforce_read.get("signals", {}):
        # The structured signal keys are series-specific, so require at least one labor signal.
        if not any("employment" in str(key) or "openings" in str(key) for key in workforce_read.get("signals", {})):
            raise AssertionError("Workforce Read is missing labor-market signals.")

    impact_read = reads["economic_impact"]
    if not any("productivity" in str(key) or "output" in str(key) for key in impact_read.get("signals", {})):
        raise AssertionError("Economic Outcomes Read is missing realized-economy signals.")

    macro = reads["macro"]
    selected = macro["signals"].get("selected_domains", [])
    if not 2 <= len(selected) <= 3 or len(selected) != len(set(selected)):
        raise AssertionError(f"Macro synthesis did not select 2-3 distinct domains: {selected}")
    if len(selected) >= len(DOMAIN_ORDER):
        raise AssertionError("Macro synthesis allocated space to every domain.")
    for domain in DOMAIN_ORDER:
        if reads[domain]["summary"] and reads[domain]["summary"] in macro["summary"]:
            raise AssertionError(f"Macro summary copied the {domain} read verbatim.")
    if not macro.get("recent_context") or not macro.get("references", []):
        raise AssertionError("Macro read did not retain referenced weekly context and selected-domain sources.")
    if len(macro.get("references", [])) > 5:
        raise AssertionError("Macro references exceeded the compact inline budget.")
    if "relevance" in macro:
        raise AssertionError("The retired Why-it-matters macro layer returned to the Read payload.")
    macro_reference_labels = {str(item.get("source_label") or item.get("source_name") or "") for item in macro.get("references", [])}
    anchor_sources = {
        str((item.get("reference_specs") or [{}])[0].get("source_label") or "")
        for item in macro.get("evidence", [])
        if item.get("reference_specs")
    }
    if not anchor_sources.issubset(macro_reference_labels):
        raise AssertionError(f"Macro references drifted away from the displayed evidence anchors: expected {anchor_sources}, found {macro_reference_labels}")

    renderer_contracts = {
        "market.py": 'tab_read=platform_reads.get("market")',
        "finance.py": 'tab_read=platform_reads.get("finance")',
        "compute.py": 'tab_read=platform_reads.get("compute")',
        "data_center.py": 'tab_read=platform_reads.get("data_center")',
        "connectivity.py": 'tab_read=platform_reads.get("connectivity")',
        "power.py": 'tab_read=platform_reads.get("power")',
        "grid_storage.py": 'tab_read=platform_reads.get("grid_storage")',
        "water.py": 'tab_read=platform_reads.get("water")',
        "adaptation.py": 'tab_read=platform_reads.get("adaptation")',
        "workforce.py": 'tab_read=platform_reads.get("workforce")',
        "economic_impact.py": 'tab_read=platform_reads.get("economic_impact")',
    }
    dashboard_source = (PROJECT_ROOT / "rendering" / "dashboard.py").read_text()
    for filename, contract in renderer_contracts.items():
        if contract not in dashboard_source:
            raise AssertionError(f"Dashboard does not pass the structured read to {filename}.")
    macro_source = (PROJECT_ROOT / "rendering" / "macro.py").read_text()
    components_source = (PROJECT_ROOT / "rendering" / "components.py").read_text()
    if 'render_section("Purpose Statement")' in macro_source or 'render_definition(METRIC_DEFINITIONS["Purpose Statement"])' in macro_source:
        raise AssertionError("Purpose Statement still appears as a permanent AI Macro section.")
    if "_render_front_page_purpose" in macro_source or "front-page-purpose" in macro_source:
        raise AssertionError("Purpose disclosure is still owned by the AI Macro domain.")
    if 'st.expander("About this platform", expanded=False)' not in components_source:
        raise AssertionError("Purpose disclosure must be collapsed by default.")
    theme_source = (PROJECT_ROOT / "rendering" / "theme.css").read_text(encoding="utf-8")
    app_source = (PROJECT_ROOT / "ai_macro.py").read_text()
    definitions_source = (PROJECT_ROOT / "config" / "metric_definitions.py").read_text()
    evidence_source = (PROJECT_ROOT / "rendering" / "evidence.py").read_text(encoding="utf-8")
    for required in (
        "AI Macro is built around evidence, not allegiance.",
        "Social media is excluded from the research pipeline.",
        "Corroboration means independent evidence, not repeated publication.",
        "No source is owed agreement.",
    ):
        if required not in evidence_source:
            raise AssertionError("Evidence standards statement is incomplete.")
    if 'st.expander("Evidence standards", expanded=False)' not in evidence_source:
        raise AssertionError("Evidence standards must lead the Evidence tab in a collapsed disclosure.")
    approved_subtitle = (
        "An economic research platform focused on the evolution of the AI economy."
    )
    if approved_subtitle not in app_source:
        raise AssertionError("AI Macro brand and descriptor are not installed in the masthead.")
    masthead_position = app_source.index("render_masthead(")
    purpose_position = app_source.index('render_platform_purpose(METRIC_DEFINITIONS["Purpose Statement"])')
    dashboard_position = app_source.index("render_research_dashboard(")
    if not masthead_position < purpose_position < dashboard_position:
        raise AssertionError("Purpose disclosure is not between the platform masthead and the domain dashboard.")
    if 'st.session_state.market_snapshot_frame = raw_universe_data.get("yfinance")' not in app_source:
        raise AssertionError("Loaded market data is not persisted across Streamlit reruns.")
    if 'status=market_snapshot_label(st.session_state.get("market_snapshot_frame"))' not in app_source:
        raise AssertionError("Masthead market date does not read from rerun-safe session state.")
    if 'status=market_snapshot_label(raw_universe_data.get("yfinance"))' in app_source:
        raise AssertionError("Masthead still depends on rebuild-local raw_universe_data and will fail on rerun.")
    loaded_market = pd.DataFrame({
        "Market Data Date": ["2026-08-07"] * 203 + ["2026-07-29"],
        "Date": ["2026-08-07"] * 204,
    })
    if market_snapshot_label(loaded_market) != "Market data 8.7.2026":
        raise AssertionError("Masthead market date does not follow the loaded market dataset.")
    if 'market_report["energy"]' in app_source or 'render_source("Power"' in app_source:
        raise AssertionError("Power refresh diagnostics remain attached to the developer load report.")
    approved_purpose = (
        "AI Macro traces the AI economy from capital and construction through deployment, adoption, and economic results. "
        "Using publicly available data, it connects companies and markets with the data centers, resources, and infrastructure behind "
        "the buildout—and examines how that buildout is reshaping the broader U.S. economy. Its central questions are whether rising "
        "investment and capacity are producing durable use, broad participation, and realized value—and how the resulting gains, costs, "
        "and risks are distributed across investors, businesses, workers, communities, and regions."
    )
    if approved_purpose not in definitions_source:
        raise AssertionError("The approved Purpose Statement copy is not installed verbatim.")

    if ".st-key-platform-purpose details > summary" not in theme_source:
        raise AssertionError("Purpose disclosure has no dedicated summary alignment rule.")
    if "padding-block: 0.72rem" not in theme_source or "align-items: center" not in theme_source:
        raise AssertionError("Purpose disclosure summary is missing balanced vertical padding or centering.")
    purpose_details_rule = theme_source[theme_source.index('.st-key-platform-purpose [data-testid="stExpanderDetails"]'):]
    if ".st-key-platform-purpose .rm-purpose-copy" not in purpose_details_rule:
        raise AssertionError("Expanded Purpose text is missing its dedicated centering wrapper.")
    if "min-height: 8.25rem" not in purpose_details_rule or "padding: 1.35rem 1.35rem 1.45rem 1.35rem" not in purpose_details_rule:
        raise AssertionError("Expanded Purpose text does not have balanced visible breathing room.")
    if "display: flex" not in purpose_details_rule or "align-items: center" not in purpose_details_rule:
        raise AssertionError("Expanded Purpose text is not vertically centered.")

    common_source = (PROJECT_ROOT / "rendering" / "common.py").read_text()
    if "def _render_floating_terms(" not in common_source or "st.popover(" not in common_source:
        raise AssertionError("The shared domain-header Terms control is not installed.")
    if "rm-metric-registry-divider" in common_source or "rm-metric-registry-divider" in theme_source:
        raise AssertionError("The retired inline metric registry divider remains in the platform.")
    terms_rule = theme_source[theme_source.index('div[class*="st-key-floating-terms-"] {'):].split("}", 1)[0]
    if 'st-key-floating-terms-' not in theme_source or "justify-content: flex-end" not in terms_rule:
        raise AssertionError("The Terms control is not aligned to the domain header edge.")
    if "position: fixed" in terms_rule:
        raise AssertionError("The Terms control regressed to a chart-obscuring viewport overlay.")
    for filename in ("macro.py", "market.py", "finance.py", "compute.py", "data_center.py", "connectivity.py", "power.py", "grid_storage.py", "water.py", "adaptation.py", "workforce.py", "economic_impact.py"):
        source = (PROJECT_ROOT / "rendering" / filename).read_text()
        if "_render_floating_terms(" not in source:
            raise AssertionError(f"{filename} does not expose the shared floating Terms control.")
        if "render_line_break()" in source:
            raise AssertionError(f"{filename} still inserts the retired post-header line break.")

    expected_tabs = '["AI MACRO", "MARKET", "FINANCE", "COMPUTE", "DATA CENTERS", "CONNECTIVITY", "POWER", "GRID & STORAGE", "WATER", "ADOPTION", "WORKFORCE", "ECONOMIC OUTCOMES", "EVIDENCE"]'
    if expected_tabs not in app_source:
        raise AssertionError("The app does not expose the approved 13-tab architecture.")
    if '"ENERGY"' in app_source or '"INFRASTRUCTURE"' in app_source:
        raise AssertionError("Retired Energy or Infrastructure tab labels remain visible.")
    if "macro-buildout-leadership-rotation" not in macro_source:
        raise AssertionError("Buildout Leadership Rotation was not rehomed to AI Macro.")

    evidence_source = (PROJECT_ROOT / "rendering" / "evidence.py").read_text()
    if "render_domain_read" in evidence_source:
        raise AssertionError("Evidence should remain a provenance surface, not a narrative-read surface.")
    for token in (
        "def _render_evidence_lookup(",
        "def _evidence_lineage_rows(",
        '"Find evidence for"',
        '"Search this evidence path"',
        '"Evidence layer"',
        '"Definition / boundary"',
        '"Primary sources"',
        '"Current Context snapshot:',
        "def _sync_evidence_detail_view(",
        "on_change=_sync_evidence_detail_view",
    ):
        if token not in evidence_source:
            raise AssertionError(f"Evidence claim-to-source navigation is missing: {token}")
    dashboard_source = (PROJECT_ROOT / "rendering" / "dashboard.py").read_text()
    if "platform_reads=platform_reads" not in dashboard_source:
        raise AssertionError("Evidence does not receive the current domain Reads for claim tracing.")
    market_source = (PROJECT_ROOT / "rendering" / "market.py").read_text()
    if "_render_sector_read" not in market_source:
        raise AssertionError("The sector-level read was not retained.")
    for approved_label in ('"Market value concentration"', '"One-year return contribution"', '"Ownership and participation"'):
        if approved_label not in market_source:
            raise AssertionError(f"Approved Market label missing: {approved_label}")
    market_render_body = market_source[market_source.index("def render_market_tab("):]
    order_tokens = [
        '_render_market_ledger_summary(market_ledger, (market_universe_summary or {}).get("valuation_context"))',
        'render_signal_rail(_assessment_stats',
        '_render_market_structure(market_ledger)',
        'render_section("Sector valuations and trading"',
        '"Sector profile"',
        '_render_market_constituent_ledger(selection, market_ledger)',
    ]
    order_positions = [market_render_body.index(token) for token in order_tokens]
    if order_positions != sorted(order_positions):
        raise AssertionError("Market current-state analysis no longer precedes deep structure/history.")

    for domain in DOMAIN_ORDER:
        domain_references = reads[domain].get("references", [])
        if not domain_references:
            raise AssertionError(f"{domain} Read is missing its References section data.")
    if len(reads["market"].get("references", [])) != 2:
        raise AssertionError("Market Read should retain exactly two compact references.")
    if not reads["macro"].get("references"):
        raise AssertionError("AI Macro Read did not inherit selected-domain references.")

    from rendering.read_markup import build_domain_read_html

    market_markup = build_domain_read_html(
        reads["market"], label="Market Read", accent_color="#a78bfa"
    )
    if market_markup.count('class="rm-read-section-divider"') != 1:
        raise AssertionError("The shared Read component must emit exactly one post-Read divider.")
    expected_order = [
        "rm-domain-read-kicker",
        "rm-domain-read-title",
        "rm-domain-read-copy",
        "References",
    ]
    positions = [market_markup.index(token) for token in expected_order]
    if positions != sorted(positions):
        raise AssertionError("Market Read sections are not rendered in the required order.")
    if "\n" in market_markup or "&lt;div" in market_markup:
        raise AssertionError("Domain Read markup can leak escaped HTML into Streamlit.")
    if "Watchpoint" in market_markup:
        raise AssertionError("Watchpoint leaked back into the visible Read component.")
    if '<div class="rm-domain-read-refs"><span>References</span>' not in market_markup:
        raise AssertionError("References did not retain the compact inline layout.")
    if market_markup.count("[1]") != 1 or market_markup.count("[2]") != 1:
        raise AssertionError("Market Read references are not numbered side by side.")
    if "confidence" in market_markup.casefold():
        raise AssertionError("Internal evidence completeness leaked into the public Read label.")
    macro_markup = build_domain_read_html(
        reads["macro"], label="Read", accent_color="#60a5fa", macro=True
    )
    if "What it means" in macro_markup or "Why it matters" in macro_markup or "rm-domain-read-relevance" in macro_markup:
        raise AssertionError("The retired Why-it-matters macro layer returned to visible Read markup.")
    if "<ol" in market_markup or "<li" in market_markup:
        raise AssertionError("References regressed to a stacked list.")

    context_markup = build_domain_read_html(
        {
            **reads["market"],
            "current_context_items": [{
                "text": "Recent developments.",
                "reference_number": 1,
                "source_url": "https://example.com/source",
            }],
        },
        label="Market Read",
        accent_color="#a78bfa",
    )
    if "Watchpoint" in context_markup:
        raise AssertionError("Watchpoint leaked into the Current Context rendering path.")
    if not (context_markup.index("Recent developments") < context_markup.index("References")):
        raise AssertionError("Read context and references are out of order.")

    rejected_context = _attach_current_context(
        reads["market"],
        {
            "events": [{
                "display": "No qualifying development found.",
                "verification_status": "no_match",
                "source_url": "https://example.com/no-match",
            }]
        },
    )
    if rejected_context.get("current_context_items"):
        raise AssertionError("A no-match placeholder leaked into a public Read.")

    if selected != ["market", "data_center", "economic_impact"]:
        raise AssertionError(f"Macro lifecycle anchors drifted: {selected}")

    print(
        "PASS  v7.2.0 read architecture · "
        f"{len(DOMAIN_ORDER)} tab reads · {len(selected)} macro-selected domains · "
        f"headline: {macro['headline']}"
    )


if __name__ == "__main__":
    main()
