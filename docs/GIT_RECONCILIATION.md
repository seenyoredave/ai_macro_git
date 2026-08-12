# Desktop master and Git publication state

AI Macro uses two deliberately separate working directories.

- `/Users/Dave/desktop/vsc/ai_macro/` is the owner development master.
- `/Users/Dave/desktop/vsc/ai_macro_git/` is the Git staging/publication repository.

Code and configuration flow from the desktop master into Git. Retained research data do not use blind overwrite semantics because GitHub automation is also an approved retained-data writer.

## Retained-state freshness

`data/retained_state_manifest.json` records a SHA-256 and `updated_at_utc` for every mutable retained file under `data/` and retained archives under `archive/`. The timestamp advances only when the content hash changes. Normal retained-only Reader rebuilds do not advance it.

Desktop explicit refreshes update the ledger after persistence. GitHub automation updates it after the deterministic refresh. This provides a durable ordering that survives ZIP extraction, directory copies, and Git checkout timestamps.

## Desktop reconciliation

Run reconciliation from the Git staging repository before every owner commit that imports desktop work:

```bash
cd "/Users/Dave/desktop/vsc/ai_macro_git"
./.venv/bin/python -m tooling.desktop_sync --desktop "/Users/Dave/desktop/vsc/ai_macro"
```

The command:

1. refuses to run while the automation refresh lock is active;
2. requires a clean Git staging worktree;
3. fetches `origin/main` and fast-forwards when appropriate;
4. copies program code/configuration from the desktop master while preserving Git-local `.gitignore`, `.venv`, `.git`, `automation_artifacts/`, and `.streamlit/secrets.toml`;
5. reconciles mutable retained data per file using the freshness ledger;
6. unions paid-attempt JSON artifacts by immutable attempt identity;
7. selects the newer validated `openai_artifacts/current.json` by publication/generation time;
8. preserves the online automation ledger;
9. rebuilds the release manifest and runs the non-network release gates.

After reconciliation, inspect `git status`, then commit and push normally.

## Push guard

The repository includes `.githooks/pre-push`. Install it once in the Git staging repository:

```bash
cd "/Users/Dave/desktop/vsc/ai_macro_git"
./.venv/bin/python -m tooling.git_guard install
```

The hook fails closed. It refuses a normal push when the automation refresh lock is present, when the lock state cannot be checked, or when `origin/main` contains commits missing from the local branch. No files are sent in those cases.

The hook uses ordinary Git remote authentication and does not require a GitHub API token or GitHub CLI.

## Automation race boundary

The GitHub workflow publishes the annotated tag `ai-macro-automation-refresh-lock` before provider work begins and removes it during cleanup. Workflow-level concurrency prevents overlapping automation runs.

Immediately before an automation commit and again before its push, the transport verifies that `origin/main` is still the exact commit from which the workflow started. If main moved, automation stops rather than merging a refreshed dataset generated from an older source revision. Git itself remains the final non-fast-forward safety boundary; automation never force-pushes `main`.

This produces an intentionally asymmetric authority model:

- desktop wins for code/configuration;
- newest retained state wins for mutable research data;
- newest validated publication timestamp wins for the current Read;
- online automation ledgers remain online-owned and append-only;
- an ambiguous freshness conflict stops for review instead of guessing.
