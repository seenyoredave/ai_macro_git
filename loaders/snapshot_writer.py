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


def _yfinance_has_publishable_live_rows(report: dict) -> bool:
    """Return True when a refresh produced at least one live ticker row."""
    payload = report or {}
    mode = str(payload.get("source_mode") or "").strip().casefold()
    try:
        live = int(payload.get("live_tickers") or 0)
        returned = int(
            payload.get("returned_tickers")
            or (int(payload.get("live_tickers") or 0) + int(payload.get("archive_fallback_tickers") or 0))
        )
    except (TypeError, ValueError):
        return False
    return mode.startswith("live") and live > 0 and returned > 0


def _benchmark_can_advance(benchmark_metrics: dict, market_data_date: str) -> bool:
    payload = benchmark_metrics or {}
    mode = str(payload.get("source_mode") or "").strip().casefold()
    try:
        expected = int(payload.get("expected_tickers") or payload.get("member_count") or 0)
        members = int(payload.get("member_count") or 0)
    except (TypeError, ValueError):
        return False
    missing = payload.get("missing_tickers") or []
    return (
        mode in {"live_market_universe", "mixed_market_universe"}
        and expected > 0
        and members == expected
        and not missing
        and str(payload.get("market_data_date") or "").strip() == str(market_data_date)
    )


def _market_observation_date(raw_universe_data: dict) -> str | None:
    """Return the newest provider market date present in the current-best universe."""
    frame = raw_universe_data.get("yfinance")
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    if "Market Data Date" not in frame.columns:
        return None
    dates = pd.to_datetime(
        frame["Market Data Date"], errors="coerce", format="mixed"
    ).dropna()
    if dates.empty:
        return None
    return dates.max().date().isoformat()


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
        "retained_fallbacks": [],
        "warnings": {},
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
    retained_fallbacks: list[str] = report["retained_fallbacks"]
    report_warnings: dict[str, str] = report["warnings"]
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
        mode = str(yf_report.get("source_mode") or "unknown")
        live = int(yf_report.get("live_tickers") or 0)
        expected = int(yf_report.get("expected_tickers") or 0)
        fallback_rows = int(yf_report.get("archive_fallback_tickers") or 0)
        fallback_fields = int(yf_report.get("archive_field_backfills") or 0)
        missing_symbols = yf_report.get("missing_tickers") or []
        returned = int(yf_report.get("returned_tickers") or 0)

        if _yfinance_has_publishable_live_rows(yf_report):
            market_observation_date = _market_observation_date(raw_universe_data)
            if not market_observation_date:
                errors["yfinance"] = "Live YFinance rows have no valid Market Data Date"
            elif run(
                "yfinance",
                lambda: append_yf_history(
                    raw_universe_data.get("yfinance"),
                    sector_data,
                    observation_date=snapshot_date,
                ),
            ):
                mixed_dates = bool(yf_report.get("mixed_market_dates"))
                if fallback_rows or missing_symbols or mixed_dates:
                    report_warnings["yfinance"] = (
                        "YFinance refreshed partially and retained current-best market state. "
                        f"Live={live}/{expected}; retained ticker rows={fallback_rows}; "
                        f"missing tickers={len(missing_symbols)}; "
                        f"retained field fills={fallback_fields}."
                    )

                if _benchmark_can_advance(benchmark_metrics, market_observation_date):
                    run(
                        "benchmark",
                        lambda: append_benchmark_history(
                            {"QQQ": benchmark_metrics},
                            observation_date=market_observation_date,
                        ),
                    )
                else:
                    report_warnings["benchmark"] = (
                        "The fixed QQQ reference could not be advanced from the current-best "
                        "market universe; its prior retained benchmark remains in use. "
                        f"Mode={benchmark_metrics.get('source_mode')}; "
                        f"missing={benchmark_metrics.get('missing_tickers') or []}."
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
            retained_date = _market_observation_date(raw_universe_data)
            valid_retained_fallback = (
                ("archive" in mode.casefold() or "retained" in mode.casefold())
                and returned > 0
                and bool(retained_date)
            )
            if valid_retained_fallback:
                retained_fallbacks.append("yfinance")
                report_warnings["yfinance"] = (
                    "The live YFinance refresh produced no publishable live ticker rows. "
                    "The current-best retained market state remains in use and no YFinance-owned "
                    f"history was advanced. Mode={mode}; latest retained market date={retained_date}."
                )
            else:
                errors["yfinance"] = (
                    "YFinance refresh produced no usable live rows and no usable retained market state. "
                    f"Mode={mode}, live={live}/{expected}, returned={returned}, "
                    f"missing rows={len(missing_symbols)}."
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
                    for key, message in (finance_report.get("warnings") or {}).items():
                        report_warnings[f"finance:{key}"] = str(message)
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
        "written"
        if written or retained_by_loader
        else "retained_fallback"
        if retained_fallbacks
        else "no_successful_live_sources"
    )
    return report
