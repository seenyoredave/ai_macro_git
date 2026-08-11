"""Retained and selectively refreshable U.S. connectivity evidence.

Connectivity is a first-class physical domain.  The public contract combines
submarine systems and landing markets, IXPs and interconnection facilities,
public middle-mile expansion, and campus-proximity screening.  It deliberately
does not infer proprietary fiber routes, contracted capacity, traffic, latency,
or route diversity that the cited sources do not disclose.
"""

from __future__ import annotations

from io import StringIO
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
import re

import numpy as np
import pandas as pd
import requests
import streamlit as st

from config.debug_config import debug_print
from config.deployment import repository_writes_enabled
from helpers.atomic_io import atomic_write_csv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "connectivity"
IXP_PATH = DATA_DIR / "ixp_snapshot.csv"
NATIONAL_PATH = DATA_DIR / "national_summary.csv"
GATEWAY_PATH = DATA_DIR / "gateway_ledger.csv"  # legacy compatibility
CABLE_SYSTEM_PATH = DATA_DIR / "submarine_cable_systems.csv"
LANDING_MARKET_PATH = DATA_DIR / "cable_landing_markets.csv"
INTERCONNECTION_MARKET_PATH = DATA_DIR / "interconnection_market_summary.csv"
FACILITY_SUMMARY_PATH = DATA_DIR / "interconnection_facility_summary.csv"
MIDDLE_MILE_AWARDS_PATH = DATA_DIR / "middle_mile_awards.csv"
MIDDLE_MILE_SUMMARY_PATH = DATA_DIR / "middle_mile_summary.csv"
MANIFEST_PATH = DATA_DIR / "source_manifest.csv"

PULSE_URL = "https://pulse.internetsociety.org/en/ixp-tracker/country/US/"
TELEGEOGRAPHY_URL = "https://www.submarinecablemap.com/country/united-states"
PEERINGDB_FACILITY_URL = "https://www.peeringdb.com/api/fac"
NTIA_MIDDLE_MILE_URL = "https://broadbandusa.ntia.gov/news/latest-news/constructing-digital-landscape-highlights-ntias-middle-mile-program"

CONNECTIVITY_PHASE = "Full public-evidence transport layer"
REQUIRED_NATIONAL_FIELDS = (
    "Active IXPs",
    "Combined Reported Members",
    "Population Centers With IXP",
    "Population Centers Over 300k",
    "Domestic Network Coverage Percent",
    "Locally Cached Top Sites Percent",
    "Active Domestic Networks",
    "Internet Resilience Score",
)

_CITY_STATE = {
    "Phoenix":"AZ","Albuquerque":"NM","Atlanta":"GA","Chicago":"IL","Dallas":"TX","Fremont":"CA","Kansas":"KS",
    "Los Angeles":"CA","Miami":"FL","New York":"NY","Baltimore":"MD","Boston":"MA","Mount Pleasant":"MI","Bend":"OR",
    "NewYork":"NY","Cleveland":"OH","Columbus":"OH","Denver":"CO","Washington DC":"DC","Orlando":"FL",
    "Silicon Valley":"CA","Ashburn":"VA","Honolulu":"HI","Des Moines":"IA","Detroit":"MI","Palo Alto":"CA",
    "San Jose":"CA","Seattle":"WA","Kansas City":"MO","Amarillo":"TX","Houston":"TX","Fargo":"ND","Austin":"TX",
    "St. Louis":"MO","Saint Louis":"MO","Washington":"DC","Grand Rapids":"MI","Salt Lake City":"UT",
    "North Kansas City":"MO","Boise":"ID","Indianapolis":"IN","Oklahoma City":"OK","Las Vegas":"NV",
    "Jacksonville":"FL","Northern Virginia":"VA","El Paso":"TX","McAllen":"TX","Madison":"WI","San Francisco":"CA",
    "Charlotte":"NC","Minneapolis":"MN","Montgomery":"AL","Nashville":"TN","Reston":"VA","Philadelphia":"PA",
    "Northern California":"CA","Norfolk":"VA","Richmond":"VA","Sacramento":"CA","Akron":"OH","Omaha":"NE",
    "Paducah":"KY","Pittsburgh":"PA","Davenport":"IA","San Antonio":"TX","Medford":"OR","Saint George":"UT",
    "Spokane":"WA","Springfield":"MO","Reno":"NV","Tampa":"FL","Milwaukee":"WI","Tucson":"AZ","Charleston":"WV",
    "Eugene":"OR",
}


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception as exc:
        debug_print(f"Connectivity retained load failed {path.name} -> {exc}")
        return pd.DataFrame()


def _finite(value) -> bool:
    numeric = pd.to_numeric(value, errors="coerce")
    return bool(pd.notna(numeric) and np.isfinite(float(numeric)))


