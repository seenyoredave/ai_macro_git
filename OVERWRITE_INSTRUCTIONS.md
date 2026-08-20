# AI Macro v10.1.0 Adoption repair

This package contains only the files that must overwrite the matching paths in AI Macro. It does not touch GitHub and does not contain an OpenAI artifact.

## 1. Update and verify the local application

Assuming the extracted package is in `~/Downloads/AI_MACRO_v10.1.0_ADOPTION_REPAIR`:

```bash
ditto ~/Downloads/AI_MACRO_v10.1.0_ADOPTION_REPAIR/overwrite/ /Users/Dave/Desktop/VSC/ai_macro/

cd /Users/Dave/Desktop/VSC/ai_macro
source .venv/bin/activate

python helpers/adoption_depth_smoke_test.py
python helpers/editorial_pipeline_smoke_test.py
python helpers/editorial_service_smoke_test.py
python helpers/run_editorial_eval.py
```

Restart Streamlit after the overwrite. The application-state schema advances to `73.0-adoption-depth-activation`, forcing the retained Adoption payload to rebuild.

Expected Adoption Depth state:

- retained source mode: `retained_official`
- 85 official supplement rows
- 15 business-function categories
- 10 published worker-task categories
- 9 organizational-adjustment categories
- employment effects sum to 100%

## 2. Copy the same files into the Git working repository

```bash
ditto ~/Downloads/AI_MACRO_v10.1.0_ADOPTION_REPAIR/overwrite/ /Users/Dave/Desktop/VSC/ai_macro_git/

cd /Users/Dave/Desktop/VSC/ai_macro_git
source .venv/bin/activate

python -m tooling.git_guard stage
git --no-pager diff --cached --stat
python -m tooling.git_guard pre-commit

git commit -m "v10.1.0 - activate Adoption depth"
python -m tooling.git_guard rebase
python -m tooling.git_guard pre-push
git push origin main
```

## 3. Retained-data publication behavior

`data/adoption_ai_supplement_2026.csv` is included so the local application works immediately. The repository policy deliberately leaves `data/` unstaged in an owner commit. Do not force-add it.

After the code push, run or await the approved automation workflow. Its authorized Adoption refresh will validate the same fixed Census workbook, publish the retained CSV through the automation-owned data path, and treat the new depth facts as a material evidence addition for the next one-call editorial evaluation.

The existing `openai_artifacts/current.json` is intentionally untouched. It remains the last good publication until that evaluation succeeds.
