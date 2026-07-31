"""High-density research renderers built on the existing AI Macro engine."""

from __future__ import annotations

import html
import numpy as np
import pandas as pd
import streamlit as st

from analytics.hhi_engine import sector_hhi_component_breakdown
from analytics.financial_conditions import (
    nfci_condition,
    nfci_direction,
    nfci_snapshot,
)
from analytics.macro_dataframe import build_macro_dashboard_data
from analytics.regime_engine import AEI_VERSION, PRESSURE_VERSION
from analytics.valuation import SECTOR_VALUATION_VERSION
from analytics.sector_assessment import select_current_sector_assessment
from config.debt_markets_config import DEBT_MARKET_SERIES
from config.energy_config import ENERGY_SERIES
from config.factor_config import FACTOR_DISPLAY_NAMES
from config.metric_definitions import METRIC_DEFINITIONS
from helpers.gaps import industrial_growth_gap
from helpers.labels import (
    adoption_label,
    power_capacity_gap_label,
    sector_display_name,
    short_regime_label,
    speculation_label,
    validation_label,
)
from helpers.macro_dashboard import (
    _borrower_strain_component_table,
    _component_table,
    _lender_strain_component_table,
    render_edgar_data,
    render_macro_data,
)
from helpers.render_sector import render_ticker_controls

from research_overlay.components import (
    arrow_safe_dataframe,
    fmt_date,
    fmt_number,
    metric_card,
    render_definition,
    render_line_break,
    render_panel_heading,
    render_section,
    render_static_table,
    render_statline,
    render_tab_header,
)
from research_overlay.tables import _company_table
from research_overlay.visuals import (
    COLORS,
    component_bars,
    current_gap_bars,
    dual_history,
    earnings_support_map,
    debt_market_history,
    financial_conditions_history,
    FACILITY_SIZE_METRICS,
    data_center_map,
    infrastructure_construction_history,
    supporting_construction_history,
    adaptation_history,
    adaptation_sector_bars,
    funding_history,
    history_from_frame,
    hhi_component_chart,
    speculative_load_matrix,
    pressure_component_chart,
    restyle_figure,
    sector_factor_chart,
    single_history,
)


def _value(regime_metrics, name):
    return pd.to_numeric((regime_metrics or {}).get(name, np.nan), errors="coerce")


def _display_text(value):
    """Format a scalar for schema-stable display tables."""
    if value is None:
        return ""
    try:
        missing = pd.isna(value)
        if isinstance(missing, (bool, np.bool_)) and missing:
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def _forward_multiple_text(value, status=None):
    """Format sector EV/EBIT without presenting a non-meaningful ratio as missing."""
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.notna(numeric) and np.isfinite(numeric):
        return f"{numeric:.1f}x"
    status_text = str(status or "")
    if status_text.startswith("NM"):
        return "NM"
    return "n/a"


def _source(regime_metrics, prefix):
    return (regime_metrics or {}).get(f"{prefix} Source", "Current")


def _fallback(regime_metrics, prefix):
    return (regime_metrics or {}).get(f"{prefix} Fallback Date")


def _fred_value(fred_data, name):
    payload = (fred_data or {}).get(name, np.nan)
    return pd.to_numeric(payload.get("value", np.nan) if isinstance(payload, dict) else payload, errors="coerce")


def _coverage_text(result, total=None):
    result = result or {}
    valid = result.get("valid_components")
    coverage = pd.to_numeric(result.get("coverage"), errors="coerce")
    if valid is not None and total is not None:
        return f"{valid}/{total} components"
    if pd.notna(coverage):
        return f"{coverage * 100:.0f}% coverage"
    return "coverage n/a"


def _metric_context(name, value):
    if name == "AI Equity Index":
        return f"{short_regime_label(value)} equity regime"
    if name == "AI Development Intensity":
        if pd.isna(value):
            return "Development intensity unavailable"
        return "Observable capital and physical deployment"
    if name == "Power Stress Index":
        if pd.isna(value):
            return "Power-system stress unavailable"
        return "Above reference" if value > 0 else "Below reference"
    if name == "Sector Basket Concentration":
        return "Adjusted market-value concentration"
    return ""


TAB_METRIC_REGISTRIES = {
    "macro": [
        "AI Equity Index",
        "AI Development Intensity",
        "Speculation Gap",
        "Economic Validation Gap",
        "AI-Industrial Growth Gap",
        "Power Stress Index",
        "Power Capacity Gap",
    ],
    "finance": [
        "Internal Funding Coverage",
        "Cash Reserve Runway",
        "Debt Financing Pulse",
        "Forward Commitment Load",
        "Corporate Bond Market Distress",
        "Investment-Grade Bond Distress",
        "High-Yield Bond Distress",
        "Borrower Strain",
        "Lender Strain",
        "NFCI",
        "ANFCI",
    ],
    "infrastructure": [
        "Data Center Construction",
        "Evidence-Graded Facility Registry",
        "Computer, Electronic & Electrical Manufacturing Construction",
        "Communication Construction",
        "Public Highway and Street Construction",
        "Public Transportation Construction",
        "Public Water Supply Construction",
    ],
    "energy": [
        "Henry Hub Natural Gas",
        "WTI Crude Oil",
        "Coal Production",
        "Renewable Power Output",
        "Commercial Electricity Price",
        "Industrial Electricity Price",
        "Electric Power Output",
        "Electric Power Capacity",
        "Electric Power Capacity Utilization",
        "Power Stress Index",
        "Power Capacity Gap",
    ],
    "adaptation": [
        "Current Business AI Use",
        "Expected Business AI Use",
        "Expected Adoption Gap",
        "Adoption Breadth",
    ],
    "market": [
        "Sector AI Equity Index",
        "Trading Pressure",
        "Forward EV/EBIT",
        "Loss-Making EV Share",
        "Earnings Support",
        "Speculative Load",
        "Sector Movement",
        "Risk Breadth",
        "Sector Basket Concentration",
    ],
}


def _render_tab_metric_registry(tab_key):
    definitions = TAB_METRIC_REGISTRIES[tab_key]
    with st.expander("Metric registry", expanded=False):
        selected = st.selectbox(
            "Metric or analytical product",
            definitions,
            key=f"research-{tab_key}-definition",
            label_visibility="collapsed",
        )
        render_definition(METRIC_DEFINITIONS[selected])


def _latest_component_date(components):
    dates = []
    for payload in (components or {}).values():
        if not isinstance(payload, dict):
            continue
        parsed = pd.to_datetime(payload.get("as_of"), errors="coerce", format="mixed")
        if pd.notna(parsed):
            dates.append(parsed)
    return max(dates) if dates else None


def _financial_condition_source_stat(*, source, fallback_date, trend, components, live_sources):
    source_text = str(source or "").strip()
    is_archive = "archive" in source_text.lower()
    history_date = None
    history = (trend or {}).get("history")
    if isinstance(history, pd.DataFrame) and not history.empty and "Date" in history.columns:
        parsed = pd.to_datetime(history["Date"], errors="coerce", format="mixed").dropna()
        if not parsed.empty:
            history_date = parsed.max()
    observation_date = fallback_date or _latest_component_date(components) or history_date
    parsed_date = pd.to_datetime(observation_date, errors="coerce", format="mixed")
    date_text = (
        "n/a"
        if pd.isna(parsed_date)
        else f"{parsed_date.month}.{parsed_date.day}.{parsed_date.year}"
    )
    if is_archive:
        return "Source", "Archive", date_text
    return "Source", "Live data", f"{live_sources} · {date_text}"


