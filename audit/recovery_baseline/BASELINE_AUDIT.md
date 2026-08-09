# v6.9.1 Recovery Baseline Audit

Generated: 2026-08-09T02:40:16.637089+00:00

## Executive finding

The codebase is substantial and compiles, but the packaged green test suite is not equivalent to user-visible verification. Of 23 smoke tests, 14 use a fake Streamlit runtime, 19 inspect source text, and 0 invoke a browser.

All retained historical-series contracts pass. The retained-startup contract passed with provider network access blocked and retained-file hashes checked before and after the full loader graph. Full-app Streamlit screenshots remain unverified in this audit environment because the declared Streamlit runtime is unavailable.

## Compilation and packaged tests

- Python source compilation: **PASS** (582 files)
- Smoke tests: **23/23 passed**

| Test | Result | Seconds | Fake Streamlit | Source inspection | Browser |
|---|---:|---:|---:|---:|---:|
| application_import_smoke_test | PASS | 1.144 | yes | no | no |
| connectivity_domain_smoke_test | PASS | 3.734 | yes | yes | no |
| current_context_smoke_test | PASS | 1.105 | no | yes | no |
| data_center_page_smoke_test | PASS | 3.581 | yes | no | no |
| domain_refresh_smoke_test | PASS | 1.066 | yes | yes | no |
| energy_page_smoke_test | PASS | 2.945 | yes | yes | no |
| finance_private_capital_smoke_test | PASS | 1.326 | no | yes | no |
| finance_strain_smoke_test | PASS | 1.657 | no | yes | no |
| layout_recovery_smoke_test | PASS | 0.080 | no | yes | no |
| layout_rollout_render_smoke_test | PASS | 7.533 | yes | no | no |
| layout_spacing_smoke_test | PASS | 1.605 | no | yes | no |
| market_panel_smoke_test | PASS | 1.786 | no | yes | no |
| phase1_value_transmission_smoke_test | PASS | 1.086 | yes | yes | no |
| phase2_grid_water_smoke_test | PASS | 9.042 | yes | yes | no |
| public_copy_smoke_test | PASS | 0.751 | no | yes | no |
| read_architecture_smoke_test | PASS | 3.894 | yes | yes | no |
| read_divider_smoke_test | PASS | 0.072 | no | yes | no |
| snapshot_writer_smoke_test | PASS | 0.779 | yes | no | no |
| stack_completion_fidelity_smoke_test | PASS | 0.903 | yes | yes | no |
| startup_loader_contract_test | PASS | 9.155 | yes | yes | no |
| visual_system_smoke_test | PASS | 2.084 | no | yes | no |
| water_infrastructure_page_smoke_test | PASS | 1.067 | yes | yes | no |
| workforce_economic_impact_smoke_test | PASS | 1.511 | yes | yes | no |

## Historical-series contracts

| Contract | Result | Valid observations | Earliest | Latest | Span days |
|---|---:|---:|---:|---:|---:|
| Finance NFCI ten-year confirmation | PASS | 2900 | 1971-01-08 | 2026-07-31 | 20293 |
| Finance ANFCI ten-year confirmation | PASS | 2900 | 1971-01-08 | 2026-07-31 | 20293 |
| Corporate bond distress history | PASS | 1125 | 2005-01-07 | 2026-07-24 | 7868 |
| Borrower strain ten-year view | PASS | 17 | 2014-12-31 | 2026-06-13 | 4182 |
| Private-equity lender-strain view | PASS | 12 | 2013-12-31 | 2024-12-31 | 4018 |
| Bank capital lender-strain view | PASS | 65 | 2009-10-01 | 2025-10-01 | 5844 |
| Retained market archive (informational) | INFO | 5100 | 2026-06-12 | 2026-07-29 | 47 |
| Power-series retained history | PASS | 138 | 2015-01-01 | 2026-06-01 | 4169 |

## Startup findings

- Application constructs one central load policy: **True**
- Public mode defaults to read-only: **True**
- Public refresh requests resolve to retained mode: **True**
- Repository writes require developer mode: **True**
- Snapshot writes require an explicit refresh: **True**
- Dashboard renderer is eager rather than active-tab-only: **True**

The source findings above describe application routing. The retained-startup contract supplies the network and write instrumentation.

## Layout proof status

- Data Centers → Geographic pattern now uses the full-width proof contract.
- Water → National water claims now uses the compact chart-plus-vertical-rail proof contract.
- Shared HTML/CSS primitives are browser-measured separately at 1280, 1600, 1920, 2560, and 768 px.
- This is **not yet a full Streamlit application screenshot pass**.

## Data inventory

The machine-readable inventory contains 103 retained CSV files with row counts, column counts, and parseable date ranges.
