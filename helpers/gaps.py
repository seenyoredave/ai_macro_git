### These functions feed the gap tools that seek to merge FRED data
### with market data to create a more robust picture of the AI sector.

import pandas as pd
import numpy as np

from helpers.macro_normalization import normalize_industrial_production
from config.debug_config import DEBUG, debug_print


def as_decimal_rate(value):
    """
    Converts either decimal rates or percent values into decimal form.

    Examples:
      0.12 -> 0.12
      12.0 -> 0.12
    """
    if pd.isna(value):
        return np.nan

    value = float(value)

    # Most financial growth values from yfinance arrive as decimals.
    # Most FRED percent-change series arrive as percent values.
    if abs(value) > 2:
        return value / 100

    return value


def mean_numeric(df, column, min_count=2):
    """
    Returns the mean of a numeric dataframe column.

    min_count=2 keeps the metric from being based on a single company,
    but is less brittle than requiring 3+ valid rows during development.
    """
    if df is None or df.empty or column not in df.columns:
        return np.nan

    values = pd.to_numeric(df[column], errors="coerce").dropna()

    if len(values) < min_count:
        return np.nan

    return float(values.mean())


def extract_payload_value(payload):
    """
    Handles FRED payloads that may be either:
    - {"value": x, "date": y}
    - raw numeric values
    """
    if isinstance(payload, dict):
        return payload.get("value", np.nan)

    return payload


def fred_value(fred_data, key):
    """
    Exact-key FRED lookup.
    """
    if not fred_data:
        return np.nan

    payload = fred_data.get(key, {})
    return extract_payload_value(payload)


def fred_value_any(fred_data, possible_keys):
    """
    More forgiving FRED lookup.

    Tries exact keys first, then case-insensitive matching.
    This protects against naming drift like:
      "Financial Conditions NFCI"
      "NFCI"
      "National Financial Conditions Index"
    """
    if not fred_data:
        return np.nan

    # Exact match first
    for key in possible_keys:
        if key in fred_data:
            return extract_payload_value(fred_data[key])

    # Case-insensitive fallback
    normalized_lookup = {
        str(k).lower().strip(): k
        for k in fred_data.keys()
    }

    for key in possible_keys:
        normalized_key = str(key).lower().strip()
        if normalized_key in normalized_lookup:
            actual_key = normalized_lookup[normalized_key]
            return extract_payload_value(fred_data[actual_key])

    return np.nan


def find_sector_df(sector_data, requested_sector):
    """
    Finds the requested sector dataframe.

    First tries exact match. If that fails, tries to find a sector key
    containing ENTERPRISE or SOFTWARE.
    """
    if not sector_data:
        return None, None

    if requested_sector in sector_data:
        return sector_data.get(requested_sector), requested_sector

    for key in sector_data.keys():
        key_upper = str(key).upper()

        if "ENTERPRISE" in key_upper or "SOFTWARE" in key_upper:
            return sector_data.get(key), key

    return None, None


def validation_gap(
    sector_data,
    fred_data,
    sector="ENTERPRISE_AI_SOFTWARE",
):
    """
    Economic Validation Gap.

    Measures whether AI software/product capex growth is outrunning:
      1. software-company revenue growth
      2. broader macro software/information investment growth

    Positive = capex is running ahead of validation.
    Negative = monetization/macro validation is keeping up.
    """

    df, sector_used = find_sector_df(sector_data, sector)

    if df is None or df.empty:
        if DEBUG:
            debug_print("EVG ERROR: no usable sector dataframe.")
            debug_print("EVG requested sector:", sector)
            debug_print(
                "EVG available sectors:",
                list(sector_data.keys()) if sector_data else []
            )
        return np.nan

    capex_growth = mean_numeric(df, "CapEx Growth", min_count=2)
    revenue_growth = mean_numeric(df, "Revenue Growth", min_count=2)

    macro_growth = fred_value_any(
        fred_data,
        [
            "Info Processing Investment Growth",
            "Information Processing Investment Growth",
            "Software Investment Growth",
            "Real Private Fixed Investment: Information Processing Equipment and Software",
            "A679RL1Q225SBEA",
        ],
    )

    capex_growth = as_decimal_rate(capex_growth)
    revenue_growth = as_decimal_rate(revenue_growth)
    macro_growth = as_decimal_rate(macro_growth)

    if DEBUG:
        debug_print("EVG requested sector:", sector)
        debug_print("EVG sector used:", sector_used)
        debug_print("EVG df columns:", list(df.columns))
        debug_print("EVG capex_growth:", capex_growth)
        debug_print("EVG revenue_growth:", revenue_growth)
        debug_print("EVG macro_growth:", macro_growth)
        debug_print(
            "EVG available FRED keys:",
            list(fred_data.keys()) if fred_data else []
        )

    if any(pd.isna(x) for x in [capex_growth, revenue_growth, macro_growth]):
        return np.nan

    raw_gap = capex_growth - revenue_growth - macro_growth

    # Dashboard score, in percentage points
    return float(np.clip(raw_gap * 100, -100, 100))


def normalize_nfci_liquidity(nfci):
    """
    Converts NFCI into a 0-100 liquidity-support score.

    NFCI:
      negative = looser than average
      positive = tighter than average

    Score:
      100 = very supportive liquidity
       50 = neutral
        0 = very tight liquidity
    """

    if pd.isna(nfci):
        return np.nan

    nfci = float(nfci)

    # Rough static band:
    # NFCI <= -1: very loose
    # NFCI  =  0: neutral
    # NFCI >= +1: very tight
    liquidity_support = 50 - (nfci * 50)

    return float(np.clip(liquidity_support, 0, 100))


def liquidity_gap(macro_df, fred_data):
    """
    Liquidity Support Gap.

    Measures whether AI risk appetite is outrunning broad financial liquidity.

    Positive = AI risk appetite exceeds liquidity support.
    Negative = liquidity is supportive relative to AI market appetite.
    """

    if macro_df is None or macro_df.empty:
        if DEBUG:
            debug_print("LSG ERROR: macro_df is empty.")
        return np.nan

    if "Pressure" not in macro_df.columns:
        if DEBUG:
            debug_print("LSG ERROR: Pressure column missing.")
            debug_print("LSG macro_df columns:", list(macro_df.columns))
        return np.nan

    ai_risk_appetite = pd.to_numeric(
        macro_df["Pressure"],
        errors="coerce",
    ).dropna().mean()

    nfci = fred_value_any(
        fred_data,
        [
            "Financial Conditions NFCI",
            "NFCI",
            "National Financial Conditions Index",
            "Chicago Fed NFCI",
        ],
    )

    liquidity_support = normalize_nfci_liquidity(nfci)

    if DEBUG:
        debug_print("LSG ai_risk_appetite:", ai_risk_appetite)
        debug_print("LSG nfci:", nfci)
        debug_print("LSG liquidity_support:", liquidity_support)
        debug_print(
            "LSG available FRED keys:",
            list(fred_data.keys()) if fred_data else []
        )

    if pd.isna(ai_risk_appetite) or pd.isna(liquidity_support):
        return np.nan

    return float(np.clip(ai_risk_appetite - liquidity_support, -100, 100))


def adoption_gap(ai_temp, industrial_production):
    """
    Keep the existing adoption gap for now.
    We can redesign this later.
    """

    if pd.isna(ai_temp):
        return np.nan

    if pd.isna(industrial_production):
        return np.nan

    economy_score = normalize_industrial_production(industrial_production)

    return ai_temp - economy_score