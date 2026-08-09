"""Stable public interface for facility registry loading and consolidation.

Implementation is split by responsibility; existing imports remain valid.
"""

from loaders.facility_registry_common import (
    CAPACITY_FIELDS,
    DATE_COLUMNS,
    FACILITY_COLUMNS,
    FRACTRACKER_FEATURE_URL,
    FRACTRACKER_PATH,
    GIGAWATT_PATH,
    GIGAWATT_VERIFIED_PATH,
    NUMERIC_COLUMNS,
    PROJECT_ROOT,
    SEED_PATH,
    US_STATE_CODES,
    _UNKNOWN_TEXT,
    _blank_registry,
    _clean_token,
    _known_text,
    _normalize_registry,
    _stable_id,
    _valid_url,
    normalize_us_state,
)
from loaders.facility_sources import (
    _fractracker_raw_frame,
    _parse_capacity_text,
    _parse_mixed_dates,
    load_curated_facility_records,
    load_fractracker_facility_records,
    load_gigawatt_facility_records,
    normalize_im3_locations,
)
from loaders.facility_identity import (
    KNOWN_CAMPUS_ALIASES,
    KNOWN_WIDE_RADIUS_CAMPUS_NAMES,
    _assign_canonical_ids,
    _canonical_priority,
    _has_value,
    _haversine_km,
    _identity_token,
    _known_campus_alias,
    _merge_canonical_group,
    _same_facility,
    _token_similarity,
    build_facility_observations,
    build_facility_registry,
    canonicalize_facility_observations,
    load_facility_identity_decisions,
)
from loaders.campus_registry import (
    WATER_EVIDENCE_FIELDS,
    _campus_status,
    _merge_campus_group,
    _normalized_address,
    _same_campus,
    build_campus_registry,
    registry_coverage,
    registry_stage_summary,
    water_evidence_coverage,
    water_evidence_mask,
)

__all__ = [name for name in globals() if not name.startswith('__')]
