"""Synthetic fixtures verify mechanics only, never market performance."""
from datetime import date, datetime, timedelta, timezone
from dataclasses import replace
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from research.apmem_shadow.model import (Parameters, Fit, filter_variance,
    adjusted_range, fit_qml, walk_forward, qlike)
from research.apmem_shadow.evaluation import (validate_prices, fixed_events,
    long_cash_replay, event_outcomes, score_exposure, known_correction_forecast)
from research.apmem_shadow.consumer import SourceObservation, ModelObservation, shadow_context


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.p = Parameters(.000001, .1, .8, .2, 1.)

    def test_one_step(self):
        x = filter_variance([.0002], [-.01], self.p, .0001)
        self.assertAlmostEqual(x[-1], .000105)

    def test_negative_asymmetry(self):
        neg = filter_variance([.0002], [-.01], self.p, .0001)
        pos = filter_variance([.0002], [.01], self.p, .0001)
        self.assertGreater(neg[-1], pos[-1])

    def test_linear_filter_scalar_equivalence(self):
        p = Parameters(.01, .1, .8, .3, 1.3)
        v = np.linspace(.1, 2, 100); r = np.sin(np.arange(100))*.01
        expected = [1.]
        for a, b in zip(v, r):
            expected.append((p.omega+p.alpha*(a*(1-p.gamma*np.sign(b)))**p.delta+
                             p.beta*expected[-1]**p.delta)**(1/p.delta))
        np.testing.assert_allclose(filter_variance(v, r, p, 1.), expected, rtol=1e-12)

    def test_suffix_does_not_change_past(self):
        v = np.ones(100)*.0002; r = np.ones(100)*.01
        a = filter_variance(v, r, self.p, .0001)
        v[60:] *= 100; r[60:] *= -1
        np.testing.assert_array_equal(a[:61], filter_variance(v, r, self.p, .0001)[:61])

    def test_reject_bad_values(self):
        for v in ([0.], [-1.], [float('nan')], [float('inf')]):
            with self.assertRaises(ValueError): filter_variance(v, [.1], self.p, .001)

    def test_reject_bad_parameters(self):
        for p in (replace(self.p, gamma=1), replace(self.p, delta=0), replace(self.p, omega=-1)):
            with self.assertRaises(ValueError): filter_variance([.1], [.1], p, .1)

    def test_shape_guard(self):
        with self.assertRaises(ValueError): filter_variance([.1,.1], [.1], self.p, .1)

    def test_adjustment_scalar_formula(self):
        h=np.array([102., 104., 103.]); l=np.array([99., 100., 98.]); r=np.array([.01,-.02,.03])
        raw=np.log(h/l)**2/(4*np.log(2))
        out,meta=adjusted_range(h,l,r,.05)
        self.assertAlmostEqual(out[0],r[0]**2)
        self.assertAlmostEqual(out[1],raw[1]*r[0]**2/raw[0])
        num=.95*r[1]**2+.05*r[0]**2; den=.95*raw[1]+.05*raw[0]
        self.assertAlmostEqual(out[2],raw[2]*num/den)
        self.assertEqual(meta['floored_rows'],0)

    def test_adjustment_causal(self):
        h=np.ones(100)*102; l=np.ones(100)*99; r=np.linspace(-.03,.03,100)
        a,_=adjusted_range(h,l,r)
        h[60:]=110; r[60:]=.2
        b,_=adjusted_range(h,l,r)
        np.testing.assert_array_equal(a[:60],b[:60])

    def test_zero_return_floor_disclosed(self):
        v,meta=adjusted_range([2,2],[1,1],[0,0])
        self.assertEqual(meta['floored_rows'],2)
        self.assertTrue((v>0).all())

    def test_zero_range_rejected(self):
        with self.assertRaises(ValueError): adjusted_range([1],[1],[0])

    def test_qlike_identity(self):
        np.testing.assert_array_equal(qlike([1,2,3],[1,2,3]), [0,0,0])
        self.assertTrue((qlike([1,2],[2,1])>0).all())

    def test_fit_reject_short(self):
        with self.assertRaises(ValueError): fit_qml([1]*20,[.1]*20)

    def test_fit_is_deterministic(self):
        rng=np.random.default_rng(18)
        v=np.exp(rng.normal(0,.3,96)); r=rng.normal(0,.01,96)
        a=fit_qml(v,r); b=fit_qml(v,r)
        self.assertEqual(a.success,b.success); self.assertTrue(a.success)
        self.assertEqual(a.parameters,b.parameters); self.assertEqual(a.input_sha256,b.input_sha256)

    def test_walkforward_schedule_and_suffix(self):
        p=Parameters(.01,.1,.8,.2,1.)
        calls=[]
        def fake(v,r,**kwargs):
            calls.append(len(v));return Fit(p,1.,1.,True,len(v),'a'*64,())
        v=np.linspace(.5,1.5,180); r=np.ones(180)*.01
        with patch('research.apmem_shadow.model.fit_qml',side_effect=fake):
            a,records=walk_forward(v,r,minimum=64,window=80,refit_every=25)
            v[120:]*=100; r[120:]*=-1
            b,_=walk_forward(v,r,minimum=64,window=80,refit_every=25)
        np.testing.assert_array_equal(a[:120],b[:120])
        self.assertEqual([z['train_end_index'] for z in records],[63,88,113,138,163])
        self.assertTrue(all(n<=80 for n in calls));self.assertTrue(np.isnan(a[:63]).all())

    def test_failed_fit_remains_missing(self):
        bad=Fit(None,1.,None,False,64,'a'*64,())
        with patch('research.apmem_shadow.model.fit_qml',return_value=bad):
            a,records=walk_forward(np.ones(100),np.ones(100),minimum=64)
        self.assertTrue(np.isnan(a).all());self.assertFalse(records[0]['success'])


