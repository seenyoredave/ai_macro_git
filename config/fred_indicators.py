FRED_INDICATORS = {
    "Fed Funds Rate": "FEDFUNDS",
    "10Y Treasury Yield": "GS10",
    "2Y Treasury Yield": "GS2",
    "CPI": "CPIAUCSL",
    "Unemployment Rate": "UNRATE",
    "PPI": "PPIACO",
    "Industrial Production": "INDPRO",
    "Consumer Sentiment": "UMCSENT",
    "Financial Conditions NFCI": "NFCI",
    "Info Processing Investment Growth": "A679RL1Q225SBEA",
    "Business Loan Tightening": "SUBLPDMBSXWBNQ",
    "Bank Tier 1 Capital Ratio": "BOGZ1FL010000016Q",

    # Power Stress Index inputs. All five are monthly, seasonally adjusted.
    "Commercial Electricity Sales": "IPN22112CS",
    "Residential Electricity Sales": "IPN22112RS",
    "Electric Power Capacity Utilization": "CAPUTLG2211S",
    "Electric Power Output": "IPG2211S",
    "Electric Power Capacity": "CAPG2211S",
}

# Derived from the full live FRED series before only the latest observation is
# retained in the dashboard payload/archive.
DERIVED_FRED_INDICATORS = [
    "Industrial Production YoY",
    "Commercial Electricity Sales YoY",
    "Residential Electricity Sales YoY",
    "Electric Power Output YoY",
    "Electric Power Capacity YoY",
]


def all_indicator_names():
    return list(FRED_INDICATORS.keys()) + list(DERIVED_FRED_INDICATORS)


POWER_REQUIRED_INDICATORS = [
    "Commercial Electricity Sales YoY",
    "Residential Electricity Sales YoY",
    "Electric Power Capacity Utilization",
    "Electric Power Output YoY",
    "Electric Power Capacity YoY",
]
