"""Control-local nominal economic receipt; no source rights or new allowance.

Every use rechecks actual Runtime/Control intent and asks the existing root
owner to query the original incumbent economic row/lease. No cached receipt,
caller hash, Boolean or Runtime profile by itself permits preparation/provider.
"""
from __future__ import annotations
import hashlib
import os
import weakref
from dataclasses import dataclass
from common import memory_native_wire as wire
from control_plane import protected_memory_peer as peer
from control_plane import memory_native_issuer as issuer
from control_plane import protected_memory_profile as profile

_ISSUED=weakref.WeakKeyDictionary()

class EconomicAdmission:
    __slots__=('__weakref__',)
    def __new__(cls): raise peer.ProtectedMemoryRefused()
    def __repr__(self): return '<EconomicAdmission private>'

@dataclass(frozen=True)
class _State:
    intent:object
    selector:bytes
    lease_id:str
    pid:int
    evaluation:object=None


def _exchange(intent, action, arguments, *, evaluation=None):
    before=peer.require_control_memory_intent(intent)
    frame={'schema':issuer.SCHEMA,'operation':'economic','projection':before,
        'request':{'action':action,'arguments':arguments}}
    if evaluation is not None:
        from control_plane import protected_memory_evaluation_assignment as assignments
        from control_plane import protected_memory_annotations as annotations
        from control_plane import protected_memory_evaluation_source as evaluation_source
        state=assignments.current_prepared(evaluation)
        if state['claim'] is not peer._CONTROL_ISSUED[intent].claim: raise peer.ProtectedMemoryRefused()
        frame['operation']='evaluation_economic'
        frame['evaluation_context']={'profile_id':state['observed']['profile_id'],
            'source_request':evaluation_source.make_request(state['context'][2],'authorize_evaluation_subject_read',
                subject=annotations.subject_selector(state['subject']),assignment=annotations.c.digest(annotations.assignment_material(state)))}
    response=issuer._send(frame)
    if peer.require_control_memory_intent(intent)!=before:raise peer.ProtectedMemoryRefused()
    if type(response) is not dict or response.get('state')=='ORIGINAL_EXCHANGE_UNKNOWN':
        raise issuer.NativeCaseUnknown()
    wire.exact(response,'schema state receipt')
    if response['schema']!=issuer.SCHEMA or response['state']!='ECONOMIC_OBSERVED':raise peer.ProtectedMemoryRefused()
    result=response['receipt']
    wire.exact(result,'schema root parent run_id pre_input_sha256 profile_sha256 lease_id phase retry_authorized')
    expected=dict(root=before['native_source_locator']['root_id'],parent=before['native_source_locator']['operator_run_id'],
        run_id=before['native_source_locator']['child_run_id'],pre_input_sha256=hashlib.sha256(peer.canonical(before)).hexdigest())
    if (result['schema']!='mastermind.protected_memory_economic_receipt.v1'
            or any(result[k]!=v for k,v in expected.items()) or result['retry_authorized'] is not False):
        raise peer.ProtectedMemoryRefused()
    wire.token(result['lease_id']);wire.digest(result['profile_sha256'])
    return result


def acquire(intent, qualified_profile, claim, observed):
    value=profile.require_protected_memory_profile(qualified_profile,claim,observed)
    from control_plane.protected_memory_delegation import read_original_economic_delegation
    delegation=read_original_economic_delegation(claim,qualified_profile,observed)
    projection,actual=issuer._event_context(intent)
    payload={'schema':'mastermind.memory_economic_admission_attempt.v1',
        'operation_id':projection['original_operation_id'],
        'pre_input_sha256':hashlib.sha256(peer.canonical(projection)).hexdigest(),
        'pre_input':projection,'profile_sha256':hashlib.sha256(profile.canonical(value)).hexdigest()}
    attempt=actual.lease.attempt
    command='memory-case:'+attempt.attempt_id+':economic-admission'
    with actual.runtime.store.transaction() as con:
        if con.execute('SELECT 1 FROM events WHERE command_id=?',(command,)).fetchone():
            raise issuer.NativeCaseUnknown()
        actual.runtime.store.append_event(con,aggregate_type='attempt',aggregate_id=attempt.attempt_id,
            event_type='MEMORY_ECONOMIC_ADMISSION_ATTEMPT',job_id=attempt.job_id,attempt_id=attempt.attempt_id,
            worker_id=attempt.worker_id,quota_class=attempt.quota_class,actor='supervisor',command_id=command,payload=payload)
    peer.require_control_memory_intent(intent)
    receipt=_exchange(intent,'acquire',{'delegation':delegation})
    if receipt['phase']!='ADMITTED' or receipt['profile_sha256']!=hashlib.sha256(profile.canonical(value)).hexdigest():
        raise peer.ProtectedMemoryRefused()
    cap=object.__new__(EconomicAdmission)
    selector={k:receipt[k] for k in ('root','parent','run_id','pre_input_sha256','profile_sha256')}
    _ISSUED[cap]=_State(intent,wire.canonical(selector),receipt['lease_id'],os.getpid())
    return cap


