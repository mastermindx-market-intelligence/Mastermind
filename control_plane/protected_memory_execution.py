"""Protected Memory execution mode inside incumbent Control/Runtime ownership.

No queue, lease broker, attempt registry or session lifecycle lives here. Runtime
claim/pin/process/Events remain the owner. One fixed subprocess carries one exact
model input; no UID501 shim, manual packet directory or generic result channel.
The installed protected profile must qualify BEFORE Linux preparation.
"""
from __future__ import annotations
import base64
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import selectors
import socket
import stat
import subprocess
import sys
import time
import weakref
from datetime import datetime, timezone

from common import memory_native_wire as wire
from common.protected_memory_model_input import compile_memory_model_input
from control_plane import native_memory_admission as admission
from control_plane import protected_memory_peer as peer
from control_plane import protected_memory_profile as profile
from control_plane import memory_native_issuer as issuer
from control_plane import protected_memory_economic_client as economic
from control_plane.worker_execution_contract import WorkerProcessRef,BinaryAttestation
from control_plane.codex_worker import ProcessInspector

RUNNER=Path(__file__).resolve().parents[1]/'scripts/protected_memory_model_runner.py'
_OWNED=weakref.WeakKeyDictionary()

class MemoryExecutionRefused(ValueError):
    def __init__(self):super().__init__('protected_memory_execution_unavailable')
class MemoryExecutionUnknown(ValueError):
    def __init__(self):super().__init__('protected_memory_original_execution_unknown')
class PreparedMemoryExecution:
    __slots__=('__weakref__',)
    def __new__(cls):raise MemoryExecutionRefused()
    def __repr__(self):return '<PreparedMemoryExecution private>'
@dataclasses.dataclass
class _State:
    runtime:object
    lease:object
    claim:object
    intent:object
    profile:object
    observed:dict
    case:object
    packet:bytes
    run_dir:Path
    original_projection:bytes
    economic:object=None
    proc:object=None
    ref:object=None
    raw:bytes|None=None
    accounted:bool=False


def _private_directory(path):
    # Source storage policy owns lexical location. Every ancestor is protected;
    # hostile UID501 cannot read private450 inputs/results or replace namespace.
    if not path.is_absolute() or '..' in path.parts:raise MemoryExecutionRefused()
    for item in (path,*path.parents):
        info=item.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0,450)
                or info.st_mode&0o022):raise MemoryExecutionRefused()
    info=path.lstat()
    if info.st_uid!=450 or stat.S_IMODE(info.st_mode)!=0o700:raise MemoryExecutionRefused()


def _source_binary():
    from control_plane.paid_fabric_backend import _root_source
    root=RUNNER.parents[1]
    manifest=json.loads(_root_source(root/'.executive-release-manifest.json'))
    if manifest.get('commit_sha')!=root.name:raise MemoryExecutionRefused()
    entries={r['path']:r for r in manifest['entries'] if type(r) is dict and 'path' in r}
    required=['scripts/protected_memory_model_runner.py','common/memory_native_wire.py',
        'common/protected_memory_model_input.py','control_plane/protected_memory_profile.py']
    for name in required:
        raw=_root_source(root/name);row=entries.get(name)
        if type(row) is not dict or row.get('sha256')!=hashlib.sha256(raw).hexdigest() or row.get('size')!=len(raw):raise MemoryExecutionRefused()
    executable=Path(sys.executable).resolve(strict=True)
    raw=_root_source(executable);info=executable.stat()
    return BinaryAttestation(path=str(executable),real_path=str(executable),version=sys.version.split()[0],
        sha256=hashlib.sha256(raw).hexdigest(),team_identifier=None,size=info.st_size,device=info.st_dev,
        inode=info.st_ino,mode=info.st_mode,uid=info.st_uid,gid=info.st_gid,mtime_ns=info.st_mtime_ns)


def _event(state,kind,payload):
    attempt=state.lease.attempt;command='memory-case:'+attempt.attempt_id+':'+kind.lower()
    with state.runtime.store.transaction() as con:
        old=con.execute('SELECT event_id FROM events WHERE command_id=? LIMIT 1',(command,)).fetchone()
        if old:raise MemoryExecutionUnknown()
        state.runtime.store.append_event(con,aggregate_type='attempt',aggregate_id=attempt.attempt_id,
            event_type='MEMORY_'+kind,job_id=attempt.job_id,attempt_id=attempt.attempt_id,
            worker_id=attempt.worker_id,quota_class=attempt.quota_class,actor='supervisor',command_id=command,payload=payload)


