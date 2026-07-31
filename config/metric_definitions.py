"""Plain-language definitions for the dashboard's actual analytical products."""


def metric_help(key, fallback="Definition unavailable."):
    return METRIC_DEFINITIONS.get(key, fallback)


ADI_HELP = """
Measures observable AI capital deployment, physical construction, compute-supply realization, and power demand.

AI Development Intensity = 0.25(Capital Deployment) + 0.25(Data-Center Construction) + 0.25(Compute Supply) + 0.25(Power Footprint)

At least three of the four pillars must be valid. Available weights are renormalized. Scale: 0 to 100.

**How to read it:** Higher values indicate more intense observable development activity. The score measures activity, not project completion or investment quality.
"""


METRIC_DEFINITIONS = {
    "AI Equity Index": """
Measures valuation, relative performance, and market breadth across the selected AI equity universe.

AI Equity Index = mean(valid Sector AI Equity Index scores)

Sector AI Equity Index = 0.40(Forward EBIT-Yield Valuation) + 0.35(1Y Relative Return) + 0.25(Market Breadth)

All three sector factors and at least 75% of sector scores must be valid. Scale: 0 to 100.

**How to read it:** Higher values indicate stronger or more extended equity conditions. Lower values indicate weaker conditions. This is a regime reading, not a price target or return forecast.
""",

    "AI Development Intensity": ADI_HELP,

    "Speculation Gap": """
Compares equity enthusiasm with observable AI development activity.

Speculation Gap = AI Equity Index - AI Development Intensity

**How to read it:** Positive values indicate equities are running ahead of observable development. Negative values indicate development is running ahead of equities. Scale: -100 to +100.
""",

    "Economic Validation Gap": """
Compares enterprise-software capital-deployment growth with realized company revenue growth and real economy-wide information-processing investment growth.

Deployment Score = normalized aggregate year-over-year CapEx growth

Validation Score = 0.50(normalized aggregate revenue growth) + 0.50(normalized real information-processing investment growth)

Economic Validation Gap = Deployment Score - Validation Score

Company growth uses ratio-of-sums aggregation. All legs use year-over-year periods and are normalized independently.

**How to read it:** Positive values indicate deployment is running ahead of realized economic validation. Negative values indicate validation is keeping pace with or exceeding deployment. Scale: -100 to +100.
""",

    "AI-Industrial Growth Gap": """
Compares observable AI development activity with broad industrial growth.

AI-Industrial Growth Gap = AI Development Intensity - normalized Industrial Production growth

Source: AI Development Intensity and Federal Reserve industrial-production data.

**How to read it:** Positive values indicate AI development is outpacing broad industrial growth. Negative values indicate industrial growth is running ahead of AI development. Scale: -100 to +100.
""",

    "Power Stress Index": """
Measures pressure acting on the power system through nonresidential load, grid utilization, and capacity response.

Power Stress = 2 × [0.40(Nonresidential Load) + 0.35(Grid Utilization) + 0.25(Capacity Response) - 50]

At least two of the three components must be valid. Available weights are renormalized. Scale: -100 to +100.

**How to read it:** Positive values indicate above-reference power-system stress. Negative values indicate greater headroom or below-reference stress.
""",

    "Power Capacity Gap": """
Compares observable AI deployment pressure with the measured national response of the electric-power system.

Deployment Pressure = 0.60(Data-Center Construction) + 0.40(Capital Deployment)

Power-System Response = 0.60(Delivered Electric-Power Growth) + 0.40(Installed Electric-Power Capacity Growth)

Power Capacity Gap = Deployment Pressure - Power-System Response

**How to read it:** Positive values indicate deployment pressure is advancing faster than measured power-system response. Negative values indicate output and capacity are advancing faster than deployment pressure. Scale: -100 to +100.

**Scope:** This is a national response proxy. It does not directly measure regional transmission constraints, interconnection queues, local congestion, or firm deliverable capacity.
""",

    "Sector Basket Concentration": """
Measures market-value concentration inside each selected sector basket while controlling for differences in valid constituent count.

Raw HHI = Σ(company market-cap share)²

Adjusted HHI = 100 × (Raw HHI − 1/N) ÷ (1 − 1/N)

N is the number of companies with valid positive market capitalization. A value of 0 represents an equal-weight basket of the same size; 100 represents single-company concentration.

**How to read it:** Higher values indicate that sector-basket market value is carried by fewer companies. The metric describes the configured basket, not the entire economic sector. Rankings require at least three valid companies and 60% market-cap coverage.
""",

    "Henry Hub Natural Gas": """
Weekly Henry Hub natural-gas spot price from the U.S. Energy Information Administration through FRED.

The card reports the latest price and four-week percentage change.

**How to read it:** Rising prices indicate a more expensive fuel environment for gas-fired generation. The reading does not measure regional pipeline constraints or utility hedging.
""",

    "WTI Crude Oil": """
Weekly West Texas Intermediate crude-oil spot price from the U.S. Energy Information Administration through FRED.

The card reports the latest price and four-week percentage change.

**How to read it:** Oil has a limited direct role in U.S. utility-scale generation, but it affects backup generation, construction, transportation, and the broader energy-cost environment.
""",

    "Coal Production": """
Monthly Federal Reserve industrial-production index for U.S. coal mining.

The card reports the latest index and three-month percentage change.

**How to read it:** The reading tracks coal-supply momentum. It does not measure inventories, plant economics, or regional availability.
""",

    "Renewable Power Output": """
Monthly Federal Reserve industrial-production index for renewable and other electric-power generation.

The card reports the latest index and three-month percentage change.

**How to read it:** The reading tracks renewable-output momentum. It does not distinguish generation technology, location, storage support, or firmness.
""",

    "Commercial Electricity Price": """
Monthly U.S. average retail electricity price paid by commercial customers, reported in cents per kilowatt-hour by the U.S. Energy Information Administration.

**How to read it:** The series provides downstream electricity-cost context. It is a national customer-class average and does not represent a contracted hyperscale data-center tariff, wholesale power price, congestion charge, or site-specific delivered cost.
""",

    "Industrial Electricity Price": """
Monthly U.S. average retail electricity price paid by industrial customers, reported in cents per kilowatt-hour by the U.S. Energy Information Administration.

**How to read it:** The series provides downstream electricity-cost context. It is a national customer-class average and does not represent a contracted hyperscale data-center tariff, wholesale power price, congestion charge, or site-specific delivered cost.
""",

    "Electric Power Output": """
Federal Reserve monthly industrial-production index for electric-power generation, transmission, and distribution. Index base: 2017 = 100.

**How to read it:** Higher values indicate more delivered electric-power activity relative to the 2017 base. The chart is a national production measure, not a regional adequacy reading.
""",

    "Electric Power Capacity": """
Federal Reserve monthly capacity index for electric-power generation, transmission, and distribution. Index base: 2017 = 100.

**How to read it:** Higher values indicate a larger measured national power-system capacity base. The index does not distinguish firm from intermittent capacity.
""",

    "Electric Power Capacity Utilization": """
Federal Reserve monthly capacity-utilization rate for electric-power generation, transmission, and distribution.

Capacity Utilization = Electric Power Output ÷ Electric Power Capacity

**How to read it:** Higher utilization means more of the measured capacity base is in use. It is not the same as a regional reserve margin.
""",

    "Internal Funding Coverage": """
Internal Funding Coverage = Operating Cash Flow ÷ Trailing-Twelve-Month CapEx

**How to read it:** Above 1.0x means current operations cover current capital spending. Below 1.0x means reserves or outside financing are required.
""",

    "Cash Reserve Runway": """
Cash Reserve Runway = Cash and Equivalents ÷ Trailing-Twelve-Month CapEx

**How to read it:** The result is expressed in years. It estimates how long current liquid reserves could fund the present capital-spending rate if no additional cash were generated.
""",

    "Debt Financing Pulse": """
Debt Financing Pulse = Twelve-Month Change in Total Debt ÷ Trailing-Twelve-Month CapEx

**How to read it:** Positive values indicate debt expanded relative to the current buildout rate. Negative values indicate net debt repayment.
""",

    "Forward Commitment Load": """
Forward Commitment Load = Disclosed Forward Commitments ÷ Trailing-Twelve-Month CapEx

**How to read it:** Higher values indicate that more future spending is contractually committed relative to the current annual buildout rate.
""",

    "Corporate Bond Market Distress": """
The New York Fed Corporate Bond Market Distress Index combines indicators of primary-market issuance and pricing, secondary-market pricing and liquidity, and the relationship between traded and nontraded bonds.

The market index covers investment-grade and high-yield corporate bonds.

**How to read it:** Higher values indicate more impaired corporate-bond market functioning and more difficult access to public debt capital. The index measures market functioning, not expected bond returns or issuer default probability.
""",

    "Investment-Grade Bond Distress": """
The investment-grade segment of the New York Fed Corporate Bond Market Distress Index.

**How to read it:** Higher values indicate greater impairment in issuance, pricing, trading, or liquidity for investment-grade corporate bonds. This is the public-debt channel most relevant to large established issuers.
""",

    "High-Yield Bond Distress": """
The high-yield segment of the New York Fed Corporate Bond Market Distress Index.

**How to read it:** Higher values indicate greater impairment in issuance, pricing, trading, or liquidity for below-investment-grade corporate bonds. This segment is more relevant to weaker and more financing-dependent issuers.
""",

    "Borrower Strain": """
Measures deterioration in the selected borrower cohort's cash generation, debt capacity, and ability to absorb disclosed obligations.

Borrower Strain = 0.30(Cash Flow Strain) + 0.25(Debt Capacity Strain) + 0.30(Committed Burden) + 0.15(Contingent Exposure)

At least three of the four components must be valid. The internal 0–100 adverse-condition score is centered to a -100 to +100 display scale.

**How to read it:** Positive values indicate greater deterioration in financial condition or capacity. Negative values indicate stronger cash flow, debt capacity, and obligation coverage.
""",

    "Lender Strain": """
Measures deterioration in the U.S. financing channel's behavior, asset quality, and loss-absorbing capacity across bank and nonbank lenders.

Bank Channel = 0.50(Bank Credit Tightening) + 0.50(Bank Capital Strain)

Nonbank Channel = 0.50(Private Credit Impairment) + 0.50(PE Portfolio Financing Strain)

Lender Strain = 2 × [0.50(Bank Channel) + 0.50(Nonbank Channel) - 50]

At least three of four pillars and at least one pillar from each channel must be valid. Scale: -100 to +100.

**How to read it:** Positive values indicate tighter lending behavior, weaker lender capacity, or greater impairment. Negative values indicate stronger lending capacity and easier credit availability.
""",

    "NFCI": """
The Chicago Fed National Financial Conditions Index summarizes U.S. money-market, debt-market, equity-market, and banking conditions.

**How to read it:** Positive values indicate conditions tighter than the long-run average. Negative values indicate looser conditions. The three-month change shows whether conditions are tightening or easing.
""",

    "ANFCI": """
The Chicago Fed Adjusted National Financial Conditions Index removes the component of financial conditions associated with current economic conditions.

**How to read it:** Positive values indicate tighter-than-average financial conditions after the adjustment; negative values indicate looser conditions. ANFCI is contextual and is not blended into Borrower Strain or Lender Strain.
""",

    "Sector AI Equity Index": """
Measures valuation, one-year relative performance, and market breadth within one sector.

Sector AI Equity Index = 0.40(Forward EBIT-Yield Valuation) + 0.35(1Y Relative Return) + 0.25(Market Breadth)

All three factors are required. Scale: 0 to 100.

**How to read it:** Higher values indicate stronger or more extended sector equity conditions. Lower values indicate weaker conditions.
""",

    "Trading Pressure": """
Measures abnormal valuation and trading pressure within a sector.

Trading Pressure = 0.25(Valuation Stretch) + 0.25(Price Extension) + 0.20(Momentum Acceleration) + 0.15(Volatility Expansion) + 0.15(Volume Activity)

At least three of the five components must be valid. Available weights are renormalized. Scale: 0 to 100.

**How to read it:** Higher values indicate more valuation stretch, price extension, momentum acceleration, volatility expansion, or abnormal volume. It is not a forecast that the sector must decline.
""",

    "Forward EV/EBIT": """
Measures the valuation of the sector's profitable operating cohort as a ratio of sums.

Forward EV/EBIT = Σ Enterprise Value ÷ Σ Forward EBIT, for companies with positive Forward EBIT

The calculation requires at least five companies with valid forward-EBIT data, at least three profitable companies, and at least 60% enterprise-value data coverage.

**How to read it:** Higher values indicate a richer valuation of the profitable operating base. Interpret it together with Loss-Making EV Share.
""",

    "Loss-Making EV Share": """
Measures the share of valid sector enterprise value represented by companies with non-positive forward EBIT.

Loss-Making EV Share = Σ EV for companies with Forward EBIT ≤ 0 ÷ Σ EV for companies with valid Forward EBIT

**How to read it:** Higher values indicate that more sector enterprise value is unsupported by positive forward operating earnings.
""",

    "Earnings Support": """
Compares trailing sector repricing with the valuation of the sector's profitable operating base.

Earnings Support = 1Y Return ÷ Profitable-Cohort Forward EV/EBIT

**How to read it:** Strong returns attached to lower profitable-cohort multiples imply greater earnings support. The chart also shows Sector AI Equity Index and Loss-Making EV Share.
""",

    "Speculative Load": """
Compares abnormal trading pressure with the sector's equity foundation.

Speculative Load = Trading Pressure ÷ Sector AI Equity Index

**How to read it:** Values below 1.0 indicate that sector equity support exceeds abnormal trading pressure. Values above 1.0 indicate that pressure exceeds the sector's current market foundation.
""",

    "Sector Movement": """
Measures the combined change in Sector AI Equity Index and Trading Pressure over the available fixed lookback.

Sector Movement = √[(ΔSector AI Equity Index)² + (ΔTrading Pressure)²]

**How to read it:** Larger values indicate faster change in the sector's market regime. The measure is nonnegative; inspect the underlying changes to determine direction.
""",

    "Risk Breadth": """
Measures how broadly company fundamentals are deteriorating within a sector.

Risk Breadth = 100 × Adverse Financial Signals ÷ Valid Financial Signals

Signals are adverse when free-cash-flow margin falls, net debt/EBITDA rises, or CapEx/operating cash flow rises versus the prior comparable fiscal year. At least 50% of possible signals must be valid.

**How to read it:** Higher values indicate that deterioration is affecting more of the sector's available financial signals. It does not estimate failure probability.
""",

    "Data Center Construction": """
Measures the seasonally adjusted annual rate of private construction spending on data-center facilities.

**Source:** U.S. Census Bureau, Value of Construction Put in Place.

**How to read it:** Higher values indicate a larger active construction footprint. These spending data do not measure facility size, construction stage, compute capacity, power demand, or utilization, and they exclude announced projects until spending is put in place.
""",

    "Evidence-Graded Facility Registry": """
Combines the observed IM3/OpenStreetMap facility footprint with explicitly curated project records supported by primary evidence.

The registry keeps square footage, planned data-center capacity, contracted utility capacity, energized capacity, annual electricity consumption, onsite generation, water withdrawal, water consumption, WUE, cooling system, and water source as separate fields. Missing values remain missing and are never inferred from another field.

**How to read it:** Bubble size uses one homogeneous selected metric. Outlined markers indicate records where that metric is unavailable. The registry is not a complete census of U.S. data centers.
""",

    "Computer, Electronic & Electrical Manufacturing Construction": """
Measures private construction spending on computer, electronic, and electrical manufacturing facilities.

**Source:** U.S. Census Bureau, Value of Construction Put in Place.

**How to read it:** The category includes semiconductor-fab construction but is not semiconductor-exclusive. It is a broad manufacturing-buildout measure, not a pure fab series.
""",

    "Communication Construction": """
Measures private construction spending on communication infrastructure.

**How to read it:** The series provides broad supporting-infrastructure context. It does not identify the share attributable to AI or data centers.
""",

    "Public Highway and Street Construction": """
Measures the seasonally adjusted annual rate of public highway and street construction spending.

**How to read it:** The series describes broad transport-system investment. It is not allocated specifically to AI-related projects.
""",

    "Public Transportation Construction": """
Measures the seasonally adjusted annual rate of public transportation construction spending.

**How to read it:** The series provides supporting-infrastructure context and is not an AI-attributed measure.
""",

    "Public Water Supply Construction": """
Measures the seasonally adjusted annual rate of public water-supply construction spending.

**How to read it:** The series provides broad supporting-system context. It is capital spending on public water infrastructure, not facility withdrawal, consumptive use, legal access, or AI-attributed investment.
""",


    "Current Business AI Use": """
Share of U.S. employer businesses reporting that they used artificial intelligence in at least one business function during the prior two weeks.

**Source:** U.S. Census Bureau, Business Trends and Outlook Survey.

**How to read it:** This is a survey measure of adoption. It does not measure intensity of use, productivity, return on investment, or labor effects.
""",

    "Expected Business AI Use": """
Share of U.S. employer businesses expecting to use artificial intelligence in at least one business function during the next six months.

**How to read it:** This measures stated near-term intent, not guaranteed future adoption.
""",

    "Expected Adoption Gap": """
Difference between expected business AI use within six months and current reported use.

Expected Adoption Gap = Expected Business AI Use − Current Business AI Use

**How to read it:** A positive value indicates more businesses expect to use AI than currently report using it. It is stated intent, not committed implementation. No confidence interval is reported for the difference because the retained survey contract does not provide the covariance between the paired estimates.
""",

    "Adoption Breadth": """
Compares current and expected AI use across major U.S. industries.

**How to read it:** Broader adoption means use is distributed across more industries rather than concentrated in a small number of high-use sectors. Sector estimates are subject to sampling error and suppression.
""",

    "Purpose Statement": """
AI Macro tracks the development of AI as an economic instrument and its footprint in the US economy.

It examines who is building it, how the buildout is financed, where this growth occurs, and the physical capacity required to sustain it.

It measures deployment, economic returns, and the adaptation of businesses, workers, and institutions to AI integration.

Using publicly available data, the platform connects capital committed, capacity built, adoption achieved, and value realized.
""",
}
