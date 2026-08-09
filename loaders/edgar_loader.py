"""Stable public interface for SEC EDGAR data.

Client, archive, and XBRL parsing concerns are separated behind this facade.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd

from config.debug_config import debug_print
from loaders.edgar_archive import (
    EDGAR_CORE_FIELDS,
    EDGAR_FRESHNESS_DAYS,
    EDGAR_MAX_ANNUAL_AGE_DAYS,
    EDGAR_PERIOD_ALIGNMENT_DAYS,
    EDGAR_PRIOR_PERIOD_MAX_DAYS,
    EDGAR_PRIOR_PERIOD_MIN_DAYS,
    EDGAR_RESTORE_FIELDS,
    TERMINAL_EDGAR_STATUS_PREFIXES,
    _edgar_quality_score,
    _expected_ticker_set,
    _is_present,
    _is_usable_edgar_row,
    _latest_edgar_rows,
    _status_prefix,
    _usable_tickers_from_rows,
    describe_edgar_freshness_status,
    edgar_archive_rows_to_dict,
    is_archive_eligible_edgar_payload,
    read_latest_edgar_archive,
    read_recent_edgar_archive,
)
from loaders.edgar_client import (
    DEFAULT_SEC_USER_AGENT,
    SEC_COMPANY_FACTS_URL,
    SEC_TICKER_URL,
    _optional_streamlit_secret,
    _sec_user_agent,
    fetch_company_facts,
    load_ticker_cik_map,
    sec_headers,
    sec_ticker_headers,
)
from loaders.edgar_facts import (
    ANNUAL_FORMS,
    IFRS_CAPEX_CONCEPTS,
    IFRS_REVENUE_CONCEPTS,
    US_GAAP_CAPEX_CONCEPTS,
    US_GAAP_REVENUE_CONCEPTS,
    _all_monetary_unit_facts,
    _annual_fact_rows,
    _extract_taxonomy_metrics,
    _fact_end_date,
    _fact_fiscal_year,
    _fact_period_days,
    _has_non_usd_annual_facts,
    _is_annual_fact,
    _row_for_end,
    _taxonomy_result_rank,
    _value_and_growth_for_period,
    annual_fact_series,
    discover_capex_concepts,
    extract_company_metrics,
    get_taxonomy_facts,
    get_usd_unit_facts,
)

def _empty_edgar_payload(status, *, source="Failed"):
    return {
        "Revenue": np.nan,
        "Revenue Growth": np.nan,
        "CapEx": np.nan,
        "CapEx Growth": np.nan,
        "Revenue FY": None,
        "CapEx FY": None,
        "CIK": None,
        "EDGAR Status": status,
        "EDGAR Source": source,
        "EDGAR Archive Date": None,
    }


def _fetch_live_edgar_subset(tickers_to_fetch, ticker_cik_map, archive_fallback_data):
    edgar_data = {}
    attempted = []
    succeeded = []
    failed = []
    rejected_quality = []

    for ticker_upper in sorted(tickers_to_fetch):
        attempted.append(ticker_upper)

        try:
            cik = ticker_cik_map.get(ticker_upper)
            if not cik:
                raise ValueError(f"No CIK found for ticker {ticker_upper}")

            company_facts = fetch_company_facts(cik)
            metrics = extract_company_metrics(company_facts)
            live_payload = {
                "Revenue": metrics["Revenue"],
                "Revenue Growth": metrics["Revenue Growth"],
                "CapEx": metrics["CapEx"],
                "CapEx Growth": metrics["CapEx Growth"],
                "Revenue FY": metrics["Revenue FY"],
                "CapEx FY": metrics["CapEx FY"],
                "CIK": cik,
                "EDGAR Status": metrics["EDGAR Status"],
                "EDGAR Source": "SEC Live",
                "EDGAR Archive Date": None,
                "EDGAR Taxonomy": metrics.get("EDGAR Taxonomy"),
                "Revenue Period End": metrics.get("Revenue Period End"),
                "CapEx Period End": metrics.get("CapEx Period End"),
                "CapEx Concept": metrics.get("CapEx Concept"),
            }

            fallback = archive_fallback_data.get(ticker_upper)
            if fallback and _edgar_quality_score(live_payload) < _edgar_quality_score(fallback):
                retained = fallback.copy()
                retained["EDGAR Source"] = "Archive Fallback"
                retained["EDGAR Status"] = (
                    f"Live lower quality; retained archive: {live_payload.get('EDGAR Status', '')}"
                )
                edgar_data[ticker_upper] = retained
                rejected_quality.append(ticker_upper)
            else:
                edgar_data[ticker_upper] = live_payload
                succeeded.append(ticker_upper)

            time.sleep(0.12)

        except Exception as exc:
            debug_print(f"EDGAR failed: {ticker_upper} -> {exc}")
            failed.append(ticker_upper)
            fallback = archive_fallback_data.get(ticker_upper)

            if fallback:
                fallback = fallback.copy()
                fallback["EDGAR Status"] = f"Live Failed; Archive Fallback: {exc}"
                fallback["EDGAR Source"] = "Archive Fallback"
                edgar_data[ticker_upper] = fallback
            else:
                edgar_data[ticker_upper] = _empty_edgar_payload(
                    f"Failed: {exc}",
                    source="Failed",
                )

    return edgar_data, {
        "live_attempted_tickers": attempted,
        "live_succeeded_tickers": succeeded,
        "live_failed_tickers": failed,
        "live_rejected_quality_tickers": rejected_quality,
    }


def load_edgar_with_report(tickers, force_refresh=False, allow_live=False):
    expected = _expected_ticker_set(tickers)

    recent_rows = read_recent_edgar_archive(
        tickers,
        max_age_days=EDGAR_FRESHNESS_DAYS,
        require_complete=False,
    )
    latest_rows = read_latest_edgar_archive(tickers, require_complete=False)

    recent_data = edgar_archive_rows_to_dict(recent_rows, source_label="Archive Recent")
    archive_fallback_data = edgar_archive_rows_to_dict(
        latest_rows,
        source_label="Archive Fallback",
    )

    usable_recent = {
        ticker
        for ticker, payload in recent_data.items()
        if _is_usable_edgar_row(payload)
    }

    # EDGAR is a desktop-only explicit refresh. Public startup and ordinary
    # developer rebuilds always consume retained facts.
    if not (force_refresh and allow_live):
        # Use the newest retained row for every ticker. Freshness is reported
        # separately; it is never a reason to contact EDGAR during startup.
        retained_data = dict(archive_fallback_data)
        retained_data.update(recent_data)
        edgar_data = {}
        missing_retained = []
        for ticker_upper in sorted(expected):
            payload = retained_data.get(ticker_upper)
            if payload is None:
                missing_retained.append(ticker_upper)
                payload = _empty_edgar_payload(
                    "No retained EDGAR payload",
                    source="Retained Missing",
                )
            edgar_data[ticker_upper] = payload

        report = describe_edgar_freshness_status(tickers)
        report.update({
            "source_mode": "archive_read_mode",
            "refresh_trigger": "retained_snapshot",
            "archive_recent_tickers_used": int(sum(t in recent_data for t in expected)),
            "retained_tickers_used": int(len(expected) - len(missing_retained)),
            "missing_tickers": missing_retained,
            "live_needed_tickers": [],
            "live_attempted_tickers": [],
            "live_succeeded_tickers": [],
            "live_failed_tickers": [],
            "live_rejected_quality_tickers": [],
        })
        return edgar_data, report

    tickers_to_fetch = sorted(expected)

    edgar_data = {}

    report = describe_edgar_freshness_status(tickers)
    report.update({
        "source_mode": "manual_live",
        "refresh_trigger": "manual",
        "archive_recent_tickers_used": int(len(edgar_data)),
        "live_needed_tickers": tickers_to_fetch,
        "live_attempted_tickers": [],
        "live_succeeded_tickers": [],
        "live_failed_tickers": [],
        "live_rejected_quality_tickers": [],
    })

    try:
        ticker_cik_map = load_ticker_cik_map()
    except Exception as exc:
        debug_print(f"EDGAR ticker-CIK map failed -> {exc}")
        report["source_mode"] = "archive_fallback_map_failed"
        report["live_failed_tickers"] = tickers_to_fetch

        for ticker_upper in tickers_to_fetch:
            edgar_data[ticker_upper] = archive_fallback_data.get(
                ticker_upper,
                _empty_edgar_payload(
                    f"Ticker-CIK map failed: {exc}",
                    source="Failed",
                ),
            )

        return edgar_data, report

    live_data, live_report = _fetch_live_edgar_subset(
        tickers_to_fetch,
        ticker_cik_map,
        archive_fallback_data,
    )
    edgar_data.update(live_data)
    report.update(live_report)

    if force_refresh:
        report["source_mode"] = (
            "manual_live"
            if live_report.get("live_succeeded_tickers")
            else "manual_archive_fallback"
        )
    elif len(tickers_to_fetch) == len(expected):
        report["source_mode"] = "full_live"
    elif live_report.get("live_succeeded_tickers"):
        report["source_mode"] = "partial_live"
    else:
        report["source_mode"] = "archive_fallback"

    for ticker_upper in sorted(expected):
        if ticker_upper not in edgar_data:
            edgar_data[ticker_upper] = archive_fallback_data.get(
                ticker_upper,
                _empty_edgar_payload("No EDGAR payload", source="Failed"),
            )

    return edgar_data, report


def load_edgar(tickers, *, allow_live=False):
    edgar_data, _ = load_edgar_with_report(tickers, allow_live=allow_live)
    return edgar_data


def build_edgar_archive_snapshot(sector_data, raw_edgar_data):
    columns = [
        "Sector", "Ticker", "Revenue", "Revenue Growth", "CapEx",
        "CapEx Growth", "Revenue FY", "CapEx FY", "CIK", "EDGAR Status",
    ]
    if not raw_edgar_data:
        return pd.DataFrame(columns=columns)

    rows = []
    for sector, frame in (sector_data or {}).items():
        if frame is None or frame.empty or "Ticker" not in frame.columns:
            continue

        for ticker in frame["Ticker"].dropna().astype(str).str.upper().str.strip():
            payload = raw_edgar_data.get(ticker, {}) or {}
            if not is_archive_eligible_edgar_payload(payload):
                continue
            rows.append({
                "Sector": sector,
                "Ticker": ticker,
                "Revenue": payload.get("Revenue", np.nan),
                "Revenue Growth": payload.get("Revenue Growth", np.nan),
                "CapEx": payload.get("CapEx", np.nan),
                "CapEx Growth": payload.get("CapEx Growth", np.nan),
                "Revenue FY": payload.get("Revenue FY", np.nan),
                "CapEx FY": payload.get("CapEx FY", np.nan),
                "CIK": payload.get("CIK", np.nan),
                "EDGAR Status": payload.get("EDGAR Status", np.nan),
            })

    return pd.DataFrame(rows, columns=columns)


__all__ = [name for name in globals() if not name.startswith("__")]
