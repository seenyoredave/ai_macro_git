# v6.10.14 — Current Context activation diagnostics + named Reads

This is a narrow repair to Clump A.

## Why v6.10.13 could look unchanged

The release changed the discovery/qualification engine but intentionally preserved the retained Current Context ledger. Retained startup makes zero provider calls, so installing the new code did not automatically exercise the new engine. The packaged retained manifest also predated the Clump A discovery version, which made the mismatch invisible in the UI.

v6.10.14 keeps the zero-network retained-startup contract and makes the state explicit in Developer Tools. The Current Context block now reports engine version, retained snapshot version/date, candidates, qualified items, Market/Finance selections, and provider errors. An engine/snapshot mismatch explicitly asks the developer to use **Refresh Current Context**.

## Provider observability

Google News RSS transport failures are no longer silently converted to a successful zero-item result in the auditable discovery path. Network errors now appear in the fetch status and Developer report.

## Finance discovery coverage

Finance now includes uncommenced leases, lease commitments, contractual/purchase/capital/forward commitments, and obligations in both discovery vocabulary and materiality ranking. This prevents economically material funding-capacity developments from being rejected merely because the headline describes contractual claims rather than funded debt.

## Named Read labels

Generic `Read` call sites now inherit the canonical domain title from the visual profile. Examples: **AI Macro Read**, **Market Read**, **Finance Read**, **Data Centers Read**, **Grid & Storage Read**, and **Economic Outcomes Read**.
