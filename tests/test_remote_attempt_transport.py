from __future__ import annotations

from pathlib import Path

import pytest

from control_plane.executive_runtime import Runtime
from control_plane.remote_attempt_transport import (
    REMOTE_RECOVERY_OPERATIONS,
    REMOTE_WORKER_OPERATIONS,
    RemoteAttemptTransportError,
    RemoteTransportPurpose,
    RemoteWorkerHostBinding,
    build_attempt_bound_worker_fleet,
    resolve_remote_attempt_transport,
)
from control_plane.remote_worker_transport import BrokerTransportBinding
from control_plane.worker_adapter import WorkerExecutionAdapter
from control_plane.worker_execution_contract import WorkerLaunchSpec


HOST_A = "host-" + "a" * 64
HOST_B = "host-" + "b" * 64
WORKER = "remote-codex-01"
QUOTA = "remote"
PROVIDER = "codex"


def _join(host_ref: str = HOST_A) -> dict:
    return {
        "schema": "mastermind.executive_capacity_join/v1",
        "host_ref": host_ref,
        "capacity_capability_id": "codex-remote-capacity",
        "provider_capacity_schema": "mastermind.provider_capacity.v1",
        "worker_source_config_digest": "c" * 64,
    }


def _claimed_runtime(tmp_path: Path, *, host_ref: str = HOST_A):
    runtime = Runtime.at(tmp_path / "runtime")
    runtime.workers.register_worker(
        WORKER,
        provider=PROVIDER,
        account_label="fixture-remote",
        worker_type="fixture",
        capabilities=["research"],
        quota_classes={
            QUOTA: {
                "capabilities": ["research"],
                "metadata": {"capacity_join": _join(host_ref)},
            }
        },
    )
    job = runtime.jobs.create_job(
        "bounded remote transport proof",
        requested_authorities=["READ"],
        attempt_limit=1,
    )
    lease = runtime.attempts.claim_job(
        job.job_id,
        worker_id=WORKER,
        quota_class=QUOTA,
        lease_owner="remote-transport-test",
    )
    assert lease is not None
    return runtime, job, lease


def _host_binding(
    tmp_path: Path,
    *,
    host_ref: str = HOST_A,
    worker_id: str = WORKER,
) -> RemoteWorkerHostBinding:
    paths = {}
    for name in ("ca.pem", "client.pem", "client.key"):
        path = tmp_path / name
        path.write_bytes(b"fixture")
        paths[name] = path
    return RemoteWorkerHostBinding(
        host_ref=host_ref,
        worker_id=worker_id,
        transport=BrokerTransportBinding(
            endpoint=("remote.example.test", 7443),
            ca_path=paths["ca.pem"],
            client_cert_path=paths["client.pem"],
            client_key_path=paths["client.key"],
            expected_server_fingerprint="d" * 64,
        ),
        worker_user="_mastermind_remote_codex_01",
        worker_uid=451,
        worker_gid=451,
        secret_canary_verdict={"passed": True, "worker_id": worker_id},
    )


def _spec(tmp_path: Path, *, run_id: str, job_id: str) -> WorkerLaunchSpec:
    return WorkerLaunchSpec(
        run_id=run_id,
        job_id=job_id,
        worker_id=WORKER,
        workspace_path=tmp_path / "workspace",
        run_dir=tmp_path / "run",
        prompt="bounded job",
        result_schema_path=tmp_path / "run" / "schema.json",
    )


def test_launch_resolves_only_the_already_claimed_worker_and_host(tmp_path: Path) -> None:
    runtime, job, lease = _claimed_runtime(tmp_path)
    calls = []

    def source(host_ref: str, worker_id: str):
        calls.append((host_ref, worker_id))
        return _host_binding(tmp_path, host_ref=host_ref, worker_id=worker_id)

    resolved = resolve_remote_attempt_transport(
        runtime,
        job_id=job.job_id,
        attempt_id=lease.attempt.attempt_id,
        binding_source=source,
    )

    assert calls == [(HOST_A, WORKER)]
    assert resolved.purpose is RemoteTransportPurpose.LAUNCH
    assert resolved.host_ref == HOST_A
    assert resolved.worker_id == WORKER
    assert resolved.quota_class == QUOTA
    assert resolved.provider == PROVIDER
    assert resolved.client.identity == {
        "host_ref": HOST_A,
        "job_id": job.job_id,
        "attempt_id": lease.attempt.attempt_id,
        "worker_id": WORKER,
        "operation_id": lease.attempt.attempt_id,
    }
    assert resolved.client.allowed_operations == REMOTE_WORKER_OPERATIONS

    fleet = build_attempt_bound_worker_fleet(resolved)
    assert isinstance(fleet, WorkerExecutionAdapter)
    assert fleet.worker_ids == (WORKER,)

    bound = resolved.endpoint.bind_launch_spec(
        _spec(
            tmp_path,
            run_id=lease.attempt.attempt_id,
            job_id=job.job_id,
        )
    )
    assert bound.worker_id == WORKER
    assert bound.worker_user == "_mastermind_remote_codex_01"
    assert bound.expected_worker_uid == 451
    assert bound.expected_worker_gid == 451
    assert dict(bound.secret_canary_verdict) == {
        "passed": True,
        "worker_id": WORKER,
    }


