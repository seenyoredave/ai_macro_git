import pandas as pd 
import numpy as np 

from config.field_config import (
    FIELD_GROUPS,
    FIELD_PRIORITY
)


def resolve_field(field_name, source_data):

    group = FIELD_GROUPS.get(field_name)

    if group is None:
        return np.nan

    priorities = FIELD_PRIORITY[group]

    for source in priorities:

        value = source_data.get(source, {}).get(field_name)

        if pd.notna(value):
            return value

    return np.nan

def resolve_sector_dataframe(raw_data):

    yf_df = raw_data.get("yfinance")
    edgar = raw_data.get("edgar", {})

    if yf_df is None or yf_df.empty:
        return pd.DataFrame()

    rows = []
    
    for _, row in yf_df.iterrows():

        ticker = row["Ticker"]

        source_data = {
            "YFinance": row.to_dict(),
            "EDGAR": edgar.get(ticker, {}),
        }

        rows.append({
            "Ticker": ticker,
            "Company": row["Company"],
            "Price": resolve_field("Price", source_data),
            "P/E": resolve_field("P/E", source_data),
            "Forward P/E": resolve_field("Forward P/E", source_data),
            "Market Cap": resolve_field("Market Cap", source_data),
            "Revenue": resolve_field("Revenue", source_data),
            "Revenue Growth": resolve_field("Revenue Growth", source_data),
            "CapEx": resolve_field("CapEx", source_data),
            "CapEx Growth": resolve_field("CapEx Growth", source_data),
            "Operating Cash Flow": resolve_field("Operating Cash Flow", source_data),
            "Free Cash Flow": resolve_field("Free Cash Flow", source_data),
            "Net Income": resolve_field("Net Income", source_data),
            "EBITDA": resolve_field("EBITDA", source_data),
            "Total Debt": resolve_field("Total Debt", source_data),
            "Cash": resolve_field("Cash", source_data),
            "Net Debt": resolve_field("Net Debt", source_data),
            "Beta": resolve_field("Beta", source_data),
            "52W High": resolve_field("52W High", source_data),
            "52W Low": resolve_field("52W Low", source_data),
            "1Y Return": resolve_field("1Y Return", source_data),
        })
   
    return pd.DataFrame(rows)
