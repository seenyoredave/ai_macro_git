import tempfile
import unittest
from pathlib import Path

import pandas as pd

from analytics.intermediation_stress_engine import (
    calculate_intermediation_stress,
    load_bank_capital_history,
    load_bdc_impairment_history,
)


class CreditIntermediationStressTests(unittest.TestCase):
    def test_current_metric_is_finite_and_fully_constituted(self):
        result = calculate_intermediation_stress({})
        self.assertTrue(pd.notna(result["score"]))
        self.assertEqual(result["valid_components"], 4)
        self.assertEqual(result["coverage"], 1.0)

    def test_bdc_proxy_is_asset_weighted(self):
        history = load_bdc_impairment_history()
        latest = history.iloc[-1]
        self.assertAlmostEqual(
            latest["Weighted Nonaccrual at Cost (%)"],
            3.3581912805,
            places=6,
        )
        self.assertEqual(latest["Observations"], 5)

    def test_bank_capital_history_reaches_before_2014(self):
        history = load_bank_capital_history()
        self.assertEqual(history.iloc[0]["Date"].date().isoformat(), "2009-10-01")
        self.assertAlmostEqual(
            history.iloc[-1]["Tier 1 Capital Ratio (%)"],
            13.902,
            places=3,
        )

    def test_live_fred_payload_overrides_bundled_bank_observations(self):
        result = calculate_intermediation_stress(
            {
                "Business Loan Tightening": {
                    "value": 20.0,
                    "date": "2026-07-01",
                    "source": "FRED Live",
                },
                "Bank Tier 1 Capital Ratio": {
                    "value": 13.5,
                    "date": "2026-04-01",
                    "source": "FRED Live",
                },
            }
        )
        tightening = result["components"]["Bank Credit Tightening"]
        capital = result["components"]["Bank Capital Strain"]
        self.assertEqual(tightening["raw"], 20.0)
        self.assertEqual(tightening["as_of"], "2026-07-01")
        self.assertEqual(tightening["source"], "FRED Live")
        self.assertEqual(capital["raw"], 13.5)
        self.assertEqual(capital["as_of"], "2026-04-01")

    def test_one_missing_pillar_still_scores_from_three(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            empty_bdc = Path(temp_dir) / "empty_bdc.csv"
            pd.DataFrame(
                columns=[
                    "Date",
                    "Ticker",
                    "Portfolio Cost ($mm)",
                    "Nonaccrual at Cost (%)",
                ]
            ).to_csv(empty_bdc, index=False)
            result = calculate_intermediation_stress({}, bdc_path=empty_bdc)
            self.assertTrue(pd.notna(result["score"]))
            self.assertEqual(result["valid_components"], 3)
            self.assertEqual(result["coverage"], 0.75)

    def test_history_uses_step_observation_dates(self):
        result = calculate_intermediation_stress({})
        history = result["history"]
        self.assertFalse(history.empty)
        self.assertIn("Credit Intermediation Stress", history.columns)
        self.assertIn("Bank Capital Strain", history.columns)
        self.assertEqual(
            pd.Timestamp(history.iloc[-1]["Date"]).date().isoformat(),
            "2026-04-01",
        )


if __name__ == "__main__":
    unittest.main()
