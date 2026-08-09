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
    """Aggregate USGS categories into the parties competing for freshwater.

    This is an allocation context, not an attribution of any category's use to
    AI facilities. Data centers are not a separate USGS withdrawal category in
    the retained 2015 account.
    """
    if category_frame is None or not isinstance(category_frame, pd.DataFrame) or category_frame.empty:
        return pd.DataFrame(columns=[
            "Party", "Fresh Groundwater Bgal/day", "Fresh Surface Water Bgal/day",
            "Freshwater Bgal/day", "Freshwater Share",
        ])

    frame = category_frame.copy()
    frame["Party"] = frame.get("Use Category", pd.Series("", index=frame.index)).map(PARTY_MAP)
    frame = frame.dropna(subset=["Party"])
    for column in ("Fresh Groundwater Mgal/d", "Fresh Surface Water Mgal/d"):
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce").fillna(0.0)
    if frame.empty:
        return pd.DataFrame(columns=[
            "Party", "Fresh Groundwater Bgal/day", "Fresh Surface Water Bgal/day",
            "Freshwater Bgal/day", "Freshwater Share",
        ])

    grouped = (
        frame.groupby("Party", as_index=False)[
            ["Fresh Groundwater Mgal/d", "Fresh Surface Water Mgal/d"]
        ].sum()
    )
    grouped["Fresh Groundwater Bgal/day"] = grouped["Fresh Groundwater Mgal/d"] / 1000.0
    grouped["Fresh Surface Water Bgal/day"] = grouped["Fresh Surface Water Mgal/d"] / 1000.0
    grouped["Freshwater Bgal/day"] = (
        grouped["Fresh Groundwater Bgal/day"] + grouped["Fresh Surface Water Bgal/day"]
    )
    total = grouped["Freshwater Bgal/day"].sum()
    grouped["Freshwater Share"] = grouped["Freshwater Bgal/day"] / total if total > 0 else np.nan
    order = {name: index for index, name in enumerate(PARTY_ORDER)}
    grouped["_order"] = grouped["Party"].map(order).fillna(len(order))
    return grouped.sort_values("_order", kind="stable").drop(
        columns=["Fresh Groundwater Mgal/d", "Fresh Surface Water Mgal/d", "_order"]
    ).reset_index(drop=True)


def evidence_ladder(summary: dict | None) -> pd.DataFrame:
    """Track current facility evidence without promoting stale county data.

    State identification comes from the current facility registry. Older county
    withdrawal records remain provenance-only and are not counted as a current
    analytical evidence stage.
    """
    payload = summary or {}
    facilities = int(payload.get("facilities", 0) or 0)
    state_identified = int(payload.get("state_identified_records", facilities) or 0)
    rows = [
        ("Mapped facilities", facilities),
        ("State identified", min(state_identified, facilities)),
        ("Direct water evidence", int(payload.get("direct_water_evidence_records", 0) or 0)),
        ("Quantified withdrawal", int(payload.get("quantified_withdrawal_records", 0) or 0)),
        ("Quantified consumption", int(payload.get("quantified_consumption_records", 0) or 0)),
    ]
    frame = pd.DataFrame(rows, columns=["Evidence Stage", "Facilities"])
    frame["Coverage"] = frame["Facilities"] / facilities if facilities > 0 else np.nan
    return frame


