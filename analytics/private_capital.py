"""Public-LP private-capital realization analytics.

The retained cohort is deliberately narrow: technology-specialist and
technology-heavy venture/growth fund families disclosed by CalSTRS.  The
module derives standard ILPA-style multiples from reported paid-in capital,
distributions, and remaining NAV.  It does not attribute fund results solely
to AI investments.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "private_capital" / "fund_performance.csv"
METADATA_PATH = PROJECT_ROOT / "data" / "private_capital" / "metadata.json"


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame.get(column), errors="coerce").replace([np.inf, -np.inf], np.nan)


def load_private_capital_funds() -> pd.DataFrame:
    """Load the retained public-LP cohort and derive comparable multiples."""
    if not DATA_PATH.exists():
        return pd.DataFrame()
    frame = pd.read_csv(DATA_PATH)
    required = {
        "Manager", "Fund", "Vintage", "Exposure Tier", "Paid In Capital",
        "Distributions", "NAV", "Net IRR", "Source As Of",
    }
    if not required.issubset(frame.columns):
        return pd.DataFrame()

    for column in ("Vintage", "Capital Committed", "Paid In Capital", "Distributions", "NAV", "Net IRR"):
        frame[column] = _numeric(frame, column)
    frame["Source As Of"] = pd.to_datetime(frame["Source As Of"], errors="coerce")
    frame = frame.loc[frame["Paid In Capital"].gt(0) & frame["Vintage"].notna()].copy()
    if frame.empty:
        return frame

    paid_in = frame["Paid In Capital"]
    frame["DPI"] = frame["Distributions"] / paid_in
    frame["RVPI"] = frame["NAV"] / paid_in
    frame["TVPI"] = (frame["Distributions"] + frame["NAV"]) / paid_in
    denominator = frame["Distributions"] + frame["NAV"]
    frame["Realized Share"] = np.where(denominator.gt(0), frame["Distributions"] / denominator, np.nan)
    source_year = frame["Source As Of"].dt.year
    frame["Fund Age"] = source_year - frame["Vintage"]
    frame["Maturity"] = np.select(
        [frame["Fund Age"].ge(5), frame["Fund Age"].ge(3)],
        ["Mature (5y+)", "Developing (3-4y)"],
        default="Young (0-2y)",
    )
    return frame.sort_values(["Vintage", "Manager", "Fund"], ascending=[False, True, True], kind="stable").reset_index(drop=True)


def load_private_capital_metadata() -> dict:
    if not METADATA_PATH.exists():
        return {}
    try:
        return json.loads(METADATA_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _pooled_metrics(frame: pd.DataFrame) -> dict:
    if frame is None or frame.empty:
        return {}
    paid_in = float(_numeric(frame, "Paid In Capital").sum())
    distributed = float(_numeric(frame, "Distributions").sum())
    nav = float(_numeric(frame, "NAV").sum())
    total_value = distributed + nav
    if paid_in <= 0:
        return {}
    irr = _numeric(frame, "Net IRR").dropna()
    return {
        "fund_count": int(len(frame)),
        "manager_count": int(frame["Manager"].nunique()),
        "paid_in": paid_in,
        "distributed": distributed,
        "nav": nav,
        "dpi": distributed / paid_in,
        "rvpi": nav / paid_in,
        "tvpi": total_value / paid_in,
        "realized_share": distributed / total_value if total_value > 0 else np.nan,
        "median_net_irr": float(irr.median()) if not irr.empty else np.nan,
    }


def build_private_capital_realization() -> dict:
    """Return fund detail, mature-cohort headlines, and audit metadata."""
    funds = load_private_capital_funds()
    metadata = load_private_capital_metadata()
    if funds.empty:
        return {"funds": funds, "mature_funds": funds, "metrics": {}, "all_metrics": {}, "metadata": metadata}

    mature = funds.loc[funds["Fund Age"].ge(5)].copy()
    return {
        "funds": funds,
        "mature_funds": mature,
        "metrics": _pooled_metrics(mature),
        "all_metrics": _pooled_metrics(funds),
        "metadata": metadata,
        "as_of": funds["Source As Of"].max(),
    }
