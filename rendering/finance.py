from __future__ import annotations

import html
import pandas as pd
import streamlit as st

from rendering.credit_spreads import render_credit_spreads
from analytics.financial_conditions import nfci_direction, nfci_snapshot
from analytics.pe_us_conditions import build_pe_us_conditions, last_pe_retrieval_date
from rendering.pe_conditions_layout import build_pe_conditions_markup
from analytics.trend_engine import calc_trailing_point_change
from config.debt_markets_config import DEBT_MARKET_SERIES
from rendering.evidence_gateway import render_evidence_gateway
from rendering.finance_layout import render_finance_facts, render_finance_section, render_finance_strain_heading
from rendering.observation_meta import source_through, latest_observation
from rendering.visual_system import render_plotly_chart
from rendering.charts_common import COLORS, single_history
from rendering.charts_finance import (
    component_bars,
    debt_market_history,
    financial_conditions_history,
    funding_history,
)
from rendering.common import _value
from rendering.commercialization import metric_source_date, metric_value
from rendering.components import (
    fmt_date,
    fmt_number,
    render_domain_read,
    render_panel_heading,
    render_tab_header,
)

def _funding_current(regime_metrics):
    return (((regime_metrics or {}).get("Deployment Funding Mix", {}) or {}).get("current", {}) or {})


def _funding_mix(regime_metrics):
    return (regime_metrics or {}).get("Deployment Funding Mix", {}) or {}


def _funding_capacity_stats(regime_metrics):
    current = _funding_current(regime_metrics)
    return [
        (
            "Internal cash flow / CapEx",
            fmt_number(current.get("internal_funding_coverage"), 2, suffix="x"),
            None,
            f"{int(current.get('internal_funding_companies', 0) or 0)} companies",
        ),
        (
            "Cash reserve coverage",
            fmt_number(current.get("cash_reserve_coverage_years"), 2, suffix="y"),
            None,
            f"{int(current.get('cash_reserve_companies', 0) or 0)} companies · Cash / TTM CapEx",
        ),
        (
            "Debt change / CapEx",
            fmt_number(current.get("debt_financing_pulse"), 2, signed=True, suffix="x"),
            None,
            f"{int(current.get('debt_financing_companies', 0) or 0)} matched companies",
        ),
        (
            "Future commitments / CapEx",
            fmt_number(current.get("forward_commitment_load"), 2, suffix="x"),
            None,
            f"{int(current.get('commitment_companies', 0) or 0)} companies",
        ),
    ]


def _render_capital_capacity(regime_metrics):
    funding_mix = _funding_mix(regime_metrics)
    current = funding_mix.get("current", {}) or {}
    funding_date = current.get("measurement_date")
    render_finance_facts([
        ("TTM CapEx", _fmt_dollars(current.get("capex_total")), None, f"{int(current.get('cohort_companies', 0) or 0)} company cohort"),
        ("Forward commitments", _fmt_dollars(current.get("forward_commitments_total")), None, "Filing-backed commitments"),
        ("Total debt", _fmt_dollars(current.get("total_debt")), None, f"{int(current.get('debt_financing_companies', 0) or 0)} matched companies"),
        ("Prior-year debt", _fmt_dollars(current.get("prior_year_total_debt")), None, f"{int(current.get('debt_financing_companies', 0) or 0)} matched companies"),
    ], columns=4, treatment="lead")
    with st.container(key="finance-panel-funding-history"):
        render_panel_heading("Funding capacity over time", source_through("SEC filings + EDGAR", funding_date or latest_observation(funding_mix.get("history"))))
        chart_col, readings_col = st.columns([1.85, 1], gap="large", vertical_alignment="top")
        with chart_col:
            render_plotly_chart(
                funding_history(funding_mix.get("history"), years=5),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key="finance-funding-history",
            )
        with readings_col:
            render_finance_facts(_funding_capacity_stats(regime_metrics), treatment="funding")


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