def state_competition_exposure(
    facility_context: pd.DataFrame | None,
    state_categories: pd.DataFrame | None,
) -> pd.DataFrame:
    """Join current facility footprint to state-level freshwater allocation context.

    The resulting frame is a triage surface only. It intentionally does not
    estimate data-center withdrawal, consumption, causation, or shortage risk.
    """
    if facility_context is None or not isinstance(facility_context, pd.DataFrame) or facility_context.empty:
        return pd.DataFrame()

    facilities = facility_context.copy()
    facilities["State"] = facilities.get("State", "").fillna("").astype(str).str.upper().str.strip()
    facilities = facilities.loc[facilities["State"].ne("")].copy()
    if facilities.empty:
        return pd.DataFrame()

    facility_id = "Facility ID" if "Facility ID" in facilities.columns else None
    group = facilities.groupby("State", dropna=False)
    footprint = group.size().rename("Mapped Facilities").reset_index()
    if facility_id:
        footprint["Mapped Facilities"] = group[facility_id].nunique().values

    county_context = facilities.get("County Water Context Available")
    if county_context is None:
        total_withdrawal = facilities.get("Total Withdrawal Mgal/d")
        if total_withdrawal is None:
            total_withdrawal = pd.Series(np.nan, index=facilities.index)
        county_context = pd.to_numeric(total_withdrawal, errors="coerce").notna()
    direct = facilities.get("Direct Water Evidence")
    if direct is None:
        direct = pd.Series(False, index=facilities.index)
    facilities["_county_context"] = pd.Series(county_context, index=facilities.index).fillna(False).astype(bool)
    facilities["_direct"] = pd.Series(direct, index=facilities.index).fillna(False).astype(bool)
    coverage = facilities.groupby("State").agg(
        County_Context=("_county_context", "sum"),
        Direct_Evidence=("_direct", "sum"),
    ).reset_index()
    footprint = footprint.merge(coverage, on="State", how="left")

    if state_categories is None or not isinstance(state_categories, pd.DataFrame) or state_categories.empty:
        footprint["Community + Agriculture Share"] = np.nan
        footprint["Agriculture Share"] = np.nan
        footprint["Household & Public Share"] = np.nan
        footprint["Thermoelectric Share"] = np.nan
    else:
        states = state_categories.copy()
        states["State"] = states.get("Geography", "").fillna("").astype(str).str.upper().str.strip()
        profile = competing_freshwater_profile(states)
        # competing_freshwater_profile aggregates all supplied geographies, so build per state.
        rows = []
        for state, subset in states.groupby("State", sort=False):
            parties = competing_freshwater_profile(subset)
            values = parties.set_index("Party")["Freshwater Share"].to_dict() if not parties.empty else {}
            household = float(values.get("Households & public systems", 0.0) or 0.0)
            agriculture = float(values.get("Agriculture", 0.0) or 0.0)
            rows.append({
                "State": state,
                "Household & Public Share": household,
                "Agriculture Share": agriculture,
                "Community + Agriculture Share": household + agriculture,
                "Thermoelectric Share": float(values.get("Thermoelectric power", 0.0) or 0.0),
            })
        footprint = footprint.merge(pd.DataFrame(rows), on="State", how="left")

    footprint["County Context Coverage"] = (
        footprint["County_Context"] / footprint["Mapped Facilities"].where(footprint["Mapped Facilities"].gt(0))
    )
    footprint["Direct Evidence Coverage"] = (
        footprint["Direct_Evidence"] / footprint["Mapped Facilities"].where(footprint["Mapped Facilities"].gt(0))
    )
    return footprint.sort_values(
        ["Mapped Facilities", "State"], ascending=[False, True], kind="stable"
    ).reset_index(drop=True)


