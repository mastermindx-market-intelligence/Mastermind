"""One source-qualified research observation, no trading or periodic service.

Reuses native oscillators, existing volatility research, the incumbent data owner
and the incumbent entry assessor's read-only attachment. New context is not a
new signal; a prior turn is not backdated into a present entry opportunity.
"""
from __future__ import annotations
import argparse,concurrent.futures,datetime,gzip,hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
import features as f
from behavior import residual_panel,select_peers,build_context
from consumer import make_context,attach,FACTS
from consumer_witness import prepare as prepare_consumer
from dynamics import relative_dynamics,cross_cycle
from evaluate import write_json,clean_json
from forward_adapter import adapt_capture,compare_overlap,ORIGIN
from forward_capture import load_owner
from native_replay import load_math
from provisional import nowcast
from risk_observation import FixedRiskOwner,validate_risk_record
from support_state import slow_state,cohort_state

ROOT=None;CACHE=None


def initialize(root):
    global ROOT,CACHE
    ROOT=Path(root)
    manifest=json.loads((ROOT/'INPUT_MANIFEST.json').read_text())
    qualified=json.loads((ROOT/'forward_private/qualification.json').read_text())
    data={s:pd.read_parquet(ROOT/'forward_private'/f'{s}.parquet') for s in qualified['qualified']}
    index=data['SPY'].index
    price=pd.DataFrame({s:d.close for s,d in data.items()}).reindex(index)
    total=pd.DataFrame({s:d.total_return_close for s,d in data.items()}).reindex(index)
    names=sum(manifest['groups'].values(),[])
    for s in names:
        if s not in price:price[s]=np.nan;total[s]=np.nan
    _,_,old_vol,_=f.load_segment(ROOT,'post');vol=old_vol.reindex(index)
    residual=residual_panel(total,names)
    month=index.to_period('M');start=int(np.flatnonzero(month==month[-1])[0])
    c,mask=load_math(ROOT/'source',manifest)
    risk=FixedRiskOwner(ROOT/'source/phase2_runtime')
    CACHE=(manifest,data,price,total,vol,residual,start,c,mask,risk)


def last_event(frame,key):
    locations=np.flatnonzero(frame[key].fillna(False).to_numpy(bool))
    if not len(locations):return {'known_session':None,'age_sessions':None,'new_on_origin':False}
    i=int(locations[-1]);return {'known_session':str(frame.index[i].date()),'age_sessions':len(frame)-1-i,'new_on_origin':i==len(frame)-1}


