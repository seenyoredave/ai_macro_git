# Phase 0 visual audit

## Finding

AI Macro had a coherent palette and strong shared Read components, but its visualization shell had evolved unevenly. Most chart modules used the common Plotly base layout, while Connectivity carried a separate layout function and every renderer called Streamlit's Plotly API directly. Controls, bordered panels, and table surfaces inherited more of Streamlit's defaults than the research platform's own grammar.

The heterogeneity was therefore coming from two different places:

- **Useful heterogeneity:** maps, pipeline views, treemaps, evidence ladders, heatmaps, and other forms chosen for a real analytical purpose.
- **Accidental heterogeneity:** independent chart shells, inconsistent control framing, uneven panel rhythm, and no source-controlled declaration of which tools were meant to be distinctive.

## Phase 0 action

- Created thirteen domain visual profiles grouped into seven stage families.
- Declared one or two signature experiences per domain.
- Protected Buildout Leadership Rotation and the National Landscape Map.
- Routed every Plotly surface through one rendering contract.
- Moved Connectivity onto the shared chart shell without altering its maps or retained data.
- Added shared spacing, panel, control, table, chart, and responsive tokens.
- Added a static inventory of 125 charts, selectors, and interactive tables, including conditional views hidden behind selectors.
- Added regression tests for the visual contract.

## Deliberately deferred

Phase 0 does not redesign substantive tools, change datasets, remove charts, or force every tab into the same sequence of visual forms. The B-to-A domain work will decide which supporting surfaces should be consolidated after the stronger analytical contracts are built.
