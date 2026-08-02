from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

EASTERN_TIME = ZoneInfo("America/New_York")
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)

def eastern_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(EASTERN_TIME)
    if now.tzinfo is None:
        return now.replace(tzinfo=EASTERN_TIME)
    return now.astimezone(EASTERN_TIME)

def utc_now(now: datetime | None = None) -> datetime:
    return eastern_now(now).astimezone(timezone.utc)

def market_date(now: datetime | None = None):
    return eastern_now(now).date()

def is_market_hours(now: datetime | None = None) -> bool:
    current = eastern_now(now)
    return current.weekday() < 5 and MARKET_OPEN <= current.time().replace(tzinfo=None) < MARKET_CLOSE

def market_cache_token(now: datetime | None = None) -> str:
    current = eastern_now(now)
    phase = "open" if is_market_hours(current) else "closed"
    return f"{current.date().isoformat()}:{phase}"

def yfinance_load_decision(
    *,
    force_refresh: bool,
    market_open: bool,
    has_current_archive: bool,
    has_latest_archive: bool,
) -> str:
    if force_refresh:
        return "manual_live"
    if has_current_archive:
        return "archive_current"
    if market_open:
        return "automatic_live"
    if has_latest_archive:
        return "archive_closed"
    return "unavailable"
