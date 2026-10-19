"""Full source API tests, runnable in the official Mastermind workspace.

No substituted FastAPI/portfolio modules: missing application dependencies are
reported as a skip/blocker. The injected clock calls the real local feed reader.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from brain import sovereign_auction_context as SAC

FIX = Path(__file__).parent / 'fixtures/sovereign_auction_context/event_calendar.json'
NOW = '2026-10-08T23:00:00Z'


def frozen_view():
    return {'schema_version': 'market_view.v1', 'asof': '2026-10-08', 'seq': 42,
            'planes': {'event_calendar': {'direction': None, 'magnitude': None, 'status': 'advisory',
                                          'raw': {'present': False, 'note': 'H4 absent'}}},
            'net_posture_tilt': {'tilt': 0, 'direction': 'neutral', 'n_validated': 0, 'contributors': []},
            'label_vs_planes': {'conflict': False}, 'coverage': 0, 'coherence': 0,
            'assembly': {'present': 0, 'total': 1, 'fresh': 0, 'stale': 0, 'missing': 1,
                         'decision_coverage': 0, 'fresh_coverage': 0, 'degraded': True},
            'brief': {'posture_implication': 'unchanged'}, 'disagreements': []}


class SovereignAuctionAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from app import web
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f'Full application import blocked: {exc}') from exc
        cls.web = web

    def test_actual_api_sibling_preserves_stored_bytes_authority_and_fresh_reads(self):
        original_reader = SAC.read_context
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); stored = root / 'data/market_view/latest.json'
            stored.parent.mkdir(parents=True)
            raw = json.dumps(frozen_view(), indent=2).encode(); stored.write_bytes(raw)
            feed = root / 'vendor/macro/site/feeds/event_calendar.json'; feed.parent.mkdir(parents=True)
            feed.write_bytes(FIX.read_bytes())
            with patch.object(self.web, '_PROJECT_ROOT', root), patch.object(SAC, 'read_context', side_effect=lambda path: original_reader(path, now=NOW)):
                response = self.web.api_market_view()
                served = json.loads(response.body)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers['cache-control'], self.web._NOCACHE['Cache-Control'])
                sibling = served.pop('sovereign_auction_context')
                self.assertTrue(sibling['available'])
                self.assertEqual(served, frozen_view())
                self.assertEqual(stored.read_bytes(), raw)
                feed.write_text('{}')
                absent = json.loads(self.web.api_market_view().body)
                self.assertFalse(absent['sovereign_auction_context']['available'])
                self.assertEqual(stored.read_bytes(), raw)

    def test_actual_api_missing_or_corrupt_market_view_keeps_status(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(self.web, '_PROJECT_ROOT', Path(directory)):
            missing = self.web.api_market_view()
            self.assertEqual(missing.status_code, 404)
            self.assertNotIn('sovereign_auction_context', json.loads(missing.body))
            stored = Path(directory) / 'data/market_view/latest.json'; stored.parent.mkdir(parents=True)
            stored.write_text('not JSON')
            self.assertEqual(self.web.api_market_view().status_code, 500)

    def test_display_helper_failure_cannot_change_authority(self):
        view = frozen_view(); before = copy.deepcopy(view)
        with patch.object(SAC, 'read_context', side_effect=RuntimeError('display failed')):
            self.web._enrich_sovereign_auction_context(view)
        self.assertFalse(view.pop('sovereign_auction_context')['available'])
        self.assertEqual(view, before)

    def test_hostile_sibling_does_not_change_decision_prompt_or_crash_leg(self):
        from brain import anticipation, decision_context, pm_conviction
        stored = frozen_view()
        served = copy.deepcopy(stored)
        served['sovereign_auction_context'] = {**SAC.validate_context(json.loads(FIX.read_text())['sovereign_auction_context'], now=NOW),
                                             'band': 'critical', 'stressed': True}
        regime = {'date': '2026-10-08', 'quad': 'Q1', 'confidence': .6}
        before = decision_context.assemble(regime, stored, built_at=NOW)
        after = decision_context.assemble(regime, served, built_at=NOW)
        self.assertEqual(before, after)
        self.assertEqual(decision_context.prompt_summary(before), decision_context.prompt_summary(after))
        self.assertEqual(pm_conviction._market_view_enrichment(stored), pm_conviction._market_view_enrichment(served))
        self.assertEqual(json.dumps(decision_context.prompt_summary(before), separators=(',', ':')),
                         json.dumps(decision_context.prompt_summary(after), separators=(',', ':')))
        for base in ({}, {'auction_stress': {'band': 'low'}}, {'treasury_auctions': {'stressed': False}},
                     {'auction_stress': {'stressed': True}}):
            hostile = {**base, 'sovereign_auction_context': served['sovereign_auction_context']}
            self.assertEqual(anticipation._crash_auction_leg(base), anticipation._crash_auction_leg(hostile))
        self.assertEqual(stored, frozen_view())


if __name__ == '__main__':
    unittest.main()
