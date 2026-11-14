import copy
import unittest
import numpy as np
import pandas as pd
import consumer as c
import test_experiment as fixtures

class ConsumerTests(unittest.TestCase):
    def fixture(self):
        report={'ticker':'XLK','verdict':'knife','buyable':False,'entry_score':10.}
        o={'instrument':'XLK','origin_session':'2026-11-09','source_manifest_sha256':'a'*64,'population':'nine_sector_ETF_proxy',
           'authority':dict(c.AUTHORITY),'calibrated_entry_probability':None,
           'facts':{'market_repair':True,'declining_low_pressure':True,'sector_above126':False,'sector_positive63':False,
                    'vix_rising':None,'vvix_rising':None}}
        return report,o
    def test_positive_context_cannot_upgrade_rejection(self):
        r,o=self.fixture();before=copy.deepcopy(r)
        out=c.attach(r,o,instrument='XLK',expected_session='2026-11-09',expected_source_hash='a'*64)
        self.assertEqual(r,before);self.assertEqual({k:v for k,v in out.items() if k!='independent_recovery_research'},before)
        self.assertFalse(out['buyable']);self.assertEqual(out['entry_score'],10.)
    def test_stale_cannot_be_current(self):
        r,o=self.fixture();out=c.attach(r,o,instrument='XLK',expected_session='2026-11-13',expected_source_hash='a'*64)
        self.assertEqual(out['independent_recovery_research']['status'],'STALE_RESEARCH_CONTEXT')
        self.assertFalse(out['independent_recovery_research']['usable_as_current_context'])
    def test_future_refused(self):
        r,o=self.fixture()
        with self.assertRaises(ValueError):c.attach(r,o,instrument='XLK',expected_session='2026-11-06',expected_source_hash='a'*64)
    def test_wrong_instrument_refused(self):
        r,o=self.fixture()
        with self.assertRaises(ValueError):c.attach(r,o,instrument='XLE',expected_session='2026-11-09',expected_source_hash='a'*64)
    def test_wrong_source_refused(self):
        r,o=self.fixture()
        with self.assertRaises(ValueError):c.attach(r,o,instrument='XLK',expected_session='2026-11-09',expected_source_hash='b'*64)
    def test_authority_override_refused(self):
        r,o=self.fixture();o['authority']['may_trade']=True
        with self.assertRaises(ValueError):c.attach(r,o,instrument='XLK',expected_session='2026-11-09',expected_source_hash='a'*64)
    def test_uncalibrated_probability_refused(self):
        r,o=self.fixture();o['calibrated_entry_probability']=.9
        with self.assertRaises(ValueError):c.attach(r,o,instrument='XLK',expected_session='2026-11-09',expected_source_hash='a'*64)
    def test_missing_is_not_false(self):
        r,o=self.fixture();o['facts'].pop('declining_low_pressure')
        with self.assertRaises(ValueError):c.attach(r,o,instrument='XLK',expected_session='2026-11-09',expected_source_hash='a'*64)
    def test_source_payload_not_mutated(self):
        r,o=self.fixture();old=copy.deepcopy(o)
        out=c.attach(r,o,instrument='XLK',expected_session='2026-11-09',expected_source_hash='a'*64)
        out['independent_recovery_research']['facts']['vix_rising']=True;self.assertEqual(o,old)
    def test_research_reader_preserves_missing_volatility(self):
        p,t,v=fixtures.MechanicsTests().panel();v.VVIX=np.nan
        rows=c.readings(p,t,v,'a'*64)
        self.assertEqual(len(rows),9);self.assertTrue(all(r['facts']['vvix_rising'] is None for r in rows))
        self.assertTrue(all(not any(r['authority'].values()) for r in rows))
    def test_missing_price_and_thin_history_refused(self):
        p,t,v=fixtures.MechanicsTests().panel()
        with self.assertRaises(ValueError):c.readings(p.iloc[:100],t.iloc[:100],v.iloc[:100],'a'*64)
        p.iloc[-1,0]=np.nan
        with self.assertRaises(ValueError):c.readings(p,t,v,'a'*64)
    def test_unbound_populations_refused(self):
        r,o=self.fixture();o['population']='all_US_stock_constituents'
        with self.assertRaises(ValueError):c.attach(r,o,instrument='XLK',expected_session='2026-11-09',expected_source_hash='a'*64)

if __name__=='__main__':unittest.main()
