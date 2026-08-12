# v6.10.15 — Current Context retained round-trip + Read separators

## Defect

v6.10.14 could report selected Market and Finance developments while rendering no Recent developments on those tabs. Discovery wrote qualified automated events with provenance statuses such as `reported`, `primary`, `company_statement`, and `independently_retrieved`. The retained registry loader admitted only legacy `confirmed`/`corroborated` statuses, so the selected records were discarded on reload before Read construction.

## Repair

The retained source gate now recognizes each discovery-produced evidence status only in its appropriate source role. Blocked/social/discovery-only sources remain ineligible; manual-review sources still require corroboration. A regression now exercises the full select → persist → reload → attach → render path for Market and Finance.

## Read separators

The shared Read visual contract now supplies a thin divider above Recent developments and another above References. When Recent developments is absent, the References divider directly separates the narrative from References. Because this is implemented in the shared Read renderer/theme, it applies across all Read-bearing tabs.

## Provider cleanup

GDELT is removed from the routine Current Context refresh path after the developer audit returned SSL handshake timeouts for all eleven domains. The dormant adapter was removed in v6.10.17; canonical discovery relies on Google News RSS, direct primary feeds, and Tier-2 outbound discovery.
