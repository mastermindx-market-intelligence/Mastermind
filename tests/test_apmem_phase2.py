"""Causality, scientific comparisons, calibration, and accounting regressions."""
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from research.apmem_shadow.phase2.targets import prepare_prices,validate_prices,future_mean,causal_features
from research.apmem_shadow.phase2.forecasts import (Settings,qlike,direct_har,apmem_paths,
    loglink_fit,loglink_predict,combine)
from research.apmem_shadow.phase2.calibration import (return_quantiles,variance_upper,
    coverage_diagnostics,wilson)
from research.apmem_shadow.phase2.evaluation import (portfolio,delayed_weights,holm,
    block_mean_interval,base_exposures)
from research.apmem_shadow.phase2.consumer import research_context


def prices(n=220):
    rng=np.random.default_rng(315)
    c=100*np.exp(np.cumsum(rng.normal(.0002,.01,n)))
    o=c*np.exp(rng.normal(0,.003,n))
    return pd.DataFrame({"open":o,"high":np.maximum(o,c)*1.007,
        "low":np.minimum(o,c)*.993,"close":c,"dividends":np.zeros(n),
        "stock_splits":np.zeros(n)},index=pd.bdate_range("2010-01-01",periods=n))


class TargetsTests(unittest.TestCase):
    def test_forward_exact_and_censor(self):
        np.testing.assert_allclose(future_mean(np.arange(8.),5),[3,4,5,np.nan,np.nan,np.nan,np.nan,np.nan],equal_nan=True)
    def test_no_same_day_in_target(self):
        a=np.array([10.,2.,4.,6.]);np.testing.assert_allclose(future_mean(a,1),[2,4,6,np.nan],equal_nan=True)
    def test_dividend_gap_neutrality(self):
        p=prices(3);p.loc[:,:]=[100,101,99,100,0,0]
        p.iloc[1]=[99,100,98,99,1,0]
        x=prepare_prices(p)
        self.assertEqual(x.gap_var.iloc[0],0);self.assertEqual(x.return_log.iloc[0],0)
    def test_capital_distribution_added(self):
        p=prices(5);p["capital_gains"]=.25
        np.testing.assert_allclose(prepare_prices(p).distributions,.25)
    def test_split_rejected(self):
        p=prices();p.iloc[10,p.columns.get_loc("stock_splits")]=2
        with self.assertRaises(ValueError):validate_prices(p)
    def test_duplicate_rejected(self):
        p=prices();p.index=pd.DatetimeIndex([p.index[0]]*len(p))
        with self.assertRaises(ValueError):validate_prices(p)
    def test_bad_ohlc_rejected(self):
        p=prices();p.iloc[0,p.columns.get_loc("high")]=1
        with self.assertRaises(ValueError):validate_prices(p)
    def test_nonfinite_rejected(self):
        p=prices();p.iloc[0,0]=np.nan
        with self.assertRaises(ValueError):validate_prices(p)
    def test_incumbent_exact_algebra(self):
        raw=prices();r=raw.close.pct_change(fill_method=None)
        expected=pd.concat([r.rolling(w,min_periods=max(2,w//2)).std(ddof=0) for w in (2,5,22,66)],axis=1).mean(axis=1)**2
        np.testing.assert_allclose(prepare_prices(raw).incumbent_variance,expected.iloc[1:],equal_nan=True)
    def test_features_prefix_invariant(self):
        raw=prices();full=causal_features(prepare_prices(raw));part=causal_features(prepare_prices(raw.iloc[:120]))
        for k in full:np.testing.assert_allclose(full[k][:119],part[k],equal_nan=True)
    def test_options_lag_no_fill(self):
        p=prepare_prices(prices());o=pd.DataFrame({"iv30":.2,"net_gex_bn":2.,"root":"QQQ"},index=p.index)
        o.loc[o.index[100],"iv30"]=.9;o=o.drop(o.index[105])
        x=causal_features(p,o,"QQQ")["har_options"]
        self.assertAlmostEqual(x[101,-2],np.log(.9**2/252))
        self.assertTrue(np.isnan(x[106,-2]))
    def test_options_mismatch(self):
        p=prepare_prices(prices());o=pd.DataFrame({"iv30":.2,"net_gex_bn":2.,"root":"SPY"},index=p.index)
        with self.assertRaises(ValueError):causal_features(p,o,"QQQ")


class ForecastTests(unittest.TestCase):
    def test_qlike_exact_and_scale(self):
        y=np.array([.1,.3,.7]);f=np.array([.2,.2,.4])
        np.testing.assert_allclose(qlike(y,f),qlike(y*100,f*100))
        np.testing.assert_allclose(qlike(y,y),0)
    def test_qlike_bad_forecast(self):
        with self.assertRaises(ValueError):qlike(np.array([1.]),np.array([0.]))
    def test_fit_constant_target(self):
        rng=np.random.default_rng(7);x=rng.normal(size=(200,3));y=np.full(200,.005)
        fit=loglink_fit(x,y,.001);self.assertTrue(fit["success"])
        out,_=loglink_predict(fit,x[:5]);np.testing.assert_allclose(out,.005,rtol=1e-6)
    def test_direct_labels_mature_and_prefix(self):
        p=prepare_prices(prices(240));x=causal_features(p)["har"]
        cfg=Settings(minimum=64,window=96,refit=21,paths=16)
        f,logs=direct_har(x,p.variance.to_numpy(),20,cfg)
        g,_=direct_har(x[:160],p.variance.to_numpy()[:160],20,cfg)
        np.testing.assert_allclose(f[:160],g,equal_nan=True)
        self.assertTrue(logs);self.assertTrue(all(r["latest_label_endpoint"]<=r["origin"] for r in logs))
    def test_failed_fit_not_reused(self):
        p=prepare_prices(prices(130));x=causal_features(p)["har"]
        fail={"success":False,"objective":None,"iterations":0,"message":"fixture failure","coefficient_boundary":False}
        with patch("research.apmem_shadow.phase2.forecasts.loglink_fit",return_value=fail):
            f,logs=direct_har(x,p.variance.to_numpy(),1,Settings(minimum=64,window=96,paths=16))
        self.assertTrue(np.isnan(f).all());self.assertTrue(all(not r["success"] for r in logs))
    def test_apmem_prefix_invariant(self):
        p=prepare_prices(prices(105));cfg=Settings(minimum=64,window=96,apmem_refit=63,paths=16)
        f,logs=apmem_paths(p.variance.to_numpy(),p.return_log.to_numpy(),cfg)
        g,_=apmem_paths(p.variance.to_numpy()[:85],p.return_log.to_numpy()[:85],cfg)
        np.testing.assert_allclose(f[:85],g,equal_nan=True)
        self.assertTrue(logs[0]["success"])
    def test_blend_prefix_and_weight_bounds(self):
        n=160;v=np.linspace(.0001,.0003,n)
        pred={k:np.repeat((v*s)[:,None],3,axis=1) for k,s in (("ewma94",.8),("apmem",1.2),("har_extended",1.0))}
        eq,ada,w=combine(pred,v,minimum=10)
        a,b,_=combine({k:x[:100] for k,x in pred.items()},v[:100],minimum=10)
        np.testing.assert_allclose(a,eq[:100]);np.testing.assert_allclose(b,ada[:100])
        self.assertTrue((w>=1/6-1e-12).all());self.assertTrue((w<=2/3+1e-12).all())
        np.testing.assert_allclose(w.sum(axis=2),1)
    def test_unavailable_component_not_hidden(self):
        v=np.ones(30);p={k:np.ones((30,3)) for k in ("ewma94","apmem","har_extended")}
        p["apmem"][10]=np.nan
        a,b,_=combine(p,v);self.assertTrue(np.isnan(a[10]).all());self.assertTrue(np.isnan(b[10]).all())
    def test_bad_settings(self):
        for cfg in [Settings(minimum=1),Settings(window=1),Settings(ridge=np.nan),Settings(paths=0)]:
            with self.assertRaises(ValueError):cfg.validate()


class CalibrationTests(unittest.TestCase):
    def test_quantile_prefix_and_current_label_excluded(self):
        rng=np.random.default_rng(15);r=rng.normal(0,.02,150);f=np.full(150,.0004)
        a=return_quantiles(r,f,alpha=.05,window=60,minimum=30)
        changed=r.copy();changed[100:]=-1
        b=return_quantiles(changed,f,alpha=.05,window=60,minimum=30)
        np.testing.assert_allclose(a["filtered_historical"][:100],b["filtered_historical"][:100],equal_nan=True)
    def test_variance_envelope_prefix(self):
        v=np.linspace(.001,.003,150);f=np.full(150,.002)
        a=variance_upper(v,f,20,window=60,minimum=30)
        b=variance_upper(v[:100],f[:100],20,window=60,minimum=30)
        np.testing.assert_allclose(a[:100],b,equal_nan=True)
    def test_coverage_no_bridge(self):
        a=np.array([-2.,2.,np.nan,-2.,2.]);q=np.zeros(5)
        d=coverage_diagnostics(a,q,.5)
        self.assertEqual(d["transition_counts"],[0,0,2,0]);self.assertEqual(d["n"],4)
    def test_coverage_extremes_finite(self):
        d=coverage_diagnostics(np.ones(40),np.zeros(40),.05)
        self.assertTrue(np.isfinite(d["kupiec_lr"]));self.assertEqual(d["violations"],0)
    def test_wilson(self):
        lo,hi=wilson(5,100);self.assertLess(lo,.05);self.assertGreater(hi,.05)


class AccountingTests(unittest.TestCase):
    def test_next_open_shift(self):
        np.testing.assert_array_equal(delayed_weights([1,0,1,0],1),[0,1,0,1])
        with self.assertRaises(ValueError):delayed_weights([1,0],0)
    def test_flat_full_equity_cost(self):
        d=pd.bdate_range("2020-01-01",periods=3)
        r=portfolio([100,100,100],[0,0,0],d,[1,1,1],cost=.01)
        self.assertAlmostEqual(r["equity"][-1],.99/1.01)
    def test_buyhold_gross_scalar(self):
        d=pd.bdate_range("2020-01-01",periods=4)
        r=portfolio([100,105,99,110],[0,0,0,0],d,[1]*4,cost=0)
        self.assertAlmostEqual(r["equity"][-1],1.1)
    def test_dividend_to_previous_holder(self):
        dates=pd.bdate_range("2020-01-01",periods=3)
        a=portfolio([100,100,100],[0,10,0],dates,[1,1,1],cost=0)
        b=portfolio([100,100,100],[0,10,0],dates,[0,1,1],cost=0)
        self.assertAlmostEqual(a["equity"][-1],1.1);self.assertAlmostEqual(b["equity"][-1],1)
    def test_drift_rebalance_cost_detected(self):
        dates=pd.bdate_range("2020-01-01",periods=3)
        r=portfolio([100,200,100],[0,0,0],dates,[.5]*3,cost=.001)
        self.assertGreater(r["turnover"][1],.5)
    def test_cash_calendar_compounding(self):
        dates=pd.to_datetime(["2020-01-03","2020-01-06","2020-01-07"])
        r=portfolio([100]*3,[0]*3,dates,[0]*3,cost=0,cash_rate=.03)
        self.assertAlmostEqual(r["equity"][-1],1.03**(4/365.25))
    def test_scalar_holdings_verification(self):
        rng=np.random.default_rng(8);n=30;o=100*np.exp(np.cumsum(rng.normal(0,.02,n)))
        d=np.zeros(n);d[6]=1;w=rng.uniform(.1,.9,n);dates=pd.bdate_range("2020-01-01",periods=n)
        c=.002;cash=1.;shares=0.;equity=[1.]
        for i in range(n-1):
            total=cash+shares*o[i];desired=w[i];old=shares*o[i]
            fee=(c*(desired*total-old)/(1+c*desired) if desired*total>=old else c*(old-desired*total)/(1-c*desired))
            new_total=total-fee;shares=desired*new_total/o[i];cash=(1-desired)*new_total
            cash+=shares*d[i+1];equity.append(cash+shares*o[i+1])
        equity[-1]-=c*shares*o[-1]
        got=portfolio(o,d,dates,w,cost=c)
        np.testing.assert_allclose(got["equity"],equity,atol=1e-12)
    def test_bad_weight(self):
        with self.assertRaises(ValueError):portfolio([100]*3,[0]*3,pd.bdate_range("2020-01-01",periods=3),[2]*3)


class UncertaintyTests(unittest.TestCase):
    def test_constant_block_mean(self):
        d=block_mean_interval(np.full(71,2.),block=63,resamples=100)
        self.assertEqual(d["mean_difference"],2.);np.testing.assert_allclose(d["pointwise_95_interval"],[2,2])
    def test_holm_family(self):
        np.testing.assert_allclose(holm([.04,.01,.03]),[.06,.03,.06])
    def test_seed_reproducible(self):
        x=np.arange(91.)
        self.assertEqual(block_mean_interval(x,resamples=100),block_mean_interval(x,resamples=100))


class ConsumerTests(unittest.TestCase):
    def args(self):
        return dict(instrument="QQQ",origin_session="2026-11-12",forecast=[.001,.001,.001],upper90=[.002]*3,
            decision_at="2026-11-13T16:00:00+00:00",source_sha256="a"*64,observed_at="2026-11-13T12:00:00+00:00",
            fit_completed_at="2026-11-13T13:00:00+00:00",fit_last_session="2026-11-12")
    def test_valid_still_no_authority(self):
        r=research_context(**self.args());self.assertEqual(r["status"],"RESEARCH_ONLY")
        for k in ("may_rank","may_size","may_trade"):self.assertIs(r[k],False)
    def test_unknown_clock_abstains(self):
        a=self.args();a["observed_at"]=None;r=research_context(**a)
        self.assertEqual(r["status"],"ABSTAIN");self.assertIn("OBSERVED_CLOCK_UNKNOWN",r["reason_codes"])
    def test_future_fit_abstains(self):
        a=self.args();a["fit_completed_at"]="2026-11-14T00:00:00+00:00"
        self.assertIn("FUTURE_AVAILABILITY",research_context(**a)["reason_codes"])
    def test_stale_abstains(self):
        a=self.args();a["origin_session"]="2026-10-01"
        self.assertIn("STALE_ORIGIN",research_context(**a)["reason_codes"])
    def test_nonfinite_forecast_abstains(self):
        a=self.args();a["forecast"]=[np.nan]*3
        self.assertIn("FORECAST_UNAVAILABLE",research_context(**a)["reason_codes"])
    def test_fit_capture_order(self):
        a=self.args();a["fit_completed_at"]="2026-11-13T11:00:00+00:00"
        self.assertIn("FIT_PRECEDES_CAPTURE",research_context(**a)["reason_codes"])


if __name__ == "__main__":unittest.main()
