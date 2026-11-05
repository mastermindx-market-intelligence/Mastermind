"""Local Control integration boundaries; no admission or remote launch proof.

The exact-class adapter below is deliberately uninitialized inert DATA. It has
no source, endpoint, lease or transport and cannot launch a worker. These tests
exercise only Supervisor composition refusal and real temporary Control files.
"""
from types import SimpleNamespace
import os
import stat
from unittest.mock import Mock

import pytest

from control_plane.executive_paid_fabric_adapter import CanonicalPaidFabricWorkerAdapter
from control_plane.executive_runtime import AttemptStatus, Runtime
from control_plane.executive_supervisor import (
    CleanupPolicy, ExecutiveSupervisor, ReconcileStatus, SupervisorError,
)


def composition(tmp_path, **overrides):
    runtime = Runtime.at(tmp_path)
    adapter = object.__new__(CanonicalPaidFabricWorkerAdapter)
    adapter.runtime = runtime
    adapter.inspector = object()
    options = dict(worker_user='remote-runner', worker_uid=1000, worker_gid=1000,
        shared_run_gid=None, require_complete_launch_attestation=True,
        cleanup_policy=CleanupPolicy.FABRIC_PROCESS_GROUP)
    options.update(overrides)
    return runtime, adapter, options


@pytest.mark.parametrize('change', [
    {'shared_run_gid':1000}, {'secret_canary_verdict':{}},
    {'subscription_canary_binding_id':'other'},
    {'subscription_canary_claim_provider':lambda *_: {}},
    {'worker_user':None}, {'worker_uid':None}, {'worker_gid':None},
    {'worker_uid':True}, {'worker_gid':True},
    {'require_complete_launch_attestation':False},
    {'cleanup_policy':CleanupPolicy.DEDICATED_UID},
])
def test_paid_composition_refuses_local_identity_or_shared_group_aliases(tmp_path, change):
    runtime, adapter, options = composition(tmp_path, **change)
    with pytest.raises(SupervisorError):
        ExecutiveSupervisor(runtime, adapter, **options)


def test_remote_identity_never_chowns_control_schema(tmp_path, monkeypatch):
    runtime, adapter, options = composition(tmp_path)
    supervisor = ExecutiveSupervisor(runtime, adapter, **options)
    def forbidden_chown(*_args, **_kwargs):
        pytest.fail('remote worker identity must not chown Control paths')
    monkeypatch.setattr(os, 'chown', forbidden_chown)
    monkeypatch.setattr(supervisor, '_result_schema', lambda **_: {'type':'object'})
    run_dir = tmp_path/'real-local-control-run'
    schema = supervisor._write_schema(run_dir,
        job=SimpleNamespace(orchestration_role='work'), attempt=SimpleNamespace())
    assert schema.stat().st_uid == os.geteuid()
    assert stat.S_IMODE(run_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(schema.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(schema.stat().st_mode) == 0o600
    assert supervisor.worker_uid == 1000
    assert supervisor.shared_run_gid is None


def test_unbound_paid_restart_never_probes_terminates_refunds_or_replays(tmp_path, monkeypatch):
    runtime, adapter, options = composition(tmp_path)
    supervisor = ExecutiveSupervisor(runtime, adapter, **options)
    attempt = SimpleNamespace(attempt_id='ATT-unit', job_id='JOB-unit',
        status=AttemptStatus.CLAIMED, execution_mode='SEALED_WORKER', launch_metadata={})
    monkeypatch.setattr(runtime.attempts, 'list_attempts', lambda: [attempt])
    adapter.presence = Mock(side_effect=AssertionError('unexpected presence'))
    adapter.terminate = Mock(side_effect=AssertionError('unexpected termination'))
    adapter.cleanup_unbound_run = Mock(side_effect=AssertionError('unexpected cleanup'))
    outcomes = supervisor.reconcile_restart()
    assert len(outcomes) == 1
    assert outcomes[0].status is ReconcileStatus.IDENTITY_AMBIGUOUS
    assert 'same-owner reconciliation' in outcomes[0].error
    assert attempt.status is AttemptStatus.CLAIMED and attempt.launch_metadata == {}
    adapter.presence.assert_not_called()
    adapter.terminate.assert_not_called()
    adapter.cleanup_unbound_run.assert_not_called()
