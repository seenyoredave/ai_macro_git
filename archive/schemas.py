"""Archive identities and write contracts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArchiveSpec:
    name: str
    path: str
    keys: tuple[str, ...]
    reset_malformed: bool = False


ARCHIVE_SPECS = {
    "benchmark": ArchiveSpec("benchmark", "archive/benchmark_history.csv", ("Date", "Benchmark")),
    "edgar": ArchiveSpec("edgar", "archive/edgar_history.csv", ("Date", "Sector", "Ticker"), True),
    "fred": ArchiveSpec("fred", "archive/fred_history.csv", ("Date",)),
    "macro": ArchiveSpec("macro", "archive/macro_history.csv", ("Date",)),
    "sector": ArchiveSpec("sector", "archive/sector_history.csv", ("Date", "Sector")),
    "yf": ArchiveSpec("yf", "archive/yf_history.csv", ("Date", "Sector", "Ticker")),
}


def spec_for_path(path: str):
    normalized = str(path).replace("\\", "/")
    for spec in ARCHIVE_SPECS.values():
        if normalized == spec.path or normalized.endswith(spec.path):
            return spec
    return None
