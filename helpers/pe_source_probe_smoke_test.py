"""Offline parser and discovery regression tests for the PE source probe."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from helpers import pe_source_probe as probe


def html(text):
    return ("<!doctype html><html><body>" + text + "</body></html>").encode()


def sec_xlsx():
    book = openpyxl.Workbook()
    for i in range(3):
        sheet = book.active if i == 0 else book.create_sheet(f"Data {i}")
        sheet.append(["Fund Type", "2024Q4", "2025Q1"])
        sheet.append(["Private Equity Fund", 1234 + i, 1400 + i])
    output = BytesIO()
    book.save(output)
    return output.getvalue()


class ProbeTests(unittest.TestCase):
    def test_sec_workbook_has_real_pe_numeric_data(self):
        result = probe.parse_sec_workbook(sec_xlsx())
        self.assertEqual(result["sheets"], 3)
        self.assertEqual(result["historical_periods_detected"], ["2024Q4", "2025Q1"])
        self.assertGreater(result["quantitative_cells"], 4)

    def test_sec_rejects_pdf_or_html_disguised_as_xlsx(self):
        with self.assertRaises(probe.ProbeError):
            probe.parse_sec_workbook(b"<html>sorry</html>")

    def test_kpmg_release_requires_several_measures(self):
        sample = html("""<h1>Global private equity Pulse</h1>
        Global PE investment reached $506 billion across 4,000 deals, while
        exits totaled $210 billion and fundraising was $130 billion.
        The prior year's PE activity was $465 billion over 3,600 deals.
        The exit and fundraising market is notable for several reasons.
        """)
        self.assertGreaterEqual(probe.parse_kpmg_release(sample)["currency_amounts"], 4)
        with self.assertRaises(probe.ProbeError):
            probe.parse_kpmg_release(html("private equity " * 100))

    def test_acg_release_extracts_multiples_and_counts(self):
        sample = html("GF Data reported 85 completed transactions in Q2 2026. " +
                      "The average purchase price was 7.0x TTM adjusted EBITDA, vs 7.3x in Q1. " * 4)
        self.assertIn("7.0x", probe.parse_acg_release(sample)["multiples_detected"])

    def test_calpers_has_active_fund_table_and_as_of_date(self):
        sample = "<p>The table below reflects the performance of all active PE investments as of March 31, 2026.</p>"
        header = "<tr><th>Fund</th><th>Vintage Year</th><th>Cash In</th><th>Cash Out</th><th>Cash Out &amp; Remaining Value</th></tr>"
        rows = "".join(f"<tr><td>Fund {i}</td><td>2020</td><td>100</td><td>20</td><td>130</td></tr>" for i in range(102))
        result = probe.parse_calpers(html("Private Equity " + sample + "<table>" + header + rows + "</table>"))
        self.assertEqual(result["fund_rows"], 102)
        self.assertEqual(result["as_of"], "2026-03-31")

    def test_wsib_date_discovery_uses_latest_valid_past_pdf(self):
        sample = html('Reports ' * 50 + '<a href="/docs/reports/quarterly/ir033125.pdf">March 2025</a>' +
                      '<a href="/docs/reports/quarterly/ir033126.pdf">March 2026</a>' * 6)
        url, date = probe.parse_wsib_index(sample)
        self.assertTrue(url.endswith("ir033126.pdf"))
        self.assertEqual(date, "2026-03-31")

    def test_discovery_rejects_off_domain_links(self):
        source = html('''Press releases <a href="https://example.org/secret/private-equity-2026.html">Private equity</a>
                    <a href="/xx/en/media/press-releases/2026/07/private-equity.html">Private Equity market</a>''' * 4)
        urls = probe.discover_press_links(source, probe.KPMG_INDEX, ("kpmg.com",), "kpmg")
        self.assertEqual(len(urls), 1)
        self.assertTrue(urls[0].startswith("https://kpmg.com/"))

    def test_oregon_chart_is_not_claimed_as_numeric_data(self):
        result = probe.report_row("oregon", "LP cash flow", [probe.OREGON_URL],
                                  observation={"numeric_series": False, "pages": 20})
        self.assertEqual(result["status"], "retrievable_only")
        self.assertFalse(result["structured_observations"])

    def test_sec_pinned_fallback_is_not_automatic_discovery(self):
        landing = html("Private Fund Statistics " * 50)
        def fake_fetch(url, hosts, **kwargs):
            return ((landing if url == probe.SEC_INDEX else sec_xlsx()), {"url":url,"bytes":500,"http_status":200})
        with patch.object(probe, "fetch", side_effect=fake_fetch):
            row = probe.probe_sec()
        self.assertEqual(row["status"], "partial")
        self.assertFalse(row["index_discovery"])
        self.assertTrue(row["structured_observations"])

    def test_source_errors_are_reported_without_stopping_other_sources(self):
        with patch.dict(probe.PROBES, {"sec": lambda: (_ for _ in ()).throw(probe.ProbeError("blocked")),
                                      "calpers": lambda: probe.report_row("calpers", "cash", ["https://example.org"], observation={"fund_rows":200}, structured=True)}):
            result = probe.run(["sec", "calpers"])
        self.assertEqual(result["summary"]["sources_tested"], 2)
        self.assertEqual(result["summary"]["validated_content_without_error"], 1)
        self.assertEqual(result["results"][0]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
