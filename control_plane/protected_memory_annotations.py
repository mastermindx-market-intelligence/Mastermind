"""Protected original annotation custody, immutable pair and resolution.

No public raw-body/status/artifact endpoint. These objects remain inside the
existing protected owner and Events/run directories. They authorize no launch,
new source reservation, refund, retry, scientific admission or hold release.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import weakref
from common import memory_evaluation_contract as c
from common import memory_native_wire as w
from common import memory_evaluation_ratings as ratings
from control_plane import protected_memory_evaluation_assignment as assignment
from control_plane import protected_memory_evaluation_source as source
from control_plane import protected_memory_original as originals

_PAIRS = weakref.WeakKeyDictionary()

class RetainedAnnotationPairCapability:
    __slots__ = ('__weakref__',)
    def __new__(cls): c.fail()
    def __repr__(self): return '<RetainedAnnotationPairCapability private>'

def subject_selector(subject):
    return {k:subject[k] for k in ('operation_id', 'attempt_id', 'input_sha256', 'input_bytes', 'result_sha256', 'result_bytes')}

def assignment_material(state):
    return dict(schema='mastermind.memory_evaluation_assignment.v1', subject=state['subject'], role=state['role'],
        registered_assignment_event_id=state['registered']['event_id'],registered_assignment_sha256=c.digest(state['registered']['payload']),
        task_id=state['registered']['payload']['task_id'],original_case_sha256=state['registered']['payload']['original_case_sha256'],
        admission_event_id=state['admission']['event_id'], admission_sha256=c.digest(state['admission']['payload']),
        actor_key=state['admission']['actor_key'], attempt_id=state['lease'].attempt.attempt_id,
        job_id=state['lease'].attempt.job_id, fence=state['lease'].attempt.fence_generation,
        mapping_ref=state['admission']['slot']['identity_mapping_ref'],
        registration_ref=state['context'][2]['registration_ref'], reviewer_plan_ref=state['context'][2]['reviewer_plan_ref'],
        guide_ref=state['context'][2]['guide_ref'], profile_id=state['observed']['profile_id'])

def _authorize(state, action, input_sha=None, pair_sha=None):
    return source.exchange(state['runtime'], source.make_request(state['context'][2], action,
        subject=subject_selector(state['subject']), assignment=c.digest(assignment_material(state)),
        input_sha256=input_sha, pair_sha256=pair_sha))

def subject_bytes(state):
    _authorize(state, 'authorize_evaluation_subject_read')
    reference = state['reference']; runtime = state['runtime']; expected = state['subject']
    if originals.current_reference(reference) != expected: c.fail()
    directory = runtime.store.root/'data/control_plane/runs'/expected['attempt_id']
    from control_plane.protected_memory_execution import _private_directory
    from control_plane.paid_fabric_backend import _private_read
    _private_directory(directory)
    packet = _private_read(directory/'memory-original-input', 65536)
    result = _private_read(directory/'memory-original-result', 65536)
    for raw, kind in ((packet,'input'), (result,'result')):
        if hashlib.sha256(raw).hexdigest() != expected[kind+'_sha256'] or len(raw) != expected[kind+'_bytes']: c.fail()
    if originals.current_reference(reference) != expected: c.fail()
    _authorize(state, 'authorize_evaluation_subject_read')
    return packet, result

def _guide():
    from control_plane.paid_fabric_backend import _root_source
    raw = _root_source(Path(__file__).resolve().parents[1]/'common/memory_evaluation_guide.md')
    if hashlib.sha256(raw).hexdigest() != c.GUIDE_SHA: c.fail()
    return raw.decode('utf-8')

def input_packet(prepared, *, pair=None):
    state = assignment.current_prepared(prepared)
    packet, raw = subject_bytes(state)
    from common.memory_participant_view import project_original_result, _json
    view = project_original_result(packet, raw, attempt_id=state['subject']['attempt_id'])
    task = _json(packet[:-len(w.SUFFIX)], canonical=True)['task']
    body = dict(schema='mastermind.memory_evaluation_input.v1', task=task, guide=_guide(),
        original_packet=packet.decode('utf-8'), answer=view['answer'], answer_text_basis='original_result.answer_utf8_decoded_no_normalization.v1',
        answer_text_sha256=hashlib.sha256(view['answer'].encode()).hexdigest(), stage='independent_annotation',
        comparison=None, result_contract=ratings.result_contract(), limitations=['provider_and_method_identity_withheld', *c.LIMITS])
    if state['role'] == 'adjudicator':
        material = current_pair(pair)
        if material['subject'] != state['subject'] or not material['comparison_items']: c.fail()
        if state['admission']['actor_key'] in material['actor_keys']: c.fail()
        body.update(stage='retained_disagreement_adjudication', comparison={k:material[k] for k in ('original_annotations','comparison_items')})
        body['result_contract']=ratings.result_contract(adjudication=True)
    elif pair is not None:
        c.fail()
    # No participant role/account/method/condition/peer rating in reviewer input.
    result = w.canonical(body) + w.SUFFIX
    if len(result) > 65536: c.fail()
    assignment.current_prepared(prepared)
    return result

def _command(attempt_id, suffix): return 'memory-evaluation:' + attempt_id + ':' + suffix

def begin_exposure(bound, packet, *, pair=None):
    state, identity = assignment.current_assignment(bound)
    expected = input_packet(identity['prepared'], pair=pair)
    if packet != expected: c.fail()
    material = assignment_material(state)
    sha = hashlib.sha256(packet).hexdigest()
    _authorize(state, 'authorize_adjudication_exposure' if state['role']=='adjudicator' else 'authorize_annotation_exposure',
        sha, c.digest(current_pair(pair)) if pair is not None else None)
    attempt = state['lease'].attempt
    payload = dict(schema='mastermind.memory_evaluation_exposure.v1', **{k:material[k] for k in material if k!='schema'},
        input_sha256=sha, input_bytes=len(packet), owned_process=identity['process'].__dict__ if hasattr(identity['process'], '__dict__') else None)
    import dataclasses
    payload['owned_process'] = dataclasses.asdict(identity['process'])
    # Reserve the original exposure identity BEFORE a possibly ambiguous write.
    # A partial write is UNKNOWN and cannot become another channel/attempt.
    with state['runtime'].store.transaction() as con:
        command = _command(attempt.attempt_id, 'exposure-attempt')
        if con.execute('SELECT 1 FROM events WHERE command_id=?', (command,)).fetchone(): c.fail()
        rows = con.execute("SELECT payload_json FROM events WHERE event_type='MEMORY_EVALUATION_EXPOSURE_ATTEMPT'").fetchall()
        for row in rows:
            prior = json.loads(row['payload_json'])
            if (prior['subject'] == material['subject'] and prior['role'] != state['role']
                    and prior['actor_key'] == material['actor_key']): c.fail()
        state['runtime'].store.append_event(con, aggregate_type='attempt', aggregate_id=attempt.attempt_id,
            event_type='MEMORY_EVALUATION_EXPOSURE_ATTEMPT', job_id=attempt.job_id, attempt_id=attempt.attempt_id,
            worker_id=attempt.worker_id, quota_class=attempt.quota_class, command_id=command, actor='supervisor', payload=payload)
    return payload

def confirm_exposure(bound, payload):
    # Retain the ACTUAL successful channel operation even when the child has
    # already exited or authority subsequently withdraws. It is an observation,
    # not a new disclosure grant. Later collectors repeat current authorization.
    identity=assignment._exact_cap(assignment._BOUND,bound,assignment.EvaluationAssignmentCapability)
    state=assignment._exact_cap(assignment._PREPARED,identity['prepared'],assignment.PreparedEvaluationAssignment)
    _,attempt=assignment.event(state['runtime'],'MEMORY_EVALUATION_EXPOSURE_ATTEMPT',_command(state['lease'].attempt.attempt_id,'exposure-attempt'))
    if attempt!=payload:c.fail()
    assignment.retain_event(state['runtime'], 'MEMORY_EVALUATION_EXPOSED',
        _command(state['lease'].attempt.attempt_id, 'exposed'), payload, attempt=state['lease'].attempt)

def final_fd_window(bound, payload, packet, *, pair=None):
    """After all blocking input reads, immediately before the sole write."""
    state,_=assignment.current_assignment(bound)
    if hashlib.sha256(packet).hexdigest()!=payload['input_sha256'] or len(packet)!=payload['input_bytes']:c.fail()
    authorization=_authorize(state,'authorize_adjudication_exposure' if state['role']=='adjudicator' else 'authorize_annotation_exposure',
        payload['input_sha256'],c.digest(current_pair(pair)) if pair is not None else None)
    from control_plane import native_memory_admission as native
    native.require_memory_runtime_claim(state['claim'])
    assignment.require_owned_process(bound)
    # The authenticated source response is a bounded currentness window, not
    # echoed caller authority. No blocking operation follows this final clock.
    now=state['runtime'].store.now_ms();grant=state['context'][2]
    if not max(grant['not_before_ms'],authorization['not_before_ms'])<=now<min(grant['expires_at_ms'],authorization['expires_at_ms']):c.fail()

def collect_annotation(prepared, *, pair=None):
    """Called only by the fixed original process collector AFTER exit zero."""
    state = assignment._exact_cap(assignment._PREPARED, prepared, assignment.PreparedEvaluationAssignment)
    runtime = state['runtime']; attempt = state['lease'].attempt
    row, exposure = assignment.event(runtime, 'MEMORY_EVALUATION_EXPOSED', _command(attempt.attempt_id, 'exposed'))
    from control_plane.paid_fabric_backend import _private_read
    from control_plane.protected_memory_execution import _private_directory
    directory = runtime.store.root/'data/control_plane/runs'/attempt.attempt_id; _private_directory(directory)
    input_raw = _private_read(directory/'memory-evaluation-input', 65536)
    result_raw = _private_read(directory/'memory-evaluation-result', 65536)
    # Runtime's real terminal process is rechecked by the fixed execution
    # collector; this function cannot accept a result body as an argument.
    from control_plane.protected_memory_evaluation_execution import completed_process
    completed_process(prepared)
    if hashlib.sha256(input_raw).hexdigest()!=exposure['input_sha256'] or len(input_raw)!=exposure['input_bytes']: c.fail()
    original_packet, original_result = subject_bytes(state)
    if state['role']=='adjudicator':
        pair_material = current_pair(pair)
        value = ratings.resolution(result_raw, pair_material['comparison_items'],packet=original_packet)
    else:
        pair_material = None
        value = ratings.annotation(result_raw, original_packet, original_result)
    admitted = assignment.current_admission(runtime, state['role'])
    if admitted['payload'] != state['admission']['payload']: c.fail()
    receipt = dict(schema='mastermind.memory_evaluation_completed.v1', assignment=assignment_material(state),
        exposure_event_id=row['event_id'], input_sha256=exposure['input_sha256'], input_bytes=len(input_raw),
        result_sha256=hashlib.sha256(result_raw).hexdigest(), result_bytes=len(result_raw),
        pair_sha256=c.digest(pair_material) if pair_material is not None else None,
        verification=dict(w.FLAGS), scientific_admission=False, holds_released=False)
    if (_private_read(directory/'memory-evaluation-result',65536)!=result_raw
            or _private_read(directory/'memory-evaluation-input',65536)!=input_raw): c.fail()
    _authorize(state, 'authorize_evaluation_subject_read')
    assignment.retain_event(runtime, 'MEMORY_EVALUATION_COMPLETED', _command(attempt.attempt_id,'completed'), receipt, attempt=attempt)
    return receipt

def _completed(supervisor, attempt_id):
    from control_plane.executive_runtime import AttemptStatus, JobStatus
    from control_plane.executive_supervisor import ExecutiveSupervisor
    if type(supervisor) is not ExecutiveSupervisor: c.fail()
    runtime = supervisor.runtime; attempt = runtime.attempts.get_attempt(attempt_id)
    job = runtime.jobs.get_job(attempt.job_id) if attempt is not None else None
    if attempt is None or attempt.status is not AttemptStatus.COMPLETED or job is None or job.status is not JobStatus.COMPLETED: c.fail()
    row, receipt = assignment.event(runtime,'MEMORY_EVALUATION_COMPLETED',_command(attempt_id,'completed'))
    _, exposure = assignment.event(runtime,'MEMORY_EVALUATION_EXPOSED',_command(attempt_id,'exposed'))
    material = receipt['assignment']; admitted = assignment.current_admission(runtime, material['role'])
    registered=assignment.current_registered_assignment(runtime,job.job_id)
    if registered['event_id']!=material['registered_assignment_event_id'] or c.digest(registered['payload'])!=material['registered_assignment_sha256']:c.fail()
    if (receipt['exposure_event_id']>=row['event_id'] or receipt['assignment']['attempt_id']!=attempt_id
            or receipt['assignment']['job_id']!=job.job_id or material['admission_sha256']!=c.digest(admitted['payload'])
            or material['actor_key']!=admitted['actor_key'] or job.root_job_id!=admitted['context'][2]['root_job_id']): c.fail()
    reference = originals.completed_original_reference(runtime, material['subject']['attempt_id'])
    if originals.current_reference(reference)!=material['subject']: c.fail()
    # No mutable/constructed assignment issues authority: use original immutable
    # assignment digest in this completed-reader request rather than state helper.
    req=source.make_request(admitted['context'][2],'authorize_evaluation_subject_read',subject=subject_selector(material['subject']),assignment=c.digest(material))
    source.exchange(runtime,req)
    if material['role']=='adjudicator':
        req=source.make_request(admitted['context'][2],'authorize_adjudication_exposure',subject=subject_selector(material['subject']),
            assignment=c.digest(material),input_sha256=receipt['input_sha256'],pair_sha256=receipt['pair_sha256'])
        source.exchange(runtime,req)
    from control_plane.paid_fabric_backend import _private_read
    from control_plane.protected_memory_execution import _private_directory
    directory=runtime.store.root/'data/control_plane/runs'/attempt_id;_private_directory(directory)
    raw=_private_read(directory/'memory-evaluation-result',65536)
    if hashlib.sha256(raw).hexdigest()!=receipt['result_sha256'] or len(raw)!=receipt['result_bytes']: c.fail()
    subject_dir=runtime.store.root/'data/control_plane/runs'/material['subject']['attempt_id'];_private_directory(subject_dir)
    packet=_private_read(subject_dir/'memory-original-input',65536);answer=_private_read(subject_dir/'memory-original-result',65536)
    for body,key in ((packet,'input'),(answer,'result')):
        if hashlib.sha256(body).hexdigest()!=material['subject'][key+'_sha256'] or len(body)!=material['subject'][key+'_bytes']: c.fail()
    if _private_read(directory/'memory-evaluation-result',65536)!=raw: c.fail()
    source.exchange(runtime,req)
    if (assignment.current_admission(runtime,material['role'])['payload']!=admitted['payload']
            or assignment.current_registered_assignment(runtime,job.job_id)!=registered): c.fail()
    if originals.current_reference(reference)!=material['subject']:c.fail()
    return row,receipt,raw,packet,answer

def capture_retained_annotation_pair(supervisor, *, original_attempt_id, reviewer_attempt_ids):
    if type(reviewer_attempt_ids) not in (list,tuple) or len(reviewer_attempt_ids)!=2: c.fail()
    entries=[_completed(supervisor,aid) for aid in reviewer_attempt_ids]
    if [e[1]['assignment']['role'] for e in entries]!=['reviewer_1','reviewer_2']: c.fail()
    first,second=entries
    a,b=first[1]['assignment'],second[1]['assignment']
    if (a['subject']!=b['subject'] or a['subject']['attempt_id']!=original_attempt_id or a['actor_key']==b['actor_key']):c.fail()
    bodies=[ratings.annotation(e[2],e[3],e[4]) for e in entries]
    material=dict(schema='mastermind.retained_annotation_pair.v1',subject=a['subject'],
        annotation_receipts=[e[1] for e in entries], original_annotations=[e[2].decode('utf-8') for e in entries],
        completion_event_ids=[e[0]['event_id'] for e in entries], actor_keys=[a['actor_key'],b['actor_key']],
        comparison_items=ratings.align(*bodies), verification=dict(w.FLAGS),scientific_admission=False)
    command='memory-pair:'+c.digest([original_attempt_id,*reviewer_attempt_ids])
    event_id=assignment.retain_event(supervisor.runtime,'MEMORY_ANNOTATION_PAIR_RETAINED',command,material,root=source.installed(supervisor.runtime)[2]['root_job_id'])
    if event_id<=max(material['completion_event_ids']):c.fail()
    cap=object.__new__(RetainedAnnotationPairCapability)
    _PAIRS[cap]=dict(pid=os.getpid(),supervisor=supervisor,attempts=tuple(reviewer_attempt_ids),command=command,
        material=w.canonical(material),event_id=event_id)
    current_pair(cap)
    return cap

def current_pair(cap):
    if type(cap) is not RetainedAnnotationPairCapability or cap not in _PAIRS:c.fail()
    state=_PAIRS[cap]
    if state['pid']!=os.getpid():c.fail()
    row,material=assignment.event(state['supervisor'].runtime,'MEMORY_ANNOTATION_PAIR_RETAINED',state['command'])
    if row['event_id']!=state['event_id'] or w.canonical(material)!=state['material']:c.fail()
    entries=[_completed(state['supervisor'],aid) for aid in state['attempts']]
    if [e[1] for e in entries]!=material['annotation_receipts'] or [e[2].decode() for e in entries]!=material['original_annotations']:c.fail()
    return json.loads(state['material'])

def prepare_retained_adjudication(supervisor, *, pair, adjudicator_attempt_lease):
    material=current_pair(pair)
    reference=originals.completed_original_reference(supervisor.runtime,material['subject']['attempt_id'])
    prepared=assignment.prepare_registered_evaluation(supervisor,original_reference=reference,original_attempt_lease=adjudicator_attempt_lease)
    state=assignment.current_prepared(prepared)
    if state['role']!='adjudicator' or state['admission']['actor_key'] in material['actor_keys']:c.fail()
    return prepared

def _final_resolution_authority(supervisor, receipt, pair_material):
    """Final metadata-only recipient window AFTER the last blocking pair read.

    No body/pair reread or new authority. Fresh purpose admission is followed by
    local immutable event/revocation checks, including revocation during that
    source roundtrip. A prior _completed result alone never grants this view.
    """
    runtime=supervisor.runtime;material=receipt['assignment'];context=source.installed(runtime)
    admitted=assignment.current_admission(runtime,'adjudicator')
    registered=assignment.current_registered_assignment(runtime,material['job_id'])
    if (registered['event_id']!=material['registered_assignment_event_id']
            or c.digest(registered['payload'])!=material['registered_assignment_sha256']
            or c.digest(admitted['payload'])!=material['admission_sha256']
            or admitted['actor_key']!=material['actor_key']):c.fail()
    _,retained=assignment.event(runtime,'MEMORY_EVALUATION_COMPLETED',_command(material['attempt_id'],'completed'))
    if retained!=receipt:c.fail()
    original=originals.completed_original_reference(runtime,material['subject']['attempt_id'])
    if originals.current_reference(original)!=material['subject']:c.fail()
    permission=source.make_request(context[2],'authorize_adjudication_exposure',
        subject=subject_selector(material['subject']),assignment=c.digest(material),
        input_sha256=receipt['input_sha256'],pair_sha256=c.digest(pair_material))
    window=source.exchange(runtime,permission)
    source.same(runtime,context);assignment._current_mission(runtime,context)
    # Admissions/assignments are immutable commands; the only later local
    # authority withdrawal is its explicit retained revocation. No private IO
    # follows this final native check or the clipped wall-clock window.
    with runtime.store.read() as con:
        if con.execute("SELECT 1 FROM events WHERE event_type='MEMORY_EVALUATOR_REVOKED' AND command_id=?",
                (assignment._admission_command(context[2],'adjudicator')+':revoked',)).fetchone():c.fail()
    now=runtime.store.now_ms()
    if not max(context[2]['not_before_ms'],window['not_before_ms'])<=now<min(context[2]['expires_at_ms'],window['expires_at_ms']):c.fail()

def read_retained_resolution(supervisor, *, adjudication_attempt_id, pair):
    material=current_pair(pair)
    _,receipt,raw,packet,_=_completed(supervisor,adjudication_attempt_id)
    if receipt['assignment']['role']!='adjudicator' or receipt['pair_sha256']!=c.digest(material):c.fail()
    if receipt['assignment']['actor_key'] in material['actor_keys']:c.fail()
    resolved=ratings.resolution(raw,material['comparison_items'],packet=packet)
    # Detached protected recipient view, never a generic CLI/HTTP result route.
    current_pair(pair)
    _final_resolution_authority(supervisor,receipt,material)
    return dict(schema='mastermind.retained_memory_resolution_view.v1', pair=material,
        original_resolution=raw.decode('utf-8'),resolution=resolved,receipt=receipt,
        verification=dict(w.FLAGS),scientific_admission=False,holds_released=False)
