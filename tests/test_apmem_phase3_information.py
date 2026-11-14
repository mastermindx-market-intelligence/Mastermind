import unittest
import numpy as np
import pandas as pd
from research.apmem_shadow.phase3.information import likelihood_decomposition,exact_date_retention

class InformationTests(unittest.TestCase):
    def test_exact_likelihood_identity(self):
        p=np.array([[.3,.2,.5],[.4,.5,.1],[.2,.3,.5]])
        y=np.array([0,1,2]);d=pd.DataFrame(p,columns=['p_stop','p_target','p_timeout'])
        d['event_id']=['a','b','c'];d['model']='m';d['class_id']=y
        d['log_loss']=-np.log(p[np.arange(3),y])
        out,summary=likelihood_decomposition(d)
        np.testing.assert_allclose(out.total_log_loss_reconciled,d.log_loss)
        self.assertEqual(summary.active_n.iloc[0],2)
        self.assertTrue(np.isnan(out.direction_log_loss_on_active.iloc[2]))
    def test_wrong_stored_loss_refused(self):
        d=pd.DataFrame({'event_id':['a'],'model':['m'],'class_id':[0],
                        'p_stop':[.3],'p_target':[.2],'p_timeout':[.5],'log_loss':[0.]})
        with self.assertRaises(ValueError):likelihood_decomposition(d)
    def test_date_counts_exact_and_seeded(self):
        d=pd.DataFrame({'event_id':list('abcdef'),'origin':['2020-01-01']*3+['2020-01-02']*2+['2020-01-03']})
        a,receipt=exact_date_retention(d,{'a','c','d','f'},17)
        b,_=exact_date_retention(d,{'a','c','d','f'},17)
        pd.testing.assert_frame_equal(a,b)
        self.assertEqual(a.groupby('origin').size().tolist(),[2,1,1])
        self.assertEqual(receipt['exchangeable_dates'],2)
        self.assertEqual(receipt['exchangeable_events'],5)
    def test_singleton_has_no_randomization_power(self):
        d=pd.DataFrame({'event_id':['a'],'origin':['2020-01-01']})
        a,r=exact_date_retention(d,{'a'},1);self.assertEqual(r['exchangeable_fraction'],0.)
        self.assertEqual(a.event_id.tolist(),['a'])
    def test_foreign_retention_refused(self):
        d=pd.DataFrame({'event_id':['a'],'origin':['2020-01-01']})
        with self.assertRaises(ValueError):exact_date_retention(d,{'b'},1)

if __name__=='__main__':unittest.main()
