"""Plain-language definitions for the dashboard's actual analytical products."""

ADI_HELP = """
Measures observable AI capital deployment, physical construction, compute-supply realization, and power demand.

AI Development Intensity = 0.25(Capital Deployment) + 0.25(Data-Center Construction) + 0.25(Compute Supply) + 0.25(Power Footprint)

At least three of the four pillars must be valid. Available weights are renormalized. Scale: 0 to 100.

**How to read it:** Higher values indicate more intense observable development activity across the configured public-company cohorts and national proxy series. The score measures activity, not project completion, AI-attributable accounting, regional capacity, or investment quality.
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

**How to read it:** Positive values indicate the configured equity baskets are running ahead of the platform's selected development proxies. Negative values indicate those proxies are running ahead of equities. This is a relative composite, not a valuation theorem. Scale: -100 to +100.
""",

    "Economic Validation Gap": """
Compares observable AI deployment with realized downstream operating validation.

Deployment Score = AI Development Intensity

Validation Score = 0.65(normalized aggregate revenue growth) + 0.35(normalized revenue-weighted change in free-cash-flow margin)

Economic Validation Gap = Deployment Score - Validation Score

Validation covers the configured cloud-hyperscaler and enterprise-AI-software cohorts. Revenue growth uses ratio-of-sums aggregation; cash-margin change is revenue weighted. Both validation legs use fixed, versioned tanh transforms and year-over-year inputs.

**How to read it:** Positive values indicate observable deployment is running ahead of downstream revenue and cash-margin validation. Negative values indicate those operating outcomes are keeping pace with or exceeding deployment. It is not an AI productivity estimate or a causal return-on-investment measure. Scale: -100 to +100.
""",

    "AI-Industrial Growth Gap": """
Compares observable AI development activity with broad industrial growth.

AI-Industrial Growth Gap = AI Development Intensity - normalized Industrial Production growth

Source: AI Development Intensity and Federal Reserve industrial-production data.

**How to read it:** Positive values indicate the platform's selected AI-development proxies are outpacing broad U.S. industrial-production growth. Negative values indicate industrial growth is running ahead. The two sides are normalized indexes rather than comparable accounting totals. Scale: -100 to +100.
""",

    "Power Stress Index": """
Measures national power-system pressure through the difference between commercial and residential electric-utility output growth, sustainable-capacity utilization, and the gap between delivered output growth and sustainable-potential-output growth.

Power Stress = 2 × [0.40(Commercial-vs-Residential Output) + 0.35(Sustainable-Capacity Utilization) + 0.25(Potential-Output Response Gap) - 50]

At least two of the three components must be valid. Available weights are renormalized. Scale: -100 to +100.

**How to read it:** Positive values indicate above-reference power-system stress. Negative values indicate greater headroom or below-reference stress.
""",

    "Power Capacity Gap": """
Compares observable AI deployment pressure with the measured national response of the electric-power system.

Deployment Pressure = 0.60(Data-Center Construction) + 0.40(Capital Deployment)

Power-System Response = 0.60(Delivered Electric-Power Growth) + 0.40(Sustainable-Potential-Output Growth)

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

    "U.S. Water Utilization Ledger": """
A retained, versioned accounting layer for typed U.S. water flows. Current analytical surfaces use post-2020 evidence: the USGS 2020 national withdrawal comparison and EIA 2024 plant-level thermoelectric records. Older county records remain retained only as historical provenance and are not presented as current conditions.

Reported, agency-estimated, permitted, inferred, and scenario values retain separate evidence classes. Withdrawal, consumption, delivery, and discharge are never collapsed into one generic total.

**How to read it:** This is an evidence and accounting framework, not a facility-attribution or current local water-availability model. Source year, coverage, and measurement basis remain visible.
""",


    "Freshwater Competition Context": """
Compares the three largest modeled withdrawal categories in the retained USGS 2020 national release: crop irrigation, thermoelectric power, and public supply.

**How to read it:** This is a current-window national allocation envelope, not a complete all-use account. Data centers are not a separate category in the source, so the product does not attribute another claimant's withdrawal to AI facilities or infer local shortage, causation, or displacement.
""",

    "AI Water Evidence Ladder": """
