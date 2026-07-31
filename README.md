# AI Economic Research Platform

## Purpose

AI Macro tracks the development of AI as an economic instrument and its footprint in the US economy.

It examines who is building it, how the buildout is financed, where this growth occurs, and the physical capacity required to sustain it.

It measures deployment, economic returns, and the adaptation of businesses, workers, and institutions to AI integration.

Using publicly available data, the platform connects capital committed, capacity built, adoption achieved, and value realized.

## Dashboard structure

The v4.14 development interface is organized into seven primary tabs:

- **AI Macro:** a deterministic Snapshot spanning markets, financing, infrastructure, energy, adaptation, and economic validation
- **Market:** AI-specific sector analysis with cross-sectional positioning, movement, sector-basket concentration, fundamental evolution, and market performance; the header reports the actually loaded sector and ticker counts
- **Finance:** deployment funding, public corporate-bond market functioning, Borrower Strain, Lender Strain, and NFCI/ANFCI confirmation
- **Infrastructure:** direct buildout measures, an evidence-graded facility registry, and national infrastructure expenditure
- **Energy:** fuel supply, retail electricity cost, power production, grid capacity, and AI-linked electricity demand
- **Adaptation:** observed business AI use, expected near-term use, uncertainty intervals, and adoption breadth by industry
- **Evidence:** purpose, metric definitions, source state, coverage, methodology, and underlying observations

The masthead contains only the platform identity and purpose. Data coverage and freshness are reported where they are analytically relevant rather than compressed into a global status label.

## Design principles

- Public and reviewable source data
- Static, explicit weights
- Defined minimum-data requirements
- Missing values remain missing rather than becoming zero
- Versioned definitions to prevent silent blending with previous-method calculations
- No press-release project estimates inside scoring engines
- No numerical confidence scores for subjective information

## Primary data sources

- **YFinance:** prices, market capitalization, enterprise-value inputs, analyst revenue estimates, company statements, and price/volume history. During regular U.S. market hours, the first complete load of each Eastern trading date is live; later loads use that day's complete archive. Closed-session loads use the latest complete archive. Manual YFinance refreshes remain available in Developer Tools.
- **SEC / EDGAR:** standardized financial facts, filing-backed commitment disclosures, public BDC credit quality, and Form PF aggregates
- **FRED:** macroeconomic, bank, industrial-production, financial-conditions, information-investment, power, and weekly energy-market series
- **Federal Reserve Bank of New York:** Corporate Bond Market Distress Index history for the overall, investment-grade, and high-yield markets
- **U.S. Census Bureau:** private and public construction spending; Business Trends and Outlook Survey observations of current and expected business AI use
- **IM3 Open Source Data Center Atlas:** OpenStreetMap-derived reference locations for the observed U.S. data-center footprint
- **Primary project evidence:** company disclosures, state registrations, regulatory records, and other attributable documents used for explicitly curated facility records
- **U.S. Energy Information Administration:** monthly national commercial and industrial average retail electricity prices from Electric Power Monthly Table 5.3
- **Curated weekly context:** confirmed primary records from federal agencies, regulators, grid operators, public filings, and attributable project sources; only sources used in the current Snapshot are linked below it

## Headline framework

### Snapshot interpretation

The AI Macro tab translates the measured system into a compact Snapshot without using a language model or requiring a weekly editorial narrative. The interpretation layer produces:

- one categorical state headline;
- up to three expansion factors;
- up to three constraints; and
- up to three current-week events or material metric changes.

The headline and factor selection remain deterministic. The former free-standing synthesis sentence has been removed: the headline and three columns are the Snapshot. Each factor is a short, single-claim statement written in ordinary language.

The **This week** column uses a small, reviewable registry of confirmed primary-source events. It does not scrape headlines or generate commentary. Each entry pairs a verified fact with a restrained statement of platform relevance, and numbered source links appear directly below the Snapshot. Material platform changes since the previous completed Friday fill unused slots. Slow annual or monthly changes do not repeat unless a new observation arrives after the weekly baseline. Events expire automatically after their stated window.

The output, domain states, metric changes, weekly event metadata, and references are archived under a versioned interpretation contract, so later wording or threshold changes do not silently rewrite prior states.

Headlines are restricted to a neutral expansion-and-constraint ladder: Broad expansion, Expansion continuing, Uneven expansion, Expansion with emerging constraints, Expansion with material constraints, Constraints broadening, Financing constrained, Broad contraction, Stabilizing, Expansion reaccelerating, or Partial snapshot when coverage is insufficient.

