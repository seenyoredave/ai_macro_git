"""Market-session clock used by loaders, archive dating, and the UI.

America/New_York is the source-of-truth timezone so the 16:00 market close
tracks daylight-saving changes correctly. UTC timestamps may still be emitted
for diagnostics, but all session and archive-date decisions use Eastern time.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo


EASTERN_TIME = ZoneInfo("America/New_York")
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)


def eastern_now(now: datetime | None = None) -> datetime:
    """Return an aware datetime normalized to U.S. Eastern time."""
    if now is None:
        return datetime.now(EASTERN_TIME)
    if now.tzinfo is None:
        return now.replace(tzinfo=EASTERN_TIME)
    return now.astimezone(EASTERN_TIME)



def utc_now(now: datetime | None = None) -> datetime:
    """Return an aware UTC datetime for diagnostics and reporting."""
    return eastern_now(now).astimezone(timezone.utc)


def market_date(now: datetime | None = None):
    """Return the current U.S. Eastern calendar date."""
    return eastern_now(now).date()


def is_market_hours(now: datetime | None = None) -> bool:
    """Return True during the regular Monday-Friday 9:30-16:00 ET window."""
    current = eastern_now(now)
    return current.weekday() < 5 and MARKET_OPEN <= current.time().replace(tzinfo=None) < MARKET_CLOSE


def market_cache_token(now: datetime | None = None) -> str:
    """Invalidate cached loader decisions at date and market-window boundaries."""
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
    """Return the explicit YFinance source decision for this request."""
    if force_refresh:
        return "manual_live"
    if has_current_archive:
        return "archive_current"
    if market_open:
        return "automatic_live"
    if has_latest_archive:
        return "archive_closed"
    return "unavailable"
