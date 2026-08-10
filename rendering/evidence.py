from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics.hhi_engine import sector_hhi_component_breakdown
from analytics.private_capital import build_private_capital_realization
from config.benchmark_config import QQQ_WEIGHTS_EFFECTIVE_DATE
from config.factor_config import FACTOR_DISPLAY_NAMES
from rendering.visual_system import render_plotly_chart
from rendering.adaptation import _adaptation_source_rows
from rendering.charts_common import COLORS
from rendering.charts_finance import component_bars
from rendering.common import _coverage_text, _display_text
from rendering.components import fmt_number, render_line_break, render_section, render_static_table, render_tab_header
from rendering.dataframe import arrow_safe_dataframe
from rendering.power import _power_source_rows
from rendering.evidence_tables import _component_table, render_edgar_data, render_macro_data, render_sector_scoreboard
from rendering.finance import _debt_market_source_rows, _private_capital_detail_table


def _water_evidence_payload(water_data) -> dict:
    """Normalize Water evidence input without importing private renderer helpers."""
    return water_data if isinstance(water_data, dict) else {}
from rendering.infrastructure_common import _infrastructure_source_rows
from rendering.labels import sector_display_name


EVIDENCE_STANDARDS = """
**AI Macro is built around evidence, not allegiance.**

The platform uses public records, regulatory filings, official datasets, company disclosures, and selected business reporting to study the AI economy. Sources are evaluated for what they establish, not for their reputation, popularity, ideology, or institutional status.

Secondary aggregators and specialist publications may be used to discover relevant developments, but they do not establish facts merely by reporting them. Material claims are traced whenever practical to primary records or independently verified through approved reporting.

**Social media is excluded from the research pipeline.** Posts, threads, comments, and other user-generated social content are not used for discovery, corroboration, evidence, or citation. Popularity, repetition, and virality do not establish factual reliability.

For consequential claims, AI Macro seeks evidence that could qualify, contradict, or narrow the initial interpretation. A source that identifies useful evidence is not owed agreement with its conclusions.

Political and regulatory developments are included when they have a concrete economic or operational consequence. The platform preserves the identity of the acting institution or official, the nature of the action, and its legal or procedural status. Statements, requests, proposals, directives, orders, rules, and enacted law are not treated as interchangeable.

**Corroboration means independent evidence, not repeated publication.** Multiple stories derived from the same filing, wire report, press release, or other upstream source do not count as independent confirmation.

Data and news serve different roles. Retained datasets provide the analytical foundation. Recent developments provide limited current context and should influence interpretation only when they materially change, explain, reinforce, or complicate the evidence.

**No source is owed agreement.**
""".strip()