def _strain_horizon_point_note(trend, *, months, label):
    point_change = calc_trailing_point_change(
        (trend or {}).get("history"),
        months=months,
        tolerance=1e-8,
    )
    if pd.isna(point_change):
        return f"{label} change unavailable"
    return f"{label} {point_change:+.2f} points"

def _strain_current_display(value):
    numeric = pd.to_numeric(value, errors="coerce")
    return fmt_number(float(numeric), 1, signed=True) if pd.notna(numeric) else "n/a"

def _financial_condition_stats(*, value, trend):
    return [
        (
            "Current",
            _strain_current_display(value),
            _strain_horizon_point_note(trend, months=12, label="12-month"),
        ),
        (
            "Velocity",
            fmt_number((trend or {}).get("velocity"), 2, signed=True),
            "12-month OLS slope · points / 30d",
        ),
        (
            "Acceleration",
            fmt_number((trend or {}).get("acceleration"), 2, signed=True),
            "current minus prior 12-month slope",
        ),
    ]


def _latest_strain_date(trend):
    return latest_observation((trend or {}).get("history"))


def _financial_condition_source_meta(trend, live_sources):
    updated_date = _latest_strain_date(trend)
    return source_through(live_sources, updated_date)


def _render_financial_condition_summary(*, title, value, trend, live_sources):
    with st.container(key=f"finance-strain-summary-{title.lower().replace(' ', '-')}"):
        render_finance_strain_heading(title, _financial_condition_source_meta(trend, live_sources))
        readings = _financial_condition_stats(value=value, trend=trend)
        render_finance_facts([
            (label, reading, None, context)
            for label, reading, context in readings
        ], treatment="strain")


