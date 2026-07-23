# Data flow map

```text
ai_macro.py
│
├── Market universe
│   ├── YFinance prices, fundamentals, price history, volume history
│   ├── EDGAR standardized fundamentals
│   └── Sector dataframe + basket tiering
│
├── Macro and buildout sources
│   ├── FRED macro and power series
│   ├── Census private data-center construction workbook
│   └── Curated SEC filing commitment ledger
│
├── Sector analytics
│   ├── Factor Engine
│   │   ├── Relative Performance
│   │   ├── Earnings-Yield Discount
│   │   ├── Momentum Breadth
│   │   └── Dispersion
│   ├── Sector AEI Score
│   └── Trading Pressure v2
│       ├── Valuation Stretch
│       ├── 200D Price Extension
│       ├── Momentum Acceleration
│       ├── Volatility Expansion
│       └── Volume Activity
│
├── Macro analytics
│   ├── AI Equity Index
│   ├── AI Development Intensity
│   │   ├── Capital Deployment
│   │   ├── Data Center Construction
│   │   ├── Compute Supply Realization
│   │   └── Power Footprint
│   ├── Speculation Gap = AEI - ADI
│   ├── Power Stress Index
│   ├── Capital Stress
│   └── Concentration HHI
│
├── Archive layer
│   ├── Current observations only
│   ├── Metric-version columns
│   ├── No zero-filling of missing values
│   └── Compatible last-valid fallback for display continuity
│
└── Streamlit render
    ├── Gauge + history panels
    ├── ADI component detail
    ├── Prominent Capital Stress panel + subcomponents
    ├── Gap metrics
    ├── Sector assessment and positioning charts
    └── Collapsible Sector, FRED, and EDGAR tables
```