Tracks how far the current facility evidence progresses from mapped location and state identification to direct water evidence, quantified withdrawal, and quantified consumption.

**How to read it:** Each step is a stricter evidentiary threshold. State identification comes from the current facility registry. Direct evidence can include permits, utility records, cooling design, or source disclosure. Quantified withdrawal and consumption require facility-specific volumes. Older county-withdrawal records are retained only as historical provenance and do not count as a current evidence stage.
""",

    "Thermoelectric Cooling-Water Records": """
Reports EIA 2024 plant-level cooling-water withdrawal and consumption records by water type, source, and cooling system. Annual volumes are shown as daily equivalents for scale comparison.

Withdrawal and consumption remain separate, and source records with negative values or consumption greater than withdrawal are retained with quality flags rather than silently deleted.

**How to read it:** The records describe reported thermoelectric cooling-water activity in the EIA survey frame. They are a separate 2024 plant-level layer and are not added to the USGS 2020 national comparison.
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

**How to read it:** Use the series as broad national downstream electricity-cost context for commercial customers.
""",

    "Industrial Electricity Price": """
Monthly U.S. average retail electricity price paid by industrial customers, reported in cents per kilowatt-hour by the U.S. Energy Information Administration.

**How to read it:** Use the series as broad national downstream electricity-cost context for industrial customers.
""",

    "Electric Power Output": """
Federal Reserve monthly industrial-production index for electric-power generation, transmission, and distribution. Index base: 2017 = 100.

**How to read it:** Higher values indicate more delivered electric-power activity relative to the 2017 base. The chart is a national production measure, not a regional adequacy reading.
""",

    "Electric Power Capacity": """
Federal Reserve monthly industrial-capacity index for electric-power generation, transmission, and distribution. Index base: 2017 = 100. The Federal Reserve defines capacity as an estimate of sustainable potential output under a realistic operating schedule.

**How to read it:** Higher values indicate greater estimated sustainable national output potential. This is not installed nameplate megawatts, firm deliverable capacity, reserve margin, transmission capability, or a regional adequacy measure.
""",

    "Electric Power Capacity Utilization": """
Federal Reserve monthly utilization rate for electric-power generation, transmission, and distribution.

Capacity Utilization = Electric Power Output ÷ Estimated Sustainable Potential Output

**How to read it:** Higher utilization means more of the estimated sustainable output potential is in use. It is not installed-capacity utilization, a regional reserve margin, or a measure of firm deliverability.

The Energy tab plots the retained history's 90th percentile as a statistical tightness reference. That line is not an engineering or reliability limit.
""",

    "Internal Funding Coverage": """
Internal Funding Coverage = Σ SEC Trailing-Twelve-Month Operating Cash Flow ÷ Σ SEC Trailing-Twelve-Month CapEx

Each company uses its latest available comparable fiscal period; both flows require four reported quarters. Companies missing either leg are excluded. **How to read it:** Above 1.0x means reported operating cash flow covers reported trailing capital spending for the matched cohort. Below 1.0x indicates a funding gap at the current rate. It does not capture all project finance, leases, joint ventures, or unconsolidated obligations.
""",

    "Cash Reserve Runway": """
Cash Reserve Runway = Σ SEC Period-End Cash and Equivalents ÷ Σ SEC Trailing-Twelve-Month CapEx

The numerator and denominator use each company's latest available fiscal period; CapEx requires four reported quarters. **How to read it:** The result is expressed in years for the matched public-company cohort. It is a static ratio, not a liquidity forecast; it ignores future cash generation, minimum operating cash, restricted cash, financing access, and changes in spending.
""",

    "Debt Financing Pulse": """
Debt Financing Pulse = Σ(SEC Total Debt at t − SEC Total Debt at comparable t−4q) ÷ Σ SEC Trailing-Twelve-Month CapEx at t

Only companies with matched debt observations and four-quarter CapEx are included; vendor and SEC debt taxonomies are not mixed. **How to read it:** Positive values indicate reported total debt expanded relative to trailing capital spending for the matched cohort. Negative values indicate net debt reduction. The ratio does not identify whether borrowing financed AI projects.
""",

    "Forward Commitment Load": """
