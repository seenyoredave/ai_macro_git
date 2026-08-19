# Language layer

AI Macro’s language system is portable context supplied to OpenAI. It is not a deterministic prose generator and it does not alter OpenAI’s answer after generation.

The language/OpenAI subsystem is an overlay. It consumes finished deterministic state and may only format, label, constrain, serialize, and validate the prose generated from that state. It must never calculate or recalculate analytical state, rank or aggregate research data, resolve records, choose analytical fallbacks, or influence any metric, chart, domain state, refresh result, or application decision. Removing the subsystem must leave deterministic AI Macro unchanged except that Reader prose is unavailable.

## Production contract

A full commentary run uses two explicit Responses API calls:

1. Domain call: the complete compiled language layer, eleven compact evidence packets, and the structured output contract enter OpenAI. OpenAI returns the final eleven-domain Read set.
2. Macro call: the same complete language layer, the same compact evidence packets, every completed domain Read, and the Macro output contract enter OpenAI. OpenAI returns the final AI Macro Read.

There is no draft call, editor call, critic call, repair call, replacement call, or validator-triggered call. The direct OpenAI client uses `max_retries=0`. Macro-only regeneration is one explicit call. Public Reader sessions make no calls.

## What the layer contains

`language/AI_MACRO_LANGUAGE_LAYER_SOURCE_v1.0.json` is the auditable source. It contains:

- universal analytical and sentence-craft guidance;
- twelve evidence-sensitive prose architectures;
- set-level variation rules for the eleven domain Reads;
- uncertainty and measurement-boundary rules;
- sophisticated-non-specialist audience calibration, contextual-sufficiency rules, explanatory restraint, and flexible Macro paragraph guidance;
- one profile for each reference domain;
- a system-level Macro synthesis contract;
- generalized editorial failure lessons, never a blacklist of previously failed sentences;
- the full audited neuroscience/neurochemistry/biophysics systems-dynamics bonus.

All eleven profiles are backed by completed corpora. Power and Grid & Storage use one combined research corpus while retaining separate production profiles, evidence boundaries, and Reads. Adoption, Workforce, and Economic Outcomes likewise use one combined diffusion-and-economic-transmission corpus while retaining three separate production profiles, evidence boundaries, and Reads.

The neuroscience bonus remains complete: 16 reviewed sources, 70 atomic observations, 22 reference system families, and 14 mathematical motifs. It supplies transferable systems reasoning only. It is never economic evidence and never establishes a shared biological/economic mechanism.

## Compilation and integrity

`tooling/compile_language_layer.py` verifies:

- the reference eleven-domain order;
- required profile fields and source-state labels;
- exact structural corpus provenance identifiers;
- hashes and versions for the eight completed corpus files supporting eleven corpus-backed profiles;
- the complete neuroscience ingestion audit;
- architecture-library membership;
- the compiled payload checksum.

The compiler emits `language/AI_MACRO_LANGUAGE_LAYER_v1.0.json`. `analytics/language_layer.py` recomputes its checksum before generation and returns the entire payload to both calls. A missing, stale, malformed, incomplete, or checksum-invalid layer fails before a paid call.

```bash
python tooling/compile_language_layer.py
python tooling/compile_language_layer.py --check
python helpers/language_layer_contract_test.py
```

## Output and diagnostics

Structured Outputs provides the typed sentence/fact-id contract. The Macro contract also preserves three or four explicit paragraph objects containing two to four sentences each. The exact OpenAI response object is retained for every completed call. Public prose is assembled only by joining the exact returned sentence fields within their returned paragraph boundaries; it is not rewritten.

Deterministic validators run after the response and attach grounding diagnostics:

- sentence-sound diagnostics flag any run of three or more successive same-initial words;
- reader-context diagnostics flag undefined internal cohort labels such as `covered issuers`;
- proportional-language diagnostics flag ambiguous constructions such as `minority current business use` while accepting population-first language such as `fewer than half of businesses`;
- neutral-scope diagnostics flag social-identity or partisan framing that falls outside the analytical product;

- all checks pass: `validated`;
- one or more checks warn: `published_with_warnings`;
- a completed response lacks the structured parse but contains text: `published_raw_response`.

All three are publication states. A transport failure with no returned response is `generation_failed`. Diagnostics never trigger an additional call, restore an older Read, or suppress paid output.

## Updating the layer

Advance `layer_version`, change the source contract, compile it, and run both the language-layer and two-call architecture tests. When another domain corpus is completed, add its file and exact provenance identifiers, change that profile from `PLATFORM_NATIVE` to `CORPUS_BACKED`, rebuild the compiled layer, and update the release manifest only after tests pass.