def _receipt_event(state,kind,payload):
    """One retained observation, immutable same-original duplicate read only."""
    attempt=state.lease.attempt;command='memory-case:'+attempt.attempt_id+':'+kind.lower()
    with state.runtime.store.transaction() as con:
        rows=con.execute('SELECT event_type,job_id,attempt_id,payload_json FROM events WHERE command_id=?',(command,)).fetchall()
        if rows:
            if (len(rows)!=1 or rows[0]['event_type']!='MEMORY_'+kind or rows[0]['job_id']!=attempt.job_id
                    or rows[0]['attempt_id']!=attempt.attempt_id or json.loads(rows[0]['payload_json'])!=payload):
                raise MemoryExecutionRefused()
            return
        state.runtime.store.append_event(con,aggregate_type='attempt',aggregate_id=attempt.attempt_id,
            event_type='MEMORY_'+kind,job_id=attempt.job_id,attempt_id=attempt.attempt_id,
            worker_id=attempt.worker_id,quota_class=attempt.quota_class,actor='supervisor',command_id=command,payload=payload)


def _retain_input(state):
    """Exact bytes in the incumbent private Attempt directory, never UID501."""
    path=state.run_dir/'memory-original-input'
    try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    except FileExistsError:fd=None
    if fd is not None:
        try:
            pending=memoryview(state.packet)
            while pending:
                count=os.write(fd,pending)
                if count<=0:raise MemoryExecutionUnknown()
                pending=pending[count:]
            os.fsync(fd)
        finally:os.close(fd)
    from control_plane.paid_fabric_backend import _private_read
    if _private_read(path,65536)!=state.packet:raise MemoryExecutionRefused()
    _receipt_event(state,'INPUT_RETAINED',{'schema':'mastermind.memory_original_input.v1',
        'attempt_id':state.lease.attempt.attempt_id,
        'pre_input_sha256':hashlib.sha256(state.original_projection).hexdigest(),
        'input_sha256':hashlib.sha256(state.packet).hexdigest(),'input_bytes':len(state.packet)})


def _retain_case_binding(state):
    held=issuer._current(state.case,state.intent)
    source=json.loads(held.issuer)
    if source['protocol']!='memory.e0.native_issuer.v3':return
    projection=peer.require_control_memory_intent(state.intent)
    _,request=issuer._request(state.intent,'current_input',version='v3',locator=json.loads(held.locator))
    binding={'schema':'mastermind.memory_original_case_binding.v1',
        'attempt_id':state.lease.attempt.attempt_id,'pre_input_sha256':hashlib.sha256(peer.canonical(projection)).hexdigest(),
        'operation_id':projection['original_operation_id'],'wire_version':'v3',
        'intent':request['intent'],'issuer':source,'locator':json.loads(held.locator)}
    command='memory-case:'+state.lease.attempt.attempt_id+':case_bound'
    with state.runtime.store.read() as con:
        rows=con.execute('SELECT payload_json FROM events WHERE command_id=?',(command,)).fetchall()
    if rows:
        if len(rows)!=1:raise MemoryExecutionRefused()
        previous=json.loads(rows[0]['payload_json'])
        if ({k:v for k,v in previous.items() if k!='issuer'}!={k:v for k,v in binding.items() if k!='issuer'}
                or any(previous['issuer'][k]!=source[k] for k in set(source)-{'current_selection_sha256','current_access_ref'})):
            raise MemoryExecutionRefused()
        return
    _receipt_event(state,'CASE_BOUND',binding)


def _current(value):
    if type(value) is not PreparedMemoryExecution or value not in _OWNED:raise MemoryExecutionRefused()
    state=_OWNED[value]
    projection=peer.require_control_memory_intent(state.intent)
    if peer.canonical(projection)!=state.original_projection:raise MemoryExecutionRefused()
    profile.require_protected_memory_profile(state.profile,state.claim,state.observed)
    _private_directory(state.run_dir)
    return state


