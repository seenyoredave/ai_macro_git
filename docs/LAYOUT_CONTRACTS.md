# Analytical layout contracts

The public application supports two analytical section layouts. A section is
classified deliberately; moving metric cards to the right is never a blanket
operation.

## Full-width analytical section

Use when the chart needs horizontal room or visual prominence: dense time
series, maps, heatmaps, wide rankings, multi-series comparisons, and signature
tools.

- Metric cards appear above the chart.
- The chart renders directly in the full content container.
- No empty sibling column may reserve width.
- The chart should occupy at least 90% of the available section width.

Reference surface: Finance — Corporate bond market history.

## Compact chart with metric rail

Use only when the plot remains readable at partial width: short rankings,
limited-category comparisons, and simple summary charts.

- Chart on the left; one vertical metric stack on the right.
- Desktop chart share is 65–75% of the two-column content width.
- Chart panel and complete metric stack have the same total height.
- Rail cards divide the available height evenly.
- Card content stays in normal top-down flow; notes are never bottom-pinned.
- Visible space remains beneath every footnote; the browser contract requires
  at least 12 CSS pixels.
- Labels, values, and notes wrap without clipping or horizontal overflow.
- At 900 px and below, the rail moves above the chart and cards return to
  natural content-driven height.

Reference surface: Water — National water claims.

## Disallowed patterns

- A chart compressed merely because cards exist.
- A narrow rail that creates portrait-shaped cards and excessive wrapping.
- Metric grids embedded inside a side panel.
- Fixed card heights that clip text.
- `margin-top: auto`, `justify-content: space-between`, or equivalent rules
  that pin footnotes to the bottom edge.
- Treating source-code presence or mocked Streamlit calls as visual proof.

## Verification

The shared browser contract checks 1280, 1600, 1920, 2560, and 768 px. Full
application completion still requires screenshots and DOM measurements from a
real Streamlit session for every classified surface and selector branch.
