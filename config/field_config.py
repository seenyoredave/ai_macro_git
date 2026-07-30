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
    "fundamentals": ["EDGAR", "YFinance"],
    "market_prices": ["YFinance"],
    "financial_condition": ["YFinance"],
    "macro_indicators": ["FRED"]
}

# Map fields to groups
FIELD_GROUPS = {
    "P/E": "fundamentals",
    "Forward EV/EBIT": "fundamentals",
    "Market Cap": "fundamentals",
    "Enterprise Value": "fundamentals",
    "Revenue": "fundamentals",
    "Forward Revenue": "fundamentals",
    "Operating Income": "fundamentals",
    "Operating Margin": "fundamentals",
    "Forward EBIT": "fundamentals",
    "Revenue Growth": "fundamentals",
    "CapEx": "fundamentals",
    "CapEx Growth": "fundamentals",
    "Operating Cash Flow": "financial_condition",
    "Free Cash Flow": "financial_condition",
    "Net Income": "financial_condition",
    "EBITDA": "financial_condition",
    "Total Debt": "financial_condition",
    "Cash": "financial_condition",
    "Net Debt": "financial_condition",
    "FCF Margin YoY Change": "financial_condition",
    "Net Debt / EBITDA YoY Change": "financial_condition",
    "CapEx / OCF YoY Change": "financial_condition",
    "1Y Return": "market_prices",
    "Price Extension 200D": "market_prices",
    "Momentum Acceleration": "market_prices",
    "Volatility Expansion": "market_prices",
    "Volume Activity": "market_prices",
    "Beta": "market_prices",
    "Price": "market_prices",
    "52W High": "market_prices",
    "52W Low": "market_prices",
    "PMI": "macro_indicators",
    "Yield": "macro_indicators",
}