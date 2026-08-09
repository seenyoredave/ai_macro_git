from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics.financial_conditions import nfci_direction, nfci_snapshot
from analytics.private_capital import build_private_capital_realization
from analytics.trend_engine import calc_trailing_point_change
from config.debt_markets_config import DEBT_MARKET_SERIES
from rendering.visual_system import render_plotly_chart
from rendering.dataframe import arrow_safe_dataframe
from rendering.charts_common import COLORS, clean_history, history_from_frame, single_history
from rendering.charts_finance import (
    component_bars,
    debt_market_history,
    financial_conditions_history,
    private_capital_realization_map,
)
from rendering.common import _render_floating_terms, _value
from rendering.commercialization import filtered_ledger, metric_value
from rendering.components import (
    fmt_date,
    fmt_number,
    inject_panel_height_rules,
    metric_card,
    render_domain_read,
    render_panel_heading,
    render_section,
    render_statline,
    render_summary_row,
    render_tab_header,
)
from rendering.evidence_tables import _borrower_strain_component_table, _lender_strain_component_table

def _funding_card_history(funding_mix, series_key, history_column):
    """Build a card series from the authoritative common funding history.

    The nested ``series`` mapping is retained for compatibility, but it is a
    derived convenience object and must not be able to blank one card while
    the common history contains valid observations.
    """
    funding_mix = funding_mix or {}
    common = history_from_frame(funding_mix.get("history"), history_column)
    if len(common) >= 2:
        return common
    fallback = clean_history(
        ((funding_mix.get("series", {}) or {}).get(series_key))
    )
    return fallback if not fallback.empty else common


def _funding_specs(funding_mix):
    current = (funding_mix or {}).get("current", {}) or {}
    return [
        (
            "finance-ifc",
            "Internal cash flow / CapEx",
            current.get("internal_funding_coverage"),
            fmt_number(current.get("internal_funding_coverage"), 2, suffix="x"),
            f"OCF / CapEx · {current.get('internal_funding_companies', 0)} companies",
            _funding_card_history(
                funding_mix,
                "internal_funding_coverage",
                "Internal cash flow / CapEx",
            ),
            (0, 3),
            1,
            "violet",
            "SEC filings",
        ),
        (
            "finance-crc",
            "Cash reserve coverage",
            current.get("cash_reserve_coverage_years"),
            fmt_number(current.get("cash_reserve_coverage_years"), 2, suffix="y"),
            f"Cash / TTM CapEx · {current.get('cash_reserve_companies', 0)} companies",
            _funding_card_history(
                funding_mix,
                "cash_reserve_coverage_years",
                "Cash Reserve Coverage",
            ),
            (0, 5),
            1,
            "blue",
            "SEC filings",
        ),
        (
            "finance-dfp",
            "Debt change / CapEx",
            current.get("debt_financing_pulse"),
            fmt_number(current.get("debt_financing_pulse"), 2, signed=True, suffix="x"),
            f"Definition-matched Δ12m SEC debt / TTM CapEx · {current.get('debt_financing_companies', 0)} companies",
            _funding_card_history(
                funding_mix,
                "debt_financing_pulse",
                "Debt change / CapEx",
            ),
            (-2, 2),
            0,
            "violet",
            "SEC filings",
        ),
        (
            "finance-fcl",
            "Future commitments / CapEx",
            current.get("forward_commitment_load"),
            fmt_number(current.get("forward_commitment_load"), 2, suffix="x"),
            f"Forward commitments / TTM CapEx · {current.get('commitment_companies', 0)} companies",
            _funding_card_history(
                funding_mix,
                "forward_commitment_load",
                "Future commitments / CapEx",
            ),
            (0, 5),
            1,
            "slate",
            "EDGAR",
        ),
    ]

