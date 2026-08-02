from __future__ import annotations

import re

import pandas as pd

def clean_header(value) -> str:
    text = str(value).replace("\n_x000D_", " ").replace("\n", " ")
    return " ".join(text.split()).strip()

def parse_census_month(value):
    if value is None or pd.isna(value):
        return pd.NaT
    text = re.sub(r"[pr]$", "", str(value).strip(), flags=re.IGNORECASE)
    return pd.to_datetime(text, format="%b-%y", errors="coerce")