def _status_rows(regime_metrics):
    mappings = [
        ("AI Equity Index", "AI Equity Index", "YFinance"),
        ("AI Development Intensity", "AI Development Intensity", "YFinance + SEC EDGAR + U.S. Census Bureau + FRED"),
        ("Economic Validation Gap", "Economic Validation Gap", "ADI + SEC EDGAR + YFinance"),
        ("Power Stress Index", "Power Stress Index", "FRED + EIA"),
        ("Power Capacity Gap", "Power Capacity Gap", "FRED + EIA + U.S. Census Bureau"),
        ("Borrower Strain", "Borrower Strain", "YFinance + SEC EDGAR"),
        ("Lender Strain", "Lender Strain", "FRED + SEC"),
        ("Speculation Gap", "Speculation Gap", "YFinance + SEC EDGAR"),
        ("Average Sector Pressure", "Avg Sector Pressure", "YFinance + SEC EDGAR"),
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
    for product, value_key, source in mappings:
        rows.append(
            {
                "Product": product,
                "Reading": fmt_number(
                    (regime_metrics or {}).get(value_key),
                    2,
                    signed=product in signed_products,
                ),
                "Source": source,
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
            {"Product": "Debt change / CapEx", "Valid Components": _display_text(current.get("debt_financing_companies", "")), "Required Universe": "matched SEC company periods", "Coverage": "matched-period coverage"},
            {"Product": "Forward Commitment Load", "Valid Components": _display_text(current.get("commitment_companies", "")), "Required Universe": "commitment ledger", "Coverage": "ledger coverage"},
        ]
    )
    return pd.DataFrame(rows)

def _sector_methodology_rows():
    return pd.DataFrame(
        [
            {
                "Product": "Profitable-Cohort FWD EV/EBIT",
                "Construction": "Σ Enterprise Value₊ ÷ Σ Forward EBIT₊",
                "Treatment": "Ratio of sums across companies with positive forward EBIT; minimum 3 profitable companies",
                "Interpretation": "Multiple paid for the sector's profitable operating base",
            },
            {
                "Product": "Loss-Making EV Share",
                "Construction": "Σ Enterprise Value₍EBIT≤0₎ ÷ Σ Enterprise Value₍valid EBIT₎",
                "Treatment": "Loss-making companies remain visible as a separate enterprise-value share",
                "Interpretation": "Share of sector enterprise value unsupported by positive forward operating earnings",
            },
            {
                "Product": "1Y Relative Return",
                "Construction": "Equal-weight sector 1Y return − weighted benchmark 1Y return",
                "Treatment": f"Sector constituents are equal-weighted; benchmark uses static, renormalized top-ten QQQ proxy weights effective {QQQ_WEIGHTS_EFFECTIVE_DATE}; negative values indicate sector underperformance",
                "Interpretation": "Relative realized equity performance",
            },
            {
                "Product": "Sector AEI",
                "Construction": "0.60 1Y Relative Return + 0.40 Market Breadth",
                "Treatment": "Both normalized factors required; identical construction for all sectors",
                "Interpretation": "Sustained relative strength and participation; valuation shown separately",
            },
            {
                "Product": "Sector Basket Concentration",
                "Construction": "100 × (Raw HHI − 1/N) ÷ (1 − 1/N)",
                "Treatment": "Valid positive-market-cap constituents only; rankings require at least 3 firms and 60% coverage",
                "Interpretation": "Concentration relative to an equal-weight basket with the same constituent count",
            },
            {
                "Product": "Trading Pressure",
                "Construction": "0.30 Price Extension + 0.25 Momentum Acceleration + 0.25 Volatility Expansion + 0.20 Volume Activity",
                "Treatment": "All four normalized components required; no valuation input",
                "Interpretation": "Abnormal price and trading intensity",
            },
            {
                "Product": "Returns versus profitable-company earnings",
                "Construction": "1Y Return ÷ profitable-cohort FWD EV/EBIT",
                "Treatment": "FWD EBIT is calculated as forward revenue times current operating margin",
                "Interpretation": "Trailing repricing relative to the profitable operating-earnings base; descriptive, not causal",
            },
            {
                "Product": "Trading pressure relative to sector strength",
                "Construction": "Trading Pressure ÷ Sector AI Equity Index",
                "Treatment": "Ratio of two bounded 0–100 composite scores; undefined when AEI is zero and sensitive when AEI is low",
                "Interpretation": "Relative trading pressure versus the sector's current equity foundation; compare with both source indexes",
            },
        ]
    )

def _water_evidence_summary_rows(water_data):
    water = _water_evidence_payload(water_data or {})
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
        rows.append({"Project class": "Data-center projects", "Records": len(projects), "Evidence basis": "Deduplicated campus records"})
        power = pd.Series(False, index=projects.index)
        for field in ["Contracted Utility Capacity MW", "Energized Capacity MW", "Planned Onsite Generation MW"]:
            if field in projects.columns:
                power |= pd.to_numeric(projects[field], errors="coerce").gt(0)
        rows.append({"Project class": "Data-center projects with structured power evidence", "Records": int(power.sum()), "Evidence basis": "Deduplicated campus records"})
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
        ("evidence-validation-components", "Economic Validation Gap components", validation_result.get("components", {}), False, COLORS["blue"]),
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
                render_plotly_chart(
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


def _render_sector_factor_pressure_data(sector_data, sector_metrics):
    sectors = [
        sector
        for sector in (sector_metrics or {})
        if sector in (sector_data or {})
        and isinstance((sector_data or {}).get(sector), pd.DataFrame)
        and not (sector_data or {}).get(sector).empty
    ]
    if not sectors:
        st.caption("No sector factor or pressure data is available.")
        return

    selected = st.selectbox(
        "Sector",
        sectors,
        format_func=sector_display_name,
        key="evidence-factor-pressure-sector",
    )
    metrics = (sector_metrics or {}).get(selected, {}) or {}
    frame = (sector_data or {}).get(selected, pd.DataFrame())

    with st.expander("Selected-sector factor and pressure tables", expanded=False):
        st.markdown("**AEI factors**")
        factor_frame = metrics.get("Scored Factors", pd.DataFrame()).copy()
        if not factor_frame.empty and "Factor" in factor_frame.columns:
            factor_frame["Factor"] = factor_frame["Factor"].map(
                lambda name: FACTOR_DISPLAY_NAMES.get(name, str(name).replace("_", " ").title())
            )
        st.dataframe(
            arrow_safe_dataframe(factor_frame),
            width="stretch",
            hide_index=True,
        )

        st.markdown("**Trading-pressure components**")
        st.dataframe(
            arrow_safe_dataframe(metrics.get("Pressure Components", pd.DataFrame())),
            width="stretch",
            hide_index=True,
        )

        st.markdown("**Basket-concentration contributors**")
        concentration_table = sector_hhi_component_breakdown(frame, top_n=8)
        if not concentration_table.empty:
            concentration_table["Market Cap Share"] = (
                pd.to_numeric(concentration_table["Market Cap Share"], errors="coerce") * 100.0
            ).round(2)
            concentration_table["HHI Contribution Share"] = pd.to_numeric(
                concentration_table["HHI Contribution Share"], errors="coerce"
            ).round(2)
            concentration_table = concentration_table.rename(
                columns={
                    "Market Cap Share": "Market Cap Share (%)",
                    "HHI Contribution Share": "Share of HHI (%)",
                }
            )
        st.dataframe(
            arrow_safe_dataframe(concentration_table),
            width="stretch",
            hide_index=True,
        )


def _render_metric_evidence(regime_metrics):
    render_section("Current readings", "Metric values and primary sources.", first=True)
    render_static_table(_status_rows(regime_metrics))
    render_section("Coverage", "Minimum-data rules and component coverage for composite products.")
    render_static_table(_coverage_rows(regime_metrics))
    render_section("Component evidence")
    _render_component_evidence(regime_metrics)
    render_section("Sector construction", "Equations and aggregation rules for the sector analytical products.")
    render_static_table(_sector_methodology_rows())


def _render_market_finance_evidence(fred_data, sector_data, sector_metrics, debt_markets_data, dashboard_data):
    render_section("Sector scoreboard", "Comparable conditions across all AI-equity sector baskets.", first=True, compact=True)
    render_sector_scoreboard((dashboard_data or {}).get("macro_df", pd.DataFrame()))
    render_section(
        "Factor and pressure data",
        "Underlying sector factor scores, trading-pressure components, and concentration contributors.",
        compact=True,
    )
    _render_sector_factor_pressure_data(sector_data, sector_metrics)
    render_section("Market and financial observations", "Retained market, filing, credit, and private-capital records.")
    render_macro_data(fred_data)
    render_edgar_data(sector_data)
    with st.expander("Debt-market observations", expanded=False):
        render_static_table(_debt_market_source_rows(debt_markets_data))
    with st.expander("Private-capital fund observations", expanded=False):
        private_capital = build_private_capital_realization()
        private_funds = private_capital.get("funds", pd.DataFrame())
        private_metadata = private_capital.get("metadata", {}) or {}
        render_static_table(
            _private_capital_detail_table(private_funds)
            if isinstance(private_funds, pd.DataFrame) and not private_funds.empty
            else pd.DataFrame()
        )
        selection_method = str(private_metadata.get("selection_method") or "").strip()
        if selection_method:
            st.markdown(f"**Selection method.** {selection_method}")
        limitations = [
            str(item).strip()
            for item in private_metadata.get("important_limitations", []) or []
            if str(item).strip()
        ]
        if limitations:
            st.markdown("**Limitations.**\n\n" + "\n".join(f"- {item}" for item in limitations))


def _render_compute_data_center_evidence(infrastructure_data):
    infrastructure = infrastructure_data or {}
    render_section(
        "Data-center evidence",
        "National counts, project stages, facility locations, capacity fields, and source coverage.",
        first=True,
    )
    inventory = infrastructure.get("data_center_inventory", {}) or {}
    national_database = inventory.get("database")
    grades, fields = _facility_coverage_tables(infrastructure)
    with st.expander("Facility registry summary", expanded=False):
        render_static_table(_facility_registry_summary(infrastructure))
    with st.expander("Facility evidence grades", expanded=False):
        render_static_table(grades)
    with st.expander("Facility field coverage", expanded=False):
        render_static_table(fields)
    with st.expander("Reviewed identity decisions", expanded=False):
        decisions = infrastructure.get("facility_identity_decisions")
        render_static_table(decisions if isinstance(decisions, pd.DataFrame) else pd.DataFrame())
    with st.expander("National data-center evidence database", expanded=False):
        render_static_table(national_database if isinstance(national_database, pd.DataFrame) else pd.DataFrame())
    with st.expander("Detailed data-center facilities", expanded=False):
        registry = infrastructure.get("facility_registry")
        if registry is None or not isinstance(registry, pd.DataFrame):
            registry = infrastructure.get("locations")
        render_static_table(registry if isinstance(registry, pd.DataFrame) else pd.DataFrame())
    with st.expander("Active facility power records", expanded=False):
        render_static_table(_active_facility_power_rows(infrastructure))

    render_section(
        "Construction and infrastructure evidence",
        "Named projects, source definitions, and field documentation for compute, data centers, water, and construction.",
    )
    with st.expander("Construction and infrastructure observations", expanded=False):
        render_static_table(_infrastructure_source_rows(infrastructure))
    with st.expander("Direct project summary", expanded=False):
        render_static_table(_direct_project_evidence_rows(infrastructure))
    with st.expander("Construction and infrastructure source register", expanded=False):
        manifest = infrastructure.get("infrastructure_source_manifest")
        if isinstance(manifest, pd.DataFrame):
            public_columns = [
                "source_name", "custodian", "canonical_url", "publication_date",
                "coverage_period", "geographic_coverage", "data_role", "evidence_grade",
            ]
            manifest = manifest[[column for column in public_columns if column in manifest.columns]].copy()
        render_static_table(manifest if isinstance(manifest, pd.DataFrame) else pd.DataFrame())
    with st.expander("Construction and infrastructure field dictionary", expanded=False):
        dictionary = infrastructure.get("infrastructure_field_dictionary")
        render_static_table(dictionary if isinstance(dictionary, pd.DataFrame) else pd.DataFrame())

    render_section("Compute-manufacturing evidence", "Federal Reserve series definitions and announced manufacturing projects.")
    compute = (infrastructure.get("compute_manufacturing", {}) or {})
    with st.expander("G.17 series definitions", expanded=False):
        contract = compute.get("series_contract")
        render_static_table(contract if isinstance(contract, pd.DataFrame) else pd.DataFrame())
    with st.expander("Compute-manufacturing project records", expanded=False):
        projects = compute.get("projects")
        render_static_table(projects if isinstance(projects, pd.DataFrame) else pd.DataFrame())


def _render_connectivity_evidence(connectivity_data):
    connectivity = connectivity_data or {}
    render_section(
        "Connectivity evidence",
        "Submarine systems, landing markets, internet exchanges, public interconnection facilities, middle-mile awards, and campus proximity screens.",
        first=True,
    )
    with st.expander("Connectivity source register", expanded=False):
        render_static_table(connectivity.get("source_manifest", pd.DataFrame()))
    with st.expander("Submarine cable-system register", expanded=False):
        render_static_table(connectivity.get("submarine_cable_systems", pd.DataFrame()))
    with st.expander("Selected cable-landing markets", expanded=False):
        render_static_table(connectivity.get("cable_landing_markets", pd.DataFrame()))
    with st.expander("Internet exchange registry", expanded=False):
        render_static_table(connectivity.get("ixp_snapshot", pd.DataFrame()))
    with st.expander("Interconnection-market summary", expanded=False):
        render_static_table(connectivity.get("interconnection_market_summary", pd.DataFrame()))
    with st.expander("Interconnection facility evidence", expanded=False):
        facilities = connectivity.get("interconnection_facilities", pd.DataFrame())
        if isinstance(facilities, pd.DataFrame) and not facilities.empty:
            render_static_table(facilities)
        else:
            render_static_table(connectivity.get("interconnection_facility_summary", pd.DataFrame()))
    with st.expander("Middle-mile awards", expanded=False):
        render_static_table(connectivity.get("middle_mile_awards", pd.DataFrame()))
    with st.expander("Campus proximity to network infrastructure", expanded=False):
        render_static_table(connectivity.get("campus_connectivity_snapshot", pd.DataFrame()))


def _render_power_grid_evidence(energy_data, infrastructure_data):
    energy = energy_data or {}
    render_section(
        "Power evidence",
        "Retail markets, generation, capacity development, wholesale prices, and fuel infrastructure.",
        first=True,
    )
    with st.expander("Power and grid observations", expanded=False):
        render_static_table(_power_source_rows(energy))
    with st.expander("Operating capacity", expanded=False):
        frame = energy.get("capacity_snapshot")
        render_static_table(frame if isinstance(frame, pd.DataFrame) else pd.DataFrame())
    with st.expander("Current-year capacity changes", expanded=False):
        frame = energy.get("capacity_changes")
        render_static_table(frame if isinstance(frame, pd.DataFrame) else pd.DataFrame())
    with st.expander("Generator development summary", expanded=False):
        frame = energy.get("generator_pipeline")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            summary = frame.copy()
            summary["Expected Year"] = pd.to_numeric(summary.get("Expected Year"), errors="coerce")
            summary["Nameplate Capacity (MW)"] = pd.to_numeric(summary.get("Nameplate Capacity (MW)"), errors="coerce")
            summary = summary.groupby(["Pipeline Type", "Expected Year", "Technology Group"], as_index=False)["Nameplate Capacity (MW)"].sum()
            render_static_table(summary)
        else:
            render_static_table(pd.DataFrame())
    with st.expander("Fuel infrastructure projects", expanded=False):
        gas = energy.get("gas_pipeline_canonical")
        lng = energy.get("lng_projects")
        storage = energy.get("gas_storage_projects")
        st.markdown("**Natural-gas pipelines**")
        render_static_table(gas if isinstance(gas, pd.DataFrame) else pd.DataFrame())
        st.markdown("**LNG liquefaction**")
        render_static_table(lng if isinstance(lng, pd.DataFrame) else pd.DataFrame())
        st.markdown("**Natural-gas storage**")
        render_static_table(storage if isinstance(storage, pd.DataFrame) else pd.DataFrame())

    render_section(
        "Grid & Storage evidence",
        "Interconnection requests, storage deployment, and electric-power construction.",
    )
    with st.expander("Interconnection queue summary", expanded=False):
        official = energy.get("interconnection_queue_summary")
        if isinstance(official, pd.DataFrame) and not official.empty:
            st.markdown("**National active-capacity reconciliation**")
            render_static_table(official)
        frame = energy.get("interconnection_queue")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            st.markdown("**Submitted component capacity by region and study phase**")
            summary = frame.copy()
            summary["Queue MW"] = pd.to_numeric(summary.get("Queue MW"), errors="coerce")
            summary = summary.groupby(["q_status", "region", "Technology Group", "IA_phase_clean"], dropna=False, as_index=False)["Queue MW"].sum()
            render_static_table(summary)
        else:
            render_static_table(pd.DataFrame())
    with st.expander("Storage fleet and queue records", expanded=False):
        capacity = energy.get("capacity_snapshot")
        render_static_table(capacity if isinstance(capacity, pd.DataFrame) else pd.DataFrame())
    with st.expander("Electric-power construction chronology", expanded=False):
        construction = (infrastructure_data or {}).get("construction_history")
        if isinstance(construction, pd.DataFrame) and not construction.empty:
            mask = construction.get("Series", pd.Series("", index=construction.index)).astype(str).eq("Electric Power Construction")
            render_static_table(construction.loc[mask].copy())
        else:
            render_static_table(pd.DataFrame())


def _render_water_evidence(water_data, infrastructure_data):
    render_section(
        "Water evidence",
        "National withdrawal accounts, thermoelectric cooling-water records, and facility-level water context.",
        first=True,
    )
    water = _water_evidence_payload(water_data or {})
    render_static_table(_water_evidence_summary_rows(water))
    with st.expander("AI facility water records", expanded=False):
        render_static_table(_facility_water_rows(water_data or {}, infrastructure_data or {}))
    with st.expander("Water source register", expanded=False):
        manifest = water.get("source_manifest")
        if isinstance(manifest, pd.DataFrame) and not manifest.empty:
            columns = [
                "source_name", "custodian", "canonical_url", "persistent_identifier",
                "publication_date", "coverage_period", "geographic_coverage",
                "data_role", "evidence_grade", "retrieval_date",
            ]
            render_static_table(manifest[[column for column in columns if column in manifest.columns]])
        else:
            st.caption("No water-source register is available.")
    with st.expander("Water field dictionary", expanded=False):
        field_dictionary = water.get("field_dictionary")
        render_static_table(field_dictionary if isinstance(field_dictionary, pd.DataFrame) else pd.DataFrame())
    with st.expander("USGS county reconciliation", expanded=False):
        reconciliation = water.get("usgs_reconciliation")
        if isinstance(reconciliation, pd.DataFrame) and not reconciliation.empty:
            render_static_table(reconciliation.head(250))
        else:
            st.caption("No reconciliation evidence is available.")
    with st.expander("Wastewater construction chronology", expanded=False):
        construction = (infrastructure_data or {}).get("construction_history")
        if isinstance(construction, pd.DataFrame) and not construction.empty:
            mask = construction.get("Series", pd.Series("", index=construction.index)).astype(str).eq("Public Sewage and Waste Disposal Construction")
            render_static_table(construction.loc[mask].copy())
        else:
            render_static_table(pd.DataFrame())
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
            st.caption("No thermoelectric plant records are available.")


def _render_adoption_outcomes_evidence(adaptation_data, workforce_data, economic_impact_data):
    render_section("Adoption evidence", "Consumer use, employer adoption, and commercialization source records.", first=True)
    with st.expander("Adaptation observations", expanded=False):
        render_static_table(_adaptation_source_rows(adaptation_data or {}))

    render_section(
        "Workforce evidence",
        "Occupation exposure and official employment, earnings, demand, mobility, and separation histories.",
    )
    with st.expander("Occupation-level LLM task-exposure benchmark", expanded=False):
        render_static_table((workforce_data or {}).get("occupation_exposure", pd.DataFrame()))
    with st.expander("Employment history", expanded=False):
        render_static_table((workforce_data or {}).get("employment_history", pd.DataFrame()))
    with st.expander("Nominal and real hourly earnings", expanded=False):
        view = st.radio(
            "Earnings evidence",
            ["Nominal", "CPI-adjusted"],
            horizontal=True,
            key="evidence-workforce-earnings-view",
        )
        frame = (workforce_data or {}).get("earnings_history" if view == "Nominal" else "real_earnings_history", pd.DataFrame())
        render_static_table(frame)
    with st.expander("Job openings history", expanded=False):
        render_static_table((workforce_data or {}).get("job_openings_history", pd.DataFrame()))
    with st.expander("JOLTS labor-flow history", expanded=False):
        render_static_table((workforce_data or {}).get("labor_flows_history", pd.DataFrame()))
    with st.expander("Observed workforce outcomes", expanded=False):
        render_static_table((workforce_data or {}).get("transmission_matrix", pd.DataFrame()))
    with st.expander("Workforce source register", expanded=False):
        render_static_table((workforce_data or {}).get("source_manifest", pd.DataFrame()))

    render_section(
        "Economic Outcomes evidence",
        "Productivity, output, real compensation, labor share, median earnings, labor costs, and information investment.",
    )
    with st.expander("Productivity and labor-cost history", expanded=False):
        render_static_table((economic_impact_data or {}).get("productivity_history", pd.DataFrame()))
    with st.expander("Productivity, real compensation, and labor share", expanded=False):
        render_static_table((economic_impact_data or {}).get("value_transmission_history", pd.DataFrame()))
    with st.expander("Real median weekly earnings distribution", expanded=False):
        render_static_table((economic_impact_data or {}).get("earnings_distribution_history", pd.DataFrame()))
    with st.expander("Information-processing investment history", expanded=False):
        render_static_table((economic_impact_data or {}).get("investment_history", pd.DataFrame()))
    with st.expander("Economic-outcomes source register", expanded=False):
        render_static_table((economic_impact_data or {}).get("source_manifest", pd.DataFrame()))




_EVIDENCE_LOOKUP = {
    "market": {
        "label": "Market",
        "definition": "Equity performance, participation, concentration, and trading pressure across the configured 204-company AI market universe; not the entire stock market.",
        "datasets": "archive/yf_history.csv · archive/sector_history.csv",
        "detail_view": "Market & finance",
    },
    "finance": {
        "label": "Finance",
        "definition": "Funding capacity, credit conditions, borrower and lender stress, and cash realization in the covered company and fund records.",
        "datasets": "archive/yf_history.csv · archive/edgar_history.csv · archive/fred_history.csv · NY Fed retained series · private-capital fund records",
        "detail_view": "Market & finance",
    },
    "compute": {
        "label": "Compute",
        "definition": "U.S. compute-manufacturing output, utilization, investment, and announced production projects; project announcements are not operating capacity.",
        "datasets": "compute manufacturing history · compute project ledger · construction history",
        "detail_view": "Compute & data centers",
    },
    "data_center": {
        "label": "Data Centers",
        "definition": "Project stages, campus locations, and published capacity from the project registry; the registry is evidence of development activity, not a census of the national fleet.",
        "datasets": "facility registry · campus registry · data-center project records · facility identity decisions",
        "detail_view": "Compute & data centers",
    },
    "connectivity": {
        "label": "Connectivity",
        "definition": "Public evidence of network reach and interconnection depth, including cables, IXPs, facilities, middle-mile awards, and campus proximity; private routes are not fully observed.",
        "datasets": "connectivity source register · cable systems · IXP registry · interconnection facilities · middle-mile awards",
        "detail_view": "Connectivity",
    },
    "power": {
        "label": "Power",
        "definition": "Electricity demand, operating and planned generation, prices, and large-load context; published data-center MW is not metered electricity demand.",
        "datasets": "EIA retained power records · FRED series · generator pipeline · data-center campus records",
        "detail_view": "Power & grid",
    },
    "grid_storage": {
        "label": "Grid & Storage",
        "definition": "Interconnection progress, historical queue outcomes, reserve margins, storage duration, and grid construction; queued capacity is not connected capacity.",
        "datasets": "Berkeley Lab queue records · NERC reserve margins · EIA storage records · electric-power construction history",
        "detail_view": "Power & grid",
    },
    "water": {
        "label": "Water",
        "definition": "Regional water exposure and facility-level disclosure. State and national water totals provide context but cannot establish supply at a specific campus.",
        "datasets": "USGS water-use records · drought snapshot · EIA thermoelectric records · facility water evidence",
        "detail_view": "Water",
    },
    "adaptation": {
        "label": "Adoption",
        "definition": "Reported consumer use and business adoption. Expected future use is intent, not completed deployment, and provider users are not a national adoption rate.",
        "datasets": "consumer-use history · Census BTOS business adoption · commercialization disclosures",
        "detail_view": "Adoption & outcomes",
    },
    "workforce": {
        "label": "Workforce",
        "definition": "Observed employment, real pay, openings, hires, quits, layoffs, and a separate task-exposure benchmark. Exposure is not observed displacement.",
        "datasets": "occupation exposure benchmark · BLS CES · BLS JOLTS · workforce outcomes matrix",
        "detail_view": "Adoption & outcomes",
    },
    "economic_impact": {
        "label": "Economic Outcomes",
        "definition": "Economy-wide productivity, output, compensation, labor share, earnings, and investment. These outcomes do not identify AI as the sole cause.",
        "datasets": "BLS productivity and compensation · CPS earnings · BEA investment · FRED · provider commercialization disclosures",
        "detail_view": "Adoption & outcomes",
    },
}


def _sync_evidence_detail_view() -> None:
    selected = st.session_state.get("evidence-lookup-domain")
    spec = _EVIDENCE_LOOKUP.get(selected)
    if spec:
        st.session_state["evidence-view"] = spec["detail_view"]


def _source_role_label(reference: dict, event: dict | None = None) -> str:
    role = str((event or {}).get("evidence_role") or reference.get("evidence_role") or "").strip().casefold()
    source_type = str((event or {}).get("source_type") or "").strip().casefold()
    if role == "official_statement" or source_type == "official_statement":
        return "Primary record"
    if role == "company_statement" or source_type == "company_statement":
        return "Company statement"
    if role in {"secondary", "journalism"}:
        return "Approved reporting"
    return "Analytical source"


def _evidence_lineage_rows(selected: str, read: dict, spec: dict) -> list[dict]:
    references = [
        dict(item)
        for item in read.get("references", []) or []
        if isinstance(item, dict) and str(item.get("source_label") or item.get("source_name") or "").strip()
    ]
    static_refs = [item for item in references if not str(item.get("event_id") or "").strip()]
    static_sources = " · ".join(
        str(item.get("source_label") or item.get("source_name") or "").strip()
        for item in static_refs[:6]
    )
    rows = [{
        "Claim / evidence": str(read.get("headline") or "Current domain claim is unavailable.").strip(),
        "Layer": "Retained analytical",
        "Source": static_sources or "Detailed retained source register",
        "Provenance": f"{spec['datasets']} · boundary: {spec['definition']}",
        "source_url": "",
    }]

    context_payload = read.get("current_context", {}) if isinstance(read.get("current_context"), dict) else {}
    event_by_id = {
        str(event.get("event_id") or ""): dict(event)
        for event in context_payload.get("events", []) or []
        if isinstance(event, dict) and str(event.get("event_id") or "").strip()
    }
    reference_by_number = {
        int(item.get("reference_number")): item
        for item in references
        if str(item.get("reference_number") or "").isdigit()
    }
    for item in read.get("current_context_items", []) or []:
        if not isinstance(item, dict):
            continue
        event = event_by_id.get(str(item.get("event_id") or ""), {})
        try:
            number = int(item.get("reference_number"))
        except (TypeError, ValueError):
            number = 0
        reference = reference_by_number.get(number, {})
        source = str(reference.get("source_label") or reference.get("source_name") or event.get("source_label") or event.get("source_name") or "Source").strip()
        provider = str(event.get("discovery_provider") or "").strip()
        discovered_via = str(event.get("discovered_via") or "").strip()
        verification = str(event.get("verification_status") or item.get("status") or "").replace("_", " ").strip()
        if discovered_via:
            provenance = f"Discovered via {discovered_via}; evidence established by {source}"
        elif provider == "primary_feed":
            provenance = f"Direct primary-source discovery; {verification or 'primary'}"
        elif provider:
            provenance = f"Independently retrieved via {provider.replace('_', ' ')}; {verification or 'qualified'}"
        else:
            provenance = verification or "Retained qualified Current Context record"
        rows.append({
            "Claim / evidence": str(item.get("text") or "").strip(),
            "Layer": _source_role_label(reference, event),
            "Source": source,
            "Provenance": provenance,
            "source_url": str(reference.get("source_url") or event.get("source_url") or "").strip(),
        })
    return rows


def _render_evidence_lookup(platform_reads: dict | None) -> None:
    reads = platform_reads or {}
    options = list(_EVIDENCE_LOOKUP)
    if "evidence-view" not in st.session_state:
        st.session_state["evidence-view"] = _EVIDENCE_LOOKUP[options[0]]["detail_view"]

    selected = st.selectbox(
        "Find evidence for",
        options,
        format_func=lambda key: _EVIDENCE_LOOKUP[key]["label"],
        key="evidence-lookup-domain",
        on_change=_sync_evidence_detail_view,
    )
    spec = _EVIDENCE_LOOKUP[selected]
    read = dict(reads.get(selected) or {})
    rows = _evidence_lineage_rows(selected, read, spec)

    render_static_table(pd.DataFrame([
        {"Step": "Definition / boundary", "Record": spec["definition"]},
        {"Step": "Dataset", "Record": spec["datasets"]},
        {"Step": "Primary sources", "Record": "Trace the current claim and recent-context evidence in the lineage below, then open the detailed source register."},
    ]))

    control_a, control_b = st.columns([2, 1])
    with control_a:
        query = st.text_input(
            "Search this evidence path",
            placeholder="claim, source, dataset, or provenance",
            key="evidence-lineage-search",
        ).strip().casefold()
    with control_b:
        layers = ["All layers", "Retained analytical", "Primary record", "Company statement", "Approved reporting", "Analytical source"]
        layer = st.selectbox("Evidence layer", layers, key="evidence-lineage-layer")

    filtered = []
    for row in rows:
        haystack = " ".join(str(row.get(key) or "") for key in ("Claim / evidence", "Layer", "Source", "Provenance")).casefold()
        if query and query not in haystack:
            continue
        if layer != "All layers" and str(row.get("Layer") or "") != layer:
            continue
        filtered.append(row)

    display = pd.DataFrame([
        {key: row.get(key, "") for key in ("Claim / evidence", "Layer", "Source", "Provenance")}
        for row in filtered
    ])
    if display.empty:
        st.caption("No evidence-path records match the current search and layer filter.")
    else:
        render_static_table(display)

    snapshot_id = str(read.get("context_snapshot_id") or "").strip()
    if snapshot_id:
        st.caption(f"Current Context snapshot: {snapshot_id} · Detailed records below: {spec['detail_view']}")
    else:
        st.caption(f"Detailed records below: {spec['detail_view']}")

    linked = []
    seen = set()
    for row in filtered:
        label = str(row.get("Source") or "").strip()
        url = str(row.get("source_url") or "").strip()
        key = (label, url)
        if label and url.startswith("https://") and key not in seen:
            seen.add(key)
            linked.append(f"[{label}]({url})")
    if linked:
        st.markdown("Evidence links: " + " · ".join(linked[:6]))


def render_evidence_tab(fred_data, sector_data, sector_metrics, regime_metrics, energy_data, debt_markets_data, dashboard_data, infrastructure_data=None, connectivity_data=None, water_data=None, adaptation_data=None, workforce_data=None, economic_impact_data=None, platform_reads=None):
    render_tab_header(
        "Evidence",
        "Definitions, methods, source records, and the limits of the data.",
        "Methods and sources",
    )
    render_line_break()
    with st.expander("Evidence standards", expanded=False):
        st.markdown(EVIDENCE_STANDARDS)
    render_section(
        "Find the evidence",
        "Start with a current claim, then trace its definition, dataset, and primary sources.",
        first=True,
        compact=True,
    )
    _render_evidence_lookup(platform_reads)
    render_section("Detailed records", "Open the underlying methods, source registers, and observations.", compact=True)
    view = st.selectbox(
        "Evidence view",
        [
            "Metrics",
            "Market & finance",
            "Compute & data centers",
            "Connectivity",
            "Power & grid",
            "Water",
            "Adoption & outcomes",
        ],
        key="evidence-view",
    )
    if view == "Metrics":
        _render_metric_evidence(regime_metrics)
    elif view == "Market & finance":
        _render_market_finance_evidence(fred_data, sector_data, sector_metrics, debt_markets_data, dashboard_data)
    elif view == "Compute & data centers":
        _render_compute_data_center_evidence(infrastructure_data)
    elif view == "Connectivity":
        _render_connectivity_evidence(connectivity_data)
    elif view == "Power & grid":
        _render_power_grid_evidence(energy_data, infrastructure_data)
    elif view == "Water":
        _render_water_evidence(water_data, infrastructure_data)
    else:
        _render_adoption_outcomes_evidence(adaptation_data, workforce_data, economic_impact_data)
