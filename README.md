## v6.5.2 — Content-audit presentation cleanup

- Removes Power refresh diagnostics from the developer sidebar; FRED and NY Fed retain their own source-call reporting.
- Displays the release version at the right edge of the masthead subtitle row and advances the application version to v6.5.2.
- Completes a repository-wide data-content audit without adding an auditing subsystem or altering retained observations.

## v6.5.1 — Power cleanup and realized-growth polish

- Removes the visible **Watchpoint** row from every domain Read while retaining compact Current Context and References.
- Adds a Reported / Inflation-adjusted flip frame to Economic Impact; productivity and real output remain in their already-real form, while compensation and unit labor costs are deflated with retained CPI evidence.
- Adds the missing BLS manufacturing real-output series and preserves negative year-over-year observations.
- Repairs Workforce chart headroom, label spacing, and the current-momentum comparison frame.
- Rebuilds Power supply presentation around one selectable analytical frame: generation mix, generation momentum, or fleet changes.
- Restores protected metric-registry dividers and adds a divider between the Purpose Statement and the AI Macro header.
- Adds `data/v651_public_data_manifest.csv` for the new CPI and manufacturing-output evidence.

## v6.5.0 — Twelve-tab architecture

- Rehomes **Buildout Leadership Rotation** in AI Macro and retires Infrastructure as a standalone tab.
- Renames **Energy** to **Power** and confines it to electricity demand, generation, planned capacity, generation fuels, and prices.
- Adds **Grid & Storage** for interconnection, delivery constraints, storage deployment, and broad grid-investment context.
- Adds **Workforce** for employment, earnings, job openings, and labor-market participation across the AI production and deployment stack.
- Adds **Economic Impact** for realized productivity, real output, compensation, unit labor costs, and information-processing investment.
- Adds wastewater-system investment to Water with an explicit no-attribution boundary.
- Enforces the approved twelve-tab ceiling and the 2020-present evidence rule on current analytical surfaces.

## v6.4.1 — Water evidence correction and infrastructure alignment

- Replaces the stale facility-footprint comparison with a current USGS 2020 national withdrawal profile and a current facility-disclosure view that makes no unsupported water-use claim.
- Removes pre-2020 county evidence from current analytical surfaces while retaining older records only as historical provenance.
- Makes the facility and thermoelectric ledgers scrollable, state-first, and sortable without truncating the retained records.
- Adds a visible gutter between the buildout-rotation heatmap and its current-momentum panel.
- Expands support alignment to six enabling systems: compute manufacturing, electric power, communications, public water, roads and highways, and public transit.
- Reports gross positive excess, gross shortfall, and net balance under explicit channel-specific baseline methods.

## v6.3.1 — Auditable Current Context discovery

- Adds a real multi-provider discovery pipeline (`GDELT` plus Google News RSS fallback) for all eight substantive tabs.
- Records every fetched candidate, source assessment, relevance/materiality score, selection decision, and rejection reason in `data/current_context_candidate_audit.csv`.
- Writes a machine-readable refresh manifest with per-domain queries, provider status, candidate counts, and selected event provenance.
- Keeps one visible owner per development and allows a legitimate no-match result when no source clears the evidence threshold.
- Preserves a retained, explicitly labeled verified snapshot so the application remains reproducible when network access is unavailable.
- Adds a command-line refresh tool: `python -m loaders.current_context_discovery --as-of YYYY-MM-DD`.
- Retains tab-specific cadence, hard source exclusions, manual-review routing, compact references, registry dividers, and Purpose Statement spacing.

## v6.3.0 — Current Context intelligence

- Introduced source-controlled Current Context discovery, event-status tracking, persistent regulatory developments, shared metric-registry dividers, and the centered Purpose Statement container.

## v6.2.3 — Brand and purpose

- Establishes **AI Macro** as the project name and **An AI economic research platform** as its descriptor.
- Replaces the Purpose Statement with the approved capital-to-outcomes and distributional framing.
- Keeps the existing centered disclosure placement and all analytical behavior unchanged.

## v6.2.1 Platform spacing and alignment

### v6.2.2 — Purpose statement vertical alignment

- Vertically centers the expanded Purpose Statement copy within its disclosure window.
- Adds balanced top and bottom breathing room without changing the statement text or placement.


- Adds nice-grid axis bounds with a full visible reference interval beyond plotted data.
- Gives the electricity-demand, stacked capacity, data-center, water, adaptation, finance, and market charts more consistent visual breathing room.
- Matches 20 named side-by-side analytical panels across Market, Finance, Compute, and Energy using contained minimum-height rules.
- Avoids brittle platform-wide DOM stretching; only known paired windows are aligned.
- Adds `helpers/layout_spacing_smoke_test.py` to regression-test headroom and panel-pair coverage.

## v6.2.0 Data Center + Energy visual hierarchy

- Reframed Data Center around national scale, development lifecycle, geographic concentration, and project/operator structure.
- Reduced Data Center to three default-visible analytical views with geography and project selectors.
- Separated broad national facility estimates from the tighter stage-tracked and canonical project universes.
- Reduced Energy to four default-visible charts.
- Replaced the second demand chart with a compact large-load concentration profile.
- Combined generation mix and current fleet changes into one coordinated supply graphic.
- Preserved the cool violet-blue-slate palette and moved supporting evidence behind deliberate controls.

# AI Macro

*An AI economic research platform*

## Purpose

