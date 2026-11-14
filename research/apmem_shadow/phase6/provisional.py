"""Prefix-only slow-bar nowcasts with explicit provisional and maturity clocks."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
import features as f
from native_replay import load_math
from evaluate import account,write_json


def scheduled_end(at,unit,parity=0):
    at=pd.Timestamp(at).normalize()
    if unit=='1M':return at.to_period('M').end_time.normalize()
    if unit!='2W' or parity not in (0,1):raise ValueError('Unknown slow bar')
    friday=at+pd.Timedelta(days=(4-at.weekday())%7)
    week=(friday-f.ANCHOR).days//7;group=(week+parity)//2
    return f.ANCHOR+pd.Timedelta(days=(2*group+1-parity)*7)


def nowcast(close,c,at,unit='2W',parity=0):
    at=pd.Timestamp(at);prefix=close.loc[:at].dropna();f.validate_index(prefix.index)
    if prefix.empty or prefix.index[-1]!=at:raise ValueError('No actual observation at issue clock')
    end=scheduled_end(at,unit,parity);bars=f.period_bars(prefix,unit,parity)
    provisional=end>at
    values=bars.close.copy()
    if provisional:values.loc[end]=prefix.iloc[-1]
    macd,signal=c.rsi_macd(values);hist=macd-signal
    result={'observed_at':at,'scheduled_period_end':end,'provisional':provisional,
            'macd':np.nan,'hist':np.nan,'hist_delta':np.nan,'prior_completed_hist':np.nan}
    if len(hist)>=2 and pd.notna(hist.iloc[-1]) and pd.notna(hist.iloc[-2]):
        result.update(macd=float(macd.iloc[-1]),hist=float(hist.iloc[-1]),hist_delta=float(hist.iloc[-1]-hist.iloc[-2]),prior_completed_hist=float(hist.iloc[-2]))
    return result


def settle_label(close,c,record,unit='2W',parity=0):
    end=pd.Timestamp(record['scheduled_period_end'])
    labels={'settlement_status':'NOT_MATURED','settled_hist_delta':np.nan,'positive_slope_survived':None}
    where=close.index.searchsorted(end)
    if where>=len(close):return labels
    known=close.index[where]
    bars=f.period_bars(close.loc[:known].dropna(),unit,parity)
    if end not in bars.index:return dict(labels,settlement_status='MISSING_BAR')
    macd,signal=c.rsi_macd(bars.close);hist=macd-signal;pos=hist.index.get_loc(end)
    if pos<1 or pd.isna(hist.iloc[pos]) or pd.isna(hist.iloc[pos-1]):return dict(labels,settlement_status='INSUFFICIENT_HISTORY')
    delta=float(hist.iloc[pos]-hist.iloc[pos-1])
    return {'settlement_status':'COMPLETE','settled_hist_delta':delta,'positive_slope_survived':bool(delta>0),
            'settlement_known_at':known,'settled_hist':float(hist.iloc[pos])}


def main(root):
    root=Path(root);dest=root/'provisional_results';dest.mkdir(exist_ok=False)
    manifest=json.loads((root/'INPUT_MANIFEST.json').read_text());c,_=load_math(root/'source',manifest)
    groups={s:(g,peers) for g,peers in manifest['groups'].items() for s in peers};rows=[];accounts=[]
    for segment in ['pre','post']:
        p,t,_,_=f.load_segment(root,segment)
        for symbol,(group,peers) in groups.items():
            x=pd.read_parquet(root/'enriched'/segment/f'{symbol}.parquet');close=p[symbol].dropna()
            observed=x.eligible.fillna(False)&(x['dot'].fillna(False)|x.rsi_macd_3d_cross.fillna(False))
            index=(x.index>='2001-01-01')&(x.index<='2019-12-31') if segment=='pre' else (x.index>='2025-06-01')&(x.index<='2026-11-06')
            positive=pd.Series(False,index=x.index)
            for at in x.index[observed&index]:
                for unit in ['2W','1M']:
                    record=nowcast(close,c,at,unit);future=settle_label(close,c,record,unit)
                    exposed=bool(symbol=='MCD' and segment=='post')
                    rows.append({'symbol':symbol,'group':group,'segment':segment,'unit':unit,
                       'dot':bool(x.loc[at,'dot']),'cross':bool(x.loc[at,'rsi_macd_3d_cross']),
                       'peer_repair':bool(x.loc[at,'peer_repair']),'exposed_design_case':exposed,**record,**future})
                    if unit=='2W':positive.loc[at]=bool(record['hist_delta']>0)
            if symbol=='MCD' and segment=='post':continue
            for family in ['dot','rsi_macd_3d_cross']:
                raw=x[family].fillna(False).astype(bool)
                policies={'raw':raw,'closed_slow_peer':raw&x.slow_improving.fillna(False)&x.peer_repair.fillna(False),
                    'provisional_slow_peer':raw&positive&x.peer_repair.fillna(False),
                    'provisional_slow_only':raw&positive}
                for policy,signal in policies.items():
                    for h in [21,63]:
                        a=account(t[symbol].loc[index],signal.loc[index],x.eligible.fillna(False).loc[index],h,.0005)
                        if a is None:continue
                        name=f'{segment}__{symbol}__{family}__{policy}__{h}'
                        a['curve'].to_parquet(dest/(name+'.parquet'))
                        accounts.append({'segment':segment,'symbol':symbol,'group':group,'family':family,'policy':policy,'horizon':h,'cost_bp':5.,'curve':name+'.parquet',**a['metrics']})
            print('PROVISIONAL_TESTED',segment,symbol,flush=True)
    pd.DataFrame(rows).to_parquet(dest/'observations.parquet',index=False)
    pd.DataFrame(accounts).to_csv(dest/'accounts.csv',index=False)
    q=pd.DataFrame(rows);q=q.loc[~q.exposed_design_case&(q.settlement_status=='COMPLETE')&q.provisional&(q.hist_delta>0)]
    q.groupby(['segment','group','unit']).agg(events=('symbol','size'),dates=('observed_at','nunique'),positive_slope_survival=('positive_slope_survived','mean')).reset_index().to_csv(dest/'settlement_survival.csv',index=False)
    pd.DataFrame(rows).loc[pd.DataFrame(rows).exposed_design_case].to_csv(dest/'MCD_EXPOSED_NOWCASTS.csv',index=False)
    write_json(dest/'receipt.json',{'status':'COMPLETE','observations':len(rows),'accounts':len(accounts),'case_guided_exploratory':True,
          'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'provisional_never_labeled_confirmed':True,'may_trade':False})
    print('PROVISIONAL_STUDY_COMPLETE',len(rows),len(accounts),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',default=str(Path(__file__).parent));main(ap.parse_args().root)
