from __future__ import annotations
import json,unittest
from pathlib import Path
import numpy as np
import pandas as pd
import features as f
from native_replay import load_math

ROOT=Path(__file__).parent

def series(n=1300,start='2005-01-03',seed=3):
    r=np.random.default_rng(seed).normal(.0002,.012,n)
    return pd.Series(100*np.exp(np.cumsum(r)),index=pd.bdate_range(start,periods=n))

class TimeAndEpisodeTests(unittest.TestCase):
    def test_protected_window_refused(self):
        with self.assertRaises(ValueError):f.validate_index(pd.date_range('2020-01-01',periods=5))
    def test_protected_gap_refused(self):
        with self.assertRaises(ValueError):f.validate_index(pd.DatetimeIndex(['2019-12-31','2023-06-01']))
    def test_duplicate_dates_refused(self):
        with self.assertRaises(ValueError):f.validate_index(pd.DatetimeIndex(['2019-12-31']*2))
    def test_calendar_month_never_uses_partial(self):
        s=series(20,start='2019-01-01');b=f.period_bars(s,'1M');self.assertEqual(len(b),0)
    def test_calendar_partial_2w_not_closed(self):
        s=series(100);b=f.period_bars(s.iloc[:97],'2W')
        self.assertTrue((b.index<=s.index[96]).all())
        full=f.period_bars(s,'2W').loc[:s.index[96]]
        pd.testing.assert_frame_equal(b,full)
    def test_map_never_backdates_known_value(self):
        s=pd.DataFrame({'x':[7.]},index=pd.DatetimeIndex(['2019-01-31']))
        out=f.map_known(s,pd.bdate_range('2019-01-28',periods=5))
        self.assertTrue(out.x.iloc[:3].isna().all());self.assertEqual(out.x.iloc[3],7.)
    def test_causal_rank_prefix(self):
        s=series(500);a=f.causal_rank(s);b=f.causal_rank(s.iloc[:400]);pd.testing.assert_series_equal(a.iloc[:400],b)
    def test_causal_rank_uses_prior_not_self(self):
        s=pd.Series([1.,2.,3.,4.]);r=f.causal_rank(s,3,3);self.assertEqual(r.iloc[-1],1.)
    def test_prior_failure_only_after_breach(self):
        p=pd.Series([100.]*21+[90.,95.,85.,88.],index=pd.bdate_range('2019-01-01',periods=25))
        dot=pd.Series(False,index=p.index);dot.iloc[21]=True;dot.iloc[24]=True
        out=f.episode_features(p,dot)
        self.assertEqual(out.prior_failed_attempts.iloc[22],0)
        self.assertEqual(out.prior_failed_attempts.iloc[23],1)
        self.assertEqual(out.prior_attempts.iloc[24],1)
    def test_recovered_peak_resets_episode(self):
        p=pd.Series([100.]*21+[90.,85.,101.],index=pd.bdate_range('2019-01-01',periods=24))
        dots=pd.Series(False,index=p.index);dots.iloc[21]=True
        out=f.episode_features(p,dots);self.assertEqual(out.episode_number.iloc[-1],0);self.assertEqual(out.prior_failed_attempts.iloc[-1],0)
    def test_episode_prefix_invariance(self):
        p=series(700);d=pd.Series(np.arange(700)%30==0,index=p.index)
        pd.testing.assert_frame_equal(f.episode_features(p,d).iloc[:550],f.episode_features(p.iloc[:550],d.iloc[:550]))
    def test_phase_confirmation_observed_later(self):
        x=np.zeros((9,3),bool);x[1,0]=True;x[2,1]=True;x[4,2]=True
        y=f.confirmed_phase_onset(x);self.assertEqual(np.flatnonzero(y).tolist(),[4])
    def test_phase_confirmation_label_invariance(self):
        x=np.random.default_rng(1).uniform(size=(100,3))>.85
        np.testing.assert_array_equal(f.confirmed_phase_onset(x),f.confirmed_phase_onset(x[:,[2,0,1]]))
    def test_phase_confirmation_expires(self):
        x=np.zeros((12,3),bool);x[0,0]=True;x[1,1]=True;x[8,2]=True
        self.assertFalse(f.confirmed_phase_onset(x).any())
    def test_interpretation_unknown_not_safe(self):self.assertEqual(f.interpretation({}),'CONTEXT_INCOMPLETE')

class NativeAndPeerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ROOT/'INPUT_MANIFEST.json').exists():raise unittest.SkipTest('Private native source not installed')
        m=json.loads((ROOT/'INPUT_MANIFEST.json').read_text());cls.c,mask=load_math(ROOT/'source',m);cls.mask=staticmethod(mask)
    def test_slow_calendar_prefix_invariance(self):
        p=series(1400)
        for unit in ['2W','1M']:
            a=f.slow_features(p,self.c,unit);b=f.slow_features(p.iloc[:1103],self.c,unit)
            pd.testing.assert_frame_equal(a.iloc[:1103],b)
    def test_own_prefix_invariance(self):
        p=series(1000);a=f.own_features(p,self.c,self.mask);b=f.own_features(p.iloc[:811],self.c,self.mask)
        pd.testing.assert_frame_equal(a.iloc[:811],b)
    def test_peer_excludes_focal(self):
        p=pd.DataFrame({s:series(600,seed=i+1) for i,s in enumerate(['A','B','C','D'])})
        t=p.copy();a=f.peer_context(p,t,'A',['A','B','C','D']);p['A']*=np.linspace(.1,10,len(p));t['A']=p.A
        b=f.peer_context(p,t,'A',['A','B','C','D']);pd.testing.assert_frame_equal(a,b)
    def test_missing_peer_is_unknown_not_zero(self):
        p=pd.DataFrame({s:series(600,seed=i+1) for i,s in enumerate(['A','B','C','D'])});p.loc[p.index[-20:],['B','C','D']]=np.nan
        a=f.peer_context(p,p,'A',['A','B','C','D'])
        self.assertFalse(a.peer_valid.iloc[-1]);self.assertTrue(pd.isna(a.peer_above20.iloc[-1]));self.assertFalse(a.peer_repair.iloc[-1])
    def test_peer_future_mutation_invariance(self):
        p=pd.DataFrame({s:series(600,seed=i+1) for i,s in enumerate(['A','B','C','D'])});a=f.peer_context(p,p,'A',list(p))
        p.iloc[500:]*=10;b=f.peer_context(p,p,'A',list(p));pd.testing.assert_frame_equal(a.iloc[:500],b.iloc[:500])
    def test_too_few_peers_refused(self):
        p=pd.DataFrame({'A':series(600),'B':series(600,seed=4)})
        with self.assertRaises(ValueError):f.peer_context(p,p,'A',['A','B'])
    def test_missing_volatility_preserved(self):
        p=pd.DataFrame({s:series(700,seed=i+1) for i,s in enumerate(['A','B','C','SPY'])});v=pd.DataFrame({'VIX':20.,'VVIX':np.nan},index=p.index)
        own=f.own_features(p.A,self.c,self.mask);a=f.context_features(p,p,v,'A',['A','B','C'],own)
        self.assertTrue(a.vvix_trend.isna().all());self.assertFalse(any('authority' in k for k in a.columns))

if __name__=='__main__':unittest.main()
