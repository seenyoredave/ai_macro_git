# AI Economic Research Platform

## Purpose

AI Macro tracks the development of AI as an economic instrument and its footprint in the US economy.

It examines who is building it, how the buildout is financed, where this growth occurs, and the physical capacity required to sustain it.

It measures deployment, economic returns, and the adaptation of businesses, workers, and institutions to AI integration.

Using publicly available data, the platform connects capital committed, capacity built, adoption achieved, and value realized.

## Dashboard

The interface has ten tabs:

- **AI Macro:** current conditions and the national AI development landscape
- **Market:** sector positioning, movement, concentration, fundamentals, and market performance
- **Finance:** deployment funding, corporate-bond conditions, Borrower Strain, Lender Strain, NFCI, and ANFCI
- **Data Center:** facility universe, development pipeline, capacity evidence, and geographic concentration
- **Compute:** domestic production, utilization, and announced U.S. manufacturing investment
- **Infrastructure:** direct AI construction, named supporting projects, inferred excess build, and wider system context
- **Energy:** demand, supply response, regional constraints, and projects waiting for power
- **Water:** national water accounting and facility-level AI water context
- **Adaptation:** AI reach, breadth, depth, operational commitment, value, and experience
- **Evidence:** metric definitions, retained source observations, field dictionaries, and source records

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run ai_macro.py
```

The application uses retained local data when live sources are unavailable. Manual refresh controls are available in the sidebar.

## Project structure

```text
ai_macro.py       Streamlit entry point and application state
analytics/        analytical engines and calculated data products
archive/          retained history readers and writers
benchmarks/       benchmark construction and normalization
config/           static universes, fields, series, and metric definitions
data/             retained source and derived data
factors/          factor normalization and weights
helpers/          maintenance and data-rebuild scripts
loaders/          live and retained data loading
rendering/        dashboard components, charts, tab renderers, and theme
water/            water-source parsing and ledger construction
```

## Maintenance scripts

```bash
python helpers/backfill_borrower_strain.py
python helpers/build_data_center_inventory.py
python helpers/build_infrastructure_ledger.py
python helpers/build_water_ledger.py
python helpers/rebuild_derived_history.py
```

These scripts rebuild retained datasets used by the application. They are not required for a normal dashboard launch.