def current_top_withdrawal_profile(frame: pd.DataFrame | None) -> pd.DataFrame:
    """Normalize the retained USGS 2020 top-three withdrawal comparison.

    The source covers crop irrigation, thermoelectric power, and public supply.
    It is a current-window national allocation envelope, not a complete all-use
    account and not an estimate of data-center withdrawal.
    """
    columns = [
        "Use Category", "Withdrawal Mgal/d", "Withdrawal Bgal/day",
        "Observation Year", "Source Name", "Source URL", "Publication Date",
    ]
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=columns + ["Share of Top Three"])
    out = frame.copy()
    for column in columns:
        if column not in out.columns:
            out[column] = pd.NA
    out["Withdrawal Mgal/d"] = pd.to_numeric(out["Withdrawal Mgal/d"], errors="coerce")
    out["Withdrawal Bgal/day"] = pd.to_numeric(out["Withdrawal Bgal/day"], errors="coerce")
    missing_bgal = out["Withdrawal Bgal/day"].isna() & out["Withdrawal Mgal/d"].notna()
    out.loc[missing_bgal, "Withdrawal Bgal/day"] = out.loc[missing_bgal, "Withdrawal Mgal/d"] / 1000.0
    out["Observation Year"] = pd.to_numeric(out["Observation Year"], errors="coerce").astype("Int64")
    out = out.dropna(subset=["Use Category", "Withdrawal Bgal/day"])
    total = out["Withdrawal Bgal/day"].sum()
    out["Share of Top Three"] = out["Withdrawal Bgal/day"] / total if total > 0 else np.nan
    return out.sort_values("Withdrawal Bgal/day", ascending=False, kind="stable").reset_index(drop=True)


def state_facility_evidence_profile(facility_context: pd.DataFrame | None) -> pd.DataFrame:
    """Summarize current facility concentration and direct water evidence by state.

    No historic withdrawal data are joined here.  The output supports evidence
    triage only and makes no claim about local water use, scarcity, or displacement.
    """
    columns = [
        "State", "Mapped Facilities", "Direct Water Evidence",
        "Quantified Use", "Direct Evidence Coverage", "Quantified Use Coverage",
    ]
    if facility_context is None or not isinstance(facility_context, pd.DataFrame) or facility_context.empty:
        return pd.DataFrame(columns=columns)
    frame = facility_context.copy()
    frame["State"] = frame.get("State", "").fillna("").astype(str).str.upper().str.strip()
    frame = frame.loc[frame["State"].ne("")].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)
    direct = frame.get("Direct Water Evidence", pd.Series(False, index=frame.index))
    frame["_direct"] = pd.Series(direct, index=frame.index).fillna(False).astype(bool)
    withdrawal = pd.to_numeric(frame.get("Water Withdrawal Gallons/Year"), errors="coerce")
    consumption = pd.to_numeric(frame.get("Water Consumption Gallons/Year"), errors="coerce")
    frame["_quantified"] = withdrawal.notna() | consumption.notna()
    facility_id = "Facility ID" if "Facility ID" in frame.columns else None
    grouped = frame.groupby("State", sort=True, dropna=False)
    if facility_id:
        mapped = grouped[facility_id].nunique().rename("Mapped Facilities")
    else:
        mapped = grouped.size().rename("Mapped Facilities")
    out = pd.concat([
        mapped,
        grouped["_direct"].sum().rename("Direct Water Evidence"),
        grouped["_quantified"].sum().rename("Quantified Use"),
    ], axis=1).reset_index()
    out["Direct Evidence Coverage"] = (
        out["Direct Water Evidence"] / out["Mapped Facilities"].where(out["Mapped Facilities"].gt(0))
    )
    out["Quantified Use Coverage"] = (
        out["Quantified Use"] / out["Mapped Facilities"].where(out["Mapped Facilities"].gt(0))
    )
    return out.sort_values(["Mapped Facilities", "State"], ascending=[False, True], kind="stable").reset_index(drop=True)


