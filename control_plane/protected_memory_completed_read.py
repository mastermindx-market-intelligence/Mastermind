"""Distinct current SERVICE read capability; no active lease/start/prepare API."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import os
import time
import weakref
from common import memory_native_wire as wire
from control_plane import protected_memory_original as original
from control_plane import memory_native_issuer as issuer
from control_plane import protected_memory_profile as profile
from control_plane import protected_memory_result_access as access

_ISSUED=weakref.WeakKeyDictionary()

class CompletedReadRefused(ValueError):
    def __init__(self):super().__init__('protected_memory_completed_read_unavailable')

class CompletedMemoryRead:
    __slots__=('__weakref__',)
    def __new__(cls):raise CompletedReadRefused()
    def __repr__(self):return '<CompletedMemoryRead service-scoped; read only>'

@dataclass(frozen=True)
class _State:
    reference:object
    material:bytes
    owner:bytes
    pid:int

def _permission(material,owner):
    if os.geteuid()!=450:raise CompletedReadRefused()
    process=os.getpid()
    if issuer.describe_control_owner()!=owner:raise CompletedReadRefused()
    raw=profile._read_config()
    if hashlib.sha256(raw).hexdigest()!=owner['configuration_sha256']:raise CompletedReadRefused()
    config=profile._json(raw)
    if config.get('runtime_root')!=material['namespace']:raise CompletedReadRefused()
    policy=access.validate_access_document(config.get('memory_original_result_access'))
    result=issuer._send({'schema':issuer.SCHEMA,'operation':'completed_result','material':material})
    wire.exact(result,'schema state receipt')
    if result['schema']!=issuer.SCHEMA or result['state']!='COMPLETED_READ_CURRENT':raise CompletedReadRefused()
    expected={'schema':'mastermind.memory_completed_service_read_current.v1',
        'reference_sha256':hashlib.sha256(wire.canonical(material['reference'])).hexdigest(),
        'owner':owner,'receiver_kind':'native_broker_service','retry_authorized':False}
    if result['receipt']!=expected or issuer.describe_control_owner()!=owner:raise CompletedReadRefused()
    # No blocking read/probe follows this exact validated local window check.
    # The owner/config digest above binds these policy facts to this service.
    if (os.geteuid()!=450 or os.getpid()!=process
            or not policy['not_before_seconds']<=time.time()<policy['expires_at_seconds']):
        raise CompletedReadRefused()

def _runtime_read_permission(reference):
    held=original._REFERENCES[reference]
    job=held.runtime.jobs.get_job(original.current_reference(reference)['job_id'])
    if job is None:raise CompletedReadRefused()
    from control_plane.executive_authority import ExecutiveAuthorityPolicy
    # Current global READ policy is a further conjunct, not the original
    # active lease or a retroactive comparison to its historical policy hash.
    ExecutiveAuthorityPolicy.load().authorize(['READ'],worktree=job.worktree,
        allowed_write_paths=[],validation_commands=[])

def capture_completed_memory_read(supervisor,attempt_id):
    from control_plane.executive_supervisor import ExecutiveSupervisor
    if type(supervisor) is not ExecutiveSupervisor or os.geteuid()!=450:raise CompletedReadRefused()
    owner=issuer.describe_control_owner()
    raw=profile._read_config();config=profile._json(raw)
    if (hashlib.sha256(raw).hexdigest()!=owner['configuration_sha256']
            or config.get('runtime_root')!=str(supervisor.runtime.store.root)):raise CompletedReadRefused()
    access.validate_access_document(config.get('memory_original_result_access'))
    reference=original.completed_original_reference(supervisor.runtime,attempt_id)
    ref=original.current_reference(reference);held=original._REFERENCES[reference]
    if (ref['schema']!='mastermind.memory_completed_original_reference.v2' or held.case is None
            or ref['original_recipient']=='UNRECORDED'):raise CompletedReadRefused()
    material={'namespace':str(supervisor.runtime.store.root),'reference':ref,
        'pre_input':json.loads(held.pre_input),'case':json.loads(held.case)}
    _runtime_read_permission(reference);_permission(material,owner)
    value=object.__new__(CompletedMemoryRead)
    _ISSUED[value]=_State(reference,wire.canonical(material),wire.canonical(owner),os.getpid())
    return value

def read_completed_memory_result(capability):
    if type(capability) is not CompletedMemoryRead or capability not in _ISSUED:raise CompletedReadRefused()
    state=_ISSUED[capability]
    if state.pid!=os.getpid():raise CompletedReadRefused()
    material=json.loads(state.material);owner=json.loads(state.owner)
    if original.current_reference(state.reference)!=material['reference']:raise CompletedReadRefused()
    _runtime_read_permission(state.reference)
    _permission(material,owner)
    held=original._REFERENCES[state.reference]
    directory=held.runtime.store.root/'data/control_plane/runs'/held.attempt_id
    from control_plane.protected_memory_execution import _private_directory
    from control_plane.paid_fabric_backend import _private_read
    _private_directory(directory)
    packet=_private_read(directory/'memory-original-input',65536)
    result=_private_read(directory/'memory-original-result',65536)
    ref=material['reference']
    if any(hashlib.sha256(raw).hexdigest()!=ref[k+'_sha256'] or len(raw)!=ref[k+'_bytes']
           for raw,k in ((packet,'input'),(result,'result'))):raise CompletedReadRefused()
    from common.memory_participant_view import project_original_result
    view=project_original_result(packet,result,attempt_id=held.attempt_id)
    _runtime_read_permission(state.reference);_permission(material,owner)
    if (original.current_reference(state.reference)!=ref or _private_read(directory/'memory-original-input',65536)!=packet
            or _private_read(directory/'memory-original-result',65536)!=result):raise CompletedReadRefused()
    # All potentially blocking receipt/body reads precede the final current
    # authorization. A same-byte reread cannot preserve a withdrawn view.
    _runtime_read_permission(state.reference);_permission(material,owner)
    return view
