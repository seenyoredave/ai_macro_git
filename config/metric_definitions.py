def metric_help(key, fallback="Definition unavailable."):
    return METRIC_DEFINITIONS.get(key, fallback)


ADI_HELP = """
Measures the current intensity of observable AI capital deployment, physical construction, compute-supply realization, and power demand.

ADI = 0.25(Capital Deployment) + 0.25(Data-Center Construction) + 0.25(Compute Supply) + 0.25(Power Footprint)

At least 3 of 4 pillars must be valid; available static weights are renormalized. Scale: 0 to 100.

**How to read it:** Higher scores indicate more intense observable development activity; lower scores indicate slower or less broadly confirmed development. The score measures activity intensity, not percentage completion or investment quality.
"""


METRIC_DEFINITIONS = {
    "AI Economy Snapshot": (
        "**AI Equity Index:** Strength and breadth of the selected AI equity universe.  \n"
        "**AI Development Intensity:** Observable physical and capital AI development.  \n"
        "**Power Stress Index:** Electricity-demand pressure relative to grid capacity and reference conditions.  \n"
        "**Concentration HHI:** Concentration of market value among the selected AI-related companies.  \n"
        "**Capital Stress:** Borrower-side financing strain from cash flow, leverage, commitments, and contingent exposure.  \n"
        "**Credit Intermediation Stress:** Lender-side stress across banks, public BDCs, and private-equity portfolio financing.  \n"
        "**Financial Conditions Confirmation:** An independent NFCI check on broad liquidity, leverage, funding, and market conditions.  \n\n"
        "**How to read it:** Each metric has its own scale and direction. Higher is not uniformly better; use the interpretation included with each metric."
    ),

    "AI Equity Index": """
Measures the current strength, breadth, valuation, and return dispersion of the selected AI equity universe.

AEI = mean(valid Sector AEI scores)

Sector AEI = 0.25(Relative Performance) + 0.25(Earnings-Yield Valuation) + 0.25(Momentum Breadth) + 0.25(Return Dispersion)

At least 3 of 4 sector factors and 75% of sector scores must be valid. Scale: 0 to 100.

**How to read it:** Higher scores indicate stronger or more extended equity conditions; lower scores indicate weaker conditions. AEI describes the current equity regime—it is not a valuation target or a forecast of future returns.
""",

    "AI Development Intensity": ADI_HELP,

    "Gap Scores": """
Gap Scores compare two related parts of the AI economy on a common -100 to +100 scale.

**How to read them:** A score near zero indicates relative alignment. Positive and negative values identify which side of each relationship is running ahead; the direction is defined in each score's helper. Larger absolute values indicate a wider divergence.
""",

    "Speculation Gap": """
Compares equity enthusiasm with observable AI development activity.

Speculation Gap = AEI - AI Development Intensity

**How to read it:** Positive values indicate equities are running ahead of observable development. Negative values indicate development is running ahead of equities. Zero indicates relative alignment. Scale: -100 to +100.
""",

    "Power Stress Index": """
Measures nonresidential electricity-demand pressure and grid headroom relative to reference conditions.

Power Stress = 2 × [0.40(Nonresidential Load) + 0.35(Grid Utilization) + 0.25(Capacity Response) - 50]

At least 2 of 3 components must be valid; available static weights are renormalized. Monthly source data produces a step series.

**How to read it:** Positive values indicate above-reference power-system stress; negative values indicate greater headroom or below-reference stress. Zero represents the model's reference condition. Scale: -100 to +100.
""",

    "Capital Stress": """
Measures borrower-side financing strain using cash flow, book leverage, disclosed commitments, and contingent exposure.

Capital Stress = 2 × [0.30(Cash-Flow Strain) + 0.25(Book Leverage) + 0.30(Committed Burden) + 0.15(Contingent Exposure) - 50]

Sources: standardized company fundamentals and a filing-backed ledger of disclosed contractual and contingent obligations.

At least 3 of 4 components must be valid; available static weights are renormalized. Filing-driven inputs produce a quarterly step series.

**How to read it:** Positive values indicate greater financing strain and less balance-sheet flexibility. Negative values indicate stronger cash-flow support, lower leverage, or lighter obligation burdens. Zero represents the model's reference condition. Scale: -100 to +100.
""",

    "Credit Intermediation Stress": """
Measures whether the U.S. financing channel is tightening or losing loss-absorbing capacity.

Credit Intermediation Stress = 2 × [0.30(Bank Credit Tightening) + 0.25(Bank Capital Strain) + 0.25(Private Credit Impairment) + 0.20(PE Portfolio Financing Strain) - 50]

Sources: Federal Reserve SLOOS for business-loan standards; Federal Reserve Z.1 for the aggregate regulatory Tier 1 capital ratio; public BDC filings for asset-weighted non-accruals; and SEC Form PF statistics for private-equity portfolio leverage and payment-in-kind borrowing.

At least 3 of 4 pillars must be valid; available static weights are renormalized. Quarterly and annual inputs produce a step series.

**How to read it:** Positive values indicate a tighter or more impaired financing channel. Negative values indicate easier credit conditions and stronger intermediation capacity. Zero represents the model's reference condition. Scale: -100 to +100.
""",

    "Financial Conditions Confirmation": """
Provides an independent, fast-moving check on whether broad U.S. financial conditions confirm or contradict the borrower- and lender-side stress metrics.

The strip reports the Chicago Fed National Financial Conditions Index, its current relationship to the long-run average, and its three-month direction. It is not blended into Capital Stress or Credit Intermediation Stress.

Source: Chicago Fed NFCI via FRED. Frequency: weekly.

**How to read it:** Negative NFCI values indicate financial conditions are looser than the long-run average; positive values indicate tighter conditions; zero is the long-run average. A rising three-month change means conditions are tightening, while a falling change means they are easing.
""",

    "Concentration HHI": """
Measures how concentrated total market value is among the selected AI-related companies.

HHI = Σ(company market cap ÷ total market cap)²
HHI Score = clip[100 × (HHI - 0.01) ÷ (0.25 - 0.01), 0, 100]

**How to read it:** Higher scores indicate that a smaller number of companies account for more of the universe's market value. Lower scores indicate broader distribution. Scale: 0 to 100.
""",

    "Economic Validation Gap": """
Compares capital-spending growth with company revenue growth and broader information-investment growth.

Economic Validation Gap = 100 × (CapEx growth - Revenue growth - Information-processing investment growth)

**How to read it:** Positive values indicate capital spending is growing faster than the two validation measures combined. Negative values indicate revenue and broader information investment are providing comparatively stronger validation. Zero indicates relative alignment. Scale: -100 to +100 after clipping.
""",


    "AI-Industrial Growth Gap": """
Compares observable AI development activity with broad industrial growth.

AI-Industrial Growth Gap = AI Development Intensity - [50 + 50 × tanh((INDPRO YoY - 0.02) ÷ 0.05)]

Source: AI Development Intensity and Federal Reserve industrial-production data.

**How to read it:** Positive values indicate AI development is outpacing broad industrial growth. Negative values indicate industrial growth is running ahead of AI development. Zero indicates relative alignment. Scale: -100 to +100.
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

**How to read it:** These cards identify relative leaders within the selected universe. They are descriptive comparisons, not buy, sell, or timing recommendations.
""",
}
