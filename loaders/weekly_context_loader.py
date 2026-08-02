from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVENT_PATH = ROOT / "data" / "weekly_context_events.csv"
WEEKLY_CONTEXT_VERSION = "1.0"
REQUIRED_COLUMNS = {
    "event_id",
    "event_date",
    "domain",
    "event_type",
    "priority",
    "verified_fact",
    "platform_relevance",
    "source_name",
    "source_label",
    "source_url",
    "source_type",
    "verification_status",
    "expires_after_days",
}

def _clean_sentence(value) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    return text if text.endswith((".", "!", "?")) else f"{text}."

def _valid_https_url(value) -> bool:
    try:
        parsed = urlparse(str(value).strip())
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.netloc)

def _select_diverse(frame: pd.DataFrame, limit: int) -> pd.DataFrame:
    if frame.empty or limit <= 0:
        return frame.iloc[0:0].copy()
    ranked = frame.sort_values(
        ["priority", "event_date", "event_id"],
        ascending=[False, False, True],
        kind="stable",
    )
    chosen_indexes = []
    used_domains = set()
    for index, row in ranked.iterrows():
        domain = str(row.get("domain", "")).strip().lower()
        if domain in used_domains:
            continue
        chosen_indexes.append(index)
        used_domains.add(domain)
        if len(chosen_indexes) >= limit:
            return ranked.loc[chosen_indexes].copy()
    for index in ranked.index:
        if index in chosen_indexes:
            continue
        chosen_indexes.append(index)
        if len(chosen_indexes) >= limit:
            break
    return ranked.loc[chosen_indexes].copy()

def load_weekly_context(*, as_of=None, path=None, limit=3):
    current = pd.Timestamp(as_of or pd.Timestamp.now()).normalize()
    source_path = Path(path or DEFAULT_EVENT_PATH)
    window_start = current - pd.Timedelta(days=6)
    empty_result = {
        "events": [],
        "references": [],
        "as_of": current.date().isoformat(),
        "window_start": window_start.date().isoformat(),
        "source": "unavailable",
        "version": WEEKLY_CONTEXT_VERSION,
    }
    if not source_path.exists():
        return empty_result

    frame = pd.read_csv(source_path)
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"Weekly context registry is missing columns: {sorted(missing)}")

    frame = frame.copy()
    frame["event_date"] = pd.to_datetime(frame["event_date"], errors="coerce").dt.normalize()
    frame["priority"] = pd.to_numeric(frame["priority"], errors="coerce")
    frame["expires_after_days"] = pd.to_numeric(
        frame["expires_after_days"], errors="coerce"
    )
    frame["source_type"] = frame["source_type"].astype(str).str.strip().str.lower()
    frame["verification_status"] = (
        frame["verification_status"].astype(str).str.strip().str.lower()
    )

    age_days = (current - frame["event_date"]).dt.days
    valid = (
        frame["event_date"].notna()
        & frame["priority"].notna()
        & frame["expires_after_days"].notna()
        & frame["event_date"].between(window_start, current)
        & age_days.ge(0)
        & age_days.le(frame["expires_after_days"])
        & frame["source_type"].eq("primary")
        & frame["verification_status"].eq("confirmed")
        & frame["source_url"].map(_valid_https_url)
    )
    frame = _select_diverse(frame.loc[valid].copy(), max(0, int(limit)))

    events = []
    references = []
    for row in frame.to_dict("records"):
        fact = _clean_sentence(row.get("verified_fact"))
        relevance = _clean_sentence(row.get("platform_relevance"))
        source_label = " ".join(str(row.get("source_label") or "").split()).strip()
        source_name = " ".join(str(row.get("source_name") or "").split()).strip()
        source_url = str(row.get("source_url") or "").strip()
        if not fact or not relevance or not source_label or not source_name:
            continue
        reference_number = len(events) + 1
        event = {
            "event_id": str(row["event_id"]),
            "event_date": pd.Timestamp(row["event_date"]).date().isoformat(),
            "domain": str(row["domain"]),
            "event_type": str(row["event_type"]),
            "priority": float(row["priority"]),
            "verified_fact": fact,
            "platform_relevance": relevance,
            "display": f"{fact} {relevance}",
            "reference_number": reference_number,
            "source_name": source_name,
            "source_label": source_label,
            "source_url": source_url,
            "source_type": "primary",
            "verification_status": "confirmed",
        }
        events.append(event)
        references.append(
            {
                "reference_number": reference_number,
                "event_id": event["event_id"],
                "source_name": source_name,
                "source_label": source_label,
                "source_url": source_url,
                "event_date": event["event_date"],
            }
        )

    return {
        "events": events,
        "references": references,
        "as_of": current.date().isoformat(),
        "window_start": window_start.date().isoformat(),
        "source": "curated primary-source registry",
        "version": WEEKLY_CONTEXT_VERSION,
    }
