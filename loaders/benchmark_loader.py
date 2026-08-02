from config.benchmark_config import (
    BENCHMARK_UNIVERSES,
    BENCHMARK_WEIGHTS,
)
from loaders.market_loader import load_yfinance

def load_benchmark(
    name: str,
    *,
    force_refresh: bool = False,
    refresh_token: int = 0,
    clock_token: str | None = None,
):
    if name not in BENCHMARK_UNIVERSES:
        raise ValueError(f"Unknown benchmark: {name}")

    members = BENCHMARK_UNIVERSES[name]
    if not members:
        return None

    frame = load_yfinance(
        tuple(sorted(members.items())),
        force_refresh=bool(force_refresh),
        refresh_token=int(refresh_token),
        clock_token=clock_token,
    ).copy()
    weights = BENCHMARK_WEIGHTS.get(name)
    if not weights:
        raise ValueError(f"Active benchmark {name} has no configured weights")

    frame["Benchmark Weight"] = frame["Ticker"].map(weights)
    return frame
