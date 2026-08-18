from __future__ import annotations

import numpy as np
import pandas as pd

PARTY_MAP = {
    "public_supply": "Households & public systems",
    "domestic_self_supply": "Households & public systems",
    "irrigation": "Agriculture",
    "livestock": "Agriculture",
    "aquaculture": "Agriculture",
    "industrial_self_supply": "Industry & extraction",
    "mining": "Industry & extraction",
    "thermoelectric_power": "Thermoelectric power",
}

PARTY_ORDER = [
    "Households & public systems",
    "Agriculture",
    "Industry & extraction",
    "Thermoelectric power",
]


def competing_freshwater_profile(category_frame: pd.DataFrame | None) -> pd.DataFrame:
    """Aggregate USGS categories into the major freshwater-use parties."""
    columns = [
        "Party", "Fresh Groundwater Bgal/day", "Fresh Surface Water Bgal/day",
        "Freshwater Bgal/day", "Freshwater Share",
    ]
    if category_frame is None or not isinstance(category_frame, pd.DataFrame) or category_frame.empty:
        return pd.DataFrame(columns=columns)

    frame = category_frame.copy()
    frame["Party"] = frame.get("Use Category", pd.Series("", index=frame.index)).map(PARTY_MAP)
    frame = frame.dropna(subset=["Party"]).copy()
    for column in ("Fresh Groundwater Mgal/d", "Fresh Surface Water Mgal/d"):
        values = frame[column] if column in frame.columns else pd.Series(0.0, index=frame.index)
        frame[column] = pd.to_numeric(values, errors="coerce").fillna(0.0)
    if frame.empty:
        return pd.DataFrame(columns=columns)

    grouped = frame.groupby("Party", as_index=False)[
        ["Fresh Groundwater Mgal/d", "Fresh Surface Water Mgal/d"]
    ].sum()
    grouped["Fresh Groundwater Bgal/day"] = grouped["Fresh Groundwater Mgal/d"] / 1000.0
    grouped["Fresh Surface Water Bgal/day"] = grouped["Fresh Surface Water Mgal/d"] / 1000.0
    grouped["Freshwater Bgal/day"] = grouped["Fresh Groundwater Bgal/day"] + grouped["Fresh Surface Water Bgal/day"]
    total = float(grouped["Freshwater Bgal/day"].sum())
    grouped["Freshwater Share"] = grouped["Freshwater Bgal/day"] / total if total > 0 else np.nan
    order = {name: index for index, name in enumerate(PARTY_ORDER)}
    grouped["_order"] = grouped["Party"].map(order).fillna(len(order))
    return grouped.sort_values("_order", kind="stable").drop(
        columns=["Fresh Groundwater Mgal/d", "Fresh Surface Water Mgal/d", "_order"]
    ).reset_index(drop=True)


def local_context_coverage_profile(summary: dict | None) -> pd.DataFrame:
    """Describe independent Water observability layers at canonical campus grain."""
    payload = summary or {}
    campuses = int(payload.get("canonical_campuses", payload.get("mapped_campuses", 0)) or 0)
    rows = [
        ("Canonical campuses", campuses, "registry"),
        ("Current county drought", int(payload.get("county_drought_context_records", 0) or 0), "physical context"),
        ("EPA point query resolved", int(payload.get("pws_service_area_query_resolved_records", 0) or 0), "service-area context"),
        ("EPA service-area overlap", int(payload.get("pws_service_area_overlap_records", 0) or 0), "service-area context"),
        ("Direct campus water evidence", int(payload.get("direct_water_evidence_records", 0) or 0), "campus evidence"),
        ("Quantified withdrawal", int(payload.get("quantified_withdrawal_records", 0) or 0), "campus evidence"),
        ("Quantified consumption", int(payload.get("quantified_consumption_records", 0) or 0), "campus evidence"),
    ]
    frame = pd.DataFrame(rows, columns=["Coverage Layer", "Campuses", "Layer Type"])
    frame["Coverage"] = frame["Campuses"] / campuses if campuses > 0 else np.nan
    return frame


def current_top_withdrawal_profile(frame: pd.DataFrame | None) -> pd.DataFrame:
    """Normalize the retained USGS 2020 top-three withdrawal comparison."""
    columns = [
        "Use Category", "Withdrawal Mgal/d", "Withdrawal Bgal/day",
        "Observation Year", "Source Name", "Source URL", "Publication Date",
    ]
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=[*columns, "Share of Top Three"])

    out = frame.copy()
    for column in columns:
        if column not in out.columns:
            out[column] = pd.NA
    out["Withdrawal Mgal/d"] = pd.to_numeric(out["Withdrawal Mgal/d"], errors="coerce")
    out["Withdrawal Bgal/day"] = pd.to_numeric(out["Withdrawal Bgal/day"], errors="coerce")
    missing_bgal = out["Withdrawal Bgal/day"].isna() & out["Withdrawal Mgal/d"].notna()
    out.loc[missing_bgal, "Withdrawal Bgal/day"] = out.loc[missing_bgal, "Withdrawal Mgal/d"] / 1000.0
    out["Observation Year"] = pd.to_numeric(out["Observation Year"], errors="coerce").astype("Int64")
    out = out.dropna(subset=["Use Category", "Withdrawal Bgal/day"]).copy()
    total = float(out["Withdrawal Bgal/day"].sum())
    out["Share of Top Three"] = out["Withdrawal Bgal/day"] / total if total > 0 else np.nan
    return out.sort_values("Withdrawal Bgal/day", ascending=False, kind="stable").reset_index(drop=True)


__all__ = [
    "competing_freshwater_profile",
    "local_context_coverage_profile",
    "current_top_withdrawal_profile",
]
