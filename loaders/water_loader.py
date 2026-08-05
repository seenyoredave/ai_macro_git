from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from config.debug_config import debug_print
from water.sources import load_source_manifest

ROOT = Path(__file__).resolve().parents[1]
WATER_ROOT = ROOT / "data/water"
DERIVED = WATER_ROOT / "derived"

def _read_csv(name: str, **kwargs) -> pd.DataFrame:
    path = DERIVED / name
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, **kwargs)
    except Exception as exc:
        debug_print(f"Water ledger table load failed ({name}) -> {exc}")
        return pd.DataFrame()

@st.cache_data(show_spinner=False)
def load_water_utilization_data() -> dict:
    summary_path = DERIVED / "water_national_summary.json"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    except Exception as exc:
        debug_print(f"Water ledger summary load failed -> {exc}")
        summary = {}

    manifest = load_source_manifest(WATER_ROOT / "source_manifest.csv", project_root=ROOT)
    active = manifest.loc[manifest.get("ingestion_status", "").eq("active")].copy() if not manifest.empty else pd.DataFrame()
    source_health = "validated"
    if active.empty or not active.get("source_health", pd.Series(dtype=str)).eq("retained_and_validated").all():
        source_health = "degraded"

    return {
        "source_mode": "retained_local",
        "source_health": source_health,
        "summary": summary,
        "source_manifest": manifest,
        "field_dictionary": pd.read_csv(WATER_ROOT / "field_dictionary.csv") if (WATER_ROOT / "field_dictionary.csv").exists() else pd.DataFrame(),
        "usgs_2020_top_withdrawals": _read_csv("usgs_2020_top_withdrawals.csv"),
        "usgs_national_categories": _read_csv("usgs_2015_national_category_summary.csv"),
        "usgs_state_categories": _read_csv("usgs_2015_state_category_summary.csv"),
        "usgs_counties": _read_csv("usgs_2015_county_summary.csv.gz"),
        "usgs_reconciliation": _read_csv("usgs_2015_reconciliation.csv.gz"),
        "eia_plants": _read_csv("eia_2024_thermoelectric_plant_summary.csv.gz"),
        "eia_groups": _read_csv("eia_2024_thermoelectric_group_summary.csv"),
        "observation_count": int(summary.get("observation_rows", 0) or 0),
        "active_source_count": int(summary.get("active_sources", 0) or 0),
    }