Forward Commitment Load = Σ Latest Curated Disclosed Forward Commitments ÷ Σ Matched SEC Trailing-Twelve-Month CapEx

The current cross-section is retained; no historical trend is asserted because prior ledger vintages are not definition-stable. **How to read it:** Higher values indicate more disclosed commitments relative to trailing capital spending for the reviewed issuer cohort. Coverage depends on issuer disclosure and extraction scope; undisclosed or ambiguously described obligations remain missing.
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
Measures deterioration across a selected U.S. lender-channel proxy using bank lending standards, aggregate bank capital, a fixed listed-BDC cohort, and lagged private-equity fund aggregates.

Bank Channel = 0.50(Bank Credit Tightening) + 0.50(Bank Capital Strain)

Nonbank Channel = 0.50(Private Credit Impairment) + 0.50(PE Portfolio Financing Strain)

Lender Strain = 2 × [0.60(Bank Channel) + 0.40(Nonbank Channel) - 50]

Fixed component weights are 30% Bank Credit Tightening, 30% Bank Capital Strain, 20% Private Credit Impairment, and 20% PE Portfolio Financing Strain. All four pillars must be valid. Scale: -100 to +100.

**How to read it:** Positive values indicate tighter behavior or greater impairment in the selected proxy set. Negative values indicate stronger conditions. It is not a real-time census of banks, private credit, or private equity, and it is not AI-specific.
""",

    "NFCI": """
The Chicago Fed National Financial Conditions Index summarizes U.S. money-market, debt-market, equity-market, and banking conditions.

**How to read it:** Positive values indicate conditions tighter than the long-run average. Negative values indicate looser conditions. The three-month change shows whether conditions are tightening or easing.
""",

    "ANFCI": """
The Chicago Fed Adjusted National Financial Conditions Index removes the component of financial conditions associated with current economic conditions.

**How to read it:** Positive values indicate tighter-than-average financial conditions after the adjustment; negative values indicate looser conditions. ANFCI is contextual and is not blended into Borrower Strain or Lender Strain.
""",

    "Market Leadership Concentration": """
Measures how much of the configured public-equity universe's total company market capitalization belongs to its largest issuers.

Top-N Share = Σ Market Capitalization of the N largest valid companies ÷ Σ Market Capitalization of all valid companies

Raw HHI = Σ Company Market-Capitalization Share²

**How to read it:** Higher Top-6, Top-10, or HHI values indicate that public-equity value is concentrated in fewer companies. These measures use each issuer's total market capitalization; they do not estimate the portion attributable specifically to AI activity.
""",

    "Effective Firms": """
Translates raw market-capitalization HHI into the equivalent number of equally sized companies.

Effective Firms = 1 ÷ Raw HHI

**How to read it:** If a large company universe has 16 effective firms, its market-value concentration is equivalent to approximately 16 equally sized companies. This does not mean only 16 companies are present.
""",

    "Retained-Universe Market Return": """
Tracks price performance using beginning-period market-capitalization weights from the earliest retained date meeting the required market-cap and price coverage threshold.

Company Contribution = Beginning-Period Weight × Company Price Return

The cap-weighted, equal-weighted, and median-company series use the same valid starting universe.

**How to read it:** The cap-weighted versus equal-weighted gap shows whether the largest companies are outperforming or underperforming the typical constituent. It is a price-return history, excludes dividends, and begins with the retained archive.
""",

    "Sector AI Equity Index": """
Measures valuation, equal-weight one-year constituent performance relative to the benchmark, and market breadth within one configured sector basket.

Sector AI Equity Index = 0.40(Forward EBIT-Yield Valuation) + 0.35(1Y Relative Return) + 0.25(Market Breadth)

All three factors are required. Scale: 0 to 100.

**How to read it:** Higher values indicate stronger or more extended conditions in the configured basket. Lower values indicate weaker conditions. Basket membership, vendor market data, and the calculated-forward-earnings assumption limit population-wide interpretation.
""",

    "Trading Pressure": """
Measures abnormal valuation and trading pressure within a sector.

