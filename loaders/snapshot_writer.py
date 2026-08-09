"""Targeted persistence for successful explicit refresh transactions.

Ordinary dashboard rebuilds never enter this writer. Each retained snapshot is
updated only when its owning source was explicitly refreshed and returned live
results. Failed refreshes therefore cannot re-date stale fallback data.
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from archive.archive import (
    append_benchmark_history,
    append_edgar_history,
    append_energy_history,
    append_fred_history,
    append_macro_history,
    append_sector_history,
    append_yf_history,
)
from config.deployment import repository_writes_enabled
from config.load_policy import LoadPolicy, RefreshSource
from loaders.edgar_loader import build_edgar_archive_snapshot


def _live_mode(value: object) -> bool:
    mode = str(value or "").strip().casefold()
    if not mode:
        return False
    rejected = ("fallback", "retained", "archive", "unavailable", "failed")
    return any(token in mode for token in ("live", "refresh", "manual")) and not any(
        token in mode for token in rejected
    )


def _market_observation_date(raw_universe_data: dict) -> str | None:
    frame = raw_universe_data.get("yfinance")
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    if "Market Data Date" not in frame.columns:
        return None
    dates = pd.to_datetime(
        frame["Market Data Date"], errors="coerce", format="mixed"
    ).dt.date.dropna()
    if dates.empty:
        return None
    counts = dates.value_counts()
    dominant = counts.index[0]
    if int(counts.iloc[0]) < max(1, int(len(frame) * 0.95)):
        return None
    return dominant.isoformat()


def persist_refresh_snapshots(
    *,
    policy: LoadPolicy,
    archive_suspended: bool,
    regime_metrics: dict,
    fred_data: dict,
    fred_report: dict,
    sector_metrics: dict,
    benchmark_metrics: dict,
    sector_data: dict,
    raw_universe_data: dict,
    energy_data: dict,
    debt_markets_data: dict,
) -> dict:
    """Persist only snapshots backed by successful authorized live work."""

    report = {
        "status": "skipped",
        "policy": policy.describe(),
        "written": [],
        "errors": {},
    }
    if archive_suspended:
        report["reason"] = "archive_suspended"
        return report
    if not repository_writes_enabled():
        report["reason"] = "repository_writes_disabled"
        return report
    if not policy.is_explicit_refresh:
        report["reason"] = "retained_read_mode"
        return report

    written: list[str] = report["written"]
    errors: dict[str, str] = report["errors"]

    def run(label: str, function: Callable[[], object]) -> bool:
        try:
            function()
            written.append(label)
            return True
        except Exception as exc:  # persistence failure should not blank the app
            errors[label] = f"{type(exc).__name__}: {exc}"
            return False

    market_report = dict(raw_universe_data.get("_load_report", {}) or {})

    if policy.allows_live(RefreshSource.YFINANCE):
        yf_mode = (market_report.get("yfinance", {}) or {}).get("source_mode")
        if _live_mode(yf_mode):
            market_observation_date = _market_observation_date(raw_universe_data)
            if not market_observation_date:
                errors["yfinance"] = (
                    "Live market rows do not share a valid dominant Market Data Date"
                )
            elif run(
                "yfinance",
                lambda: append_yf_history(
                    sector_data,
                    observation_date=market_observation_date,
                ),
            ):
                if _live_mode(benchmark_metrics.get("source_mode")):
                    run(
                        "benchmark",
                        lambda: append_benchmark_history(
                            {"QQQ": benchmark_metrics},
                            observation_date=market_observation_date,
                        ),
                    )
                run(
                    "sector",
                    lambda: append_sector_history(
                        sector_metrics,
                        observation_date=market_observation_date,
                    ),
                )
                run(
                    "macro",
                    lambda: append_macro_history(
                        regime_metrics,
                        fred_data,
                        observation_date=market_observation_date,
                        market_data_date=market_observation_date,
                    ),
                )

    if policy.allows_live(RefreshSource.EDGAR):
        edgar_report = dict(market_report.get("edgar", {}) or {})
        if edgar_report.get("live_succeeded_tickers"):
            run(
                "edgar",
                lambda: append_edgar_history(
                    build_edgar_archive_snapshot(
                        sector_data,
                        raw_universe_data.get("edgar", {}),
                    )
                ),
            )

    if policy.allows_live(RefreshSource.FRED) and _live_mode(
        fred_report.get("source_mode")
    ):
        run("fred", lambda: append_fred_history(fred_data))

    energy_report = dict(energy_data.get("load_report", {}) or {})
    energy_live = _live_mode(energy_report.get("source_mode")) or _live_mode(
        energy_report.get("market_source_mode")
    )
    energy_authorized = any(
        policy.allows_live(source)
        for source in (
            RefreshSource.FRED,
            RefreshSource.POWER,
            RefreshSource.GRID_STORAGE,
        )
    )
    if energy_authorized and energy_live:
        run("energy", lambda: append_energy_history(energy_data))

    report["status"] = "written" if written else "no_successful_live_sources"
    return report
