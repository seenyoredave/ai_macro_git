# Recovery Proof Final Checks

- Baseline commit: `ddc273b`
- Recovery commit: `3615ff7e4641a9d38daeb39cbf28d5e2d2a79d02`
- Branch: `recovery/v6.9.1-stabilization`
- Working tree after verification: **clean**

## Passing checks

- Python source compilation: **177 files**
- Packaged smoke tests: **20/20 passed**
- Retained CSV inventory: **98 files**
- Shared layout source contract: **passed**
- Real Chromium shared-layout contract: **passed at 1280, 1600, 1920, 2560, and 768 px**
- Git whitespace/error check: **passed**

## Browser measurements

- Full-width chart ratio: **95.4%–98.6%** of the proof wrapper, above the 90% gate.
- Desktop compact chart share: **71.7%**, inside the 65%–75% gate.
- Narrow compact behavior: metric rail is above the chart; both occupy full width.
- Summary cards: no measured vertical overflow, horizontal overflow, or child-boundary violations.

## Failed or blocked contracts

- Finance NFCI retained history: **failed** — 5 valid observations across 21 days.
- Finance ANFCI retained history: **failed** — 1 valid observation.
- Full Streamlit application browser pass: **blocked in this environment** because Streamlit is not installed and the package index is unavailable.
- Startup network/write behavior: **not promoted to verified**; current findings are static source observations only.

The included screenshots prove the shared HTML/CSS layout primitive, not the complete Streamlit application.
