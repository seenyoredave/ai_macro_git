#################################################
# AI EQUITY INDEX FACTOR CONFIG
#################################################

DEFAULT_FACTORS = [
    "relative_performance",
    "earnings_yield_discount",
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
    "relative_performance": "Sector mean 1Y return minus the QQQ top-10 proxy mean 1Y return.",
    "earnings_yield_discount": "Benchmark earnings yield minus sector mean positive earnings yield. Positive values indicate a richer sector valuation.",
    "momentum_breadth": "Share of sector stocks with positive 1Y returns.",
    "dispersion": "Variation in 1Y returns across the sector basket; lower dispersion contributes a higher AEI factor score.",
}
