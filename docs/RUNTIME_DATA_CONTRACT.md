# Runtime data contract

This contract is intentionally small. It is the authoritative description of
how the desktop and public versions of AI Macro obtain and retain data.

## One writer, many readers

| Runtime | Network access | Retained-file writes | Role |
|---|---:|---:|---|
| Public Streamlit | Never | Never | Read the committed publication state |
| Desktop public mode | Never | Never | Preview the retained snapshot |
| Desktop developer mode, ordinary rebuild | Never | Never | Recompute the app from retained inputs |
| Desktop developer mode, explicit refresh | Selected source(s) only | Selected source(s) only | Owner-controlled research refresh |
| Desktop developer mode, Generate commentary | OpenAI only | Local paid attempt history plus published `openai_artifacts/current.json` and diagnostics | Owner-controlled commentary generation |
| GitHub Actions automation worker | Approved providers + bounded OpenAI | Working-copy retained state; committed after typed generation completes | Scheduled unattended publication |

Git is the publication boundary. Public Streamlit is deliberately boring: it reads
only committed retained data, committed Current Context, and the committed published
commentary artifact. A viewer request cannot discover news, refresh a provider, call
OpenAI, or change research state.

The desktop developer workflow and the scheduled automation worker use the same
underlying loaders, Current Context discovery engine, evidence builder, commentary
service, and deterministic validators. The automation worker operates in an
expendable Git checkout. Provider refreshes and paid model output remain working-tree
state until provider transactions and typed commentary generation complete. Commentary
audit warnings are committed with the newly generated prose; they do not substitute the
prior Read. A structurally failed run records its non-secret run ledger.

## Market refresh sequence

1. The owner launches `AI_MACRO_MODE=developer streamlit run ai_macro.py`.
2. A provider refresh button authorizes only the selected provider(s) for one rebuild. `Refresh All Sources` explicitly authorizes YFinance, EDGAR, FRED, and NY Fed together.
3. YFinance must return a live row for every configured ticker, with no retained
   ticker-row fallback and one underlying market observation date shared by the full live universe, before
   a market snapshot can be retained. YFinance may omit individual optional
   fields on otherwise successful ticker rows; those cells may be filled from
   the prior retained snapshot and must be disclosed in the Developer load report.
4. The raw YFinance snapshot is written first. Its archive `Date` is the date
   the manual refresh was saved; `Market Data Date` records the underlying
   market observation date.
5. The fixed QQQ reference is constructed from that same resolved YFinance
   frame and must share its `Market Data Date` before any YFinance-owned
   analytical histories advance. The retained 204-name universe contains GOOG
   but not GOOGL, so the fixed QQQ contract maps the GOOGL weight to the retained
   GOOG Class C row for reproducibility. Only after the market and benchmark
   dates reconcile may benchmark, sector, and macro rows be written; their
   analytical chronology remains keyed to the market observation date rather
   than the refresh date.
6. EDGAR, FRED, NY Fed, and domain refreshes update only their owned retained
   inputs. They do not create a newly dated market, sector, or macro row. A successful explicit EDGAR refresh also rebuilds the retained 10-company SEC Finance fundamentals cohort from the same refresh-token Companyfacts payloads and updates the definition-matched debt ledger with comparable current/prior-year observations. `Refresh All Domains` runs the existing domain refresh paths together; it does not broaden their ownership.
7. After the intended release is complete, the owner runs
   `python helpers/build_release_manifest.py` and
   `python helpers/integrity_gate.py`.
8. The owner reviews the load report and pushes the retained files and matching
   `data/release_manifest.json` to GitHub.

`Refresh All Sources` is the normal path when all four provider-backed retained inputs should be advanced together. Individual source buttons remain available for targeted refreshes.

## Current Context runtime

- Public Streamlit never performs Current Context discovery. It loads the retained
  `data/weekly_context_events.csv` publication state and associated manifest only.
- Current Context discovery is owned by an explicit desktop developer refresh or the
  approved automation worker. Both write the same retained Current Context paths.
- The completed domain Context packet receives its own snapshot identifier.
  Commentary has a separate deterministic evidence snapshot identifier. Current
  Context is attached after commentary loading; a Context refresh never calls
  OpenAI and never changes the commentary evidence identity. The Reader Snapshot
  records both identities explicitly.
- Developer ordinary startup remains retained-only and makes zero Current
  Context provider calls. The owner may still use the explicit Refresh Current
  Context control for audit and retained-ledger review.
- A Current Context provider failure is reported as a provider failure; it may
  fall back to the last usable retained context but may not masquerade
  as a successful zero-result query.
