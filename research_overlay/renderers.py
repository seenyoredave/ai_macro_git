"""High-density research renderers built on the existing AI Macro engine."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from analytics.hhi_engine import hhi_component_breakdown
from analytics.financial_conditions import (
    nfci_condition,
    nfci_direction,
    nfci_snapshot,
)
from analytics.macro_dataframe import build_macro_dashboard_data
from analytics.regime_engine import AEI_VERSION, PRESSURE_VERSION
from analytics.valuation import SECTOR_VALUATION_VERSION
from analytics.sector_assessment import select_current_sector_assessment
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
    _capital_component_table,
    _component_table,
    _intermediation_component_table,
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
    earnings_support_map,
    financial_conditions_history,
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
    if name == "Concentration HHI":
        return "Market-value concentration"
    return ""


def _render_primary_macro_cards(regime_metrics, trends):
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
        ),
        (
            "macro-card-hhi",
            "Concentration HHI",
            _value(regime_metrics, "Concentration HHI"),
            trends.get("concentration_trend", {}).get("history"),
            (0, 100),
            "Current",
            None,
            "slate",
        ),
    ]

    for col, spec in zip(st.columns(4), specs):
        key, label, value, history, scale, source, fallback, accent = spec
        with col:
            metric_card(
                key=key,
                label=label,
                value=value,
                value_text=fmt_number(value, 1),
                context=_metric_context(label, value),
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
            )
        with measures_col:
            render_statline(
                [
                    ("Speculation", fmt_number(gaps["Speculation Gap"], 0, signed=True), speculation_label(gaps["Speculation Gap"])),
                    ("Validation", fmt_number(gaps["Economic Validation Gap"], 0, signed=True), validation_label(gaps["Economic Validation Gap"])),
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
    adi_result = (regime_metrics or {}).get("ADI Components", {}) or {}
    validation_result = (regime_metrics or {}).get("Economic Validation Gap Components", {}) or {}
    power_result = (regime_metrics or {}).get("Power Stress Components", {}) or {}

    hhi_breakdown = hhi_component_breakdown(sector_data, top_n=5)
    groups = [
        ("ADI pillars", adi_result.get("components", {}), False, COLORS["violet"]),
        ("Validation legs", validation_result.get("components", {}), False, COLORS["blue"]),
        ("Power-stress components", power_result.get("components", {}), True, COLORS["violet"]),
    ]
    first_row = st.columns(2)
    second_row = st.columns(2)
    component_columns = first_row + second_row
    for col, (title, components, signed, color) in zip(component_columns[:3], groups):
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
                )
    with component_columns[3]:
        with st.container(border=True):
            render_panel_heading("Concentration contributors", "Top five companies plus the remainder")
            st.plotly_chart(
                hhi_component_chart(hhi_breakdown),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
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
        st.caption(
            f"Deployment pressure: {fmt_number(power_capacity_result.get('deployment_pressure_score'), 1)} · "
            f"Power-system response: {fmt_number(power_capacity_result.get('power_response_score'), 1)}"
        )

        st.markdown("**Concentration HHI**")
        hhi_table = hhi_breakdown.copy()
        if not hhi_table.empty:
            hhi_table["Market Cap Share"] = (hhi_table["Market Cap Share"] * 100.0).round(2)
            hhi_table["HHI Contribution Share"] = hhi_table["HHI Contribution Share"].round(2)
            hhi_table = hhi_table.rename(columns={
                "Market Cap Share": "Market Cap Share (%)",
                "HHI Contribution Share": "Share of HHI (%)",
            })
        render_static_table(hhi_table)
        st.caption(
            f"Raw AI HHI: {fmt_number((regime_metrics or {}).get('Raw AI HHI'), 4)} · "
            f"Average sector pressure: {fmt_number((regime_metrics or {}).get('Avg Sector Pressure'), 1)}"
        )


def render_macro_tab(sector_metrics, sector_data, fred_data, regime_metrics, dashboard_data):
    del sector_metrics
    render_tab_header(
        "AI Macro",
        "Equity trends, observable deployment, power utilization, and validation gaps.",
        "market / buildout / validation",
    )
    render_section("Regime board", "Current readings with retained histories and source state.", first=True)
    _render_primary_macro_cards(regime_metrics, dashboard_data["trends"])
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
            "Cash Reserve Coverage",
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



def _render_stress_product(
    *,
    title,
    value,
    source,
    fallback_date,
    trend,
    components,
    detail_table,
    note,
):
    with st.container(border=True):
        render_panel_heading(title)
        dynamics_note = (trend or {}).get("dynamics_note", "native-version history")
        render_statline(
            [
                ("Current", fmt_number(value, 1, signed=True), "reference = 0"),
                ("Source", source, f"fallback {fmt_date(fallback_date)}" if fallback_date else "current run"),
                ("Velocity", fmt_number((trend or {}).get("velocity"), 2, signed=True), dynamics_note),
                ("Acceleration", fmt_number((trend or {}).get("acceleration"), 2, signed=True), dynamics_note),
            ],
            key_prefix=f"finance-stress-{title.lower().replace(' ', '-')}",
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
            )
        with components_col:
            st.plotly_chart(
                component_bars(components, signed=True, height=300),
                width="stretch",
                config={"displayModeBar": True, "responsive": True},
            )
        st.caption(note)

    with st.expander(f"{title} component detail", expanded=False):
        st.dataframe(arrow_safe_dataframe(detail_table), width="stretch", hide_index=True)


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
                ("Source", "Chicago Fed NFCI", "updated every Wednesday at 8:30am ET"),
            ],
            key_prefix="finance-nfci-confirmation",
        )
        st.plotly_chart(
            financial_conditions_history(snapshot.get("history"), height=275),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
        )


def render_finance_tab(sector_metrics, sector_data, fred_data, regime_metrics, nfci_history, dashboard_data):
    del sector_metrics, sector_data
    render_tab_header(
        "Finance",
        "Funding capacity, contractual burden, borrower stress, intermediation stress, and broad financial conditions.",
        "funding / borrowers / lenders / system",
    )
    render_section("Funding profile", "Current funding ratios and retained cohort history.", first=True)
    _render_funding_section(regime_metrics)

    render_section("Borrower and lender stress", "Financial market liquidity, exposure, and credit availability.")
    capital = (regime_metrics or {}).get("Capital Stress Components", {}) or {}
    _render_stress_product(
        title="Capital Stress",
        value=_value(regime_metrics, "Capital Stress"),
        source=_source(regime_metrics, "Capital Stress"),
        fallback_date=_fallback(regime_metrics, "Capital Stress"),
        trend=dashboard_data["trends"].get("capital_stress_trend", {}),
        components=capital.get("components", {}),
        detail_table=_capital_component_table(capital),
        note="Borrower-side financing strain from cash flow, leverage, disclosed commitments, and contingent exposure.",
    )

    intermediation = (regime_metrics or {}).get("Credit Intermediation Stress Components", {}) or {}
    _render_stress_product(
        title="Credit Intermediation Stress",
        value=_value(regime_metrics, "Credit Intermediation Stress"),
        source=_source(regime_metrics, "Credit Intermediation Stress"),
        fallback_date=_fallback(regime_metrics, "Credit Intermediation Stress"),
        trend=dashboard_data["trends"].get("intermediation_stress_trend", {}),
        components=intermediation.get("components", {}),
        detail_table=_intermediation_component_table(intermediation),
        note=(
            f"Bank channel {fmt_number(intermediation.get('bank_channel_score'), 1, signed=True)} · "
            f"Nonbank channel {fmt_number(intermediation.get('nonbank_channel_score'), 1, signed=True)} · "
            f"{intermediation.get('elevated_pillars', 0)} of 4 pillars above neutral."
        ),
    )

    _render_nfci(fred_data, nfci_history)


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

    leader = None
    if macro_df is not None and not macro_df.empty and {'Sector', 'Sector Score'}.issubset(macro_df.columns):
        leader_frame = macro_df[['Sector', 'Sector Score']].copy()
        leader_frame['Sector Score'] = pd.to_numeric(leader_frame['Sector Score'], errors='coerce')
        leader_frame = leader_frame.dropna(subset=['Sector Score'])
        if not leader_frame.empty:
            leader = leader_frame.loc[leader_frame['Sector Score'].idxmax()]

    if leader is None:
        stats.append(("Most Profitable", "n/a", "insufficient eligible data"))
    else:
        stats.append((
            "Most Profitable",
            sector_display_name(leader.get('Sector')),
            f"AEI leader {fmt_number(leader.get('Sector Score'), 0)}",
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
        "Beta",
    ]
    available = [column for column in required if column in macro_df.columns]
    table = macro_df[available].copy()
    table["Sector"] = table["Sector"].apply(sector_display_name)
    table = table.rename(columns={"Sector Score": "AEI", "Avg Return": "1Y Return"})
    for column in ["AEI", "Pressure", "Beta"]:
        if column in table.columns:
            table[column] = pd.to_numeric(table[column], errors="coerce")
    if "1Y Return" in table.columns:
        table["1Y Return"] = pd.to_numeric(table["1Y Return"], errors="coerce")
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
            (
                "Loss-Making EV Share",
                fmt_number(pd.to_numeric(metrics.get("Loss-Making EV Share"), errors="coerce") * 100, 1, suffix="%"),
                f"{int(metrics.get('Loss-Making Company Count', 0) or 0)} companies with non-positive forward EBIT",
            ),
        ],
        key_prefix="sector-dossier-summary",
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
            )
    with pressure_col:
        with st.container(border=True):
            render_panel_heading("Trading-pressure structure")
            st.plotly_chart(
                pressure_component_chart(metrics.get("Pressure Components", pd.DataFrame())),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
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


def render_sectors_tab(sector_metrics, sector_data, regime_metrics, dashboard_data):
    del regime_metrics
    macro_df = dashboard_data["macro_df"]
    render_tab_header(
        "Sectors",
        "Cross-sectional positioning, movement, fundamental evolution, and metric-driven sector detail.",
        f"{len(macro_df)} sectors",
    )
    st.markdown("<br>", unsafe_allow_html=True)
    render_section("Cross-sector state", "Current leaders in market behavior.", first=True)
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
        ("AI Equity Index", "AEI", "AEI Version"),
        ("AI Development Intensity", "ADI", "ADI Version"),
        ("Economic Validation Gap", "Economic Validation Gap", "EVG Version"),
        ("Power Stress Index", "Power Stress", "Power Stress Version"),
        ("Power Capacity Gap", "Power Capacity Gap", "Power Capacity Gap Version"),
        ("Capital Stress", "Capital Stress", "Capital Stress Version"),
        ("Credit Intermediation Stress", "Credit Intermediation Stress", "Credit Intermediation Stress Version"),
        ("Concentration HHI", None, None),
        ("Speculation Gap", None, None),
        ("Average Sector Pressure", None, "Pressure Version"),
    ]
    rows = []
    for product, prefix, version_key in mappings:
        value_key = "Avg Sector Pressure" if product == "Average Sector Pressure" else product
        source = (regime_metrics or {}).get(f"{prefix} Source", "Current") if prefix else "Derived current"
        fallback = (regime_metrics or {}).get(f"{prefix} Fallback Date") if prefix else None
        rows.append(
            {
                "Product": product,
                "Reading": fmt_number((regime_metrics or {}).get(value_key), 2, signed=product in {
                    "Economic Validation Gap", "Power Stress Index", "Power Capacity Gap", "Capital Stress", "Credit Intermediation Stress", "Speculation Gap"
                }),
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
        ("Capital Stress", (regime_metrics or {}).get("Capital Stress Components", {}), 4),
        ("Credit Intermediation Stress", (regime_metrics or {}).get("Credit Intermediation Stress Components", {}), 4),
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
            {"Product": "Cash Reserve Coverage", "Valid Components": _display_text(current.get("cash_reserve_companies", "")), "Required Universe": "company cohort", "Coverage": "cohort coverage"},
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


def render_evidence_tab(fred_data, sector_data, regime_metrics):
    render_tab_header(
        "Evidence",
        "Model contract, current source state, component coverage, definitions, and source observations.",
        "definitions / versions / raw observations",
    )
    render_section("Purpose and boundary", first=True)
    render_definition(METRIC_DEFINITIONS["Purpose Statement"])

    render_section("Product status", "Current readings, source state, fallback dates, and calculation versions.")
    render_static_table(_status_rows(regime_metrics))

    render_section("Coverage", "Component and cohort sufficiency for the current run.")
    render_static_table(_coverage_rows(regime_metrics))

    render_section("Sector construction", "Current equations and aggregation rules for the sector analytical products.")
    render_static_table(_sector_methodology_rows())

    render_section("Metric registry", "Definitions remain available without interrupting the primary analytical surfaces.")
    definitions = [name for name in METRIC_DEFINITIONS if name != "Purpose Statement"]
    selected = st.selectbox("Metric or analytical product", definitions, key="research-evidence-definition")
    render_definition(METRIC_DEFINITIONS[selected])

    render_section("Source observations", "Raw FRED and EDGAR views from the current data pipeline.")
    render_macro_data(fred_data)
    render_edgar_data(sector_data)


def render_research_dashboard(
    tabs,
    sector_data,
    sector_metrics,
    fred_data,
    regime_metrics,
    nfci_history=None,
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
        )
    with tabs[1]:
        render_finance_tab(
            sector_metrics,
            sector_data,
            fred_data,
            regime_metrics,
            nfci_history,
            dashboard_data,
        )
    with tabs[2]:
        render_sectors_tab(
            sector_metrics,
            sector_data,
            regime_metrics,
            dashboard_data,
        )
    with tabs[3]:
        render_evidence_tab(fred_data, sector_data, regime_metrics)
