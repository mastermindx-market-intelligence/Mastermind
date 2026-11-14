"""Hermetic phase3 tests; no provider calls or production configuration."""
from __future__ import annotations
import hashlib
import json
import unittest
from dataclasses import replace
from unittest.mock import patch
import numpy as np
import pandas as pd
from research.apmem_shadow.phase3 import data, labels, learning, portfolio, native, replay, risk


def panel(n=100, price=100.):
    idx=pd.bdate_range('2019-12-02',periods=n)
    return data.prepare_prices(pd.DataFrame({'open':price,'high':price*1.01,'low':price*.99,
                                             'close':price,'volume':1e6,'dividend':0.,'split':1.},index=idx))


def opportunity(p, ticker='TEST', origin=0, identifier='e0', **kwargs):
    row={'event_id':identifier,'ticker':ticker,'origin':str(p.index[origin].date()),
         'family':'union','mem_h5':.0004,'ewma_h5':.0004,'relative_momentum':.1}
    return {**row,**kwargs}


class DataTests(unittest.TestCase):
    def capture(self):
        rows=[{'date':str(d.date())+'T00:00:00.000Z','open':100.,'high':101.,'low':99.,
               'close':100.,'volume':1000000,'divCash':0.,'splitFactor':1.,'adjClose':100.}
              for d in pd.bdate_range('2020-01-02',periods=4)]
        raw=json.dumps(rows).encode()
        rec={'instrument':'TEST','raw_sha256':hashlib.sha256(raw).hexdigest(),'rows':4,
             'request_path':'/tiingo/daily/TEST/prices?startDate=2010-01-01&endDate=2026-11-12',
             'historical_first_availability':None,'captured_at':'2026-11-14T00:00:00Z'}
        return raw,rec

    def test_capture_identity_and_hash(self):
        raw,rec=self.capture();p,a=data.parse_capture(raw,rec,'TEST')
        self.assertEqual(len(p),4);self.assertTrue(a['action_basis_qualified'])
        with self.assertRaises(ValueError):data.parse_capture(raw,rec,'WRONG')
        with self.assertRaises(ValueError):data.parse_capture(raw+b' ',rec,'TEST')

    def test_capture_rejects_boolean_price(self):
        raw,rec=self.capture();rows=json.loads(raw);rows[0]['open']=True
        raw=json.dumps(rows).encode();rec['raw_sha256']=hashlib.sha256(raw).hexdigest()
        with self.assertRaises(ValueError):data.parse_capture(raw,rec,'TEST')

    def test_capture_rejects_duplicate_dates(self):
        raw,rec=self.capture();rows=json.loads(raw);rows[1]['date']=rows[0]['date']
        raw=json.dumps(rows).encode();rec['raw_sha256']=hashlib.sha256(raw).hexdigest()
        with self.assertRaises(ValueError):data.parse_capture(raw,rec,'TEST')

    def test_unexplained_adjustment_is_quarantined(self):
        raw,rec=self.capture();rows=json.loads(raw);rows[2]['adjClose']=80.
        raw=json.dumps(rows).encode();rec['raw_sha256']=hashlib.sha256(raw).hexdigest()
        _,a=data.parse_capture(raw,rec,'TEST');self.assertFalse(a['action_basis_qualified'])

    def test_split_does_not_make_a_crash(self):
        p=panel(6);p.loc[p.index[3]:,['open','high','low','close']]/=2
        p.loc[p.index[3],'split']=2
        result=data.prepare_prices(p)
        np.testing.assert_allclose(result.signal_close,100.)
        self.assertAlmostEqual(result.return_log.iloc[3],0.)

    def test_dividend_total_return(self):
        p=panel(6);p.loc[p.index[3]:,['open','high','low','close']]-=1
        p.loc[p.index[3],'dividend']=1
        result=data.prepare_prices(p)
        self.assertAlmostEqual(result.signal_close.iloc[3],100.)

    def test_price_prefix_ignores_future_actions(self):
        p=panel(160);a=data.prepare_prices(p.iloc[:100])
        p.loc[p.index[120]:,['open','high','low','close']]/=10;p.loc[p.index[120],'split']=10
        b=data.prepare_prices(p).iloc[:100]
        pd.testing.assert_frame_equal(a,b)

    def test_direct_bad_ohlc_is_rejected(self):
        p=panel();p.loc[p.index[4],'low']=102.
        with self.assertRaises(ValueError):data.prepare_prices(p)

    def test_membership_half_open_and_snapshot(self):
        ix=pd.date_range('2026-05-29',periods=8)
        rows=pd.DataFrame({'start_date':['2026-05-30'],'end_date':['2026-06-02']})
        np.testing.assert_array_equal(data.member_at(ix,rows),[False,True,True,True,False,False,False,False])
        rows.end_date=pd.NaT
        self.assertFalse(data.member_at(ix,rows)[-1])

    def test_next_horizon_target(self):
        result=data.future_mean(np.arange(7.),3)
        np.testing.assert_allclose(result[:4],[2,3,4,5]);self.assertTrue(np.isnan(result[4:]).all())

    def test_momentum_uses_prior_high(self):
        p=panel(150);p.loc[p.index[-1],['open','close']]=105.;p.loc[p.index[-1],'high']=106.
        p=data.prepare_prices(p);states=data.momentum_states(p)
        self.assertTrue(states.breakout20.iloc[-1]);self.assertFalse(states.breakout20.iloc[-2])


