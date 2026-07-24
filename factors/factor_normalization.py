"""Raw AI Equity Index factor normalization."""

import numpy as np
import pandas as pd


def soft_clip(value, scale):
    if pd.isna(value):
        return np.nan
    return np.tanh(float(value) / scale)


def normalize_relative_performance(value):
    # A 30-percentage-point one-year relative return is a large regime signal.
    return soft_clip(value, 0.30)


def normalize_forward_ebit_yield_discount(value):
    # A four-percentage-point operating-earnings-yield discount is substantial.
    return soft_clip(value, 0.04)


def normalize_market_breadth(value):
    if pd.isna(value):
        return np.nan
    return np.clip((float(value) - 0.50) / 0.50, -1, 1)


NORMALIZERS = {
    "relative_performance": normalize_relative_performance,
    "forward_ebit_yield_discount": normalize_forward_ebit_yield_discount,
    "market_breadth": normalize_market_breadth,
}


def normalize_factor(factor_name, value):
    if factor_name not in NORMALIZERS:
        raise ValueError(f"Unknown factor: {factor_name}")
    return NORMALIZERS[factor_name](value)
