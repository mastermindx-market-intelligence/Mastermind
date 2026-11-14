"""Paired statistical and policy input-contract checks."""
import unittest
import numpy as np
import pandas as pd
from research.apmem_shadow.phase3.statistics import block_indices,paired_events,paired_returns,holm,es5
from research.apmem_shadow.phase3.arms import data_for_policy
from research.apmem_shadow.phase3.portfolio import Policy


class PairedTests(unittest.TestCase):
    def test_indices_are_bounded_contiguous_blocks(self):
        x=block_indices(300,draws=100)
        self.assertEqual(x.shape,(100,300));self.assertTrue(((x>=0)&(x<300)).all())
        np.testing.assert_array_equal(np.diff(x[:,:63],axis=1),np.ones((100,62)))

    def test_zero_difference_is_not_significant(self):
        r=np.sin(np.arange(300))*.01
        out=paired_returns(r,r)
        for row in out.values():
            self.assertEqual(row['difference'],0);self.assertEqual(row['centered_block_two_sided_p'],1.)

    def test_same_date_events_are_paired_before_resampling(self):
        cal=pd.bdate_range('2020-01-01',periods=200)
        a=pd.DataFrame({'event_id':[str(i) for i in range(80)],'origin':[str(cal[i//2].date()) for i in range(80)],'loss':1.})
        b=a.copy();b.loss=2.
        result=paired_events(a,b,'loss',cal)
        self.assertEqual(result['n'],80);self.assertEqual(result['distinct_event_dates'],40)
        self.assertEqual(result['difference'],-1.)

    def test_duplicate_events_refused(self):
        cal=pd.bdate_range('2020-01-01',periods=200)
        a=pd.DataFrame({'event_id':['x','x'],'origin':[str(cal[0].date())]*2,'loss':[1,2]})
        with self.assertRaises(ValueError):paired_events(a,a,'loss',cal)

    def test_changed_event_date_refused(self):
        cal=pd.bdate_range('2020-01-01',periods=200)
        a=pd.DataFrame({'event_id':['x'],'origin':[str(cal[0].date())],'loss':[1.]})
        b=a.copy();b.origin=str(cal[1].date())
        with self.assertRaises(ValueError):paired_events(a,b,'loss',cal)

    def test_missing_contrast_does_not_shrink_holm_family(self):
        rows=[{'computed':True,'centered_block_two_sided_p':.001}]+[{'computed':False} for _ in range(33)]
        result=holm(rows);self.assertAlmostEqual(result[0]['holm_adjusted_p'],.034)
        self.assertFalse(any(r['holm_below_05'] for r in result[1:]))
        with self.assertRaises(ValueError):holm(rows[:1])

    def test_expected_shortfall_definition(self):
        self.assertEqual(es5(np.arange(100.)),2.)

    def test_classifier_coverage_requires_all_named_models(self):
        events=pd.DataFrame({'event_id':['x'],'origin':['2020-01-03'],'ticker':['TEST'],'common_risk_available':[True]})
        pred=pd.DataFrame({'event_id':['x']*4,'model':['price','risk','interaction','wrong'],
                           'origin':['2020-01-03']*4,'ticker':['TEST']*4,
                           'fit_origin':['2020-01-02']*4,'latest_training_label_end':['2020-01-02']*4,
                           'p_stop':[.3]*4,'p_target':[.3]*4,'p_timeout':[.4]*4,'expected_net_payoff':[.01]*4})
        with self.assertRaises(ValueError):data_for_policy(events,pred,Policy('union_risk_ev',selection='ev_positive'))

    def test_future_fit_cannot_enter_portfolio(self):
        events=pd.DataFrame({'event_id':['x'],'origin':['2020-01-03'],'ticker':['TEST'],'common_risk_available':[True]})
        pred=pd.DataFrame({'event_id':['x']*4,'model':['price','risk','interaction','frequency'],
                           'origin':['2020-01-03']*4,'ticker':['TEST']*4,
                           'fit_origin':['2020-01-04']*4,'latest_training_label_end':['2020-01-02']*4,
                           'p_stop':[.3]*4,'p_target':[.3]*4,'p_timeout':[.4]*4,'expected_net_payoff':[.01]*4})
        with self.assertRaises(ValueError):data_for_policy(events,pred,Policy('union_risk_ev',selection='ev_positive'))


if __name__=='__main__':unittest.main()
