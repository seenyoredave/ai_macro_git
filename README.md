# AI Macro

AI Macro is a Streamlit research platform for tracking the U.S. AI economy from capital investment and physical buildout through adoption, labor markets, and broader economic outcomes. It brings public market, company, infrastructure, labor, and government data into one place.

## Coverage

- Market and Finance
- Compute, Data Centers, and Connectivity
- Power, Grid & Storage, and Water
- Adoption and Workforce
- Economic Outcomes
- Evidence

## Access

The deployed application runs in **Reader mode**. Users can explore the research and underlying data, but they cannot refresh sources, write files, or modify the project.

**Developer mode** is restricted to the owner and contains the refresh, diagnostic, and maintenance controls.

## Runtime

AI Macro requires Python 3.11 or newer. Release artifacts for this version were produced from a Python 3.13 development environment. `requirements.txt` contains the application runtime; `requirements-dev.txt` adds local browser-contract tooling.

## Commentary

AI Macro separates deterministic research from probabilistic interpretation. Retained data and local analytics build bounded evidence packets; OpenAI generates grounded analytical domain Reads and a cross-domain Macro synthesis; a deterministic validator decides whether the result may be published. Reader sessions never call OpenAI.

Commentary is generated from bounded evidence packets and published only after deterministic validation. If validated commentary is unavailable, the underlying dashboard data remain available.


## Automation

The hosted Reader remains read-only. A single scheduled GitHub Actions worker may refresh retained research, update Current Context, generate commentary when analytical evidence changes, and publish only after deterministic validation passes. Paid automation is bounded by hard call ceilings and has no automatic API retry loop.

## Data

Reader mode uses retained data. Definitions, source coverage, and provenance are available in the **Evidence** tab.

## Current Context evidence resolution

Discovery nominates events, not mandatory article URLs. The discovered evidence source is tried first; when it is inaccessible for a non-disqualifying reason, the canonical Current Context engine may research the same event through another policy-eligible source. Alternate evidence must pass the same source-body grounding contract and preserves discovery-to-evidence lineage.
