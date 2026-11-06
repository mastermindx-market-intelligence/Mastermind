"""Control450 nominal facade for the fixed root-confined Linux issuer exchange.

Only the existing current Control/Runtime owner can compose this. Capability
possession never replaces current Runtime, protected peer, enrollment or Linux
recipient/source checks. No packet reaches ordinary UID501 Fabric channels.
"""
from __future__ import annotations
import hashlib
import json
import os
import time
import weakref
from dataclasses import dataclass, replace

from common import memory_native_wire as wire
from control_plane import protected_memory_peer as peer
from control_plane import native_memory_admission as admission
from control_plane.executive_memory_issuer import SCHEMA

_ISSUED = weakref.WeakKeyDictionary()

class NativeCaseRefused(ValueError):
    def __init__(self): super().__init__('native_memory_case_unavailable')

class NativeCaseUnknown(ValueError):
    def __init__(self): super().__init__('native_memory_original_case_unknown')

class NativeCaseCapability:
    __slots__ = ('__weakref__',)
    def __new__(cls): raise NativeCaseRefused()
    def __repr__(self): return '<NativeCaseCapability private>'

@dataclass(frozen=True)
class _State:
    intent: peer.ControlMemoryIntent
    issuer: bytes
    locator: bytes
    input_sha256: str
    pid: int
    recipient: bytes|None=None


def _send(payload):
    from control_plane.executive_privileged_client import _send_one_frame, DEFAULT_SOCKET
    return _send_one_frame(payload, socket_path=DEFAULT_SOCKET, timeout_seconds=125,
        require_root_peer=True, deadline_monotonic_ns=time.monotonic_ns()+125_000_000_000)


def describe_control_owner():
    """Observation-only metadata; not source or provider admission."""
    if os.geteuid() != 450: raise NativeCaseRefused()
    response = _send({'schema':SCHEMA,'operation':'describe'})
    wire.exact(response,'schema state owner')
    if response['schema'] != SCHEMA or response['state'] != 'OWNER_CURRENT': raise NativeCaseRefused()
    return peer._owner_shape(response['owner'])


def qualify_transport(intent):
    """Fixed local installed metadata only; NOT Linux permission/read/auth."""
    before=peer.require_control_memory_intent(intent)
    response=_send({'schema':SCHEMA,'operation':'qualify_transport','projection':before})
    if peer.require_control_memory_intent(intent)!=before:raise NativeCaseRefused()
    if response!={'schema':SCHEMA,'state':'TRANSPORT_CONFIGURED','protocol':'memory.e0.native_issuer.v3'}:
        raise NativeCaseRefused()


def _request(intent, action, *, version='v2', **extra):
    projection = peer.require_control_memory_intent(intent)
    digest = hashlib.sha256(peer.canonical(projection)).hexdigest()
    return projection, wire.validate_request({'schema':'research_factory.market_memory_e0_native_issuer_request.'+version,
        'action':action,'operation_id':projection['original_operation_id'],
        'intent':dict(projection['native_source_locator'],participant_binding_sha256=digest), **extra})


def _exchange(intent, request):
    before = peer.require_control_memory_intent(intent)
    try: response = _send({'schema':SCHEMA,'operation':'exchange','projection':before,'request':request})
    except Exception: raise NativeCaseUnknown() from None
    if peer.require_control_memory_intent(intent) != before: raise NativeCaseRefused()
    if type(response) is not dict or response.get('schema') != SCHEMA: raise NativeCaseUnknown()
    if response.get('state') == 'ORIGINAL_EXCHANGE_UNKNOWN': raise NativeCaseUnknown()
    if response.get('state') != 'EXCHANGED': raise NativeCaseRefused()
    wire.exact(response, 'schema state response')
    parsed = wire.validate_response(response['response'],request=request)
    if parsed['status'] in ('REFUSED','ORIGINAL_OPERATION_PENDING'): raise NativeCaseRefused()
    return parsed


def _event_context(intent):
    projection = peer.require_control_memory_intent(intent)
    state = peer._CONTROL_ISSUED[intent]
    claim = admission._ISSUED[state.claim]
    return projection, claim


def _prepare_attempt(intent,version='v2'):
    projection, claim = _event_context(intent)
    attempt = claim.lease.attempt
    command = 'memory-case:'+attempt.attempt_id+':prepare'
    safe = {'schema':'mastermind.memory_prepare_attempt.v1',
        'operation_id':projection['original_operation_id'],
        'pre_input_sha256':hashlib.sha256(peer.canonical(projection)).hexdigest()}
    if version=='v3':safe.update(schema='mastermind.memory_prepare_attempt.v2',wire_version='v3')
    elif version!='v2':raise NativeCaseRefused()
    with claim.runtime.store.transaction() as con:
        prior = con.execute('SELECT event_id,payload_json FROM events WHERE command_id=? LIMIT 2',(command,)).fetchall()
        if prior: raise NativeCaseUnknown()
        claim.runtime.store.append_event(con, aggregate_type='attempt', aggregate_id=attempt.attempt_id,
            event_type='MEMORY_PREPARE_ATTEMPT', job_id=attempt.job_id, attempt_id=attempt.attempt_id,
            worker_id=attempt.worker_id, quota_class=attempt.quota_class, actor='supervisor',
            command_id=command, payload=safe)
    # Committed attempt precedes any source exchange. Every interruption from
    # this point retains UNKNOWN; only read_original_case may recover it.
    peer.require_control_memory_intent(intent)