class OnsetTests(unittest.TestCase):
    def test_absence_rule(self):
        a=np.array([True,True,False,False,True,False,False,False,True])
        self.assertEqual(np.flatnonzero(native.onset_mask(a)).tolist(),[0,8])

    def test_unknown_does_not_count_as_absent(self):
        a=np.array([True,False,False,False,True])
        k=np.array([True,True,False,True,True])
        self.assertEqual(np.flatnonzero(replay.observed_onsets(a,k)).tolist(),[0])

    def test_fields_do_not_include_future_targets(self):
        self.assertFalse(any('future_' in c for columns in risk.FEATURE_GROUPS.values() for c in columns))


class PathTests(unittest.TestCase):
    def test_flat_path_exact_cost(self):
        p=panel(40);r=labels.evaluate_path(p,0)
        self.assertEqual(r['exit_kind'],'timeout');self.assertEqual(r['days_held'],21)
        self.assertAlmostEqual(r['net_return'],.9995/1.0005-1)

    def test_gap_stop_is_not_stop_price(self):
        p=panel(40);p.loc[p.index[2],['open','high','low','close']]=[90,92,88,91]
        r=labels.evaluate_path(p,0)
        self.assertEqual(r['exit_price'],90);self.assertTrue(r['gap_exit'])
        self.assertAlmostEqual(r['gross_return'],-.10)
        self.assertEqual(r['label_end_pos'],21)

    def test_intraday_stop(self):
        p=panel(40);p.loc[p.index[1],'low']=94.
        r=labels.evaluate_path(p,0);self.assertEqual(r['exit_price'],95)

    def test_target_and_ambiguous_order(self):
        p=panel(40);p.loc[p.index[1],['high','low']]=[110,94]
        a=labels.evaluate_path(p,0);b=labels.evaluate_path(p,0,order='target_first')
        self.assertEqual(a['exit_kind'],'stop');self.assertEqual(b['exit_kind'],'target')
        self.assertTrue(a['ambiguous_exit_bar'])

    def test_gap_target(self):
        price,kind,both,gap=labels.barrier_fill(115,116,114,95,108)
        self.assertEqual((price,kind,both,gap),(115,'target',False,True))

    def test_entry_dividend_not_earned(self):
        p=panel(40);p.loc[p.index[1],'dividend']=2
        r=labels.evaluate_path(p,0);self.assertEqual(r['dividend_cash'],0.)

    def test_held_dividend_earned_not_later_cash(self):
        p=panel(40);p.loc[p.index[2],'dividend']=1;p.loc[p.index[3],'high']=110
        p.loc[p.index[10],'dividend']=50
        r=labels.evaluate_path(p,0);self.assertEqual(r['dividend_cash'],1.)
        self.assertAlmostEqual(r['gross_return'],.09)

    def test_split_adjusts_barriers_and_share_units(self):
        p=panel(40);p.loc[p.index[2]:,['open','high','low','close']]/=2;p.loc[p.index[2],'split']=2
        p.loc[p.index[3],'high']=55
        r=labels.evaluate_path(p,0);self.assertEqual(r['exit_kind'],'target')
        self.assertAlmostEqual(r['exit_price'],54);self.assertAlmostEqual(r['gross_return'],.08)

    def test_censored_not_timeout(self):
        self.assertEqual(labels.evaluate_path(panel(10),0)['status'],'CENSORED')

    def test_missing_path_not_zero(self):
        p=panel(40);p.loc[p.index[3],'close']=np.nan
        with self.assertRaises(ValueError):labels.evaluate_path(p,0)

    def test_trailing_executes_next_open(self):
        p=panel(100);p.loc[p.index[40],['open','high','low','close']]=[100,101,89,90]
        p.loc[p.index[41],['open','high','low','close']]=[91,92,90,91]
        p=data.prepare_prices(p);r=labels.evaluate_path(p,20,rule='trail63')
        self.assertEqual(r['exit_pos'],41);self.assertEqual(r['exit_price'],91)


