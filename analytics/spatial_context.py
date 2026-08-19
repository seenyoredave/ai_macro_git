from __future__ import annotations

import re

import numpy as np
import pandas as pd

from loaders.data_center_registry import assert_campus_foreign_keys


def _county_key(value) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()
    for suffix in (" county", " parish", " borough", " census area", " municipality", " city and borough"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
            break
    return text


def _normalize_fips(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(5) if digits else ""


def _text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.casefold() == "nan" else text


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    """Return an index-aligned numeric Series for an optional column."""
    values = frame[column] if column in frame.columns else pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(values, errors="coerce")


def _data_center_context_registry(infrastructure: dict) -> pd.DataFrame:
    """Return the program-wide data-center campus set."""
    campuses = infrastructure.get("data_center_registry")
    if not isinstance(campuses, pd.DataFrame):
        raise ValueError("Infrastructure payload is missing the Universal Data Center Registry")
    if "Campus ID" not in campuses.columns:
        raise ValueError("Universal Data Center Registry is missing Campus ID")
    if campuses["Campus ID"].astype(str).duplicated().any():
        raise ValueError("Universal Data Center Registry contains duplicate Campus IDs")
    return campuses.copy()


def _pws_point_key(latitude, longitude) -> str:
    lat = pd.to_numeric(latitude, errors="coerce")
    lon = pd.to_numeric(longitude, errors="coerce")
    if pd.isna(lat) or pd.isna(lon):
        return ""
    return f"{float(lat):.5f}|{float(lon):.5f}"


def _pws_query_keys(registry: pd.DataFrame) -> pd.DataFrame:
    from water.epa_pws import query_key

    output = registry.copy()
    campus_ids: list[str] = []
    query_keys: list[str] = []
    point_keys: list[str] = []
    for index, row in output.iterrows():
        campus_id = _text(row.get("Campus ID"))
        if not campus_id:
            raise ValueError(f"Water campus row {index} is missing Campus ID")
        latitude = pd.to_numeric(row.get("Latitude"), errors="coerce")
        longitude = pd.to_numeric(row.get("Longitude"), errors="coerce")
        point_key = _pws_point_key(latitude, longitude)
        key = query_key(campus_id, float(latitude), float(longitude)) if point_key else ""
        campus_ids.append(campus_id)
        query_keys.append(key)
        point_keys.append(point_key)
    output["_pws_campus_id"] = campus_ids
    output["_pws_query_key"] = query_keys
    output["_pws_point_key"] = point_keys
    return output


def _pws_context_rows(frame: pd.DataFrame, key_column: str, prefix: str) -> pd.DataFrame:
    rows = []
    for key, group in frame.groupby(key_column, sort=False, dropna=False):
        source_key = str(key or "").strip()
        if not source_key:
            continue
        statuses = set(group["Query Status"].astype(str))
        resolved = bool(statuses.intersection({"matched", "no_match"}))
        matched = group.loc[group["Query Status"].eq("matched") & group["PWSID"].ne("")].copy()
        pwsids = sorted(set(matched["PWSID"].tolist()))
        names = sorted({name for name in matched["PWS Name"].tolist() if name})
        bases = {value.casefold() for value in matched["Boundary Basis"].tolist() if value}
        authoritative = "authoritative" in bases
        modeled = "modeled" in bases
        if authoritative and modeled:
            basis = "mixed"
        elif authoritative:
            basis = "authoritative"
        elif modeled:
            basis = "modeled"
        elif pwsids:
            basis = "unclassified"
        else:
            basis = ""
        rows.append(
            {
                "_pws_lookup_key": f"{prefix}:{source_key}",
                "PWS Service Area Query Resolved": resolved,
                "PWS Service Area Overlap": bool(pwsids),
                "PWS Match Count": int(len(pwsids)),
                "PWSIDs": "; ".join(pwsids),
                "PWS Names": "; ".join(names),
                "PWS Boundary Basis": basis,
                "PWS Authoritative Boundary Overlap": authoritative,
                "PWS Modeled Boundary Overlap": modeled,
                "PWS Ambiguous Overlap": len(pwsids) > 1,
            }
        )
    return pd.DataFrame(rows)


def _pws_context(matches: pd.DataFrame | None) -> pd.DataFrame:
    frame = matches.copy() if isinstance(matches, pd.DataFrame) else pd.DataFrame()
    if frame.empty or "Query Key" not in frame.columns:
        return pd.DataFrame()
    for column in ("PWSID", "PWS Name", "Boundary Basis", "Query Status"):
        if column not in frame.columns:
            frame[column] = ""
        frame[column] = frame[column].fillna("").astype(str).str.strip()
    if "Latitude" not in frame.columns:
        frame["Latitude"] = np.nan
    if "Longitude" not in frame.columns:
        frame["Longitude"] = np.nan
    frame["_pws_point_key"] = [
        _pws_point_key(latitude, longitude)
        for latitude, longitude in zip(frame["Latitude"], frame["Longitude"])
    ]

    by_query = _pws_context_rows(frame, "Query Key", "q")
    by_point = _pws_context_rows(
        frame.loc[frame["_pws_point_key"].ne("")],
        "_pws_point_key",
        "p",
    )
    populated = [part for part in (by_query, by_point) if not part.empty]
    if not populated:
        return pd.DataFrame()
    return pd.concat(populated, ignore_index=True, sort=False).drop_duplicates(
        "_pws_lookup_key", keep="last"
    )


def _merge_refresh_reports(water: dict, local_report: dict) -> None:
    refresh = dict(water.get("refresh_report") or {})
    refresh["local_context"] = dict(local_report or {})
    existing_errors = dict(refresh.get("errors") or {})
    local_errors = dict((local_report or {}).get("errors") or {})
    for key, value in local_errors.items():
        existing_errors[f"local_{key}"] = value
    if existing_errors:
        refresh["errors"] = existing_errors
    datasets = list(refresh.get("refreshed_datasets") or [])
    datasets.extend(list((local_report or {}).get("refreshed_datasets") or []))
    if datasets:
        refresh["refreshed_datasets"] = list(dict.fromkeys(datasets))

    local_mode = str((local_report or {}).get("source_mode") or "")
    current_mode = str(refresh.get("source_mode") or water.get("source_mode") or "retained_local")
    if local_mode in {"failed", "partial_refresh"} or current_mode in {"failed", "retained_fallback", "partial_refresh"}:
        refresh["source_mode"] = "partial_refresh"
    elif local_mode == "live_refresh" or current_mode == "live_refresh":
        refresh["source_mode"] = "live_refresh"
    water["refresh_report"] = refresh
    water["source_mode"] = str(refresh.get("source_mode") or water.get("source_mode") or "retained_local")


def attach_water_context(infrastructure_data: dict, water_data: dict) -> tuple[dict, dict]:
    infrastructure = dict(infrastructure_data or {})
    water = dict(water_data or {})
    registry = _data_center_context_registry(infrastructure)
    counties = water.get("usgs_counties")
    state_drought = water.get("usdm_state_drought")
    county_drought = water.get("usdm_county_drought")
    pws_matches = water.get("epa_pws_matches")
    water["campus_context_source"] = "data_center_registry"
    if not isinstance(counties, pd.DataFrame):
        counties = pd.DataFrame()
    if not isinstance(state_drought, pd.DataFrame):
        state_drought = pd.DataFrame()
    if not isinstance(county_drought, pd.DataFrame):
        county_drought = pd.DataFrame()
    if not isinstance(pws_matches, pd.DataFrame):
        pws_matches = pd.DataFrame()
    registry = registry.copy()
    if registry.empty:
        water["campus_context"] = registry
        water["campus_context_summary"] = {"campuses": 0}
        return infrastructure, water

    registry["_state_key"] = registry.get("State", "").fillna("").astype(str).str.upper().str.strip()
    registry["_county_key"] = registry.get("County", "").map(_county_key)
    if not counties.empty and {"State", "County"}.issubset(counties.columns):
        context = counties.copy()
        context["_state_key"] = context["State"].fillna("").astype(str).str.upper().str.strip()
        context["_county_key"] = context["County"].map(_county_key)
        keep = [
            "_state_key", "_county_key", "FIPS", "Year", "Groundwater Withdrawal Mgal/d",
            "Surface Water Withdrawal Mgal/d", "Freshwater Withdrawal Mgal/d",
            "Saline Withdrawal Mgal/d", "Total Withdrawal Mgal/d", "Partial Consumptive Use Mgal/d",
        ]
        context = context[[column for column in keep if column in context.columns]].drop_duplicates(
            ["_state_key", "_county_key"], keep="last"
        )
        registry = registry.merge(context, on=["_state_key", "_county_key"], how="left", validate="many_to_one")
    registry["_fips_key"] = registry.get("FIPS", pd.Series("", index=registry.index)).map(_normalize_fips)
    registry = _pws_query_keys(registry)

    if bool(water.get("local_context_refresh_requested")):
        try:
            from water.local_context import refresh_local_water_context

            local = refresh_local_water_context(registry)
            refreshed_county = local.get("usdm_county_drought")
            refreshed_pws = local.get("epa_pws_matches")
            if isinstance(refreshed_county, pd.DataFrame) and not refreshed_county.empty:
                county_drought = refreshed_county
                water["usdm_county_drought"] = refreshed_county
            if isinstance(refreshed_pws, pd.DataFrame) and not refreshed_pws.empty:
                pws_matches = refreshed_pws
                water["epa_pws_matches"] = refreshed_pws
            manifest = local.get("source_manifest")
            if isinstance(manifest, pd.DataFrame):
                water["source_manifest"] = manifest
                active = manifest.loc[manifest.get("ingestion_status", "").eq("active")]
                water["active_source_count"] = int(len(active))
            _merge_refresh_reports(water, dict(local.get("report") or {}))
        except Exception as exc:
            _merge_refresh_reports(
                water,
                {
                    "source_mode": "failed",
                    "refreshed_datasets": [],
                    "errors": {"refresh": f"{type(exc).__name__}: {exc}"},
                },
            )

    # Current county drought is joined by 5-digit FIPS.
    if not county_drought.empty and "FIPS" in county_drought.columns:
        local = county_drought.copy()
        local["_fips_key"] = local["FIPS"].map(_normalize_fips)
        rename = {
            "Snapshot Date": "County Drought Snapshot Date",
            "D0+ Area Percent": "County D0+ Area Percent",
            "D1+ Area Percent": "County D1+ Area Percent",
            "D2+ Area Percent": "County D2+ Area Percent",
            "D3+ Area Percent": "County D3+ Area Percent",
            "D4 Area Percent": "County D4 Area Percent",
            "Source": "County Drought Source",
            "Source URL": "County Drought Source URL",
        }
        local = local.rename(columns=rename)
        keep = ["_fips_key", *rename.values()]
        local = local[[column for column in keep if column in local.columns]].drop_duplicates("_fips_key", keep="last")
        registry = registry.merge(local, on="_fips_key", how="left", validate="many_to_one")

    if not state_drought.empty and "State" in state_drought.columns:
        drought_context = state_drought.copy()
        drought_context["_state_key"] = drought_context["State"].fillna("").astype(str).str.upper().str.strip()
        drought_columns = [
            "_state_key", "Snapshot Date", "D0+ Area Percent", "D1+ Area Percent",
            "D2+ Area Percent", "D3+ Area Percent", "D4 Area Percent",
            "Population in Drought", "Source", "Source URL",
        ]
        drought_context = drought_context[
            [column for column in drought_columns if column in drought_context.columns]
        ].drop_duplicates("_state_key", keep="last")
        registry = registry.merge(drought_context, on="_state_key", how="left", suffixes=("", " Drought"), validate="many_to_one")

    pws_query_keys = set(
        pws_matches.get("Query Key", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
    ) if isinstance(pws_matches, pd.DataFrame) and not pws_matches.empty else set()
    registry["_pws_lookup_key"] = [
        f"q:{query_key_value}"
        if query_key_value and query_key_value in pws_query_keys
        else f"p:{point_key_value}" if point_key_value else ""
        for query_key_value, point_key_value in zip(
            registry["_pws_query_key"], registry["_pws_point_key"]
        )
    ]
    pws_context = _pws_context(pws_matches)
    if not pws_context.empty:
        registry = registry.merge(pws_context, on="_pws_lookup_key", how="left", validate="many_to_one")
    for column, default in (
        ("PWS Service Area Query Resolved", False),
        ("PWS Service Area Overlap", False),
        ("PWS Authoritative Boundary Overlap", False),
        ("PWS Modeled Boundary Overlap", False),
        ("PWS Ambiguous Overlap", False),
    ):
        if column not in registry.columns:
            registry[column] = default
        registry[column] = registry[column].map(lambda value: bool(value) if pd.notna(value) else default)
    if "PWS Match Count" not in registry.columns:
        registry["PWS Match Count"] = 0
    registry["PWS Match Count"] = pd.to_numeric(registry["PWS Match Count"], errors="coerce").fillna(0).astype(int)
    for column in ("PWSIDs", "PWS Names", "PWS Boundary Basis"):
        if column not in registry.columns:
            registry[column] = ""
        registry[column] = registry[column].fillna("").astype(str)

    registry = registry.drop(
        columns=[
            "_state_key", "_county_key", "_fips_key", "_pws_campus_id",
            "_pws_query_key", "_pws_point_key", "_pws_lookup_key",
        ],
        errors="ignore",
    )
    direct_fields = [
        "Water Withdrawal Gallons/Year", "Water Consumption Gallons/Year", "Site WUE L/kWh",
        "Water Permit or Utility Record", "Cooling System", "Water Source",
    ]
    direct_mask = pd.Series(False, index=registry.index)
    for field in direct_fields:
        if field not in registry.columns:
            continue
        if field in {"Water Withdrawal Gallons/Year", "Water Consumption Gallons/Year", "Site WUE L/kWh"}:
            direct_mask |= pd.to_numeric(registry[field], errors="coerce").notna()
        else:
            values = registry[field].fillna("").astype(str).str.casefold().str.strip()
            direct_mask |= values.ne("") & ~values.str.contains("not disclosed|unknown|unavailable", regex=True)
    registry["Direct Water Evidence"] = direct_mask
    registry["County Water Context Available"] = _numeric_series(
        registry, "Total Withdrawal Mgal/d"
    ).notna()

    county_d1 = _numeric_series(registry, "County D1+ Area Percent")
    county_d2 = _numeric_series(registry, "County D2+ Area Percent")
    state_d1 = _numeric_series(registry, "D1+ Area Percent")

    # Water owns an enriched domain view keyed by Campus ID. The registry
    # registry remains unchanged; every water row must resolve to that universe.
    if registry["Campus ID"].astype(str).duplicated().any():
        duplicate_ids = registry.loc[registry["Campus ID"].astype(str).duplicated(False), "Campus ID"].astype(str).unique().tolist()
        raise ValueError(f"Water enrichment multiplied Campus IDs: {duplicate_ids[:10]}")
    assert_campus_foreign_keys(infrastructure["data_center_registry"], registry[["Campus ID"]], domain="water", allow_subset=False)
    water["campus_context"] = registry
    water["campus_context_summary"] = {
        "campuses": int(len(registry)),
        "mapped_campuses": int(pd.to_numeric(registry.get("Latitude"), errors="coerce").notna().sum()),
        "states": int(registry.get("State", pd.Series(dtype=object)).replace("", np.nan).nunique()),
        "state_identified_records": int(registry.get("State", pd.Series("", index=registry.index)).fillna("").astype(str).str.strip().ne("").sum()),
        "county_context_records": int(registry["County Water Context Available"].sum()),
        "county_drought_context_records": int(county_d1.notna().sum()),
        "state_drought_context_records": int(state_d1.notna().sum()),
        "direct_water_evidence_records": int(registry["Direct Water Evidence"].sum()),
        "quantified_withdrawal_records": int(pd.to_numeric(registry.get("Water Withdrawal Gallons/Year", pd.Series(np.nan, index=registry.index)), errors="coerce").notna().sum()),
        "quantified_consumption_records": int(pd.to_numeric(registry.get("Water Consumption Gallons/Year", pd.Series(np.nan, index=registry.index)), errors="coerce").notna().sum()),
        "pws_service_area_query_resolved_records": int(registry["PWS Service Area Query Resolved"].sum()),
        "pws_service_area_overlap_records": int(registry["PWS Service Area Overlap"].sum()),
        "pws_authoritative_overlap_records": int(registry["PWS Authoritative Boundary Overlap"].sum()),
        "pws_modeled_overlap_records": int(registry["PWS Modeled Boundary Overlap"].sum()),
        "pws_ambiguous_overlap_records": int(registry["PWS Ambiguous Overlap"].sum()),
    }
    return infrastructure, water


def infrastructure_attribution(history: pd.DataFrame | None) -> dict:
    """Compare enabling-system construction with lagged channel baselines.

    Private channels are benchmarked against the relevant broad private
    construction denominator. Public water, roads, and transit are benchmarked
    against their lagged share of the selected public-system construction mix.
    The result is a statistical alignment diagnostic, not AI attribution.
    """
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        return {"history": pd.DataFrame(), "latest": {}, "components": pd.DataFrame()}
    frame = history.copy()
    frame["Observation Date"] = pd.to_datetime(frame.get("Observation Date"), errors="coerce", format="mixed")
    required = [
        "Data Center Construction",
        "Computer, Electronic & Electrical Manufacturing Construction",
        "Private Manufacturing Construction",
        "Electric Power Construction",
        "Communication Construction",
        "Private Nonresidential Construction",
        "Public Water Supply Construction",
        "Public Highway and Street Construction",
        "Public Transportation Construction",
    ]
    for column in required:
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
    frame = frame.dropna(subset=["Observation Date"]).sort_values("Observation Date", kind="stable")
    if frame.empty:
        return {"history": pd.DataFrame(), "latest": {}, "components": pd.DataFrame()}

    frame["Selected Public System Construction"] = frame[[
        "Public Water Supply Construction",
        "Public Highway and Street Construction",
        "Public Transportation Construction",
    ]].sum(axis=1, min_count=3)

    specs = [
        {
            "label": "Compute manufacturing",
            "observed": "Computer, Electronic & Electrical Manufacturing Construction",
            "denominator": "Private Manufacturing Construction",
            "group": "Direct support",
            "method": "Lagged 60-month median share of private manufacturing",
        },
        {
            "label": "Electric power",
            "observed": "Electric Power Construction",
            "denominator": "Private Nonresidential Construction",
            "group": "Direct support",
            "method": "Lagged 60-month median share of private nonresidential construction",
        },
        {
            "label": "Communications",
            "observed": "Communication Construction",
            "denominator": "Private Nonresidential Construction",
            "group": "Direct support",
            "method": "Lagged 60-month median share of private nonresidential construction",
        },
        {
            "label": "Public water",
            "observed": "Public Water Supply Construction",
            "denominator": "Selected Public System Construction",
            "group": "Public-system mix",
            "method": "Lagged 60-month median share of selected public water, roads, and transit construction",
        },
        {
            "label": "Roads & highways",
            "observed": "Public Highway and Street Construction",
            "denominator": "Selected Public System Construction",
            "group": "Public-system mix",
            "method": "Lagged 60-month median share of selected public water, roads, and transit construction",
        },
        {
            "label": "Public transit",
            "observed": "Public Transportation Construction",
            "denominator": "Selected Public System Construction",
            "group": "Public-system mix",
            "method": "Lagged 60-month median share of selected public water, roads, and transit construction",
        },
    ]

    expected_columns = []
    excess_columns = []
    component_rows = []
    for spec in specs:
        label = spec["label"]
        observed_column = spec["observed"]
        denominator_column = spec["denominator"]
        share = frame[observed_column] / frame[denominator_column].where(frame[denominator_column].gt(0))
        normal_share = share.shift(12).rolling(60, min_periods=36).median()
        expected_column = f"Expected {label}"
        excess_column = f"Excess {label}"
        deviation_column = f"Deviation {label}"
        frame[expected_column] = normal_share * frame[denominator_column]
        frame[deviation_column] = frame[observed_column] - frame[expected_column]
        frame[excess_column] = frame[deviation_column].clip(lower=0)
        expected_columns.append(expected_column)
        excess_columns.append(excess_column)
        valid = frame[["Observation Date", observed_column, expected_column, deviation_column, excess_column]].dropna().tail(1)
        if not valid.empty:
            row = valid.iloc[0]
            component_rows.append({
                "Component": label,
                "Group": spec["group"],
                "Date": row["Observation Date"],
                "Observed": row[observed_column],
                "Expected Baseline": row[expected_column],
                "Deviation from Baseline": row[deviation_column],
                "Excess Above Baseline": row[excess_column],
                "Baseline Method": spec["method"],
            })

    observed_columns = [spec["observed"] for spec in specs]
    broader_support = frame[observed_columns].sum(axis=1, min_count=len(observed_columns))
    expected_support = frame[expected_columns].sum(axis=1, min_count=len(expected_columns))
    output = pd.DataFrame({
        "Date": frame["Observation Date"],
        "Direct AI Construction": frame["Data Center Construction"],
        "Broader Supporting Construction": broader_support,
        "Expected Baseline": expected_support,
        "Excess Above Baseline": frame[excess_columns].sum(axis=1, min_count=len(excess_columns)),
        "Net Support Balance": broader_support - expected_support,
    }).dropna(subset=["Date"])
    valid_latest = output.dropna(subset=["Direct AI Construction"])
    latest = valid_latest.iloc[-1] if not valid_latest.empty else pd.Series(dtype=float)
    return {
        "history": output,
        "components": pd.DataFrame(component_rows),
        "latest": {
            "date": latest.get("Date"),
            "direct_ai_construction": pd.to_numeric(latest.get("Direct AI Construction"), errors="coerce"),
            "supporting_construction": pd.to_numeric(latest.get("Broader Supporting Construction"), errors="coerce"),
            "expected_baseline": pd.to_numeric(latest.get("Expected Baseline"), errors="coerce"),
            "excess_above_baseline": pd.to_numeric(latest.get("Excess Above Baseline"), errors="coerce"),
            "net_support_balance": pd.to_numeric(latest.get("Net Support Balance"), errors="coerce"),
        },
    }
