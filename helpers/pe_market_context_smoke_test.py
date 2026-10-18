"""Regression checks for retained private-equity industry data and its charts."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.pe_market_context import (build_pe_market_context, load_pe_market_context,
                                          validate_market_context)
from rendering.charts_finance import pe_buyout_valuation_chart, pe_global_capital_flow_chart


class PrivateEquityIndustryTests(unittest.TestCase):
    def setUp(self):
        self.context = build_pe_market_context()
        self.frame = self.context["observations"]

    def test_reference_snapshot(self):
        self.assertEqual(len(self.frame), 9)
        flows = self.context["flows"]
        self.assertEqual(set(flows), {"deal_value", "exit_value", "fundraising"})
        self.assertEqual(flows["deal_value"]["value"], 1000.0)
        self.assertEqual(flows["deal_value"]["count"], 9294)
        self.assertEqual(flows["exit_value"]["value"], 570.0)
        self.assertEqual(flows["fundraising"]["value"], 261.8)
        self.assertEqual(self.context["valuations"]["buyout_ev_ebitda"]["value"], 12.5)

    def test_scope_and_date_separation(self):
        self.assertEqual({r["geography"] for r in self.context["flows"].values()}, {"Global"})
        self.assertEqual({r["period"] for r in self.context["flows"].values()}, {"H1 2026"})
        self.assertEqual({r["geography"] for r in self.context["valuations"].values()}, {"United States"})
        self.assertEqual({r["period"] for r in self.context["valuations"].values()}, {"2025"})

    def test_charts_present_actual_values(self):
        flow_fig = pe_global_capital_flow_chart(self.context["flows"], self.context["previous_flows"])
        self.assertEqual([trace.name for trace in flow_fig.data], ["H1 2025", "H1 2026"])
        self.assertEqual(list(flow_fig.data[0].x), [869.0, 501.9, 224.9])
        self.assertEqual(list(flow_fig.data[1].x), [1000.0, 570.0, 261.8])
        self.assertEqual(len(flow_fig.data), 2)
        val_fig = pe_buyout_valuation_chart(self.context["valuations"])
        self.assertEqual(list(val_fig.data[0].x), [10.8, 12.5, 16.0])

    def test_h1_year_over_year_value_comparison(self):
        self.assertEqual({r["period"] for r in self.context["previous_flows"].values()}, {"H1 2025"})
        yoy = self.context["flow_yoy_pct"]
        self.assertAlmostEqual(yoy["deal_value"], 15.074798619, places=6)
        self.assertAlmostEqual(yoy["exit_value"], 13.568439928, places=6)
        self.assertAlmostEqual(yoy["fundraising"], 16.407292130, places=6)
        # 2026 deal value is rounded ($1T), so its YoY change is approximate.
        self.assertEqual(self.context["flows"]["deal_value"]["precision"], "rounded")

    def test_prior_exits_have_no_invented_count(self):
        self.assertTrue(pd.isna(self.context["previous_flows"]["exit_value"]["count"]))
        self.assertEqual(int(self.context["flows"]["exit_value"]["count"]), 1315)

    def test_mismatched_prior_period_disables_comparison(self):
        altered = self.frame.copy()
        row = altered["metric"].eq("exit_value") & altered["period"].eq("H1 2025")
        altered.loc[row, "period_start"] = pd.Timestamp("2025-02-01")
        result = build_pe_market_context_from_frame(altered)
        self.assertEqual(result["flows"]["deal_value"]["period"], "H1 2026")
        self.assertFalse(result["previous_flows"])
        self.assertFalse(result["flow_yoy_pct"])

    def test_missing_source_does_not_invent_data(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(load_pe_market_context(Path(directory) / "absent.csv").empty)
            self.assertFalse(build_pe_market_context(Path(directory) / "absent.csv")["flows"])

    def test_reject_duplicate_and_negative_records(self):
        with self.assertRaisesRegex(ValueError, "duplicated"):
            validate_market_context(pd.concat([self.frame, self.frame.iloc[[0]]], ignore_index=True))
        altered = self.frame.copy()
        altered.loc[0, "value"] = -1
        with self.assertRaisesRegex(ValueError, "positive"):
            validate_market_context(altered)

    def test_reject_mislabeled_scope(self):
        altered = self.frame.copy()
        altered.loc[altered["metric"].eq("exit_value"), "geography"] = "United States"
        with self.assertRaisesRegex(ValueError, "geography"):
            validate_market_context(altered)

    def test_reject_wrong_units_or_missing_count(self):
        altered = self.frame.copy()
        altered.loc[altered["metric"].eq("deal_value"), "unit"] = "EV/EBITDA multiple"
        with self.assertRaisesRegex(ValueError, "units"):
            validate_market_context(altered)
        altered = self.frame.copy()
        altered.loc[altered["metric"].eq("deal_value"), "count"] = None
        with self.assertRaisesRegex(ValueError, "count"):
            validate_market_context(altered)

    def test_no_composite_as_of_from_mixed_periods(self):
        altered = self.frame.copy()
        altered.loc[altered["metric"].eq("deal_value") & altered["period"].eq("H1 2026"), "period_start"] = pd.Timestamp("2026-02-01")
        result = build_pe_market_context_from_frame(altered)
        self.assertEqual(result["flows"]["deal_value"]["period"], "H1 2025")
        self.assertFalse(result["previous_flows"])
        self.assertFalse(result["flow_yoy_pct"])


def build_pe_market_context_from_frame(frame):
    """Write an owner-edited candidate snapshot to exercise the real loader."""
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "candidate.csv"
        frame.to_csv(path, index=False, date_format="%Y-%m-%d")
        return build_pe_market_context(path)


if __name__ == "__main__":
    unittest.main()