class LearningTests(unittest.TestCase):
    def sample(self):
        rng=np.random.default_rng(42);cal=pd.bdate_range('2018-01-01',periods=200)
        rows=[]
        for i in range(150):
            r={'event_id':str(i),'ticker':'TEST','origin':str(cal[i].date()),
               'label_end':str(cal[i+5].date()),'class_id':i%3,'net_return':[-.06,.08,.01][i%3]}
            r.update({c:float(rng.normal()) for c in risk.INTERACTION_FEATURES});rows.append(r)
        return pd.DataFrame(rows),cal

    def test_probability_simplex(self):
        rng=np.random.default_rng(8);x=rng.normal(size=(90,3));y=np.arange(90)%3
        f=learning.fit_multinomial(x,y);p,_=learning.predict_multinomial(f,x[:4])
        self.assertTrue(f['success']);np.testing.assert_allclose(p.sum(axis=1),1.)

    def test_missing_class_rejected(self):
        with self.assertRaises(ValueError):learning.fit_multinomial(np.ones((10,2)),np.zeros(10))

    def test_preprocessing_is_training_only(self):
        x=np.arange(90.).reshape(30,3);f=learning.fit_multinomial(x,np.arange(30)%3)
        center=f['center'].copy();p,clip=learning.predict_multinomial(f,np.full((1,3),1e8))
        np.testing.assert_array_equal(center,f['center']);self.assertTrue(clip[0])

    def test_matured_clock_and_future_invariance(self):
        e,cal=self.sample();cfg=learning.LearningSettings(30,5,20,126,1.)
        a,receipts,_=learning.walk_forward(e,cal,cfg,start=str(cal[40].date()))
        for r in receipts:
            if 'latest_training_label_end' in r:self.assertLessEqual(r['latest_training_label_end'],r['fit_origin'])
        future=pd.to_datetime(e.origin)>=cal[100];e.loc[future,'class_id']=(e.loc[future,'class_id']+1)%3
        e.loc[future,list(risk.INTERACTION_FEATURES)]=1000
        b,_,_=learning.walk_forward(e,cal,cfg,start=str(cal[40].date()))
        key=['event_id','model'];cols=['p_stop','p_target','p_timeout','expected_net_payoff']
        aa=a[pd.to_datetime(a.origin)<cal[100]].sort_values(key)[cols].reset_index(drop=True)
        bb=b[pd.to_datetime(b.origin)<cal[100]].sort_values(key)[cols].reset_index(drop=True)
        pd.testing.assert_frame_equal(aa,bb)

    def test_insufficient_training_is_abstention(self):
        e,cal=self.sample();p,r,b=learning.walk_forward(e,cal,start='2018-01-01')
        self.assertTrue(p.empty);self.assertIsNone(b)

    def test_stale_fit_removed_when_refresh_has_no_training(self):
        e,cal=self.sample();e=e.iloc[:65].copy();future=e.iloc[:1].copy()
        future['event_id']='late';future['origin']=str(cal[180].date());future['label_end']=str(cal[185].date())
        e=pd.concat([e,future],ignore_index=True)
        p,r,b=learning.walk_forward(e,cal,learning.LearningSettings(30,5,20,63,1.),start=str(cal[40].date()))
        self.assertFalse(p.empty);self.assertNotIn('late',set(p.event_id));self.assertIsNone(b)


