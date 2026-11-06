"""Closed packet/result DATA projection. It grants no read/disclosure authority.

Only the protected owner supplies exact currently authenticated issuer input and
stable original result. Citation membership is availability, never prose truth,
semantic blinding, served identity, scientific admission or adjudicator access.
"""
import hashlib
import json
import math
import re
from datetime import datetime
from common import memory_native_wire as w

FIELDS=('growth_score','inflation_score','quad','liquidity_overlay','cycle_tag')
LIMITATIONS=['source_dates_and_counts_may_reveal_condition','original_house_output_not_constituent_truth',
    'subsequent_outcomes_not_attached','no_semantic_causal_predictive_or_action_authority']
CLOCKS='captured_at raw_source_observed_at raw_source_built_at feature_as_of event_time as_known_at knowledge_cutoff'

class ParticipantViewRefused(ValueError):
    def __init__(self):super().__init__('memory_participant_view_refused')

def fail():raise ParticipantViewRefused()

def _tree(v,depth=0,budget=None):
    if budget is None:budget=[8192]
    budget[0]-=1
    if budget[0]<0 or depth>16:fail()
    if type(v) is dict:
        for k,item in v.items():
            if type(k) is not str:fail()
            _tree(item,depth+1,budget)
    elif type(v) is list:
        for item in v:_tree(item,depth+1,budget)
    elif type(v) is float:
        if not math.isfinite(v):fail()
    elif type(v) not in (str,int,bool,type(None)):fail()

def _json(raw,*,canonical=False):
    if type(raw) is not bytes or not 1<=len(raw)<=65536:fail()
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:fail()
            result[k]=v
        return result
    try:
        value=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:fail());_tree(value)
        if canonical and w.canonical(value)!=raw:fail()
        return value
    except (ValueError,TypeError,UnicodeError,RecursionError):raise ParticipantViewRefused() from None

def _utc(v):
    if type(v) is not str or not 1<=len(v)<=64:fail()
    try:
        value=datetime.fromisoformat(v[:-1]+'+00:00' if v.endswith('Z') else v)
        if value.tzinfo is None or value.utcoffset() is None:fail()
        return value
    except (ValueError,TypeError,OverflowError):raise ParticipantViewRefused() from None

def _ids(values,minimum,maximum):
    if type(values) is not list or not minimum<=len(values)<=maximum:fail()
    for value in values:w.token(value)
    if len(set(values))!=len(values):fail()

