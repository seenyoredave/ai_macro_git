import pandas as pd


def validation_label(score):
    if pd.isna(score):
        return "No Data"
    if score < -25:
        return "Validation Ahead of Capex"
    if score < -10:
        return "Validation Supportive"
    if score < 10:
        return "Balanced"
    if score < 25:
        return "Capex Running Ahead"
    return "Overbuild Pressure"


def liquidity_label(score):
    if pd.isna(score):
        return "No Data"
    if score < -25:
        return "Liquidity Strongly Supportive"
    if score < -10:
        return "Liquidity Supportive"
    if score < 10:
        return "Liquidity Aligned"
    if score < 25:
        return "Risk Appetite Ahead of Liquidity"
    return "Liquidity Disconnect"


def adoption_label(score):
    if pd.isna(score):
        return "No Data"
    if score < -20:
        return "Industrial Growth Leading"
    if score < 20:
        return "Development and Industry Aligned"
    if score < 40:
        return "AI Development Leading"
    return "AI Development Far Ahead"


def speculation_label(score):
    if pd.isna(score):
        return "No Data"
    if score < -20:
        return "Development Ahead of Equities"
    if score < 20:
        return "Equities and Development Aligned"
    if score < 40:
        return "Equities Running Ahead"
    return "Large Speculation Gap"


def short_regime_label(score):
    if pd.isna(score):
        return "No Data"
    if score < 30:
        return "Weak"
    if score < 60:
        return "Neutral"
    if score < 80:
        return "Strong"
    return "Extended"


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
        "CONSUMER_AI": "Consumer AI",
    }
    label = label_map.get(
        str(sector).upper(),
        str(sector).replace("_", " ").title(),
    )
    return label.upper() if style == "upper" else label