Trading Pressure = 0.25(Valuation Stretch) + 0.25(Price Extension) + 0.20(Momentum Acceleration) + 0.15(Volatility Expansion) + 0.15(Volume Activity)

At least three of the five components must be valid. Available weights are renormalized. Scale: 0 to 100.

**How to read it:** Higher values indicate more valuation stretch, price extension, momentum acceleration, volatility expansion, or abnormal volume in the configured basket. The anchored normalization is descriptive and is not a forecast that the sector must decline.
""",

    "Forward EV/EBIT": """
Measures the valuation of the sector's profitable operating cohort using a calculated forward operating-income estimate.

Forward EBIT = consensus forward revenue × current operating margin

Forward EV/EBIT = Σ Enterprise Value ÷ Σ Forward EBIT, for companies with positive Forward EBIT

The calculation requires at least five companies with valid forward-EBIT data, at least three profitable companies, and at least 60% enterprise-value data coverage.

**How to read it:** Higher values indicate a richer valuation of the profitable operating base under a constant-margin assumption. It is not consensus EBIT and must be interpreted together with Loss-Making EV Share.
""",

    "Loss-Making EV Share": """
Measures the share of valid sector enterprise value represented by companies with non-positive forward EBIT.

Loss-Making EV Share = Σ EV for companies with Forward EBIT ≤ 0 ÷ Σ EV for companies with valid Forward EBIT

**How to read it:** Higher values indicate that more sector enterprise value is unsupported by positive forward operating earnings.
""",

    "Earnings Support": """
Compares trailing sector repricing with the valuation of the sector's profitable operating base.

Earnings Support = 1Y Return ÷ Profitable-Cohort Forward EV/EBIT

Forward EBIT is calculated from consensus forward revenue and the current operating margin to preserve coverage where a direct forward-EBIT field is unavailable.

**How to read it:** Strong returns attached to lower profitable-cohort multiples imply greater earnings support. This is a descriptive cross-sectional relationship, not evidence that earnings caused the return. The chart also shows Sector AI Equity Index and Loss-Making EV Share.
""",

    "Speculative Load": """
Compares abnormal trading pressure with the sector's equity foundation.

Speculative Load = Trading Pressure ÷ Sector AI Equity Index

**How to read it:** Values below 1.0 indicate that sector equity support exceeds abnormal trading pressure. Values above 1.0 indicate that pressure exceeds the sector's current market foundation. Because both inputs are bounded composite scores, interpret the ratio together with the two source indexes; it is undefined at an AI Equity Index of zero and becomes sensitive at very low index values.
""",

    "Sector Movement": """
Measures the combined change in Sector AI Equity Index and Trading Pressure over the available fixed lookback.

Sector Movement = √[(ΔSector AI Equity Index)² + (ΔTrading Pressure)²]

**How to read it:** Larger values indicate faster change in the configured sector basket's two-dimensional market state. The measure is nonnegative, period-dependent, and not a forecast; inspect the underlying changes to determine direction.
""",

    "Risk Breadth": """
Measures how broadly company fundamentals are deteriorating within a sector.

Risk Breadth = 100 × Adverse Financial Signals ÷ Valid Financial Signals

Signals are adverse when free-cash-flow margin falls, net debt/EBITDA rises, or CapEx/operating cash flow rises versus the prior comparable fiscal year. At least 50% of possible signals must be valid.

**How to read it:** Higher values indicate deterioration across more of the configured basket's available filing-derived signals. Missing signals are excluded subject to the coverage rule. It does not estimate failure probability or represent the full economic sector.
""",

    "Data Center Construction": """
Measures the seasonally adjusted annual rate of private construction spending on data-center facilities.

**Source:** U.S. Census Bureau, Value of Construction Put in Place.

**How to read it:** Higher values indicate a larger active construction footprint. These spending data do not measure facility size, construction stage, compute capacity, power demand, or utilization, and they exclude announced projects until spending is put in place.
""",

    "U.S. Data Center Footprint": """
Tracks the national operating base and in-development data-center footprint. Detailed location records are deconflicted to physical campuses so multiple buildings at one site do not inflate campus counts.
""",

    "Data Center Development Pipeline": """
