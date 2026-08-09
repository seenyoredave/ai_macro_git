from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np
import pandas as pd

from loaders.facility_identity import (
    KNOWN_CAMPUS_ALIASES,
    KNOWN_WIDE_RADIUS_CAMPUS_NAMES,
    _MatchRecord,
    _canonical_priority,
    _haversine_km,
    _identity_token,
    _identity_decision_groups,
    _identity_separation_groups,
    _known_campus_alias,
    _prepared_match_records,
    _token_set_similarity,
    _token_similarity,
)
from loaders.facility_registry_common import (
    CAPACITY_FIELDS,
    NUMERIC_COLUMNS,
    _clean_token,
    _known_text,
    _normalize_registry,
    _stable_id,
    normalize_us_state,
)

WATER_EVIDENCE_FIELDS = {
    "Water source identified": "Water Source",
    "Cooling design disclosed": "Cooling System",
    "Withdrawal disclosed": "Water Withdrawal Gallons/Year",
    "Consumption disclosed": "Water Consumption Gallons/Year",
    "WUE disclosed": "Site WUE L/kWh",
    "Permit or utility record located": "Water Permit or Utility Record",
    "Reclaimed-water use documented": "Reclaimed Water Use",
}


class _CampusMatchRecord(NamedTuple):
    facility: _MatchRecord
    address: str


def _normalized_address(value) -> str:
    text = _clean_token(value)
    if text in {"", "unknown", "n a", "na", "none", "not disclosed"}:
        return ""
    replacements = {
        " street ": " st ", " road ": " rd ", " avenue ": " ave ",
        " boulevard ": " blvd ", " drive ": " dr ", " highway ": " hwy ",
        " lane ": " ln ", " court ": " ct ", " parkway ": " pkwy ",
    }
    padded = f" {text} "
    for old, new in replacements.items():
        padded = padded.replace(old, new)
    return " ".join(padded.split())


def _same_campus(left: pd.Series, right: pd.Series) -> bool:
    if normalize_us_state(left.get("State")) != normalize_us_state(right.get("State")):
        return False
    distance = _haversine_km(left.get("Latitude"), left.get("Longitude"), right.get("Latitude"), right.get("Longitude"))
    if not np.isfinite(distance):
        return False

    left_decisions = _identity_decision_groups(left.get("Source Record ID"))
    right_decisions = _identity_decision_groups(right.get("Source Record ID"))
    left_separations = _identity_separation_groups(left.get("Source Record ID"))
    right_separations = _identity_separation_groups(right.get("Source Record ID"))
    if left_separations.intersection(right_separations):
        return False
    if left_decisions.intersection(right_decisions):
        return True

    # A small, explicit alias table handles materially important records whose
    # published coordinates refer to different points within the same project.
    if distance <= 50.0 and _known_campus_alias(left, right):
        return True

    left_address = _normalized_address(left.get("Address"))
    right_address = _normalized_address(right.get("Address"))
    if left_address and left_address == right_address and distance <= 1.0:
        return True
    if distance <= 0.075:
        return True

    name_score = _token_similarity(left.get("Facility"), right.get("Facility"))
    operator_score = _token_similarity(left.get("Operator"), right.get("Operator"))
    left_name = _identity_token(left.get("Facility"))
    right_name = _identity_token(right.get("Facility"))
    if distance <= 1.5 and left_name and left_name == right_name:
        return True
    if (
        distance <= 10.0
        and left_name
        and left_name == right_name
        and left_name in KNOWN_WIDE_RADIUS_CAMPUS_NAMES
    ):
        return True
    if distance > 5.0:
        return False
    if distance <= 0.25 and name_score >= 0.80:
        return True
    if distance <= 0.75 and operator_score >= 0.90 and name_score >= 0.25:
        return True
    return distance <= 1.5 and name_score >= 0.82 and operator_score >= 0.72


def _prepared_campus_records(frame: pd.DataFrame) -> list[_CampusMatchRecord]:
    facilities = _prepared_match_records(frame)
    addresses = frame["Address"].map(_normalized_address).tolist()
    return [
        _CampusMatchRecord(facility=facility, address=address)
        for facility, address in zip(facilities, addresses)
    ]


