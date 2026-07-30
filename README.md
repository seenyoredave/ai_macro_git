# AI Economic Research Platform

## Purpose

Measure whether AI-related market enthusiasm is supported by observable economic development, corporate financial performance, and resilient financing conditions.

Identify divergences, constraints, and financial pressures that may increase vulnerability to market corrections using publicly available market, company-filing, construction, power, and Federal Reserve data.

The dashboard is a personal analytical system, not a trading platform. It describes observable conditions and does not claim to predict the date or proximity of a market correction.

## Dashboard structure

The research interface is organized into four primary tabs:

- **AI Macro:** equity conditions, development intensity, power stress, concentration, and gap metrics
- **Finance:** deployment funding, Borrower Strain, Lender Strain, and NFCI confirmation with ANFCI context
- **Sectors:** sector assessment, positioning, rotation, the consolidated sector table, and dropdown-selected sector detail
- **Evidence:** purpose, metric definitions, FRED observations, and EDGAR company data

The tab reorganization does not change metric definitions, calculations, gauges, histories, component charts, or the dashboard color system.

## Design principles

- Public and reviewable source data
- Static, explicit weights
- Defined minimum-data requirements
- Missing values remain missing rather than becoming zero
- Versioned definitions to prevent silent blending with legacy calculations
- No press-release project estimates inside scoring engines
- No numerical confidence scores for subjective information

## Primary data sources

- **YFinance:** prices, market capitalization, enterprise-value inputs, analyst revenue estimates, company statements, and price/volume history. Current pulls take precedence; archive rows fill only failed tickers or missing fields.
- **SEC / EDGAR:** standardized financial facts, filing-backed commitment disclosures, public BDC credit quality, and Form PF aggregates
- **FRED:** macroeconomic, bank, industrial-production, financial-conditions, information-investment, and power series
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

CIS measures deterioration in financing-system behavior and capacity through two equally weighted channels.

**Bank Channel: 50%**

- Bank Credit Tightening
- Bank Capital Strain

**Nonbank Channel: 50%**

- Public BDC Private Credit Impairment
- PE Portfolio Financing Strain

The headline requires at least three of four pillars and at least one valid pillar from each channel. Missing weights are renormalized inside the affected channel only. Each pillar uses its own historical normalization when enough observations exist and an explicit anchored scale before then.

Scale: **-100 to +100**, centered at 0

### Financial Conditions Confirmation

The Chicago Fed National Financial Conditions Index is shown directly as an independent weekly confirmation signal.

- Negative NFCI: conditions looser than the long-run average
- Positive NFCI: conditions tighter than the long-run average
- Three-month change: current direction of travel

NFCI is not blended into Borrower Strain or Lender Strain. ANFCI is shown only as a dashed comparator in the same financial-conditions plot and is not promoted to a separate dashboard product.

### Concentration HHI

HHI measures market-cap concentration within the selected AI universe. Higher readings mean a greater share of market value is concentrated in fewer companies.

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
- Market-sensitive YFinance products attempt a live pull every 15-minute cache cycle; a same-day archive never blocks that pull.
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

See `data_notes/borrower_financial_condition_history_backfill.md`.

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

Run the regression suite from the project root:

```bash
PYTHONPATH=. python -m unittest discover -s tests -v
```

## Architecture

- `ai_macro.py`: sole Streamlit execution entry point and application data pipeline
- `research_overlay/renderers.py`: four-tab research interface orchestration
- `research_overlay/components.py`: reusable research UI components
- `research_overlay/visuals.py`: Plotly research figures
- `research_overlay/theme.py`: platform visual system
- `loaders/market_prices.py`: price-history calculations
- `loaders/company_fundamentals.py`: statement parsing and company financial calculations
- `loaders/market_loader.py`: live-first market orchestration, retry logic, and complete-universe archive fallback
- `loaders/market_freshness.py`: pure live/archive reconciliation and runtime source diagnostics
- `loaders/fred_loader.py`: macro and power data
- `loaders/nfci_loader.py`: isolated NFCI history and fallback chain
- `loaders/edgar_loader.py`: EDGAR data quality and archive eligibility
- `analytics/factor_engine.py`: three-factor AEI inputs
- `analytics/economic_validation.py`: aligned EVG construction
- `analytics/borrower_financial_condition_engine.py`: borrower financial condition
- `analytics/intermediation_strain_engine.py`: bank/nonbank financing strain
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
python tools/backfill_borrower_financial_condition.py
```

The command uses SEC CompanyFacts for core financials and original SEC filings
for commitment disclosures. It writes a review ledger and accepts only explicit,
high-confidence obligation values automatically. See
`data_notes/borrower_financial_condition_history_backfill.md` for methodology and review rules.
