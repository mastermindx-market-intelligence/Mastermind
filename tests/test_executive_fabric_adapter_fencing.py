"""Inert SQLite lease takeover regressions; never contacts Fabric or providers."""
import asyncio
import copy
import dataclasses

import pytest

from control_plane import executive_fabric_adapter as module
from control_plane.executive_runtime import StateConflict
from control_plane.executive_worker_broker import BrokerStateError
from control_plane.worker_execution_contract import WorkerRecoveryBinding
from test_executive_fabric_adapter import _fixture, result


class RetainedClient:
    def __init__(self):
        self.calls = []
        self.retained = None
        self.during_request = None

    def response(self, operation, payload):
        self.calls.append(operation)
        if operation == "start":
            self.retained = result(payload)
            ref = self.retained["process_ref"]
            ref["run_id"] = payload["launch_spec"]["run_id"]
            for name, suffix in (("stdout_path", "stdout"), ("stderr_path", "stderr"),
                                 ("result_path", "result")):
                ref[name] = payload["launch_spec"]["run_dir"] + "/" + suffix
            return copy.deepcopy(self.retained)
        if self.during_request is not None:
            self.during_request()
        outer = {key: copy.deepcopy(self.retained[key]) for key in
                 ("adapter_id", "binding", "physical_binding_sha256")}
        ref = copy.deepcopy(self.retained["process_ref"])
        if operation == "status" and "start_request_sha256" in payload:
            outer.update(start_state="EXISTS", start_result=copy.deepcopy(self.retained))
        elif operation == "status":
            outer["run"] = dict(run_id=ref["run_id"], status="RUNNING", process_ref=ref)
        elif operation == "cancel":
            outer["cancellation"] = dict(run_id=ref["run_id"], reason=payload["reason"],
                signal_sent=True, escalated_to_sigkill=False, already_exited=False,
                finished_at="2026-10-11T10:01:00Z")
        elif operation == "validate":
            outer["validation"] = dict(argv=payload["argv"], exit_code=0,
                stdout_sha256="a" * 64, stdout_size=0, stderr_sha256="b" * 64,
                stderr_size=0, timed_out=False, error=None)
        elif operation == "collect":
            outer["collection"] = dict(process_ref=ref, stdout_sha256="a" * 64,
                stderr_sha256="b" * 64, result_sha256="c" * 64,
                result=dict(job_id=self.spec.job_id, run_id=ref["run_id"],
                    worker_id=self.spec.worker_id, status="SUCCEEDED", structured_output=None,
                    artifact_manifest=[], git_manifest={}, usage={},
                    provider_session_id=ref["provider_session_id"], exit_code=0,
                    started_at=ref["started_at"], finished_at="2026-10-11T10:01:00Z", error=None))
        return outer

    async def request(self, operation, payload, **kwargs):
        return self.response(operation, payload)

    def request_sync(self, operation, payload, **kwargs):
        return self.response(operation, payload)


def started(tmp_path, monkeypatch):
    client = RetainedClient()
    runtime, job, lease, adapter, spec, payload = _fixture(tmp_path, monkeypatch, client)
    run_dir = tmp_path / "run"
    workspace = tmp_path / "workspace"
    spec = dataclasses.replace(spec, run_dir=run_dir, workspace_path=workspace,
                               result_schema_path=run_dir / "schema.json")
    payload["launch_spec"].update(run_dir=str(run_dir), workspace_path=str(workspace),
                                 result_schema_path=str(spec.result_schema_path))
    payload["validation_commands"] = [["/usr/bin/true"]]
    client.spec = spec
    ref = asyncio.run(adapter.start(spec, lease=lease))
    # Actual persisted Runtime process identity makes adoption lawful. No host
    # process exists; all effects are confined to this test's SQLite store.
    runtime.attempts.record_process(spec.run_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token, provider_session_id=ref.provider_session_id)
    runtime.attempts.mark_running(spec.run_id, fence_generation=lease.attempt.fence_generation,
                                 lease_token=lease.lease_token)
    return runtime, lease, adapter, spec, ref, client


def adopt(runtime, lease):
    return runtime.attempts.adopt_attempt(lease.attempt.attempt_id,
        expected_fence_generation=lease.attempt.fence_generation,
        lease_owner="successor-supervisor")


def test_assignment_identity_is_exact_original_pin_and_revalidates_fence(tmp_path, monkeypatch):
    from control_plane.broker_assignment_seal import digest
    from control_plane.executive_runtime import REMOTE_LAUNCH_IDENTITY_KEY
    runtime, lease, adapter, spec, ref, client = started(tmp_path, monkeypatch)
    identity = adapter.assignment_launch_identity(ref)
    assert digest(identity) == runtime.attempts.get_attempt(spec.run_id).launch_metadata[REMOTE_LAUNCH_IDENTITY_KEY]["sha256"]
    identity["request"]["binding"]["root_id"] = "foreign"
    assert adapter.assignment_launch_identity(ref)["request"]["binding"]["root_id"] != "foreign"
    adopt(runtime, lease)
    with pytest.raises(Exception, match="stale fence"):
        adapter.assignment_launch_identity(ref)


