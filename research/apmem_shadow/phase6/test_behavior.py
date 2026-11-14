import unittest
import numpy as np
import pandas as pd
from behavior import select_peers,monthly_peer_plan,residual_panel,build_context

class BehavioralPeerTests(unittest.TestCase):
    def panel(self,n=700):
        rng=np.random.default_rng(7);x=rng.normal(0,.01,n);y=rng.normal(0,.01,n)
        return pd.DataFrame({'A':x,'B':x+rng.normal(0,.002,n),'C':x+rng.normal(0,.003,n),
                             'D':y,'E':-x},index=pd.bdate_range('2007-01-02',periods=n))
    def test_future_returns_do_not_select_peers(self):
        r=self.panel();a=select_peers(r,'A',400);r.iloc[400:]=100.;b=select_peers(r,'A',400);self.assertEqual(a,b)
    def test_focal_name_excluded(self):
        chosen=select_peers(self.panel(),'A',400);self.assertNotIn('A',[r[0] for r in chosen]);self.assertEqual(chosen[0][0],'B')
    def test_negative_correlation_not_supporting_peer(self):
        self.assertNotIn('E',[r[0] for r in select_peers(self.panel(),'A',400)])
    def test_insufficient_history_unknown(self):self.assertEqual(select_peers(self.panel(),'A',80),[])
    def test_selection_clock_precedes_effective_month(self):
        for row in monthly_peer_plan(self.panel(330)):
            self.assertLess(pd.Timestamp(row['selected_at']),pd.Timestamp(row['starts']))
    def test_lagged_beta_prefix_invariant(self):
        r=self.panel();t=100*np.exp(r.cumsum());t['SPY']=100*np.exp(r.D.cumsum())
        a=residual_panel(t,list(r));b=residual_panel(t.iloc[:500],list(r));pd.testing.assert_frame_equal(a.iloc[:500],b)
    def test_missing_peer_plan_produces_unknown(self):
        r=self.panel();p=100*np.exp(r.cumsum());a=build_context(p,p,'A',[])
        self.assertFalse(a.beh_peer_valid.any());self.assertTrue(a.beh_peer_return_21.isna().all())

    def test_real_selected_context_has_typed_values(self):
        r=self.panel();p=100*np.exp(r.cumsum())
        plan=[{'symbol':'A','start_pos':300,'end_pos':320,'peers':['B','C'],
               'selected_at':str(p.index[299].date()),'correlations':[.8,.7]}]
        out=build_context(p,p,'A',plan)
        self.assertTrue(out.beh_peer_valid.iloc[319]);self.assertTrue(np.isfinite(out.beh_peer_above20.iloc[319]))
        self.assertFalse(out.beh_peer_valid.iloc[299]);self.assertTrue(pd.isna(out.beh_peer_above20.iloc[299]))

if __name__=='__main__':unittest.main()
