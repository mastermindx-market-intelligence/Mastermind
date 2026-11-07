"""Prospective study-assessor ingress, retained admission and actual actor join.

Identity mappings are assessed attestations over exact retained evidence. Native
credential/process observations are separate issuers. No machine observation
certifies expertise, independence, a human, or the provider-served identity.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import os
import weakref
from common import memory_evaluation_contract as c
from common import memory_native_wire as w
from control_plane import protected_memory_evaluation_source as source

INGRESS = 'mastermind.ceo_ingress.memory_evaluation_assessment_frame.v1'
_AUTH = weakref.WeakKeyDictionary()
_PREPARED = weakref.WeakKeyDictionary()
_BOUND = weakref.WeakKeyDictionary()
_HOSTS = weakref.WeakKeyDictionary()  # live existing host objects, never stored authority

class AssessmentCommitUnknown(ValueError):
    def __init__(self): super().__init__('memory_evaluation_assessment_commit_unknown')

class AuthenticatedAssessment:
    __slots__ = ('__weakref__',)
    def __new__(cls): c.fail()
    def __repr__(self): return '<AuthenticatedAssessment protected>'

class PreparedEvaluationAssignment:
    __slots__ = ('__weakref__',)
    def __new__(cls): c.fail()
    def __repr__(self): return '<PreparedEvaluationAssignment protected>'

class EvaluationAssignmentCapability:
    __slots__ = ('__weakref__',)
    def __new__(cls): c.fail()
    def __repr__(self): return '<EvaluationAssignmentCapability protected>'

def _exact_cap(table, value, cls):
    if type(value) is not cls or value not in table: c.fail()
    state = table[value]
    if state['pid'] != os.getpid(): c.fail()
    return state

def ingress_frame(value):
    w.exact(value, 'schema principal verified_expires_at assessment')
    if value['schema'] != INGRESS: c.fail()
    c.assessment(value['assessment'])
    w.integer(value['verified_expires_at'], 100_000_000_000)
    import time
    if time.time() >= value['verified_expires_at']: c.fail()
    from control_plane.coo_principal_host import FACT_SCHEMA, validate_facts_frame
    validate_facts_frame(dict(schema=FACT_SCHEMA, operation='authority',
        work_ref=value['assessment']['work_ref'], principal=value['principal']))
    return value

def _authenticate_gateway(connection):
    from control_plane.executive_peer_identity import capture_peer_identity, require_installed_service_peer
    from control_plane.executive_installed_peer import qualify_installed_peer
    captured = capture_peer_identity(connection)
    binding = qualify_installed_peer(captured, role='gateway')
    owner = require_installed_service_peer(captured, binding)
    if owner.service_label != 'com.mastermind.executive.mcp': c.fail()
    return captured, binding, owner

def _gateway_snapshot(context):
    # Trusted contexts are deliberately nominal/eq=False. Requalify using the
    # real API, then compare these original connection facts (not a DTO grant).
    return tuple(getattr(context,k) for k in ('real_boot_id','audit_identity_digest','service_label',
        'installed_release','config_digest','connection_instance'))

def capture_authenticated_assessment(connection, frame, provider, supervisor):
    """Only the real CeoIngress App branch calls this with its accepted socket.

    The App's JWT verifier/binding precedes this frame; the kernel + installed
    gateway qualifier excludes caller-authored principal dictionaries on other
    local sockets. The sealed delegation is an additional explicit authority.
    """
    from control_plane.coo_principal_host import CooHostProvider
    from control_plane.executive_supervisor import ExecutiveSupervisor
    if type(provider) is not CooHostProvider or type(supervisor) is not ExecutiveSupervisor: c.fail()
    ingress_frame(frame)
    observed = _authenticate_gateway(connection)
    context = source.installed(supervisor.runtime)
    from control_plane.paid_fabric_backend import _root_source
    from pathlib import Path
    if (observed[2].installed_release != Path(context[3]['coo_source']).name
            or observed[2].config_digest != hashlib.sha256(_root_source(Path(context[3]['coo_config']))).hexdigest()): c.fail()
    if frame['assessment']['work_ref'] != context[3]['work_ref']: c.fail()
    before = provider.source.for_principal(frame['principal'], frame['assessment']['work_ref'])
    if before[0] != context[1]: c.fail()
    from control_plane.coo_principal_mandate import project_coo_principal_mandate
    mission = provider.workspace.read_mission_for_work_ref(frame['assessment']['work_ref'])
    mandate = project_coo_principal_mandate(principal=before[1], authority=before[2], mission_workspace=mission)
    if mandate['new_effect_gate'] != 'OPEN' or mandate['mission']['root_job_id'] != context[2]['root_job_id']: c.fail()
    source.same(supervisor.runtime, context)
    if provider.source.for_principal(frame['principal'], frame['assessment']['work_ref']) != before: c.fail()
    from control_plane.executive_peer_identity import require_installed_service_peer
    if _gateway_snapshot(require_installed_service_peer(observed[0], observed[1])) != _gateway_snapshot(observed[2]): c.fail()
    _HOSTS[supervisor.runtime] = provider
    cap = object.__new__(AuthenticatedAssessment)
    _AUTH[cap] = dict(pid=os.getpid(), runtime=supervisor.runtime, context=context,
        provider=provider, connection=connection, observed=observed, frame=w.canonical(frame), used=False)
    return cap

def _current_authenticated(cap):
    state = _exact_cap(_AUTH, cap, AuthenticatedAssessment)
    source.same(state['runtime'], state['context'])
    frame = json.loads(state['frame'])
    ingress_frame(frame)
    if state['provider'].source.for_principal(frame['principal'], frame['assessment']['work_ref'])[0] != state['context'][1]: c.fail()
    # Source-qualified audit/process identity is rechecked after blocking reads.
    from control_plane.executive_peer_identity import require_installed_service_peer
    captured, binding, observed = state['observed']
    if _gateway_snapshot(require_installed_service_peer(captured, binding)) != _gateway_snapshot(observed): c.fail()
    _current_mission(state['runtime'], state['context'])
    return state, frame

def _current_mission(runtime, context):
    provider = _HOSTS.get(runtime)
    if provider is None: c.fail()
    before = provider.source.snapshot(context[3]['work_ref'])
    if before[0] != context[1]: c.fail()
    from control_plane.coo_principal_mandate import project_coo_principal_mandate
    mission = provider.workspace.read_mission_for_work_ref(context[3]['work_ref'])
    mandate = project_coo_principal_mandate(principal=before[1], authority=before[2], mission_workspace=mission)
    if (mandate['new_effect_gate'] != 'OPEN' or mandate['mission']['root_job_id'] != context[2]['root_job_id']
            or provider.source.snapshot(context[3]['work_ref']) != before): c.fail()

def retain_event(runtime, kind, command, payload, *, attempt=None, root=None):
    """Immutable command identity in the incumbent Events, not a new registry."""
    with runtime.store.transaction() as con:
        rows = con.execute('SELECT * FROM events WHERE command_id=? LIMIT 2', (command,)).fetchall()
        if rows:
            row = rows[0]
            if (len(rows) != 1 or row['event_type'] != kind or json.loads(row['payload_json']) != payload
                    or row['job_id'] != (attempt.job_id if attempt else root)
                    or row['attempt_id'] != (attempt.attempt_id if attempt else None)): c.fail()
            return row['event_id']
        runtime.store.append_event(con, aggregate_type='attempt' if attempt else 'job',
            aggregate_id=attempt.attempt_id if attempt else root, event_type=kind, command_id=command,
            job_id=attempt.job_id if attempt else root, attempt_id=attempt.attempt_id if attempt else None,
            worker_id=attempt.worker_id if attempt else None, quota_class=attempt.quota_class if attempt else None,
            actor='authenticated-study-assessor' if kind == 'MEMORY_EVALUATOR_ADMITTED' else 'supervisor', payload=payload)
        return con.execute('SELECT event_id FROM events WHERE command_id=?', (command,)).fetchone()['event_id']

def event(runtime, kind, command):
    with runtime.store.read() as con:
        rows = con.execute('SELECT * FROM events WHERE command_id=? AND event_type=? LIMIT 2', (command, kind)).fetchall()
    if len(rows) != 1: c.fail()
    return dict(rows[0]), json.loads(rows[0]['payload_json'])

def _admission_command(grant, role):
    return 'memory-evaluator:' + c.digest([grant['study_root'], grant['study_id'], grant['generation'], role])

def _evidence(basis, assessment, study_id):
    slot = next(s for s in basis['slots'] if s['role'] == assessment['participant_slot'])
    if assessment['identity_mapping_ref'] != slot['identity_mapping_ref']: c.fail()
    mapping = c.identity_mapping(c.evidence_body(basis, slot['identity_mapping_ref']))
    if mapping['canonical_actor_ref'] != assessment['canonical_actor_ref']: c.fail()
    # Criteria originate in the registered guide/profile, never invented model
    # scores, provider counts or a generic software-review policy.
    if [r['criterion_id'] for r in assessment['criteria']] != basis['required_criteria']: c.fail()
    for row in assessment['criteria']:
        c.evidence_body(basis, row['evidence_ref'])
        if row['finding'] != 'SATISFIED': c.fail()
    for key in ('principal_ref', 'qualification_ref', 'independence_ref'):
        c.evidence_body(basis, slot[key])
    # Reuse the accepted v2 metadata DATA grammar. Its all-false declarations
    # remain declarations; only this authorized assessor supplies the decision.
    from ops.native_fabric.quota_continuity.candidate.fabric_participant_owner import validate_payload
    reads = [dict(evidence_role=key, participant_id=s['principal_ref']['object_id'], study_id=study_id,
        reference=s[key]) for s in basis['slots'] for key in ('principal_ref','qualification_ref','independence_ref')]
    for descriptor in reads:
        validate_payload(descriptor, w.canonical(c.evidence_body(basis, descriptor['reference'])), reads)
    # The mapping/evidence are exact source bytes; only the authenticated
    # assessor's reasoned ADMIT decision below gives them admission meaning.
    return slot, mapping

def admit_registered_evaluator(authenticated):
    state, frame = _current_authenticated(authenticated)
    runtime = state['runtime']; grant = state['context'][2]; decision = c.assessment(frame['assessment'])
    if decision['decision'] == 'REFUSE':
        _current_authenticated(authenticated)
        payload = dict(schema='mastermind.memory_evaluator_revocation.v1', delegation=grant,
            assessor=frame['principal'], decision=decision)
        try:
            event_id = retain_event(runtime, 'MEMORY_EVALUATOR_REVOKED', _admission_command(grant, decision['participant_slot'])+':revoked', payload, root=grant['root_job_id'])
        except Exception: raise AssessmentCommitUnknown() from None
        return dict(schema='mastermind.memory_evaluator_admission_receipt.v1',event_id=event_id,
            admission_sha256=c.digest(payload),verification=dict(w.FLAGS),scientific_admission=False)
    answer = source.exchange(runtime, source.make_request(grant))
    basis = answer['basis']; slot, mapping = _evidence(basis, decision, grant['study_id'])
    _current_authenticated(authenticated)
    payload = dict(schema='mastermind.memory_evaluator_admission.v1', delegation=grant,
        mission_generation=state['context'][1], assessor=frame['principal'], decision=decision,
        basis=basis, source_owner=answer['source_owner'], source_generation=answer['generation'],
        actor_key=c.digest(['assessor-canonical-actor.v1', mapping['canonical_actor_ref']]),
        supported_observations=list(c.OBSERVED), limitations=list(c.LIMITS))
    command = _admission_command(grant, slot['role'])
    # Source/authority revocation after assessment still prevents issuance.
    _current_authenticated(authenticated)
    try:
        event_id = retain_event(runtime, 'MEMORY_EVALUATOR_ADMITTED', command, payload, root=grant['root_job_id'])
        state['used'] = True
        reread = current_admission(runtime, slot['role'])
        if reread['event_id'] != event_id: c.fail()
    except Exception: raise AssessmentCommitUnknown() from None
    return dict(schema='mastermind.memory_evaluator_admission_receipt.v1', event_id=event_id,
        admission_sha256=c.digest(payload), verification=dict(w.FLAGS), scientific_admission=False)

def current_admission(runtime, role):
    context = source.installed(runtime); grant = context[2]
    if role not in c.ROLES: c.fail()
    _current_mission(runtime, context)
    with runtime.store.read() as con:
        if con.execute("SELECT 1 FROM events WHERE event_type='MEMORY_EVALUATOR_REVOKED' AND command_id=?",(_admission_command(grant,role)+':revoked',)).fetchone(): c.fail()
    row, payload = event(runtime, 'MEMORY_EVALUATOR_ADMITTED', _admission_command(grant, role))
    if (payload['delegation'] != grant or payload['mission_generation'] != context[1]
            or payload['assessor']['subject_digest'] != context[0].snapshot(context[3]['work_ref'])[1].subject_digest): c.fail()
    answer = source.exchange(runtime, source.make_request(grant))
    if answer['basis'] != payload['basis'] or answer['source_owner'] != payload['source_owner']: c.fail()
    slot, mapping = _evidence(answer['basis'], payload['decision'], grant['study_id'])
    if payload['actor_key'] != c.digest(['assessor-canonical-actor.v1', mapping['canonical_actor_ref']]): c.fail()
    source.same(runtime, context)
    return dict(event_id=row['event_id'], payload=payload, slot=slot, mapping=mapping,
        actor_key=payload['actor_key'], context=context)

def prepare_registered_evaluation(supervisor, *, original_reference, original_attempt_lease):
    """No paid reservation/dispatch here. Existing admitted original only."""
    from control_plane.executive_supervisor import ExecutiveSupervisor
    from control_plane.executive_runtime import AttemptLease
    from control_plane import native_memory_admission as native
    from control_plane import protected_memory_original as originals
    if type(supervisor) is not ExecutiveSupervisor or type(original_attempt_lease) is not AttemptLease: c.fail()
    runtime = supervisor.runtime; context = source.installed(runtime)
    subject = originals.current_reference(original_reference)
    held = originals._REFERENCES[original_reference]
    if held.runtime is not runtime: c.fail()
    job = runtime.jobs.get_job(original_attempt_lease.attempt.job_id)
    selector = job.constraints.get('native_memory_evaluation') if job is not None else None
    w.exact(selector, 'schema subject_attempt_id participant_slot registration_ref reviewer_plan_ref guide_ref')
    if (selector['schema'] != 'mastermind.native_memory_evaluation_intent.v1'
            or selector['subject_attempt_id'] != subject['attempt_id']
            or job.root_job_id != context[2]['root_job_id']): c.fail()
    for k in ('registration_ref', 'reviewer_plan_ref', 'guide_ref'):
        if selector[k] != context[2][k]: c.fail()
    admitted = current_admission(runtime, selector['participant_slot'])
    # Reject alias/rotated-credential collisions BEFORE another private input.
    with runtime.store.read() as con:
        prior = con.execute("SELECT payload_json FROM events WHERE event_type='MEMORY_EVALUATION_EXPOSED' AND job_id IN (SELECT job_id FROM jobs WHERE root_job_id=?)", (job.root_job_id,)).fetchall()
    for row in prior:
        used = json.loads(row['payload_json'])
        if (used['subject'] == subject and used['role'] != selector['participant_slot']
                and used['actor_key'] == admitted['actor_key']): c.fail()
    claim = native.capture_memory_runtime_claim(runtime, original_attempt_lease)
    observed = source.model_observation(runtime, admitted['slot']['execution_profile_id'])
    selected = observed['profile']; actual = original_attempt_lease.attempt
    worker = runtime.workers.get_worker(actual.worker_id)
    quota = runtime.workers.get_quota_class(actual.worker_id, actual.quota_class)
    if (worker is None or quota is None or actual.worker_id != selected['worker_id']
            or actual.quota_class != selected['quota_class']
            or worker.account_label != selected['account_ref'] or quota.model != selected['model']): c.fail()
    binding = dict(credential_binding_ref=observed['credential_binding_ref'],
        credential_document_sha256=observed['credential_document_sha256'])
    if binding not in admitted['mapping']['credential_bindings']: c.fail()
    # Across admitted aliases, one owned credential cannot acquire two actors.
    for role in c.ROLES:
        if role == selector['participant_slot']: continue
        try: other = current_admission(runtime, role)
        except ValueError: continue
        if (any(b['credential_document_sha256']==binding['credential_document_sha256'] for b in other['mapping']['credential_bindings'])
                and other['actor_key'] != admitted['actor_key']): c.fail()
    state = dict(pid=os.getpid(), supervisor=supervisor, runtime=runtime, lease=original_attempt_lease,
        claim=claim, reference=original_reference, subject=subject, admission=admitted,
        role=selector['participant_slot'], observed=observed, context=context)
    cap = object.__new__(PreparedEvaluationAssignment); _PREPARED[cap] = state
    current_prepared(cap)
    return cap

def current_prepared(cap):
    state = _exact_cap(_PREPARED, cap, PreparedEvaluationAssignment)
    from control_plane import protected_memory_original as originals
    from control_plane import native_memory_admission as native
    native.require_memory_runtime_claim(state['claim'])
    source.same(state['runtime'], state['context'])
    if (originals.current_reference(state['reference']) != state['subject']
            or current_admission(state['runtime'], state['role'])['payload'] != state['admission']['payload']
            or source.model_observation(state['runtime'], state['admission']['slot']['execution_profile_id']) != state['observed']): c.fail()
    return state

def native_locator(state):
    from control_plane import native_memory_admission as native
    return native.require_memory_runtime_claim(state['claim'])

def bind_evaluation_execution(prepared, *, process):
    """Only after actual Runtime process registration; never declared Attempt."""
    state = _exact_cap(_PREPARED, prepared, PreparedEvaluationAssignment)
    from control_plane.worker_execution_contract import WorkerProcessRef
    from control_plane.codex_worker import ProcessInspector
    if type(process) is not WorkerProcessRef: c.fail()
    from control_plane import native_memory_admission as native
    native.bind_memory_runtime_process(state['claim'], process)
    inspector = ProcessInspector(); actual = inspector.inspect(process.pid)
    if (actual.start_identity != process.process_start_identity or actual.pgid != process.pgid
            or actual.session_id != process.session_id or actual.effective_uid != 450
            or actual.real_uid != 450 or inspector.boot_session_id() != process.boot_session_id): c.fail()
    # current_prepared now requires the actual bound Runtime process too.
    current_prepared(prepared)
    cap = object.__new__(EvaluationAssignmentCapability)
    _BOUND[cap] = dict(pid=os.getpid(), prepared=prepared, process=process,
        actor_key=state['admission']['actor_key'])
    return cap

def current_assignment(cap):
    bound = _exact_cap(_BOUND, cap, EvaluationAssignmentCapability)
    state = current_prepared(bound['prepared'])
    from control_plane.codex_worker import ProcessInspector
    inspector = ProcessInspector(); actual = inspector.inspect(bound['process'].pid)
    if (actual.start_identity != bound['process'].process_start_identity
            or inspector.boot_session_id() != bound['process'].boot_session_id): c.fail()
    return state, bound
