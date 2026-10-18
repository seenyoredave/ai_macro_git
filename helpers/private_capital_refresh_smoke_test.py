"""Test fund ingestion safely; --live tests both sites using temporary files only."""

from __future__ import annotations

from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics import private_capital as analytics
from loaders import private_capital_loader as loader


def fixture(as_of="2026-03-31"):
    rows = []
    for manager, prefix in (("Francisco Partners", "Francisco Partners"),
                            ("Thoma Bravo", "Thoma Bravo"),
                            ("Silver Lake", "Silver Lake Partners"),
                            ("Insight Partners", "Insight Partners")):
        for index in range(3):
            rows.append({"Manager": manager, "Fund": f"{prefix} Test {index}",
                         "Vintage": 2015 + index, "Exposure Tier": "Technology-focused manager",
                         "Capital Committed": 100.0, "Paid In Capital": 80.0,
                         "Distributions": 40.0, "NAV": 60.0, "Net IRR": 12.5,
                         "Source As Of": as_of})
    return pd.DataFrame(rows).sort_values(["Vintage", "Manager", "Fund"], ascending=[False, True, True]).reset_index(drop=True)


def calpers_html():
    headers = ("Fund", "Vintage Year", "Capital Committed", "Cash In", "Cash Out",
               "Cash Out &amp; Remaining Value", "Net IRR", "Investment Multiple")
    rows = []
    for index, row in fixture().iterrows():
        values = [row["Fund"], row["Vintage"], "$100", "$80", "$40", "$100",
                  "N/M" if index == 0 else "12.5%<sup>1</sup>", "1.25x<sup>1</sup>"]
        rows.append("<tr>" + "".join(f"<td>{value}</td>" for value in values) + "</tr>")
    return (
        "<p>As of December 31, 2024, the overall IRR is 10%.</p>"
        "<p>The table below reflects the performance of all active PE partnership investments as of March 31, 2026.</p>"
        "<table><thead><tr>" + "".join(f"<th>{value}</th>" for value in headers)
        + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def temporary_paths(stack, directory):
    root = Path(directory)
    names = {
        "DATA_PATH": root / "fund_performance.csv", "METADATA_PATH": root / "metadata.json",
        "WSIB_DATA_PATH": root / "wsib.csv", "WSIB_METADATA_PATH": root / "wsib.json",
        "CALPERS_DATA_PATH": root / "calpers.csv", "CALPERS_METADATA_PATH": root / "calpers.json",
    }
    for name, value in names.items():
        stack.enter_context(patch.object(analytics, name, value))
    for name, value in {"CSV_PATH": names["WSIB_DATA_PATH"], "METADATA_PATH": names["WSIB_METADATA_PATH"],
                        "CALPERS_CSV_PATH": names["CALPERS_DATA_PATH"], "CALPERS_METADATA_PATH": names["CALPERS_METADATA_PATH"]}.items():
        stack.enter_context(patch.object(loader, name, value))
    stack.enter_context(patch.object(loader, "repository_writes_enabled", return_value=True))
    return names


class PrivateCapitalTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.paths = temporary_paths(self.stack, directory)
        fixture("2025-06-30").to_csv(self.paths["DATA_PATH"], index=False)
        self.paths["METADATA_PATH"].write_text(json.dumps({"source_as_of": "2025-06-30", "source_short": "CalSTRS"}))

    def save(self, provider="WSIB", as_of="2026-03-31"):
        data = loader.CSV_PATH if provider == "WSIB" else loader.CALPERS_CSV_PATH
        meta = loader.METADATA_PATH if provider == "WSIB" else loader.CALPERS_METADATA_PATH
        metadata = loader._metadata(source_short=provider, source_url="https://example.test/report", as_of=pd.Timestamp(as_of).date())
        return loader._save_snapshot(fixture(as_of), metadata, data_path=data, metadata_path=meta)

    def test_html_uses_table_date_and_ignores_irr_footnotes(self):
        as_of, frame = loader.parse_calpers(calpers_html())
        self.assertEqual(str(as_of), "2026-03-31")
        self.assertEqual(len(frame), 12)
        self.assertTrue(frame["NAV"].eq(60).all())
        self.assertEqual(frame["Net IRR"].isna().sum(), 1)
        self.assertTrue(frame["Net IRR"].dropna().eq(12.5).all())

    def test_missing_amounts_and_unknown_date_are_rejected(self):
        with self.assertRaises(ValueError):
            loader.parse_calpers(calpers_html().replace("$80", "N/A", 1))
        with self.assertRaises(ValueError):
            loader.parse_calpers(calpers_html().replace("table below reflects", "unidentified report"))

    def test_newest_source_is_one_cohort_and_invalid_source_falls_back(self):
        self.save()
        self.save("CalPERS", "2026-06-30")
        result = analytics.build_private_capital_realization()
        self.assertEqual(result["metadata"]["source_short"], "CalPERS")
        self.assertEqual(result["all_metrics"]["fund_count"], 12)
        self.paths["CALPERS_DATA_PATH"].write_text("broken\nfile\n")
        self.assertEqual(analytics.load_private_capital_metadata()["source_short"], "WSIB")

    def test_newer_local_records_are_preserved_and_ties_are_stable(self):
        fixture("2026-06-30").to_csv(self.paths["DATA_PATH"], index=False)
        self.save()
        self.assertEqual(analytics.load_private_capital_metadata()["source_short"], "CalSTRS")
        self.save("WSIB", "2026-09-30")
        self.save("CalPERS", "2026-09-30")
        self.assertEqual(analytics.load_private_capital_metadata()["source_short"], "WSIB")

    def test_provider_regression_cannot_overwrite_good_records(self):
        self.save("WSIB", "2026-06-30")
        before = loader.CSV_PATH.read_bytes()
        with self.assertRaises(ValueError):
            self.save("WSIB", "2026-03-31")
        self.assertEqual(loader.CSV_PATH.read_bytes(), before)

    def test_optional_403_is_reported_without_failing_wsib(self):
        blocked = HTTPError(loader.CALPERS_URL, 403, "Forbidden", None, None)
        with patch.object(loader, "_refresh_wsib", side_effect=self.save), patch.object(loader, "_refresh_calpers", side_effect=blocked):
            report = loader.refresh_private_capital(force_refresh=True, allow_live=True)
        self.assertEqual(report["source_mode"], "live_refresh")
        self.assertEqual(report["source"], "WSIB")
        self.assertEqual(report["providers"]["CalPERS"]["http_status"], 403)
        self.assertNotIn("error", report)
        self.assertTrue(report["provider_warnings"])

    def test_both_provider_failures_preserve_files(self):
        self.save()
        before = loader.CSV_PATH.read_bytes()
        with patch.object(loader, "_refresh_wsib", side_effect=ValueError("PDF layout changed")), patch.object(loader, "_refresh_calpers", side_effect=ValueError("No table")):
            report = loader.refresh_private_capital(force_refresh=True, allow_live=True)
        self.assertEqual(report["source_mode"], "retained_fallback")
        self.assertEqual(loader.CSV_PATH.read_bytes(), before)
        self.assertEqual(report["source"], "WSIB")

    def test_reader_and_unauthorized_runtime_do_not_fetch(self):
        with patch.object(loader, "_fetch", side_effect=AssertionError("Reader fetched")) as fetch:
            loader.refresh_private_capital()
            with patch.object(loader, "repository_writes_enabled", return_value=False):
                loader.refresh_private_capital(force_refresh=True, allow_live=True)
        fetch.assert_not_called()

    def test_unchanged_data_has_stable_signature(self):
        self.save()
        signature = loader._retained_status()["snapshot_signature"]
        self.assertEqual(self.save()["status"], "checked_current")
        self.assertEqual(signature, loader._retained_status()["snapshot_signature"])

    def test_same_date_revisions_change_the_snapshot_signature(self):
        self.save()
        before = loader._retained_status()["snapshot_signature"]
        revised = fixture()
        revised.loc[0, "NAV"] += 5
        metadata = loader._metadata(source_short="WSIB", source_url="https://example.test/report", as_of=pd.Timestamp("2026-03-31").date())
        result = loader._save_snapshot(revised, metadata, data_path=loader.CSV_PATH, metadata_path=loader.METADATA_PATH)
        self.assertEqual(result["status"], "updated")
        self.assertNotEqual(before, loader._retained_status()["snapshot_signature"])


def live_check():
    with ExitStack() as stack:
        directory = stack.enter_context(tempfile.TemporaryDirectory())
        temporary_paths(stack, directory)
        report = loader.refresh_private_capital(force_refresh=True, allow_live=True)
        print(json.dumps(report, indent=2))
        if report["source_mode"] == "retained_fallback" or not report["rows"]:
            raise SystemExit("Live source check failed; no project data files were changed.")


if __name__ == "__main__":
    live = "--live" in sys.argv
    program = unittest.main(argv=[sys.argv[0]], exit=False)
    if not program.result.wasSuccessful():
        raise SystemExit(1)
    if live:
        live_check()
