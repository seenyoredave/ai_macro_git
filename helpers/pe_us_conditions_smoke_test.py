"""Deterministic source, failure-retention, Finance and Reader PE contracts."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from types import SimpleNamespace
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analytics import pe_us_conditions as c
from rendering.pe_conditions_layout import build_pe_conditions_markup
from loaders import pe_us_liquidity_retained as retained
from helpers.pe_us_liquidity_smoke_test import fake_fetch


class ConditionsTests(unittest.TestCase):
    def test_last_retrieval_is_published_success_not_observation_or_today(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'refresh_graph_state.json'
            self.assertIsNone(c.last_pe_retrieval_date(path))
            path.write_text(json.dumps({'nodes': {
                'pe_us_liquidity': {
                    'last_success_at_utc': '2026-10-15T03:00:00+00:00',
                    'last_attempt_at_utc': '2026-10-18T06:00:00+00:00',
                    'last_status': 'failed',
                },
                'pe_industry': {'last_success_at_utc': '2026-10-17T03:00:00+00:00'},
            }}))
            self.assertEqual(c.last_pe_retrieval_date(path), '10.17.2026')
            path.write_text(json.dumps({'nodes': {
                'pe_us_liquidity': {
                    'last_retrieval_at_utc': '2026-10-18T04:00:00+00:00',
                    'last_success_at_utc': '2026-10-15T03:00:00+00:00',
                    'last_attempt_at_utc': '2026-10-19T06:00:00+00:00',
                    'last_status': 'partial',
                },
                'pe_industry': {'last_success_at_utc': '2026-10-17T03:00:00+00:00'},
            }}))
            self.assertEqual(c.last_pe_retrieval_date(path), '10.18.2026')

    def test_no_retrieval_date_from_invalid_or_unrecorded_source(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'refresh_graph_state.json'
            path.write_text(json.dumps({'nodes': {'pe_us_liquidity': {
                'last_attempt_at_utc': '2026-10-19T06:00:00+00:00',
                'last_status': 'failed'}}}))
            self.assertIsNone(c.last_pe_retrieval_date(path))
            path.write_text(json.dumps({'nodes': {
                'pe_us_liquidity': {'last_success_at_utc': 'not-a-date'},
                'pe_industry': {'last_retrieval_at_utc': '2099-10-19T06:00:00+00:00'},
            }}))
            self.assertIsNone(c.last_pe_retrieval_date(path))

    def test_refresh_retrieval_marker_advances_only_for_successful_source(self):
        from automation.pe_retrieval import record_pe_retrieval
        plan = SimpleNamespace(now=datetime(2026, 10, 19, 6, 0, tzinfo=timezone.utc),
                               state={'nodes': {'pe_us_liquidity': {}}})
        record_pe_retrieval(plan, 'pe_us_liquidity', [
            {'source': 'cambridge', 'status': 'retained_on_failure'},
            {'source': 'kpmg', 'status': 'updated'}])
        self.assertEqual(plan.state['nodes']['pe_us_liquidity']['last_retrieval_at_utc'],
                         '2026-10-19T06:00:00+00:00')
        plan.now = datetime(2026, 10, 20, 6, 0, tzinfo=timezone.utc)
        record_pe_retrieval(plan, 'pe_us_liquidity', [
            {'source': 'cambridge', 'status': 'unavailable'},
            {'source': 'kpmg', 'status': 'retained_on_failure'}])
        self.assertEqual(plan.state['nodes']['pe_us_liquidity']['last_retrieval_at_utc'],
                         '2026-10-19T06:00:00+00:00')
        record_pe_retrieval(plan, 'pe_us_liquidity', [])
        self.assertEqual(plan.state['nodes']['pe_us_liquidity']['last_retrieval_at_utc'],
                         '2026-10-19T06:00:00+00:00')
        record_pe_retrieval(plan, 'pe_us_liquidity', [{'status': 'unchanged'}])
        self.assertEqual(plan.state['nodes']['pe_us_liquidity']['last_retrieval_at_utc'],
                         '2026-10-20T06:00:00+00:00')

    def test_seed_files_are_actual_validated_artifacts(self):
        lp = c.validated_rows(c.SEED / c.LP_NAME, 'cambridge')
        exits = c.validated_rows(c.SEED / c.EXIT_NAME, 'kpmg')
        self.assertEqual([row['year'] for row in lp], [2024, 2025])
        self.assertEqual([row['year'] for row in exits], [2025, 2026])
        self.assertEqual(lp[-1]['distributions_to_calls'], 1.2759)
        self.assertEqual(exits[-1]['exit_value_usd_bn'], 273.1)

    def test_fallback_only_when_retained_absent(self):
        with tempfile.TemporaryDirectory() as d:
            result = c.build_pe_us_conditions(Path(d))
            self.assertEqual(result['lp']['year'], 2025)
            self.assertEqual(result['exits']['year'], 2026)

    def test_exit_changes_are_independent_of_benchmark(self):
        with tempfile.TemporaryDirectory() as d:
            result = c.build_pe_us_conditions(Path(d))
            self.assertEqual(result['exits']['exit_value_change_pct'], -14.38)
            self.assertEqual(result['exits']['exit_count_change_pct'], 6.72)
            self.assertEqual(result['exits']['prior_year'], 2025)

    def test_lp_prior_benchmark_is_explicitly_dated(self):
        with tempfile.TemporaryDirectory() as d:
            result = c.build_pe_us_conditions(Path(d))
        self.assertEqual(result['lp']['prior_year'], 2024)
        self.assertAlmostEqual(result['lp']['prior_distributions_to_calls'], 174 / 143, places=4)

    def test_pe_layout_has_four_equal_unnumbered_cards(self):
        with tempfile.TemporaryDirectory() as d:
            markup = build_pe_conditions_markup(c.build_pe_us_conditions(Path(d)))
        self.assertEqual(markup.count('class="rm-pe-stage"'), 4)
        self.assertEqual(markup.count('class="rm-pe-stage-top"'), 4)
        self.assertEqual(markup.count('class="rm-pe-stage-measures"'), 4)
        self.assertNotIn('rm-pe-stage-source', markup)
        self.assertEqual(markup.count('class="rm-pe-measure"'), 8)
        self.assertEqual(markup.count('class="rm-pe-scale"'), 1)
        self.assertIn('U.S. PE fund net assets', markup)
        self.assertIn('$8.52T', markup)
        self.assertNotIn('rm-pe-scale-source', markup)
        self.assertNotIn('href=', markup)
        buying, selling, cash, returns = (
            markup.index('Valuations'), markup.index('Selling companies'),
            markup.index('Cash to investors'), markup.index('Investor returns'))
        self.assertLess(buying, selling)
        self.assertLess(selling, cash)
        self.assertLess(cash, returns)
        for phrase in ('Average valuation', '7.0× EBITDA',
                       'Quarterly change', '-0.3×',
                       'Exit transaction value', '$273.1B', 'Number of exits', '508',
                       'Paid to investors', '$185B', 'Paid by investors', '$145B',
                       'Five-year annualized net return', '+11.7%', '2025 net return', '+8.7%'):
            self.assertIn(phrase, markup)
        for unwanted in ('rm-pe-step', 'Company value for each $1',
                         'Funds paid out $40B', 'cash-flow-matched public-market',
                         'Previous five-year reading:', 'Average acquisition price', 'Purchase value / annual EBITDA'):
            self.assertNotIn(unwanted, markup)
        self.assertNotIn('rel="noopener noreferrer"', markup)
        self.assertNotIn('1.28×', markup)
        self.assertNotIn('private_capital', markup)

    def test_pe_layout_css_uses_one_four_card_treatment(self):
        css = (ROOT / 'rendering/theme.css').read_text()
        block = css[css.index('/* Private equity: Finance-purple top rules') :]
        self.assertIn('grid-template-columns: repeat(2, minmax(0, 1fr));', block)
        self.assertIn('border-top: 3px solid #a78bfa;', block)
        self.assertIn('.rm-pe-scale,\n.rm-pe-stage {', block)
        self.assertIn('.rm-finance-section--sourced', block)
        self.assertIn('.rm-finance-section-sources', block)
        self.assertIn('@media (max-width: 850px)', block)
        self.assertIn('.rm-pe-journey {grid-template-columns: 1fr;}', block)
        for unwanted in ('nth-child(4)', '.rm-pe-step', '.rm-pe-net-note',
                         '.rm-pe-measure--secondary', '.rm-pe-journey > .rm-pe-stage'):
            self.assertNotIn(unwanted, block)

    def test_layout_handles_partial_and_empty_retained_data(self):
        with tempfile.TemporaryDirectory() as d:
            complete = c.build_pe_us_conditions(Path(d))
        self.assertEqual(build_pe_conditions_markup({}), '')
        self.assertIn('Exit data unavailable', build_pe_conditions_markup({'lp': complete['lp']}))
        self.assertIn('Investor cash-flow data unavailable', build_pe_conditions_markup({'exits': complete['exits']}))
        self.assertIn('Valuation unavailable', build_pe_conditions_markup({'lp': complete['lp']}))

    def test_layout_rejects_untrusted_provider_link(self):
        with tempfile.TemporaryDirectory() as d:
            complete = c.build_pe_us_conditions(Path(d))
        lp = dict(complete['lp'])
        lp['source_url'] = 'javascript:alert(1)'
        markup = build_pe_conditions_markup({'lp': lp})
        self.assertNotIn('href="javascript:', markup)

    def test_pricing_uses_matched_gf_population(self):
        with tempfile.TemporaryDirectory() as d:
            pricing = c.build_pe_us_conditions(Path(d))['valuation']
            self.assertEqual(pricing['value'], 7.0)
            self.assertEqual(pricing['period'], '2026Q2')
            self.assertEqual(pricing['quarter_change'], -0.3)
            self.assertEqual(pricing['sample_count'], 85)

    def test_retained_state_takes_precedence(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / c.LP_NAME).write_bytes((c.SEED / c.LP_NAME).read_bytes())
            r = c.build_pe_us_conditions(base)
            self.assertEqual(r['lp']['year'], 2025)

    def test_no_remote_source_reads_from_public_analytics(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('Public runtime fetched provider')):
            self.assertIn('lp', c.build_pe_us_conditions(Path(tempfile.gettempdir()) / 'missing-pe-state'))

    def test_mismatched_reported_ratio_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / c.LP_NAME
            s = (c.SEED / c.LP_NAME).read_text().replace('1.2759', '8.2759')
            p.write_text(s)
            with self.assertRaises(c.InvalidPEObservation):
                c.validated_rows(p, 'cambridge')
            self.assertEqual(c.build_pe_us_conditions(Path(d))['lp'], {})

    def test_ambiguous_future_report_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / c.EXIT_NAME
            p.write_text((c.SEED / c.EXIT_NAME).read_text().replace('2026-06-30','2099-06-30'))
            with self.assertRaises(c.InvalidPEObservation):
                c.validated_rows(p, 'kpmg')

    def test_historical_revision_held(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            p = base / c.LP_NAME
            p.write_text((c.SEED / c.LP_NAME).read_text().replace('174.0,143.0','175.0,143.0'))
            before = p.read_bytes()
            with patch.dict(os.environ, {'AI_MACRO_MODE':'automation'}), patch.object(retained.probe,'fetch',side_effect=fake_fetch):
                reports = retained.refresh(out_dir=base,current_year=2026)
            self.assertEqual(reports[0]['status'],'retained_on_failure')
            self.assertEqual(p.read_bytes(),before)
            self.assertEqual(reports[1]['status'],'updated')

    def test_independent_sources_and_readable_staging(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            with patch.object(retained.probe,'fetch',side_effect=fake_fetch):
                reports = retained.refresh(out_dir=base,current_year=2026)
            self.assertEqual([x['status'] for x in reports], ['updated','updated'])
            self.assertEqual(len(c.validated_rows(base/c.LP_NAME,'cambridge')),2)
            self.assertEqual(len(c.validated_rows(base/c.EXIT_NAME,'kpmg')),2)

    def test_second_refresh_preserves_unchanged_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            with patch.object(retained.probe,'fetch',side_effect=fake_fetch):
                retained.refresh(out_dir=base,current_year=2026)
                reports = retained.refresh(out_dir=base,current_year=2026)
            self.assertEqual([x['status'] for x in reports], ['unchanged','unchanged'])

    def test_outage_retains_both_sources(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            with patch.object(retained.probe,'fetch',side_effect=fake_fetch):
                retained.refresh(out_dir=base,current_year=2026)
            before = {f:p.read_bytes() for f in (c.LP_NAME,c.EXIT_NAME) for p in [base/f]}
            with patch.object(retained.probe,'fetch',side_effect=OSError('blocked')):
                reports=retained.refresh(out_dir=base,current_year=2026)
            self.assertEqual([x['status'] for x in reports],['retained_on_failure','retained_on_failure'])
            self.assertEqual(before,{f:(base/f).read_bytes() for f in before})

    def test_prod_writes_not_authorized_locally(self):
        with patch.dict(os.environ, {'AI_MACRO_MODE':'public'}):
            with self.assertRaises(PermissionError):
                retained.refresh(out_dir=retained.PRODUCTION,current_year=2026)

    def test_one_compact_pe_section_other_finance_untouched(self):
        code = (ROOT/'rendering/finance.py').read_text()
        self.assertEqual(code.count('            "Private equity", "Cash in • cash out • ROI",'),1)
        for unwanted in ('finance-section-pe-market','finance-section-private','private_capital_realization_map'):
            self.assertNotIn(unwanted,code)
        for key in ('finance-section-funding','finance-section-disclosures','finance-section-credit','finance-section-stress'):
            self.assertIn(key,code)
        self.assertIn('render_domain_read(tab_read, label="Read", domain="finance")',code)
        self.assertIn('render_finance_facts([',code)

    def test_reader_receives_facts_without_extra_ai_call(self):
        state = (ROOT/'analytics/domain_state.py').read_text()
        evidence = (ROOT/'analytics/read_evidence.py').read_text()
        for key in ('pe_lp_distribution_to_call_ratio','pe_us_exit_value_change_pct','pe_us_entry_quarter_change'):
            self.assertIn(key,state)
            self.assertIn(key,evidence)
        self.assertNotIn('"private_capital_dpi"', evidence)

    def test_refresh_uses_existing_graph_and_reports(self):
        graph = (ROOT/'automation/refresh_graph.py').read_text()
        research = (ROOT/'automation/research_refresh.py').read_text()
        self.assertIn('RefreshNodeSpec("pe_us_liquidity", 168.0',graph)
        self.assertIn('"pe_us_liquidity": pe_us_report',research)
        self.assertIn('plan.should_refresh("pe_us_liquidity")',research)
        self.assertNotIn('OpenAI(', (ROOT/'loaders/pe_us_liquidity_retained.py').read_text())


if __name__ == '__main__':
    unittest.main()