def _issue(intent, response):
    if 'input' not in response: raise NativeCaseRefused()
    packet = wire.packet(response['input'],response['locator'])
    cap = object.__new__(NativeCaseCapability)
    _ISSUED[cap] = _State(intent,wire.canonical(response['issuer']),wire.canonical(response['locator']),
        hashlib.sha256(packet).hexdigest(),os.getpid())
    return cap


def prepare_case(intent,*,version='v2'):
    _prepare_attempt(intent,version)
    _, request = _request(intent,'prepare_case',version=version)
    return _issue(intent,_exchange(intent,request))


def read_original_case(intent):
    """Read/reopen same original only. ABSENT/PENDING never retry preparation."""
    projection, claim = _event_context(intent)
    command='memory-case:'+claim.lease.attempt.attempt_id+':prepare'
    with claim.runtime.store.read() as con:
        rows=con.execute('SELECT payload_json FROM events WHERE command_id=? LIMIT 2',(command,)).fetchall()
    if len(rows)!=1: raise NativeCaseRefused()
    expected={'schema':'mastermind.memory_prepare_attempt.v1','operation_id':projection['original_operation_id'],
        'pre_input_sha256':hashlib.sha256(peer.canonical(projection)).hexdigest()}
    actual=json.loads(rows[0]['payload_json']);version='v2'
    if actual.get('schema')=='mastermind.memory_prepare_attempt.v2':
        expected.update(schema='mastermind.memory_prepare_attempt.v2',wire_version='v3');version='v3'
    if actual!=expected: raise NativeCaseRefused()
    _,request=_request(intent,'read_original_case',version=version)
    response=_exchange(intent,request)
    if response['operation_state']!='COMPLETE': return response['operation_state'],None
    return 'COMPLETE',_issue(intent,response)


def _current(capability, intent):
    if (type(capability) is not NativeCaseCapability or capability not in _ISSUED
            or type(intent) is not peer.ControlMemoryIntent): raise NativeCaseRefused()
    state=_ISSUED[capability]
    if state.pid!=os.getpid() or state.intent is not intent: raise NativeCaseRefused()
    peer.require_control_memory_intent(intent)
    return state


def _same_source(state, response):
    before=json.loads(state.issuer);after=response['issuer']
    # Access continuation can advance only when actual Linux current owner
    # qualifies it. Original source/installation/registration remain immutable.
    mutable=({'current_selection_sha256','current_access_ref'} if before['protocol']=='memory.e0.native_issuer.v3'
             else {'current_access_ref','recipient_grant_ref'})
    keys=set(before)-mutable
    if any(before[k]!=after[k] for k in keys) or wire.canonical(response['locator'])!=state.locator:
        raise NativeCaseRefused()


def current_input(capability,intent):
    state=_current(capability,intent)
    _,request=_request(intent,'current_input',version=json.loads(state.issuer)['protocol'][-2:],locator=json.loads(state.locator))
    response=_exchange(intent,request);_same_source(state,response)
    raw=wire.packet(response['input'],response['locator'])
    if hashlib.sha256(raw).hexdigest()!=state.input_sha256: raise NativeCaseRefused()
    _current(capability,intent)
    return raw


def authorize_result_disclosure(capability,intent,original_attempt,original_input_digest,retained_result_digest):
    # These values are supplied ONLY by the same protected execution owner.
    # Public callers never select a result_ref or acquire this nominal handle.
    state=_current(capability,intent)
    _, claim = _event_context(intent)
    if original_attempt != claim.lease.attempt.attempt_id:
        raise NativeCaseRefused()
    if original_input_digest!=state.input_sha256 or type(retained_result_digest) is not dict:
        raise NativeCaseRefused()
    wire.exact(retained_result_digest,'sha256 bytes')
    reference={'attempt_id':original_attempt,'input_sha256':original_input_digest,
        'result_sha256':retained_result_digest['sha256'],'result_bytes':retained_result_digest['bytes']}
    _,request=_request(intent,'authorize_result_disclosure',version=json.loads(state.issuer)['protocol'][-2:],locator=json.loads(state.locator),result_ref=reference)
    response=_exchange(intent,request);_same_source(state,response);_current(capability,intent)
    if request['schema'].endswith('.v3'):
        fact=wire.canonical(response['authorization']['original_recipient'])
        if state.recipient is not None and state.recipient!=fact:raise NativeCaseRefused()
        if state.recipient is None:_ISSUED[capability]=replace(state,recipient=fact)
    return response['authorization']
