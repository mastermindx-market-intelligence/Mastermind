import unittest
import numpy as np
import pandas as pd
from modeling import ConditionalLogit,training_rows,date_weights,frequency,losses,holm

class ModelTests(unittest.TestCase):
    def frame(self,n=300):
        rng=np.random.default_rng(42);x=rng.normal(size=n);date=pd.bdate_range('2010-01-04',periods=n)
        return pd.DataFrame({'x':x,'y':(x+rng.normal(size=n)*.8>0).astype(int),'origin':date,
          'end_date':date+pd.offsets.BDay(21),'event_id':['e'+str(i) for i in range(n)],
          'group':['g']*n,'family':['dot']*n,'symbol':['A']*n,'horizon':[21]*n,
          'outcome_status':['COMPLETE']*n,'exposed_design_case':[False]*n})
    def test_mature_labels_only(self):
        x=self.frame();at=x.origin.iloc[200];tr=training_rows(x,at,'y',21)
        self.assertTrue((tr.end_date<at).all());self.assertLess(len(tr),200)
    def test_exposed_case_never_training(self):
        x=self.frame();x.loc[:100,'exposed_design_case']=True;tr=training_rows(x,pd.Timestamp('2015-01-01'),'y',21)
        self.assertFalse(tr.exposed_design_case.any());self.assertEqual(len(tr),199)
    def test_model_does_not_mutate_inputs(self):
        x=self.frame();old=x.copy(deep=True);model=ConditionalLogit(['x']).fit(x,'y');model.predict(x);pd.testing.assert_frame_equal(x,old)
    def test_future_test_values_not_standardization(self):
        x=self.frame();m=ConditionalLogit(['x']).fit(x,'y');med=m.median.copy();scale=m.scale.copy();test=x.copy();test['x']=1e6;m.predict(test)
        np.testing.assert_array_equal(m.median,med);np.testing.assert_array_equal(m.scale,scale)
    def test_invalid_probability_refused(self):
        with self.assertRaises(ValueError):losses([0,1],[0,1])
    def test_unknown_category_does_not_change_coefficients(self):
        x=self.frame();m=ConditionalLogit(['x']).fit(x,'y');test=x.iloc[:4].copy();test['symbol']='UNSEEN';p=m.predict(test)
        self.assertTrue(((p>0)&(p<1)).all())
    def test_one_class_refused(self):
        x=self.frame();x['y']=1
        with self.assertRaises(ValueError):ConditionalLogit(['x']).fit(x,'y')
    def test_missing_features_are_not_zero_risk(self):
        x=self.frame();x.loc[:60,'x']=np.nan;m=ConditionalLogit(['x']).fit(x,'y');self.assertTrue(np.isfinite(m.predict(x)).all())
    def test_date_weights_preserve_date_mass(self):
        x=self.frame(6);x.loc[:2,'origin']=x.origin.iloc[0];w=date_weights(x);self.assertAlmostEqual(w[:3].sum(),w[3])
    def test_holm_cannot_improve_raw_p(self):
        x=pd.DataFrame({'p_raw':[.01,.04,.2]});h=holm(x);self.assertTrue((h>=x.p_raw).all())
    def test_frequency_shrinks_unknown_name(self):
        tr=self.frame();test=tr.iloc[:2].copy();test['symbol']='OTHER';p=frequency(tr,test,'y');self.assertTrue((p>0).all());self.assertTrue((p<1).all())

if __name__=='__main__':unittest.main()
