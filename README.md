# AI Economic Research Platform

## Purpose

Measure whether AI-related market enthusiasm is supported by observable economic development, corporate financial performance, and resilient financing conditions.

Identify divergences, constraints, and financial pressures that may increase vulnerability to market corrections using publicly available market, company-filing, construction, power, and Federal Reserve data.

The dashboard is a personal analytical system, not a trading platform. It describes observable conditions and does not claim to predict the date or proximity of a market correction.

## Dashboard structure

The research interface is organized into five primary tabs:

- **AI Macro:** equity conditions, development intensity, power stress, concentration, and gap metrics
- **Finance:** deployment funding, public corporate-bond market functioning, Borrower Strain, Lender Strain, and NFCI/ANFCI confirmation
- **Energy:** fuel supply, power production, grid capacity, and AI-linked electricity demand
- **Sectors:** sector assessment, positioning, rotation, the consolidated sector table, and dropdown-selected sector detail
- **Evidence:** purpose, metric definitions, FRED observations, and EDGAR company data

The tab reorganization does not change metric definitions, calculations, gauges, histories, component charts, or the dashboard color system.

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
- **U.S. Census Bureau:** private data-center construction spending

## Headline framework

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

### Concentration HHI

HHI measures market-cap concentration within the selected AI universe. Higher readings mean a greater share of market value is concentrated in fewer companies.

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
- Energy performs one automatic public-source pull per completed week. A completed-week archive blocks repeated requests; manual Energy refreshes remain independent.
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
- `research_overlay/renderers.py`: five-tab research interface orchestration
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
- `loaders/edgar_loader.py`: EDGAR data quality and archive eligibility
- `analytics/factor_engine.py`: three-factor AEI inputs
- `analytics/economic_validation.py`: aligned EVG construction
- `analytics/borrower_strain_engine.py`: borrower strain
- `analytics/lender_strain_engine.py`: bank/nonbank financing strain
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
