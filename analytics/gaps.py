from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.scoring import tanh_score

def industrial_growth_gap(adi, industrial_production_growth):
    if pd.isna(adi) or pd.isna(industrial_production_growth):
        return np.nan

    industrial_score = tanh_score(
        industrial_production_growth,
        center=0.02,
        scale=0.05,
    )

    if pd.isna(industrial_score):
        return np.nan

    return float(np.clip(float(adi) - industrial_score, -100, 100))
