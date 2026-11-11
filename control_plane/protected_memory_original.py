"""Read-only original receipt integrity, NOT recipient/disclosure permission.

This leaf reads only existing Runtime rows/Events and fixed path metadata. It
never reads private packet/result files, creates Runtime, reconstructs a lease,
prepares source, calls an issuer/provider or returns an answer. The next owner
must obtain genuine original-recipient identity + current receiver permission
before a distinct read-only disclosure capability can exist. Missing recipient
fact is explicit; Control custody/owner_seat are not promoted to that fact.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import weakref
from dataclasses import dataclass

from common import memory_native_wire as wire
from common.native_memory_intent_contract import normalize_memory_runtime_intent
from control_plane import protected_memory_peer as peer
from control_plane.executive_runtime import Runtime, RuntimeStore, AttemptStatus, JobStatus

_REFERENCES=weakref.WeakKeyDictionary()

class OriginalReferenceRefused(ValueError):
    def __init__(self):super().__init__('protected_memory_original_reference_unavailable')

class OriginalMemoryReference:
    __slots__=('__weakref__',)
    def __new__(cls):raise OriginalReferenceRefused()
    def __repr__(self):return '<OriginalMemoryReference comparison-only; no disclosure authority>'

@dataclass(frozen=True)
class _State:
    runtime:object
    attempt_id:str
    reference:bytes
    pre_input:bytes
    case:bytes|None=None


def _fail():raise OriginalReferenceRefused()


def _one(con,kind,attempt):
    rows=con.execute('SELECT * FROM events WHERE event_type=? AND attempt_id=? LIMIT 2',(kind,attempt.attempt_id)).fetchall()
    if len(rows)!=1:_fail()
    row=dict(rows[0])
    if (row['job_id']!=attempt.job_id or row['attempt_id']!=attempt.attempt_id
            or row['worker_id']!=attempt.worker_id or row['quota_class']!=attempt.quota_class):_fail()
    return row,json.loads(row['payload_json'])


def _read(runtime,attempt_id):
    if type(runtime) is not Runtime or type(runtime.store) is not RuntimeStore:_fail()
    wire.token(attempt_id)
    with runtime.store.read() as con:
        # Existing read APIs own DTO decoding; the read-only SQL transaction
        # rechecks immutable rows after gathering the exact original receipts.
        attempt=runtime.attempts.get_attempt(attempt_id)
        if attempt is None or attempt.status is not AttemptStatus.COMPLETED:_fail()
        job=runtime.jobs.get_job(attempt.job_id)
        if (job is None or job.status is not JobStatus.COMPLETED or job.current_attempt_id!=attempt_id
                or job.allowed_write_paths or 'READ' not in job.requested_authorities
                or not set(job.requested_authorities)<= {'READ','RESEARCH'}):_fail()
        claimed=con.execute('SELECT event_id,aggregate_type,aggregate_id,event_type,job_id,attempt_id,worker_id,quota_class,payload_json '
            "FROM events WHERE event_type='JOB_CLAIMED' AND job_id=? AND attempt_id=? LIMIT 2",(job.job_id,attempt_id)).fetchall()
        if len(claimed)!=1:_fail()
        economic,event=_one(con,'MEMORY_ECONOMIC_ADMISSION_ATTEMPT',attempt)
        wire.exact(event,'schema operation_id pre_input_sha256 pre_input profile_sha256')
        if event['schema']!='mastermind.memory_economic_admission_attempt.v1':_fail()
        wire.digest(event['profile_sha256'])
        projection=event['pre_input'];peer._projection_shape(projection)
        original=peer.canonical(projection)
        if hashlib.sha256(original).hexdigest()!=event['pre_input_sha256']:_fail()
        bound=projection['runtime_admission']
        claim_ref={'schema':'mastermind.runtime_claim_ref.v1','event_id':claimed[0]['event_id'],
            'sha256':hashlib.sha256(peer.canonical(dict(claimed[0]))).hexdigest()}
        locator=normalize_memory_runtime_intent(job.constraints.get('native_memory'))
        if (bound['claim_ref']!=claim_ref or bound['job_id']!=job.job_id
                or bound['runtime_root']!=job.root_job_id or bound['parent_job_id']!=job.parent_job_id
                or bound['attempt_id']!=attempt_id or bound['worker_id']!=attempt.worker_id
                or bound['quota_class']!=attempt.quota_class or bound['fence']!=attempt.fence_generation
                or bound['authority_policy_hash']!=attempt.authority_policy_hash
                or bound['owner_seat']!=job.owner_seat
                or bound['orchestration_provenance_digest']!=job.orchestration_provenance_digest
                or bound['locator_sha256']!=hashlib.sha256(peer.canonical(locator)).hexdigest()
                or event['profile_sha256']!=job.constraints.get('execution_profile_digest')
                or locator['operation_id']!=event['operation_id']
                or projection['original_operation_id']!=event['operation_id']
                or locator['intent']!=projection['native_source_locator']):_fail()
        input_event,held=_one(con,'MEMORY_INPUT_RETAINED',attempt)
        wire.exact(held,'schema attempt_id pre_input_sha256 input_sha256 input_bytes')
        if (held['schema']!='mastermind.memory_original_input.v1' or held['attempt_id']!=attempt_id
                or held['pre_input_sha256']!=event['pre_input_sha256']):_fail()
        wire.digest(held['input_sha256']);wire.integer(held['input_bytes'],65536)
        launch_event,launch=_one(con,'MEMORY_EXECUTION_ATTEMPT',attempt)
        wire.exact(launch,'schema pre_input_sha256 input_sha256 input_bytes profile_sha256 body_sha256')
        if (launch['schema']!='mastermind.protected_memory_execution_start.v1'
                or any(launch[k]!=held[k] for k in ('pre_input_sha256','input_sha256','input_bytes'))
                or launch['profile_sha256']!=event['profile_sha256']):_fail()
        wire.digest(launch['body_sha256'])
        result_event,result=_one(con,'MEMORY_ORIGINAL_RESULT_RETAINED',attempt)
        version=result.get('schema')
        if version not in ('mastermind.protected_memory_original_result.v1','mastermind.protected_memory_original_result.v2'):_fail()
        wire.exact(result,'schema attempt_id input_sha256 result_sha256 result_bytes verification scientific_admission adjudicator_access'+
            (' source_authorization' if version.endswith('.v2') else ''))
        if (result['attempt_id']!=attempt_id
                or result['input_sha256']!=held['input_sha256'] or type(result['verification']) is not dict
                or set(result['verification'])!=set(wire.FLAGS)
                or any(value is not False for value in result['verification'].values())
                or result['scientific_admission'] is not False or result['adjudicator_access'] is not False):_fail()
        wire.digest(result['result_sha256']);wire.integer(result['result_bytes'],65536)
        case=None;recipient='UNRECORDED'
        if version.endswith('.v2'):
            case_event,case=_one(con,'MEMORY_CASE_BOUND',attempt)
            wire.exact(case,'schema attempt_id pre_input_sha256 operation_id wire_version intent issuer locator')
            expected_intent=dict(projection['native_source_locator'],participant_binding_sha256=event['pre_input_sha256'])
            if (case['schema']!='mastermind.memory_original_case_binding.v1' or case['attempt_id']!=attempt_id
                    or case['pre_input_sha256']!=event['pre_input_sha256'] or case['operation_id']!=event['operation_id']
                    or case['wire_version']!='v3' or case['intent']!=expected_intent
                    or not economic['event_id']<case_event['event_id']<input_event['event_id']):_fail()
            wire._issuer(case['issuer'],'v3');wire.locator(case['locator'])
            if (case['locator']['input_sha256']!=held['input_sha256'] or case['locator']['input_bytes']!=held['input_bytes']
                    or case['locator']['installation_id']!=case['issuer']['installation_id']
                    or case['locator']['installation_epoch']!=case['issuer']['installation_epoch']):_fail()
            request=wire.validate_request({'schema':'research_factory.market_memory_e0_native_issuer_request.v3',
                'action':'authorize_result_disclosure','operation_id':case['operation_id'],'intent':case['intent'],
                'locator':case['locator'],'result_ref':{k:result[k] for k in ('attempt_id','input_sha256','result_sha256','result_bytes')}})
            authorization=result['source_authorization']
            wire.exact(authorization,'purpose input_sha256 result_sha256 result_bytes original_recipient')
            if (authorization['purpose']!='disclose_exact_original_untrusted_child_result'
                    or any(authorization[k]!=result[k] for k in ('input_sha256','result_sha256','result_bytes'))):_fail()
            recipient=wire.original_recipient(authorization['original_recipient'],request=request,issuer=case['issuer'])
        view_event,view=_one(con,'MEMORY_RESULT_VIEW_OBSERVED',attempt)
        wire.exact(view,'schema attempt_id input_sha256 result_sha256 view_sha256 verification scientific_admission adjudicator_access')
        wire.digest(view['view_sha256'])
        if (view.get('schema')!='mastermind.memory_case_completion.v1' or view.get('attempt_id')!=attempt_id
                or any(view.get(k)!=result[k] for k in ('input_sha256','result_sha256'))
                or type(view['verification']) is not dict or set(view['verification'])!=set(wire.FLAGS)
                or any(value is not False for value in view['verification'].values())
                or view.get('scientific_admission') is not False
                or view.get('adjudicator_access') is not False):_fail()
        terminal,_=_one(con,'JOB_COMPLETED',attempt)
        if not (economic['event_id']<input_event['event_id']<launch_event['event_id']
                <result_event['event_id']<view_event['event_id']<terminal['event_id']):_fail()
        directory=runtime.store.root/'data/control_plane/runs'/attempt_id
        if (attempt.result_path!=str(directory/'memory-original-result') or attempt.stdout_path!=attempt.result_path
                or attempt.stderr_path!=str(directory/'memory-fixed-diagnostic')
                or not attempt.pid or not attempt.pgid or not attempt.process_start_identity or not attempt.boot_id):_fail()
        current=con.execute('SELECT status,job_id,result_path FROM attempts WHERE attempt_id=?',(attempt_id,)).fetchone()
        if current is None or tuple(current)!=('COMPLETED',job.job_id,attempt.result_path):_fail()
    ref={'schema':'mastermind.memory_completed_original_reference.v1','operation_id':event['operation_id'],
        'job_id':job.job_id,'root_job_id':job.root_job_id,'parent_job_id':job.parent_job_id,'attempt_id':attempt_id,
        'pre_input_sha256':event['pre_input_sha256'],'input_sha256':held['input_sha256'],'input_bytes':held['input_bytes'],
        'result_sha256':result['result_sha256'],'result_bytes':result['result_bytes'],
        'receipt_event_ids':[row['event_id'] for row in (economic,input_event,launch_event,result_event,view_event,terminal)],
        'original_recipient':recipient,'disclosure_authorized':False,'retry_authorized':False}
    if case is not None:ref.update(schema='mastermind.memory_completed_original_reference.v2',wire_version='v3')
    return wire.canonical(ref),original,None if case is None else wire.canonical(case)


def completed_original_reference(runtime,attempt_id):
    """Owner-internal receipt integrity only; never a current read permission."""
    try:
        ref,original,case=_read(runtime,attempt_id)
        value=object.__new__(OriginalMemoryReference)
        _REFERENCES[value]=_State(runtime,attempt_id,ref,original,case)
        return value
    except Exception:raise OriginalReferenceRefused() from None


def current_reference(value):
    try:
        if type(value) is not OriginalMemoryReference or value not in _REFERENCES:_fail()
        state=_REFERENCES[value];ref,original,case=_read(state.runtime,state.attempt_id)
        if ref!=state.reference or original!=state.pre_input or case!=state.case:_fail()
        return json.loads(ref)
    except Exception:raise OriginalReferenceRefused() from None
