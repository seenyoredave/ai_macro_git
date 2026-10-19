"""Offline five-year U.S. PE net-return source and Finance/Read integration tests."""
from __future__ import annotations

import csv
from io import BytesIO
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analytics import pe_us_conditions as pe
from loaders import pe_us_returns_retained as r
from rendering.pe_conditions_layout import build_pe_conditions_markup


def fixture(year=2025, *, pe5=11.7, sp5=14.9, russ5=6.8):
    return '\n'.join([
        'INSIGHTS US Private Equity & Venture Capital Benchmark Commentary',
        f'Calendar Year {year}',
        'Figure 1 US private equity and venture capital index returns',
        f'Periods Ended December 31, {year} • Percent (%)',
        'Index   6 Mo  1 Yr  3 Yr  5 Yr  10 Yr  15 Yr  20 Yr  25 Yr',
        f'CA US Private Equity*  4.5  8.7  8.7  {pe5}  15.2  15.0  13.2  12.4',
        f'Russell 2000® mPME  14.9  12.9  13.7  {russ5}  9.9  9.9  8.7  8.8',
        f'S&P 500 mPME  11.0  17.9  23.0  {sp5}  15.1  14.3  11.3  10.0',
        'CA US Venture Capital 14.1 21.1 8.7 10.2 14.9 15.5 12.9 8.1',
        'Russell 2000® mPME 14.8 13.3 13.8 6.8 9.7 9.7 8.6 8.8',
    ])