The interpretation does not collapse the platform into a single numerical master score. The underlying metrics remain visible immediately below it.

Infrastructure and Adaptation are first-class Snapshot domains. Data-center construction is expansion evidence on its own and becomes a constraint only when rapid construction growth is corroborated by an independently measured Power Capacity Gap. Business AI-use changes can describe diffusion or weakening, but do not imply productivity, return on investment, or labor effects. Snapshot coverage distinguishes nine core inputs from two supplemental Infrastructure and Adaptation inputs. The selected values, domain states, and Snapshot context are archived under the versioned interpretation contract.

### AI Equity Index

AEI measures the strength and extension of the selected AI equity universe. It is the equal mean of valid sector scores; at least 75% of configured sectors must be valid.

Each sector requires all three factors:

- Forward EBIT-Yield Valuation Stretch: 40%
- Relative Performance: 35%
- Market Breadth above the 200-day moving average: 25%

The valuation factor uses aggregate forward EBIT yield:

`sum(forward EBIT) / sum(enterprise value)`

A sector requires at least five companies and 60% enterprise-value coverage for that factor. Negative forward EBIT remains valid in the full-sector yield used by AEI. The displayed Forward EV/EBIT product is calculated separately for the profitable cohort as `sum(EV) / sum(forward EBIT)`, while Loss-Making EV Share reports the portion of valid enterprise value with non-positive forward EBIT.

Scale: **0–100**

- Weak: below 30
- Neutral: 30–59
- Strong: 60–79
- Extended: 80+

### AI Development Intensity

ADI measures observable physical and capital buildout through four equally weighted pillars:

1. Capital Deployment
2. Data Center Construction
3. Compute Supply Realization
4. Power Footprint

At least three of four pillars must be valid. Valid fixed weights are renormalized.

Scale: **0–100**

### Speculation Gap

`Speculation Gap = AEI - ADI`

- Positive: equity enthusiasm is running ahead of observable development.
- Negative: development is running ahead of the equity regime.
- Near zero: market enthusiasm and measured development are broadly aligned.

Scale: **-100 to +100**

### Economic Validation Gap

EVG asks whether enterprise capital deployment is being validated by realized company revenue and broader real information-processing investment.

All three legs use year-over-year growth:

- Aggregate enterprise-software CapEx deployment
- Aggregate enterprise-software revenue validation
- Real information-processing equipment and software investment validation

Company growth uses ratio-of-sums aggregation. Each leg is normalized independently. Empirical percentiles are used only after at least eight distinct historical observations exist; explicit anchored scales are used before then.

`EVG = Deployment Score - 0.50(Revenue Validation) - 0.50(Macro Investment Validation)`

- Positive: deployment is running ahead of observed validation.
- Negative: revenue and broader investment are validating or outpacing deployment.

Scale: **approximately -100 to +100**


### Power Capacity Gap

Power Capacity Gap asks whether observable AI deployment pressure is advancing faster than the measured national response of the electric-power system.

`Deployment Pressure = 0.60(Data Center Construction) + 0.40(Capital Deployment)`

`Power-System Response = 0.60(Delivered Power Growth) + 0.40(Installed Capacity Growth)`

`Power Capacity Gap = Deployment Pressure - Power-System Response`

- Positive: deployment pressure is outrunning measured power delivery and capacity growth.
- Negative: the national power response is advancing faster than deployment pressure.
- Near zero: deployment and the measured response are broadly aligned.

Both response components are required, so nameplate capacity is not used alone. The result remains a national proxy and does not directly measure regional transmission constraints, interconnection queues, local congestion, or firm-capacity adequacy.

Scale: **-100 to +100**

### Power Stress Index

Power Stress combines:

- Commercial electricity-sales growth minus residential growth: 40%
- Electric-power capacity utilization: 35%
- Electric-power output growth minus capacity growth: 25%

At least two of three components must be valid.

Scale: **-100 to +100**, centered at 0

### Borrower Strain

Borrower Strain combines cash-flow and debt-capacity strain with applied obligations and contingent exposures:

- Cash Flow Strain: 30%
- Debt Capacity Strain: 25%
- Committed Burden: 30%
- Contingent Exposure: 15%

At least three of four components must be valid.

Debt Capacity Strain distinguishes:

