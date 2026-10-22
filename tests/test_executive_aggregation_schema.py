"""Frozen aggregation producers and the supervisor's persisted selection seam.

Constructor/recovery tests use immutable Job/Attempt stubs and a controlled
handoff reader, real schema files, and serialized recovery bindings. Launch
tests use real Runtime admission/dispatch and immutable handoffs, stopping at
a counted fake adapter boundary. Neither family claims process adoption or
provider execution proof.
"""
from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from control_plane.executive_orchestration_result import (
    OrchestrationResultError,
    _role_body_schema,
    canonical_digest,
    orchestration_result_schema,
    validate_envelope,
)
from control_plane.executive_supervisor import (
    ExecutiveSupervisor,
    SupervisorError,
    worker_result_schema,
)
from control_plane.worker_execution_contract import (
    BinaryAttestation,
    OrchestrationLaunchSpec,
    WorkerProcessRef,
    WorkerRecoveryBinding,
)


V1 = "mastermind.aggregation_result/v1"
V2 = "mastermind.aggregation_result/v2"
LEGACY_DIGEST = "7a042278d90f4d3e477c5f9d4c51a8553c64ac53947a70ccb40e96fea55ca933"
GRANT_DIGEST = "a" * 64


def _aggregation(version=V1, count=1):
    body = {
        "schema_version": version,
        "root_job_id": "ROOT",
        "handoff_digest": "b" * 64,
        "policy_sha": "c" * 64,
        "plan_attempt_id": "PLAN-ATT",
        "plan_digest": "d" * 64,
        "revisions": [
            {
                "ordinal": i,
                "plan_step_id": f"STEP-{i}",
                "current_job_id": f"WORK-{i}",
                "current_attempt_id": f"ATT-{i}",
                "current_result_digest": "e" * 64,
                "repair_round": 0,
                "review_required": False,
                "qualifying_review_job_id": None,
                "qualifying_review_attempt_id": None,
                "qualifying_review_result_digest": None,
            }
            for i in range(count)
        ],
        "aggregate_summary": "Retained child results",
        "evidence_digests": [],
    }
    if version == V2:
        body["coordinator_job_id"] = "AGG"
    return body


def _envelope(version=V1, count=1):
    return {
        "schema_version": "mastermind.executive_orchestration_result/v1",
        "job_id": "AGG",
        "run_id": "AGG-ATT",
        "worker_id": "worker-1",
        "role": "aggregation",
        "status": "COMPLETED",
        "role_result": _aggregation(version, count),
        "summary": "Complete",
        "current_state": "Retained",
        "next_actions": [],
        "errors": [],
        "validations": [],
    }


def test_default_aggregation_schema_preserves_exact_legacy_digest():
    schema = orchestration_result_schema("aggregation")
    assert canonical_digest(schema) == LEGACY_DIGEST
    assert schema == orchestration_result_schema(
        "aggregation", aggregation_schema_version=V1
    )
    assert schema["properties"]["role_result"] == _role_body_schema("aggregation")
    Draft202012Validator(schema).validate(_envelope())
    assert list(Draft202012Validator(schema).iter_errors(_envelope(V2)))


def test_explicit_v2_is_one_closed_envelope_and_rejects_v1():
    schema = orchestration_result_schema("aggregation", aggregation_schema_version=V2)
    body = schema["properties"]["role_result"]
    assert body == _role_body_schema("aggregation", aggregation_schema_version=V2)
    assert "oneOf" not in body
    assert body["additionalProperties"] is False
    validator = Draft202012Validator(schema)
    validator.validate(_envelope(V2, 16))
    assert list(validator.iter_errors(_envelope(V1)))
    for change in ("missing_coordinator", "unknown_field", "seventeenth"):
        bad = _envelope(V2)
        if change == "missing_coordinator":
            del bad["role_result"]["coordinator_job_id"]
        elif change == "unknown_field":
            bad["role_result"]["authority"] = "WRITE_BRANCH"
        else:
            bad = _envelope(V2, 17)
        assert list(validator.iter_errors(bad)), change