- Current Context has one network discovery owner: `current_context_discovery`.
  Registry and weekly-context loaders are provider-free and may only resolve
  already-qualified records. Retired live-loader and aggregate score-gate paths
  must not be preserved behind compatibility flags.
- Discovery metadata is not evidence. RSS titles, search headlines, snippets,
  feed descriptions, and discovered article URLs nominate an event but may not
  supply Reader-facing Recent Developments prose. The nominated source gets the
  first grounding attempt; inability to fetch that one URL is not evidence that
  the event did not happen.
- Google News RSS article links are transport wrappers, not citation targets.
  Opaque current-generation Google article identifiers must resolve through the
  reference decode flow before the discovered publisher route is trusted. A host
  mismatch or decode/fetch failure rejects that route. For non-disqualifying
  failures, the same reference discovery owner may perform a bounded event-level
  evidence lookup and try another eligible primary or approved independent source
  that matches the event in subject, date, and factual signature.
- Alternate evidence is not a lower bar or a headline fallback. It must be a
  policy-eligible source, must not simply retry the same publisher, must preserve
  the nominated event identity, and must pass the exact same source-body recency,
  concrete-development, domain-materiality, and synthesis gates as a direct source.
  If no eligible source establishes the event, the correct output is no development.
- Materiality is evaluated before final fact extraction. The evidence source must
  present a clear current development in its lead evidence; Current Context may not
  mine a weak/commentary article for an isolated historical statistic that merely
  matches domain vocabulary. Historical comparisons can support a qualified current
  event but cannot serve as the anchor development on their own.
- Market has a separate significance boundary after AI relevance: broad market or
  sector read-through, a systemically important AI/technology issuer, a major
  public-market repricing, or a major transaction. AI-adjacent company results alone
  do not earn a Market slot.
- Reader prose and selector rationale are separate data products. Qualification,
  ownership, and rank reasons remain in audit/developer fields; Reader prose states
  the event and its economic meaning without explaining why the algorithm selected it.
- Source grounding walks the ranked qualified queue until enough grounded events
  exist to survive ownership/deduplication or bounded direct/evidence-search budgets
  are reached. A fixed first-N shortlist or a single inaccessible publisher may not
  make a domain disappear while later qualified evidence remains available.
- The publication date of the evidence source that actually establishes the event
  controls recency when available. A recent search or RSS timestamp cannot make an
  old evidence page current; modification date is a fallback only when publication
  date is absent.
- Full fetched source bodies are transient refresh inputs. They are never written
  to retained Current Context ledgers. Persist only compact derived
  facts, analytical relevance, resolved evidence URL, source dates, extraction
  metadata, and a non-reversible evidence hash for audit.
- A source-grounded automated row remains eligible across later engine-version
  changes while it is still within the domain freshness window and still meets
  the durable evidence contract (`grounded` status, substantive source-text
  provenance, evidence hash, eligible source, current materiality). Version is
  provenance, not expiry. `weekly_context_events.csv` stores the most recent
  vetted row for each `event_id`; rediscovery upserts that row, while historical
  gate-level trace remains in the candidate audit.
- Current Context never authorizes YFinance, EDGAR, FRED, NY Fed, or domain-data
  provider traffic.

## Commentary runtime

