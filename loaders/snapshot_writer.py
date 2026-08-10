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
from archive.archive_reader import today_iso
from config.deployment import repository_writes_enabled
from config.load_policy import LoadPolicy, RefreshSource
from loaders.edgar_loader import build_edgar_archive_snapshot
from loaders.borrower_finance_refresh import refresh_borrower_finance_derivatives


def _live_mode(value: object) -> bool:
    mode = str(value or "").strip().casefold()
    if not mode:
        return False
    rejected = ("fallback", "retained", "archive", "unavailable", "failed")
    return any(token in mode for token in ("live", "refresh", "manual")) and not any(
        token in mode for token in rejected
    )


def _yfinance_live_refresh_succeeded(report: dict) -> bool:
    """Return True when every configured ticker returned a live row.

    Individual YFinance fields can be unavailable on an otherwise successful
    ticker refresh. The loader resolves those cells from the previous retained
    snapshot and reports them as field backfills. Field-level backfills do not
    block persistence; row-level fallbacks and missing tickers do.
    """
    payload = report or {}
    mode = str(payload.get("source_mode") or "").strip().casefold()
    try:
        expected = int(payload.get("expected_tickers") or 0)
        live = int(payload.get("live_tickers") or 0)
        fallback_rows = int(payload.get("archive_fallback_tickers") or 0)
    except (TypeError, ValueError):
        return False
    missing = payload.get("missing_tickers") or []
    return (
        mode.startswith("live")
        and expected > 0
        and live == expected
        and fallback_rows == 0
        and not missing
    )




def _benchmark_matches_market_refresh(benchmark_metrics: dict, market_data_date: str) -> bool:
    payload = benchmark_metrics or {}
    mode = str(payload.get("source_mode") or "").strip().casefold()
    try:
        expected = int(payload.get("expected_tickers") or payload.get("member_count") or 0)
        live = int(payload.get("live_tickers") or 0)
        fallback_rows = int(payload.get("archive_fallback_tickers") or 0)
        members = int(payload.get("member_count") or 0)
    except (TypeError, ValueError):
        return False
    missing = payload.get("missing_tickers") or []
    benchmark_date = str(payload.get("market_data_date") or "").strip()
    return (
        mode == "live_market_universe"
        and expected > 0
        and members == expected
        and live == expected
        and fallback_rows == 0
        and not missing
        and benchmark_date == str(market_data_date)
    )

def _market_observation_date(raw_universe_data: dict) -> str | None:
    frame = raw_universe_data.get("yfinance")
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    if "Market Data Date" not in frame.columns:
        return None
    dates = pd.to_datetime(
        frame["Market Data Date"], errors="coerce", format="mixed"
    ).dt.date
    # A retained market snapshot represents one completed provider observation
    # date. Every live ticker row must therefore carry the same valid market
    # date; a dominant-date heuristic can hide one or more stale ticker rows.
    if dates.isna().any() or len(dates) != len(frame):
        return None
    unique = sorted(set(dates.tolist()))
    if len(unique) != 1:
        return None
    return unique[0].isoformat()


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
    edgar_refresh_token: int = 0,
) -> dict:
    """Persist only snapshots backed by successful authorized live work."""

    report = {
        "status": "skipped",
        "policy": policy.describe(),
        "written": [],
        "retained_by_loader": [],
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
    retained_by_loader: list[str] = report["retained_by_loader"]
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
    snapshot_date = today_iso()
    report["snapshot_date"] = snapshot_date

    if policy.allows_live(RefreshSource.YFINANCE):
        yf_report = dict(market_report.get("yfinance", {}) or {})
        if _yfinance_live_refresh_succeeded(yf_report):
            market_observation_date = _market_observation_date(raw_universe_data)
            if not market_observation_date:
                errors["yfinance"] = (
                    "Live market rows do not share a valid dominant Market Data Date"
                )
            elif not _benchmark_matches_market_refresh(benchmark_metrics, market_observation_date):
                errors["benchmark"] = (
                    "The QQQ reference did not reconcile to the same complete live market "
                    f"snapshot. Market data date={market_observation_date}; "
                    f"benchmark mode={benchmark_metrics.get('source_mode')}; "
                    f"benchmark data date={benchmark_metrics.get('market_data_date')}. "
                    "No YFinance-owned retained histories were advanced."
                )
            elif run(
                "yfinance",
                lambda: append_yf_history(
                    raw_universe_data.get("yfinance"),
                    sector_data,
                    observation_date=snapshot_date,
                ),
            ):
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
        else:
            mode = str(yf_report.get("source_mode") or "unknown")
            live = int(yf_report.get("live_tickers") or 0)
            expected = int(yf_report.get("expected_tickers") or 0)
            fallback_rows = int(yf_report.get("archive_fallback_tickers") or 0)
            fallback_fields = int(yf_report.get("archive_field_backfills") or 0)
            missing = len(yf_report.get("missing_tickers") or [])
            errors["yfinance"] = (
                "YFinance refresh did not return a complete live ticker universe; "
                "the retained archive was not advanced. "
                f"Mode={mode}, live={live}/{expected}, "
                f"fallback rows={fallback_rows}, missing rows={missing}, "
                f"retained field fills={fallback_fields}."
            )

    if policy.allows_live(RefreshSource.EDGAR):
        edgar_report = dict(market_report.get("edgar", {}) or {})
        if edgar_report.get("live_succeeded_tickers"):
            edgar_written = run(
                "edgar",
                lambda: append_edgar_history(
                    build_edgar_archive_snapshot(
                        sector_data,
                        raw_universe_data.get("edgar", {}),
                    )
                ),
            )
            if edgar_written:
                try:
                    finance_report = refresh_borrower_finance_derivatives(
                        refresh_token=int(edgar_refresh_token),
                        observation_date=snapshot_date,
                    )
                    report["finance_derivatives"] = finance_report
                    if finance_report.get("status") == "written":
                        written.append("finance_fundamentals")
                    else:
                        errors["finance_fundamentals"] = (
                            "EDGAR refreshed, but the 10-company Finance derivative cohort "
                            "was incomplete and retained derivatives were not advanced."
                        )
                    for key, message in (finance_report.get("errors") or {}).items():
                        errors[f"finance:{key}"] = str(message)
                except Exception as exc:
                    errors["finance_fundamentals"] = f"{type(exc).__name__}: {exc}"

    if policy.allows_live(RefreshSource.FRED) and _live_mode(
        fred_report.get("source_mode")
    ):
        run("fred", lambda: append_fred_history(fred_data))

    debt_report = dict(debt_markets_data.get("load_report", {}) or {})
    if policy.allows_live(RefreshSource.NYFED) and _live_mode(
        debt_report.get("source_mode")
    ):
        # The NY Fed loader persists its retained history atomically before it
        # returns a live result, so record that successful write here even
        # though this generic snapshot writer did not perform it.
        retained_by_loader.append("nyfed")

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

    report["status"] = (
        "written" if written or retained_by_loader else "no_successful_live_sources"
    )
    return report