def test_v1_refuses_nested_fields_and_expanded_revision_limit():
    validator = Draft202012Validator(orchestration_result_schema("aggregation"))
    validator.validate(_envelope(V1, 8))
    extra = _envelope()
    extra["role_result"]["coordinator_job_id"] = "COORD"
    assert list(validator.iter_errors(extra))
    assert list(validator.iter_errors(_envelope(V1, 9)))


@pytest.mark.parametrize("version", [V1, V2])
def test_selected_envelope_also_passes_typed_identity_validation(version):
    value = _envelope(version)
    if version == V1:
        value["job_id"] = value["role_result"]["root_job_id"]
    expected = dict(expected_job_id=value["job_id"], expected_run_id=value["run_id"],
                    expected_worker_id=value["worker_id"], expected_role="aggregation",
                    expected_root_job_id=value["role_result"]["root_job_id"])
    assert validate_envelope(value, **expected) == value
    bad = copy.deepcopy(value)
    bad["role_result"]["coordinator_job_id" if version == V2 else "root_job_id"] = "OTHER"
    with pytest.raises(OrchestrationResultError):
        validate_envelope(bad, **expected)


@pytest.mark.parametrize("version", [None, True, [], "mastermind.aggregation_result/v3"])
@pytest.mark.parametrize("producer", [_role_body_schema, orchestration_result_schema])
def test_unknown_aggregation_selector_refuses_without_fallback(producer, version):
    with pytest.raises(OrchestrationResultError):
        producer("aggregation", aggregation_schema_version=version)


@pytest.mark.parametrize("role", ["plan", "work", "review", "repair"])
@pytest.mark.parametrize("producer", [_role_body_schema, orchestration_result_schema])
def test_v2_selector_cannot_widen_another_role(producer, role):
    with pytest.raises(OrchestrationResultError):
        producer(role, aggregation_schema_version=V2)


@pytest.mark.parametrize("version", [V1, V2])
def test_worker_result_schema_forwards_the_explicit_selector(version):
    schema = worker_result_schema(
        job_id="AGG", run_id="AGG-ATT", worker_id="worker-1",
        effective_grant_digest=GRANT_DIGEST, orchestration_role="aggregation",
        root_job_id="ROOT", aggregation_schema_version=version,
    )
    assert schema["x-mastermind-effective-grant-digest"] == GRANT_DIGEST
    validator = Draft202012Validator(schema)
    validator.validate(_envelope(version))
    assert list(validator.iter_errors(_envelope(V2 if version == V1 else V1)))
    wrong_root = _envelope(version)
    wrong_root["role_result"]["root_job_id"] = "OTHER"
    assert list(validator.iter_errors(wrong_root))


def test_worker_default_is_legacy_and_nonaggregation_v2_is_refused():
    kwargs = dict(job_id="AGG", run_id="AGG-ATT", worker_id="worker-1",
                  effective_grant_digest=GRANT_DIGEST, orchestration_role="aggregation")
    schema = worker_result_schema(**kwargs)
    assert list(Draft202012Validator(schema).iter_errors(_envelope(V2)))
    with pytest.raises(OrchestrationResultError):
        worker_result_schema(**{**kwargs, "orchestration_role": "work"},
                             aggregation_schema_version=V2)


@pytest.mark.parametrize("version", [None, True, [], V2, V2 + "-unknown"])
def test_regular_worker_cannot_select_an_aggregation_producer(version):
    with pytest.raises(SupervisorError):
        worker_result_schema(job_id="WORK", run_id="ATT", worker_id="worker-1",
                             aggregation_schema_version=version)


@dataclass(frozen=True)
class _Job:
    job_id: str = "AGG"
    orchestration_role: str = "aggregation"
    root_job_id: str = "ROOT"
    worktree: str = ""
    requested_authorities: tuple = ("READ",)
    allowed_write_paths: tuple = ()
    constraints: object = None


@dataclass(frozen=True)
class _Attempt:
    attempt_id: str = "AGG-ATT"
    worker_id: str = "worker-1"
    job_id: str = "AGG"
    effective_grant_digest: str = GRANT_DIGEST
    pid: int = 42420
    pgid: int = 42420
    process_start_identity: str = "start-fixture"
    boot_id: str = "boot-fixture"
    provider_session_id: str = "retained-session"
    stdout_path: str = "stdout"
    stderr_path: str = "stderr"
    result_path: str = "result"
    launch_metadata: object = None