Tracks active U.S. data-center campuses by development stage, geography, operator, and published capacity.
""",

    "Computer, Electronic & Electrical Manufacturing Construction": """
Measures private construction spending on computer, electronic, and electrical manufacturing facilities.

**Source:** U.S. Census Bureau, Value of Construction Put in Place.

**How to read it:** The category includes semiconductor-fab construction but is not semiconductor-exclusive. It is a broad manufacturing-buildout measure, not a pure fab series.
""",

    "Electric Power Construction": """
Measures the seasonally adjusted annual rate of private construction spending on electric-power facilities and systems.

**Source:** U.S. Census Bureau, Value of Construction Put in Place.

**How to read it:** The series is a broad downstream enabling-infrastructure flow covering electric-power construction. It is plotted beside data-center and compute-manufacturing construction to show whether the physical buildout is propagating into power infrastructure; no AI-attributable share is assigned.
""",

    "Domestic Compute Manufacturing Output": """
Tracks Federal Reserve G.17 industrial-production indexes for U.S. computer and peripheral equipment, communications equipment, and semiconductor and electronic component manufacturing.

**How to read it:** These are domestic industry output indexes, not AI-specific production volumes. They provide a consistent operating view of compute-related manufacturing while preserving the broader official industry definitions.
""",

    "Compute Manufacturing Capacity Utilization": """
Tracks Federal Reserve G.17 capacity-utilization rates for U.S. computer/peripheral and semiconductor/electronic-component manufacturing.

**How to read it:** Utilization describes the share of estimated industry capacity in use. It does not establish advanced-node, HBM, packaging, accelerator, or AI-specific capacity.
""",

    "U.S. Compute Manufacturing Investment": """
Tracks announced private capital spending and direct federal awards across official U.S. compute-manufacturing projects.

**How to read it:** Expected private investment shows the scale of planned manufacturing buildout, while direct awards show the public funding contribution. The project set covers leading-edge logic, memory, packaging, photonics, and other compute-enabling layers. Announced investment is not completed construction or production output.
""",


    "Buildout Leadership Rotation": """
Compares rolling year-over-year construction growth across data centers, compute manufacturing, electric power, communications, and public water. Quarterly snapshots show which layer of the physical AI stack is absorbing the strongest current investment momentum.

**How to read it:** Leadership rotation is a flow measure, not a verdict on long-run importance. A sharp slowdown can reflect normalization from an unusually high base after an earlier investment surge, so momentum should be read alongside current spending levels.
""",

    "Net Infrastructure Support Balance": """
Compares six enabling systems with channel-specific lagged baselines. Compute manufacturing, electric power, and communications are benchmarked to broad private-construction denominators; public water, roads and highways, and public transit are benchmarked to their lagged shares of the selected public-system construction mix.

Net support balance = Σ(observed component − expected baseline component)

**How to read it:** Positive and negative deviations are both retained. Gross positive excess reports only channels above baseline and is a secondary diagnostic; the net balance is the headline measure because it also includes below-baseline channels. This is a statistical composition relationship, not causal AI attribution or a measure of physical capacity adequacy.
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

**How to read it:** This is a weighted survey estimate for U.S. employer businesses. Standard errors are retained. It does not measure intensity of use, productivity, return on investment, or labor effects.
""",

    "Expected Business AI Use": """
Share of U.S. employer businesses expecting to use artificial intelligence in at least one business function during the next six months.

**How to read it:** This is a weighted survey estimate of stated near-term intent, with a retained standard error. It is not committed implementation or guaranteed future adoption.
""",

    "Expected Adoption Gap": """
Difference between expected business AI use within six months and current reported use.

Expected Adoption Gap = Expected Business AI Use − Current Business AI Use

**How to read it:** A positive value indicates more businesses expect to use AI than currently report using it. It is stated intent, not committed implementation. No confidence interval is reported for the difference because the retained survey contract does not provide the covariance between the paired estimates.
""",

    "Adoption Breadth": """
Compares current and expected AI use across major U.S. industries.

