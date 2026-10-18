"""Synthetic contract checks for the read-only CalPERS liquidity candidate parser."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from loaders import pe_lp_liquidity_probe as p


BEGIN = 112810432778.40
CALLS = 12692849953.00
DISTRIB = 10345920797.00
OTHER = 4156902751.01
END = 119314264685.41


def example(*, distributions=DISTRIB, month='March', year=2026):
    return f'''Agenda Item 4d, Attachment 1, Page 12 of 18
Investment Transaction Summary for the Month Ended {month} {year}
Total Fund - Private Markets
     Private Debt ($)      Private Equity ($)     Real Estate ($)    Infrastructure ($)
Beginning Market Value   24,464,312,524.80   112,810,432,778.40   54,377,137,702.62
+ Contributions          868,410,961.19     12,692,849,953.00    1,006,271,732.00
- Distributions         (445,476,143.71)   ({distributions:,.2f})   (1,275,706,364.00)
+/- Other Changes in MV   476,043,332.55     4,156,902,751.01     162,017,805.90
Ending Market Value      25,363,290,674.83   119,314,264,685.41   54,269,720,876.52
Total Public Markets   Total Private Markets   Total Fund'''


class LiquidityTest(unittest.TestCase):
    def test_monthly_value_reconciles(self):
        row = p.parse_month_page(example(), 'https://www.calpers.ca.gov/test')
        self.assertEqual(row['period_end'], '2026-03-31')
        self.assertEqual(row['contributions_usd'], CALLS)
        self.assertEqual(row['distributions_usd'], DISTRIB)
        self.assertEqual(row['ending_value_usd'], END)
        self.assertEqual(row['net_cash_to_lps_usd'], DISTRIB-CALLS)

    def test_rejects_failed_reconciliation(self):
        with self.assertRaisesRegex(p.SourceRejected, 'reconciliation'):
            p.parse_month_page(example(distributions=10000000000), 'https://www.calpers.ca.gov/test')

    def test_rejects_wrong_population(self):
        with self.assertRaises(p.SourceRejected):
            p.parse_month_page(example().replace('Private Debt ($)      Private Equity ($)',
                                                      'Private Equity ($)      Private Debt ($)'),
                               'https://www.calpers.ca.gov/test')

    def test_rejects_missing_value(self):
        with self.assertRaises(p.SourceRejected):
            p.parse_month_page(example().replace('112,810,432,778.40', ''),
                               'https://www.calpers.ca.gov/test')

    def test_no_fake_quarter_from_one_month(self):
        month = p.parse_month_page(example(), 'https://www.calpers.ca.gov/test')
        self.assertEqual(p.complete_quarters([month]), [])

    def test_three_complete_months(self):
        a = p.parse_month_page(example(month='January'), 'https://www.calpers.ca.gov/test')
        b = p.parse_month_page(example(month='February'), 'https://www.calpers.ca.gov/test')
        c = p.parse_month_page(example(), 'https://www.calpers.ca.gov/test')
        quarter = p.complete_quarters([a,b,c])
        self.assertEqual(len(quarter), 1)
        self.assertEqual(quarter[0]['months'], 3)
        self.assertEqual(quarter[0]['contributions_usd'], 3*CALLS)

    def test_conflicting_month_rejected(self):
        first = p.parse_month_page(example(), 'https://www.calpers.ca.gov/first')
        other = dict(first, ending_value_usd=10)
        with self.assertRaisesRegex(p.SourceRejected, 'Conflicting'):
            p.merge_months([[first],[other]])

    def test_index_follows_attachment_not_other_docs(self):
        html = b'''<ul><li><a href="/documents/a/download">Private Equity Annual Review</a></li>
        <li><a href="/documents/202606-invest-agenda-item04d-00-a/download">Quarterly Update - Investment Controls</a>
        <ul><li><a href="/documents/202606-invest-agenda-item04d-01-a/download">Attachment 1 (PDF)</a></li></ul></li></ul>'''
        self.assertEqual(p.discover_documents(html, 'https://www.calpers.ca.gov/about/board/board-meetings/invest-202606'),
                         ['https://www.calpers.ca.gov/documents/202606-invest-agenda-item04d-01-a/download'])

    def test_meeting_discovery_uses_actual_links(self):
        html = b'''<a href="/about/board/board-meetings/invest-202612">Investment Committee</a>
                     <a href="/about/board/board-meetings/full-202612">Board</a>
                     <a href="https://example.org/about/board/board-meetings/invest-202701">External</a>'''
        self.assertEqual(p.discover_meetings(html),
                         ['https://www.calpers.ca.gov/about/board/board-meetings/invest-202612'])

    def test_prohibits_off_site_redirects(self):
        self.assertFalse(p.allowed('https://evil.example.org/a'))
        self.assertFalse(p.allowed('http://www.calpers.ca.gov/x'))
        self.assertTrue(p.allowed('https://www.calpers.ca.gov/documents/foo/download'))

    def test_source_failure_does_not_make_records(self):
        with patch.object(p, 'fetch', side_effect=OSError('network unavailable')):
            with __import__('tempfile').TemporaryDirectory() as temp:
                from pathlib import Path
                result = p.run(Path(temp), board_pages=p.BOARD_PAGES[:1], seeds=p.SEED_PDFS[:1])
                self.assertEqual(result, ([], []))
                self.assertFalse((Path(temp) / 'calpers_pe_monthly.csv').exists())


if __name__ == '__main__':
    unittest.main()