def _same_prepared_campus(left: _CampusMatchRecord, right: _CampusMatchRecord) -> bool:
    left_facility = left.facility
    right_facility = right.facility
    if left_facility.state != right_facility.state:
        return False
    distance = _haversine_km(
        left_facility.latitude,
        left_facility.longitude,
        right_facility.latitude,
        right_facility.longitude,
    )
    if not math.isfinite(distance):
        return False

    if left_facility.separation_groups.intersection(right_facility.separation_groups):
        return False

    if left_facility.decision_groups.intersection(right_facility.decision_groups):
        return True

    alias_pair = frozenset({left_facility.name, right_facility.name})
    if distance <= 50.0 and len(alias_pair) == 2 and alias_pair in KNOWN_CAMPUS_ALIASES:
        return True
    if left.address and left.address == right.address and distance <= 1.0:
        return True
    if distance <= 0.075:
        return True
    if (
        distance <= 1.5
        and left_facility.name
        and left_facility.name == right_facility.name
    ):
        return True
    if (
        distance <= 10.0
        and left_facility.name
        and left_facility.name == right_facility.name
        and left_facility.name in KNOWN_WIDE_RADIUS_CAMPUS_NAMES
    ):
        return True
    if distance > 5.0:
        return False
    name_score = _token_set_similarity(
        left_facility.name_tokens,
        right_facility.name_tokens,
    )
    operator_score = _token_set_similarity(
        left_facility.operator_tokens,
        right_facility.operator_tokens,
    )
    if distance <= 0.25 and name_score >= 0.80:
        return True
    if distance <= 0.75 and operator_score >= 0.90 and name_score >= 0.25:
        return True
    return distance <= 1.5 and name_score >= 0.82 and operator_score >= 0.72


def _campus_status(values: pd.Series) -> str:
    statuses = {str(value).strip() for value in values if str(value).strip()}
    active = {
        "Approved / permitted / under construction", "Under construction",
        "Proposed", "Planned", "Announced",
    }
    if "Expanding" in statuses or ("Operational" in statuses and statuses.intersection(active)):
        return "Expanding"
    for status in [
        "Operational", "Under construction", "Approved / permitted / under construction",
        "Proposed", "Planned", "Announced", "Suspended", "Cancelled", "Blocked",
        "Observed footprint", "Status unknown",
    ]:
        if status in statuses:
            return status
    return "Status unknown"


def _merge_campus_group(group: pd.DataFrame) -> pd.Series:
    ranked = group.copy()
    ranked["_priority"] = _canonical_priority(ranked)
    ranked = ranked.sort_values("_priority", ascending=False, kind="stable")
    result = ranked.iloc[0].copy()
    result["Status"] = _campus_status(group["Status"])
    building_total = pd.to_numeric(group["Building Count"], errors="coerce").sum(min_count=1)
    result["Building Count"] = max(int(building_total) if pd.notna(building_total) else 0, len(group))
    for column in [
        "Square Feet", "Published Capacity Estimate Low MW",
        "Published Capacity Estimate MW", "Published Capacity Estimate High MW",
        "Planned Data Center Capacity MW", "Contracted Utility Capacity MW",
        "Energized Capacity MW", "Annual Electricity Consumption MWh",
        "Planned Onsite Generation MW", "Property Size Acres",
        "Water Withdrawal Gallons/Year", "Water Consumption Gallons/Year",
    ]:
        values = pd.to_numeric(group[column], errors="coerce").dropna()
        if not values.empty:
            result[column] = values.max()
    dates = pd.to_datetime(group["Expected Service Date"], errors="coerce").dropna()
    if not dates.empty:
        result["Expected Service Date"] = dates.min()
    campus_id = _stable_id("campus", *sorted(group["Canonical Facility ID"].astype(str)))
    result["Facility ID"] = campus_id
    result["Canonical Facility ID"] = campus_id
    result["Duplicate Group ID"] = campus_id
    source_ids = list(dict.fromkeys(group["Source Record ID"].replace("", np.nan).dropna().astype(str)))
    result["Source Record ID"] = " | ".join(source_ids)
    sources = list(dict.fromkeys(group["Source"].replace("", np.nan).dropna().astype(str)))
    result["Source"] = " | ".join(sources)
    result["Review Status"] = f"Campus record from {len(group)} canonical location record{'s' if len(group) != 1 else ''}"
    return result.drop(labels=["_priority"], errors="ignore")


