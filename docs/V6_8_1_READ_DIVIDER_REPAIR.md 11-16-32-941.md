# v6.8.1 Read-divider repair

## Purpose

Restore a single, consistent horizontal divider between every domain Read and the analytical content that follows it.

## Implementation

- `rendering/read_markup.py` now emits `rm-read-section-divider` from the shared Read component.
- `rendering/theme.css` owns the divider color, width, and spacing through the platform border token.
- The first post-Read section in every Read-bearing tab uses the `first=True` section contract so the universal divider is not duplicated.
- Later analytical sections retain their existing section dividers.

## Coverage

The contract covers all twelve Read-bearing tabs:

1. AI Macro
2. Market
3. Finance
4. Compute
5. Data Centers
6. Connectivity
7. Power
8. Grid & Storage
9. Water
10. Adoption
11. Workforce
12. Economic Outcomes

Evidence does not currently render a domain Read and is therefore outside this specific contract.

## Regression protection

`helpers/read_divider_smoke_test.py` verifies:

- one divider is emitted by the shared Read markup;
- the divider uses the shared visual-system style;
- every Read-bearing tab still routes through `render_domain_read`;
- every first post-Read section suppresses its own top border.
