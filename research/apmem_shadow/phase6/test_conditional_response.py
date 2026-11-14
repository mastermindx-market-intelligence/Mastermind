import unittest
import numpy as np
import pandas as pd
from conditional_response import ConditionalResponse

class ConditionalResponseTests(unittest.TestCase):
    def fixture(self,n=600):
        rng=np.random.default_rng(18);x=rng.normal(size=n);group=np.where(np.arange(n)%2==0,'A','B')
        y=np.where(group=='A',x,-x)+rng.normal(0,.1,n)
        dates=pd.bdate_range('2007-01-02',periods=n)
        return pd.DataFrame({'slow_mean_change':x,'y':y,'binary':(y>0).astype(int),'group':group,
           'family':['dot']*n,'symbol':group,'origin':dates,'end_date':dates+pd.offsets.BDay(21),
           'event_id':['e'+str(i) for i in range(n)]})
    def test_group_response_can_represent_opposite_effects(self):
        x=self.fixture();shared=ConditionalResponse(['slow_mean_change'],heterogeneous=False).fit_mean(x,'y')
        conditional=ConditionalResponse(['slow_mean_change'],heterogeneous=True).fit_mean(x,'y')
        a=np.mean((shared.predict_mean(x)-x.y)**2);b=np.mean((conditional.predict_mean(x)-x.y)**2)
        self.assertLess(b,a*.5)
    def test_group_deviations_have_stronger_penalty(self):
        x=self.fixture();m=ConditionalResponse(['slow_mean_change'],heterogeneous=True).fit_mean(x,'y')
        self.assertTrue((m.penalty_vector[-3:]>=5).all())
    def test_predict_does_not_refit(self):
        x=self.fixture();m=ConditionalResponse(['slow_mean_change'],heterogeneous=True).fit_mean(x,'y')
        beta=m.beta.copy();test=x.iloc[:10].copy();test['slow_mean_change']=1e4;m.predict_mean(test)
        np.testing.assert_array_equal(m.beta,beta)
    def test_unseen_group_keeps_shared_prediction(self):
        x=self.fixture();m=ConditionalResponse(['slow_mean_change'],heterogeneous=True).fit_mean(x,'y')
        test=x.iloc[:3].copy();test['group']='UNSEEN';test['symbol']='NEW'
        self.assertTrue(np.isfinite(m.predict_mean(test)).all())
    def test_training_data_not_mutated(self):
        x=self.fixture();old=x.copy(deep=True);ConditionalResponse(['slow_mean_change'],heterogeneous=True).fit(x,'binary')
        pd.testing.assert_frame_equal(x,old)
    def test_nonfinite_training_payoff_refused(self):
        x=self.fixture();x.loc[0,'y']=np.nan
        with self.assertRaises(ValueError):ConditionalResponse(['slow_mean_change']).fit_mean(x,'y')

if __name__=='__main__':unittest.main()
