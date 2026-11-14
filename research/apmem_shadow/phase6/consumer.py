"""Read-only integration seam for nested-cycle research context.

The incumbent owns verdict, score, buyability and live policy. This module can
attach descriptive evidence or an unavailable/stale result, never upgrade it.
"""
from __future__ import annotations
import copy,datetime,math,re
from typing import Mapping

SCHEMA='mastermind.nested_cycle_research.v1'
AUTHORITY={'may_rank':False,'may_size':False,'may_trade':False,'may_override_entry':False}
STATES={'CONTEXT_INCOMPLETE','FAST_TURN_WITH_SLOW_PRESSURE','LOCAL_REPAIR_WITHOUT_COHORT_CONFIRMATION',
        'COHORT_REPAIR_WITHOUT_RELATIVE_RESILIENCE','REPAIR_WITH_RELATIVE_RESILIENCE'}
FACTS={'w2_hist','w2_hist_delta','month_hist','month_hist_delta','peer_return_21','peer_breadth_change',
       'peer_low_pressure_change','peer_coverage','relative_resilience21','market_resilience21',
       'beh_peer_return_21','beh_relative_resilience21','prior_failed_attempts','episode_age',
       'alternate_w2_hist_delta','vix_trend','vvix_trend'}


def iso(value):
    if not isinstance(value,str):raise ValueError('ISO date required')
    return datetime.date.fromisoformat(value)


def make_context(symbol,as_of,state,facts,*,source_hash,research_revision,peer_basis,peer_selected_at=None,
                 history_reset=False,latest_forecast=None,risk_forecast=None,support_context=None):
    if not re.fullmatch(r'[A-Z][A-Z0-9.-]{0,12}',symbol):raise ValueError('Invalid instrument')
    iso(as_of)
    if state not in STATES:raise ValueError('Unknown research state')
    if not re.fullmatch(r'[a-f0-9]{64}',source_hash):raise ValueError('Unbound source')
    if not re.fullmatch(r'[a-f0-9]{40}',research_revision):raise ValueError('Unbound code')
    if peer_basis not in ('fixed_economic_diagnostic','lagged_behavioral_diagnostic','sector_ETF_proxy'):raise ValueError('Unknown population')
    if peer_selected_at is not None and iso(peer_selected_at)>=iso(as_of):raise ValueError('Behavioral peers must precede observation')
    if peer_basis=='lagged_behavioral_diagnostic' and peer_selected_at is None:raise ValueError('Missing peer-selection clock')
    numeric={}
    for key,value in facts.items():
        if key not in FACTS:continue
        if value is None:numeric[key]=None
        elif isinstance(value,(int,float)) and math.isfinite(float(value)):numeric[key]=float(value)
        else:raise ValueError('Nonfinite/untyped research fact: '+key)
    forecast=copy.deepcopy(latest_forecast)
    if forecast is not None:
        if forecast.get('calibrated') is not False:raise ValueError('No calibrated-probability authority')
        if iso(forecast['last_training_end'])>=iso(as_of):raise ValueError('Future training labels')
        if forecast.get('horizon_sessions') not in (21,63):raise ValueError('Unsupported forecast horizon')
        for value in forecast.get('probabilities',{}).values():
            if not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<value<1:raise ValueError('Invalid probability')
    risk=copy.deepcopy(risk_forecast)
    if risk is not None:
        from risk_observation import validate_risk_record
        validate_risk_record(risk,as_of)
    support=copy.deepcopy(support_context)
    if support is not None:
        validate_support(support,as_of)
    return {'schema':SCHEMA,'instrument':symbol,'as_of':as_of,'state':state,'facts':numeric,
      'source_hash':source_hash,'research_revision':research_revision,'peer_basis':peer_basis,
      'peer_selected_at':peer_selected_at,'history_reset':bool(history_reset),'forecast':forecast,
      'risk_forecast':risk,'support_context':support,
      'authority':copy.deepcopy(AUTHORITY),'validation':'RETROSPECTIVE_RESEARCH_NOT_PRODUCTION_QUALIFIED'}


def attach(incumbent:Mapping,context:Mapping,*,instrument,expected_session,expected_source_hash):
    original=copy.deepcopy(dict(incumbent));c=copy.deepcopy(dict(context))
    if c.get('schema')!=SCHEMA or c.get('instrument')!=instrument:raise ValueError('Context identity mismatch')
    if original.get('ticker',instrument)!=instrument:raise ValueError('Incumbent identity mismatch')
    if c.get('authority')!=AUTHORITY:raise ValueError('Research cannot grant entry authority')
    if c.get('source_hash')!=expected_source_hash:raise ValueError('Unexpected source bytes')
    if c.get('validation')!='RETROSPECTIVE_RESEARCH_NOT_PRODUCTION_QUALIFIED':raise ValueError('Unexpected validation claim')
    if c.get('risk_forecast') is not None:
        from risk_observation import validate_risk_record
        validate_risk_record(c['risk_forecast'],c['as_of'])
    if c.get('support_context') is not None:validate_support(c['support_context'],c['as_of'])
    observed=iso(c['as_of']);expected=iso(expected_session)
    if observed>expected:raise ValueError('Future observation')
    c['freshness']='current_for_requested_session' if observed==expected else 'stale_for_requested_session'
    c['expected_session']=expected_session
    # Preserve the entire incumbent verbatim; attach only a namespaced context.
    if 'nested_cycle_research' in original:raise ValueError('Existing attachment must be reconciled, not overwritten')
    out=copy.deepcopy(original);out['nested_cycle_research']=c
    for key,value in original.items():
        if out[key]!=value:raise AssertionError('Incumbent decision changed')
    return out


def validate_support(support,as_of):
    required=['slow_known','slow_supported','cohort_known','cohort_supported','phase_disagreement','new_trigger_on_origin']
    if support.get('observed_session')!=as_of or any(type(support.get(k)) is not bool for k in required):
        raise ValueError('Invalid recovery-support clocks or types')
    if support['slow_supported'] and not support['slow_known']:raise ValueError('Unknown slow evidence cannot confirm')
    if support['cohort_supported'] and not support['cohort_known']:raise ValueError('Unknown peers cannot confirm')
    expected='CONTEXT_INCOMPLETE'
    if support['slow_known'] and support['cohort_known']:
        expected=('SLOW_AND_COHORT_SUPPORTED' if support['slow_supported'] and support['cohort_supported'] else
                  'SLOW_SUPPORT_ONLY' if support['slow_supported'] else
                  'COHORT_SUPPORT_ONLY' if support['cohort_supported'] else 'SUPPORT_NOT_ESTABLISHED')
    if support.get('state')!=expected:raise ValueError('Recovery-state label contradicts its evidence')
