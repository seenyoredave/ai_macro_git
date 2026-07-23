# AI Regime Dashboard

## Project statement

This project uses reproducible public data to distinguish observable AI-driven economic buildout from AI-driven capital speculation. It is a personal analytical dashboard—not a trading platform—and does not prescribe investment actions.

The model deliberately balances accuracy, precision, availability, and reliability. It uses static, explicit weights and defined minimum-data rules rather than dynamic weighting or subjective estimates.

## Core questions

- How strong and extended is the public-equity regime across the selected AI basket?
- Is observable physical and capital development keeping pace with equity enthusiasm?
- Is electricity demand beginning to pressure generation and grid capacity?
- Is the buildout creating material cash-flow, leverage, commitment, or contingent-obligation stress?
- Which sectors are strong, crowded, accelerating, or financially strained?

## Objective data sources

- **YFinance:** market prices, valuation, market capitalization, company fundamentals, price history, and volume history.
- **SEC filings / EDGAR:** standardized financial facts and a curated commitment ledger backed by filing disclosures.
- **FRED:** macroeconomic, financial-conditions, industrial-production, and electric-power series.
- **U.S. Census Bureau:** monthly private data-center construction spending.

Press releases and announcement-based project estimates are intentionally excluded from the scoring engines.

## Headline metrics

### AI Equity Index (AEI)

AEI is the equal-weighted mean of valid sector equity scores. At least 75% of configured sectors must have a valid score.

Each sector score uses four equal-weighted factors and requires at least three:

1. Relative performance versus the benchmark proxy
2. Earnings-yield discount versus the benchmark proxy
3. Momentum breadth
4. Return dispersion

Scale: **0–100**

- Weak: below 30
- Neutral: 30–59
- Strong: 60–79
- Extended: 80+

AEI describes the equity-market regime. It does not claim to measure physical economic development.

### AI Development Intensity (ADI)

ADI measures observable physical and capital buildout. It uses four equal-weighted pillars and requires at least three:

1. Capital Deployment
2. Data Center Construction
3. Compute Supply Realization
4. Power Footprint

Valid weights are renormalized when the 3-of-4 rule is met. Missing values are never treated as zero.

Scale: **0–100**

### Speculation Gap

`Speculation Gap = AEI - ADI`

- Positive: equity enthusiasm is running ahead of observable development.
- Negative: observable development is running ahead of the equity regime.

Scale: **-100 to +100**

### Power Stress Index

Power Stress combines:

- Commercial electricity-sales growth minus residential growth: 40%
- Electric-power capacity utilization: 35%
- Electric-power output growth minus capacity growth: 25%

At least two of three components must be valid. It is a national proxy for nonresidential load pressure and grid headroom; it does not perfectly isolate data-center demand. Because the official source series are monthly, its history is expected to move in steps rather than drift every day.

Scale: **-100 to +100**, centered at **0**

- Negative: below-reference system stress
- Zero: reference conditions
- Positive: above-reference system stress

### Capital Stress

Capital Stress combines:

- Cash Flow Strain: 30%
- Book Leverage: 25%
- Committed Burden: 30%
- Contingent Exposure: 15%

At least three of four components must be valid. Standardized fundamentals are combined with a filing-backed commitment ledger covering qualifying companies in the existing AI universe. Missing disclosure remains unknown rather than becoming zero. The four components are filing- and fundamental-driven, so Capital Stress is expected to remain flat between source updates and then change in steps. Daily motion is intentionally not manufactured from equity prices.

The current filing-screened cohort is **MSFT, AMZN, GOOG, META, ORCL, NVDA, AMD, IREN, SMCI, and ANET**. Inclusion requires disclosed unrecognized, contractual, or contingent obligations above 50% of reported debt; ordinary recognized lease liabilities are excluded from the commitment ledger to reduce double counting.

Scale: **-100 to +100**, centered at **0**

- Negative: below-reference capital stress
- Zero: reference conditions
- Positive: above-reference capital stress

### Concentration HHI

HHI is calculated from total company market capitalization within the selected AI universe. It measures concentration among selected companies and does not attempt to isolate AI-attributable enterprise value.

Higher values mean greater concentration.

## History-chart scaling

Headline gauges retain their full theoretical scales. Historical plots use a bounded adaptive vertical window with a minimum 20-point span so genuine movement in a short archive is visible without implying that a small change occupies the entire scale. Power Stress and Capital Stress are drawn as step series because their underlying official or filing data update discretely.

## Sector Trading Pressure

Pressure is intentionally separate from AEI. It measures trading extension and instability using:

- Valuation Stretch: 25%
- Price Extension above the 200-day average: 25%
- Momentum Acceleration: 20%
- Realized-Volatility Expansion: 15%
- Abnormal Volume Activity: 15%

At least three of five components must be valid. Ticker-level market inputs are aggregated by sector median.

## Benchmark

The active benchmark is a static ten-member QQQ top-holdings proxy. The selected holdings represented 45.95% of QQQ in the retained 2026-07-21 snapshot. Their actual QQQ weight ratios are normalized to 100% inside the proxy rather than equal-weighted.

Weighted benchmark return and beta use the normalized holdings weights. Benchmark valuation is calculated through weighted earnings yield and converted back to an equivalent forward P/E for the existing factor contract. QQQ is the only active runtime benchmark; SPY and DIA remain configured for possible future use but are not downloaded or archived by the current page.
