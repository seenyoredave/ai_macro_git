from __future__ import annotations

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
from config.benchmark_config import (
    ACTIVE_BENCHMARKS,
    BENCHMARK_VERSION,
    QQQ_WEIGHTS_EFFECTIVE_DATE,
)
from config.energy_config import ENERGY_DATA_VERSION, ENERGY_SERIES
from config.market_clock import eastern_now
from helpers.atomic_io import atomic_write_csv, synchronized_path

YF_ARCHIVE_COLUMNS = [
    "Ticker", "Company", "Market Data Date", "Price", "P/E", "Forward EV/EBIT",
    "Market Cap", "Enterprise Value", "Revenue", "Forward Revenue",
    "Operating Income", "Operating Margin", "Forward EBIT",
    "Revenue Growth", "CapEx", "CapEx Growth",
    "Operating Cash Flow", "Free Cash Flow", "Net Income", "EBITDA",
    "Total Debt", "Cash", "Net Debt", "FCF Margin YoY Change",
    "Net Debt / EBITDA YoY Change", "CapEx / OCF YoY Change", "Beta",
    "52W High", "52W Low", "1Y Return", "YTD Return",
    "YTD Start Market Cap", "YTD Year", "Price Extension 200D",
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
    timestamp = eastern_now().strftime("%Y%m%d_%H%M%S")
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

def _atomic_write(frame, archive_file, keys, *, lock=True):
    _validate_keys(frame, keys, archive_file, require_values=True)

    def validate_temp(temp_file):
        check = pd.read_csv(temp_file)
        _validate_keys(check, keys, archive_file, require_values=True)

    atomic_write_csv(frame, archive_file, lock=lock, validator=validate_temp)

def write_archive_snapshot(snapshot, archive_path, key_cols=None):
    spec = archive_path if isinstance(archive_path, ArchiveSpec) else spec_for_path(archive_path)
    path = spec.path if spec else archive_path
    keys = tuple(key_cols or (spec.keys if spec else ()))
    if not keys:
        raise ValueError(f"Archive identity keys are required for {path}")

    archive_file = resolve_archive_path(path)
    archive_file.parent.mkdir(parents=True, exist_ok=True)
    incoming = _normalize_frame(snapshot, archive_file, keys)

    with synchronized_path(archive_file):
        existing = _read_existing(
            archive_file,
            keys,
            reset_malformed=bool(spec and spec.reset_malformed),
        )
        existing = _remove_matching_keys(existing, incoming, keys)

        combined = (
            pd.concat([existing, incoming], ignore_index=True)
            if existing is not None and not existing.empty
            else incoming.copy()
        )
        combined = _normalize_frame(combined, archive_file, keys)
        combined = combined.reindex(columns=_ordered_columns(existing, incoming, keys))
        _atomic_write(combined, archive_file, keys, lock=False)

def append_dataframe_history(
    frame,
    archive_path,
    key_cols=None,
    *,
    observation_date=None,
):
    snapshot = frame.copy()
    snapshot.insert(0, "Date", str(observation_date or today_iso()))
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

def append_macro_history(
    regime_metrics,
    fred_data,
    *,
    observation_date,
    market_data_date,
):
    row = {
        "Date": str(observation_date),
        "Market Data Date": str(market_data_date),
        "AI Equity Index": _current_metric_value(regime_metrics, "AI Equity Index", "AEI Source"),
        "AI Development Intensity": _current_metric_value(regime_metrics, "AI Development Intensity", "ADI Source"),
        "Speculation Gap": (
            regime_metrics.get("Speculation Gap", np.nan)
            if regime_metrics.get("Speculation Gap Source") == "Current"
            else np.nan
        ),
        "Economic Validation Gap": _current_metric_value(
            regime_metrics,
            "Economic Validation Gap",
            "Economic Validation Gap Source",
        ),
        "Power Stress Index": _current_metric_value(regime_metrics, "Power Stress Index", "Power Stress Source"),
        "Power Capacity Gap": _current_metric_value(
            regime_metrics,
            "Power Capacity Gap",
            "Power Capacity Gap Source",
        ),
        "Borrower Strain": _current_metric_value(regime_metrics, "Borrower Strain", "Borrower Strain Source"),
        "Lender Strain": _current_metric_value(
            regime_metrics,
            "Lender Strain",
            "Lender Strain Source",
        ),
        "Concentration HHI": regime_metrics.get("Concentration HHI", np.nan),
        "Raw AI HHI": regime_metrics.get("Raw AI HHI", np.nan),
        "Avg Sector Pressure": regime_metrics.get("Avg Sector Pressure", np.nan),
        "ADI Capital Deployment": _component_value(regime_metrics, "ADI Components", "Capital Deployment"),
        "ADI Data Center Construction": _component_value(regime_metrics, "ADI Components", "Data Center Construction"),
        "ADI Compute Supply Realization": _component_value(regime_metrics, "ADI Components", "Compute Supply Realization"),
        "ADI Power Footprint": _component_value(regime_metrics, "ADI Components", "Power Footprint"),
        "Power Nonresidential Load": _component_value(regime_metrics, "Power Stress Components", "Commercial-vs-Residential Output Pressure"),
        "Power Grid Utilization": _component_value(regime_metrics, "Power Stress Components", "Power-System Utilization Pressure"),
        "Power Capacity Response": _component_value(regime_metrics, "Power Stress Components", "Potential-Output Response Gap"),
        "PCG Deployment Pressure": (regime_metrics.get("Power Capacity Gap Components", {}) or {}).get("deployment_pressure_score", np.nan),
        "PCG Power Response": (regime_metrics.get("Power Capacity Gap Components", {}) or {}).get("power_response_score", np.nan),
        "PCG Data Center Construction": _component_value(regime_metrics, "Power Capacity Gap Components", "Data Center Construction"),
        "PCG Capital Deployment": _component_value(regime_metrics, "Power Capacity Gap Components", "Capital Deployment"),
        "PCG Delivered Power Growth": _component_value(regime_metrics, "Power Capacity Gap Components", "Delivered Power Growth"),
        "PCG Installed Capacity Growth": _component_value(regime_metrics, "Power Capacity Gap Components", "Sustainable Capacity Growth"),
        "Borrower Cash Flow Strain": _component_value(regime_metrics, "Borrower Strain Components", "Cash Flow Strain"),
        "Borrower Debt Capacity Strain": _component_value(
            regime_metrics,
            "Borrower Strain Components",
            "Debt Capacity Strain",
        ),
        "Borrower Committed Burden": _component_value(regime_metrics, "Borrower Strain Components", "Committed Burden"),
        "Borrower Contingent Exposure": _component_value(regime_metrics, "Borrower Strain Components", "Contingent Exposure"),
        "Lender Credit Tightening": _component_value(
            regime_metrics,
            "Lender Strain Components",
            "Bank Credit Tightening",
        ),
        "Lender Bank Capital Strain": _component_value(
            regime_metrics,
            "Lender Strain Components",
            "Bank Capital Strain",
        ),
        "Lender Private Credit Impairment": _component_value(
            regime_metrics,
            "Lender Strain Components",
            "Private Credit Impairment",
        ),
        "Lender PE Portfolio Financing Strain": _component_value(
            regime_metrics,
            "Lender Strain Components",
            "PE Portfolio Financing Strain",
        ),
        "AEI Version": regime_metrics.get("AEI Version", np.nan),
        "Benchmark Version": BENCHMARK_VERSION,
        "Benchmark Weight Date": QQQ_WEIGHTS_EFFECTIVE_DATE,
        "ADI Version": regime_metrics.get("ADI Version", np.nan),
        "EVG Version": regime_metrics.get("EVG Version", np.nan),
        "Power Stress Version": regime_metrics.get("Power Stress Version", np.nan),
        "Power Capacity Gap Version": regime_metrics.get("Power Capacity Gap Version", np.nan),
        "Borrower Strain Version": regime_metrics.get("Borrower Strain Version", np.nan),
        "Lender Strain Version": regime_metrics.get(
            "Lender Strain Version", np.nan
        ),
        "Pressure Version": regime_metrics.get("Pressure Version", np.nan),
        "Consumer Sentiment": fred_data.get("Consumer Sentiment", {}).get("value", np.nan),
        "Fed Funds Rate": fred_data.get("Fed Funds Rate", {}).get("value", np.nan),
        "Industrial Production": fred_data.get("Industrial Production", {}).get("value", np.nan),
        "Industrial Production YoY": fred_data.get("Industrial Production YoY", {}).get("value", np.nan),
    }
    write_archive_snapshot(pd.DataFrame([row]), ARCHIVE_SPECS["macro"])

def append_sector_history(sector_metrics, *, observation_date):
    rows = [
        {
            "Date": str(observation_date),
            "Sector": sector,
            "Sector Score": metrics.get("Sector Score"),
            "Pressure": metrics.get("Sector Pressure"),
            "Forward EV/EBIT": metrics.get("Forward EV/EBIT"),
            "Sector Valuation Version": metrics.get("Sector Valuation Version"),
            "Forward EV/EBIT Coverage": metrics.get("Forward EV/EBIT Coverage"),
            "Forward EV/EBIT Data Coverage": metrics.get("Forward EV/EBIT Data Coverage"),
            "Loss-Making EV Share": metrics.get("Loss-Making EV Share"),
            "Forward EBIT Yield": metrics.get("Forward EBIT Yield"),
            "Avg Return": metrics.get("Avg Return"),
            "AEI Version": "4.0",
            "Benchmark Version": BENCHMARK_VERSION,
            "Benchmark Weight Date": QQQ_WEIGHTS_EFFECTIVE_DATE,
            "Pressure Version": "4.0",
        }
        for sector, metrics in sector_metrics.items()
    ]
    if rows:
        write_archive_snapshot(pd.DataFrame(rows), ARCHIVE_SPECS["sector"])

def append_benchmark_history(metrics_by_benchmark=None, *, observation_date=None):
    supplied = metrics_by_benchmark or {}
    rows = []
    for benchmark in ACTIVE_BENCHMARKS:
        metrics = supplied.get(benchmark) or get_benchmark_metrics(benchmark)
        aliases = metrics.get("member_aliases") or {}
        construction = "Fixed QQQ top-ten reference weights"
        if aliases.get("GOOGL") == "GOOG":
            construction += "; GOOGL weight uses retained GOOG Class C return"
        rows.append({
            "Date": str(observation_date or today_iso()),
            "Benchmark": benchmark,
            "Forward EV/EBIT": metrics.get("forward_ev_ebit"),
            "Forward EBIT Yield": metrics.get("forward_ebit_yield"),
            "Avg Return": metrics.get("avg_return"),
            "Beta": metrics.get("beta"),
            "Member Count": metrics.get("member_count"),
            "Benchmark Version": BENCHMARK_VERSION,
            "Weight Effective Date": QQQ_WEIGHTS_EFFECTIVE_DATE,
            "Member Coverage": 1.0 if metrics.get("member_count") == 10 else np.nan,
            "Return Construction": construction,
        })
    if rows:
        write_archive_snapshot(pd.DataFrame(rows), ARCHIVE_SPECS["benchmark"])

def build_yf_archive_snapshot(raw_yfinance, sector_data):
    """Build the retained YFinance snapshot from provider rows, not resolved fields.

    ``sector_data`` is used only for sector and basket metadata. Fundamental
    values in the retained YFinance archive must come from the resolved
    YFinance provider frame itself; otherwise EDGAR-priority fields from the
    analytical sector frame can leak into ``yf_history.csv``.
    """
    if raw_yfinance is None or not isinstance(raw_yfinance, pd.DataFrame) or raw_yfinance.empty:
        return pd.DataFrame(columns=["Sector", *YF_ARCHIVE_COLUMNS])

    raw = raw_yfinance.copy()
    if "Ticker" not in raw.columns:
        return pd.DataFrame(columns=["Sector", *YF_ARCHIVE_COLUMNS])
    raw["Ticker"] = raw["Ticker"].astype(str).str.upper().str.strip()

    metadata_rows = []
    for sector, frame in (sector_data or {}).items():
        if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty or "Ticker" not in frame.columns:
            continue
        available = [
            column
            for column in ("Ticker", "Basket Score", "Basket Tier", "Basket Weight")
            if column in frame.columns
        ]
        meta = frame[available].copy()
        meta["Ticker"] = meta["Ticker"].astype(str).str.upper().str.strip()
        meta["Sector"] = sector
        metadata_rows.append(meta)

    if not metadata_rows:
        return pd.DataFrame(columns=["Sector", *YF_ARCHIVE_COLUMNS])

    metadata = (
        pd.concat(metadata_rows, ignore_index=True)
        .drop_duplicates(subset=["Ticker"], keep="last")
    )
    metadata_columns = ["Sector", "Basket Score", "Basket Tier", "Basket Weight"]
    raw = raw.drop(columns=[column for column in metadata_columns if column in raw.columns], errors="ignore")
    snapshot = raw.merge(metadata, on="Ticker", how="left", validate="one_to_one")
    ordered = ["Sector", *YF_ARCHIVE_COLUMNS]
    for column in ordered:
        if column not in snapshot.columns:
            snapshot[column] = np.nan
    return snapshot[ordered].copy()


def append_yf_history(raw_yfinance, sector_data, *, observation_date):
    snapshot = build_yf_archive_snapshot(raw_yfinance, sector_data)
    if snapshot.empty:
        return
    append_dataframe_history(
        snapshot,
        ARCHIVE_SPECS["yf"],
        key_cols=ARCHIVE_KEYS["yf"],
        observation_date=observation_date,
    )

def append_edgar_history(edgar_snapshot):
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

def append_energy_history(energy_data):
    if not energy_data or str(energy_data.get("source_mode", "")) not in {"live_weekly", "live_manual", "live_with_local_fallback"}:
        return

    row = {
        "Date": str(energy_data.get("snapshot_date", "")),
        "Version": ENERGY_DATA_VERSION,
    }
    for name in ENERGY_SERIES:
        payload = ((energy_data.get("series", {}) or {}).get(name, {}) or {})
        row[name] = payload.get("value", np.nan)
        row[f"{name} Date"] = payload.get("date")
        row[f"{name} Change"] = payload.get("change_pct", np.nan)

    write_archive_snapshot(pd.DataFrame([row]), ARCHIVE_SPECS["energy"])
