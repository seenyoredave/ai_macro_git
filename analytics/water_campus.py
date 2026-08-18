from __future__ import annotations

import re

import numpy as np
import pandas as pd


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    values = frame[column] if column in frame.columns else pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(values, errors="coerce")


def _boolean(frame: pd.DataFrame, column: str) -> pd.Series:
    values = frame[column] if column in frame.columns else pd.Series(False, index=frame.index, dtype=bool)
    return values.fillna(False).astype(bool)


def _county_token(value) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()
    for suffix in (" county", " parish", " borough", " census area", " municipality", " city and borough"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
            break
    return text


def _fips(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    digits = "".join(character for character in text if character.isdigit())
    return digits.zfill(5) if digits else ""


def _campus_frame(campuses: pd.DataFrame | None) -> pd.DataFrame:
    if campuses is None or not isinstance(campuses, pd.DataFrame) or campuses.empty:
        return pd.DataFrame()
    if "Campus ID" not in campuses.columns:
        raise ValueError("Water campus analytics require Universal Data Center Registry Campus IDs")
    if campuses["Campus ID"].astype(str).duplicated().any():
        duplicate_ids = campuses.loc[campuses["Campus ID"].astype(str).duplicated(False), "Campus ID"].astype(str).unique().tolist()
        raise ValueError(f"Water received duplicate canonical Campus IDs: {duplicate_ids[:10]}")
    return campuses.copy()


def county_water_exposure_profile(campuses: pd.DataFrame | None) -> pd.DataFrame:
    """Aggregate canonical campuses by one county identity, preferring FIPS."""
    columns = [
        "State", "County", "FIPS", "Campuses", "D1+ Area Percent", "D2+ Area Percent",
        "D3+ Area Percent", "D4 Area Percent", "PWS Query Resolved", "PWS Overlap Campuses",
        "Authoritative PWS Overlap", "Modeled PWS Overlap", "Unclassified PWS Overlap",
        "Direct Water Evidence", "Quantified Use", "County Drought Snapshot Date",
    ]
    frame = _campus_frame(campuses)
    if frame.empty:
        return pd.DataFrame(columns=columns)

    frame["State"] = frame.get("State", pd.Series("", index=frame.index)).fillna("").astype(str).str.upper().str.strip()
    frame["County"] = frame.get("County", pd.Series("", index=frame.index)).fillna("").astype(str).str.strip()
    frame["_fips"] = frame.get("FIPS", pd.Series("", index=frame.index)).map(_fips)
    frame["_county_key"] = [
        f"fips:{fips}" if fips else f"name:{state}:{_county_token(county)}"
        for fips, state, county in zip(frame["_fips"], frame["State"], frame["County"])
    ]
    frame = frame.loc[frame["State"].ne("") & frame["County"].ne("")].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)

    for column in ("County D1+ Area Percent", "County D2+ Area Percent", "County D3+ Area Percent", "County D4 Area Percent"):
        frame[column] = _numeric(frame, column)
    frame["_pws_resolved"] = _boolean(frame, "PWS Service Area Query Resolved")
    frame["_pws_overlap"] = _boolean(frame, "PWS Service Area Overlap")
    frame["_pws_authoritative"] = _boolean(frame, "PWS Authoritative Boundary Overlap")
    frame["_pws_modeled"] = _boolean(frame, "PWS Modeled Boundary Overlap")
    frame["_pws_unclassified"] = frame["_pws_overlap"] & ~frame["_pws_authoritative"] & ~frame["_pws_modeled"]
    frame["_direct"] = _boolean(frame, "Direct Water Evidence")
    frame["_quantified"] = _numeric(frame, "Water Withdrawal Gallons/Year").notna() | _numeric(frame, "Water Consumption Gallons/Year").notna()

    rows: list[dict] = []
    for _, group in frame.groupby("_county_key", sort=False, dropna=False):
        rows.append({
            "State": str(group["State"].iloc[0]),
            "County": str(group["County"].iloc[0]),
            "FIPS": next((value for value in group["_fips"].astype(str) if value), ""),
            "Campuses": int(group["Campus ID"].astype(str).nunique()),
            "D1+ Area Percent": _numeric(group, "County D1+ Area Percent").max(),
            "D2+ Area Percent": _numeric(group, "County D2+ Area Percent").max(),
            "D3+ Area Percent": _numeric(group, "County D3+ Area Percent").max(),
            "D4 Area Percent": _numeric(group, "County D4 Area Percent").max(),
            "PWS Query Resolved": int(group["_pws_resolved"].sum()),
            "PWS Overlap Campuses": int(group["_pws_overlap"].sum()),
            "Authoritative PWS Overlap": int(group["_pws_authoritative"].sum()),
            "Modeled PWS Overlap": int(group["_pws_modeled"].sum()),
            "Unclassified PWS Overlap": int(group["_pws_unclassified"].sum()),
            "Direct Water Evidence": int(group["_direct"].sum()),
            "Quantified Use": int(group["_quantified"].sum()),
            "County Drought Snapshot Date": max(
                (str(value).strip() for value in group.get("County Drought Snapshot Date", pd.Series("", index=group.index)).fillna("") if str(value).strip()),
                default="",
            ),
        })
    out = pd.DataFrame(rows, columns=columns)
    return out.sort_values(["D2+ Area Percent", "Campuses", "State", "County"], ascending=[False, False, True, True], kind="stable").reset_index(drop=True)


def campus_water_dossier(campuses: pd.DataFrame | None) -> pd.DataFrame:
    """Return one Water dossier row for every canonical Campus ID."""
    frame = _campus_frame(campuses)
    if frame.empty:
        return pd.DataFrame()

    keep = [
        "Campus ID", "Campus Name", "Campus Label", "Identity Basis", "Identity Confidence",
        "Operator", "State", "County", "FIPS", "Latitude", "Longitude", "Status", "Building Count", "Facility Count",
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
    out["Published Capacity MW"] = planned.where(planned.gt(0)).combine_first(published.where(published.gt(0)))

    county_d1 = _numeric(out, "County D1+ Area Percent")
    county_d2 = _numeric(out, "County D2+ Area Percent")
    state_d1 = _numeric(out, "D1+ Area Percent")
    state_d2 = _numeric(out, "D2+ Area Percent")
    out["Local D1+ Area Percent"] = county_d1.combine_first(state_d1)
    out["Local D2+ Area Percent"] = county_d2.combine_first(state_d2)
    out["Local Drought Geography"] = np.where(county_d2.notna() | county_d1.notna(), "county", "state")
    county_snapshot = out.get("County Drought Snapshot Date", pd.Series("", index=out.index)).fillna("").astype(str)
    state_snapshot = out.get("Snapshot Date", pd.Series("", index=out.index)).fillna("").astype(str)
    out["Local Drought Snapshot Date"] = county_snapshot.where(county_snapshot.str.strip().ne(""), state_snapshot)
    out["Direct Water Evidence"] = _boolean(out, "Direct Water Evidence")
    out["PWS Service Area Query Resolved"] = _boolean(out, "PWS Service Area Query Resolved")
    out["PWS Service Area Overlap"] = _boolean(out, "PWS Service Area Overlap")

    if out["Campus ID"].astype(str).duplicated().any():
        raise ValueError("Water dossier multiplied canonical Campus IDs")
    return out.sort_values(
        ["Local D2+ Area Percent", "Published Capacity MW", "Campus Label"],
        ascending=[False, False, True],
        na_position="last",
        kind="stable",
    ).reset_index(drop=True)




def state_campus_evidence_profile(campuses: pd.DataFrame | None) -> pd.DataFrame:
    """Summarize canonical campus coverage and direct water evidence by state."""
    columns = [
        "State", "Mapped Campuses", "Direct Water Evidence", "Quantified Use",
        "Direct Evidence Coverage", "Quantified Use Coverage",
    ]
    frame = _campus_frame(campuses)
    if frame.empty:
        return pd.DataFrame(columns=columns)
    frame["State"] = frame.get("State", pd.Series("", index=frame.index)).fillna("").astype(str).str.upper().str.strip()
    frame = frame.loc[frame["State"].ne("")].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)
    frame["_direct"] = _boolean(frame, "Direct Water Evidence")
    frame["_quantified"] = _numeric(frame, "Water Withdrawal Gallons/Year").notna() | _numeric(frame, "Water Consumption Gallons/Year").notna()
    grouped = frame.groupby("State", sort=True, dropna=False)
    out = pd.concat([
        grouped["Campus ID"].nunique().rename("Mapped Campuses"),
        grouped["_direct"].sum().rename("Direct Water Evidence"),
        grouped["_quantified"].sum().rename("Quantified Use"),
    ], axis=1).reset_index()
    out["Direct Evidence Coverage"] = out["Direct Water Evidence"] / out["Mapped Campuses"].where(out["Mapped Campuses"].gt(0))
    out["Quantified Use Coverage"] = out["Quantified Use"] / out["Mapped Campuses"].where(out["Mapped Campuses"].gt(0))
    return out.sort_values(["Mapped Campuses", "State"], ascending=[False, True], kind="stable").reset_index(drop=True)


def state_competition_exposure(
    campuses: pd.DataFrame | None,
    state_categories: pd.DataFrame | None,
) -> pd.DataFrame:
    """Join the canonical campus universe to state freshwater-allocation context."""
    from analytics.water_competition import competing_freshwater_profile

    frame = _campus_frame(campuses)
    if frame.empty:
        return pd.DataFrame()
    frame["State"] = frame.get("State", pd.Series("", index=frame.index)).fillna("").astype(str).str.upper().str.strip()
    frame = frame.loc[frame["State"].ne("")].copy()
    if frame.empty:
        return pd.DataFrame()

    frame["_county_context"] = _boolean(frame, "County Water Context Available")
    frame["_direct"] = _boolean(frame, "Direct Water Evidence")
    grouped = frame.groupby("State", dropna=False)
    footprint = pd.concat([
        grouped["Campus ID"].nunique().rename("Mapped Campuses"),
        grouped["_county_context"].sum().rename("County Context"),
        grouped["_direct"].sum().rename("Direct Evidence"),
    ], axis=1).reset_index()

    if state_categories is None or not isinstance(state_categories, pd.DataFrame) or state_categories.empty:
        for column in ("Community + Agriculture Share", "Agriculture Share", "Household & Public Share", "Thermoelectric Share"):
            footprint[column] = np.nan
    else:
        states = state_categories.copy()
        states["State"] = states.get("Geography", pd.Series("", index=states.index)).fillna("").astype(str).str.upper().str.strip()
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

    footprint["County Context Coverage"] = footprint["County Context"] / footprint["Mapped Campuses"].where(footprint["Mapped Campuses"].gt(0))
    footprint["Direct Evidence Coverage"] = footprint["Direct Evidence"] / footprint["Mapped Campuses"].where(footprint["Mapped Campuses"].gt(0))
    return footprint.sort_values(["Mapped Campuses", "State"], ascending=[False, True], kind="stable").reset_index(drop=True)


__all__ = [
    "county_water_exposure_profile",
    "campus_water_dossier",
    "state_campus_evidence_profile",
    "state_competition_exposure",
]
