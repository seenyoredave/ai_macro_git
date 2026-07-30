def metric_help(key, fallback="Definition unavailable."):
    return METRIC_DEFINITIONS.get(key, fallback)


ADI_HELP = """
Measures the current intensity of observable AI capital deployment, physical construction, compute-supply realization, and power demand.

ADI = 0.25(Capital Deployment) + 0.25(Data-Center Construction) + 0.25(Compute Supply) + 0.25(Power Footprint)

At least 3 of 4 pillars must be valid; available static weights are renormalized. Scale: 0 to 100.

**How to read it:** Higher scores indicate more intense observable development activity; lower scores indicate slower or less broadly confirmed development. The score measures activity intensity, not percentage completion or investment quality.
"""


METRIC_DEFINITIONS = {

    "AI Equity Index": """
Measures the current valuation, relative performance, and market breadth of the selected AI equity universe.

AEI = mean(valid Sector AEI scores)

Sector AEI = 0.40(Forward EBIT-Yield Valuation) + 0.35(1Y Relative Return) + 0.25(Market Breadth)

All 3 sector factors and at least 75% of sector scores must be valid. The forward EBIT-yield factor retains negative aggregate forward EBIT as economically informative. Scale: 0 to 100.

**How to read it:** Higher scores indicate stronger or more extended equity conditions; lower scores indicate weaker conditions. AEI describes the current equity regime—it is not a valuation target or a forecast of future returns.
""",

    "AI Development Intensity": ADI_HELP,


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


    "Power Capacity Gap": """
Compares observable AI deployment pressure with the measured national response of the electric-power system.

Deployment Pressure = 0.60(Data-Center Construction) + 0.40(Capital Deployment)

Power-System Response = 0.60(Delivered Electric-Power Growth) + 0.40(Installed Electric-Power Capacity Growth)

Power Capacity Gap = Deployment Pressure - Power-System Response

The deployment leg reuses the two ADI pillars most directly associated with physical power demand. The response leg requires both actual electric-power output growth and installed-capacity growth, reducing reliance on nameplate additions alone. All four inputs are normalized independently to 0–100 before comparison.

**How to read it:** Positive values indicate AI deployment pressure is advancing faster than the measured national power-system response. Negative values indicate power delivery and capacity growth are advancing faster than deployment pressure. Zero indicates relative alignment. Scale: -100 to +100.

**Scope limitation:** This is a national response proxy, not a regional resource-adequacy model. It does not directly capture transmission constraints, interconnection queues, local congestion, generation firmness, or the differing reliability characteristics of capacity types.
""",


    "Internal Funding Coverage": """
**IFC = OCF / CapEx**

Above 1.0x means current operations cover current CapEx; below 1.0x means reserves or outside financing are required.
""",

    "Cash Reserve Coverage": """
**CRC = Cash / TTM CapEx**

Shows how many years of current capital spending could be covered from existing liquid reserves alone.
""",

    "Debt Financing Pulse": """
**DFP = Δ₁₂ₘ Total Debt / TTM CapEx**

Positive values indicate debt expanded relative to the current buildout rate; negative values indicate debt repayment.
""",

    "Forward Commitment Load": """
**FCL = Forward Commitments / TTM CapEx**

Higher values mean more future spending is contractually locked in relative to the current annual buildout rate.
""",

    "Lender Strain": """
Measures deterioration in the U.S. financing channel's behavior, asset quality, and loss-absorbing capacity across bank and nonbank channels.

Bank Channel = 0.50(Bank Credit Tightening) + 0.50(Bank Capital Strain)

Nonbank Channel = 0.50(Private Credit Impairment) + 0.50(PE Portfolio Financing Strain)

Lender Strain = 2 × [0.50(Bank Channel) + 0.50(Nonbank Channel) - 50]

Sources: Federal Reserve SLOOS for business-loan standards; Federal Reserve Z.1 for the aggregate regulatory Tier 1 capital ratio; public BDC filings for asset-weighted non-accruals; and SEC Form PF statistics for private-equity portfolio leverage and payment-in-kind borrowing.

Each pillar is normalized against its own available history when sufficient observations exist; otherwise an explicit anchored scale is used. At least 3 of 4 pillars and at least one pillar from each channel must be valid. Missing weight is renormalized only within its channel. Quarterly and annual inputs produce a step series.

**How to read it:** Positive values indicate greater intermediation strain: tighter lending behavior, weaker capital capacity, or more impaired private credit. Negative values indicate stronger intermediation capacity and easier credit transmission. Zero represents the model's reference condition. Scale: -100 to +100.
""",

    "Financial Conditions Confirmation": """
Provides an independent, fast-moving check on whether broad U.S. financial conditions confirm or contradict borrower and lender strain.

The strip reports the Chicago Fed National Financial Conditions Index, its current relationship to the long-run average, and its three-month direction. It is not blended into Borrower Strain or Lender Strain.

Source: Chicago Fed NFCI and ANFCI via FRED. Frequency: weekly. NFCI remains the headline reading; ANFCI is contextual only.

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

Identify divergences, constraints, and financial pressures that may increase vulnerability to market corrections using publicly available market, company-filing, construction, power, and Federal Reserve data.
    """,

    "Forward EV/EBIT": """
Sector Forward EV/EBIT is calculated for the profitable operating cohort as a ratio of sums:

Profitable-Cohort Forward EV/EBIT = Σ Enterprise Valueᵢ ÷ Σ Forward EBITᵢ, for Forward EBITᵢ > 0

The product requires at least five companies with valid forward-EBIT data, at least three profitable companies, and at least 60% enterprise-value data coverage. It is not an average of company multiples and does not approach an asymptote when an individual company's EBIT is close to zero.

Loss-making companies are not discarded from the analytical system. Their enterprise-value footprint is reported separately through Loss-Making EV Share, while the full-sector Forward EBIT Yield used inside AEI continues to include both positive and negative forward EBIT.

**How to read it:** This multiple measures what the market is paying for the sector's profitable operating base. It should be interpreted together with Loss-Making EV Share and the full-sector AEI valuation factor.
""",

    "Loss-Making EV Share": """
Measures the share of valid sector enterprise value represented by companies with non-positive forward EBIT.

Loss-Making EV Share = Σ Enterprise Value₍Forward EBIT ≤ 0₎ ÷ Σ Enterprise Value₍valid Forward EBIT₎

**How to read it:** A higher share means more of the sector's market value is currently unsupported by positive forward operating earnings. The measure preserves the economic significance of loss-making companies without forcing their near-zero EBIT denominators into an unstable signed EV/EBIT multiple.
""",

    "Earnings Support": """
Compares trailing sector repricing with the valuation of the sector's profitable operating base.

Earnings Support = 1Y Return ÷ Profitable-Cohort Forward EV/EBIT

X-axis: profitable-cohort Forward EV/EBIT on a bounded positive-log display scale; raw multiples remain available in hover.  
Y-axis: trailing one-year return.  
Marker color: sector AI Equity Index.  
Marker size: Loss-Making EV Share.

**How to read it:** The relationship asks whether realized repricing is accompanied by prospective operating-earnings support. Strong returns attached to lower profitable-cohort multiples imply greater earnings support; large markers identify sectors where a greater share of enterprise value remains loss-making.
""",

    "Speculative Load": """
Measures abnormal trading pressure relative to the sector's earnings-supported, broad-based equity strength.

Speculative Load = Trading Pressure ÷ Sector AI Equity Index

Sector AEI = 0.40(Forward EBIT-Yield Valuation) + 0.35(1Y Relative Return) + 0.25(Market Breadth)

X-axis: sector AI Equity Index.  
Y-axis: Trading Pressure.  
Marker color: profitable-cohort Forward EV/EBIT on the same bounded positive-log display scale used by Earnings Support; raw values remain available in hover.  
Marker size: Loss-Making EV Share.  
The diagonal is the Pressure = AEI reference line.

**How to read it:** Values below 1.0 indicate that sector equity support exceeds abnormal trading pressure. Values above 1.0 indicate that pressure exceeds the sector's market foundation. Larger markers identify sectors where more enterprise value lacks positive forward operating earnings.
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
