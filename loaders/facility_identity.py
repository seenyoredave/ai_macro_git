from __future__ import annotations

import math
from functools import lru_cache
from typing import NamedTuple

import numpy as np
import pandas as pd

from loaders.facility_registry_common import (
    DATE_COLUMNS,
    FACILITY_COLUMNS,
    NUMERIC_COLUMNS,
    PROJECT_ROOT,
    _blank_registry,
    _clean_token,
    _known_text,
    _normalize_registry,
    _stable_id,
    _valid_url,
    normalize_us_state,
)
from loaders.facility_sources import load_curated_facility_records, normalize_im3_locations

KNOWN_CAMPUS_ALIASES = {
    frozenset({"homer city energy", "homer city redevelopment"}),
    frozenset({"meta hyperion richland parish", "meta rpl 10x hyperion sucre"}),
    # Reviewed TECfusions identity survives upstream tracker edits that can
    # change fallback Source Record IDs while the published campus names remain
    # recognizably the same 1,400-acre Keystone Connect project.
    frozenset({"upper burrell tecfusions keystone connect", "tecfusions keystone connect"}),
}


KNOWN_WIDE_RADIUS_CAMPUS_NAMES = {
    "caprock lbb 01",
    "coreweave plano",
    "xai colossus 2",
}

IDENTITY_DECISIONS_PATH = PROJECT_ROOT / "data" / "facility_identity_decisions.csv"
IDENTITY_DECISION_COLUMNS = (
    "Source Record ID",
    "Decision Group",
    "Decision",
    "Evidence URL",
    "Decision Note",
)


def load_facility_identity_decisions() -> pd.DataFrame:
    """Return the reviewed record-level identity ledger."""
    if not IDENTITY_DECISIONS_PATH.exists() or not IDENTITY_DECISIONS_PATH.stat().st_size:
        return pd.DataFrame(columns=IDENTITY_DECISION_COLUMNS)
    decisions = pd.read_csv(IDENTITY_DECISIONS_PATH, dtype=str).fillna("")
    required = {"Source Record ID", "Decision Group", "Decision"}
    if not required.issubset(decisions.columns):
        raise ValueError("Facility identity decision ledger schema changed")
    return decisions


@lru_cache(maxsize=1)
def _identity_decision_maps() -> dict[str, dict[str, frozenset[str]]]:
    """Return reviewed source-record-to-campus decisions.

    The ledger is deliberately small. It resolves only evidence-backed campus
    identities that a conservative spatial matcher cannot safely infer.
    """
    decisions = load_facility_identity_decisions()
    if decisions.empty:
        return {"merge": {}, "separate": {}}
    output: dict[str, dict[str, frozenset[str]]] = {}
    for decision in ("merge", "separate"):
        selected = decisions.loc[decisions["Decision"].str.casefold().eq(decision)]
        mapping: dict[str, set[str]] = {}
        for source_id, group in zip(selected["Source Record ID"], selected["Decision Group"]):
            source_id = str(source_id).strip()
            group = str(group).strip()
            if source_id and group:
                mapping.setdefault(source_id, set()).add(group)
        output[decision] = {
            key: frozenset(value) for key, value in mapping.items()
        }
    return output


def _identity_groups(value, decision: str) -> frozenset[str]:
    mapping = _identity_decision_maps()[decision]
    groups: set[str] = set()
    for source_id in str(value or "").split("|"):
        groups.update(mapping.get(source_id.strip(), ()))
    return frozenset(groups)


def _identity_decision_groups(value) -> frozenset[str]:
    return _identity_groups(value, "merge")


def _identity_separation_groups(value) -> frozenset[str]:
    return _identity_groups(value, "separate")


class _MatchRecord(NamedTuple):
    state: str
    latitude: float
    longitude: float
    source: str
    name: str
    name_tokens: frozenset[str]
    operator_tokens: frozenset[str]
    address_tokens: frozenset[str]
    decision_groups: frozenset[str]
    separation_groups: frozenset[str]


def _identity_token(value) -> str:
    tokens = [
        token for token in _clean_token(value).split()
        if token not in {
            "data", "center", "centre", "datacenter", "campus", "facility", "project",
            "llc", "inc", "corp", "corporation", "company", "co", "the",
        }
    ]
    return " ".join(tokens)


