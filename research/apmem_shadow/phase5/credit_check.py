"""Non-trading credit-stress and earlier-era falsifiers; no threshold search."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import experiment as ex
from robustness import recovered_dot,extended_context


def credit_features(series,calendar,lag):
    if lag not in (1,2,5):raise ValueError('Unregistered publication-lag assumption')
    ex.check_index(calendar)
    x=series.reindex(calendar).shift(lag)
    m10=x.rolling(10,min_periods=10).mean();m30=x.rolling(30,min_periods=30).mean()
    valid=m10.notna()&m30.notna()&m10.shift(5).notna()
    return pd.DataFrame({'valid':valid,'not_rising':valid&~(m10.gt(m30)&m10.gt(m10.shift(5))),
                         'easing':valid&m10.lt(m10.shift(5))},index=calendar)


def main(root):
    out=root/'credit_results'
    if out.exists():raise ValueError('Original credit output exists')
    out.mkdir();(out/'private').mkdir()
    manifest=json.loads((root/'INPUT_MANIFEST.json').read_text());credit=json.loads((root/'CREDIT_MANIFEST.json').read_text())
    bound={x['segment']:x for x in credit['snapshots']};result=[];coverage=[]
    for segment in ('pre','post'):
        p,t,v=ex.load_segment(root,segment,manifest);ctx=ex.context(p,t,v);xt=extended_context(p,t,ctx)
        cp=root/'private'/('CREDIT_'+segment+'.parquet')
        if hashlib.sha256(cp.read_bytes()).hexdigest()!=bound[segment]['snapshot_sha256']:raise ValueError('Credit source drift')
        cr=pd.read_parquet(cp).hy_oas
        evals={'2007_2019' if segment=='pre' else 'post_reset':ex.eval_mask(p.index,segment)}
        if segment=='pre':evals['2001_2006']=np.asarray((p.index>='2001-01-01')&(p.index<='2006-12-31'))
        for phase in (0,1,2):
            dot=recovered_dot(root,p.index,segment,phase);pol=ex.policies(dot,ctx)
            repair=pd.DataFrame(np.repeat(ctx['repair'].to_numpy()[:,None],9,axis=1),index=p.index,columns=ex.SECTORS)
            lower=pd.DataFrame(np.repeat(xt['lower_pressure'].to_numpy()[:,None],9,axis=1),index=p.index,columns=ex.SECTORS)
            base={'dot_repair':dot&repair,'declining_low_pressure':dot&repair&lower}
            for era,valid in evals.items():
                if era=='2001_2006':
                    controls={'dot':pol['dot'],'dot_repair':pol['dot_repair'],'declining_low_pressure':ex.onset(base['declining_low_pressure']),
                              'ongoing_repair':pol['dot_repair'],'continuation':pol['continuation']}
                    for h in (21,63):
                        for name,sig in controls.items():
                            a=ex.account(t,sig,valid,h,.0005,exit_condition=xt['ongoing_exit'] if name=='ongoing_repair' else None)
                            a['curve'].to_csv(out/'private'/f'{era}_p{phase}_h{h}_{name}.csv')
                            result.append({'era':era,'phase':phase,'horizon':h,'lag':0,'cost_bp':5.,'policy':name,**a['metrics']})
                lags=(1,2,5) if phase==0 and era!='2001_2006' else (2,)
                for lag in lags:
                    cf=credit_features(cr,p.index,lag)
                    coverage.append({'era':era,'phase':phase,'lag':lag,'evaluation_sessions':int(valid.sum()),
                      'valid_credit_sessions':int((cf.valid&valid).sum()),'historical_availability_proven':False})
                    for name,raw in base.items():
                        for condition in ('valid','not_rising','easing'):
                            gate=pd.DataFrame(np.repeat(cf[condition].to_numpy()[:,None],9,axis=1),index=p.index,columns=ex.SECTORS)
                            sig=ex.onset(raw&gate)
                            for h in (21,63):
                                costs=(.0005,.002) if phase==0 and era!='2001_2006' else (.0005,)
                                for cost in costs:
                                    a=ex.account(t,sig,valid,h,cost)
                                    policy=name+'_credit_'+condition
                                    a['curve'].to_csv(out/'private'/f'{era}_p{phase}_h{h}_l{lag}_c{int(cost*10000)}_{policy}.csv')
                                    result.append({'era':era,'phase':phase,'horizon':h,'lag':lag,'cost_bp':cost*10000,'policy':policy,**a['metrics']})
            print('CREDIT_FALSIFIER_PHASE',segment,phase,flush=True)
    pd.DataFrame(result).to_csv(out/'portfolio_metrics.csv',index=False);pd.DataFrame(coverage).to_csv(out/'coverage.csv',index=False)
    ex.write_json(out/'RUN_RECEIPT.json',{'status':'COMPLETE','accounts':len(result),'outcome_guided_exploratory':True,
        'source_sha256':hashlib.sha256((root/'credit_check.py').read_bytes()).hexdigest(),
        'primary_credit_delay_sessions':2,'historical_availability_proven':False,'may_trade':False})
    print('CREDIT_FALSIFIER_COMPLETE',len(result),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();main(a.root)
