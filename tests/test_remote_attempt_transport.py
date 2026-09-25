from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from control_plane.executive_runtime import AttemptStatus, Runtime
from control_plane.executive_supervisor import ExecutiveSupervisor
from control_plane.remote_attempt_transport import (
    REMOTE_RECOVERY_OPERATIONS,
    AttemptBoundRemoteWorkerAdapter,
    REMOTE_WORKER_OPERATIONS,
    RemoteAttemptTransportError,
    RemoteTransportPurpose,
    RemoteWorkerHostBinding,
    build_attempt_bound_worker_fleet,
    resolve_remote_attempt_transport,
)
from control_plane.remote_worker_transport import BrokerTransportBinding
from control_plane.worker_adapter import WorkerExecutionAdapter
from control_plane.worker_execution_contract import (
    BinaryAttestation,
    WorkerLaunchSpec,
    WorkerProcessRef,
    WorkerRecoveryBinding,
)


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


def _process_ref(run_id: str) -> WorkerProcessRef:
    return WorkerProcessRef(
        run_id=run_id,
        pid=7001,
        pgid=7001,
        process_start_identity="start-1",
        boot_session_id="boot-1",
        launch_nonce="nonce-1",
        provider_session_id="provider-session-1",
        stdout_path="/tmp/remote.stdout",
        stderr_path="/tmp/remote.stderr",
        result_path="/tmp/remote.result.json",
        started_at="2026-09-25T00:00:00Z",
        binary=BinaryAttestation(
            path="/usr/local/bin/codex",
            real_path="/usr/local/bin/codex",
            version="fixture",
            sha256="a" * 64,
            team_identifier=None,
            size=1,
            device=1,
            inode=1,
            mode=0o755,
            uid=0,
            gid=0,
            mtime_ns=1,
        ),
        base_sha="b" * 40,
        session_id=7001,
        effective_uid=451,
        effective_gid=451,
        real_uid=451,
        real_gid=451,
    )


class _FakeAttemptFleet:
    adapter_id = "remote-worker-broker-fleet"

    def __init__(
        self,
        worker_id: str,
        *,
        process_ref: WorkerProcessRef,
        fail_start: bool = False,
    ) -> None:
        self.worker_ids = (worker_id,)
        self.process_ref = process_ref
        self.fail_start = fail_start
        self.start_calls = 0
        self.reattach_bindings = []
        self.cleanup_calls = []
        self.last_spec = None

    async def start(self, spec: WorkerLaunchSpec) -> WorkerProcessRef:
        self.start_calls += 1
        self.last_spec = spec
        if self.fail_start:
            raise RuntimeError("simulated ambiguous start")
        return self.process_ref

    def reattach(
        self, spec: WorkerLaunchSpec, binding: WorkerRecoveryBinding
    ) -> WorkerProcessRef:
        self.last_spec = spec
        self.reattach_bindings.append(binding)
        return binding.process_ref

    async def status(self, ref: WorkerProcessRef):
        return "RUNNING"

    async def collect_result(self, ref: WorkerProcessRef):
        raise AssertionError("not used in facade contract test")

    async def cancel(self, ref: WorkerProcessRef, reason: str):
        raise AssertionError("not used in facade contract test")

    async def run_validation_argv(
        self,
        spec: WorkerLaunchSpec,
        argv,
        *,
        timeout_seconds: float = 300.0,
    ):
        raise AssertionError("not used in facade contract test")

    def launch_attestation(self, ref: WorkerProcessRef):
        if ref != self.process_ref:
            raise AssertionError("wrong process")
        return {"schema_version": "fixture"}

    def uid_sweep_receipt(self, subject):
        return {"reason": "fixture", "passed": True}

    async def cleanup_unbound_run(self, run_id: str):
        self.cleanup_calls.append(run_id)
        return {"reason": "fixture", "passed": True}


@pytest.mark.asyncio
async def test_executive_supervisor_consumes_facade_only_after_runtime_claim(
    tmp_path: Path,
) -> None:
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
                "metadata": {"capacity_join": _join()},
            }
        },
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    job = runtime.jobs.create_job(
        "supervisor remote carrier proof",
        worktree=str(workspace),
        requested_authorities=["READ"],
        attempt_limit=1,
    )
    built = []

    def fleet_factory(resolution):
        fleet = _FakeAttemptFleet(
            resolution.worker_id,
            process_ref=_process_ref(resolution.attempt_id),
        )
        built.append((resolution, fleet))
        return fleet

    adapter = AttemptBoundRemoteWorkerAdapter(
        runtime,
        lambda host_ref, worker_id: _host_binding(
            tmp_path, host_ref=host_ref, worker_id=worker_id
        ),
        fleet_factory=fleet_factory,
    )
    supervisor = ExecutiveSupervisor(
        runtime,
        adapter,
        runs_root=tmp_path / "runs",
        process_controller=adapter.process_controller,
    )

    assert built == []
    active = await supervisor.start_job(job.job_id)

    assert len(built) == 1
    resolution, fleet = built[0]
    assert resolution.job_id == job.job_id
    assert resolution.attempt_id == active.lease.attempt.attempt_id
    assert resolution.worker_id == active.lease.attempt.worker_id == WORKER
    assert resolution.purpose is RemoteTransportPurpose.LAUNCH
    assert fleet.start_calls == 1

    current = runtime.attempts.get_attempt(resolution.attempt_id)
    assert current is not None
    assert current.status is AttemptStatus.CHECKPOINTED
    recovery = current.launch_metadata["worker_recovery_binding"]
    assert recovery["adapter_id"] == AttemptBoundRemoteWorkerAdapter.adapter_id
    assert recovery["process_ref"]["run_id"] == resolution.attempt_id


