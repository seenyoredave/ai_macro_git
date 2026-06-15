#################################################
# FACTOR CONFIG
#################################################
FACTOR_CONFIG = {

    "COMPUTE": [
        "relative_performance",
        "valuation_premium",
        "momentum_breadth",
        "dispersion",
    ],

    "SEMICAP_EQUIPMENT": [
        "relative_performance",
        "valuation_premium",
        "momentum_breadth",
        "dispersion",
    ],

    "CLOUD_HYPERSCALERS": [
        "relative_performance",
        "valuation_premium",
        "momentum_breadth",
        "dispersion",
    ],

    "DATA_CENTER_INFRASTRUCTURE": [
        "relative_performance",
        "valuation_premium",
        "momentum_breadth",
        "dispersion",
    ],

    "POWER_GRID": [
        "relative_performance",
        "valuation_premium",
        "momentum_breadth",
        "dispersion",
    ],

    "ENTERPRISE_AI_SOFTWARE": [
        "relative_performance",
        "valuation_premium",
        "momentum_breadth",
        "dispersion",
    ],

    "AI_SECURITY": [
        "relative_performance",
        "valuation_premium",
        "momentum_breadth",
        "dispersion",
    ],

    "PHYSICAL_AI_ROBOTICS": [
        "relative_performance",
        "valuation_premium",
        "momentum_breadth",
        "dispersion",
    ],

    "DEFENSE_NATIONAL_SECURITY": [
        "relative_performance",
        "valuation_premium",
        "momentum_breadth",
        "dispersion",
    ],
}


FACTOR_HELP = {
    "relative_performance": "RP = sector 1Y return - benchmark 1Y return.",
    "valuation_premium": "VP = sector forward P/E / benchmark forward P/E.",
    "momentum_breadth": "MB = share of sector stocks with positive 1Y returns.",
    "dispersion": "D = variation in 1Y returns across the sector basket.",
}