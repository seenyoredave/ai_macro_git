"""Deterministic campus-level local water-constraint summaries."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _number(series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _capacity(frame: pd.DataFrame) -> pd.Series:
    candidates = ["Planned Data Center Capacity MW", "Published Capacity Estimate MW", "Published Capacity MW"]
    output = pd.Series(np.nan, index=frame.index, dtype=float)
    for column in candidates:
        if column in frame.columns:
            output = output.where(output.notna(), _number(frame[column]))
    return output.where(output > 0)


def local_water_constraint_summary(campus_context: pd.DataFrame | None) -> dict:
    frame = campus_context.copy() if isinstance(campus_context, pd.DataFrame) else pd.DataFrame()
    if frame.empty:
        return {
            "campuses": 0,
            "campuses_with_county_drought_data": 0,
            "service_area_query_resolved": 0,
            "service_area_overlap": 0,
            "authoritative_service_area_overlap": 0,
            "modeled_service_area_overlap": 0,
            "unclassified_service_area_overlap": 0,
            "service_area_provenance_classified_share": float("nan"),
            "ambiguous_service_area_overlap": 0,
            "direct_water_evidence": 0,
            "quantified_withdrawal": 0,
            "quantified_consumption": 0,
        }
    if "Campus ID" not in frame.columns or frame["Campus ID"].astype(str).duplicated().any():
        raise ValueError("Water context must contain one row per Campus ID")

    county_d2 = _number(frame.get("County D2+ Area Percent", pd.Series(np.nan, index=frame.index)))
    capacity = _capacity(frame)
    pws_resolved = frame.get("PWS Service Area Query Resolved", pd.Series(False, index=frame.index)).fillna(False).astype(bool)
    pws_overlap = frame.get("PWS Service Area Overlap", pd.Series(False, index=frame.index)).fillna(False).astype(bool)
    pws_authoritative = frame.get("PWS Authoritative Boundary Overlap", pd.Series(False, index=frame.index)).fillna(False).astype(bool)
    pws_modeled = frame.get("PWS Modeled Boundary Overlap", pd.Series(False, index=frame.index)).fillna(False).astype(bool)
    pws_ambiguous = frame.get("PWS Ambiguous Overlap", pd.Series(False, index=frame.index)).fillna(False).astype(bool)
    pws_unclassified = pws_overlap & ~pws_authoritative & ~pws_modeled
    pws_classified = pws_overlap & (pws_authoritative | pws_modeled)
    direct = frame.get("Direct Water Evidence", pd.Series(False, index=frame.index)).fillna(False).astype(bool)
    withdrawal = _number(frame.get("Water Withdrawal Gallons/Year", pd.Series(np.nan, index=frame.index))).notna()
    consumption = _number(frame.get("Water Consumption Gallons/Year", pd.Series(np.nan, index=frame.index))).notna()
    any_d2 = county_d2.gt(0)
    material_d2 = county_d2.ge(25)
    highest = frame.loc[county_d2.idxmax()] if county_d2.notna().any() else pd.Series(dtype=object)
    highest_location = ", ".join(part for part in [str(highest.get("County") or "").strip(), str(highest.get("State") or "").strip()] if part)

    def capacity_gw(mask: pd.Series) -> float:
        total = capacity.loc[mask].sum(min_count=1)
        return float(total / 1000.0) if pd.notna(total) else np.nan

    return {
        "campuses": int(len(frame)),
        "campuses_with_county_drought_data": int(county_d2.notna().sum()),
        "county_drought_coverage_share": float(county_d2.notna().mean()),
        "service_area_query_resolved": int(pws_resolved.sum()),
        "service_area_overlap": int(pws_overlap.sum()),
        "service_area_query_resolution_share": float(pws_resolved.mean()),
        "service_area_overlap_share": float(pws_overlap.mean()),
        "authoritative_service_area_overlap": int(pws_authoritative.sum()),
        "modeled_service_area_overlap": int(pws_modeled.sum()),
        "unclassified_service_area_overlap": int(pws_unclassified.sum()),
        "service_area_provenance_classified_share": float(pws_classified.sum() / pws_overlap.sum()) if int(pws_overlap.sum()) else np.nan,
        "ambiguous_service_area_overlap": int(pws_ambiguous.sum()),
        "direct_water_evidence": int(direct.sum()),
        "quantified_withdrawal": int(withdrawal.sum()),
        "quantified_consumption": int(consumption.sum()),
        "published_capacity_records": int(capacity.notna().sum()),
        "published_capacity_coverage_share": float(capacity.notna().mean()),
        "campuses_in_counties_with_d2": int(any_d2.sum()),
        "campuses_in_counties_with_d2_share": float(any_d2.loc[county_d2.notna()].mean()) if county_d2.notna().any() else np.nan,
        "campuses_in_counties_with_25pct_d2": int(material_d2.sum()),
        "campuses_in_counties_with_25pct_d2_share": float(material_d2.loc[county_d2.notna()].mean()) if county_d2.notna().any() else np.nan,
        "published_capacity_in_counties_with_d2_gw": capacity_gw(any_d2),
        "published_capacity_in_counties_with_25pct_d2_gw": capacity_gw(material_d2),
        "service_area_overlap_in_counties_with_d2": int((pws_overlap & any_d2).sum()),
        "authoritative_overlap_in_counties_with_d2": int((pws_authoritative & any_d2).sum()),
        "highest_county_d2_area_pct": float(county_d2.max()) if county_d2.notna().any() else np.nan,
        "highest_county_d2_location": highest_location,
    }