def _infer_state(name: str, location: str) -> tuple[str, str]:
    name = str(name or "")
    location = str(location or "")
    if name.startswith("Amateur IX"):
        return "OR", "inferred_from_exchange_identity"
    if (
        name.startswith("Amateur Radio") or "US-West" in name or
        name.startswith("CoreSite - Any2East") or name.startswith("CoreSite - Any2West") or
        name.startswith("Pacific Wave") or name.startswith("Lightboard - American") or
        name.startswith("Lightboard - Vermont") or "West Coast" in location or
        "New York/New Jersey" in location
    ):
        return "MULTI", "multi_state_exchange"
    if name.startswith("Community IX - Northern Virginia") or name.startswith("DE-CIX Richmond") or "NoVA" in name or "Northern Virginia" in location:
        return "VA", "exchange_identity"
    if name.startswith("Northern New England"):
        return "ME", "exchange_identity"
    if name.startswith("Northwest Access"):
        return "OR", "exchange_identity"
    if name.startswith("Ninja-IX Auburn"):
        return "UNKNOWN", "ambiguous_location"
    if "Fremont / Neuheim" in location:
        return "CA", "primary_us_location"
    explicit_names = {"Massachusetts":"MA","Florida":"FL","Ohio":"OH","Indiana":"IN"}
    for token, state in explicit_names.items():
        if token in location:
            return state, "source_location"
    for state in ["AK","AL","AR","AZ","CA","CO","CT","DC","DE","FL","GA","HI","IA","ID","IL","IN","KS","KY","LA","MA","MD","ME","MI","MN","MO","MS","MT","NC","ND","NE","NH","NJ","NM","NV","NY","OH","OK","OR","PA","PR","RI","SC","SD","TN","TX","UT","VA","VT","WA","WI","WV","WY","GU","VI"]:
        if re.search(rf"(?:,|\s){state}(?:$|\s)", location):
            return state, "source_location"
    first = location.replace(" and ", ",").split(",")[0].strip()
    state = _CITY_STATE.get(first, "UNKNOWN")
    return state, "city_crosswalk" if state != "UNKNOWN" else "unresolved"


def _normalize_ixps(frame: pd.DataFrame) -> pd.DataFrame:
    columns = ["IXP Name","Location","State","State Assignment","Physical Locations","Reported Members","Observation Date","Source","Source URL","Evidence Class","Evidence Grade","Boundary"]
    if frame is None or frame.empty:
        return pd.DataFrame(columns=columns)
    output = frame.copy().rename(columns={"Physical locations":"Physical Locations", "Number of members":"Reported Members"})
    for column in columns:
        if column not in output.columns:
            output[column] = np.nan
    output["IXP Name"] = output["IXP Name"].fillna("").astype(str).str.strip()
    output["Location"] = output["Location"].fillna("").astype(str).str.strip()
    output["State"] = output["State"].astype("string")
    output["State Assignment"] = output["State Assignment"].astype("string")
    output["Physical Locations"] = pd.to_numeric(output["Physical Locations"], errors="coerce").fillna(0).astype(int)
    output["Reported Members"] = pd.to_numeric(output["Reported Members"], errors="coerce").fillna(0).astype(int)
    missing_state = output["State"].isna() | output["State"].str.strip().eq("")
    if missing_state.any():
        inferred = output.loc[missing_state].apply(lambda row: _infer_state(row["IXP Name"], row["Location"]), axis=1)
        output.loc[missing_state, "State"] = [item[0] for item in inferred]
        output.loc[missing_state, "State Assignment"] = [item[1] for item in inferred]
    output["Observation Date"] = pd.to_datetime(output["Observation Date"], errors="coerce", format="mixed").dt.date.astype("string")
    output["Source"] = output["Source"].fillna("Internet Society Pulse / PeeringDB")
    output["Source URL"] = output["Source URL"].fillna(PULSE_URL)
    output["Evidence Class"] = output["Evidence Class"].fillna("operator_self_reported_registry")
    output["Evidence Grade"] = output["Evidence Grade"].fillna("B")
    output["Boundary"] = output["Boundary"].fillna("Active IXPs listing at least 3 members; memberships are not unique networks.")
    return output.loc[output["IXP Name"].ne(""), columns].drop_duplicates("IXP Name", keep="last").sort_values(["State","Reported Members","IXP Name"], ascending=[True,False,True], kind="stable").reset_index(drop=True)


