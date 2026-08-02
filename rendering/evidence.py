from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics.regime_engine import AEI_VERSION, PRESSURE_VERSION
from analytics.valuation import SECTOR_VALUATION_VERSION
from config.metric_definitions import METRIC_DEFINITIONS
from rendering.adaptation import _adaptation_source_rows
from rendering.charts_common import COLORS
from rendering.charts_finance import component_bars
from rendering.common import _coverage_text, _display_text
from rendering.components import fmt_number, render_definition, render_line_break, render_section, render_static_table, render_tab_header
from rendering.energy import _energy_source_rows
from rendering.evidence_tables import _component_table, render_edgar_data, render_macro_data
from rendering.finance import _debt_market_source_rows
from rendering.infrastructure_common import _infrastructure_source_rows
from rendering.water import _water_utilization_payload

def _status_rows(regime_metrics):
    mappings = [
        ("AI Equity Index", "AI Equity Index", "AEI Version", "YFinance + SEC EDGAR"),
        ("AI Development Intensity", "AI Development Intensity", "ADI Version", "YFinance + SEC EDGAR + U.S. Census Bureau + FRED"),
        ("Economic Validation Gap", "Economic Validation Gap", "EVG Version", "YFinance + SEC EDGAR + FRED"),
        ("Power Stress Index", "Power Stress Index", "Power Stress Version", "FRED + EIA"),
        ("Power Capacity Gap", "Power Capacity Gap", "Power Capacity Gap Version", "FRED + EIA + U.S. Census Bureau"),
        ("Borrower Strain", "Borrower Strain", "Borrower Strain Version", "YFinance + SEC EDGAR"),
        ("Lender Strain", "Lender Strain", "Lender Strain Version", "FRED + SEC"),
        ("Speculation Gap", "Speculation Gap", None, "YFinance + SEC EDGAR"),
        ("Average Sector Pressure", "Avg Sector Pressure", "Pressure Version", "YFinance + SEC EDGAR"),
    ]
    signed_products = {
        "Economic Validation Gap",
        "Power Stress Index",
        "Power Capacity Gap",
        "Borrower Strain",
        "Lender Strain",
        "Speculation Gap",
    }
    rows = []
    for product, value_key, version_key, source in mappings:
        rows.append(
            {
                "Product": product,
                "Reading": fmt_number(
                    (regime_metrics or {}).get(value_key),
                    2,
                    signed=product in signed_products,
                ),
                "Source": source,
                "Version": str((regime_metrics or {}).get(version_key, "") if version_key else ""),
            }
        )
    return pd.DataFrame(rows)

def _coverage_rows(regime_metrics):
    groups = [
        ("AI Development Intensity", (regime_metrics or {}).get("ADI Components", {}), 4),
        ("Economic Validation Gap", (regime_metrics or {}).get("Economic Validation Gap Components", {}), 3),
        ("Power Stress Index", (regime_metrics or {}).get("Power Stress Components", {}), 3),
        ("Power Capacity Gap", (regime_metrics or {}).get("Power Capacity Gap Components", {}), 4),
        ("Borrower Strain", (regime_metrics or {}).get("Borrower Strain Components", {}), 4),
        ("Lender Strain", (regime_metrics or {}).get("Lender Strain Components", {}), 4),
    ]
    rows = []
    for product, result, total in groups:
        result = result or {}
        rows.append(
            {
                "Product": product,
                "Valid Components": _display_text(result.get("valid_components", "")),
                "Required Universe": f"{total} components",
                "Coverage": _coverage_text(result, total),
            }
        )
    funding = (regime_metrics or {}).get("Deployment Funding Mix", {}) or {}
    current = funding.get("current", {}) or {}
    rows.extend(
        [
            {"Product": "Internal Funding Coverage", "Valid Components": _display_text(current.get("internal_funding_companies", "")), "Required Universe": "company cohort", "Coverage": "cohort coverage"},
            {"Product": "Cash Reserve Runway", "Valid Components": _display_text(current.get("cash_reserve_companies", "")), "Required Universe": "company cohort", "Coverage": "cohort coverage"},
            {"Product": "Forward Commitment Load", "Valid Components": _display_text(current.get("commitment_companies", "")), "Required Universe": "commitment ledger", "Coverage": "ledger coverage"},
        ]
    )
    return pd.DataFrame(rows)

