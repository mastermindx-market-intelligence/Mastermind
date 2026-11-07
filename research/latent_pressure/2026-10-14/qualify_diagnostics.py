"""Post-run diagnostic boundary qualification; no feature/model changes or refits."""
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd
O=Path(__file__).parent
q=pd.read_csv(O/'results/predictions.csv.gz',parse_dates=['date','label_end'])
r=json.loads((O/'results/results.json').read_text())
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--data',type=Path,required=True,help='Authorized original hash-matched Yahoo root')
D=parser.parse_args().data
ts='SPY XLB XLC XLE XLF XLI XLK XLP XLRE XLU XLV XLY SMH SOXX'.split()
c={}
for t in ts:
 x=pd.read_parquet(D/f'{t}.parquet');x=x.set_index('Date') if 'Date' in x else x;c[t]=x['close'].loc['2010-01-01':]
c=pd.DataFrame(c).reindex(c['SPY'].index);rs=np.log(c.div(c.SPY,axis=0)).diff(20)
a={'classification':'POST_RUN_DIAGNOSTIC_QUALIFICATION_NOT_NEW_MODEL_SELECTION','no_refits':True,'original_results_unchanged':True,'periods':{}}
for p,lo,hi in [('development','2018-01-01','2022-12-31'),('holdout','2023-01-01','2025-12-31')]:
 g0=q[(q.date>=lo)&(q.date<=hi)];end=int(np.flatnonzero(c.index<=pd.Timestamp(hi))[-1]);dd={}
 for m in ['baseline','combined']:
  ev=[]
  for t,g in g0.groupby('ticker'):
   arr=rs[t].to_numpy();last=-1000
   for row in g.sort_values('date').itertuples():
    i=int(row.position);pp=getattr(row,'p_'+m);s=1 if pp>=.6 else (-1 if pp<=.4 else 0)
    if i+24>end or not s or arr[i]*s>=0 or i-last<20:continue
    last=i;matches=[k for k in range(i+1,i+21) if arr[k-1]*s<0 and np.all(arr[k:k+5]*s>=0)]
    ev.append(matches[0]-i if matches else None)
  hit=[x for x in ev if x is not None]
  dd[m]={'alerts_with_full_24session_outcome_window':len(ev),'matches':len(hit),'false_alarms':len(ev)-len(hit),'precision':len(hit)/len(ev) if ev else None,'median_lead_among_matches':float(np.median(hit)) if hit else None}
 dd['base_rate']=float(g0.y.mean());dd['rows']=len(g0);dd['eligible_dates']=g0.date.nunique()
 a['periods'][p]=dd
print(json.dumps(a,indent=2));(O/'DIAGNOSTIC_QUALIFICATION.json').write_text(json.dumps(a,indent=2)+'\n')
