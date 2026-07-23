"""Raw AI Equity Index factor normalization."""

import numpy as np
import pandas as pd


def soft_clip(value, scale):
    if pd.isna(value):
        return np.nan
    return np.tanh(float(value) / scale)


def normalize_relative_performance(value):
    return soft_clip(value, 2.50)


def normalize_earnings_yield_discount(value):
    # A three-percentage-point earnings-yield discount/premium is already a
    # material valuation difference, so this factor uses a tighter scale than
    # return dispersion.
    return soft_clip(value, 0.03)


def normalize_momentum_breadth(value):
    if pd.isna(value):
        return np.nan
    return np.clip((float(value) - 0.50) / 0.50, -1, 1)


def normalize_dispersion(value):
    if pd.isna(value):
        return np.nan
    return -soft_clip(value, 2.50)




NORMALIZERS = {
    "relative_performance": normalize_relative_performance,
    "earnings_yield_discount": normalize_earnings_yield_discount,
    "momentum_breadth": normalize_momentum_breadth,
    "dispersion": normalize_dispersion,
}


def normalize_factor(factor_name, value):
    if factor_name not in NORMALIZERS:
        raise ValueError(f"Unknown factor: {factor_name}")
    return NORMALIZERS[factor_name](value)
