"""Independent arithmetic checks on output replay, not generator validation."""
import unittest
import numpy as np
import pandas as pd
from research.apmem_shadow.creator_replay import signed_replay, replay_published


class CreatorReplayTests(unittest.TestCase):
    def fixture(self):
        dates=pd.bdate_range('2023-01-02',periods=6)
        p=pd.DataFrame({'open':[100.,200,220,242,242,242],
            'close':[100.,200,220,242,242,242]},index=dates)
        p['high']=p.close+1;p['low']=p.close-1
        s={'dates':[str(x.date()) for x in dates],'regime':[1,1,-1,-1,-1,1],
           'closes':p.close.tolist()}
        return s,p

    def test_first_signal_executes_next_open(self):
        s,p=self.fixture();r=replay_published(s,p)
        x=next(z for z in r['results'] if z['policy']=='published_long_short' and z['delay_sessions']==1 and z['one_way_cost']==0)
        self.assertAlmostEqual(x['total_return'],.21)
        self.assertFalse(r['historical_publication_time_verified'])
        self.assertEqual(r['start_open'],str(p.index[1].date()))

    def test_additional_delay_holds_cash_first_interval(self):
        s,p=self.fixture();r=replay_published(s,p)
        x=next(z for z in r['results'] if z['policy']=='published_long_short' and z['delay_sessions']==2 and z['one_way_cost']==0)
        self.assertAlmostEqual(x['total_return'],.1)

    def test_signed_scalar_accounting(self):
        p=np.array([100.,110.,90.,105.]);w=np.array([1.,-1.,-1.]);cost=.001;borrow=.03
        eq=1.;prev=0.
        for i,pos in enumerate(w):
            eq*=1-cost*abs(pos-prev)
            eq*=1+pos*(p[i+1]/p[i]-1)-(borrow/252 if pos<0 else 0)
            prev=pos
        eq*=1-cost*abs(w[-1])
        z=signed_replay(p,w,pd.bdate_range('2023-01-02',periods=4),cost=cost,short_borrow=borrow)
        self.assertAlmostEqual(z['total_return'],eq-1)

    def test_missing_independent_date_rejected(self):
        s,p=self.fixture()
        with self.assertRaises(ValueError):replay_published(s,p.iloc[1:])

    def test_invalid_regime_rejected(self):
        s,p=self.fixture();s['regime'][0]=np.nan
        with self.assertRaises(ValueError):replay_published(s,p)


if __name__=='__main__':unittest.main()
