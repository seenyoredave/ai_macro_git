This project seeks to quantify and ****distinguish genuine AI-driven
economic transformation from AI-driven capital speculation**** through use of novel and industry-standard
measures drawing from publicly available market and Federal Reserve economic
data.

Questions we seek to
answer include:

Can we adequately define the stages of the AI maturation cycle by sector and use sector development to
track the progression of AI build-out in the economy at large?

Can we use power consumption and grid expansion as an adequate proxies of AI build-out phase and
rate?

Can we determine if AI adaptation is occurring in a wide swath of society or is concentrated in specific
industries?

Can we determine if AI adaptation is economically benefitting a wide swath of society or is concentrated largely
in the hands of the investor class?

Does the progression of AI build-out follow a predictable and linear path that may enable non-institutional investors to capitalize on the economic upheaval caused by market-driven AI implementation?

Data sources include: YFinance, FRED, EDGAR, and put/call.

Metric definitions:

Maturation cycle: How developed is the AI ecosystem?
MCS = weighted average of all sector scores

Measures overall economic progress towards completion of AI buildout cycle
Scale: 0-100.

Divergence estimation : Is value creation broadening or concentrating?
DE = MCS - average speculation pressure.
Measures relative strength of buildout vs speculative pressure.
Scale: -100 <> +100.

Power stress index: PSI = current utility/electric power activity - trailing historical average
Measures how far current electricity demand pressure is running above its recent historical baseline.
Scale: 0 - 100

Concentration HHI:
Herfindahl-Herschman Index = ∑(market cap)^2 for each company within total AI basket
Measures whether AI-related market value is concentrated in a few dominant firms or spread across the broader AI ecosystem.
Scale: 0 – 100 – higher = more diffusion

Reality Gap: Do consumers and investors agree?
RG = normalized investor sentiment (put/call) – normalized consumer sentiment (CPI)
Scale: +/- -->  + = speculation, - = retraction

Liquidity Gap: Is AI strength being supported by monetary conditions?
LG = MCS – normalized fed funds liquidity score
Scale: +/- --> + = liquidity crunch, - = investors nervous

Adoption Gap: Is deployment keeping pace with enthusiasm?
AG = MCS – normalized industrial production score
Scale: +/- --> + = AI buildout getting ahead of economy at large, - = economic buildout happening without AI sector

Current regime = phase of AI buildout based upon MCS
Early phase: <30
Expansion phase: 30-59
Late expansion phase: 60-79
Mature buildout phase: 80+

Factor Metrics

Relative Performance = average sector 1Y return - benchmark 1Y return

Valuation Premium = average sector Forward P/E / benchmark Forward P/E

Momentum Breadth = number of sector stocks with positive 1Y return / total valid stocks

Dispersion = standard deviation of sector 1Y returns

Raw Score = normalized -1 to +1
Display Score = ((Raw Score + 1) / 2) * 100
