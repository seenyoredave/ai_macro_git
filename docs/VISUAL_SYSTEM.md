# AI Macro visual system

## Purpose

The visual system exists to make thirteen domains feel like one research platform without stripping away the tools that make individual tabs memorable. It governs the presentation shell; it does not force unlike analytical questions into the same chart.

The governing rule is **70 / 20 / 10**:

- **70% shared platform grammar:** headers, Read placement, spacing, chart shell, controls, metadata, legends, tables, empty states, and responsive behavior.
- **20% domain adoption:** the shared components may emphasize the measures and evidence conventions appropriate to a domain.
- **10% signature experience:** each domain owns one or two memorable tools whose form is justified by the analytical question.

## Protected signature tools

Two AI Macro surfaces are explicitly protected:

1. **Buildout Leadership Rotation** — the time-varying capital-flow view across compute manufacturing, data centers, communications, power, and water systems.
2. **National Landscape Map** — the facility-geography explorer with linked capacity, power, water, and evidence layers.

They may inherit platform typography, spacing, controls, metadata, legends, accessibility treatment, and responsive rules. Their analytical form and availability must not be removed during standardization.

## Signature registry

The registry distinguishes **current** signature tools from **planned** signatures that will be built during the B-to-A domain work. Phase 0 does not relabel an ordinary chart as a finished signature experience. Workforce's outcomes matrix, Economic Outcomes' realized-value transmission ladder, and Evidence's claim-to-source lineage explorer are declared as planned surfaces rather than treated as already complete.

Current signatures include the Market sector dossier and ownership view, Finance private-capital realization map, Compute critical-supply-chain view, Data Centers pipeline explorer, Connectivity gateway map, Power demand profile, Grid queue screen, Water evidence ladder, and Adoption diffusion history.

## Shared grammar

Every analytical tab follows this order unless the domain has a documented reason to diverge:

1. Domain-stage header
2. Purpose sentence and source family
3. Terms access
4. Domain Read
5. Current-state or regime metrics
6. Primary analytical section
7. Signature tool
8. Supporting views and detail tables
9. Evidence and limitations

The same analytical job should ordinarily use the same visual form:

| Analytical job | Default form |
|---|---|
| Change over time | Line or indexed line |
| Ranking | Horizontal bars |
| Composition | Stacked bars |
| Development stages | Stage or pipeline bars |
| Geography | Map |
| Relationship or mismatch | Scatterplot or paired bars |
| Coverage or confidence | Coverage bar, matrix, or evidence ladder |
| Detailed records | Searchable table |

A different form is welcome when it improves comprehension. Novelty by itself is not an analytical reason.

### Evidence surface

Evidence uses a reader-first hierarchy rather than exposing the technical warehouse by default:

1. published interpretation;
2. cited analytical facts;
3. source foundation and scope limits;
4. separately sourced Current Context, when present;
5. collapsed technical records for formulas, lineage, source registers, and raw observations.

The Evidence page is an audit trail, not a second dashboard. Do not add decorative charts merely to make the surface look richer.

## Semantic conventions

- Violet: capital, synthesis, or platform emphasis
- Blue: physical buildout and transport
- Amber: resource constraints and delivery risk
- Green: adoption and realized outcomes
- Slate: neutral context, methodology, and unavailable evidence
- Red: adverse condition or negative exception, not decoration

Observed, estimated, announced, retained, partial, fallback, and inferred values remain textually labeled. Color never carries that distinction alone.

## Chart contract

All Plotly surfaces render through `rendering.visual_system.render_plotly_chart`. The wrapper standardizes typography, backgrounds, hover treatment, legend text, responsive configuration, state persistence, and accessible descriptions for registered signature tools. It deliberately preserves chart type, annotations, axis ranges, map projection, and domain-specific encodings.

`rendering.charts_common._base_layout` remains the reference figure shell. Domain chart modules may change margins and heights when labels or geography require it, but should not define an independent visual theme.

## Governance

- `config.visual_design` owns domain profiles, stage families, signature tools, and protected status.
- `data/visual_surface_inventory.csv` records the current chart, selector, and interactive-table footprint.
- Visual changes are verified in the running application. Protected signature tools and shared Plotly ownership remain design rules, not executable release gates.
- Phase-specific redesigns must update the visual inventory and explain any new signature surface.
