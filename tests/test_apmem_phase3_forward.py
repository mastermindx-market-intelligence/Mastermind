import unittest
import hashlib
import json
import numpy as np
import pandas as pd
from research.apmem_shadow.phase3.forward import maturity_scores,score_captured_outcomes,validate_capture_roster,prefix_digest
from research.apmem_shadow.phase3.data import prepare_prices

class ForwardMaturityTests(unittest.TestCase):
    def fixture(self):
        dates=pd.bdate_range('2026-11-16',periods=20)
        record={'instrument':'TEST','status':'RECORDED_RESEARCH','origin_session':'2026-11-13',
                'expected_future_sessions':[str(x.date()) for x in dates],
                'forecasts':{'mem':{'mean_daily_variance':{'1':.0004,'5':.0004,'20':.0004}}}}
        p=pd.DataFrame({'variance':.0004,'return_log':.02},index=dates)
        return record,p
    def test_no_future_outcome_is_invented(self):
        r,p=self.fixture();p.index=p.index-pd.Timedelta(days=100)
        out=maturity_scores(r,p,instrument='TEST',model='mem')
        self.assertEqual([x['status'] for x in out],['NOT_MATURED']*3)
    def test_only_matured_horizon_scored(self):
        r,p=self.fixture();out=maturity_scores(r,p.iloc[:5],instrument='TEST',model='mem')
        self.assertEqual(out[-1]['status'],'NOT_MATURED')
        self.assertEqual(sum(x['status']=='MATURED_OBSERVATION_ONLY' for x in out),4)
    def test_exact_forecast_zero_loss(self):
        r,p=self.fixture();out=maturity_scores(r,p,instrument='TEST',model='mem')
        for x in out:self.assertAlmostEqual(x['qlike'],0.)
    def test_missing_session_not_zero(self):
        r,p=self.fixture();out=maturity_scores(r,p.drop(p.index[2]),instrument='TEST',model='mem')
        self.assertEqual(out[-1]['status'],'MISSING_REALIZED_SESSION')
    def test_instrument_binding(self):
        r,p=self.fixture()
        with self.assertRaises(ValueError):maturity_scores(r,p,instrument='OTHER',model='mem')
    def test_invalid_future_calendar(self):
        r,p=self.fixture();r['expected_future_sessions'][0]='2026-11-13'
        with self.assertRaises(ValueError):maturity_scores(r,p,instrument='TEST',model='mem')


class BoundFutureSourceTests(unittest.TestCase):
    def fixture(self):
        dates=pd.bdate_range('2026-11-11',periods=5)
        rows=[{'date':str(d.date())+'T00:00:00.000Z','open':100.,'high':101.,'low':99.,'close':100.,
               'volume':1e6,'divCash':0.,'splitFactor':1.} for d in dates]
        raw=json.dumps(rows).encode()
        receipt={'instrument':'TEST','raw_sha256':hashlib.sha256(raw).hexdigest(),'rows':5,
                 'captured_at':'2026-11-18T12:00:00Z','historical_first_availability':None,
                 'request_path':'/tiingo/daily/TEST/prices?startDate=2010-01-01&endDate=2026-11-17'}
        p=prepare_prices(pd.DataFrame({'open':100.,'high':101.,'low':99.,'close':100.,'volume':1e6,
                                      'dividend':0.,'split':1.},index=dates))
        future=pd.bdate_range('2026-11-16',periods=20)
        record={'instrument':'TEST','status':'RECORDED_RESEARCH','origin_session':'2026-11-13',
                'expected_future_sessions':[str(d.date()) for d in future],
                'lineage':{'prefix_sha256':prefix_digest(p.signal_close.loc[:'2026-11-13'])},
                'forecasts':{'mem':{'mean_daily_variance':{'1':.0004,'5':.0004,'20':.0004}}}}
        frozen=json.dumps(record).encode()
        return frozen,hashlib.sha256(frozen).hexdigest(),raw,receipt
    def test_prefix_digest_ignores_pandas_names_but_not_prices(self):
        p=pd.Series([100.,101.],index=pd.date_range('2026-11-11',periods=2),name='close')
        q=p.copy();q.index.name='date';q.name='signal_close'
        self.assertEqual(prefix_digest(p),prefix_digest(q))
        q.iloc[-1]=102.;self.assertNotEqual(prefix_digest(p),prefix_digest(q))
    def test_bound_source_only_matured(self):
        args=self.fixture();out=score_captured_outcomes(*args,model='mem',now='2026-11-18T13:00:00Z')
        self.assertEqual(out['scores'][-1]['status'],'NOT_MATURED');self.assertFalse(out['may_trade'])
    def test_forecast_digest_change_refused(self):
        frozen,digest,raw,receipt=self.fixture()
        with self.assertRaises(ValueError):score_captured_outcomes(frozen+b' ',digest,raw,receipt,model='mem',now='2026-11-18T13:00:00Z')
    def test_revision_does_not_rewrite_forecast(self):
        frozen,digest,raw,receipt=self.fixture();rows=json.loads(raw)
        rows[0].update(open=110.,high=111.,low=109.,close=110.)
        raw=json.dumps(rows).encode();receipt['raw_sha256']=hashlib.sha256(raw).hexdigest()
        out=score_captured_outcomes(frozen,digest,raw,receipt,model='mem',now='2026-11-18T13:00:00Z')
        self.assertEqual(out['status'],'SOURCE_REVISION_DETECTED');self.assertEqual(out['scores'],[])
    def test_future_capture_clock_refused(self):
        args=self.fixture()
        with self.assertRaises(ValueError):score_captured_outcomes(*args,model='mem',now='2026-11-18T11:00:00Z')


class FixedRosterTests(unittest.TestCase):
    def test_complete_roster_keeps_failed_capture(self):
        s={'origin_session':'2026-11-13','instruments':['AAA','BBB']}
        c=[{'instrument':'AAA','status':'CAPTURED'},{'instrument':'BBB','status':'CAPTURE_FAILED'}]
        self.assertEqual(validate_capture_roster(s,c,'2026-11-13'),['AAA','BBB'])
    def test_missing_duplicate_foreign_are_refused(self):
        s={'origin_session':'2026-11-13','instruments':['AAA','BBB']}
        for names in (['AAA'],['AAA','AAA'],['AAA','CCC']):
            c=[{'instrument':x,'status':'CAPTURED'} for x in names]
            with self.assertRaises(ValueError):validate_capture_roster(s,c,'2026-11-13')
    def test_origin_mismatch_refused(self):
        with self.assertRaises(ValueError):validate_capture_roster({'origin_session':'2026-11-12','instruments':['AAA']},[],'2026-11-13')

if __name__=='__main__':unittest.main()