def invoke(adapter, spec, ref, operation):
    if operation == "validate":
        return adapter.run_validation_argv(spec, ("/usr/bin/true",))
    if operation == "cancel":
        return adapter.cancel(ref, "old supervisor request")
    if operation == "collect":
        return adapter.collect_result(ref)
    return adapter.status(ref)


@pytest.mark.parametrize("operation", ["cancel", "validate", "status", "collect"])
def test_old_facade_refuses_request_before_io_after_adoption(tmp_path, monkeypatch, operation):
    runtime, lease, adapter, spec, ref, client = started(tmp_path, monkeypatch)
    replacement = adopt(runtime, lease)
    assert replacement.attempt.fence_generation == lease.attempt.fence_generation + 1
    with pytest.raises(StateConflict, match="stale fence"):
        runtime.attempts.heartbeat_attempt(spec.run_id,
            fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token)
    with pytest.raises((StateConflict, BrokerStateError)):
        asyncio.run(invoke(adapter, spec, ref, operation))
    assert client.calls == ["start"]


@pytest.mark.parametrize("operation", ["cancel", "validate", "status", "collect"])
def test_old_facade_refuses_return_when_adopted_during_rpc(tmp_path, monkeypatch, operation):
    runtime, lease, adapter, spec, ref, client = started(tmp_path, monkeypatch)
    client.during_request = lambda: adopt(runtime, lease)
    with pytest.raises((StateConflict, BrokerStateError)):
        asyncio.run(invoke(adapter, spec, ref, operation))
    assert client.calls == ["start", operation]
    assert runtime.attempts.get_attempt(spec.run_id).fence_generation == 2


def recovery_binding(spec, ref):
    prompt = spec.run_dir / "input" / "prompt.txt"
    prompt.parent.mkdir(parents=True)
    prompt.write_text(spec.prompt)
    prompt.chmod(0o600)
    return WorkerRecoveryBinding.bind(adapter_id=module.ADAPTER_ID, spec=spec,
                                     process_ref=ref, prompt_path=prompt)


def fresh_adapter(runtime, original, client, monkeypatch):
    recovered = module.AttendedFabricWorkerAdapter(runtime, original.binding_source,
                                                   client_factory=lambda physical: client)
    monkeypatch.setattr(recovered, "_resolve", original._resolve)
    return recovered


def test_recovery_without_actual_adopter_lease_refuses_before_status(tmp_path, monkeypatch):
    runtime, lease, adapter, spec, ref, client = started(tmp_path, monkeypatch)
    adopt(runtime, lease)
    recovered = fresh_adapter(runtime, adapter, client, monkeypatch)
    with pytest.raises((StateConflict, BrokerStateError)):
        recovered.reattach(spec, recovery_binding(spec, ref))
    assert client.calls == ["start"]


def test_recovery_adopter_lease_is_status_only_and_old_token_is_refused(tmp_path, monkeypatch):
    runtime, lease, adapter, spec, ref, client = started(tmp_path, monkeypatch)
    replacement = adopt(runtime, lease)
    recovered = fresh_adapter(runtime, adapter, client, monkeypatch)
    binding = recovery_binding(spec, ref)
    with pytest.raises((StateConflict, BrokerStateError)):
        recovered.reattach(spec, binding, lease=lease)
    assert client.calls == ["start"]
    assert recovered.reattach(spec, binding, lease=replacement) == ref
    assert client.calls == ["start", "status"]
    assert asyncio.run(recovered.status(ref)).value == "RUNNING"
    assert client.calls == ["start", "status", "status"]


def test_recovery_refuses_adoption_during_status_reply(tmp_path, monkeypatch):
    runtime, lease, adapter, spec, ref, client = started(tmp_path, monkeypatch)
    replacement = adopt(runtime, lease)
    recovered = fresh_adapter(runtime, adapter, client, monkeypatch)
    client.during_request = lambda: adopt(runtime, replacement)
    with pytest.raises((StateConflict, BrokerStateError)):
        recovered.reattach(spec, recovery_binding(spec, ref), lease=replacement)
    assert client.calls == ["start", "status"]
    assert runtime.attempts.get_attempt(spec.run_id).fence_generation == 3


def test_current_owner_can_execute_durable_cancellation(tmp_path, monkeypatch):
    runtime, lease, adapter, spec, ref, client = started(tmp_path, monkeypatch)
    runtime.jobs.cancel_job(spec.job_id)
    receipt = asyncio.run(adapter.cancel(ref, "durable cancellation request"))
    assert receipt.signal_sent is True
    assert client.calls == ["start", "cancel"]
    with pytest.raises(BrokerStateError):
        asyncio.run(adapter.run_validation_argv(spec, ("/usr/bin/true",)))
    assert client.calls == ["start", "cancel"]
