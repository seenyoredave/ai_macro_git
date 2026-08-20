# Editorial evaluation

This directory contains the network-free acceptance suite for AI Macro's one-call editorial synthesis.

## Validate the suite

```bash
python helpers/run_editorial_eval.py
```

The command verifies 25 cases, expected publish/retain decisions, fact IDs, lifecycle coverage, and eight paired contrast sets.

## Create a human scorecard

```bash
python helpers/run_editorial_eval.py --write-scorecard evaluation/editorial_eval_scorecard.json
```

Populate each case with the saved model decision and 1–5 scores for factual grounding, decision quality, material relevance, cross-domain coherence, readability, and causal restraint. The scorecard is a local evaluation artifact; the helper never contacts OpenAI.

## Score completed results

```bash
python helpers/run_editorial_eval.py --results evaluation/editorial_eval_scorecard.json
```

Use the suite before changing the scheduled model, reasoning effort, prompt contract, or editorial constitution. A paid rehearsal is a separate, explicitly authorized action.
