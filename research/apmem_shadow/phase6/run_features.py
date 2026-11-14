from __future__ import annotations
import argparse,concurrent.futures,datetime,hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
import features as f
from native_replay import load_math

_ROOT=None
_CACHE={}

def init(root):
    global _ROOT
    _ROOT=Path(root)

def work(task):
    segment,symbol,members,group=task
    if segment not in _CACHE:
        price,total,vol,m=f.load_segment(_ROOT,segment)
        c,mask=load_math(_ROOT/'source',m)
        _CACHE[segment]=(price,total,vol,m,c,mask)
    price,total,vol,m,c,mask=_CACHE[segment]
    close=price[symbol].dropna()
    if len(close)<300:return {'segment':segment,'symbol':symbol,'status':'INSUFFICIENT_HISTORY'}
    own=f.own_features(close,c,mask)
    out=f.context_features(price,total,vol,symbol,members,own)
    out['group']=group;out['symbol']=symbol;out['segment']=segment
    out['research_anchor']='observed_snapshot_start_not_certified_listing_anchor'
    out['history_reset']=segment=='post'
    out['eligible']=(out.rv126.notna()&(out.w2_bars>=40)&(out.month_bars>=24)&price[symbol].notna())
    dest=_ROOT/'features'/segment/f'{symbol}.parquet';dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():raise FileExistsError(dest)
    out.to_parquet(dest)
    return {'segment':segment,'symbol':symbol,'group':group,'status':'COMPLETE','rows':len(out),
      'dot_events':int(out['dot'].fillna(False).sum()),'macd_cross_events':int(out.rsi_macd_3d_cross.fillna(False).sum()),
      'eligible_dates':int(out.eligible.sum()),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()}

def main(root):
    root=Path(root);manifest=json.loads((root/'INPUT_MANIFEST.json').read_text())
    if (root/'features/receipt.json').exists():raise FileExistsError('Existing immutable result')
    tasks=[]
    for segment in ('pre','post'):
        for group,members in manifest['groups'].items():
            for symbol in members:tasks.append((segment,symbol,members,group))
        for symbol in ['RSP','DIA','QQQ']:
            tasks.append((segment,symbol,['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY'],'sector_ETF_proxy'))
    receipts=[]
    with concurrent.futures.ProcessPoolExecutor(max_workers=5,initializer=init,initargs=(str(root),)) as pool:
        for row in pool.map(work,tasks):
            receipts.append(row);print('FEATURED',row['segment'],row['symbol'],row['status'],row.get('dot_events'),row.get('macd_cross_events'),flush=True)
    result={'status':'COMPLETE','created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'results':receipts,
            'model_outcomes_read':False,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (root/'features/receipt.json').write_text(json.dumps(result,indent=2))
    print('FEATURE_PANEL_COMPLETE',len(receipts),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',default=str(Path(__file__).parent));main(parser.parse_args().root)
