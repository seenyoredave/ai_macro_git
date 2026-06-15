### These functions create the labels for the macroeconomic indicator badges 

import pandas as pd


def reality_gap_label(score):

    if pd.isna(score):
        return "No Data"

    if score <= -25:
        return "Economic Confidence > Market Optimism"

    elif score < 10:
        return "Consumers Neutral"

    elif score < 30:
        return "Moderate Enthusiasm"

    else:
        return "AI Euphoria" 
   
def liquidity_label(score):

    if pd.isna(score):
        return "No Data"

    if score < -20:
        return "Liquidity Supports Risk"

    elif score < 20:
        return "Markets Aligned With Liquidity"

    elif score < 40:
        return "Risk Appetite Exceeding Liquidity"

    else:
        return "Speculative Liquidity Disconnect"

def adoption_label(score):

    if pd.isna(score):
        return "No Data"

    if score < -20:
        return "Economic Adoption Exceeding Market Expectations"

    elif score < 20:
        return "Market and Economy Aligned"

    elif score < 40:
        return "Market Leading Economic Adoption"

    else:
        return "Narrative Running Ahead of Adoption"
    
def short_regime_label(score):

    if pd.isna(score):
        return "No Data"

    if score < 30:
        return "Early Buildout"

    elif score < 60:
        return "Expansion"

    elif score < 80:
        return "Late Expansion"

    else:
        return "Mature Buildout"

def sector_display_name(sector, style="title"):

    label_map = {
        "COMPUTE": "Compute",
        "SEMICAP_EQUIPMENT": "Semicap",
        "CLOUD_HYPERSCALERS": "Cloud",
        "DATA_CENTER_INFRASTRUCTURE": "Data Centers",
        "POWER_GRID": "Power & Grid",
        "ENTERPRISE_AI_SOFTWARE": "Enterprise",
        "AI_SECURITY": "Security",
        "PHYSICAL_AI_ROBOTICS": "Physical AI",
        "DEFENSE_NATIONAL_SECURITY": "Defense",
    }

    label = label_map.get(
        str(sector).upper(),
        str(sector).replace("_", " ").title()
    )

    
    if style == "upper":
        return label.upper()

    return label