- profitable companies with positive EBITDA;
- nonprofitable companies carrying positive net debt; and
- nonprofitable companies holding net cash.

Negative EBITDA is therefore not silently excluded from the leverage assessment.

Borrower Strain is filing-driven rather than truly daily. Its chart retains every dated snapshot, while displayed velocity and acceleration use only distinct score observations so repeated same-value app runs do not create false zero movement.

Scale: **-100 to +100**, centered at 0

### Lender Strain

Lender Strain measures deterioration in financing-system behavior and capacity through two equally weighted channels.

**Bank Channel: 50%**

- Bank Credit Tightening
- Bank Capital Strain

**Nonbank Channel: 50%**

- Public BDC Private Credit Impairment
- PE Portfolio Financing Strain

The headline requires at least three of four pillars and at least one valid pillar from each channel. Missing weights are renormalized inside the affected channel only. Each pillar uses its own historical normalization when enough observations exist and an explicit anchored scale before then.

Scale: **-100 to +100**, centered at 0

### Electricity Cost

The Energy tab reports monthly U.S. commercial and industrial average retail electricity prices in cents per kilowatt-hour. Both customer classes are shown because neither is a universal data-center tariff. The readings provide downstream delivered-cost context and do not represent wholesale prices, nodal congestion, utility riders, or negotiated hyperscale contracts.

Wholesale power prices remain outside the current national product because they are regional and nodal. They become analytically useful when facility records can be mapped consistently to organized-market and balancing-authority geography.

### Debt Markets

The Finance tab adds the New York Fed Corporate Bond Market Distress Index as a direct reading of public debt-market functioning. The section shows the overall market, investment-grade, and high-yield indexes plus ten years of weekly observation history.

CMDI combines primary-market issuance and pricing, secondary-market pricing and liquidity, and the relationship between traded and nontraded bonds. Higher readings indicate more impaired market functioning and more difficult access to public debt capital. The readings remain separate from Borrower Strain and Lender Strain.

The workbook contains weekly observations and is published monthly. The loader uses bundled history and requests an update only after the scheduled last-Wednesday release or when **Refresh Debt Markets** is selected.

### NFCI and ANFCI

The Chicago Fed National Financial Conditions Index is shown directly as an independent weekly confirmation signal.

- Negative NFCI: conditions looser than the long-run average
- Positive NFCI: conditions tighter than the long-run average
- Three-month change: current direction of travel

NFCI is not blended into Borrower Strain or Lender Strain. ANFCI is shown as a contextual comparator in the same financial-conditions plot.

### Sector Basket Concentration

Market concentration is reported by sector on the Market tab rather than as a universe-wide AI Macro reading. Each sector uses raw market-cap HHI adjusted for its valid constituent count:

`Adjusted HHI = 100 × (Raw HHI - 1/N) / (1 - 1/N)`

A value of 0 represents an equal-weight basket with the same number of valid companies; 100 represents single-company concentration. Rankings require at least three positive-market-cap constituents and 60% coverage. The measure describes the configured sector basket, not the entire economic sector.

## Infrastructure tab

Infrastructure records buildout and site context.

### Evidence-graded facility registry

The facility layer combines the IM3/OpenStreetMap observed footprint with explicitly curated project records. It is a registry of source-backed records, not a complete census and not a confirmed AI-compute inventory. Curated records retain source, evidence grade, status, observation date, and location precision. Geographic proxies are labeled as proxies.

The data contract keeps the following fields separate:

- square footage;
- planned data-center capacity;
- contracted utility capacity;
- energized capacity;
- annual electricity consumption;
- planned onsite generation;
- water withdrawal;
- water consumption;
- site WUE;
- cooling system; and
- water source.

A value is never inferred from another field. Planned generation is not treated as data-center capacity, square footage is not converted into MW, and undisclosed water use remains missing. The map sizes records using one selected metric at a time. Records without that metric remain visible as outlined markers rather than being treated as zero or sized with a substitute. The evidence table reports the underlying fields and provenance.

The initial curated ledger adds three Texas Panhandle projects that are absent from the observed IM3 footprint: Project Caprock, Google's Armstrong County campus, and Project Matador. Their markers use disclosed-area proxies where exact coordinates are unavailable.

### Buildout and U.S. Infrastructure Expenditure

The Buildout section places the direct construction chart immediately below its summary readings. It contains Data Center Construction and the Census **Computer, Electronic & Electrical Manufacturing Construction** category. The latter includes semiconductor-fab construction but is not semiconductor-exclusive.

