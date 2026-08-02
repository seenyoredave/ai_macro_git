DEFAULT_FACTORS = [
    "forward_ebit_yield_discount",
    "relative_performance",
    "market_breadth",
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
    "forward_ebit_yield_discount": (
        "QQQ proxy forward EBIT yield minus the sector aggregate forward EBIT yield. "
        "Positive values indicate a richer sector valuation."
    ),
    "relative_performance": (
        "Basket-weighted sector 1Y return minus the weighted QQQ top-10 proxy return."
    ),
    "market_breadth": "Share of sector stocks trading above their 200-day moving average.",
}

FACTOR_DISPLAY_NAMES = {
    "forward_ebit_yield_discount": "Forward EBIT-Yield Valuation",
    "relative_performance": "1Y Relative Return",
    "market_breadth": "Market Breadth",
}
