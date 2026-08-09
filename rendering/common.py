from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from config.metric_definitions import METRIC_DEFINITIONS
from rendering.labels import short_regime_label
from rendering.components import render_definition

def _value(regime_metrics, name):
    return pd.to_numeric((regime_metrics or {}).get(name, np.nan), errors="coerce")

def _display_text(value):
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
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.notna(numeric) and np.isfinite(numeric):
        return f"{numeric:.1f}x"
    status_text = str(status or "")
    if status_text.startswith("NM"):
        return "NM"
    return "n/a"

def _source(regime_metrics, prefix):
    return (regime_metrics or {}).get(f"{prefix} Source", "Unavailable")

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
        "Buildout Leadership Rotation",
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
    "data_center": [
        "U.S. Data Center Footprint",
        "Data Center Development Pipeline",
    ],
    "connectivity": [
        "U.S. Connectivity Transport Layer",
        "Submarine Cable System Coverage",
        "Internet Exchange Depth",
        "Middle-Mile Expansion",
        "Capacity-Connectivity Mismatch",
        "Campus Connectivity Proximity",
    ],
    "compute": [
        "Domestic Compute Manufacturing Output",
        "Compute Manufacturing Capacity Utilization",
        "U.S. Compute Manufacturing Investment",
    ],
    "grid_storage": [
        "Interconnection Pipeline",
        "Queue Conversion",
        "Advanced-Stage Queue Share",
        "Summer Reserve Margins",
        "Electric Storage Deployment",
        "Operating Storage Duration",
        "Electric Power Construction",
    ],
    "water": [
        "Freshwater Competition Context",
        "State Water Exposure",
        "Campus Water Exposure Dossier",
        "AI Water Evidence Ladder",
        "U.S. Water Utilization Ledger",
        "Thermoelectric Cooling-Water Records",
        "Wastewater System Investment",
    ],
    "power": [
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
        "Adult Generative-AI Use",
        "Personal Generative-AI Use",
        "Work Generative-AI Use",
        "Weekly Generative-AI Use",
        "Daily Generative-AI Use",
        "Current Business AI Use",
        "Expected Business AI Use",
        "Expected Adoption Gap",
        "Adoption Breadth",
    ],
    "workforce": [
        "AI-Linked Employment Footprint",
        "LLM Task Exposure Benchmark",
        "Supporting Labor Demand",
        "Labor-Flow Rates",
        "AI-Linked Wage Trajectory",
        "Real Earnings Breadth",
        "Workforce Outcomes Matrix",
    ],
    "economic_impact": [
        "Labor Productivity",
        "Real Value-Added Output",
        "Real Hourly Compensation",
        "Labor Share",
        "Productivity–Compensation Gap",
        "Median Real Weekly Earnings",
        "Broad Participation",
        "Inflation-Adjusted Realized Growth",
        "Unit Labor Costs",
        "Information-Processing Investment",
    ],
    "market": [
        "Market Leadership Concentration",
        "Effective Firms",
        "Retained-Universe Market Return",
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

TERM_DISPLAY_NAMES = {
    "Retained-Universe Market Return": "AI-Equity Basket Return",
}

def _render_floating_terms(tab_key):
    """Place tab-specific definitions at the domain header's upper-right edge."""
    definitions = TAB_METRIC_REGISTRIES[tab_key]
    with st.popover(
        "Terms",
        key=f"floating-terms-{tab_key}",
        width="content",
        help="Definitions for this tab",
    ):
        selected = st.selectbox(
            "Metric or analytical product",
            definitions,
            key=f"research-{tab_key}-definition",
            label_visibility="collapsed",
            format_func=lambda name: TERM_DISPLAY_NAMES.get(name, name),
        )
        render_definition(METRIC_DEFINITIONS[selected])