class EvaluationTests(unittest.TestCase):
    def prices(self,n=400):
        return pd.DataFrame({'open':100.,'high':102.,'low':98.,'close':100.},
                            index=pd.bdate_range('2020-01-01',periods=n))

    def test_known_correction_forecast_manual_and_causal(self):
        h=np.array([102.,104.,105.,106.]);l=np.array([99.,100.,101.,102.]);r=np.array([.01,-.02,.03,-.01])
        raw=np.log(h/l)**2/(4*np.log(2));c=.05
        f=known_correction_forecast(h,l,r,c)
        self.assertAlmostEqual(f[0],r[0]**2)
        correction=(.95*r[1]**2+.05*r[0]**2)/(.95*raw[1]+.05*raw[0])
        self.assertAlmostEqual(f[1],(.06*raw[1]+.94*raw[0])*correction)
        r[2:]*=30;h[2:]*=2
        np.testing.assert_array_equal(f[:2],known_correction_forecast(h,l,r,c)[:2])

    def test_risk_measures_include_cash_and_fees(self):
        p=np.array([100.,102.,101.,104.]);w=np.ones(3)
        z=score_exposure(p,w,0)
        r=p[1:]/p[:-1]-1
        self.assertAlmostEqual(z['annualized_open_mark_volatility'],np.std(r,ddof=1)*np.sqrt(252))
        self.assertAlmostEqual(z['zero_cash_rate_sharpe'],np.mean(r)/np.std(r,ddof=1)*np.sqrt(252))

    def test_duplicate_dates(self):
        p=self.prices(4);p.index=[p.index[0]]*4
        with self.assertRaises(ValueError):validate_prices(p)

    def test_ohlc_range(self):
        p=self.prices();p.loc[p.index[0],'high']=90
        with self.assertRaises(ValueError):validate_prices(p)

    def test_unsorted(self):
        with self.assertRaises(ValueError):validate_prices(self.prices().iloc[::-1])

    def test_missing_options_abstain_all(self):
        e=fixed_events(self.prices(),np.arange(400.)+1,None)
        self.assertFalse(e.any().any())

    def test_options_shift_preserves_missing_date(self):
        p=self.prices(); opt=pd.DataFrame({'net_gex_bn':np.arange(400.),'iv30':np.linspace(.4,.1,400)},index=p.index)
        opt=opt.drop(p.index[250]);e=fixed_events(p,np.ones(400),opt)
        self.assertFalse(e.loc[p.index[251],'options_available'])
        self.assertFalse(e.loc[p.index[252],'options_available'])

    def test_events_no_future_threshold(self):
        p=self.prices();opt=pd.DataFrame({'net_gex_bn':np.arange(400.),'iv30':np.linspace(.4,.1,400)},index=p.index)
        f=np.linspace(.1,.2,400);a=fixed_events(p,f,opt)
        f[300:]*=100;b=fixed_events(p,f,opt)
        pd.testing.assert_frame_equal(a.iloc[:300],b.iloc[:300])

    def test_next_open_excludes_signal_day_jump(self):
        opens=np.array([100,200,220,242,242,242.]);sig=np.array([True,False,False,False,False,False])
        z=long_cash_replay(opens,sig,holding=2,one_way_cost=0)
        self.assertAlmostEqual(z['total_return'],.21)
        self.assertEqual(z['trades'][0]['entry_index'],1)
        self.assertEqual(z['trades'][0]['exit_index'],3)

    def test_full_delay(self):
        opens=np.array([100,200,220,242,242,242.]);sig=np.array([True,False,False,False,False,False])
        z=long_cash_replay(opens,sig,delay=2,holding=2,one_way_cost=0)
        self.assertAlmostEqual(z['total_return'],.10)

    def test_costs_initial_and_final(self):
        opens=np.ones(6)*100;sig=np.array([True,False,False,False,False,False])
        z=long_cash_replay(opens,sig,holding=20,one_way_cost=.01)
        self.assertAlmostEqual(z['total_return'],.99**2-1)
        self.assertEqual(z['turnover_including_liquidation'],2)
        self.assertTrue(z['trades'][0]['censored'])

    def test_signals_while_occupied_ignored(self):
        z=long_cash_replay(np.ones(8)*100,np.ones(8,dtype=bool),holding=2,one_way_cost=0)
        self.assertEqual(z['exposure'],[0.,1.,1.,0.,1.,1.,0.])

    def test_no_signals_means_cash(self):
        z=long_cash_replay(np.arange(100.,110.),np.zeros(10,dtype=bool))
        self.assertEqual(z['total_return'],0);self.assertEqual(z['trades'],[])

    def test_reject_noncaual_delay_and_nan_flags(self):
        with self.assertRaises(ValueError):long_cash_replay(np.ones(4),np.ones(4,dtype=bool),delay=0)
        with self.assertRaises(ValueError):long_cash_replay(np.ones(4),np.array([True,False,np.nan,False]))

    def test_maturity_open_horizon(self):
        p=np.arange(100.,126.);sig=np.zeros(26,dtype=bool);sig[[0,10,24]]=True
        z=event_outcomes(p,sig,20)
        self.assertEqual(z['matured'],1);self.assertEqual(z['censored'],2)
        self.assertAlmostEqual(z['median_forward_open_return'],121/101-1)

    def test_score_scalar_loop(self):
        p=np.array([100.,110,100,120,115,130]);w=np.array([0.,1,1,0,1]);c=.002
        eq=1.;prev=0
        for i,x in enumerate(w):
            eq*=1-c*abs(x-prev);eq*=1+x*(p[i+1]/p[i]-1);prev=x
        eq*=1-c*w[-1]
        z=score_exposure(p,w,c)
        self.assertAlmostEqual(z['total_return'],eq-1)


class ConsumerTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,13,1,tzinfo=timezone.utc)
        self.price=SourceObservation('QQQ',date(2026,11,12),self.now-timedelta(hours=4),
             self.now-timedelta(minutes=30),'a'*64,'approved-price','raw_ohlc')
        self.options=SourceObservation('QQQ',date(2026,11,11),self.now-timedelta(hours=28),
             self.now-timedelta(minutes=30),'b'*64,'approved-options','gex_bn_iv_annual_decimal',True)
        self.fit=ModelObservation('QQQ',self.price.observed_through,self.now-timedelta(minutes=2),
                                  ('a'*64,),'original-v1',.0001)

    def run_context(self,**kw):
        args=dict(instrument='QQQ',decision_at=self.now,price=self.price,options=self.options,
                  fit=self.fit,expected_options_session=date(2026,11,11));args.update(kw)
        return shadow_context(**args)

    def test_unknown_publication_clocks_are_not_backdated(self):
        z=self.run_context(price=replace(self.price,observed_through=None),fit=replace(self.fit,train_through=None))
        self.assertEqual(z['status'],'ABSTAIN')
        self.assertIsNone(z['forecast_annualized_percent'])

    def test_economic_staleness_with_unknown_clock(self):
        z=self.run_context(options=replace(self.options,economic_session=date(2026,10,1),observed_through=None))
        self.assertIn('OPTIONS_STALE',z['reason_codes'])

    def test_context_not_authority(self):
        z=self.run_context();self.assertEqual(z['status'],'CONTEXT_ONLY')
        for k in ('may_rank','may_size','may_trade'):self.assertIs(z[k],False)
        self.assertAlmostEqual(z['forecast_annualized_percent'],np.sqrt(.0001*252)*100)

    def test_missing_input(self):
        z=self.run_context(options=None);self.assertEqual(z['status'],'ABSTAIN')
        self.assertIsNone(z['forecast_annualized_percent'])

    def test_future_capture(self):
        z=self.run_context(price=replace(self.price,first_observed_at=self.now+timedelta(hours=1)))
        self.assertIn('PRICE_NOT_YET_AVAILABLE',z['reason_codes'])

    def test_stale(self):
        z=self.run_context(options=replace(self.options,observed_through=self.now-timedelta(days=8)))
        self.assertIn('OPTIONS_STALE',z['reason_codes'])

    def test_instrument(self):
        z=self.run_context(options=replace(self.options,instrument='SPY'))
        self.assertIn('OPTIONS_INSTRUMENT_MISMATCH',z['reason_codes'])

    def test_units(self):
        z=self.run_context(options=replace(self.options,units='iv_percent'))
        self.assertIn('OPTIONS_UNITS_MISMATCH',z['reason_codes'])

    def test_wrong_options_session(self):
        z=self.run_context(options=replace(self.options,economic_session=date(2026,11,10)))
        self.assertIn('OPTIONS_SESSION_MISMATCH',z['reason_codes'])

    def test_fit_source_revision(self):
        z=self.run_context(fit=replace(self.fit,input_sha256=('c'*64,)))
        self.assertIn('FIT_SOURCE_MISMATCH',z['reason_codes'])

    def test_fit_before_data_known(self):
        z=self.run_context(fit=replace(self.fit,completed_at=self.now-timedelta(hours=2)))
        self.assertIn('FIT_PRECEDES_INPUT_CAPTURE',z['reason_codes'])

    def test_missing_fit(self):
        z=self.run_context(fit=None);self.assertIn('FIT_MISSING',z['reason_codes'])

    def test_invalid_forecast(self):
        for x in (None,float('nan'),0.,-1.,True):
            z=self.run_context(fit=replace(self.fit,next_daily_variance=x))
            self.assertIn('FORECAST_UNAVAILABLE',z['reason_codes'])

    def test_naive_clock(self):
        with self.assertRaises(ValueError):self.run_context(decision_at=self.now.replace(tzinfo=None))
        z=self.run_context(price=replace(self.price,observed_through=self.now.replace(tzinfo=None)))
        self.assertIn('PRICE_CLOCK_UNKNOWN',z['reason_codes'])

    def test_digest_guard(self):
        z=self.run_context(price=replace(self.price,sha256='not-a-digest'))
        self.assertIn('PRICE_DIGEST_INVALID',z['reason_codes'])

    def test_fit_after_decision(self):
        z=self.run_context(fit=replace(self.fit,completed_at=self.now+timedelta(minutes=1)))
        self.assertIn('FIT_CLOCK_ORDER_INVALID',z['reason_codes'])


if __name__=='__main__':unittest.main()
