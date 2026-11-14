"""Behavioral and real-source timing checks for the independent experiment."""
import importlib.util
import json
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
import experiment as ex
from native_replay import frame, load_math, dots

ROOT=Path(__file__).resolve().parent

class MechanicsTests(unittest.TestCase):
    def panel(self,n=800):
        ix=pd.bdate_range('2007-01-02',periods=n)
        p=pd.DataFrame({k:100*np.exp(.0002*np.arange(n)+.04*np.sin(np.arange(n)/12+j)) for j,k in enumerate(ex.SECTORS+['SPY'])},index=ix)
        v=pd.DataFrame({'VIX':20+np.sin(np.arange(n)/30),'VVIX':90+2*np.sin(np.arange(n)/25),'VIX3M':21.},index=ix)
        return p,p.copy(),v
    def test_reserved_window_refused(self):
        with self.assertRaises(ValueError):ex.check_index(pd.bdate_range('2019-12-30',periods=5))
    def test_duplicate_dates_refused(self):
        with self.assertRaises(ValueError):ex.check_index(pd.DatetimeIndex(['2015-01-01','2015-01-01']))
    def test_onset_not_board_days(self):
        x=pd.Series([False]*3+[True]*6+[False]*2+[True]+[False]*3+[True])
        self.assertEqual(list(np.flatnonzero(ex.onset(x))),[3,15])
    def test_context_prefix_invariance(self):
        p,t,v=self.panel();a=ex.context(p,t,v);b=ex.context(p.iloc[:650],t.iloc[:650],v.iloc[:650])
        for k in a:
            if isinstance(a[k],pd.DataFrame):pd.testing.assert_frame_equal(a[k].iloc[:650],b[k])
            else:pd.testing.assert_series_equal(a[k].iloc[:650],b[k])
    def test_missing_vvix_not_calm(self):
        p,t,v=self.panel();v.VVIX=np.nan;c=ex.context(p,t,v)
        d=pd.DataFrame(False,index=p.index,columns=ex.SECTORS);d.iloc[600]=True
        policies=ex.policies(d,c)
        self.assertTrue(policies['dot'].iloc[600].all())
        self.assertFalse(policies['dot_vvix_not_rising'].to_numpy().any())
    def test_protected_gap_warmup(self):
        ix=pd.bdate_range('2023-06-01',periods=600);m=ex.eval_mask(ix,'post')
        self.assertFalse(m[:504].any());self.assertTrue(m[504:].all())
    def test_memory_not_indefinite(self):
        p,t,v=self.panel(100);c=ex.context(p,t,v)
        c['stress'][:]=True;c['repair'][:]=True;c['own5'][:]=.01
        d=pd.DataFrame(False,index=p.index,columns=ex.SECTORS);d.iloc[40]=True
        s=ex.policies(d,c)['sequence_repair'];self.assertEqual(list(np.flatnonzero(s.iloc[:,0])),[40])
        c['repair'][:]=False;c['repair'].iloc[47:]=True
        self.assertFalse(ex.policies(d,c)['sequence_repair'].to_numpy().any())
    def test_memory_can_wait_for_repair(self):
        p,t,v=self.panel(100);c=ex.context(p,t,v)
        c['stress'][:]=True;c['repair'][:]=False;c['repair'].iloc[43:]=True;c['own5'][:]=.01
        d=pd.DataFrame(False,index=p.index,columns=ex.SECTORS);d.iloc[40]=True
        self.assertEqual(list(np.flatnonzero(ex.policies(d,c)['sequence_repair'].iloc[:,0])),[43])
        self.assertFalse(ex.policies(d,c)['same_day_sequence'].to_numpy().any())
    def test_costs_reduce_identical_trades(self):
        p,t,v=self.panel(100);s=pd.DataFrame(False,index=p.index,columns=ex.SECTORS);s.iloc[[5,35,65]]=True
        a=ex.account(t,s,np.ones(100,bool),21,.0005);b=ex.account(t,s,np.ones(100,bool),21,.002)
        self.assertEqual(a['metrics']['closed_trades'],b['metrics']['closed_trades'])
        self.assertLess(b['curve'].equity.iloc[-1],a['curve'].equity.iloc[-1])
    def test_next_close_not_signal_close(self):
        p,t,v=self.panel(100);t[:]=100.;t.iloc[11:,0]=200.
        s=pd.DataFrame(False,index=p.index,columns=ex.SECTORS);s.iloc[10,0]=True
        a=ex.account(t,s,np.ones(100,bool),21,0)
        self.assertAlmostEqual(a['metrics']['total_return'],0.)
        self.assertEqual(a['trades'][0]['entry'],str(p.index[11].date()))
    def test_independent_account_identity(self):
        p,t,v=self.panel(100);t[:]=100.;t.iloc[12:,0]=110.
        s=pd.DataFrame(False,index=p.index,columns=ex.SECTORS);s.iloc[10,0]=True
        a=ex.account(t,s,np.ones(100,bool),21,.0005)
        expected=8/9+(1/9)*1.1*.9995/1.0005
        self.assertAlmostEqual(a['curve'].equity.iloc[-1],expected,places=13)
    def test_no_pyramiding(self):
        p,t,v=self.panel(100);s=pd.DataFrame(True,index=p.index,columns=ex.SECTORS)
        a=ex.account(t,s,np.ones(100,bool),21,0)
        self.assertLessEqual(a['metrics']['closed_trades'],9*4)
        self.assertLessEqual(a['curve'].gross.max(),1.000000001)
    def test_no_position_no_return(self):
        p,t,v=self.panel(100);s=pd.DataFrame(False,index=p.index,columns=ex.SECTORS)
        a=ex.account(t,s,np.ones(100,bool),21,.0005)
        self.assertAlmostEqual(a['metrics']['total_return'],0.)
        self.assertIsNone(a['metrics']['sharpe'])
    def test_complete_horizon_only(self):
        p,t,v=self.panel(100);s=pd.DataFrame(False,index=p.index,columns=ex.SECTORS);s.iloc[-10:]=True
        a=ex.account(t,s,np.ones(100,bool),21,0);self.assertEqual(a['metrics']['closed_trades'],0)
    def test_no_reserved_crossing_in_events(self):
        p,t,v=self.panel(100);s=pd.DataFrame(False,index=p.index,columns=ex.SECTORS);s.iloc[-10]=True
        e=ex.event_outcomes(p,t,{'dot':s},np.ones(100,bool),ex.context(p,t,v),0,'pre')
        self.assertTrue(e.empty)

