import unittest

import pandas as pd

from analytics.capital_stress_engine import _debt_capacity_stress


class DebtCapacityStressTests(unittest.TestCase):
    def test_negative_ebitda_with_net_debt_is_high_stress(self):
        frame = pd.DataFrame(
            {
                "Net Debt": [100.0, 200.0],
                "EBITDA": [-10.0, 0.0],
                "Revenue": [500.0, 500.0],
            }
        )
        result = _debt_capacity_stress(frame)
        self.assertGreaterEqual(result["score"], 70.0)
        self.assertEqual(result["impaired_companies"], 2)

    def test_negative_ebitda_with_net_cash_is_not_leverage_failure(self):
        frame = pd.DataFrame(
            {
                "Net Debt": [-100.0, -50.0],
                "EBITDA": [-10.0, 0.0],
                "Revenue": [500.0, 500.0],
            }
        )
        result = _debt_capacity_stress(frame)
        self.assertEqual(result["score"], 25.0)
        self.assertEqual(result["net_cash_companies"], 2)

    def test_mixed_branches_remain_finite_and_count_all_companies(self):
        frame = pd.DataFrame(
            {
                "Net Debt": [100.0, 200.0, -100.0],
                "EBITDA": [100.0, -10.0, -5.0],
                "Revenue": [1000.0, 500.0, 500.0],
            }
        )
        result = _debt_capacity_stress(frame)
        self.assertTrue(pd.notna(result["score"]))
        self.assertEqual(result["observations"], 3)
        self.assertEqual(result["positive_ebitda_companies"], 1)
        self.assertEqual(result["impaired_companies"], 1)
        self.assertEqual(result["net_cash_companies"], 1)


if __name__ == "__main__":
    unittest.main()