def _sector_methodology_rows():
    return pd.DataFrame(
        [
            {
                "Product": "Profitable-Cohort FWD EV/EBIT",
                "Version": SECTOR_VALUATION_VERSION,
                "Construction": "Σ Enterprise Value₊ ÷ Σ Forward EBIT₊",
                "Treatment": "Ratio of sums across companies with positive forward EBIT; minimum 3 profitable companies",
                "Interpretation": "Multiple paid for the sector's profitable operating base",
            },
            {
                "Product": "Loss-Making EV Share",
                "Version": SECTOR_VALUATION_VERSION,
                "Construction": "Σ Enterprise Value₍EBIT≤0₎ ÷ Σ Enterprise Value₍valid EBIT₎",
                "Treatment": "Loss-making companies remain visible as a separate enterprise-value share",
                "Interpretation": "Share of sector enterprise value unsupported by positive forward operating earnings",
            },
            {
                "Product": "Full-Sector Forward EBIT Yield",
                "Version": f"AEI {AEI_VERSION}",
                "Construction": "Σ Forward EBIT ÷ Σ Enterprise Value",
                "Treatment": "Positive and negative forward EBIT are both retained",
                "Interpretation": "AEI valuation input for the entire sector, including losses",
            },
            {
                "Product": "1Y Relative Return",
                "Version": f"AEI {AEI_VERSION}",
                "Construction": "Basket-weighted sector 1Y return − benchmark 1Y return",
                "Treatment": "Negative values indicate sector underperformance",
                "Interpretation": "Relative realized equity performance",
            },
            {
                "Product": "Sector AEI",
                "Version": AEI_VERSION,
                "Construction": "0.40 Valuation + 0.35 1Y Relative Return + 0.25 Market Breadth",
                "Treatment": "Normalized factor scores; all three factors required",
                "Interpretation": "Earnings-supported, broad-based sector equity strength",
            },
            {
                "Product": "Sector Basket Concentration",
                "Version": "1.0",
                "Construction": "100 × (Raw HHI − 1/N) ÷ (1 − 1/N)",
                "Treatment": "Valid positive-market-cap constituents only; rankings require at least 3 firms and 60% coverage",
                "Interpretation": "Concentration relative to an equal-weight basket with the same constituent count",
            },
            {
                "Product": "Trading Pressure",
                "Version": PRESSURE_VERSION,
                "Construction": "0.25 Valuation Stretch + 0.25 Price Extension + 0.20 Momentum Acceleration + 0.15 Volatility Expansion + 0.15 Volume Activity",
                "Treatment": "Valid components are normalized to 0–100 and available weights are renormalized",
                "Interpretation": "Abnormal valuation and trading intensity",
            },
            {
                "Product": "Earnings Support",
                "Version": SECTOR_VALUATION_VERSION,
                "Construction": "1Y Return ÷ profitable-cohort FWD EV/EBIT",
                "Treatment": "FWD EBIT is calculated as forward revenue times current operating margin",
                "Interpretation": "Trailing repricing relative to the profitable operating-earnings base; descriptive, not causal",
            },
            {
                "Product": "Speculative Load",
                "Version": SECTOR_VALUATION_VERSION,
                "Construction": "Trading Pressure ÷ Sector AI Equity Index",
                "Treatment": "Ratio of two bounded 0–100 composite scores; undefined when AEI is zero and sensitive when AEI is low",
                "Interpretation": "Relative trading pressure versus the sector's current equity foundation; compare with both source indexes",
            },
        ]
    )

