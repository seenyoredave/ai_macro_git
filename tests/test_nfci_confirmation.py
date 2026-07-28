import unittest

import pandas as pd

from analytics.financial_conditions import (
    nfci_condition,
    nfci_direction,
    nfci_snapshot,
    nfci_summary,
)


class NFCIConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.history = pd.DataFrame({
            "Date": ["2026-01-01", "2026-04-01", "2026-07-01"],
            "Value": [-0.80, -0.70, -0.50],
        })
        self.fred_data = {
            "Financial Conditions NFCI": {
                "value": -0.45,
                "date": "2026-07-10",
                "source": "FRED Live",
            }
        }

    def test_snapshot_uses_current_value_and_three_month_direction(self):
        snapshot = nfci_snapshot(self.fred_data, self.history)
        self.assertAlmostEqual(snapshot["value"], -0.45)
        self.assertAlmostEqual(snapshot["three_month_change"], 0.25)
        self.assertEqual(snapshot["as_of"], "2026-07-10")

    def test_interpretation_labels(self):
        self.assertEqual(nfci_condition(-0.45), "Looser Than Average")
        self.assertEqual(nfci_direction(0.25), "Tightening ↑")
        self.assertIn("tightened", nfci_summary(-0.45, 0.25))

    def test_history_fallback(self):
        snapshot = nfci_snapshot({}, self.history)
        self.assertAlmostEqual(snapshot["value"], -0.50)
        self.assertEqual(snapshot["as_of"], "2026-07-01")


if __name__ == "__main__":
    unittest.main()


def test_nfci_snapshot_preserves_anfci_comparator_history():
    history = pd.DataFrame({
        "Date": ["2026-01-01", "2026-04-01", "2026-07-01"],
        "Value": [-0.80, -0.70, -0.50],
        "ANFCI": [-0.40, -0.35, -0.20],
    })
    snapshot = nfci_snapshot({}, history)
    assert "ANFCI" in snapshot["history"].columns
    assert snapshot["history"]["ANFCI"].iloc[-1] == -0.20
    assert snapshot["anfci_value"] == -0.20


def test_financial_conditions_chart_keeps_nfci_primary_and_anfci_dashed():
    from research_overlay.visuals import financial_conditions_history

    history = pd.DataFrame({
        "Date": ["2026-01-01", "2026-04-01", "2026-07-01"],
        "Value": [-0.80, -0.70, -0.50],
        "ANFCI": [-0.40, -0.35, -0.20],
    })
    fig = financial_conditions_history(history)
    assert [trace.name for trace in fig.data] == ["NFCI", "ANFCI"]
    assert fig.data[0].line.width > fig.data[1].line.width
    assert fig.data[0].line.dash is None
    assert fig.data[1].line.dash == "dash"
    assert fig.layout.showlegend is True
