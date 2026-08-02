from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from water.eia_thermoelectric import (
    PARSER_VERSION as EIA_PARSER_VERSION,
    SOURCE_ID as EIA_SOURCE_ID,
    group_summary as eia_group_summary,
    load_raw_frame as load_eia,
    national_summary as eia_national_summary,
    normalize_observation_ledger as normalize_eia,
    plant_summary as eia_plant_summary,
)
from water.ledger import sha256_file
from water.schema import SOURCE_MANIFEST_COLUMNS, WATER_LEDGER_VERSION
from water.usgs_2015 import (
    PARSER_VERSION as USGS_PARSER_VERSION,
    SOURCE_ID as USGS_SOURCE_ID,
    category_summary as usgs_category_summary,
    county_summary as usgs_county_summary,
    load_raw_county_frame as load_usgs,
    national_summary as usgs_national_summary,
    normalize_county_observations as normalize_usgs,
    reconciliation_table as usgs_reconciliation_table,
)

RAW_USGS = ROOT / "data/water/raw/usgs/usco2015v2.0.xlsx"
RAW_EIA = ROOT / "data/water/raw/eia/Cooling_Boiler_Generator_Data_Summary_2024.xlsx"
DERIVED = ROOT / "data/water/derived"
MANIFEST_PATH = ROOT / "data/water/source_manifest.csv"
DICTIONARY_PATH = ROOT / "data/water/field_dictionary.csv"

