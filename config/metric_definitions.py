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
Measures the current valuation, relative performance, and market breadth of the selected AI equity universe.

AEI = mean(valid Sector AEI scores)

Sector AEI = 0.40(Forward EBIT-Yield Valuation) + 0.35(Relative Performance) + 0.25(Market Breadth)

All 3 sector factors and at least 75% of sector scores must be valid. Scale: 0 to 100.

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
Measures borrower-side financing strain using cash flow, debt capacity, disclosed commitments, and contingent exposure.

Capital Stress = 2 × [0.30(Cash-Flow Strain) + 0.25(Debt Capacity Stress) + 0.30(Committed Burden) + 0.15(Contingent Exposure) - 50]

Sources: standardized company fundamentals and a filing-backed ledger of disclosed contractual and contingent obligations.

Debt Capacity Stress uses net debt/EBITDA for profitable companies, net debt/revenue with a stress floor for negative-EBITDA borrowers, and a lower leverage score for negative-EBITDA companies that retain net cash.

At least 3 of 4 components must be valid; available static weights are renormalized. Filing-driven inputs produce a quarterly step series.

**How to read it:** Positive values indicate greater financing strain and less balance-sheet flexibility. Negative values indicate stronger cash-flow support, lower leverage, or lighter obligation burdens. Zero represents the model's reference condition. Scale: -100 to +100.
""",

    "Credit Intermediation Stress": """
Measures whether the U.S. financing channel is tightening or losing loss-absorbing capacity across bank and nonbank channels.

Bank Channel = 0.50(Bank Credit Tightening) + 0.50(Bank Capital Strain)

Nonbank Channel = 0.50(Private Credit Impairment) + 0.50(PE Portfolio Financing Strain)

Credit Intermediation Stress = 2 × [0.50(Bank Channel) + 0.50(Nonbank Channel) - 50]

Sources: Federal Reserve SLOOS for business-loan standards; Federal Reserve Z.1 for the aggregate regulatory Tier 1 capital ratio; public BDC filings for asset-weighted non-accruals; and SEC Form PF statistics for private-equity portfolio leverage and payment-in-kind borrowing.

Each pillar is normalized against its own available history when sufficient observations exist; otherwise an explicit anchored scale is used. At least 3 of 4 pillars and at least one pillar from each channel must be valid. Missing weight is renormalized only within its channel. Quarterly and annual inputs produce a step series.

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
Compares enterprise-software capital-deployment growth with realized company revenue growth and real economy-wide information-processing investment growth.

Deployment Score = normalized aggregate year-over-year CapEx growth

Validation Score = 0.50(normalized aggregate revenue growth) + 0.50(normalized real information-processing investment growth)

Economic Validation Gap = Deployment Score - Validation Score

Company growth uses ratio-of-sums aggregation. All three legs use year-over-year periods and are normalized independently. Empirical percentiles are used only when enough distinct history exists; otherwise transparent anchored scales are used.

**How to read it:** Positive values indicate capital deployment is running ahead of realized revenue and broader investment validation. Negative values indicate validation is keeping pace with or exceeding deployment. Zero indicates relative alignment. Scale: -100 to +100.
""",


    "AI-Industrial Growth Gap": """
Compares observable AI development activity with broad industrial growth.

AI-Industrial Growth Gap = AI Development Intensity - [50 + 50 × tanh((INDPRO YoY - 0.02) ÷ 0.05)]

Source: AI Development Intensity and Federal Reserve industrial-production data.

**How to read it:** Positive values indicate AI development is outpacing broad industrial growth. Negative values indicate industrial growth is running ahead of AI development. Zero indicates relative alignment. Scale: -100 to +100.
""",

    "Purpose Statement": """
Measure whether AI-related market enthusiasm is supported by observable economic development, corporate financial performance, and resilient financing conditions.

Identify divergences, constraints, and financial stresses that may increase vulnerability to market corrections using publicly available market, company-filing, construction, power, and Federal Reserve data.
    """,

    "AI Sector Positioning Map": """
Compares sector valuation with trailing market performance.

X-axis: Forward EV/EBIT.  
Y-axis: one-year return.  
Marker color: sector AI Equity Index.  
Marker size: Trading Pressure.  
Dotted lines mark the current cross-sector medians.

**How to read it:** The map shows where each sector sits relative to its peers on price and performance. It is a cross-sectional positioning view, not a forecast or recommendation.
""",

    "AI Sector Rotation Matrix": """
Compares each sector's current AI Equity Index with its Trading Pressure score.

X-axis: sector AI Equity Index.  
Y-axis: Trading Pressure.  
Marker color: Forward EV/EBIT.  
Marker size: absolute one-year return.  
Dotted lines mark the current cross-sector medians.

**How to read it:** The matrix separates stronger or weaker equity regimes from more or less crowded trading conditions. A sector's quadrant describes its current relative position, not its future direction.
""",

    "Current Sector Assessment": """
Summarizes sector crowding, movement, and the breadth of year-over-year financial deterioration.

**How to read it:** These cards identify relative leaders within the selected universe. They are descriptive comparisons, not buy, sell, or timing recommendations. Each card has its own helper describing the selection rule.
""",

    "Most Crowded": """
Identifies the sector with the highest current Trading Pressure score.

Trading Pressure combines forward operating-earnings valuation stretch, price extension, momentum acceleration, volatility expansion, and abnormal volume.

**How to read it:** A sector can be the most crowded because investors are paying a rich valuation, prices are extended, trading activity is unusually intense, or several of those conditions occur together. This is a relative ranking within the selected universe, not proof that the sector must decline.
""",

    "Fastest Mover": """
Identifies the sector with the largest combined change in AEI and Trading Pressure over the available fixed lookback.

Sector Movement = √[(ΔSector AEI)² + (ΔPressure)²]

The root-sum-of-squares calculation prevents opposing changes from cancelling and keeps movement on a nonnegative scale.

**How to read it:** A larger value means the sector's market regime is changing more rapidly than its peers, regardless of whether that change is favorable or unfavorable. Review the sector's AEI and Pressure direction to understand what moved.
""",

    "Biggest Risk": """
Identifies the sector with the broadest year-over-year deterioration across company fundamentals.

Risk Breadth = 100 × adverse financial signals ÷ valid financial signals

Signals are adverse when FCF margin falls, net debt/EBITDA rises, or CapEx/OCF rises versus the prior comparable fiscal year. At least 50% of possible signals must be valid.

**How to read it:** A higher breadth score means deterioration is affecting more of the sector's available financial signals. It measures the spread of weakening fundamentals, not the absolute probability of failure or the magnitude of any single company's risk.
""",
}