def observe_symbol(symbol):
    manifest,data,price,total,vol,residual,start,c,mask,risk=CACHE
    close=price[symbol].dropna()
    if str(close.index[-1].date())!=ORIGIN:raise ValueError('Stale qualified instrument')
    own=f.own_features(close,c,mask)
    group=next((g for g,members in manifest['groups'].items() if symbol in members),'sector_ETF_proxy')
    peers=manifest['groups'][group] if group!='sector_ETF_proxy' else ['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']
    for s in peers:
        if s not in price:price[s]=np.nan;total[s]=np.nan
    x=f.context_features(price,total,vol,symbol,peers,own)
    alternate=f.slow_features(close,c,'2W',1)
    x=x.join(alternate[['w2_hist','w2_hist_delta','w2_macd','w2_depth_rank']].add_prefix('alternate_'))
    selection=[];behavioral=None
    if symbol in residual:
        selection=select_peers(residual,symbol,start)
        plan=[{'symbol':symbol,'start_pos':start,'end_pos':len(price),
          'starts':str(price.index[start].date()),'selected_at':str(price.index[start-1].date()),
          'peers':[r[0] for r in selection],'correlations':[r[1] for r in selection],
          'common_counts':[r[2] for r in selection]}]
        b=build_context(price,total,symbol,plan);x=x.join(b)
        if len(selection)>=2:behavioral=cohort_state(x,'beh_').iloc[-1].to_dict()
    state=cohort_state(x).iloc[-1].to_dict();slow=slow_state(x).iloc[-1].to_dict();last=x.iloc[-1]
    relative=relative_dynamics(total[symbol],x.peer_return_1).iloc[-1].to_dict()
    events={name:last_event(own,name) for name in ['dot','persistent_dot','rsi_macd_3d_cross']}
    failed={}
    for name in ['dot','rsi_macd_3d_cross']:
        failed[name]=cross_cycle(price[symbol],x[name].fillna(False),x.w2_hist,x.episode_number).iloc[-1].to_dict()
    closed_clocks={}
    for name,unit,parity in [('2W_pair0','2W',0),('2W_pair1','2W',1),('1M','1M',0)]:
        bars=f.period_bars(close,unit,parity)
        closed_clocks[name]={'known_calendar_end':str(bars.index[-1].date()),'last_price_session':str(bars.last_input.iloc[-1].date()),'completed_bars':len(bars)}
    facts={key:float(last[key]) if key in last and pd.notna(last[key]) and np.isfinite(float(last[key])) else None for key in FACTS}
    risk_record=risk.observe(data[symbol],ORIGIN);validate_risk_record(risk_record,ORIGIN)
    status='CONTEXT_INCOMPLETE'
    if slow['slow_known'] and state['cohort_known']:
        status=('SLOW_AND_COHORT_SUPPORTED' if slow['slow_supported'] and state['cohort_supported'] else
                'SLOW_SUPPORT_ONLY' if slow['slow_supported'] else 'COHORT_SUPPORT_ONLY' if state['cohort_supported'] else 'SUPPORT_NOT_ESTABLISHED')
    record={'instrument':symbol,'origin':ORIGIN,'group':group,'source_snapshot_sha256':hashlib.sha256((ROOT/'forward_private'/f'{symbol}.parquet').read_bytes()).hexdigest(),
      'event_observations':events,'new_trigger_on_origin':any(r['new_on_origin'] for r in events.values()),
      'context_state':status,'original_impulse_interpretation':f.interpretation(last),'slow_support':slow,
      'economic_cohort':{'members':[s for s in peers if s!=symbol],**state},
      'behavioral_cohort':{'selected_at':str(price.index[start-1].date()) if selection else None,
          'members':[r[0] for r in selection],'residual_correlations':[r[1] for r in selection],
          'state':behavioral,'current_vintage_survivor_panel':True},
      'relative_dynamics':relative,'prior_failed_attempt_context':failed,'facts':facts,'closed_timeframe_clocks':closed_clocks,
      'provisional_slow_observations':{'2W_pair0':nowcast(close,c,ORIGIN,'2W',0),'2W_pair1':nowcast(close,c,ORIGIN,'2W',1),'1M':nowcast(close,c,ORIGIN,'1M')},
      'risk_forecast':risk_record,'missing_fresh_context':['VIX','VVIX'],
      'history_reset_start':'2023-06-01','source_anchor':'dataset_start_not_certified_chart_listing_anchor',
      'conditional_entry_probability':None,'guaranteed_durable_bottom':False,
      'authority':{'may_rank':False,'may_size':False,'may_trade':False,'may_override_entry':False}}
    return clean_json(record)


def qualify(root,owner_path):
    capture=json.loads((root/'FORWARD_CAPTURE_RECEIPT.json').read_text())
    if capture['status']!='COMPLETE':raise ValueError('Original capture incomplete; reconcile it')
    dest=root/'forward_private';dest.mkdir(exist_ok=False)
    owner=load_owner(Path(owner_path));old_price,_,_,_=f.load_segment(root,'post')
    records={};refused={}
    roster=capture['requested_symbols']
    for request in capture['requests']:
        symbol=request['instrument']
        receipt=json.loads(Path(request['receipt_path']).read_text());owner.validate_receipt(receipt)
        raw=gzip.decompress(Path(request['raw_path']).read_bytes())
        try:
            data,record=adapt_capture(raw,receipt,symbol,roster)
            record['cross_provider_basis_check']=compare_overlap(data,old_price[symbol])
            data.to_parquet(dest/f'{symbol}.parquet');record['snapshot_sha256']=hashlib.sha256((dest/f'{symbol}.parquet').read_bytes()).hexdigest()
            record['original_receipt_path']=request['receipt_path'];record['original_raw_path']=request['raw_path'];records[symbol]=record
            print('CURRENT_INPUT_QUALIFIED',symbol,record['ordinary_action_count'],flush=True)
        except ValueError as exc:
            refused[symbol]={'reason':str(exc),'source_receipt_id':receipt['receipt_id']}
            print('CURRENT_INPUT_QUARANTINED',symbol,str(exc),flush=True)
    result={'qualified':records,'quarantined':refused,'source_provider':'tiingo','historical_payoff_replays_changed':False,'origin':ORIGIN}
    write_json(dest/'qualification.json',result)
    if 'SPY' not in records:raise ValueError('Required common calendar source unavailable')
    return result


