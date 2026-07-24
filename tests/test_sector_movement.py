import unittest

import pandas as pd

from analytics.sector_assessment import _movement_from_history


class SectorMovementTests(unittest.TestCase):
    def test_opposing_deltas_do_not_cancel(self):
        history = pd.DataFrame(
            {
                "Sector": ["TEST", "TEST"],
                "Sector Score": [40.0, 60.0],
                "Pressure": [60.0, 40.0],
                "_assessment_date": pd.to_datetime(["2026-01-01", "2026-02-01"]),
            }
        )
        result = _movement_from_history(history, lookback=10, source="test")
        self.assertAlmostEqual(result.iloc[0]["Sector Movement"], 28.284271247, places=6)
        self.assertGreaterEqual(result.iloc[0]["Sector Movement"], 0)


if __name__ == "__main__":
    unittest.main()
