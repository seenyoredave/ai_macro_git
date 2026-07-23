# Final revision audit

## History plots

The headline gauges retain their full theoretical scales. Their adjacent history plots use a bounded adaptive vertical window with a minimum 20-point span. This makes movement visible without letting a tiny change occupy the entire chart.

The retained archive contains:

- AI Equity Index: 27 observations, 24 distinct values
- AI Development Intensity: 20 observations, 10 distinct values
- Power Stress Index: 27 observations, 3 distinct monthly values
- Concentration HHI: 27 observations, 22 distinct values
- Capital Stress: 8 observations, 1 distinct value

Power Stress is rendered as a step series because its official inputs update monthly.

Capital Stress is also rendered as a step series. Its current components use filing and fundamental data rather than daily market prices. In the retained archive, the valid cash-flow, leverage, commitment, and contingent-exposure inputs are identical across all eight supported dates. The resulting flat history is therefore mathematically correct. The chart explicitly identifies this condition rather than manufacturing daily variation.

## Data integrity

Running `python tools/rebuild_derived_history.py` repeatedly produces byte-identical derived archives. The retained YFinance, EDGAR, and benchmark archives are unchanged by the rebuild.
