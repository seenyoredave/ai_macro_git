from loaders.benchmark_loader import load_benchmark
from benchmarks.benchmark_normalization import normalize_benchmark_dataframe
from loaders.benchmark_loader import get_constituents
from benchmarks.benchmark_package import BenchmarkPackage


def build_benchmark(name: str, df):

    constituents = get_constituents(name)

    metrics = normalize_benchmark_dataframe(df)

    return BenchmarkPackage(
        name=name,
        constituents=constituents,
        df=df,

        forward_pe=metrics["forward_pe"],
        avg_return=metrics["avg_return"],
        beta=metrics["beta"],
        member_count=metrics["member_count"]
    )


def build_all_benchmarks(load_yfinance_func):

    results = {}

    for name in ["QQQ", "SPY", "DIA"]:

        constituents = get_constituents(name)

        df = load_yfinance_func(tuple(constituents.items()))

        results[name] = build_benchmark(name, df)

    return results