class _Handoffs:
    def __init__(self, value):
        self.value = value
        self.reads = []

    def get_cycle_handoff(self, job_id):
        self.reads.append(job_id)
        return copy.deepcopy(self.value)


def _supervisor(tmp_path, handoff):
    supervisor = ExecutiveSupervisor.__new__(ExecutiveSupervisor)
    supervisor.runtime = SimpleNamespace(jobs=_Handoffs(handoff))
    supervisor.shared_run_gid = None
    supervisor.runs_root = tmp_path / "runs"
    # Illustrative contradictory attribute; this is not a service-config reader
    # or proof of real service reconfiguration. The controlled handoff is the
    # only runtime input available to this constructor seam.
    supervisor.service_config = {"aggregate_result_schema": V1 if handoff and handoff.get("aggregate_result_schema") == V2 else V2}
    return supervisor


@pytest.mark.parametrize("version", [V1, V2])
def test_write_schema_uses_persisted_handoff_version(tmp_path, version):
    supervisor = _supervisor(tmp_path, {"aggregate_result_schema": version})
    job, attempt = _Job(), _Attempt()
    path = supervisor._write_schema(tmp_path / "run", job=job, attempt=attempt,
                                    effective_grant={"authorities": ["READ"], "write_paths": []})
    schema = json.loads(path.read_text())
    validator = Draft202012Validator(schema)
    validator.validate(_envelope(version))
    assert list(validator.iter_errors(_envelope(V2 if version == V1 else V1)))
    assert supervisor.runtime.jobs.reads == [job.job_id]


@pytest.mark.parametrize("handoff", [None, {}, {"aggregate_result_schema": V2 + "-unknown"}])
def test_invalid_handoff_refuses_before_creating_run_directory(tmp_path, handoff):
    supervisor = _supervisor(tmp_path, handoff)
    run_dir = tmp_path / "run"
    with pytest.raises(SupervisorError, match="aggregation producer schema"):
        supervisor._write_schema(run_dir, job=_Job(), attempt=_Attempt(),
                                 effective_grant={"authorities": ["READ"], "write_paths": []})
    assert not run_dir.exists()


def test_handoff_selection_refuses_an_attempt_from_another_job(tmp_path):
    supervisor = _supervisor(tmp_path, {"aggregate_result_schema": V2})
    with pytest.raises(SupervisorError, match="aggregation producer"):
        supervisor._write_schema(tmp_path / "run", job=_Job(),
                                 attempt=replace(_Attempt(), job_id="OTHER"),
                                 effective_grant={"authorities": ["READ"], "write_paths": []})
    assert not (tmp_path / "run").exists()


def _recovery_fixture(tmp_path, monkeypatch, selected):
    supervisor = _supervisor(tmp_path, {"aggregate_result_schema": selected})
    grant = {"authorities": ["READ"], "write_paths": []}
    run_dir = supervisor._run_dir("AGG-ATT")
    input_dir = run_dir / "input"
    input_dir.mkdir(parents=True)
    prompt_path = input_dir / "worker-prompt.txt"
    prompt_path.write_text("Retained immutable prompt")
    prompt_path.chmod(0o600)
    schema_path = input_dir / "worker-result.schema.json"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    job = _Job(worktree=str(workspace), constraints={"base_sha": "b" * 40})
    spec = OrchestrationLaunchSpec(
        run_id="AGG-ATT", job_id="AGG", worker_id="worker-1", workspace_path=workspace,
        run_dir=run_dir, prompt=prompt_path.read_text(), result_schema_path=schema_path,
        authorities=("READ",), expected_base_sha="b" * 40,
        effective_grant_digest=GRANT_DIGEST, isolation_manifest_sha256="f" * 64,
    )
    binary = BinaryAttestation("fixture", "fixture", "fixture", "c" * 64,
                               None, 1, 1, 1, 0o700, 501, 20, 1)
    ref = WorkerProcessRef("AGG-ATT", 42420, 42420, "start-fixture", "boot-fixture",
                           "nonce", "retained-session", "stdout", "stderr", "result",
                           "2026-10-11T00:00:00Z", binary, "b" * 40)
    binding = WorkerRecoveryBinding.bind(adapter_id="fixture", spec=spec,
                                         process_ref=ref, prompt_path=prompt_path)
    attestation = {"process_identity": {
        "pid": ref.pid, "pgid": ref.pgid, "session_id": ref.session_id,
        "start_identity": ref.process_start_identity, "boot_id": ref.boot_session_id,
        "effective_uid": ref.effective_uid, "effective_gid": ref.effective_gid,
        "real_uid": ref.real_uid, "real_gid": ref.real_gid,
    }, "isolation_manifest_sha256": spec.isolation_manifest_sha256}
    attempt = _Attempt(launch_metadata={"worker_recovery_binding": binding.to_dict(),
                                       "launch_attestation": attestation})
    monkeypatch.setattr(supervisor, "_job", lambda _job_id: job)
    monkeypatch.setattr(supervisor, "_effective_grant", lambda _job, _attempt: grant)
    supervisor.require_complete_launch_attestation = False
    return supervisor, job, attempt, schema_path


