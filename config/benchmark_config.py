import pandas as pd

#################################################
# STATIC INDEX CONSTITUENTS (STABLE SNAPSHOT)
#################################################

QQQ_MEMBERS = {
    # Nasdaq 100 representative subset (update periodically manually)
    "AAPL": "Apple Inc",
    "MSFT": "Microsoft Corp",
    "NVDA": "NVIDIA Corp",
    "AMZN": "Amazon.com Inc",
    "META": "Meta Platforms Inc",
    "AVGO": "Broadcom Inc",
    "TSLA": "Tesla Inc",
    "COST": "Costco Wholesale",
    "PEP": "PepsiCo Inc",
    "ADBE": "Adobe Inc",
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
    "CAT": "Caterpillar"
}

BENCHMARK_UNIVERSES = {
    "QQQ": QQQ_MEMBERS,
    "SPY": SPY_MEMBERS,
    "DIA": DIA_MEMBERS,
}