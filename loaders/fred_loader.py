
import streamlit as st 
import numpy as np 
from fredapi import Fred

from config import fred_indicators 

def get_fred_client():

    key = st.secrets.get("FRED_API_KEY")

    if not key:
        return None

    return Fred(api_key=key)


@st.cache_data(ttl=86400)
def load_fred():

    fred = get_fred_client()

    if fred is None:
        return {}

    data = {}

    for name, series_id in fred_indicators.FRED_INDICATORS.items():

        try:

            series = fred.get_series(series_id)

            clean = series.dropna()

            if clean.empty:
                raise ValueError("No data returned")

            data[name] = {
                "value": float(clean.iloc[-1]),
                "date": clean.index[-1].isoformat() if hasattr(clean.index[-1], "isoformat") else str(clean.index[-1])
            }

        except Exception as e:

            print(
                f"FRED failed: {name} ({series_id}) -> {e}"
            )

            data[name] = {
                "value": np.nan,
                "date": None
            }

    return data
