# Capital Stress Historical Backfill

## Feasibility

A like-for-like Capital Stress history can reasonably be reconstructed to 2014, but Yahoo Finance alone is not sufficient.

- The project's retained Yahoo archive begins in June 2026.
- Yahoo/yfinance generally exposes only a small recent window of annual financial statements.
- SEC structured financial-statement and notes data extends back to 2009.

## Recommended source hierarchy

1. **SEC face-financial XBRL data** for revenue, operating cash flow, capital expenditure, debt, cash, and EBITDA-compatible operating fields.
2. **SEC notes data and original filings** for uncommenced leases, purchase or contractual commitments, guarantees, and contingent obligations.
3. **Yahoo Finance only as a current-period cross-check**, not as the historical source of record.

## Validity requirements

- Use filing dates, rather than fiscal-period dates, to prevent look-ahead bias.
- Preserve missing note disclosures as unknown, never zero.
- Reconstruct the commitment ledger by filing period.
- Define the historical company cohort explicitly. A fixed present-day cohort introduces survivor and selection bias; an as-of-date cohort is preferable when historical universe membership is available.
- Retain the existing three-of-four component rule and publish historical coverage with each observation.

## Practical sequence

1. Backfill Cash Flow Strain and Book Leverage from SEC XBRL.
2. Build a semi-automated historical note-disclosure ledger for Committed Burden and Contingent Exposure.
3. Recalculate Capital Stress on filing release dates and append it as a step series.
4. Review extracted note values against the original filings before accepting each annual batch.
