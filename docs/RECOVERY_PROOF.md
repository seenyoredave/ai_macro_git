# v6.9.1 Recovery Proof

This branch starts from the untouched `v6.9.1_phase2_import_repair` package. It is a deliberately narrow recovery proof, not a release candidate.

## Scope

Two representative analytical surfaces were changed:

- **Full-width:** Data Centers → Geographic pattern. Summary metrics are above the chart; the chart remains in the page container and is not placed in a narrow sibling column.
- **Compact with rail:** Water → National water claims. The chart receives roughly 72% of desktop width, metrics form one vertical rail, and the rail moves above the chart below 900 px.

No analytical calculation, retained dataset, selector option, chart definition, or historical window was intentionally changed.

## Independent checks

```bash
python helpers/recovery_baseline_audit.py
python helpers/layout_recovery_smoke_test.py
python helpers/browser_layout_contract.py
```

The browser contract launches real Chromium and measures the shared HTML/CSS primitives at 1280, 1600, 1920, 2560, and 768 pixels. It checks chart-width ratios, compact column proportions, narrow-screen ordering, and card overflow.

## Important limitation

The current audit environment does not contain the declared Streamlit runtime and cannot install it from a package index. Therefore the included Chromium screenshots verify the shared layout primitive, **not the complete Streamlit application**. Full-app screenshots, selector traversal, DOM measurement, startup network tracing, and startup write tracing remain release gates.

## Baseline finding

The retained Finance NFCI/ANFCI archive does not satisfy the promised ten-year confirmation window. This proof records that failure but does not repair it, keeping layout and data work in separate patches.


## v6.10.21 Current Context Finance gate recovery

Finance gate tracing now preserves vetted rows across engine-version changes, upserts rediscovered event IDs, uses browser-profile publisher HTML retrieval, recognizes quantified financing transactions already in motion, and adds a named-borrower capital-markets discovery query. Evidence thresholds remain unchanged.

## v6.10.22 event-level evidence resolution

Current Context no longer allows one inaccessible discovered URL to veto a material event. The single canonical discovery engine tries the nominated source first, then performs a bounded same-event evidence lookup across eligible sources when transport/access—not substantive disqualification—caused the failure. Alternate sources must match the event and pass the identical source-body grounding gates. Discovery identity and evidence lineage are preserved; headline-derived fallback remains prohibited.

## v6.10.23 materiality-first Current Context

Current Context now evaluates development-level salience before final fact extraction. A recent article cannot donate an old historical statistic as the anchor development merely because the number matches a domain vocabulary. Market additionally separates AI relevance from Market significance: company-specific AI news needs broad market/sector read-through, a systemically important issuer, a major public-market repricing, or a major transaction before it can occupy a Market slot. Reader prose is separated from selector rationale; qualification/ranking reasons remain audit-only and canned "why this qualifies" language is prohibited from Recent Developments.
