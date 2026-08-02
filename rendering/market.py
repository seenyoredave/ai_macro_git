from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from analytics.hhi_engine import sector_hhi_component_breakdown
from analytics.sector_assessment import select_current_sector_assessment
from config.factor_config import FACTOR_DISPLAY_NAMES
from rendering.dataframe import arrow_safe_dataframe
from rendering.labels import sector_display_name
from rendering.charts_market import earnings_support_map, pressure_component_chart, sector_factor_chart, speculative_load_matrix
from rendering.common import _forward_multiple_text, _render_tab_metric_registry
from rendering.components import fmt_number, render_line_break, render_panel_heading, render_section, render_statline, render_tab_header
from rendering.sector import render_ticker_controls
from rendering.tables import _company_table

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
                (
                    f"Applied HHI · raw {fmt_number(metrics.get('Sector Raw HHI'), 3)} · "
                    f"{int(metrics.get('Sector Concentration Company Count', 0) or 0)} firms"
                ),
            ),
        ],
        key_prefix="sector-dossier-summary-structure",
    )
    factors_col, pressure_col = st.columns(2)
    with factors_col:
        with st.container(border=True):
            render_panel_heading("AEI factor structure", "Valuation · relative return · market breadth")
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
            render_panel_heading("Trading-pressure structure", "Valuation stretch · price extension · momentum · volatility · volume")
            st.plotly_chart(
                pressure_component_chart(metrics.get("Pressure Components", pd.DataFrame())),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key="sector-detail-trading-pressure-structure",
            )

    st.markdown("<br>", unsafe_allow_html=True)
    render_panel_heading(f"{sector_display_name(selected)} companies", "YFinance + SEC EDGAR")
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
        "YFinance + SEC EDGAR",
    )
    render_line_break()
    _render_tab_metric_registry("market")
    render_section("Cross-sector state", "Leading and lagging sectors across equity strength and trading pressure.")
    render_statline(_assessment_stats(macro_df, sector_data), key_prefix="sector-cross-state")

    render_section("Positioning", "Valuation support, realized repricing, equity strength, and trading pressure in cross section.", compact=True)
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
