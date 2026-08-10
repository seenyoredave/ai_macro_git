from __future__ import annotations

from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALUATION_CONTEXT_PATH = PROJECT_ROOT / "data" / "market_valuation_context.csv"


def load_market_valuation_context(path: str | Path | None = None) -> dict:
    target = Path(path) if path else VALUATION_CONTEXT_PATH
    if not target.exists() or target.stat().st_size == 0:
        return {}
    frame = pd.read_csv(target)
    if frame.empty:
        return {}
    row = frame.iloc[-1]
    return {
        "cape": pd.to_numeric(row.get("Value"), errors="coerce"),
        "as_of_date": row.get("As Of Date"),
        "historical_peak": pd.to_numeric(row.get("Historical Peak"), errors="coerce"),
        "historical_peak_date": row.get("Historical Peak Date"),
        "historical_mean": pd.to_numeric(row.get("Historical Mean"), errors="coerce"),
        "historical_median": pd.to_numeric(row.get("Historical Median"), errors="coerce"),
        "source": row.get("Source"),
        "source_url": row.get("Source URL"),
        "notes": row.get("Notes"),
    }
