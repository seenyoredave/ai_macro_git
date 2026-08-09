from __future__ import annotations

import html

import numpy as np
import pandas as pd
import streamlit as st

from analytics.market_ledger import build_market_ledger
from analytics.sector_assessment import select_current_sector_assessment
from config.factor_config import FACTOR_DISPLAY_NAMES
from rendering.visual_system import render_plotly_chart
from rendering.dataframe import arrow_safe_dataframe
from rendering.labels import sector_display_name
from rendering.charts_market import (
    concentration_history_chart,
    earnings_support_map,
    market_ownership_treemap,
    participation_history_chart,
    return_contribution_chart,
    sector_signal_anatomy_chart,
    speculative_load_matrix,
)
from rendering.common import _forward_multiple_text, _render_floating_terms
from rendering.components import fmt_date, fmt_number, inject_panel_height_rules, render_domain_read, render_panel_heading, render_section, render_signal_rail, render_statline, render_tab_header
from rendering.sector_dossier import (
    build_sector_narrative,
    build_structure_interpretation,
    build_structure_snapshot,
)
from rendering.tables import _company_table


def _inject_market_page_theme() -> None:
    """Apply a contained visual system to Market-tab panels and stat cards."""
    st.markdown(
        """
        <style>
        div[class*="st-key-market-panel-"] {
            border-color: rgba(148, 163, 184, 0.17) !important;
            background: rgba(17, 24, 39, 0.78) !important;
            box-shadow: inset 0 1px 0 rgba(167, 139, 250, 0.055) !important;
        }
        div[class*="st-key-market-panel-"] [data-testid="stPlotlyChart"] {
            margin-top: -0.12rem;
        }
        div[class*="st-key-statline-market-ledger-"],
        div[class*="st-key-statline-sector-cross-state-"],
        div[class*="st-key-statline-sector-dossier-"] {
            border-top-color: rgba(167, 139, 250, 0.86) !important;
        }
        .rm-sector-read {
            border: 1px solid rgba(167, 139, 250, 0.22);
            border-left: 3px solid #a78bfa;
            border-radius: 0 13px 13px 0;
            background: linear-gradient(90deg, rgba(124, 58, 237, 0.12), rgba(17, 24, 39, 0.64));
            padding: 0.82rem 1rem 0.86rem 1rem;
            margin: 0.15rem 0 0.95rem 0;
        }
        .rm-sector-read-kicker {
            color: #a78bfa;
            font-size: 0.64rem;
            font-weight: 800;
            letter-spacing: 0.11em;
            text-transform: uppercase;
        }
        .rm-sector-read-title {
            color: #f8fafc;
            font-size: 1.02rem;
            font-weight: 760;
            margin-top: 0.18rem;
        }
        .rm-sector-read-copy {
            color: #b9c3d2;
            font-size: 0.82rem;
            line-height: 1.48;
            margin-top: 0.2rem;
        }
        .rm-sector-read-weekly {
            border-top: 1px solid rgba(148, 163, 184, 0.14);
            color: #aab5c5;
            font-size: 0.76rem;
            line-height: 1.45;
            margin-top: 0.62rem;
            padding-top: 0.58rem;
        }
        .rm-sector-read-weekly span {
            color: #60a5fa;
            font-size: 0.62rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            margin-right: 0.28rem;
            text-transform: uppercase;
        }
        .rm-sector-read-reference {
            font-size: 0.68rem;
            margin-top: 0.28rem;
        }
        .rm-sector-read-reference a { color: #93c5fd; text-decoration: none; }
        .rm-sector-structure-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.52rem;
            margin-top: 0.55rem;
        }
        .rm-sector-structure-item {
            border: 1px solid rgba(148, 163, 184, 0.13);
            border-radius: 10px;
            background: rgba(15, 23, 42, 0.50);
            padding: 0.62rem 0.68rem;
            min-height: 67px;
        }
        .rm-sector-structure-label {
            color: #8591a5;
            font-size: 0.61rem;
            font-weight: 800;
            letter-spacing: 0.075em;
            text-transform: uppercase;
        }
        .rm-sector-structure-value {
            color: #eef2f7;
            font-size: 1.15rem;
            font-weight: 740;
            margin-top: 0.16rem;
        }
        .rm-sector-structure-note {
            border-top: 1px solid rgba(148, 163, 184, 0.13);
            color: #9ca8ba;
            font-size: 0.75rem;
            line-height: 1.45;
            margin-top: 0.72rem;
            padding-top: 0.68rem;
        }
        div[class*="st-key-market-panel-sector-structure"] {
            min-height: 505px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _assessment_stats(macro_df, sector_data):
    selections = select_current_sector_assessment(macro_df, sector_data=sector_data)
    rows = selections.get("rows", {})
    stats = []
    assessment_labels = (
        ("Most Crowded", "Highest Trading Pressure"),
        ("Fastest Mover", "Fastest Sector Movement"),
        ("Biggest Risk", "Broadest Deterioration"),
    )
    for source_label, display_label in assessment_labels:
        row = rows.get(source_label)
        if row is None:
            stats.append((display_label, "n/a", "insufficient eligible data"))
            continue
        sector = sector_display_name(row.get("Sector"))
        if source_label == "Most Crowded":
            note = f"Pressure {fmt_number(row.get('Pressure'), 0)}"
        elif source_label == "Fastest Mover":
            delta_score = pd.to_numeric(row.get('_Delta Sector Score'), errors='coerce')
            delta_pressure = pd.to_numeric(row.get('_Delta Pressure'), errors='coerce')
            movement = pd.to_numeric(row.get('_Abs Sector Movement'), errors='coerce')
            prior_date = fmt_date(row.get('_Movement Prior Date'))
            latest_date = fmt_date(row.get('_Movement Latest Date'))
            note = (
                f"Movement {fmt_number(movement, 1)} · "
                f"ΔAEI {fmt_number(delta_score, 1, signed=True)} · "
                f"ΔPressure {fmt_number(delta_pressure, 1, signed=True)} · "
                f"{prior_date}–{latest_date}"
            )
        else:
            note = f"Deterioration breadth {fmt_number(row.get('Risk Breadth Score'), 0)}%"
        stats.append((display_label, sector, note))

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
        stats.append(("Most Concentrated Basket", "n/a", "insufficient market-cap coverage"))
    else:
        note = f"Adjusted HHI {fmt_number(concentration.get('Sector Basket Concentration'), 1)}"
        stats.append((
            "Most Concentrated Basket",
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

def _render_sector_read(metrics: dict, selected: str, df: pd.DataFrame, peer_metrics: dict, weekly_context=None, movement=None) -> None:
    narrative = build_sector_narrative(metrics, selected, sector_display_name(selected), df, peer_metrics, weekly_context, movement)
    headline = narrative["headline"]
    sentence = narrative["body"]
    weekly_note = narrative.get("weekly_note")
    reference = narrative.get("reference")
    weekly_html = ""
    if weekly_note:
        reference_html = ""
        citation = ""
        if reference:
            url = str(reference.get("source_url") or "")
            label = str(reference.get("source_label") or reference.get("source_name") or "Source")
            if url.startswith("https://"):
                citation = " [1]"
                reference_html = (
                    f'<div class="rm-sector-read-reference"><a href="{html.escape(url, quote=True)}" '
                    f'target="_blank" rel="noopener noreferrer">[1] {html.escape(label)}</a></div>'
                )
        weekly_html = (
            f'<div class="rm-sector-read-weekly"><span>This week</span> '
            f'{html.escape(weekly_note)}{citation}</div>{reference_html}'
        )
    st.markdown(
        f"""
        <div class="rm-sector-read">
            <div class="rm-sector-read-kicker">Sector read</div>
            <div class="rm-sector-read-title">{html.escape(headline)}</div>
            <div class="rm-sector-read-copy">{html.escape(sentence)}</div>
            {weekly_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_structure_snapshot(metrics: dict, company_count: int) -> None:
    items = build_structure_snapshot(metrics, company_count)
    cells = "".join(
        (
            '<div class="rm-sector-structure-item">'
            f'<div class="rm-sector-structure-label">{html.escape(label)}</div>'
            f'<div class="rm-sector-structure-value">{html.escape(value)}</div>'
            '</div>'
        )
        for label, value in items
    )
    interpretation = build_structure_interpretation(metrics)
    st.markdown(
        (
            f'<div class="rm-sector-structure-grid">{cells}</div>'
            f'<div class="rm-sector-structure-note">{html.escape(interpretation)}</div>'
        ),
        unsafe_allow_html=True,
    )


def _render_sector_detail(sector_data, sector_metrics, macro_df, weekly_context=None):
    sectors = [
        sector for sector in sector_metrics
        if sector in sector_data and sector_data[sector] is not None and not sector_data[sector].empty
    ]
    if not sectors:
        st.warning("No sector detail is available.")
        return None

    selected = st.selectbox(
        "Sector",
        sectors,
        format_func=sector_display_name,
        key="research-overlay-sector",
    )
    metrics = sector_metrics[selected]
    df = sector_data[selected]
    company_count = int(df["Ticker"].nunique()) if "Ticker" in df.columns else int(len(df))
    strategy = metrics.get("Cycle Strategy", {}) or {}
    pressure_note = _pressure_movement_text(macro_df, selected)
    return_rank = _rank_text(macro_df, selected, "Avg Return", ascending=False)
    multiple_rank = _rank_text(macro_df, selected, "Forward EV/EBIT", ascending=False)

    render_statline(
        [
            ("Sector AEI", fmt_number(metrics.get("Sector Score"), 1), strategy.get("regime", "n/a")),
            ("Trading Pressure", fmt_number(metrics.get("Sector Pressure"), 1), pressure_note),
            (
                "1Y Return",
                fmt_number(
                    pd.to_numeric(metrics.get("Avg Return"), errors="coerce") * 100,
                    1,
                    signed=True,
                    suffix="%",
                ),
                return_rank,
            ),
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
    movement_frame = select_current_sector_assessment(macro_df, sector_data={}).get("movement", pd.DataFrame())
    movement_row = movement_frame.loc[movement_frame["Sector"].astype(str).eq(str(selected))].iloc[0].to_dict() if movement_frame is not None and not movement_frame.empty and "Sector" in movement_frame.columns and movement_frame["Sector"].astype(str).eq(str(selected)).any() else {}
    _render_sector_read(metrics, selected, df, sector_metrics, weekly_context, movement_row)

    signal_col, structure_col = st.columns([1.65, 0.85])
    with signal_col:
        with st.container(border=True, key="market-panel-sector-signal-anatomy"):
            render_panel_heading(
                "Sector score components",
                "AEI drivers and trading pressure · common 0–100 scale",
            )
            factor_frame = metrics.get("Scored Factors", pd.DataFrame()).copy()
            if not factor_frame.empty and "Factor" in factor_frame.columns:
                factor_frame["Factor"] = factor_frame["Factor"].map(
                    lambda name: FACTOR_DISPLAY_NAMES.get(
                        name,
                        str(name).replace("_", " ").title(),
                    )
                )
            render_plotly_chart(
                sector_signal_anatomy_chart(
                    factor_frame,
                    metrics.get("Pressure Components", pd.DataFrame()),
                ),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key="sector-detail-signal-anatomy",
            )

    with structure_col:
        with st.container(border=True, key="market-panel-sector-structure"):
            render_panel_heading(
                "Market structure",
                f"{company_count} included companies",
            )
            _render_structure_snapshot(metrics, company_count)

    return {"sector": selected, "frame": df, "company_count": company_count}


def _market_ledger_stats(ledger):
    metrics = (ledger or {}).get("metrics", {}) or {}
    company_count = int(metrics.get("company_count", 0) or 0)
    return_count = int(metrics.get("return_count", 0) or 0)
    positive_count = int(round(
        float(metrics.get("positive_breadth", 0.0) or 0.0) * return_count
    ))
    return [
        (
            "Top 6 Share",
            fmt_number(pd.to_numeric(metrics.get("top_6_share"), errors="coerce") * 100.0, 1, suffix="%"),
            f"6 of {company_count} companies",
        ),
        (
            "Top 10 Share",
            fmt_number(pd.to_numeric(metrics.get("top_10_share"), errors="coerce") * 100.0, 1, suffix="%"),
            f"10 of {company_count} companies",
        ),
        (
            "Effective Firms",
            fmt_number(metrics.get("effective_firms"), 1),
            (
                f"Raw HHI {fmt_number(metrics.get('raw_hhi'), 3)} · "
                f"normalized {fmt_number(metrics.get('normalized_hhi'), 1)}"
            ),
        ),
        (
            "Positive 1Y Breadth",
            fmt_number(pd.to_numeric(metrics.get("positive_breadth"), errors="coerce") * 100.0, 1, suffix="%"),
            f"{positive_count} of {return_count} companies",
        ),
    ]


def _history_label(metadata):
    metadata = metadata or {}
    start = metadata.get("start_date")
    end = metadata.get("end_date")
    if not start or not end:
        return "Comparable market history"
    return f"Market structure · {start} to {end}"


def _one_year_return_label(metadata):
    metadata = metadata or {}
    as_of_date = metadata.get("as_of_date")
    company_count = int(metadata.get("company_count", 0) or 0)
    universe_count = int(metadata.get("universe_count", 0) or 0)
    coverage = (
        f"{company_count} of {universe_count} companies"
        if universe_count > 0
        else "Company contribution"
    )
    return f"{coverage} · as of {as_of_date}" if as_of_date else coverage


def _render_market_ledger_summary(ledger):
    metrics = (ledger or {}).get("metrics", {}) or {}
    company_count = int(metrics.get("company_count", 0) or 0)
    sector_count = int(metrics.get("sector_count", 0) or 0)
    coverage = pd.to_numeric(metrics.get("cap_coverage"), errors="coerce")
    coverage_text = fmt_number(coverage * 100.0, 0, suffix="%")
    render_section(
        "Current market conditions",
        (
            f"Current ownership concentration and participation across {sector_count} sectors and "
            f"{company_count} unique companies · {coverage_text} market-cap coverage."
        ),
        first=True,
    )
    render_statline(_market_ledger_stats(ledger), key_prefix="market-ledger")


def _render_market_structure(ledger):
    history_meta = (ledger or {}).get("history_metadata", {}) or {}
    return_meta = (ledger or {}).get("return_metadata", {}) or {}

    render_section(
        "Ownership and participation",
        "Market value concentration, return contribution, and breadth across the covered public-equity universe.",
    )
    with st.container(key="market-structure-signature"):
        left, right = st.columns(2, gap="large")
        with left:
            with st.container(border=True, key="market-panel-ownership"):
                render_panel_heading("Market value concentration", "Industry leaders by sector")
                render_plotly_chart(
                    market_ownership_treemap((ledger or {}).get("companies", pd.DataFrame())),
                    width="stretch",
                    config={"displayModeBar": False, "responsive": True},
                    key="market-ownership-treemap-v3",
                )
        with right:
            with st.container(border=True, key="market-panel-return-contribution"):
                render_panel_heading("One-year return contribution", _one_year_return_label(return_meta))
                render_plotly_chart(
                    return_contribution_chart((ledger or {}).get("contributions", pd.DataFrame())),
                    width="stretch",
                    config={"displayModeBar": False, "responsive": True},
                    key="market-return-contribution-1y",
                )

        lower_left, lower_right = st.columns(2, gap="large")
        with lower_left:
            with st.container(border=True, key="market-panel-concentration-history"):
                render_panel_heading("Market concentration", _history_label(history_meta))
                render_plotly_chart(
                    concentration_history_chart((ledger or {}).get("history", pd.DataFrame())),
                    width="stretch",
                    config={"displayModeBar": False, "responsive": True},
                    key="market-concentration-history",
                )
        with lower_right:
            with st.container(border=True, key="market-panel-participation-history"):
                render_panel_heading("Large companies versus the broader market", _history_label(history_meta))
                render_plotly_chart(
                    participation_history_chart((ledger or {}).get("history", pd.DataFrame())),
                    width="stretch",
                    config={"displayModeBar": False, "responsive": True},
                    key="market-participation-history",
                )


def _render_market_constituent_ledger(selection: dict | None, ledger: dict) -> None:
    render_section(
        "Underlying company data",
        "Company-level records behind the ownership, return, and sector views.",
    )
    with st.expander("Company records", expanded=False):
        options = ["Selected sector", "Full market universe"] if selection else ["Full market universe"]
        view = st.radio(
            "Constituent view",
            options,
            horizontal=True,
            label_visibility="collapsed",
            key="market-constituent-ledger-view",
        )
        if view == "Selected sector" and selection:
            st.caption(
                f"{sector_display_name(selection['sector'])} · {selection['company_count']} included companies · monetary values in USD millions."
            )
            frame = _company_table(selection["frame"])
        else:
            st.caption("Full market-ledger company universe used by the ownership and contribution views.")
            frame = (ledger or {}).get("companies", pd.DataFrame())
        st.dataframe(
            arrow_safe_dataframe(frame),
            width="stretch",
            hide_index=True,
            height=460,
        )


def render_market_tab(sector_metrics, sector_data, regime_metrics, dashboard_data, market_universe_summary=None, weekly_context=None, tab_read=None):
    del regime_metrics
    macro_df = dashboard_data["macro_df"]
    market_ledger = build_market_ledger(sector_data)
    _inject_market_page_theme()
    inject_panel_height_rules({
        "market-panel-ownership": 575,
        "market-panel-return-contribution": 575,
        "market-panel-concentration-history": 405,
        "market-panel-participation-history": 405,
        "market-panel-earnings-support": 470,
        "market-panel-speculative-load": 470,
        "market-panel-sector-signal-anatomy": 505,
        "market-panel-sector-structure": 505,
    })
    render_tab_header(
        "Market",
        "Public-market value, return concentration, breadth, sector valuations, and company-level fundamentals.",
        "YFinance + SEC EDGAR",
    )
    _render_floating_terms("market")
    render_domain_read(tab_read, label="Read", domain="market")
    _render_market_ledger_summary(market_ledger)
    render_signal_rail(_assessment_stats(macro_df, sector_data), key_prefix="sector-cross-state")
    _render_market_structure(market_ledger)

    render_section("Sector valuations and trading", "Valuation, earnings, returns, and trading pressure across sectors.")
    left, right = st.columns(2)
    with left:
        with st.container(border=True, key="market-panel-earnings-support"):
            render_panel_heading(
                "Earnings Support",
                "Trailing repricing relative to the profitable operating-earnings base",
            )
            render_plotly_chart(
                earnings_support_map(macro_df),
                width="stretch",
                config={"responsive": True},
                key="sectors-earnings-support",
            )
    with right:
        with st.container(border=True, key="market-panel-speculative-load"):
            render_panel_heading(
                "Speculative Load",
                "Abnormal trading pressure relative to sustained, broad-based equity strength",
            )
            render_plotly_chart(
                speculative_load_matrix(macro_df),
                width="stretch",
                config={"responsive": True},
                key="sectors-speculative-load",
            )


    render_section(
        "Sector profile",
        "Select a sector to see its drivers, market structure, fundamentals, and trading pressure.",
    )
    selection = _render_sector_detail(sector_data, sector_metrics, macro_df, weekly_context)
    _render_market_constituent_ledger(selection, market_ledger)