The separate **U.S. Infrastructure Expenditure** section reports national communication, transport, and public water-supply construction expenditures. The complete national series are shown without inferring an AI-attributable share.

Communication, highway and street, public transportation, and public water-supply construction are shown separately and in full. The platform does not estimate an AI-attributable share. Public water-supply construction is capital spending on water infrastructure, not data-center withdrawal or consumption.

## Adaptation tab

The first Adaptation view measures observed employer-business AI use, expected use within six months, the **Expected Adoption Gap**, and the breadth of use across industries using Census Business Trends and Outlook Survey estimates.

Current-use and expected-use charts display 95% confidence intervals calculated as estimate ± 1.96 × published standard error. The platform does not display an exact interval for the Expected Adoption Gap because the covariance between the two estimates is not available in the published input; assuming independence would imply unsupported precision.

Adoption is not treated as productivity, return on investment, labor displacement, or institutional adaptation. Those outcomes require separate measurements.

## Energy tab

The Energy tab follows the chain from fuel supply to power delivery and AI-linked demand. It is a weekly data product, not a real-time trading screen.

Four Energy-only series are retrieved in one public FRED CSV request and archived by completed week:

- Henry Hub natural-gas spot price: four-week change
- WTI crude-oil spot price: four-week change
- Coal-production index: three-month change
- Renewable-power-output index: three-month change

Electric-power output, capacity, and utilization are reused from the application's existing FRED pipeline and retained power-series history. The bundled monthly G.17 history begins in 2015, supporting an eight-year production and capacity-response view without another live request. They are not downloaded a second time by the Energy loader.

The weekly refresh date advances after Friday at 4:00 p.m. Eastern. A complete current-week Energy archive suppresses another automatic request. **Refresh Energy** bypasses the weekly gate without refreshing YFinance or EDGAR. Source failures are recorded in the Developer Tools load report, and the bundled local history prevents a blank first render.

## Sector analytics

### Trading Pressure

Pressure is separate from AEI and measures trading extension and instability:

- Forward EBIT-Yield Valuation Stretch: 25%
- Price Extension above 200-day average: 25%
- Momentum Acceleration: 20%
- Realized-Volatility Expansion: 15%
- Abnormal Volume Activity: 15%

At least three of five components must be valid.

### Fastest Mover

Movement is the root-sum-of-squares change in sector assessment and trading pressure:

`Movement = sqrt((Delta Assessment)^2 + (Delta Pressure)^2)`

Opposing changes cannot cancel, and movement remains on a nonnegative scale.

## Missing-data contract

- Calculation functions return a finite value or missing data.
- Missing inputs are never converted to zero.
- Composite scores use explicit minimum-data rules.
- Static weights are renormalized only after the minimum-data rule is met.
- Current headlines may use the latest valid archive value from the same metric version.
- YFinance performs one automatic live universe pull per Eastern trading date during regular market hours. A complete same-day archive blocks repeated automatic pulls; after 4:00 p.m. Eastern and on weekends, the latest complete archive is used.
- Energy performs one automatic public-source refresh per completed week. Weekly FRED observations and monthly EIA retail-price observations retain separate source dates; a current weekly archive plus retained monthly history blocks unnecessary requests. Manual Energy refreshes remain independent.
- Debt Markets uses the bundled CMDI history until a new scheduled monthly release is due. Manual Debt Markets refreshes bypass the release gate.
- A partial hosted-market pull is retried once, then reconciled ticker-by-ticker with the latest complete archive rather than silently shrinking the universe.
- Carried-forward display values are not archived as new observations.
- The renderer shows a bordered **No Data** state when neither current nor compatible archive data exists.

## Archive versions

The revised definitions use new version boundaries:

- AEI: 3.0
- Economic Validation Gap: 2.0
- Power Capacity Gap: 1.0
- Borrower Strain: 3.0
- Lender Strain: 3.0
- Trading Pressure: 3.0
- Current Sector Assessment: CSA_v4.0

Older derived histories are retained but are not silently treated as observations from the revised definitions. New compatible history accumulates prospectively unless source fields permit a defensible rebuild.

## Borrower Strain historical backfill

The recommended history is:

- annual filing-date observations through 2024;
- quarterly observations from 2025 until the existing live archive begins; and
- the current archive thereafter.

