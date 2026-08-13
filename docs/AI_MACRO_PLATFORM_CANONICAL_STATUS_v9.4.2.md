# AI Macro platform canonical status — v9.4.2

## Purpose

AI Macro v9.4.2 recalibrates the explanatory Reader for an intellectually sophisticated non-specialist. The intended reader may know little about macroeconomics, infrastructure, power markets, bond markets, or AI Macro's internal labels, but can understand complex relationships when the prose supplies enough context.

This release corrects the v9.4.0 tendency toward classroom narration and padding. It does not restore compressed academic prose and does not simplify the underlying analysis.

## Reader calibration

The compiled language layer is `language-layer-1.4.1`, with payload digest `e7019e1bed12d3266e5c6e5e8df6a02372ffd1cdf2b5cd3e4ad5deb779623cf2`.

The former `reader_pedagogy` object has been removed. Its replacement, `reader_calibration`, establishes five rules:

1. Assume strong reasoning ability rather than specialist vocabulary.
2. Identify an unfamiliar cohort, measure, proxy, institution, stage, or process on first reference.
3. Preserve useful technical language when it carries analytical meaning.
4. Explain only relationships that are not already self-evident.
5. Use paragraph space to sharpen context, mechanism, consequence, or evidentiary limits rather than to teach or pad.

OpenAI is explicitly told not to announce the structure of the argument, narrate a sequence of domains, explain ordinary financial or causal reasoning, translate every ratio, or repeat the thesis to fill space.

## Macro contract

The Macro Read keeps explicit OpenAI-authored paragraph boundaries. It now uses:

- three paragraphs by default;
- a fourth paragraph only when analytically necessary;
- two to four grounded sentences per paragraph;
- a normal range of 150–225 words;
- no minimum word count;
- a hard ceiling of 250 words;
- no more than 28 words per analysis sentence;
- three to five selected domains spanning at least three lifecycle stages.

The additional space remains available when the evidence requires it, but the schema and prompt no longer force twelve or more sentences or 180 words of output.

## Context diagnostic

The prose validator now flags undefined internal cohort labels including `covered issuers`, `covered companies`, and `covered cohort`. A phrase such as `the companies tracked in this analysis` passes that specific diagnostic because it identifies the subject for a new reader.

This diagnostic attaches a warning only. It never rewrites or suppresses OpenAI's prose, triggers a retry, restores an older Read, or creates another paid call.

The existing three-word alliteration diagnostic remains active.

## Architecture and state

A full generation remains exactly two explicit, separately persisted OpenAI calls with zero retries: all domain Reads first, then the Macro Read using the completed domain prose. The complete compiled layer enters both calls. Automation, schedules, call ceilings, publication routing, evidence packets, research corpora, retained data, and paid-generation artifacts are unchanged.

## Versions

- application: `v9.4.2`;
- language layer: `language-layer-1.4.1`;
- domain prompt: `domain-language-layer-1.2`;
- Macro prompt: `macro-rollup-2.1`;
- generator: `4.2.0`;
- Read service: `4.2.0`;
- validator: `3.3.0`.

## Verification

The release passes the language compiler and checksum contract, all eleven corpus-backed profile checks, two-call architecture, paragraph preservation, parsed-response serialization, contextual-sufficiency diagnostic, absence of a Macro word floor, editorial regression, seven stack-completion fidelity contracts, the 131-file release manifest contract, and all nine critical integrity contracts.

Scratch verification of the stack-completion program used inert import shims because the scratch runtime lacks the project `requests` and Plotly packages. The complete seven-test body ran and passed. The owner must run the normal unmodified command inside the project `.venv` after applying the overlay.

## Acceptance step

Apply the v9.4.2 matched overlay, run the full verification commands, and make one explicit full generation. Evaluate whether the Read identifies unfamiliar subjects, preserves intellectual authority, uses technical language naturally, and advances its thesis without a roadmap or classroom explanation.
