"""Inert direct Supervisor contract tests; no direct admission is fabricated.

Job/Attempt DATA is derived from disposable legacy Runtime records, then marked
only at the local Supervisor seam. Claim/access and physical receipts are
explicit spies. Joined admission and deep Runtime acceptance remain separate.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane import executive_supervisor as s
from control_plane.executive_authority import ExecutiveAuthorityPolicy
from control_plane.executive_orchestration_result import canonical_digest
from control_plane.executive_runtime import (Runtime, AttemptLease, AttemptStatus,
    OrchestrationDispatchOutcome)
from control_plane.worker_execution_contract import CleanupPolicy


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    runtime = Runtime.at(tmp_path)
    runtime.workers.register_worker('codex-01', provider='codex', account_label='inert',
        worker_type='codex-cli', capabilities=['research'], quota_classes={
            'codex-native': {'provider': 'codex', 'capabilities': ['research'],
                'model': 'gpt-5.6-sol', 'effort': 'xhigh', 'cost_class': 'standard'}})
    original = runtime.jobs.create_job('Inert research', requested_authorities=['READ', 'RESEARCH'],
        constraints={'eligible_quota_classes': ['codex-native'], 'required_capabilities': ['research']},
        attempt_limit=1)
    lease = runtime.attempts.claim_job(original.job_id, lease_owner='inert-supervisor')
    assert type(lease) is AttemptLease
    job = dataclasses.replace(original, constraints={**original.constraints,
        'direct_native_policy': 'mastermind.direct_native_readonly/v1'})
    grant = dict(schema_version='mastermind.executive_effective_grant/v1',
        authorities=['READ', 'RESEARCH'], write_paths=[], validation_argv=[],
        policy_sha=lease.attempt.authority_policy_hash, job_id=job.job_id, role=None)
    attempt = dataclasses.replace(lease.attempt, effective_grant=grant,
        effective_grant_digest=canonical_digest(grant))
    lease = AttemptLease(attempt=attempt, lease_token=lease.lease_token)
    decision = ExecutiveAuthorityPolicy.load().authorize(job.requested_authorities)
    # This spy is only the pure discriminator; it grants no access/admission.
    monkeypatch.setattr(s, '_is_direct_native_job', lambda value:
        value.constraints.get('direct_native_policy') == 'mastermind.direct_native_readonly/v1')
    supervisor = object.__new__(s.ExecutiveSupervisor)
    supervisor.runtime = runtime
    supervisor.instance_id = 'inert-supervisor'
    supervisor.cleanup_policy = CleanupPolicy.DEDICATED_UID
    supervisor.adapter = object()
    monkeypatch.setattr(supervisor, '_job', lambda _id: job)
    return SimpleNamespace(runtime=runtime, job=job, lease=lease, grant=grant,
                           decision=decision, supervisor=supervisor, root=tmp_path)


def test_direct_grant_exact_and_legacy_role_null_unchanged(fixture):
    f = fixture
    assert s.validate_effective_grant(f.job, f.lease.attempt, f.decision) == f.grant
    legacy = dataclasses.replace(f.job, constraints={})
    legacy_attempt = dataclasses.replace(f.lease.attempt, effective_grant=None,
                                         effective_grant_digest=None)
    assert s.validate_effective_grant(legacy, legacy_attempt, f.decision) is None
    with pytest.raises(s.SupervisorError):
        s.validate_effective_grant(legacy, f.lease.attempt, f.decision)


@pytest.mark.parametrize('field,value', [
    ('authorities', ['READ']), ('authorities', ['READ', 'RESEARCH', 'READ']),
    ('authorities', ['READ', 'RESEARCH', 'WRITE_BRANCH']), ('role', 'work'),
    ('write_paths', ['research/write.txt']), ('validation_argv', [['true']]),
    ('job_id', 'JOB-other'), ('policy_sha', 'f'*64),
])
def test_direct_grant_rehash_does_not_authorize_widened_or_incomplete_scope(fixture, field, value):
    f = fixture
    grant = {**f.grant, field: value}
    attempt = dataclasses.replace(f.lease.attempt, effective_grant=grant,
                                   effective_grant_digest=canonical_digest(grant))
    with pytest.raises(s.SupervisorError):
        s.validate_effective_grant(f.job, attempt, f.decision)


@pytest.mark.parametrize('status', [AttemptStatus.CLAIMED, AttemptStatus.RUNNING, AttemptStatus.COMPLETED])
def test_every_dispatch_replay_returns_without_launch_even_claimed(fixture, monkeypatch, status):
    f = fixture
    attempt = dataclasses.replace(f.lease.attempt, status=status)
    outcome = OrchestrationDispatchOutcome(command_id='direct-native-dispatch:'+f.job.job_id,
        job_id=f.job.job_id, attempt=attempt,
        outcome='TERMINAL' if status is AttemptStatus.COMPLETED else 'ACTIVE',
        lease_token=None if status is AttemptStatus.COMPLETED else f.lease.lease_token)
    observed = []
    monkeypatch.setattr(f.runtime.jobs, 'direct_native_provenance', lambda job_id:
                        observed.append(('provenance', job_id)) or {}, raising=False)
    monkeypatch.setattr(f.runtime.attempts, 'claim_job', lambda job_id, **kw:
                        observed.append(('claim', job_id, kw)) or outcome)
    async def never(*args, **kwargs):
        raise AssertionError('replay must not launch')
    monkeypatch.setattr(f.supervisor, '_start_claimed_job', never)
    access = object()
    assert asyncio.run(f.supervisor.start_direct_native_job(f.job.job_id, access=access)) is outcome
    assert observed[1] == ('claim', f.job.job_id, dict(
        command_id='direct-native-dispatch:'+f.job.job_id,
        lease_owner='inert-supervisor', _direct_native_access=access))


def test_only_fresh_lease_passes_exact_access_to_launch_seam(fixture, monkeypatch):
    f = fixture
    monkeypatch.setattr(f.runtime.jobs, 'direct_native_provenance', lambda _: {}, raising=False)
    monkeypatch.setattr(f.runtime.attempts, 'claim_job', lambda *a, **k: f.lease)
    observed = []
    async def stop(job_id, lease, **kw):
        observed.append((job_id, lease, kw)); return 'inert-no-launch'
    monkeypatch.setattr(f.supervisor, '_start_claimed_job', stop)
    access = object()
    assert asyncio.run(f.supervisor.start_direct_native_job(f.job.job_id, access=access)) == 'inert-no-launch'
    assert observed == [(f.job.job_id, f.lease, {'_direct_native_access': access})]


def test_direct_job_refuses_legacy_and_cycle_entry_before_claim(fixture, monkeypatch):
    f = fixture
    def never(*a, **k):
        raise AssertionError('alternate claim path reached')
    monkeypatch.setattr(f.runtime.broker, 'claim', never)
    monkeypatch.setattr(f.runtime.attempts, 'dispatch_cycle_job', never)
    for call in (f.supervisor.start_job(f.job.job_id),
                 f.supervisor.start_cycle_job(f.job.job_id, command_id='arbitrary')):
        with pytest.raises(s.SupervisorError):
            asyncio.run(call)


def terminal_fixture(f, monkeypatch):
    output = dict(schema_version=s.RESULT_SCHEMA_VERSION, job_id=f.job.job_id,
        run_id=f.lease.attempt.attempt_id, worker_id=f.lease.attempt.worker_id,
        status='COMPLETED', summary='Actual findings DATA', current_state='Complete',
        completed_steps=['Read'], next_actions=[], artifacts=[], errors=[], validations=[])
    active = SimpleNamespace(effective_grant=f.grant, lease=f.lease)
    monkeypatch.setattr(f.supervisor, '_effective_grant', lambda *a: copy.deepcopy(f.grant))
    provenance = dict(schema_version='test-only-admission-data', source_digest='a'*64)
    monkeypatch.setattr(f.runtime.jobs, 'direct_native_provenance', lambda _: provenance, raising=False)
    receipts = [dict(collection=dict(result=dict(artifact_manifest=[], structured_output=output))),
                dict(commands=[], effective_grant_digest=f.lease.attempt.effective_grant_digest),
                dict(schema_version='test-only-assignment-data')]
    paths = []
    for i, receipt in enumerate(receipts):
        path = f.root / ('owned-receipt-'+str(i)+'.json')
        path.write_text(json.dumps(receipt)); path.chmod(0o600); paths.append(path)
    kwargs = dict(active=active, job=f.job, output=output,
        collection_path=paths[0], validation_path=paths[1], assignment_path=paths[2])
    return kwargs, receipts, paths, provenance


def test_terminal_producer_projects_owned_receipts_without_role_or_self_hash(fixture, monkeypatch):
    f = fixture
    kwargs, receipts, paths, provenance = terminal_fixture(f, monkeypatch)
    result = f.supervisor._direct_native_terminal_payload(**kwargs)
    assert set(result) == {'schema_version','status','job_id','attempt_id','admission_digest',
        'payload','result_evidence','result_envelope','result_envelope_digest',
        'artifact_receipt_digest','validation_receipt_digest','effective_grant_digest'}
    assert result['schema_version'] == 'mastermind.direct_native_terminal/v1'
    assert result['admission_digest'] == canonical_digest(provenance)
    assert result['payload'] == {k: kwargs['output'][k] for k in (
        'summary','current_state','completed_steps','next_actions')}
    assert result['result_evidence']['assignment_seal_receipt'] == receipts[2]
    assert result['result_envelope_digest'] == canonical_digest(kwargs['output'])
    assert 'role_result' not in result['result_envelope']
    assert 'terminal_evidence_digest' not in result
    schema = f.supervisor._result_schema(job=f.job, attempt=f.lease.attempt, effective_grant=f.grant)
    assert schema['properties']['artifacts']['maxItems'] == 0


@pytest.mark.parametrize('mutation', ['other-job','role','artifact','validation','failed','collected-output','collected-artifact'])
def test_terminal_protocol_and_collection_mismatch_refuse(fixture, monkeypatch, mutation):
    f = fixture
    kwargs, receipts, paths, _ = terminal_fixture(f, monkeypatch)
    if mutation == 'other-job': kwargs['output']['job_id'] = 'JOB-other'
    if mutation == 'role': kwargs['output']['role_result'] = {}
    if mutation == 'artifact': kwargs['output']['artifacts'] = [{'path':'write.txt'}]
    if mutation == 'validation': kwargs['output']['validations'] = [{'argv':['true'],'exit_code':0}]
    if mutation == 'failed': kwargs['output']['status'] = 'FAILED'
    if mutation == 'collected-output': receipts[0]['collection']['result']['structured_output']['summary'] = 'other'
    if mutation == 'collected-artifact': receipts[0]['collection']['result']['artifact_manifest'] = [{'path':'write.txt'}]
    if mutation.startswith('collected-'):
        paths[0].write_text(json.dumps(receipts[0])); paths[0].chmod(0o600)
        if mutation == 'collected-output': kwargs['output'] = dict(kwargs['output'], summary='original')
    with pytest.raises(s.SupervisorError):
        f.supervisor._direct_native_terminal_payload(**kwargs)


def test_private_receipt_foreign_mode_refuses(fixture, monkeypatch):
    kwargs, _, paths, _ = terminal_fixture(fixture, monkeypatch)
    paths[2].chmod(0o644)
    with pytest.raises(s.SupervisorError):
        fixture.supervisor._direct_native_terminal_payload(**kwargs)


@pytest.mark.parametrize('outcome', [None, 'unknown-claim-shape'])
def test_missing_or_unknown_claim_never_reaches_launch(fixture, monkeypatch, outcome):
    f = fixture
    monkeypatch.setattr(f.runtime.jobs, 'direct_native_provenance', lambda _: {}, raising=False)
    monkeypatch.setattr(f.runtime.attempts, 'claim_job', lambda *a, **k: outcome)
    async def never(*a, **k):
        raise AssertionError('unqualified outcome reached launch')
    monkeypatch.setattr(f.supervisor, '_start_claimed_job', never)
    with pytest.raises(s.SupervisorError):
        asyncio.run(f.supervisor.start_direct_native_job(f.job.job_id, access=object()))


def test_direct_commission_missing_source_refuses_but_legacy_stays_optional(fixture, monkeypatch):
    f = fixture
    monkeypatch.setattr(s, '_dialogue_source_from_root_creation', lambda *a, **k: None)
    with pytest.raises(s.SupervisorError, match='lost its admitted commission'):
        s.verify_commission_for_job(f.runtime, f.job, None)
    legacy = dataclasses.replace(f.job, constraints={})
    assert s.verify_commission_for_job(f.runtime, legacy, None) is None


def test_direct_commission_keeps_exact_digest_verification(fixture, monkeypatch):
    f = fixture
    raw = b'# Immutable direct research commission\n'
    ref = SimpleNamespace(repository='mastermindx-market-intelligence/Mastermind',
                          commit='a'*40, path='research/direct.md',
                          content_sha256=__import__('hashlib').sha256(raw).hexdigest())
    source = SimpleNamespace(commission_ref=ref)
    monkeypatch.setattr(s, '_dialogue_source_from_root_creation', lambda *a, **k: source)
    monkeypatch.setattr(s, '_verify_commission_workspace', lambda *a: None)
    monkeypatch.setattr(s, '_commission_local_resolution', lambda *a, **k:
        s._CommissionLocalResolution(state=s._CommissionLocalState.AVAILABLE, blob_oid='b'*40))
    monkeypatch.setattr(s, '_read_local_commission_blob', lambda *a: raw)
    verified = s.verify_commission_for_job(f.runtime, f.job, f.root)
    assert verified.content == raw
    ref.content_sha256 = 'f'*64
    with pytest.raises(s.SupervisorError, match='digest differs'):
        s.verify_commission_for_job(f.runtime, f.job, f.root)


def test_current_access_is_rechecked_after_preparation_before_adapter_start(fixture, monkeypatch):
    f = fixture
    workspace = f.root / 'workspace'; workspace.mkdir(mode=0o700)
    job = dataclasses.replace(f.job, worktree=str(workspace))
    monkeypatch.setattr(f.supervisor, '_job', lambda _: job)
    f.supervisor.runs_root = f.root / 'runs'
    f.supervisor.shared_run_gid = None
    f.supervisor._product_acceptance_review_owner = None
    monkeypatch.setattr(f.supervisor, '_effective_grant', lambda *a: f.grant)
    monkeypatch.setattr(f.supervisor, '_validate_execution_profile', lambda *a: None)
    monkeypatch.setattr(f.supervisor, 'verified_commission', lambda *a: None)
    monkeypatch.setattr(f.supervisor, 'materialize_commission', lambda *a, **k: None)
    monkeypatch.setattr(f.supervisor, '_launch_spec', lambda *a: SimpleNamespace(prompt='inert'))
    monkeypatch.setattr(f.supervisor, '_enrich_spec_with_canary_claim', lambda spec, job: spec)
    monkeypatch.setattr(f.supervisor, '_reviewed_role_prompt_suffix', lambda *a: '')
    seen = []
    access = object()
    def deny(runtime, job_id, attempt_id, actual):
        assert runtime is f.runtime
        assert actual is access
        assert job_id == f.job.job_id and attempt_id == f.lease.attempt.attempt_id
        assert (f.supervisor._run_dir(attempt_id) / 'input' / 'worker-prompt.txt').is_file()
        seen.append('late-current-access')
        raise s.SupervisorError('current access expired during preparation')
    monkeypatch.setattr(Runtime, 'require_direct_native_launch_access', deny, raising=False)
    monkeypatch.setattr(f.supervisor, '_seal_terminal_assignment', lambda **kw: seen.append('sealed-refusal'))
    monkeypatch.setattr(f.supervisor, '_fail_claim', lambda *a: seen.append('failed-original-claim'))
    class Adapter:
        async def start(self, *a, **k):
            raise AssertionError('expired current access reached provider')
    f.supervisor.adapter = Adapter()
    with pytest.raises(s.SupervisorError, match='current access expired'):
        asyncio.run(f.supervisor._start_claimed_job(job.job_id, f.lease, _direct_native_access=access))
    assert seen == ['late-current-access', 'sealed-refusal', 'failed-original-claim']


def test_direct_missing_profile_cannot_take_legacy_unprofiled_path(fixture):
    with pytest.raises(s.SupervisorError, match='requires its sealed execution profile'):
        fixture.supervisor._validate_execution_profile(fixture.job, fixture.lease, fixture.grant)
