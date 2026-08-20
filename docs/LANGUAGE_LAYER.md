# Language and editorial layer

AI Macro’s language system is portable context supplied to OpenAI. It is not a deterministic prose generator and it does not alter a response after generation.

The language/OpenAI subsystem is an overlay. It consumes finished deterministic state and may only format, constrain, serialize, interpret, and validate commentary. It must never recalculate analytical state, rank research inputs, resolve records, authorize providers, or influence a metric, chart, refresh result, or application decision. Removing the subsystem must leave deterministic AI Macro unchanged except that Reader prose is unavailable.

## Production contract

A material commentary evaluation uses exactly one Responses API Structured Outputs call. The request contains:

- 10–15 compact signal capsules built from deterministic evidence;
- current state, material change, short trajectory, source labels, fact IDs, and explicit measurement boundaries;
- only the prior domain prose relevant to possible replacements, plus the prior Macro Read;
- compact prior analytical state for continuity;
- `language/AI_MACRO_EDITORIAL_CONSTITUTION_v1.0.json`.

The response is one `GeneratedEditorialSynthesis` object. It must choose either:

- `retain_prior`, with no replacement prose; or
- `publish`, with only the required/candidate domain replacements and one final Macro Read.

There is no second Macro call, draft, editor, critic, repair, replay, replacement, or validation-triggered call. The direct client uses `max_retries=0`. Public Reader sessions make no calls.

## Offline corpus and production constitution

The complete research assets remain retained and auditable:

- `AI_MACRO_MARKET_CORPUS_COMPLETE_v1.0.json`
- `AI_MACRO_FINANCE_CORPUS_COMPLETE_v1.1.json`
- `AI_MACRO_COMPUTE_CORPUS_COMPLETE_v1.0.json`
- `AI_MACRO_DATA_CENTER_CORPUS_COMPLETE_v1.0.json`
- `AI_MACRO_CONNECTIVITY_CORPUS_COMPLETE_v1.0.json`
- `AI_MACRO_POWER_GRID_STORAGE_CORPUS_COMPLETE_v1.0.json`
- `AI_MACRO_WATER_CORPUS_COMPLETE_v1.0.json`
- `AI_MACRO_DIFFUSION_ECONOMIC_TRANSMISSION_CORPUS_COMPLETE_v1.0.json`
- the auditable source and compiled full language layer.

All eleven profiles remain backed by completed corpora. Power and Grid & Storage share one research corpus while retaining separate evidence boundaries and Reads. Adoption, Workforce, and Economic Outcomes share one diffusion/economic-transmission corpus while retaining three separate production boundaries and Reads.

The full audited neuroscience/neurochemistry/biophysics product also remains intact: 16 reviewed sources, 70 atomic observations, 22 reference system families, and 14 mathematical motifs. Production preserves its systems-dynamics contribution through the compact constitution’s architecture rules and explicit analogy boundary. It is never economic evidence, does not license biological claims in Reader prose, and never establishes a shared mechanism.

The production constitution is intentionally compact. It carries the durable editorial lessons needed on every call—causal restraint, stock/flow and bottleneck reasoning, feedback and lag structures, measurement boundaries, prose limits, citation discipline, and abstention—without retransmitting the complete research corpus.

## Integrity

`analytics/language_layer.py` validates the constitution’s type, version, required sections, and SHA-256 identity before generation. A missing, malformed, or identity-mismatched constitution fails before the API request. The full compiled language layer retains its own compiler and checksum workflow for offline audit:

```bash
python tooling/compile_language_layer.py
python tooling/compile_language_layer.py --check
```

## Output and hard gate

Structured Outputs provides the typed decision, sentence, fact-ID, domain-membership, Macro, and analytical-state contract. The exact OpenAI response object is retained before validation. Public prose is assembled only by joining the exact returned fields; it is never rewritten locally.

The hard publication gate rejects:

- unknown or unsupplied fact IDs;
- citations outside the domain or selected Macro scope;
- numeric claims unsupported by the cited supplied facts;
- omitted domain replacements when prior prose cites materially changed facts;
- duplicate or inconsistent incremental-update membership;
- a malformed publish/retain decision;
- a Macro selection outside 3–5 domains or fewer than three lifecycle stages.

Sentence shape, word budgets, repetition, filler, and related editorial checks remain diagnostics. They inform evaluation without spending another call or replacing model prose with deterministic prose.

Completed response outcomes are:

- `validated` or `published_with_warnings`: hard gate passed and the incremental publication is current;
- `retained_prior`: the model explicitly found no materially useful editorial update;
- `rejected_hard_validation`: a typed response failed the hard factual/contract gate;
- `rejected_unparseable`: a response was returned but could not satisfy the schema;
- `generation_failed`: transport ended without a response.

The first four advance `openai_artifacts/evaluated.json`. Only the first two replace `openai_artifacts/current.json`; `retained_prior` preserves and may renew it. A rejection preserves the prior good Read and prevents automatic repeat spending on the same evidence snapshot. A transport failure does not advance the evaluated baseline.

## Evaluation

`evaluation/editorial_eval_cases_v1.0.json` contains 25 deterministic evidence scenarios, including eight paired contrast sets designed to distinguish broad effects from narrow or weak proxies. `helpers/run_editorial_eval.py` never calls OpenAI; it validates the suite, emits a blank human scorecard, or scores saved results. The acceptance dimensions are factual grounding, decision quality, material relevance, cross-domain coherence, readability, causal restraint, and correct abstention.

## Updating the layer

Advance the constitution version only when a durable editorial rule changes. Preserve the complete corpora and full neuroscience audit as reference assets, update their compiled lineage if the underlying research changes, then run the contract smoke tests and local eval harness before authorizing a paid rehearsal.
