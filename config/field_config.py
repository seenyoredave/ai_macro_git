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
    "financial_strain": ["YFinance"],
    "macro_indicators": ["FRED"]
}

# Map fields to groups
FIELD_GROUPS = {
    "P/E": "fundamentals",
    "Forward EV/EBIT": "financial_strain",
    "Market Cap": "fundamentals",
    "Enterprise Value": "financial_strain",
    "Revenue": "fundamentals",
    "Forward Revenue": "financial_strain",
    "Operating Income": "financial_strain",
    "Operating Margin": "financial_strain",
    "Forward EBIT": "financial_strain",
    "Revenue Growth": "fundamentals",
    "CapEx": "fundamentals",
    "CapEx Growth": "fundamentals",
    "Operating Cash Flow": "financial_strain",
    "Free Cash Flow": "financial_strain",
    "Net Income": "financial_strain",
    "EBITDA": "financial_strain",
    "Total Debt": "financial_strain",
    "Cash": "financial_strain",
    "Net Debt": "financial_strain",
    "FCF Margin YoY Change": "financial_strain",
    "Net Debt / EBITDA YoY Change": "financial_strain",
    "CapEx / OCF YoY Change": "financial_strain",
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