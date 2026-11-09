"""One original admitted evaluation through incumbent private process/FD custody.

No scheduler, new allowance, public packet ingress or provider fallback. The
existing Runtime claim, original economic delegation and installed model
profile remain required. Failure after launch/write preserves UNKNOWN.
"""
from __future__ import annotations
import base64
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import weakref
from datetime import datetime, timezone
from common import memory_evaluation_contract as c
from common import memory_native_wire as w
from common.protected_memory_model_input import compile_memory_model_input
from control_plane import protected_memory_evaluation_assignment as assignment
from control_plane import protected_memory_evaluation_source as source
from control_plane import protected_memory_annotations as annotations
from control_plane import protected_memory_execution as incumbent
from control_plane import protected_memory_economic_client as economic
from control_plane import protected_memory_peer as peer
from control_plane import memory_native_issuer as issuer
from control_plane.worker_execution_contract import WorkerProcessRef
from control_plane.codex_worker import ProcessInspector

_RUNS=weakref.WeakKeyDictionary()

def _source_binary():
    binary=incumbent._source_binary()
    from control_plane.paid_fabric_backend import _root_source
    root=Path(__file__).resolve().parents[1]
    manifest=json.loads(_root_source(root/'.executive-release-manifest.json'))
    entries={r['path']:r for r in manifest['entries']}
    for name in ('control_plane/protected_memory_evaluation_execution.py',
            'control_plane/protected_memory_evaluation_assignment.py','control_plane/protected_memory_evaluation_source.py',
            'control_plane/protected_memory_annotations.py','common/memory_evaluation_contract.py',
            'common/memory_evaluation_ratings.py','common/memory_evaluation_guide.md'):
        raw=_root_source(root/name);row=entries.get(name)
        if row is None or row['sha256']!=hashlib.sha256(raw).hexdigest() or row['size']!=len(raw):c.fail()
    return binary

def _retain(path, raw):
    from control_plane.paid_fabric_backend import _private_read
    incumbent._private_directory(path.parent)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        pending=memoryview(raw)
        while pending:
            n=os.write(fd,pending)
            if n<=0:c.fail()
            pending=pending[n:]
        os.fsync(fd)
    finally:os.close(fd)
    if _private_read(path,65536)!=raw:c.fail()

