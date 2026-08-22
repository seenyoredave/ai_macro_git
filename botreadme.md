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
12. `README.md` is a short, human-facing explanation of the project. Do not add bot instructions, internal architecture, workflow policy, implementation history, release notes, limitations sections, manifest language, or project doctrine to it. Do not add anything to it. Do not touch it unless given explicit permission by the owner. 
13. `botreadme.md` is the sole Markdown file for bot-facing rules and durable operating instructions.
14. The owner’s workflow is local-first. Changes are prepared for the local `ai_macro/` copy, tested by the owner, then copied by the owner into `ai_macro_git/` and pushed by the owner. No bot may modify GitHub without the owner’s express permission.
15. The deployed Reader uses retained research state. Source refreshes, OpenAI calls, file writes, and publication occur only through an authorized owner or automation workflow.
16. Editorial automation makes at most one OpenAI request per run and performs no SDK, validator, or stage-triggered retry. Only a completed response with usable output consumes the safety allowance.
17. A completed editorial response must pass the hard grounding and publication contract before replacing the published Read. Rejection retains the last good Read; bots must not rewrite or repair rejected prose locally.
18. When `required_update_domains` is nonempty, the published prose is stale: publication is mandatory, `retain_prior` is forbidden, and every required domain must be returned.
19. Preserve OpenAI attempt records in `openai_artifacts/attempts/`.
20. The completed domain corpora and audited neuroscience product are retained reference assets. Do not rebuild, replace, or reaudit them without the owner’s express instruction.
21. Current Context must remain independently discovered and source-grounded. Do not substitute model memory, unsupported summaries, or invented events for source evidence.
22. Runtime schedules, thresholds, source policies, schemas, and other changeable implementation details belong in code and configuration, not in `README.md` or `botreadme.md`.
