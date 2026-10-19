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
                           "PETotal_Actl": str(12 if i <= (20 if year == 2023 else 30) else 8),
                           "PETotal_Trgt": "10"})
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
        self.assertEqual(y[0]["allocation_status"], "over")

    def test_rejects_out_of_range(self):
        x = records()
        x[0]["PETotal_Trgt"] = "125"
        with self.assertRaises(p.SourceRejected):
            p.normalize(x, "url", start_year=2023, end_year=2024)

    def test_classification_boundary(self):
        x = records()
        x[0]["PETotal_Actl"] = "10.5"
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

    def test_insufficient_history(self):
        y, _ = p.normalize(records()[:40], "url", start_year=2023, end_year=2024)
        with self.assertRaises(p.SourceRejected):
            p.validate_sample(y, p.summarize(y, "url"))

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
