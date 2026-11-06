"""Original economic bearer retained only by the existing private Attempt owner.

This is an UNVERIFIED delegation until the actual incumbent OperatorOwner checks
its original grant, expiry, scope and counts. It is never Linux/source authority.
No token appears in Events, public returns, provider input, logs or command argv.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
from pathlib import Path
from common import memory_native_wire as wire
from control_plane import native_memory_admission as admission
from control_plane import memory_native_issuer as issuer
from control_plane import protected_memory_profile as profile

NAME='memory-original-economic-delegation'
SCHEMA='mastermind.memory_original_economic_delegation.v1'

def _context(runtime,lease):
    claim=admission.capture_memory_runtime_claim(runtime,lease)
    observed=issuer.describe_control_owner()
    qualified=profile.load_protected_memory_profile(claim,observed)
    selected=profile.require_protected_memory_profile(qualified,claim,observed)
    locator=admission.require_memory_runtime_claim(claim)
    directory=runtime.store.root/'data/control_plane/runs'/lease.attempt.attempt_id
    from control_plane.protected_memory_execution import _private_directory
    _private_directory(directory)
    return claim,observed,selected,locator,directory

def _shape(value,locator,selected):
    wire.exact(value,'schema operation_id study_id root_id operator_run_id child_run_id profile_sha256 model task_class task_complexity token')
    if (value['schema']!=SCHEMA or value['operation_id']!=locator['operation_id']
            or any(value[k]!=v for k,v in locator['intent'].items())
            or value['profile_sha256']!=hashlib.sha256(profile.canonical(selected)).hexdigest()
            or value['model']!=selected['model']
            or value['task_class'] not in ('mechanical','extract','fix_build','census','audit','build')
            or value['task_complexity'] not in ('C0_MECHANICAL','C1_ROUTINE_BOUNDED')
            or type(value['token']) is not str or re.fullmatch('[0-9a-f]{64}',value['token']) is None):
        raise admission.MemoryAdmissionRefused()
    return json.loads(wire.canonical(value))

def retain_original_economic_delegation(supervisor,lease,token,*,task_class,task_complexity):
    """Internal original-parent handoff, NOT a public auth/grant issuer."""
    from control_plane.executive_supervisor import ExecutiveSupervisor
    from control_plane.executive_runtime import AttemptLease
    if type(supervisor) is not ExecutiveSupervisor or type(lease) is not AttemptLease:
        raise admission.MemoryAdmissionRefused()
    runtime=supervisor.runtime
    supervisor._effective_grant(runtime.jobs.get_job(lease.attempt.job_id),lease.attempt)
    claim,observed,selected,locator,directory=_context(runtime,lease)
    value=_shape(dict(schema=SCHEMA,operation_id=locator['operation_id'],**locator['intent'],
        profile_sha256=hashlib.sha256(profile.canonical(selected)).hexdigest(),model=selected['model'],
        task_class=task_class,task_complexity=task_complexity,token=token),locator,selected)
    raw=wire.canonical(value);path=directory/NAME
    try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    except FileExistsError:fd=None
    if fd is not None:
        try:
            pending=memoryview(raw)
            while pending:
                count=os.write(fd,pending)
                if count<=0:raise admission.MemoryAdmissionRefused()
                pending=pending[count:]
            os.fsync(fd)
        finally:os.close(fd)
    from control_plane.paid_fabric_backend import _private_read
    if _private_read(path,8192)!=raw:raise admission.MemoryAdmissionRefused()
    admission.require_memory_runtime_claim(claim)
    if issuer.describe_control_owner()!=observed:raise admission.MemoryAdmissionRefused()
    # Safe immutable receipt only; the bearer stays solely in the private file.
    payload={'schema':'mastermind.memory_economic_delegation_retained.v1',
        'operation_id':locator['operation_id'],'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
    command='memory-case:'+lease.attempt.attempt_id+':economic-delegation'
    with runtime.store.transaction() as con:
        rows=con.execute('SELECT payload_json FROM events WHERE command_id=?',(command,)).fetchall()
        if rows:
            if len(rows)!=1 or json.loads(rows[0]['payload_json'])!=payload:raise admission.MemoryAdmissionRefused()
        else:
            runtime.store.append_event(con,aggregate_type='attempt',aggregate_id=lease.attempt.attempt_id,
                event_type='MEMORY_ECONOMIC_DELEGATION_RETAINED',job_id=lease.attempt.job_id,attempt_id=lease.attempt.attempt_id,
                worker_id=lease.attempt.worker_id,quota_class=lease.attempt.quota_class,actor='supervisor',command_id=command,payload=payload)
    return payload

def read_original_economic_delegation(claim,qualified,observed):
    locator=admission.require_memory_runtime_claim(claim)
    state=admission._ISSUED[claim]
    selected=profile.require_protected_memory_profile(qualified,claim,observed)
    directory=state.runtime.store.root/'data/control_plane/runs'/state.lease.attempt.attempt_id
    from control_plane.protected_memory_execution import _private_directory
    from control_plane.paid_fabric_backend import _private_read
    _private_directory(directory);raw=_private_read(directory/NAME,8192)
    value=_shape(wire.parse(raw,8192),locator,selected)
    command='memory-case:'+state.lease.attempt.attempt_id+':economic-delegation'
    with state.runtime.store.read() as con:
        rows=con.execute('SELECT payload_json FROM events WHERE command_id=?',(command,)).fetchall()
    expected={'schema':'mastermind.memory_economic_delegation_retained.v1','operation_id':locator['operation_id'],
        'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
    if len(rows)!=1 or json.loads(rows[0]['payload_json'])!=expected:raise admission.MemoryAdmissionRefused()
    admission.require_memory_runtime_claim(claim)
    if issuer.describe_control_owner()!=observed:raise admission.MemoryAdmissionRefused()
    return {k:value[k] for k in ('token','task_class','task_complexity','model')}