def _water_evidence_summary_rows(water_data):
    water = _water_utilization_payload(water_data or {})
    summary = water.get("summary", {}) or {}
    usgs = summary.get("usgs_2015", {}) or {}
    eia = summary.get("eia_2024_thermoelectric", {}) or {}
    reconciliation = summary.get("reconciliation", {}) or {}
    rows = [
        {
            "Evidence layer": "USGS county water-use account",
            "Coverage": f"{int(usgs.get('county_records', 0) or 0):,} county records · {int(usgs.get('jurisdictions', 0) or 0)} jurisdictions",
            "Observation period": str(usgs.get("year") or ""),
            "Boundary": "County withdrawal account by use, source, and fresh or saline quality.",
        },
        {
            "Evidence layer": "EIA thermoelectric cooling-water survey",
            "Coverage": (
                f"{int(eia.get('records', 0) or 0):,} records · {int(eia.get('plants', 0) or 0):,} plants · "
                f"{int(eia.get('plants_with_withdrawal', 0) or 0):,} with withdrawal"
            ),
            "Observation period": str(eia.get("year") or ""),
            "Boundary": "Plant-level withdrawal and consumption from the 2024 thermoelectric survey.",
        },
        {
            "Evidence layer": "Water source register",
            "Coverage": f"{int(water.get('active_source_count', summary.get('active_sources', 0)) or 0)} active retained sources",
            "Observation period": "Retained local",
            "Boundary": f"Source health: {str(water.get('source_health') or 'unknown').replace('_', ' ')}.",
        },
        {
            "Evidence layer": "USGS reconciliation",
            "Coverage": (
                f"{int(reconciliation.get('usgs_county_records_reconciled', 0) or 0):,}/"
                f"{int(reconciliation.get('usgs_county_records', 0) or 0):,} county records reconciled"
            ),
            "Observation period": str(usgs.get("year") or ""),
            "Boundary": f"Maximum absolute residual: {float(reconciliation.get('usgs_max_absolute_residual_mgd', 0) or 0):.3g} Mgal/day.",
        },
    ]
    return pd.DataFrame(rows)


def _facility_coverage_tables(infrastructure_data):
    coverage = (infrastructure_data or {}).get("facility_coverage", {}) or {}
    grades = pd.DataFrame(
        [
            {"Evidence grade": grade, "Records": int(count or 0)}
            for grade, count in (coverage.get("evidence_grades", {}) or {}).items()
        ]
    )
    fields = pd.DataFrame(
        [
            {
                "Field": field,
                "Records": int((payload or {}).get("records", 0) or 0),
                "Coverage": fmt_number(float((payload or {}).get("share", 0) or 0) * 100.0, 1, suffix="%"),
            }
            for field, payload in (coverage.get("fields", {}) or {}).items()
        ]
    )
    return grades, fields


def _facility_registry_summary(infrastructure_data):
    registry = (infrastructure_data or {}).get("facility_registry")
    if not isinstance(registry, pd.DataFrame) or registry.empty:
        return pd.DataFrame(
            [
                {"Measure": "Mapped records", "Value": "0"},
                {"Measure": "States", "Value": "0"},
                {"Measure": "Capacity coverage", "Value": "0.0%"},
                {"Measure": "Higher-grade evidence", "Value": "0"},
            ]
        )

    capacity = pd.Series(False, index=registry.index)
    for field in [
        "Published Capacity Estimate MW",
        "Planned Data Center Capacity MW",
        "Contracted Utility Capacity MW",
        "Energized Capacity MW",
    ]:
        if field in registry.columns:
            capacity |= pd.to_numeric(registry[field], errors="coerce").gt(0)

    grades = registry.get("Evidence Grade", pd.Series("", index=registry.index)).fillna("").astype(str).str.upper()
    states = registry.get("State", pd.Series("", index=registry.index)).fillna("").astype(str).str.strip()
    state_count = states.mask(states.eq("")).nunique()

    return pd.DataFrame(
        [
            {"Measure": "Mapped records", "Value": f"{len(registry):,}"},
            {"Measure": "States", "Value": f"{state_count:,}"},
            {"Measure": "Capacity coverage", "Value": fmt_number(float(capacity.mean()) * 100.0, 1, suffix="%")},
            {"Measure": "Higher-grade evidence", "Value": f"{int(grades.isin({'A', 'B'}).sum()):,}"},
        ]
    )


