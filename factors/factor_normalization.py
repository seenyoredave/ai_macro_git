### raw factor --> normalized factor ###

import numpy as np


#################################################
# SOFT CAP NORMALIZATION
#
# CURRENTLY ACTIVE
#################################################

def soft_clip(value, scale):

    if np.isnan(value):
        return np.nan

    return np.tanh(value / scale)

def normalize_relative_performance(value):

    return soft_clip(
        value,
        2.50
    )


def normalize_valuation_premium(value):

    if np.isnan(value):
        return np.nan

    return soft_clip(
        value - 1.0,
        1.00
    )


def normalize_momentum_breadth(value):

    if np.isnan(value):
        return np.nan

    return np.clip(
        (value - 0.50) / 0.50,
        -1,
        1
    )


def normalize_dispersion(value):

    if np.isnan(value):
        return np.nan

    return -soft_clip(
        value,
        2.50
    )


#################################################
# ACTIVE DISPATCH TABLE
#################################################

NORMALIZERS = {

    "relative_performance":
        normalize_relative_performance,

    "valuation_premium":
        normalize_valuation_premium,

    "momentum_breadth":
        normalize_momentum_breadth,

    "dispersion":
        normalize_dispersion
}


def normalize_factor(
    factor_name,
    value
):

    if factor_name not in NORMALIZERS:

        raise ValueError(
            f"Unknown factor: {factor_name}"
        )

    return NORMALIZERS[factor_name](value)



""" 
current map: 

data_loader
↓
sector_builder
↓
sector_dataframe
↓
factor_engine
↓
factor_normalization
↓
factor_weights
↓
sector_engine
↓
regime_engine
↓
dashboard
"""