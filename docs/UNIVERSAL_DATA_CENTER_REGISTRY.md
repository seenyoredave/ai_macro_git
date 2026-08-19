# AI Macro v9.6.2 — Universal Data Center Registry

## Authority

`loaders/data_center_registry.py` is the only data-center identity authority in AI Macro.

All domains use the same `Campus ID` set. Water, Power, Grid & Storage, Connectivity, Evidence, and the Data Centers page may enrich or aggregate those entities; they do not create, split, merge, deduplicate, or rename data-center identities.

## Entity hierarchy

```text
Campus ID
├── Facility ID
│   ├── Building ID
│   └── Building ID
└── Facility ID
    └── Building ID
```

The retained registry consists of normalized relational tables:

- campuses;
- facility and building entities;
- source-native observations;
- observation-to-entity membership;
- unresolved source observations;
- registry metadata and source fingerprint.

These tables are different grains of one registry, not independent registries.

## Source-grain rules

Source semantics are preserved before cross-source resolution.

- A source `campus` record can establish campus identity when it carries sufficient identity evidence.
- A source `facility` record can establish a local campus when no stronger campus record exists.
- A source `building` record remains a building. An uncorroborated lone building cannot create a campus. A geographically coherent multi-building site can establish an inferred campus when the building records support the same local identity.
- A source `site_point` remains location evidence. It can attach to an established campus; an uncorroborated point never creates a campus.
- Explicit reviewed merge/separate decisions are applied centrally by the registry.

IM3 `campus`, `building`, and `point` observations therefore retain their source-native meanings instead of being flattened into one facility table.

## Metric grain

Every data-center fact has an entity grain. Campus-wide direct measurements take precedence over facility/building rollups. When no campus total exists, facility values roll to the campus; when facility values are unavailable, building values may roll to the campus using the metric's declared aggregation rule.

A campus total and its facility/building measurements are not added together.

## Runtime contract

Normal application startup reads the retained universal registry from:

```text
data/infrastructure/derived/universal_data_center_registry.json
data/infrastructure/derived/universal_data_center_entities.csv
data/infrastructure/derived/universal_data_center_observations.csv
data/infrastructure/derived/universal_data_center_membership.csv
data/infrastructure/derived/universal_data_center_unresolved.csv
```

Raw identity sources are read only when the retained registry is absent/stale or Data Centers is explicitly refreshed. This keeps identity resolution out of the ordinary Streamlit startup path.

The curated registry sources live under:

```text
data/infrastructure/curated/data_center_primary_evidence.csv
data/infrastructure/curated/data_center_identity_decisions.csv
```

The v9.6.2 cutover removes the former facility/campus identity modules and former top-level identity-source filenames.

## Geography contract

Macro and Data Centers use the same interactive campus map in `rendering/spatial.py` / `rendering/charts_data_center.py`.

Map points carry `Campus ID` in selection data. A national campus click can drill into the selected state, and state maps preserve campus selection. Water uses the same Campus IDs for its drought/water context and campus selection.

## Release gate

The overhaul is accepted only after `helpers/data_center_registry_release_gate.py` passes against the actual retained national checkout. The gate verifies:

- one identity authority and no legacy identity modules/keys;
- retained registry freshness through the current source fingerprint and retained-table SHA-256 verification;
- unique IDs and labels;
- no county-only identities promoted to campuses;
- no uncorroborated point or lone-building campus creation;
- observation membership uniqueness;
- Umatilla AWS regression: the 15 generic IM3 AWS building footprints resolve into four local campuses rather than 15 campus identities;
- Water has exactly the campus universe;
- Connectivity joins only by Campus ID;
- retained registry startup-load performance bound.
