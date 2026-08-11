# Automation architecture

AI Macro v7.1.0 introduces one approved unattended writer. Public Streamlit is not that writer.

## Operating level

The initial target is conditional automatic publication: deterministic research refreshes and Current Context run on schedule; OpenAI commentary runs only when the analytical evidence snapshot requires it; deterministic validators decide whether the result may be published. A failed run leaves the previous committed publication intact.

## Schedule

The workflow pins the GitHub-owned checkout, Python-setup, and artifact-upload actions to reviewed full commit SHAs. It runs daily at 05:17 in `America/New_York`. The IANA timezone is intentional so the schedule follows Eastern Standard and Eastern Daylight Time automatically. The same workflow also supports an explicit manual trigger.

## Publication transaction

1. GitHub checks out the current committed publication state.
2. The automation worker refreshes approved retained inputs and Current Context in that expendable checkout.
3. The worker rebuilds the deterministic evidence snapshot.
4. If a validated artifact already matches that evidence snapshot, no OpenAI call is made.
5. If generation is required, one domain request is made and persisted before validation.
6. A domain validation failure stops the run. No Macro request is allowed.
7. After domain validation, one Macro request may be made and is persisted before validation.
8. Only a fully validated artifact becomes locally current.
9. The workflow commits retained research, Current Context, `openai_artifacts/current.json`, and the run ledger only when `publish_ready=true`.
10. Otherwise only the non-secret automation ledger is committed; research changes in the disposable runner are abandoned.

Git commit is therefore the production publication boundary, not the successful completion of an HTTP request or model response.

## Paid-call safety

The code has non-configurable upper bounds of two paid calls per run and four paid calls per Eastern calendar day. Environment settings may lower those ceilings but cannot raise them. A complete fresh commentary generation requires two available call slots before it begins.

The automation OpenAI client sets SDK `max_retries=0`. Validation failure never authorizes another paid request. The call journal reserves a call before the request starts, so failed requests count against the budget. The scheduled workflow runs only once per day and concurrency prevents overlapping production workers. A scheduled run with `AUTO_PUBLISH=false` is not allowed to spend OpenAI money merely to create an unpublished draft; paid validation-only rehearsals are manual-only.

Three controls are independent:

- `AI_MACRO_AUTOMATION_ENABLED` — master unattended-worker switch.
- `OPENAI_AUTOMATION_ENABLED` — permits bounded paid calls; deterministic automation may remain enabled when this is false.
- `AUTO_PUBLISH` — permits Git publication after every required gate passes.

Manual GitHub runs require additional `allow_paid` and `publish` opt-ins. A manual trigger alone never authorizes spending or publication.

## State and audit

`automation_artifacts/status.json` records the latest committed run. `runs.jsonl` is the run ledger and `call_journal.jsonl` is the non-secret paid-call reservation ledger. Provider failures that safely fall back to valid retained evidence are recorded as warnings; unavailable required state and snapshot-transaction failures block publication. Failed model attempts remain ignored by Git under `openai_artifacts/attempts/`; the workflow uploads them as short-retention GitHub Actions artifacts for diagnosis.

The automation ledger contains no API key and no source bodies.

## Current Context

There is one retained Current Context publication state. Desktop developer refresh and the automation worker may update it. Public Streamlit only reads it. The retired public 15-minute discovery/cache path is prohibited by regression tests.

## Deliberate omissions

v7.1.0 does not include automatic model retries, event-triggered regeneration, domain-selective dependency graphs, self-healing retry policies, multiple workers, or another publication database. Those belong to later automation levels only after the scheduled system establishes a reliability record.
## Activation

GitHub repository configuration is intentionally separate from source code. The worker expects one Actions secret, `OPENAI_API_KEY`, and three repository variables: `AI_MACRO_AUTOMATION_ENABLED`, `OPENAI_AUTOMATION_ENABLED`, and `AUTO_PUBLISH`. Optional call-limit variables may lower the built-in 2/run and 4/day ceilings but cannot raise them.

A manual `workflow_dispatch` rehearsal adds its own `allow_paid` and `publish` checkboxes. Manual paid generation can therefore be tested with publication withheld. Scheduled runs behave more conservatively: when `AUTO_PUBLISH=false`, changed analytical evidence stops before any paid call rather than buying a draft that cannot be published.

Recommended activation order is deterministic/manual first, then one bounded paid manual rehearsal with publication withheld, then one bounded paid manual publish, and only then scheduled publication.

