"""Offline checks for production PE source parsing, history and fail-closed refresh."""

from __future__ import annotations

from io import BytesIO
from urllib.error import HTTPError
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
    metrics = {"Tab.1.1": [21000, 23000, 25124, 25107, 25136, 25158, 27682],
               "Tab.2.1": [6500, 7100, 7952, 7942, 7950, 7958, 9334],
               "Tab.2.3": [6000, 6590, 7289, 7279, 7286, 7294, 8523]}
    for name, numbers in metrics.items():
        sheet = book.create_sheet(name)
        sheet.append(["Table", name]); sheet.append(["Fund Type", "2022Q4", "2023Q4", "2024Q4", "2025Q1", "2025Q2", "2025Q3", "2025Q4"])
        sheet.append(["Hedge Fund", *([500] * 7)])
        sheet.append(["Private Equity Fund" if not wrong_row else "Venture Capital Fund", *numbers])
    b = BytesIO(); book.save(b); book.close()
    return b.getvalue()


KPMG_HTML = """<html><body><h1>Global private equity PE market shows resilience with over $1 trillion</h1>
<p>27 July 2026</p><p>The global PE market showed resilience in Q2’26, bringing the
mid-year total of PE investment to $1 trillion across 9,294 deals.</p>
<p>Global PE exit flow was $570.0 billion across 1,315 exits.</p>
<p>At mid-year, global fundraising was at $261.8 billion across 315 funds.</p></body></html>""".encode()
KPMG_2025 = """<html><body><h1>Global PE Investment Slows Sharply Amid Rising Geopolitical and Trade Uncertainty</h1>
<p>Global PE investment totals $363.7 billion across 3,769 deals during Q2’25</p>
<p>24 July 2025 – Global private equity investment declined from $505.3 billion in Q1’25 to $363.7 billion in Q2’25.</p>
<h2>Q2’25 — Key Highlights</h2>
<p>Global PE investment fell from $505.3 billion across 4,527 deals in Q1’25 to $363.7 billion across 3,769 deals in Q2’25.</p>
<p>Global PE fundraising was $225 billion across 248 funds at the end of Q2’25.</p>
<p>The PE exit market continues to be challenging and a separate comparable H1 global value was not stated here.</p>
</body></html>""".encode()
ACG_2025_Q2 = """<html><body><h1>GF Data Releases Q2 2025 M&A and Leverage Reports</h1>
<p>Chicago, IL – August 22, 2025 — GF Data released its M&A and Leverage Reports, covering transactions completed through June 30, 2025.</p>
<p>In the second quarter, GF Data’s contributing private equity firms reporting 81 completed deals—an increase over 61 in the first quarter.</p>
<p>In terms of valuation, average purchase price multiples fell sharply in Q2 to 6.8x trailing 12-month adjusted EBITDA, down from 7.6x in Q1.</p>
<p>Private equity-sponsored M&A in the $10 million–$500 million enterprise value range.</p></body></html>""".encode()
ACG_2025_Q3 = """<html><body><h1>GF Data Releases Q3 2025 M&A and Leverage Reports</h1>
<p>Chicago, IL – November 18, 2025 — GF Data has released its M&A and Leverage Reports covering PE transactions completed through September 30, 2025.</p>
<p>GF Data’s contributing private equity firms reported 66 completed transactions in Q3—down from 83 deals in the second quarter.</p>
<p>Despite lower volume, average purchase price multiples rebounded to 7.5x trailing 12-month adjusted EBITDA, up from 6.9x in the second quarter.</p>
<p>Private equity-sponsored transactions in the $10 million–$500 million enterprise value range.</p></body></html>""".encode()
ACG_2025_Q4 = """<html><body><h1>GF Data Releases Q4 2025 M&A and Leverage Reports</h1>
<p>Chicago, IL – February 18, 2026 — GF Data released its reports through December 31, 2025.</p>
<p>Contributing PE firms reported 297 completed transactions for the full year, with average price multiples at 7.2x trailing 12-month adjusted EBITDA.</p>
<p>PE transactions in the $10 million–$500 million enterprise value range.</p></body></html>""".encode()

ACG_Q1 = """<html><body><h1>GF Data Reports Show Stronger Financing Markets Fueled M&amp;A Gains in Q1</h1>
<p>CHICAGO – May 19, 2026 – GF Data has released its Q1 2026 M&amp;A and Leverage Reports.</p>
<p>GF Data’s contributing private equity firms reported 80 completed transactions during the first quarter
at an average valuation of 7.3x trailing 12-month (TTM) adjusted EBITDA.</p>
<p>PE-sponsored transactions in the $1 million–$500 million enterprise value range.</p></body></html>""".encode()
ACG_Q2 = """<html><body><h1>GF Data Reports Show Steady Middle-Market Deal Flow in Q2</h1>
<p>CHICAGO – August 27, 2026 – GF Data has released its Q2 2026 M&amp;A and Leverage Reports.</p>
<p>GF Data’s contributing private equity firms reported 85 completed transactions in the second quarter.</p>
<p>Average purchase price multiples declined in the second quarter to 7.0x trailing 12-month (TTM) adjusted EBITDA,
down from 7.3x in Q1. Average total debt declined to 2.9x TTM EBITDA from 3.4x in Q1.</p>
<p>PE-sponsored transactions in the $1 million–$500 million enterprise value range.</p></body></html>""".encode()