def _direct_project_evidence_rows(infrastructure_data):
    registry = (infrastructure_data or {}).get("facility_registry")
    compute = ((infrastructure_data or {}).get("compute_manufacturing", {}) or {}).get("projects")
    rows = []
    if isinstance(registry, pd.DataFrame) and not registry.empty:
        record_type = registry.get("Record Type", pd.Series("", index=registry.index)).fillna("").astype(str).str.casefold()
        projects = registry.loc[record_type.eq("project")].copy()
        rows.append({"Project class": "Data-center projects", "Records": len(projects), "Evidence basis": "Canonical facility registry"})
        power = pd.Series(False, index=projects.index)
        for field in ["Contracted Utility Capacity MW", "Energized Capacity MW", "Planned Onsite Generation MW"]:
            if field in projects.columns:
                power |= pd.to_numeric(projects[field], errors="coerce").gt(0)
        rows.append({"Project class": "Data-center projects with structured power evidence", "Records": int(power.sum()), "Evidence basis": "Canonical facility registry"})
    if isinstance(compute, pd.DataFrame):
        rows.append({"Project class": "Compute-manufacturing projects", "Records": len(compute), "Evidence basis": "CHIPS project ledger"})
    return pd.DataFrame(rows)


def _active_facility_power_rows(infrastructure_data):
    registry = (infrastructure_data or {}).get("facility_registry")
    if not isinstance(registry, pd.DataFrame) or registry.empty:
        return pd.DataFrame()
    record_type = registry.get("Record Type", pd.Series("", index=registry.index)).fillna("").astype(str).str.casefold()
    projects = registry.loc[record_type.eq("project")].copy()
    if projects.empty:
        return pd.DataFrame()
    status = projects.get("Status", pd.Series("", index=projects.index)).fillna("").astype(str).str.casefold()
    active_statuses = {
        "approved / permitted / under construction", "under construction", "construction",
        "announced", "planned", "proposed", "expanding",
    }
    table = projects.loc[status.isin(active_statuses)].copy()
    columns = [
        "Facility", "Operator", "State", "Status", "Expected Service Date", "Utility",
        "Published Capacity Estimate MW", "Planned Data Center Capacity MW",
        "Contracted Utility Capacity MW", "Energized Capacity MW",
        "Planned Onsite Generation MW", "Evidence Grade", "Source URL",
    ]
    columns = [column for column in columns if column in table.columns]
    table = table[columns]
    if "Published Capacity Estimate MW" in table.columns:
        table = table.sort_values("Published Capacity Estimate MW", ascending=False, na_position="last", kind="stable")
    return table


def _facility_water_rows(water_data, infrastructure_data):
    context = (water_data or {}).get("facility_context")
    if not isinstance(context, pd.DataFrame):
        context = (infrastructure_data or {}).get("facility_registry")
    if not isinstance(context, pd.DataFrame) or context.empty:
        return pd.DataFrame()
    columns = [
        "Facility", "Operator", "State", "County", "Status",
        "Total Withdrawal Mgal/d", "Freshwater Withdrawal Mgal/d", "Groundwater Withdrawal Mgal/d",
        "Water Withdrawal Gallons/Year", "Water Consumption Gallons/Year", "Site WUE L/kWh",
        "Cooling System", "Water Source", "Water Permit or Utility Record",
        "Direct Water Evidence", "Evidence Grade", "Source URL",
    ]
    columns = [column for column in columns if column in context.columns]
    table = context[columns].copy()
    if "Total Withdrawal Mgal/d" in table.columns:
        table = table.sort_values("Total Withdrawal Mgal/d", ascending=False, na_position="last", kind="stable")
    return table


