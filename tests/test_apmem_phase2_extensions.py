import unittest
import numpy as np
import pandas as pd
from research.apmem_shadow.model import Parameters
from research.apmem_shadow.phase2.extensions import common_execution_end,simulate_conditional_variance


class ExtensionTests(unittest.TestCase):
    def test_execution_end_is_input_not_outcome_bound(self):
        p=pd.DataFrame(index=pd.bdate_range('2020-01-01',periods=20))
        a=np.ones((20,3));a[16:]=np.nan
        end,mask=common_execution_end(p,{'m':a},['m'])
        self.assertEqual(end,17);self.assertFalse(mask[16])
    def test_exact_one_step_independent_of_seed(self):
        par=Parameters(.04,.1,.85,.2,1.)
        for seed in (1,20,100):
            a=simulate_conditional_variance(2.,par,np.array([.5,1.5]),np.array([-1,1]),16,seed)
            self.assertEqual(a[0],2.)
    def test_deterministic_recurrence(self):
        par=Parameters(.04,.1,.85,0.,1.);state=2.;means=[state]
        for _ in range(19):state=.04+.95*state;means.append(state)
        a=simulate_conditional_variance(2.,par,np.ones(50),np.ones(50),16,1)
        np.testing.assert_allclose(a,[np.mean(means[:h]) for h in (1,5,20)],atol=1e-12)
    def test_empirical_linear_expectation(self):
        par=Parameters(.04,.1,.85,.2,1.);eps=np.array([.5,1.5]);sign=np.array([-1,1])
        persistence=par.beta+par.alpha*np.mean(eps*(1-par.gamma*sign));state=2.;means=[state]
        for _ in range(19):state=par.omega+persistence*state;means.append(state)
        a=simulate_conditional_variance(2.,par,eps,sign,100000,77)
        np.testing.assert_allclose(a,[np.mean(means[:h]) for h in (1,5,20)],rtol=.003)


if __name__=='__main__':unittest.main()
