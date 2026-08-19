from __future__ import annotations

WATER_LEDGER_VERSION = "1.0"
WATER_SOURCE_REGISTER_VERSION = "1.0"

EVIDENCE_CLASSES = {
    "measured",
    "reported",
    "agency_estimate",
    "academic_model",
    "permitted",
    "inferred",
    "scenario",
}

FLOW_TYPES = {
    "withdrawal",
    "purchase_import",
    "transfer_in",
    "treatment_production",
    "delivery_sale",
    "consumptive_use",
    "reuse_intake",
    "reclaimed_delivery",
    "discharge",
    "return_flow",
    "transfer_out",
    "nonrevenue_water",
    "system_use",
    "storage_addition",
    "storage_release",
}

SOURCE_CATEGORIES = {
    "groundwater",
    "surface_water",
    "purchased_water",
    "reclaimed_wastewater",
    "seawater",
    "brackish_water",
    "mixed",
    "other",
    "unknown",
}

WATER_QUALITY_CLASSES = {
    "fresh",
    "brackish",
    "saline",
    "reclaimed",
    "mixed",
    "other",
    "unknown",
}

MEASUREMENT_BASES = {
    "metered",
    "reported_estimate",
    "pump_hours_estimate",
    "engineering_estimate",
    "agency_model",
    "remote_sensing",
    "permit_allocation",
    "inferred_residual",
    "unknown",
}

OBSERVATION_COLUMNS = [
    "observation_id",
    "entity_id",
    "site_id",
    "geography_type",
    "geography_id",
    "state",
    "county",
    "period_start",
    "period_end",
    "temporal_resolution",
    "flow_type",
    "original_value",
    "original_unit",
    "volume_million_gallons",
    "average_mgd",
    "source_category",
    "water_quality_class",
    "use_category",
    "measurement_basis",
    "evidence_class",
    "source_id",
    "source_record_id",
    "retrieved_at",
    "source_revision_date",
    "method_version",
    "quality_flag",
    "confidence_grade",
    "missing_reason",
]

SOURCE_MANIFEST_COLUMNS = [
    "source_id",
    "source_name",
    "custodian",
    "source_url",
    "acquisition_url",
    "persistent_identifier",
    "publication_date",
    "coverage_period",
    "geographic_coverage",
    "data_role",
    "evidence_grade",
    "resilience_grade",
    "evidence_class",
    "source_kind",
    "license",
    "raw_retention_allowed",
    "raw_path",
    "raw_sha256",
    "parser_version",
    "schema_version",
    "retrieval_date",
    "refresh_frequency",
    "ingestion_status",
    "source_health",
    "notes",
]
