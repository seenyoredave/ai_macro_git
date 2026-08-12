# Presentation architecture

This document is the presentation contract for AI Macro. It governs hierarchy and composition without changing analytical calculations, retained data, or the Streamlit/Plotly width architecture.

## Core grammar

**Lifecycle outside; proof inside.**

Across domains, the platform traces synthesis, capital formation, physical buildout, resource constraints, adoption, realized outcomes, and verification. Inside a domain, the reader should be able to answer:

1. **Read** — What matters here?
2. **State** — What is true now?
3. **Motion** — What is changing?
4. **Structure** — Who, where, or what dominates?
5. **Transmission** — What converts, validates, or constrains it?
6. **Records** — Can I inspect the underlying observations?

These are analytical questions, not six mandatory boxes.

**Briefing first; workbench second.** The top of a tab should establish the argument quickly: domain Read, current-state readings, and a dominant signature object. Deeper structural analysis, alternate views, dossiers, and records follow below.

## Surface vocabulary

- **Instrument board** — reserved for genuine indexed conditions with scale, history, reference point, and interpretation.
- **Reading rail** — three to five current observations in one shallow horizontal strip.
- **Signature canvas** — one dominant analytical object per domain.
- **Paired view** — two graphics only when they directly answer the same question.
- **Small multiples** — three or more genuinely comparable measures.
- **Dossier** — one selected company, campus, state, sector, or project.
- **Bridge / process screen** — conversion, sequence, or transmission.
- **Workbench** — one analytical object with controls embedded inside it; only the active view renders.
- **Ledger** — one bottom-of-page disclosure with selectable underlying tables.

The old chart-plus-right-side metric stack is an exception, not a default. It is permitted only when the sidecar materially interprets the adjacent graphic.

These surface names are **internal design vocabulary**. They should not automatically appear in reader-facing titles or subtitles. Public copy follows `docs/EDITORIAL_STYLE.md` and should name the actual measure, comparison, place, or process in ordinary language.

## Space-efficiency contract

Large accidental voids are presentation failures.

- A narrow object must not sit alone inside a full-width chapter container.
- Shallow multi-stage summaries and pathways are horizontal-first on desktop; the Grid connection summary uses five native Streamlit columns so runtime geometry does not depend on markdown/CSS grid behavior.
- A vertical rail is acceptable only when it is meaningfully paired with an adjacent analytical object.
- If a section claims full-width page real estate, the analytical content should use that width.
- Alternate views should render lazily; do not eagerly initialize hidden charts to fill space.
- Controls live inside the analytical object they affect.
- Chart height remains content-driven.

## Protected references

- AI Macro composition and Regime Board.
- Buildout Leadership Rotation and the national project map.
- Economic Outcomes Value Realization Bridge.
- Campus and sector dossiers where already established.
- Signature maps and matrices.
- Streamlit ownership of Plotly width through `width="stretch"`.
- Active-domain rendering only; hidden domains do not initialize their Plotly charts.

## Domain hierarchy

- **Market:** state → ownership / concentration / contribution / participation → positioning → sector dossier → constituent ledger.
- **Finance:** funding-capacity instrument board → commercial realization → private-capital realization → credit conditions → financial strain → ledger.
- **Compute:** manufacturing trajectory hero → capacity and demand → serving economics → critical supply-chain structure → domestic buildout → ledger.
- **Data Centers:** pulse → Pipeline Explorer → geographic concentration → connectivity / operator structure → project ledger.
- **Connectivity:** pulse → Gateway Map → interconnection depth → terrestrial expansion → compute / transport mismatch → one connectivity ledger.
- **Power:** demand → supply response → generation buildout → price / fuel consequences → ledger.
- **Grid & Storage:** grid connection conditions → queue outcomes → reliability / storage → regional queue conditions → grid construction spending.
- **Water:** exposure state → Campus Water Dossier → Evidence Ladder → broader water-system workbench.
- **Adoption:** diffusion state → unified People / Business trajectory → paid-adoption validation → industry breadth → ledger.
- **Workforce:** Outcomes Matrix hero → workforce pulse → coordinated employment / labor-flow / compensation / exposure workbench → ledger.
- **Economic Outcomes:** protected Value Realization Bridge → national outcomes history → paired distribution of gains → investment validation → production context → ledger.
- **Evidence:** preserve the existing cleanup; source-lineage and stronger search/filter behavior remain future work.

## Rendering non-negotiable

Streamlit remains the sole owner of responsive Plotly width. Do not add Plotly `layout.width`, CSS sizing on Plotly descendants, or eager hidden-tab rendering. Presentation work must build on the repaired `width="stretch"` contract, never around it.