def prepare_memory_execution(runtime,lease):
    """Actual fixed composition; no injected source/provider/admission callbacks."""
    claim=admission.capture_memory_runtime_claim(runtime,lease)
    observed=issuer.describe_control_owner()
    qualified=profile.load_protected_memory_profile(claim,observed)
    # Profile/provider private custody and fixed executable source qualify before
    # any case source reservation/read. Missing deployment is a precise refusal.
    binary=_source_binary()
    run_dir=runtime.store.root/'data/control_plane/runs'/lease.attempt.attempt_id
    _private_directory(run_dir)
    intent=peer.capture_control_memory_intent(claim,observed)
    issuer.qualify_transport(intent)
    paid=economic.acquire(intent,qualified,claim,observed)
    case=issuer.prepare_case(intent,version='v3')
    packet=issuer.current_input(case,intent)
    state=_State(runtime,lease,claim,intent,qualified,observed,case,packet,run_dir,
        peer.canonical(peer.require_control_memory_intent(intent)),economic=paid)
    value=object.__new__(PreparedMemoryExecution);_OWNED[value]=state
    _current(value)
    _retain_case_binding(state)
    _retain_input(state)
    return value


def recover_memory_preparation(runtime,lease):
    """Same original read only after committed prepare attempt; never replay."""
    claim=admission.capture_memory_runtime_claim(runtime,lease)
    observed=issuer.describe_control_owner();qualified=profile.load_protected_memory_profile(claim,observed)
    _source_binary();run_dir=runtime.store.root/'data/control_plane/runs'/lease.attempt.attempt_id;_private_directory(run_dir)
    intent=peer.capture_control_memory_intent(claim,observed)
    paid=economic.recover(intent,qualified,claim,observed)
    result,case=issuer.read_original_case(intent)
    if result!='COMPLETE':return result,None
    packet=issuer.current_input(case,intent)
    value=object.__new__(PreparedMemoryExecution)
    _OWNED[value]=_State(runtime,lease,claim,intent,qualified,observed,case,packet,run_dir,
        peer.canonical(peer.require_control_memory_intent(intent)),economic=paid)
    _current(value);_retain_case_binding(_OWNED[value]);_retain_input(_OWNED[value]);_current(value);return 'COMPLETE',value


def start_memory_execution(value):
    state=_current(value)
    if state.proc is not None:raise MemoryExecutionUnknown()
    config=profile.require_protected_memory_profile(state.profile,state.claim,state.observed)
    economic.require(state.economic,state.intent)
    packet=issuer.current_input(state.case,state.intent)
    if packet!=state.packet:raise MemoryExecutionRefused()
    body=compile_memory_model_input(packet,model=config['model']);binary=_source_binary()
    seal={'schema':'mastermind.protected_memory_execution_start.v1',
        'pre_input_sha256':hashlib.sha256(state.original_projection).hexdigest(),
        'input_sha256':hashlib.sha256(packet).hexdigest(),'input_bytes':len(packet),
        'profile_sha256':hashlib.sha256(profile.canonical(config)).hexdigest(),
        'body_sha256':hashlib.sha256(body).hexdigest()}
    economic.require(state.economic,state.intent,'bind_input',{
        k:seal[k] for k in ('input_sha256','input_bytes','body_sha256')})
    current=state.runtime.attempts.get_attempt(state.lease.attempt.attempt_id)
    pinned=state.runtime.attempts.pin_remote_launch_identity(current.attempt_id,
        fence_generation=current.fence_generation,lease_token=state.lease.lease_token,
        expected_version=current.version,identity_digest=hashlib.sha256(wire.canonical(seal)).hexdigest())
    state.runtime.attempts.validate_pinned_remote_launch(pinned,lease_token=state.lease.lease_token)
    _event(state,'EXECUTION_ATTEMPT',seal)
    stdout=state.run_dir/'memory-original-result';stderr=state.run_dir/'memory-fixed-diagnostic'
    fds=[];parent=None;child=None
    try:
        for path in (stdout,stderr):fds.append(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600))
        parent,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
        _current(value)
        proc=subprocess.Popen([binary.real_path,'-I','-B',str(RUNNER),str(child.fileno())],
            stdin=subprocess.DEVNULL,stdout=fds[0],stderr=fds[1],close_fds=True,pass_fds=(child.fileno(),),
            start_new_session=True,env={'PATH':'/usr/bin:/bin','HOME':'/var/empty','LANG':'C','PYTHONDONTWRITEBYTECODE':'1'})
        state.proc=proc;child.close();child=None
        parent.settimeout(10)
        if parent.recv(6)!=b'READY\n':raise MemoryExecutionUnknown()
        inspector=ProcessInspector();observed=inspector.inspect(proc.pid)
        if any(getattr(observed,k)!=450 for k in ('effective_uid','real_uid')):raise MemoryExecutionRefused()
        ref=WorkerProcessRef(run_id=current.attempt_id,pid=proc.pid,pgid=observed.pgid,
            process_start_identity=observed.start_identity,boot_session_id=inspector.boot_session_id(),
            launch_nonce=seal['body_sha256'],provider_session_id=None,stdout_path=str(stdout),stderr_path=str(stderr),
            result_path=str(stdout),started_at=datetime.now(timezone.utc).isoformat(),binary=binary,base_sha=Path(__file__).resolve().parents[1].name,
            session_id=observed.session_id,effective_uid=observed.effective_uid,effective_gid=observed.effective_gid,
            real_uid=observed.real_uid,real_gid=observed.real_gid)
        state.runtime.attempts.validate_pinned_remote_launch(pinned,lease_token=state.lease.lease_token)
        state.runtime.attempts.record_process(current.attempt_id,fence_generation=current.fence_generation,
            lease_token=state.lease.lease_token,pid=ref.pid,pgid=ref.pgid,process_start_identity=ref.process_start_identity,
            boot_id=ref.boot_session_id,stdout_path=ref.stdout_path,stderr_path=ref.stderr_path,result_path=ref.result_path,
            launch_metadata={'protected_memory':seal})
        state.runtime.attempts.mark_running(current.attempt_id,fence_generation=current.fence_generation,lease_token=state.lease.lease_token)
        admission.bind_memory_runtime_process(state.claim,ref);state.ref=ref
        _current(value)
        receipt=economic.require(state.economic,state.intent,'consume',{
            'attempt_id':ref.run_id,'process_ref_sha256':hashlib.sha256(wire.canonical(dataclasses.asdict(ref))).hexdigest()})
        if receipt['phase']!='CONSUMED':raise MemoryExecutionRefused()
        # Sole release of exact input. Metadata/handshake alone cannot send it.
        envelope={'schema':'mastermind.protected_memory_model_request.v1','profile_sha256':seal['profile_sha256'],
            'input_sha256':seal['input_sha256'],'input_base64':base64.b64encode(packet).decode(),
            'body_base64':base64.b64encode(body).decode()}
        raw=wire.canonical(envelope);parent.sendall(len(raw).to_bytes(4,'big')+raw);parent.shutdown(socket.SHUT_WR)
        return ref
    except Exception:
        # Attempt/pin/process identity remain; never kill, refund or redispatch.
        raise MemoryExecutionUnknown() from None
    finally:
        for fd in fds:os.close(fd)
        if parent is not None:parent.close()
        if child is not None:child.close()