def _token_similarity(left, right) -> float:
    left_tokens = frozenset(_identity_token(left).split())
    right_tokens = frozenset(_identity_token(right).split())
    return _token_set_similarity(left_tokens, right_tokens)


def _token_set_similarity(left_tokens: frozenset[str], right_tokens: frozenset[str]) -> float:
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _known_campus_alias(left, right) -> bool:
    pair = frozenset(
        {
            _identity_token(left.get("Facility")),
            _identity_token(right.get("Facility")),
        }
    )
    return len(pair) == 2 and pair in KNOWN_CAMPUS_ALIASES


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    try:
        values = tuple(float(value) for value in (lat1, lon1, lat2, lon2))
    except (TypeError, ValueError):
        return np.inf
    if not all(math.isfinite(value) for value in values):
        return np.inf
    a1, o1, a2, o2 = map(math.radians, values)
    delta_lat = a2 - a1
    delta_lon = o2 - o1
    h = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(a1) * math.cos(a2) * math.sin(delta_lon / 2.0) ** 2
    )
    return float(6371.0088 * 2.0 * math.asin(math.sqrt(h)))


def _prepared_match_records(frame: pd.DataFrame) -> list[_MatchRecord]:
    columns = list(frame.columns)
    records = []
    for values in frame.itertuples(index=False, name=None):
        row = dict(zip(columns, values))
        name = _identity_token(row.get("Facility"))
        operator = _identity_token(row.get("Operator"))
        address = _identity_token(row.get("Address"))
        latitude = pd.to_numeric(row.get("Latitude"), errors="coerce")
        longitude = pd.to_numeric(row.get("Longitude"), errors="coerce")
        records.append(
            _MatchRecord(
                state=normalize_us_state(row.get("State")),
                latitude=float(latitude) if pd.notna(latitude) else math.nan,
                longitude=float(longitude) if pd.notna(longitude) else math.nan,
                source=str(row.get("Source") or ""),
                name=name,
                name_tokens=frozenset(name.split()),
                operator_tokens=frozenset(operator.split()),
                address_tokens=frozenset(address.split()),
                decision_groups=_identity_decision_groups(row.get("Source Record ID")),
                separation_groups=_identity_separation_groups(row.get("Source Record ID")),
            )
        )
    return records


def _same_prepared_facility(left: _MatchRecord, right: _MatchRecord) -> bool:
    if left.state != right.state:
        return False
    # Reviewed identity decisions outrank generic source/spatial heuristics.
    # This is especially important for duplicate rows emitted by the same
    # upstream tracker: those rows were historically impossible to merge even
    # when the decision ledger explicitly said they describe one campus.
    if left.separation_groups.intersection(right.separation_groups):
        return False
    if left.decision_groups.intersection(right.decision_groups):
        return True
    # Reviewed semantic aliases are durable identity evidence when an upstream
    # tracker rewrites content-derived record IDs.  Apply them before the
    # same-source guard so duplicate rows from one tracker can still resolve
    # to the reviewed campus after an ID churn.
    if frozenset({left.name, right.name}) in KNOWN_CAMPUS_ALIASES:
        return True
    if left.source == right.source:
        return False
    distance = _haversine_km(
        left.latitude,
        left.longitude,
        right.latitude,
        right.longitude,
    )
    if not math.isfinite(distance) or distance > 5.0:
        return False
    name_score = _token_set_similarity(left.name_tokens, right.name_tokens)
    operator_score = _token_set_similarity(left.operator_tokens, right.operator_tokens)
    address_score = _token_set_similarity(left.address_tokens, right.address_tokens)
    if distance <= 0.06:
        return True
    if distance <= 0.35 and max(name_score, operator_score, address_score) >= 0.34:
        return True
    if distance <= 1.5 and name_score >= 0.72:
        return True
    return distance <= 5.0 and name_score >= 0.85 and operator_score >= 0.5


