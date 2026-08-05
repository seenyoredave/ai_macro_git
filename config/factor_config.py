DEFAULT_FACTORS = [
    "forward_ebit_yield_discount",
    "relative_performance",
    "market_breadth",
]

from config.sector_config import SECTOR_CONFIG

INSURANCE_FACTORS = [
    "relative_performance",
    "market_breadth",
]

FACTOR_CONFIG = {
    sector: (INSURANCE_FACTORS if sector == "INSURANCE_RISK" else DEFAULT_FACTORS)
    for sector in SECTOR_CONFIG
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
