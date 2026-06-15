import pandas as pd
import numpy as np

def normalize_benchmark_dataframe(df: pd.DataFrame) -> dict:
    df = df.copy()

    def safe_mean(col):
        if col not in df.columns:
            return np.nan
        return pd.to_numeric(df[col], errors="coerce").mean()

    def safe_nunique(col):
        if col not in df.columns:
            return 0
        return df[col].nunique(dropna=True)

    return {
        "forward_pe": safe_mean("Forward P/E"),
        "avg_return": safe_mean("1Y Return"),
        "beta": safe_mean("Beta"),
        "member_count": safe_nunique("Ticker")
    }