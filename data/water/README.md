# Retained Water Data

- `raw/` contains immutable source snapshots used by the active ledger modules.
- `derived/` contains reproducible application tables created by `helpers/build_water_ledger.py`.
- `source_manifest.csv` records authority, resilience, license, checksum, parser, and ingestion state.
- `field_dictionary.csv` records the active extraction and normalization contract.

Run:

```bash
python helpers/build_water_ledger.py
```

The application reads only retained derivatives. It does not make live water-source requests.
