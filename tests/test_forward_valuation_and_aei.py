import unittest

import numpy as np
import pandas as pd
import pytest

from analytics.factor_engine import (
    calc_forward_ebit_yield_discount,
    calc_market_breadth,
    calc_relative_performance,
)
from analytics.valuation import aggregate_forward_ebit_yield
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


    def test_negative_aggregate_forward_ebit_remains_valid_for_yield_factor(self):
        frame = pd.DataFrame(
            {
                "Forward EBIT": [10.0, -20.0, 5.0, -10.0, 2.0],
                "Enterprise Value": [100.0, 200.0, 100.0, 100.0, 100.0],
            }
        )
        sector_yield = frame["Forward EBIT"].sum() / frame["Enterprise Value"].sum()
        benchmark_yield = 0.06
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


def test_signed_sector_ev_ebit_subtracts_negative_company_contributions():
    from analytics.valuation import aggregate_signed_forward_ev_ebit

    frame = pd.DataFrame(
        {
            "Enterprise Value": [100.0, 200.0, 300.0, 400.0, 500.0],
            "Forward EBIT": [10.0, 10.0, -10.0, 20.0, -25.0],
            "Effective Basket Weight": [1.0, 2.0, 1.0, 1.0, 1.0],
        }
    )
    result = aggregate_signed_forward_ev_ebit(frame, min_count=5, min_coverage=0.60)
    company_multiples = pd.Series([10.0, 20.0, -30.0, 20.0, -20.0])
    weights = pd.Series([1.0, 2.0, 1.0, 1.0, 1.0])
    expected = float((company_multiples * weights / weights.sum()).sum())
    assert result["multiple"] == pytest.approx(expected)
    assert result["positive_contribution"] > 0
    assert result["negative_contribution"] < 0


def test_sector_dataframe_reconstructs_negative_company_ev_ebit():
    from analytics.sector_dataframe import resolve_sector_dataframe

    raw = {
        "yfinance": pd.DataFrame(
            {
                "Ticker": ["LOSS"],
                "Company": ["Loss Co"],
                "Enterprise Value": [200.0],
                "Forward EBIT": [-10.0],
                "Forward EV/EBIT": [np.nan],
            }
        ),
        "edgar": {},
    }
    out = resolve_sector_dataframe(raw)
    assert out.loc[0, "Forward EV/EBIT"] == -20.0


def test_profitable_cohort_ev_ebit_and_loss_making_share_are_separate_products():
    from analytics.valuation import aggregate_profitable_forward_ev_ebit

    frame = pd.DataFrame(
        {
            "Enterprise Value": [100.0, 200.0, 300.0, 400.0, 500.0],
            "Forward EBIT": [10.0, 20.0, -10.0, 40.0, 0.0],
        }
    )
    result = aggregate_profitable_forward_ev_ebit(
        frame,
        min_valid_count=5,
        min_profitable_count=3,
        min_coverage=0.60,
    )

    expected_multiple = (100.0 + 200.0 + 400.0) / (10.0 + 20.0 + 40.0)
    expected_loss_share = (300.0 + 500.0) / 1500.0
    assert result["multiple"] == pytest.approx(expected_multiple)
    assert result["loss_making_ev_share"] == pytest.approx(expected_loss_share)
    assert result["profitable_ev_share"] == pytest.approx(1.0 - expected_loss_share)
    assert result["profitable_company_count"] == 3
    assert result["loss_making_company_count"] == 2


def test_near_zero_negative_ebit_cannot_blow_up_profitable_cohort_multiple():
    from analytics.valuation import aggregate_profitable_forward_ev_ebit

    frame = pd.DataFrame(
        {
            "Enterprise Value": [100.0, 200.0, 300.0, 400.0, 50_000.0],
            "Forward EBIT": [10.0, 20.0, 30.0, 40.0, -0.0001],
        }
    )
    result = aggregate_profitable_forward_ev_ebit(frame)

    assert result["multiple"] == pytest.approx((100.0 + 200.0 + 300.0 + 400.0) / 100.0)
    assert result["loss_making_ev_share"] == pytest.approx(50_000.0 / 51_000.0)
