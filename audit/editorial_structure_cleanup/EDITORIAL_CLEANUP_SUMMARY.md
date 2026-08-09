# Editorial structure cleanup — 2026-08-09

This pass tightens public-facing language without changing analytical calculations or retained data.

## Changes

- Removed the separate AI Macro `Why it matters` / `What it means` layer. The Read now moves directly from the conclusion and explanation to compact evidence anchors.
- Removed the redundant `National AI development landscape` panel heading from AI Macro; the section is now titled `Project locations` once.
- Rewrote reader-facing headings and subtitles that began with Who / What / When / Where / Why / How / Whether.
- Replaced question-form headings with direct descriptive labels.
- Simplified Grid & Storage copy:
  - `Grid connection conditions` — queue size, project progress, reserve margins, battery duration, and grid construction spending.
  - `Queue outcomes` — historical completion, withdrawal, cancellation, and connection-time measures.
  - `Reliability and storage` — summer reserve margins and operating battery duration.
  - `Regional queue conditions` — queue size, median age, and target-year status by region.
- Simplified public copy across Market, Finance, Compute, Data Centers, Connectivity, Power, Water, Adoption, Workforce, and Economic Outcomes.
- Fixed missing punctuation in the generated Power Read.
- Added regression coverage for interrogative sentence starts and the retired macro relevance layer.
- Updated the editorial style guide with the declarative-heading rule.
- Removed temporary/cache artifacts before packaging, including `tmpsxkldbas` and `__pycache__` directories.

## Verification

See `verification.txt` for the clean regression log. It includes public-copy, Read, layout, rendering, retained-startup, integrity, and real-browser contracts.
