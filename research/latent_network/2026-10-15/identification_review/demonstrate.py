"""Constructed estimator counterexample, NOT market performance.

The covariance/target coefficients were selected to illustrate an existence claim
from a small deterministic grid inspected in this review. No p-value or empirical
market acceptance is assigned. The full network-study outcome was not accessed.
"""
from pathlib import Path
import hashlib
import json
import platform
import numpy as np
import scipy
from scipy.stats import rankdata
from ridge_identification import published_ridge_formula, fit_controlled, rank_target

BASE_NAMES = ([f'mom{k}' for k in (5,21,63,126,252)] + [f'rs{k}' for k in (5,21,63,126,252)] +
        ['accel21','relvol63','vol21','vol63','drawdown63','drawup63','trend63','trend252',
         'rank21','market21','marketvol63','SMB21','HML21','other5','other21','other63',
         'dispersion21','ownres5','ownres21','ownres63','otherres5','otherres21','otherres63','resvol63'])
NET_NAMES = ['peer5','peer21','peer63','peer_positive21','peer_gap21','peer_disp21','edge_strength','edge_coverage']


def mean_ic(target, prediction):
    values=[]
    for y,p in zip(target.reshape(-1,49),prediction.reshape(-1,49)):
        values.append(np.corrcoef(rankdata(y),rankdata(p))[0,1])
    return float(np.mean(values))


def experiment():
    rng=np.random.default_rng(90151026)
    ntrain,ntest=49*82,49*104
    a=rng.normal(size=(ntrain,2));b=rng.normal(size=(ntest,2));rho=.99
    x=np.c_[a[:,0],rho*a[:,0]+np.sqrt(1-rho*rho)*a[:,1]]
    t=np.c_[b[:,0],rho*b[:,0]+np.sqrt(1-rho*rho)*b[:,1]]
    synthetic_future=x[:,0]-.8*x[:,1]
    synthetic_future_test=t[:,0]-.8*t[:,1]
    y=np.concatenate([rank_target(v) for v in synthetic_future.reshape(-1,49)])
    yt=np.concatenate([rank_target(v) for v in synthetic_future_test.reshape(-1,49)])
    xb=np.zeros((ntrain,len(BASE_NAMES)));tb=np.zeros((ntest,len(BASE_NAMES)))
    xb[:,BASE_NAMES.index('ownres21')]=x[:,0];tb[:,BASE_NAMES.index('ownres21')]=t[:,0]
    xb[:,BASE_NAMES.index('mom5')]=x[:,1];tb[:,BASE_NAMES.index('mom5')]=t[:,1]
    xn=np.zeros((ntrain,len(NET_NAMES)));tn=np.zeros((ntest,len(NET_NAMES)))
    # A ZERO graph gives no peer information, but the original gap still equals -own.
    xn[:,NET_NAMES.index('peer_gap21')]=-x[:,0]
    tn[:,NET_NAMES.index('peer_gap21')]=-t[:,0]
    pred0=published_ridge_formula(xb,y,tb)
    pred1=published_ridge_formula(np.c_[xb,xn],y,np.c_[tb,tn])
    control=fit_controlled(xb,xn,y)
    pred2=control.predict(tb,tn)
    def metrics(p):return {'mean_rank_ic':mean_ic(yt,p),'rank_mse':float(np.mean((p-yt)**2))}
    metrics_by_name={k:metrics(p) for k,p in [('baseline',pred0),('redundant_zero_graph',pred1),('orthogonal_control',pred2)]}
    r=metrics_by_name
    example=np.array([-.02,-.01,0,.01,.02])
    return {
      'scope':'CONSTRUCTED_ESTIMATOR_IDENTIFICATION_TEST_NOT_MARKET_BACKTEST',
      'source_under_review':'Mastermind@566e0db2f3ef3913c8645ce93d2d8ed62f2b3f71/research/latent_network/2026-10-15/network_study.py',
      'original_market_result_accessed':False,'original_market_model_refitted':False,
      'construction':{'seed':90151026,'training_rows':ntrain,'test_rows':ntest,'subjects_per_date':49,'correlation':rho,
                      'target':'Date-centered midrank of x-0.8z','graph_weights':'ALL_ZERO',
                      'new_information_in_candidate':False,'selection':'Existence example selected from a deterministic covariance/coefficient grid; no significance assertion'},
      'metrics':r,
      'apparent_gains':{'rank_ic':r['redundant_zero_graph']['mean_rank_ic']-r['baseline']['mean_rank_ic'],
                        'rank_mse':r['baseline']['rank_mse']-r['redundant_zero_graph']['rank_mse']},
      'full_original_acceptance_gate_tested':False,
      'control':{'max_prediction_difference_from_baseline':float(np.max(np.abs(pred2-pred0))),**control.diagnostics},
      'rank_sign_counterexample':{'common_shift':.05,'targets_identical':bool(np.array_equal(rank_target(example),rank_target(example+.05))),
                                  'positive_returns_before':int((example>0).sum()),'positive_returns_after':int((example+.05>0).sum()),
                                  'note':'Identical ranking target does not specify benchmark-relative direction or a pivot probability'},
      'versions':{'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__},
    }


if __name__=='__main__':
    root=Path(__file__).parent
    result=experiment()
    result['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob('*.py'))}
    (root/'EVIDENCE.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result,indent=2,allow_nan=False))
