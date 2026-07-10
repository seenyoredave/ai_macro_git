# AI Macro Dashboard Cleanup Patch

## Scope

This patch applies the agreed one-pass cleanup and contract repair:

- `regime_metrics` is now a first-class session-state data product.
- Power Stress receives FRED history again.
- FRED is weekly archive-first using a Sunday-Saturday window.
- Put/call is daily archive-first and sequestered in `archive/put_call_history.csv` only.
- `macro_history.csv` no longer stores put/call.
- EDGAR is preferred over YFinance for fundamentals, with field-by-field YFinance fallback.
- `archive/archive_reader.py` now owns central archive read/date/key helpers.
- Existing archive dates were normalized to ISO `YYYY-MM-DD`.
- Duplicate archive keys were deduped using latest-row-wins with missing-field backfill.
- EDGAR archive schema was expanded to preserve CapEx/Revenue FY fields going forward.
- Trend calculations now sort by parsed date before velocity/acceleration.
- Basket tier smoke test was moved out of regular sector pages and into Developer Tools.
- Unused macro normalizers were commented out.
- `.DS_Store`, `__pycache__`, stale `.pyc`, and the empty `config/edgar_indicators.py` were removed.

## Archive migration

Original archive CSVs were copied into:

`archive/_pre_migration_backup/`

Migration details are recorded in:

`archive/migration_report.txt`

## Validation performed

- Python compile check across the project.
- Streamlit test runner before the EDGAR fallback-completeness tightening.
- Targeted validation for:
  - ISO archive dates.
  - no duplicate declared archive keys.
  - put/call removed from `macro_history.csv`.
  - put/call raw/normalized/source retained in `put_call_history.csv`.
  - Power Stress z-score computable from migrated FRED history.
  - FRED current-week archive-first behavior.
  - put/call today archive-first behavior.
  - EDGAR-first / YFinance field-fallback behavior.

## Note on EDGAR

Migrated legacy EDGAR rows have the new schema, but old rows may not contain true EDGAR CapEx/FY data. Rows without EDGAR Status/CapEx are treated as fallback-only so a live EDGAR pull can repair the archive when available.
