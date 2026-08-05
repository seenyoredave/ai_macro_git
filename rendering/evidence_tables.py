from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from rendering.common import _forward_multiple_text
from rendering.dataframe import arrow_safe_dataframe
from rendering.labels import sector_display_name

def fmt_percent(value):
    value = pd.to_numeric(value, errors="coerce")
    return "No Data" if pd.isna(value) else f"{value * 100:.1f}%"

def fmt_multiple(value):
    value = pd.to_numeric(value, errors="coerce")
    return "No Data" if pd.isna(value) else f"{value:.1f}x"

def fmt_decimal(value):
    value = pd.to_numeric(value, errors="coerce")
    return "No Data" if pd.isna(value) else f"{value:.2f}"

def fmt_dollars(value):
    value = pd.to_numeric(value, errors="coerce")
    if pd.isna(value):
        return "No Data"
    magnitude = abs(float(value))
    if magnitude >= 1e12:
        return f"${value / 1e12:.2f}T"
    if magnitude >= 1e9:
        return f"${value / 1e9:.1f}B"
    if magnitude >= 1e6:
        return f"${value / 1e6:.1f}M"
    return f"${value:,.0f}"

def _fmt_signed(value, decimals=2):
    value = pd.to_numeric(value, errors="coerce")
    return "No Data" if pd.isna(value) else f"{value:+.{decimals}f}"

def build_sector_scoreboard_table(macro_df):
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
    if macro_df is None or macro_df.empty:
        return pd.DataFrame(columns=required)

    available = [column for column in required if column in macro_df.columns]
    table = macro_df[available].copy()
    if "Sector" in table.columns:
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
    if "AEI" in table.columns:
        table = table.sort_values("AEI", ascending=False, na_position="last")
    return table


def render_sector_scoreboard(macro_df):
    with st.container(border=True):
        st.dataframe(
            arrow_safe_dataframe(build_sector_scoreboard_table(macro_df)),
            width="stretch",
            hide_index=True,
            height=460,
        )


def _component_table(component_group):
    rows = []
    for name, payload in (component_group or {}).items():
        payload = payload or {}
        rows.append({
            "Component": name,
            "Score": fmt_decimal(payload.get("score", np.nan)),
            "Weight": fmt_percent(payload.get("weight", np.nan)),
            "Primary Raw": fmt_decimal(payload.get("raw", np.nan)),
            "Secondary Raw": fmt_decimal(payload.get("secondary_raw", np.nan)),
            "Observations": payload.get("observations", ""),
        })
    return pd.DataFrame(rows)

def _lender_strain_component_table(lender_strain_result):
    components = (lender_strain_result or {}).get("components", {}) or {}
    rows = []

    for name, payload in components.items():
        raw = payload.get("raw", np.nan)
        secondary = payload.get("secondary_raw", np.nan)

        if name == "Bank Credit Tightening":
            measure = f"SLOOS net tightening: {fmt_decimal(raw)}%"
        elif name == "Bank Capital Strain":
            measure = f"Regulatory Tier 1 capital / risk-weighted assets: {fmt_decimal(raw)}%"
        elif name == "Private Credit Impairment":
            portfolio_cost = pd.to_numeric(
                payload.get("portfolio_cost_mm", np.nan), errors="coerce"
            )
            observations = payload.get("observations", "")
            measure = (
                f"BDC non-accruals at cost: {fmt_decimal(raw)}%; "
                f"{observations} lenders; portfolio cost {fmt_dollars(portfolio_cost * 1e6)}"
            )
        else:
            reported_assets = pd.to_numeric(
                payload.get("reported_assets_bn", np.nan), errors="coerce"
            )
            measure = (
                f"High-leverage portfolio share: {fmt_decimal(raw)}%; "
                f"PIK / borrowings: {fmt_decimal(secondary)}%; "
                f"reported assets {fmt_dollars(reported_assets * 1e9)}"
            )

        normalization = payload.get("normalization", {}) or {}
        if name == "PE Portfolio Financing Strain":
            methods = sorted(
                {
                    str(item.get("method"))
                    for item in normalization.values()
                    if isinstance(item, dict) and item.get("method")
                }
            )
            normalization_text = " / ".join(methods)
        else:
            normalization_text = str(normalization.get("method", ""))

        rows.append({
            "Component": name,
            "Score": _fmt_signed(payload.get("score", np.nan), decimals=1),
            "Intended Weight": fmt_percent(payload.get("weight", np.nan)),
            "Active Weight": fmt_percent(payload.get("active_weight", np.nan)),
            "Current Measure": measure,
            "Normalization": normalization_text,
            "As Of": payload.get("as_of", ""),
            "Source": payload.get("source", ""),
        })

    return pd.DataFrame(rows)