@pytest.mark.parametrize("selected", [V1, V2])
def test_recovery_retains_selected_producer_and_refuses_schema_drift(tmp_path, monkeypatch, selected):
    supervisor, job, attempt, schema_path = _recovery_fixture(tmp_path, monkeypatch, selected)
    schema = worker_result_schema(
        job_id=job.job_id, run_id=attempt.attempt_id, worker_id=attempt.worker_id,
        effective_grant_digest=GRANT_DIGEST, orchestration_role="aggregation",
        root_job_id=job.root_job_id, aggregation_schema_version=selected,
    )
    schema_path.write_text(json.dumps(schema))
    _binding, recovered, grant = supervisor._validated_recovery_binding(attempt)
    assert recovered.run_id == attempt.attempt_id
    assert grant["authorities"] == ["READ"]
    schema_path.write_text(json.dumps(worker_result_schema(
        job_id=job.job_id, run_id=attempt.attempt_id, worker_id=attempt.worker_id,
        effective_grant_digest=GRANT_DIGEST, orchestration_role="aggregation",
        root_job_id=job.root_job_id, aggregation_schema_version=V2 if selected == V1 else V1,
    )))
    with pytest.raises(SupervisorError, match="aggregation producer schema"):
        supervisor._validated_recovery_binding(attempt)


@pytest.mark.parametrize("corruption", ["missing", "invalid_json", "bound_job", "boolean_type"])
def test_recovery_refuses_missing_malformed_or_rebound_schema(tmp_path, monkeypatch, corruption):
    supervisor, job, attempt, schema_path = _recovery_fixture(tmp_path, monkeypatch, V1)
    if corruption == "invalid_json":
        schema_path.write_text("{")
    elif corruption in {"bound_job", "boolean_type"}:
        schema = worker_result_schema(
            job_id="OTHER" if corruption == "bound_job" else job.job_id,
            run_id=attempt.attempt_id, worker_id=attempt.worker_id,
            effective_grant_digest=GRANT_DIGEST, orchestration_role="aggregation",
            root_job_id=job.root_job_id,
        )
        if corruption == "boolean_type":
            schema["additionalProperties"] = 0
        schema_path.write_text(json.dumps(schema))
    with pytest.raises(SupervisorError, match="aggregation producer schema"):
        supervisor._validated_recovery_binding(attempt)


class _ProviderStartReached(BaseException):
    """Deliberate test boundary; no provider process was started."""


class _CountingAdapter:
    def __init__(self):
        self.start_calls = []

    async def start(self, spec):
        self.start_calls.append(spec)
        schema = json.loads(spec.result_schema_path.read_text())
        assert schema["properties"]["role_result"]["properties"]["schema_version"] == {"const": V2}
        raise _ProviderStartReached


