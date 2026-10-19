"""Offline regression tests for PPD institutional PE-capacity candidate."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loaders import pe_institutional_capacity_probe as p


def records() -> list[dict]:
    values = []
    for year in (2023, 2024):
        for i in range(1, 41):
            values.append({"fy": str(year), "ppd_id": str(i), "PlanName": f"Pension {i}",
                           "PETotal_Actl": str(0.12 if i <= (20 if year == 2023 else 30) else 0.08),
                           "PETotal_Trgt": "0.10"})
    return values


def payload(rows: list[dict], *, status="OK", count=None) -> bytes:
    return json.dumps([{"status": status, "q": "qvariables", "recordcount": len(rows) if count is None else count}, *rows]).encode()


class CapacityTests(unittest.TestCase):
    def test_requested_fields_and_years(self):
        url = p.query_url(2023, 2024)
        self.assertIn("PETotal_Actl", url)
        self.assertIn("PETotal_Trgt", url)
        self.assertIn("filterfystart=2023", url)
        self.assertIn("filtertierid=0", url)

    def test_query_range_rejection(self):
        with self.assertRaises(p.SourceRejected):
            p.query_url(2025, 2020)

    def test_valid_api_contract(self):
        self.assertEqual(len(p.decode_api(payload(records()))), 80)

    def test_refuses_api_error(self):
        with self.assertRaises(p.SourceRejected):
            p.decode_api(payload([{"Error": "No dataset"}], status="ERROR"))

    def test_refuses_truncation(self):
        with self.assertRaises(p.SourceRejected):
            p.decode_api(payload(records(), count=81))

    def test_refuses_missing_field(self):
        x = records()
        x[0].pop("PETotal_Trgt")
        with self.assertRaises(p.SourceRejected):
            p.decode_api(payload(x))

    def test_refuses_duplicate_plan_year(self):
        x = records()
        with self.assertRaises(p.SourceRejected):
            p.normalize(x + [x[0]], "https://publicplansdata.org/api/", start_year=2023, end_year=2024)

    def test_excludes_unpaired_missing_values(self):
        x = records()
        x[0]["PETotal_Actl"] = None
        y, diagnostics = p.normalize(x, "url", start_year=2023, end_year=2024)
        self.assertEqual(len(y), 79)
        self.assertEqual(diagnostics["missing_actual_or_target"], 1)

    def test_preserves_target_zero(self):
        x = records()
        x[0]["PETotal_Trgt"] = "0"
        y, _ = p.normalize(x, "url", start_year=2023, end_year=2024)
        self.assertEqual(y[0]["allocation_status"], "zero_target_positive_exposure")

    def test_rejects_out_of_range(self):
        x = records()
        x[0]["PETotal_Trgt"] = "1.25"
        with self.assertRaises(p.SourceRejected):
            p.normalize(x, "url", start_year=2023, end_year=2024)

    def test_classification_boundary(self):
        x = records()
        x[0]["PETotal_Actl"] = "0.105"
        y, _ = p.normalize(x, "url", start_year=2023, end_year=2024)
        self.assertEqual(y[0]["allocation_status"], "at")

    def test_balanced_panel_change(self):
        y, _ = p.normalize(records(), "url", start_year=2023, end_year=2024)
        annual = p.summarize(y, "url")
        p.validate_sample(y, annual)
        self.assertEqual(annual[0]["over_target_pct"], 50.0)
        self.assertEqual(annual[1]["over_target_pct"], 75.0)
        self.assertEqual(annual[1]["paired_plans"], 40)
        self.assertEqual(annual[1]["paired_change_pp"], 25.0)

    def test_pairing_avoids_sample_composition(self):
        x = [r for r in records() if not (r["fy"] == "2024" and int(r["ppd_id"]) > 30)]
        y, _ = p.normalize(x, "url", start_year=2023, end_year=2024)
        annual = p.summarize(y, "url")
        self.assertEqual(annual[1]["paired_plans"], 30)
        self.assertEqual(annual[1]["paired_prior_over_pct"], 66.67)
        self.assertEqual(annual[1]["paired_change_pp"], 33.33)

    def test_fractional_units_are_percentage_points(self):
        y, _ = p.normalize(records(), "url", start_year=2023, end_year=2024)
        self.assertEqual(y[0]["actual_pe_pct"], 12.0)
        self.assertEqual(y[0]["target_pe_pct"], 10.0)
        self.assertEqual(y[0]["gap_pp"], 2.0)
        self.assertEqual(y[0]["allocation_status"], "over")

    def test_zero_target_is_not_overallocation(self):
        x = records()
        x[0]["PETotal_Trgt"] = "0"
        x[0]["PETotal_Actl"] = "0"
        x[1]["PETotal_Trgt"] = "0"
        rows, _ = p.normalize(x, "url", start_year=2023, end_year=2024)
        annual = p.summarize(rows, "url")[0]
        self.assertEqual(annual["pe_targeted_plans"], 38)
        self.assertEqual(annual["zero_exposure_zero_target"], 1)
        self.assertEqual(annual["positive_exposure_zero_target"], 1)
        self.assertEqual(annual["over_target"], 18)
        self.assertEqual(annual["over_target_pct"], 47.37)

    def test_strictly_rejects_pct_points_in_fractional_input(self):
        x = records()
        x[0]["PETotal_Trgt"] = "10"
        with self.assertRaises(p.SourceRejected):
            p.normalize(x, "url", start_year=2023, end_year=2024)

    def test_shared_history_collapse_requires_three_consecutive_years(self):
        x = []
        for year in (2022, 2023, 2024):
            for i in range(1, 41):
                val = 0.1 + (0.02 if i in (1, 2) else -0.02)
                # Stable, matching sponsors + nonzero, precise three-year
                # trajectory; everyone else has distinct plan-name sponsor.
                name = f"Washington Plan {i}" if i in (1, 2) else f"Sponsor{i} Plan"
                x.append({"fy": str(year), "ppd_id": str(i), "PlanName": name,
                          "PETotal_Actl": str(val), "PETotal_Trgt": "0.10"})
        rows, _ = p.normalize(x, "url", start_year=2022, end_year=2024)
        annual = p.summarize(rows, "url")
        self.assertEqual(annual[0]["portfolio_proxy_collapsed_plans"], 0)
        self.assertEqual(annual[1]["portfolio_proxy_collapsed_plans"], 0)
        self.assertEqual(annual[2]["portfolio_proxy_collapsed_plans"], 1)
        self.assertEqual(annual[2]["portfolio_proxy_units"], 39)
        matches = [r for r in rows if r["fiscal_year"] == 2024 and r["ppd_id"] in (1, 2)]
        self.assertEqual(len({r["portfolio_unit_id"] for r in matches}), 1)
        self.assertEqual(annual[2]["paired_portfolio_units"], 39)
        # Deliberately not called a verified common pension investment pool.
        self.assertEqual(matches[0]["portfolio_basis"], "identical_three_year_exposure")

    def test_aggregation_is_idempotent(self):
        x = []
        for year in (2022, 2023, 2024):
            for i in range(1, 41):
                x.append({"fy": str(year), "ppd_id": str(i),
                          "PlanName": f"Washington Plan {i}" if i <= 2 else f"Agency{i} Plan",
                          "PETotal_Actl": "0.12", "PETotal_Trgt": "0.10"})
        rows, _ = p.normalize(x, "url", start_year=2022, end_year=2024)
        first = p.summarize(rows, "url")
        self.assertEqual(first, p.summarize(rows, "url"))

    def test_identical_values_different_sponsors_not_collapsed(self):
        x = []
        for year in (2022, 2023, 2024):
            for i in range(1, 41):
                x.append({"fy": str(year), "ppd_id": str(i),
                          "PlanName": f"Agency{i} Plan",
                          "PETotal_Actl": "0.12", "PETotal_Trgt": "0.10"})
        rows, _ = p.normalize(x, "url", start_year=2022, end_year=2024)
        annual = p.summarize(rows, "url")
        self.assertEqual(annual[2]["portfolio_proxy_collapsed_plans"], 0)

    def test_unverified_high_target_does_not_distort_breadth(self):
        x = records()
        x[0]["PETotal_Trgt"] = "1.0"
        rows, _ = p.normalize(x, "url", start_year=2023, end_year=2024)
        annual = p.summarize(rows, "url")[0]
        self.assertEqual(rows[0]["allocation_status"], "unverified_high_pe_target")
        self.assertEqual(annual["unverified_high_pe_target"], 1)
        self.assertEqual(annual["pe_targeted_plans"], 39)

    def test_incomplete_year_flag_is_not_an_economic_signal(self):
        x = []
        for year, count in ((2022, 40), (2023, 40), (2024, 40), (2025, 25)):
            for i in range(1, count + 1):
                x.append({"fy": str(year), "ppd_id": str(i), "PlanName": f"Sponsor{i} Plan",
                          "PETotal_Actl": "0.12", "PETotal_Trgt": "0.10"})
        rows, _ = p.normalize(x, "url", start_year=2022, end_year=2025)
        ann = p.summarize(rows, "url")
        self.assertEqual(ann[-2]["coverage_status"], "adequate")
        self.assertEqual(ann[-1]["coverage_status"], "incomplete")
        self.assertEqual(ann[-1]["reporting_coverage_ratio"], 0.625)
        self.assertEqual(ann[-1]["paired_plans"], 25)
        self.assertEqual(ann[-1]["paired_change_pp"], 0.0)
        self.assertEqual(ann[-1]["signal_eligible"], 0)
        self.assertEqual(ann[-2]["signal_eligible"], 1)

    def test_insufficient_history(self):
        y, _ = p.normalize(records()[:40], "url", start_year=2023, end_year=2024)
        with self.assertRaises(p.SourceRejected):
            p.validate_sample(y, p.summarize(y, "url"))

    def test_workflow_summary_guards_incomplete_year(self):
        text = (ROOT / ".github" / "workflows" / "pe_institutional_capacity_probe.yml").read_text()
        self.assertIn("row['signal_eligible']", text)
        self.assertIn("row['coverage_status']", text)
        self.assertIn("if eligible else '—'", text)

    def test_csv_column_schema(self):
        y, _ = p.normalize(records(), "url", start_year=2023, end_year=2024)
        content = p.csv_bytes(y, p.DETAIL_FIELDS).decode()
        self.assertTrue(content.startswith("fiscal_year,ppd_id,plan_name"))

    def test_candidate_writes_only_after_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with patch.object(p, "download", return_value=payload(records())):
                r = p.run(out_dir=out, start_year=2023, end_year=2024)
            self.assertEqual(r["matched_plan_years"], 80)
            self.assertEqual(len(list(out.glob("*.csv"))), 2)

    def test_failure_does_not_replace_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            out.mkdir(exist_ok=True)
            prior = out / "public_pension_pe_allocation_annual.csv"
            prior.write_text("prior validated output")
            with patch.object(p, "download", return_value=payload(records(), status="ERROR")):
                with self.assertRaises(p.SourceRejected):
                    p.run(out_dir=out, start_year=2023, end_year=2024)
            self.assertEqual(prior.read_text(), "prior validated output")


if __name__ == "__main__":
    unittest.main()