def state_water_exposure_profile(
    facility_context: pd.DataFrame | None,
    state_categories: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Combine campus footprint, drought area, disclosure, and freshwater allocation by state."""
    if facility_context is None or not isinstance(facility_context, pd.DataFrame) or facility_context.empty:
        return pd.DataFrame()
    frame = facility_context.copy()
    frame["State"] = frame.get("State", "").fillna("").astype(str).str.upper().str.strip()
    frame = frame.loc[frame["State"].ne("")].copy()
    published = pd.to_numeric(frame.get("Published Capacity Estimate MW"), errors="coerce")
    planned = pd.to_numeric(frame.get("Planned Data Center Capacity MW"), errors="coerce")
    frame["Published MW"] = published.combine_first(planned)
    frame["D1+ Area Percent"] = pd.to_numeric(frame.get("D1+ Area Percent"), errors="coerce")
    frame["D2+ Area Percent"] = pd.to_numeric(frame.get("D2+ Area Percent"), errors="coerce")
    direct = frame.get("Direct Water Evidence", pd.Series(False, index=frame.index)).fillna(False).astype(bool)
    frame["_direct"] = direct
    grouped = frame.groupby("State", dropna=False)
    out = grouped.agg(
        Facilities=("State", "size"),
        Published_MW=("Published MW", lambda values: values.sum(min_count=1)),
        Direct_Evidence=("_direct", "sum"),
        D1_Area_Percent=("D1+ Area Percent", "max"),
        D2_Area_Percent=("D2+ Area Percent", "max"),
    ).reset_index().rename(columns={
        "Published_MW": "Published Capacity MW",
        "Direct_Evidence": "Direct Water Evidence",
        "D1_Area_Percent": "D1+ Area Percent",
        "D2_Area_Percent": "D2+ Area Percent",
    })
    out["Direct Evidence Coverage Percent"] = out["Direct Water Evidence"] / out["Facilities"].where(out["Facilities"].gt(0)) * 100.0
    allocation = state_competition_exposure(frame, state_categories)
    if not allocation.empty:
        keep = ["State", "Community + Agriculture Share", "Agriculture Share", "Household & Public Share", "Thermoelectric Share"]
        out = out.merge(allocation[[c for c in keep if c in allocation.columns]], on="State", how="left")
    out["Exposure Tier"] = np.select(
        [out["D2+ Area Percent"].fillna(0).ge(25), out["D1+ Area Percent"].fillna(0).ge(25)],
        ["Severe drought overlap", "Drought overlap"],
        default="Limited current drought overlap",
    )
    return out.sort_values(["D2+ Area Percent", "Published Capacity MW"], ascending=[False, False], kind="stable").reset_index(drop=True)


def campus_water_dossier(facility_context: pd.DataFrame | None) -> pd.DataFrame:
    if facility_context is None or not isinstance(facility_context, pd.DataFrame) or facility_context.empty:
        return pd.DataFrame()
    frame = facility_context.copy()
    keep = [
        "Facility ID", "Facility", "Operator", "State", "County", "Status",
        "Published Capacity Estimate MW", "Planned Data Center Capacity MW", "Cooling System", "Water Source",
        "Reclaimed Water Use", "Direct Water Evidence", "Water Evidence Grade",
        "Water Withdrawal Gallons/Year", "Water Consumption Gallons/Year",
        "D1+ Area Percent", "D2+ Area Percent", "D3+ Area Percent", "D4 Area Percent",
        "Snapshot Date", "Freshwater Withdrawal Mgal/d", "Total Withdrawal Mgal/d",
        "Water Evidence Source", "Water Evidence URL",
    ]
    out = frame[[column for column in keep if column in frame.columns]].copy()
    published = pd.to_numeric(out.get("Published Capacity Estimate MW"), errors="coerce")
    planned = pd.to_numeric(out.get("Planned Data Center Capacity MW"), errors="coerce")
    out["Published Capacity MW"] = published.combine_first(planned)
    out["D1+ Area Percent"] = pd.to_numeric(out.get("D1+ Area Percent"), errors="coerce")
    out["D2+ Area Percent"] = pd.to_numeric(out.get("D2+ Area Percent"), errors="coerce")
    out["Direct Water Evidence"] = out.get("Direct Water Evidence", False).fillna(False).astype(bool)
    out["Exposure Tier"] = np.select(
        [out["D2+ Area Percent"].fillna(0).ge(25), out["D1+ Area Percent"].fillna(0).ge(25)],
        ["Severe drought overlap", "Drought overlap"],
        default="Limited current drought overlap",
    )
    return out.sort_values(["D2+ Area Percent", "Published Capacity MW"], ascending=[False, False], kind="stable").reset_index(drop=True)
