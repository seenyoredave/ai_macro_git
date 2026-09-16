from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics.financial_conditions import nfci_direction, nfci_snapshot
from analytics.private_capital import build_private_capital_realization
from analytics.trend_engine import calc_trailing_point_change
from config.debt_markets_config import DEBT_MARKET_SERIES
from rendering.evidence_gateway import render_evidence_gateway
from rendering.visual_system import render_plotly_chart
from rendering.charts_common import COLORS, single_history
from rendering.charts_finance import (
    component_bars,
    debt_market_history,
    financial_conditions_history,
    funding_history,
    private_capital_realization_map,
)
from rendering.common import _value
from rendering.commercialization import metric_value
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
            f"{int(current.get('internal_funding_companies', 0) or 0)} companies · SEC filings",
        ),
        (
            "Cash reserve coverage",
            fmt_number(current.get("cash_reserve_coverage_years"), 2, suffix="y"),
            f"{int(current.get('cash_reserve_companies', 0) or 0)} companies · Cash / TTM CapEx",
        ),
        (
            "Debt change / CapEx",
            fmt_number(current.get("debt_financing_pulse"), 2, signed=True, suffix="x"),
            f"{int(current.get('debt_financing_companies', 0) or 0)} matched companies · SEC filings",
        ),
        (
            "Future commitments / CapEx",
            fmt_number(current.get("forward_commitment_load"), 2, suffix="x"),
            f"{int(current.get('commitment_companies', 0) or 0)} companies · EDGAR",
        ),
    ]


def _render_current_state(regime_metrics, debt_markets_data, fred_data, nfci_history):
    current = _funding_current(regime_metrics)
    bond = _debt_market_item(debt_markets_data, "Corporate Bond Market Distress")
    financial = nfci_snapshot(fred_data or {}, nfci_history)
    render_section(
        "Current state",
        "Capital deployment and broad financing conditions around the AI investment cycle.",
        first=True,
        compact=True,
    )
    render_statline(
        [
            (
                "TTM CapEx",
                _fmt_dollars(current.get("capex_total")),
                f"{int(current.get('cohort_companies', 0) or 0)} company cohort",
            ),
            (
                "Forward commitments",
                _fmt_dollars(current.get("forward_commitments_total")),
                "filing-backed commitments",
            ),
            (
                "Bond-market distress",
                fmt_number(bond.get("value"), 2),
                f"New York Fed CMDI · {fmt_date(bond.get('date'))}",
            ),
            (
                "Broad financial conditions",
                fmt_number(financial.get("value"), 3, signed=True),
                f"NFCI · {nfci_direction(financial.get('three_month_change'))}",
            ),
        ],
        key_prefix="finance-current-state",
    )


def _render_capital_capacity(regime_metrics):
    funding_mix = _funding_mix(regime_metrics)
    current = funding_mix.get("current", {}) or {}
    render_summary_row(
        _funding_capacity_stats(regime_metrics),
        key_prefix="finance-capital-capacity",
    )
    with st.container(border=True, key="finance-panel-funding-history"):
        render_panel_heading(
            "Current funding capacity",
            "Cash flow, cash reserves, debt changes, and future commitments relative to current capital spending",
        )
        render_plotly_chart(
            funding_history(funding_mix.get("history"), years=5),
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
            key="finance-funding-history",
        )
    debt_count = int(current.get("debt_financing_companies", 0) or 0)
    render_summary_row(
        [
            ("TTM CapEx", _fmt_dollars(current.get("capex_total")), f"{current.get('cohort_companies', 0)} cohort companies"),
            ("Total debt", _fmt_dollars(current.get("total_debt")), f"{debt_count} matched companies"),
            ("Prior-year debt", _fmt_dollars(current.get("prior_year_total_debt")), f"{debt_count} matched companies"),
            ("Forward commitments", _fmt_dollars(current.get("forward_commitments_total")), "filing-backed ledger"),
        ],
        key_prefix="finance-capital-totals",
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
            "10-year history · FRED and direct BDC data"
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

    with st.container(border=True, key="finance-panel-company-ai-disclosures"):
        render_panel_heading(
            "Company AI disclosures",
            "Reported AI revenue, backlog, margins, and demand indicators from company disclosures.",
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

def render_finance_tab(sector_metrics, sector_data, fred_data, regime_metrics, nfci_history, debt_markets_data, dashboard_data, commercialization_data=None, tab_read=None):
    del sector_metrics, sector_data
    inject_panel_height_rules({"finance-panel-funding-history": 405})
    render_tab_header(
        "Finance",
        "Cash flow, capital spending, debt, commitments, credit conditions, and private-fund returns.",
        "SEC / company disclosures / CalSTRS / ILPA / FRED / New York Fed / Chicago Fed",
        terms_key="finance",
    )
    render_domain_read(tab_read, label="Read", domain="finance")

    _render_current_state(regime_metrics, debt_markets_data, fred_data, nfci_history)

    render_section(
        "Funding capacity",
        "Operating cash flow, cash reserves, debt change, and disclosed commitments relative to capital spending.",
    )
    _render_capital_capacity(regime_metrics)

    render_section(
        "Company AI disclosures",
        "Reported AI revenue, backlog, margins, and demand indicators from company disclosures.",
    )
    _render_commercial_realization(commercialization_data)

    render_section(
        "Private-fund cash returns",
        "Distributions and remaining NAV for technology and AI-adjacent funds in the retained sample.",
    )
    _render_private_capital_realization()

    render_section(
        "Credit conditions",
        "Corporate-bond distress and Chicago Fed financial-conditions indexes.",
    )
    _render_debt_markets(debt_markets_data)
    _render_nfci(fred_data, nfci_history)

    render_section(
        "Borrower and lender stress",
        "Borrower balance-sheet strain and lender-side credit indicators.",
    )
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

    stress_view = st.radio(
        "Stress detail",
        ["Borrower", "Lender"],
        horizontal=True,
        label_visibility="collapsed",
        key="finance-view-stress-detail",
    )
    if stress_view == "Lender":
        _render_financial_condition_detail(
            title="Lender Strain",
            trend=lender_trend,
            components=lender_strain.get("components", {}),
            detail_table=pd.DataFrame(),
        )
    else:
        _render_financial_condition_detail(
            title="Borrower Strain",
            trend=borrower_trend,
            components=borrower_strain.get("components", {}),
            detail_table=pd.DataFrame(),
        )

    render_evidence_gateway("finance")

