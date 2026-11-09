"""Focused temporal, graph and scoring tests. Not financial validation."""
import unittest
import numpy as np
import pandas as pd
from network_study import (innovations,estimate_graph,top_graph,make_graphs,build_features,
                           attach_labels,ridge,BASE,NET,GRAPHS,correlation,block_interval)

class NetworkTests(unittest.TestCase):
    def data(self,n=1700):
        rng=np.random.default_rng(1802)
        dates=pd.bdate_range('2000-01-03',periods=n)
        f=pd.DataFrame(rng.normal(0,.007,(n,3)),index=dates,columns=['Mkt-RF','SMB','HML']);f['RF']=.0001
        values=pd.DataFrame(rng.normal(0,.01,(n,6)),index=dates,columns=list('ABCDEF'))
        return values,f

    def test_factor_coefficients_do_not_use_current_response(self):
        v,f=self.data(600);a=innovations(v,f);v2=v.copy();v2.iloc[400,0]+=.3;b=innovations(v2,f)
        np.testing.assert_allclose(a.iloc[:400],b.iloc[:400],equal_nan=True)
        self.assertAlmostEqual(b.iloc[400,0]-a.iloc[400,0],.3,places=10)

    def test_direction_orientation_known_leader(self):
        rng=np.random.default_rng(800);leader=rng.normal(size=2000)
        follower=np.r_[np.zeros(5),leader[:-5]]+.05*rng.normal(size=2000)
        noise=rng.normal(size=2000);a=estimate_graph(np.c_[leader,follower,noise])['directed'][0]
        self.assertGreater(a[1,0],.8)
        self.assertEqual(a[0,1],0)

    def test_top_graph_positive_diagonal_and_coverage(self):
        a=np.array([[9,.4,-.2],[.8,9,.2],[-.1,-.2,9]])
        w,strength,coverage=top_graph(a,k=2)
        np.testing.assert_array_equal(np.diag(w),0)
        np.testing.assert_allclose(w.sum(1),[1,1,0])
        np.testing.assert_allclose(coverage,[.5,1,0])
        self.assertEqual(strength[2],0)

    def test_relabeling_preserves_weight_multiset(self):
        rng=np.random.default_rng(160);graphs=estimate_graph(rng.normal(size=(756,10)));orig=graphs['directed'][0]
        for name in GRAPHS:
            if name.startswith('placebo'):
                w=graphs[name][0]
                np.testing.assert_allclose(np.sort(w.ravel()),np.sort(orig.ravel()))
                np.testing.assert_array_equal(np.diag(w),0)
                np.testing.assert_array_equal(np.sort((w>0).sum(0)),np.sort((orig>0).sum(0)))
                np.testing.assert_array_equal(np.sort((w>0).sum(1)),np.sort((orig>0).sum(1)))

    def test_graph_end_before_feature_year(self):
        v,f=self.data();res=innovations(v,f);g,receipts=make_graphs(res)
        for r in receipts:self.assertLess(pd.Timestamp(r['last_source_date']),pd.Timestamp(f"{r['year']}-01-01"))
        self.assertTrue(receipts)

    def test_full_feature_prefix_invariance(self):
        v,f=self.data();a,_,_=build_features(v,f);b,_,_=build_features(v.iloc[:1400],f.iloc[:1400])
        cols=BASE+[g+'_'+k for g in GRAPHS for k in NET]
        old=a[a.date<=v.index[1399]]
        np.testing.assert_allclose(old[cols],b[cols],equal_nan=True,rtol=1e-8,atol=1e-9)

    def test_current_year_future_cannot_change_graph(self):
        v,f=self.data();res=innovations(v,f);g,_=make_graphs(res)
        year=max(g);changed=res.copy();changed.loc[changed.index.year>=year]=1000
        b,_=make_graphs(changed)
        for name in GRAPHS:np.testing.assert_array_equal(g[year][name][0],b[year][name][0])

    def test_entry_day_return_is_excluded(self):
        v,f=self.data();z,_,_=build_features(v,f);one=z[(z.industry=='A')&(z.position==1200)]
        a,_=attach_labels(one,v,f,21);v2=v.copy();v2.iloc[1201,0]=.5;b,_=attach_labels(one,v2,f,21)
        self.assertAlmostEqual(a.future_relative_log.iloc[0],b.future_relative_log.iloc[0],places=10)
        self.assertEqual(a.entry_date.iloc[0],v.index[1201]);self.assertEqual(a.label_end.iloc[0],v.index[1222])

    def test_rank_target_is_date_centered(self):
        v,f=self.data();z,_,_=build_features(v,f);one=z[z.position==1200]
        a,_=attach_labels(one,v,f,5)
        self.assertAlmostEqual(a.target.mean(),0,places=12)
        self.assertGreater(a.target.max(),0);self.assertLess(a.target.min(),0)

    def test_missing_future_is_not_zero_return(self):
        v,f=self.data();z,_,_=build_features(v,f);one=z[z.position==1200];v.iloc[1203,0]=np.nan
        a,n=attach_labels(one,v,f,5)
        self.assertEqual(n,1);self.assertNotIn('A',list(a.industry))

    def test_ridge_fit_does_not_use_test_distribution(self):
        rng=np.random.default_rng(12)
        train=pd.DataFrame({'a':rng.normal(size=100),'b':rng.normal(size=100),'target':rng.normal(size=100),'label_end':pd.Timestamp('2000-01-01')})
        test=train.iloc[:10].copy();a,ra=ridge(train,test,['a','b']);test.loc[:,'a']+=100;b,rb=ridge(train,test,['a','b'])
        self.assertEqual(ra['coefficients_sha256'],rb['coefficients_sha256'])
        self.assertFalse(np.allclose(a,b))

    def test_no_short_sample_significance(self):
        r=block_interval(np.arange(27))
        self.assertIsNone(r['ci95']);self.assertIsNone(r['p'])
        self.assertEqual(r['inference'],'INSUFFICIENT_BLOCKS_DESCRIPTIVE_ONLY')

    def test_rank_ic_direction_and_constant(self):
        self.assertAlmostEqual(correlation([1,2,3],[3,2,1]),-1)
        self.assertEqual(correlation([1,1,1],[1,2,3]),0)

if __name__=='__main__':unittest.main(verbosity=2)