def retain_evaluation_economic_delegation(prepared, token, *, task_class, task_complexity):
    """Original parent supplies its existing bearer to the existing private slot.

    This does not issue/renew/validate a budget. The incumbent root/helper must
    later authenticate and consume that exact root/operator delegation itself.
    """
    from control_plane.protected_memory_delegation import NAME,SCHEMA,_shape
    state=assignment.current_prepared(prepared)
    state['supervisor']._effective_grant(state['runtime'].jobs.get_job(state['lease'].attempt.job_id),state['lease'].attempt)
    locator=assignment.native_locator(state); selected=state['observed']['profile']
    value=_shape(dict(schema=SCHEMA,operation_id=locator['operation_id'],**locator['intent'],
        profile_sha256=c.digest(selected),model=selected['model'],task_class=task_class,task_complexity=task_complexity,token=token),locator,selected)
    directory=state['runtime'].store.root/'data/control_plane/runs'/state['lease'].attempt.attempt_id
    raw=w.canonical(value);_retain(directory/NAME,raw)
    receipt=dict(schema='mastermind.memory_economic_delegation_retained.v1',operation_id=locator['operation_id'],sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
    assignment.retain_event(state['runtime'],'MEMORY_ECONOMIC_DELEGATION_RETAINED',
        'memory-case:'+state['lease'].attempt.attempt_id+':economic-delegation',receipt,attempt=state['lease'].attempt)
    assignment.current_prepared(prepared)
    return receipt

def start_registered_evaluation(prepared, *, pair=None):
    state=assignment.current_prepared(prepared)
    if prepared in _RUNS:c.fail()
    runtime=state['runtime'];lease=state['lease'];attempt=lease.attempt
    directory=runtime.store.root/'data/control_plane/runs'/attempt.attempt_id
    incumbent._private_directory(directory)
    intent=peer.capture_control_memory_intent(state['claim'],state['context'][4])
    packet=annotations.input_packet(prepared,pair=pair)
    selected=state['observed']['profile']
    body=compile_memory_model_input(packet,model=selected['model'])
    binary=_source_binary()
    # Qualify exact input size/grammar and installed executable before any new
    # economic reservation. Existing retained subject reads have their own grant.
    paid=economic.acquire_evaluation(prepared,intent)
    economic.require(paid,intent)
    _retain(directory/'memory-evaluation-input',packet)
    seal=dict(schema='mastermind.protected_memory_evaluation_start.v1',assignment=annotations.assignment_material(state),
        input_sha256=hashlib.sha256(packet).hexdigest(),input_bytes=len(packet),profile_sha256=c.digest(selected),body_sha256=hashlib.sha256(body).hexdigest())
    economic.require(paid,intent,'bind_input',{k:seal[k] for k in ('input_sha256','input_bytes','body_sha256')})
    current=runtime.attempts.get_attempt(attempt.attempt_id)
    pinned=runtime.attempts.pin_remote_launch_identity(current.attempt_id,fence_generation=current.fence_generation,
        lease_token=lease.lease_token,expected_version=current.version,identity_digest=c.digest(seal))
    assignment.retain_event(runtime,'MEMORY_EVALUATION_LAUNCH_ATTEMPT',annotations._command(attempt.attempt_id,'launch'),seal,attempt=attempt)
    fds=[];parent=child=None
    try:
        output=directory/'memory-evaluation-result';diagnostic=directory/'memory-evaluation-diagnostic'
        for path in (output,diagnostic):fds.append(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600))
        parent,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
        assignment.current_prepared(prepared)
        proc=subprocess.Popen([binary.real_path,'-I','-B',str(incumbent.RUNNER),str(child.fileno())],
            stdin=subprocess.DEVNULL,stdout=fds[0],stderr=fds[1],close_fds=True,pass_fds=(child.fileno(),),start_new_session=True,
            env={'PATH':'/usr/bin:/bin','HOME':'/var/empty','LANG':'C','PYTHONDONTWRITEBYTECODE':'1'})
        _RUNS[prepared]=dict(proc=proc,pair=pair,paid=paid,intent=intent,ref=None,settled=False)
        child.close();child=None;parent.settimeout(10)
        if parent.recv(6)!=b'READY\n':raise incumbent.MemoryExecutionUnknown()
        inspector=ProcessInspector();observed=inspector.inspect(proc.pid)
        if observed.effective_uid!=450 or observed.real_uid!=450:c.fail()
        ref=WorkerProcessRef(run_id=attempt.attempt_id,pid=proc.pid,pgid=observed.pgid,process_start_identity=observed.start_identity,
            boot_session_id=inspector.boot_session_id(),launch_nonce=seal['body_sha256'],provider_session_id=None,
            stdout_path=str(output),stderr_path=str(diagnostic),result_path=str(output),started_at=datetime.now(timezone.utc).isoformat(),
            binary=binary,base_sha=Path(__file__).resolve().parents[1].name,session_id=observed.session_id,
            effective_uid=observed.effective_uid,effective_gid=observed.effective_gid,real_uid=observed.real_uid,real_gid=observed.real_gid)
        runtime.attempts.validate_pinned_remote_launch(pinned,lease_token=lease.lease_token)
        runtime.attempts.record_process(attempt.attempt_id,fence_generation=current.fence_generation,lease_token=lease.lease_token,
            pid=ref.pid,pgid=ref.pgid,process_start_identity=ref.process_start_identity,boot_id=ref.boot_session_id,
            stdout_path=ref.stdout_path,stderr_path=ref.stderr_path,result_path=ref.result_path,launch_metadata={'memory_evaluation':seal})
        runtime.attempts.mark_running(attempt.attempt_id,fence_generation=current.fence_generation,lease_token=lease.lease_token)
        bound=assignment.bind_evaluation_execution(prepared,process=ref);_RUNS[prepared]['ref']=ref
        receipt=economic.require(paid,intent,'consume',{'attempt_id':ref.run_id,'process_ref_sha256':c.digest(dataclasses.asdict(ref))})
        if receipt['phase']!='CONSUMED':c.fail()
        exposure=annotations.begin_exposure(bound,packet,pair=pair)
        envelope=dict(schema='mastermind.protected_memory_evaluation_model_request.v1',profile_id=state['observed']['profile_id'],
            profile_sha256=seal['profile_sha256'],input_sha256=seal['input_sha256'],input_base64=base64.b64encode(packet).decode(),
            body_base64=base64.b64encode(body).decode())
        raw=w.canonical(envelope)
        annotations.final_fd_window(bound,exposure,packet,pair=pair)
        parent.sendall(len(raw).to_bytes(4,'big')+raw);parent.shutdown(socket.SHUT_WR)
        annotations.confirm_exposure(bound,exposure)
        return ref
    except Exception:
        # No kill, replay, replacement or refund. Original Runtime/process/
        # exposure-attempt/economic rows remain authoritative and unresolved.
        raise incumbent.MemoryExecutionUnknown() from None
    finally:
        for fd in fds:os.close(fd)
        if parent is not None:parent.close()
        if child is not None:child.close()

