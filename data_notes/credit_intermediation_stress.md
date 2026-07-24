# Credit Intermediation Stress

## Purpose

Credit Intermediation Stress measures the condition of the financing channel. It is intentionally separate from Capital Stress, which measures the condition of the borrowers.

## Headline construction

- Bank Credit Tightening: 30%
- Bank Capital Strain: 25%
- Private Credit Impairment: 25%
- PE Portfolio Financing Strain: 20%

At least three of four pillars must be valid. Available fixed weights are renormalized only after that rule is met. Internal 0–100 scores are displayed on the dashboard's centered -100 to +100 scale.

## Public input ledgers

### `data/bank_credit_tightening_history.csv`

Federal Reserve SLOOS series `SUBLPDMBSXWBNQ`: net percentage of domestic banks tightening standards on business loans, weighted by outstanding loan balances. The live FRED payload overrides the bundled observation when a newer value is available.

### `data/bank_tier1_capital_history.csv`

Federal Reserve Z.1 series `BOGZ1FL010000016Q`: aggregate regulatory Tier 1 capital as a percentage of risk-weighted assets. Higher capital ratios reduce the stress score. The live FRED payload overrides the bundled observation when a newer value is available.

### `data/private_credit_bdc_history.csv`

Quarterly non-accrual investments at amortized cost and total portfolio cost for the fixed public BDC cohort:

- ARCC
- OBDC
- FSK
- GBDC
- CION

The engine calculates an asset-weighted cohort ratio. Each row retains its public source URL. Update this ledger after the cohort's quarterly filings or earnings exhibits are available.

### `data/private_equity_stress_history.csv`

Annual SEC Form PF aggregate statistics:

- portfolio-company gross assets by debt-to-equity bucket;
- mean payment-in-kind borrowing as a percentage of portfolio-company borrowing.

High-leverage share includes negative-equity portfolio companies and debt-to-equity buckets of 2–5 and 5+. Form PF is structurally lagged, so the dashboard always displays its as-of date.

## Reference mappings

- Bank tightening: neutral at 0%, scale 35 percentage points.
- Bank Tier 1 capital: neutral at 12.5%, scale 4 percentage points; scoring is inverted so lower capital means higher stress.
- BDC non-accruals at cost: neutral at 2%, scale 2.5 percentage points.
- PE high-leverage share: neutral at 30%, scale 12 percentage points.
- PE PIK burden: neutral at 18%, scale 10 percentage points.

The mappings use the same bounded hyperbolic-tangent scoring helper as other dashboard engines. They are transparent reference mappings, not forecasts or regulatory thresholds.