def _same_facility(left: pd.Series, right: pd.Series) -> bool:
    if str(left.get("Source") or "") == str(right.get("Source") or ""):
        return False
    if normalize_us_state(left.get("State")) != normalize_us_state(right.get("State")):
        return False
    distance = _haversine_km(left.get("Latitude"), left.get("Longitude"), right.get("Latitude"), right.get("Longitude"))
    if not np.isfinite(distance) or distance > 5.0:
        return False
    name_score = _token_similarity(left.get("Facility"), right.get("Facility"))
    operator_score = _token_similarity(left.get("Operator"), right.get("Operator"))
    address_score = _token_similarity(left.get("Address"), right.get("Address"))
    if distance <= 0.06:
        return True
    if distance <= 0.35 and max(name_score, operator_score, address_score) >= 0.34:
        return True
    if distance <= 1.5 and name_score >= 0.72:
        return True
    return distance <= 5.0 and name_score >= 0.85 and operator_score >= 0.5


def _canonical_priority(frame: pd.DataFrame) -> pd.Series:
    source_rank = frame["Source Class"].map({
        "Primary project evidence": 5,
        "Open project tracker": 4,
        "Secondary project inventory": 3,
        "Observed footprint": 1,
    }).fillna(0)
    grade_rank = frame["Evidence Grade"].map({"A": 5, "B": 4, "C": 3, "D": 2}).fillna(0)
    structured = frame[
        ["Planned Data Center Capacity MW", "Contracted Utility Capacity MW", "Energized Capacity MW"]
    ].notna().sum(axis=1)
    freshness = pd.to_datetime(frame["Source Updated Date"], errors="coerce").rank(method="dense", pct=True).fillna(0)
    return source_rank * 100 + grade_rank * 10 + structured + freshness


def _assign_canonical_ids(observations: pd.DataFrame) -> pd.DataFrame:
    if observations.empty:
        return observations
    clean = observations.reset_index(drop=True).copy()
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
    bucket_degrees = 0.05
    bucket_span = 2
    prepared = _prepared_match_records(clean)

    # Reviewed merge decisions are explicit identity evidence and are not
    # constrained by the generic spatial candidate window.  Apply them first
    # so same-source duplicates and wide-campus records can resolve exactly as
    # reviewed even when the upstream tracker edits coordinates or labels.
    reviewed_groups: dict[str, int] = {}
    for index, row in enumerate(prepared):
        for group in row.decision_groups:
            if group in reviewed_groups:
                union(index, reviewed_groups[group])
            else:
                reviewed_groups[group] = index

    # Semantic aliases are reviewed identity evidence too.  They must be
    # applied before the spatial bucket search because a large campus can span
    # more than the generic candidate radius and upstream content-derived IDs
    # can churn.  Keep state in the key so a shared project name cannot merge
    # records across jurisdictions.
    semantic_alias_groups: dict[tuple[str, frozenset[str]], int] = {}
    for index, row in enumerate(prepared):
        for alias_group in KNOWN_CAMPUS_ALIASES:
            if row.name not in alias_group:
                continue
            key = (row.state, alias_group)
            if key in semantic_alias_groups:
                union(index, semantic_alias_groups[key])
            else:
                semantic_alias_groups[key] = index

    for index, row in enumerate(prepared):
        if not math.isfinite(row.latitude) or not math.isfinite(row.longitude):
            continue
        lat_bucket = math.floor(row.latitude / bucket_degrees)
        lon_bucket = math.floor(row.longitude / bucket_degrees)
        candidates = []
        for lat_offset in range(-bucket_span, bucket_span + 1):
            for lon_offset in range(-bucket_span, bucket_span + 1):
                candidates.extend(
                    buckets.get(
                        (row.state, lat_bucket + lat_offset, lon_bucket + lon_offset),
                        [],
                    )
                )
        for candidate in candidates:
            if _same_prepared_facility(row, prepared[candidate]):
                union(index, candidate)
        buckets.setdefault((row.state, lat_bucket, lon_bucket), []).append(index)

    groups: dict[int, list[int]] = {}
    for index in range(len(clean)):
        groups.setdefault(find(index), []).append(index)
    for member_indexes in groups.values():
        member_ids = sorted(clean.loc[member_indexes, "Facility ID"].astype(str))
        canonical_id = _stable_id("facility", *member_ids)
        clean.loc[member_indexes, "Canonical Facility ID"] = canonical_id
        clean.loc[member_indexes, "Duplicate Group ID"] = canonical_id
        if len(member_indexes) > 1:
            clean.loc[member_indexes, "Review Status"] = f"Matched across {len(member_indexes)} source records"
    return _normalize_registry(clean)


