# Model definitions

## Design principles

The dashboard uses objective public data, static explicit weights, reproducible calculations, and minimum-data rules. It avoids dynamic weighting, press-release estimates, and numerical confidence scores for subjective information.

All scores are analytical state measures rather than trading instructions.

## AI Equity Index

**Question:** How strong and extended is the selected AI equity universe?

`AEI = equal mean of valid sector AEI scores`

At least 75% of sectors must have valid scores.

Each sector AEI score uses equal 25% weights:

- Relative Performance
- Earnings-Yield Discount
- Momentum Breadth
- Dispersion

A sector score requires at least three of four factors. Missing factors are omitted and valid fixed weights are renormalized.

Scale: 0–100.

Regime labels:

- Weak: below 30
- Neutral: 30–59
- Strong: 60–79
- Extended: 80+

## AI Development Intensity

**Question:** How intense is the observable physical and capital AI buildout?

ADI uses four equal-weighted pillars and requires at least three:

### Capital Deployment

- Aggregate CapEx Growth: 60%
- Aggregate CapEx / Operating Cash Flow: 40%

The company cohort is drawn from Cloud Hyperscalers, Data Center Infrastructure, and Power Grid sectors. Growth and intensity use ratio-of-sums calculations where the source data permits.

### Data Center Construction

- Census Data Center Construction YoY Growth: 70%
- Data Center Share of Private Nonresidential Construction: 30%

### Compute Supply Realization

- Aggregate Revenue Growth: 70%
- Revenue Growth Breadth: 30%

The cohort is drawn from Compute, Semiconductor Equipment, Data/AI Infrastructure, and Data Center Infrastructure.

### Power Footprint

- Commercial Electricity-Sales Growth: 60%
- Electric-Power Output Growth: 40%

Scale: 0–100.

## Speculation Gap

`Speculation Gap = AEI - ADI`

Positive values indicate equities are running ahead of observable development. Negative values indicate development is running ahead of equities.

Scale: -100 to +100.

## Sector Trading Pressure

**Question:** How extended, crowded, and unstable is current trading behavior?

- Valuation Stretch: 25%
- Price Extension above 200-day average: 25%
- Momentum Acceleration: 20%
- Volatility Expansion: 15%
- Volume Activity: 15%

A sector Pressure score requires at least three of five components. Price/volume inputs are aggregated by sector median.

Pressure v2 is versioned separately from the old pressure definition because it no longer reuses the AEI factor set.

## Power Stress Index

- Commercial-minus-Residential Electricity-Sales Growth: 40%
- Electric-Power Capacity Utilization: 35%
- Electric-Power Output Growth minus Capacity Growth: 25%

At least two of three components must be valid.

`Power Stress base = 0.40(NL) + 0.35(GU) + 0.25(CR)`

`Power Stress = 2 × (Power Stress base - 50)`

Scale: -100 to +100, centered at 0.

## Capital Stress

- Cash Flow Strain: 30%
- Book Leverage: 25%
- Committed Burden: 30%
- Contingent Exposure: 15%

`Capital Stress base = 0.30(CF) + 0.25(BL) + 0.30(CB) + 0.15(CE)`

`Capital Stress = 2 × (Capital Stress base - 50)`

At least three of four components must be valid. The internal base scale is 0–100; the displayed scale is -100 to +100, centered at the component reference points.

### Cash Flow Strain

- FCF Margin Strain: 60%
- Reinvestment Burden (CapEx / OCF): 40%

### Book Leverage

Aggregate Net Debt / EBITDA for the selected AI-company cohort.

### Committed Burden

Curated uncommenced leases plus purchase/contractual commitments divided by aggregate operating cash flow for matching disclosed companies.

### Contingent Exposure

Curated guarantees, backstops, and other quantified contingent obligations divided by aggregate operating cash flow for matching disclosed companies.

The commitment ledger is intentionally filing-backed and limited to companies in the existing AI universe whose disclosed unrecognized, contractual, or contingent obligations exceed 50% of reported debt. Missing categories are unknown, not zero.

## Credit Intermediation Stress

**Question:** Is the financing system becoming less willing or less able to support operating businesses?

- Bank Credit Tightening: 30%
- Bank Capital Strain: 25%
- Private Credit Impairment: 25%
- PE Portfolio Financing Strain: 20%

`Intermediation base = 0.30(BT) + 0.25(BC) + 0.25(PC) + 0.20(PE)`

`Credit Intermediation Stress = 2 × (Intermediation base - 50)`

At least three of four components must be valid. The internal base scale is 0–100; the displayed scale is -100 to +100.

### Bank Credit Tightening

Federal Reserve SLOOS net percentage of domestic banks tightening business-loan standards, weighted by banks' outstanding loan balances.

### Bank Capital Strain

Federal Reserve Z.1 aggregate regulatory Tier 1 capital as a percentage of risk-weighted assets. The score is inverted so lower capital ratios indicate greater strain.

### Private Credit Impairment

Asset-weighted non-accrual investments at amortized cost for the fixed public BDC cohort ARCC, OBDC, FSK, GBDC, and CION.

### PE Portfolio Financing Strain

- High-Leverage Portfolio Share: 60%
- Payment-in-Kind Borrowing Burden: 40%

High leverage is the share of reported portfolio-company gross assets with debt-to-equity of 2 or more or negative equity. Both inputs come from lagged annual SEC Form PF aggregates.

## Concentration HHI

Raw HHI is the sum of squared company market-cap shares across the selected AI universe. The dashboard converts raw HHI to a 0–100 display scale.

Higher values mean greater concentration. The calculation uses total company market capitalization and does not allocate enterprise value to AI activities.

## Financial Conditions Confirmation

The Chicago Fed National Financial Conditions Index is displayed directly as an independent weekly confirmation signal. Negative readings indicate conditions looser than the long-run average; positive readings indicate tighter conditions. The dashboard also reports the three-month change to distinguish the current level from its direction. NFCI is not blended into Capital Stress or Credit Intermediation Stress.

## Gap metrics

### Economic Validation Gap

Enterprise AI software CapEx growth minus company revenue growth minus broader information-processing investment growth. This remains a directional proxy rather than an accounting identity.

### AI–Industrial Growth Gap

ADI minus a normalized score for year-over-year broad industrial-production growth.

## Missing-data and archive rules

- Invalid or non-finite values remain missing.
- No calculation or renderer converts missing values to zero.
- Fixed weights are renormalized only after a metric's minimum-component rule is met.
- A headline metric may display its latest valid, version-compatible archived value when the current run is insufficient.
- Archive fallbacks are display continuity only and are never written as new current observations.
- New metric definitions carry explicit version columns to prevent silent blending with legacy histories.