def _render_component_evidence(regime_metrics):
    adi_result = (regime_metrics or {}).get("ADI Components", {}) or {}
    validation_result = (regime_metrics or {}).get("Economic Validation Gap Components", {}) or {}
    power_result = (regime_metrics or {}).get("Power Stress Components", {}) or {}

    groups = [
        ("evidence-adi-components", "ADI pillars", adi_result.get("components", {}), False, COLORS["violet"]),
        ("evidence-validation-components", "Economic validation legs", validation_result.get("components", {}), False, COLORS["blue"]),
        ("evidence-power-stress-components", "Power-stress components", power_result.get("components", {}), True, COLORS["violet"]),
    ]
    for col, (chart_key, title, components, signed, color) in zip(st.columns(3), groups):
        chart_components = components
        if chart_key == "evidence-power-stress-components":
            chart_components = {
                ("Output Pressure" if name == "Commercial-vs-Residential Output Pressure" else name): payload
                for name, payload in (components or {}).items()
            }
        with col:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.plotly_chart(
                    component_bars(
                        chart_components,
                        signed=signed,
                        height=285,
                        color=color,
                    ),
                    width="stretch",
                    config={"displayModeBar": False, "responsive": True},
                    key=chart_key,
                )

    with st.expander("Component observations and normalization", expanded=False):
        st.markdown("**AI Development Intensity**")
        render_static_table(_component_table(adi_result.get("components", {})))

        validation_rows = []
        for name, payload in (validation_result.get("components", {}) or {}).items():
            payload = payload or {}
            validation_rows.append(
                {
                    "Component": name,
                    "Score": fmt_number(payload.get("score"), 1),
                    "Raw": fmt_number(payload.get("raw"), 3),
                    "Observations": payload.get("observations", ""),
                    "Normalization": payload.get("normalization", ""),
                    "History Observations": payload.get("history_observations", ""),
                }
            )
        st.markdown("**Economic Validation Gap**")
        render_static_table(pd.DataFrame(validation_rows))

        st.markdown("**Power Stress Index**")
        render_static_table(_component_table(power_result.get("components", {})))

        power_capacity_result = (regime_metrics or {}).get("Power Capacity Gap Components", {}) or {}
        st.markdown("**Power Capacity Gap**")
        render_static_table(_component_table(power_capacity_result.get("components", {})))

