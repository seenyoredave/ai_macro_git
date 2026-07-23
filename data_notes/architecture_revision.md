# Architecture and universe revision

## Removed

- Put/call loader, session-state value, renderer arguments, archive writer/reader path, and historical CSV.
- Dead AMI, divergence, maturity-gauge, speculation-pressure, and old valuation-premium aliases.
- Unused benchmark universe JSON and unused normalization helpers.
- Unused Python dependencies: `edgartools`, `beautifulsoup4`, `lxml`, `matplotlib`, `pyarrow`, and `yahooquery`.

## Refactored

- Market price calculations: `loaders/market_prices.py`
- Fundamental statement calculations: `loaders/company_fundamentals.py`
- Market orchestration: `loaders/market_loader.py`
- Archive contracts: `archive/schemas.py`
- Generic archive persistence: `archive/archive.py`
- Headline snapshot rendering: five coherent section renderers in `helpers/macro_dashboard.py`

## Ownership contracts

- EDGAR quality, terminal-status interpretation, and archive eligibility live only in `loaders/edgar_loader.py`.
- The archive layer accepts a persistence-ready EDGAR DataFrame and performs no SEC-quality scoring.
- QQQ is the only active runtime benchmark. SPY and DIA remain configured but dormant.
- QQQ proxy weights preserve the retained fund-weight ratios and are normalized to sum to one.
- Raw YFinance, EDGAR, Census, and FRED observations remain separate from reproducible derived archives.