def recover(intent, qualified_profile, claim, observed):
    value=profile.require_protected_memory_profile(qualified_profile,claim,observed)
    projection,actual=issuer._event_context(intent)
    command='memory-case:'+actual.lease.attempt.attempt_id+':economic-admission'
    with actual.runtime.store.transaction() as con:
        rows=con.execute('SELECT payload_json FROM events WHERE command_id=?',(command,)).fetchall()
    if len(rows)!=1:raise peer.ProtectedMemoryRefused()
    import json
    original=json.loads(rows[0]['payload_json'])
    if (original.get('pre_input')!=projection
            or original.get('profile_sha256')!=hashlib.sha256(profile.canonical(value)).hexdigest()):
        raise peer.ProtectedMemoryRefused()
    receipt=_exchange(intent,'current',{})
    if receipt['phase'] not in ('RESERVED','BOUND'):
        raise issuer.NativeCaseUnknown()
    if receipt['profile_sha256']!=hashlib.sha256(profile.canonical(value)).hexdigest():raise peer.ProtectedMemoryRefused()
    cap=object.__new__(EconomicAdmission)
    selector={k:receipt[k] for k in ('root','parent','run_id','pre_input_sha256','profile_sha256')}
    _ISSUED[cap]=_State(intent,wire.canonical(selector),receipt['lease_id'],os.getpid())
    return cap


def require(value, intent, action='current', arguments=None):
    if type(value) is not EconomicAdmission or value not in _ISSUED:raise peer.ProtectedMemoryRefused()
    state=_ISSUED[value]
    if state.intent is not intent or state.pid!=os.getpid():raise peer.ProtectedMemoryRefused()
    receipt=_exchange(intent,action,{} if arguments is None else arguments,evaluation=state.evaluation)
    selector={k:receipt[k] for k in ('root','parent','run_id','pre_input_sha256','profile_sha256')}
    if wire.canonical(selector)!=state.selector or receipt['lease_id']!=state.lease_id:
        raise peer.ProtectedMemoryRefused()
    return receipt

def acquire_evaluation(prepared, intent):
    """Existing original bearer/allowance law, after genuine evaluator admission.

    The new purpose never creates an allowance, root, account or free reservation.
    The fixed root receiver independently qualifies the new source purpose.
    """
    from control_plane import protected_memory_evaluation_assignment as assignments
    from control_plane import protected_memory_evaluation_source as evaluation_source
    from control_plane.protected_memory_delegation import NAME, _shape
    from control_plane.paid_fabric_backend import _private_read
    state=assignments.current_prepared(prepared)
    value=state['observed']['profile']
    projection,actual=issuer._event_context(intent)
    if state['claim'] is not peer._CONTROL_ISSUED[intent].claim: raise peer.ProtectedMemoryRefused()
    locator=assignments.native_locator(state)
    directory=state['runtime'].store.root/'data/control_plane/runs'/state['lease'].attempt.attempt_id
    from control_plane.protected_memory_execution import _private_directory
    _private_directory(directory)
    raw=_private_read(directory/NAME,8192)
    secret=_shape(wire.parse(raw,8192),locator,value)
    attempt=state['lease'].attempt
    with state['runtime'].store.read() as con:
        rows=con.execute('SELECT payload_json FROM events WHERE event_type=? AND command_id=?',
            ('MEMORY_ECONOMIC_DELEGATION_RETAINED','memory-case:'+attempt.attempt_id+':economic-delegation')).fetchall()
    expected={'schema':'mastermind.memory_economic_delegation_retained.v1','operation_id':locator['operation_id'],
        'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
    if len(rows)!=1 or __import__('json').loads(rows[0]['payload_json'])!=expected: raise peer.ProtectedMemoryRefused()
    payload={'schema':'mastermind.memory_economic_admission_attempt.v1','operation_id':projection['original_operation_id'],
        'pre_input_sha256':hashlib.sha256(peer.canonical(projection)).hexdigest(),'pre_input':projection,
        'profile_sha256':hashlib.sha256(profile.canonical(value)).hexdigest()}
    command='memory-case:'+attempt.attempt_id+':economic-admission'
    with state['runtime'].store.transaction() as con:
        if con.execute('SELECT 1 FROM events WHERE command_id=?',(command,)).fetchone(): raise issuer.NativeCaseUnknown()
        state['runtime'].store.append_event(con,aggregate_type='attempt',aggregate_id=attempt.attempt_id,
            event_type='MEMORY_ECONOMIC_ADMISSION_ATTEMPT',job_id=attempt.job_id,attempt_id=attempt.attempt_id,
            worker_id=attempt.worker_id,quota_class=attempt.quota_class,actor='supervisor',command_id=command,payload=payload)
    receipt=_exchange(intent,'acquire',{ 'delegation':{k:secret[k] for k in ('token','task_class','task_complexity','model')}},evaluation=prepared)
    if receipt['phase']!='ADMITTED' or receipt['profile_sha256']!=payload['profile_sha256']: raise peer.ProtectedMemoryRefused()
    cap=object.__new__(EconomicAdmission)
    selector={k:receipt[k] for k in ('root','parent','run_id','pre_input_sha256','profile_sha256')}
    _ISSUED[cap]=_State(intent,wire.canonical(selector),receipt['lease_id'],os.getpid(),prepared)
    return cap