def render_evidence_tab(fred_data, sector_data, regime_metrics, energy_data, debt_markets_data, infrastructure_data=None, water_data=None, adaptation_data=None):
    render_tab_header(
        "Evidence",
        "Metric definitions, source records, coverage, retained evidence, and calculation methods.",
        "Methods and provenance",
    )
    render_line_break()
    render_section("Purpose Statement", first=True)
    render_definition(METRIC_DEFINITIONS["Purpose Statement"])
    render_line_break()

    render_section("Product status", "Metric readings, institutional sources, and calculation versions.")
    render_static_table(_status_rows(regime_metrics))

    render_section("Coverage", "Minimum-data rules and component coverage for composite products.")
    render_static_table(_coverage_rows(regime_metrics))

    render_section("Component evidence")
    _render_component_evidence(regime_metrics)

    render_section("Source Data")
    st.caption("Source observations used by the platform.")
    render_macro_data(fred_data)
    render_edgar_data(sector_data)
    with st.expander("Energy observations", expanded=False):
        render_static_table(_energy_source_rows(energy_data))
    with st.expander("Debt-market observations", expanded=False):
        render_static_table(_debt_market_source_rows(debt_markets_data))
    with st.expander("Infrastructure observations", expanded=False):
        render_static_table(_infrastructure_source_rows(infrastructure_data or {}))
    with st.expander("Adaptation observations", expanded=False):
        render_static_table(_adaptation_source_rows(adaptation_data or {}))

    render_section(
        "Data-center evidence",
        "National counts, project-stage records, facility locations, capacity fields, and source coverage.",
    )
    inventory = (infrastructure_data or {}).get("data_center_inventory", {}) or {}
    national_database = inventory.get("database")
    grades, fields = _facility_coverage_tables(infrastructure_data or {})
    with st.expander("Facility registry summary", expanded=False):
        render_static_table(_facility_registry_summary(infrastructure_data or {}))
    with st.expander("Facility evidence grades", expanded=False):
        render_static_table(grades)
    with st.expander("Facility field coverage", expanded=False):
        render_static_table(fields)
    with st.expander("National data-center evidence database", expanded=False):
        render_static_table(national_database if isinstance(national_database, pd.DataFrame) else pd.DataFrame())
    with st.expander("Detailed data-center facilities", expanded=False):
        registry = (infrastructure_data or {}).get("facility_registry")
        if registry is None or not isinstance(registry, pd.DataFrame):
            registry = (infrastructure_data or {}).get("locations")
        render_static_table(registry if isinstance(registry, pd.DataFrame) else pd.DataFrame())
    with st.expander("Active facility power records", expanded=False):
        render_static_table(_active_facility_power_rows(infrastructure_data or {}))

    render_section(
        "Infrastructure evidence",
        "Named project records, source contracts, and field definitions supporting the physical-development sections.",
    )
    with st.expander("Direct project summary", expanded=False):
        render_static_table(_direct_project_evidence_rows(infrastructure_data or {}))
    with st.expander("Infrastructure source register", expanded=False):
        manifest = (infrastructure_data or {}).get("infrastructure_source_manifest")
        render_static_table(manifest if isinstance(manifest, pd.DataFrame) else pd.DataFrame())
    with st.expander("Infrastructure field dictionary", expanded=False):
        dictionary = (infrastructure_data or {}).get("infrastructure_field_dictionary")
        render_static_table(dictionary if isinstance(dictionary, pd.DataFrame) else pd.DataFrame())

    render_section(
        "Compute-manufacturing evidence",
        "Federal Reserve series contracts and attributable project records used by the Compute tab.",
    )
    compute = ((infrastructure_data or {}).get("compute_manufacturing", {}) or {})
    with st.expander("G.17 series contract", expanded=False):
        contract = compute.get("series_contract")
        render_static_table(contract if isinstance(contract, pd.DataFrame) else pd.DataFrame())
    with st.expander("G.17 latest-release validation", expanded=False):
        validation = compute.get("series_validation")
        render_static_table(validation if isinstance(validation, pd.DataFrame) else pd.DataFrame())
    with st.expander("Compute-manufacturing project records", expanded=False):
        projects = compute.get("projects")
        render_static_table(projects if isinstance(projects, pd.DataFrame) else pd.DataFrame())

    render_section(
        "Water evidence",
        "National withdrawal accounts, thermoelectric cooling-water records, and facility-level water context.",
    )
    water = _water_utilization_payload(water_data or {})
    render_static_table(_water_evidence_summary_rows(water))
    with st.expander("AI facility water records", expanded=False):
        render_static_table(_facility_water_rows(water_data or {}, infrastructure_data or {}))
    with st.expander("Water source register", expanded=False):
        manifest = water.get("source_manifest")
        if isinstance(manifest, pd.DataFrame) and not manifest.empty:
            columns = [
                "source_name", "custodian", "canonical_url", "persistent_identifier",
                "coverage_period", "data_role", "evidence_grade", "resilience_grade",
                "ingestion_status", "source_health", "retrieval_date", "parser_version",
            ]
            render_static_table(manifest[[column for column in columns if column in manifest.columns]])
        else:
            st.caption("No retained water-source register is available.")
    with st.expander("Water field dictionary", expanded=False):
        field_dictionary = water.get("field_dictionary")
        render_static_table(field_dictionary if isinstance(field_dictionary, pd.DataFrame) else pd.DataFrame())
    with st.expander("USGS county reconciliation", expanded=False):
        reconciliation = water.get("usgs_reconciliation")
        if isinstance(reconciliation, pd.DataFrame) and not reconciliation.empty:
            render_static_table(reconciliation.head(250))
        else:
            st.caption("No reconciliation evidence is available.")
    with st.expander("Thermoelectric plant evidence", expanded=False):
        plants = water.get("eia_plants")
        if isinstance(plants, pd.DataFrame) and not plants.empty:
            columns = [
                "Plant Code", "Plant Name", "State", "Withdrawal Bgal/day",
                "Consumption Bgal/day", "Water Type", "Water Source",
                "Cooling System", "Quality Flags",
            ]
            render_static_table(plants[[column for column in columns if column in plants.columns]])
        else:
            st.caption("No retained thermoelectric plant records are available.")

    render_section("Sector construction", "Equations and aggregation rules for the sector analytical products.")
    render_static_table(_sector_methodology_rows())