@pytest.mark.asyncio
async def test_static_facade_resolves_only_after_claim_and_sticks_ambiguous_start(
    tmp_path: Path,
) -> None:
    runtime, job, lease = _claimed_runtime(tmp_path)
    spec = _spec(
        tmp_path, run_id=lease.attempt.attempt_id, job_id=job.job_id
    )
    ref = _process_ref(spec.run_id)
    built = []

    def fleet_factory(resolution):
        fleet = _FakeAttemptFleet(
            resolution.worker_id, process_ref=ref, fail_start=True
        )
        built.append((resolution, fleet))
        return fleet

    adapter = AttemptBoundRemoteWorkerAdapter(
        runtime,
        lambda host_ref, worker_id: _host_binding(
            tmp_path, host_ref=host_ref, worker_id=worker_id
        ),
        fleet_factory=fleet_factory,
    )
    assert isinstance(adapter, WorkerExecutionAdapter)
    assert built == []

    with pytest.raises(RuntimeError, match="simulated ambiguous start"):
        await adapter.start(spec)

    assert len(built) == 1
    resolution, fleet = built[0]
    assert resolution.purpose is RemoteTransportPurpose.LAUNCH
    assert resolution.worker_id == WORKER
    assert resolution.host_ref == HOST_A

    # The carrier is pinned before the ambiguous provider/network return. The
    # Supervisor cleanup path therefore cannot re-resolve to another host.
    receipt = await adapter.cleanup_unbound_run(spec.run_id)
    assert receipt["passed"] is True
    assert fleet.cleanup_calls == [spec.run_id]
    assert len(built) == 1


def test_static_facade_recovery_uses_recovery_only_transport(
    tmp_path: Path,
) -> None:
    runtime, job, lease = _claimed_runtime(tmp_path)
    spec = _spec(
        tmp_path, run_id=lease.attempt.attempt_id, job_id=job.job_id
    )
    input_dir = spec.run_dir / "input"
    input_dir.mkdir(parents=True)
    prompt_path = input_dir / "worker-prompt.txt"
    prompt_path.write_text(spec.prompt, encoding="utf-8")
    prompt_path.chmod(0o600)
    ref = _process_ref(spec.run_id)
    outer = WorkerRecoveryBinding.bind(
        adapter_id=AttemptBoundRemoteWorkerAdapter.adapter_id,
        spec=spec,
        process_ref=ref,
        prompt_path=prompt_path,
    )
    built = []

    def fleet_factory(resolution):
        fleet = _FakeAttemptFleet(resolution.worker_id, process_ref=ref)
        built.append((resolution, fleet))
        return fleet

    adapter = AttemptBoundRemoteWorkerAdapter(
        runtime,
        lambda host_ref, worker_id: _host_binding(
            tmp_path, host_ref=host_ref, worker_id=worker_id
        ),
        fleet_factory=fleet_factory,
    )
    recovered = adapter.reattach(spec, outer)

    assert recovered == ref
    assert len(built) == 1
    resolution, fleet = built[0]
    assert resolution.purpose is RemoteTransportPurpose.RECOVERY
    assert "start" not in resolution.client.allowed_operations
    assert len(fleet.reattach_bindings) == 1
    assert fleet.reattach_bindings[0].adapter_id == fleet.adapter_id
    assert fleet.reattach_bindings[0].process_ref == ref


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


def test_resolution_is_runtime_read_only(tmp_path: Path) -> None:
    runtime, job, lease = _claimed_runtime(tmp_path)

    def counts():
        with runtime.store.read() as connection:
            return tuple(
                connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                for table in (
                    "workers",
                    "worker_quota_classes",
                    "jobs",
                    "attempts",
                    "events",
                )
            )

    before = counts()
    resolve_remote_attempt_transport(
        runtime,
        job_id=job.job_id,
        attempt_id=lease.attempt.attempt_id,
        binding_source=lambda host_ref, worker_id: _host_binding(
            tmp_path, host_ref=host_ref, worker_id=worker_id
        ),
    )
    assert counts() == before


def test_current_fleet_consumer_refuses_unaccepted_provider_adapter(
    tmp_path: Path,
) -> None:
    runtime, job, lease = _claimed_runtime(tmp_path)
    resolved = resolve_remote_attempt_transport(
        runtime,
        job_id=job.job_id,
        attempt_id=lease.attempt.attempt_id,
        binding_source=lambda host_ref, worker_id: _host_binding(
            tmp_path, host_ref=host_ref, worker_id=worker_id
        ),
    )
    with pytest.raises(RemoteAttemptTransportError) as raised:
        build_attempt_bound_worker_fleet(
            dataclasses.replace(resolved, provider="anthropic")
        )
    assert raised.value.code == "PROVIDER_UNSUPPORTED"


@pytest.mark.parametrize("field,value", [("job_id", True), ("attempt_id", 7), ("job_id", " JOB-1")])
def test_resolution_refuses_noncanonical_caller_identity(
    tmp_path: Path, field: str, value: object
) -> None:
    runtime, job, lease = _claimed_runtime(tmp_path)
    kwargs = {
        "runtime": runtime,
        "job_id": job.job_id,
        "attempt_id": lease.attempt.attempt_id,
        "binding_source": lambda host_ref, worker_id: _host_binding(
            tmp_path, host_ref=host_ref, worker_id=worker_id
        ),
    }
    kwargs[field] = value
    with pytest.raises(RemoteAttemptTransportError) as raised:
        resolve_remote_attempt_transport(**kwargs)
    assert raised.value.code == "INVALID_INPUT"


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