def _real_handoff(tmp_path, *, version=V2):
    """Reuse actual hierarchy transitions and immutable Runtime evidence."""
    from control_plane.ceo_intent import submit_intent
    from control_plane.executive_runtime import Runtime
    from tests.test_executive_os_phase1fc import _register, _v2_intent, _plan_body, _complete_ohf_role
    from tests.test_executive_coo_hierarchy import admit, finish_leaf

    runtime = Runtime.at(tmp_path / "runtime")
    _register(runtime)
    workspace_root = tmp_path / "workspaces"
    workspace = workspace_root / "aggregate"
    workspace.mkdir(parents=True)
    intent = _v2_intent(business_impact="routine")
    intent["execution_contract"]["worktree"] = str(workspace)
    receipt = submit_intent(runtime, intent, workspace_root=workspace_root)
    root = runtime.jobs.get_job(receipt["job_id"])
    if version == V2:
        child, = admit(runtime, root)
    else:
        planner = runtime.jobs.create_cycle_planner(root.job_id,
            command_id=f"coo-cycle:{root.job_id}:create-planner:0")
        dispatch = runtime.attempts.dispatch_cycle_job(planner.job_id,
            command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
            worker_id="worker-1")
        body = _plan_body()
        body.update(root_job_id=root.job_id, plan_attempt_id=dispatch.attempt.attempt_id)
        body["steps"][0]["allowed_write_paths"] = []
        _complete_ohf_role(runtime, dispatch, body, identity_seed=1001)
        child, = runtime.jobs.admit_cycle_plan(root.job_id,
            command_id=f"coo-cycle:{root.job_id}:admit-plan:{dispatch.attempt.attempt_id}")
    finish_leaf(runtime, child)
    runtime.jobs.create_cycle_handoff(root.job_id,
        command_id=f"coo-cycle:{root.job_id}:aggregation-handoff:1")
    handoff = runtime.jobs.get_cycle_handoff(root.job_id)
    assert handoff["aggregate_result_schema"] == version
    if version == V2:
        assert handoff["coordinator_job_id"] == root.job_id
    return runtime, root, handoff


@pytest.mark.parametrize("drift", [False, True])
def test_start_cycle_job_checks_real_v2_handoff_before_adapter_start(tmp_path, monkeypatch, drift):
    """Real dispatch/schema/spec path, stopped at the fake provider boundary.

    Fixture OHF completions establish the actual immutable V2 handoff. No
    provider is launched, so complete launch attestation and process persistence
    remain outside this proof; negative cleanup is independently stubbed.
    """
    runtime, root, handoff = _real_handoff(tmp_path)
    adapter = _CountingAdapter()
    supervisor = ExecutiveSupervisor(
        runtime, adapter, runs_root=tmp_path / "runs", inspector=SimpleNamespace(),
        require_complete_launch_attestation=False,
    )
    if drift:
        original_enrich = supervisor._enrich_spec_with_canary_claim

        def corrupt_after_spec_construction(spec, job):
            selected = original_enrich(spec, job)
            wrong = worker_result_schema(
                job_id=job.job_id, run_id=spec.run_id, worker_id=spec.worker_id,
                effective_grant_digest=spec.effective_grant_digest,
                orchestration_role="aggregation", root_job_id=job.root_job_id,
                aggregation_schema_version=V1,
            )
            spec.result_schema_path.write_text(json.dumps(wrong))
            return selected

        monkeypatch.setattr(supervisor, "_enrich_spec_with_canary_claim", corrupt_after_spec_construction)
        monkeypatch.setattr(supervisor, "_seal_terminal_assignment", lambda **_kwargs: None)
        monkeypatch.setattr(supervisor, "_fail_claim", lambda *_args: None)

    command = f"coo-cycle:{root.job_id}:dispatch:{root.job_id}:attempt:1"
    if drift:
        with pytest.raises(SupervisorError) as refusal:
            asyncio.run(supervisor.start_cycle_job(root.job_id, command_id=command))
        assert adapter.start_calls == []
        assert "aggregation producer schema differs" in str(refusal.value)
    else:
        with pytest.raises(_ProviderStartReached):
            asyncio.run(supervisor.start_cycle_job(root.job_id, command_id=command))
        assert len(adapter.start_calls) == 1
        spec = adapter.start_calls[0]
        schema = json.loads(spec.result_schema_path.read_text())
        keys = set(_aggregation(V2)["revisions"][0])
        value = _envelope(V2)
        value.update(job_id=root.job_id, run_id=spec.run_id, worker_id=spec.worker_id)
        value["role_result"].update(
            **{key: handoff[key] for key in ("root_job_id", "handoff_digest", "policy_sha", "plan_attempt_id", "plan_digest")},
            coordinator_job_id=root.job_id,
            revisions=[{key: revision[key] for key in keys} for revision in handoff["revisions"]],
        )
        Draft202012Validator(schema).validate(value)
        assert validate_envelope(value, expected_job_id=root.job_id,
            expected_run_id=spec.run_id, expected_worker_id=spec.worker_id,
            expected_role="aggregation", expected_root_job_id=root.root_job_id) == value
        wrong = copy.deepcopy(value)
        wrong["role_result"]["schema_version"] = V1
        del wrong["role_result"]["coordinator_job_id"]
        assert list(Draft202012Validator(schema).iter_errors(wrong))
    assert runtime.jobs.get_cycle_handoff(root.job_id) == handoff


