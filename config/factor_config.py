#################################################
# FACTOR CONFIG
#################################################

DEFAULT_FACTORS = [
    "relative_performance",
    "valuation_premium",
    "momentum_breadth",
    "dispersion",
]

FACTOR_CONFIG = {
    "COMPUTE": DEFAULT_FACTORS,
    "SEMICAP_EQUIPMENT": DEFAULT_FACTORS,
    "CLOUD_HYPERSCALERS": DEFAULT_FACTORS,
    "DATA_AI_INFRASTRUCTURE": DEFAULT_FACTORS,
    "DATA_CENTER_INFRASTRUCTURE": DEFAULT_FACTORS,
    "POWER_GRID": DEFAULT_FACTORS,
    "ENTERPRISE_AI_SOFTWARE": DEFAULT_FACTORS,
    "CYBERSECURITY_AI_TRUST": DEFAULT_FACTORS,
    "INDUSTRIAL_AUTOMATION": DEFAULT_FACTORS,
    "ROBOTICS": DEFAULT_FACTORS,
    "DEFENSE_NATIONAL_SECURITY": DEFAULT_FACTORS,
    "CONSUMER_AI": DEFAULT_FACTORS,
}

FACTOR_HELP = {
    "relative_performance": "RP = sector 1Y return - benchmark 1Y return.",
    "valuation_premium": "VP = sector forward P/E / benchmark forward P/E.",
    "momentum_breadth": "MB = share of sector stocks with positive 1Y returns.",
    "dispersion": "D = variation in 1Y returns across the sector basket.",
}