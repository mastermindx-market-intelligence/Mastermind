"""Admitted-port typed gates and formally-owned connector conformance.

Fail-closed refusals below use scripted fixtures ONLY as refusal input --
never as production proof.  ``FormalOwner`` is a formally typed conformance
stand-in for the still-absent incumbent nonplanner execution owner: it proves
this connector binds complete owner-sealed evidence and recomputes every
trial through the canonical EVAL owners.  It is NOT live admission, a real
provider run, an installed port or a model-efficacy result.  The one real
local subprocess is the same fixed arithmetic laboratory program the native
recursion tests use; the missing nonplanner admission stays a typed
``MISSING_EXECUTION_OWNER`` gate until a genuine owner composition exists.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from control_plane.executive_authority import (
    PHASE1B_ALLOWED,
    PHASE1B_REQUIRED_DENIES,
    ExecutiveAuthorityPolicy,
)
from control_plane.executive_orchestration_result import (
    PLAN_SCHEMA_V1,
    RESULT_SCHEMA,
    RawRoleResultObservation,
    canonical_bytes,
)
from control_plane.executive_runtime import Attempt, AttemptStatus, Job, JobStatus
from scripts.agent_eval import contracts, store
from scripts.agent_eval.canonical import digest_value
from scripts.agent_eval.harness2_native import (
    Harness2ImportError,
    harness_digest,
    sha256_bytes,
)
from scripts.ohf.harness2_admitted_port import (
    GATE_SCHEMA,
    AdmittedHarness2Port,
    AdmittedPortGateError,
    AdmittedStageReceipt,
    ComparisonDeclaration,
    ExecutionObservation,
    StageAdmissionRequest,
    ValidatorSeal,
    stage_context_digest,
)
from scripts.ohf.harness2_recursion import Limits, _validate_trial, run_refinement
from tests.agent_eval_factories import (
    PROOF_ARTIFACT,
    PUBLIC_TOOL_SCHEMA_DIGEST_A,
    REPO_REF_BASE,
    build_baseline_configuration,
    build_baseline_scenario_fields,
)

BASE = {"AGENTS.md": b"Protected fixture: execute only the admitted task.\n",
        "scripts/total.py": b"numbers = (100, -20, 5)\nprint(sum(n for n in numbers if n > 0))\n"}
TASK = {"task_id": "signed-ledger", "domain": "accounting", "request": "Sum all signed amounts: 100, -20, 5."}
POLICY_SHA = "c" * 64
GRANT_SCHEMA = "mastermind.executive_effective_grant/v1"


# ---------------------------------------------------------------------------
# incumbent typed evidence construction (owner-side, conformance only)
# ---------------------------------------------------------------------------

def _policy() -> ExecutiveAuthorityPolicy:
    return ExecutiveAuthorityPolicy(
        path=Path("/dev/null"), sha256=POLICY_SHA, schema_version=1,
        allowed=frozenset(PHASE1B_ALLOWED), denied=frozenset(PHASE1B_REQUIRED_DENIES),
        scope_requirements={
            "WRITE_BRANCH": "assigned_workspace_and_declared_paths",
            "RUN_TESTS": "declared_argv_commands",
            "REQUEST_WORKER_LOGIN_CHECK": "current_attempt_assigned_worker_slot",
        },
    )


def _grant_digest(grant: dict) -> str:
    encoded = json.dumps(grant, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _work_job(worktree: str) -> Job:
    return Job(
        job_id="job-" + uuid4().hex, objective=TASK["request"], department="engineering",
        priority=1, status=JobStatus.COMPLETED, assigned_worker_id="worker-" + uuid4().hex,
        assigned_quota_class="quota-harness2-lab", authority_level="worker",
        branch="sol/manual-harness2-admitted-port-r1-20261030", worktree=worktree,
        checkpoint=None, result={"status": "COMPLETED"}, created_at="2026-08-26T00:00:00Z",
        updated_at="2026-08-26T00:00:05Z", constraints={}, current_attempt_id=None,
        requested_authorities=["READ", "WRITE_BRANCH", "RUN_TESTS"],
        authority_policy_hash=POLICY_SHA, allowed_write_paths=["harness2"],
        validation_commands=[["python3", "-B", "scripts/total.py"]],
        parent_job_id=None, root_job_id="root-" + uuid4().hex, depth=1,
        orchestration_role="work", plan_attempt_id=None, plan_digest=None, plan_step_id="step-1",
    )


def _planner_job(worktree: str) -> Job:
    job = _work_job(worktree)
    return replace(job, orchestration_role="plan", requested_authorities=["READ"],
                   allowed_write_paths=[], validation_commands=[], depth=0)


def _effective_grant(job: Job) -> dict:
    return {
        "schema_version": GRANT_SCHEMA,
        "authorities": list(job.requested_authorities),
        "write_paths": list(job.allowed_write_paths),
        "validation_argv": [list(argv) for argv in job.validation_commands],
        "policy_sha": job.authority_policy_hash,
        "job_id": job.job_id,
        "role": job.orchestration_role,
    }


def _attempt(job: Job) -> Attempt:
    grant = _effective_grant(job)
    return Attempt(
        attempt_id="attempt-" + uuid4().hex, job_id=job.job_id, attempt_number=1,
        worker_id=job.assigned_worker_id, quota_class=job.assigned_quota_class,
        status=AttemptStatus.COMPLETED, fence_generation=7, lease_owner="supervisor-conformance",
        lease_expires_at="2026-08-26T00:05:00Z", heartbeat_at="2026-08-26T00:01:00Z",
        checkpoint_sequence=0, checkpoint=None, result={"status": "COMPLETED"}, error=None,
        started_at="2026-08-26T00:00:00Z", finished_at="2026-08-26T00:00:05Z", version=3,
        authority_policy_hash=job.authority_policy_hash, pid=4321, pgid=4321,
        process_start_identity="pid-4321-boot-lab", boot_id="boot-lab",
        provider_session_id="provider-session-lab", stdout_path="/tmp/out", stderr_path="/tmp/err",
        result_path="/tmp/result", exit_code=0, launch_metadata={}, execution_mode="WORKER_V1",
        effective_grant=grant, effective_grant_digest=_grant_digest(grant),
    )


def _raw_observation(job: Job, attempt: Attempt, *, output_digest: str | None = None,
                     envelope_override: dict | None = None) -> RawRoleResultObservation:
    if envelope_override is not None:
        envelope = envelope_override
    elif job.orchestration_role == "work":
        envelope = {
            "schema_version": RESULT_SCHEMA, "job_id": job.job_id, "run_id": attempt.attempt_id,
            "worker_id": attempt.worker_id, "role": "work", "status": "COMPLETED",
            "role_result": {
                "schema_version": "mastermind.work_result/v1", "root_job_id": job.root_job_id,
                "plan_attempt_id": attempt.attempt_id, "plan_digest": "d" * 64,
                "plan_step_id": "step-1", "repair_round": 0,
                "artifacts": [{"path": "output/total.out",
                               "digest": output_digest or ("0" * 64)}],
                "evidence_digests": ["e" * 64],
            },
            "summary": "executed the staged candidate harness", "current_state": "done",
            "next_actions": [], "errors": [], "validations": [],
        }
    else:
        envelope = {
            "schema_version": RESULT_SCHEMA, "job_id": job.job_id, "run_id": attempt.attempt_id,
            "worker_id": attempt.worker_id, "role": "plan", "status": "COMPLETED",
            "role_result": {
                "schema_version": PLAN_SCHEMA_V1, "root_job_id": job.root_job_id,
                "plan_attempt_id": attempt.attempt_id,
                "steps": [{
                    "ordinal": 0, "step_id": "step-1", "objective": "improve the staged harness",
                    "business_impact": "routine", "review_required": False,
                    "requested_authorities": ["READ"], "allowed_write_paths": [],
                    "validation_ids": [], "attempt_limit": 1, "cost_class": "default",
                }],
            },
            "summary": "reasoned over the frozen stage context", "current_state": "done",
            "next_actions": [], "errors": [], "validations": [],
        }
    encoded = canonical_bytes(envelope).decode("utf-8")
    raw_bytes = encoded.encode("utf-8")
    return RawRoleResultObservation(
        attempt_id=attempt.attempt_id, session_epoch_id="epoch-lab",
        process_generation_id="generation-lab", turn_id="turn-" + uuid4().hex,
        provider_session_id=attempt.provider_session_id,
        provider_native_turn_id="native-turn-" + str(attempt.attempt_number),
        provider_turn_artifact_digest="f" * 64,
        canonical_result_json=encoded,
        canonical_result_digest=hashlib.sha256(raw_bytes).hexdigest(),
        canonical_result_byte_length=len(raw_bytes),
    )


def _observation(scenario: dict, output: bytes, tool_events: bytes, *, ordinal: int) -> ExecutionObservation:
    allowlist = scenario["source_policy"]["allowlist_artifacts"]
    return ExecutionObservation(
        model_served="gpt-5.1-codex", execution_surface="codex-app-server",
        execution_surface_version="1.0.0", provider="codex",
        fresh_process_observed=True, fresh_workspace_observed=True,
        fresh_session_observed=True, resume_used=False,
        observed_capability_ids=("read_file",),
        observed_tool_schema_digests=(PUBLIC_TOOL_SCHEMA_DIGEST_A,),
        observed_sources=(dict(allowlist[0]),),
        observed_network_destinations=(), dependency_degradations=(),
        effect_state="NO_EFFECT", cleanup_status="PROVEN", cleanup_proof=dict(PROOF_ARTIFACT),
        output_artifact_path="output/total.out",
        output_artifact_ref=REPO_REF_BASE + f"#harness2/output/{ordinal}.json",
        output_bytes=output,
        tool_events_artifact_ref=REPO_REF_BASE + f"#harness2/tool_events/{ordinal}.json",
        tool_events_bytes=tool_events,
        resources={"input_tokens": 10, "output_tokens": 20, "tool_calls": 0, "elapsed_ms": 5,
                   "provider_usage_ref": None, "estimated_marginal_cost": "0.01",
                   "cost_currency": "USD"},
        timing={"started_at": "2026-08-26T00:00:00Z", "completed_at": "2026-08-26T00:00:05Z",
                "monotonic_duration_ms": 5},
    )


def _payload(body: dict) -> str:
    return canonical_bytes(body).decode("utf-8")


def _candidates_digest(candidates: dict) -> str:
    return digest_value({key: sha256_bytes(raw) for key, raw in candidates.items()})


class FormalOwner:
    """Formally typed conformance owner; see the module docstring for limits.

    For ``execute`` it stages the candidate bundle in its own workspace and
    runs the fixed arithmetic lab program once, then seals the complete
    observation; for reasoning stages it seals a scripted proposal/selection/
    reflection bound to the exact attempt, native turn and context digest.
    """

    def __init__(self, root: Path, declaration: ComparisonDeclaration) -> None:
        self.declaration = declaration
        self.native = store.ArtifactStore(Path(root) / "eval")
        self.workspace = Path(root) / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.turns = 0
        self.requests: list[StageAdmissionRequest] = []
        self._policy = _policy()

    def admitted_stage_receipt(self, request: StageAdmissionRequest) -> AdmittedStageReceipt:
        self.requests.append(copy.deepcopy(request))
        self.turns += 1
        scenario = self.declaration.scenario
        worktree = str(self.workspace)
        if request.stage == "execute":
            job = _work_job(worktree)
            attempt = _attempt(job)
            job = replace(job, current_attempt_id=attempt.attempt_id)
            script = self.workspace / f"staged-{self.turns}.py"
            script.write_bytes(request.harness_files["scripts/total.py"])
            response = subprocess.run([sys.executable, "-B", str(script)],
                                      capture_output=True, timeout=10, check=True)
            output = response.stdout
            tool_events = json.dumps({"events": [{"turn": self.turns,
                                                  "staged_digest": request.harness_digest}]}
                                      ).encode("utf-8")
            raw = _raw_observation(job, attempt,
                                   output_digest=hashlib.sha256(output).hexdigest())
            decision = self._policy.authorize(
                job.requested_authorities, worktree=job.worktree,
                allowed_write_paths=job.allowed_write_paths,
                validation_commands=job.validation_commands)
            return AdmittedStageReceipt(
                attempt=attempt, job=job, raw=raw,
                payload_json=_payload({"attempt_id": attempt.attempt_id,
                                       "turn_id": raw.turn_id, "context_digest": None}),
                fence_generation=attempt.fence_generation, authority_decision=decision,
                observation=_observation(scenario, output, tool_events, ordinal=self.turns))
        job = _planner_job(worktree)
        attempt = _attempt(job)
        job = replace(job, current_attempt_id=attempt.attempt_id)
        raw = _raw_observation(job, attempt)
        if request.stage == "improve":
            current = copy.deepcopy(request.context["current_harness"])
            current["scripts/total.py"] = current["scripts/total.py"].replace(b" if n > 0", b"")
            body = {"proposal": {
                "files": {path: raw_bytes.decode("utf-8") for path, raw_bytes in current.items()},
                "notes": "Remove the positive-only filter; retain credits and debits.",
                "evidence_run_ids": [request.context["executions"][0]["run_id"]],
            }}
        elif request.stage == "select":
            body = {"candidates_digest": _candidates_digest(request.candidates),
                    "selection": sorted(request.candidates)[0]}
        elif request.stage == "reflect":
            body = {"reflection": {
                "claim": "The positive-only filter excluded a signed credit in this lab fixture.",
                "falsifier": "Replay the signed inputs and compare with the direct signed sum.",
                "so_what": "Keep negative as well as positive ledger amounts when adapting this helper.",
                "evidence_run_ids": [request.context["executions"][0]["run_id"],
                                     request.chosen["run_id"]],
            }}
        else:  # pragma: no cover - the stage set is closed
            body = {}
        payload = {"attempt_id": attempt.attempt_id, "turn_id": raw.turn_id,
                   # A genuine owner seals the digest of the context it actually
                   # received, recomputed here -- never the caller's claim.
                   "context_digest": (stage_context_digest(request.context)
                                      if request.context is not None else None),
                   **body}
        return AdmittedStageReceipt(attempt=attempt, job=job, raw=raw,
                                    payload_json=_payload(payload),
                                    fence_generation=attempt.fence_generation,
                                    authority_decision=None, observation=None)

    def retain_evaluation_documents(self, documents: tuple[dict, ...]) -> tuple:
        return tuple(self.native.create(document) for document in documents)


def _declaration(scenario, configuration) -> ComparisonDeclaration:
    return ComparisonDeclaration(
        scenario=scenario, baseline_configuration=configuration, experiment=None,
        validator=ValidatorSeal(validator_id="mastermind.eval_r0_finalizer.v1",
                                validator_version="1", validator_code_ref=REPO_REF_BASE,
                                validated_at="2026-08-26T00:00:10Z",
                                created_at="2026-08-26T00:00:11Z"),
        runner_id="mastermind.eval_r0_synthetic_runner.v1", runner_code_ref=REPO_REF_BASE,
        bundle_ref_namespace=REPO_REF_BASE + "#harness2/",
    )


def _documents():
    fields = build_baseline_scenario_fields()
    fields["objective"] = TASK["request"]
    scenario = contracts.build_scenario(fields)
    config = build_baseline_configuration()
    config.pop("schema")
    config.pop("configuration_digest")
    config["execution"].update(provider="codex", model_requested="gpt-5.1-codex",
                               execution_surface="codex-app-server")
    config["procedure"]["instruction_bundle"] = {
        "artifact_ref": REPO_REF_BASE + "#fixture/base.json", "digest": harness_digest(BASE)}
    configuration = contracts.build_configuration(config)
    return scenario, configuration


def _port(tmp_path: Path) -> tuple[AdmittedHarness2Port, FormalOwner, dict, dict]:
    scenario, configuration = _documents()
    declaration = _declaration(scenario, configuration)
    owner = FormalOwner(tmp_path, declaration)
    port = AdmittedHarness2Port(declaration=declaration, owner=owner)
    return port, owner, scenario, configuration


def _execute_request(harness: dict | None = None) -> StageAdmissionRequest:
    return StageAdmissionRequest(stage="execute", task=TASK, label="base1", kind=None,
                                 context_digest=None, context=None,
                                 harness_digest=harness_digest(harness or BASE),
                                 harness_files=copy.deepcopy(harness or BASE),
                                 candidates=None, chosen=None)


class MutatingOwner:
    """Wrap a formal owner; subclasses intercept exactly one sealed piece."""

    def __init__(self, inner: FormalOwner, mutate=None) -> None:
        self._inner = inner
        self._mutate = mutate

    def admitted_stage_receipt(self, request: StageAdmissionRequest) -> AdmittedStageReceipt:
        receipt = self._inner.admitted_stage_receipt(request)
        return self._mutate(receipt) if self._mutate is not None else receipt

    def retain_evaluation_documents(self, documents):
        return self._inner.retain_evaluation_documents(documents)


# ---------------------------------------------------------------------------
# 1. typed gates: missing owner / non-conforming owner / declaration
# ---------------------------------------------------------------------------

def test_missing_owner_is_a_typed_gate(tmp_path):
    scenario, configuration = _documents()
    with pytest.raises(AdmittedPortGateError) as excinfo:
        AdmittedHarness2Port(declaration=_declaration(scenario, configuration), owner=None)
    gate = excinfo.value
    assert gate.code == "MISSING_EXECUTION_OWNER"
    assert gate.to_dict()["schema"] == GATE_SCHEMA
    assert "nonplanner" in gate.to_dict()["detail"]


def test_owner_without_exact_seams_is_not_admitted(tmp_path):
    scenario, configuration = _documents()
    for bad in (object(), "supervisor", AdmittedStageReceipt):
        with pytest.raises(AdmittedPortGateError) as excinfo:
            AdmittedHarness2Port(declaration=_declaration(scenario, configuration), owner=bad)
        assert excinfo.value.code == "OWNER_NOT_ADMITTED"


def test_incomplete_declaration_is_refused(tmp_path):
    scenario, configuration = _documents()
    owner = FormalOwner(tmp_path, _declaration(scenario, configuration))
    declaration = _declaration(scenario, configuration)
    broken = replace(declaration, validator=replace(declaration.validator, validator_id=""))
    with pytest.raises(AdmittedPortGateError) as excinfo:
        AdmittedHarness2Port(declaration=broken, owner=owner)
    assert excinfo.value.code == "MISSING_EVAL_OWNER_DOCUMENTS"


# ---------------------------------------------------------------------------
# 2. per-stage binding gates (scripted fixtures as refusal input only)
# ---------------------------------------------------------------------------

def test_wrong_attempt_binding_is_refused(tmp_path):
    scenario, configuration = _documents()
    owner = FormalOwner(tmp_path, _declaration(scenario, configuration))
    other = _work_job(str(owner.workspace))
    def mutate(receipt):
        return replace(receipt, job=replace(receipt.job, job_id=other.job_id))
    port = AdmittedHarness2Port(declaration=owner.declaration,
                                owner=MutatingOwner(owner, mutate))
    with pytest.raises(AdmittedPortGateError) as excinfo:
        port.execute(TASK, "base1", BASE)
    assert excinfo.value.code == "WRONG_ATTEMPT_BINDING"


def test_stale_generation_is_refused(tmp_path):
    scenario, configuration = _documents()
    owner = FormalOwner(tmp_path, _declaration(scenario, configuration))
    def mutate(receipt):
        return replace(receipt, fence_generation=receipt.fence_generation + 1)
    port = AdmittedHarness2Port(declaration=owner.declaration,
                                owner=MutatingOwner(owner, mutate))
    with pytest.raises(AdmittedPortGateError) as excinfo:
        port.execute(TASK, "base1", BASE)
    assert excinfo.value.code == "STALE_ATTEMPT_GENERATION"
    assert owner.turns == 1  # the refusal consumed exactly one owner binding


def test_incomplete_attempt_is_refused(tmp_path):
    scenario, configuration = _documents()
    owner = FormalOwner(tmp_path, _declaration(scenario, configuration))
    def mutate(receipt):
        return replace(receipt, attempt=replace(receipt.attempt, status=AttemptStatus.RUNNING))
    port = AdmittedHarness2Port(declaration=owner.declaration,
                                owner=MutatingOwner(owner, mutate))
    with pytest.raises(AdmittedPortGateError) as excinfo:
        port.execute(TASK, "base1", BASE)
    assert excinfo.value.code == "ATTEMPT_NOT_COMPLETED"


def test_malformed_raw_role_result_is_refused(tmp_path):
    scenario, configuration = _documents()
    owner = FormalOwner(tmp_path, _declaration(scenario, configuration))
    def mutate(receipt):
        broken_envelope = {
            "schema_version": RESULT_SCHEMA, "job_id": receipt.job.job_id,
            "run_id": receipt.attempt.attempt_id, "worker_id": receipt.attempt.worker_id,
            "role": "work", "status": "COMPLETED",
            "role_result": {
                "schema_version": "mastermind.work_result/v1",
                "root_job_id": receipt.job.root_job_id,
                "plan_attempt_id": receipt.attempt.attempt_id, "plan_digest": "d" * 64,
                "plan_step_id": "step-1", "repair_round": 0,
                "artifacts": [{"path": "output/total.out", "digest": "0" * 64}],
                "evidence_digests": ["e" * 64],
            },
        }  # summary/current_state/next_actions/errors/validations deliberately absent
        return replace(receipt, raw=_raw_observation(receipt.job, receipt.attempt,
                                                     envelope_override=broken_envelope))
    port = AdmittedHarness2Port(declaration=owner.declaration,
                                owner=MutatingOwner(owner, mutate))
    with pytest.raises(AdmittedPortGateError) as excinfo:
        port.execute(TASK, "base1", BASE)
    assert excinfo.value.code == "RAW_ROLE_RESULT_MALFORMED"


def test_role_drift_between_job_and_envelope_is_refused(tmp_path):
    scenario, configuration = _documents()
    owner = FormalOwner(tmp_path, _declaration(scenario, configuration))
    def mutate(receipt):
        drifted_job = replace(receipt.job, orchestration_role="plan")
        return replace(receipt, job=drifted_job)
    port = AdmittedHarness2Port(declaration=owner.declaration,
                                owner=MutatingOwner(owner, mutate))
    with pytest.raises(AdmittedPortGateError) as excinfo:
        port.execute(TASK, "base1", BASE)
    assert excinfo.value.code == "RAW_ROLE_RESULT_MALFORMED"


def test_execute_refuses_a_planner_attempt(tmp_path):
    scenario, configuration = _documents()
    owner = FormalOwner(tmp_path, _declaration(scenario, configuration))
    def mutate(receipt):
        planner = owner.admitted_stage_receipt(replace(
            _execute_request(), stage="improve", context_digest=None,
            context=_reasoning_context()))
        payload = json.loads(planner.payload_json)
        payload["context_digest"] = None  # execute seals no context; isolate the role gate
        return replace(receipt, attempt=planner.attempt, job=planner.job, raw=planner.raw,
                       payload_json=_payload(payload),
                       authority_decision=None, observation=None)
    port = AdmittedHarness2Port(declaration=owner.declaration,
                                owner=MutatingOwner(owner, mutate))
    with pytest.raises(AdmittedPortGateError) as excinfo:
        port.execute(TASK, "base1", BASE)
    assert excinfo.value.code == "UNAUTHORIZED_ROLE_PROFILE"
    assert "planner" in excinfo.value.detail


def _reasoning_context() -> dict:
    return {"current_harness": copy.deepcopy(BASE), "common_base": copy.deepcopy(BASE),
            "executions": [{"label": "base1", "run_id": "run:conformance-1",
                            "output": b"105\n", "harness": copy.deepcopy(BASE), "notes": ""}]}


def test_reasoning_stage_refuses_a_work_role(tmp_path):
    scenario, configuration = _documents()
    owner = FormalOwner(tmp_path, _declaration(scenario, configuration))
    context = _reasoning_context()
    sealed = stage_context_digest(context)
    def mutate(receipt):
        work = owner.admitted_stage_receipt(_execute_request())
        payload = {"attempt_id": work.attempt.attempt_id, "turn_id": work.raw.turn_id,
                   "context_digest": sealed,
                   "proposal": {"files": {"scripts/total.py": "print(0)\n"}, "notes": "n",
                                "evidence_run_ids": ["run:1"]}}
        return replace(receipt, attempt=work.attempt, job=work.job, raw=work.raw,
                       payload_json=_payload(payload))
    port = AdmittedHarness2Port(declaration=owner.declaration,
                                owner=MutatingOwner(owner, mutate))
    with pytest.raises(AdmittedPortGateError) as excinfo:
        port.improve(TASK, "inv1", "invariant", context)
    assert excinfo.value.code == "UNAUTHORIZED_ROLE_PROFILE"


def test_missing_observation_is_refused(tmp_path):
    scenario, configuration = _documents()
    owner = FormalOwner(tmp_path, _declaration(scenario, configuration))
    port = AdmittedHarness2Port(declaration=owner.declaration,
                                owner=MutatingOwner(owner, lambda receipt: replace(receipt, observation=None)))
    with pytest.raises(AdmittedPortGateError) as excinfo:
        port.execute(TASK, "base1", BASE)
    assert excinfo.value.code == "EXECUTION_OBSERVATION_UNPROVEN"


def test_served_model_mismatch_is_refused(tmp_path):
    scenario, configuration = _documents()
    owner = FormalOwner(tmp_path, _declaration(scenario, configuration))
    def mutate(receipt):
        return replace(receipt, observation=replace(receipt.observation,
                                                    model_served="some-other-model"))
    port = AdmittedHarness2Port(declaration=owner.declaration,
                                owner=MutatingOwner(owner, mutate))
    with pytest.raises(AdmittedPortGateError) as excinfo:
        port.execute(TASK, "base1", BASE)
    assert excinfo.value.code == "MODEL_SERVED_MISMATCH"


def test_tainted_or_unknown_effect_is_refused(tmp_path):
    scenario, configuration = _documents()
    owner = FormalOwner(tmp_path, _declaration(scenario, configuration))
    for state in ("EFFECT_UNKNOWN", "EFFECT_KNOWN"):
        def mutate(receipt, state=state):
            return replace(receipt, observation=replace(receipt.observation, effect_state=state))
        port = AdmittedHarness2Port(declaration=owner.declaration,
                                    owner=MutatingOwner(owner, mutate))
        with pytest.raises(AdmittedPortGateError) as excinfo:
            port.execute(TASK, "base1", BASE)
        assert excinfo.value.code == "TAINTED_OR_UNKNOWN_EFFECT"


def test_unproven_cleanup_is_refused(tmp_path):
    scenario, configuration = _documents()
    owner = FormalOwner(tmp_path, _declaration(scenario, configuration))
    def mutate(receipt):
        return replace(receipt, observation=replace(receipt.observation, cleanup_status="UNPROVEN"))
    port = AdmittedHarness2Port(declaration=owner.declaration,
                                owner=MutatingOwner(owner, mutate))
    with pytest.raises(AdmittedPortGateError) as excinfo:
        port.execute(TASK, "base1", BASE)
    assert excinfo.value.code == "CLEANUP_UNPROVEN"


def test_output_bytes_outside_the_sealed_artifact_are_refused(tmp_path):
    scenario, configuration = _documents()
    owner = FormalOwner(tmp_path, _declaration(scenario, configuration))
    def mutate(receipt):
        return replace(receipt, observation=replace(receipt.observation,
                                                    output_bytes=b"tampered\n"))
    port = AdmittedHarness2Port(declaration=owner.declaration,
                                owner=MutatingOwner(owner, mutate))
    with pytest.raises(AdmittedPortGateError) as excinfo:
        port.execute(TASK, "base1", BASE)
    assert excinfo.value.code == "MISSING_IMMUTABLE_FILES"


def test_missing_or_binary_staged_files_never_reach_the_owner(tmp_path):
    port, owner, _scenario, _configuration = _port(tmp_path)
    with pytest.raises(AdmittedPortGateError) as excinfo:
        port.execute(TASK, "base1", {})
    assert excinfo.value.code == "MISSING_IMMUTABLE_FILES"
    assert owner.turns == 0
    with pytest.raises(Harness2ImportError):
        port.execute(TASK, "base1", {"scripts/total.py": b"\xff\xfe\x00binary"})
    assert owner.turns == 0


def test_payload_bound_to_another_turn_is_refused(tmp_path):
    scenario, configuration = _documents()
    owner = FormalOwner(tmp_path, _declaration(scenario, configuration))
    def mutate(receipt):
        payload = json.loads(receipt.payload_json)
        payload["attempt_id"] = "attempt-somewhere-else"
        return replace(receipt, payload_json=_payload(payload))
    port = AdmittedHarness2Port(declaration=owner.declaration,
                                owner=MutatingOwner(owner, mutate))
    with pytest.raises(AdmittedPortGateError) as excinfo:
        port.execute(TASK, "base1", BASE)
    assert excinfo.value.code == "WRONG_ATTEMPT_BINDING"


def test_non_canonical_payload_is_refused(tmp_path):
    scenario, configuration = _documents()
    owner = FormalOwner(tmp_path, _declaration(scenario, configuration))
    def mutate(receipt):
        payload = json.loads(receipt.payload_json)
        return replace(receipt, payload_json=json.dumps(payload, sort_keys=False,
                                                        separators=(", ", ": ")))
    port = AdmittedHarness2Port(declaration=owner.declaration,
                                owner=MutatingOwner(owner, mutate))
    with pytest.raises(AdmittedPortGateError) as excinfo:
        port.execute(TASK, "base1", BASE)
    assert excinfo.value.code == "STAGE_PAYLOAD_MALFORMED"


def test_context_seal_mismatch_is_refused(tmp_path):
    scenario, configuration = _documents()
    declaration = _declaration(scenario, configuration)
    owner = FormalOwner(tmp_path, declaration)
    class DriftedSealOwner(MutatingOwner):
        def admitted_stage_receipt(self, request):
            drifted = replace(request, context=dict(request.context,
                                                    common_base={"AGENTS.md": b"drifted\n"}))
            return self._inner.admitted_stage_receipt(drifted)
    port = AdmittedHarness2Port(declaration=declaration, owner=DriftedSealOwner(owner))
    context = _reasoning_context()
    with pytest.raises(AdmittedPortGateError) as excinfo:
        port.improve(TASK, "inv1", "invariant", context)
    assert excinfo.value.code == "CONTEXT_SEAL_MISMATCH"


def test_retention_refusal_is_typed(tmp_path):
    scenario, configuration = _documents()
    owner = FormalOwner(tmp_path, _declaration(scenario, configuration))
    class RefusingRetention(MutatingOwner):
        def retain_evaluation_documents(self, documents):
            return ()
    port = AdmittedHarness2Port(declaration=owner.declaration,
                                owner=RefusingRetention(owner))
    with pytest.raises(AdmittedPortGateError) as excinfo:
        port.execute(TASK, "base1", BASE)
    assert excinfo.value.code == "EVAL_RETENTION_REFUSED"


# ---------------------------------------------------------------------------
# 3. formally supplied accepted-owner conformance (never production proof)
# ---------------------------------------------------------------------------

def test_single_admitted_execution_returns_a_kernel_valid_trial(tmp_path):
    port, owner, _scenario, _configuration = _port(tmp_path)
    trial = port.execute(TASK, "base1", BASE)
    _validate_trial(trial, BASE)
    assert trial.run["validity"]["status"] == "VALID"
    assert trial.run["effect"]["state"] == "NO_EFFECT"
    assert trial.configuration["procedure"]["instruction_bundle"]["digest"] == harness_digest(BASE)
    assert trial.output == b"105\n"
    reopened = store.ArtifactStore(tmp_path / "eval")
    assert reopened.resolve_run(trial.run["run_id"]) == trial.run
    evidence = port.stage_evidence()
    assert len(evidence) == 1
    assert evidence[0]["role"] == "work" and evidence[0]["run_id"] == trial.run["run_id"]


def test_kernel_refinement_runs_through_the_admitted_port(tmp_path):
    scenario, configuration = _documents()
    declaration = _declaration(scenario, configuration)
    owner = FormalOwner(tmp_path, declaration)
    port = AdmittedHarness2Port(declaration=declaration, owner=owner)
    result = run_refinement(
        task=TASK, common_base=copy.deepcopy(BASE), expected_scenario=scenario,
        baseline_configuration=configuration, prior_experience=(),
        allowed_edit_paths=frozenset({"scripts/total.py"}), k=1, mode="agg",
        limits=Limits(max_rollouts=8, max_improver_calls=6, selector_seed=7), port=port)
    assert result["rollout_count"] == 4
    assert len(result["retained_native_runs"]) == 4
    assert result["automatic_memory_write"] is False and result["promotion"] == "NONE"
    assert result["selected_output"] == b"85\n"  # the lab program's signed sum after the proposal
    evidence = port.stage_evidence()
    assert len(evidence) == 8  # 4 executions + 3 improvements + 1 reflection
    assert len({item["attempt_id"] for item in evidence}) == 8
    assert sorted(item["role"] for item in evidence) == ["plan"] * 4 + ["work"] * 4
    execute_evidence = [item for item in evidence if item["stage"] == "execute"]
    assert all(item["harness_digest"] for item in execute_evidence)
    assert all(request.task == TASK for request in owner.requests)
    retained = owner.native.resolve_run(result["selected_native_run_id"])
    assert retained["run_id"] == result["selected_native_run_id"]


def test_selection_stage_binds_the_exact_anonymized_finals(tmp_path):
    scenario, configuration = _documents()
    declaration = _declaration(scenario, configuration)
    owner = FormalOwner(tmp_path, declaration)
    port = AdmittedHarness2Port(declaration=declaration, owner=owner)
    candidates = {"A": b"85\n", "B": b"105\n"}
    assert port.select(TASK, candidates) in candidates
    assert owner.requests[-1].candidates == candidates
    mutated = dict(candidates)
    mutated["A"] = b"drifted\n"
    class DriftedFinals(MutatingOwner):
        def admitted_stage_receipt(self, request):
            receipt = self._inner.admitted_stage_receipt(request)
            payload = json.loads(receipt.payload_json)
            payload["candidates_digest"] = _candidates_digest(mutated)
            return replace(receipt, payload_json=_payload(payload))
    port = AdmittedHarness2Port(declaration=declaration, owner=DriftedFinals(owner))
    with pytest.raises(AdmittedPortGateError) as excinfo:
        port.select(TASK, candidates)
    assert excinfo.value.code == "CONTEXT_SEAL_MISMATCH"


def test_stage_context_digest_distinguishes_frozen_contexts():
    context = {"current_harness": copy.deepcopy(BASE), "common_base": copy.deepcopy(BASE),
               "executions": [{"label": "base1", "run_id": "run:1", "output": b"105\n",
                               "harness": copy.deepcopy(BASE), "notes": ""}]}
    digest = stage_context_digest(context)
    assert digest == stage_context_digest(copy.deepcopy(context))
    drifted = copy.deepcopy(context)
    drifted["executions"][0]["output"] = b"85\n"
    assert stage_context_digest(drifted) != digest
