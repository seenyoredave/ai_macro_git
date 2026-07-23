"""Market-cap concentration calculations."""

from __future__ import annotations

import numpy as np
import pandas as pd


def calc_hhi_from_sector_data(sector_data):
    """Calculate raw HHI from positive company market capitalizations."""
    if not sector_data:
        return np.nan

    market_caps = []
    for frame in sector_data.values():
        if frame is None or frame.empty or "Market Cap" not in frame.columns:
            continue
        caps = pd.to_numeric(frame["Market Cap"], errors="coerce")
        caps = caps[np.isfinite(caps) & (caps > 0)]
        market_caps.extend(caps.tolist())

    if not market_caps:
        return np.nan

    values = np.asarray(market_caps, dtype=float)
    shares = values / values.sum()
    return float(np.sum(shares**2))


def normalize_hhi(hhi):
    """Map raw HHI from the fixed 0.01–0.25 reference interval to 0–100."""
    value = pd.to_numeric(hhi, errors="coerce")
    if pd.isna(value) or not np.isfinite(value):
        return np.nan
    return float(np.clip((float(value) - 0.01) / (0.25 - 0.01) * 100, 0, 100))
