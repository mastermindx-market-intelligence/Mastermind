"""Event/admission and fixed-arm tests without private observations."""
import unittest
import numpy as np
import pandas as pd
from research.apmem_shadow.phase3.data import prepare_prices
from research.apmem_shadow.phase3.events import build_events
from research.apmem_shadow.phase3.arms import core_policies,PRIMARY_TEST_FAMILY_SIZE,data_for_policy
from research.apmem_shadow.phase3.portfolio import Policy


class EventTests(unittest.TestCase):
    def inputs(self):
        ix=pd.bdate_range('2018-01-01',periods=400)
        p=prepare_prices(pd.DataFrame({'open':100.,'high':101.,'low':99.,'close':100.,
            'volume':1e6,'dividend':0.,'split':1.},index=ix))
        n=pd.DataFrame({'t1_onset':False,'t2_onset':False,'union_onset':False,
                         'evaluated':True,'native_tier':None},index=ix)
        n.loc[ix[200],['t2_onset','union_onset']]=True
        n.loc[ix[200],'native_tier']='T2'
        f=pd.DataFrame({**{m+'_h'+str(h):.0002 for m in ('mem','ewma') for h in (1,5,20)},
            **{'future_'+t+'_h'+str(h):.0002 for t in ('variance','return_square') for h in (1,5,20)}},index=ix)
        members=pd.DataFrame({'ticker':['TEST'],'start_date':[pd.Timestamp('2010-01-01')],
                              'end_date':[pd.NaT],'src':['sp500']})
        return p,n,f,members

    def test_admitted_native_event_and_full_label_clock(self):
        p,n,f,m=self.inputs();e,paths,rec=build_events('TEST',p,n,f,m,p)
        self.assertEqual(set(e.family),{'t2','union'});self.assertEqual(len(e),2)
        self.assertTrue(e.event_id.is_unique);self.assertTrue((e.label_end>e.origin).all())
        self.assertTrue((e.tier_t2==1).all());self.assertEqual(len(paths),10)

    def test_delete_date_is_not_member(self):
        p,n,f,m=self.inputs();m.end_date=p.index[200]
        e,paths,_=build_events('TEST',p,n,f,m,p);self.assertTrue(e.empty)

    def test_liquidity_failure_not_an_entry(self):
        p,n,f,m=self.inputs();p['tradable']=False
        e,_,_=build_events('TEST',p,n,f,m,p);self.assertTrue(e.empty)

    def test_foreign_membership_rejected(self):
        p,n,f,m=self.inputs();m.ticker='WRONG'
        with self.assertRaises(ValueError):build_events('TEST',p,n,f,m,p)

    def test_unknown_native_row_cannot_create_event(self):
        p,n,f,m=self.inputs();n.loc[p.index[200],'evaluated']=False
        with self.assertRaises(ValueError):build_events('TEST',p,n,f,m,p)

    def test_fixed_arm_and_contrast_counts(self):
        arms=core_policies();self.assertEqual(len(arms),20)
        self.assertEqual(len({a.name for a in arms}),20)
        self.assertEqual(PRIMARY_TEST_FAMILY_SIZE,34)
        for a in arms:a.validate()

    def test_classifier_policy_does_not_fill_missing_predictions(self):
        p,n,f,m=self.inputs();e,_,_=build_events('TEST',p,n,f,m,p)
        out=data_for_policy(e,pd.DataFrame(),Policy('union_risk_ev',selection='ev_positive'))
        self.assertTrue(out.empty)


if __name__=='__main__':unittest.main()
