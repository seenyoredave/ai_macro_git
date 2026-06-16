METRIC_DEFINITIONS = {
    "Maturation Cycle": """
    MCS = weighted average of all sector scores
    
    Measures overall economic progress towards completion of AI buildout cycle

    Scale: 0-100.
    Higher values suggest a more mature or advanced cycle position. 
    """,

    "Divergence Estimate": """
    DE = MCS - average speculation pressure.

    Measures relative strength of buildout vs speculative pressure. 
    
    Scale: -100 <> +100.
    Positive values suggest AI buildout strength exceeds speculative pressure.
    Negative values suggest speculation may be running ahead of buildout.
    """,
    
    "Power Stress Index": """
    PSI = current utility/electric power activity - trailing historical average
    
    Measures how far current electricity demand pressure is running above its recent historical baseline.
    
    Scale: 0 - 100
    A rising Power Stress Index suggests that AI infrastructure demand may be creating a larger physical footprint in the economy.
    """,

    "Concentration HHI": """
    Herfindahl-Hirschman Index = ∑(market cap)^2 for each company within total AI basket
    
    Measures whether AI-related market value is concentrated in a few dominant firms or spread across the broader AI ecosystem.
    
    Scale: 0 - 100
    Higher values mean more concentration; lower values mean broader diffusion.
    """,
    
    "Reality Gap": """
    RG = normalized investor sentiment - normalized consumer sentiment.

    Positive values suggest market optimism is running ahead of consumer confidence.
    Negative values suggest consumer confidence is stronger than market enthusiasm.
    """,

    "Liquidity Gap": """
    LG = MCS - normalized Fed Funds liquidity score.

    Positive values suggest AI market enthusiasm is running ahead of monetary liquidity conditions.
    Negative values suggest liquidity conditions are supportive relative to AI market enthusiasm.
    """,

    "Adoption Gap": """
    Adoption Gap = AI Buildout Score - normalized Industrial Production score.

    Positive values suggest AI market enthusiasm is ahead of broad real-economy production.
    Negative values suggest real-economy activity is stronger than AI market enthusiasm.
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