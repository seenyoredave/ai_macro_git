# Bot Rules

1. No bot may create any `.md` file without the owner's express permission.
2. No bot may produce release reports, status reports, checkpoint reports, handoff documents, audit summaries, manifests, or similar project-management artifacts without the owner's express permission.
3. AI Macro software versions use `ERA.MAJOR.FEATURE.PATCH`. The next delivered software upgrade starts at `3.0.0.1`.
4. `ERA` changes only when the owner explicitly declares a new generation of the platform. It is never incremented at a bot's discretion.
5. `MAJOR` changes only for a broad product-level release that materially changes multiple core areas, the platform's fundamental architecture, or its primary operating model. A major increment requires the owner's explicit approval.
6. `FEATURE` changes when one delivered upgrade adds or materially changes a bounded user capability, domain, tab, analytical product, or workflow. The reader must be able to do or understand something meaningfully new.
7. `PATCH` changes for repairs and refinements that do not add a materially new capability, including bug fixes, loader or source corrections, validation fixes, copy changes, layout improvements, performance work, and maintenance.
8. Routine data refreshes, newly generated AI Reads, retained-state updates, and source observations do not change the software version unless they also change code, schema, or product behavior.
9. Increment exactly one position for each delivered upgrade and reset every position to its right to zero. Examples: `3.0.0.1` to `3.0.0.2` for a patch, `3.0.1.0` for a feature, `3.1.0.0` for a major release, and `4.0.0.0` only for an owner-declared new era.
10. Assign one version to the completed deliverable. Do not create new version numbers for drafts, intermediate work, audits, tests, reports, or packaging steps.
11. No bot may put defensive caveats, methodological throat-clearing, scope disclaimers, or robotic “not X” qualifiers into reader-facing product copy unless the owner explicitly requests them. Write directly, concretely, and like a human.
