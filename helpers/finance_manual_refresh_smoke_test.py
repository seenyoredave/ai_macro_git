"""Offline contracts for owner-initiated local Finance retrieval."""
from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.load_policy import RefreshSource, build_load_policy
from developer.state import (DOMAIN_REFRESH_LABELS, SOURCE_REFRESH_LABELS,
                             request_domain_refresh, request_source_refresh,
                             request_all_source_refreshes)
from loaders import finance_domain_refresh as manual


class FinanceRefreshTests(unittest.TestCase):
    def test_finance_is_developer_domain(self):
        self.assertEqual(DOMAIN_REFRESH_LABELS['finance'], 'Finance')
        state = {}
        request_domain_refresh(state, 'finance')
        self.assertTrue(state['force_rebuild'])
        self.assertEqual(state['domain_refresh_request'], 'finance')
        self.assertEqual(state['domain_refresh_tokens']['finance'], 1)

    def test_source_refresh_is_provider_only(self):
        self.assertNotIn('finance', SOURCE_REFRESH_LABELS)
        self.assertEqual(set(SOURCE_REFRESH_LABELS), {'yfinance', 'edgar', 'fred', 'nyfed'})
        with self.assertRaises(KeyError):
            request_source_refresh({}, 'finance')

        for action in (lambda state: request_source_refresh(state, 'fred'),
                       request_all_source_refreshes):
            state = {}
            action(state)
            self.assertNotIn('domain_refresh_request', state)
            self.assertTrue(state['force_rebuild'])
            self.assertEqual(state['developer_last_operation']['kind'], 'source_refresh')

        state = {}
        request_domain_refresh(state, 'finance')
        self.assertEqual(state['domain_refresh_request'], 'finance')
        self.assertEqual(state['developer_last_operation']['kind'], 'domain_refresh')

    def test_local_authorization_covers_all_shared_finance_sources(self):
        with patch('config.load_policy.repository_writes_enabled', return_value=True):
            policy = build_load_policy(refresh_domains={'finance'})
        for source in (RefreshSource.FINANCE, RefreshSource.YFINANCE,
                       RefreshSource.EDGAR, RefreshSource.FRED, RefreshSource.NYFED):
            self.assertTrue(policy.allows_live(source), source)

    def test_public_has_no_refresh_authorization(self):
        with patch('config.load_policy.repository_writes_enabled', return_value=False):
            policy = build_load_policy(refresh_domains={'finance'})
        self.assertTrue(policy.is_read_mode)
        with patch.object(manual, 'repository_writes_enabled', return_value=False):
            with self.assertRaises(PermissionError):
                manual.refresh_finance_pe_sources()

    def test_no_provider_refresh_without_explicit_finance_request(self):
        with patch('config.load_policy.repository_writes_enabled', return_value=True):
            self.assertTrue(build_load_policy().is_read_mode)
            self.assertFalse(build_load_policy(refresh_domains={'compute'}).allows_live(RefreshSource.FINANCE))

    def test_industry_and_liquidity_independent_and_locally_retained(self):
        # The normal publisher functions are reused; network is not exercised.
        import types
        fake_industry = types.ModuleType('loaders.pe_industry_pipeline')
        fake_industry.source_candidate = lambda name: ([{'source': name}], [])
        fake_industry.validate_observations = lambda rows, name: rows
        fake_industry.persist_source = lambda name, frame, path: {'source': name, 'status': 'unchanged'}
        with patch.object(manual, 'repository_writes_enabled', return_value=True), \
             patch.dict(sys.modules, {'loaders.pe_industry_pipeline': fake_industry}), \
             patch.object(manual, 'refresh_liquidity', return_value=[{'source':'cambridge','status':'updated'},
                                                                     {'source':'kpmg','status':'retained_on_failure','error':'blocked'}]), \
             patch.object(manual, 'refresh_returns', return_value={'source':'cambridge_return','status':'unchanged'}), \
             patch.object(manual, '_record_successful_retrievals') as record:
            report = manual.refresh_finance_pe_sources()
        self.assertEqual(len(report['industry']),2)
        self.assertEqual(len(report['liquidity']),3)
        self.assertEqual(report['source_mode'],'partial_refresh')
        self.assertEqual(report['errors'], {'kpmg':'blocked'})
        self.assertEqual(record.call_count, 2)

    def test_retrieval_timestamp_requires_success(self):
        fixed = datetime(2026,10,19,18,0,tzinfo=timezone.utc)
        with patch.object(manual, 'load_refresh_graph_state', return_value={'nodes':{'edgar':{'last_success_at_utc':'prior'}}}), \
             patch.object(manual, 'save_refresh_graph_state') as save, \
             patch.object(manual, 'utc_now', return_value=fixed):
            manual._record_successful_retrievals([{'status':'retained_on_failure'}],node='pe_industry')
            save.assert_not_called()
            manual._record_successful_retrievals([{'status':'unchanged'}],node='pe_industry')
            state=save.call_args.args[0]
            self.assertEqual(state['nodes']['pe_industry']['last_retrieval_at_utc'],fixed.isoformat())
            self.assertEqual(state['nodes']['edgar']['last_success_at_utc'],'prior')

    def test_finance_app_routes_all_callable_sources(self):
        source=(ROOT/'ai_macro.py').read_text(encoding='utf-8')
        ast.parse(source)
        self.assertIn('finance_refresh = refreshing("finance")', source)
        for required in ('force_yfinance_refresh=st.session_state.force_yfinance_refresh or finance_refresh',
                         'force_edgar_refresh=st.session_state.force_edgar_refresh or finance_refresh',
                         'force_refresh=st.session_state.force_fred_refresh or finance_refresh',
                         'force_refresh=st.session_state.force_nyfed_refresh or finance_refresh',
                         'commercialization_refresh = bool(refresh_domains & commercialization_domains) or finance_refresh',
                         'pe_refresh_report = refresh_finance_pe_sources()',
                         'edgar_refresh_token=max(st.session_state.edgar_refresh_token, finance_token)'):
            self.assertIn(required, source)


if __name__ == '__main__':
    unittest.main(verbosity=2)