def _render_funding_section(regime_metrics):
    funding_mix = (regime_metrics or {}).get("Deployment Funding Mix", {}) or {}
    current = funding_mix.get("current", {}) or {}
    with st.container(border=True, key="finance-funding-instrument-board"):
        render_panel_heading(
            "Current funding capacity",
            "Cash flow, cash reserves, debt changes, and future commitments relative to current capital spending",
        )
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
                    years=5,
                )
        render_summary_row(
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


def _financial_condition_source_meta(trend, live_sources):
    history = (trend or {}).get("history")
    updated_date = None
    if isinstance(history, pd.DataFrame) and not history.empty:
        updated_date = pd.to_datetime(history.get("Date"), errors="coerce").max()
    date_text = fmt_date(updated_date)
    return f"{live_sources} · through {date_text}"


def _render_financial_condition_summary(*, title, value, trend, live_sources):
    with st.container(border=True):
        render_panel_heading(
            title,
            _financial_condition_source_meta(trend, live_sources),
        )
        render_statline(
            _financial_condition_stats(
                value=value,
                trend=trend,
            ),
            key_prefix=f"finance-condition-{title.lower().replace(' ', '-')}",
        )


def _render_financial_condition_detail(
    *,
    title,
    trend,
    components,
    detail_table,
    supplemental_tables=(),
):
    del detail_table, supplemental_tables
    slug = title.lower().replace(" ", "-")
    with st.container(border=True, key=f"finance-panel-{slug}-detail"):
        detail_meta = (
            "10-year history · FRED bridge before direct BDC panel"
            if title == "Lender Strain"
            else "10-year history · component contribution"
        )
        render_panel_heading(f"{title} detail", detail_meta)
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
        render_plotly_chart(
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
        render_panel_heading("Broad financial conditions")
        render_statline(
            [
                ("NFCI/ANFCI", paired_value, "headline / macro-adjusted"),
                ("3-month change", fmt_number(change, 3, signed=True), nfci_direction(change)),
                ("Observation", fmt_date(snapshot.get("as_of")), "weekly observation"),
                ("Source", "Chicago Fed NFCI", f"observed {fmt_date(snapshot.get('as_of'))}"),
            ],
            key_prefix="finance-nfci-confirmation",
        )
        render_plotly_chart(
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



def _business_loan_delinquency_history_table(lender_strain):
    component = ((lender_strain or {}).get("components", {}) or {}).get(
        "Private Credit Impairment", {}
    ) or {}
    history = component.get("historical_bridge")
    if not isinstance(history, pd.DataFrame) or history.empty:
        return pd.DataFrame()
    display = history.copy().rename(
        columns={
            "Business Loan Delinquency Rate (%)": "Business-loan delinquency (%)",
        }
    )
    columns = [
        "Date",
        "Business-loan delinquency (%)",
        "Source",
    ]
    columns = [column for column in columns if column in display.columns]
    return display[columns].sort_values("Date", kind="stable")


def _private_capital_detail_table(funds: pd.DataFrame) -> pd.DataFrame:
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
    return display[[column for column in columns if column in display.columns]].sort_values(
        ["Vintage", "Manager", "Fund"], ascending=[False, True, True], kind="stable"
    )


def _render_private_capital_realization():
    realization = build_private_capital_realization()
    metrics = realization.get("metrics", {}) or {}
    funds = realization.get("funds", pd.DataFrame())
    as_of = fmt_date(realization.get("as_of"))

    if not metrics or funds is None or funds.empty:
        with st.container(border=True):
            render_panel_heading("Private-market cash returns", "Public pension fund records")
            st.caption("Private-fund cash-return data are unavailable.")
        return

    with st.container(key="full-width-layout-finance-private-capital"):
        render_summary_row(
            [
                ("DPI", fmt_number(metrics.get("dpi"), 2, suffix="x"), "cash returned / paid in"),
                ("RVPI", fmt_number(metrics.get("rvpi"), 2, suffix="x"), "remaining NAV / paid in"),
                ("TVPI", fmt_number(metrics.get("tvpi"), 2, suffix="x"), "distributed + residual value"),
                ("Cash-returned share", fmt_number((metrics.get("realized_share") or 0) * 100, 0, suffix="%"), "share of current total value"),
            ],
            key_prefix="finance-private-capital-realization",
        )
        with st.container(border=True, key="finance-panel-realization-map"):
            render_panel_heading(
                "Cash returned versus remaining fund value",
                "Cash returned versus remaining value · bubble size reflects paid-in capital",
            )
            render_plotly_chart(
                private_capital_realization_map(funds),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key="finance-private-capital-map",
            )
        st.caption(
            f"{metrics.get('fund_count', 0)} funds across {metrics.get('manager_count', 0)} managers · "
            f"{_fmt_dollars(metrics.get('paid_in'))} paid in · five-year-plus vintages · as of {as_of}."
        )

def _render_commercial_realization(commercialization_data):
    microsoft_arr = metric_value(commercialization_data, "Microsoft", "Annual revenue run rate")
    microsoft_growth = metric_value(commercialization_data, "Microsoft", "Annual revenue run-rate growth")
    openai_arr = metric_value(commercialization_data, "OpenAI", "Annualized revenue run rate")
    alphabet_backlog = metric_value(commercialization_data, "Alphabet", "Backlog")
    microsoft_margin = metric_value(commercialization_data, "Microsoft", "Gross margin")
    if all(pd.isna(value) for value in [microsoft_arr, openai_arr, alphabet_backlog, microsoft_margin]):
        return

    render_section(
        "Reported AI revenue and demand",
        "AI-related revenue, backlog, and operating scale from primary company disclosures.",
    )
    render_summary_row(
        [
            ("Microsoft AI ARR", "$" + fmt_number(microsoft_arr, 1, suffix="B"), fmt_number(microsoft_growth, 0, signed=True, suffix="% YoY")),
            ("OpenAI ARR", "$" + fmt_number(openai_arr, 1, suffix="B+"), "2025 disclosed floor"),
            ("Google Cloud backlog", "$" + fmt_number(alphabet_backlog, 0, suffix="B"), "reported cloud backlog"),
            ("Microsoft Cloud margin", fmt_number(microsoft_margin, 0, suffix="%"), "AI infrastructure and usage pressure"),
        ],
        key_prefix="finance-commercial-realization",
    )

def _render_finance_ledger(commercialization_data, debt_markets_data, borrower_strain, lender_strain):
    realization = build_private_capital_realization()
    options = ["Commercial disclosures", "Private-fund records", "Debt-market readings", "Borrower stress components", "Lender stress components"]
    with st.expander("Finance data", expanded=False):
        view = st.radio("Ledger", options, horizontal=True, key="finance-ledger-view")
        if view == "Private-fund records":
            frame = _private_capital_detail_table(realization.get("funds", pd.DataFrame()))
        elif view == "Debt-market readings":
            frame = _debt_market_source_rows(debt_markets_data)
        elif view == "Borrower stress components":
            frame = _borrower_strain_component_table(borrower_strain)
        elif view == "Lender stress components":
            frame = _lender_strain_component_table(lender_strain)
        else:
            frame = filtered_ledger(commercialization_data, pillars=["Revenue realization", "Cost pressure", "Capital burden"])
        st.dataframe(arrow_safe_dataframe(frame), width="stretch", hide_index=True, height=440)

def render_finance_tab(sector_metrics, sector_data, fred_data, regime_metrics, nfci_history, debt_markets_data, dashboard_data, commercialization_data=None, tab_read=None):
    del sector_metrics, sector_data
    inject_panel_height_rules({})
    render_tab_header(
        "Finance",
        "Funding capacity, reported AI revenue and demand, private-market cash returns, credit conditions, and balance-sheet stress.",
        "SEC / company disclosures / CalSTRS / ILPA / FRED / New York Fed / Chicago Fed",
    )
    _render_floating_terms("finance")
    render_domain_read(tab_read, label="Read", domain="finance")

    render_section(
        "Funding capacity",
        "Internal funding capacity, cash reserves, debt formation, and future commitments.",
        first=True,
    )
    _render_funding_section(regime_metrics)
    _render_commercial_realization(commercialization_data)

    render_section(
        "Private-market cash returns",
        "Cash distributions and remaining NAV across technology and AI-adjacent private funds.",
    )
    _render_private_capital_realization()

    render_section(
        "Credit conditions",
        "Corporate-bond stress and the Chicago Fed financial-conditions indexes.",
    )
    _render_debt_markets(debt_markets_data)
    _render_nfci(fred_data, nfci_history)

    render_section(
        "Borrower and lender stress",
        "Borrower balance sheets and lender credit channels.",
    )
    trends = (dashboard_data or {}).get("trends", {}) or {}
    borrower_strain = (regime_metrics or {}).get("Borrower Strain Components", {}) or {}
    lender_strain = (regime_metrics or {}).get("Lender Strain Components", {}) or {}
    borrower_trend = trends.get("borrower_strain_trend", {})
    lender_trend = trends.get("lender_strain_trend", {})

    left, right = st.columns(2)
    with left:
        _render_financial_condition_summary(title="Borrower Strain", value=_value(regime_metrics, "Borrower Strain"), trend=borrower_trend, live_sources="YFinance + EDGAR")
    with right:
        _render_financial_condition_summary(title="Lender Strain", value=_value(regime_metrics, "Lender Strain"), trend=lender_trend, live_sources="FRED + SEC")

    stress_view = st.radio("Stress detail", ["Borrower", "Lender"], horizontal=True, label_visibility="collapsed", key="finance-view-stress-detail")
    if stress_view == "Lender":
        _render_financial_condition_detail(title="Lender Strain", trend=lender_trend, components=lender_strain.get("components", {}), detail_table=pd.DataFrame())
    else:
        _render_financial_condition_detail(title="Borrower Strain", trend=borrower_trend, components=borrower_strain.get("components", {}), detail_table=pd.DataFrame())

    _render_finance_ledger(commercialization_data, debt_markets_data, borrower_strain, lender_strain)

