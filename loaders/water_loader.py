from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from config.debug_config import debug_print
from water.sources import load_source_manifest
from water.refresh import refresh_water_sources

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
def load_water_utilization_data(
    force_refresh: bool = False,
    refresh_token: int = 0,
    allow_live: bool = False,
) -> dict:
    del refresh_token
    live_refresh = bool(force_refresh and allow_live)
    refresh_report = refresh_water_sources() if live_refresh else {}
    summary_path = DERIVED / "water_national_summary.json"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    except Exception as exc:
        debug_print(f"Water ledger summary load failed -> {exc}")
        summary = {}

    manifest = load_source_manifest(WATER_ROOT / "source_manifest.csv", project_root=ROOT)
    active = (
        manifest.loc[manifest.get("ingestion_status", "").eq("active")].copy()
        if not manifest.empty
        else pd.DataFrame()
    )
    acceptable_health = {"retained_and_validated", "retained_query_cache"}
    source_health = "validated"
    if active.empty or not active.get("source_health", pd.Series(dtype=str)).isin(acceptable_health).all():
        source_health = "degraded"

    return {
        "source_mode": str(refresh_report.get("source_mode") or "retained_local"),
        "refresh_report": refresh_report,
        # Local sources need the facility registry, so their live refresh is
        # executed by analytics.spatial_context.attach_water_context after the
        # infrastructure registry has been assembled.
        "local_context_refresh_requested": live_refresh,
        "source_health": source_health,
        "summary": summary,
        "source_manifest": manifest,
        "field_dictionary": (
            pd.read_csv(WATER_ROOT / "field_dictionary.csv")
            if (WATER_ROOT / "field_dictionary.csv").exists()
            else pd.DataFrame()
        ),
        "usgs_2020_top_withdrawals": _read_csv("usgs_2020_top_withdrawals.csv"),
        "usgs_national_categories": _read_csv("usgs_2015_national_category_summary.csv"),
        "usgs_state_categories": _read_csv("usgs_2015_state_category_summary.csv"),
        "usgs_counties": _read_csv("usgs_2015_county_summary.csv.gz", dtype={"FIPS": str}),
        "usgs_reconciliation": _read_csv("usgs_2015_reconciliation.csv.gz"),
        "eia_plants": _read_csv("eia_2024_thermoelectric_plant_summary.csv.gz"),
        "eia_groups": _read_csv("eia_2024_thermoelectric_group_summary.csv"),
        # Legacy state snapshot remains available for compatibility and as a
        # fallback when current county statistics cannot be resolved.
        "usdm_state_drought": _read_csv("usdm_state_drought_snapshot.csv"),
        "usdm_county_drought": _read_csv("usdm_county_drought_snapshot.csv.gz", dtype={"FIPS": str}),
        "epa_pws_matches": _read_csv(
            "epa_pws_facility_matches.csv.gz",
            dtype={"PWSID": str, "Facility ID": str, "Query Key": str},
        ),
        "observation_count": int(summary.get("observation_rows", 0) or 0),
        "active_source_count": int(len(active)),
    }
