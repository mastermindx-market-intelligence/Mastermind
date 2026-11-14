"""Read-only research context. Never changes an incumbent decision or grants risk.

This consumes explicit phase5 observations; it is not a replacement G0 producer,
market-state database, service or source of calibrated entry probabilities.
"""
from __future__ import annotations
import copy
import hashlib
import re
from datetime import date
import numpy as np
import pandas as pd
import experiment as ex
from robustness import extended_context

AUTHORITY={'may_rank':False,'may_size':False,'may_trade':False,'may_override_entry':False}


def as_day(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError('Economic date required')
    return date.fromisoformat(value)


def attach(incumbent,observation,*,instrument,expected_session,expected_source_hash):
    if not isinstance(incumbent,dict) or 'independent_recovery_research' in incumbent:
        raise ValueError('Ambiguous incumbent report')
    if not isinstance(observation,dict):raise ValueError('Observation required')
    if incumbent.get('ticker')!=instrument or observation.get('instrument')!=instrument:
        raise ValueError('Wrong instrument binding')
    if not isinstance(expected_source_hash,str) or observation.get('source_manifest_sha256')!=expected_source_hash or not re.fullmatch(r'[0-9a-f]{64}',expected_source_hash):
        raise ValueError('Source lineage mismatch')
    origin=as_day(observation.get('origin_session'));expected=as_day(expected_session)
    if origin>expected:raise ValueError('Future observation')
    if observation.get('authority')!=AUTHORITY:raise ValueError('Research cannot grant authority')
    if observation.get('population')!='nine_sector_ETF_proxy':raise ValueError('Undeclared cohort basis')
    if observation.get('calibrated_entry_probability') is not None:raise ValueError('Unqualified probability')
    required=['market_repair','declining_low_pressure','sector_above126','sector_positive63']
    facts=observation.get('facts',{})
    if any(type(facts.get(k)) is not bool for k in required):raise ValueError('Missing or invalid observation facts')
    for k in ('vix_rising','vvix_rising'):
        if facts.get(k) is not None and type(facts[k]) is not bool:raise ValueError('Invalid volatility state')
    status='HISTORICAL_RESEARCH_CONTEXT' if origin==expected else 'STALE_RESEARCH_CONTEXT'
    state='mixed'
    if facts['market_repair'] and facts['declining_low_pressure']:state='repair_with_receding_new_lows_observed'
    elif facts['market_repair']:state='repair_observed_pressure_not_confirmed'
    elif facts['sector_above126'] and facts['sector_positive63']:state='continuation_structure_observed'
    # States describe measurements, not calibrated recovery predictions.
    extra=copy.deepcopy(observation);extra.update(status=status,descriptive_state=state,
      expected_session=expected_session,usable_as_current_context=status!='STALE_RESEARCH_CONTEXT',
      scientific_promotion='NOT_ESTABLISHED',incumbent_decision_preserved=True)
    result=copy.deepcopy(incumbent);result['independent_recovery_research']=extra
    return result


def readings(price,total,vol,source_manifest_hash):
    if not price.index.equals(total.index) or not price.index.equals(vol.index):raise ValueError('Mixed observation calendars')
    if len(price)<252 or not set(ex.SECTORS+['SPY']).issubset(price.columns) or not set(ex.SECTORS+['SPY']).issubset(total.columns):
        raise ValueError('Insufficient qualified price history')
    if not np.isfinite(price.to_numpy(float)).all() or not np.isfinite(total.to_numpy(float)).all():
        raise ValueError('Missing price is not benign context')
    if (price<=0).any().any() or (total<=0).any().any():raise ValueError('Nonpositive price')
    ctx=ex.context(price,total,vol);xt=extended_context(price,total,ctx)
    origin=str(price.index[-1].date());rows=[]
    for ticker in ex.SECTORS:
        good=price[ticker].iloc[-1]>price[ticker].rolling(126).mean().iloc[-1]
        momentum=(total[ticker]/total[ticker].shift(63)-1).iloc[-1]>0
        rows.append({'instrument':ticker,'origin_session':origin,'source_manifest_sha256':source_manifest_hash,
          'population':'nine_sector_ETF_proxy','native_event_status':'NOT_SUPPLIED_BY_THIS_CONTEXT_READER',
          'facts':{'market_repair':bool(ctx['repair'].iloc[-1]),'declining_low_pressure':bool(xt['lower_pressure'].iloc[-1]),
             'sector_above126':bool(good),'sector_positive63':bool(momentum),
             'vix_rising':bool(ctx['VIX_rising'].iloc[-1]) if ctx['VIX_valid'].iloc[-1] else None,
             'vvix_rising':bool(ctx['VVIX_rising'].iloc[-1]) if ctx['VVIX_valid'].iloc[-1] else None},
          'calibrated_entry_probability':None,'authority':dict(AUTHORITY),
          'limitations':['Not stock-constituent breadth','Current-vintage history, original availability unknown',
                         'Context cannot independently create or approve an entry']})
    return rows
