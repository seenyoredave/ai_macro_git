"""Plain-language definitions for the dashboard's actual analytical products."""

ADI_HELP = """
Measures observable AI capital spending, physical construction, compute-supply growth, and power demand.

AI Development Intensity = 0.25(Capital Deployment) + 0.25(Data-Center Construction) + 0.25(Compute Supply) + 0.25(Power Footprint)

At least three of the four pillars must be valid. Available weights are renormalized. Scale: 0 to 100.

**Interpretation:** Higher values indicate more intense observable development activity across the selected public-company cohorts and national series. The score measures activity, not project completion, AI-attributable accounting, regional capacity, or investment quality.
"""

METRIC_DEFINITIONS = {
    "AI Economic Transmission": """
Six readings that follow the AI economy from market performance and funding through construction, grid delivery, business use, and economic results.
""",

    "AI Equity Index": """
Measures sustained relative performance and participation across the selected AI equity universe.

AI Equity Index = mean(valid Sector AI Equity Index scores)

Sector AI Equity Index = 0.60(1Y Relative Return) + 0.40(Market Breadth)

The same two-factor construction applies to every sector, including insurance. Both sector factors and at least 75% of sector scores must be valid. Scale: 0 to 100.

**Interpretation:** Higher values indicate stronger and more broadly participated equity conditions relative to the benchmark. Valuation remains a separate diagnostic rather than an index input. This is a regime reading, not a price target or return forecast.
""",

    "AI Development Intensity": ADI_HELP,

    "Speculation Gap": """
Compares equity enthusiasm with observable AI development activity.

Speculation Gap = AI Equity Index - AI Development Intensity

**Interpretation:** Positive values indicate the selected equity baskets are running ahead of the development measures. Negative values indicate the development measures are running ahead of equities. This is a relative composite, not a valuation theorem. Scale: -100 to +100.
""",

    "Economic Validation Gap": """
Compares observable AI deployment with revenue growth and changes in free-cash-flow margins.

Deployment Score = AI Development Intensity

Validation Score = 0.65(normalized aggregate revenue growth) + 0.35(normalized revenue-weighted change in free-cash-flow margin)

Economic Validation Gap = Deployment Score - Validation Score

The operating-results score covers the selected cloud-hyperscaler and enterprise-AI-software cohorts. Revenue growth uses ratio-of-sums aggregation; cash-margin change is revenue weighted. Both inputs use fixed tanh transforms and year-over-year values.

**Interpretation:** Positive values mean the deployment score is ahead of the revenue and cash-margin score. Negative values mean those operating results are keeping pace with or exceeding deployment. This is not an AI productivity estimate or a causal return-on-investment measure. Scale: -100 to +100.
""",

    "AI-Industrial Growth Gap": """
Compares observable AI development activity with broad industrial growth.

AI-Industrial Growth Gap = AI Development Intensity - normalized Industrial Production growth

Source: AI Development Intensity and Federal Reserve industrial-production data.

**Interpretation:** Positive values indicate the selected AI-development measures are outpacing broad U.S. industrial-production growth. Negative values indicate industrial growth is running ahead. The two sides are normalized indexes rather than comparable accounting totals. Scale: -100 to +100.
""",

    "Power Stress Index": """
Measures national power-system pressure through the difference between commercial and residential electric-utility output growth, sustainable-capacity utilization, and the gap between delivered output growth and sustainable-potential-output growth.

Power Stress = 2 × [0.40(Commercial-vs-Residential Output) + 0.35(Sustainable-Capacity Utilization) + 0.25(Potential-Output Response Gap) - 50]

At least two of the three components must be valid. Available weights are renormalized. Scale: -100 to +100.

**Interpretation:** Positive values indicate above-reference power-system stress. Negative values indicate greater headroom or below-reference stress.
""",

    "Power Capacity Gap": """
Compares observable AI deployment pressure with the measured national response of the electric-power system.

Deployment Pressure = 0.60(Data-Center Construction) + 0.40(Capital Deployment)

Power-System Response = 0.60(Delivered Electric-Power Growth) + 0.40(Sustainable-Potential-Output Growth)

Power Capacity Gap = Deployment Pressure - Power-System Response

**Interpretation:** Positive values indicate deployment pressure is advancing faster than measured power-system response. Negative values indicate output and capacity are advancing faster than deployment pressure. Scale: -100 to +100.

**Scope:** National response proxy. **Excludes:** regional transmission constraints, interconnection queues, local congestion, and firm deliverable capacity.
""",

    "Sector Basket Concentration": """
Measures market-value concentration inside each selected sector basket while controlling for differences in valid constituent count.

Raw HHI = Σ(company market-cap share)²

Adjusted HHI = 100 × (Raw HHI − 1/N) ÷ (1 − 1/N)

N is the number of companies with valid positive market capitalization. A value of 0 represents an equal-weight basket of the same size; 100 represents single-company concentration.

**Interpretation:** Higher values indicate that sector-basket market value is carried by fewer companies. The metric describes the selected basket, not the entire economic sector. Rankings require at least three valid companies and 60% market-cap coverage.
""",

    "U.S. Water Utilization Ledger": """
An accounting view of U.S. water flows. Withdrawal, consumption, delivery, and discharge remain separate measures with separate evidence classes.

**Coverage:** USGS national withdrawals, EIA thermoelectric records, drought conditions, and facility-linked disclosures.
""",


    "Freshwater Competition Context": """
The three largest modeled withdrawal categories in the USGS 2020 national release: crop irrigation, thermoelectric power, and public supply.

**Coverage:** National allocation context; facility exposure appears in the state and campus layers.
""",

    "AI Water Evidence Ladder": """
Facility evidence from mapped location through state identification, direct water records, quantified withdrawal, and quantified consumption.

**Thresholds:** Direct evidence includes permits, utility records, cooling design, or source disclosure. Quantified stages require facility-specific volumes.
""",

    "Thermoelectric Cooling-Water Records": """
Reports EIA 2024 plant-level cooling-water withdrawal and consumption records by water type, source, and cooling system. Annual volumes are shown as daily equivalents for scale comparison.

Withdrawal and consumption remain separate. Records with negative values or consumption greater than withdrawal are shown with quality flags.

**Interpretation:** The records describe reported thermoelectric cooling-water activity in the EIA survey frame. They are a separate 2024 plant-level layer and are not added to the USGS 2020 national comparison.
""",

    "Henry Hub Natural Gas": """
Weekly Henry Hub natural-gas spot price from the U.S. Energy Information Administration through FRED.

The card reports the latest price and four-week percentage change.

**Interpretation:** Rising prices indicate a more expensive fuel environment for gas-fired generation. **Excludes:** regional pipeline constraints and utility hedging.
""",

    "WTI Crude Oil": """
Weekly West Texas Intermediate crude-oil spot price from the U.S. Energy Information Administration through FRED.

The card reports the latest price and four-week percentage change.

**Interpretation:** Oil has a limited direct role in U.S. utility-scale generation, but it affects backup generation, construction, transportation, and the broader energy-cost environment.
""",

    "Coal Production": """
Monthly Federal Reserve industrial-production index for U.S. coal mining.

The card reports the latest index and three-month percentage change.

**Interpretation:** Tracks coal-supply momentum. **Excludes:** inventories, plant economics, and regional availability.
""",

    "Renewable Power Output": """
Monthly Federal Reserve industrial-production index for renewable and other electric-power generation.

The card reports the latest index and three-month percentage change.

**Interpretation:** Tracks renewable-output momentum. **Breakouts unavailable:** generation technology, location, storage support, and firmness.
""",

    "Commercial Electricity Price": """
Monthly U.S. average retail electricity price paid by commercial customers, reported in cents per kilowatt-hour by the U.S. Energy Information Administration.

**Interpretation:** Use the series as broad national downstream electricity-cost context for commercial customers.
""",

    "Industrial Electricity Price": """
Monthly U.S. average retail electricity price paid by industrial customers, reported in cents per kilowatt-hour by the U.S. Energy Information Administration.

**Interpretation:** Use the series as broad national downstream electricity-cost context for industrial customers.
""",

    "Electric Power Output": """
Federal Reserve monthly industrial-production index for electric-power generation, transmission, and distribution. Index base: 2017 = 100.

**Interpretation:** Higher values indicate more delivered electric-power activity relative to the 2017 base. The chart is a national production measure, not a regional adequacy reading.
""",

    "Electric Power Capacity": """
Federal Reserve monthly industrial-capacity index for electric-power generation, transmission, and distribution. Index base: 2017 = 100. The Federal Reserve defines capacity as an estimate of sustainable potential output under a realistic operating schedule.

**Interpretation:** Higher values indicate greater estimated sustainable national output potential. This is not installed nameplate megawatts, firm deliverable capacity, reserve margin, transmission capability, or a regional adequacy measure.
""",

    "Electric Power Capacity Utilization": """
Federal Reserve monthly utilization rate for electric-power generation, transmission, and distribution.

Capacity Utilization = Electric Power Output ÷ Estimated Sustainable Potential Output

**Interpretation:** Higher utilization means more of the estimated sustainable output potential is in use. It is not installed-capacity utilization, a regional reserve margin, or a measure of firm deliverability.

The Energy tab plots the displayed history's 90th percentile as a statistical tightness reference. That line is not an engineering or reliability limit.
""",

    "Internal Funding Coverage": """
Internal Funding Coverage = Σ SEC Trailing-Twelve-Month Operating Cash Flow ÷ Σ SEC Trailing-Twelve-Month CapEx

Each company uses its latest available comparable fiscal period; both flows require four reported quarters. Companies missing either leg are excluded. **Interpretation:** Above 1.0x means reported operating cash flow covers reported trailing capital spending for the matched cohort. Below 1.0x indicates a funding gap at the current rate. **Excludes:** project finance, leases, joint ventures, and unconsolidated obligations outside the reported cohort.
""",

    "Cash Reserve Runway": """
Cash Reserve Runway = Σ SEC Period-End Cash and Equivalents ÷ Σ SEC Trailing-Twelve-Month CapEx

The numerator and denominator use each company's latest available fiscal period; CapEx requires four reported quarters. **Interpretation:** The result is expressed in years for the matched public-company cohort. It is a static ratio, not a liquidity forecast; it ignores future cash generation, minimum operating cash, restricted cash, financing access, and changes in spending.
""",

    "Debt Financing Pulse": """
Debt change / CapEx = Σ(Definition-Matched SEC Debt at t − Definition-Matched SEC Debt at comparable t−4q) ÷ Σ SEC Trailing-Twelve-Month CapEx at t

Only companies with the same issuer debt definition in both periods, a complete current/non-current concept group, period ends within 62 days of TTM CapEx, and four-quarter CapEx are included. Vendor and SEC debt taxonomies are never mixed. The five-year sparkline requires at least two eligible issuers at each observation; its matched membership can expand as reviewed history becomes available. **Interpretation:** Positive values indicate reported debt expanded relative to trailing capital spending for the matched cohort. Negative values indicate net debt reduction. AI-project use of proceeds is not identified.
""",

    "Forward Commitment Load": """
Forward Commitment Load = Σ(Uncommenced Leases + Purchase or Contractual Commitments) ÷ Σ Matched SEC Trailing-Twelve-Month CapEx

For every point in the five-year sparkline, the numerator uses each issuer's latest reviewed disclosure available by that observation date and the denominator requires four-quarter SEC CapEx. The current numerator is assembled from component-level disclosures, so lease and contractual-commitment components can carry their own as-of date, filing date, source, and scope. At least two matched issuers are required; membership can change with disclosure coverage, but the two numerator categories do not. **Interpretation:** Higher values indicate more disclosed commitments relative to trailing capital spending for the reviewed issuer cohort. This is disclosed obligation load, not a payment forecast or a measure of funded debt. Some issuer disclosures are broader than AI or data-center investment; scope is retained with each component rather than silently attributed to AI. Undisclosed or ambiguously described obligations remain missing.
""",

    "Corporate Bond Market Distress": """
The New York Fed Corporate Bond Market Distress Index combines indicators of primary-market issuance and pricing, secondary-market pricing and liquidity, and the relationship between traded and nontraded bonds.

The market index covers investment-grade and high-yield corporate bonds.

**Interpretation:** Higher values indicate more impaired corporate-bond market functioning and more difficult access to public debt capital. The index measures market functioning, not expected bond returns or issuer default probability.
""",

    "Investment-Grade Bond Distress": """
The investment-grade segment of the New York Fed Corporate Bond Market Distress Index.

**Interpretation:** Higher values indicate greater impairment in issuance, pricing, trading, or liquidity for investment-grade corporate bonds. This is the public-debt channel most relevant to large established issuers.
""",

    "High-Yield Bond Distress": """
The high-yield segment of the New York Fed Corporate Bond Market Distress Index.

**Interpretation:** Higher values indicate greater impairment in issuance, pricing, trading, or liquidity for below-investment-grade corporate bonds. This segment is more relevant to weaker and more financing-dependent issuers.
""",

    "Borrower Strain": """
Measures deterioration in the selected borrower cohort's cash generation, debt capacity, and ability to absorb disclosed obligations.

Borrower Strain = 0.30(Cash Flow Strain) + 0.25(Debt Capacity Strain) + 0.30(Committed Burden) + 0.15(Contingent Exposure)

At least three of the four components must be valid. The internal 0–100 adverse-condition score is centered to a -100 to +100 display scale.

**Interpretation:** Positive values indicate greater deterioration in financial condition or capacity. Negative values indicate stronger cash flow, debt capacity, and obligation coverage.
""",

    "Lender Strain": """
Measures deterioration across a selected U.S. lender-channel proxy using bank lending standards, aggregate bank capital, credit impairment, and lagged private-equity fund aggregates.

Bank Channel = 0.50(Bank Credit Tightening) + 0.50(Bank Capital Strain)

Nonbank Channel = 0.50(Private Credit Impairment) + 0.50(PE Portfolio Financing Strain)

Lender Strain = 2 × [0.60(Bank Channel) + 0.40(Nonbank Channel) - 50]

Fixed component weights are 30% Bank Credit Tightening, 30% Bank Capital Strain, 20% Private Credit Impairment, and 20% PE Portfolio Financing Strain. All four pillars must be valid. Scale: -100 to +100.

The ten-year history uses the Federal Reserve business-loan delinquency rate before the listed-BDC nonaccrual series begins in late 2025. The current reading uses the listed-BDC series. The historical bridge and direct series are normalized independently before entering the fixed-weight composite.

**Interpretation:** Positive values indicate tighter behavior or greater impairment in the selected proxy set. Negative values indicate stronger conditions. It is not a real-time census of banks, private credit, or private equity, and it is not AI-specific.
""",

    "NFCI": """
The Chicago Fed National Financial Conditions Index summarizes U.S. money-market, debt-market, equity-market, and banking conditions.

**Interpretation:** Positive values indicate conditions tighter than the long-run average. Negative values indicate looser conditions. The three-month change shows whether conditions are tightening or easing.
""",

    "ANFCI": """
The Chicago Fed Adjusted National Financial Conditions Index removes the component of financial conditions associated with current economic conditions.

**Interpretation:** Positive values indicate tighter-than-average financial conditions after the adjustment; negative values indicate looser conditions. ANFCI is contextual and is not blended into Borrower Strain or Lender Strain.
""",

    "Market Leadership Concentration": """
Measures how much of the selected public-equity universe's total company market capitalization belongs to its largest issuers.

Top-N Share = Σ Market Capitalization of the N largest valid companies ÷ Σ Market Capitalization of all valid companies

Raw HHI = Σ Company Market-Capitalization Share²

**Interpretation:** Higher Top-6, Top-10, or HHI values indicate that public-equity value is concentrated in fewer companies. **Basis:** each issuer's total market capitalization; no AI-attributable allocation.
""",

    "Effective Firms": """
Translates raw market-capitalization HHI into the equivalent number of equally sized companies.

Effective Firms = 1 ÷ Raw HHI

**Interpretation:** A reading of 16 means the observed concentration matches a hypothetical universe of 16 equally sized firms; the actual company count may be much larger.
""",

    "Retained-Universe Market Return": """
Tracks price performance using beginning-period market-capitalization weights from the first date with sufficient market-cap and price data.

Company Contribution = Beginning-Period Weight × Company Price Return

The cap-weighted, equal-weighted, and median-company series use the same valid starting universe.

**Interpretation:** The cap-weighted versus equal-weighted gap shows whether the largest companies are outperforming or underperforming the typical constituent. It is a price-return history, excludes dividends, and begins at the earliest date meeting the coverage threshold.
""",

    "Sector AI Equity Index": """
Measures equal-weight one-year constituent performance relative to the benchmark and market breadth within one selected sector basket.

Sector AI Equity Index = 0.60(1Y Relative Return) + 0.40(Market Breadth)

Both factors are required and the same formula applies to every sector. Scale: 0 to 100.

**Interpretation:** Higher values indicate stronger and more broadly participated conditions in the selected basket. Lower values indicate weaker conditions. Valuation is reported separately through Forward EV/EBIT and Loss-Making EV Share. Basket membership and vendor market data limit population-wide interpretation.
""",

    "Trading Pressure": """
Measures abnormal price and trading pressure within a sector.

Trading Pressure = 0.30(Price Extension) + 0.25(Momentum Acceleration) + 0.25(Volatility Expansion) + 0.20(Volume Activity)

All four components are required. Scale: 0 to 100.

**Interpretation:** Higher values indicate more price extension, momentum acceleration, volatility expansion, or abnormal volume in the selected basket. Valuation is kept outside this metric. The anchored normalization is descriptive and is not a forecast that the sector must decline.
""",

    "Forward EV/EBIT": """
Measures the valuation of the sector's profitable operating cohort using a calculated forward operating-income estimate.

Forward EBIT = consensus forward revenue × current operating margin

Forward EV/EBIT = Σ Enterprise Value ÷ Σ Forward EBIT, for companies with positive Forward EBIT

The calculation requires at least five companies with valid forward-EBIT data, at least three profitable companies, and at least 60% enterprise-value data coverage.

**Interpretation:** Higher values indicate a richer valuation of the profitable operating base under a constant-margin assumption. It is not consensus EBIT and must be interpreted together with Loss-Making EV Share.
""",

    "Loss-Making EV Share": """
Measures the share of valid sector enterprise value represented by companies with non-positive forward EBIT.

Loss-Making EV Share = Σ EV for companies with Forward EBIT ≤ 0 ÷ Σ EV for companies with valid Forward EBIT

**Interpretation:** Higher values indicate that more sector enterprise value is unsupported by positive forward operating earnings.
""",

    "Earnings Support": """
Compares trailing sector repricing with the valuation of the sector's profitable operating base.

Earnings Support = 1Y Return ÷ Profitable-Cohort Forward EV/EBIT

Forward EBIT is calculated from consensus forward revenue and the current operating margin to preserve coverage where a direct forward-EBIT field is unavailable.

**Interpretation:** Strong returns attached to lower profitable-cohort multiples imply greater earnings support. This is a descriptive cross-sectional relationship, not evidence that earnings caused the return. The chart also shows Sector AI Equity Index and Loss-Making EV Share.
""",

    "Speculative Load": """
Compares abnormal trading pressure with the sector's equity foundation.

Speculative Load = Trading Pressure ÷ Sector AI Equity Index

**Interpretation:** Values below 1.0 indicate that sector equity support exceeds abnormal trading pressure. Values above 1.0 indicate that pressure exceeds the sector's current market foundation. Because both inputs are bounded composite scores, interpret the ratio together with the two source indexes; it is undefined at an AI Equity Index of zero and becomes sensitive at very low index values.
""",

    "Sector Movement": """
Measures the combined change in Sector AI Equity Index and Trading Pressure over the available fixed lookback.

Sector Movement = √[(ΔSector AI Equity Index)² + (ΔTrading Pressure)²]

**Interpretation:** Larger values indicate faster change in the selected sector basket's two-dimensional market state. The measure is nonnegative, period-dependent, and not a forecast; inspect the underlying changes to determine direction.
""",

    "Risk Breadth": """
Measures how broadly company fundamentals are deteriorating within a sector.

Risk Breadth = 100 × Adverse Financial Signals ÷ Valid Financial Signals

Signals are adverse when free-cash-flow margin falls, net debt/EBITDA rises, or CapEx/operating cash flow rises versus the prior comparable fiscal year. At least 50% of possible signals must be valid.

**Interpretation:** Higher values indicate deterioration across more of the selected basket's available filing-derived signals. Missing signals are excluded subject to the coverage rule. **Scope:** selected public-company basket; no failure-probability estimate.
""",

    "Data Center Construction": """
Measures the seasonally adjusted annual rate of private construction spending on data-center facilities.

**Source:** U.S. Census Bureau, Value of Construction Put in Place.

**Interpretation:** Higher values indicate a larger active construction footprint. **Coverage:** construction put in place. **Excludes:** facility size, stage, compute capacity, power demand, utilization, and announced spending not yet underway.
""",

    "U.S. Data Center Footprint": """
Tracks the national operating base and in-development data-center footprint. Detailed location records are deconflicted to physical campuses; multiple buildings and multiple source observations at one site count as one campus.

### Campus-identity methodology

**1. Preserve source evidence.** Every record keeps its source ID, link, date, evidence grade, reported stage, coordinates, and capacity description.

**2. Normalize identity fields.** State names, addresses, facility names, and operator names are standardized for comparison. Generic words such as “data center,” “campus,” “project,” and corporate suffixes do not count as distinguishing name evidence.

**3. Apply conservative automatic matching.** Records must be in the same state and have usable coordinates. Exact or near-exact coordinates can match within 75 meters. A normalized address can match within 1 kilometer. An exact normalized project name can match within 1.5 kilometers. Fuzzy name/operator matches use progressively stricter thresholds out to a general maximum of 5 kilometers; operator identity alone is not sufficient. Spatial candidate cells expose the full comparison radius before these rules are applied.

**4. Review material ambiguity.** Large or coordinate-imprecise campuses that cannot be resolved safely by the general rules use a small, source-record-level decision ledger. Every override identifies the records, the decision to merge or keep separate, an evidence URL, and the reason. Reviewed “keep separate” decisions take precedence over fuzzy similarity. Reviewed merges may bridge a wider radius when primary or direct project evidence establishes one campus.

**5. Consolidate duplicate records without adding duplicate claims.** Field selection prioritizes primary project evidence, then open project trackers, secondary inventories, and mapped footprints; evidence grade, field specificity, and publication date break ties. Statuses use the most informative lifecycle state. Capacity observations inside a matched campus are **not summed**: each capacity field uses the largest reported value in the matched group, and structured planned capacity takes precedence over a generic published estimate. Thus a site-level capacity and a tenant lease at the same campus do not become two projects or additive megawatts.

**Interpretation boundary.** The consolidated campus dataset represents physical campuses, not independently verified counts of every building, phase, lease, powered shell, or land parcel. Proximity, a shared operator, or a generic name does not by itself prove identity. Published or tracker-estimated capacity is not necessarily contracted utility capacity, energized load, IT load, or realized consumption.
""",

    "Data Center Development Pipeline": """
Tracks active U.S. data-center campuses by development stage, geography, operator, and published capacity.
""",

    "U.S. Connectivity Transport Layer": """
U.S.-connected submarine cable systems, landing markets, internet exchanges, interconnection facilities, middle-mile awards, and data-center proximity screens.

**Coverage:** Published infrastructure and registry records. Traffic, latency, dark fiber, contracted capacity, pricing, and unreported routes remain outside the current dataset.
""",

    "Submarine Cable System Coverage": """
Two separate counts: FCC-licensed U.S.-international systems and a broader catalog of U.S.-connected international, territorial, domestic, and regional systems.

**Coverage:** System presence, service status, authorization, and selected landing markets.
""",

    "Internet Exchange Depth": """
Active exchanges, reported memberships, physical-location references, and PeeringDB facility records by market.

**Units:** Membership totals count memberships; facility records use the operator-maintained PeeringDB registry.
""",

    "Middle-Mile Expansion": """
Federal middle-mile awards, disclosed route miles, geography, endpoints, funding, and planned fiber construction.

**Coverage:** Publicly funded projects and published program milestones.
""",

    "Capacity-Connectivity Mismatch": """
States with large published data-center pipelines and limited public exchange, landing, facility, or middle-mile evidence.

**Use:** Flags places where data-center growth appears large relative to visible network infrastructure and warrants deeper site research.
""",

    "Campus Connectivity Proximity": """
Great-circle distance from deduplicated data-center campuses to selected landing markets and public PeeringDB facilities.

**Use:** Geographic screening before route- and contract-level diligence.
""",

    "Computer, Electronic & Electrical Manufacturing Construction": """
Measures private construction spending on computer, electronic, and electrical manufacturing facilities.

**Source:** U.S. Census Bureau, Value of Construction Put in Place.

**Interpretation:** The category includes semiconductor-fab construction but is not semiconductor-exclusive. It is a broad manufacturing-buildout measure, not a pure fab series.
""",

    "Electric Power Construction": """
Measures the seasonally adjusted annual rate of private construction spending on electric-power facilities and systems.

**Source:** U.S. Census Bureau, Value of Construction Put in Place.

**Interpretation:** The series is a broad downstream enabling-infrastructure flow covering electric-power construction. It is plotted beside data-center and compute-manufacturing construction to show whether the physical buildout is propagating into power infrastructure; no AI-attributable share is assigned.
""",

    "Domestic Compute Manufacturing Output": """
Tracks Federal Reserve G.17 industrial-production indexes for U.S. computer and peripheral equipment, communications equipment, and semiconductor and electronic component manufacturing.

**Interpretation:** These are domestic industry output indexes, not AI-specific production volumes. They provide a consistent operating view of compute-related manufacturing while preserving the broader official industry definitions.
""",

    "Compute Manufacturing Capacity Utilization": """
Tracks Federal Reserve G.17 capacity-utilization rates for U.S. computer/peripheral and semiconductor/electronic-component manufacturing.

**Interpretation:** Utilization describes the share of estimated industry capacity in use. **Excludes:** advanced-node, HBM, packaging, accelerator, and other AI-specific capacity breakouts.
""",

    "U.S. Compute Manufacturing Investment": """
Tracks announced private capital spending and direct federal awards across official U.S. compute-manufacturing projects.

**Interpretation:** Expected private investment shows the scale of planned manufacturing buildout, while direct awards show the public funding contribution. The project set covers leading-edge logic, memory, packaging, photonics, and other compute-enabling layers. Announced investment is not completed construction or production output.
""",


    "Buildout Leadership Rotation": """
Compares rolling year-over-year construction growth across data centers, compute manufacturing, electric power, communications, and public water. Quarterly snapshots show which layer of the physical AI stack is absorbing the strongest current investment momentum.

**Interpretation:** Leadership rotation is a flow measure, not a verdict on long-run importance. A sharp slowdown can reflect normalization from an unusually high base after an earlier investment surge, so momentum should be read alongside current spending levels.
""",

    "Net Infrastructure Support Balance": """
Compares six enabling systems with channel-specific lagged baselines. Compute manufacturing, electric power, and communications are benchmarked to broad private-construction denominators; public water, roads and highways, and public transit are benchmarked to their lagged shares of the selected public-system construction mix.

Net support balance = Σ(observed component − expected baseline component)

**Interpretation:** Positive and negative deviations are both included. Gross positive excess reports only channels above baseline and is a secondary diagnostic; the net balance is the headline measure because it also includes below-baseline channels. This is a statistical composition relationship, not causal AI attribution or a measure of physical capacity adequacy.
""",

    "Communication Construction": """
Measures private construction spending on communication infrastructure.

**Interpretation:** Broad supporting-infrastructure context; no AI- or data-center-attributable share.
""",

    "Public Highway and Street Construction": """
Measures the seasonally adjusted annual rate of public highway and street construction spending.

**Interpretation:** The series describes broad transport-system investment. It is not allocated specifically to AI-related projects.
""",

    "Public Transportation Construction": """
Measures the seasonally adjusted annual rate of public transportation construction spending.

**Interpretation:** The series provides supporting-infrastructure context and is not an AI-attributed measure.
""",

    "Public Water Supply Construction": """
Measures the seasonally adjusted annual rate of public water-supply construction spending.

**Interpretation:** The series provides broad supporting-system context. It is capital spending on public water infrastructure, not facility withdrawal, consumptive use, legal access, or AI-attributed investment.
""",

    "Adult Generative-AI Use": """
Share of U.S. adults age 18–64 reporting generative-AI use for work, personal use, or both.

**Source:** Real-Time Population Survey via FRED, series `RPSGENAIUSAGESHAREALL`.

**Interpretation:** This is a nationally representative quarterly survey estimate of reported use. It measures reach, not frequency, spending, paid conversion, provider market share, or broader economic results.
""",

    "Personal Generative-AI Use": """
Share of U.S. adults age 18–64 reporting generative-AI use outside work for personal purposes.

**Source:** Real-Time Population Survey via FRED, series `RPSGENAIUSAGESHARENONWORK`.

**Interpretation:** Direct measure of reported personal AI use. **Breakouts unavailable:** free versus paid use and provider.
""",

    "Work Generative-AI Use": """
Share of employed U.S. adults age 18–64 reporting generative-AI use for their job.

**Source:** Real-Time Population Survey via FRED, series `RPSGENAIUSAGESHAREWORK`.

**Interpretation:** The denominator is employed adults, unlike the all-adult overall and personal-use series. Reported work use is not the same as employer-level deployment or workflow integration.
""",

    "Weekly Generative-AI Use": """
Share of U.S. adults age 18–64 reporting generative-AI use for any purpose during the prior week.

**Source:** Real-Time Population Survey via FRED, series `RPSGENAIUSAGESHARELWALL`.

**Interpretation:** Stricter engagement measure than general adoption; occasional users outside the prior week are excluded. **Excludes:** paid use and revenue.
""",

    "Daily Generative-AI Use": """
Share of U.S. adults age 18–64 reporting generative-AI use every day during the prior week for personal use, every workday for work use, or both.

**Source:** Real-Time Population Survey via FRED, series `RPSGENAIUSAGESHAREEDLWALL`.

**Interpretation:** This is the strongest available public indicator of habitual engagement. It is not a subscription, retention-cohort, or monetization measure.
""",

    "Current Business AI Use": """
Share of U.S. employer businesses reporting that they used artificial intelligence in at least one business function during the prior two weeks.

**Source:** U.S. Census Bureau, Business Trends and Outlook Survey.

**Interpretation:** Weighted survey estimate for U.S. employer businesses; published standard errors are shown. **Excludes:** usage intensity, productivity, return on investment, and labor effects.
""",

    "Expected Business AI Use": """
Share of U.S. employer businesses expecting to use artificial intelligence in at least one business function during the next six months.

**Interpretation:** This is a weighted survey estimate of stated near-term intent, with the published standard error. It is not committed implementation or guaranteed future adoption.
""",

    "Expected Adoption Gap": """
Difference between expected business AI use within six months and current reported use.

Expected Adoption Gap = Expected Business AI Use − Current Business AI Use

**Interpretation:** A positive value indicates more businesses expect to use AI than currently report using it. It is stated intent, not committed implementation. No confidence interval is reported for the difference because the published tables do not provide covariance between the paired estimates.
""",

    "Adoption Breadth": """
Compares current and expected AI use across major U.S. industries.

**Interpretation:** Broader adoption means reported use is distributed across more BTOS industry groups rather than concentrated in a few. Sector estimates retain standard errors and missing/suppressed values; this is breadth across the survey frame, not use intensity.
""",

    "Business-Function AI Deployment": """
Share of businesses using AI in a named function during the prior six months, expressed as a share of businesses using AI in at least one function.

**Source:** U.S. Census BTOS 2026 AI Supplement. The published function-level rates are conditionalized using Census's 27.7% pooled functional-use benchmark.

**Interpretation:** This dated cross-section shows where functional adopters report deployment. It is not a time series, a measure of use intensity, or evidence that the function was transformed. Conditionalized standard errors are unavailable because the published tables do not provide the required covariance.
""",

    "Employee Generative-AI Task Use": """
Share of businesses reporting employee Generative AI use that identify a named work-task category during the prior six months.

**Source:** U.S. Census BTOS 2026 AI Supplement.

**Interpretation:** The denominator is businesses reporting employee Generative AI task use, not all workers or all businesses. Categories may overlap, so their shares do not sum to 100%.
""",

    "AI-Related Organizational Change": """
Share of AI-using businesses reporting training, workflow, data, infrastructure, staffing, or external-support changes during the prior six months.

**Source:** U.S. Census BTOS 2026 AI Supplement.

**Interpretation:** The categories are reported organizational responses associated with AI use. They may overlap and do not establish productivity effects or causation.
""",

    "Purpose Statement": """
AI Macro is a research platform that examines the development of the U.S. AI economy from capital investment and physical construction through deployment, adoption, and economic results. It uses publicly available data to relate corporate and market activity to the physical systems required to support the buildout. It evaluates the extent to which that investment produces durable economic value and how its effects are transmitted through the broader U.S. economy.
""",

    "Interconnection Pipeline": """
Tracks active U.S. generator and storage interconnection requests using Berkeley Lab component accounting.

**Interpretation:** Requested queue capacity is not operating, financed, or deliverable capacity. Projects may withdraw, resize, change technology, or remain constrained by transmission and study requirements.
""",

    "Advanced-Stage Queue Share": """
Share of submitted active interconnection capacity whose records indicate an executed interconnection agreement or construction-stage status.

**Interpretation:** A higher share indicates more capacity beyond early study stages. Energization timing and firm deliverability remain unresolved.
""",

    "Electric Storage Deployment": """
Combines EIA operating battery power and energy capacity with submitted storage components in the active Berkeley Lab interconnection queue.

**Interpretation:** Operating capacity and queued capacity remain separate. Queue storage is requested capacity, not installed capacity, and hybrid projects use component-level accounting.
""",

    "Queue Conversion": """
Historical outcomes for U.S. interconnection requests submitted from 2000 through 2020, paired with the current active pipeline.

**Measures:** Operational, withdrawn, and still-active shares; draft or executed agreements; and request-to-operation time.
""",

    "Summer Reserve Margins": """
NERC summer reserve margins under anticipated, typical-outage, and extreme-condition scenarios.

**Units:** Percent of available resources above forecast demand for each assessment area and scenario.
""",

    "Operating Storage Duration": """
EIA operating battery nameplate energy divided by nameplate power, grouped into duration bands.

**Units:** Power in gigawatts, energy in gigawatt-hours, and duration in hours.
""",

    "State Water Exposure": """
Data-center facilities and published capacity by state, paired with July 2026 U.S. Drought Monitor area shares.

**Use:** Current geographic exposure screening at the state level.
""",

    "Campus Water Exposure Dossier": """
Campus development status, published capacity, state drought conditions, cooling method, water source, reclaimed-water evidence, and quantified-use disclosure.

**Use:** Facility-level research and disclosure comparison.
""",

    "AI-Linked Employment Footprint": """
Tracks BLS employment in computer-systems design, computing-infrastructure services, semiconductor manufacturing, and power-and-communication-line construction from 2020 to the present.

**Interpretation:** These industries are directly connected to the AI production and deployment stack, but their full employment changes are not attributed to AI.
""",

    "LLM Task Exposure Benchmark": """
Occupation-level task-exposure estimates from Eloundou, Manning, Mishkin, and Rock's **GPTs are GPTs** research dataset, using human ratings for direct LLM exposure and exposure when LLM-powered software is included.

**Interpretation:** Exposure is the share of an occupation's tasks affected under the study rubric. The benchmark is static and unweighted by current employment. **Excludes:** observed AI use, automation, displacement, job loss, productivity, and adoption timing.
""",

    "Supporting Labor Demand": """
Tracks BLS JOLTS job openings, hires, quits, and layoffs-and-discharges rates in information, manufacturing, construction, and professional and business services.

**Interpretation:** Broad labor-market context around AI-linked industries; no AI-specific vacancy, hire, quit, or displacement attribution.
""",

    "Labor-Flow Rates": """
BLS JOLTS job openings, hires, quits, and layoffs-and-discharges expressed as rates within each broad labor market.

**Interpretation:** Openings indicate unmet demand; hires show actual recruitment; quits signal worker mobility; layoffs and discharges show employer-initiated separation pressure. The industries are broader than AI, with no causal attribution.
""",

    "AI-Linked Wage Trajectory": """
Tracks average hourly earnings in directly relevant technology, semiconductor, and infrastructure-construction industries.

**Interpretation:** Wage changes can reflect labor scarcity, worker composition, inflation, bargaining conditions, and industry mix. AI attribution remains separate.
""",

    "Real Earnings Breadth": """
Counts how many selected AI-linked industries have positive year-over-year average-hourly-earnings growth after adjustment with the all-items CPI.

**Interpretation:** Breadth shows the number of selected labor channels with purchasing-power gains. **Excludes:** household income, benefits, hours, and worker-level distribution.
""",

    "Workforce Outcomes Matrix": """
Places observed employment growth and CPI-adjusted earnings growth beside JOLTS openings, hires, quits, and layoffs-and-discharges rates for the broad labor market mapped to each AI-linked industry.

**Interpretation:** The matrix distinguishes observed labor outcomes from generalized claims about AI exposure. Mapping a detailed industry to a broad JOLTS market provides context, not causal attribution or an occupation-level measure.
""",

    "Labor Productivity": """
BLS nonfarm-business and manufacturing output-per-hour measures.

**Interpretation:** Productivity is an observed economic outcome and one test of whether a large investment cycle is producing more output per hour. Quarterly movements are not attributed to AI without causal evidence.
""",

    "Real Value-Added Output": """
BLS real value-added output for nonfarm business and manufacturing.

**Interpretation:** This measures inflation-adjusted production in the underlying sector account. It is not an AI-specific output series.
""",

    "Hourly Compensation": """
BLS compensation per hour in the nonfarm-business productivity account.

**Interpretation:** Pair with productivity to assess labor capture. **Breakouts unavailable:** occupations and income groups.
""",

    "Real Hourly Compensation": """
BLS nonfarm-business compensation per hour adjusted for consumer-price change in the Labor Productivity and Costs program.

**Interpretation:** Compare with labor productivity over matching periods. Aggregate production-account measure; no worker-level distribution.
""",

    "Labor Share": """
BLS nonfarm-business labor-share index, measuring the share of current-dollar output paid as employee compensation.

**Interpretation:** A falling index means compensation accounts for a smaller share of output. The counterpart may include profit, depreciation, taxes, or other income components.
""",

    "Productivity–Compensation Gap": """
Difference between cumulative nonfarm-business labor-productivity growth and cumulative real-hourly-compensation growth from the 2020 baseline.

Productivity–Compensation Gap = Productivity growth since 2020 − Real hourly compensation growth since 2020

**Interpretation:** A positive gap means output per hour has grown faster than workers' inflation-adjusted compensation per hour. The comparison is descriptive and is not an estimate of AI's causal contribution.
""",

    "Median Real Weekly Earnings": """
BLS Current Population Survey median usual weekly earnings for full-time wage and salary workers, converted to constant purchasing-power dollars by BLS.

**Interpretation:** The median describes the middle full-time wage and salary worker. **Excludes:** self-employment, wealth gains, benefits, and household composition.
""",

    "Broad Participation": """
Compares real median weekly earnings across women and men and across White, Black, Hispanic or Latino, and Asian full-time wage and salary workers.

**Interpretation:** Compares real-earnings growth across available national groups. Categories are not exhaustive; most race and ethnicity series are unadjusted. **Uncontrolled dimensions:** occupation, hours, education, age, geography, and household structure.
""",

    "Inflation-Adjusted Realized Growth": """
The Economic Outcomes comparison keeps BLS labor productivity and real output in their published inflation-adjusted form, while converting hourly compensation and unit labor costs using the latest year-over-year CPI change.

**Interpretation:** The adjustment separates purchasing-power growth from nominal growth. It is a descriptive normalization, not an estimate of AI's causal contribution.
""",

    "Unit Labor Costs": """
BLS labor compensation required to produce one unit of output.

**Interpretation:** Growth can reflect compensation rising faster than productivity. It is a production-cost measure, not a market valuation or stock-price signal.
""",

    "Information-Processing Investment": """
BEA investment in information-processing equipment and software, published through FRED.

**Interpretation:** This is broader than AI investment. It supplies a consistent capital-spending benchmark for comparing investment growth with output and productivity.
""",

    "Wastewater System Investment": """
U.S. Census seasonally adjusted annual rate of public sewage and waste-disposal construction spending.

**Interpretation:** This is a chronological public-system investment series, not a measure of wastewater volumes, treatment headroom, discharge permits, or AI-attributed spending.
""",

}