- OpenAI is an interpretation service, not a data owner. Reference facts, calculations, source provenance, and refresh authorization remain deterministic and local.
- The API receives bounded domain evidence packets. It does not receive the raw retained-data universe merely because it fits in the model context window.
- Developer mode owns the explicit **Generate commentary** action and the zero-cost **Apply last Read** publication action; the approved automation worker may invoke the same two-call service under hard call ceilings. Public Reader sessions never call OpenAI.
- The Responses API must return the Pydantic Structured Output contract. Every sentence must identify supporting evidence `fact_id` values.
- A deterministic validator diagnoses unknown/out-of-domain fact IDs, unsupported numeric claims, interrogative filler, word-budget violations, schema/domain-membership failures, and invalid Macro domain scope. Numeric validation includes cited fact labels/context and normalizes formatting-equivalent values such as `300k` and `300,000`; it does not permit rounding or uncited numbers merely because they appear elsewhere in the domain. Diagnostics never rewrite, suppress, retry, or replace a paid response.
- Every completed paid API response is persisted before validation under `openai_artifacts/attempts/<attempt_id>.json`, together with its exact raw response, evidence snapshot, structured model output when available, generation metadata, prompt versions, and eventual validation result.
- A completed artifact is promoted atomically to `openai_artifacts/current.json` and records its evidence snapshot, model, reasoning effort, per-stage prompt provenance, validation diagnostics, exact response metadata, Reader payload, and a 24-hour publication lease. Warned or raw output is labeled explicitly. Neither attempt nor current artifacts contain an API credential.
- Reader mode publishes a completed artifact as `validated`, `published_with_warnings`, or `published_raw_response` while its 24-hour publication lease is active. The artifact remains bound to its original evidence snapshot: a later deterministic refresh may make `evidence_current=false` without immediately removing the Read. Evidence mismatch still triggers fresh automation generation and still blocks snapshot-bound resume/Macro-regeneration paths. Once the lease expires, the retained Read fails closed to the reference unavailable message until new output is generated or the owner uses **Apply last Read** to renew it for another 24 hours.
- Current Context remains a separately sourced layer. It may add Recent developments to a validated or unavailable Read without mutating the retained commentary artifact. After source grounding, its deterministic language engine may reconstruct a compact event frame and one same-event supporting detail; it does not generate analytical implications and does not call OpenAI.
- Paid OpenAI artifacts are runtime/publication state, not retained-data source-release inputs. `helpers/build_release_manifest.py` deliberately excludes `openai_artifacts/`. `openai_artifacts/attempts/` stays local/private; `openai_artifacts/current.json` may be intentionally committed for hosted Reader publication until a later scheduler/storage path replaces Git publication.

## Archive invariants

- A public startup performs zero provider calls of any kind and zero retained-file writes. Current Context has no public-network exception.
- A developer retained startup performs zero provider calls, including Current Context, and zero retained-file writes.
- A rebuild is not a refresh.
- Clearing Streamlit caches is not a refresh.
- A retained-data live request requires an authorized writer (desktop developer
  or the approved automation worker) and explicit refresh intent. Public Current
  Context has no live exception; Reader mode consumes the committed retained snapshot.
- A force/request flag is intent only. It must never authorize itself: every
  network-owning retained-data loader requires the matching live authorization
  from the same `LoadPolicy` execution before contacting a provider.
- Every dated sector or macro row must reference a complete raw YFinance row set
  whose `Market Data Date` matches that analytical market date.
- Every retained QQQ row used for sector-relative performance must be reproducible
  from the same YFinance market snapshot and analytical `Market Data Date`.
- The Developer load report keeps refresh/archive dates separate from provider
  observation dates. A successful manual refresh advances the complete archive
  date even when the newest provider observation is earlier (for example a
  weekend YFinance refresh).
- A market refresh with missing live ticker rows or retained ticker-row fallback
  is not retained as a new market snapshot. Field-level fills on otherwise live
  ticker rows are allowed, remain visible in the Developer load report, and do
  not block the completed snapshot from being saved.
- A nonmarket refresh cannot advance or re-date market-derived history.
- An explicit EDGAR refresh must bypass any earlier 24-hour Companyfacts cache entry by carrying the refresh token into the Companyfacts cache key. The same token is then reused by the Finance derivative rebuild so the 10-company cohort consumes the exact refreshed SEC payloads without redundant provider calls.
- Debt Financing Pulse may advance only when current and prior-year observations preserve the issuer-specific retained debt definition. Prefer one common complete standard XBRL debt group across both dates; selecting the best current and prior-year tag families independently is not definition matching. If Companyfacts cannot express the issuer's matched debt definition completely, the refresh may fall back to a filing-reviewed retained pair only when that pair preserves that exact definition and is aligned to the current CapEx period. A refresh may not replace an unmatched definition simply because a generic SEC debt fact is available. The Developer load report distinguishes automatic Companyfacts updates, filing-reviewed fallbacks, and unresolved debt tickers.
- Local GitHub pushes may replace the deployed retained snapshot. No online
  merge or first-viewer-write protocol exists.
- `data/release_manifest.json` fingerprints the critical archives, baskets,
  formulas, benchmark, queue, source register, and facility-identity decisions
  that form one publication release. A stale manifest is a failed release, not
  a reason to create another writer or synchronization layer.

## Change control

Viewer-triggered provider calls and public Reader writes remain prohibited. The
owner has approved one scheduled publication worker: `.github/workflows/ai_macro_automation.yml`
running the deterministic `automation/` orchestrator. It is the only unattended
writer and must retain the hard paid-call ceilings, zero automatic model retries,
diagnostic retention, Git transaction boundary, and structurally fail-closed behavior
described above. Do not create a parallel refresh framework, second worker,
or alternate publication path without explicit approval. Any approved change must
update this document and the bounded runtime/snapshot/automation contract checks in
the same change.
