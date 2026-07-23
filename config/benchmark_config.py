"""Static benchmark proxy configuration.

QQQ is the only active runtime benchmark. SPY and DIA remain configured for
future use but are not downloaded or archived by the current page.
"""

QQQ_MEMBERS = {
    "NVDA": "NVIDIA Corp",
    "AAPL": "Apple Inc",
    "MSFT": "Microsoft Corp",
    "MU": "Micron Technology Inc",
    "AMZN": "Amazon.com Inc",
    "AMD": "Advanced Micro Devices Inc",
    "GOOGL": "Alphabet Inc Class A",
    "GOOG": "Alphabet Inc Class C",
    "META": "Meta Platforms Inc",
    "TSLA": "Tesla Inc",
}

# QQQ holdings snapshot dated 2026-07-21. The selected holdings represented
# 45.95% of QQQ; ratios are normalized to 100% for the ten-member proxy.
QQQ_RAW_WEIGHTS = {
    "NVDA": 8.05,
    "AAPL": 7.85,
    "MSFT": 4.89,
    "MU": 4.41,
    "AMZN": 4.40,
    "AMD": 3.71,
    "GOOGL": 3.35,
    "GOOG": 3.14,
    "META": 3.13,
    "TSLA": 3.02,
}
_QQQ_WEIGHT_TOTAL = sum(QQQ_RAW_WEIGHTS.values())
QQQ_WEIGHTS = {
    ticker: weight / _QQQ_WEIGHT_TOTAL
    for ticker, weight in QQQ_RAW_WEIGHTS.items()
}

SPY_MEMBERS = {
    "AAPL": "Apple Inc",
    "MSFT": "Microsoft Corp",
    "AMZN": "Amazon.com Inc",
    "NVDA": "NVIDIA Corp",
    "GOOGL": "Alphabet Inc Class A",
    "GOOG": "Alphabet Inc Class C",
    "BRK-B": "Berkshire Hathaway",
    "JPM": "JPMorgan Chase",
    "UNH": "UnitedHealth Group",
    "XOM": "Exxon Mobil",
}

DIA_MEMBERS = {
    "AAPL": "Apple Inc",
    "MSFT": "Microsoft Corp",
    "UNH": "UnitedHealth Group",
    "HD": "Home Depot",
    "GS": "Goldman Sachs",
    "MCD": "McDonald's",
    "V": "Visa Inc",
    "CRM": "Salesforce",
    "BA": "Boeing",
    "CAT": "Caterpillar",
}

BENCHMARK_UNIVERSES = {
    "QQQ": QQQ_MEMBERS,
    "SPY": SPY_MEMBERS,
    "DIA": DIA_MEMBERS,
}
BENCHMARK_WEIGHTS = {"QQQ": QQQ_WEIGHTS}
ACTIVE_BENCHMARKS = ("QQQ",)
BENCHMARK_VERSION = "2.0"
