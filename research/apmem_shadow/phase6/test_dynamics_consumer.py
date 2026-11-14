import copy,unittest
import numpy as np
import pandas as pd
from dynamics import relative_dynamics,cross_cycle,support_exit
import consumer as c

class RecoveryDynamicsTests(unittest.TestCase):
    def index(self,n):return pd.bdate_range('2019-01-02',periods=n)
    def test_acceleration_not_positive_level(self):
        r=np.r_[0.,np.full(16,-.01),np.full(5,.005)]
        t=pd.Series(100*np.exp(np.cumsum(r)),index=self.index(len(r)))
        peer=pd.Series(0.,index=t.index);out=relative_dynamics(t,peer)
        self.assertGreater(out.relative_log5.iloc[-1],0);self.assertGreater(out.relative_acceleration.iloc[-1],0)
        self.assertLess(t.iloc[-1]/t.iloc[0]-1,0)
    def test_future_relative_returns_do_not_change_past(self):
        t=pd.Series(np.exp(np.linspace(4,5,90)),index=self.index(90));peer=pd.Series(.001,index=t.index)
        a=relative_dynamics(t,peer);t.iloc[70:]*=9;b=relative_dynamics(t,peer)
        pd.testing.assert_frame_equal(a.iloc[:70],b.iloc[:70])
    def test_missing_peer_is_not_flat_peer(self):
        t=pd.Series(np.exp(np.linspace(4,5,90)),index=self.index(90));peer=pd.Series(.001,index=t.index);peer.iloc[-1]=np.nan
        self.assertTrue(pd.isna(relative_dynamics(t,peer).relative_log5.iloc[-1]))
    def test_cross_cycle_requires_observed_failure(self):
        p=pd.Series([100.]*21+[90.,95.,92.,85.,88.],index=self.index(26));s=pd.Series(False,index=p.index);s.iloc[[21,25]]=True
        hist=pd.Series(-3.,index=p.index);hist.iloc[24:]=-1.;episode=pd.Series(1,index=p.index)
        out=cross_cycle(p,s,hist,episode)
        self.assertFalse(out.cross_cycle_known.iloc[23]);self.assertTrue(out.cross_cycle_divergence.iloc[25])
        self.assertEqual(out.prior_failed_at.iloc[25],p.index[24]);self.assertEqual(out.prior_attempt_at.iloc[25],p.index[21])
    def test_cross_cycle_cannot_transfer_between_episodes(self):
        p=pd.Series([100.]*21+[90.,85.,88.],index=self.index(24));s=pd.Series(False,index=p.index);s.iloc[21]=True
        hist=pd.Series(-3.,index=p.index);hist.iloc[-1]=-1.;episode=pd.Series(1,index=p.index);episode.iloc[-1]=2
        self.assertFalse(cross_cycle(p,s,hist,episode).cross_cycle_known.iloc[-1])
    def test_nested_exit_does_not_require_simultaneous_cross(self):
        x=pd.DataFrame({'fast_hist':[1.,-1.,-2.],'w2_hist_delta':[1.,1.,-1.],
             'peer_return_5':[.1,.1,.1],'peer_breadth_change':[.2,.2,.2],'peer_valid':[True]*3})
        self.assertEqual(support_exit(x,'fast_cross').tolist(),[False,True,False])
        self.assertEqual(support_exit(x,'nested_support').tolist(),[False,False,True])
    def test_missing_slow_and_peer_not_exit(self):
        x=pd.DataFrame({'fast_hist':[-1.],'w2_hist_delta':[np.nan],'peer_return_5':[np.nan],
                         'peer_breadth_change':[np.nan],'peer_valid':[False]})
        self.assertFalse(support_exit(x,'nested_support').iloc[0])

class ConsumerTests(unittest.TestCase):
    def context(self):
        return c.make_context('MCD','2026-11-09','LOCAL_REPAIR_WITHOUT_COHORT_CONFIRMATION',
          {'w2_hist':-.2,'peer_coverage':.8,'vvix_trend':None},source_hash='a'*64,research_revision='b'*40,
          peer_basis='fixed_economic_diagnostic')
    def incumbent(self):return {'ticker':'MCD','buyable':False,'verdict':'knife','entry_score':20.,'nested':{'reason':'unchanged'}}
    def attach(self,context,incumbent=None):
        return c.attach(self.incumbent() if incumbent is None else incumbent,context,instrument='MCD',expected_session='2026-11-13',expected_source_hash='a'*64)
    def test_preserves_rejection(self):
        i=self.incumbent();out=self.attach(self.context(),i)
        self.assertEqual({k:out[k] for k in i},i);self.assertEqual(out['nested_cycle_research']['freshness'],'stale_for_requested_session')
    def test_truthy_authority_refused(self):
        x=self.context();x['authority']['may_trade']=True
        with self.assertRaises(ValueError):self.attach(x)
    def test_wrong_instrument_refused(self):
        x=self.context();x['instrument']='RSP'
        with self.assertRaises(ValueError):self.attach(x)
    def test_wrong_source_refused(self):
        x=self.context();x['source_hash']='f'*64
        with self.assertRaises(ValueError):self.attach(x)
    def test_future_context_refused(self):
        x=self.context();x['as_of']='2026-11-16'
        with self.assertRaises(ValueError):self.attach(x)
    def test_payload_isolation(self):
        i=self.incumbent();x=self.context();out=self.attach(x,i);out['nested']['reason']='changed';out['nested_cycle_research']['facts']['w2_hist']=0
        self.assertEqual(i['nested']['reason'],'unchanged');self.assertEqual(x['facts']['w2_hist'],-.2)
    def test_duplicate_namespace_refused(self):
        first=self.attach(self.context())
        with self.assertRaises(ValueError):self.attach(self.context(),first)
    def test_false_validation_refused(self):
        x=self.context();x['validation']='PRODUCTION_VALIDATED'
        with self.assertRaises(ValueError):self.attach(x)
    def test_missing_peer_selection_clock_refused(self):
        with self.assertRaises(ValueError):c.make_context('MCD','2026-11-09','CONTEXT_INCOMPLETE',{},source_hash='a'*64,research_revision='b'*40,peer_basis='lagged_behavioral_diagnostic')
    def test_nonfinite_fact_refused(self):
        with self.assertRaises(ValueError):c.make_context('MCD','2026-11-09','CONTEXT_INCOMPLETE',{'w2_hist':float('nan')},source_hash='a'*64,research_revision='b'*40,peer_basis='fixed_economic_diagnostic')
    def test_calibrated_claim_refused(self):
        with self.assertRaises(ValueError):c.make_context('MCD','2026-11-09','CONTEXT_INCOMPLETE',{},source_hash='a'*64,research_revision='b'*40,peer_basis='fixed_economic_diagnostic',latest_forecast={'calibrated':True})
    def test_training_clock_refused(self):
        x={'calibrated':False,'last_training_end':'2026-11-09','horizon_sessions':21,'probabilities':{'low_hold':.7}}
        with self.assertRaises(ValueError):c.make_context('MCD','2026-11-09','CONTEXT_INCOMPLETE',{},source_hash='a'*64,research_revision='b'*40,peer_basis='fixed_economic_diagnostic',latest_forecast=x)

if __name__=='__main__':unittest.main()