def main(root,owner_path,revision,donor):
    root=Path(root);out=root/'FORWARD_OBSERVATION.json';receipt=root/'FORWARD_OBSERVATION_RECEIPT.json'
    if out.exists() or receipt.exists():raise RuntimeError('Original observation exists; reconcile before continuation')
    state={'status':'PREPARING','started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'research_revision':revision,'completed_instruments':[]}
    write_json(receipt,state)
    qualification=qualify(root,owner_path);observations=[]
    (root/'forward_private/results').mkdir()
    with concurrent.futures.ProcessPoolExecutor(max_workers=4,initializer=initialize,initargs=(str(root),)) as pool:
        for row in pool.map(observe_symbol,sorted(qualification['qualified'])):
            observations.append(row);symbol=row['instrument'];write_json(root/'forward_private/results'/f'{symbol}.json',row)
            state['completed_instruments'].append(symbol);state['status']='OBSERVING';write_json(receipt,state)
            print('CURRENT_RESEARCH_OBSERVATION',symbol,row['context_state'],row['risk_forecast']['status'],flush=True)
    # Actual existing source consumer, explicitly without current implicit defaults.
    prepare_consumer(Path(donor))
    from engine.signal_gate import gate
    from portfolio.entry_engine import assess
    digest=hashlib.sha256((root/'forward_private/qualification.json').read_bytes()).hexdigest();consumer_records=[]
    for row in observations:
        symbol=row['instrument'];data=pd.read_parquet(root/'forward_private'/f'{symbol}.parquet')
        native=gate(symbol,data.close,washout_waiver=False)
        before=assess(symbol,series=data.close,signal_gate_row=native,as_of=ORIGIN,_use_defaults=False)
        context=make_context(symbol,ORIGIN,row['original_impulse_interpretation'],row['facts'],source_hash=digest,
             research_revision=revision,peer_basis='sector_ETF_proxy' if row['group']=='sector_ETF_proxy' else 'fixed_economic_diagnostic',history_reset=True,
             risk_forecast=row['risk_forecast'],support_context={
               'observed_session':ORIGIN,'state':row['context_state'],'slow_known':bool(row['slow_support']['slow_known']),
               'slow_supported':bool(row['slow_support']['slow_supported']),'cohort_known':bool(row['economic_cohort']['cohort_known']),
               'cohort_supported':bool(row['economic_cohort']['cohort_supported']),'phase_disagreement':bool(row['slow_support']['slow_phase_disagreement']),
               'new_trigger_on_origin':bool(row['new_trigger_on_origin'])})
        joined=attach(before,context,instrument=symbol,expected_session=ORIGIN,expected_source_hash=digest)
        if {k:v for k,v in joined.items() if k!='nested_cycle_research'}!=before:raise AssertionError('Incumbent changed')
        consumer_records.append({'instrument':symbol,'verdict':before.get('verdict'),'buyable':before.get('buyable'),
            'score':before.get('entry_score'),'decision_unchanged':True,'context_freshness':joined['nested_cycle_research']['freshness'],
            'actual_risk_forecast_attached':joined['nested_cycle_research']['risk_forecast'] is not None,
            'actual_recovery_support_attached':joined['nested_cycle_research']['support_context'] is not None})
    issue=datetime.datetime.now(datetime.timezone.utc).isoformat()
    risk_values=sum(len(r['risk_forecast']['comparator']['mean_daily_variance'])+len((r['risk_forecast']['forecasts'] or {}).get('mean_daily_variance',[])) for r in observations)
    packet={'schema':'mastermind.nested_cycle_forward_research.v1','origin':ORIGIN,'issued_at_utc':issue,
      'research_revision':revision,'qualified_input_manifest_sha256':digest,'source_provider':'tiingo',
      'historical_first_availability_proven':False,'prospective_outcomes_matured_at_issue':0,
      'forecast_target_sessions':'strictly_after_origin_and_after_issuance_no_backdated_entry',
      'variance_forecast_horizons_sessions':[1,5,20],'future_entry_outcome_contract_sessions':[21,63],
      'execution_if_future_research_policy_is_evaluated':'first_regular_session_close_after_issue',
      'observations':observations,'actual_pinned_consumer_witness':consumer_records,
      'new_trigger_count':sum(r['new_trigger_on_origin'] for r in observations),'recorded_model_horizon_variance_values':risk_values,
      'missing_fresh_market_context':['VIX','VVIX'],'quarantined_inputs':qualification['quarantined'],
      'no_live_orders_or_ranking_changes':True,'recurring_collector_installed':False,'production_service_called':False,
      'authority':{'may_rank':False,'may_size':False,'may_trade':False,'may_override_entry':False}}
    write_json(out,packet)
    state.update(status='COMPLETE',finished_at=issue,instruments=len(observations),forecast_values=risk_values,
        packet_sha256=hashlib.sha256(out.read_bytes()).hexdigest(),all_incumbents_preserved=True,source_revision=revision,
        publication_not_yet_proven=True,actual_production_deployment=False);write_json(receipt,state)
    print('FORWARD_INTELLIGENCE_COMPLETE',len(observations),risk_values,'new_triggers',packet['new_trigger_count'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default=str(Path(__file__).parent));p.add_argument('--owner',required=True);p.add_argument('--revision',required=True);p.add_argument('--donor',required=True)
    a=p.parse_args();main(a.root,a.owner,a.revision,a.donor)
