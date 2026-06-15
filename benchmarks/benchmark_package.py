from dataclasses import dataclass
import pandas as pd


@dataclass
class BenchmarkPackage:
    name: str
    constituents: dict
    df: pd.DataFrame

    forward_pe: float
    avg_return: float
    beta: float
    member_count: int