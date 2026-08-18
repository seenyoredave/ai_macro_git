#!/usr/bin/env python3
"""Full retained-data release gate for AI Macro v9.6.0 data-center identity.

This gate is intentionally national and retained-data based. It validates the
current retained artifact produced by the explicit registry build, including
source fingerprint, table hashes, entity quality, and cross-domain Campus IDs.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import time

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.spatial_context import attach_water_context  # noqa: E402
from helpers.data_center_identity_authority_test import main as authority_main  # noqa: E402
from loaders.connectivity_loader import load_connectivity_data  # noqa: E402
from loaders.data_center_registry import (  # noqa: E402
    REGISTRY_VERSION,
    assert_campus_foreign_keys,
    load_retained_universal_data_center_registry,
)
from loaders.water_loader import load_water_utilization_data  # noqa: E402

MAX_RETAINED_LOAD_SECONDS = 5.0


def _ids(frame: pd.DataFrame) -> set[str]:
    if not isinstance(frame, pd.DataFrame) or "Campus ID" not in frame.columns:
        return set()
    return set(frame["Campus ID"].dropna().astype(str)) - {""}


def _county_token(value) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()
    for suffix in (" county", " parish", " borough", " census area", " municipality", " city and borough"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
            break
    return text


def _quality_gate(payload: dict) -> None:
    campuses = payload["campuses"]
    entities = payload["entities"]
    observations = payload["observations"]
    membership = payload["membership"]

    if str(payload.get("version")) != REGISTRY_VERSION:
        raise AssertionError("Retained registry version changed")
    if campuses.empty or "Campus ID" not in campuses.columns:
        raise AssertionError("Canonical campus table is empty")
    if not campuses["Campus ID"].is_unique:
        raise AssertionError("Canonical Campus IDs are duplicated")
    if "Campus Label" not in campuses.columns or not campuses["Campus Label"].astype(str).is_unique:
        raise AssertionError("Canonical campus labels are missing or duplicated")

    labels = campuses["Campus Label"].fillna("").astype(str).str.strip()
    names = campuses["Campus Name"].fillna("").astype(str).str.strip()
    if labels.eq("").any() or names.eq("").any():
        raise AssertionError("Canonical campus contains a blank name/label")
    if labels.str.contains(" · ", regex=False).any():
        raise AssertionError("Legacy concatenated selector labels remain in the canonical registry")
    # A dash-number token can be part of a source-native project/facility name.
    # Reject it only when it was introduced by identity/rendering logic rather
    # than carried verbatim from a member source observation.
    dash_number = r"\s-\s\d+(?:\s|$)"
    numbered_labels = labels.str.contains(dash_number, regex=True)
    numbered_names = names.str.contains(dash_number, regex=True)
    generated_numbering = numbered_labels & ~numbered_names
    if generated_numbering.any():
        bad = campuses.loc[generated_numbering, ["Campus ID", "Campus Name", "Campus Label"]]
        raise AssertionError(
            f"Ungrounded dash-number identity labels remain in the canonical registry: {bad.head(10).to_dict('records')}"
        )

    if numbered_names.any():
        observation_names = observations[["Observation ID", "Name"]].copy()
        observation_names["_name_key"] = observation_names["Name"].fillna("").astype(str).str.strip().str.casefold()
        member_names = membership[["Campus ID", "Observation ID"]].merge(
            observation_names[["Observation ID", "_name_key"]],
            on="Observation ID",
            how="left",
            validate="many_to_one",
        )
        names_by_campus = (
            member_names.groupby("Campus ID", sort=False)["_name_key"]
            .agg(lambda values: set(value for value in values if value))
            .to_dict()
        )
        ungrounded = []
        for campus_id, campus_name in zip(
            campuses.loc[numbered_names, "Campus ID"].astype(str),
            names.loc[numbered_names],
        ):
            key = str(campus_name).strip().casefold()
            if key not in names_by_campus.get(campus_id, set()):
                ungrounded.append({"Campus ID": campus_id, "Campus Name": campus_name})
        if ungrounded:
            raise AssertionError(
                f"Dash-number campus names lack source provenance: {ungrounded[:10]}"
            )
    if labels.str.contains("Unidentified data-center site", case=False, regex=False).any():
        raise AssertionError("Unidentified placeholder campuses remain in the canonical registry")

    state_codes = campuses.get("State", pd.Series("", index=campuses.index)).fillna("").astype(str).str.upper().str.strip()
    missing_state_in_label = [
        str(campus_id)
        for campus_id, label, state in zip(campuses["Campus ID"], labels, state_codes)
        if state and not re.search(rf"(?:,\s|—\s){re.escape(state)}(?:\s|$|—)", label)
    ]
    if missing_state_in_label:
        raise AssertionError(
            f"Canonical campus labels do not expose their U.S. state jurisdiction: {missing_state_in_label[:10]}"
        )

    county_name = [
        _county_token(name) == _county_token(county) and bool(_county_token(county))
        for name, county in zip(names, campuses.get("County", pd.Series("", index=campuses.index)))
    ]
    if any(county_name):
        bad = campuses.loc[county_name, ["Campus ID", "Campus Name", "County"]]
        raise AssertionError(f"County-only source identities became campuses: {bad.head(10).to_dict('records')}")

    inferred = campuses.get("Identity Basis", pd.Series("", index=campuses.index)).astype(str).eq(
        "inferred campus from co-located building records"
    )
    building_counts = pd.to_numeric(campuses.get("Building Count"), errors="coerce")
    if (inferred & building_counts.lt(2)).any():
        bad = campuses.loc[inferred & building_counts.lt(2), ["Campus ID", "Campus Label", "Building Count"]]
        raise AssertionError(f"A lone building manufactured a campus: {bad.head(10).to_dict('records')}")
    if campuses.get("Identity Basis", pd.Series("", index=campuses.index)).astype(str).eq("standalone mapped site observation").any():
        raise AssertionError("Uncorroborated point observations still manufacture campuses")

    canonical = _ids(campuses)
    if set(entities.get("Campus ID", pd.Series(dtype=str)).dropna().astype(str)) - {""} - canonical:
        raise AssertionError("Entity hierarchy contains unknown Campus IDs")
    if set(membership.get("Campus ID", pd.Series(dtype=str)).dropna().astype(str)) - {""} - canonical:
        raise AssertionError("Membership table contains unknown Campus IDs")
    if membership.get("Observation ID", pd.Series(dtype=str)).astype(str).duplicated().any():
        raise AssertionError("A source observation is assigned more than once")

    # Point observations may attach to an established campus, but they cannot be
    # the basis for creating a campus. Building observations can establish an
    # inferred campus only as a multi-building site (checked above).
    source_levels = observations.set_index("Observation ID")["Observation Level"].astype(str).to_dict()
    if "Anchor Observation ID" in campuses.columns:
        point_anchors = [
            campus_id
            for campus_id, anchor in zip(campuses["Campus ID"], campuses["Anchor Observation ID"])
            if source_levels.get(str(anchor)) == "site_point"
        ]
        if point_anchors:
            raise AssertionError(f"Point observations anchor canonical campuses: {point_anchors[:10]}")


def _umatilla_gate(payload: dict) -> None:
    """Protect the exact failure that triggered the overhaul on retained data.

    The retained IM3 layer contains fifteen Umatilla AWS building footprints
    whose source name is literally ``Amazon Web Services``. They are building
    observations. The registry may attach them to stronger named evidence or
    infer geographically coherent multi-building campuses; it may never promote
    the fifteen footprints into fifteen campuses.
    """
    observations = payload["observations"].copy()
    membership = payload["membership"].copy()
    campuses = payload["campuses"].copy()

    state = observations.get("State", pd.Series("", index=observations.index)).fillna("").astype(str).str.upper()
    county = observations.get("County", pd.Series("", index=observations.index)).fillna("").astype(str)
    source = observations.get("Source", pd.Series("", index=observations.index)).fillna("").astype(str)
    operator = observations.get("Operator", pd.Series("", index=observations.index)).fillna("").astype(str).str.casefold().str.strip()
    name = observations.get("Name", pd.Series("", index=observations.index)).fillna("").astype(str).str.casefold().str.strip()
    level = observations.get("Observation Level", pd.Series("", index=observations.index)).fillna("").astype(str)
    target = observations.loc[
        state.eq("OR")
        & county.eq("Umatilla County")
        & source.str.contains("IM3", case=False, na=False)
        & operator.eq("amazon web services")
        & name.eq("amazon web services")
        & level.eq("building")
    ].copy()
    if len(target) != 15:
        raise AssertionError(
            f"Umatilla retained IM3 generic-AWS building slice changed: expected 15, found {len(target)}"
        )
    target_membership = membership.loc[
        membership["Observation ID"].astype(str).isin(set(target["Observation ID"].astype(str)))
    ].copy()
    if len(target_membership) != len(target):
        missing = set(target["Observation ID"].astype(str)) - set(target_membership["Observation ID"].astype(str))
        raise AssertionError(f"Umatilla generic AWS buildings were lost from membership: {sorted(missing)[:5]}")
    resolved_ids = set(target_membership["Campus ID"].astype(str)) - {""}
    if len(resolved_ids) != 4:
        raise AssertionError(
            f"Fifteen Umatilla AWS building footprints resolve to {len(resolved_ids)} campuses instead of four"
        )
    resolved = campuses.loc[campuses["Campus ID"].astype(str).isin(resolved_ids)].copy()
    if len(resolved) != 4:
        raise AssertionError("Umatilla membership references a missing canonical campus")
    if resolved["Campus Label"].astype(str).str.match(r"^Umatilla County(?:\s|$)", case=False).any():
        raise AssertionError("A county-only Umatilla placeholder became a canonical campus")
    if pd.to_numeric(resolved.get("Building Count"), errors="coerce").fillna(0).lt(2).any():
        raise AssertionError("A Umatilla generic building footprint became a one-building campus")


def _domain_gate(payload: dict) -> None:
    campuses = payload["campuses"]
    canonical = _ids(campuses)
    infrastructure = {
        "data_center_registry": campuses,
        "data_center_entities": payload["entities"],
        "data_center_observations": payload["observations"],
        "data_center_membership": payload["membership"],
        "data_center_unresolved_observations": payload["unresolved_observations"],
        "data_center_registry_summary": payload["summary"],
    }

    water = load_water_utilization_data(force_refresh=False, allow_live=False)
    _, water = attach_water_context(infrastructure, water)
    water_campuses = water.get("campus_context")
    if not isinstance(water_campuses, pd.DataFrame):
        raise AssertionError("Water campus context is unavailable")
    assert_campus_foreign_keys(campuses, water_campuses[["Campus ID"]], domain="water", allow_subset=False)
    if _ids(water_campuses) != canonical:
        raise AssertionError("Water does not preserve the full canonical campus universe")

    connectivity = load_connectivity_data(campuses, force_refresh=False, allow_live=False)
    snapshot = connectivity.get("campus_connectivity_snapshot")
    if isinstance(snapshot, pd.DataFrame) and not snapshot.empty:
        assert_campus_foreign_keys(campuses, snapshot[["Campus ID"]], domain="connectivity", allow_subset=True)


def main() -> int:
    if authority_main() != 0:
        raise AssertionError("Identity-authority gate failed")

    started = time.perf_counter()
    retained = load_retained_universal_data_center_registry(require_current=True)
    retained_elapsed = time.perf_counter() - started
    if retained is None:
        raise AssertionError(
            "Retained registry is absent or stale. Run helpers/build_universal_data_center_registry.py first."
        )
    if retained_elapsed > MAX_RETAINED_LOAD_SECONDS:
        raise AssertionError(
            f"Retained registry load took {retained_elapsed:.2f}s; limit {MAX_RETAINED_LOAD_SECONDS:.1f}s"
        )
    _quality_gate(retained)
    _umatilla_gate(retained)

    # The build command immediately preceding this gate already resolved the
    # complete retained national source universe. Rebuilding the same universe
    # here duplicated the expensive identity pass without adding another input.
    # Current-source fingerprinting plus retained-table SHA-256 verification in
    # load_retained_universal_data_center_registry() proves this gate is reading
    # the exact artifact produced from the current retained source set.
    _domain_gate(retained)
    summary = retained["summary"]
    print(
        "PASS  v9.6.0 retained national release gate · "
        f"{int(summary.get('campuses', 0) or 0):,} campuses · "
        f"{int(summary.get('facility_entities', 0) or 0):,} facilities · "
        f"{int(summary.get('building_entities', 0) or 0):,} buildings · "
        f"{int(summary.get('unresolved_observations', 0) or 0):,} unresolved · "
        f"retained load {retained_elapsed:.2f}s · source fingerprint + table hashes verified · "
        "Data Centers/Water/Connectivity share canonical Campus IDs"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
