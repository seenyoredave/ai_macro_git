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
            "Forward EV/EBIT": resolve_field("Forward EV/EBIT", source_data),
            "Market Cap": resolve_field("Market Cap", source_data),
            "Enterprise Value": resolve_field("Enterprise Value", source_data),
            "Revenue": resolve_field("Revenue", source_data),
            "Forward Revenue": resolve_field("Forward Revenue", source_data),
            "Operating Income": resolve_field("Operating Income", source_data),
            "Operating Margin": resolve_field("Operating Margin", source_data),
            "Forward EBIT": resolve_field("Forward EBIT", source_data),
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
            "FCF Margin YoY Change": resolve_field("FCF Margin YoY Change", source_data),
            "Net Debt / EBITDA YoY Change": resolve_field(
                "Net Debt / EBITDA YoY Change", source_data
            ),
            "CapEx / OCF YoY Change": resolve_field("CapEx / OCF YoY Change", source_data),
            "Beta": resolve_field("Beta", source_data),
            "52W High": resolve_field("52W High", source_data),
            "52W Low": resolve_field("52W Low", source_data),
            "1Y Return": resolve_field("1Y Return", source_data),
            "Price Extension 200D": resolve_field("Price Extension 200D", source_data),
            "Momentum Acceleration": resolve_field("Momentum Acceleration", source_data),
            "Volatility Expansion": resolve_field("Volatility Expansion", source_data),
            "Volume Activity": resolve_field("Volume Activity", source_data),
        })
   
    out = pd.DataFrame(rows)
    if not out.empty and {"Enterprise Value", "Forward EBIT"}.issubset(out.columns):
        enterprise_value = pd.to_numeric(out["Enterprise Value"], errors="coerce")
        forward_ebit = pd.to_numeric(out["Forward EBIT"], errors="coerce")
        valid = (
            enterprise_value.notna()
            & np.isfinite(enterprise_value)
            & enterprise_value.gt(0)
            & forward_ebit.notna()
            & np.isfinite(forward_ebit)
            & forward_ebit.abs().gt(1e-9)
        )
        signed_multiple = (enterprise_value / forward_ebit).where(valid)
        existing = pd.to_numeric(out.get("Forward EV/EBIT"), errors="coerce")
        out["Forward EV/EBIT"] = signed_multiple.combine_first(existing)
    return out
