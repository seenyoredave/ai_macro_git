**Project statement:**

This project seeks to quantify and distinguish genuine AI-driven economic transformation from AI-driven capital speculation through use of novel and industry-standard measures drawing from publicly available market and Federal Reserve economic data.

**Questions I seek to answer include:** 

* Can we adequately define the stages of the AI maturation cycle by sector and use sector development to track the progression of AI build-out in the economy at large?
* Can we use power consumption and grid expansion as an adequate proxies of AI build-out phase and rate?

* Can we determine if AI adaptation is occurring in a wide swath of society or is concentrated in specific industries?
* Can we determine if AI adaptation is economically benefitting a wide swath of society or is concentrated largely in the hands of the investor class?

* Does the progression of AI build-out follow a predictable and linear path that may enable non-institutional investors to capitalize on the economic upheaval caused by market-driven AI implementation?


**Data sources include:** YFinance, FRED, EDGAR, and put/call.


**Economic metric definitions:** 

Maturation cycle: How developed is the AI ecosystem?

* MCS = weighted average of all sector scores
* Measures overall economic progress towards completion of AI buildout cycle
* Scale: 0-100.

Divergence estimation : Is value creation broadening or concentrating?

* DE = MCS - average speculation pressure.
* Measures relative strength of buildout vs speculative pressure.
* Scale: -100 <> +100.

Power stress index:

* PSI = current utility/electric power activity - trailing historical average
* Measures how far current electricity demand pressure is running above its recent historical baseline.
* Scale: 0 - 100

Concentration HHI:

* Herfindahl-Herschman Index = ∑(market cap)^2 for each company within total AI basket
* Measures whether AI-related market value is concentrated in a few dominant firms or spread across the broader AI ecosystem.
* Scale: 0 – 100 –-> higher = more diffusion

Reality Gap: Do consumers and investors agree?

* RG = normalized investor sentiment (put/call) – normalized consumer sentiment (CPI)
* Scale: +/- --> (+) = speculation, (-) = recession

Liquidity Gap: Is AI strength being supported by monetary conditions?

* LG = MCS – normalized fed funds liquidity score
* Scale: +/- --> (+) = liquidity crunch, (-) = investors nervous

Adoption Gap: Is deployment keeping pace with enthusiasm?

* AG = MCS – normalized industrial production score
* Scale: +/- --> (+) = AI buildout getting ahead of economy at large, (-) = economic buildout happening without AI sector

Current regime = phase of AI buildout based upon MCS

* Early phase: <30
* Expansion phase: 30-59
* Late expansion phase: 60-79
* Mature buildout phase: 80+


**Factor Metric Definitions:**

Relative Performance = average sector 1Y return - benchmark 1Y return

Answers the question: “how well is this sector performing vs benchmark over the past year?”

Valuation Premium = average sector Forward P/E / benchmark Forward P/E

Answers the question: “how much valuation confidence do investors have in this sector vs benchmark?”

Momentum Breadth = number of sector stocks with positive 1Y return /total valid stocks

Answers the question: “how well is the sector performing in aggregate?”

Dispersion = standard deviation of sector 1Y returns

Answers the question: “are there clear winners and losers within each sector over the past year?”


**Grapics:** 

AI sector position map: this uses two widely used market metrics (1YR and FP/E) to approximate where each sector is in terms of revenue vs valuation. General interpretation should use quadrant labels.

AI sector rotation matrix: this uses my proprietary metrics (MCS and speculation pressure (MCS – weighted*MCS) to approximate how bubble-like the behavior of each sector is as it trends through the phases of market maturation. General interpretation should use quadrant labels.


**Factor metrics:**

Relative performance: RP = sector 1YR – benchmark 1YR

Valuation premium: VP = sector forward P/E / benchmark forward P/E

Momentum breadth: MB = share of sector stocks with (+) 1YR

Dispersion: D = variation in 1YR across the sector baskets