def build_facility_observations(
    locations: pd.DataFrame | None,
    supplemental_records: pd.DataFrame | None = None,
) -> pd.DataFrame:
    frames = [normalize_im3_locations(locations), _normalize_registry(supplemental_records), load_curated_facility_records()]
    populated = [frame for frame in frames if not frame.empty]
    observations = pd.concat(populated, ignore_index=True, sort=False) if populated else _blank_registry()
    observations = _normalize_registry(observations)
    return _assign_canonical_ids(observations) if not observations.empty else observations


def _has_value(value, column: str) -> bool:
    if column in NUMERIC_COLUMNS:
        return pd.notna(pd.to_numeric(value, errors="coerce"))
    if column in DATE_COLUMNS:
        return pd.notna(pd.to_datetime(value, errors="coerce"))
    return _known_text(value)


def _merge_canonical_group(group: pd.DataFrame) -> pd.Series:
    ranked = group.copy()
    ranked["_priority"] = _canonical_priority(ranked)
    ranked = ranked.sort_values("_priority", ascending=False, kind="stable")
    result = ranked.iloc[0].copy()
    for column in FACILITY_COLUMNS:
        for value in ranked[column]:
            if _has_value(value, column):
                result[column] = value
                break
    canonical_id = str(group["Canonical Facility ID"].iloc[0])
    result["Facility ID"] = canonical_id
    result["Canonical Facility ID"] = canonical_id
    result["Duplicate Group ID"] = canonical_id
    result["Source Record ID"] = " | ".join(dict.fromkeys(group["Source Record ID"].replace("", np.nan).dropna().astype(str)))
    result["Source"] = " | ".join(dict.fromkeys(group["Source"].replace("", np.nan).dropna().astype(str)))
    urls = []
    for field in ["Source URL", "Upstream Source URL"]:
        for cell in group.loc[group[field].fillna("").astype(str).str.strip().ne(""), field].astype(str):
            urls.extend(item.strip() for item in cell.split("|") if _valid_url(item.strip()))
    result["Upstream Source URL"] = " | ".join(dict.fromkeys(urls))
    if len(group) > 1:
        result["Review Status"] = f"Canonical record from {len(group)} source records"
    return result.drop(labels=["_priority"], errors="ignore")


def _merge_singleton_canonical(row: pd.Series) -> pd.Series:
    result = row.copy()
    canonical_id = str(result["Canonical Facility ID"])
    result["Facility ID"] = canonical_id
    result["Canonical Facility ID"] = canonical_id
    result["Duplicate Group ID"] = canonical_id
    urls = []
    for field in ["Source URL", "Upstream Source URL"]:
        urls.extend(
            item.strip()
            for item in str(result.get(field) or "").split("|")
            if _valid_url(item.strip())
        )
    result["Upstream Source URL"] = " | ".join(dict.fromkeys(urls))
    return result


def canonicalize_facility_observations(observations: pd.DataFrame | None) -> pd.DataFrame:
    clean = _normalize_registry(observations)
    if clean.empty:
        return clean
    if clean["Canonical Facility ID"].fillna("").astype(str).str.strip().eq("").any():
        clean = _assign_canonical_ids(clean)
    rows = []
    for _, group in clean.groupby("Canonical Facility ID", sort=False, dropna=False):
        rows.append(
            _merge_singleton_canonical(group.iloc[0])
            if len(group) == 1
            else _merge_canonical_group(group)
        )
    return _normalize_registry(pd.DataFrame(rows))


def build_facility_registry(
    locations: pd.DataFrame | None,
    supplemental_records: pd.DataFrame | None = None,
) -> pd.DataFrame:
    return canonicalize_facility_observations(
        build_facility_observations(locations, supplemental_records)
    )
