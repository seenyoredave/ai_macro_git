DEFAULT_FACTORS = [
    "relative_performance",
    "market_breadth",
]

from config.sector_config import SECTOR_CONFIG

FACTOR_CONFIG = {
    sector: list(DEFAULT_FACTORS)
    for sector in SECTOR_CONFIG
}


FACTOR_HELP = {
    "relative_performance": (
        "Equal-weight sector 1Y return minus the weighted QQQ top-10 proxy return."
    ),
    "market_breadth": "Share of sector stocks trading above their 200-day moving average.",
}

FACTOR_DISPLAY_NAMES = {
    "relative_performance": "1Y Relative Return",
    "market_breadth": "Market Breadth",
}
