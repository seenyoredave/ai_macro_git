from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from analytics.capital_commitments import load_commitment_components
from analytics.hhi_engine import sector_hhi_component_breakdown
from analytics.market_ledger import build_market_ledger
from analytics.private_capital import build_private_capital_realization
from analytics.water_campus import campus_water_dossier, county_water_exposure_profile
from config.benchmark_config import QQQ_WEIGHTS_EFFECTIVE_DATE
from config.factor_config import FACTOR_DISPLAY_NAMES
from rendering.visual_system import render_plotly_chart
from rendering.adoption import _adoption_source_rows
from rendering.charts_common import COLORS
from rendering.charts_finance import component_bars
from rendering.common import _coverage_text, _display_text
from rendering.comparison import render_change_evidence
from rendering.commercialization import filtered_ledger
from rendering.components import fmt_number, render_line_break, render_section, render_static_table, render_tab_header
from rendering.data_center import _campus_detail, _operator_detail
from rendering.dataframe import arrow_safe_dataframe
from rendering.evidence_gateway import EVIDENCE_LOOKUP as _EVIDENCE_LOOKUP
from rendering.evidence_tables import (
    _borrower_strain_component_table,
    _component_table,
    _lender_strain_component_table,
    render_edgar_data,
    render_macro_data,
    render_sector_scoreboard,
)
from rendering.finance import _debt_market_source_rows, _private_capital_detail_table
from rendering.grid_storage import _context as _grid_storage_context
from rendering.power import _active_campuses as _active_power_campuses, _power_source_rows
from rendering.tables import _company_table


def _water_evidence_payload(water_data) -> dict:
    """Normalize Water evidence input without importing private renderer helpers."""
    return water_data if isinstance(water_data, dict) else {}
from rendering.infrastructure_common import _infrastructure_source_rows
from rendering.labels import sector_display_name


