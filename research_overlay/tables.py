"""Pure dataframe preparation helpers for the research overlay."""

from __future__ import annotations

import pandas as pd


def _company_table(df):
    columns = [
        "Ticker",
        "Company",
        "Price",
        "P/E",
        "Forward EV/EBIT",
        "1Y Return",
        "Market Cap",
        "Revenue",
        "Revenue Growth",
        "CapEx",
        "CapEx Growth",
        "Beta",
        "Basket Tier",
        "Basket Weight",
        "AI Weight",
    ]
    available = [column for column in columns if column in df.columns]
    table = df[available].copy()

    # Display large dollar values in millions while retaining numeric columns
    # for sorting. Column names carry the unit so the table stays compact.
    for column in ("Market Cap", "Revenue", "CapEx"):
        if column in table.columns:
            table[column] = (
                pd.to_numeric(table[column], errors="coerce") / 1_000_000.0
            ).round(1)
    table = table.rename(columns={
        "Market Cap": "Market Cap ($M)",
        "Revenue": "Revenue ($M)",
        "CapEx": "CapEx ($M)",
    })

    for column in ("1Y Return", "Revenue Growth", "CapEx Growth"):
        if column in table.columns:
            table[column] = (pd.to_numeric(table[column], errors="coerce") * 100.0).round(2)
    table = table.rename(columns={
        "1Y Return": "1Y Return (%)",
        "Revenue Growth": "Revenue Growth (%)",
        "CapEx Growth": "CapEx Growth (%)",
    })

    for column, digits in {
        "Price": 2,
        "P/E": 1,
        "Forward EV/EBIT": 1,
        "Beta": 2,
        "Basket Weight": 2,
        "AI Weight": 2,
    }.items():
        if column in table.columns:
            table[column] = pd.to_numeric(table[column], errors="coerce").round(digits)
    return table