def _borrower_strain_component_table(borrower_strain_result):
    components = (borrower_strain_result or {}).get("components", {}) or {}
    rows = []

    for name, payload in components.items():
        raw = payload.get("raw", np.nan)
        secondary = payload.get("secondary_raw", np.nan)
        total = payload.get("obligation_total", np.nan)

        if name == "Cash Flow Strain":
            measure = (
                f"sum(FCF)/sum(Revenue) = {fmt_percent(raw)}; "
                f"sum(CapEx)/sum(OCF) = {fmt_multiple(secondary)}"
            )
        elif name == "Debt Capacity Strain":
            positive_count = payload.get("positive_ebitda_companies", 0)
            impaired_count = payload.get("impaired_companies", 0)
            net_cash_count = payload.get("net_cash_companies", 0)
            measure = (
                f"Positive-EBITDA net leverage = {fmt_multiple(raw)}; "
                f"negative-EBITDA net debt/revenue = {fmt_multiple(secondary)}; "
                f"branches {positive_count}/{impaired_count}/{net_cash_count}"
            )
        elif name == "Committed Burden":
            measure = (
                f"sum(Commitments)/sum(OCF) = {fmt_multiple(raw)}; "
                f"sum(Commitments) = {fmt_dollars(total)}"
            )
        else:
            measure = (
                f"sum(Contingent Exposure)/sum(OCF) = {fmt_multiple(raw)}; "
                f"sum(Contingent Exposure) = {fmt_dollars(total)}"
            )

        rows.append({
            "Component": name,
            "Score": _fmt_signed(payload.get("score", np.nan), decimals=1),
            "Weight": fmt_percent(payload.get("weight", np.nan)),
            "Current Measure": measure,
            "Companies": payload.get("observations", 0),
        })

    return pd.DataFrame(rows)

def render_macro_data(fred_data):
    if not fred_data:
        st.warning("No FRED data available")
        return

    rows = []
    for indicator, payload in fred_data.items():
        if isinstance(payload, dict):
            value = payload.get("value", None)
            date = payload.get("date", None)
        else:
            value = payload
            date = None
        rows.append({"Indicator": indicator, "Value": value, "Date": date})

    with st.expander("FRED Data", expanded=False):
        st.dataframe(arrow_safe_dataframe(pd.DataFrame(rows)), width="stretch", hide_index=True)
        st.caption("Market data cache: 1 hour | FRED cache: 24 hours")

def render_edgar_data(sector_data):
    if not sector_data:
        st.warning("No EDGAR data available")
        return

    rows = []
    for sector, df in sector_data.items():
        if df is None or df.empty:
            continue

        cols = [
            "Ticker",
            "Company",
            "Market Cap",
            "Revenue",
            "Revenue Growth",
            "CapEx",
            "CapEx Growth",
        ]
        available = [col for col in cols if col in df.columns]
        sector_snapshot = df[available].copy()
        sector_snapshot.insert(0, "Sector", sector_display_name(sector))
        rows.append(sector_snapshot)

    if not rows:
        st.warning("No EDGAR rows available")
        return

    with st.expander("EDGAR Data", expanded=False):
        st.dataframe(arrow_safe_dataframe(pd.concat(rows, ignore_index=True)), width="stretch", hide_index=True)
