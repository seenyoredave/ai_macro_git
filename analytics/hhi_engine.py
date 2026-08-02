from __future__ import annotations

import numpy as np
import pandas as pd

SECTOR_CONCENTRATION_VERSION = "1.0"

def _positive_market_caps(frame: pd.DataFrame | None) -> pd.Series:
    if frame is None or frame.empty or "Market Cap" not in frame.columns:
        return pd.Series(dtype=float)
    caps = pd.to_numeric(frame["Market Cap"], errors="coerce")
    return caps[np.isfinite(caps) & caps.gt(0)].astype(float)

def calc_hhi_from_sector_data(sector_data):
    if not sector_data:
        return np.nan

    market_caps = []
    for frame in sector_data.values():
        market_caps.extend(_positive_market_caps(frame).tolist())

    if not market_caps:
        return np.nan

    values = np.asarray(market_caps, dtype=float)
    shares = values / values.sum()
    return float(np.sum(shares**2))

def normalize_hhi(hhi):
    value = pd.to_numeric(hhi, errors="coerce")
    if pd.isna(value) or not np.isfinite(value):
        return np.nan
    return float(np.clip((float(value) - 0.01) / (0.25 - 0.01) * 100, 0, 100))

def adjusted_hhi(raw_hhi, constituent_count):
    value = pd.to_numeric(raw_hhi, errors="coerce")
    count = pd.to_numeric(constituent_count, errors="coerce")
    if pd.isna(value) or not np.isfinite(value) or pd.isna(count) or count < 2:
        return np.nan
    floor = 1.0 / float(count)
    denominator = 1.0 - floor
    if denominator <= 0:
        return np.nan
    return float(np.clip((float(value) - floor) / denominator * 100.0, 0.0, 100.0))

def sector_basket_concentration(frame: pd.DataFrame | None, *, min_count: int = 3) -> dict:
    total_count = int(len(frame)) if isinstance(frame, pd.DataFrame) else 0
    caps = _positive_market_caps(frame)
    valid_count = int(len(caps))
    coverage = float(valid_count / total_count) if total_count else 0.0
    if valid_count < max(int(min_count), 2):
        return {
            "raw_hhi": np.nan,
            "adjusted_hhi": np.nan,
            "effective_firms": np.nan,
            "valid_company_count": valid_count,
            "total_company_count": total_count,
            "coverage": coverage,
            "version": SECTOR_CONCENTRATION_VERSION,
        }

    shares = caps.to_numpy(dtype=float) / float(caps.sum())
    raw = float(np.sum(shares**2))
    return {
        "raw_hhi": raw,
        "adjusted_hhi": adjusted_hhi(raw, valid_count),
        "effective_firms": float(1.0 / raw) if raw > 0 else np.nan,
        "valid_company_count": valid_count,
        "total_company_count": total_count,
        "coverage": coverage,
        "version": SECTOR_CONCENTRATION_VERSION,
    }

def sector_hhi_component_breakdown(frame: pd.DataFrame | None, top_n: int = 8) -> pd.DataFrame:
    columns = [
        "Company",
        "Market Cap",
        "Market Cap Share",
        "Raw HHI Contribution",
        "HHI Contribution Share",
    ]
    if frame is None or frame.empty or "Market Cap" not in frame.columns:
        return pd.DataFrame(columns=columns)
    tickers = (
        frame["Ticker"].astype(str)
        if "Ticker" in frame.columns
        else pd.Series(frame.index.astype(str), index=frame.index)
    )
    caps = pd.to_numeric(frame["Market Cap"], errors="coerce")
    valid = caps.notna() & np.isfinite(caps) & caps.gt(0)
    if valid.sum() < 2:
        return pd.DataFrame(columns=columns)
    out = pd.DataFrame({"Company": tickers.loc[valid], "Market Cap": caps.loc[valid].astype(float)})
    total = float(out["Market Cap"].sum())
    out["Market Cap Share"] = out["Market Cap"] / total
    out["Raw HHI Contribution"] = out["Market Cap Share"] ** 2
    raw = float(out["Raw HHI Contribution"].sum())
    out["HHI Contribution Share"] = out["Raw HHI Contribution"] / raw * 100.0
    out = out.sort_values("HHI Contribution Share", ascending=False, kind="stable")
    top_n = max(int(top_n), 1)
    if len(out) <= top_n:
        return out[columns].reset_index(drop=True)
    top = out.iloc[:top_n].copy()
    remainder = out.iloc[top_n:]
    other = pd.DataFrame([{
        "Company": "Other",
        "Market Cap": float(remainder["Market Cap"].sum()),
        "Market Cap Share": float(remainder["Market Cap Share"].sum()),
        "Raw HHI Contribution": float(remainder["Raw HHI Contribution"].sum()),
        "HHI Contribution Share": float(remainder["HHI Contribution Share"].sum()),
    }])
    return pd.concat([top[columns], other[columns]], ignore_index=True)
