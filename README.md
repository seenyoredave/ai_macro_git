# AI Macro

The v9 Reader uses a compiled, integrity-checked 11-domain language layer supplied directly to OpenAI. See `docs/LANGUAGE_LAYER.md` for the production contract.

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

AI Macro separates deterministic research from probabilistic interpretation. Retained data and local analytics build bounded evidence packets; OpenAI generates all domain Reads in one call, then receives those completed Reads in a second call to write the cross-domain Macro synthesis. Reader sessions never call OpenAI.

The complete portable language layer is supplied to both calls. Returned prose is not rewritten locally. Deterministic checks attach diagnostics only; completed output publishes as `validated`, `published_with_warnings`, or `published_raw_response`. A published Read remains available for 24 hours and can be reapplied without an OpenAI call.


## Automation

The hosted Reader remains read-only. A single scheduled GitHub Actions worker runs at 09:07 Eastern on weekdays. It refreshes domain sources, then shared market sources, then Current Context before it makes one publication decision. Commentary is regenerated only when a curated evidence fact changes materially relative to the last generated Read; smaller changes accumulate against that baseline while the existing Read is renewed at zero API cost. Full generation is bounded to two calls, the SDK retry count is zero, and diagnostics never trigger a replacement call. Desktop-to-Git reconciliation preserves newer online retained state while keeping desktop code/configuration authoritative.

## Current Context

Current Context is an independently discovered, source-grounded news layer. It prefers the strongest developments from the most recent seven days, progressively relaxes source/materiality/anchor thresholds within a hard ten-day window until at least six analytical domains are represented, and exposes the qualification tier used for each refresh. The AI Macro Read surfaces the top three developments with diversity limits: no more than two from one domain and no more than two from Market and Finance combined.
Reader copy is reconstructed deterministically around a corroborated event nucleus: the resolved publisher title may frame the actor/action only when the fetched body confirms the same event, and one same-event body detail may follow within the 70-word ceiling.

## Data

Reader mode uses retained data. Definitions, source coverage, and provenance are available in the **Evidence** tab.

## Current Context evidence resolution

Discovery nominates events, not mandatory article URLs. The discovered evidence source is tried first; when it is inaccessible for a non-disqualifying reason, the canonical Current Context engine may research the same event through another policy-eligible source. Alternate evidence must pass the same source-body grounding contract and preserves discovery-to-evidence lineage.
