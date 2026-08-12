# Commentary architecture

AI Macro uses OpenAI only for interpretation and synthesis. The deterministic platform remains the authority for data retrieval, calculations, evidence selection, source provenance, state, and publication validation.

## Flow

1. `DashboardContext` holds the assembled retained analytical state.
2. `analytics/read_evidence.py` reduces that state to one bounded full `EvidencePacket` per domain. Full packets retain raw values, source URLs, versions, and other audit material used by deterministic hashing, validation, and Reader provenance.
3. Before a paid request, each full packet is projected into a smaller model-facing packet. The model receives the canonical human-scale `display` value, fact label, non-empty context, boundaries, importance, and source labels. Raw numeric values, source URLs, empty context fields, and packet versions are deliberately omitted.
4. `analytics/read_generation.py` sends all model-facing domain packets in one Structured Outputs request. Each domain output is a grounded headline plus 3–4 connected `analysis` sentences; there is no Watch/watchpoint field.
5. The completed paid domain response is atomically persisted to `openai_artifacts/attempts/<attempt_id>.json` before validation. The attempt record preserves both the full deterministic evidence packets and the exact compact evidence projection supplied to the model.
6. `analytics/read_validation.py` validates every generated headline and analysis sentence against supplied `fact_id` values and rejects unsupported numeric claims or scope violations. Numeric grounding is restricted to fields visible to the model: fact label, display, and non-empty context. Hidden raw values are not valid support. Formatting-equivalent forms such as `300k` and `300,000` are normalized before comparison. A negative displayed change may be expressed as an unsigned magnitude only when nearby directional language preserves the negative sign (for example, `-8.4%` → `fell 8.4%`).
7. A second Structured Outputs request creates an independent AI Macro analysis. It receives compact domain orientation (each domain thesis headline plus the fact IDs the validated Read used), not the domain prose paragraphs, together with the same model-facing evidence packets. Macro selects 4–6 domains spanning at least three lifecycle stages and writes exactly four grounded sentences as two short paragraphs. That paid response is added to the same attempt record before Macro validation.
8. The Macro result passes the same deterministic validation gate plus synthesis checks: every selected domain must contribute support, at least two analysis sentences must cite more than one domain, and verbatim/long-run reuse of domain Read language is rejected.
9. Only a fully validated result may be atomically promoted to `openai_artifacts/current.json`. Promotion starts a 24-hour publication lease.
10. Reader visibility and evidence currency are separate. A validated, schema-compatible artifact remains Reader-visible until its publication lease expires even if a later deterministic refresh changes the analytical evidence snapshot. The artifact keeps its original `evidence_snapshot_id`; the mismatch is surfaced explicitly and still requires fresh generation before the new evidence can be represented as current commentary.
11. **Apply last Read** in Developer Tools renews the most recent validated artifact for another 24 hours without an OpenAI call. Reapplication changes only publication metadata; it never rewrites prose, retargets fact support, changes the original generation time, or changes the evidence snapshot.
12. Current Context is attached afterward as an independent sourced layer and never causes an OpenAI commentary call. Its deterministic language engine is structural: it may restore event framing, identity, sentence order, attribution, and one bounded supporting detail from the same grounded source, but it does not generate analytical implications.

## Editorial contract

- Commentary exists to interpret relationships among selected facts, not to restate the dashboard.
- Domain Reads use a headline plus 3–4 grounded analytical sentences as one coherent paragraph. AI Macro is intentionally broader in scope but shorter in form: exactly four grounded sentences, normally about 85–110 words, rendered as two short paragraphs and spanning multiple lifecycle stages; the deterministic hard cap remains 120 words.
- Numbers are selective evidence, not the organizing structure of the prose. The model should normally use only the few quantities needed to support its thesis.
- Trading-terminal language, catalyst language, rhetorical questions, separate monitoring lines, and forecasts do not belong in the Reader commentary schema. Macro should be understandable to a smart non-specialist without weakening the analysis. Prefer ordinary language and direct sentences; do not insert definitions or parenthetical mini-glossaries into the Read.
- Reader Voice treats logic as part of style. Each analysis sentence carries one main relationship, explicit input/process/outcome hierarchy replaces false peer contrasts, four or more commas fail validation, semicolons are prohibited, domain analysis is capped at 95 words, and Macro analysis is capped at 120 words.
- Sentence-level `fact_id` support remains mandatory even as the prose becomes more interpretive. Macro is not permitted to function as a stitched recap of domain Reads; it must form a system-level thesis from their conclusions and underlying evidence.

