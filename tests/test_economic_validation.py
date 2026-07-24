import tempfile
import unittest
from pathlib import Path

import pandas as pd

from analytics.economic_validation import calculate_economic_validation_gap


class EconomicValidationGapTests(unittest.TestCase):
    def _sector_frame(self):
        return pd.DataFrame(
            {
                "Ticker": ["A", "B", "C", "D", "E"],
                "CapEx": [110.0, 220.0, 55.0, 110.0, 55.0],
                "CapEx Growth": [0.10, 0.10, 0.10, 0.10, 0.10],
                "Revenue": [1200.0, 2400.0, 600.0, 1200.0, 600.0],
                "Revenue Growth": [0.20, 0.20, 0.20, 0.20, 0.20],
            }
        )

    def test_gap_uses_aligned_yoy_inputs_and_ratio_of_sums(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            yf_path = Path(temp_dir) / "yf.csv"
            info_path = Path(temp_dir) / "info.csv"
            pd.DataFrame().to_csv(yf_path, index=False)
            pd.DataFrame().to_csv(info_path, index=False)

            result = calculate_economic_validation_gap(
                {"ENTERPRISE_AI_SOFTWARE": self._sector_frame()},
                {"Info Processing Investment YoY": {"value": 0.05}},
                yf_history_path=yf_path,
                info_history_path=info_path,
            )

        components = result["components"]
        self.assertAlmostEqual(components["Capital Deployment"]["raw"], 0.10)
        self.assertAlmostEqual(components["Revenue Validation"]["raw"], 0.20)
        self.assertAlmostEqual(components["Macro Investment Validation"]["raw"], 0.05)
        self.assertAlmostEqual(
            result["score"],
            result["deployment_score"] - result["validation_score"],
        )

    def test_old_quarterly_saar_key_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            yf_path = Path(temp_dir) / "yf.csv"
            info_path = Path(temp_dir) / "info.csv"
            pd.DataFrame().to_csv(yf_path, index=False)
            pd.DataFrame().to_csv(info_path, index=False)
            result = calculate_economic_validation_gap(
                {"ENTERPRISE_AI_SOFTWARE": self._sector_frame()},
                {"Info Processing Investment Growth": {"value": 30.0}},
                yf_history_path=yf_path,
                info_history_path=info_path,
            )
        self.assertTrue(pd.isna(result["score"]))


if __name__ == "__main__":
    unittest.main()