def _merge_singleton_campus(row: pd.Series) -> pd.Series:
    result = row.copy()
    result["Status"] = _campus_status(pd.Series([result.get("Status")]))
    building_count = pd.to_numeric(result.get("Building Count"), errors="coerce")
    result["Building Count"] = max(
        int(building_count) if pd.notna(building_count) else 0,
        1,
    )
    campus_id = _stable_id("campus", str(result["Canonical Facility ID"]))
    result["Facility ID"] = campus_id
    result["Canonical Facility ID"] = campus_id
    result["Duplicate Group ID"] = campus_id
    result["Review Status"] = "Campus record from 1 canonical location record"
    return result


def build_campus_registry(registry: pd.DataFrame | None) -> pd.DataFrame:
    clean = _normalize_registry(registry)
    if clean.empty:
        return clean
    clean = clean.reset_index(drop=True)
    parent = list(range(len(clean)))

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    buckets: dict[tuple[str, int, int], list[int]] = {}
    # 0.25-degree cells plus a two-cell search expose the full comparison
    # radius, including coordinate-imprecise large campuses. The match rules
    # above remain conservative; this only fixes candidate generation.
    bucket_degrees = 0.25
    bucket_span = 2
    prepared = _prepared_campus_records(clean)

    # Reviewed record-level merge decisions are authoritative and must not be
    # defeated by a bad coordinate, state proxy, or spatial candidate bucket.
    # The ledger remains deliberately small and evidence-backed; automatic
    # matching below continues to use the conservative distance thresholds.
    reviewed_groups: dict[str, list[int]] = {}
    for index, record in enumerate(prepared):
        for decision_group in record.facility.decision_groups:
            reviewed_groups.setdefault(decision_group, []).append(index)
    for indexes in reviewed_groups.values():
        for index in indexes[1:]:
            union(indexes[0], index)

    for index, row in enumerate(prepared):
        facility = row.facility
        if not math.isfinite(facility.latitude) or not math.isfinite(facility.longitude):
            continue
        lat_bucket = math.floor(facility.latitude / bucket_degrees)
        lon_bucket = math.floor(facility.longitude / bucket_degrees)
        candidates = []
        for lat_offset in range(-bucket_span, bucket_span + 1):
            for lon_offset in range(-bucket_span, bucket_span + 1):
                candidates.extend(
                    buckets.get(
                        (
                            facility.state,
                            lat_bucket + lat_offset,
                            lon_bucket + lon_offset,
                        ),
                        [],
                    )
                )
        for candidate in candidates:
            if _same_prepared_campus(row, prepared[candidate]):
                union(index, candidate)
        buckets.setdefault((facility.state, lat_bucket, lon_bucket), []).append(index)

    groups: dict[int, list[int]] = {}
    for index in range(len(clean)):
        groups.setdefault(find(index), []).append(index)
    rows = [
        _merge_singleton_campus(clean.iloc[indexes[0]])
        if len(indexes) == 1
        else _merge_campus_group(clean.loc[indexes])
        for indexes in groups.values()
    ]
    return _normalize_registry(pd.DataFrame(rows))


def registry_coverage(registry: pd.DataFrame | None) -> dict:
    clean = _normalize_registry(registry)
    total = int(len(clean))
    fields = {}
    for field in CAPACITY_FIELDS:
        valid = int(pd.to_numeric(clean[field], errors="coerce").notna().sum()) if total else 0
        fields[field] = {"records": valid, "total": total, "share": valid / total if total else np.nan}
    structured = ["Planned Data Center Capacity MW", "Contracted Utility Capacity MW", "Energized Capacity MW"]
    structured_count = int(clean[structured].notna().any(axis=1).sum()) if total else 0
    return {
        "records": total,
        "states": int(clean["State"].replace("", np.nan).nunique()) if total else 0,
        "mapped_footprints": int(clean["Record Type"].eq("footprint").sum()) if total else 0,
        "project_records": int(clean["Record Type"].eq("project").sum()) if total else 0,
        "primary_project_records": int(clean["Source Class"].eq("Primary project evidence").sum()) if total else 0,
        "open_tracker_records": int(clean["Source Class"].eq("Open project tracker").sum()) if total else 0,
        "records_with_structured_capacity": structured_count,
        "records_with_source_links": int((clean["Upstream Source URL"].map(_known_text) | clean["Source URL"].map(_known_text)).sum()) if total else 0,
        "evidence_grades": {str(k): int(v) for k, v in clean["Evidence Grade"].replace("", np.nan).value_counts().to_dict().items()},
        "evidence_types": {str(k): int(v) for k, v in clean["Evidence Type"].replace("", np.nan).value_counts().to_dict().items()},
        "inventory_confidence": {str(k): int(v) for k, v in clean["Inventory Confidence"].replace("", np.nan).value_counts().to_dict().items()},
        "fields": fields,
    }


