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


def hhi_component_breakdown(sector_data, top_n=5):
    """Return company-level contributions to the current raw HHI.

    Each company contributes its squared market-cap share. The returned
    ``HHI Contribution Share`` expresses that squared-share contribution as a
    percentage of total HHI, making the additive decomposition readable while
    preserving the raw market-cap share for context.
    """
    columns = [
        "Company",
        "Market Cap",
        "Market Cap Share",
        "Raw HHI Contribution",
        "HHI Contribution Share",
    ]
    if not sector_data:
        return pd.DataFrame(columns=columns)

    rows = []
    for sector, frame in sector_data.items():
        if frame is None or frame.empty or "Market Cap" not in frame.columns:
            continue
        tickers = (
            frame["Ticker"].astype(str)
            if "Ticker" in frame.columns
            else pd.Series(frame.index.astype(str), index=frame.index)
        )
        caps = pd.to_numeric(frame["Market Cap"], errors="coerce")
        valid = caps.notna() & np.isfinite(caps) & caps.gt(0)
        for ticker, cap in zip(tickers.loc[valid], caps.loc[valid]):
            rows.append({"Company": str(ticker), "Market Cap": float(cap)})

    if not rows:
        return pd.DataFrame(columns=columns)

    out = pd.DataFrame(rows)
    total_cap = float(out["Market Cap"].sum())
    if total_cap <= 0:
        return pd.DataFrame(columns=columns)

    out["Market Cap Share"] = out["Market Cap"] / total_cap
    out["Raw HHI Contribution"] = out["Market Cap Share"] ** 2
    raw_hhi = float(out["Raw HHI Contribution"].sum())
    out["HHI Contribution Share"] = (
        out["Raw HHI Contribution"] / raw_hhi * 100.0
        if raw_hhi > 0
        else np.nan
    )
    out = out.sort_values("HHI Contribution Share", ascending=False, kind="stable")

    top_n = max(int(top_n), 1)
    if len(out) <= top_n:
        return out[columns].reset_index(drop=True)

    top = out.iloc[:top_n].copy()
    remainder = out.iloc[top_n:]
    other = pd.DataFrame([
        {
            "Company": "Other",
            "Market Cap": float(remainder["Market Cap"].sum()),
            "Market Cap Share": float(remainder["Market Cap Share"].sum()),
            "Raw HHI Contribution": float(remainder["Raw HHI Contribution"].sum()),
            "HHI Contribution Share": float(remainder["HHI Contribution Share"].sum()),
        }
    ])
    return pd.concat([top[columns], other[columns]], ignore_index=True)
