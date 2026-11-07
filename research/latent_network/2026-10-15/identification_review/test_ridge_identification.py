import unittest
import numpy as np
from ridge_identification import (published_ridge_formula, fit_controlled,
                                 rank_target, standardizer, solve_ridge)

class IdentificationTests(unittest.TestCase):
    def data(self):
        rng=np.random.default_rng(90151026)
        x=rng.uniform(-1,1,(401,2));test=rng.uniform(-1,1,(199,2))
        y=.45*x[:,0]-.2*x[:,1]+.03*rng.normal(size=len(x))
        return x,y,test

    def test_null_network_feature_identity(self):
        own=np.linspace(-2,2,50);peer=np.zeros(50);gap=peer-own
        self.assertTrue(np.array_equal(gap,-own))

    def test_duplicate_changes_published_penalty(self):
        x=np.linspace(-1,1,401)[:,None];y=x[:,0];test=np.linspace(-1,1,199)[:,None]
        baseline=published_ridge_formula(x,y,test)
        duplicate=published_ridge_formula(np.c_[x,-x],y,np.c_[test,-test])
        self.assertLess(np.mean((duplicate-test[:,0])**2),np.mean((baseline-test[:,0])**2))
        self.assertGreater(np.max(np.abs(duplicate-baseline)),0)

    def test_duplicate_equivalent_to_half_penalty(self):
        x=np.linspace(-1,1,401)[:,None];y=x[:,0];test=np.linspace(-1,1,199)[:,None]
        duplicated=published_ridge_formula(np.c_[x,-x],y,np.c_[test,-test],.01)
        changed_lambda=published_ridge_formula(x,y,test,.005)
        np.testing.assert_allclose(duplicated,changed_lambda,rtol=1e-12,atol=1e-12)

    def test_null_control_restores_baseline_exactly(self):
        x,y,test=self.data();n=np.c_[np.zeros(len(x)), -x[:,0]];nt=np.c_[np.zeros(len(test)),-test[:,0]]
        m=fit_controlled(x,n,y)
        np.testing.assert_allclose(m.predict(test,nt),published_ridge_formula(x,y,test),atol=1e-12)
        self.assertEqual(m.diagnostics['kept_residual_columns'],0)

    def test_intercept_and_linear_combinations_removed(self):
        x,y,t=self.data();n=np.c_[np.ones(len(x)),3*x[:,0]+2*x[:,1],-x[:,1]]
        nt=np.c_[np.ones(len(t)),3*t[:,0]+2*t[:,1],-t[:,1]]
        m=fit_controlled(x,n,y)
        self.assertFalse(m.keep.any())
        np.testing.assert_allclose(m.predict(t,nt),published_ridge_formula(x,y,t),atol=1e-12)

    def test_training_projection_not_fit_on_target(self):
        x,y,_=self.data();rng=np.random.default_rng(20);n=rng.uniform(-1,1,(len(x),3))
        a=fit_controlled(x,n,y);b=fit_controlled(x,n,y[::-1])
        np.testing.assert_array_equal(a.projection,b.projection)
        np.testing.assert_array_equal(a.keep,b.keep)

    def test_test_distribution_cannot_change_transform(self):
        x,y,t=self.data();n=np.c_[x[:,0],x[:,0]*x[:,1]];nt=np.c_[t[:,0],t[:,0]*t[:,1]]
        m=fit_controlled(x,n,y);first=m.predict(t,nt)
        extended=m.predict(np.vstack([t,[[100,100]]]),np.vstack([nt,[[100,10000]]]))
        np.testing.assert_allclose(first,extended[:-1],atol=1e-12)

    def test_kept_training_features_orthogonal(self):
        x,y,_=self.data();n=np.c_[x[:,0],x[:,0]*x[:,1]];m=fit_controlled(x,n,y)
        self.assertEqual(m.diagnostics['kept_residual_columns'],1)
        self.assertLess(m.diagnostics['max_training_base_residual_cross_moment'],1e-12)

    def test_ridge_baseline_coefficients_unchanged_by_orthogonal_addition(self):
        x,y,t=self.data();n=(x[:,0]*x[:,1])[:,None];m=fit_controlled(x,n,y)
        a=np.c_[np.ones(len(x)),standardizer(x).apply(x)]
        expected=solve_ridge(a,y,.01)
        np.testing.assert_allclose(m.coefficients[:len(expected)],expected,atol=1e-12)

    def test_noninformative_nearly_duplicate_not_amplified(self):
        x,y,t=self.data();n=x[:,[0]]+1e-13*np.sin(np.arange(len(x)))[:,None]
        m=fit_controlled(x,n,y)
        self.assertEqual(m.keep.sum(),0)

    def test_invalid_rows_and_nonfinite_refused(self):
        x,y,t=self.data()
        with self.assertRaises(ValueError):fit_controlled(x,x[:-1],y)
        bad=x.copy();bad[0,0]=np.nan
        with self.assertRaises(ValueError):fit_controlled(x,bad,y)
        with self.assertRaises(ValueError):fit_controlled(x,x,y,penalty=0)

    def test_inference_shape_refused(self):
        x,y,t=self.data();m=fit_controlled(x,x[:,[0]],y)
        with self.assertRaises(ValueError):m.predict(t,t)

    def test_rank_invariant_under_common_return_shift(self):
        r=np.array([-.02,-.01,0,.01,.02]);shifted=r+.05
        np.testing.assert_array_equal(rank_target(r),rank_target(shifted))
        self.assertNotEqual(int((r>0).sum()),int((shifted>0).sum()))

    def test_rank_invariant_under_common_negative_shift(self):
        r=np.array([-.02,-.01,0,.01,.02]);shifted=r-.05
        np.testing.assert_array_equal(rank_target(r),rank_target(shifted))
        self.assertEqual(int((shifted>0).sum()),0)

    def test_rank_target_centered_with_ties(self):
        self.assertAlmostEqual(rank_target([.01,.01,.03,-.02]).sum(),0)

if __name__=='__main__': unittest.main(verbosity=2)
