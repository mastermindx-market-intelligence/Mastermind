"""Persistent-account and attribution tests without private market observations."""
import unittest
from dataclasses import replace
import numpy as np
import pandas as pd
from research.apmem_shadow.phase3 import data,portfolio,continuous


def panel(n=90):
    return data.prepare_prices(pd.DataFrame({'open':100.,'high':101.,'low':99.,'close':100.,
        'volume':1e6,'dividend':0.,'split':1.},index=pd.bdate_range('2020-01-01',periods=n)))


def features(p):
    return pd.DataFrame({'eligible':True,'relative_momentum':.1,'mem_h5':.0004,'ewma_h5':.0004},index=p.index)


class ContinuousTests(unittest.TestCase):
    def run_book(self,p,f=None,policy=None):
        return continuous.simulate(portfolio.Market({'TEST':p},p.index),{'TEST':features(p) if f is None else f},
            policy or continuous.ContinuousPolicy('test'),start=str(p.index[1].date()),end=str(p.index[-1].date()))

    def test_self_financing_buy(self):
        target,cash,fee,turn=continuous.rebalance_targets(1.,0.,np.zeros(2),np.array([.4,.4]),.001)
        after=1/(1+.8*.001)
        np.testing.assert_allclose(target,[.4*after,.4*after])
        self.assertAlmostEqual(cash+target.sum()+fee,1.)
        self.assertAlmostEqual(turn,target.sum())

    def test_self_financing_sells_before_buys(self):
        target,cash,fee,turn=continuous.rebalance_targets(.2,0.,np.array([.8,0.]),np.array([0.,.8]),.001)
        self.assertAlmostEqual(cash+target.sum()+fee,1.)
        self.assertGreaterEqual(cash,0);self.assertEqual(target[0],0.)
        self.assertAlmostEqual(turn,.8+target[1])

    def test_receivable_cannot_finance_targets(self):
        target,cash,fee,turn=continuous.rebalance_targets(0.,.9,np.array([.1]),np.array([.8]),.001)
        self.assertLessEqual(target.sum(),.1)
        self.assertGreaterEqual(cash,0.)
        self.assertAlmostEqual(cash+.9+target.sum()+fee,1.)

    def test_zero_cost_flat_account(self):
        p=panel();r=self.run_book(p,policy=continuous.ContinuousPolicy('flat',cost=0))
        np.testing.assert_allclose(r['equity'],1.)
        self.assertEqual(r['metrics']['maximum_decision_open_gross'],.08)

    def test_fee_account_reconciliation(self):
        p=panel();r=self.run_book(p)
        self.assertAlmostEqual(r['equity'][-1],1-r['fees'].sum())
        self.assertTrue((r['equity']<=1+1e-12).all())

    def test_split_preserves_account_wealth(self):
        p=panel();a=self.run_book(p)
        p.loc[p.index[10]:,['open','high','low','close']]/=2;p.loc[p.index[10],'split']=2
        p=data.prepare_prices(p);b=self.run_book(p)
        np.testing.assert_allclose(a['equity'],b['equity'],atol=1e-14)

    def test_ex_date_buyer_not_eligible_for_distribution(self):
        p=panel();p.loc[p.index[1],'dividend']=2
        r=self.run_book(p);self.assertEqual(r['metrics']['terminal_receivable_wealth'],0.)

    def test_earned_distribution_is_receivable(self):
        p=panel();p.loc[p.index[5],'dividend']=2
        r=self.run_book(p,policy=continuous.ContinuousPolicy('r',cost=0))
        self.assertAlmostEqual(r['metrics']['terminal_receivable_wealth'],.0016)
        self.assertAlmostEqual(r['equity'][-1],1.0016)

    def test_current_close_cannot_change_current_open_target(self):
        p=panel();f=features(p);f.loc[p.index[0],'eligible']=False
        r=self.run_book(p,f,continuous.ContinuousPolicy('d',selection_cadence=1,risk_cadence=1))
        self.assertEqual(r['opening_exposure'][0],0.)
        self.assertGreater(r['opening_exposure'][1],0.)

    def test_future_feature_changes_do_not_revise_past_account(self):
        p=panel();f=features(p);a=self.run_book(p,f)
        f.loc[p.index[50]:,'relative_momentum']=-1
        b=self.run_book(p,f)
        np.testing.assert_array_equal(a['equity'][:50],b['equity'][:50])

    def test_missing_risk_cannot_be_full_weight(self):
        p=panel();f=features(p);f['mem_h5']=np.nan
        r=self.run_book(p,f,continuous.ContinuousPolicy('r',sizing='mem',risk_cadence=1))
        np.testing.assert_array_equal(r['equity'],1.)

    def test_invalid_policy_rejected(self):
        for fields in ({'cost':np.nan},{'slots':True},{'gross_cap':1.1},{'selection':'future'}):
            with self.assertRaises(ValueError):replace(continuous.ContinuousPolicy('bad'),**fields).validate()

    def test_attributed_lot_profit_reconciles_to_account(self):
        p=panel();p.loc[p.index[3],'dividend']=1
        p.loc[p.index[8],'high']=110
        events=pd.DataFrame([{'event_id':'a','ticker':'TEST','origin':str(p.index[0].date()),
                             'family':'union','mem_h5':.0004,'ewma_h5':.0004,'relative_momentum':.1}])
        r=portfolio.simulate(portfolio.Market({'TEST':p},p.index),events,portfolio.Policy('a'),
            start=str(p.index[0].date()),end=str(p.index[-1].date()))
        self.assertAlmostEqual(r['trades'].pnl_equity_units.sum(),r['equity'][-1]-1.)


if __name__=='__main__':unittest.main()
