# Current Context Clump B — shared snapshot, Read binding, and Evidence lineage

## Reader contract

Current Context is a small, high-confidence context layer rather than a news
feed. Public Reader mode may refresh this layer through a globally shared
approximately 15-minute cache. Retained analytical datasets remain immutable
and are never refreshed by a viewer request.

The completed Current Context packet receives a snapshot identifier. Every
platform Read is bound to that exact packet. Readers inside the same cache
window therefore receive the same Context + Read pair; the next cache window may
advance both together.

Developer ordinary startup remains retained-only. Explicit `Refresh Current
Context` continues to exist for audit and owner review.

## Recent Developments language

Reader-facing copy does not lead with publisher names. Numbered citations carry
source identity. Each item follows the same editorial grammar as the strongest
retained examples:

1. state the development directly;
2. explain why it materially changes interpretation of that domain's evidence.

Generic suffixes such as `The development may change...` are prohibited.
Week-ahead previews, calendars, listicles, generic market recaps, and merely
adjacent transactions are not completed developments.

Market and Finance retain their high evidence threshold. Finance requires a
specific AI/technology/infrastructure connection unless an item changes a
system-wide financing condition.

## Evidence lineage

The Evidence tab distinguishes retained analytical claims from Recent
Developments and traces the visible evidence source and discovery provenance.
Tier-2 discovery remains internal provenance only; the curator is never promoted
to evidence merely because it surfaced a lead.

Search and evidence-layer filters narrow the lineage view without changing the
underlying evidence contract.