SEC structured statements can support Cash Flow Strain and Debt Capacity Strain. Committed Burden and Contingent Exposure require semi-automated filing-note reconstruction and review. Missing historical disclosures must remain unknown.

See `data_notes/borrower_strain_history_backfill.md`.

## Benchmark

The active benchmark is the configured static QQQ top-holdings proxy. Holdings weights are normalized within the proxy. Return, beta, enterprise value, and forward EBIT are aggregated using those normalized weights. Benchmark valuation is expressed as aggregate forward EBIT yield and its reciprocal Forward EV/EBIT multiple.

## Optional API configuration

The dashboard can start without a `.streamlit/secrets.toml` file by using archives and public fallbacks. Optional credentials may be supplied as environment variables or Streamlit secrets:

```toml
FRED_API_KEY = "your_fred_api_key"
SEC_USER_AGENT = "AI Macro Dashboard your_email@example.com"
```

## Run locally

```bash
python -m pip install -r requirements.txt
streamlit run ai_macro.py
```

## Validation

Install the development dependencies and run the mandatory release gate from
the project root:

```bash
python -m pip install -r requirements-dev.txt
python tools/release_check.py
```

The release gate compiles the repository, runs the complete pytest suite,
executes `ai_macro.py` from top to bottom with deterministic source stubs, and
runs the actual Finance and Evidence render paths against a narrow Streamlit
stand-in. Packaging should not proceed unless the gate exits successfully.

## Architecture

- `ai_macro.py`: sole Streamlit execution entry point and application data pipeline
- `research_overlay/renderers.py`: seven-tab research interface orchestration
- `research_overlay/components.py`: reusable research UI components
- `research_overlay/visuals.py`: Plotly research figures
- `research_overlay/theme.py`: platform visual system
- `loaders/market_prices.py`: price-history calculations
- `loaders/company_fundamentals.py`: statement parsing and company financial calculations
- `loaders/market_loader.py`: session-aware YFinance orchestration, manual source refreshes, retry logic, and complete-universe archive fallback
- `loaders/market_freshness.py`: pure live/archive reconciliation and runtime source diagnostics
- `loaders/fred_loader.py`: macro and power data
- `loaders/nfci_loader.py`: isolated NFCI history and fallback chain
- `loaders/debt_markets_loader.py`: monthly publication gate and bundled New York Fed CMDI history
- `loaders/infrastructure_loader.py`: construction history, IM3 footprint ingestion, composite facility-registry assembly, and coverage
- `loaders/facility_registry_loader.py`: field-specific evidence contract for observed and curated facility records
- `loaders/adaptation_loader.py`: Census BTOS current/expected AI-use history, standard errors, and industry snapshot
- `loaders/edgar_loader.py`: EDGAR data quality and archive eligibility
- `analytics/factor_engine.py`: three-factor AEI inputs
- `analytics/economic_validation.py`: aligned EVG construction
- `analytics/borrower_strain_engine.py`: borrower strain
- `analytics/lender_strain_engine.py`: bank/nonbank financing strain
- `analytics/macro_interpretation.py`: deterministic Snapshot state engine and domain coverage contract
- `archive/archive.py`: atomic archive persistence
- `helpers/macro_dashboard.py`: shared macro, finance, sector, and evidence render components
- `helpers/render_ai_macro.py`: AI Macro tab orchestration
- `helpers/render_finance.py`: Finance tab orchestration
- `helpers/render_sectors.py`: consolidated sector overview and dropdown-selected detail
- `helpers/render_evidence.py`: purpose, definitions, and raw-source evidence

## Borrower Strain historical backfill

Borrower Strain history is retained separately from the live macro archive. The
maintenance build uses annual point-in-time observations from 2014 through 2024,
then quarterly observations through June 13, 2026.

```bash
python -m pip install -r requirements-backfill.txt
python tools/backfill_borrower_strain.py
```

The command uses SEC CompanyFacts for core financials and original SEC filings
for commitment disclosures. It writes a review ledger and accepts only explicit,
high-confidence obligation values automatically. See
`data_notes/borrower_strain_history_backfill.md` for methodology and review rules.

### Benchmark loading policy

The active QQQ proxy follows the same session boundary as the market universe but uses its own archive. During market hours, the first build without a current-date compatible benchmark row performs a live benchmark pull. After the close and on weekends, the latest compatible row in `archive/benchmark_history.csv` is used. **Refresh YFinance** explicitly refreshes both the 168-ticker universe and the active benchmark proxy.
