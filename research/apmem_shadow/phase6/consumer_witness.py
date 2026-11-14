"""Exercise pinned native entry assessor and attach non-authoritative research facts."""
from __future__ import annotations
import argparse,copy,hashlib,json,sys
from pathlib import Path
import numpy as np
import pandas as pd
import features as f
from consumer import make_context,attach,FACTS
from evaluate import write_json


def prepare(donor):
    owner=donor/'source/entry_consumer';manifest=json.loads((donor/'ENTRY_CONSUMER_MANIFEST.json').read_text())
    for forbidden in ['.env','.env.local']:
        if (owner/forbidden).exists():raise ValueError('Unexpected credential-bearing source tree')
    for rel,item in manifest['files'].items():
        if hashlib.sha256((owner/rel).read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Native consumer source changed')
    sys.path.insert(0,str(donor/'source'));sys.path.insert(0,str(donor/'source/macro_native'));sys.path.insert(0,str(owner))
    from native_adapter.native import verify_source
    verify_source(donor/'source/macro_native',json.loads((donor/'MACRO_NATIVE_MANIFEST.json').read_text()))
    return manifest


def main(root,donor,revision):
    root=Path(root);donor=Path(donor);dest=root/'CONSUMER_WITNESS.json'
    if dest.exists():raise FileExistsError('Original consumer witness must be reconciled')
    manifest=prepare(donor)
    from engine.signal_gate import gate
    from portfolio.entry_engine import assess
    price,total,vol,inputs=f.load_segment(root,'post')
    digest=hashlib.sha256((root/'INPUT_MANIFEST.json').read_bytes()).hexdigest();records=[]
    cases=[('MCD','2026-06-11'),('MCD','2026-10-12'),('MCD','2026-10-20'),('MCD','2026-11-06'),('RSP','2026-11-06'),('QQQ','2026-11-06'),('DIA','2026-11-06')]
    for symbol,date in cases:
        path=root/'features/post'/f'{symbol}.parquet';x=pd.read_parquet(path);at=pd.Timestamp(date);row=x.loc[at]
        facts={k:float(row[k]) if k in row and pd.notna(row[k]) and np.isfinite(float(row[k])) else None for k in FACTS}
        basis='sector_ETF_proxy' if symbol in ('RSP','QQQ','DIA') else 'fixed_economic_diagnostic'
        context=make_context(symbol,date,f.interpretation(row),facts,source_hash=digest,research_revision=revision,peer_basis=basis,history_reset=True)
        prefix=price[symbol].loc[:at].dropna()
        native=gate(symbol,prefix,washout_waiver=False)
        incumbent=assess(symbol,series=prefix,signal_gate_row=native,as_of=date,_use_defaults=False)
        before=copy.deepcopy(incumbent)
        joined=attach(incumbent,context,instrument=symbol,expected_session=date,expected_source_hash=digest)
        stale=attach(incumbent,context,instrument=symbol,expected_session='2026-11-13',expected_source_hash=digest)
        identical={k:v for k,v in joined.items() if k!='nested_cycle_research'}==before and incumbent==before
        if not identical:raise AssertionError('Research modified existing decision')
        records.append({'instrument':symbol,'as_of':date,'research_state':context['state'],
            'incumbent_verdict':incumbent.get('verdict'),'incumbent_buyable':incumbent.get('buyable'),
            'incumbent_score':incumbent.get('entry_score'),'incumbent_exactly_preserved':identical,
            'historical_requested_session_status':joined['nested_cycle_research']['freshness'],
            'current_requested_session_status':stale['nested_cycle_research']['freshness'],
            'facts':facts,'authority':context['authority']})
    result={'status':'COMPLETE','native_assessor_pin':manifest['pin'],'research_revision':revision,
          'actual_pinned_assessor_exercised':True,'actual_production_service_called':False,'observed_historical_live_signals_claimed':False,
          'results':records,'all_incumbents_preserved':True,'source_vintage_limit':'November 6/9 capture is stale versus November 13 expected session',
          'history_reset_after_reserved_window':True,'no_current_trade_recommendation':True}
    write_json(dest,result);print('ACTUAL_PINNED_CONSUMER_EXERCISED',len(records),'unchanged',flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',default=str(Path(__file__).parent));ap.add_argument('--donor',required=True);ap.add_argument('--revision',required=True);a=ap.parse_args();main(a.root,a.donor,a.revision)
