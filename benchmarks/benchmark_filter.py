import numpy as np


REQUIRED_FIELDS = [

    "Forward P/E",
    "1Y Return"
]


def filter_benchmark(df):

    if df.empty:
        return df

    df = df.replace(
        [np.inf, -np.inf],
        np.nan
    )

    df = df.dropna(
        subset=REQUIRED_FIELDS
    )

    return (
        df
        .reset_index(drop=True)
        .copy()
    )