def _render_financial_condition_detail(
    *,
    title,
    trend,
    components,
):
    slug = title.lower().replace(" ", "-")
    with st.container(key=f"finance-panel-{slug}-detail"):
        source = "YFinance + EDGAR" if title == "Borrower Strain" else "FRED + SEC"
        render_panel_heading(f"{title} · 10-year history and components", _financial_condition_source_meta(trend, source))
        st.radio(
            "Stress detail", ["Borrower", "Lender"], horizontal=True,
            label_visibility="collapsed", key="finance-view-stress-detail",
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
            render_plotly_chart(
                strain_history_figure,
                width="stretch",
                config={"displayModeBar": True, "responsive": True},
                key=f"finance-{slug}-history",
            )
        with components_col:
            render_plotly_chart(
                component_bars(components, signed=True, height=300),
                width="stretch",
                config={"displayModeBar": True, "responsive": True},
                key=f"finance-{slug}-components",
            )


def _debt_market_item(debt_markets_data, name):
    return (((debt_markets_data or {}).get("series", {}) or {}).get(name, {}) or {})

def _render_debt_markets(debt_markets_data):
    with st.container(key="finance-panel-bond-distress"):
        render_panel_heading("Bond-market distress", source_through("New York Fed CMDI", latest_observation((debt_markets_data or {}).get("history"))))
        cards = (
            ("Corporate Bond Market Distress", "Primary and secondary markets"),
            ("Investment-Grade Bond Distress", "Investment-grade segment"),
            ("High-Yield Bond Distress", "High-yield segment"),
        )
        rows = []
        for name, context in cards:
            item = _debt_market_item(debt_markets_data, name)
            rows.append(
                '<div class="rm-finance-cmdi-card">'
                f'<div class="rm-card-label">{html.escape(name)}</div>'
                f'<div class="rm-card-value">{html.escape(fmt_number(item.get("value"), 2))}</div>'
                f'<div class="rm-card-context">{html.escape(context)}</div>'
                '</div>'
            )
        st.markdown('<div class="rm-finance-cmdi">' + ''.join(rows) + '</div>', unsafe_allow_html=True)
        render_plotly_chart(
            debt_market_history((debt_markets_data or {}).get("history"), height=310, years=10),
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
    with st.container(key="finance-panel-broad-conditions"):
        render_panel_heading("Broad financial conditions", source_through("Chicago Fed / FRED", snapshot.get("as_of")))
        render_finance_facts([
            ("NFCI", fmt_number(value, 3, signed=True), None, "Headline"),
            ("ANFCI", fmt_number(anfci_value, 3, signed=True), None, "Macro-adjusted"),
            ("3-month change", fmt_number(change, 3, signed=True), None, nfci_direction(change)),
        ], columns=3, treatment="lead")
        render_plotly_chart(
            financial_conditions_history(snapshot.get("history"), height=310),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="finance-nfci-history",
        )



def _private_capital_detail_table(funds: pd.DataFrame, *, year_basis: str = "vintage") -> pd.DataFrame:
    if funds is None or funds.empty:
        return pd.DataFrame()
    display = funds.copy()
    display["Paid In ($M)"] = pd.to_numeric(display.get("Paid In Capital"), errors="coerce") / 1e6
    display["Distributions ($M)"] = pd.to_numeric(display.get("Distributions"), errors="coerce") / 1e6
    display["NAV ($M)"] = pd.to_numeric(display.get("NAV"), errors="coerce") / 1e6
    display["DPI"] = pd.to_numeric(display.get("DPI"), errors="coerce")
    display["RVPI"] = pd.to_numeric(display.get("RVPI"), errors="coerce")
    display["TVPI"] = pd.to_numeric(display.get("TVPI"), errors="coerce")
    display["Net IRR (%)"] = pd.to_numeric(display.get("Net IRR"), errors="coerce")
    display["Source As Of"] = pd.to_datetime(display.get("Source As Of"), errors="coerce").dt.date
    columns = [
        "Manager", "Fund", "Vintage", "Maturity", "Exposure Tier",
        "Paid In ($M)", "Distributions ($M)", "NAV ($M)",
        "DPI", "RVPI", "TVPI", "Net IRR (%)", "Source As Of",
    ]
    result = display[[column for column in columns if column in display.columns]].sort_values(
        ["Vintage", "Manager", "Fund"], ascending=[False, True, True], kind="stable"
    )
    names = {"Manager": "Fund family (derived)"}
    if year_basis == "initial investment year":
        names["Vintage"] = "Initial investment year"
    return result.rename(columns=names)



def _render_pe_conditions(context):
    markup = build_pe_conditions_markup(context)
    if not markup:
        st.caption("U.S. private-equity liquidity observations are unavailable.")
        return
    with st.container(key="finance-panel-pe-conditions"):
        st.markdown(markup, unsafe_allow_html=True)


def _render_commercial_realization(commercialization_data):
    microsoft_arr = metric_value(commercialization_data, "Microsoft", "Annual revenue run rate")
    microsoft_growth = metric_value(commercialization_data, "Microsoft", "Annual revenue run-rate growth")
    openai_arr = metric_value(commercialization_data, "OpenAI", "Annualized revenue run rate")
    alphabet_backlog = metric_value(commercialization_data, "Alphabet", "Backlog")
    microsoft_margin = metric_value(commercialization_data, "Microsoft", "Gross margin")
    if all(pd.isna(value) for value in [microsoft_arr, openai_arr, alphabet_backlog, microsoft_margin]):
        return

    with st.container(key="finance-panel-company-ai-disclosures"):
        render_finance_facts([
            (label, value, source_through(*metric_source_date(commercialization_data, provider, metric)), detail)
            for label, value, provider, metric, detail in [
                ("Microsoft AI ARR", "$" + fmt_number(microsoft_arr, 1, suffix="B"), "Microsoft", "Annual revenue run rate", fmt_number(microsoft_growth, 0, signed=True, suffix="% YoY")),
                ("OpenAI ARR", "$" + fmt_number(openai_arr, 1, suffix="B+"), "OpenAI", "Annualized revenue run rate", "2025 disclosed floor"),
                ("Google Cloud backlog", "$" + fmt_number(alphabet_backlog, 0, suffix="B"), "Alphabet", "Backlog", "Reported cloud backlog"),
                ("Microsoft Cloud margin", fmt_number(microsoft_margin, 0, suffix="%"), "Microsoft", "Gross margin", "AI infrastructure and usage pressure"),
            ]
        ], columns=4, treatment="index")

def render_finance_tab(sector_metrics, sector_data, fred_data, regime_metrics, nfci_history, debt_markets_data, dashboard_data, commercialization_data=None, tab_read=None):
    del sector_metrics, sector_data
    pe_conditions = build_pe_us_conditions()
    retrieved = last_pe_retrieval_date()
    pe_sources = "GF Data/ACG • KPMG • Cambridge Associates"
    if retrieved:
        pe_sources += f" • through {retrieved}"
    else:
        pe_sources += " • retrieval pending"
    render_tab_header(
        "Finance",
        "Cash flow, capital spending, debt, commitments, credit conditions, and private-equity liquidity.",
        "SEC / company disclosures / Cambridge Associates / KPMG / GF Data / FRED / New York Fed / Chicago Fed",
        terms_key="finance",
    )
    render_domain_read(tab_read, label="Read", domain="finance")

    with st.container(border=True, key="finance-section-funding"):
        render_finance_section("Funding capacity", "Operating cash flow, cash reserves, debt change, and disclosed commitments relative to capital spending.")
        _render_capital_capacity(regime_metrics)

    with st.container(border=True, key="finance-section-disclosures"):
        render_finance_section("Company AI disclosures", "Reported AI revenue, backlog, margins, and demand indicators from company disclosures.")
        _render_commercial_realization(commercialization_data)

    with st.container(border=True, key="finance-section-pe-conditions"):
        render_finance_section(
            "Private equity", "Cash in • cash out • ROI",
            sources=pe_sources,
        )
        _render_pe_conditions(pe_conditions)

    with st.container(border=True, key="finance-section-credit"):
        render_finance_section("Credit conditions", "Daily corporate credit spreads, bond-market distress, and Chicago Fed financial conditions.")
        credit_view = st.radio(
            "Credit view", ["Spreads", "Bond distress", "Broad conditions"],
            horizontal=True, label_visibility="collapsed", key="finance-credit-view",
        )
        if credit_view == "Bond distress":
            _render_debt_markets(debt_markets_data)
        elif credit_view == "Broad conditions":
            _render_nfci(fred_data, nfci_history)
        else:
            render_credit_spreads()

    with st.container(border=True, key="finance-section-stress"):
        render_finance_section("Borrower and lender stress", "Borrower balance-sheet strain and lender-side credit indicators.")
        trends = (dashboard_data or {}).get("trends", {}) or {}
        borrower_strain = (regime_metrics or {}).get("Borrower Strain Components", {}) or {}
        lender_strain = (regime_metrics or {}).get("Lender Strain Components", {}) or {}
        borrower_trend = trends.get("borrower_strain_trend", {})
        lender_trend = trends.get("lender_strain_trend", {})

        left, right = st.columns(2)
        with left:
            _render_financial_condition_summary(
                title="Borrower Strain",
                value=_value(regime_metrics, "Borrower Strain"),
                trend=borrower_trend,
                live_sources="YFinance + EDGAR",
            )
        with right:
            _render_financial_condition_summary(
                title="Lender Strain",
                value=_value(regime_metrics, "Lender Strain"),
                trend=lender_trend,
                live_sources="FRED + SEC",
            )

        stress_view = st.session_state.get("finance-view-stress-detail", "Borrower")
        if stress_view == "Lender":
            _render_financial_condition_detail(
                title="Lender Strain",
                trend=lender_trend,
                components=lender_strain.get("components", {}),
            )
            momentum = lender_strain.get("loan_momentum", {})
            st.caption(
                f"Bank lending momentum {fmt_number(momentum.get('13_week_change_pct'), 2, signed=True, suffix='%')}"
                f" · {source_through('Fed H.8 / FRED', momentum.get('as_of'))}"
            )
        else:
            _render_financial_condition_detail(
                title="Borrower Strain",
                trend=borrower_trend,
                components=borrower_strain.get("components", {}),
            )

    render_evidence_gateway("finance")

