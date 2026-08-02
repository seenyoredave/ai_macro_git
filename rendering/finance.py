from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics.financial_conditions import nfci_direction, nfci_snapshot
from analytics.trend_engine import calc_trailing_directional_pct
from config.debt_markets_config import DEBT_MARKET_SERIES
from rendering.dataframe import arrow_safe_dataframe
from rendering.charts_common import COLORS, single_history
from rendering.charts_finance import component_bars, debt_market_history, financial_conditions_history, funding_history
from rendering.common import _financial_condition_source_stat, _render_tab_metric_registry, _value
from rendering.components import fmt_date, fmt_number, metric_card, render_line_break, render_panel_heading, render_section, render_statline, render_tab_header
from rendering.evidence_tables import _borrower_strain_component_table, _lender_strain_component_table

FINANCE_UPDATE_DATE = "8.2.2026"

def _funding_specs(funding_mix):
    current = (funding_mix or {}).get("current", {}) or {}
    series = (funding_mix or {}).get("series", {}) or {}
    return [
        (
            "finance-ifc",
            "Internal Funding Coverage",
            current.get("internal_funding_coverage"),
            fmt_number(current.get("internal_funding_coverage"), 2, suffix="x"),
            f"OCF / CapEx · {current.get('internal_funding_companies', 0)} companies",
            series.get("internal_funding_coverage"),
            (0, 3),
            1,
            "violet",
            "YFinance + EDGAR",
        ),
        (
            "finance-crc",
            "Cash Reserve Runway",
            current.get("cash_reserve_coverage_years"),
            fmt_number(current.get("cash_reserve_coverage_years"), 2, suffix="y"),
            f"Cash / TTM CapEx · {current.get('cash_reserve_companies', 0)} companies",
            series.get("cash_reserve_coverage_years"),
            (0, 5),
            1,
            "blue",
            "YFinance + EDGAR",
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
            "YFinance + EDGAR",
        ),
        (
            "finance-fcl",
            "Forward Commitment Load",
            current.get("forward_commitment_load"),
            fmt_number(current.get("forward_commitment_load"), 2, suffix="x"),
            f"Forward commitments / TTM CapEx · {current.get('commitment_companies', 0)} companies",
            series.get("forward_commitment_load"),
            (0, 5),
            1,
            "slate",
            "EDGAR",
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
        render_panel_heading("Funding diagnostics history", "Borrower cohort · 10-year window")
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

def _strain_horizon_pct_note(trend, *, months, label):
    pct_change = calc_trailing_directional_pct(
        (trend or {}).get("history"),
        months=months,
        tolerance=1e-8,
    )
    if pd.isna(pct_change):
        return f"{label} change unavailable"
    return f"{label} {pct_change:+.2f}% change"

def _strain_current_display(value):
    numeric = pd.to_numeric(value, errors="coerce")
    return fmt_number(float(numeric), 1, signed=True) if pd.notna(numeric) else "n/a"

def _render_financial_condition_product(
    *,
    title,
    value,
    trend,
    components,
    detail_table,
    note,
    live_sources,
    supplemental_tables=(),
):
    with st.container(border=True):
        render_panel_heading(title, note)
        source_stat = _financial_condition_source_stat(
            source_label=live_sources,
            updated_date=FINANCE_UPDATE_DATE,
        )
        render_statline(
            [
                (
                    "Current",
                    _strain_current_display(value),
                    _strain_horizon_pct_note(trend, months=12, label="12-month"),
                ),
                (
                    "Velocity",
                    fmt_number((trend or {}).get("velocity"), 2, signed=True),
                    _strain_horizon_pct_note(trend, months=3, label="3-month"),
                ),
                (
                    "Acceleration",
                    fmt_number((trend or {}).get("acceleration"), 2, signed=True),
                    _strain_horizon_pct_note(trend, months=1, label="1-month"),
                ),
                source_stat,
            ],
            key_prefix=f"finance-condition-{title.lower().replace(' ', '-')}",
        )
        history_col, components_col = st.columns([1.25, 1])
        with history_col:
            strain_history_figure = single_history(
                (trend or {}).get("history"),
                color=COLORS["violet"],
                reference=0,
                y_range=(-100, 100),
                height=300,
                step=True,
                years=10,
            )
            strain_history_figure.update_yaxes(title="Strain index points")
            st.plotly_chart(
                strain_history_figure,
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

    with st.expander(f"{title} component detail", expanded=False):
        st.dataframe(arrow_safe_dataframe(detail_table), width="stretch", hide_index=True)
        for label, table in supplemental_tables:
            if isinstance(table, pd.DataFrame) and not table.empty:
                st.markdown(f"**{label}**")
                st.dataframe(arrow_safe_dataframe(table), width="stretch", hide_index=True)

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
                source="New York Fed CMDI",
                fallback_date=item.get("date"),
                accent=accent,
                years=10,
            )

    with st.container(border=True):
        render_panel_heading("Corporate bond market history", "New York Fed CMDI")
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
                ("Observation", fmt_date(snapshot.get("as_of")), "weekly observation"),
                ("Source", "Chicago Fed NFCI", f"updated {FINANCE_UPDATE_DATE}"),
            ],
            key_prefix="finance-nfci-confirmation",
        )
        st.plotly_chart(
            financial_conditions_history(snapshot.get("history"), height=275),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="finance-nfci-history",
        )