def collect_original_memory_result(value):
    """Private collector; no raw result is exposed to a generic participant API."""
    state=_current(value)
    if state.proc is None or state.ref is None:raise MemoryExecutionUnknown()
    code=state.proc.poll()
    if code is None:return None
    _private_directory(state.run_dir)
    from control_plane.paid_fabric_backend import _private_read
    if code!=0:
        # Terminal failure is still original accounting. No raw body is
        # disclosed and no failed/unknown model execution becomes retryable.
        if not state.accounted:
            path=Path(state.ref.result_path)
            raw=_private_read(path,65536) if path.stat().st_size else b''
            economic.require(state.economic,state.intent,'settle',{'rc':min(255,code if code>0 else 128-code),
                'result_sha256':hashlib.sha256(raw).hexdigest(),'result_bytes':len(raw)})
            state.accounted=True
        raise MemoryExecutionUnknown()
    raw=_private_read(Path(state.ref.result_path),65536)
    if state.raw is not None and state.raw!=raw:raise MemoryExecutionRefused()
    _current(value)
    if not state.accounted:
        economic.require(state.economic,state.intent,'settle',{'rc':0,
            'result_sha256':hashlib.sha256(raw).hexdigest(),'result_bytes':len(raw)})
        state.accounted=True
    # Current Linux source permission authorizes only the exact original digest.
    authorization=issuer.authorize_result_disclosure(state.case,state.intent,state.ref.run_id,
        hashlib.sha256(state.packet).hexdigest(),{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
    if _private_read(Path(state.ref.result_path),65536)!=raw:raise MemoryExecutionRefused()
    _current(value);state.raw=raw
    receipt={'schema':'mastermind.protected_memory_original_result.v1','attempt_id':state.ref.run_id,
        'input_sha256':hashlib.sha256(state.packet).hexdigest(),
        'result_sha256':hashlib.sha256(raw).hexdigest(),'result_bytes':len(raw),
        'verification':dict(wire.FLAGS),'scientific_admission':False,'adjudicator_access':False}
    if 'original_recipient' in authorization:
        receipt.update(schema='mastermind.protected_memory_original_result.v2',source_authorization=authorization)
    _receipt_event(state,'ORIGINAL_RESULT_RETAINED',receipt)
    return receipt


def disclose_memory_result(value):
    """Current exact recipient view; no generic raw result/allowlist input."""
    state=_current(value)
    receipt=collect_original_memory_result(value)
    if receipt is None:return None
    from common.memory_participant_view import project_original_result
    view=project_original_result(state.packet,state.raw,attempt_id=state.ref.run_id)
    issuer.authorize_result_disclosure(state.case,state.intent,state.ref.run_id,
        receipt['input_sha256'],{'sha256':receipt['result_sha256'],'bytes':receipt['result_bytes']})
    from control_plane.paid_fabric_backend import _private_read
    if _private_read(Path(state.ref.result_path),65536)!=state.raw:raise MemoryExecutionRefused()
    _current(value)
    return view


async def run_protected_memory_case(supervisor, lease):
    """One already-admitted original Attempt through the incumbent Supervisor.

    There is no automatic claim/placement/retry and no new lifecycle owner. This
    dedicated mode cannot fall through to the ordinary UID501 provider adapter.
    The existing Control command owner selects it only for its current admitted
    native_memory Job. Public request fields alone cannot enter this function.
    """
    job=supervisor.runtime.jobs.get_job(lease.attempt.job_id)
    if job is not None and 'native_memory_evaluation' in job.constraints:
        from control_plane.protected_memory_evaluation_execution import run_registered_evaluation
        return await run_registered_evaluation(supervisor,lease)
    import asyncio
    from control_plane.executive_supervisor import ExecutiveSupervisor
    from control_plane.executive_runtime import AttemptLease,JobPayload
    if type(supervisor) is not ExecutiveSupervisor or type(lease) is not AttemptLease:
        raise MemoryExecutionRefused()
    runtime=supervisor.runtime
    job=runtime.jobs.get_job(lease.attempt.job_id)
    if job is None or job.orchestration_role is not None:
        # A normal role/result envelope must not be relabeled as a Memory case.
        raise MemoryExecutionRefused()
    supervisor._effective_grant(job,lease.attempt)
    async def attended(call):
        task=asyncio.create_task(asyncio.to_thread(call))
        permission_lost = False
        while not task.done():
            done,_=await asyncio.wait({task},timeout=min(5.0,runtime.store.lease_seconds/3))
            if done:break
            if not permission_lost:
                try:
                    runtime.attempts.heartbeat_attempt(lease.attempt.attempt_id,
                        fence_generation=lease.attempt.fence_generation,lease_token=lease.lease_token)
                except Exception:
                    # Consume this same in-flight helper's result, withhold it;
                    # no abandoned source task or duplicate operation is made.
                    permission_lost = True
        result=task.result()
        if permission_lost:raise MemoryExecutionRefused()
        return result
    prepared=await attended(lambda:prepare_memory_execution(runtime,lease))
    await attended(lambda:start_memory_execution(prepared))
    deadline=time.monotonic()+600;next_paid_heartbeat=0
    while True:
        if time.monotonic()>=next_paid_heartbeat:
            await attended(lambda:economic.require(_OWNED[prepared].economic,_OWNED[prepared].intent,'heartbeat'))
            next_paid_heartbeat=time.monotonic()+5
        view=await attended(lambda:disclose_memory_result(prepared))
        if view is not None:break
        if time.monotonic()>=deadline:raise MemoryExecutionUnknown()
        runtime.attempts.heartbeat_attempt(lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,lease_token=lease.lease_token)
        await asyncio.sleep(0.05)
    state=_current(prepared)
    receipt={'schema':'mastermind.memory_case_completion.v1','attempt_id':state.ref.run_id,
        'input_sha256':view['input_sha256'],'result_sha256':view['result_sha256'],
        'view_sha256':hashlib.sha256(wire.canonical(view)).hexdigest(),
        'verification':dict(wire.FLAGS),'scientific_admission':False,'adjudicator_access':False}
    # Runtime receives safe completion evidence; no raw source/result/prose,
    # provider envelope or private capability is copied to generic Job output.
    _event(state,'RESULT_VIEW_OBSERVED',receipt)
    _current(prepared)
    supervisor._effective_grant(runtime.jobs.get_job(job.job_id),runtime.attempts.get_attempt(state.ref.run_id))
    runtime.attempts.complete_attempt(state.ref.run_id,fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,payload=JobPayload(summary='Protected Memory result retained',
            completed_steps=['Original protected result qualified'],current_state='Recipient-scoped result available',
            next_actions=[]))
    return view
