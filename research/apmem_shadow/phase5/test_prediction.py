import unittest
import numpy as np
import pandas as pd
import prediction_check as pc
import experiment as ex
import test_experiment as fixtures

class PredictionTests(unittest.TestCase):
    def test_fit_and_prediction_are_bounded(self):
        rng=np.random.default_rng(7);x=rng.normal(size=(200,4));y=(x[:,0]+rng.normal(size=200)>.1).astype(int)
        f=pc.fit_logistic(x,y);p=pc.predict_logistic(f,x)
        self.assertTrue(np.isfinite(p).all());self.assertTrue(((p>0)&(p<1)).all())
        self.assertGreater(p[y==1].mean(),p[y==0].mean())
    def test_thin_labels_refused(self):
        with self.assertRaises(ValueError):pc.fit_logistic(np.zeros((149,2)),np.arange(149)%2)
        with self.assertRaises(ValueError):pc.fit_logistic(np.zeros((200,2)),np.zeros(200))
    def test_nonfinite_prediction_refused(self):
        f=pc.fit_logistic(np.zeros((200,2)),np.arange(200)%2)
        with self.assertRaises(ValueError):pc.predict_logistic(f,[[np.nan,1.]])
    def test_feature_prefix_invariance(self):
        p,t,v=fixtures.MechanicsTests().panel();c=ex.context(p,t,v)
        a=pc.feature_frame(p,t,v,c,'XLK')
        pp,tt,vv=p.iloc[:650],t.iloc[:650],v.iloc[:650]
        b=pc.feature_frame(pp,tt,vv,ex.context(pp,tt,vv),'XLK')
        pd.testing.assert_frame_equal(a.iloc[:650],b)
    def fixture(self):
        rng=np.random.default_rng(32);cal=pd.bdate_range('2007-01-02',periods=400);rows=[]
        for i in range(300):
            for j in range(2):
                rows.append({'event_id':str(i)+':'+str(j),'origin':str(cal[i].date()),'end':str(cal[i+22].date()),
                  'ticker':'A' if j==0 else 'B','segment':'pre',**{k:int(rng.integers(0,2)) for k in pc.TARGETS},
                  **dict(zip(pc.FEATURES,rng.normal(size=len(pc.FEATURES))))})
        return pd.DataFrame(rows),cal
    def test_matured_training_clocks(self):
        e,c=self.fixture();p,f=pc.walk_forward(e,c)
        self.assertGreater(len(p),0)
        self.assertTrue((p.training_last_outcome<p.fit_date).all())
        self.assertTrue((p.fit_date<=p.origin).all())
    def test_future_labels_cannot_change_prior_predictions(self):
        e,c=self.fixture();a,_=pc.walk_forward(e,c)
        cutoff=str(c[220].date());modified=e.copy();late=modified.end>=cutoff
        for k in pc.TARGETS:modified.loc[late,k]=1-modified.loc[late,k]
        b,_=pc.walk_forward(modified,c)
        aa=a.loc[a.origin<cutoff,['event_id','target','model','probability']].reset_index(drop=True)
        bb=b.loc[b.origin<cutoff,['event_id','target','model','probability']].reset_index(drop=True)
        pd.testing.assert_frame_equal(aa,bb)

if __name__=='__main__':unittest.main()
