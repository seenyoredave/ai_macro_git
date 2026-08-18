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


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _boolean(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(False, index=frame.index, dtype=bool)
    return frame[column].fillna(False).astype(bool)


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
    """Retained compatibility view of facility water-evidence depth."""
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


def local_context_coverage_profile(summary: dict | None) -> pd.DataFrame:
    """Describe independent Water v2 observability layers without implying a funnel.

    County drought, EPA service-area overlap, and direct facility disclosure are
    separate evidence surfaces.  A facility does not need to intersect an EPA
    polygon to have direct water evidence, and an EPA overlap does not establish
    a customer relationship.
    """
    payload = summary or {}
    facilities = int(payload.get("facilities", 0) or 0)
    rows = [
        ("Mapped facilities", facilities, "registry"),
        ("Current county drought", int(payload.get("county_drought_context_records", 0) or 0), "physical context"),
        ("EPA point query resolved", int(payload.get("pws_service_area_query_resolved_records", 0) or 0), "service-area context"),
        ("EPA service-area overlap", int(payload.get("pws_service_area_overlap_records", 0) or 0), "service-area context"),
        ("Direct facility water evidence", int(payload.get("direct_water_evidence_records", 0) or 0), "facility evidence"),
        ("Quantified withdrawal", int(payload.get("quantified_withdrawal_records", 0) or 0), "facility evidence"),
        ("Quantified consumption", int(payload.get("quantified_consumption_records", 0) or 0), "facility evidence"),
    ]
    frame = pd.DataFrame(rows, columns=["Coverage Layer", "Facilities", "Layer Type"])
    frame["Coverage"] = frame["Facilities"] / facilities if facilities > 0 else np.nan
    return frame


def county_water_exposure_profile(facility_context: pd.DataFrame | None) -> pd.DataFrame:
    """Aggregate mapped facilities by county using current USDM county statistics.

    The output is physical exposure context only.  Drought area is not treated
    as proof of campus-level shortage, available supply, or curtailment.
    """
    columns = [
        "State", "County", "Facilities", "D1+ Area Percent", "D2+ Area Percent",
        "D3+ Area Percent", "D4 Area Percent", "PWS Query Resolved",
        "PWS Overlap Facilities", "Authoritative PWS Overlap",
        "Modeled PWS Overlap", "Unclassified PWS Overlap", "Direct Water Evidence", "Quantified Use",
        "County Drought Snapshot Date",
    ]
    if facility_context is None or not isinstance(facility_context, pd.DataFrame) or facility_context.empty:
        return pd.DataFrame(columns=columns)

    frame = facility_context.copy()
    frame["State"] = frame.get("State", "").fillna("").astype(str).str.upper().str.strip()
    frame["County"] = frame.get("County", "").fillna("").astype(str).str.strip()
    frame = frame.loc[frame["State"].ne("") & frame["County"].ne("")].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)

    for column in (
        "County D1+ Area Percent", "County D2+ Area Percent",
        "County D3+ Area Percent", "County D4 Area Percent",
    ):
        frame[column] = _numeric(frame, column)
    frame["_pws_resolved"] = _boolean(frame, "PWS Service Area Query Resolved")
    frame["_pws_overlap"] = _boolean(frame, "PWS Service Area Overlap")
    frame["_pws_authoritative"] = _boolean(frame, "PWS Authoritative Boundary Overlap")
    frame["_pws_modeled"] = _boolean(frame, "PWS Modeled Boundary Overlap")
    frame["_pws_unclassified"] = frame["_pws_overlap"] & ~frame["_pws_authoritative"] & ~frame["_pws_modeled"]
    frame["_direct"] = _boolean(frame, "Direct Water Evidence")
    frame["_quantified"] = (
        _numeric(frame, "Water Withdrawal Gallons/Year").notna()
        | _numeric(frame, "Water Consumption Gallons/Year").notna()
    )

    grouped = frame.groupby(["State", "County"], dropna=False, sort=False)
    out = grouped.agg(
        Facilities=("County", "size"),
        D1=("County D1+ Area Percent", "max"),
        D2=("County D2+ Area Percent", "max"),
        D3=("County D3+ Area Percent", "max"),
        D4=("County D4 Area Percent", "max"),
        PWS_Query_Resolved=("_pws_resolved", "sum"),
        PWS_Overlap=("_pws_overlap", "sum"),
        PWS_Authoritative=("_pws_authoritative", "sum"),
        PWS_Modeled=("_pws_modeled", "sum"),
        PWS_Unclassified=("_pws_unclassified", "sum"),
        Direct_Evidence=("_direct", "sum"),
        Quantified_Use=("_quantified", "sum"),
    ).reset_index()
    out = out.rename(columns={
        "D1": "D1+ Area Percent",
        "D2": "D2+ Area Percent",
        "D3": "D3+ Area Percent",
        "D4": "D4 Area Percent",
        "PWS_Query_Resolved": "PWS Query Resolved",
        "PWS_Overlap": "PWS Overlap Facilities",
        "PWS_Authoritative": "Authoritative PWS Overlap",
        "PWS_Modeled": "Modeled PWS Overlap",
        "PWS_Unclassified": "Unclassified PWS Overlap",
        "Direct_Evidence": "Direct Water Evidence",
        "Quantified_Use": "Quantified Use",
    })

    snapshot = frame.get("County Drought Snapshot Date", pd.Series("", index=frame.index)).fillna("").astype(str).str.strip()
    if snapshot.ne("").any():
        dates = (
            frame.assign(_snapshot=snapshot)
            .groupby(["State", "County"], dropna=False)["_snapshot"]
            .max()
            .rename("County Drought Snapshot Date")
            .reset_index()
        )
        out = out.merge(dates, on=["State", "County"], how="left")
    else:
        out["County Drought Snapshot Date"] = ""

    return out.sort_values(
        ["D2+ Area Percent", "Facilities", "State", "County"],
        ascending=[False, False, True, True],
        kind="stable",
    ).reset_index(drop=True)


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
    """Normalize the retained USGS 2020 top-three withdrawal comparison."""
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
    """Summarize current facility concentration and direct water evidence by state."""
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
    frame["_direct"] = _boolean(frame, "Direct Water Evidence")
    frame["_quantified"] = (
        _numeric(frame, "Water Withdrawal Gallons/Year").notna()
        | _numeric(frame, "Water Consumption Gallons/Year").notna()
    )
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
    """Compatibility state view; Water v2 primary exposure uses county context."""
    if facility_context is None or not isinstance(facility_context, pd.DataFrame) or facility_context.empty:
        return pd.DataFrame()
    frame = facility_context.copy()
    frame["State"] = frame.get("State", "").fillna("").astype(str).str.upper().str.strip()
    frame = frame.loc[frame["State"].ne("")].copy()
    published = _numeric(frame, "Published Capacity Estimate MW")
    planned = _numeric(frame, "Planned Data Center Capacity MW")
    frame["Published MW"] = published.combine_first(planned)
    frame["D1+ Area Percent"] = _numeric(frame, "D1+ Area Percent")
    frame["D2+ Area Percent"] = _numeric(frame, "D2+ Area Percent")
    frame["_direct"] = _boolean(frame, "Direct Water Evidence")
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
    out["Direct Evidence Coverage Percent"] = (
        out["Direct Water Evidence"] / out["Facilities"].where(out["Facilities"].gt(0)) * 100.0
    )
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
    """Return campus-level local context without upgrading overlap into service."""
    if facility_context is None or not isinstance(facility_context, pd.DataFrame) or facility_context.empty:
        return pd.DataFrame()
    frame = facility_context.copy()
    keep = [
        "Facility ID", "Facility", "Operator", "State", "County", "Status",
        "Published Capacity Estimate MW", "Planned Data Center Capacity MW", "Cooling System", "Water Source",
        "Reclaimed Water Use", "Direct Water Evidence", "Water Evidence Grade", "Water Evidence Status",
        "Water Withdrawal Gallons/Year", "Water Consumption Gallons/Year",
        "County D1+ Area Percent", "County D2+ Area Percent", "County D3+ Area Percent", "County D4 Area Percent",
        "County Drought Snapshot Date", "County Drought Source", "County Drought Source URL",
        "D1+ Area Percent", "D2+ Area Percent", "D3+ Area Percent", "D4 Area Percent", "Snapshot Date",
        "Freshwater Withdrawal Mgal/d", "Total Withdrawal Mgal/d", "Year",
        "PWS Service Area Query Resolved", "PWS Service Area Overlap", "PWS Match Count", "PWSIDs", "PWS Names",
        "PWS Boundary Basis", "PWS Authoritative Boundary Overlap", "PWS Modeled Boundary Overlap", "PWS Ambiguous Overlap",
        "Water Evidence Source", "Water Evidence URL",
    ]
    out = frame[[column for column in keep if column in frame.columns]].copy()
    published = _numeric(out, "Published Capacity Estimate MW")
    planned = _numeric(out, "Planned Data Center Capacity MW")
    out["Published Capacity MW"] = published.combine_first(planned)

    county_d1 = _numeric(out, "County D1+ Area Percent")
    county_d2 = _numeric(out, "County D2+ Area Percent")
    state_d1 = _numeric(out, "D1+ Area Percent")
    state_d2 = _numeric(out, "D2+ Area Percent")
    out["Local D1+ Area Percent"] = county_d1.combine_first(state_d1)
    out["Local D2+ Area Percent"] = county_d2.combine_first(state_d2)
    out["Local Drought Geography"] = np.where(county_d2.notna() | county_d1.notna(), "county", "state fallback")
    out["Local Drought Snapshot Date"] = out.get(
        "County Drought Snapshot Date", pd.Series("", index=out.index)
    ).fillna("").astype(str)
    if "Snapshot Date" in out.columns:
        fallback = out["Snapshot Date"].fillna("").astype(str)
        out["Local Drought Snapshot Date"] = out["Local Drought Snapshot Date"].where(
            out["Local Drought Snapshot Date"].str.strip().ne(""), fallback
        )

    out["Direct Water Evidence"] = _boolean(out, "Direct Water Evidence")
    out["PWS Service Area Query Resolved"] = _boolean(out, "PWS Service Area Query Resolved")
    out["PWS Service Area Overlap"] = _boolean(out, "PWS Service Area Overlap")
    out["PWS Authoritative Boundary Overlap"] = _boolean(out, "PWS Authoritative Boundary Overlap")
    out["PWS Modeled Boundary Overlap"] = _boolean(out, "PWS Modeled Boundary Overlap")
    out["PWS Ambiguous Overlap"] = _boolean(out, "PWS Ambiguous Overlap")

    out["Exposure Tier"] = np.select(
        [out["Local D2+ Area Percent"].fillna(0).ge(25), out["Local D1+ Area Percent"].fillna(0).ge(25)],
        ["Material D2+ county overlap", "County drought overlap"],
        default="Limited current drought overlap",
    )
    return out.sort_values(
        ["Local D2+ Area Percent", "Published Capacity MW"],
        ascending=[False, False],
        kind="stable",
    ).reset_index(drop=True)
