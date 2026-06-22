### These functions create the labels for the macroeconomic indicator badges 

import pandas as pd


def validation_label(score):
    if pd.isna(score):
        return "No Data"

    if score < -25:
        return "Validation Ahead of Capex"
    elif score < -10:
        return "Validation Supportive"
    elif score < 10:
        return "Balanced"
    elif score < 25:
        return "Capex Running Ahead"
    else:
        return "Overbuild Pressure"
    
def liquidity_label(score):
    if pd.isna(score):
        return "No Data"

    if score < -25:
        return "Liquidity Strongly Supportive"
    elif score < -10:
        return "Liquidity Supportive"
    elif score < 10:
        return "Liquidity Aligned"
    elif score < 25:
        return "Risk Appetite Ahead of Liquidity"
    else:
        return "Liquidity Disconnect"

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
        "DATA_AI_INFRASTRUCTURE": "Data Stack",
        "DATA_CENTER_INFRASTRUCTURE": "Data Centers",
        "POWER_GRID": "Power",
        "ENTERPRISE_AI_SOFTWARE": "Enterprise",
        "CYBERSECURITY_AI_TRUST": "Security",
        "INDUSTRIAL_AUTOMATION": "Automation",
        "ROBOTICS": "Robotics",
        "DEFENSE_NATIONAL_SECURITY": "Defense",
        "CONSUMER_AI": "Consumer AI"
    }

    label = label_map.get(
        str(sector).upper(),
        str(sector).replace("_", " ").title()
    )

    
    if style == "upper":
        return label.upper()

    return label