def _manifest_rows() -> list[dict]:
    rows = [
        {
            "source_id": USGS_SOURCE_ID,
            "source_name": "Estimated Use of Water in the United States, County-Level Data for 2015, version 2.0",
            "custodian": "U.S. Geological Survey",
            "canonical_url": "https://www.usgs.gov/data/estimated-use-water-united-states-county-level-data-2015",
            "acquisition_url": "https://github.com/USEPA/USEEIO-waste-disaggregation/raw/master/data/usco2015v2.0.xlsx",
            "persistent_identifier": "doi:10.5066/F7TB15V5",
            "publication_date": "2018-06-19",
            "coverage_period": "2015",
            "geographic_coverage": "50 states, District of Columbia, Puerto Rico, U.S. Virgin Islands; county-equivalent records",
            "data_role": "Complete national withdrawal baseline by use, source, and fresh/saline class",
            "evidence_grade": "A",
            "resilience_grade": "R1",
            "evidence_class": "agency_estimate",
            "source_kind": "versioned bulk workbook",
            "license": "CC0 / U.S. government public-domain data",
            "raw_retention_allowed": "yes",
            "raw_path": str(RAW_USGS.relative_to(ROOT)),
            "raw_sha256": sha256_file(RAW_USGS),
            "parser_version": USGS_PARSER_VERSION,
            "schema_version": WATER_LEDGER_VERSION,
            "retrieval_date": "2026-07-31",
            "refresh_frequency": "historical release",
            "ingestion_status": "active",
            "source_health": "retained_and_validated",
            "notes": "Canonical DOI and USGS metadata are authoritative. The retained workbook was acquired from a public mirror because the source host was unavailable in the build environment; checksum is retained.",
        },
        {
            "source_id": EIA_SOURCE_ID,
            "source_name": "Thermoelectric Cooling Water Data, 2024 Summary",
            "custodian": "U.S. Energy Information Administration",
            "canonical_url": "https://www.eia.gov/electricity/data/water/",
            "acquisition_url": "https://www.eia.gov/electricity/data/water/",
            "persistent_identifier": "",
            "publication_date": "",
            "coverage_period": "2024 monthly",
            "geographic_coverage": "Reported U.S. thermoelectric plants in the EIA cooling-water survey frame",
            "data_role": "Plant-level reported thermoelectric withdrawal and consumption detail",
            "evidence_grade": "A",
            "resilience_grade": "R1",
            "evidence_class": "reported",
            "source_kind": "annual bulk workbook",
            "license": "U.S. government public-domain data",
            "raw_retention_allowed": "yes",
            "raw_path": str(RAW_EIA.relative_to(ROOT)),
            "raw_sha256": sha256_file(RAW_EIA),
            "parser_version": EIA_PARSER_VERSION,
            "schema_version": WATER_LEDGER_VERSION,
            "retrieval_date": "2026-07-31",
            "refresh_frequency": "annual",
            "ingestion_status": "active",
            "source_health": "retained_and_validated",
            "notes": "Reported survey records are retained without silently deleting negative or internally inconsistent values; anomalies receive quality flags.",
        },
    ]
    planned = [
        ("uswwd-user-withdrawals", "United States Water Withdrawals Database", "Virginia Tech / state water agencies", "https://doi.org/10.1038/s41597-025-06300-1", "42-state user-level self-supplied withdrawals", "A", "R1"),
        ("usgs-public-supply-2000-2020", "Public-Supply Water-Use Reanalysis, 2000–2020", "U.S. Geological Survey", "https://www.usgs.gov/data/public-supply-water-use-reanalysis-2000-2020-period-huc12-month-and-year-conterminous-united", "Modeled monthly public-supply withdrawals and consumption", "B", "R1"),
        ("usgs-irrigation-2000-2020", "Irrigation Water-Use Reanalysis, 2000–2020", "U.S. Geological Survey", "https://www.usgs.gov/data/irrigation-water-use-reanalysis-2000-20-period-huc12-month-and-year-conterminous-united-states", "Modeled monthly irrigation withdrawals and consumptive use", "B", "R1"),
        ("epa-pws-service-areas", "Public Water System Service Areas", "U.S. Environmental Protection Agency", "https://www.epa.gov/ground-water-and-drinking-water/public-water-system-service-areas", "Public-system identity and service-area geography", "A/B", "R1"),
        ("epa-icis-npdes-dmr", "ICIS-NPDES Discharge Monitoring Reports", "U.S. Environmental Protection Agency", "https://echo.epa.gov/helpers/data-downloads/icis-npdes-dmr-and-limit-data-set", "Facility permits, outfalls, discharge flow, and limits", "A", "R1"),
        ("usgs-groundwater-trends", "National Groundwater-Level Trends", "U.S. Geological Survey", "https://www.usgs.gov/data/long-term-monotonic-trends-annual-groundwater-metrics-united-states-through-2020-ver-40-may", "Groundwater-condition context", "A/B", "R1"),
        ("wade-water-rights", "Water Data Exchange / WestDAAT", "Western States Water Council", "https://westernstateswater.org/wade/", "Western water rights, allocations, and reported use", "A", "R2"),
        ("state-utility-modules", "State and Utility Water-Operations Modules", "State agencies and utilities", "", "Customer-class deliveries, sources, losses, purchases, and local permits", "A-D", "R2-R4"),
    ]
    for source_id, name, custodian, url, role, evidence, resilience in planned:
        rows.append({
            "source_id": source_id,
            "source_name": name,
            "custodian": custodian,
            "canonical_url": url,
            "acquisition_url": "",
            "persistent_identifier": "",
            "publication_date": "",
            "coverage_period": "varies",
            "geographic_coverage": "varies",
            "data_role": role,
            "evidence_grade": evidence,
            "resilience_grade": resilience,
            "evidence_class": "",
            "source_kind": "planned module",
            "license": "review required",
            "raw_retention_allowed": "review required",
            "raw_path": "",
            "raw_sha256": "",
            "parser_version": "",
            "schema_version": WATER_LEDGER_VERSION,
            "retrieval_date": "",
            "refresh_frequency": "varies",
            "ingestion_status": "identified_not_ingested",
            "source_health": "identified",
            "notes": "Inventory entry only. No observation from this source is published until raw data, contract validation, lineage, and quality tests are complete.",
        })
    return rows

