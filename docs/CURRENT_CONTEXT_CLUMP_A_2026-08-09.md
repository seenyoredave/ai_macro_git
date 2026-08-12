# Current Context Clump A — Market and Finance discovery quality

This release changes discovery and qualification, not the public refresh cadence. The shared 15-minute Context + Read snapshot remains a later workstream.

## Market and Finance qualification

Market and Finance use a seven-calendar-day lookback and four reader-auditable hard gates:

1. eligible evidence source;
2. within the lookback window;
3. domain relevance;
4. substantive domain-specific development.

Aggregate rank score no longer decides whether a Market or Finance item is true enough to exist. It orders items that already passed the hard gates. Each domain may retain zero, one, or two developments.

Market also requires an AI/technology-universe anchor so a generic market recap does not become AI Macro context merely because it mentions earnings or stocks.

## Discovery paths

The proof domains use several narrow Google News RSS searches rather than one giant query. GDELT was initially retained as a broad fallback request, but routine use was removed in v6.10.15 after repeated all-domain SSL-handshake failures. The dormant adapter was removed in v6.10.17 rather than retained as a parallel fallback.

Direct primary feeds are added for high-value official material, initially Federal Reserve monetary-policy releases for Finance and SEC press releases for Market/Finance.

Tier-2 sources are discovery infrastructure only:

- Techmeme;
- Abnormal Returns;
- Data Center Richness.

The adapter reads their feeds, extracts outbound links, and discards the intermediary as evidence. A Tier-2 lead that lands on a primary record or company statement can proceed through normal qualification; a lead that lands only on secondary journalism must also be found through an independent non-Tier-2 discovery path before it is eligible for unattended selection. The retained audit preserves `discovered_via` and the resulting evidence path for Developer review.

At most one selected development per domain may originate from a Tier-2 discovery path, so a single curator cannot monopolize the two-item Current Context surface.

## Source roles

Approved independent business reporting and primary institutional records may qualify automatically. Business Wire is treated as a company-statement distribution path, not independent journalism. Social media remains excluded entirely. Associated Press is excluded from unattended Current Context selection.

## Auditability

The candidate audit now records the narrow query set, source role, materiality, topic anchors, discovery provenance, evidence path, decision, and rejection reason. A network-free retrospective replay is available at:

`python helpers/current_context_retrospective_audit.py`

The retained replay is intentionally not a quota test. It only shows how the same saved candidates behave under the revised policy; the live proof requires a fresh discovery pass because the new query and feed adapters expand the candidate pool.