## Artifact durability

- `openai_artifacts/attempts/` is permanent local paid-generation history. Rejected attempts remain useful audit/debug artifacts and are never Reader publication material.
- A failed attempt may be revalidated/resumed from Developer Tools when its evidence snapshot still matches the current analytical snapshot. Already-paid model output is reused; only a missing stage may trigger another API request. Developer Tools also supports Macro-only regeneration from the current validated domain Reads, allowing Macro editorial iteration with one paid call instead of rerunning all domains.
- `openai_artifacts/current.json` is the single validated Reader artifact and may be intentionally committed for hosted publication. Its publication metadata records a 24-hour lease (`published_at`, `expires_at`, source, and renewal count) while preserving the original generation/evidence identity.
- Ordinary code releases, patch archives, and the retained-data release fingerprint exclude `openai_artifacts/`. Code replacement must not erase paid generation state.
- API credentials are never written to either artifact.

## Failure contract

If commentary is absent, expired, schema-incompatible, rejected, or otherwise unavailable, there is no legacy prose engine and no synthetic fallback path. The Reader displays:

**Commentary temporarily unavailable.**  
The analyst has wandered off. The data have not.

Current Context continues to render when it has qualified content. Event reconstruction is deterministic and auditable; a valid item is framed around the source-established actor/action nucleus rather than dropped because the raw publisher prose is awkward.

## OpenAI boundary

- API credentials stay in `OPENAI_API_KEY`; credentials are never persisted in artifacts.
- Generation is owner-triggered from Developer Tools or invoked by the approved automation worker under hard paid-call ceilings and zero SDK retries. Public Streamlit never calls OpenAI.
- Model output is Pydantic-structured and then deterministically validated. Structured shape does not establish factual truth; local validation remains mandatory.
- The API is not a scheduler, provider loader, database, or autonomous agent. Scheduling and publication authority live in the deterministic automation layer.
- Current Context semantic triage/search remains a separate future evaluation surface.

## Code ownership

- `analytics/read_evidence.py` — deterministic evidence extraction and model-facing projection
- `analytics/read_models.py` — Pydantic output contracts
- `analytics/read_prompts.py` — versioned generation instructions
- `analytics/read_generation.py` — OpenAI Responses API boundary
- `analytics/read_validation.py` — deterministic publication gate
- `analytics/read_store.py` — permanent paid-attempt archive plus validated artifact promotion
- `analytics/read_service.py` — commentary orchestration and unavailable state
- `analytics/read_context.py` — independent Current Context attachment
- `analytics/reader_snapshot.py` — final Reader assembly
- `developer/` — owner-only Operations, Current Context, AI, and Diagnostics workspaces
- `automation/` — bounded headless refresh, paid-call guard, run ledger, and publication decision


## Two-paragraph Macro shape

AI Macro is a system-level synthesis, not a stitched recap of domain prose. The Macro request receives compact domain orientation plus the underlying evidence packets, never reusable domain analysis paragraphs. It selects 4–6 domains spanning at least three lifecycle stages and returns exactly four grounded sentences. The Reader renders sentences 1–2 as the system thesis / dominant constraint paragraph and sentences 3–4 as the diffusion / outcomes / broad-implication paragraph. The validator caps sentence scope and length so the closing sentence cannot become a multi-domain run-on.
