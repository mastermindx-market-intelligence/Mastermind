"""Lagged monthly behavioral peers; never select peers from subsequent payoffs."""
from __future__ import annotations
import argparse,datetime,hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
import features as f
from native_replay import load_math
from evaluate import write_json


def residual_panel(total,names):
    f.validate_index(total.index)
    r=total[names].pct_change(fill_method=None);market=total.SPY.pct_change(fill_method=None)
    variance=market.rolling(126,min_periods=63).var()
    beta=pd.DataFrame({s:r[s].rolling(126,min_periods=63).cov(market)/variance for s in names}).shift(1)
    return r.sub(beta.mul(market,axis=0))


def select_peers(residual,symbol,at,lookback=252,minimum=126,maximum=3):
    if not 1<=at<=len(residual) or minimum<2:raise ValueError('Invalid selection clock')
    hist=residual.iloc[max(0,at-lookback):at]
    scored=[]
    for other in residual.columns:
        if other==symbol:continue
        pair=hist[[symbol,other]].dropna()
        if len(pair)<minimum:continue
        corr=pair.corr().iloc[0,1]
        if np.isfinite(corr) and corr>.10:scored.append((other,float(corr),len(pair)))
    scored.sort(key=lambda v:(-v[1],v[0]))
    return scored[:maximum]


def monthly_peer_plan(residual):
    month=residual.index.to_period('M')
    starts=np.flatnonzero(np.r_[True,np.asarray(month[1:]!=month[:-1])])
    plan=[]
    for k,i in enumerate(starts):
        if i==0:continue
        end=int(starts[k+1]) if k+1<len(starts) else len(residual)
        for symbol in residual.columns:
            selected=select_peers(residual,symbol,int(i))
            plan.append({'symbol':symbol,'start_pos':int(i),'end_pos':end,
                         'starts':str(residual.index[i].date()),'selected_at':str(residual.index[i-1].date()),
                         'peers':[x[0] for x in selected],'correlations':[x[1] for x in selected],
                         'common_counts':[x[2] for x in selected]})
    return plan


def build_context(price,total,symbol,plan):
    cols=['peer_return_1','peer_return_5','peer_return_21','peer_above20','peer_breadth_change',
          'peer_low_pressure_change','peer_coverage','peer_count','peer_valid','peer_repair','peer_pressure_easing']
    out=pd.DataFrame(np.nan,index=price.index,columns=['beh_'+c for c in cols])
    out['beh_peer_valid']=False;out['beh_peer_repair']=False;out['beh_peer_pressure_easing']=False
    out['beh_selected_at']=None;out['beh_peer_ids']=None;out['beh_selection_corr']=np.nan
    for row in plan:
        if row['symbol']!=symbol:continue
        start,end=row['start_pos'],row['end_pos'];peers=row['peers']
        if len(peers)<2:continue
        low=max(0,start-126);p=price.iloc[low:end];t=total.iloc[low:end]
        context=f.peer_context(p,t,symbol,[symbol]+peers).loc[price.index[start:end]]
        for col in cols:
            dtype=bool if col in ('peer_valid','peer_repair','peer_pressure_easing') else float
            out.loc[context.index,'beh_'+col]=context[col].to_numpy(dtype=dtype)
        out.loc[context.index,'beh_selected_at']=row['selected_at']
        out.loc[context.index,'beh_peer_ids']='|'.join(peers)
        out.loc[context.index,'beh_selection_corr']=np.mean(row['correlations'])
    out['beh_relative_resilience21']=(total[symbol]/total[symbol].shift(21)-1)-out.beh_peer_return_21
    return out


def main(root):
    root=Path(root);dest=root/'enriched';dest.mkdir(exist_ok=False)
    manifest=json.loads((root/'INPUT_MANIFEST.json').read_text());names=sum(manifest['groups'].values(),[])
    c,_=load_math(root/'source',manifest);receipts=[]
    for segment in ['pre','post']:
        price,total,_,_=f.load_segment(root,segment);res=residual_panel(total,names);plan=monthly_peer_plan(res)
        write_json(dest/f'{segment}_peer_plan.json',plan)
        for symbol in names:
            source=root/'features'/segment/f'{symbol}.parquet'
            x=pd.read_parquet(source);context=build_context(price,total,symbol,plan)
            out=x.join(context)
            alternative=f.slow_features(price[symbol].dropna(),c,'2W',parity=1)
            keep=['w2_hist','w2_hist_delta','w2_macd','w2_depth_rank']
            out=out.join(alternative[keep].add_prefix('alternate_'))
            path=dest/segment/f'{symbol}.parquet';path.parent.mkdir(exist_ok=True);out.to_parquet(path)
            receipts.append({'symbol':symbol,'segment':segment,'peer_context_days':int(context.beh_peer_valid.sum()),
                              'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        print('BEHAVIORAL_CONTEXT_COMPLETE',segment,len(plan),flush=True)
    write_json(dest/'receipt.json',{'status':'COMPLETE','results':receipts,'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                 'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',default=str(Path(__file__).parent));main(ap.parse_args().root)
