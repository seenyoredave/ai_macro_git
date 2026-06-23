def metric_help(key, fallback="Definition unavailable."):
    return METRIC_DEFINITIONS.get(key, fallback)


METRIC_DEFINITIONS = {
    "Maturation Index": """
    AMI = weighted average of all sector scores
    
    Measures overall economic progress towards completion of AI buildout cycle

    Scale: 0-100.
    Higher values suggest a more mature or advanced cycle position. 
    """,

    "Divergence Estimate": """
    DE = AMI - average speculation pressure.

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
    
    "Economic Validation Gap": """
    EVG = Enterprise AI CapEx Growth - Enterprise AI Revenue Growth - Macro Information-Processing Investment Growth

    EVG compares enterprise AI software-company capital spending pressure against company-level monetization and broader macro information-processing investment momentum.

    Positive values suggest AI capex is running ahead of company revenue growth and macro investment validation.
    Negative values suggest revenue growth and broader information-processing investment are keeping pace with, or exceeding, AI capex growth.

    This metric is intended as a capital-validation signal, not a precise accounting identity.
    """,

    "Liquidity Support Gap": """
    LSG = AI Risk Appetite - Macro Liquidity Support.

    AI Risk Appetite is proxied by average sector speculation pressure.
    Macro Liquidity Support is proxied by the inverted Chicago Fed NFCI.

    Positive values suggest AI risk appetite is running ahead of liquidity support.
    Negative values suggest liquidity conditions are supportive relative to AI risk appetite.
    """,
    
    "Adoption Gap": """
    AG = AMI - normalized industrial production score
    
    Compares the AI Maturation Index against broad industrial production.

    Positive values suggest the AI economy is advancing faster than the broader industrial economy.
    Negative values suggest broader industrial activity is keeping pace with, or exceeding, AI-cycle development.
        
    """,

    "Purpose Statement": """
    This project seeks to quantify and distinguish genuine AI-driven economic transformation 
    from AI-driven capital speculation through use of novel and industry-standard measures 
    drawing from publicly available market and Federal Reserve economic data. 
    """
}


