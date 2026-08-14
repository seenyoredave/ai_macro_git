# Phase 1 — Workforce and Realized-Value Transmission

## Purpose test

Phase 1 addresses the second half of the platform purpose statement: whether rising investment, infrastructure, and adoption are producing broad participation and realized value, and how the gains are reaching workers and households.

## Workforce contract

Workforce now keeps two evidence classes visibly separate:

1. **Theoretical task exposure** — the static 2023 `GPTs are GPTs` occupation benchmark estimates the share of tasks that LLM capabilities or LLM-powered software could affect under the study rubric.
2. **Observed labor outcomes** — BLS CES and JOLTS series measure employment, nominal and CPI-adjusted earnings, openings, hires, quits, and layoffs-and-discharges.

The application does not combine the two classes into an automation, displacement, or job-loss score. Detailed CES industries are mapped to broader JOLTS markets only for contextual demand, mobility, and separation evidence.

## Economic Outcomes contract

Economic Outcomes now follows a transmission ladder:

```text
Commercial demand
→ productivity and output
→ real hourly compensation and labor share
→ median real weekly earnings
→ broad participation
```

Every stage carries a causal label. Provider revenue is directly observed but provider-defined. Economy-wide productivity and worker outcomes are observed; their AI contribution remains not distinguishable without causal evidence.

## Retained data

- `workforce_llm_exposure_snapshot.csv`
- `workforce_labor_flows_history.csv`
- `economic_value_transmission_history.csv`
- `household_earnings_distribution_history.csv`
- `v680_public_data_manifest.csv`

## Known limits

Phase 1 does not yet observe worker-level transitions, hours, benefits, contingent work, employer-paid versus worker-paid training costs, firm-level AI adoption effects, wealth ownership, regional household capture, or causal AI effects. These limits are displayed in the tabs and Evidence rather than inferred around.
