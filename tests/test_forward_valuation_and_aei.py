import unittest

import numpy as np
import pandas as pd

from analytics.factor_engine import (
    calc_forward_ebit_yield_discount,
    calc_market_breadth,
    calc_relative_performance,
)
from benchmarks.benchmark_normalization import normalize_benchmark_dataframe
from factors.factor_weights import FACTOR_WEIGHTS
from loaders.company_fundamentals import (
    _latest_statement_value,
    calc_forward_revenue,
)


class _TickerWithEstimates:
    revenue_estimate = pd.DataFrame(
        {
            "numberOfAnalysts": [12, 14, 16, 18],
            "avg": [100.0, 110.0, 400.0, 500.0],
            "low": [90.0, 100.0, 380.0, 470.0],
            "high": [110.0, 120.0, 420.0, 530.0],
        },
        index=["0q", "+1q", "0y", "+1y"],
    )


class _TickerWithoutEstimates:
    revenue_estimate = pd.DataFrame()


class _TickerWithGrowthOnlyEstimate:
    revenue_estimate = pd.DataFrame(
        {"growth": [0.05, 0.20]},
        index=["0y", "+1y"],
    )


class _TickerWithShortQuarterlyAndAnnual:
    quarterly_income_stmt = pd.DataFrame(
        {"2026Q2": [25.0], "2026Q1": [20.0]},
        index=["Operating Income"],
    )
    income_stmt = pd.DataFrame(
        {"2025": [120.0], "2024": [100.0]},
        index=["Operating Income"],
    )


class ForwardValuationAndAEITests(unittest.TestCase):
    def test_forward_revenue_parser_prefers_next_year_consensus(self):
        value = calc_forward_revenue(
            _TickerWithEstimates(),
            {"revenueGrowth": 0.10},
            latest_revenue=400.0,
        )
        self.assertEqual(value, 500.0)

    def test_forward_revenue_has_explicit_growth_fallback(self):
        value = calc_forward_revenue(
            _TickerWithoutEstimates(),
            {"revenueGrowth": 0.10},
            latest_revenue=400.0,
        )
        self.assertAlmostEqual(value, 440.0)

    def test_forward_revenue_uses_analyst_growth_before_reported_growth(self):
        value = calc_forward_revenue(
            _TickerWithGrowthOnlyEstimate(),
            {"revenueGrowth": 0.10},
            latest_revenue=400.0,
        )
        self.assertAlmostEqual(value, 480.0)

    def test_ttm_statement_value_does_not_mix_one_quarter_with_annual_revenue(self):
        value = _latest_statement_value(
            _TickerWithShortQuarterlyAndAnnual(),
            ["quarterly_income_stmt", "income_stmt"],
            ["Operating Income"],
            ttm=True,
        )
        self.assertEqual(value, 120.0)

    def test_sector_forward_ebit_yield_uses_ratio_of_sums(self):
        frame = pd.DataFrame(
            {
                "Forward EBIT": [10.0, 90.0, 20.0, 20.0, 20.0],
                "Enterprise Value": [100.0, 1800.0, 400.0, 400.0, 400.0],
            }
        )
        sector_yield = frame["Forward EBIT"].sum() / frame["Enterprise Value"].sum()
        benchmark_yield = 0.08
        discount = calc_forward_ebit_yield_discount(frame, benchmark_yield)
        self.assertAlmostEqual(discount, benchmark_yield - sector_yield)

    def test_benchmark_uses_ratio_of_sums_operating_earnings_yield(self):
        frame = pd.DataFrame(
            {
                "Forward EBIT": [10.0, 20.0],
                "Enterprise Value": [100.0, 400.0],
                "Benchmark Weight": [0.75, 0.25],
                "1Y Return": [0.20, 0.00],
                "Beta": [1.2, 0.8],
                "Ticker": ["A", "B"],
            }
        )
        metrics = normalize_benchmark_dataframe(frame)
        expected_yield = (10.0 + 20.0) / (100.0 + 400.0)
        self.assertAlmostEqual(metrics["forward_ebit_yield"], expected_yield)
        self.assertAlmostEqual(metrics["forward_ev_ebit"], 1.0 / expected_yield)

    def test_aei_has_three_distinct_factors_and_weights_sum_to_one(self):
        self.assertEqual(
            set(FACTOR_WEIGHTS),
            {"forward_ebit_yield_discount", "relative_performance", "market_breadth"},
        )
        self.assertAlmostEqual(sum(FACTOR_WEIGHTS.values()), 1.0)

    def test_breadth_uses_200_day_participation(self):
        frame = pd.DataFrame(
            {
                "Price Extension 200D": [0.1, 0.2, -0.1, 0.0, 0.3],
                "1Y Return": [0.5, -0.2, 0.1, 0.2, -0.4],
                "Basket Weight": [1, 1, 1, 1, 1],
            }
        )
        self.assertAlmostEqual(calc_market_breadth(frame), 3 / 5)
        self.assertAlmostEqual(calc_relative_performance(frame, 0.0), 0.04)


if __name__ == "__main__":
    unittest.main()
