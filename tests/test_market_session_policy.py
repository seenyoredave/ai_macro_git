from datetime import datetime, timezone
from pathlib import Path

from config.market_clock import (
    eastern_now,
    is_market_hours,
    market_date,
    yfinance_load_decision,
)


ROOT = Path(__file__).resolve().parents[1]


def test_yfinance_daily_decision_matrix():
    assert yfinance_load_decision(
        force_refresh=False,
        market_open=True,
        has_current_archive=False,
        has_latest_archive=True,
    ) == "automatic_live"
    assert yfinance_load_decision(
        force_refresh=False,
        market_open=True,
        has_current_archive=True,
        has_latest_archive=True,
    ) == "archive_current"
    assert yfinance_load_decision(
        force_refresh=False,
        market_open=False,
        has_current_archive=False,
        has_latest_archive=True,
    ) == "archive_closed"
    assert yfinance_load_decision(
        force_refresh=True,
        market_open=False,
        has_current_archive=True,
        has_latest_archive=True,
    ) == "manual_live"


def test_eastern_clock_handles_utc_rollover_and_daylight_saving():
    # 2026-07-30 02:30 UTC is still 2026-07-29 in New York.
    rollover = datetime(2026, 7, 30, 2, 30, tzinfo=timezone.utc)
    assert market_date(rollover).isoformat() == "2026-07-29"

    # In July, 15:59 ET is 19:59 UTC and the 16:00 close is 20:00 UTC.
    assert is_market_hours(datetime(2026, 7, 29, 19, 59, tzinfo=timezone.utc))
    assert not is_market_hours(datetime(2026, 7, 29, 20, 0, tzinfo=timezone.utc))

    # In January, the same 16:00 Eastern close is 21:00 UTC.
    winter_close = eastern_now(datetime(2026, 1, 15, 21, 0, tzinfo=timezone.utc))
    assert winter_close.hour == 16
    assert not is_market_hours(datetime(2026, 1, 15, 21, 0, tzinfo=timezone.utc))


def test_developer_source_refresh_controls_are_independent():
    app = (ROOT / "ai_macro.py").read_text()
    assert 'st.button("Refresh Dashboard"' in app
    assert 'st.button("Refresh YFinance"' in app
    assert 'st.button("Refresh EDGAR"' in app
    assert 'st.button("Refresh Energy"' in app
    assert 'st.button("Refresh live dashboard"' not in app

    dashboard_block = app.split('if st.button("Refresh Dashboard"', 1)[1].split(
        'if st.button("Refresh YFinance"', 1
    )[0]
    assert "st.cache_data.clear()" not in dashboard_block
    assert "force_yfinance_refresh" not in dashboard_block
    assert "force_edgar_refresh" not in dashboard_block

    yf_block = app.split('if st.button("Refresh YFinance"', 1)[1].split(
        'if st.button("Refresh EDGAR"', 1
    )[0]
    assert "force_yfinance_refresh = True" in yf_block
    assert "force_edgar_refresh = True" not in yf_block

    edgar_block = app.split('if st.button("Refresh EDGAR"', 1)[1].split(
        'if st.button("Refresh Energy"', 1
    )[0]
    assert "force_edgar_refresh = True" in edgar_block
    assert "force_yfinance_refresh = True" not in edgar_block
    assert "force_energy_refresh = True" not in edgar_block

    energy_block = app.split('if st.button("Refresh Energy"', 1)[1].split(
        'if st.button("Clear cache"', 1
    )[0]
    assert "force_energy_refresh = True" in energy_block
    assert "force_yfinance_refresh = True" not in energy_block
    assert "force_edgar_refresh = True" not in energy_block