@pytest.mark.parametrize(
    ("host_ref", "worker_id"),
    [(HOST_B, WORKER), (HOST_A, "remote-codex-02")],
)
def test_root_binding_cannot_redirect_capacity_identity(
    tmp_path: Path, host_ref: str, worker_id: str
) -> None:
    runtime, job, lease = _claimed_runtime(tmp_path)

    def source(_host_ref: str, _worker_id: str):
        return _host_binding(tmp_path, host_ref=host_ref, worker_id=worker_id)

    with pytest.raises(RemoteAttemptTransportError) as raised:
        resolve_remote_attempt_transport(
            runtime,
            job_id=job.job_id,
            attempt_id=lease.attempt.attempt_id,
            binding_source=source,
        )
    assert raised.value.code == "HOST_BINDING_MISMATCH"


def test_invalid_root_managed_worker_principal_is_sanitized(tmp_path: Path) -> None:
    runtime, job, lease = _claimed_runtime(tmp_path)

    def source(host_ref: str, worker_id: str):
        binding = _host_binding(tmp_path, host_ref=host_ref, worker_id=worker_id)
        return RemoteWorkerHostBinding(
            host_ref=binding.host_ref,
            worker_id=binding.worker_id,
            transport=binding.transport,
            worker_user=binding.worker_user,
            worker_uid=0,
            worker_gid=binding.worker_gid,
            secret_canary_verdict=binding.secret_canary_verdict,
        )

    with pytest.raises(RemoteAttemptTransportError) as raised:
        resolve_remote_attempt_transport(
            runtime,
            job_id=job.job_id,
            attempt_id=lease.attempt.attempt_id,
            binding_source=source,
        )
    assert raised.value.code == "HOST_BINDING_MISMATCH"
    assert "worker_uid" not in str(raised.value)


def test_local_unbound_capacity_never_becomes_remote_transport(tmp_path: Path) -> None:
    runtime, job, lease = _claimed_runtime(tmp_path, host_ref="local-unbound")
    called = False

    def source(_host_ref: str, _worker_id: str):
        nonlocal called
        called = True
        return _host_binding(tmp_path)

    with pytest.raises(RemoteAttemptTransportError) as raised:
        resolve_remote_attempt_transport(
            runtime,
            job_id=job.job_id,
            attempt_id=lease.attempt.attempt_id,
            binding_source=source,
        )
    assert raised.value.code == "CAPACITY_UNAVAILABLE"
    assert called is False


def test_claim_movement_during_host_resolution_refuses_before_client_return(
    tmp_path: Path,
) -> None:
    runtime, job, lease = _claimed_runtime(tmp_path)

    def source(host_ref: str, worker_id: str):
        runtime.attempts.heartbeat_attempt(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )
        return _host_binding(tmp_path, host_ref=host_ref, worker_id=worker_id)

    with pytest.raises(RemoteAttemptTransportError) as raised:
        resolve_remote_attempt_transport(
            runtime,
            job_id=job.job_id,
            attempt_id=lease.attempt.attempt_id,
            binding_source=source,
        )
    assert raised.value.code == "STATE_MOVED"


def test_recovery_resolution_cannot_relaunch_the_attempt(tmp_path: Path) -> None:
    runtime, job, lease = _claimed_runtime(tmp_path)

    resolved = resolve_remote_attempt_transport(
        runtime,
        job_id=job.job_id,
        attempt_id=lease.attempt.attempt_id,
        purpose=RemoteTransportPurpose.RECOVERY,
        binding_source=lambda host_ref, worker_id: _host_binding(
            tmp_path, host_ref=host_ref, worker_id=worker_id
        ),
    )

    assert resolved.client.allowed_operations == REMOTE_RECOVERY_OPERATIONS
    assert "start" not in resolved.client.allowed_operations


def test_missing_host_binding_is_zero_effect_typed_refusal(tmp_path: Path) -> None:
    runtime, job, lease = _claimed_runtime(tmp_path)

    with pytest.raises(RemoteAttemptTransportError) as raised:
        resolve_remote_attempt_transport(
            runtime,
            job_id=job.job_id,
            attempt_id=lease.attempt.attempt_id,
            binding_source=lambda _host_ref, _worker_id: None,
        )
    assert raised.value.code == "HOST_BINDING_UNAVAILABLE"
    assert "remote.example" not in str(raised.value)


def test_wrong_job_or_attempt_identity_never_reselects_another_worker(tmp_path: Path) -> None:
    runtime, job, lease = _claimed_runtime(tmp_path)
    source_calls = []

    def source(host_ref: str, worker_id: str):
        source_calls.append((host_ref, worker_id))
        return _host_binding(tmp_path, host_ref=host_ref, worker_id=worker_id)

    with pytest.raises(RemoteAttemptTransportError):
        resolve_remote_attempt_transport(
            runtime,
            job_id="JOB-DOES-NOT-EXIST",
            attempt_id=lease.attempt.attempt_id,
            binding_source=source,
        )
    with pytest.raises(RemoteAttemptTransportError):
        resolve_remote_attempt_transport(
            runtime,
            job_id=job.job_id,
            attempt_id="ATT-DOES-NOT-EXIST",
            binding_source=source,
        )
    assert source_calls == []
