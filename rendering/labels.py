import pandas as pd

from config.sector_config import SECTOR_DISPLAY_NAMES

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

def power_capacity_gap_label(score):
    if pd.isna(score):
        return "No Data"
    if score < -20:
        return "Power Response Leading"
    if score < 20:
        return "Deployment and Power Aligned"
    if score < 40:
        return "Deployment Outpacing Power"
    return "Large Capacity Gap"

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
    key = str(sector).upper()
    label = SECTOR_DISPLAY_NAMES.get(
        key,
        str(sector).replace("_", " ").title(),
    )
    return label.upper() if style == "upper" else label
