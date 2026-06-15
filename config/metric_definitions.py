METRIC_DEFINITIONS = {
    "Cycle Score": """
    Weighted composite score measuring where a sector appears to be in the AI market cycle.

    Current inputs:
    - Relative Performance
    - Valuation Premium
    - Momentum Breadth
    - Dispersion

    Scale: 0–100.
    Higher values suggest a more mature or advanced cycle position.
    """,

    "Speculation Pressure": """
    Composite score measuring bubble-like or crowded behavior within a sector.

    Current inputs:
    - Valuation Premium
    - Relative Performance
    - Dispersion Pressure
    - Momentum Breadth

    Scale: 0–100.
    Higher values suggest greater speculative pressure.
    """,

    "AI Divergence": """
    AI Divergence = average Cycle Score - average Speculation Pressure.

    Scale: approximately -100 to +100.

    Positive values suggest AI buildout strength exceeds speculative pressure.
    Negative values suggest speculation may be running ahead of buildout.
    """,

    "Reality Gap": """
    Reality Gap = normalized investor sentiment - normalized consumer sentiment.

    Positive values suggest market optimism is running ahead of consumer confidence.
    Negative values suggest consumer confidence is stronger than market enthusiasm.
    """,

    "Liquidity Gap": """
    Liquidity Gap = AI Buildout Score - normalized Fed Funds liquidity score.

    Positive values suggest AI market enthusiasm is running ahead of monetary liquidity conditions.
    Negative values suggest liquidity conditions are supportive relative to AI market enthusiasm.
    """,

    "Adoption Gap": """
    Adoption Gap = AI Buildout Score - normalized Industrial Production score.

    Positive values suggest AI market enthusiasm is ahead of broad real-economy production.
    Negative values suggest real-economy activity is stronger than AI market enthusiasm.
    """,

    "AI Maturation Score": """
    AI Maturation Score = average Cycle Score across all AI sectors.

    Measures the broad market-implied maturity of the AI buildout.
    """,
}




"""
when its time to set up hover boxes over each section to explain the calculations, look here. 


from config.metric_definitions import METRIC_DEFINITIONS

st.subheader("Regime Snapshot",help=METRIC_DEFINITIONS["AI Buildout Score"])
#Shows the current AI cycle state using sector scores,
#macro gaps, and sentiment/liquidity indicators.

st.metric(
    "Reality Gap",
    fmt_score(reality_gap),
    help=METRIC_DEFINITIONS["Reality Gap"]
)

st.metric(
    "Liquidity Gap",
    fmt_score(liquidity_gap),
    help=METRIC_DEFINITIONS["Liquidity Gap"]
)

st.metric(
    "Adoption Gap",
    fmt_score(adoption_gap),
    help=METRIC_DEFINITIONS["Adoption Gap"]
)

And so on... 

#Reality Gap = normalized investor sentiment - normalized consumer sentiment.

#Positive values suggest market enthusiasm is running ahead of consumer confidence.

Any updates to the info within the help boxes will occur above. 

"""