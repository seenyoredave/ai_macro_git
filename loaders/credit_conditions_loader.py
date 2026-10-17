"""Retained daily spreads and weekly lender inputs; Reader loads never fetch."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from config.deployment import PROJECT_ROOT, repository_writes_enabled
from helpers.atomic_io import atomic_write_csv
from loaders.official_series_refresh import fetch_fred_series_batch

HISTORY_PATH = PROJECT_ROOT / "data" / "finance" / "credit_conditions_history.csv"
OAS_SERIES = {"IG": "BAMLC0A0CM", "HY": "BAMLH0A0HYM2"}
WEEKLY_SERIES = {
    "Credit conditions": "NFCICREDIT",
    "Borrowings": "H8B3094NCBA",  # millions USD; remaining H.8 levels are billions
    "Deposits": "DPSACBW027SBOG",
    "Cash": "CASACBW027SBOG",
    "Assets": "TLAACBW027SBOG",
    "Loans": "TOTLL",
}
SERIES_IDS = tuple(OAS_SERIES.values()) + tuple(WEEKLY_SERIES.values())
COLUMNS = ["Date", "Series ID", "Value", "Retrieved At"]


def normalize_history(frame):
    if frame is None or frame.empty or not {"Date", "Series ID", "Value"}.issubset(frame):
        return pd.DataFrame({"Date": pd.Series(dtype="datetime64[ns]"), "Series ID": pd.Series(dtype=str), "Value": pd.Series(dtype=float), "Retrieved At": pd.Series(dtype=str)})
    out = frame.copy()
    if "Retrieved At" not in out:
        out["Retrieved At"] = ""
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce", utc=True).dt.tz_localize(None).dt.normalize()
    out["Value"] = pd.to_numeric(out["Value"], errors="coerce").replace([np.inf, -np.inf], np.nan)
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    out = out.dropna(subset=["Date", "Value"])
    out = out[out["Series ID"].isin(SERIES_IDS) & out["Date"].le(today)]
    return out[COLUMNS].sort_values("Date", kind="stable").drop_duplicates(["Series ID", "Date"], keep="last").reset_index(drop=True)


def load_credit_conditions(*, force_refresh=False, allow_live=False, path=None):
    target = Path(path or HISTORY_PATH)
    errors = {}
    try:
        retained = normalize_history(pd.read_csv(target)) if target.exists() else normalize_history(None)
    except Exception as exc:
        retained = normalize_history(None)
        errors["retained"] = type(exc).__name__
    history = retained.copy()
    refreshed = []
    attempted = bool(force_refresh and allow_live and repository_writes_enabled())
    if attempted:
        try:
            # OAS providers expose a rolling window. Merge rather than replace
            # so observations already accumulated locally are preserved.
            batch = fetch_fred_series_batch(SERIES_IDS, start_date="2000-01-01")
            errors.update(getattr(batch, "errors", {}))
            stamp = pd.Timestamp.now(tz="UTC").isoformat()
            for sid in SERIES_IDS:
                incoming = batch.get(sid)
                if incoming is None or incoming.empty:
                    errors.setdefault(sid, "No numeric observations returned")
                    continue
                new = normalize_history(incoming.assign(**{"Series ID": sid, "Retrieved At": stamp}))
                old = retained[retained["Series ID"].eq(sid)]
                invalid_level = sid != "NFCICREDIT" and (new["Value"].lt(0).any() or (sid not in OAS_SERIES.values() and new["Value"].le(0).any()))
                if new.empty or invalid_level or (not old.empty and new["Date"].max() < old["Date"].max()):
                    errors[sid] = "Rejected empty, invalid, or regressed history; retained prior observations"
                    continue
                history = normalize_history(pd.concat([history, new], ignore_index=True))
                refreshed.append(sid)
            if refreshed:
                output = history.copy()
                output["Date"] = output["Date"].dt.strftime("%Y-%m-%d")
                atomic_write_csv(output, target)
        except Exception as exc:
            # Shared FRED helper sanitizes authenticated request exceptions.
            errors["refresh"] = str(exc)
    mode = "partial_refresh" if refreshed and errors else "live" if refreshed else "retained_fallback" if attempted else "retained"
    missing = [sid for sid in SERIES_IDS if history[history["Series ID"].eq(sid)].empty]
    report = {"source_mode": mode, "errors": errors, "missing_series": missing,
              "refreshed_series": refreshed, "returned_series": len(SERIES_IDS) - len(missing)}
    return {"history": history, "load_report": report}


def series_history(data, sid):
    frame = (data or {}).get("history")
    frame = normalize_history(frame)
    return frame.loc[frame["Series ID"].eq(sid), ["Date", "Value", "Retrieved At"]].reset_index(drop=True)


def spread_snapshot(data):
    result = {}
    for label, sid in OAS_SERIES.items():
        frame = series_history(data, sid)
        frame["Value"] = frame["Value"] * 100.0
        item = {"history": frame, "value": np.nan, "date": None, "changes": {}}
        if not frame.empty:
            last = frame.iloc[-1]
            item.update(value=float(last["Value"]), date=last["Date"], retrieved_at=last["Retrieved At"])
            item["changes"] = {n: float(last["Value"] - frame.iloc[-n-1]["Value"]) if len(frame) > n else np.nan for n in (1, 5, 20)}
        result[label] = item
    common = result["IG"]["history"].merge(result["HY"]["history"], on="Date", suffixes=("_IG", "_HY"))
    result["gap"] = {"date": common.iloc[-1]["Date"], "value": float(common.iloc[-1]["Value_HY"] - common.iloc[-1]["Value_IG"])} if not common.empty else {"date": None, "value": np.nan}
    return result
