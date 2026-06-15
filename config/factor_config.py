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
    "relative_performance": "Sector 1Y return minus benchmark 1Y return.",
    "valuation_premium": "Sector forward P/E divided by benchmark forward P/E.",
    "momentum_breadth": "Share of sector stocks with positive 1Y returns.",
    "dispersion": "Variation in 1Y returns across the sector basket.",
}