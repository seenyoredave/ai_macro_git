# Automation architecture

AI Macro uses one approved unattended writer. Public Streamlit is not that writer.

## Operating level

Deterministic research refreshes and Current Context run on schedule; OpenAI commentary runs only when the analytical evidence has changed materially from the evidence saved with the last generated Read. Every completed OpenAI response is published with its diagnostics under a 24-hour lease. A transport failure with no response leaves the previous committed publication intact for whatever remains of that lease.

## Schedule

The workflow pins the GitHub-owned checkout, Python-setup, and artifact-upload actions to reviewed full commit SHAs. It runs Monday through Friday at 08:07 in `America/New_York`, leaving more than 80 minutes before the regular U.S. market open while avoiding the top-of-hour scheduling hotspot. The IANA timezone is intentional so the schedule follows Eastern Standard and Eastern Daylight Time automatically. The same workflow also supports an explicit manual trigger.

## Publication transaction

1. GitHub checks out the current committed publication state and publishes the temporary `ai-macro-automation-refresh-lock` tag.
2. The automation worker refreshes every approved domain-owned source.
3. It refreshes the shared Market and Finance sources: YFinance, EDGAR, FRED, and the New York Fed.
4. It refreshes Current Context, then assembles and persists one final deterministic evidence snapshot. No provider call occurs after assembly.
5. The worker compares that snapshot with the complete evidence packets saved with the last generated Read. An exact match requires no OpenAI call. A numeric fact is material at a 10% relative move; percentage measures also trigger at two percentage points. Categorical changes, fact/domain additions or removals, and evidence-semantic changes are material immediately.
6. When all changes are below threshold, the worker renews the existing Read for 24 hours at zero API cost and records the current evidence identity plus the materiality decision. The generated-evidence baseline does not advance, so small changes accumulate across runs.
7. When a material change is present, fresh generation is required before commentary can represent the new analytical snapshot.
8. If generation is required, one domain request is made and persisted before validation.
9. The complete returned domain Reads feed the Macro request. Domain diagnostics do not stop that planned call.
10. One Macro request is made and persisted before its diagnostics run.
11. A completed artifact becomes locally current as `validated`, `published_with_warnings`, or `published_raw_response`; successful generation starts a new 24-hour lease and saves the new evidence baseline.
12. The worker advances the retained-state freshness ledger only for files whose content hash changed and rebuilds the release fingerprint.
13. Before committing and again before pushing, Git transport verifies that `origin/main` is still the exact source commit used by the run. If main moved, automation stops rather than merging a refreshed dataset produced from an older source revision.
14. The workflow commits retained research, Current Context, `openai_artifacts/current.json`, and the run ledger only when `publish_ready=true`.
15. Otherwise only the non-secret automation ledger is committed; research changes in the disposable runner are abandoned.
16. Cleanup removes the temporary automation lock tag on success and failure paths.

Git commit is therefore the production publication boundary, not the successful completion of an HTTP request or model response.

## Paid-call safety

The code has non-configurable upper bounds of two paid calls per run and four paid calls per Eastern calendar day. Environment settings may lower those ceilings but cannot raise them. A complete fresh commentary generation requires two available call slots before it begins.

The automation OpenAI client sets SDK `max_retries=0`. Validation never authorizes another paid request. The call journal reserves a call before the request starts, so failed requests count against the budget. The scheduled workflow runs only once per day and concurrency prevents overlapping production workers. A scheduled run with `AUTO_PUBLISH=false` is not allowed to spend OpenAI money on output it cannot publish; paid manual rehearsals remain explicit opt-ins.

Three controls are independent:

- `AI_MACRO_AUTOMATION_ENABLED` — master unattended-worker switch.
- `OPENAI_AUTOMATION_ENABLED` — permits bounded paid calls; deterministic automation may remain enabled when this is false.
- `AUTO_PUBLISH` — permits Git publication after the two planned responses complete.

Manual GitHub runs require additional `allow_paid` and `publish` opt-ins. A manual trigger alone never authorizes spending or publication.

## State and audit

`automation_artifacts/status.json` records the latest committed run. `runs.jsonl` is the run ledger and `call_journal.jsonl` is the non-secret paid-call reservation ledger. Provider failures that safely fall back to valid retained evidence are recorded as warnings; unavailable required state and snapshot-transaction failures block publication. Failed model attempts remain ignored by Git under `openai_artifacts/attempts/`; the workflow uploads them as short-retention GitHub Actions artifacts for diagnosis.

The automation ledger contains no API key and no source bodies.

## Current Context

There is one retained Current Context publication state. Desktop developer refresh and the automation worker may update it; Public Streamlit only reads it. Discovery prefers the strongest source-grounded developments from the most recent seven days and progressively broadens qualification within a hard ten-day window until at least six analytical domains are represented. Qualification tier and coverage are retained as diagnostics, and only program-retrieved developments with durable source-grounding provenance may enter the Reader surface.

## Deliberate omissions

The worker does not include automatic model retries, event-triggered regeneration, domain-selective dependency graphs, self-healing retry policies, multiple workers, or another publication database.
## Activation

GitHub repository configuration is intentionally separate from source code. The worker expects two Actions secrets, `OPENAI_API_KEY` and `FRED_API_KEY`, plus repository variables `SEC_USER_AGENT`, `AI_MACRO_AUTOMATION_ENABLED`, `OPENAI_AUTOMATION_ENABLED`, and `AUTO_PUBLISH`. Optional call-limit variables may lower the built-in 2/run and 4/day ceilings but cannot raise them.

A manual `workflow_dispatch` rehearsal adds its own `allow_paid` and `publish` checkboxes. Manual paid generation can therefore be tested with publication withheld. Scheduled runs behave more conservatively: when `AUTO_PUBLISH=false`, changed analytical evidence stops before any paid call rather than buying a draft that cannot be published.

Recommended activation order is deterministic/manual first, then one bounded paid manual rehearsal with publication withheld, then one bounded paid manual publish, and only then scheduled publication.
