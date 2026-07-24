"""Key-based archive writers.

Each domain function builds a snapshot. One generic coalescing engine owns file
validation, same-key replacement, column ordering, and atomic writes.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from archive.archive_reader import (
    ARCHIVE_KEYS,
    EDGAR_REQUIRED_COLUMNS,
    normalize_date_column,
    normalize_key_columns,
    resolve_archive_path,
    today_iso,
)
from archive.schemas import ARCHIVE_SPECS, ArchiveSpec, spec_for_path
from benchmarks.benchmark_service import get_benchmark_metrics
from config.benchmark_config import ACTIVE_BENCHMARKS, BENCHMARK_VERSION


YF_ARCHIVE_COLUMNS = [
    "Ticker", "Company", "Price", "P/E", "Forward P/E", "Market Cap",
    "Revenue", "Revenue Growth", "CapEx", "CapEx Growth",
    "Operating Cash Flow", "Free Cash Flow", "Net Income", "EBITDA",
    "Total Debt", "Cash", "Net Debt", "FCF Margin YoY Change",
    "Net Debt / EBITDA YoY Change", "CapEx / OCF YoY Change", "Beta",
    "52W High", "52W Low", "1Y Return", "Price Extension 200D",
    "Momentum Acceleration", "Volatility Expansion", "Volume Activity",
    "Basket Score", "Basket Tier", "Basket Weight",
]


def _validate_keys(frame, keys, archive_file, *, require_values=False):
    missing = [key for key in keys if key not in frame.columns]
    if missing:
        raise ValueError(
            f"Refusing to write malformed archive {archive_file}: missing keys {missing}"
        )

    if require_values:
        for key in keys:
            blank = frame[key].isna() | (frame[key].astype(str).str.strip() == "")
            if blank.any():
                raise ValueError(
                    f"Refusing to write malformed archive {archive_file}: "
                    f"{int(blank.sum())} blank {key!r} values"
                )

    if "Date" in keys and "Date" in frame.columns:
        bad = pd.to_datetime(frame["Date"], errors="coerce").isna()
        if bad.any():
            raise ValueError(
                f"Refusing to write malformed archive {archive_file}: "
                f"{int(bad.sum())} unparseable Date values"
            )


def _normalize_frame(frame, archive_file, keys):
    normalized = frame.copy().dropna(how="all")
    normalized = normalize_key_columns(normalized)
    if "Date" in normalized.columns:
        normalized = normalize_date_column(normalized, "Date")
    _validate_keys(normalized, keys, archive_file, require_values=True)
    return normalized


def _quarantine(archive_file, reason):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = archive_file.with_name(
        f"{archive_file.stem}.malformed_{timestamp}{archive_file.suffix}"
    )
    counter = 1
    while backup.exists():
        backup = archive_file.with_name(
            f"{archive_file.stem}.malformed_{timestamp}_{counter}{archive_file.suffix}"
        )
        counter += 1
    archive_file.replace(backup)
    print(f"Archive reset: moved malformed file to {backup}. Reason: {reason}")


def _read_existing(archive_file, keys, *, reset_malformed=False):
    if not archive_file.exists() or archive_file.stat().st_size == 0:
        return pd.DataFrame()

    try:
        existing = pd.read_csv(archive_file).dropna(how="all")
        if existing.empty:
            return existing
        return _normalize_frame(existing, archive_file, keys)
    except (ValueError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        if not reset_malformed:
            raise
        _quarantine(archive_file, str(exc))
        return pd.DataFrame()


def _remove_matching_keys(existing, snapshot, keys):
    if existing is None or existing.empty or snapshot.empty:
        return existing

    identities = snapshot[list(keys)].drop_duplicates().copy()
    identities["_replace"] = True
    merged = existing.merge(identities, on=list(keys), how="left")
    return merged.loc[merged["_replace"].isna()].drop(columns="_replace")


def _ordered_columns(existing, snapshot, keys):
    ordered = list(keys)
    for frame in (existing, snapshot):
        if frame is None:
            continue
        for column in frame.columns:
            if column not in ordered:
                ordered.append(column)
    return ordered


def _atomic_write(frame, archive_file, keys):
    _validate_keys(frame, keys, archive_file, require_values=True)
    temp_file = archive_file.with_suffix(archive_file.suffix + ".tmp")
    frame.to_csv(temp_file, index=False)
    check = pd.read_csv(temp_file)
    _validate_keys(check, keys, archive_file, require_values=True)
    temp_file.replace(archive_file)


def write_archive_snapshot(snapshot, archive_path, replace_today=True, key_cols=None):
    """Replace matching full-key rows and preserve every unrelated row.

    ``replace_today`` remains for call compatibility. Its practical meaning is
    full-key replacement, so multiple same-day sectors or tickers cannot erase
    one another.
    """
    spec = archive_path if isinstance(archive_path, ArchiveSpec) else spec_for_path(archive_path)
    path = spec.path if spec else archive_path
    keys = tuple(key_cols or (spec.keys if spec else ()))
    if not keys:
        raise ValueError(f"Archive identity keys are required for {path}")

    archive_file = resolve_archive_path(path)
    archive_file.parent.mkdir(parents=True, exist_ok=True)
    incoming = _normalize_frame(snapshot, archive_file, keys)
    existing = _read_existing(
        archive_file,
        keys,
        reset_malformed=bool(spec and spec.reset_malformed),
    )

    if replace_today:
        existing = _remove_matching_keys(existing, incoming, keys)

    combined = (
        pd.concat([existing, incoming], ignore_index=True)
        if existing is not None and not existing.empty
        else incoming.copy()
    )
    combined = _normalize_frame(combined, archive_file, keys)
    combined = combined.reindex(columns=_ordered_columns(existing, incoming, keys))
    _atomic_write(combined, archive_file, keys)


def append_dataframe_history(frame, archive_path, key_cols=None):
    snapshot = frame.copy()
    snapshot.insert(0, "Date", today_iso())
    write_archive_snapshot(snapshot, archive_path, key_cols=key_cols)


def _component_value(regime_metrics, group_key, component_name, field="score"):
    return (
        ((regime_metrics.get(group_key, {}) or {}).get("components", {}) or {})
        .get(component_name, {})
        .get(field, np.nan)
    )


def _current_metric_value(regime_metrics, metric_name, source_name):
    if regime_metrics.get(source_name) != "Current":
        return np.nan
    return regime_metrics.get(
        f"{metric_name} Current",
        regime_metrics.get(metric_name, np.nan),
    )


def append_macro_history(regime_metrics, fred_data):
    row = {
        "Date": today_iso(),
        "AI Equity Index": _current_metric_value(regime_metrics, "AI Equity Index", "AEI Source"),
        "AI Development Intensity": _current_metric_value(regime_metrics, "AI Development Intensity", "ADI Source"),
        "Speculation Gap": (
            regime_metrics.get("Speculation Gap", np.nan)
            if regime_metrics.get("Speculation Gap Source") == "Current"
            else np.nan
        ),
        "Power Stress Index": _current_metric_value(regime_metrics, "Power Stress Index", "Power Stress Source"),
        "Capital Stress": _current_metric_value(regime_metrics, "Capital Stress", "Capital Stress Source"),
        "Credit Intermediation Stress": _current_metric_value(
            regime_metrics,
            "Credit Intermediation Stress",
            "Credit Intermediation Stress Source",
        ),
        "Concentration HHI": regime_metrics.get("Concentration HHI", np.nan),
        "Raw AI HHI": regime_metrics.get("Raw AI HHI", np.nan),
        "Avg Sector Pressure": regime_metrics.get("Avg Sector Pressure", np.nan),
        "ADI Capital Deployment": _component_value(regime_metrics, "ADI Components", "Capital Deployment"),
        "ADI Data Center Construction": _component_value(regime_metrics, "ADI Components", "Data Center Construction"),
        "ADI Compute Supply Realization": _component_value(regime_metrics, "ADI Components", "Compute Supply Realization"),
        "ADI Power Footprint": _component_value(regime_metrics, "ADI Components", "Power Footprint"),
        "Power Nonresidential Load": _component_value(regime_metrics, "Power Stress Components", "Nonresidential Load Pressure"),
        "Power Grid Utilization": _component_value(regime_metrics, "Power Stress Components", "Grid Utilization Pressure"),
        "Power Capacity Response": _component_value(regime_metrics, "Power Stress Components", "Capacity Response Gap"),
        "Capital Cash Flow Strain": _component_value(regime_metrics, "Capital Stress Components", "Cash Flow Strain"),
        "Capital Book Leverage": _component_value(regime_metrics, "Capital Stress Components", "Book Leverage"),
        "Capital Committed Burden": _component_value(regime_metrics, "Capital Stress Components", "Committed Burden"),
        "Capital Contingent Exposure": _component_value(regime_metrics, "Capital Stress Components", "Contingent Exposure"),
        "Intermediation Bank Credit Tightening": _component_value(
            regime_metrics,
            "Credit Intermediation Stress Components",
            "Bank Credit Tightening",
        ),
        "Intermediation Bank Capital Strain": _component_value(
            regime_metrics,
            "Credit Intermediation Stress Components",
            "Bank Capital Strain",
        ),
        "Intermediation Private Credit Impairment": _component_value(
            regime_metrics,
            "Credit Intermediation Stress Components",
            "Private Credit Impairment",
        ),
        "Intermediation PE Portfolio Financing Strain": _component_value(
            regime_metrics,
            "Credit Intermediation Stress Components",
            "PE Portfolio Financing Strain",
        ),
        "AEI Version": regime_metrics.get("AEI Version", np.nan),
        "ADI Version": regime_metrics.get("ADI Version", np.nan),
        "Power Stress Version": regime_metrics.get("Power Stress Version", np.nan),
        "Capital Stress Version": regime_metrics.get("Capital Stress Version", np.nan),
        "Credit Intermediation Stress Version": regime_metrics.get(
            "Credit Intermediation Stress Version", np.nan
        ),
        "Pressure Version": regime_metrics.get("Pressure Version", np.nan),
        "Consumer Sentiment": fred_data.get("Consumer Sentiment", {}).get("value", np.nan),
        "Fed Funds Rate": fred_data.get("Fed Funds Rate", {}).get("value", np.nan),
        "Industrial Production": fred_data.get("Industrial Production", {}).get("value", np.nan),
        "Industrial Production YoY": fred_data.get("Industrial Production YoY", {}).get("value", np.nan),
    }
    write_archive_snapshot(pd.DataFrame([row]), ARCHIVE_SPECS["macro"])


def append_sector_history(sector_metrics):
    rows = [
        {
            "Date": today_iso(),
            "Sector": sector,
            "Sector Score": metrics.get("Sector Score"),
            "Pressure": metrics.get("Sector Pressure"),
            "Forward P/E": metrics.get("Forward P/E"),
            "Avg Return": metrics.get("Avg Return"),
            "AEI Version": "2.0",
            "Pressure Version": "2.0",
        }
        for sector, metrics in sector_metrics.items()
    ]
    if rows:
        write_archive_snapshot(pd.DataFrame(rows), ARCHIVE_SPECS["sector"])


def append_benchmark_history():
    rows = []
    for benchmark in ACTIVE_BENCHMARKS:
        metrics = get_benchmark_metrics(benchmark)
        rows.append({
            "Date": today_iso(),
            "Benchmark": benchmark,
            "Forward P/E": metrics.get("forward_pe"),
            "Avg Return": metrics.get("avg_return"),
            "Beta": metrics.get("beta"),
            "Member Count": metrics.get("member_count"),
            "Benchmark Version": BENCHMARK_VERSION,
        })
    if rows:
        write_archive_snapshot(pd.DataFrame(rows), ARCHIVE_SPECS["benchmark"])


def append_yf_history(sector_data):
    rows = []
    for sector, frame in sector_data.items():
        if frame is None or frame.empty:
            continue
        available = [column for column in YF_ARCHIVE_COLUMNS if column in frame.columns]
        snapshot = frame[available].copy()
        snapshot.insert(0, "Sector", sector)
        rows.append(snapshot)

    if rows:
        append_dataframe_history(
            pd.concat(rows, ignore_index=True),
            ARCHIVE_SPECS["yf"],
            key_cols=ARCHIVE_KEYS["yf"],
        )


def append_edgar_history(edgar_snapshot):
    """Persist a loader-approved EDGAR snapshot without re-evaluating quality."""
    if edgar_snapshot is None or edgar_snapshot.empty:
        return

    snapshot = edgar_snapshot.copy()
    if "Date" not in snapshot.columns:
        snapshot.insert(0, "Date", today_iso())
    snapshot = snapshot.reindex(columns=EDGAR_REQUIRED_COLUMNS)
    write_archive_snapshot(snapshot, ARCHIVE_SPECS["edgar"])


def append_fred_history(fred_data):
    if not fred_data:
        return

    sources = [
        payload.get("source")
        for payload in fred_data.values()
        if isinstance(payload, dict)
    ]
    if sources and not any(str(source).lower().startswith("fred live") for source in sources):
        return

    row = {"Date": today_iso()}
    for indicator, payload in fred_data.items():
        if isinstance(payload, dict):
            row[indicator] = payload.get("value", np.nan)
            row[f"{indicator} Date"] = payload.get("date")
        else:
            row[indicator] = payload
            row[f"{indicator} Date"] = None
    write_archive_snapshot(pd.DataFrame([row]), ARCHIVE_SPECS["fred"])
