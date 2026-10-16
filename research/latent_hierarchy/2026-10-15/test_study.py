"""Independent constructed timing/identification checks. Not market-alpha tests."""
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from study import (ROOT,BASE,CHILD,rollover,features,attach_labels,fit_year,score,interval,alerts,
                   shuffle_maps,read_data,conditional_candidate,frozen_baseline,fit_year,sha)
from mapping import mapping,definitions

class ScientificChecks(unittest.TestCase):
    def test_exact_sic_crosswalk(self):
        m=mapping();self.assertEqual(m['pure_industries'],38)
        self.assertEqual(len(m['mixed_excluded']),11)
        self.assertEqual(len(m['retained']),7)
        self.assertEqual(sorted(len(v) for v in m['retained'].values()),[2,2,3,4,7,8,10])
        self.assertNotIn('Toys',sum(m['retained'].values(),[]))

    def test_all_49_sic_ranges_are_globally_disjoint(self):
        groups=definitions(ROOT/'private/Siccodes49.zip')
        seen=set()
        for name,codes in groups.items():
            self.assertFalse(seen.intersection(codes),name+' repeated SIC code')
            seen.update(codes)
        self.assertEqual(len(seen),5054)

    def test_scrambles_preserve_exact_child_multiset(self):
        m=mapping();original=sum(m['retained'].values(),[])
        for seed in [9101526,9101527,9101528,9101529]:
            z=shuffle_maps(m,seed)
            self.assertEqual(sorted(sum(z.values(),[])),sorted(original))
            self.assertEqual({k:len(v) for k,v in z.items()},{k:len(v) for k,v in m['retained'].items()})

    def test_rollover_known_dropout_can_invert_sign(self):
        # Large positive OLD return disappears; recent negative returns remain.
        a=np.array([.04]+[-.001]*20)
        self.assertGreater(a.sum(),.005)
        z=rollover(a,1,vol=.01)
        self.assertEqual(z['known_rollover_confirmed'],1)
        self.assertLess(z['known_rollover_margin'],0)

    def test_rollover_does_not_invent_unobserved_future(self):
        a=np.array([.004]*21)
        z=rollover(a,1,vol=.01)
        self.assertEqual(z['known_rollover_confirmed'],0)
        self.assertEqual(z['known_rollover_first_day'],22)

    def test_rollover_ignores_future_input(self):
        a=np.array([.04]+[-.001]*20)
        same=rollover(a,1,vol=.012)
        future=np.array([-10,.02,.5])
        self.assertEqual(same,rollover(np.r_[a,future][:21],1,vol=.012))

    def test_rollover_rejects_boolean_zero_sign_nonfinite(self):
        for sign in [0,2,True]:
            with self.assertRaises(ValueError):rollover(np.ones(21)*.001,sign)
        a=np.ones(21);a[4]=np.nan
        with self.assertRaises(ValueError):rollover(a,1)

    def make_synthetic(self,n=720):
        rng=np.random.default_rng(20261015)
        idx=pd.bdate_range('1980-01-01',periods=n)
        names=['NoDur','Durbl','Manuf','Enrgy','HiTec','Telcm','Shops','Hlth','Utils','Other']
        m=mapping();children=sorted(set(sum(m['retained'].values(),[])))
        vw=pd.DataFrame(rng.normal(.0005,.008,(n,len(names))),index=idx,columns=names)
        ew=vw+pd.DataFrame(rng.normal(0,.001,(n,len(names))),index=idx,columns=names)
        vw49=pd.DataFrame(rng.normal(.0004,.009,(n,len(children))),index=idx,columns=children)
        ff=pd.DataFrame(rng.normal(0,.004,(n,3)),index=idx,columns=['Mkt-RF','SMB','HML']);ff['RF']=.00005
        return vw,ew,vw49,ff,m

    def test_complete_feature_prefix_invariance(self):
        vw,ew,k,f,m=self.make_synthetic()
        a=features(vw,ew,k,f,m)
        b=features(vw.iloc[:670],ew.iloc[:670],k.iloc[:670],f.iloc[:670],m)
        a=a[a.date<=vw.index[669]]
        columns=BASE+[family+'_'+s for family in ['real','placebo0','placebo1','placebo2','placebo3'] for s in CHILD]
        np.testing.assert_allclose(a[columns].astype(float),b[columns].astype(float),equal_nan=True,atol=1e-9,rtol=1e-9)

    def test_target_confirmed_only_after_three_full_sessions(self):
        idx=pd.bdate_range('2000-01-01',periods=680)
        r=np.zeros(680);r[580:601]=.002;r[601:606]=-.02
        vw=pd.DataFrame({'NoDur':np.expm1(r)},index=idx)
        ff=pd.DataFrame({'Mkt-RF':np.zeros(680),'RF':np.zeros(680)},index=idx)
        z=pd.DataFrame({'date':[idx[600]],'parent':['NoDur'],'pos':[600],'rs21':[.042]})
        actual,sk=attach_labels(z,vw,ff)
        self.assertEqual(len(actual),1)
        self.assertEqual(actual['class'].iloc[0],1)
        self.assertGreaterEqual(actual['confirmation_delay'].iloc[0],3)
        self.assertEqual(actual['entry_date'].iloc[0],idx[601])
        self.assertEqual(actual['label_end'].iloc[0],idx[621])

    def test_known_rollover_only_can_trigger_observed_target(self):
        idx=pd.bdate_range('2000-01-01',periods=680)
        r=np.zeros(680);r[580]=.04;r[581:601]=-.001
        vw=pd.DataFrame({'NoDur':np.expm1(r)},index=idx)
        ff=pd.DataFrame({'Mkt-RF':np.zeros(680),'RF':np.zeros(680)},index=idx)
        z=pd.DataFrame({'date':[idx[600]],'parent':['NoDur'],'pos':[600],'rs21':[.02]})
        y,_=attach_labels(z,vw,ff)
        self.assertEqual(y['class'].iloc[0],1)
        self.assertEqual(rollover(r[580:601],1,vol=.01)['known_rollover_confirmed'],1)

    def test_missing_horizon_does_not_mean_no_pivot(self):
        idx=pd.bdate_range('2000-01-01',periods=680)
        r=np.zeros(680);r[580:601]=.002;r[605]=np.nan
        vw=pd.DataFrame({'NoDur':np.expm1(r)},index=idx)
        ff=pd.DataFrame({'Mkt-RF':np.zeros(680),'RF':np.zeros(680)},index=idx)
        z=pd.DataFrame({'date':[idx[600],idx[601]],'parent':['NoDur','NoDur'],'pos':[600,601],'rs21':[.042,.040]})
        with self.assertRaises(ValueError):attach_labels(z,vw,ff)

    def test_threshold_initial_rs_eligibility_prefix_only(self):
        idx=pd.bdate_range('2000-01-01',periods=680)
        v=np.zeros(680);v[580:601]=.0001
        vw=pd.DataFrame({'NoDur':np.expm1(v)},index=idx)
        ff=pd.DataFrame({'Mkt-RF':np.zeros(680),'RF':np.zeros(680)},index=idx)
        z=pd.DataFrame({'date':[idx[600]],'parent':['NoDur'],'pos':[600],'rs21':[.0021]})
        with self.assertRaises(ValueError):attach_labels(z,vw,ff)

    def model_panel(self,n=900):
        rng=np.random.default_rng(17)
        x=pd.DataFrame(rng.normal(size=(n,len(BASE))),columns=BASE)
        y=(.8*x['rs5']-.4*x['rs63']+rng.normal(scale=.7,size=n)>0).astype(int)
        x['class']=y
        for c in CHILD:
            x['real_'+c]=x['rs5'] # exact redundant information after zscore
            for k in range(4):x[f'placebo{k}_'+c]=x['rs5']
        return x

    def test_identical_child_information_does_not_change_baseline(self):
        x=self.model_panel();pred,receipt=fit_year(x.iloc[:700],x.iloc[700:])
        self.assertEqual(receipt['real']['n_independent_training_features'],0)
        np.testing.assert_allclose(pred['real'],pred['baseline'],atol=1e-12,rtol=0)
        for name in ['placebo0','placebo1','placebo2','placebo3']:
            np.testing.assert_allclose(pred[name],pred['baseline'],atol=1e-12,rtol=0)

    def test_parent_penalty_unchanged_by_orthogonal_new_feature(self):
        x=self.model_panel()
        x['real_breadth5']=(x.rs21*x.rs63)
        xtrain,xtest=x.iloc[:700],x.iloc[700:]
        aa,bb,ot,oe,rec=frozen_baseline(xtrain,xtest)
        baseline_offset_before=oe.copy()
        prior_features=aa.copy()
        p,r=conditional_candidate(xtrain,xtest,'real',aa,bb,ot,oe)
        np.testing.assert_allclose(oe,baseline_offset_before,atol=0,rtol=0)
        np.testing.assert_array_equal(aa,prior_features)
        self.assertLess(r['max_training_linear_cross_moment'],1e-10)
        self.assertGreaterEqual(r['n_independent_training_features'],1)
        prediction,_=fit_year(xtrain,xtest)
        np.testing.assert_allclose(prediction['baseline'],expit_safe(baseline_offset_before),atol=1e-12,rtol=0)

    def test_probability_and_loss_range(self):
        x=self.model_panel();pred,_=fit_year(x.iloc[:700],x.iloc[700:])
        y=x.iloc[700:].copy()
        for name,p in pred.items():
            self.assertTrue(np.isfinite(p).all());self.assertTrue(((p>=0)&(p<=1)).all())
            y[name]=p
            self.assertTrue(0<=score(y,name)['brier']<=1)

    def test_date_blocks_are_primary_inference_units(self):
        d=pd.bdate_range('2010-01-01',periods=150)
        z=pd.DataFrame({'date':np.repeat(d,2),'class':np.tile([0,1],len(d)),
                        'baseline':np.full(len(d)*2,.5),'real':np.full(len(d)*2,.6)})
        a=interval(z)
        self.assertEqual(a['dates'],150)
        self.assertEqual(a['independent_units'],'WEEKLY_ORIGIN_DATES_NOT_PARENT_ROWS')

    def test_matching_alert_count_before_cooldown(self):
        days=pd.date_range('2010-01-01',periods=6,freq='7D')
        x=[]
        for j,t in enumerate(days):
            for i in range(7):x.append({'date':t,'parent':str(i),'pos':100+j*5,'class':int(i==0),
                     'real':.99-i*.02,'baseline':.99-i*.02,'confirmation_delay':5 if i==0 else None,
                     'forward_signed_logrel':.01})
        df=pd.DataFrame(x);report=alerts(df,'real')
        self.assertEqual(report['weekly_alerts'],12)
        self.assertEqual(report['correct'],6)
        self.assertGreater(report['weekly_alerts'],report['declustered_episodes'])


def expit_safe(x):
    from scipy.special import expit
    return expit(x)

if __name__=='__main__':unittest.main(verbosity=2)