def completed_process(prepared):
    state=assignment._exact_cap(assignment._PREPARED,prepared,assignment.PreparedEvaluationAssignment)
    run=_RUNS.get(prepared)
    if run is None or run['ref'] is None or run['proc'].poll()!=0: c.fail()
    current=state['runtime'].attempts.get_attempt(state['lease'].attempt.attempt_id)
    ref=run['ref']
    if (current is None or current.pid!=ref.pid or current.process_start_identity!=ref.process_start_identity
            or current.boot_id!=ref.boot_session_id or current.result_path!=ref.result_path):c.fail()
    return run

def collect_registered_evaluation(prepared):
    run=completed_process(prepared)
    from control_plane.paid_fabric_backend import _private_read
    raw=_private_read(Path(run['ref'].result_path),65536)
    if not run['settled']:
        economic.require(run['paid'],run['intent'],'settle',{'rc':0,'result_sha256':hashlib.sha256(raw).hexdigest(),'result_bytes':len(raw)})
        run['settled']=True
    return annotations.collect_annotation(prepared,pair=run['pair'])

async def run_registered_evaluation(supervisor,lease):
    """Selected only by a real normalized new intent, before any reservation."""
    from control_plane import protected_memory_original as originals
    job=supervisor.runtime.jobs.get_job(lease.attempt.job_id)
    selector=c.evaluation_intent(job.constraints.get('native_memory_evaluation'))
    reference=originals.completed_original_reference(supervisor.runtime,selector['subject_attempt_id'])
    # The source-installed, current role is derived from the retained Job.
    # Adjudicator pair must already have been sealed in original registered
    # reviewer order; never accept request-supplied rating/pair bodies.
    pair=None
    if selector['participant_slot']=='adjudicator':
        with supervisor.runtime.store.read() as con:
            rows=con.execute("SELECT payload_json FROM events WHERE event_type='MEMORY_ANNOTATION_PAIR_RETAINED' AND job_id=?",(job.root_job_id,)).fetchall()
        matches=[json.loads(r['payload_json']) for r in rows if json.loads(r['payload_json'])['subject']['attempt_id']==selector['subject_attempt_id']]
        if len(matches)!=1:c.fail()
        ids=[r['assignment']['attempt_id'] for r in matches[0]['annotation_receipts']]
        pair=annotations.capture_retained_annotation_pair(supervisor,original_attempt_id=selector['subject_attempt_id'],reviewer_attempt_ids=ids)
    import asyncio
    async def attended(call):
        task=asyncio.create_task(asyncio.to_thread(call));lost=False
        while not task.done():
            done,_=await asyncio.wait({task},timeout=min(5.0,supervisor.runtime.store.lease_seconds/3))
            if done:break
            try:
                supervisor.runtime.attempts.heartbeat_attempt(lease.attempt.attempt_id,fence_generation=lease.attempt.fence_generation,lease_token=lease.lease_token)
            except Exception:lost=True
        result=task.result()
        if lost:raise incumbent.MemoryExecutionRefused()
        return result
    prepared=await attended(lambda:assignment.prepare_registered_evaluation(supervisor,original_reference=reference,original_attempt_lease=lease))
    await attended(lambda:start_registered_evaluation(prepared,pair=pair))
    proc=_RUNS[prepared]['proc']
    deadline=time.monotonic()+600;heartbeat=0
    while proc.poll() is None:
        if time.monotonic()>=deadline:raise incumbent.MemoryExecutionUnknown()
        if time.monotonic()>=heartbeat:
            supervisor.runtime.attempts.heartbeat_attempt(lease.attempt.attempt_id,fence_generation=lease.attempt.fence_generation,lease_token=lease.lease_token)
            await attended(lambda:economic.require(_RUNS[prepared]['paid'],_RUNS[prepared]['intent'],'heartbeat'))
            heartbeat=time.monotonic()+5
        await asyncio.sleep(0.1)
    if proc.returncode!=0:raise incumbent.MemoryExecutionUnknown()
    receipt=await attended(lambda:collect_registered_evaluation(prepared))
    from control_plane.executive_runtime import JobPayload
    supervisor._effective_grant(job,lease.attempt)
    supervisor.runtime.attempts.complete_attempt(lease.attempt.attempt_id,fence_generation=lease.attempt.fence_generation,lease_token=lease.lease_token,
        payload=JobPayload(summary='Original protected evaluation retained; no scientific admission',
            completed_steps=['Original protected annotation retained'],current_state='Protected retained evaluation',next_actions=[]))
    return receipt
