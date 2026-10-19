"""Offline parser and publication-safety contracts for the U.S. PE liquidity probe."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from loaders import pe_us_liquidity_probe as p


def article(headings_and_paragraphs):
    body = ''.join(f'<{tag}>{txt}</{tag}>' for tag, txt in headings_and_paragraphs)
    return f'<html><body><script>fake 9,999 exits</script>{body}</body></html>'.encode()


def cambridge(year):
    cash = ('In 2024, LP distributions ($174 billion) outpaced contributions ($143 billion), a reversal. Distributions rose 37% from 2023.'
            if year == 2024 else
            'In 2025, fund managers distributed $185 billion and called $145 billion. '
            'Those totals represented a 5% increase in capital returned to LPs.')
    return article([('h1', f'US PE/VC Benchmark Commentary: Calendar Year {year}'),
                    ('h2', 'US Private Equity Performance Insights'),
                    ('p', 'US private equity benchmark buyout and growth equity returns.'),
                    ('h3', 'LP Cash Flows'), ('p', cash),
                    ('h2', 'US Venture Capital Performance Insights'),
                    ('p', 'US VC in 2025 distributed $999 billion and called $888 billion.'),
                    ('p', 'US VC LP distributions rose sharply.')])


def kpmg(year):
    cash = ('In the first half of 2025, PE exits rebounded, with $318.97 billion in exit value, '
            'nearing 2024’s $373.1 billion. The U.S. saw 476 exits, fewer than 2024’s 1,302.'
            if year == 2025 else
            'US PE exit value reached $273.1 billion at H1 2026, but volume remained '
            'suppressed at just 508 exits — well below 2025’s 1,376 pace.')
    return article([('h1', f'Q2 {year} Pulse of Private Equity'),
                    ('h3', 'U.S. insights'), ('p', 'US private equity exits are important.'),
                    ('h3', 'PE exit value remains solid'), ('p', cash),
                    ('h3', 'Global insights'),
                    ('p', f'Global PE exits in the first half of {year} '
                          'totaled $576.9 billion and 1,315 exits.')])


def fake_fetch(url, *, source):
    year = int(__import__('re').search(r'/20(\d\d)/|calendar-year-(20\d\d)', url).group(2)
               if 'cambridgeassociates' in url else
               __import__('re').search(r'/articles/(20\d\d)/', url).group(1))
    if source == 'cambridge':
        return cambridge(year)
    return kpmg(year)


class LiquiditySourceTests(unittest.TestCase):
    def test_cambridge_2024_exact(self):
        row = p.parse_cambridge(cambridge(2024), year=2024, url='a')
        self.assertEqual((row['distributions_usd_bn'], row['capital_calls_usd_bn']), (174, 143))
        self.assertEqual(row['distributions_to_calls'], round(174/143, 4))

    def test_cambridge_2025_exact(self):
        row = p.parse_cambridge(cambridge(2025), year=2025, url='b')
        self.assertEqual((row['distributions_usd_bn'], row['capital_calls_usd_bn']), (185, 145))

    def test_us_vc_not_used_for_pe_cash_flows(self):
        with self.assertRaises(p.SourceRejected):
            p.parse_cambridge(article([('h2','US Private Equity Performance Insights'),
                                       ('p','No reported LP cash flow.'),
                                       ('h2','US Venture Capital Performance Insights'),
                                       ('p','In 2025, fund managers distributed $185 billion and called $145 billion.')]),
                              year=2025, url='c')

    def test_kpmg_2025_exact(self):
        row = p.parse_kpmg(kpmg(2025), year=2025, url='u')
        self.assertEqual((row['exit_value_usd_bn'], row['exit_count']), (318.97, 476))

    def test_kpmg_2026_exact(self):
        row = p.parse_kpmg(kpmg(2026), year=2026, url='u')
        self.assertEqual((row['exit_value_usd_bn'], row['exit_count']), (273.1, 508))

    def test_unheaded_2026_us_insights_parses_exit_headline(self):
        # Live KPMG 2026 markup has a visible U.S. insights label, but it is
        # not exposed as an h1-h6 heading. The exit headline remains a h3.
        raw = article([
            ('h1', 'Q2 2026 Pulse of Private Equity'),
            ('p', 'Overview: global exit value was $576.9 billion at H1 2026, 1,315 exits.'),
            ('h3', 'PE exit value remains solid, despite continued slowdown in exit volume'),
            ('p', 'US PE exit value reached $273.1 billion at H1 2026, '
                  'but volume remained suppressed at just 508 exits.'),
            ('h3', 'Global PE market sees $1 trillion in investment at mid-year'),
            ('p', 'Global PE exit value reached $576.9 billion at H1 2026, with 1,315 exits.'),
        ])
        row = p.parse_kpmg(raw, year=2026, url='https://kpmg.com/source')
        self.assertEqual((row['exit_value_usd_bn'], row['exit_count']), (273.1, 508))

    def test_unheaded_fallback_cannot_use_global_or_overview(self):
        raw = article([
            ('h1', 'Q2 2026 Pulse of Private Equity'),
            ('p', 'US PE exit value reached $273.1 billion at H1 2026, with 508 exits.'),
            ('h3', 'Global PE market sees $1 trillion in investment at mid-year'),
            ('p', 'US PE exit value reached $576.9 billion at H1 2026, with 1,315 exits.'),
        ])
        with self.assertRaises(p.SourceRejected):
            p.parse_kpmg(raw, year=2026, url='https://kpmg.com/source')

    def test_unheaded_fallback_refuses_multiple_us_exit_paragraphs(self):
        raw = article([
            ('h1', 'Q2 2026 Pulse of Private Equity'),
            ('h3', 'PE exit value remains solid, despite continued slowdown in exit volume'),
            ('p', 'US PE exit value reached $273.1 billion at H1 2026, with 508 exits.'),
            ('p', 'US PE exit value reached $100 billion at H1 2026, with 600 exits.'),
            ('h3', 'Global PE market sees $1 trillion'),
            ('p', 'Global PE exits were strong.'),
        ])
        with self.assertRaises(p.SourceRejected):
            p.parse_kpmg(raw, year=2026, url='https://kpmg.com/source')

    def test_global_pe_not_mixed_into_us(self):
        data = article([('h3','U.S. insights'),('p','US exits still slow.'),
                        ('h3','Global insights'),
                        ('p','US PE exit value reached $273.1 billion at H1 2026, but 508 exits.')])
        with self.assertRaises(p.SourceRejected):
            p.parse_kpmg(data, year=2026, url='u')

    def test_fails_closed_on_ambiguous_reports(self):
        base = [('h3','U.S. insights'),('p','US PE exit value reached $273.1 billion at H1 2026, 508 exits.'),
                ('p','US PE exit value reached $100 billion at H1 2026, 600 exits.'),
                ('h3','Global insights'),('p','Nothing.')]
        with self.assertRaises(p.SourceRejected):
            p.parse_kpmg(article(base), year=2026, url='u')

    def test_wrong_period_is_rejected(self):
        with self.assertRaises(p.SourceRejected):
            p.parse_kpmg(kpmg(2025), year=2026, url='u')

    def test_numeric_plausibility(self):
        bad = article([('h3','U.S. insights'),
                       ('p','US PE exit value reached $99999 billion at H1 2026 and 508 exits.'),
                       ('h3','Global insights'),('p','Nothing.')])
        with self.assertRaises(p.SourceRejected):
            p.parse_kpmg(bad, year=2026, url='u')

    def test_year_on_year_separate_populations(self):
        a = [p.parse_cambridge(cambridge(y), year=y, url='a') for y in (2024,2025)]
        b = [p.parse_kpmg(kpmg(y), year=y, url='b') for y in (2025,2026)]
        ca = p.comparisons(a, source='cambridge')
        km = p.comparisons(b, source='kpmg')
        self.assertEqual(ca[0]['publisher_distribution_yoy_pct'], 37.0)
        self.assertEqual(ca[-1]['publisher_distribution_yoy_pct'], 5.0)
        self.assertEqual(km[-1]['cross_report_exit_value_change_pct'], -14.38)
        self.assertEqual(km[-1]['cross_report_exit_count_change_pct'], 6.72)

    def test_gap_prevents_false_yoy(self):
        b = [p.parse_kpmg(kpmg(y), year=y, url='u') for y in (2025,2026)]
        b[-1]['year'] = 2027
        self.assertEqual(p.comparisons(b, source='kpmg')[-1]['cross_report_exit_value_change_pct'], '')

    def test_disallow_unknown_sources(self):
        with self.assertRaises(p.SourceRejected):
            p.fetch('https://example.com/pe', source='kpmg')

    def test_no_foreign_redirect(self):
        with self.assertRaises(p.SourceRejected):
            p.fetch('http://kpmg.com/us/en/articles/2026/x', source='kpmg')

    def test_csv_has_readable_provenance(self):
        row = p.parse_cambridge(cambridge(2025), year=2025, url='https://www.cambridgeassociates.com/a')
        csv_text = p._csv_bytes([row], p.CAMBRIDGE_FIELDS).decode()
        self.assertIn('Cambridge U.S. PE benchmark', csv_text)
        self.assertIn('source_url,population', csv_text.splitlines()[0])

    def test_atomic_publish_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(p, 'fetch', side_effect=fake_fetch):
                result = p.run(Path(tmp), current_year=2026)
            self.assertEqual(result['status'], 'candidate_extracted')
            self.assertEqual(result['sources']['cambridge']['validated_years'], [2024, 2025])
            self.assertEqual(result['sources']['kpmg']['validated_years'], [2025, 2026])
            self.assertEqual(len(list(Path(tmp).glob('*.csv'))), 2)

    def test_failed_fetch_preserves_prior_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = Path(tmp) / 'us_pe_exits_h1.csv'
            old.write_text('prior validated')
            with patch.object(p, 'fetch', side_effect=OSError('unavailable')):
                with self.assertRaises(p.SourceRejected):
                    p.run(Path(tmp), current_year=2026)
            self.assertEqual(old.read_text(), 'prior validated')

    def test_future_year_urls_are_predictable(self):
        self.assertIn('q2-27-pulse', p.source_url('kpmg', 2027))
        self.assertIn('calendar-year-2026', p.source_url('cambridge', 2026))

    def test_only_candidate_paths(self):
        self.assertEqual(p.OUT, Path('pe_probe_output/us_liquidity'))


if __name__ == '__main__':
    unittest.main()
