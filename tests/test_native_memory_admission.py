"""Real temporary Runtime/opaque lease; no protected peer/Linux/provider claim.

The source locator is public correlation only. These tests deliberately do not
pretend that creating a Runtime or an intent enrolls a protected source owner.
"""
import copy
import dataclasses
import json

import pytest

from control_plane import native_memory_admission as admission
from control_plane.executive_runtime import Runtime
from test_remote_attempt_transport import WORKER, QUOTA, PROVIDER, _join


def locator():
    return {'schema': admission.SCHEMA, 'operation_id': 'original-memory-op',
        'intent': {'study_id': 'selected-study', 'root_id': 'native-original-root',
            'operator_run_id': 'native-operator', 'child_run_id': 'native-child'}}


@pytest.fixture
def claimed(tmp_path):
    runtime = Runtime.at(tmp_path/'runtime')
    runtime.workers.register_worker(WORKER, provider=PROVIDER, account_label='fixture-remote',
        worker_type='fixture', capabilities=['research'], quota_classes={QUOTA: {
            'capabilities': ['research'], 'metadata': {'capacity_join': _join()}}})
    job = runtime.jobs.create_job('Protected Memory claim integration fixture',
        requested_authorities=['READ'], constraints={'eligible_quota_classes': [QUOTA],
            'native_memory': locator()}, attempt_limit=1)
    lease = runtime.attempts.claim_job(job.job_id, worker_id=WORKER, quota_class=QUOTA,
        lease_owner='native-memory-fixture')
    assert lease is not None
    return runtime, job, lease


def test_real_runtime_current_token_and_native_locator_stay_distinct_without_effect(claimed):
    runtime, job, lease = claimed
    before = runtime.events.list_events()
    cap = admission.capture_memory_runtime_claim(runtime, lease)
    actual = admission.require_memory_runtime_claim(cap)
    assert actual == locator()
    assert actual['intent']['root_id'] != job.root_job_id
    assert actual['intent']['child_run_id'] != lease.attempt.attempt_id
    actual['intent']['child_run_id'] = 'changed-copy'
    assert admission.require_memory_runtime_claim(cap) == locator()
    assert lease.lease_token not in repr(cap)
    assert runtime.events.list_events() == before
    assert len(runtime.jobs.list_jobs()) == 1


@pytest.mark.parametrize('shape', ['dict', 'clone', 'subclass'])
def test_no_dto_clone_or_subclass_replaces_original_claim(claimed, shape):
    runtime, _, lease = claimed
    admission.capture_memory_runtime_claim(runtime, lease)
    if shape == 'dict': cap = locator()
    elif shape == 'clone': cap = object.__new__(admission.MemoryRuntimeClaim)
    else:
        class Foreign(admission.MemoryRuntimeClaim): pass
        cap = object.__new__(Foreign)
    with pytest.raises(admission.MemoryAdmissionRefused):
        admission.require_memory_runtime_claim(cap)


def test_wrong_private_token_and_foreign_runtime_cannot_capture(claimed, tmp_path):
    runtime, _, lease = claimed
    with pytest.raises(admission.MemoryAdmissionRefused):
        admission.capture_memory_runtime_claim(runtime, dataclasses.replace(lease, lease_token='forged'))
    foreign = Runtime.at(tmp_path/'foreign')
    with pytest.raises(admission.MemoryAdmissionRefused):
        admission.capture_memory_runtime_claim(foreign, lease)


@pytest.mark.parametrize('damage', ['native_root', 'participant', 'expired', 'job_state', 'write_authority'])
def test_current_owner_or_grant_drift_withholds_existing_claim(claimed, damage):
    runtime, job, lease = claimed
    cap = admission.capture_memory_runtime_claim(runtime, lease)
    with runtime.store.transaction() as con:
        if damage in {'native_root', 'participant'}:
            value = copy.deepcopy(job.constraints)
            if damage == 'native_root': value['native_memory']['intent']['root_id'] = 'other-native-root'
            else: value['native_memory']['intent']['operator_run_id'] = 'other-operator'
            con.execute('UPDATE jobs SET constraints_json=? WHERE job_id=?', (json.dumps(value), job.job_id))
        elif damage == 'expired':
            con.execute("UPDATE attempts SET lease_expires_at_ms=1 WHERE attempt_id=?", (lease.attempt.attempt_id,))
        elif damage == 'job_state':
            con.execute("UPDATE jobs SET status='CANCELLED' WHERE job_id=?", (job.job_id,))
        else:
            con.execute('UPDATE jobs SET requested_authorities_json=? WHERE job_id=?', (json.dumps(['READ', 'WRITE']), job.job_id))
    with pytest.raises(admission.MemoryAdmissionRefused):
        admission.require_memory_runtime_claim(cap)


@pytest.mark.parametrize('extra', ['role', 'slot', 'task_id', 'packet', 'authenticated', 'path', 'participant_binding_sha256'])
def test_retained_caller_selector_is_not_a_supported_source_intent(claimed, extra):
    runtime, job, lease = claimed
    value = copy.deepcopy(job.constraints)
    value['native_memory']['intent'][extra] = 'not-authority'
    with runtime.store.transaction() as con:
        con.execute('UPDATE jobs SET constraints_json=? WHERE job_id=?', (json.dumps(value), job.job_id))
    with pytest.raises(admission.MemoryAdmissionRefused):
        admission.capture_memory_runtime_claim(runtime, lease)


def test_job_writer_rejects_future_input_hash_before_creating_any_record(claimed):
    from control_plane.executive_runtime import StateConflict
    runtime, _, _ = claimed
    before = runtime.events.list_events()
    value = locator()
    value['intent']['participant_binding_sha256'] = 'c'*64
    with pytest.raises(StateConflict, match='native Memory intent constraint is invalid'):
        runtime.jobs.create_job('Not an admitted protected case', requested_authorities=['READ'],
            constraints={'native_memory': value})
    assert runtime.events.list_events() == before
    assert len(runtime.jobs.list_jobs()) == 1


def test_ordinary_job_constraint_normalization_does_not_gain_memory_mode(claimed):
    from control_plane.executive_runtime import _normalise_constraints
    assert _normalise_constraints({'eligible_quota_classes': [QUOTA]}) == {'eligible_quota_classes': [QUOTA]}


def test_current_policy_reversal_withholds_already_issued_runtime_claim(claimed, monkeypatch):
    from types import SimpleNamespace
    from control_plane.executive_authority import ExecutiveAuthorityPolicy
    runtime,_,lease=claimed
    cap=admission.capture_memory_runtime_claim(runtime,lease)
    monkeypatch.setattr(ExecutiveAuthorityPolicy,'load',lambda:SimpleNamespace(authorize=lambda *a,**k:SimpleNamespace(policy_sha256='f'*64)))
    with pytest.raises(admission.MemoryAdmissionRefused):admission.require_memory_runtime_claim(cap)