**How to read it:** Broader adoption means reported use is distributed across more BTOS industry groups rather than concentrated in a few. Sector estimates retain standard errors and missing/suppressed values; this is breadth across the survey frame, not use intensity.
""",

    "Purpose Statement": """
AI Macro traces the AI economy from capital and construction through deployment, adoption, and economic results. Using publicly available data, it connects companies and markets with the data centers, resources, and infrastructure behind the buildout—and examines how that buildout is reshaping the broader U.S. economy. Its central questions are whether rising investment and capacity are producing durable use, broad participation, and realized value—and how the resulting gains, costs, and risks are distributed across investors, businesses, workers, communities, and regions.
""",

    "Interconnection Pipeline": """
Tracks active U.S. generator and storage interconnection requests using Berkeley Lab component accounting.

**How to read it:** Requested queue capacity is not operating, financed, or deliverable capacity. Projects may withdraw, resize, change technology, or remain constrained by transmission and study requirements.
""",

    "Advanced-Stage Queue Share": """
Share of submitted active interconnection capacity whose records indicate an executed interconnection agreement or construction-stage status.

**How to read it:** A higher share indicates more of the queue has progressed beyond early study stages. It does not guarantee timely energization or firm deliverability.
""",

    "Electric Storage Deployment": """
Combines EIA operating battery power and energy capacity with submitted storage components in the active Berkeley Lab interconnection queue.

**How to read it:** Operating capacity and queued capacity remain separate. Queue storage is requested capacity, not installed capacity, and hybrid-project accounting is displayed using the retained component methodology.
""",

    "AI-Linked Employment Footprint": """
Tracks BLS employment in computer-systems design, computing-infrastructure services, semiconductor manufacturing, and power-and-communication-line construction from 2020 to the present.

**How to read it:** These industries are directly connected to the AI production and deployment stack, but their full employment changes are not attributed to AI.
""",

    "Supporting Labor Demand": """
Tracks BLS JOLTS job openings in information, manufacturing, construction, and professional and business services.

**How to read it:** These broad labor markets show the hiring environment in which AI-related employers compete for workers. They do not isolate AI-specific vacancies.
""",

    "AI-Linked Wage Trajectory": """
Tracks average hourly earnings in directly relevant technology, semiconductor, and infrastructure-construction industries.

**How to read it:** Wage changes can reflect labor scarcity, worker composition, inflation, bargaining conditions, and industry mix. The platform does not assign the full change to AI.
""",

    "Labor Productivity": """
BLS nonfarm-business and manufacturing output-per-hour measures.

**How to read it:** Productivity is a realized economic outcome and a validation test for the investment cycle. Quarterly movements are not attributed to AI without causal evidence.
""",

    "Real Value-Added Output": """
BLS real value-added output for nonfarm business and manufacturing.

**How to read it:** This measures inflation-adjusted production in the underlying sector account. It is not an AI-specific output series.
""",

    "Hourly Compensation": """
BLS compensation per hour in the nonfarm-business productivity account.

**How to read it:** Use alongside productivity to assess whether realized gains are reaching labor. It does not identify distribution across occupations or income groups.
""",

    "Inflation-Adjusted Realized Growth": """
The Economic Impact comparison keeps BLS labor productivity and real output in their published inflation-adjusted form, while converting hourly compensation and unit labor costs using the latest year-over-year CPI change.

**How to read it:** The adjustment separates purchasing-power growth from nominal growth. It is a descriptive normalization, not an estimate of AI's causal contribution.
""",

    "Unit Labor Costs": """
BLS labor compensation required to produce one unit of output.

**How to read it:** Growth can reflect compensation rising faster than productivity. It is a realized production-cost measure, not a market valuation or stock-price signal.
""",

    "Information-Processing Investment": """
BEA investment in information-processing equipment and software, retained through FRED.

**How to read it:** This is broader than AI investment. It supplies a consistent capital-formation benchmark for comparing investment growth with realized output and productivity.
""",

    "Wastewater System Investment": """
U.S. Census seasonally adjusted annual rate of public sewage and waste-disposal construction spending.

**How to read it:** This is a chronological public-system investment series, not a measure of wastewater volumes, treatment headroom, discharge permits, or AI-attributed spending.
""",

}