def _private_credit_history_table(lender_strain):
    component = ((lender_strain or {}).get("components", {}) or {}).get("Private Credit Impairment", {}) or {}
    history = component.get("panel_history")
    if not isinstance(history, pd.DataFrame) or history.empty:
        return pd.DataFrame()
    display = history.copy().rename(columns={
        "Weighted Nonaccrual at Cost (%)": "Nonaccrual at cost (%)",
        "Weighted Nonaccrual at Fair Value (%)": "Nonaccrual at fair value (%)",
        "Weighted PIK Income Share (%)": "PIK income share (%)",
        "Weighted NAV Change (%)": "NAV change (%)",
        "Weighted Net Losses / Portfolio (%)": "Net losses / portfolio (%)",
        "Weighted Debt to Equity (x)": "Debt / equity (x)",
        "Portfolio Cost ($mm)": "Portfolio cost ($mm)",
    })
    columns = [
        "Date", "Nonaccrual at cost (%)", "Nonaccrual at fair value (%)", "PIK income share (%)",
        "NAV change (%)", "Net losses / portfolio (%)", "Debt / equity (x)",
        "Portfolio cost ($mm)", "Observations", "Cohort",
    ]
    columns = [column for column in columns if column in display.columns]
    return display[columns].sort_values("Date", kind="stable")


def render_finance_tab(sector_metrics, sector_data, fred_data, regime_metrics, nfci_history, debt_markets_data, dashboard_data):
    del sector_metrics, sector_data
    render_tab_header(
        "Finance",
        "Funding capacity, contractual burden, borrower strain, lender strain, and broad financial conditions.",
        "YFinance / SEC / FRED / New York Fed / Chicago Fed",
    )
    render_line_break()
    _render_tab_metric_registry("finance")
    render_section("Funding profile", "Internal funding capacity, cash runway, debt formation, and forward commitments.")
    _render_funding_section(regime_metrics)

    render_section("Debt Markets", "Corporate bond-market distress across overall, investment-grade, and high-yield markets.")
    _render_debt_markets(debt_markets_data)

    render_section(
        "Credit Conditions",
        "Borrower balance sheets and lender credit channels.",
    )
    render_line_break()
    borrower_strain = (regime_metrics or {}).get("Borrower Strain Components", {}) or {}
    _render_financial_condition_product(
        title="Borrower Strain",
        value=_value(regime_metrics, "Borrower Strain"),
        trend=dashboard_data["trends"].get("borrower_strain_trend", {}),
        components=borrower_strain.get("components", {}),
        detail_table=_borrower_strain_component_table(borrower_strain),
        note="Cash flow · debt capacity · commitments · contingent exposure",
        live_sources="YFinance + EDGAR",
    )

    lender_strain = (regime_metrics or {}).get("Lender Strain Components", {}) or {}
    _render_financial_condition_product(
        title="Lender Strain",
        value=_value(regime_metrics, "Lender Strain"),
        trend=dashboard_data["trends"].get("lender_strain_trend", {}),
        components=lender_strain.get("components", {}),
        detail_table=_lender_strain_component_table(lender_strain),
        note="Bank credit · bank capital · private credit · PE financing",
        live_sources="FRED + SEC",
        supplemental_tables=(("Private credit history", _private_credit_history_table(lender_strain)),),
    )

    _render_nfci(fred_data, nfci_history)
