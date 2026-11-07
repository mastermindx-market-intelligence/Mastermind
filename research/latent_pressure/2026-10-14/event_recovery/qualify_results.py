"""Post-result dependence/carry-rule checks only; no feature selection or refits."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np,pandas as pd

def qualify(root:Path):
 report=json.loads((root/'report.json').read_text());p=root/'predictions.csv.gz'
 if hashlib.sha256(p.read_bytes()).hexdigest()!=report['private_predictions_sha256']:raise ValueError('changed predictions')
 q=pd.read_csv(p,dtype={'decision_ns':'uint64','sequence':'uint64','label_end_ns':'uint64'})
 y=q['class'].to_numpy(int);rule=np.where(q.median_momentum>0,2,np.where(q.median_momentum<0,0,1))
 out={'status':'POST_RESULT_DIAGNOSTICS_NO_REFIT_OR_GATE_CHANGE','single_day_only':True,'unchanged_predictions_sha256':report['private_predictions_sha256'],'primary_gain':float(q.brier_gain.mean()),'carry_direction_rule':{'definition':'UP/DOWN/SAME sign of observed latest5 median versusprevious5 median; hard classification only, not calibrated probabilities','timing':'specified as secondary in protocol, omitted from frozen primary script; computed after primary as explicit diagnostic','accuracy':float(np.mean(rule==y)),'class_recall':{str(k):float(np.mean(rule[y==k]==k)) if (y==k).any() else None for k in range(3)}},'block_sensitivity':{}}
 for mins in [15,30]:
  keys=(q.decision_ns.astype('int64')-pd.Timestamp('2026-10-05T13:00:00-04:00').value)//(mins*60*10**9);b=q.groupby(keys).brier_gain.agg(['sum','count']);rng=np.random.default_rng(20261015);vals=[]
  for _ in range(1000):
   z=b.iloc[rng.integers(len(b),size=len(b))];vals.append(float(z['sum'].sum()/z['count'].sum()))
  out['block_sensitivity'][str(mins)]={'number_of_blocks':len(b),'ci95':np.quantile(vals,[.025,.975]).tolist()}
 out['interpretation']='Dependence sensitivity is not independent-day evidence. Outcome overlap and one selectedday prohibit a population-significance claim. Carry classification cannot establish calibrated forecast or executableprofit.'
 return out
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',type=Path,required=True);a=p.parse_args();print(json.dumps(qualify(a.study),indent=2,allow_nan=False))
