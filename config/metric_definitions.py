def metric_help(key, fallback="Definition unavailable."):
    return METRIC_DEFINITIONS.get(key, fallback)


ADI_HELP = """
Measures the current intensity of observable AI capital deployment, physical construction, compute-supply realization, and power demand.

ADI = 0.25(Capital Deployment) + 0.25(Data-Center Construction) + 0.25(Compute Supply) + 0.25(Power Footprint)

At least 3 of 4 pillars must be valid; available static weights are renormalized. Scale: 0 to 100. Higher values indicate more intense development activity, not percentage completion.
"""


METRIC_DEFINITIONS = {
    "AI Economy Snapshot": (
        "**AI Equity Index:** Current strength and breadth of the selected AI equity universe.  \n"
        "**AI Development Intensity:** Current intensity of observable physical and capital AI development.  \n"
        "**Power Stress Index:** Electricity-demand pressure relative to available grid capacity and historical conditions.  \n"
        "**Concentration HHI:** Concentration of market value among the selected AI-related companies.  \n"
        "**Capital Stress:** Financing strain from cash flow, leverage, commitments, and contingent exposure."
    ),

    "AI Equity Index": """
Measures the current strength, breadth, valuation, and return dispersion of the selected AI equity universe.

AEI = mean(valid Sector AEI scores)

Sector AEI = 0.25(Relative Performance) + 0.25(Earnings-Yield Valuation) + 0.25(Momentum Breadth) + 0.25(Return Dispersion)

At least 3 of 4 sector factors and 75% of sector scores must be valid. Scale: 0 to 100; higher values indicate a stronger or more extended equity regime.
""",

    "AI Development Intensity": ADI_HELP,

    "Speculation Gap": """
Compares equity enthusiasm with observable AI development activity.

Speculation Gap = AEI - AI Development Intensity

Positive values indicate equities are running ahead of observable development; negative values indicate development is running ahead of equities. Scale: -100 to +100.
""",

    "Power Stress Index": """
Measures nonresidential electricity-demand pressure and grid headroom relative to reference conditions.

Power Stress = 2 × [0.40(Nonresidential Load) + 0.35(Grid Utilization) + 0.25(Capacity Response) - 50]

At least 2 of 3 components must be valid; available static weights are renormalized. Scale: -100 to +100; zero represents reference stress. Monthly source data produces a step series.
""",

    "Capital Stress": """
Measures filing-based financing strain from cash flow, book leverage, disclosed commitments, and contingent exposure.

Capital Stress = 2 × [0.30(Cash-Flow Strain) + 0.25(Book Leverage) + 0.30(Committed Burden) + 0.15(Contingent Exposure) - 50]

At least 3 of 4 components must be valid; available static weights are renormalized. Scale: -100 to +100; zero represents reference stress. Filing-driven inputs produce a quarterly step series.
""",

    "Concentration HHI": """
Measures how concentrated total market value is among the selected AI-related companies.

HHI = Σ(company market cap ÷ total market cap)²
HHI Score = clip[100 × (HHI - 0.01) ÷ (0.25 - 0.01), 0, 100]

Higher values indicate greater concentration.
""",

    "Economic Validation Gap": """
Compares capital-spending growth with company revenue growth and broader information-investment growth.

Economic Validation Gap = 100 × (CapEx growth - Revenue growth - Information-processing investment growth)

Positive values indicate capital spending is growing faster than the two validation measures combined. Scale: -100 to +100 after clipping.
""",

    "Liquidity Support Gap": """
Compares current sector trading pressure with support from broad financial conditions.

Liquidity Support Gap = mean(Sector Pressure) - clip[50 - 50(NFCI), 0, 100]

Positive values indicate trading pressure exceeds liquidity support; negative values indicate financial conditions are comparatively supportive. Scale: -100 to +100.
""",

    "AI-Industrial Growth Gap": """
Compares observable AI development activity with broad industrial growth.

AI-Industrial Growth Gap = AI Development Intensity - [50 + 50 × tanh((INDPRO YoY - 0.02) ÷ 0.05)]

Positive values indicate AI development is outpacing broad industrial growth; negative values indicate the reverse. Scale: -100 to +100.
""",

    "Purpose Statement": """
    This project seeks to quantify and distinguish genuine AI-driven economic transformation 
    from AI-driven capital speculation through use of novel and industry-standard measures 
    drawing from publicly available market and Federal Reserve economic data. 
    
    This project further seeks to understand the flow of liquidity in the AI economy and detect proximity to future market corrections. 
    
    """,

    "Current Sector Assessment": """
Summarizes sector crowding, movement, and the breadth of year-over-year financial deterioration.

Most Crowded = sector with max(current Pressure)
Fastest Mover = sector with max|ΔSector AEI + ΔPressure| over the fixed observation lookback
Biggest Risk = sector with max(100 × adverse financial signals ÷ valid financial signals)

A financial signal is adverse when FCF margin falls, net debt/EBITDA rises, or CapEx/OCF rises versus the prior comparable fiscal year. At least 50% of possible signals must be valid.
""",
}
