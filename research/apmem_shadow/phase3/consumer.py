"""Read-only research context for the existing entry assessor.

This projection never changes buyability, rank, score, size or a held position.
It distinguishes movement probability from favorable-direction information and
refuses to reuse a twenty-one-session barrier model as a different trade plan.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime
import math
import re

CONTRACT='stop5_target8_h21_next_open_v1'
SHA=re.compile(r'^[a-f0-9]{64}$')
REV=re.compile(r'^[a-f0-9]{40}$')
MODELS={'frequency','price','risk','interaction'}
AUTHORITY={'may_rank':False,'may_size':False,'may_trade':False,'may_change_entry':False}


def timestamp(value):
    if not isinstance(value,str):raise ValueError('clock is not a string')
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None or result.utcoffset() is None:raise ValueError('clock lacks timezone')
    return result


def session(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):
        raise ValueError('invalid observed session')
    return datetime.strptime(value,'%Y-%m-%d').date()


def positive(value):
    return type(value) in (int,float) and math.isfinite(value) and value>0


def build_context(entry_report: dict,payload: dict,*,instrument: str,origin: str,now: str,
                  intended_contract: str=CONTRACT,expected_lineage: dict | None=None):
    out={'schema':'mastermind.entry_risk_research.v1','status':'ABSTAIN','reason_codes':[],
         'instrument':instrument,'origin_session':origin,'authority':dict(AUTHORITY),
         'forecast_status':'UNAVAILABLE','conditional_status':'UNAVAILABLE',
         'evidence_maturity':'RESEARCH_NOT_PRODUCTION_QUALIFIED',
         'component_roles':{'technical':'observed entry-state representation',
                            'volatility':'dispersion estimate, not expected return',
                            'conditional_model':'barrier activity and conditional outcome estimates'},
         'directional_edge_established':False,'recurring_execution':False}
    def fail(reason):
        out['reason_codes'].append(reason);return out
    if not isinstance(entry_report,dict) or not isinstance(payload,dict):return fail('INVALID_ENVELOPE')
    if entry_report.get('ticker')!=instrument or payload.get('instrument')!=instrument:
        return fail('WRONG_INSTRUMENT')
    try:
        observed=session(origin)
        if session(entry_report.get('as_of'))!=observed or session(payload.get('origin_session'))!=observed:
            return fail('WRONG_OR_STALE_ORIGIN')
        captured=timestamp(payload.get('captured_at'));computed=timestamp(payload.get('computed_at'));clock=timestamp(now)
        if captured>computed or computed>clock:return fail('INVALID_COMPUTATION_CLOCK')
    except (ValueError,TypeError,OverflowError):return fail('UNKNOWN_OR_INVALID_CLOCK')
    lineage=payload.get('lineage')
    if not isinstance(lineage,dict):return fail('MISSING_SOURCE_LINEAGE')
    for key in ('raw_capture_sha256','prefix_sha256'):
        if not isinstance(lineage.get(key),str) or not SHA.fullmatch(lineage[key]):return fail('INVALID_INPUT_DIGEST')
    for key in ('native_source_commit','research_source_commit'):
        if not isinstance(lineage.get(key),str) or not REV.fullmatch(lineage[key]):return fail('INVALID_SOURCE_REVISION')
    if any(payload.get(key) is True for key in AUTHORITY):return fail('INCOMPATIBLE_AUTHORITY_CLAIM')
    if any(str(key).startswith('future_') or key in ('class_id','realized_return','actual_outcome') for key in payload):
        return fail('FUTURE_OUTCOME_IN_CONSUMER_INPUT')
    if expected_lineage is None or not isinstance(expected_lineage,dict) or lineage!=expected_lineage:
        return fail('UNBOUND_OR_MISMATCHED_SOURCE_LINEAGE')
    if payload.get('historical_first_availability') is not None:
        return fail('UNVERIFIED_HISTORICAL_PUBLICATION_CLAIM')
    forecast=payload.get('forecast')
    if not isinstance(forecast,dict) or forecast.get('unit')!='mean_daily_variance':return fail('INVALID_FORECAST_UNIT')
    try:
        if session(forecast.get('fit_cutoff'))>observed:return fail('FUTURE_FORECAST_FIT')
    except (ValueError,TypeError):return fail('UNKNOWN_FORECAST_FIT_CLOCK')
    if not all(positive(forecast.get('h'+str(h))) for h in (1,5,20)):
        return fail('INVALID_OR_MISSING_FORECAST')
    out.update(status='RESEARCH_ONLY',forecast_status='AVAILABLE_RESEARCH',lineage=deepcopy(lineage),
               captured_at=payload['captured_at'],computed_at=payload['computed_at'],
               historical_first_availability=payload.get('historical_first_availability'),
               capture_utc_date_after_origin=captured.date()>observed,
               historical_first_availability_proven=False,prospective_outcomes_validated=False,
               forecast={'model':forecast.get('model'),'unit':'annualized_volatility_fraction',
                         'h1':math.sqrt(252*forecast['h1']),'h5':math.sqrt(252*forecast['h5']),
                         'h20':math.sqrt(252*forecast['h20']),'fit_cutoff':forecast['fit_cutoff'],
                         'is_loss_limit':False,'is_direction_forecast':False})
    conditional=payload.get('conditional')
    if conditional is None:
        out['reason_codes'].append('CONDITIONAL_MODEL_UNAVAILABLE');return out
    if not isinstance(conditional,dict) or conditional.get('contract')!=CONTRACT or intended_contract!=CONTRACT:
        out['conditional_status']='ABSTAIN_CONTRACT_MISMATCH';out['reason_codes'].append('DIFFERENT_EXIT_OR_HORIZON');return out
    native=payload.get('native')
    if not isinstance(native,dict) or native.get('eligible') is not True or native.get('tier') not in ('T1','T2') or native.get('provisional') is not False:
        out['conditional_status']='ABSTAIN_NO_CONFIRMED_ENTRY';out['reason_codes'].append('NO_CONFIRMED_T1_T2');return out
    if conditional.get('model') not in MODELS or type(conditional.get('training_n')) is not int or conditional['training_n']<300:
        out['conditional_status']='ABSTAIN_UNQUALIFIED_FIT';out['reason_codes'].append('INSUFFICIENT_OR_UNKNOWN_MODEL');return out
    try:
        fit=session(conditional.get('fit_origin'));last_label=session(conditional.get('latest_training_label_end'))
        if last_label>fit or fit>observed:raise ValueError('future training')
        age=conditional.get('fit_age_sessions')
        if type(age) is not int or not 0<=age<63:raise ValueError('stale training')
    except (ValueError,TypeError):
        out['conditional_status']='ABSTAIN_TRAINING_CLOCK';out['reason_codes'].append('FUTURE_STALE_OR_UNKNOWN_TRAINING');return out
    probabilities=[conditional.get(k) for k in ('p_stop','p_target','p_timeout')]
    if (not all(type(x) in (int,float) and math.isfinite(x) and 0<=x<=1 for x in probabilities)
            or abs(sum(probabilities)-1)>1e-9):
        out['conditional_status']='ABSTAIN_INVALID_PROBABILITY';out['reason_codes'].append('INVALID_OUTCOME_DISTRIBUTION');return out
    active=probabilities[0]+probabilities[1]
    out['conditional_status']='AVAILABLE_RESEARCH'
    out['conditional']={'model':conditional['model'],'contract':CONTRACT,
                        'p_stop':probabilities[0],'p_target':probabilities[1],'p_timeout':probabilities[2],
                        'p_activity':active,'p_target_given_activity':probabilities[1]/active if active>0 else None,
                        'fit_origin':conditional['fit_origin'],'latest_training_label_end':conditional['latest_training_label_end'],
                        'training_n':conditional['training_n'],'fit_age_sessions':age,
                        'prospective_calibration_proven':False,'not_a_recommendation':True}
    return out


def attach(entry_report: dict,payload: dict,**kwargs):
    if not isinstance(entry_report,dict):raise ValueError('existing entry report required')
    if 'entry_risk_research' in entry_report:raise ValueError('research context already attached; reconcile its version')
    original=deepcopy(entry_report)
    result=deepcopy(entry_report)
    result['entry_risk_research']=build_context(entry_report,payload,**kwargs)
    if entry_report!=original or {k:v for k,v in result.items() if k!='entry_risk_research'}!=original:
        raise AssertionError('research projection changed the incumbent decision')
    return result