def _parse_pulse_pages() -> tuple[pd.DataFrame, pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    first_text = ""
    for page in range(1, 8):
        url = PULSE_URL if page == 1 else f"{PULSE_URL}?page={page}"
        response = requests.get(url, timeout=30, headers={"User-Agent":"ai-macro-connectivity/1.2"})
        response.raise_for_status()
        if page == 1:
            first_text = re.sub(r"\s+", " ", response.text)
        tables = pd.read_html(StringIO(response.text))
        table = next((table for table in tables if {"IXP Name","Location"}.issubset(set(map(str, table.columns)))), None)
        if table is None:
            raise ValueError(f"Pulse page {page} did not contain the IXP table")
        frames.append(table)
    ixps = pd.concat(frames, ignore_index=True, sort=False)
    ixps["Observation Date"] = pd.Timestamp.utcnow().date().isoformat()
    ixps = _normalize_ixps(ixps)
    if len(ixps) < 150:
        raise ValueError(f"Pulse IXP refresh returned only {len(ixps)} rows")

    def number(pattern: str):
        match = re.search(pattern, first_text, flags=re.I)
        return float(str(match.group(1)).replace(",", "")) if match else np.nan

    national = pd.DataFrame([{
        "Observation Date": pd.Timestamp.utcnow().date().isoformat(),
        "Active IXPs": number(r"There are\s+([\d,]+)\s+active Internet Exchange"),
        "Combined Reported Members": number(r"combined total of\s+([\d,]+)\s+members"),
        "Population Centers With IXP": number(r"IXPs are present in\s+([\d,]+)\s+of"),
        "Population Centers Over 300k": number(r"present in\s+[\d,]+\s+of the\s+([\d,]+)\s+population centers"),
        "Domestic Network Coverage Percent": number(r"([\d.]+)%\s+of networks are either members"),
        "Locally Cached Top Sites Percent": number(r"([\d.]+)%\s+of the 1000 most-visited websites"),
        "Active Domestic Networks": number(r"proportion of\s+([\d,]+)\s+active networks"),
        "Internet Resilience Score": number(r"Internet Resilience Score\s*([\d.]+)"),
        "Source":"Internet Society Pulse / PeeringDB",
        "Source URL":PULSE_URL,
        "Evidence Grade":"B",
        "Boundary":"IXP and membership data are self-reported; member totals are memberships, not unique networks.",
    }])
    return ixps, national


def _merge_national_refresh(refreshed: pd.DataFrame, retained: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    refreshed_row = refreshed.iloc[-1].to_dict() if isinstance(refreshed, pd.DataFrame) and not refreshed.empty else {}
    retained_row = retained.iloc[-1].to_dict() if isinstance(retained, pd.DataFrame) and not retained.empty else {}
    merged = dict(retained_row)
    merged.update({key: value for key, value in refreshed_row.items() if key not in REQUIRED_NATIONAL_FIELDS})
    live_fields: list[str] = []
    fallback_fields: list[str] = []
    missing_fields: list[str] = []
    for field in REQUIRED_NATIONAL_FIELDS:
        live_value = refreshed_row.get(field)
        retained_value = retained_row.get(field)
        if _finite(live_value):
            merged[field] = float(pd.to_numeric(live_value, errors="coerce"))
            live_fields.append(field)
        elif _finite(retained_value):
            merged[field] = float(pd.to_numeric(retained_value, errors="coerce"))
            fallback_fields.append(field)
        else:
            merged[field] = np.nan
            missing_fields.append(field)
    report = {"required_fields":list(REQUIRED_NATIONAL_FIELDS),"live_fields":live_fields,"retained_fields":fallback_fields,"missing_fields":missing_fields,"complete":not fallback_fields and not missing_fields}
    return pd.DataFrame([merged]), report


def _parse_telegeography_catalog() -> pd.DataFrame:
    response = requests.get(TELEGEOGRAPHY_URL, timeout=35, headers={"User-Agent":"ai-macro-connectivity/1.2"})
    response.raise_for_status()
    text = response.text
    names = []
    for match in re.finditer(r'href=["\']/submarine-cable/[^"\']+["\'][^>]*>(.*?)</a>', text, flags=re.I | re.S):
        clean = re.sub(r"<[^>]+>", " ", match.group(1))
        clean = re.sub(r"\s+", " ", clean).strip()
        if clean and clean not in names:
            names.append(clean)
    if len(names) < 80:
        # Some deployments serialize cable names in JSON rather than anchors.
        candidates = re.findall(r'"name"\s*:\s*"([^"\\]{2,120})"', text)
        for candidate in candidates:
            clean = bytes(candidate, "utf-8").decode("unicode_escape").strip()
            if clean and clean not in names:
                names.append(clean)
    if len(names) < 80:
        raise ValueError(f"TeleGeography catalog refresh returned only {len(names)} candidate systems")
    today = pd.Timestamp.utcnow().date().isoformat()
    rows=[]
    for raw in names:
        years=re.findall(r"\((20\d{2})\)", raw)
        rfs=int(years[-1]) if years else np.nan
        name=re.sub(r"\s*\((20\d{2})\)\s*$", "", raw).strip()
        status = "Planned" if _finite(rfs) and float(rfs) > pd.Timestamp.utcnow().year else "Current-year / planned or entering service" if _finite(rfs) and int(rfs) == pd.Timestamp.utcnow().year else "Listed without retained RFS year"
        rows.append({"Cable System":name,"Retained RFS Year":rfs,"Temporal Status":status,"Catalog Scope":"U.S.-connected catalog entry; may be international, territorial, domestic, or regional","Observation Date":today,"Source":"TeleGeography Submarine Cable Map","Source URL":TELEGEOGRAPHY_URL,"Evidence Grade":"B","Boundary":"Catalog presence is not FCC license status, activated capacity, traffic, or route ownership."})
    return pd.DataFrame(rows).drop_duplicates("Cable System", keep="last").sort_values(["Temporal Status","Retained RFS Year","Cable System"], na_position="last", kind="stable").reset_index(drop=True)


def _fetch_peeringdb_facilities() -> pd.DataFrame:
    records: list[dict] = []
    skip = 0
    limit = 250
    for _ in range(12):
        response = requests.get(PEERINGDB_FACILITY_URL, params={"country":"US","limit":limit,"skip":skip}, timeout=35, headers={"User-Agent":"ai-macro-connectivity/1.2"})
        response.raise_for_status()
        payload = response.json()
        batch = payload.get("data", []) if isinstance(payload, dict) else []
        if not batch:
            break
        records.extend(batch)
        if len(batch) < limit:
            break
        skip += limit
    if len(records) < 250:
        raise ValueError(f"PeeringDB facility refresh returned only {len(records)} U.S. rows")
    frame = pd.DataFrame(records)
    out = pd.DataFrame({
        "Facility ID": frame.get("id"),
        "Facility": frame.get("name"),
        "Organization": frame.get("org_name"),
        "City": frame.get("city"),
        "State": frame.get("state"),
        "Postal Code": frame.get("zipcode"),
        "Latitude": pd.to_numeric(frame.get("latitude"), errors="coerce"),
        "Longitude": pd.to_numeric(frame.get("longitude"), errors="coerce"),
        "Networks Present": pd.to_numeric(frame.get("net_count"), errors="coerce"),
        "Updated": frame.get("updated"),
    })
    out["Observation Date"] = pd.Timestamp.utcnow().date().isoformat()
    out["Source"] = "PeeringDB API"
    out["Source URL"] = "https://www.peeringdb.com/apidocs/"
    out["Evidence Grade"] = "B"
    out["Boundary"] = "Operator-maintained facility registry; presence and network counts are self-reported and not a regulatory census."
    return out.dropna(subset=["Facility"]).drop_duplicates("Facility ID", keep="last").reset_index(drop=True)


def _refresh_ntia_summary(retained: pd.DataFrame) -> pd.DataFrame:
    response = requests.get(NTIA_MIDDLE_MILE_URL, timeout=35, headers={"User-Agent":"ai-macro-connectivity/1.2"})
    response.raise_for_status()
    text = re.sub(r"\s+", " ", response.text)
    miles = re.search(r"(?:over|more than)\s+([\d,]+)\s+miles", text, flags=re.I)
    dollars = re.search(r"nearly\s+\$?([\d.]+)\s*(billion|million)", text, flags=re.I)
    if not miles or not dollars:
        raise ValueError("NTIA summary refresh did not expose both federal funding and fiber-mile totals")
    amount = float(dollars.group(1)) * (1_000_000_000 if dollars.group(2).lower() == "billion" else 1_000_000)
    row = retained.iloc[-1].to_dict() if isinstance(retained, pd.DataFrame) and not retained.empty else {}
    row.update({"Observation Date":pd.Timestamp.utcnow().date().isoformat(),"Federal Awards USD":amount,"New Fiber Miles":float(miles.group(1).replace(",", "")),"Miles Measure":f"More than {miles.group(1)}","Source":"NTIA BroadbandUSA Middle Mile Program","Source URL":NTIA_MIDDLE_MILE_URL,"Evidence Grade":"A","Boundary":"Program-level awarded and planned construction; not the full commercial long-haul or middle-mile network."})
    return pd.DataFrame([row])


def _published_development_by_state(campuses: pd.DataFrame) -> pd.DataFrame:
    if campuses is None or not isinstance(campuses, pd.DataFrame) or campuses.empty:
        return pd.DataFrame(columns=["State","Published Development MW","Published Campuses"])
    frame = campuses.copy()
    status = frame.get("Status", pd.Series("", index=frame.index)).fillna("").astype(str).str.casefold()
    allowed = {"proposed","planned","announced","approved / permitted / under construction","approved","permitted","under construction","expanding"}
    capacity_column = next((column for column in ["Published Capacity Estimate MW","Published Capacity MW","Capacity MW"] if column in frame.columns), None)
    if capacity_column is None or "State" not in frame.columns:
        return pd.DataFrame(columns=["State","Published Development MW","Published Campuses"])
    frame["Published Development MW"] = pd.to_numeric(frame[capacity_column], errors="coerce")
    frame = frame.loc[status.isin(allowed) & frame["Published Development MW"].gt(0)].copy()
    frame["State"] = frame["State"].fillna("").astype(str).str.strip().str.upper()
    return frame.groupby("State", as_index=False).agg(**{"Published Development MW":("Published Development MW","sum"),"Published Campuses":("Published Development MW","size")})


def _state_summary(ixps: pd.DataFrame, landing_markets: pd.DataFrame, middle_mile_awards: pd.DataFrame, campuses: pd.DataFrame, facilities: pd.DataFrame | None = None) -> pd.DataFrame:
    valid = ixps.loc[~ixps["State"].isin(["","MULTI","UNKNOWN"])].copy() if not ixps.empty else ixps
    if valid.empty:
        state = pd.DataFrame(columns=["State","IXPs","Reported Memberships","Physical Locations"])
    else:
        state = valid.groupby("State", as_index=False).agg(IXPs=("IXP Name","nunique"), **{"Reported Memberships":("Reported Members","sum"),"Physical Locations":("Physical Locations","sum")})
    if isinstance(landing_markets, pd.DataFrame) and not landing_markets.empty:
        landing = landing_markets.rename(columns={"State / Territory":"State"}).groupby("State", as_index=False).agg(**{"Landing Markets":("Landing Market","nunique")})
        state = state.merge(landing, on="State", how="outer")
    if isinstance(middle_mile_awards, pd.DataFrame) and not middle_mile_awards.empty:
        awards = middle_mile_awards.rename(columns={"State / Territory":"State"}).copy()
        awards["Federal Award"] = pd.to_numeric(awards.get("Federal Award"), errors="coerce")
        awards["Disclosed Route Miles"] = pd.to_numeric(awards.get("Disclosed Route Miles"), errors="coerce")
        award_state = awards.groupby("State", as_index=False).agg(**{"Middle-Mile Awards":("Award Recipient","size"),"Federal Middle-Mile Award USD":("Federal Award","sum"),"Disclosed Award Miles":("Disclosed Route Miles",lambda values: values.sum(min_count=1))})
        state = state.merge(award_state, on="State", how="outer")
    if isinstance(facilities, pd.DataFrame) and not facilities.empty and "State" in facilities.columns:
        fac = facilities.groupby("State", as_index=False).agg(**{"PeeringDB Facilities":("Facility","nunique"),"Facility Networks Present":("Networks Present",lambda values: pd.to_numeric(values, errors="coerce").sum(min_count=1))})
        state = state.merge(fac, on="State", how="outer")
    state = state.merge(_published_development_by_state(campuses), on="State", how="outer")
    integer_columns = ["IXPs","Reported Memberships","Physical Locations","Landing Markets","Middle-Mile Awards","Published Campuses","PeeringDB Facilities"]
    for column in integer_columns:
        if column not in state.columns:
            state[column] = 0
        state[column] = pd.to_numeric(state[column], errors="coerce").fillna(0).astype(int)
    for column in ["Federal Middle-Mile Award USD","Disclosed Award Miles","Facility Networks Present","Published Development MW"]:
        if column not in state.columns:
            state[column] = np.nan
        state[column] = pd.to_numeric(state[column], errors="coerce")
    state["MW per reported membership"] = state["Published Development MW"] / state["Reported Memberships"].replace(0, np.nan)
    state["Connectivity Presence"] = np.select([state["Reported Memberships"].ge(250),state["Reported Memberships"].ge(75),state["Reported Memberships"].gt(0)],["Deep","Established","Present"],default="Limited public evidence")
    capacity = state["Published Development MW"].fillna(0)
    memberships = state["Reported Memberships"].fillna(0)
    state["Capacity-Connectivity Flag"] = np.select([capacity.ge(5000) & memberships.lt(75),capacity.ge(1000) & memberships.lt(75),capacity.gt(0) & memberships.eq(0)],["High-capacity mismatch","Review mismatch","No reported IXP memberships"],default="No mismatch flag")
    state["Mismatch Priority"] = np.log1p(capacity.clip(lower=0)) / np.log1p(memberships.clip(lower=0) + 2)
    return state.sort_values(["Reported Memberships","IXPs"], ascending=False, kind="stable").reset_index(drop=True)


def _haversine_miles(lat1, lon1, lat2, lon2) -> float:
    values = [pd.to_numeric(value, errors="coerce") for value in [lat1, lon1, lat2, lon2]]
    if any(pd.isna(value) for value in values):
        return np.nan
    lat1, lon1, lat2, lon2 = map(radians, map(float, values))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 3958.8 * 2 * asin(sqrt(a))


def _nearest_market(lat, lon, frame: pd.DataFrame, name_column: str) -> tuple[str, float]:
    if not isinstance(frame, pd.DataFrame) or frame.empty or not {"Latitude","Longitude",name_column}.issubset(frame.columns):
        return "", np.nan
    distances = frame.apply(lambda row: _haversine_miles(lat, lon, row.get("Latitude"), row.get("Longitude")), axis=1)
    valid = pd.to_numeric(distances, errors="coerce").dropna()
    if valid.empty:
        return "", np.nan
    index = valid.idxmin()
    return str(frame.loc[index, name_column]), float(valid.loc[index])


def _ixp_market_coordinates(ixp_markets: pd.DataFrame, landing_markets: pd.DataFrame) -> pd.DataFrame:
    # The retained IXP source does not publish coordinates.  Reuse coordinates
    # only where an interconnection location matches a selected landing market;
    # otherwise campus screening remains state-level for IXP depth.
    if not isinstance(ixp_markets, pd.DataFrame) or ixp_markets.empty:
        return pd.DataFrame()
    output = ixp_markets.copy()
    output["Latitude"] = np.nan
    output["Longitude"] = np.nan
    if isinstance(landing_markets, pd.DataFrame) and not landing_markets.empty:
        for idx, row in output.iterrows():
            market = str(row.get("Interconnection Market") or "").casefold()
            matches = landing_markets.loc[landing_markets["Landing Market"].astype(str).str.casefold().map(lambda value: any(token and token in value for token in re.split(r"\s*/\s*|,\s*", market)))]
            if not matches.empty:
                output.loc[idx, ["Latitude","Longitude"]] = matches.iloc[0][["Latitude","Longitude"]].values
    return output


def _campus_connectivity_snapshot(campuses: pd.DataFrame, state_summary: pd.DataFrame, landing_markets: pd.DataFrame, facilities: pd.DataFrame | None = None) -> pd.DataFrame:
    columns = ["Facility","Operator","City","State","Status","Published Capacity Estimate MW","Reported State IXP Memberships","State IXPs","Landing Markets","Middle-Mile Awards","Nearest Selected Landing Market","Miles to Selected Landing Market","Nearest PeeringDB Facility","Miles to PeeringDB Facility","Connectivity Presence","Capacity-Connectivity Flag","Screening Boundary"]
    if not isinstance(campuses, pd.DataFrame) or campuses.empty or not isinstance(state_summary, pd.DataFrame):
        return pd.DataFrame(columns=columns)
    frame = campuses.copy()
    capacity_column = next((column for column in ["Published Capacity Estimate MW","Published Capacity MW","Capacity MW"] if column in frame.columns), None)
    if capacity_column is None or "State" not in frame.columns:
        return pd.DataFrame(columns=columns)
    status = frame.get("Status", pd.Series("", index=frame.index)).fillna("").astype(str).str.casefold()
    allowed = {"proposed","planned","announced","approved / permitted / under construction","approved","permitted","under construction","expanding"}
    frame = frame.loc[status.isin(allowed)].copy()
    frame["Published Capacity Estimate MW"] = pd.to_numeric(frame[capacity_column], errors="coerce")
    frame = frame.loc[frame["Published Capacity Estimate MW"].gt(0)].copy()
    frame["State"] = frame["State"].fillna("").astype(str).str.strip().str.upper()
    join_columns = ["State","Reported Memberships","IXPs","Landing Markets","Middle-Mile Awards","Connectivity Presence","Capacity-Connectivity Flag"]
    join = state_summary[[column for column in join_columns if column in state_summary.columns]].copy()
    frame = frame.merge(join, on="State", how="left")
    frame = frame.rename(columns={"Reported Memberships":"Reported State IXP Memberships","IXPs":"State IXPs"})
    nearest_landing=[]
    nearest_landing_miles=[]
    nearest_facility=[]
    nearest_facility_miles=[]
    for _, row in frame.iterrows():
        landing_name, landing_distance = _nearest_market(row.get("Latitude"), row.get("Longitude"), landing_markets, "Landing Market")
        facility_name, facility_distance = _nearest_market(row.get("Latitude"), row.get("Longitude"), facilities if isinstance(facilities, pd.DataFrame) else pd.DataFrame(), "Facility")
        nearest_landing.append(landing_name)
        nearest_landing_miles.append(landing_distance)
        nearest_facility.append(facility_name)
        nearest_facility_miles.append(facility_distance)
    frame["Nearest Selected Landing Market"] = nearest_landing
    frame["Miles to Selected Landing Market"] = nearest_landing_miles
    frame["Nearest PeeringDB Facility"] = nearest_facility
    frame["Miles to PeeringDB Facility"] = nearest_facility_miles
    for column in ["Facility","Operator","City","Status"]:
        if column not in frame.columns:
            frame[column] = ""
    frame["Screening Boundary"] = "Proximity and state-level public evidence only; no direct campus route, latency, capacity, or path-diversity claim."
    for column in columns:
        if column not in frame.columns:
            frame[column] = np.nan
    return frame[columns].sort_values(["Capacity-Connectivity Flag","Published Capacity Estimate MW"], ascending=[True,False], kind="stable").reset_index(drop=True)


def _augment_national(national: pd.DataFrame, cables: pd.DataFrame, landing_markets: pd.DataFrame, ixp_markets: pd.DataFrame, facilities: pd.DataFrame, facility_summary: pd.DataFrame, middle_summary: pd.DataFrame) -> dict:
    row = national.iloc[-1].to_dict() if isinstance(national, pd.DataFrame) and not national.empty else {}
    row["U.S.-Connected Cable Catalog Entries"] = int(len(cables))
    if isinstance(cables, pd.DataFrame) and not cables.empty:
        row["Future / Current-Year Cable Entries"] = int(cables.get("Temporal Status", pd.Series(dtype=str)).astype(str).isin(["Planned","Current-year / planned or entering service"]).sum())
    row["Selected Landing Markets"] = int(len(landing_markets))
    row["Interconnection Markets"] = int(len(ixp_markets))
    if isinstance(facilities, pd.DataFrame) and not facilities.empty:
        row["PeeringDB Facilities"] = int(facilities.get("Facility", pd.Series(dtype=str)).nunique())
    elif isinstance(facility_summary, pd.DataFrame) and not facility_summary.empty:
        row["PeeringDB Facility Coverage Floor"] = _finite(facility_summary.iloc[-1].get("Public Search Result Floor")) and int(float(facility_summary.iloc[-1].get("Public Search Result Floor"))) or 0
    if isinstance(middle_summary, pd.DataFrame) and not middle_summary.empty:
        mm = middle_summary.iloc[-1]
        award_records = pd.to_numeric(mm.get("Award Records"), errors="coerce")
        reached = pd.to_numeric(mm.get("States and Territories Reached"), errors="coerce")
        row["Middle-Mile Award Records"] = int(award_records) if pd.notna(award_records) else 0
        row["Middle-Mile States and Territories"] = int(reached) if pd.notna(reached) else 0
        row["Middle-Mile Federal Awards USD"] = _finite(mm.get("Federal Awards USD")) and float(mm.get("Federal Awards USD")) or np.nan
        row["Middle-Mile New Fiber Miles"] = _finite(mm.get("New Fiber Miles")) and float(mm.get("New Fiber Miles")) or np.nan
    return row


@st.cache_data(ttl=86400)
def load_connectivity_data(campuses: pd.DataFrame | None = None, *, force_refresh: bool = False, refresh_token: int = 0, allow_live: bool = False) -> dict:
    del refresh_token
    live_refresh = bool(force_refresh and allow_live)
    ixps = _normalize_ixps(_load_csv(IXP_PATH))
    retained_national = _load_csv(NATIONAL_PATH)
    national = retained_national.copy()
    cable_systems = _load_csv(CABLE_SYSTEM_PATH)
    landing_markets = _load_csv(LANDING_MARKET_PATH)
    ixp_markets = _load_csv(INTERCONNECTION_MARKET_PATH)
    facility_summary = _load_csv(FACILITY_SUMMARY_PATH)
    facilities = pd.DataFrame()
    middle_awards = _load_csv(MIDDLE_MILE_AWARDS_PATH)
    retained_middle_summary = _load_csv(MIDDLE_MILE_SUMMARY_PATH)
    middle_summary = retained_middle_summary.copy()

    layer_reports = {
        "ixp": {"source_mode":"retained","error":""},
        "cable_catalog": {"source_mode":"retained","error":""},
        "interconnection_facilities": {"source_mode":"retained_summary","error":""},
        "middle_mile": {"source_mode":"retained","error":""},
    }
    national_validation = {"required_fields":list(REQUIRED_NATIONAL_FIELDS),"live_fields":[],"retained_fields":[],"missing_fields":[],"complete":True}

    if live_refresh:
        try:
            refreshed_ixps, refreshed_national = _parse_pulse_pages()
            national, national_validation = _merge_national_refresh(refreshed_national, retained_national)
            if national_validation["missing_fields"]:
                raise ValueError("Missing required national fields: " + ", ".join(national_validation["missing_fields"]))
            ixps = refreshed_ixps
            ixp_markets = _load_csv(INTERCONNECTION_MARKET_PATH)
            if ixp_markets.empty:
                ixp_markets = ixps.groupby(["Location","State"], as_index=False).agg(IXPs=("IXP Name","nunique"), **{"Reported Memberships":("Reported Members","sum"),"IXP Physical Location References":("Physical Locations","sum")}).rename(columns={"Location":"Interconnection Market"})
            layer_reports["ixp"]["source_mode"] = "live_refresh" if national_validation["complete"] else "partial_refresh"
            if repository_writes_enabled():
                atomic_write_csv(ixps, IXP_PATH)
                atomic_write_csv(national, NATIONAL_PATH)
        except Exception as exc:
            layer_reports["ixp"] = {"source_mode":"retained_fallback","error":f"{type(exc).__name__}: {exc}"}
            national = retained_national.copy()
            debug_print(f"Connectivity IXP refresh failed -> {exc}")

        try:
            refreshed_cables = _parse_telegeography_catalog()
            cable_systems = refreshed_cables
            layer_reports["cable_catalog"]["source_mode"] = "live_refresh"
            if repository_writes_enabled():
                atomic_write_csv(cable_systems, CABLE_SYSTEM_PATH)
        except Exception as exc:
            layer_reports["cable_catalog"] = {"source_mode":"retained_fallback","error":f"{type(exc).__name__}: {exc}"}
            debug_print(f"Connectivity cable refresh failed -> {exc}")

        try:
            facilities = _fetch_peeringdb_facilities()
            layer_reports["interconnection_facilities"]["source_mode"] = "live_refresh"
        except Exception as exc:
            layer_reports["interconnection_facilities"] = {"source_mode":"retained_summary","error":f"{type(exc).__name__}: {exc}"}
            debug_print(f"Connectivity facility refresh failed -> {exc}")

        try:
            middle_summary = _refresh_ntia_summary(retained_middle_summary)
            layer_reports["middle_mile"]["source_mode"] = "live_refresh"
            if repository_writes_enabled():
                atomic_write_csv(middle_summary, MIDDLE_MILE_SUMMARY_PATH)
        except Exception as exc:
            layer_reports["middle_mile"] = {"source_mode":"retained_fallback","error":f"{type(exc).__name__}: {exc}"}
            debug_print(f"Connectivity middle-mile refresh failed -> {exc}")

    live_layers = sum(report.get("source_mode") == "live_refresh" for report in layer_reports.values())
    fallback_layers = sum("fallback" in str(report.get("source_mode")) or str(report.get("source_mode")) == "retained_summary" for report in layer_reports.values())
    source_mode = "retained" if not live_refresh else "live_refresh" if live_layers == len(layer_reports) else "partial_refresh" if live_layers else "retained_fallback"

    campus_frame = campuses if isinstance(campuses, pd.DataFrame) else pd.DataFrame()
    state = _state_summary(ixps, landing_markets, middle_awards, campus_frame, facilities)
    campus_snapshot = _campus_connectivity_snapshot(campus_frame, state, landing_markets, facilities)
    national_row = _augment_national(national, cable_systems, landing_markets, ixp_markets, facilities, facility_summary, middle_summary)
    mismatch_states = int(state["Capacity-Connectivity Flag"].isin(["High-capacity mismatch","Review mismatch","No reported IXP memberships"]).sum()) if not state.empty else 0
    planned_cables = int(cable_systems.get("Temporal Status", pd.Series(dtype=str)).astype(str).eq("Planned").sum()) if not cable_systems.empty else 0
    award_miles = pd.to_numeric(middle_awards.get("Disclosed Route Miles"), errors="coerce") if not middle_awards.empty else pd.Series(dtype=float)
    return {
        "source_mode": source_mode,
        "phase": CONNECTIVITY_PHASE,
        "load_report": {
            "source_mode":source_mode,
            "requested":bool(force_refresh),
            "authorized":bool(allow_live),
            "executed":live_refresh,
            "error":"; ".join(report.get("error", "") for report in layer_reports.values() if report.get("error")),
            "errors":{name:report.get("error") for name,report in layer_reports.items() if report.get("error")},
            "layers":layer_reports,
            "ixp_rows":int(len(ixps)),
            "national_validation":national_validation,
            "live_layers":live_layers,
            "fallback_layers":fallback_layers,
        },
        "ixp_snapshot": ixps,
        "national_summary": national_row,
        "gateway_ledger": _load_csv(GATEWAY_PATH),
        "submarine_cable_systems": cable_systems,
        "cable_landing_markets": landing_markets,
        "interconnection_market_summary": ixp_markets,
        "interconnection_facilities": facilities,
        "interconnection_facility_summary": facility_summary,
        "middle_mile_awards": middle_awards,
        "middle_mile_summary": middle_summary.iloc[-1].to_dict() if isinstance(middle_summary, pd.DataFrame) and not middle_summary.empty else {},
        "state_summary": state,
        "campus_connectivity_snapshot": campus_snapshot,
        "source_manifest": _load_csv(MANIFEST_PATH),
        "coverage": {
            "cable_catalog_entries": int(len(cable_systems)),
            "planned_cable_entries": planned_cables,
            "selected_landing_markets": int(len(landing_markets)),
            "ixp_rows": int(len(ixps)),
            "interconnection_markets": int(len(ixp_markets)),
            "facility_rows_live": int(len(facilities)),
            "facility_search_floor": (lambda value: int(value) if pd.notna(value) else 0)(pd.to_numeric(facility_summary.iloc[-1].get("Public Search Result Floor"), errors="coerce")) if not facility_summary.empty else 0,
            "middle_mile_awards": int(len(middle_awards)),
            "middle_mile_award_miles_disclosed": float(award_miles.sum(min_count=1)) if not award_miles.empty and pd.notna(award_miles.sum(min_count=1)) else np.nan,
            "states_with_ixp_evidence": int(state["Reported Memberships"].gt(0).sum()) if not state.empty else 0,
            "mismatch_states": mismatch_states,
            "campuses_screened": int(len(campus_snapshot)),
            "campuses_with_landing_proximity": int(pd.to_numeric(campus_snapshot.get("Miles to Selected Landing Market"), errors="coerce").notna().sum()) if not campus_snapshot.empty else 0,
            "campuses_with_live_facility_proximity": int(pd.to_numeric(campus_snapshot.get("Miles to PeeringDB Facility"), errors="coerce").notna().sum()) if not campus_snapshot.empty else 0,
        },
    }
