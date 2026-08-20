# Automation architecture

AI Macro uses one approved unattended writer. Public Streamlit is not that writer.

## Operating level

Deterministic research refreshes and Current Context run on schedule. OpenAI runs only when analytical evidence has changed materially from the last **completed evaluation**. Publication and evaluation are separate state: `openai_artifacts/current.json` is the last good Read, while `openai_artifacts/evaluated.json` records the newest evidence snapshot that received a completed model response.

One completed response may publish incremental replacements, explicitly retain the prior Read, or fail the hard factual gate. All three advance the evaluated baseline. A transport failure with no response does not.

## Schedule

The workflow runs Monday through Friday at 08:07 in `America/New_York`, leaving more than 80 minutes before the regular U.S. market open while avoiding the top-of-hour scheduling hotspot. The IANA timezone follows Eastern Standard and Eastern Daylight Time. The same workflow supports an explicit manual trigger.

## Publication transaction

1. GitHub checks out the current committed publication state and publishes the temporary automation lock tag.
2. The worker refreshes approved domain-owned sources, shared Market and Finance sources, and Current Context.
3. It assembles and persists one final deterministic evidence snapshot. No provider call occurs after assembly.
4. The worker compares that snapshot with `evaluated.json`, falling back to the evidence stored with `current.json` during migration. A numeric fact is material at a 10% relative move; point-scale measures also trigger at two points. Categorical changes, fact/domain additions or removals, and evidence-semantic changes are immediately material.
5. Exact or immaterial changes require no API call. The last good Read may be renewed at zero cost, and small changes continue to accumulate against the evaluated baseline.
6. Material evidence is compressed into 10–15 signal capsules. Each capsule contains current state, change, short trajectory, source labels, confidence and measurement boundaries, and fact IDs. The production prompt includes the compact editorial constitution, relevant prior prose, and prior analytical state; it does not send raw provider payloads or the full corpus.
7. One zero-retry Structured Outputs request returns one of two decisions:
   - `retain_prior`: no supplied change warrants publication;
   - `publish`: return only required/candidate domain replacements plus one new Macro Read.
8. The exact completed response is persisted before validation. The evaluated baseline then advances regardless of publish, retain, or hard rejection.
9. Publication is blocked by unknown, unsupplied, or out-of-scope fact IDs; unsupported numbers; a missing required domain replacement; or an invalid publish/retain contract. Style findings are diagnostics and do not trigger another call.
10. On `publish`, only returned domain Reads replace prior domain prose; unchanged domains remain verbatim. The new Macro Read replaces the prior Macro Read. On `retain_prior` or rejection, `current.json` remains the last good publication.
11. The worker advances retained-state freshness only for content-changed files and rebuilds the release fingerprint.
12. Before committing and again before pushing, Git transport verifies that `origin/main` still matches the source commit used by the run. If main moved, automation stops rather than merging refreshed state produced from an older revision.
13. The workflow commits retained research, Current Context, `openai_artifacts/current.json`, `openai_artifacts/evaluated.json`, and the automation ledger only when `publish_ready=true`. Failed transport leaves prior committed publication intact.
14. Cleanup removes the temporary automation lock tag on success and failure paths.

Git commit is the production publication boundary, not the completion of an HTTP request.

## Paid-call safety

The code has non-configurable upper bounds of one paid call per run and two calls per Eastern calendar day. Environment settings may lower those ceilings but cannot raise them. A material editorial evaluation requires one available call slot.

The SDK uses `max_retries=0`. No validator, stage transition, timeout handler, or recovery route can authorize another request. The call journal records a reservation before transport and then records whether a response was produced. The safety allowance counts only entries that produced a response. A scheduled run with `AUTO_PUBLISH=false` cannot spend money on output it is not authorized to publish; paid manual rehearsals remain explicit opt-ins.

Three controls are independent:

- `AI_MACRO_AUTOMATION_ENABLED` — master unattended-worker switch.
- `OPENAI_AUTOMATION_ENABLED` — permits the bounded paid call.
- `AUTO_PUBLISH` — permits Git publication after evaluation.

Manual GitHub runs require separate `allow_paid` and `publish` opt-ins. A manual trigger alone never authorizes spending or publication.

## State and audit

- `automation_artifacts/status.json` records the latest committed run.
- `automation_artifacts/runs.jsonl` is the run ledger.
- `automation_artifacts/call_journal.jsonl` is the non-secret call reservation/response ledger.
- `openai_artifacts/attempts/` retains exact completed response payloads for local audit and short-retention workflow diagnostics.
- `openai_artifacts/evaluated.json` stores the last completed-evaluation evidence packets, bounded fact history, analytical state, decision, and validation result.
- `openai_artifacts/current.json` stores only the last good published Reader artifact.

None contains an API key.

## Current Context

There is one retained Current Context publication state. Desktop developer refresh and the automation worker may update it; Public Streamlit only reads it. Discovery prefers source-grounded developments from the most recent seven days and progressively broadens qualification within a hard ten-day window until at least six analytical domains are represented.

## Deliberate omissions

The worker does not include automatic model retries, a second Macro call, editor/critic calls, replay, repair, multiple workers, provider tools exposed to the model, or another publication database.

## Activation

GitHub configuration is separate from source code. The worker expects Actions secrets `OPENAI_API_KEY` and `FRED_API_KEY`, plus repository variables `SEC_USER_AGENT`, `AI_MACRO_AUTOMATION_ENABLED`, `OPENAI_AUTOMATION_ENABLED`, and `AUTO_PUBLISH`. Optional call-limit variables may lower the built-in 1/run and 2/day ceilings but cannot raise them.

The code default is model `gpt-5.6`, reasoning effort `medium`, and `AI_MACRO_OPENAI_MAX_OUTPUT_TOKENS=12000`. Repository variables can override those values. A manual `workflow_dispatch` rehearsal adds its own `allow_paid` and `publish` checkboxes.

Recommended activation order is deterministic/manual first, then the local contract and eval harnesses, then one bounded paid manual rehearsal with publication withheld, then one bounded paid manual publish, and only then scheduled publication.