def _field_dictionary() -> pd.DataFrame:
    rows = [
        ("observation_id", "Canonical", "Stable unique observation key", "text", "platform-generated"),
        ("flow_type", "Canonical", "Withdrawal, consumptive use, delivery, discharge, or other typed flow", "controlled vocabulary", "never collapsed into a generic total"),
        ("original_value", "Canonical", "Value exactly as represented by the retained source record", "source-native", "preserved before conversion"),
        ("original_unit", "Canonical", "Unit attached to the original value", "source-native", "preserved before conversion"),
        ("average_mgd", "Canonical", "Average million gallons per day", "Mgal/d", "derived only when period and volume permit"),
        ("source_category", "Canonical", "Groundwater, surface water, reclaimed, mixed, or other source", "controlled vocabulary", "source medium, not legal entitlement"),
        ("water_quality_class", "Canonical", "Fresh, brackish, saline, reclaimed, mixed, or other", "controlled vocabulary", "kept separate from source medium"),
        ("measurement_basis", "Canonical", "Metered, reported estimate, agency model, inferred residual, or other basis", "controlled vocabulary", "determines evidentiary treatment"),
        ("TO-Wtotl", "USGS 2015", "Total withdrawals for all reported categories", "Mgal/d", "agency estimate; county record"),
        ("TO-WGWTo", "USGS 2015", "Total groundwater withdrawals", "Mgal/d", "fresh plus saline"),
        ("TO-WSWTo", "USGS 2015", "Total surface-water withdrawals", "Mgal/d", "fresh plus saline"),
        ("TO-WFrTo", "USGS 2015", "Total freshwater withdrawals", "Mgal/d", "groundwater plus surface water"),
        ("TO-WSaTo", "USGS 2015", "Total saline withdrawals", "Mgal/d", "groundwater plus surface water"),
        ("TO-CUTotPartial", "USGS 2015", "Partial consumptive-use total", "Mgal/d", "nationally available only for irrigation and thermoelectric power; not total U.S. consumption"),
        ("Water Withdrawal Volume (Million Gallons)", "EIA 2024", "Monthly cooling-water withdrawal", "million gallons", "reported survey value"),
        ("Water Consumption Volume (Million Gallons)", "EIA 2024", "Monthly cooling-water consumption", "million gallons", "reported survey value; anomalies retained and flagged"),
        ("Water Type", "EIA 2024", "Fresh, saline, brackish, reclaimed, mixed, or other water-quality class", "text", "reported classification"),
        ("Water Source", "EIA 2024", "Surface, ground, discharge/reclaimed, mixed, or other source", "text", "reported classification"),
        ("Cooling System Type", "EIA 2024", "Open, closed, dry/hybrid, mixed, or other cooling system", "text", "reported classification"),
    ]
    return pd.DataFrame(rows, columns=["Field", "Layer", "Definition", "Unit or Type", "Treatment"])

def build() -> None:
    DERIVED.mkdir(parents=True, exist_ok=True)
    if not RAW_USGS.exists() or not RAW_EIA.exists():
        raise FileNotFoundError("Retained USGS and EIA raw snapshots are required")

    usgs_raw = load_usgs(RAW_USGS)
    eia_raw = load_eia(RAW_EIA)

    usgs_obs = normalize_usgs(usgs_raw)
    eia_obs = normalize_eia(eia_raw)
    observations = pd.concat([usgs_obs, eia_obs], ignore_index=True)

    usgs_county = usgs_county_summary(usgs_raw)
    usgs_national_categories = usgs_category_summary(usgs_raw, group="national")
    usgs_state_categories = usgs_category_summary(usgs_raw, group="state")
    usgs_reconciliation = usgs_reconciliation_table(usgs_raw)
    eia_plants = eia_plant_summary(eia_raw)
    eia_groups = pd.concat(
        [eia_group_summary(eia_raw, field) for field in ["Water Type", "Water Source", "Cooling System Type", "State"]],
        ignore_index=True,
    )

    summary = {
        "ledger_version": WATER_LEDGER_VERSION,
        "generated_at": "2026-07-31",
        "source_mode": "retained_local",
        "usgs_2015": usgs_national_summary(usgs_raw),
        "eia_2024_thermoelectric": eia_national_summary(eia_raw),
        "observation_rows": int(len(observations)),
        "active_sources": 2,
        "reconciliation": {
            "usgs_county_records": int(len(usgs_reconciliation)),
            "usgs_county_records_reconciled": int(usgs_reconciliation["Reconciled"].sum()),
            "usgs_max_absolute_residual_mgd": float(usgs_reconciliation["Residual Mgal/d"].abs().max()),
        },
    }

    observations.to_csv(DERIVED / "water_observations.csv.gz", index=False, compression="gzip")
    usgs_county.to_csv(DERIVED / "usgs_2015_county_summary.csv.gz", index=False, compression="gzip")
    usgs_national_categories.to_csv(DERIVED / "usgs_2015_national_category_summary.csv", index=False)
    usgs_state_categories.to_csv(DERIVED / "usgs_2015_state_category_summary.csv", index=False)
    usgs_reconciliation.to_csv(DERIVED / "usgs_2015_reconciliation.csv.gz", index=False, compression="gzip")
    eia_plants.to_csv(DERIVED / "eia_2024_thermoelectric_plant_summary.csv.gz", index=False, compression="gzip")
    eia_groups.to_csv(DERIVED / "eia_2024_thermoelectric_group_summary.csv", index=False)
    (DERIVED / "water_national_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    manifest = pd.DataFrame(_manifest_rows())
    for column in SOURCE_MANIFEST_COLUMNS:
        if column not in manifest.columns:
            manifest[column] = ""
    manifest[SOURCE_MANIFEST_COLUMNS].to_csv(MANIFEST_PATH, index=False)
    _field_dictionary().to_csv(DICTIONARY_PATH, index=False)

    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    build()
