import math

import pandas as pd

from analytics.trend_engine import calc_metric_trend, distinct_metric_observations
from loaders.market_freshness import merge_live_with_archive


def test_live_market_rows_win_and_archive_only_fills_failed_tickers():
    fresh = pd.DataFrame(
        [
            {"Ticker": "AAA", "Price": 20.0, "Market Cap": 200.0},
        ]
    )
    archive = pd.DataFrame(
        [
            {"Ticker": "AAA", "Price": 10.0, "Market Cap": 100.0},
            {"Ticker": "BBB", "Price": 5.0, "Market Cap": 50.0},
        ]
    )

    merged = merge_live_with_archive(
        fresh,
        archive,
        {"AAA": "AAA", "BBB": "BBB"},
        required_columns=["Ticker", "Price", "Market Cap"],
    ).set_index("Ticker")

    assert merged.at["AAA", "Price"] == 20.0
    assert merged.at["AAA", "Market Cap"] == 200.0
    assert merged.at["BBB", "Price"] == 5.0
    assert merged.at["BBB", "Market Cap"] == 50.0


def test_market_merge_reports_live_and_archive_coverage():
    fresh = pd.DataFrame([{"Ticker": "AAA", "Market Cap": 200.0}])
    archive = pd.DataFrame(
        [
            {"Ticker": "AAA", "Market Cap": 100.0},
            {"Ticker": "BBB", "Market Cap": 50.0},
        ]
    )

    merged = merge_live_with_archive(
        fresh,
        archive,
        {"AAA": "AAA", "BBB": "BBB"},
        required_columns=["Ticker", "Market Cap"],
    )
    report = merged.attrs["load_report"]

    assert report["source_mode"] == "live_with_archive_fallback"
    assert report["live_tickers"] == 1
    assert report["archive_fallback_tickers"] == 1
    assert report["archive_fallback_symbols"] == ["BBB"]
    assert report["missing_tickers"] == []


def test_distinct_observation_trend_ignores_repeated_daily_snapshots():
    history = pd.DataFrame(
        {
            "Date": [
                "2026-06-13",
                "2026-07-23",
                "2026-07-24",
                "2026-07-25",
                "2026-07-28",
            ],
            "Borrower Financial Condition": [
                -14.139242,
                -0.447844,
                -0.447844,
                -0.167322,
                -0.167322,
            ],
            "Borrower Financial Condition Version": ["3.0"] * 5,
        }
    )

    trend = calc_metric_trend(
        history,
        "Borrower Financial Condition",
        version_column="Borrower Financial Condition Version",
        required_version="3.0",
        distinct_observations=True,
    )

    assert len(trend["history"]) == 5
    assert trend["dynamics_observations"] == 3
    assert math.isclose(trend["velocity"], 0.280522, abs_tol=1e-6)
    assert math.isclose(trend["acceleration"], -13.410876, abs_tol=1e-6)


def test_distinct_observation_helper_preserves_first_and_each_change_point():
    series = pd.DataFrame(
        {
            "Date": pd.date_range("2026-01-01", periods=6),
            "Value": [1.0, 1.0, 1.0, 3.0, 3.0, 2.0],
        }
    )

    distinct = distinct_metric_observations(series)

    assert distinct["Value"].tolist() == [1.0, 3.0, 2.0]