AI Macro traces the AI economy from capital and construction through deployment, adoption, and economic results. Using publicly available data, it connects companies and markets with the data centers, resources, and infrastructure behind the buildout—and examines how that buildout is reshaping the broader U.S. economy. Its central questions are whether rising investment and capacity are producing durable use, broad participation, and realized value—and how the resulting gains, costs, and risks are distributed across investors, businesses, workers, communities, and regions.

## Dashboard

The interface has twelve tabs:

- **AI Macro:** cross-platform synthesis, regime indicators, buildout leadership rotation, gap measures, and the national facility landscape
- **Market:** equity leadership, concentration, participation, valuation, fundamentals, and sector conditions
- **Finance:** funding capacity, private-capital realization, credit markets, and financial stress
- **Compute:** domestic compute manufacturing, utilization, investment, projects, and supply coverage
- **Data Center:** facility scale, development pipeline, geography, capacity evidence, projects, and operators
- **Power:** electricity demand, generation, planned capacity additions and retirements, generation fuels, and prices
- **Grid & Storage:** interconnection queues, delivery maturity, storage deployment, and broad electric-power construction context
- **Water:** competing water claims, facility disclosure, thermoelectric demand, wastewater investment, and resource constraints
- **Adaptation:** current and expected business AI use, diffusion, and deployment breadth
- **Workforce:** employment, earnings, job openings, and labor demand in directly relevant industries
- **Economic Impact:** realized productivity, output, compensation, unit labor costs, and investment validation
- **Evidence:** definitions, methods, retained observations, source records, coverage, and provenance

## v6.0 read architecture

The platform uses a shared deterministic read contract across eleven analytical tabs. Each Read presents one compact condition, driver summary, Current Context row, and references. The Market Sector Read remains a selected-sector diagnostic, while the Evidence tab remains provenance-only.

The AI Macro Read is generated from the structured domain signals, not by concatenating domain prose. It selects at most three material cross-platform observations, may omit entire domains, and may include one sourced Current Context development from a domain that actually contributes to the synthesis. Editorial budgets are regression-tested.

Run the narrative regression suite with `python helpers/read_architecture_smoke_test.py` and the new-domain regression with `python helpers/workforce_economic_impact_smoke_test.py`.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run ai_macro.py
```

The application uses retained local data when live sources are unavailable. Manual refresh controls are available in the sidebar.

Run the bounded stop-the-line integrity gate with `python helpers/integrity_gate.py`. It checks only headline data contracts and named high-impact campus duplicates; it is not a general UI test suite.

## Project structure

```text
ai_macro.py       Streamlit entry point and application state
analytics/        analytical engines and calculated data products
archive/          retained history readers and writers
benchmarks/       benchmark construction and normalization
config/           static universes, fields, series, and metric definitions
data/             retained source and derived data
factors/          factor normalization and weights
helpers/          maintenance and data-rebuild scripts
loaders/          live and retained data loading
rendering/        dashboard components, charts, tab renderers, and theme
water/            water-source parsing and ledger construction
```

## Maintenance scripts

```bash
python helpers/backfill_borrower_strain.py
python helpers/build_data_center_inventory.py
python helpers/build_infrastructure_ledger.py
python helpers/build_water_ledger.py
python helpers/rebuild_derived_history.py
```

These scripts rebuild retained datasets used by the application. They are not required for a normal dashboard launch.

## v6.0.2 read and sector-context refinements

- Restores compact inline Recent Context and References rows across subordinate tab reads.
- Adds source references to every subordinate read using the same numbered side-by-side treatment.
- Gives every Market sector a This Week row. Curated primary-source items are preferred; missing sectors use a live seven-day sector news RSS pull, with an explicit no-match status if no qualifying headline is available.
- Enforces exact sector and constituent membership so a company event cannot leak into an unrelated sector.


## v6.1.1 Front-page purpose disclosure

- Moves the Purpose Statement out of the permanent AI Macro body.
- Adds one collapsed Purpose statement disclosure immediately above the AI Macro title and subtitle.
- Keeps the purpose copy available on the landing page without competing with the macro analysis.

## v6.1.0 Finance capital lifecycle

- Reorganizes Finance into Capital Funding, Private Capital Realization, Credit Markets, and Financial Stress.
- Adds a retained CalSTRS public-LP technology and AI-adjacent fund cohort with standard DPI, RVPI, and TVPI calculations.
- Uses five-year-plus vintages for headline realization metrics while retaining younger funds in the realization map and collapsed evidence table.
- Adds a cool-toned realization ledger and DPI/TVPI fund map without changing the platform's restrained violet-blue-slate visual system.
- Extends the Finance Read and source references with private-capital realization evidence and ILPA methodology.

Run the targeted regression with `python helpers/finance_private_capital_smoke_test.py`.

## v6.1.2 Purpose disclosure spacing

- Vertically centers the collapsed Purpose Statement label and disclosure icon.
- Adds balanced top and bottom breathing room without changing the component placement or content.

## Deployment modes

AI Macro defaults to **public mode**. Public mode keeps the GitHub-retained data and archive files read-only, hides developer refresh controls, and stores the once-daily Current Context result in an ephemeral shared runtime ledger. The first session for an Eastern market date performs the discovery pass; later sessions reuse that result.

For the desktop maintenance workflow, start the app in **developer mode**:

```bash
AI_MACRO_MODE=developer streamlit run ai_macro.py
```

Developer mode enables the refresh, cache, archive, tier-diagnostic, and load-report controls and permits retained repository data to be updated before a GitHub push. Sector membership is maintained only in `config/sector_config.py`.

The twelve dashboard tabs remain eagerly rendered so tab changes stay immediate. Source loaders continue to use shared Streamlit caches, while public users cannot force cache clears or upstream refreshes.