class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads((ROOT/'INPUT_MANIFEST.json').read_text())
        cls.c,mask=load_math(ROOT/'source',cls.manifest)
        cls.mask=staticmethod(mask)
    def test_wrong_source_refused(self):
        m=json.loads(json.dumps(self.manifest));m['source_files']['signal_layer/confluence.py']='0'*64
        with self.assertRaises(ValueError):load_math(ROOT/'source',m)
    def test_prefix_snapshot_invariance(self):
        x=pd.read_parquet(ROOT/'private/XLK_pre.parquet').close_price
        a,_=dots(x.iloc[:1800],self.c,self.mask);b,_=dots(x.iloc[:1501],self.c,self.mask)
        pd.testing.assert_series_equal(a.iloc[:1501],b)
    def test_exact_native_input_fields(self):
        # Full original module has no top-level execution beyond imports/literal config;
        # __main__ is not run. It is used only for parity of the pure signal inputs.
        spec=importlib.util.spec_from_file_location('_frozen_c',ROOT/'source/confluence.py')
        native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
        x=pd.read_parquet(ROOT/'private/XLP_pre.parquet').close_price
        for n in (600,1000,1501):
            for phase in (0,1,2):
                a=frame(x.iloc[:n],self.c,phase);b=native.compute_signals(x.iloc[:n],bar_anchor=phase)
                for k in ['macd','sig','k','d','rsi14','known_ts']:
                    pd.testing.assert_series_equal(a[k],b[k],check_names=False)
    def test_completed_bars_and_known_clocks(self):
        x=pd.read_parquet(ROOT/'private/XLE_pre.parquet').close_price.iloc[:1800]
        for phase in (0,1,2):
            _,records=dots(x,self.c,self.mask,phase)
            self.assertGreater(len(records),1)
            for r in records:
                i=x.index.get_loc(pd.Timestamp(r['known_session']))
                self.assertEqual((i+phase)%3,0)
                self.assertGreaterEqual(r['known_session'],r['signal_label'])
                self.assertFalse(r['provisional'])

if __name__=='__main__':unittest.main()