class USReturnsTests(unittest.TestCase):
    def test_seed_source_matches_published_figure(self):
        rows = pe.validated_return_rows(pe.SEED / pe.RETURN_NAME)
        self.assertEqual([row['year'] for row in rows], [2024, 2025])
        self.assertEqual([row['pe_5y_annualized_net_pct'] for row in rows], [15.8, 11.7])
        self.assertEqual(rows[-1]['sp500_5y_mpme_pct'], 14.9)
        self.assertEqual(rows[-1]['russell2000_5y_mpme_pct'], 6.8)

    def test_pdf_table_row_parses_correct_horizon(self):
        row = r.parse_report(fixture(), year=2025, source_url=r.PDF_URLS[2025])
        self.assertEqual(row['pe_5y_annualized_net_pct'], 11.7)
        self.assertEqual(row['pe_1y_net_pct'], 8.7)
        self.assertEqual(row['sp500_5y_mpme_pct'], 14.9)
        self.assertEqual(row['russell2000_5y_mpme_pct'], 6.8)

    def test_wrong_year_and_missing_horizon_fail_closed(self):
        with self.assertRaises(r.ReturnSourceRejected):
            r.parse_report(fixture(), year=2024, source_url=r.PDF_URLS[2024])
        with self.assertRaises(r.ReturnSourceRejected):
            r.parse_report(fixture().replace('5 Yr', '4 Yr'), year=2025, source_url=r.PDF_URLS[2025])

    def test_vc_or_misordered_row_cannot_be_selected(self):
        altered = fixture().replace('CA US Private Equity*', 'CA US Venture Capital')
        with self.assertRaises(r.ReturnSourceRejected):
            r.parse_report(altered, year=2025, source_url=r.PDF_URLS[2025])

    def test_unsafe_source_rejected(self):
        with self.assertRaises(r.ReturnSourceRejected):
            r.parse_report(fixture(), year=2025, source_url='https://evil.example/report.pdf')

    def test_invalid_seed_rejected_without_seed_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / pe.RETURN_NAME
            path.write_text((pe.SEED / pe.RETURN_NAME).read_text().replace('11.7,8.7', '111.7,8.7'))
            with self.assertRaises(pe.InvalidPEObservation):
                pe.validated_return_rows(path)
            self.assertEqual(pe.build_pe_us_conditions(Path(tmp))['returns'], {})

    def test_sec_pe_fund_scale_is_net_assets_not_cash(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = pe.build_pe_us_conditions(Path(tmp))
        self.assertEqual(data['scale']['value_usd_bn'], 8523.0)
        markup = build_pe_conditions_markup(data)
        self.assertIn('U.S. PE fund net assets', markup)
        self.assertIn('$8.52T', markup)
        self.assertIn('SEC Form PF', markup)
        self.assertNotIn('cash held in', markup.lower())

    def test_uniform_four_card_display_with_uncluttered_return_figures(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = pe.build_pe_us_conditions(Path(tmp))
        self.assertEqual(data['returns']['pe_5y_annualized_net_pct'], 11.7)
        markup = build_pe_conditions_markup(data)
        self.assertEqual(markup.count('class="rm-pe-stage"'), 4)
        self.assertEqual(markup.count('class="rm-pe-measure"'), 8)
        self.assertLess(markup.index('Valuations'), markup.index('Selling companies'))
        self.assertLess(markup.index('Selling companies'), markup.index('Cash to investors'))
        self.assertLess(markup.index('Cash to investors'), markup.index('Investor returns'))
        self.assertIn('Five-year annualized net return', markup)
        self.assertIn('+11.7%', markup)
        self.assertIn('2025 net return', markup)
        self.assertIn('+8.7%', markup)
        self.assertNotIn('S&amp;P 500', markup)
        self.assertNotIn('Russell 2000', markup)
        self.assertNotIn('Previous five-year reading:', markup)
        self.assertNotIn('rm-pe-step', markup)

    def test_fully_empty_and_partially_missing_returns(self):
        self.assertEqual(build_pe_conditions_markup({}), '')
        with tempfile.TemporaryDirectory() as tmp:
            data = pe.build_pe_us_conditions(Path(tmp))
        data['returns'] = {}
        self.assertIn('Investment-return data unavailable', build_pe_conditions_markup(data))

    def test_automation_preserves_prior_on_download_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / r.NAME
            initial = (pe.SEED / pe.RETURN_NAME).read_bytes()
            dest.write_bytes(initial)
            with patch.object(r, '_fetch', side_effect=OSError('not reachable')):
                result = r.refresh(out_dir=Path(tmp), current_year=2026, current_month=10)
            self.assertEqual(result['status'], 'retained_on_failure')
            self.assertEqual(dest.read_bytes(), initial)

    def test_staging_refresh_changes_only_return_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            def fake_pdf(url, *, pdf):
                self.assertTrue(pdf)
                return b'%PDF-test'
            # Exercise the real source parser, rather than trusting mocked row values.
            def fake_return_page(body):
                    year = 2024 if body.endswith(b'2024') else 2025
                    return fixture(year, pe5=15.8 if year==2024 else 11.7,
                                   sp5=15.0 if year==2024 else 14.9,
                                   russ5=7.9 if year==2024 else 6.8)
            with patch.object(r, '_fetch', side_effect=lambda url,pdf:b'%PDF'+(b'2024' if '2024' in url else b'2025')), \
                 patch.object(r,'extract_first_page',side_effect=fake_return_page):
                result = r.refresh(out_dir=Path(tmp), current_year=2026, current_month=10)
            self.assertEqual(result['status'],'updated')
            self.assertEqual(len(pe.validated_return_rows(Path(tmp)/r.NAME)),2)
            self.assertEqual([p.name for p in Path(tmp).iterdir()], [r.NAME])

    def test_public_automation_gate(self):
        with patch.dict(os.environ, {'AI_MACRO_MODE': 'public'}):
            with self.assertRaises(PermissionError):
                r.refresh(out_dir=r.PRODUCTION, current_year=2026, current_month=10)

    def test_read_gets_return_and_comparison_facts(self):
        text = (ROOT / 'analytics/read_evidence.py').read_text()
        for key in ('pe_5y_annualized_net_pct', 'pe_1y_net_pct',
                    'pe_sp500_5y_mpme_pct', 'pe_russell2000_5y_mpme_pct'):
            self.assertIn(key, text)
            self.assertIn(key, (ROOT / 'analytics/domain_state.py').read_text())
        self.assertIn('"returns", "Cambridge Associates U.S. PE Net Returns"', text)
        self.assertIn('refresh_pe_us_returns', (ROOT / 'automation/research_refresh.py').read_text())


if __name__ == '__main__':
    unittest.main()