def registry_stage_summary(registry: pd.DataFrame | None) -> dict:
    clean = _normalize_registry(registry)
    specs = {
        "online": ("Operational", {"Operational"}),
        "expanding": ("Expanding", {"Expanding"}),
        "approved": ("Approved / permitted / construction", {"Approved / permitted / under construction"}),
        "planned": ("Proposed / announced", {"Proposed", "Planned", "Announced"}),
        "suspended": ("Suspended / cancelled / blocked", {"Suspended", "Cancelled", "Blocked"}),
        "footprint": ("Observed footprint", {"Observed footprint"}),
    }
    output = {}
    for key, (label, statuses) in specs.items():
        rows = clean.loc[clean["Status"].isin(statuses)].copy()
        published = pd.to_numeric(rows["Published Capacity Estimate MW"], errors="coerce")
        planned = pd.to_numeric(rows["Planned Data Center Capacity MW"], errors="coerce")
        capacity = planned.combine_first(published)
        output[key] = {
            "label": label,
            "records": int(len(rows)),
            "states": int(rows["State"].replace("", np.nan).nunique()) if not rows.empty else 0,
            "capacity_mw": float(capacity.sum(min_count=1)) if capacity.notna().any() else np.nan,
            "capacity_records": int(capacity.notna().sum()),
            "records_frame": rows,
        }
    pipeline_statuses = {"Approved / permitted / under construction", "Expanding", "Proposed", "Planned", "Announced"}
    pipeline_rows = clean.loc[clean["Status"].isin(pipeline_statuses)].copy()
    published = pd.to_numeric(pipeline_rows["Published Capacity Estimate MW"], errors="coerce")
    planned = pd.to_numeric(pipeline_rows["Planned Data Center Capacity MW"], errors="coerce")
    capacity = planned.combine_first(published)
    output["pipeline"] = {
        "label": "Active pipeline",
        "records": int(len(pipeline_rows)),
        "states": int(pipeline_rows["State"].replace("", np.nan).nunique()) if not pipeline_rows.empty else 0,
        "capacity_mw": float(capacity.sum(min_count=1)) if capacity.notna().any() else np.nan,
        "capacity_records": int(capacity.notna().sum()),
        "records_frame": pipeline_rows,
    }
    return output


def water_evidence_mask(registry: pd.DataFrame | None) -> pd.Series:
    clean = _normalize_registry(registry)
    if clean.empty:
        return pd.Series(dtype=bool)
    masks = []
    for field in WATER_EVIDENCE_FIELDS.values():
        masks.append(pd.to_numeric(clean[field], errors="coerce").notna() if field in NUMERIC_COLUMNS else clean[field].map(_known_text))
    result = masks[0].copy()
    for mask in masks[1:]:
        result |= mask
    return result


def water_evidence_coverage(registry: pd.DataFrame | None) -> dict:
    clean = _normalize_registry(registry)
    total = int(len(clean))
    fields = {}
    for label, field in WATER_EVIDENCE_FIELDS.items():
        valid = 0 if total == 0 else int(
            pd.to_numeric(clean[field], errors="coerce").notna().sum()
            if field in NUMERIC_COLUMNS else clean[field].map(_known_text).sum()
        )
        fields[label] = {"field": field, "records": valid, "total": total, "share": valid / total if total else np.nan}
    return {
        "records": total,
        "records_with_any_water_evidence": int(water_evidence_mask(clean).sum()) if total else 0,
        "fields": fields,
    }
