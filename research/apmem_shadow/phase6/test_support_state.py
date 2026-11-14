import unittest
import numpy as np
import pandas as pd
from support_state import cohort_state,slow_state

class SupportStateTests(unittest.TestCase):
    def fixture(self,n=60):
        return pd.DataFrame({'peer_valid':[True]*n,'peer_above20':[.6]*n,'peer_return_21':[.02]*n,
          'peer_return_5':[.01]*n,'peer_low_pressure_change':[0.]*n,'peer_repair':[False]*n},index=pd.bdate_range('2018-01-02',periods=n))
    def test_healthy_plateau_not_false_negative(self):
        x=self.fixture();s=cohort_state(x);self.assertTrue(s.cohort_supported.all());self.assertTrue((s.cohort_state=='SUPPORTED_HEALTHY').all())
    def test_impulse_memory_expires(self):
        x=self.fixture();x.peer_above20=.3;x.peer_return_21=-.02;x.loc[x.index[1],'peer_repair']=True
        s=cohort_state(x);self.assertTrue(s.cohort_supported.iloc[20]);self.assertFalse(s.cohort_supported.iloc[22])
    def test_unknown_clears_retained_support(self):
        x=self.fixture();x.peer_above20=.3;x.peer_return_21=-.02;x.loc[x.index[1],'peer_repair']=True;x.loc[x.index[3],'peer_valid']=False
        s=cohort_state(x);self.assertEqual(s.cohort_state.iloc[3],'UNKNOWN');self.assertFalse(s.cohort_supported.iloc[4])
    def test_deterioration_revokes_repair_window(self):
        x=self.fixture();x.peer_above20=.3;x.peer_return_21=-.02;x.loc[x.index[1],'peer_repair']=True
        x.loc[x.index[4],['peer_return_5','peer_low_pressure_change']]=[-.01,.2]
        s=cohort_state(x);self.assertEqual(s.cohort_state.iloc[4],'DETERIORATING');self.assertFalse(s.cohort_supported.iloc[4])
    def test_state_prefix_invariance(self):
        x=self.fixture();x.loc[x.index[25:],'peer_return_21']=-.5
        pd.testing.assert_frame_equal(cohort_state(x).iloc[:20],cohort_state(x.iloc[:20]))
    def test_fixed_pairings_are_symmetric(self):
        x=pd.DataFrame({'w2_hist':[-2.,1.],'alternate_w2_hist':[-1.,.5],'w2_hist_delta':[.3,-.2],'alternate_w2_hist_delta':[-.1,-.3]})
        y=x.rename(columns={'w2_hist':'alternate_w2_hist','alternate_w2_hist':'w2_hist','w2_hist_delta':'alternate_w2_hist_delta','alternate_w2_hist_delta':'w2_hist_delta'})
        pd.testing.assert_frame_equal(slow_state(x),slow_state(y))
    def test_unknown_slow_pairing_not_confirmation(self):
        x=pd.DataFrame({'w2_hist':[1.],'alternate_w2_hist':[np.nan],'w2_hist_delta':[.3],'alternate_w2_hist_delta':[np.nan]})
        s=slow_state(x);self.assertFalse(s.slow_supported.iloc[0]);self.assertFalse(s.slow_known.iloc[0])
    def test_disagreement_is_visible(self):
        x=pd.DataFrame({'w2_hist':[-2.],'alternate_w2_hist':[-1.],'w2_hist_delta':[.3],'alternate_w2_hist_delta':[-.1]})
        s=slow_state(x);self.assertTrue(s.slow_supported.iloc[0]);self.assertTrue(s.slow_phase_disagreement.iloc[0])

if __name__=='__main__':unittest.main()