def selected_descriptors(packet):
    """Pure exact native wrapper extraction, never a supplied allowlist grant."""
    try:
        if type(packet) is not bytes or not 89<=len(packet)<=65536 or not packet.endswith(w.SUFFIX) or packet.count(w.SUFFIX)!=1:fail()
        body=_json(packet[:-len(w.SUFFIX)],canonical=True);w.exact(body,'schema task source_view')
        if body['schema']!='research_factory.market_memory_e0_participant_packet.v1':fail()
        task=body['task'];w.exact(task,'task_id subject_id instrument_id analysis_cutoff mode question question_sha256 required_facet_ids')
        w.token(task['task_id'])
        for key in ('subject_id','instrument_id'):
            if type(task[key]) is not str or re.fullmatch('mmsecurity_[a-f0-9]{64}',task[key]) is None:fail()
        cutoff=_utc(task['analysis_cutoff'])
        if task['mode'] not in ('historical_hypothetical','current_contextual_support'):fail()
        if type(task['question']) is not str or not 1<=len(task['question'])<=8192:fail()
        if hashlib.sha256(task['question'].encode()).hexdigest()!=task['question_sha256']:fail()
        _ids(task['required_facet_ids'],1,64)
        view=body['source_view'];w.exact(view,'schema authority source_cards state_differences explicit_method_identity_redacted actual_blinding_established limitations')
        if (view['schema']!='research_factory.market_memory_e0_method_redacted_sources.v1' or view['authority']!='display_only'
                or view['explicit_method_identity_redacted'] is not True or view['actual_blinding_established'] is not False
                or view['limitations']!=LIMITATIONS):fail()
        cards=view['source_cards']
        if type(cards) is not list or not 1<=len(cards)<=9:fail()
        descriptors=[];by_context={}
        for i,card in enumerate(cards):
            w.exact(card,'role context_id capture_id packet_sha256 subject_id source_receipt_ids source_session clocks facts missing_feature_ids evidence_basis')
            if card['role']!=('query' if i==0 else 'selected_neighbor') or card['evidence_basis']!='retained_original_house_output' or card['subject_id']!=task['subject_id']:fail()
            w.token(card['context_id']);w.token(card['capture_id']);w.digest(card['packet_sha256'])
            if card['context_id'] in by_context:fail()
            _ids(card['source_receipt_ids'],1,128);_ids(card['missing_feature_ids'],0,64)
            if type(card['source_session']) is not str or not 1<=len(card['source_session'])<=128:fail()
            w.exact(card['clocks'],CLOCKS)
            if any(_utc(v)>cutoff for v in card['clocks'].values()):fail()
            facts=card['facts']
            if type(facts) is not list or len(facts)!=5:fail()
            mapped={}
            for field,fact in zip(FIELDS,facts):
                w.exact(fact,'field value meaning citation structural_source_closure underlying_component_truth_authenticated')
                if (fact['field']!=field or fact['meaning']!='the_retained_house_output_reports_this_value'
                        or fact['structural_source_closure'] is not True or fact['underlying_component_truth_authenticated'] is not False):fail()
                cite=fact['citation'];w.exact(cite,'snapshot_id source_sha256 source_bytes json_pointer start_byte end_byte_exclusive span_sha256 quoted_json')
                w.token(cite['snapshot_id']);w.digest(cite['source_sha256']);w.digest(cite['span_sha256']);w.integer(cite['source_bytes'],4194304)
                if (type(cite['start_byte']) is not int or type(cite['end_byte_exclusive']) is not int
                        or not 0<=cite['start_byte']<cite['end_byte_exclusive']<=cite['source_bytes']
                        or cite['json_pointer']!='/state/'+field or type(cite['quoted_json']) is not str):fail()
                quote=cite['quoted_json'].encode()
                if (quote!=w.canonical(fact['value']) or len(quote)!=cite['end_byte_exclusive']-cite['start_byte']
                        or hashlib.sha256(quote).hexdigest()!=cite['span_sha256']):fail()
                # We deliberately do not fetch original snapshot or equate its
                # SHA with context packet SHA. Native owner established spans.
                mapped[field]=fact['value']
                descriptors.append({k:card[k] for k in ('context_id','capture_id','packet_sha256')}|{'field':field,'citation':cite})
            by_context[card['context_id']]=mapped
        differences=view['state_differences']
        if type(differences) is not list or len(differences)>40:fail()
        query=by_context[cards[0]['context_id']]
        expected=[]
        for card in cards[1:]:
            for field in FIELDS:
                neighbor=by_context[card['context_id']][field]
                if neighbor!=query[field]:expected.append({'context_id':card['context_id'],'field':field,
                    'query_value':query[field],'neighbor_value':neighbor,'meaning':'different_dated_outputs_not_a_logical_contradiction'})
        if w.canonical(differences)!=w.canonical(expected):fail()
        return json.loads(w.canonical(descriptors))
    except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):raise ParticipantViewRefused() from None

def project_original_result(packet,raw,*,attempt_id):
    """Only called inside current protected custody/disclosure authorization."""
    try:
        w.token(attempt_id)
        allowed={w.canonical(v) for v in selected_descriptors(packet)}
        result=_json(raw);w.exact(result,'schema answer citations')
        if result['schema']!='research_factory.market_memory_e0_participant_result.v1':fail()
        if type(result['answer']) is not str or not 1<=len(result['answer'])<=12000:fail()
        citations=result['citations']
        if type(citations) is not list or len(citations)>45:fail()
        encoded=[w.canonical(v) for v in citations]
        if len(set(encoded))!=len(encoded) or any(v not in allowed for v in encoded):fail()
        return {'schema':'mastermind.memory_recipient_result_view.v1','attempt_id':attempt_id,
            'input_sha256':hashlib.sha256(packet).hexdigest(),'result_sha256':hashlib.sha256(raw).hexdigest(),
            'answer':result['answer'],'citations':json.loads(w.canonical(citations)),
            'untrusted_worker_content':True,'actual_blinding_established':False,
            'verification':dict(w.FLAGS),'scientific_admission':False,'adjudicator_access':False}
    except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):raise ParticipantViewRefused() from None
