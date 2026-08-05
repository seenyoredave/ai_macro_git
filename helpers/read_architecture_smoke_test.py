"""Regression test for the v6.5 twelve-tab read architecture."""

from __future__ import annotations

from pathlib import Path
import json
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

from analytics.read_architecture import DOMAIN_ORDER, build_platform_reads  # noqa: E402
from analytics.spatial_context import infrastructure_attribution  # noqa: E402
from loaders.workforce_loader import load_workforce_data  # noqa: E402
from loaders.economic_impact_loader import load_economic_impact_data  # noqa: E402
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
    registry = infrastructure_data["facility_registry"]
    evidence = registry.get("Water Evidence Grade", pd.Series("", index=registry.index)).fillna("").astype(str)
    return {
        "summary": summary,
        "usgs_2020_top_withdrawals": pd.read_csv(PROJECT_ROOT / "data" / "water" / "derived" / "usgs_2020_top_withdrawals.csv"),
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
    return {
        "current_use": latest["Current AI Use"],
        "expected_use": latest["Expected AI Use"],
        "expected_adoption_gap": latest["Expected Adoption Gap"],
        "annual_change": latest["Current AI Use"] - prior["Current AI Use"],
        "sector_snapshot": pd.read_csv(PROJECT_ROOT / "data" / "adaptation_sector_snapshot.csv"),
        "snapshot_date": latest["Date"],
    }


def main() -> None:
    infrastructure = _infrastructure_data()
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
        water_data=_water_data(infrastructure),
        adaptation_data=_adaptation_data(),
        workforce_data=load_workforce_data(),
        economic_impact_data=load_economic_impact_data(),
        current_context=current_context,
    )

    expected = set(DOMAIN_ORDER) | {"macro"}
    if set(reads) != expected:
        raise AssertionError(f"Unexpected read surfaces: {sorted(reads)}")
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

    water = reads["water"]
    if water["signals"].get("quantified_use_records") != 0:
        raise AssertionError("Water Read must retain the current zero quantified-use evidence boundary.")
    if "attribution" not in water["headline"].casefold() and "evidence" not in water["headline"].casefold():
        raise AssertionError("Water Read no longer distinguishes competition from AI attribution.")

    power_read = reads["power"]
    if "advanced_share" in power_read.get("signals", {}):
        raise AssertionError("Power Read retained the Grid & Storage queue-maturity signal.")
    if "queue" in power_read.get("watchpoint", "").casefold():
        raise AssertionError("Power watchpoint crossed into Grid & Storage ownership.")

    grid_read = reads["grid_storage"]
    if pd.isna(pd.to_numeric(grid_read["signals"].get("queue_gw"), errors="coerce")):
        raise AssertionError("Grid & Storage Read is missing the interconnection pipeline.")

    workforce_read = reads["workforce"]
    if "employment" not in workforce_read.get("signals", {}):
        # The structured signal keys are series-specific, so require at least one labor signal.
        if not any("employment" in str(key) or "openings" in str(key) for key in workforce_read.get("signals", {})):
            raise AssertionError("Workforce Read is missing labor-market signals.")

    impact_read = reads["economic_impact"]
    if not any("productivity" in str(key) or "output" in str(key) for key in impact_read.get("signals", {})):
        raise AssertionError("Economic Impact Read is missing realized-economy signals.")

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

    renderer_contracts = {
        "market.py": 'tab_read=platform_reads.get("market")',
        "finance.py": 'tab_read=platform_reads.get("finance")',
        "compute.py": 'tab_read=platform_reads.get("compute")',
        "data_center.py": 'tab_read=platform_reads.get("data_center")',
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
    purpose_call = '_render_front_page_purpose()'
    header_call = 'render_tab_header('
    if purpose_call not in macro_source:
        raise AssertionError("Front-page Purpose disclosure is missing.")
    render_body = macro_source[macro_source.index("def render_macro_tab"): ]
    if render_body.index(purpose_call) > render_body.index(header_call):
        raise AssertionError("Purpose disclosure must appear above the AI Macro title and subtitle.")
    if 'render_section("Purpose Statement")' in macro_source or 'render_definition(METRIC_DEFINITIONS["Purpose Statement"])' in macro_source:
        raise AssertionError("Purpose Statement still appears as a permanent AI Macro section.")
    if 'st.expander("Purpose statement", expanded=False)' not in macro_source:
        raise AssertionError("Purpose disclosure must be collapsed by default.")
    if 'class="rm-purpose-divider"' not in macro_source:
        raise AssertionError("AI Macro is missing the divider between Purpose and the tab header.")
    theme_source = (PROJECT_ROOT / "rendering" / "theme.css").read_text(encoding="utf-8")
    app_source = (PROJECT_ROOT / "ai_macro.py").read_text()
    definitions_source = (PROJECT_ROOT / "config" / "metric_definitions.py").read_text()
    if 'render_masthead(\n    "AI Macro",\n    "An AI economic research platform",' not in app_source:
        raise AssertionError("AI Macro brand and descriptor are not installed in the masthead.")
    approved_purpose = (
        "AI Macro traces the AI economy from capital and construction through deployment, adoption, and economic results. "
        "Using publicly available data, it connects companies and markets with the data centers, resources, and infrastructure "
        "behind the buildout—and examines how that buildout is reshaping the broader U.S. economy. Its central questions are "
        "whether rising investment and capacity are producing durable use, broad participation, and realized value—and how the "
        "resulting gains, costs, and risks are distributed across investors, businesses, workers, communities, and regions."
    )
    if approved_purpose not in definitions_source:
        raise AssertionError("The approved Purpose Statement copy is not installed verbatim.")

    if ".st-key-front-page-purpose details > summary" not in theme_source:
        raise AssertionError("Purpose disclosure has no dedicated summary alignment rule.")
    if ".rm-purpose-divider" not in theme_source:
        raise AssertionError("Purpose divider has no protected platform style.")
    if "padding-block: 0.72rem" not in theme_source or "align-items: center" not in theme_source:
        raise AssertionError("Purpose disclosure summary is missing balanced vertical padding or centering.")
    purpose_details_rule = theme_source[theme_source.index('.st-key-front-page-purpose [data-testid="stExpanderDetails"]'):]
    if ".st-key-front-page-purpose .rm-purpose-copy" not in purpose_details_rule:
        raise AssertionError("Expanded Purpose text is missing its dedicated centering wrapper.")
    if "min-height: 8.25rem" not in purpose_details_rule or "padding: 1.35rem 1.35rem 1.45rem 1.35rem" not in purpose_details_rule:
        raise AssertionError("Expanded Purpose text does not have balanced visible breathing room.")
    if "display: flex" not in purpose_details_rule or "align-items: center" not in purpose_details_rule:
        raise AssertionError("Expanded Purpose text is not vertically centered.")

    common_source = (PROJECT_ROOT / "rendering" / "common.py").read_text()
    if 'class="rm-metric-registry-divider"' not in common_source:
        raise AssertionError("The metric registry no longer owns its mandatory divider.")
    for filename in ("macro.py", "market.py", "finance.py", "compute.py", "data_center.py", "power.py", "grid_storage.py", "water.py", "adaptation.py", "workforce.py", "economic_impact.py"):
        source = (PROJECT_ROOT / "rendering" / filename).read_text()
        if "_render_tab_metric_registry(" not in source:
            raise AssertionError(f"{filename} does not use the shared metric-registry divider contract.")

    expected_tabs = '["AI MACRO", "MARKET", "FINANCE", "COMPUTE", "DATA CENTER", "POWER", "GRID & STORAGE", "WATER", "ADAPTATION", "WORKFORCE", "ECONOMIC IMPACT", "EVIDENCE"]'
    if expected_tabs not in app_source:
        raise AssertionError("The app does not expose the approved 12-tab architecture.")
    if '"ENERGY"' in app_source or '"INFRASTRUCTURE"' in app_source:
        raise AssertionError("Retired Energy or Infrastructure tab labels remain visible.")
    if "macro-buildout-leadership-rotation" not in macro_source:
        raise AssertionError("Buildout Leadership Rotation was not rehomed to AI Macro.")

    evidence_source = (PROJECT_ROOT / "rendering" / "evidence.py").read_text()
    if "render_domain_read" in evidence_source:
        raise AssertionError("Evidence should remain a provenance surface, not a narrative-read surface.")
    market_source = (PROJECT_ROOT / "rendering" / "market.py").read_text()
    if "_render_sector_read" not in market_source:
        raise AssertionError("The sector-level read was not retained.")

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
    if "<ol" in market_markup or "<li" in market_markup:
        raise AssertionError("References regressed to a stacked list.")

    context_markup = build_domain_read_html(
        {
            **reads["market"],
            "current_context_items": [{
                "text": "Current context.",
                "reference_number": 1,
                "source_url": "https://example.com/source",
            }],
        },
        label="Market Read",
        accent_color="#a78bfa",
    )
    if "Watchpoint" in context_markup:
        raise AssertionError("Watchpoint leaked into the Current Context rendering path.")
    if not (context_markup.index("Current context") < context_markup.index("References")):
        raise AssertionError("Read context and references are out of order.")

    print(
        "PASS  v6.5.2 read architecture · "
        f"{len(DOMAIN_ORDER)} tab reads · {len(selected)} macro-selected domains · "
        f"headline: {macro['headline']}"
    )


if __name__ == "__main__":
    main()
