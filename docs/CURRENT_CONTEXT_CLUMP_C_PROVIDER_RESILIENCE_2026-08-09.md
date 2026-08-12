# Current Context Clump C — one domain grammar + provider resilience

## Canonical Current Context architecture

All eleven Current Context domains now use the same acceptance architecture:

1. eligible evidence source;
2. seven-calendar-day freshness window;
3. domain relevance vocabulary;
4. domain-specific AI/technology/infrastructure or system anchor;
5. domain-specific materiality threshold;
6. rank already-qualified items by materiality/fit/freshness;
7. display zero, one, or two developments.

Each domain has its own targeted search set and its own materiality vocabulary.
There is no aggregate score threshold and no second live-news loader. Network
retrieval is owned only by `loaders/current_context_discovery.py`; registry and
weekly-context loaders are provider-free. The unused GDELT adapter and the old
direct-live domain/sector feed path were removed rather than left dormant.

## Surgical renovation rule

Architecture removal is dependency-led, not cosmetic. A branch is removed only
after its active callers and data responsibilities are traced and the canonical
path covers them. Focused tests run immediately after removal, followed by the
full retained/startup/integrity/browser gates. Do not perform speculative
adjacent cleanup while replacing an engine.

## YFinance resilience

The existing YFinance refresh path is hardened in place. The canonical pull now
uses low-concurrency batches, brief inter-batch pacing, retries only failed
tickers, single-worker retry rounds, and a longer adaptive cooldown when the
provider emits a rate-limit signal. Provider attempt counts, retry rounds,
cooldowns, rate-limit observations, and unresolved tickers are surfaced in the
Developer load report.

The archive contract is unchanged: retained YFinance advances only when the
live pull provides complete ticker-row coverage. Archive field fills may repair
optional missing cells for display, but they do not turn a missing live ticker
into a successful live refresh.
