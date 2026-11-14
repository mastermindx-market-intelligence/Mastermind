import copy,hashlib,json,unittest
from pathlib import Path
import numpy as np
import pandas as pd
from forward_adapter import adapt_capture,compare_overlap
from risk_observation import FixedRiskOwner,validate_risk_record

class CurrentCaptureTests(unittest.TestCase):
    def raw(self):
        rows=[]
        for date,p,s,div in [('2026-11-11',100.,1.,2.),('2026-11-12',50.,2.,0.),('2026-11-13',51.,1.,0.)]:
            rows.append({'date':date+'T00:00:00.000Z','open':p,'high':p*1.01,'low':p*.99,'close':p,
                        'adjClose':p if s!=1 or date.endswith('13') else p/2,'divCash':div,'splitFactor':s,'volume':1000})
        raw=json.dumps(rows).encode();receipt={'vendor':'tiingo','source':'eod-bars','symbol':'MCD',
          'raw_sha256':hashlib.sha256(raw).hexdigest(),'receipt_id':'synthetic_owner_receipt',
          'observed_at_utc':'2026-11-14T11:00:00+00:00',
          'request_path':'/tiingo/daily/MCD/prices?endDate=2026-11-13&startDate=2023-06-01'}
        return raw,receipt
    def adapt(self,raw,receipt):return adapt_capture(raw,receipt,'MCD',['MCD'])
    def test_split_factor_applies_only_to_prior_units(self):
        raw,r=self.raw();x,m=self.adapt(raw,r)
        np.testing.assert_allclose(x.close,[50,50,51]);np.testing.assert_allclose(x.dividends,[1,0,0])
        self.assertEqual(x.source_split_factor.iloc[1],2);self.assertTrue((x.stock_splits==0).all());self.assertEqual(m['ordinary_action_count'],1)
    def test_raw_payload_unmodified(self):
        raw,r=self.raw();old=copy.deepcopy(r);self.adapt(raw,r);self.assertEqual(r,old);self.assertEqual(json.loads(raw)[0]['close'],100.)
    def test_unsupported_action_quarantined(self):
        raw,r=self.raw();rows=json.loads(raw);rows[1]['splitFactor']=1.006;raw=json.dumps(rows).encode();r['raw_sha256']=hashlib.sha256(raw).hexdigest()
        with self.assertRaises(ValueError):self.adapt(raw,r)
    def test_wrong_source_digest_refused(self):
        raw,r=self.raw();r['raw_sha256']='a'*64
        with self.assertRaises(ValueError):self.adapt(raw,r)
    def test_stale_origin_refused(self):
        raw,r=self.raw();rows=json.loads(raw)[:-1];raw=json.dumps(rows).encode();r['raw_sha256']=hashlib.sha256(raw).hexdigest()
        with self.assertRaises(ValueError):self.adapt(raw,r)
    def test_historical_window_not_reopened(self):
        raw,r=self.raw();r['request_path']=r['request_path'].replace('2023-06-01','2010-01-01')
        with self.assertRaises(ValueError):self.adapt(raw,r)
    def test_bad_range_refused(self):
        raw,r=self.raw();rows=json.loads(raw);rows[-1]['high']=40;raw=json.dumps(rows).encode();r['raw_sha256']=hashlib.sha256(raw).hexdigest()
        with self.assertRaises(ValueError):self.adapt(raw,r)
    def test_boolean_quote_refused(self):
        raw,r=self.raw();rows=json.loads(raw);rows[-1]['close']=True;raw=json.dumps(rows).encode();r['raw_sha256']=hashlib.sha256(raw).hexdigest()
        with self.assertRaises(ValueError):self.adapt(raw,r)
    def test_capture_before_session_end_refused(self):
        raw,r=self.raw();r['observed_at_utc']='2026-11-13T15:00:00+00:00'
        with self.assertRaises(ValueError):self.adapt(raw,r)
    def test_cross_provider_disagreement_refused(self):
        idx=pd.bdate_range('2025-01-02',periods=200);new=pd.DataFrame({'close':100.},index=idx);old=pd.Series(101.,index=idx)
        with self.assertRaises(ValueError):compare_overlap(new,old)
    def test_cross_provider_agreement_qualified(self):
        idx=pd.bdate_range('2025-01-02',periods=200);new=pd.DataFrame({'close':100.},index=idx);old=pd.Series(100.,index=idx)
        self.assertTrue(compare_overlap(new,old)['qualified'])

class RiskContractTests(unittest.TestCase):
    def record(self):
        v=np.array([.0001,.0002,.0003])
        return {'origin':'2026-11-13','training_end':'2026-11-13','may_rank':False,'may_size':False,'may_trade':False,
          'bounds_are_prediction_intervals':False,'variance_units':'squared_daily_return','volatility_units':'annualized_decimal_252_sessions',
          'status':'RECORDED_RESEARCH','forecasts':{'horizons':[1,5,20],'mean_daily_variance':v.tolist(),'annualized_volatility':np.sqrt(252*v).tolist()}}
    def test_valid_variance_units(self):validate_risk_record(self.record(),'2026-11-13')
    def test_percent_decimal_confusion_refused(self):
        r=self.record();r['forecasts']['annualized_volatility']=[10,20,30]
        with self.assertRaises(ValueError):validate_risk_record(r,'2026-11-13')
    def test_horizon_mismatch_refused(self):
        r=self.record();r['forecasts']['horizons']=[1,5,21]
        with self.assertRaises(ValueError):validate_risk_record(r,'2026-11-13')
    def test_forecast_not_trade_authority(self):
        r=self.record();r['may_size']=True
        with self.assertRaises(ValueError):validate_risk_record(r,'2026-11-13')
    def test_mean_bound_not_loss_bound(self):
        r=self.record();r['bounds_are_prediction_intervals']=True
        with self.assertRaises(ValueError):validate_risk_record(r,'2026-11-13')
    def test_failed_fit_no_fabricated_forecast(self):
        r=self.record();r['status']='FIT_FAILED'
        with self.assertRaises(ValueError):validate_risk_record(r,'2026-11-13')

class NativeRiskMathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).parent/'source/phase2_runtime'
        if not (root/'SOURCE_MANIFEST.json').exists():raise unittest.SkipTest('Pinned volatility runtime not installed in portable test')
        cls.owner=FixedRiskOwner(root)
    def test_uniform_share_unit_change_preserves_risk_target(self):
        rng=np.random.default_rng(17);c=100*np.exp(np.cumsum(rng.normal(0,.01,200)));index=pd.bdate_range('2018-01-02',periods=200)
        p=pd.DataFrame({'open':c*.999,'high':c*1.01,'low':c*.99,'close':c,'dividends':0.,'stock_splits':0.},index=index)
        q=p.copy();q[['open','high','low','close','dividends']]/=10
        a=self.owner.targets.prepare_prices(p);b=self.owner.targets.prepare_prices(q)
        np.testing.assert_allclose(a.variance,b.variance,rtol=1e-10,atol=1e-14)
    def test_current_fixed_power_forecast_contract(self):
        rng=np.random.default_rng(91);c=100*np.exp(np.cumsum(rng.normal(.0002,.01,550)));index=pd.bdate_range('2016-01-04',periods=550)
        p=pd.DataFrame({'open':c*.999,'high':c*1.01,'low':c*.99,'close':c,'dividends':0.,'stock_splits':0.},index=index)
        origin=str(index[-1].date());record=self.owner.observe(p,origin);validate_risk_record(record,origin)
        self.assertEqual(record['training_rows'],504);self.assertFalse(record['may_trade'])

if __name__=='__main__':unittest.main()
