from __future__ import annotations

import pandas as pd

from rendering.components import fmt_date, fmt_number
from rendering.compute import _compute_index_change, _compute_index_value

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
            "Source": "U.S. Census Bureau Construction Spending",
        })
    inventory = (infrastructure_data or {}).get("data_center_inventory", {}) or {}
    national = inventory.get("broad_summary", {}) or {}
    pipeline = inventory.get("open_tracker_summary", {}) or {}
    rows.append({
        "Series": "U.S. Data Center Footprint",
        "Reading": f"{int(national.get('total', 0) or 0):,} facilities",
        "Change": (
            f"{int(national.get('operating', 0) or 0):,} operating · "
            f"{int(national.get('development', 0) or 0):,} in development"
        ),
        "Observation Date": fmt_date(national.get("observation_date")),
        "Source": "Pew Research Center / Data Center Map",
    })
    pipeline_mw = pd.to_numeric(pipeline.get("active_pipeline_published_mw"), errors="coerce")
    pipeline_mw_text = "published capacity unavailable" if pd.isna(pipeline_mw) else f"{pipeline_mw / 1000.0:,.1f} GW published capacity"
    rows.append({
        "Series": "Data Center Development Pipeline",
        "Reading": f"{int(pipeline.get('active_pipeline', 0) or 0):,} active projects",
        "Change": (
            f"{int(pipeline.get('proposed', 0) or 0):,} proposed · "
            f"{int(pipeline.get('approved_or_construction', 0) or 0):,} approved/construction · "
            f"{int(pipeline.get('expanding', 0) or 0):,} expanding · {pipeline_mw_text}"
        ),
        "Observation Date": fmt_date(pipeline.get("observation_date")),
        "Source": "FracTracker Alliance",
    })
    compute = (infrastructure_data or {}).get("compute_manufacturing", {}) or {}
    for name, item in (compute.get("series", {}) or {}).items():
        rows.append({
            "Series": name,
            "Reading": _compute_index_value(item, suffix="%" if "Utilization" in name else ""),
            "Change": _compute_index_change(item) if "Output" in name else "operating rate",
            "Observation Date": fmt_date(item.get("date")),
            "Source": "Federal Reserve G.17",
        })
    project_summary = compute.get("project_summary", {}) or {}
    rows.append({
        "Series": "U.S. Compute Manufacturing Investment",
        "Reading": f"${fmt_number(project_summary.get('expected_capex_usd_b'), 1)}B expected investment",
        "Change": (
            f"{int(project_summary.get('projects', 0) or 0):,} projects · "
            f"{int(project_summary.get('states', 0) or 0):,} states · "
            f"${fmt_number(project_summary.get('direct_funding_usd_b'), 1)}B direct awards"
        ),
        "Observation Date": "varies by project",
        "Source": "NIST CHIPS for America",
    })
    return pd.DataFrame(rows)
