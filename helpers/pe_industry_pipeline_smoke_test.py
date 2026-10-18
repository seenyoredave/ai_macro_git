"""Offline checks for production PE source parsing, history and fail-closed refresh."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from loaders import pe_industry_pipeline as pipeline
from loaders.pe_industry_parsers import (SourceFormatError, parse_acg_quarter,
                                         parse_kpmg_h1, parse_sec_tables)


def workbook(*, wrong_row=False) -> bytes:
    book = openpyxl.Workbook()
    book.remove(book.active)
    metrics = {"Tab.1.1": [25124, 25107, 25136, 25158, 27682],
               "Tab.2.1": [7952, 7942, 7950, 7958, 9334],
               "Tab.2.3": [7289, 7279, 7286, 7294, 8523]}
    for name, numbers in metrics.items():
        sheet = book.create_sheet(name)
        sheet.append(["Table", name]); sheet.append(["Fund Type", "2024Q4", "2025Q1", "2025Q2", "2025Q3", "2025Q4"])
        sheet.append(["Hedge Fund", 500, 500, 500, 500, 500])
        sheet.append(["Private Equity Fund" if not wrong_row else "Venture Capital Fund", *numbers])
    b = BytesIO(); book.save(b); book.close()
    return b.getvalue()


KPMG_HTML = """<html><body><h1>Global private equity PE market shows resilience with over $1 trillion</h1>
<p>27 July 2026</p><p>The global PE market showed resilience in Q2’26, bringing the
mid-year total of PE investment to $1 trillion across 9,294 deals.</p>
<p>Global PE exit flow was $570.0 billion across 1,315 exits.</p>
<p>At mid-year, global fundraising was at $261.8 billion across 315 funds.</p></body></html>""".encode()
ACG_Q1 = """<html><body><h1>GF Data Reports Show Stronger Financing Markets Fueled M&amp;A Gains in Q1</h1>
<p>CHICAGO – May 19, 2026 – GF Data has released its Q1 2026 M&amp;A and Leverage Reports.</p>
<p>GF Data’s contributing private equity firms reported 80 completed transactions during the first quarter
at an average valuation of 7.3x trailing 12-month (TTM) adjusted EBITDA.</p></body></html>""".encode()
ACG_Q2 = """<html><body><h1>GF Data Reports Show Steady Middle-Market Deal Flow in Q2</h1>
<p>CHICAGO – August 27, 2026 – GF Data has released its Q2 2026 M&amp;A and Leverage Reports.</p>
<p>GF Data’s contributing private equity firms reported 85 completed transactions in the second quarter.</p>
<p>Average purchase price multiples declined in the second quarter to 7.0x trailing 12-month (TTM) adjusted EBITDA,
down from 7.3x in Q1. Average total debt declined to 2.9x TTM EBITDA from 3.4x in Q1.</p></body></html>""".encode()


class PEIndustryRefreshTests(unittest.TestCase):
    def test_sec_tables_select_exact_fund_population(self):
        rows = parse_sec_tables(workbook(), source_url="https://www.sec.gov/valid.xlsx", published_on="")
        frame = pipeline.validate_observations(rows, "sec")
        latest = frame.loc[frame.period.eq("2025Q4")].set_index("metric").value
        self.assertEqual(latest.to_dict(), {"fund_count": 27682.0, "gross_assets_usd_bn": 9334.0, "net_assets_usd_bn": 8523.0})
        self.assertEqual(len(frame), 15)
        self.assertEqual(set(frame.period_end), {"2024-12-31", "2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"})
        self.assertTrue(frame.published_on.eq("").all())

    def test_sec_rejects_wrong_population(self):
        with self.assertRaisesRegex(SourceFormatError, "Expected one PE row"):
            parse_sec_tables(workbook(wrong_row=True), source_url="https://www.sec.gov/x.xlsx", published_on="")

    def test_sec_rejects_future_or_missing_and_mismatched_tables(self):
        data = parse_sec_tables(workbook(), source_url="https://www.sec.gov/valid.xlsx", published_on="")
        data[0]["period_end"] = "2099-12-31"
        with self.assertRaisesRegex(SourceFormatError, "future"):
            pipeline.validate_observations(data, "sec")
        data = parse_sec_tables(workbook(), source_url="https://www.sec.gov/valid.xlsx", published_on="")
        data.pop()
        with self.assertRaisesRegex(SourceFormatError, "Incomplete"):
            pipeline.validate_observations(data, "sec")

    def test_kpmg_h1_exact_period_and_definition(self):
        rows = parse_kpmg_h1(KPMG_HTML, source_url=pipeline.KPMG_SEEDS[0]); self.assertEqual(len(rows), 3)
        values = {r["metric"]: (r["value"], r["sample_count"]) for r in rows}
        self.assertEqual(values, {"deal_value": (1000.0, 9294), "exit_value": (570.0, 1315), "fundraising": (261.8, 315)})
        self.assertTrue(all(r["period"] == "H1 2026" for r in rows))
        pipeline.validate_observations(rows, "kpmg")

    def test_kpmg_rejects_h1_when_only_quarterly(self):
        bad = KPMG_HTML.replace(b"mid-year total", b"Q2 total").replace(b"At mid-year", b"In Q2")
        with self.assertRaises(SourceFormatError):
            parse_kpmg_h1(bad, source_url=pipeline.KPMG_SEEDS[0])

    def test_kpmg_does_not_substitute_us_for_global(self):
        bad = KPMG_HTML.replace(b"Global PE exit flow", b"US PE exit flow")
        with self.assertRaises(SourceFormatError):
            parse_kpmg_h1(bad, source_url=pipeline.KPMG_SEEDS[0])

    def test_acg_q1_q2_no_prior_quarter_leakage(self):
        first = parse_acg_quarter(ACG_Q1, source_url=pipeline.ACG_SEEDS[1])[0]
        second = parse_acg_quarter(ACG_Q2, source_url=pipeline.ACG_SEEDS[0])[0]
        self.assertEqual([(o["period"], o["value"], o["sample_count"]) for o in (first, second)],
                         [("2026Q1", 7.3, 80), ("2026Q2", 7.0, 85)])
        pipeline.validate_observations([first, second], "acg")

    def test_acg_rejects_comparative_multiple_instead_of_observed(self):
        bad = ACG_Q2.replace(b"to 7.0x trailing", b"to an undisclosed figure from 7.0x trailing")
        with self.assertRaises(SourceFormatError):
            parse_acg_quarter(bad, source_url=pipeline.ACG_SEEDS[0])

    def test_discovery_does_not_accept_unrelated_links(self):
        sec_index = b'<html><a href="/files/investment/private-funds-statistics-2025-q4-supporting-data.xlsx">Private Fund Statistics Supporting Data (XLSX)</a></html>'
        self.assertIn("2025-q4", pipeline.discover_sec(sec_index))
        acg_index = b'<html><a href="/news-trends/news/gf-data-reports-test">GF Data Reports Q3</a><a href="/news-trends/news/irrelevant">Tech</a></html>'
        self.assertEqual(len(pipeline.discover_press(acg_index, "acg")), 1)

    def test_historical_records_not_dropped_and_regression_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"pe_industry_acg.csv"
            a = pipeline.validate_observations([parse_acg_quarter(ACG_Q1, source_url=pipeline.ACG_SEEDS[1])[0]], "acg")
            b = pipeline.validate_observations([parse_acg_quarter(ACG_Q2, source_url=pipeline.ACG_SEEDS[0])[0]], "acg")
            pipeline.persist_source("acg", a, path)
            pipeline.persist_source("acg", b, path)
            self.assertEqual(len(pd.read_csv(path)), 2)
            before = path.read_bytes()
            with self.assertRaisesRegex(SourceFormatError, "older"):
                pipeline.persist_source("acg", a, path)
            self.assertEqual(before, path.read_bytes())

    def test_source_failure_retains_prior_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"pe_industry_acg.csv"
            a = pipeline.validate_observations([parse_acg_quarter(ACG_Q1, source_url=pipeline.ACG_SEEDS[1])[0]], "acg")
            pipeline.persist_source("acg", a, path)
            before = path.read_bytes()
            with patch.object(pipeline, "source_candidate", side_effect=SourceFormatError("bad response")):
                result = pipeline.run(out_dir=Path(tmp), selected=("acg",))
            self.assertEqual(result[0]["status"], "retained_on_failure")
            self.assertEqual(path.read_bytes(), before)

    def test_published_urls_are_strictly_allowlisted(self):
        with self.assertRaisesRegex(SourceFormatError, "Invalid source URL"):
            frame = parse_kpmg_h1(KPMG_HTML, source_url="https://fake.kpmg.example/report")
            pipeline.validate_observations(frame, "kpmg")

    def test_rejected_release_does_not_overwrite_prior(self):
        with tempfile.TemporaryDirectory() as tmp:
            latest = pipeline.validate_observations(parse_kpmg_h1(KPMG_HTML, source_url=pipeline.KPMG_SEEDS[0]), "kpmg")
            path=Path(tmp)/"pe_industry_kpmg.csv"
            pipeline.persist_source("kpmg",latest,path)
            bad=latest.copy();bad.loc[bad.metric.eq("exit_value"),"value"]=-1
            before=path.read_bytes()
            with self.assertRaisesRegex(SourceFormatError,"Invalid financial"):
                pipeline.validate_observations(bad.to_dict("records"), "kpmg")
            self.assertEqual(path.read_bytes(),before)


if __name__ == "__main__":
    unittest.main()
