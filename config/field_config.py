"""
Central field classification registry.

FIELD_GROUPS:
    Maps dashboard fields to data groups.

FIELD_PRIORITY:
    Defines preferred source hierarchy for each group.

Used by loaders and factor calculations to determine
where metrics originate.

Currently most fields originate from a single source,
but this structure exists to support future multi-source
validation and fallback logic.

Example future use:

fundamentals:
    SEC -> YFinance -> AlphaVantage

market_prices:
    Polygon -> YFinance

macro_indicators:
    FRED -> BLS
"""

FIELD_PRIORITY = {
    "fundamentals": ["YFinance"],
    "market_prices": ["YFinance"],
    "macro_indicators": ["FRED"]
}

# Map fields to groups
FIELD_GROUPS = {

    "P/E": "fundamentals",
    "Forward P/E": "fundamentals",

    "Market Cap": "fundamentals",
    "Revenue": "fundamentals",
    "Revenue Growth": "fundamentals",

    "1Y Return": "market_prices",
    "Beta": "market_prices",
    "Price": "market_prices",
    "52W High": "market_prices",
    "52W Low": "market_prices",

    "PMI": "macro_indicators",
    "Yield": "macro_indicators"
}