class PEIndustryRefreshTests(unittest.TestCase):
    def test_sec_tables_select_exact_fund_population(self):
        rows = parse_sec_tables(workbook(), source_url="https://www.sec.gov/valid.xlsx", published_on="")
        frame = pipeline.validate_observations(rows, "sec")
        latest = frame.loc[frame.period.eq("2025Q4")].set_index("metric").value
        self.assertEqual(latest.to_dict(), {"fund_count": 27682.0, "gross_assets_usd_bn": 9334.0, "net_assets_usd_bn": 8523.0})
        self.assertEqual(len(frame), 12)
        self.assertEqual(set(frame.period_end), {"2022-12-31", "2023-12-31", "2024-12-31", "2025-12-31"})
        self.assertEqual(set(frame.geography), {"SEC Form PF reporting population"})
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

    def test_kpmg_2025_h1_partial_is_explicitly_partial(self):
        rows = parse_kpmg_h1(KPMG_2025, source_url=pipeline.KPMG_SEEDS[1])
        self.assertEqual({r["metric"] for r in rows}, {"deal_value", "fundraising"})
        self.assertEqual({r["metric"]: (r["value"], r["sample_count"]) for r in rows},
                         {"deal_value": (869.0, 8296), "fundraising": (225.0, 248)})
        self.assertEqual(rows[0]["precision"], "derived from stated quarters")
        pipeline.validate_observations(rows + parse_kpmg_h1(KPMG_HTML, source_url=pipeline.KPMG_SEEDS[0]), "kpmg")

    def test_kpmg_2025_rejects_missing_q1_deal_basis(self):
        bad = KPMG_2025.replace(b"4,527 deals in Q1", b"4,527 deals in the prior year")
        with self.assertRaises(SourceFormatError):
            parse_kpmg_h1(bad, source_url=pipeline.KPMG_SEEDS[1])

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

    def test_acg_distinguishes_2025_transaction_population(self):
        rows = [parse_acg_quarter(body, source_url=url)[0] for body, url in (
            (ACG_2025_Q2, pipeline.ACG_SEEDS[3]),
            (ACG_2025_Q3, pipeline.ACG_SEEDS[2]),
            (ACG_Q1, pipeline.ACG_SEEDS[1]),
            (ACG_Q2, pipeline.ACG_SEEDS[0]),
        )]
        self.assertEqual([(o["period"], o["value"], o["sample_count"]) for o in rows],
                         [("2025Q2", 6.8, 81), ("2025Q3", 7.5, 66), ("2026Q1", 7.3, 80), ("2026Q2", 7.0, 85)])
        self.assertIn("$10m-", rows[0]["population"])
        self.assertIn("$1m-", rows[-1]["population"])
        pipeline.validate_observations(rows, "acg")

    def test_acg_rejects_annual_price_disguised_as_q4(self):
        with self.assertRaises(SourceFormatError):
            parse_acg_quarter(ACG_2025_Q4, source_url=pipeline.ACG_SEEDS[2])

    def test_acg_rejects_unknown_deal_size_population(self):
        bad = ACG_Q1.replace(b"$1 million", b"$5 million")
        with self.assertRaisesRegex(SourceFormatError, "population"):
            parse_acg_quarter(bad, source_url=pipeline.ACG_SEEDS[1])

    def test_acg_rejects_comparative_multiple_instead_of_observed(self):
        bad = ACG_Q2.replace(b"to 7.0x trailing", b"to an undisclosed figure from 7.0x trailing")
        with self.assertRaises(SourceFormatError):
            parse_acg_quarter(bad, source_url=pipeline.ACG_SEEDS[0])

    def test_article_navigation_does_not_hide_report_period(self):
        # The live publisher pages can contain thousands of characters of
        # navigation before the first editorial heading.
        nav = "<nav>" + "<span>All services and locations</span>" * 550 + "</nav>"
        for payload, parser, url, expected_period in (
            (KPMG_HTML, parse_kpmg_h1, pipeline.KPMG_SEEDS[0], "H1 2026"),
            (KPMG_2025, parse_kpmg_h1, pipeline.KPMG_SEEDS[1], "H1 2025"),
            (ACG_Q1, parse_acg_quarter, pipeline.ACG_SEEDS[1], "2026Q1"),
            (ACG_Q2, parse_acg_quarter, pipeline.ACG_SEEDS[0], "2026Q2"),
        ):
            body = payload.replace(b"<body>", ("<body>" + nav).encode())
            rows = parser(body, source_url=url)
            self.assertTrue(rows)
            self.assertEqual({row["period"] for row in rows}, {expected_period})


    def test_kpmg_published_release_wording_after_large_page_shell(self):
        # These excerpts reproduce the report's actual definition-bearing
        # sentences. The live site can place sizable navigation first.
        chrome = "<section>Worldwide services and articles</section>" * 450
        releases = (
            (pipeline.KPMG_SEEDS[0], """<h1>Global PE market shows resilience with over $1 trillion in PE investment in first half of 2026</h1>
                <p>27 July 2026</p>
                <p>The global PE market showed resilience in Q2’26, bringing the mid-year total of PE investment to $1 trillion across 9,294 deals.</p>
                <h2>Q2'26 - Key highlights</h2>
                <p>In the first half of 2026, global PE deal value sat at $1 trillion across 9,294 deals.</p>
                <p>As of the end of Q2’26, global exit flow was $570.0 billion across 1,315 exits.</p>
                <p>At mid-year, global fundraising was at $261.8 billion across 315 funds.</p>""", {"deal_value": (1000.0, 9294), "exit_value": (570.0, 1315), "fundraising": (261.8, 315)}),
            (pipeline.KPMG_SEEDS[1], """<h1>Global PE Investment Slows Sharply Amid Rising Geopolitical and Trade Uncertainty</h1>
                <p>24 July 2025 – Global private equity investment declined from $505.3 billion in Q1’25 to $363.7 billion in Q2’25.</p>
                <h2>Q2’25 — Key Highlights</h2>
                <p>Global PE investment fell from $505.3 billion across 4,527 deals in Q1’25 to $363.7 billion across 3,769 deals in Q2’25.</p>
                <p>Global PE fundraising was $225 billion across 248 funds at the end of Q2’25.</p>
                <p>The first half of 2025 saw a slower exit market.</p>""", {"deal_value": (869.0, 8296), "fundraising": (225.0, 248)}),
        )
        combined = []
        for url, body, expected in releases:
            payload = ("<html><body>" + chrome + body + "</body></html>").encode("utf-8")
            rows = parse_kpmg_h1(payload, source_url=url)
            self.assertEqual({r["metric"]: (r["value"], r["sample_count"]) for r in rows}, expected)
            combined.extend(rows)
        pipeline.validate_observations(combined, "kpmg")

    def test_acg_published_2026_announcement_with_navigation_and_comparison(self):
        chrome = "<nav>Learn about acquisitions and global markets</nav>" * 400
        articles = (
            (pipeline.ACG_SEEDS[1], """<h1>GF Data Reports Show Stronger Financing Markets Fueled M&amp;A Gains in Q1</h1>
                <p>CHICAGO – May 19, 2026 – GF Data®, an ACG® company, has released its Q1 2026 M&amp;A and Leverage Reports.</p>
                <p>GF Data’s contributing private equity firms reported 80 completed transactions during the first quarter at an average valuation of 7.3x trailing 12-month (TTM) adjusted EBITDA.</p>
                <p>GF Data provides transaction intelligence in the $1 million–$500 million enterprise value range.</p>""", ("2026Q1", 80, 7.3)),
            (pipeline.ACG_SEEDS[0], """<h1>GF Data Reports Show Steady Middle-Market Deal Flow Amid More Selective Financing Conditions in Q2</h1>
                <p>CHICAGO – August 27, 2026 – GF Data®, an ACG® company, has released its Q2 2026 M&amp;A and Leverage Reports.</p>
                <p>GF Data’s contributing private equity firms reported 85 completed transactions in the second quarter. With 170 transactions recorded in the first half of 2026, it is tracking toward 340 full year.</p>
                <p>Average purchase price multiples declined in the second quarter to 7.0x trailing 12-month (TTM) adjusted EBITDA, down from 7.3x in Q1.</p>
                <p>GF Data provides transaction intelligence in the $1 million–$500 million enterprise value range.</p>""", ("2026Q2", 85, 7.0)),
        )
        for url, body, expected in articles:
            rows = parse_acg_quarter(("<html><body>" + chrome + body + "</body></html>").encode(), source_url=url)
            self.assertEqual((rows[0]["period"], rows[0]["sample_count"], rows[0]["value"]), expected)

    def test_q3_kpmg_discovery_cannot_supply_q2_h1_observations(self):
        url = "https://kpmg.com/xx/en/media/press-releases/2025/10/global-pe-deal-volume-on-pace-for-four-year-high.html"
        payload = KPMG_2025.replace(b"<h1>", b"<h1>Highlights about Q2'25. ")
        with self.assertRaisesRegex(SourceFormatError, "H1 reporting window"):
            parse_kpmg_h1(payload, source_url=url)

    def test_acg_rejects_reference_quarter_without_report_identification(self):
        fake = """<html><body><h1>GF Data Market Commentary</h1>
            <p>May 19, 2026 — GF Data reviewed deals completed in Q1 2026.</p>
            <p>GF Data’s contributing private equity firms reported 80 completed transactions during the first quarter at an average valuation of 7.3x trailing 12-month (TTM) adjusted EBITDA.</p>
            <p>Transactions cover $1 million–$500 million enterprise values.</p></body></html>""".encode()
        with self.assertRaisesRegex(SourceFormatError, "report quarter/year"):
            parse_acg_quarter(fake, source_url=pipeline.ACG_SEEDS[1])

    def test_acg_q3_quarter_count_survives_subsequent_ytd_sentence(self):
        body = b"""<html><body><h1>GF Data Releases Q3 2025 M&amp;A and Leverage Reports</h1>
        <p>Chicago, IL - November 18, 2025 - GF Data reports on middle-market transactions.</p>
        <p>GF Data's contributing private equity firms reported 66 completed transactions in Q3--down approximately 20% from the 83 deals recorded in the second quarter.
        Year to date, 211 transactions have been reported, representing a 27% decline.</p>
        <p>Despite lower volume, average purchase price multiples rebounded to 7.5x trailing 12-month adjusted EBITDA, up from 6.9x in the second quarter.</p>
        <p>GF Data's sample covers private equity-sponsored transactions in the $10 million-$500 million enterprise value range.</p>
        </body></html>"""
        rows = parse_acg_quarter(body, source_url=pipeline.ACG_SEEDS[2])
        self.assertEqual((rows[0]["period"], rows[0]["sample_count"], rows[0]["value"]), ("2025Q3", 66, 7.5))

    def test_local_sec_403_explains_identity_and_keeps_data_untouched(self):
        err = HTTPError(pipeline.SEC_INDEX, 403, "Forbidden", {}, None)
        with patch.dict("os.environ", {"SEC_USER_AGENT": ""}), patch.object(pipeline, "urlopen", side_effect=err):
            with self.assertRaisesRegex(SourceFormatError, "SEC_USER_AGENT is not set locally"):
                pipeline.fetch(pipeline.SEC_INDEX, "sec")

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

    def test_partial_provider_failure_retains_other_source(self):
        acg_rows = [parse_acg_quarter(ACG_Q1, source_url=pipeline.ACG_SEEDS[1])[0]]
        def candidate(name):
            if name == "sec":
                raise SourceFormatError("SEC rate limited")
            return acg_rows, []
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(pipeline, "source_candidate", side_effect=candidate):
                outcome = pipeline.run(out_dir=Path(tmp), selected=("sec", "acg"))
            self.assertEqual([row["status"] for row in outcome], ["unavailable", "updated"])
            self.assertTrue((Path(tmp) / "pe_industry_acg.csv").exists())
            self.assertFalse((Path(tmp) / "pe_industry_sec.csv").exists())

    def test_production_write_is_not_available_from_local_probe(self):
        with patch.dict("os.environ", {"AI_MACRO_MODE": "local"}):
            with self.assertRaises(PermissionError):
                pipeline.run(out_dir=pipeline.PRODUCTION, selected=("sec",))

    def test_automation_publication_is_graph_scheduled_and_retained(self):
        from automation.refresh_graph import NODE_INDEX
        from tooling.repository_policy import is_automation_publication_path
        self.assertEqual(NODE_INDEX["pe_industry"].interval_hours, 168)
        self.assertTrue(is_automation_publication_path("data/private_capital/pe_industry_sec.csv"))
        source = (ROOT / "automation" / "research_refresh.py").read_text(encoding="utf-8")
        self.assertIn('refresh_pe_industry(out_dir=PE_INDUSTRY_DIR)', source)
        self.assertIn('"pe_industry": pe_industry_report', source)

    def test_revisions_require_review_and_leave_prior_state_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = pipeline.validate_observations([parse_acg_quarter(ACG_Q1, source_url=pipeline.ACG_SEEDS[1])[0]], "acg")
            path = Path(tmp) / "pe_industry_acg.csv"
            pipeline.persist_source("acg", a, path)
            before = path.read_bytes()
            corrected = a.copy()
            corrected.loc[0, "value"] = 7.4
            with self.assertRaisesRegex(SourceFormatError, "changed; review"):
                pipeline.persist_source("acg", corrected, path)
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
