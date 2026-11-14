"""Exercise the actual pinned entry assessor plus the read-only research adapter."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import experiment as ex
from consumer import readings,attach
from native_comparison import prepare_native


def main(root):
    target=root/'CONSUMER_WITNESS.json'
    if target.exists():raise ValueError('Original witness exists')
    owner=root/'source/entry_consumer';manifest=json.loads((root/'ENTRY_CONSUMER_MANIFEST.json').read_text())
    if (owner/'.env').exists() or (owner/'.env.local').exists():raise ValueError('Isolated source must not contain credentials')
    for rel,item in manifest['files'].items():
        if hashlib.sha256((owner/rel).read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Entry owner source drift')
    prepare_native(root);sys.path.insert(0,str(owner))
    from portfolio.entry_engine import assess
    from engine.signal_gate import gate
    inputs=json.loads((root/'INPUT_MANIFEST.json').read_text());p,t,v=ex.load_segment(root,'post',inputs)
    digest=hashlib.sha256((root/'INPUT_MANIFEST.json').read_bytes()).hexdigest();obs=readings(p,t,v,digest)
    results=[]
    for row in obs:
        ticker=row['instrument'];native=gate(ticker,p[ticker],washout_waiver=False)
        incumbent=assess(ticker,series=p[ticker],signal_gate_row=native,as_of=row['origin_session'],_use_defaults=False)
        before=copy.deepcopy(incumbent)
        joined=attach(incumbent,row,instrument=ticker,expected_session='2026-11-13',expected_source_hash=digest)
        unchanged={k:v for k,v in joined.items() if k!='independent_recovery_research'}==before and incumbent==before
        if not unchanged:raise AssertionError('Incumbent entry decision altered')
        results.append({'ticker':ticker,'source_origin':row['origin_session'],'expected_completed_session':'2026-11-13',
          'incumbent_verdict':incumbent.get('verdict'),'incumbent_buyable':incumbent.get('buyable'),
          'incumbent_score':incumbent.get('entry_score'),'incumbent_exactly_preserved':unchanged,
          'research_status':joined['independent_recovery_research']['status'],
          'research_state':joined['independent_recovery_research']['descriptive_state'],
          'missing_vvix_state':row['facts']['vvix_rising'] is None,'authority':row['authority']})
    ex.write_json(target,{'actual_source_assessor_exercised':True,'production_service_called':False,
        'entry_owner_pin':manifest['pin'],'source_manifest_sha256':digest,'results':results,
        'all_incumbent_decisions_preserved':True,'latest_source_stale_not_current':True,
        'missing_inputs':['point-in-time constituent breadth','fundamental/catalyst context','live holdings','fresh November13 market data'],
        'no_current_entry_recommendation':True,'may_trade':False})
    print('ACTUAL_SOURCE_CONSUMER_WITNESS',len(results),'preserved','stale_source_disclosed',flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();main(a.root)
