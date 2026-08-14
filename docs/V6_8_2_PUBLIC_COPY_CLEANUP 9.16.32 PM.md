# v6.8.2 Public-interface copy cleanup

## Purpose

Public analytical pages should speak to readers, not to the people maintaining the application. This patch removes implementation commentary from the visible interface while preserving concise source, scope, and uncertainty disclosures.

## Changes

- Removed the developer-style note beneath the Adoption Read.
- Removed the implementation summary beneath the Workforce Read.
- Rewrote public captions that referred to retained archives, parser behavior, manual refreshes, source modes, or platform implementation choices.
- Removed Connectivity refresh diagnostics from the public Connectivity and Evidence tabs. Refresh diagnostics remain available through Developer Tools.
- Simplified the public water-source register to omit parser and ingestion fields.
- Added an AST-based public-copy smoke test to prevent implementation language from reappearing in reader-facing components.

## Preserved

- Universal divider after every Read.
- Analytical caveats and non-causality boundaries.
- Institutional source attribution.
- All Phase 1 data and signature tools.
- Buildout Leadership Rotation and National Landscape Map.
