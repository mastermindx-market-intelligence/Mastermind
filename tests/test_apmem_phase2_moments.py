import unittest
from unittest.mock import patch
import numpy as np
from research.apmem_shadow.model import Parameters,fit_qml
from research.apmem_shadow.phase2.moments import (moment_projection,transition_coefficients,
    replay_moments,fit_fixed_power,fixed_power_forecasts)
from research.apmem_shadow.phase2.forecasts import Settings


class MomentsTests(unittest.TestCase):
    def test_linear_exact(self):
        p=Parameters(.1,.1,.8,.2,1.);a=np.array([.5,1.1]);x=2.;values=[x]
        for _ in range(19):x=.1+a.mean()*x;values.append(x)
        out,lo,hi,d=moment_projection(2.,p,a)
        np.testing.assert_allclose(out,[np.mean(values[:h]) for h in (1,5,20)])
        np.testing.assert_array_equal(lo,hi);self.assertTrue(d['point_estimate_exact_under_empirical_recursion'])
    def test_power2_exact_enumeration(self):
        p=Parameters(.1,.1,.8,.2,.5);a=np.array([.5,1.1]);states=np.array([np.sqrt(2.)]);values=[2.]
        for _ in range(6):states=(.1+states[:,None]*a).ravel();values.append(np.mean(states**2))
        out,lo,hi,_=moment_projection(2.,p,a,horizons=(1,3,7))
        np.testing.assert_allclose(out,[np.mean(values[:h]) for h in (1,3,7)],atol=1e-12)
        np.testing.assert_array_equal(lo,hi)
    def test_fractional_bounds_exact_enumeration(self):
        for delta in (.51,.7,1.2,1.9,2.):
            p=Parameters(.1,.1,.8,.2,delta);a=np.array([.2,1.7]);states=np.array([2.**delta]);values=[2.]
            for _ in range(7):states=(.1+states[:,None]*a).ravel();values.append(np.mean(states**(1/delta)))
            out,lo,hi,d=moment_projection(2.,p,a,horizons=(1,3,8))
            exact=np.array([np.mean(values[:h]) for h in (1,3,8)])
            self.assertTrue(np.all(lo<=exact+1e-12));self.assertTrue(np.all(hi>=exact-1e-12))
            self.assertTrue(np.all(lo<=out+1e-12));self.assertTrue(np.all(hi>=out-1e-12))
            self.assertFalse(d['bounds_are_market_prediction_intervals'])
    def test_zero_transition_uncertainty_exact(self):
        p=Parameters(.1,.1,.8,.2,.8);a=np.full(12,.9)
        out,lo,hi,_=moment_projection(2,p,a)
        np.testing.assert_allclose(out,lo,atol=1e-12);np.testing.assert_allclose(out,hi,atol=1e-12)
    def test_h1_exact_and_no_rng(self):
        p=Parameters(.1,.1,.8,.2,.6)
        with patch('numpy.random.default_rng',side_effect=RuntimeError('RNG forbidden')):
            a,lo,hi,_=moment_projection(2.,p,np.array([.3,1.8]))
        self.assertAlmostEqual(a[0],2.);self.assertAlmostEqual(lo[0],2.);self.assertAlmostEqual(hi[0],2.)
    def test_stationarity_moment_not_power_state(self):
        p=Parameters(.1,.1,.8,.2,.5);a=np.array([.01,1.9])
        _,_,_,d=moment_projection(2.,p,a)
        self.assertLess(d['mean_power_state_coefficient'],1)
        self.assertGreater(d['variance_mean_moment_coefficient'],1)
        self.assertFalse(d['variance_mean_stationarity_diagnostic'])
    def test_invalid_arguments(self):
        for state in (-1,np.nan):
            with self.assertRaises(ValueError):moment_projection(state,Parameters(.1,.1,.8,.2,1.),np.ones(3))
    def test_sign_pairs_validated(self):
        with self.assertRaises(ValueError):transition_coefficients(Parameters(.1,.1,.8,.2,1.),np.ones(3),np.full(3,2))
    def test_saved_digest_fenced(self):
        rng=np.random.default_rng(13);v=np.exp(rng.normal(-8,.3,85));r=rng.normal(0,.01,85)
        fit=fit_qml(v[:70],r[:70]);rec={'origin':69,'train_start':0,'train_end':69,**fit.record()}
        out,_,_,_=replay_moments(v,r,[rec]);self.assertTrue(np.isfinite(out[69:]).all())
        changed=v.copy();changed[0]*=2
        with self.assertRaises(ValueError):replay_moments(changed,r,[rec])
    def test_replay_prefix_invariant(self):
        rng=np.random.default_rng(12);v=np.exp(rng.normal(-8,.3,95));r=rng.normal(0,.01,95)
        fit=fit_qml(v[:70],r[:70]);rec={'origin':69,'train_start':0,'train_end':69,**fit.record()}
        a,_,_,_=replay_moments(v,r,[rec]);b,_,_,_=replay_moments(v[:80],r[:80],[rec])
        np.testing.assert_allclose(a[:80],b,equal_nan=True)
    def test_failed_block_is_not_previous_fit(self):
        rng=np.random.default_rng(14);v=np.exp(rng.normal(-8,.3,95));r=rng.normal(0,.01,95)
        fit=fit_qml(v[:70],r[:70]);rec={'origin':69,'train_start':0,'train_end':69,**fit.record()}
        fail={'origin':80,'train_start':0,'train_end':80,'success':False}
        a,_,_,_=replay_moments(v,r,[rec,fail]);self.assertTrue(np.isnan(a[80:]).all())
    def test_fixed_power_and_prefix(self):
        rng=np.random.default_rng(15);v=np.exp(rng.normal(-8,.4,150));r=rng.normal(0,.01,150)
        cfg=Settings(minimum=64,window=100,apmem_refit=63)
        a,logs,_=fixed_power_forecasts(v,r,cfg);b,_,_=fixed_power_forecasts(v[:90],r[:90],cfg)
        self.assertTrue(all(x['parameters']['delta']==1 for x in logs if x['success']))
        np.testing.assert_allclose(a[:90],b,equal_nan=True)
    def test_fixed_fit_invalid(self):
        with self.assertRaises(ValueError):fit_fixed_power(np.ones(5),np.ones(5))


if __name__=='__main__':unittest.main()