EVIDENCE_STANDARDS = """
**AI Macro applies a consistent evidence standard across its research.**

The platform draws on public records, regulatory filings, official datasets, company disclosures, and selected business reporting. Sources are evaluated according to the quality and specificity of the evidence they provide, with preference given to primary records when material claims can be traced directly to them.

Secondary aggregators and specialist publications may identify relevant developments, but material claims are independently corroborated whenever practical.

Social media is excluded from the research pipeline. Posts, threads, comments, and other user-generated social content are not used for discovery, corroboration, evidence, or citation.

Consequential claims are evaluated against evidence that may support or challenge the initial interpretation. Conclusions reflect the available evidence rather than the interpretation of any individual source.

Political and regulatory developments are included when they produce a concrete economic or operational consequence. The platform identifies the acting institution or official and preserves the legal or procedural status of the action.

Corroboration requires independent evidence. Multiple reports derived from the same root source are treated as a single source rather than independent confirmation.

Current Context independently discovers and grounds recent developments in source evidence. It favors material developments from approved primary, general-news, specialist, and local sources. Recency and materiality thresholds may widen within a ten-day limit, but source quality is not relaxed simply to fill domain slots.
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
                "Interpretation": "One-year returns relative to profitable-company forward earnings; descriptive, not causal",
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


def _data_center_registry_coverage_tables(infrastructure_data):
    registry = (infrastructure_data or {}).get("data_center_registry")
    if not isinstance(registry, pd.DataFrame):
        registry = pd.DataFrame()

    grades = pd.DataFrame()
    if not registry.empty:
        values = registry.get("Evidence Grade", pd.Series("", index=registry.index)).fillna("").astype(str).str.upper().str.strip()
        counts = values.loc[values.ne("")].value_counts().sort_index()
        grades = pd.DataFrame([{"Evidence grade": grade, "Campuses": int(count)} for grade, count in counts.items()])

    fields_to_measure = [
        "Published Capacity Estimate MW",
        "Planned Data Center Capacity MW",
        "Contracted Utility Capacity MW",
        "Energized Capacity MW",
        "Annual Electricity Consumption MWh",
        "Water Withdrawal Gallons/Year",
        "Water Consumption Gallons/Year",
        "Source URL",
    ]
    rows = []
    for field in fields_to_measure:
        if field not in registry.columns:
            continue
        series = registry[field]
        if field == "Source URL":
            present = series.fillna("").astype(str).str.strip().ne("")
        else:
            present = pd.to_numeric(series, errors="coerce").notna()
        rows.append({
            "Field": field,
            "Campuses": int(present.sum()),
            "Coverage": fmt_number(float(present.mean()) * 100.0 if len(present) else 0.0, 1, suffix="%"),
        })
    return grades, pd.DataFrame(rows)

def _data_center_registry_summary(infrastructure_data):
    infrastructure = infrastructure_data or {}
    registry = infrastructure.get("data_center_registry")
    registry = registry if isinstance(registry, pd.DataFrame) else pd.DataFrame()
    summary = dict(infrastructure.get("data_center_registry_summary", {}) or {})

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

    return pd.DataFrame([
        {"Measure": "Campuses", "Value": f"{int(summary.get('campuses', len(registry)) or 0):,}"},
        {"Measure": "Mapped campuses", "Value": f"{int(summary.get('mapped_campuses', 0) or 0):,}"},
        {"Measure": "States", "Value": f"{int(summary.get('states', 0) or 0):,}"},
        {"Measure": "Facility entities", "Value": f"{int(summary.get('facility_entities', 0) or 0):,}"},
        {"Measure": "Building entities", "Value": f"{int(summary.get('building_entities', 0) or 0):,}"},
        {"Measure": "Source observations", "Value": f"{int(summary.get('source_observations', 0) or 0):,}"},
        {"Measure": "Capacity coverage", "Value": fmt_number(float(capacity.mean()) * 100.0 if len(capacity) else 0.0, 1, suffix="%")},
        {"Measure": "Higher-grade evidence", "Value": f"{int(grades.isin({'A', 'B'}).sum()):,}"},
    ])

def _direct_project_evidence_rows(infrastructure_data):
    campuses = (infrastructure_data or {}).get("data_center_registry")
    compute = ((infrastructure_data or {}).get("compute_manufacturing", {}) or {}).get("projects")
    rows = []
    if isinstance(campuses, pd.DataFrame) and not campuses.empty:
        rows.append({
            "Project class": "Data-center campuses",
            "Records": int(campuses["Campus ID"].nunique()) if "Campus ID" in campuses.columns else len(campuses),
            "Evidence basis": "Universal Data Center Registry",
        })
        power = pd.Series(False, index=campuses.index)
        for field in ["Contracted Utility Capacity MW", "Energized Capacity MW", "Planned Onsite Generation MW"]:
            if field in campuses.columns:
                power |= pd.to_numeric(campuses[field], errors="coerce").gt(0)
        rows.append({
            "Project class": "Data-center campuses with structured power evidence",
            "Records": int(power.sum()),
            "Evidence basis": "Universal Data Center Registry",
        })
    if isinstance(compute, pd.DataFrame):
        rows.append({"Project class": "Compute-manufacturing projects", "Records": len(compute), "Evidence basis": "CHIPS project ledger"})
    return pd.DataFrame(rows)

def _active_campus_power_rows(infrastructure_data):
    campuses = (infrastructure_data or {}).get("data_center_registry")
    if not isinstance(campuses, pd.DataFrame) or campuses.empty:
        return pd.DataFrame()
    status = campuses.get("Status", pd.Series("", index=campuses.index)).fillna("").astype(str).str.casefold()
    active_statuses = {
        "approved / permitted / under construction", "under construction", "construction",
        "announced", "planned", "proposed", "expanding",
    }
    table = campuses.loc[status.isin(active_statuses)].copy()
    if table.empty:
        return pd.DataFrame()
    power = pd.Series(False, index=table.index)
    for field in [
        "Published Capacity Estimate MW", "Planned Data Center Capacity MW",
        "Contracted Utility Capacity MW", "Energized Capacity MW", "Planned Onsite Generation MW",
    ]:
        if field in table.columns:
            power |= pd.to_numeric(table[field], errors="coerce").gt(0)
    table = table.loc[power].copy()
    columns = [
        "Campus ID", "Campus Name", "Operator", "State", "Status", "Expected Service Date", "Utility",
        "Published Capacity Estimate MW", "Planned Data Center Capacity MW",
        "Contracted Utility Capacity MW", "Energized Capacity MW",
        "Planned Onsite Generation MW", "Evidence Grade", "Source URL",
    ]
    columns = [column for column in columns if column in table.columns]
    return table[columns].reset_index(drop=True)

def _campus_water_rows(water_data, infrastructure_data):
    context = (water_data or {}).get("campus_context")
    if not isinstance(context, pd.DataFrame):
        context = (infrastructure_data or {}).get("data_center_registry")
    if not isinstance(context, pd.DataFrame) or context.empty:
        return pd.DataFrame()
    columns = [
        "Campus ID", "Campus Name", "Operator", "State", "County", "Status",
        "Total Withdrawal Mgal/d", "Freshwater Withdrawal Mgal/d", "Groundwater Withdrawal Mgal/d",
        "County D1+ Area Percent", "County D2+ Area Percent", "PWS Service Area Overlap",
        "PWS Match Count", "PWS Boundary Basis", "Direct Water Evidence",
        "Water Withdrawal Gallons/Year", "Water Consumption Gallons/Year", "Site WUE L/kWh",
        "Cooling System", "Water Source", "Water Permit or Utility Record",
    ]
    available = [column for column in columns if column in context.columns]
    return context[available].copy().reset_index(drop=True)

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
    grades, fields = _data_center_registry_coverage_tables(infrastructure)
    with st.expander("Universal data-center registry", expanded=False):
        render_static_table(_data_center_registry_summary(infrastructure))
    with st.expander("Campus evidence grades", expanded=False):
        render_static_table(grades)
    with st.expander("Campus field coverage", expanded=False):
        render_static_table(fields)
    with st.expander("Reviewed identity decisions", expanded=False):
        decisions = infrastructure.get("data_center_identity_decisions")
        render_static_table(decisions if isinstance(decisions, pd.DataFrame) else pd.DataFrame())
    with st.expander("National data-center evidence database", expanded=False):
        render_static_table(national_database if isinstance(national_database, pd.DataFrame) else pd.DataFrame())
    with st.expander("Data-center campuses", expanded=False):
        registry = infrastructure.get("data_center_registry")
        if registry is None or not isinstance(registry, pd.DataFrame):
            registry = infrastructure.get("locations")
        render_static_table(registry if isinstance(registry, pd.DataFrame) else pd.DataFrame())
    with st.expander("Active campus power records", expanded=False):
        render_static_table(_active_campus_power_rows(infrastructure))

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
                "source_name", "custodian", "source_url", "publication_date",
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
        gas = energy.get("gas_pipeline_projects")
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
        render_static_table(_campus_water_rows(water_data or {}, infrastructure_data or {}))
    with st.expander("Water source register", expanded=False):
        manifest = water.get("source_manifest")
        if isinstance(manifest, pd.DataFrame) and not manifest.empty:
            columns = [
                "source_name", "custodian", "source_url", "persistent_identifier",
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


def _render_adoption_outcomes_evidence(adoption_data, workforce_data, economic_impact_data):
    render_section("Adoption evidence", "Consumer use, employer adoption, and commercialization source records.", first=True)
    with st.expander("Adoption observations", expanded=False):
        render_static_table(_adoption_source_rows(adoption_data or {}))

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






def _market_company_records(sector_data, scope: str) -> pd.DataFrame:
    sector_data = sector_data or {}
    if scope == "Full market universe":
        ledger = build_market_ledger(sector_data)
        frame = (ledger or {}).get("companies", pd.DataFrame())
        return frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    frame = sector_data.get(scope)
    if not isinstance(frame, pd.DataFrame):
        return pd.DataFrame()
    return _company_table(frame)


def _render_market_reference_records(sector_data) -> None:
    sectors = [
        key for key, frame in (sector_data or {}).items()
        if isinstance(frame, pd.DataFrame) and not frame.empty
    ]
    options = ["Full market universe", *sectors]
    scope = st.selectbox(
        "Company record scope",
        options,
        format_func=lambda value: value if value == "Full market universe" else sector_display_name(value),
        key="evidence-market-company-scope",
    )
    render_static_table(_market_company_records(sector_data, scope))


def _render_finance_reference_records(commercialization_data, debt_markets_data, regime_metrics) -> None:
    options = [
        "Commercial disclosures",
        "Forward commitment records",
        "Private-fund records",
        "Debt-market readings",
        "Borrower stress components",
        "Lender stress components",
    ]
    view = st.radio("Reference dataset", options, horizontal=True, key="evidence-finance-reference-view")
    borrower_strain = (regime_metrics or {}).get("Borrower Strain Components", {}) or {}
    lender_strain = (regime_metrics or {}).get("Lender Strain Components", {}) or {}
    if view == "Forward commitment records":
        frame = load_commitment_components()
        columns = [
            "Ticker", "Category", "Value", "As Of Date", "Filing Date",
            "Scope", "Carried Forward", "Source URL",
        ]
        frame = frame[[column for column in columns if column in frame.columns]].copy()
    elif view == "Private-fund records":
        realization = build_private_capital_realization()
        frame = _private_capital_detail_table(realization.get("funds", pd.DataFrame()))
    elif view == "Debt-market readings":
        frame = _debt_market_source_rows(debt_markets_data)
    elif view == "Borrower stress components":
        frame = _borrower_strain_component_table(borrower_strain)
    elif view == "Lender stress components":
        frame = _lender_strain_component_table(lender_strain)
    else:
        frame = filtered_ledger(
            commercialization_data,
            pillars=["Revenue realization", "Cost pressure", "Capital burden"],
        )
    render_static_table(frame)


def _render_compute_reference_records(infrastructure_data, commercialization_data) -> None:
    projects = (((infrastructure_data or {}).get("compute_manufacturing", {}) or {}).get("projects"))
    view = st.radio(
        "Reference dataset",
        ["Manufacturing projects", "AI service-cost disclosures"],
        horizontal=True,
        key="evidence-compute-reference-view",
    )
    if view == "AI service-cost disclosures":
        frame = filtered_ledger(
            commercialization_data,
            pillars=["Compute economics", "Revenue realization", "Cost pressure"],
        )
    else:
        frame = projects if isinstance(projects, pd.DataFrame) else pd.DataFrame()
    render_static_table(frame)


def _render_data_center_reference_records(infrastructure_data) -> None:
    infrastructure = infrastructure_data or {}
    campuses = infrastructure.get("data_center_registry")
    campuses = campuses if isinstance(campuses, pd.DataFrame) else pd.DataFrame()
    entities = infrastructure.get("data_center_entities")
    entities = entities if isinstance(entities, pd.DataFrame) else pd.DataFrame()
    options = ["Campuses", "Operators"] + (["Hierarchy"] if not entities.empty else [])
    view = st.radio("Reference dataset", options, horizontal=True, key="evidence-data-center-reference-view")
    if view == "Operators":
        frame = _operator_detail(campuses)
    elif view == "Hierarchy":
        columns = [
            "Entity Level", "Entity Name", "Entity ID", "Parent Entity ID", "Campus ID",
            "Operator", "State", "County", "Square Feet",
        ]
        frame = entities[[column for column in columns if column in entities.columns]].copy()
    else:
        frame = _campus_detail(campuses)
    render_static_table(frame)


def _render_connectivity_reference_records(connectivity_data) -> None:
    connectivity = connectivity_data or {}
    facilities = connectivity.get("interconnection_facilities")
    facility_summary = connectivity.get("interconnection_facility_summary")
    facility_frame = facilities if isinstance(facilities, pd.DataFrame) and not facilities.empty else facility_summary
    datasets = {
        "Cable systems": connectivity.get("submarine_cable_systems"),
        "Landing markets": connectivity.get("cable_landing_markets"),
        "IXP registry": connectivity.get("ixp_snapshot"),
        "Interconnection facilities": facility_frame,
        "Middle-mile awards": connectivity.get("middle_mile_awards"),
        "Campus connectivity": connectivity.get("campus_connectivity_snapshot"),
    }
    view = st.radio("Reference dataset", list(datasets), horizontal=True, key="evidence-connectivity-reference-view")
    render_static_table(datasets.get(view) if isinstance(datasets.get(view), pd.DataFrame) else pd.DataFrame())


def _render_power_reference_records(energy_data, infrastructure_data) -> None:
    energy = energy_data or {}
    datasets = {
        "Retail demand & prices": energy.get("retail_history"),
        "Generation": energy.get("generation_history"),
        "Capacity snapshot": energy.get("capacity_snapshot"),
        "Generator pipeline": energy.get("generator_pipeline"),
        "Wholesale prices": energy.get("wholesale_prices"),
        "Large-load campuses": _active_power_campuses(infrastructure_data or {}),
        "Gas pipelines": energy.get("gas_pipeline_projects"),
        "LNG projects": energy.get("lng_projects"),
    }
    view = st.radio("Reference dataset", list(datasets), horizontal=True, key="evidence-power-reference-view")
    render_static_table(datasets.get(view) if isinstance(datasets.get(view), pd.DataFrame) else pd.DataFrame())


def _render_grid_storage_reference_records(energy_data, infrastructure_data) -> None:
    context = _grid_storage_context(energy_data or {}, infrastructure_data or {})
    datasets = {
        "Interconnection requests": context.get("development", {}).get("active_queue"),
        "Queue outcomes": context.get("queue_outcomes"),
        "Queue conditions by region": context.get("queue_regions"),
        "Reserve margins": context.get("reserve_margins"),
        "Operating storage": context.get("storage_duration"),
    }
    view = st.radio("Reference dataset", list(datasets), horizontal=True, key="evidence-grid-storage-reference-view")
    render_static_table(datasets.get(view) if isinstance(datasets.get(view), pd.DataFrame) else pd.DataFrame())


def _water_campuses(water_data, infrastructure_data) -> pd.DataFrame:
    water = _water_evidence_payload(water_data or {})
    campuses = water.get("campus_context")
    if not isinstance(campuses, pd.DataFrame):
        campuses = (infrastructure_data or {}).get("data_center_registry")
    return campuses if isinstance(campuses, pd.DataFrame) else pd.DataFrame()


def _render_water_reference_records(water_data, infrastructure_data) -> None:
    water = _water_evidence_payload(water_data or {})
    campuses = _water_campuses(water_data, infrastructure_data)
    datasets = {
        "Campus profile": campus_water_dossier(campuses),
        "County exposure": county_water_exposure_profile(campuses),
        "County drought snapshot": water.get("usdm_county_drought"),
        "EPA service-area matches": water.get("epa_pws_matches"),
        "Campus records": campuses,
        "Thermoelectric plants": water.get("eia_plants"),
    }
    view = st.radio("Reference dataset", list(datasets), horizontal=True, key="evidence-water-reference-view")
    render_static_table(datasets.get(view) if isinstance(datasets.get(view), pd.DataFrame) else pd.DataFrame())


def _render_adoption_reference_records(adoption_data, commercialization_data) -> None:
    adoption = adoption_data or {}
    datasets = {
        "People history": adoption.get("consumer_history"),
        "Business history": adoption.get("national_history"),
        "AI supplement": ((adoption.get("depth") or {}).get("table")),
        "Industry snapshot": adoption.get("sector_snapshot"),
        "Paid disclosures": filtered_ledger(
            commercialization_data,
            pillars=["Paid demand", "Enterprise adoption", "Reach"],
        ),
    }
    view = st.radio("Reference dataset", list(datasets), horizontal=True, key="evidence-adoption-reference-view")
    render_static_table(datasets.get(view) if isinstance(datasets.get(view), pd.DataFrame) else pd.DataFrame())


def _render_workforce_reference_records(workforce_data) -> None:
    workforce = workforce_data or {}
    datasets = {
        "Employment": workforce.get("employment_history"),
        "Hourly earnings": workforce.get("earnings_history"),
        "Labor flows": workforce.get("labor_flows_history"),
        "Job openings": workforce.get("job_openings_history"),
        "Occupation exposure": workforce.get("occupation_exposure"),
        "Inflation": workforce.get("cpi_history"),
    }
    view = st.radio("Reference dataset", list(datasets), horizontal=True, key="evidence-workforce-reference-view")
    render_static_table(datasets.get(view) if isinstance(datasets.get(view), pd.DataFrame) else pd.DataFrame())


def _render_economic_reference_records(economic_impact_data, commercialization_data) -> None:
    data = economic_impact_data or {}
    datasets = {
        "Productivity and costs": data.get("productivity_history"),
        "Worker compensation": data.get("value_transmission_history"),
        "Earnings distribution": data.get("earnings_distribution_history"),
        "Information investment": data.get("investment_history"),
        "Inflation": data.get("cpi_history"),
        "Provider revenue and paid use": filtered_ledger(
            commercialization_data,
            pillars=["Revenue realization", "Paid demand", "Enterprise adoption"],
        ),
    }
    view = st.radio("Reference dataset", list(datasets), horizontal=True, key="evidence-economic-reference-view")
    render_static_table(datasets.get(view) if isinstance(datasets.get(view), pd.DataFrame) else pd.DataFrame())


def _render_domain_reference_records(
    selected: str,
    *,
    sector_data,
    regime_metrics,
    energy_data,
    debt_markets_data,
    infrastructure_data,
    connectivity_data,
    water_data,
    adoption_data,
    workforce_data,
    economic_impact_data,
    commercialization_data,
) -> None:
    if selected == "market":
        _render_market_reference_records(sector_data)
    elif selected == "finance":
        _render_finance_reference_records(commercialization_data, debt_markets_data, regime_metrics)
    elif selected == "compute":
        _render_compute_reference_records(infrastructure_data, commercialization_data)
    elif selected == "data_center":
        _render_data_center_reference_records(infrastructure_data)
    elif selected == "connectivity":
        _render_connectivity_reference_records(connectivity_data)
    elif selected == "power":
        _render_power_reference_records(energy_data, infrastructure_data)
    elif selected == "grid_storage":
        _render_grid_storage_reference_records(energy_data, infrastructure_data)
    elif selected == "water":
        _render_water_reference_records(water_data, infrastructure_data)
    elif selected == "adoption":
        _render_adoption_reference_records(adoption_data, commercialization_data)
    elif selected == "workforce":
        _render_workforce_reference_records(workforce_data)
    elif selected == "economic_impact":
        _render_economic_reference_records(economic_impact_data, commercialization_data)
    else:
        raise KeyError(f"Unknown evidence domain: {selected}")


def _render_domain_technical_records(
    selected: str,
    *,
    fred_data,
    sector_data,
    sector_metrics,
    regime_metrics,
    energy_data,
    debt_markets_data,
    dashboard_data,
    infrastructure_data,
    connectivity_data,
    water_data,
    adoption_data,
    workforce_data,
    economic_impact_data,
) -> None:
    if selected == "market":
        render_section("Sector scoreboard", "Comparable conditions across the AI-equity sector baskets.", first=True, compact=True)
        render_sector_scoreboard((dashboard_data or {}).get("macro_df", pd.DataFrame()))
        render_section("Factor and pressure data", "Underlying factor scores, trading-pressure components, and concentration contributors.", compact=True)
        _render_sector_factor_pressure_data(sector_data, sector_metrics)
        render_edgar_data(sector_data)
    elif selected == "finance":
        render_section("Financial observations", "Retained financial-condition, credit, and private-capital records.", first=True)
        render_macro_data(fred_data)
        with st.expander("Debt-market observations", expanded=False):
            render_static_table(_debt_market_source_rows(debt_markets_data))
        with st.expander("Private-capital fund observations", expanded=False):
            realization = build_private_capital_realization()
            render_static_table(_private_capital_detail_table(realization.get("funds", pd.DataFrame())))
    elif selected == "compute":
        compute = ((infrastructure_data or {}).get("compute_manufacturing", {}) or {})
        render_section("Compute-manufacturing evidence", "Series definitions and announced manufacturing projects.", first=True)
        with st.expander("G.17 series definitions", expanded=False):
            render_static_table(compute.get("series_contract", pd.DataFrame()))
        with st.expander("Infrastructure source register", expanded=False):
            render_static_table((infrastructure_data or {}).get("infrastructure_source_manifest", pd.DataFrame()))
    elif selected == "data_center":
        grades, fields = _data_center_registry_coverage_tables(infrastructure_data or {})
        render_section("Registry coverage", "Campus identity, capacity-field coverage, and source quality.", first=True)
        render_static_table(_data_center_registry_summary(infrastructure_data or {}))
        with st.expander("Campus evidence grades", expanded=False):
            render_static_table(grades)
        with st.expander("Campus field coverage", expanded=False):
            render_static_table(fields)
        with st.expander("Reviewed identity decisions", expanded=False):
            render_static_table((infrastructure_data or {}).get("data_center_identity_decisions", pd.DataFrame()))
        with st.expander("Infrastructure source register", expanded=False):
            render_static_table((infrastructure_data or {}).get("infrastructure_source_manifest", pd.DataFrame()))
    elif selected == "connectivity":
        render_section("Connectivity source register", "Public network and infrastructure sources used in the domain.", first=True)
        render_static_table((connectivity_data or {}).get("source_manifest", pd.DataFrame()))
    elif selected == "power":
        render_section("Power source register", "Dataset readings, observation dates, coverage, and custodians.", first=True)
        render_static_table(_power_source_rows(energy_data or {}))
    elif selected == "grid_storage":
        context = _grid_storage_context(energy_data or {}, infrastructure_data or {})
        render_section("Grid & Storage source register", "Interconnection, reliability, storage, and construction evidence.", first=True)
        render_static_table(context.get("source_manifest", pd.DataFrame()))
        with st.expander("Electric-power construction chronology", expanded=False):
            construction = (infrastructure_data or {}).get("construction_history")
            if isinstance(construction, pd.DataFrame) and not construction.empty:
                mask = construction.get("Series", pd.Series("", index=construction.index)).astype(str).eq("Electric Power Construction")
                render_static_table(construction.loc[mask].copy())
            else:
                render_static_table(pd.DataFrame())
    elif selected == "water":
        water = _water_evidence_payload(water_data or {})
        render_section("Water evidence coverage", "National accounts, campus disclosure, and source coverage.", first=True)
        render_static_table(_water_evidence_summary_rows(water))
        with st.expander("Water source register", expanded=False):
            render_static_table(water.get("source_manifest", pd.DataFrame()))
        with st.expander("Water field dictionary", expanded=False):
            render_static_table(water.get("field_dictionary", pd.DataFrame()))
        with st.expander("USGS county reconciliation", expanded=False):
            render_static_table(water.get("usgs_reconciliation", pd.DataFrame()))
    elif selected == "adoption":
        render_section("Adoption source observations", "Consumer-use, business-adoption, and integration records.", first=True)
        render_static_table(_adoption_source_rows(adoption_data or {}))
    elif selected == "workforce":
        render_section("Workforce source register", "Official labor-market sources and retained coverage.", first=True)
        render_static_table((workforce_data or {}).get("source_manifest", pd.DataFrame()))
    elif selected == "economic_impact":
        render_section("Economic Outcomes source register", "Productivity, compensation, earnings, output, and investment sources.", first=True)
        render_static_table((economic_impact_data or {}).get("source_manifest", pd.DataFrame()))
    else:
        raise KeyError(f"Unknown evidence domain: {selected}")

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
    generator = str(read.get("generator") or "").strip().casefold()
    headline_support = next((
        item for item in read.get("claim_support", []) or []
        if isinstance(item, dict) and str(item.get("field") or "") == "headline"
    ), {})
    fact_ids = [str(item) for item in headline_support.get("fact_ids", []) or [] if str(item).strip()]
    if generator == "openai":
        first_claim = str(read.get("headline") or "Generated interpretation unavailable.").strip()
        layer = "Validated interpretation"
        source = static_sources or "Validated retained evidence packet"
        support = f" · fact IDs: {', '.join(fact_ids)}" if fact_ids else ""
        provenance = f"OpenAI commentary passed deterministic validation{support} · boundary: {spec['definition']}"
    else:
        first_claim = "Retained evidence remains available; generated commentary is not currently published."
        layer = "Retained evidence"
        source = "Detailed retained source register"
        provenance = f"{spec['datasets']} · boundary: {spec['definition']}"
    rows = [{
        "Claim / evidence": first_claim,
        "Layer": layer,
        "Source": source,
        "Provenance": provenance,
        "source_url": "",
    }]

    context_payload = read.get("current_context", {}) if isinstance(read.get("current_context"), dict) else {}
    event_by_id = {
        str(event.get("event_id") or ""): dict(event)
        for event in context_payload.get("events", []) or []
        if isinstance(event, dict) and str(event.get("event_id") or "").strip()
    }
    reference_by_number = {
        int(item.get("normalized_number")): item
        for item in references
        if str(item.get("normalized_number") or "").isdigit()
    }
    for item in read.get("current_context_items", []) or []:
        if not isinstance(item, dict):
            continue
        event = event_by_id.get(str(item.get("event_id") or ""), {})
        try:
            number = int(item.get("normalized_number"))
        except (TypeError, ValueError):
            number = 0
        reference = reference_by_number.get(number, {})
        source = str(reference.get("source_label") or reference.get("source_name") or event.get("source_label") or event.get("source_name") or "Source").strip()
        provider = str(event.get("discovery_provider") or "").strip()
        discovered_via = str(event.get("discovered_via") or "").strip()
        resolution_mode = str(event.get("evidence_resolution_mode") or "").strip()
        seed_source = str(event.get("evidence_seed_source_name") or "").strip()
        verification = str(event.get("verification_status") or item.get("status") or "").replace("_", " ").strip()
        if resolution_mode == "alternate_source" and seed_source:
            provenance = f"Event surfaced by {seed_source}; evidence established independently by {source}"
        elif discovered_via:
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


def _read_fact_ids(read: dict) -> list[str]:
    fact_ids: list[str] = []
    for claim in read.get("claim_support", []) or []:
        if not isinstance(claim, dict):
            continue
        for fact_id in claim.get("fact_ids", []) or []:
            value = str(fact_id or "").strip()
            if value and value not in fact_ids:
                fact_ids.append(value)
    return fact_ids


def _packet_fact_index(packet: dict) -> dict[str, dict]:
    return {
        str(item.get("id") or "").strip(): dict(item)
        for item in packet.get("facts", []) or []
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }


def _safe_source_link(label: str, url: str) -> str:
    safe_label = html.escape(str(label or "Source").strip())
    safe_url = str(url or "").strip()
    if safe_url.startswith("https://"):
        return (
            f'<a class="rm-evidence-source-link" href="{html.escape(safe_url, quote=True)}" '
            f'target="_blank" rel="noopener noreferrer">{safe_label}</a>'
        )
    return f'<span class="rm-evidence-source-text">{safe_label}</span>'


def _render_evidence_interpretation(read: dict) -> None:
    generator = str(read.get("generator") or "").strip().casefold()
    if generator == "openai":
        headline = str(read.get("headline") or "").strip()
        analysis = str(read.get("analysis") or "").strip()
        kicker = "Validated interpretation"
    else:
        headline = "Retained evidence is available."
        analysis = "No validated generated interpretation is published for the current analytical evidence snapshot."
        kicker = "Analytical evidence"
    st.markdown(
        "".join([
            '<div class="rm-evidence-interpretation">',
            f'<div class="rm-evidence-kicker">{html.escape(kicker)}</div>',
            f'<div class="rm-evidence-interpretation-title">{html.escape(headline)}</div>',
            f'<div class="rm-evidence-interpretation-copy">{html.escape(analysis)}</div>' if analysis else "",
            '</div>',
        ]),
        unsafe_allow_html=True,
    )


def _render_cited_facts(read: dict, packet: dict) -> None:
    fact_index = _packet_fact_index(packet)
    facts = [fact_index[fact_id] for fact_id in _read_fact_ids(read) if fact_id in fact_index][:6]
    if not facts:
        st.caption("No generated claim-to-fact links are published for the current evidence snapshot.")
        return
    cards = []
    for fact in facts:
        label = str(fact.get("label") or "Evidence").strip()
        value = str(fact.get("display") or "n/a").strip()
        context = str(fact.get("context") or "").strip()
        cards.append(
            '<div class="rm-evidence-fact-card">'
            '<div class="rm-evidence-fact-label">{}</div>'
            '<div class="rm-evidence-fact-value">{}</div>'
            '{}'
            '</div>'.format(
                html.escape(label),
                html.escape(value),
                f'<div class="rm-evidence-fact-context">{html.escape(context)}</div>' if context else "",
            )
        )
    st.markdown('<div class="rm-evidence-fact-grid">' + ''.join(cards) + '</div>', unsafe_allow_html=True)


def _render_analytical_foundation(packet: dict, spec: dict) -> None:
    references = [dict(item) for item in packet.get("references", []) or [] if isinstance(item, dict)]
    source_links = []
    seen = set()
    for reference in references:
        label = str(reference.get("source_label") or reference.get("source_name") or "").strip()
        url = str(reference.get("source_url") or "").strip()
        key = (label, url)
        if not label or key in seen:
            continue
        seen.add(key)
        source_links.append(_safe_source_link(label, url))
    sources_html = ' · '.join(source_links) if source_links else '<span class="rm-evidence-source-text">Detailed source register</span>'
    st.markdown(
        "".join([
            '<div class="rm-evidence-foundation-card">',
            '<div class="rm-evidence-card-kicker">Data foundation</div>',
            f'<div class="rm-evidence-card-copy">{html.escape(str(spec.get("datasets") or "").strip())}</div>',
            '<div class="rm-evidence-card-divider"></div>',
            '<div class="rm-evidence-card-kicker">Source foundation</div>',
            f'<div class="rm-evidence-source-list">{sources_html}</div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )


def _render_scope_and_limits(packet: dict, spec: dict) -> None:
    boundaries = [str(item).strip() for item in packet.get("boundaries", []) or [] if str(item).strip()]
    items = [str(spec.get("definition") or "").strip(), *boundaries]
    items = [item for item in items if item]
    list_html = ''.join(f'<li>{html.escape(item)}</li>' for item in items)
    st.markdown(
        "".join([
            '<div class="rm-evidence-foundation-card">',
            '<div class="rm-evidence-card-kicker">Scope &amp; limits</div>',
            f'<ul class="rm-evidence-boundary-list">{list_html}</ul>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )


def _render_current_context_evidence(read: dict) -> None:
    items = [dict(item) for item in read.get("current_context_items", []) or [] if isinstance(item, dict) and str(item.get("text") or "").strip()]
    if not items:
        return
    references = {
        int(item.get("normalized_number")): dict(item)
        for item in read.get("references", []) or []
        if isinstance(item, dict) and str(item.get("normalized_number") or "").isdigit()
    }
    cards = []
    for item in items[:2]:
        try:
            number = int(item.get("normalized_number"))
        except (TypeError, ValueError):
            number = 0
        reference = references.get(number, {})
        source = str(reference.get("source_label") or reference.get("source_name") or "Source").strip()
        url = str(reference.get("source_url") or item.get("source_url") or "").strip()
        cards.append(
            '<div class="rm-evidence-context-card">'
            f'<div class="rm-evidence-context-copy">{html.escape(str(item.get("text") or "").strip())}</div>'
            f'<div class="rm-evidence-context-source">{_safe_source_link(source, url)}</div>'
            '</div>'
        )
    if cards:
        render_section(
            "Recent context",
            "Current developments are sourced separately from retained analytical evidence.",
        )
        st.markdown('<div class="rm-evidence-context-grid">' + ''.join(cards) + '</div>', unsafe_allow_html=True)


def _evidence_domain_selector() -> str:
    options = list(_EVIDENCE_LOOKUP)
    if st.session_state.get("evidence-lookup-domain") not in options:
        st.session_state["evidence-lookup-domain"] = options[0]
    return st.selectbox(
        "Evidence for",
        options,
        format_func=lambda key: _EVIDENCE_LOOKUP[key]["label"],
        key="evidence-lookup-domain",
    )


def _render_evidence_trace(
    selected: str,
    platform_reads: dict | None,
    evidence_packets: dict | None,
) -> None:
    reads = platform_reads or {}
    packets = evidence_packets or {}
    spec = _EVIDENCE_LOOKUP[selected]
    read = dict(reads.get(selected) or {})
    packet = dict(packets.get(selected) or {})

    _render_evidence_interpretation(read)
    render_section(
        "Evidence used in the Read",
        "Analytical records cited by the published Read.",
    )
    _render_cited_facts(read, packet)

    foundation, limits = st.columns(2)
    with foundation:
        _render_analytical_foundation(packet, spec)
    with limits:
        _render_scope_and_limits(packet, spec)

    _render_current_context_evidence(read)


def _render_lineage_audit(selected: str, platform_reads: dict | None) -> None:
    reads = platform_reads or {}
    spec = _EVIDENCE_LOOKUP[selected]
    read = dict(reads.get(selected) or {})
    rows = _evidence_lineage_rows(selected, read, spec)

    control_a, control_b = st.columns([2, 1])
    with control_a:
        query = st.text_input(
            "Search claim lineage",
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
        st.caption("No lineage records match the current search and layer filter.")
    else:
        render_static_table(display)

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
        st.markdown("Source links: " + " · ".join(linked[:8]))

def render_evidence_tab(
    fred_data,
    sector_data,
    sector_metrics,
    regime_metrics,
    energy_data,
    debt_markets_data,
    dashboard_data,
    infrastructure_data=None,
    connectivity_data=None,
    water_data=None,
    adoption_data=None,
    workforce_data=None,
    economic_impact_data=None,
    commercialization_data=None,
    platform_reads=None,
    evidence_packets=None,
    comparison_state=None,
    comparison_change_set=None,
):
    render_tab_header(
        "Evidence",
        "Sources, formulas, coverage rules, and records behind the platform’s published research.",
        "Sources and methodology",
    )
    render_line_break()
    render_section(
        "Research standards",
        "Source selection, corroboration, and the boundary between evidence and interpretation.",
        first=True,
    )
    with st.expander("Read the evidence standards", expanded=False):
        st.markdown(EVIDENCE_STANDARDS)

    selected = _evidence_domain_selector()
    spec = _EVIDENCE_LOOKUP[selected]

    read_tab, change_tab, reference_tab, technical_tab = st.tabs(
        ["Read citations", "Change inspection", "Reference records", "Technical records"]
    )

    with read_tab:
        render_section(
            "Read citations",
            "Open a published Read and inspect the analytical records it cites.",
            first=True,
        )
        _render_evidence_trace(selected, platform_reads, evidence_packets)
        with st.expander("Open claim lineage", expanded=False):
            _render_lineage_audit(selected, platform_reads)

    with change_tab:
        render_section(
            "Change inspection",
            "Inspect a point-in-time metric change, its source register, and its published Read linkage.",
            first=True,
        )
        render_change_evidence(
            comparison_state,
            comparison_change_set,
            platform_reads=platform_reads,
            evidence_packets=evidence_packets,
            domain_filter=selected,
        )

    with reference_tab:
        render_section(
            "Reference records",
            f"Underlying {spec['label']} datasets used by the analytical views.",
            first=True,
        )
        _render_domain_reference_records(
            selected,
            sector_data=sector_data,
            regime_metrics=regime_metrics,
            energy_data=energy_data,
            debt_markets_data=debt_markets_data,
            infrastructure_data=infrastructure_data,
            connectivity_data=connectivity_data,
            water_data=water_data,
            adoption_data=adoption_data,
            workforce_data=workforce_data,
            economic_impact_data=economic_impact_data,
            commercialization_data=commercialization_data,
        )

    with technical_tab:
        render_section(
            "Technical records",
            "Coverage, source registers, lineage, formulas, and analytical construction.",
            first=True,
        )
        _render_domain_technical_records(
            selected,
            fred_data=fred_data,
            sector_data=sector_data,
            sector_metrics=sector_metrics,
            regime_metrics=regime_metrics,
            energy_data=energy_data,
            debt_markets_data=debt_markets_data,
            dashboard_data=dashboard_data,
            infrastructure_data=infrastructure_data,
            connectivity_data=connectivity_data,
            water_data=water_data,
            adoption_data=adoption_data,
            workforce_data=workforce_data,
            economic_impact_data=economic_impact_data,
        )
        with st.expander("Open platform metric methods", expanded=False):
            _render_metric_evidence(regime_metrics)