def _render_interpretation_list(title, items, *, empty_text):
    clean = [str(item).strip() for item in (items or []) if str(item).strip()]
    if not clean:
        clean = [empty_text]
    list_html = "".join(
        f'<li>{html.escape(item)}</li>'
        for item in clean[:3]
    )
    st.markdown(
        f"""
        <div class="rm-state-column">
            <div class="rm-state-column-title">{html.escape(title)}</div>
            <ul>{list_html}</ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_weekly_references(references):
    links = []
    for reference in references or []:
        number = int(reference.get("reference_number") or 0)
        label = str(reference.get("source_label") or reference.get("source_name") or "").strip()
        url = str(reference.get("source_url") or "").strip()
        if number <= 0 or not label or not url.startswith("https://"):
            continue
        links.append(
            f'<a href="{html.escape(url, quote=True)}" target="_blank" '
            f'rel="noopener noreferrer">[{number}] {html.escape(label)}</a>'
        )
    if not links:
        return
    st.markdown(
        '<div class="rm-snapshot-references">'
        '<span class="rm-snapshot-references-label">References</span>'
        + '<span class="rm-snapshot-reference-separator"> · </span>'.join(links)
        + '</div>',
        unsafe_allow_html=True,
    )


def _render_macro_interpretation(regime_metrics):
    interpretation = (regime_metrics or {}).get("Macro Interpretation", {}) or {}
    headline = str(interpretation.get("headline") or "Snapshot unavailable")
    confidence = str(interpretation.get("confidence") or "unknown")
    coverage_note = (
        '<div class="rm-state-kicker">Partial source coverage</div>'
        if confidence != "high"
        else ""
    )

    with st.container(border=True):
        state_head_html = (
            '<div class="rm-state-head">'
            f'{coverage_note}'
            f'<div class="rm-state-title">{html.escape(headline)}</div>'
            '</div>'
        )
        st.markdown(state_head_html, unsafe_allow_html=True)
        expansion_col, constraint_col, change_col = st.columns(3)
        with expansion_col:
            _render_interpretation_list(
                "Expansion",
                interpretation.get("expansion_factors", interpretation.get("resilience_factors")),
                empty_text="No material expansion signal is currently available.",
            )
        with constraint_col:
            _render_interpretation_list(
                "Constraints",
                interpretation.get("constraint_factors", interpretation.get("pressure_factors")),
                empty_text="No material constraint is currently active.",
            )
        with change_col:
            _render_interpretation_list(
                "This week",
                interpretation.get("changes"),
                empty_text="No material development this week.",
            )
        _render_weekly_references(interpretation.get("weekly_references"))



def _render_primary_macro_cards(regime_metrics, trends, adaptation_data):
    adaptation_history_frame = history_from_frame(
        (adaptation_data or {}).get("national_history"),
        "Current AI Use",
    )
    adaptation_value = pd.to_numeric(
        (adaptation_data or {}).get("current_use"), errors="coerce"
    )
    specs = [
        (
            "macro-card-aei",
            "AI Equity Index",
            _value(regime_metrics, "AI Equity Index"),
            trends.get("aei_trend", {}).get("history"),
            (0, 100),
            _source(regime_metrics, "AEI"),
            _fallback(regime_metrics, "AEI"),
            "violet",
            _metric_context("AI Equity Index", _value(regime_metrics, "AI Equity Index")),
        ),
        (
            "macro-card-adi",
            "AI Development Intensity",
            _value(regime_metrics, "AI Development Intensity"),
            trends.get("adi_trend", {}).get("history"),
            (0, 100),
            _source(regime_metrics, "ADI"),
            _fallback(regime_metrics, "ADI"),
            "blue",
            _metric_context("AI Development Intensity", _value(regime_metrics, "AI Development Intensity")),
        ),
        (
            "macro-card-power",
            "Power Stress Index",
            _value(regime_metrics, "Power Stress Index"),
            trends.get("power_stress_trend", {}).get("history"),
            (-100, 100),
            _source(regime_metrics, "Power Stress"),
            _fallback(regime_metrics, "Power Stress"),
            "violet",
            _metric_context("Power Stress Index", _value(regime_metrics, "Power Stress Index")),
        ),
        (
            "macro-card-adaptation",
            "Business Adaptation",
            adaptation_value,
            adaptation_history_frame,
            (0, 100),
            str((adaptation_data or {}).get("source") or "Census BTOS"),
            (adaptation_data or {}).get("snapshot_date"),
            "green",
            "Employer businesses reporting current AI use",
        ),
    ]

    for col, spec in zip(st.columns(4), specs):
        key, label, value, history, scale, source, fallback, accent, context = spec
        with col:
            metric_card(
                key=key,
                label=label,
                value=value,
                value_text=fmt_number(value, 1, suffix="%" if label == "Business Adaptation" else ""),
                context=context,
                history=history,
                scale=scale,
                source=source,
                fallback_date=fallback,
                accent=accent,
                reference=0 if scale[0] < 0 else None,
            )


def _render_gap_measures(regime_metrics, fred_data, dashboard_data):
    del dashboard_data

    industrial_growth = _fred_value(fred_data, "Industrial Production YoY")
    industrial_gap = industrial_growth_gap(
        _value(regime_metrics, "AI Development Intensity"),
        industrial_growth,
    )
    gaps = {
        "Speculation Gap": _value(regime_metrics, "Speculation Gap"),
        "Economic Validation Gap": _value(regime_metrics, "Economic Validation Gap"),
        "AI–Industrial Growth Gap": industrial_gap,
        "Power Capacity Gap": _value(regime_metrics, "Power Capacity Gap"),
    }

    with st.container(border=True):
        render_panel_heading("Current divergence")
        chart_col, measures_col = st.columns([1.05, 1.25])
        with chart_col:
            render_panel_heading("", "Centered -100 to +100")
            st.plotly_chart(
                current_gap_bars(gaps),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key="macro-current-divergence-chart",
            )
        with measures_col:
            render_statline(
                [
                    ("Speculation", fmt_number(gaps["Speculation Gap"], 0, signed=True), speculation_label(gaps["Speculation Gap"])),
                    ("Economic Validation", fmt_number(gaps["Economic Validation Gap"], 0, signed=True), validation_label(gaps["Economic Validation Gap"])),
                ],
                key_prefix="macro-current-divergence-primary",
            )
            render_statline(
                [
                    ("Industrial", fmt_number(gaps["AI–Industrial Growth Gap"], 0, signed=True), adoption_label(gaps["AI–Industrial Growth Gap"])),
                    ("Power Capacity", fmt_number(gaps["Power Capacity Gap"], 0, signed=True), power_capacity_gap_label(gaps["Power Capacity Gap"])),
                ],
                key_prefix="macro-current-divergence-context",
            )


def _render_macro_components(regime_metrics, sector_data):
    del sector_data
    adi_result = (regime_metrics or {}).get("ADI Components", {}) or {}
    validation_result = (regime_metrics or {}).get("Economic Validation Gap Components", {}) or {}
    power_result = (regime_metrics or {}).get("Power Stress Components", {}) or {}

    groups = [
        ("macro-adi-components", "ADI pillars", adi_result.get("components", {}), False, COLORS["violet"]),
        ("macro-validation-components", "Economic validation legs", validation_result.get("components", {}), False, COLORS["blue"]),
        ("macro-power-stress-components", "Power-stress components", power_result.get("components", {}), True, COLORS["violet"]),
    ]
    for col, (chart_key, title, components, signed, color) in zip(st.columns(3), groups):
        with col:
            with st.container(border=True):
                render_panel_heading(title)
                st.plotly_chart(
                    component_bars(
                        components,
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


def render_macro_tab(sector_metrics, sector_data, fred_data, regime_metrics, dashboard_data, adaptation_data):
    del sector_metrics
    render_tab_header(
        "AI Macro",
        "Overview of the AI economy using novel metrics to track the evolution.",
        "market / buildout / adaptation / validation",
    )
    render_line_break()
    _render_tab_metric_registry("macro")
    render_section("Snapshot")
    _render_macro_interpretation(regime_metrics)
    render_section("Regime board", "Current readings with retained histories and source state.")
    _render_primary_macro_cards(regime_metrics, dashboard_data["trends"], adaptation_data)
    render_section("Gap Measures", "Approximations of divergence from broader economic trends.")
    _render_gap_measures(regime_metrics, fred_data, dashboard_data)
    render_section("Component evidence", "Structural decomposition of top-level AI economy metrics.")
    _render_macro_components(regime_metrics, sector_data)


def _funding_specs(funding_mix):
    current = (funding_mix or {}).get("current", {}) or {}
    series = (funding_mix or {}).get("series", {}) or {}
    return [
        (
            "finance-ifc",
            "Internal Funding Coverage",
            current.get("internal_funding_coverage"),
            fmt_number(current.get("internal_funding_coverage"), 2, suffix="x"),
            "OCF / CapEx",
            series.get("internal_funding_coverage"),
            (0, 3),
            1,
            "violet",
            f"{current.get('internal_funding_companies', 0)} companies",
        ),
        (
            "finance-crc",
            "Cash Reserve Runway",
            current.get("cash_reserve_coverage_years"),
            fmt_number(current.get("cash_reserve_coverage_years"), 2, suffix="y"),
            "Cash / TTM CapEx",
            series.get("cash_reserve_coverage_years"),
            (0, 5),
            1,
            "blue",
            f"{current.get('cash_reserve_companies', 0)} companies",
        ),
        (
            "finance-dfp",
            "Debt Financing Pulse",
            current.get("debt_financing_pulse"),
            fmt_number(current.get("debt_financing_pulse"), 2, signed=True, suffix="x"),
            "Δ12m debt / TTM CapEx",
            series.get("debt_financing_pulse"),
            (-2, 2),
            0,
            "violet",
            "cohort debt formation",
        ),
        (
            "finance-fcl",
            "Forward Commitment Load",
            current.get("forward_commitment_load"),
            fmt_number(current.get("forward_commitment_load"), 2, suffix="x"),
            "Forward commitments / TTM CapEx",
            series.get("forward_commitment_load"),
            (0, 5),
            1,
            "slate",
            f"{current.get('commitment_companies', 0)} companies",
        ),
    ]


def _render_funding_section(regime_metrics):
    funding_mix = (regime_metrics or {}).get("Deployment Funding Mix", {}) or {}
    for col, spec in zip(st.columns(4), _funding_specs(funding_mix)):
        key, label, value, value_text, context, history, scale, reference, accent, source = spec
        with col:
            metric_card(
                key=key,
                label=label,
                value=value,
                value_text=value_text,
                context=context,
                history=history,
                scale=scale,
                source=source,
                accent=accent,
                reference=reference,
                years=10,
            )

    history = funding_mix.get("history")
    with st.container(border=True):
        render_panel_heading("Funding diagnostics history")
        st.plotly_chart(
            funding_history(history, years=10),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="finance-funding-diagnostics-history",
        )

    current = funding_mix.get("current", {}) or {}
    with st.expander("Funding cohort totals", expanded=False):
        render_statline(
            [
                ("TTM CapEx", _fmt_dollars(current.get("capex_total")), f"{current.get('cohort_companies', 0)} cohort companies"),
                ("Total debt", _fmt_dollars(current.get("total_debt")), "current aggregate"),
                ("Prior-year debt", _fmt_dollars(current.get("prior_year_total_debt")), "comparison base"),
                ("Forward commitments", _fmt_dollars(current.get("forward_commitments_total")), "filing-backed ledger"),
            ],
            key_prefix="finance-funding-cohort-totals",
        )


def _fmt_dollars(value):
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return "n/a"
    magnitude = abs(float(numeric))
    if magnitude >= 1e12:
        return f"${numeric / 1e12:.2f}T"
    if magnitude >= 1e9:
        return f"${numeric / 1e9:.1f}B"
    if magnitude >= 1e6:
        return f"${numeric / 1e6:.1f}M"
    return f"${numeric:,.0f}"



def _render_financial_condition_product(
    *,
    title,
    value,
    source,
    fallback_date,
    trend,
    components,
    detail_table,
    note,
    live_sources,
):
    with st.container(border=True):
        render_panel_heading(title)
        source_stat = _financial_condition_source_stat(
            source=source,
            fallback_date=fallback_date,
            trend=trend,
            components=components,
            live_sources=live_sources,
        )
        render_statline(
            [
                ("Current", fmt_number(value, 1, signed=True), None),
                ("Velocity", fmt_number((trend or {}).get("velocity"), 2, signed=True), None),
                ("Acceleration", fmt_number((trend or {}).get("acceleration"), 2, signed=True), None),
                source_stat,
            ],
            key_prefix=f"finance-condition-{title.lower().replace(' ', '-')}",
        )
        history_col, components_col = st.columns([1.25, 1])
        with history_col:
            st.plotly_chart(
                single_history(
                    (trend or {}).get("history"),
                    color=COLORS["violet"],
                    reference=0,
                    y_range=(-100, 100),
                    height=300,
                    step=True,
                    years=10,
                ),
                width="stretch",
                config={"displayModeBar": True, "responsive": True},
                key=f"finance-{title.lower().replace(' ', '-')}-history",
            )
        with components_col:
            st.plotly_chart(
                component_bars(components, signed=True, height=300),
                width="stretch",
                config={"displayModeBar": True, "responsive": True},
                key=f"finance-{title.lower().replace(' ', '-')}-components",
            )
        st.caption(note)

    with st.expander(f"{title} component detail", expanded=False):
        st.dataframe(arrow_safe_dataframe(detail_table), width="stretch", hide_index=True)


def _debt_market_item(debt_markets_data, name):
    return (((debt_markets_data or {}).get("series", {}) or {}).get(name, {}) or {})


def _render_debt_markets(debt_markets_data):
    cards = [
        (
            "finance-debt-market",
            "Corporate Bond Market Distress",
            "Primary and secondary markets",
            "violet",
        ),
        (
            "finance-debt-ig",
            "Investment-Grade Bond Distress",
            "Investment-grade segment",
            "blue",
        ),
        (
            "finance-debt-hy",
            "High-Yield Bond Distress",
            "High-yield segment",
            "slate",
        ),
    ]
    for column, (key, name, context, accent) in zip(st.columns(3), cards):
        item = _debt_market_item(debt_markets_data, name)
        with column:
            metric_card(
                key=key,
                label=name,
                value=item.get("value"),
                value_text=fmt_number(item.get("value"), 2),
                context=context,
                history=item.get("history"),
                scale=(0, 0.85),
                source=item.get("source", "New York Fed archive"),
                fallback_date=item.get("date"),
                accent=accent,
                years=10,
            )

    with st.container(border=True):
        render_panel_heading("Corporate bond market history")
        st.plotly_chart(
            debt_market_history((debt_markets_data or {}).get("history"), years=10),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="finance-debt-market-history",
        )


def _debt_market_source_rows(debt_markets_data):
    rows = []
    for name, spec in DEBT_MARKET_SERIES.items():
        item = _debt_market_item(debt_markets_data, name)
        rows.append(
            {
                "Series": spec.get("display_name", name),
                "Reading": fmt_number(item.get("value"), 2),
                "Observation Date": fmt_date(item.get("date")),
                "Source": str(item.get("source") or "New York Fed"),
            }
        )
    return pd.DataFrame(rows)


def _render_nfci(fred_data, nfci_history):
    snapshot = nfci_snapshot(fred_data or {}, nfci_history)
    value = snapshot.get("value")
    anfci_value = snapshot.get("anfci_value")
    change = snapshot.get("three_month_change")
    paired_value = f"{fmt_number(value, 3, signed=True)} / {fmt_number(anfci_value, 3, signed=True)}"
    with st.container(border=True):
        render_panel_heading("Financial Conditions Confirmation")
        render_statline(
            [
                ("NFCI/ANFCI", paired_value, "headline / macro-adjusted"),
                ("3-month change", fmt_number(change, 3, signed=True), nfci_direction(change)),
                ("Observation", fmt_date(snapshot.get("as_of")), snapshot.get("source", "FRED")),
                ("Source", "Chicago Fed NFCI", "updated Wednesday at 8:30am ET"),
            ],
            key_prefix="finance-nfci-confirmation",
        )
        st.plotly_chart(
            financial_conditions_history(snapshot.get("history"), height=275),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="finance-nfci-history",
        )


def render_finance_tab(sector_metrics, sector_data, fred_data, regime_metrics, nfci_history, debt_markets_data, dashboard_data):
    del sector_metrics, sector_data
    render_tab_header(
        "Finance",
        "Funding capacity, contractual burden, borrower strain, lender strain, and broad financial conditions.",
        "funding / borrowers / lenders / system",
    )
    render_line_break()
    _render_tab_metric_registry("finance")
    render_section("Funding profile", "Current funding ratios and retained cohort history.")
    _render_funding_section(regime_metrics)

    render_section("Debt Markets")
    _render_debt_markets(debt_markets_data)

    render_section("Credit Conditions")
    render_line_break()
    borrower_strain = (regime_metrics or {}).get("Borrower Strain Components", {}) or {}
    _render_financial_condition_product(
        title="Borrower Strain",
        value=_value(regime_metrics, "Borrower Strain"),
        source=_source(regime_metrics, "Borrower Strain"),
        fallback_date=_fallback(regime_metrics, "Borrower Strain"),
        trend=dashboard_data["trends"].get("borrower_strain_trend", {}),
        components=borrower_strain.get("components", {}),
        detail_table=_borrower_strain_component_table(borrower_strain),
        note="Cash-flow and debt-capacity strain combined with disclosed commitments and contingent exposure.",
        live_sources="yfinance + EDGAR",
    )

    lender_strain = (regime_metrics or {}).get("Lender Strain Components", {}) or {}
    _render_financial_condition_product(
        title="Lender Strain",
        value=_value(regime_metrics, "Lender Strain"),
        source=_source(regime_metrics, "Lender Strain"),
        fallback_date=_fallback(regime_metrics, "Lender Strain"),
        trend=dashboard_data["trends"].get("lender_strain_trend", {}),
        components=lender_strain.get("components", {}),
        detail_table=_lender_strain_component_table(lender_strain),
        note=(
            f"Bank channel {fmt_number(lender_strain.get('bank_channel_score'), 1, signed=True)} · "
            f"Nonbank channel {fmt_number(lender_strain.get('nonbank_channel_score'), 1, signed=True)} · "
            f"{lender_strain.get('elevated_pillars', 0)} of 4 pillars above neutral."
        ),
        live_sources="FRED + EDGAR",
    )

    _render_nfci(fred_data, nfci_history)




def _infrastructure_item(infrastructure_data, name):
    return (((infrastructure_data or {}).get("series", {}) or {}).get(name, {}) or {})


def _construction_value_text(item):
    value = pd.to_numeric((item or {}).get("value"), errors="coerce")
    return "n/a" if pd.isna(value) else f"${value / 1000.0:,.1f}B"


def _construction_change_text(item):
    growth = pd.to_numeric((item or {}).get("yoy_growth"), errors="coerce")
    return "year over year n/a" if pd.isna(growth) else f"{growth * 100:+.1f}% year over year"


def _infrastructure_source_rows(infrastructure_data):
    rows = []
    for name, item in ((infrastructure_data or {}).get("series", {}) or {}).items():
        rows.append({
            "Series": name,
            "Reading": _construction_value_text(item),
            "Change": _construction_change_text(item),
            "Observation Date": fmt_date(item.get("date")),
            "Source": str(item.get("source") or (infrastructure_data or {}).get("construction_source") or "Census"),
        })
    coverage = (infrastructure_data or {}).get("facility_coverage", {}) or {}
    rows.append({
        "Series": "Evidence-Graded Facility Registry",
        "Reading": f"{int(coverage.get('records', 0) or 0):,} records",
        "Change": f"{int(coverage.get('verified_project_records', 0) or 0):,} curated project records",
        "Observation Date": "varies by source",
        "Source": str((infrastructure_data or {}).get("map_source") or "IM3") + " + curated primary evidence",
    })
    return pd.DataFrame(rows)


def _render_infrastructure_summary(infrastructure_data):
    data_centers = _infrastructure_item(infrastructure_data, "Data Center Construction")
    manufacturing = _infrastructure_item(
        infrastructure_data,
        "Computer, Electronic & Electrical Manufacturing Construction",
    )
    coverage = (infrastructure_data or {}).get("facility_coverage", {}) or {}
    records = int(coverage.get("records", 0) or 0)
    states = int(coverage.get("states", 0) or 0)
    verified = int(coverage.get("verified_project_records", 0) or 0)
    render_statline(
        [
            ("Data-center construction", _construction_value_text(data_centers), _construction_change_text(data_centers)),
            ("compute/electrical", _construction_value_text(manufacturing), _construction_change_text(manufacturing)),
            ("Facility registry", f"{records:,}" if records else "n/a", f"{states} states · {verified} curated projects" if records else "registry unavailable"),
            ("Observation", fmt_date(data_centers.get("date")), str((infrastructure_data or {}).get("construction_source") or "Census")),
        ],
        key_prefix="infrastructure-summary",
    )


def _facility_metric_coverage(infrastructure_data, metric_label):
    field = FACILITY_SIZE_METRICS.get(metric_label)
    coverage = (infrastructure_data or {}).get("facility_coverage", {}) or {}
    total = int(coverage.get("records", 0) or 0)
    if field is None:
        return total, total
    item = ((coverage.get("fields", {}) or {}).get(field, {}) or {})
    return int(item.get("records", 0) or 0), int(item.get("total", total) or total)


def _facility_table(registry: pd.DataFrame, size_by: str) -> pd.DataFrame:
    if not isinstance(registry, pd.DataFrame) or registry.empty:
        return pd.DataFrame()
    metric = FACILITY_SIZE_METRICS.get(size_by)
    columns = [
        "Facility", "Operator", "State", "County", "Status", "Location Precision",
        "Square Feet", "Planned Data Center Capacity MW", "Contracted Utility Capacity MW",
        "Energized Capacity MW", "Annual Electricity Consumption MWh",
        "Planned Onsite Generation MW", "Water Withdrawal Gallons/Year",
        "Water Consumption Gallons/Year", "Site WUE L/kWh", "Cooling System",
        "Water Source", "Evidence Grade", "Evidence Type", "Source Date", "Source",
    ]
    available = [column for column in columns if column in registry.columns]
    table = registry[available].copy()
    if metric and metric in table.columns:
        table[metric] = pd.to_numeric(table[metric], errors="coerce")
        table = table.sort_values(metric, ascending=False, na_position="last", kind="stable")
    else:
        table = table.sort_values([column for column in ["State", "Facility"] if column in table.columns], kind="stable")
    for column in ["Source Date"]:
        if column in table.columns:
            table[column] = pd.to_datetime(table[column], errors="coerce", format="mixed").dt.date.astype("string").fillna("")
    return table.reset_index(drop=True)


def _render_data_center_footprint(infrastructure_data):
    registry = (infrastructure_data or {}).get("facility_registry")
    if registry is None or not isinstance(registry, pd.DataFrame):
        registry = (infrastructure_data or {}).get("locations")
    source = str((infrastructure_data or {}).get("map_source") or "IM3")
    size_options = list(FACILITY_SIZE_METRICS)
    size_by = st.selectbox(
        "Bubble size",
        size_options,
        index=size_options.index("Square feet"),
        key="infrastructure-facility-size-by",
    )
    valid, total = _facility_metric_coverage(infrastructure_data, size_by)

    with st.container(border=True):
        render_panel_heading("Data Center Registry", f"metric coverage: {valid:,}/{total:,} facility records")
        if registry is None or not isinstance(registry, pd.DataFrame) or registry.empty:
            st.caption("The facility registry is unavailable. Live source records are cached after a successful refresh.")
        else:
            st.plotly_chart(
                data_center_map(registry, size_by=size_by),
                width="stretch",
                config={"displayModeBar": True, "responsive": True},
                key="infrastructure-data-center-map",
            )
        st.caption(
            "Outlined markers remain visible when the selected metric is unavailable. "
            f"Base footprint: {source}; curated project records use explicit primary evidence. Records do not establish AI-specific use, compute output, or undisclosed operating demand."
        )

    if isinstance(registry, pd.DataFrame) and not registry.empty:
        with st.expander("Facility evidence table", expanded=False):
            render_static_table(_facility_table(registry, size_by))


def _render_infrastructure_construction(infrastructure_data):
    history = (infrastructure_data or {}).get("construction_history")
    with st.container(border=True):
        render_panel_heading("AI-linked buildout measures", "seasonally adjusted annual rate")
        st.plotly_chart(
            infrastructure_construction_history(history),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="infrastructure-core-construction-history",
        )
        st.caption(
            "Data-center construction is reported separately from the broader computer, electronic, and electrical manufacturing category. "
            "The manufacturing series includes semiconductor-fab construction but is not semiconductor-exclusive."
        )


def _render_supporting_infrastructure(infrastructure_data):
    history = (infrastructure_data or {}).get("construction_history")
    names = [
        "Communication Construction",
        "Public Highway and Street Construction",
        "Public Transportation Construction",
        "Public Water Supply Construction",
    ]
    stats = []
    for name in names:
        item = _infrastructure_item(infrastructure_data, name)
        stats.append((name.replace(" Construction", ""), _construction_value_text(item), _construction_change_text(item)))
    render_statline(stats, key_prefix="infrastructure-supporting")
    with st.container(border=True):
        render_panel_heading("US Infrastructure Expenditure")
        st.plotly_chart(
            supporting_construction_history(history),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="infrastructure-supporting-history",
        )
        st.caption(
            "These are full national construction series. The platform does not estimate an AI-attributable share, and proximity or correlation must not be read as causation. "
            "Public water-supply construction is capital spending on water infrastructure, not data-center water withdrawal or consumption."
        )



def render_infrastructure_tab(infrastructure_data):
    render_tab_header(
        "Infrastructure",
        "Physical AI buildout, evidence-graded facility capacity, and supporting infrastructure expenditure.",
        "construction / facilities / infrastructure expenditure",
    )
    render_line_break()
    _render_tab_metric_registry("infrastructure")
    render_section("Buildout", "Current construction scale and evidence-graded facility coverage.")
    _render_infrastructure_summary(infrastructure_data)
    _render_infrastructure_construction(infrastructure_data)

    render_section("Facility registry", "Observed locations and verified projects, with homogeneous bubble sizing and explicit unknowns.")
    _render_data_center_footprint(infrastructure_data)


    render_section(
        "US Infrastructure Expenditure",
        "National-level communication, transport, and public water-supply construction expenditures",
    )
    _render_supporting_infrastructure(infrastructure_data)


def _adaptation_source_rows(adaptation_data):
    national = (adaptation_data or {}).get("national_history")
    rows = []
    if isinstance(national, pd.DataFrame) and not national.empty:
        latest = national.sort_values("Date").iloc[-1]
        for name, display_name in [
            ("Current AI Use", "Current AI Use"),
            ("Expected AI Use", "Expected AI Use"),
            ("Expected Adoption Gap", "Expected Adoption Gap"),
        ]:
            rows.append({
                "Series": display_name,
                "Reading": fmt_number(latest.get(name), 1, suffix=" percentage points" if name == "Expected Adoption Gap" else "%"),
                "Observation Date": fmt_date(latest.get("Date")),
                "Source": str((adaptation_data or {}).get("source") or "Census BTOS"),
            })
    return pd.DataFrame(rows)


def _render_adaptation_summary(adaptation_data):
    current = pd.to_numeric((adaptation_data or {}).get("current_use"), errors="coerce")
    expected = pd.to_numeric((adaptation_data or {}).get("expected_use"), errors="coerce")
    expected_gap = pd.to_numeric((adaptation_data or {}).get("expected_adoption_gap"), errors="coerce")
    annual = pd.to_numeric((adaptation_data or {}).get("annual_change"), errors="coerce")
    render_statline(
        [
            ("Current business use", fmt_number(current, 1, suffix="%"), "used AI in any business function"),
            ("Expected use", fmt_number(expected, 1, suffix="%"), "expected within six months"),
            ("Expected adoption gap", fmt_number(expected_gap, 1, signed=True, suffix=" pp"), "expected minus current use"),
            ("12-month change", fmt_number(annual, 1, signed=True, suffix=" pp"), fmt_date((adaptation_data or {}).get("snapshot_date"))),
        ],
        key_prefix="adaptation-summary",
    )


def render_adaptation_tab(adaptation_data):
    render_tab_header(
        "Adaptation",
        "Observed business AI use, expected near-term adoption, and the breadth of integration across the US economy.",
        "use / diffusion / breadth",
    )
    render_line_break()
    _render_tab_metric_registry("adaptation")
    render_section("Business adoption", "Observed use and expected use within the next six months.")
    _render_adaptation_summary(adaptation_data)
    with st.container(border=True):
        render_panel_heading("AI use trajectory", "Census BTOS / employer businesses / 95% confidence intervals")
        st.plotly_chart(
            adaptation_history((adaptation_data or {}).get("national_history")),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="adaptation-national-history",
        )
        st.caption("Error bars are estimate ± 1.96 standard errors. They reflect reported sampling error, not systematic error or model uncertainty.")

    render_section("Adoption breadth", "Current and expected use across major industries.")
    with st.container(border=True):
        render_panel_heading("Highest-use sectors", "latest published observation / 95% confidence intervals")
        st.plotly_chart(
            adaptation_sector_bars((adaptation_data or {}).get("sector_snapshot")),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="adaptation-sector-breadth",
        )
        st.caption(
            "Sector estimates are survey observations with sampling error. Suppressed values are omitted; small differences should not be overinterpreted. "
            "No confidence interval is shown for expected use minus current use because the covariance between the paired estimates is not available in the retained contract."
        )

    render_section("Measurement boundary")
    with st.container(border=True):
        st.markdown(
            "This view measures **adoption**, not realized productivity, return on investment, labor displacement, or institutional adaptation. Those outcomes require separate measurements and will not be inferred from AI use alone."
        )

def _energy_item(energy_data, name):
    return (((energy_data or {}).get("series", {}) or {}).get(name, {}) or {})


def _energy_source_label(energy_data):
    mode = str((energy_data or {}).get("source_mode", ""))
    if mode.startswith("live"):
        return "Live data"
    if mode == "unavailable":
        return "Unavailable"
    return "Archive"


def _energy_source_rows(energy_data):
    """Return the Energy source observations shown in the Evidence tab."""
    rows = []
    for name, spec in ENERGY_SERIES.items():
        item = _energy_item(energy_data, name)
        value = pd.to_numeric(item.get("value"), errors="coerce")
        change = pd.to_numeric(item.get("change_pct"), errors="coerce")
        unit = str(item.get("unit") or spec.get("unit") or "")

        if unit.startswith("$"):
            reading = f"${fmt_number(value, 2)}"
        elif unit == "%":
            reading = fmt_number(value, 1, suffix="%")
        elif unit == "¢/kWh":
            reading = fmt_number(value, 2, suffix="¢/kWh")
        else:
            reading = fmt_number(value, 1)

        if spec.get("change_days"):
            change_period = "4-week"
        elif int(spec.get("change_months") or 0) == 3:
            change_period = "3-month"
        else:
            change_period = "12-month"

        rows.append(
            {
                "Series": spec.get("display_name", name),
                "Reading": reading,
                "Change": f"{change_period} {fmt_number(change, 1, signed=True, suffix='%')}",
                "Observation Date": fmt_date(item.get("date")),
                "Source": str(item.get("source") or _energy_source_label(energy_data)),
            }
        )
    return pd.DataFrame(rows)


def _energy_change_text(item, period):
    change = pd.to_numeric((item or {}).get("change_pct"), errors="coerce")
    return f"{period} {fmt_number(change, 1, signed=True, suffix='%')}"


def _year_over_year_history(item):
    """Convert a monthly level history to exact 12-month percentage changes."""
    history = (item or {}).get("history")
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        return pd.DataFrame(columns=["Date", "Value"])
    if not {"Date", "Value"}.issubset(history.columns):
        return pd.DataFrame(columns=["Date", "Value"])

    clean = history[["Date", "Value"]].copy()
    clean["Date"] = pd.to_datetime(clean["Date"], errors="coerce", format="mixed")
    clean["Value"] = pd.to_numeric(clean["Value"], errors="coerce")
    clean = (
        clean.dropna(subset=["Date", "Value"])
        .sort_values("Date", kind="stable")
        .drop_duplicates("Date", keep="last")
    )
    if clean.empty:
        return pd.DataFrame(columns=["Date", "Value"])

    monthly = clean.set_index(clean["Date"].dt.to_period("M"))["Value"]
    growth = monthly.pct_change(periods=12, fill_method=None) * 100.0
    output = pd.DataFrame(
        {
            "Date": growth.index.to_timestamp(),
            "Value": growth.to_numpy(dtype=float),
        }
    )
    return output.replace([np.inf, -np.inf], np.nan).dropna(subset=["Value"])


def _render_energy_supply(energy_data):
    specs = [
        ("energy-gas", "Natural Gas Price", "Henry Hub Natural Gas", (0, 15), "violet", "4-week change"),
        ("energy-oil", "WTI Crude Oil", "WTI Crude Oil", (20, 160), "blue", "4-week change"),
        ("energy-coal", "Coal Production", "Coal Production", (40, 140), "slate", "3-month change"),
        ("energy-renewables", "Renewable Power Output", "Renewable Power Output", (50, 300), "green", "3-month change"),
    ]
    source = _energy_source_label(energy_data)
    for column, (key, series_name, label, scale, accent, period) in zip(st.columns(4), specs):
        item = _energy_item(energy_data, series_name)
        value = pd.to_numeric(item.get("value"), errors="coerce")
        if series_name in {"Natural Gas Price", "WTI Crude Oil"}:
            value_text = f"${fmt_number(value, 2)}"
        else:
            value_text = fmt_number(value, 1)
        with column:
            metric_card(
                key=key,
                label=label,
                value=value,
                value_text=value_text,
                context=_energy_change_text(item, period),
                history=item.get("history"),
                scale=scale,
                source=source,
                fallback_date=item.get("date"),
                accent=accent,
                years=6,
            )


def _render_electricity_cost(energy_data):
    commercial = _energy_item(energy_data, "Commercial Electricity Price")
    industrial = _energy_item(energy_data, "Industrial Electricity Price")
    with st.container(border=True):
        render_statline(
            [
                (
                    "Commercial price",
                    fmt_number(commercial.get("value"), 2, suffix="¢/kWh"),
                    _energy_change_text(commercial, "12-month change"),
                ),
                (
                    "Industrial price",
                    fmt_number(industrial.get("value"), 2, suffix="¢/kWh"),
                    _energy_change_text(industrial, "12-month change"),
                ),
            ],
            key_prefix="energy-electricity-cost",
        )
        render_panel_heading("US Retail Electricity Prices", "Commercial and industrial customer classes")
        st.plotly_chart(
            dual_history(
                commercial.get("history"),
                industrial.get("history"),
                first_name="Commercial",
                second_name="Industrial",
                first_color=COLORS["violet"],
                second_color=COLORS["blue"],
                years=8,
                height=330,
                value_suffix="¢/kWh",
            ),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="energy-electricity-cost-history",
        )
        st.markdown(
            '<div class="rm-chart-note">National commercial and industrial averages provide '
            'electricity-cost context; they do not represent contracted data-center rates.</div>',
            unsafe_allow_html=True,
        )


def _render_power_production(energy_data, regime_metrics):
    output = _energy_item(energy_data, "Electric Power Output")
    capacity = _energy_item(energy_data, "Electric Power Capacity")
    utilization = _energy_item(energy_data, "Electric Power Utilization")
    with st.container(border=True):
        render_statline(
            [
                ("Output index", fmt_number(output.get("value"), 1), _energy_change_text(output, "12-month change")),
                ("Capacity index", fmt_number(capacity.get("value"), 1), _energy_change_text(capacity, "12-month change")),
                ("Utilization", fmt_number(utilization.get("value"), 1, suffix="%"), _energy_change_text(utilization, "12-month change")),
                ("Power Stress", fmt_number(_value(regime_metrics, "Power Stress Index"), 1, signed=True), _metric_context("Power Stress Index", _value(regime_metrics, "Power Stress Index"))),
            ],
            key_prefix="energy-power-production",
        )
        st.plotly_chart(
            dual_history(
                output.get("history"),
                capacity.get("history"),
                first_name="Electric power output",
                second_name="Electric power capacity",
                first_color=COLORS["violet"],
                second_color=COLORS["blue"],
                years=8,
                height=330,
            ),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="energy-power-production-history",
        )


def _render_grid_capacity(regime_metrics, dashboard_data, energy_data):
    value = _value(regime_metrics, "Power Capacity Gap")
    result = (regime_metrics or {}).get("Power Capacity Gap Components", {}) or {}
    components = result.get("components", {}) or {}

    output_component = components.get("Delivered Power Growth", {}) or {}
    capacity_component = components.get("Installed Capacity Growth", {}) or {}
    output_growth = pd.to_numeric(output_component.get("raw"), errors="coerce") * 100.0
    capacity_growth = pd.to_numeric(capacity_component.get("raw"), errors="coerce") * 100.0
    utilization = pd.to_numeric(
        _energy_item(energy_data, "Electric Power Utilization").get("value"),
        errors="coerce",
    )

    del dashboard_data
    render_statline(
        [
            (
                "Power Capacity Gap",
                fmt_number(value, 1, signed=True),
                power_capacity_gap_label(value),
            ),
            (
                "Output growth",
                fmt_number(output_growth, 1, signed=True, suffix="%"),
                "12-month",
            ),
            (
                "Capacity growth",
                fmt_number(capacity_growth, 1, signed=True, suffix="%"),
                "12-month",
            ),
            (
                "Capacity utilization",
                fmt_number(utilization, 1, suffix="%"),
                "current",
            ),
        ],
        key_prefix="energy-grid-capacity",
    )

    output_history = _year_over_year_history(
        _energy_item(energy_data, "Electric Power Output")
    )
    capacity_history = _year_over_year_history(
        _energy_item(energy_data, "Electric Power Capacity")
    )
    with st.container(border=True):
        render_panel_heading("Power-system response", "12-month change")
        st.plotly_chart(
            dual_history(
                output_history,
                capacity_history,
                first_name="Electric power output",
                second_name="Installed power capacity",
                first_color=COLORS["violet"],
                second_color=COLORS["blue"],
                reference=0,
                years=8,
                height=310,
                value_suffix="%",
            ),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="energy-grid-capacity-growth",
        )


def _render_ai_energy_demand(regime_metrics):
    capacity_result = (regime_metrics or {}).get("Power Capacity Gap Components", {}) or {}
    capacity_components = capacity_result.get("components", {}) or {}
    power_result = (regime_metrics or {}).get("Power Stress Components", {}) or {}
    footprint_components = power_result.get("footprint_components", {}) or {}
    demand_components = {
        name: payload
        for name, payload in capacity_components.items()
        if (payload or {}).get("channel") == "Deployment Pressure"
    }
    demand_components.update(footprint_components)

    construction = demand_components.get("Data Center Construction", {}) or {}
    deployment = demand_components.get("Capital Deployment", {}) or {}
    commercial = demand_components.get("Commercial Load Growth", {}) or {}
    footprint = pd.to_numeric(power_result.get("footprint_score"), errors="coerce")
    render_statline(
        [
            ("Data-center construction", fmt_number(construction.get("score"), 1), "normalized activity"),
            ("Capital deployment", fmt_number(deployment.get("score"), 1), "normalized CapEx growth"),
            ("Commercial load growth", fmt_number(pd.to_numeric(commercial.get("raw"), errors="coerce") * 100, 1, signed=True, suffix="%"), "year over year"),
            ("Power footprint", fmt_number(footprint, 1), "ADI demand pillar"),
        ],
        key_prefix="energy-ai-demand",
    )
    with st.container(border=True):
        render_panel_heading("Demand indicators", "Normalized 0–100")
        st.plotly_chart(
            component_bars(demand_components, signed=False, height=300, color=COLORS["violet"]),
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
            key="energy-ai-demand-indicators",
        )

def render_energy_tab(fred_data, regime_metrics, energy_data, dashboard_data):
    del fred_data
    render_tab_header(
        "Energy",
        "Fuel supply, electricity cost, power production, grid capacity, and AI-linked demand.",
        "weekly / cost / power / grid",
    )
    render_line_break()
    _render_tab_metric_registry("energy")
    render_section("Energy supply", "Current fuel prices and production momentum.")
    _render_energy_supply(energy_data)

    render_section("Electricity cost", "Average retail prices paid by commercial and industrial customers.")
    _render_electricity_cost(energy_data)

    render_section("Power production", "Electric-power output, capacity, utilization, and system pressure.")
    _render_power_production(energy_data, regime_metrics)

    render_section("Grid capacity", "Delivered power and installed capacity relative to deployment pressure.")
    _render_grid_capacity(regime_metrics, dashboard_data, energy_data)

    render_section("AI energy demand", "Construction, capital deployment, and commercial-load evidence.")
    _render_ai_energy_demand(regime_metrics)

def _assessment_stats(macro_df, sector_data):
    selections = select_current_sector_assessment(macro_df, sector_data=sector_data)
    rows = selections.get("rows", {})
    stats = []
    for label in ("Most Crowded", "Fastest Mover", "Biggest Risk"):
        row = rows.get(label)
        if row is None:
            stats.append((label, "n/a", "insufficient eligible data"))
            continue
        sector = sector_display_name(row.get("Sector"))
        if label == "Most Crowded":
            note = f"Pressure {fmt_number(row.get('Pressure'), 0)}"
        elif label == "Fastest Mover":
            delta_score = pd.to_numeric(row.get('_Delta Sector Score'), errors='coerce')
            signed_move = pd.to_numeric(row.get('_Abs Sector Movement'), errors='coerce')
            if pd.notna(delta_score) and pd.notna(signed_move):
                signed_move = signed_move if delta_score >= 0 else -signed_move
            note = f"Movement {fmt_number(signed_move, 1, signed=True)}"
        else:
            note = f"Deterioration breadth {fmt_number(row.get('Risk Breadth Score'), 0)}%"
        stats.append((label, sector, note))

    concentration = None
    required = {
        "Sector", "Sector Basket Concentration", "Sector Raw HHI",
        "Sector Effective Firms", "Sector Concentration Company Count",
        "Sector Concentration Coverage",
    }
    if macro_df is not None and not macro_df.empty and required.issubset(macro_df.columns):
        frame = macro_df[list(required)].copy()
        for column in required - {"Sector"}:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.loc[
            frame["Sector Basket Concentration"].notna()
            & frame["Sector Concentration Company Count"].ge(3)
            & frame["Sector Concentration Coverage"].ge(0.60)
        ]
        if not frame.empty:
            concentration = frame.loc[frame["Sector Basket Concentration"].idxmax()]

    if concentration is None:
        stats.append(("Most Concentrated", "n/a", "insufficient market-cap coverage"))
    else:
        note = f"Adjusted HHI {fmt_number(concentration.get('Sector Basket Concentration'), 1)}"
        stats.append((
            "Most Concentrated",
            sector_display_name(concentration.get("Sector")),
            note,
        ))
    return stats


def _rank_text(macro_df: pd.DataFrame, sector: str, column: str, *, ascending=False) -> str:
    if macro_df is None or macro_df.empty or column not in macro_df.columns or 'Sector' not in macro_df.columns:
        return "Rank n/a"
    frame = macro_df[['Sector', column]].copy()
    frame[column] = pd.to_numeric(frame[column], errors='coerce')
    frame = frame.dropna(subset=[column])
    if frame.empty:
        return "Rank n/a"
    frame = frame.sort_values(column, ascending=ascending, kind='stable').reset_index(drop=True)
    frame['Rank'] = np.arange(1, len(frame) + 1)
    row = frame.loc[frame['Sector'].astype(str) == str(sector)]
    if row.empty:
        return f"Rank n/a/{len(frame)}"
    rank = int(row.iloc[0]['Rank'])
    return f"Rank {rank}/{len(frame)}"


def _pressure_movement_text(macro_df: pd.DataFrame, sector: str) -> str:
    movement_df = select_current_sector_assessment(macro_df, sector_data={}).get('movement', pd.DataFrame())
    if movement_df is None or movement_df.empty or 'Sector' not in movement_df.columns:
        return 'Static'
    row = movement_df.loc[movement_df['Sector'].astype(str) == str(sector)]
    if row.empty:
        return 'Static'
    delta = pd.to_numeric(row.iloc[0].get('Delta Pressure'), errors='coerce')
    if pd.isna(delta):
        return 'Static'
    if delta > 1.0:
        return 'Expanding'
    if delta < -1.0:
        return 'Shrinking'
    return 'Static'


def _sector_table(macro_df):
    required = [
        "Sector",
        "Sector Score",
        "Pressure",
        "Avg Return",
        "Forward EV/EBIT",
        "Forward EV/EBIT Status",
        "Forward EV/EBIT Data Coverage",
        "Loss-Making EV Share",
        "Sector Basket Concentration",
        "Sector Effective Firms",
        "Sector Concentration Company Count",
        "Sector Concentration Coverage",
        "Beta",
    ]
    available = [column for column in required if column in macro_df.columns]
    table = macro_df[available].copy()
    table["Sector"] = table["Sector"].apply(sector_display_name)
    table = table.rename(columns={"Sector Score": "AEI", "Avg Return": "1Y Return"})
    for column in ["AEI", "Pressure", "Sector Basket Concentration", "Sector Effective Firms", "Beta"]:
        if column in table.columns:
            table[column] = pd.to_numeric(table[column], errors="coerce")
    if "1Y Return" in table.columns:
        table["1Y Return"] = pd.to_numeric(table["1Y Return"], errors="coerce")
    if "Sector Concentration Coverage" in table.columns:
        table["Sector Concentration Coverage"] = (
            pd.to_numeric(table["Sector Concentration Coverage"], errors="coerce") * 100.0
        ).round(1)
        table = table.rename(columns={"Sector Concentration Coverage": "Concentration Coverage (%)"})
    if "Forward EV/EBIT Data Coverage" in table.columns:
        table["Forward EV/EBIT Data Coverage"] = (
            pd.to_numeric(table["Forward EV/EBIT Data Coverage"], errors="coerce") * 100.0
        ).round(1)
        table = table.rename(columns={"Forward EV/EBIT Data Coverage": "FWD EBIT Data Coverage (%)"})
    if "Loss-Making EV Share" in table.columns:
        table["Loss-Making EV Share"] = (
            pd.to_numeric(table["Loss-Making EV Share"], errors="coerce") * 100.0
        ).round(1)
        table = table.rename(columns={"Loss-Making EV Share": "Loss-Making EV Share (%)"})
    if "Forward EV/EBIT" in table.columns:
        statuses = table.get("Forward EV/EBIT Status", pd.Series("", index=table.index))
        table["Forward EV/EBIT"] = [
            _forward_multiple_text(value, status)
            for value, status in zip(table["Forward EV/EBIT"], statuses)
        ]
    table = table.drop(columns=["Forward EV/EBIT Status"], errors="ignore")
    return table.sort_values("AEI", ascending=False, na_position="last")


def _render_sector_detail(sector_data, sector_metrics, macro_df):
    sectors = [
        sector for sector in sector_metrics
        if sector in sector_data and sector_data[sector] is not None and not sector_data[sector].empty
    ]
    if not sectors:
        st.warning("No sector detail is available.")
        return

    selected = st.selectbox(
        "Sector",
        sectors,
        format_func=sector_display_name,
        key="research-overlay-sector",
    )
    metrics = sector_metrics[selected]
    df = sector_data[selected]
    strategy = metrics.get("Cycle Strategy", {}) or {}
    pressure_note = _pressure_movement_text(macro_df, selected)
    return_rank = _rank_text(macro_df, selected, "Avg Return", ascending=False)
    multiple_rank = _rank_text(macro_df, selected, "Forward EV/EBIT", ascending=False)
    render_statline(
        [
            ("Sector AEI", fmt_number(metrics.get("Sector Score"), 1), strategy.get("regime", "n/a")),
            ("Trading Pressure", fmt_number(metrics.get("Sector Pressure"), 1), pressure_note),
            ("1Y Return", fmt_number(pd.to_numeric(metrics.get("Avg Return"), errors="coerce") * 100, 1, signed=True, suffix="%"), return_rank),
            (
                "FWD EV/EBIT",
                _forward_multiple_text(
                    metrics.get("Forward EV/EBIT"),
                    metrics.get("Forward EV/EBIT Status"),
                ),
                multiple_rank,
            ),
        ],
        key_prefix="sector-dossier-summary-primary",
    )
    render_statline(
        [
            (
                "Loss-Making EV Share",
                fmt_number(pd.to_numeric(metrics.get("Loss-Making EV Share"), errors="coerce") * 100, 1, suffix="%"),
                f"{int(metrics.get('Loss-Making Company Count', 0) or 0)} companies with non-positive forward EBIT",
            ),
            (
                "Basket Concentration",
                fmt_number(metrics.get("Sector Basket Concentration"), 1),
                f"Adjusted HHI · {int(metrics.get('Sector Concentration Company Count', 0) or 0)} valid firms · effective firms {fmt_number(metrics.get('Sector Effective Firms'), 1)}",
                "Adjusted HHI controls for different sector-basket sizes. 0 is equal-weighted; 100 is single-company concentration.",
            ),
        ],
        key_prefix="sector-dossier-summary-structure",
    )

    factors_col, pressure_col = st.columns(2)
    with factors_col:
        with st.container(border=True):
            render_panel_heading("AEI factor structure", "Normalized 0–100 · raw values on hover")
            factor_frame = metrics.get("Scored Factors", pd.DataFrame()).copy()
            if not factor_frame.empty and "Factor" in factor_frame.columns:
                factor_frame["Factor"] = factor_frame["Factor"].map(
                    lambda name: FACTOR_DISPLAY_NAMES.get(name, str(name).replace("_", " ").title())
                )
            st.plotly_chart(
                sector_factor_chart(factor_frame),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key="sector-detail-aei-factor-structure",
            )
    with pressure_col:
        with st.container(border=True):
            render_panel_heading("Trading-pressure structure")
            st.plotly_chart(
                pressure_component_chart(metrics.get("Pressure Components", pd.DataFrame())),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key="sector-detail-trading-pressure-structure",
            )

    st.markdown("<br>", unsafe_allow_html=True)
    render_panel_heading(f"{sector_display_name(selected)} companies", f"{len(df)} observations")
    st.dataframe(arrow_safe_dataframe(_company_table(df)), width="stretch", hide_index=True, height=440)

    render_ticker_controls(selected)

    with st.expander("Factor and pressure data", expanded=False):
        st.markdown("**AEI factors**")
        st.dataframe(arrow_safe_dataframe(metrics.get("Scored Factors", pd.DataFrame())), width="stretch", hide_index=True)
        st.markdown("**Trading-pressure components**")
        st.dataframe(arrow_safe_dataframe(metrics.get("Pressure Components", pd.DataFrame())), width="stretch", hide_index=True)
        st.markdown("**Basket-concentration contributors**")
        concentration_table = sector_hhi_component_breakdown(df, top_n=8)
        if not concentration_table.empty:
            concentration_table["Market Cap Share"] = (concentration_table["Market Cap Share"] * 100.0).round(2)
            concentration_table["HHI Contribution Share"] = concentration_table["HHI Contribution Share"].round(2)
            concentration_table = concentration_table.rename(columns={
                "Market Cap Share": "Market Cap Share (%)",
                "HHI Contribution Share": "Share of HHI (%)",
            })
        st.dataframe(arrow_safe_dataframe(concentration_table), width="stretch", hide_index=True)


def _market_universe_label(summary, macro_df):
    summary = summary or {}
    loaded_sectors = int(summary.get("loaded_sectors", len(macro_df)) or 0)
    configured_sectors = int(summary.get("configured_sectors", loaded_sectors) or loaded_sectors)
    loaded_tickers = int(summary.get("loaded_tickers", 0) or 0)
    configured_tickers = int(summary.get("configured_tickers", loaded_tickers) or loaded_tickers)
    sector_text = (
        f"{loaded_sectors} sectors"
        if loaded_sectors == configured_sectors
        else f"{loaded_sectors} of {configured_sectors} sectors"
    )
    ticker_text = (
        f"{loaded_tickers} tickers loaded"
        if loaded_tickers == configured_tickers
        else f"{loaded_tickers} of {configured_tickers} tickers loaded"
    )
    return f"{sector_text} / {ticker_text}"


def render_market_tab(sector_metrics, sector_data, regime_metrics, dashboard_data, market_universe_summary=None):
    del regime_metrics
    macro_df = dashboard_data["macro_df"]
    render_tab_header(
        "Market",
        "AI-specific sector analysis with cross-sectional positioning, movement, fundamental evolution, and market performance.",
        _market_universe_label(market_universe_summary, macro_df),
    )
    render_line_break()
    _render_tab_metric_registry("market")
    render_section("Cross-sector state", "Current leaders in market behavior.")
    render_statline(_assessment_stats(macro_df, sector_data), key_prefix="sector-cross-state")

    render_section("Positioning", "Valuation support, realized repricing, equity strength, and trading pressure in cross section.")
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            render_panel_heading(
                "Earnings Support",
                "Trailing repricing relative to the profitable operating-earnings base",
            )
            st.plotly_chart(
                earnings_support_map(macro_df),
                width="stretch",
                config={"responsive": True},
                key="sectors-earnings-support",
            )
    with right:
        with st.container(border=True):
            render_panel_heading(
                "Speculative Load",
                "Abnormal trading pressure relative to earnings-supported, broad-based equity strength",
            )
            st.plotly_chart(
                speculative_load_matrix(macro_df),
                width="stretch",
                config={"responsive": True},
                key="sectors-speculative-load",
            )

    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("Sector matrix", expanded=False):
        st.dataframe(arrow_safe_dataframe(_sector_table(macro_df)), width="stretch", hide_index=True, height=460)

    render_section(
        "Sector dossier",
        "Sector equity conditions, trading pressure, factor structure, and constituent fundamentals.",
    )
    _render_sector_detail(sector_data, sector_metrics, macro_df)


def _status_rows(regime_metrics):
    mappings = [
        ("AI Equity Index", "AI Equity Index", "AEI", "AEI Version"),
        ("AI Development Intensity", "AI Development Intensity", "ADI", "ADI Version"),
        ("Economic Validation Gap", "Economic Validation Gap", "Economic Validation Gap", "EVG Version"),
        ("Power Stress Index", "Power Stress Index", "Power Stress", "Power Stress Version"),
        ("Power Capacity Gap", "Power Capacity Gap", "Power Capacity Gap", "Power Capacity Gap Version"),
        ("Borrower Strain", "Borrower Strain", "Borrower Strain", "Borrower Strain Version"),
        ("Lender Strain", "Lender Strain", "Lender Strain", "Lender Strain Version"),
        ("Speculation Gap", "Speculation Gap", None, None),
        ("Average Sector Pressure", "Avg Sector Pressure", None, "Pressure Version"),
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
    for product, value_key, prefix, version_key in mappings:
        source = (regime_metrics or {}).get(f"{prefix} Source", "Current") if prefix else "Derived current"
        fallback = (regime_metrics or {}).get(f"{prefix} Fallback Date") if prefix else None
        rows.append(
            {
                "Product": product,
                "Reading": fmt_number(
                    (regime_metrics or {}).get(value_key),
                    2,
                    signed=product in signed_products,
                ),
                "Source State": source,
                "Fallback Date": str(fallback or ""),
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
                "Treatment": "FWD EV/EBIT uses a raw linear x-axis; bubble size is Loss-Making EV Share",
                "Interpretation": "Prospective operating-earnings support for realized repricing",
            },
            {
                "Product": "Speculative Load",
                "Version": SECTOR_VALUATION_VERSION,
                "Construction": "Trading Pressure ÷ Sector AEI",
                "Treatment": "Point color is profitable-cohort FWD EV/EBIT; point size is Loss-Making EV Share",
                "Interpretation": "Abnormal trading pressure carried by each unit of sector equity support",
            },
        ]
    )


def render_evidence_tab(fred_data, sector_data, regime_metrics, energy_data, debt_markets_data, infrastructure_data=None, adaptation_data=None):
    render_tab_header(
        "Evidence",
        "Model contract, current source state, component coverage, definitions, and source data.",
        "definitions / versions / source data",
    )
    render_line_break()
    render_section("Purpose Statement", first=True)
    render_definition(METRIC_DEFINITIONS["Purpose Statement"])

    render_line_break()
    render_section("Source Data")
    render_macro_data(fred_data)
    render_edgar_data(sector_data)
    with st.expander("Energy Data", expanded=False):
        render_static_table(_energy_source_rows(energy_data))
    with st.expander("Debt Markets Data", expanded=False):
        render_static_table(_debt_market_source_rows(debt_markets_data))
    with st.expander("Infrastructure Data", expanded=False):
        render_static_table(_infrastructure_source_rows(infrastructure_data or {}))
    with st.expander("Adaptation Data", expanded=False):
        render_static_table(_adaptation_source_rows(adaptation_data or {}))

    render_section("Product status", "Current readings, source state, fallback dates, and calculation versions.")
    render_static_table(_status_rows(regime_metrics))

    render_section("Coverage")
    render_static_table(_coverage_rows(regime_metrics))

    render_section("Sector construction", "Current equations and aggregation rules for the sector analytical products.")
    render_static_table(_sector_methodology_rows())


def render_research_dashboard(
    tabs,
    sector_data,
    sector_metrics,
    fred_data,
    regime_metrics,
    nfci_history=None,
    energy_data=None,
    debt_markets_data=None,
    infrastructure_data=None,
    adaptation_data=None,
    market_universe_summary=None,
):
    dashboard_data = build_macro_dashboard_data(
        sector_metrics=sector_metrics,
        regime_metrics=regime_metrics,
    )

    with tabs[0]:
        render_macro_tab(
            sector_metrics,
            sector_data,
            fred_data,
            regime_metrics,
            dashboard_data,
            adaptation_data or {},
        )
    with tabs[1]:
        render_market_tab(
            sector_metrics,
            sector_data,
            regime_metrics,
            dashboard_data,
            market_universe_summary,
        )
    with tabs[2]:
        render_finance_tab(
            sector_metrics,
            sector_data,
            fred_data,
            regime_metrics,
            nfci_history,
            debt_markets_data or {},
            dashboard_data,
        )
    with tabs[3]:
        render_infrastructure_tab(infrastructure_data or {})
    with tabs[4]:
        render_energy_tab(
            fred_data,
            regime_metrics,
            energy_data or {},
            dashboard_data,
        )
    with tabs[5]:
        render_adaptation_tab(adaptation_data or {})
    with tabs[6]:
        render_evidence_tab(
            fred_data,
            sector_data,
            regime_metrics,
            energy_data or {},
            debt_markets_data or {},
            infrastructure_data or {},
            adaptation_data or {},
        )