def test_real_v1_handoff_survives_restart_with_current_default_policy_v2(tmp_path, monkeypatch):
    from control_plane.executive_coo_policy import CooCyclePolicy
    from control_plane.executive_runtime import Runtime

    runtime, root, handoff = _real_handoff(tmp_path, version=V1)
    dispatch = runtime.attempts.dispatch_cycle_job(root.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{root.job_id}:attempt:1",
        worker_id="worker-1")
    supervisor = ExecutiveSupervisor(runtime, _CountingAdapter(),
        runs_root=tmp_path / "runs", inspector=SimpleNamespace(),
        require_complete_launch_attestation=False)
    job = runtime.jobs.get_job(root.job_id)
    attempt = runtime.attempts.get_attempt(dispatch.attempt.attempt_id)
    grant = supervisor._effective_grant(job, attempt)
    retained_path = supervisor._write_schema(supervisor._run_dir(attempt.attempt_id),
        job=job, attempt=attempt, effective_grant=grant)
    retained = json.loads(retained_path.read_text())

    reopened = Runtime.at(tmp_path / "runtime")
    original_load = CooCyclePolicy.load

    def current_default_v2(cls, path=None, *, version=2):
        return original_load(path, version=version)

    monkeypatch.setattr(CooCyclePolicy, "load", classmethod(current_default_v2))
    assert CooCyclePolicy.load().schema_version == 2
    assert CooCyclePolicy.for_digest(handoff["policy_sha"]).schema_version == 1
    assert reopened.jobs.get_cycle_handoff(root.job_id) == handoff
    restarted = ExecutiveSupervisor(reopened, _CountingAdapter(),
        runs_root=tmp_path / "runs", inspector=SimpleNamespace(),
        require_complete_launch_attestation=False)
    same_job = reopened.jobs.get_job(root.job_id)
    same_attempt = reopened.attempts.get_attempt(attempt.attempt_id)
    same_grant = restarted._effective_grant(same_job, same_attempt)
    restarted._validate_aggregation_schema(job=same_job, attempt=same_attempt,
        effective_grant=same_grant, schema_path=retained_path)
    rebuilt_path = restarted._write_schema(tmp_path / "rebuilt-input",
        job=same_job, attempt=same_attempt, effective_grant=same_grant)
    assert json.loads(rebuilt_path.read_text()) == retained
    assert retained["properties"]["role_result"]["properties"]["schema_version"] == {"const": V1}
    retained_path.write_text(json.dumps(worker_result_schema(
        job_id=same_job.job_id, run_id=same_attempt.attempt_id, worker_id=same_attempt.worker_id,
        effective_grant_digest=same_attempt.effective_grant_digest,
        orchestration_role="aggregation", root_job_id=same_job.root_job_id,
        aggregation_schema_version=V2,
    )))
    with pytest.raises(SupervisorError, match="aggregation producer schema differs"):
        restarted._validate_aggregation_schema(job=same_job, attempt=same_attempt,
            effective_grant=same_grant, schema_path=retained_path)
    assert restarted.adapter.start_calls == []