class PortfolioTests(unittest.TestCase):
    def run_book(self,p,events=None,policy=None):
        e=pd.DataFrame(events or [opportunity(p)])
        cfg=policy or portfolio.Policy('test')
        return portfolio.simulate(portfolio.Market({'TEST':p},p.index),e,cfg,
                                  start=str(p.index[0].date()),end=str(p.index[-1].date()))

    def test_flat_account_fees_independent_calculation(self):
        p=panel(40);r=self.run_book(p)
        self.assertAlmostEqual(r['equity'][-1],1-.08*.0005*2)
        self.assertEqual(len(r['trades']),1)

    def test_gap_loss_scalar_reconciles(self):
        p=panel(40);p.loc[p.index[2],['open','high','low','close']]=[90,92,88,91]
        r=self.run_book(p);expected=1-.08*1.0005+.08*.9*.9995
        self.assertAlmostEqual(r['equity'][-1],expected)

    def test_dividend_receivable_never_finances_or_earns_cash_interest(self):
        p=panel(40);p.loc[p.index[2],'dividend']=2
        r=self.run_book(p,policy=portfolio.Policy('r',cash_rate=.03))
        s=self.run_book(p,policy=portfolio.Policy('s',cash_rate=.03,distribution_cash='ex_date_spendable'))
        self.assertAlmostEqual(r['metrics']['terminal_receivable_wealth'],float(r['fills'].query("side == 'buy'").iloc[0].notional_equity_units)/100*2)
        self.assertGreater(s['equity'][-1],r['equity'][-1])

    def test_open_exposure_retains_same_day_stop(self):
        p=panel(40);p.loc[p.index[1],'low']=94
        r=self.run_book(p)
        self.assertGreater(r['opening_exposure'][1],0);self.assertEqual(r['exposure'][1],0)

    def test_held_duplicate_not_pyramided(self):
        p=panel(40);r=self.run_book(p,[opportunity(p),opportunity(p,origin=3,identifier='second')])
        self.assertEqual(r['rejections'].get('already_held'),1);self.assertEqual(len(r['trades']),1)

    def test_future_labels_cannot_change_account(self):
        p=panel(40);a=[opportunity(p)];b=[{**a[0],'class_id':1,'net_return':100,'future_variance_h5':100}]
        np.testing.assert_array_equal(self.run_book(p,a)['equity'],self.run_book(p,b)['equity'])

    def test_split_is_account_neutral(self):
        p=panel(40);base=self.run_book(p)
        p.loc[p.index[3]:,['open','high','low','close']]/=2;p.loc[p.index[3],'split']=2
        r=self.run_book(p);np.testing.assert_allclose(base['equity'],r['equity'])

    def test_missing_forecast_is_not_zero_risk(self):
        p=panel(40);r=self.run_book(p,[opportunity(p,mem_h5=np.nan)],portfolio.Policy('risk',sizing='mem'))
        self.assertEqual(r['rejections']['forecast_unavailable'],1);self.assertEqual(r['equity'][-1],1.)

    def test_gross_cap_and_no_intraday_cash_recycling(self):
        a=panel(45);b=panel(45);a.loc[a.index[2],'low']=94
        events=pd.DataFrame([opportunity(a,ticker='AAA'),opportunity(b,ticker='BBB',origin=1,identifier='b')])
        cfg=portfolio.Policy('limited',maximum_positions=1)
        r=portfolio.simulate(portfolio.Market({'AAA':a,'BBB':b},a.index),events,cfg,
                             start=str(a.index[0].date()),end=str(a.index[-1].date()))
        self.assertEqual(r['rejections']['position_limit'],1)
        self.assertLessEqual(r['metrics']['maximum_decision_open_gross'],.8+1e-10)
        self.assertEqual(set(r['trades'].ticker),{'AAA'})

    def test_unknown_ev_is_not_admitted(self):
        p=panel(40);r=self.run_book(p,policy=portfolio.Policy('ev',selection='ev_positive'))
        self.assertEqual(r['equity'][-1],1.)

    def test_invalid_policy(self):
        for changes in ({'cost':np.nan},{'maximum_positions':True},{'gross_cap':1.1},{'delay':-1}):
            with self.assertRaises(ValueError):replace(portfolio.Policy('bad'),**changes).validate()


if __name__=='__main__':unittest.main()
