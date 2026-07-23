# Derived History Rebuild

## Purpose

The calculated archives were rebuilt from retained source observations after the metric definitions changed. Raw YFinance, EDGAR, and benchmark archives were not modified.

## Rebuilt calculations

| Metric | Rebuilt coverage | Inputs |
|---|---:|---|
| Sector AEI score | 275 sector observations | Archived company market/fundamental fields and benchmark observations |
| AI Equity Index | 27 macro observations, 2026-06-14 through 2026-07-21 | Rebuilt sector AEI scores |
| Concentration HHI | 27 macro observations | Archived company market capitalization |
| Signed Power Stress v3 | 27 macro observations | Official historical electricity-sales, electric-output, electric-capacity, and capacity-utilization series |
| AI Development Intensity | 20 macro observations beginning 2026-06-21 | Capital Deployment, Census Data-Center Construction, Compute-Supply Realization, and Power Footprint |
| Speculation Gap | 20 macro observations beginning 2026-06-21 | AEI minus ADI |
| Signed Capital Stress v2 | 8 macro observations beginning 2026-07-10 | Archived cash-flow/debt fields plus filing-dated commitment disclosures |

## Pressure limitation

Pressure v2 requires four raw market-history features:

- Price Extension 200D
- Momentum Acceleration
- Volatility Expansion
- Volume Activity

Those fields were not retained in the older YFinance archive, so Pressure v2 cannot be reconstructed honestly for those dates. The previous calculated series is retained only as `Legacy Pressure` and `Legacy Avg Sector Pressure`. It is not labeled or used as Pressure v2. Future YFinance snapshots archive the required raw fields.

## Source-date handling

- Historical market calculations use the latest archived market snapshot available on or before each macro archive date. `Market Data Date` records that source date.
- Power inputs use the latest complete official observation set available for the historical dashboard date.
- Data-center construction uses the historical Census observation and release mapping retained under `data/`.
- Capital Stress includes only commitment-ledger rows whose filing date was available by the historical dashboard date.

## Rebuild command

From the project root:

```bash
python tools/rebuild_derived_history.py
```

The script is deterministic and validates that the raw YFinance, EDGAR, and benchmark dataframes remain unchanged during execution.

## Preserved raw-archive hashes

These hashes match the prior delivered package:

- `archive/yf_history.csv`: `58b8673660a7e06d4d990cdfa26c7f43429cd0168144f04b614d2b8fb57c4503`
- `archive/edgar_history.csv`: `fdcbaf1623dbd753bb813cca6ff9db9546e20d45169e47cd5f59d6b9c5864719`
- `archive/benchmark_history.csv`: `2a95ee0962d566dc51ee1b96194becf0cc57f4131e99ff0116253ce885c24108`
