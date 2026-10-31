"""First admitted-execution seam binding the native Harness2 kernel to owners.

This module is the missing consumer named in
``docs/superpowers/plans/2026-10-21-harness2-agentos-native-adaptation.md``
("the exact consumer needed"): an existing-owner, parent/Attempt-bound
implementation of :class:`scripts.ohf.harness2_recursion.Harness2Port` that
observes complete ``RawRoleResultObservation`` evidence from admitted native
Attempts and recomputes each returned EVAL trial through the canonical EVAL
owners (``scripts.agent_eval.contracts``/``validity``/``store``).  It performs
no dispatch, no queue, no lease write, no retry, no provider call and no
scheduler of its own: the incumbent Executive OS owner owns admission, START,
collection, effects and reconciliation, exactly as the kernel docstring
requires.  One effect carrier exists -- the create-only EVAL artifact store
reached through the owner's retention seam.

Admission determination (source truth on this branch): the protected
``ExecutiveOperatorSupervisor`` admits only ``plan``/READ and four reviewed
read-only profiles, and ``MixedExecutionOwnerSupervisor`` refuses
``OPERATOR_HARNESS`` Attempts.  No incumbent nonplanner work-role admission
exists yet, therefore **no lawful production composition can supply a genuine
owner today**.  Every entry point of this module fails closed with a typed
gate unless a formally conforming owner is supplied.  A scripted fixture may
exercise only the fail-closed behavior; a formally typed owner in tests proves
connector conformance, never production proof, live admission or model
efficacy.

Role law enforced here (never widened): ``execute`` accepts only a
``work``-role Attempt whose effective grant validates through the incumbent
``validate_effective_grant`` owner -- a planner grant is never accepted for a
work role.  ``improve``/``select``/``reflect`` accept only the read-only
``plan`` reasoning envelope.  Missing served-model, profile, attestation,
effect, cleanup, source, tool-event or staged-file evidence is a typed
refusal, never a placeholder or a self-signed fill.
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from scripts.agent_eval import contracts, store, validity
from scripts.agent_eval.canonical import digest_value
from scripts.agent_eval.harness2_native import (
    configuration_lock,
    harness_digest,
    parse_digest_string,
    sha256_bytes,
    validate_native_harness_text,
)
from scripts.ohf.harness2_recursion import Proposal, Trial

from control_plane.executive_authority import AuthorityDecision
from control_plane.executive_orchestration_result import (
    OrchestrationResultError,
    RawRoleResultObservation,
    parse_canonical_json,
    validate_envelope,
)
from control_plane.executive_runtime import Attempt, AttemptStatus, Job, JobStatus
from control_plane.executive_supervisor import SupervisorError, validate_effective_grant

GATE_SCHEMA = "mastermind.harness2_admitted_port_gate.v1"
MAX_OUTPUT_BYTES = 1_048_576
_MAX_RETAINED_EVIDENCE = 512
_WORK_ROLE = "work"
_PLANNER_ROLE = "plan"
_PLANNER_READ_AUTHORITIES = frozenset({"READ"})
_NO_EFFECT = "NO_EFFECT"
_CLEANUP_PROVEN = "PROVEN"

_PAYLOAD_IDENTITY_KEYS = frozenset({"attempt_id", "turn_id", "context_digest"})
_EXECUTE_PAYLOAD_KEYS = _PAYLOAD_IDENTITY_KEYS
_IMPROVE_PAYLOAD_KEYS = _PAYLOAD_IDENTITY_KEYS | {"proposal"}
_PROPOSAL_KEYS = frozenset({"files", "notes", "evidence_run_ids"})
_SELECT_PAYLOAD_KEYS = _PAYLOAD_IDENTITY_KEYS | {"candidates_digest", "selection"}
_REFLECT_PAYLOAD_KEYS = _PAYLOAD_IDENTITY_KEYS | {"reflection"}
_REFLECTION_KEYS = frozenset({"claim", "falsifier", "so_what", "evidence_run_ids"})
_STAGES = frozenset({"execute", "improve", "select", "reflect"})


class AdmittedPortGateError(RuntimeError):
    """Typed, stable refusal.  Never a retry, fallback or carrier hint."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(code if not detail else f"{code}: {detail}")

    def to_dict(self) -> dict:
        return {"schema": GATE_SCHEMA, "gate": self.code, "detail": self.detail}


def _gate(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise AdmittedPortGateError(code, detail)


@dataclass(frozen=True)
class ValidatorSeal:
    """Validator provenance supplied by the incumbent EVAL validator owner."""

    validator_id: str
    validator_version: str
    validator_code_ref: str
    validated_at: str
    created_at: str


@dataclass(frozen=True)
class ComparisonDeclaration:
    """The EVAL comparison the kernel caller already declared, bound once.

    ``scenario``/``baseline_configuration`` must be the exact documents the
    same composition passes to ``run_refinement``; this port never invents or
    edits them.  ``bundle_ref_namespace`` is the owner's admitted artifact-ref
    prefix for per-candidate instruction bundles.
    """

    scenario: dict
    baseline_configuration: dict
    experiment: dict | None
    validator: ValidatorSeal
    runner_id: str
    runner_code_ref: str
    bundle_ref_namespace: str


@dataclass(frozen=True)
class StageAdmissionRequest:
    """What the port asks the owner to bind; never a dispatch instruction.

    The complete frozen stage inputs travel to the owner so its composition can
    seal them into the admitted Job it owns; the port keeps only digests of the
    owner's sealed statements.  No field here grants any authority.
    """

    stage: str
    task: dict
    label: str
    kind: str | None
    context_digest: str | None
    context: dict | None
    harness_digest: str | None
    harness_files: dict | None
    candidates: dict | None
    chosen: dict | None


@dataclass(frozen=True)
class ExecutionObservation:
    """Complete observed execution facts, supplied by the owner only.

    Every field is required evidence; an absent fact must reach this port as a
    typed gate refusal from the owner, never as a placeholder value.
    ``output_bytes`` and ``tool_events_bytes`` must be the complete retained
    bytes the owner resolved through its own workspace/artifact authority.
    """

    model_served: str
    execution_surface: str
    execution_surface_version: str
    provider: str
    fresh_process_observed: bool
    fresh_workspace_observed: bool
    fresh_session_observed: bool
    resume_used: bool
    observed_capability_ids: tuple[str, ...]
    observed_tool_schema_digests: tuple[str, ...]
    observed_sources: tuple[dict, ...]
    observed_network_destinations: tuple[dict, ...]
    dependency_degradations: tuple[str, ...]
    effect_state: str
    cleanup_status: str
    cleanup_proof: dict
    output_artifact_path: str
    output_artifact_ref: str
    output_bytes: bytes
    tool_events_artifact_ref: str
    tool_events_bytes: bytes
    resources: dict
    timing: dict


@dataclass(frozen=True)
class AdmittedStageReceipt:
    """One owner-sealed stage binding: admitted Attempt + complete evidence.

    ``authority_decision`` is the owner's preauthorization for this exact Job
    (required for ``execute``); ``fence_generation`` is the generation the
    owner collected under, so any later fence bump is detectable as stale.
    ``payload_json`` is the owner's canonical sealed turn payload, bound to the
    exact Attempt and native turn and to the stage's frozen context digest.
    """

    attempt: Attempt
    job: Job
    raw: RawRoleResultObservation
    payload_json: str
    fence_generation: int
    authority_decision: AuthorityDecision | None
    observation: ExecutionObservation | None


@runtime_checkable
class AdmittedHarness2ExecutionOwner(Protocol):
    """The incumbent composition's two seams; nothing else is consumed.

    ``admitted_stage_receipt`` returns an already-admitted, already-finished
    Attempt binding for exactly the requested stage -- the owner performed
    claim/START/collect through its existing supervisors before this call.
    ``retain_evaluation_documents`` is create-only retention through the
    owner's existing EVAL artifact store.
    """

    def admitted_stage_receipt(self, request: StageAdmissionRequest) -> AdmittedStageReceipt: ...

    def retain_evaluation_documents(self, documents: tuple[dict, ...]) -> tuple[store.WriteResult, ...]: ...


def stage_context_digest(context: dict) -> str:
    """Digest the exact frozen context the kernel handed to this stage.

    File trees and outputs enter as digests so the owner can recompute the
    same digest when it seals its turn payload; nothing else about the
    context is reinterpreted here.
    """
    _gate(type(context) is dict, "PORT_CONTEXT_SHAPE")

    def _files(files) -> dict:
        _gate(type(files) is dict, "PORT_CONTEXT_SHAPE")
        return {path: sha256_bytes(raw) for path, raw in files.items()}

    executions = context.get("executions", ())
    _gate(isinstance(executions, list), "PORT_CONTEXT_SHAPE")
    return digest_value({
        "current_harness": _files(context.get("current_harness", {})),
        "common_base": _files(context.get("common_base", {})),
        "prior_experience": list(context.get("prior_experience", ())),
        "prior_harnesses": {ref: _files(files)
                            for ref, files in (context.get("prior_harnesses") or {}).items()},
        "organizational_context": context.get("organizational_context"),
        "experience_exclusions": list(context.get("experience_exclusions", ())),
        "executions": [{"label": item["label"], "run_id": item["run_id"],
                        "output_digest": sha256_bytes(item["output"]),
                        "harness": _files(item["harness"]), "notes": item["notes"]}
                       for item in executions],
    })


def _payload(receipt: AdmittedStageReceipt) -> dict:
    try:
        payload = parse_canonical_json(receipt.payload_json)
    except OrchestrationResultError as exc:
        raise AdmittedPortGateError("STAGE_PAYLOAD_MALFORMED",
                                    f"payload is not canonical JSON: {exc}") from exc
    _gate(type(payload) is dict, "STAGE_PAYLOAD_MALFORMED", "payload must be one JSON object")
    return payload


def _sealed_identity(payload: dict, receipt: AdmittedStageReceipt) -> None:
    _gate(payload["attempt_id"] == receipt.attempt.attempt_id
          and payload["turn_id"] == receipt.raw.turn_id,
          "WRONG_ATTEMPT_BINDING", "sealed payload is not this Attempt's native turn")


class AdmittedHarness2Port:
    """Strict ``Harness2Port`` connector; every method fails closed."""

    def __init__(self, *, declaration: ComparisonDeclaration,
                 owner: AdmittedHarness2ExecutionOwner | None) -> None:
        if owner is None:
            raise AdmittedPortGateError(
                "MISSING_EXECUTION_OWNER",
                "no incumbent admitted nonplanner execution owner exists on this branch; "
                "a genuine owner composition must be supplied before any port call",
            )
        _gate(type(declaration) is ComparisonDeclaration, "MISSING_EVAL_OWNER_DOCUMENTS")
        if not callable(getattr(owner, "admitted_stage_receipt", None)) or not callable(
                getattr(owner, "retain_evaluation_documents", None)):
            raise AdmittedPortGateError("OWNER_NOT_ADMITTED", "owner lacks the exact owner seams")
        self._owner = owner
        self._declaration = declaration
        contracts.validate_scenario_shape(declaration.scenario)
        contracts.validate_configuration_shape(declaration.baseline_configuration)
        if declaration.experiment is not None:
            contracts.validate_experiment_shape(declaration.experiment)
        parse_digest_string(declaration.baseline_configuration["procedure"]["instruction_bundle"]["digest"])
        self._factor_lock = self._lock(declaration.baseline_configuration)
        for name in ("validator_id", "validator_version", "validator_code_ref",
                     "validated_at", "created_at"):
            _gate(type(getattr(declaration.validator, name)) is str
                  and bool(getattr(declaration.validator, name)),
                  "MISSING_EVAL_OWNER_DOCUMENTS", f"validator.{name}")
        _gate(type(declaration.runner_id) is str and bool(declaration.runner_id)
              and type(declaration.runner_code_ref) is str and bool(declaration.runner_code_ref),
              "MISSING_EVAL_OWNER_DOCUMENTS", "runner identity")
        _gate(type(declaration.bundle_ref_namespace) is str and bool(declaration.bundle_ref_namespace),
              "MISSING_EVAL_OWNER_DOCUMENTS", "bundle_ref_namespace")
        self._evidence: tuple[dict, ...] = ()

    # -- public Harness2Port surface --------------------------------------------------

    def execute(self, task: dict, label: str, files: dict) -> Trial:
        _gate(type(files) is dict and bool(files), "MISSING_IMMUTABLE_FILES",
              "staged candidate harness is absent")
        validate_native_harness_text(files)
        bundle_digest = harness_digest(files)
        receipt = self._bound_receipt("execute", task, label, kind=None, context_digest=None,
                                      context=None, harness_digest=bundle_digest,
                                      harness_files=copy.deepcopy(files),
                                      candidates=None, chosen=None)
        self._require_work_envelope(receipt)
        observation = self._require_observation(receipt)
        scenario, baseline, experiment = self._documents()
        self._verify_observation_against_declaration(observation, baseline, scenario)
        candidate = self._candidate_configuration(baseline, bundle_digest)
        output = self._resolve_output(receipt, observation)
        _gate(type(observation.tool_events_bytes) is bytes
              and 0 < len(observation.tool_events_bytes) <= MAX_OUTPUT_BYTES,
              "TOOL_EVENTS_UNPROVEN")
        draft = self._draft(receipt, observation, scenario, candidate, experiment, output)
        run = self._finalize(scenario, candidate, experiment, draft)
        self._require_valid(run)
        self._retain(scenario, candidate, experiment, run)
        self._retain_evidence("execute", receipt, run, bundle_digest)
        return Trial(scenario, candidate, experiment, run, output)

    def improve(self, task: dict, label: str, kind: str, context: dict) -> Proposal:
        receipt = self._bound_receipt("improve", task, label, kind=kind,
                                      context_digest=stage_context_digest(context),
                                      context=copy.deepcopy(context), harness_digest=None,
                                      harness_files=None, candidates=None, chosen=None)
        self._require_planner_envelope(receipt)
        payload = _payload(receipt)
        _gate(set(payload) == _IMPROVE_PAYLOAD_KEYS, "STAGE_PAYLOAD_MALFORMED", "improve keys")
        _sealed_identity(payload, receipt)
        proposal = payload["proposal"]
        _gate(type(proposal) is dict and set(proposal) == _PROPOSAL_KEYS,
              "STAGE_PAYLOAD_MALFORMED", "proposal keys")
        files = proposal["files"]
        _gate(type(files) is dict and bool(files), "STAGE_PAYLOAD_MALFORMED", "proposal files")
        _gate(all(type(path) is str and type(text) is str for path, text in files.items()),
              "STAGE_PAYLOAD_MALFORMED", "proposal file text")
        notes = proposal["notes"]
        _gate(type(notes) is str, "STAGE_PAYLOAD_MALFORMED", "proposal notes")
        evidence = proposal["evidence_run_ids"]
        _gate(type(evidence) is list and all(type(item) is str for item in evidence),
              "STAGE_PAYLOAD_MALFORMED", "proposal evidence")
        self._retain_evidence("improve", receipt, None, None)
        return Proposal({path: text.encode("utf-8") for path, text in files.items()},
                        notes, tuple(evidence))

    def select(self, task: dict, candidates: dict) -> str:
        receipt = self._bound_receipt("select", task, label="", kind=None, context_digest=None,
                                      context=None, harness_digest=None, harness_files=None,
                                      candidates={key: bytes(raw) for key, raw in candidates.items()},
                                      chosen=None)
        self._require_planner_envelope(receipt)
        payload = _payload(receipt)
        _gate(set(payload) == _SELECT_PAYLOAD_KEYS, "STAGE_PAYLOAD_MALFORMED", "select keys")
        _sealed_identity(payload, receipt)
        _gate(type(candidates) is dict and bool(candidates), "STAGE_PAYLOAD_MALFORMED", "candidates")
        _gate(all(type(key) is str and type(raw) is bytes for key, raw in candidates.items()),
              "STAGE_PAYLOAD_MALFORMED", "candidates bytes")
        _gate(payload["candidates_digest"] == digest_value(
            {key: sha256_bytes(raw) for key, raw in candidates.items()}),
            "CONTEXT_SEAL_MISMATCH", "finals drifted after the selection turn was sealed")
        selection = payload["selection"]
        _gate(type(selection) is str and selection in candidates,
              "STAGE_PAYLOAD_MALFORMED", "selection outside the anonymized finals")
        self._retain_evidence("select", receipt, None, None)
        return selection

    def reflect(self, task: dict, chosen: dict, context: dict) -> dict | None:
        receipt = self._bound_receipt("reflect", task, label="", kind=None,
                                      context_digest=stage_context_digest(context),
                                      context=copy.deepcopy(context), harness_digest=None,
                                      harness_files=None, candidates=None,
                                      chosen=copy.deepcopy(chosen))
        self._require_planner_envelope(receipt)
        payload = _payload(receipt)
        _gate(set(payload) == _REFLECT_PAYLOAD_KEYS, "STAGE_PAYLOAD_MALFORMED", "reflect keys")
        _sealed_identity(payload, receipt)
        reflection = payload["reflection"]
        _gate(reflection is None or (type(reflection) is dict and set(reflection) == _REFLECTION_KEYS),
              "STAGE_PAYLOAD_MALFORMED", "reflection keys")
        self._retain_evidence("reflect", receipt, None, None)
        return copy.deepcopy(reflection) if reflection is not None else None

    # -- retained evidence ------------------------------------------------------------

    def stage_evidence(self) -> tuple[dict, ...]:
        """Frozen per-stage bindings this port consumed (audit view)."""
        return copy.deepcopy(self._evidence)

    def declared_factor_lock(self) -> str:
        return self._factor_lock

    # -- owner binding ----------------------------------------------------------------

    def _bound_receipt(self, stage: str, task: dict, label: str, *, kind: str | None,
                       context_digest: str | None, context: dict | None,
                       harness_digest: str | None, harness_files: dict | None,
                       candidates: dict | None, chosen: dict | None) -> AdmittedStageReceipt:
        _gate(self._owner is not None, "MISSING_EXECUTION_OWNER")
        _gate(stage in _STAGES, "PORT_STAGE_UNKNOWN")
        _gate(type(task) is dict and set(task) == {"task_id", "domain", "request"}, "PORT_TASK_SHAPE")
        request = StageAdmissionRequest(stage=stage, task=copy.deepcopy(task), label=label, kind=kind,
                                        context_digest=context_digest, context=context,
                                        harness_digest=harness_digest, harness_files=harness_files,
                                        candidates=candidates, chosen=chosen)
        receipt = self._owner.admitted_stage_receipt(request)
        _gate(type(receipt) is AdmittedStageReceipt, "OWNER_NOT_ADMITTED",
              "owner returned no canonical AdmittedStageReceipt")
        _gate(type(receipt.attempt) is Attempt and type(receipt.job) is Job
              and type(receipt.raw) is RawRoleResultObservation,
              "OWNER_RESOLUTION_INCOMPLETE", "receipt lacks incumbent Attempt/Job/observation types")
        attempt, job = receipt.attempt, receipt.job
        _gate(attempt.status is AttemptStatus.COMPLETED and job.status is JobStatus.COMPLETED,
              "ATTEMPT_NOT_COMPLETED", f"{attempt.status.value}/{job.status.value}")
        _gate(attempt.job_id == job.job_id and job.current_attempt_id == attempt.attempt_id
              and job.assigned_worker_id == attempt.worker_id,
              "WRONG_ATTEMPT_BINDING", "attempt/job identity mismatch")
        _gate(type(receipt.fence_generation) is int
              and receipt.fence_generation == attempt.fence_generation,
              "STALE_ATTEMPT_GENERATION", "receipt generation differs from the admitted Attempt")
        _gate(type(receipt.payload_json) is str and bool(receipt.payload_json),
              "STAGE_PAYLOAD_MALFORMED", "payload absent")
        _gate(receipt.raw.attempt_id == attempt.attempt_id,
              "WRONG_ATTEMPT_BINDING", "raw observation belongs to another Attempt")
        self._verify_raw_envelope(receipt)
        payload = _payload(receipt)
        _sealed_identity(payload, receipt)
        _gate(payload["context_digest"] == context_digest,
              "CONTEXT_SEAL_MISMATCH", "owner sealed a different stage context")
        return receipt

    def _verify_raw_envelope(self, receipt: AdmittedStageReceipt) -> None:
        try:
            parsed = parse_canonical_json(receipt.raw.canonical_result_json)
            validate_envelope(parsed,
                              expected_job_id=receipt.job.job_id,
                              expected_run_id=receipt.attempt.attempt_id,
                              expected_worker_id=receipt.attempt.worker_id,
                              expected_role=receipt.job.orchestration_role,
                              expected_root_job_id=receipt.job.root_job_id)
        except OrchestrationResultError as exc:
            raise AdmittedPortGateError("RAW_ROLE_RESULT_MALFORMED", str(exc)) from exc

    def _require_work_envelope(self, receipt: AdmittedStageReceipt) -> None:
        job, attempt = receipt.job, receipt.attempt
        _gate(job.orchestration_role == _WORK_ROLE, "UNAUTHORIZED_ROLE_PROFILE",
              "execute accepts only an admitted work-role Attempt; a planner grant "
              "is never accepted for a work role")
        _gate(attempt.execution_mode != "OPERATOR_HARNESS", "UNAUTHORIZED_ROLE_PROFILE",
              "OPERATOR_HARNESS Attempts are planner-only and cannot carry a work role")
        _gate(type(receipt.authority_decision) is AuthorityDecision,
              "OWNER_RESOLUTION_INCOMPLETE", "execute requires the owner's preauthorization")
        try:
            grant = validate_effective_grant(job, attempt, receipt.authority_decision)
        except SupervisorError as exc:
            raise AdmittedPortGateError("UNAUTHORIZED_ROLE_PROFILE",
                                        f"effective grant refused by its incumbent owner: {exc}") from exc
        _gate(type(grant) is dict and grant["role"] == _WORK_ROLE,
              "UNAUTHORIZED_ROLE_PROFILE", "validated grant is not bound to this work role")

    def _require_planner_envelope(self, receipt: AdmittedStageReceipt) -> None:
        job, attempt = receipt.job, receipt.attempt
        _gate(job.orchestration_role == _PLANNER_ROLE, "UNAUTHORIZED_ROLE_PROFILE",
              "reasoning stages accept only the read-only planner envelope")
        _gate(attempt.execution_mode != "OPERATOR_HARNESS", "UNAUTHORIZED_ROLE_PROFILE",
              "this port consumes no OPERATOR_HARNESS Attempt")
        _gate(set(job.requested_authorities) <= _PLANNER_READ_AUTHORITIES
              and not job.allowed_write_paths and not job.validation_commands,
              "UNAUTHORIZED_ROLE_PROFILE", "reasoning envelope is not closed read-only")
        grant = attempt.effective_grant
        _gate(type(grant) is dict and grant.get("role") == _PLANNER_ROLE
              and set(grant.get("authorities", ())) <= _PLANNER_READ_AUTHORITIES,
              "UNAUTHORIZED_ROLE_PROFILE", "planner grant is missing or widened")

    def _require_observation(self, receipt: AdmittedStageReceipt) -> ExecutionObservation:
        observation = receipt.observation
        _gate(type(observation) is ExecutionObservation, "EXECUTION_OBSERVATION_UNPROVEN")
        for name in ("model_served", "execution_surface", "execution_surface_version", "provider"):
            _gate(type(getattr(observation, name)) is str and bool(getattr(observation, name)),
                  "EXECUTION_OBSERVATION_UNPROVEN", name)
        _gate(type(observation.output_bytes) is bytes
              and 0 < len(observation.output_bytes) <= MAX_OUTPUT_BYTES,
              "EXECUTION_OBSERVATION_UNPROVEN", "output_bytes")
        return observation

    # -- declaration and configuration ------------------------------------------------

    def _documents(self) -> tuple[dict, dict, dict | None]:
        declaration = self._declaration
        return (declaration.scenario, declaration.baseline_configuration, declaration.experiment)

    def _lock(self, configuration: dict) -> str:
        scenario = self._declaration.scenario
        scenario_ref = {key: scenario[key] for key in
                        ("scenario_id", "scenario_version", "scenario_digest", "corpus_revision")}
        scenario_ref["temporal_cutoff"] = scenario["temporal"]["cutoff_at"]
        return configuration_lock(scenario_ref, configuration)

    def _candidate_configuration(self, baseline: dict, bundle_digest: str) -> dict:
        fields = copy.deepcopy(baseline)
        fields.pop("schema", None)
        fields.pop("configuration_digest", None)
        fields["configuration_id"] = "configuration:" + str(uuid.uuid4())
        fields["procedure"]["instruction_bundle"] = {
            "artifact_ref": self._declaration.bundle_ref_namespace
            + bundle_digest.split(":", 1)[1] + ".json",
            "digest": bundle_digest,
        }
        try:
            candidate = contracts.build_configuration(fields)
        except contracts.ContractError as exc:
            raise AdmittedPortGateError("MISSING_EVAL_OWNER_DOCUMENTS",
                                        f"candidate configuration refused: {exc}") from exc
        _gate(self._lock(candidate) == self._factor_lock, "DECLARED_COMPARISON_DRIFT",
              "candidate moved a factor-locked comparison field")
        return candidate

    def _verify_observation_against_declaration(self, observation: ExecutionObservation,
                                                baseline: dict, scenario: dict) -> None:
        execution = baseline["execution"]
        _gate(observation.model_served == execution["model_requested"], "MODEL_SERVED_MISMATCH",
              f"served {observation.model_served!r} != requested {execution['model_requested']!r}")
        _gate(observation.execution_surface == execution["execution_surface"]
              and observation.execution_surface_version == execution["execution_surface_version"]
              and observation.provider == execution["provider"],
              "DECLARED_COMPARISON_DRIFT", "observed execution surface differs from the declaration")
        policy = scenario["execution_policy"]
        _gate((not policy["fresh_process_required"]) or observation.fresh_process_observed,
              "FRESH_PROCESS_UNPROVEN")
        _gate((not policy["fresh_workspace_required"]) or observation.fresh_workspace_observed,
              "FRESH_WORKSPACE_UNPROVEN")
        _gate((not policy["fresh_session_required"]) or observation.fresh_session_observed,
              "FRESH_SESSION_UNPROVEN")
        _gate(policy["resume_allowed"] or not observation.resume_used, "RESUME_FORBIDDEN")
        capabilities = baseline["capabilities"]
        observed_caps = tuple(observation.observed_capability_ids)
        observed_tools = tuple(observation.observed_tool_schema_digests)
        _gate(bool(observed_caps) and bool(observed_tools), "EXECUTION_OBSERVATION_UNPROVEN",
              "capability/tool-schema observations absent")
        _gate(set(observed_caps) <= set(capabilities["declared_capability_ids"]), "CAPABILITY_DRIFT")
        _gate(set(observed_tools) <= set(capabilities["declared_tool_schema_digests"]), "TOOL_SCHEMA_DRIFT")
        sources = tuple(observation.observed_sources)
        _gate(bool(sources), "EXECUTION_OBSERVATION_UNPROVEN", "observed_sources absent")
        allowlist = {item["artifact_ref"]: item["digest"]
                     for item in scenario["source_policy"]["allowlist_artifacts"]}
        digests = set()
        for source in sources:
            _gate(type(source) is dict and set(source) == {"artifact_ref", "digest"},
                  "EXECUTION_OBSERVATION_UNPROVEN", "observed source shape")
            _gate(source["artifact_ref"] in allowlist, "UNAUTHORIZED_SOURCE", source["artifact_ref"])
            _gate(allowlist[source["artifact_ref"]] == source["digest"], "SOURCE_DIGEST_MISMATCH")
            _gate(source["digest"] not in digests, "DUPLICATE_SOURCE_DIGEST")
            digests.add(source["digest"])
        authorized = {digest_value(item) for item in scenario["execution_policy"]["network_allowlist"]}
        for destination in observation.observed_network_destinations:
            _gate(type(destination) is dict and "value_digest" in destination
                  and destination["value_digest"] in authorized, "UNEXPECTED_NETWORK_DESTINATION")
        _gate(set(observation.dependency_degradations)
              <= set(scenario["execution_policy"]["allowed_degradations"]), "DEGRADATION_NOT_ALLOWED")
        _gate(observation.effect_state == _NO_EFFECT, "TAINTED_OR_UNKNOWN_EFFECT",
              f"effect state {observation.effect_state!r} requires owner reconciliation")
        _gate(observation.cleanup_status == _CLEANUP_PROVEN and type(observation.cleanup_proof) is dict,
              "CLEANUP_UNPROVEN")

    def _resolve_output(self, receipt: AdmittedStageReceipt, observation: ExecutionObservation) -> bytes:
        parsed = parse_canonical_json(receipt.raw.canonical_result_json)
        matches = [artifact for artifact in parsed["role_result"]["artifacts"]
                   if artifact["path"] == observation.output_artifact_path]
        _gate(len(matches) == 1, "MISSING_IMMUTABLE_FILES",
              f"output artifact path {observation.output_artifact_path!r} is not bound exactly once")
        # The incumbent role-result grammar hashes bare hex; EVAL evidence pairs
        # carry the prefixed digest string.  Compare the exact same bytes.
        _gate(matches[0]["digest"] == sha256_bytes(observation.output_bytes).split(":", 1)[1],
              "MISSING_IMMUTABLE_FILES", "resolved output bytes do not hash to the sealed artifact")
        return observation.output_bytes

    # -- EVAL recompute ---------------------------------------------------------------

    def _draft(self, receipt: AdmittedStageReceipt, observation: ExecutionObservation,
               scenario: dict, candidate: dict, experiment: dict | None, output: bytes) -> dict:
        attempt, job, raw = receipt.attempt, receipt.job, receipt.raw
        execution = candidate["execution"]
        comparison = {"experiment_id": None, "arm_id": None, "pair_key": None, "replicate_index": None}
        if experiment is not None:
            arm = next((item for item in experiment["arms"]
                        if item["configuration_id"] == candidate["configuration_id"]), None)
            _gate(arm is not None, "MISSING_EVAL_OWNER_DOCUMENTS",
                  "declared experiment has no arm for this candidate configuration")
            method = experiment["pairing"]["method"]
            _gate(method in ("PAIRED_BY_SCENARIO", "UNPAIRED"), "MISSING_EVAL_OWNER_DOCUMENTS",
                  f"unsupported pairing method {method!r} in this first seam")
            comparison["experiment_id"] = experiment["experiment_id"]
            comparison["arm_id"] = arm["arm_id"]
            comparison["replicate_index"] = 1
            comparison["pair_key"] = (f"pair:{scenario['scenario_id']}:v{scenario['scenario_version']}:r1"
                                      if method == "PAIRED_BY_SCENARIO" else None)
        draft = {
            "schema": contracts.RUN_DRAFT_SCHEMA,
            "run_id": "run:" + str(uuid.uuid4()),
            "scenario": {
                "scenario_id": scenario["scenario_id"],
                "scenario_version": scenario["scenario_version"],
                "scenario_digest": scenario["scenario_digest"],
                "corpus_revision": scenario["corpus_revision"],
                "temporal_cutoff": scenario["temporal"]["cutoff_at"],
            },
            "configuration": {"configuration_id": candidate["configuration_id"],
                              "configuration_digest": candidate["configuration_digest"]},
            "comparison": comparison,
            "execution": {
                "runner_id": self._declaration.runner_id,
                "runner_code_ref": self._declaration.runner_code_ref,
                "execution_surface": execution["execution_surface"],
                "execution_surface_version": execution["execution_surface_version"],
                "provider": execution["provider"],
                "model_requested": execution["model_requested"],
                "model_served": observation.model_served,
                "reasoning_effort": execution["reasoning_effort"],
                "auth_realm_class": execution["auth_realm_class"],
                "process_fingerprint": digest_value({
                    "boot_id": attempt.boot_id,
                    "process_start_identity": attempt.process_start_identity,
                }),
                "native_session_fingerprint": digest_value({
                    "provider_session_id": raw.provider_session_id,
                    "provider_native_turn_id": raw.provider_native_turn_id,
                }),
                "completion_status": "COMPLETED",
                "termination_reason": "COMPLETED_NORMALLY",
                "fresh_process_observed": observation.fresh_process_observed,
                "fresh_workspace_observed": observation.fresh_workspace_observed,
                "fresh_session_observed": observation.fresh_session_observed,
                "resume_used": observation.resume_used,
            },
            "procedure": copy.deepcopy(candidate["procedure"]),
            "context": {
                "source_policy_digest": digest_value(scenario["source_policy"]),
                "context_packet": dict(candidate["context"]["context_packet"]),
                "retrieval_configuration": candidate["context"]["retrieval_configuration"],
            },
            "observations": {
                "observed_sources": [dict(item) for item in
                                     sorted(observation.observed_sources,
                                            key=lambda item: item["artifact_ref"])],
                "observed_capability_ids": sorted(set(observation.observed_capability_ids)),
                "observed_tool_schema_digests": sorted(set(observation.observed_tool_schema_digests)),
                "observed_network_destinations": [dict(item)
                                                  for item in observation.observed_network_destinations],
                "dependency_degradations": sorted(set(observation.dependency_degradations)),
            },
            "capabilities": {
                "profile_id": candidate["capabilities"]["profile_id"],
                "profile_digest": candidate["capabilities"]["profile_digest"],
                "sandbox_digest": candidate["capabilities"]["sandbox_digest"],
                "network_policy_digest": candidate["capabilities"]["network_policy_digest"],
                "workspace_digest": digest_value({"worktree": job.worktree,
                                                  "attempt_id": attempt.attempt_id}),
                "environment_digest": candidate["capabilities"]["environment_digest"],
            },
            "randomness": copy.deepcopy(candidate["randomness"]),
            "effect": {"state": _NO_EFFECT, "operation_ref": None, "reconciliation_ref": None},
            "cleanup": {"status": _CLEANUP_PROVEN, "proof": dict(observation.cleanup_proof)},
            "evidence": {
                "output": {"artifact_ref": observation.output_artifact_ref,
                           "digest": sha256_bytes(output)},
                "tool_events": {"artifact_ref": observation.tool_events_artifact_ref,
                                "digest": sha256_bytes(observation.tool_events_bytes)},
                "trace": None,
                "artifacts": [],
            },
            "resources": copy.deepcopy(observation.resources),
            "timing": copy.deepcopy(observation.timing),
        }
        try:
            contracts.validate_run_draft_shape(draft)
        except contracts.ContractError as exc:
            raise AdmittedPortGateError("EXECUTION_OBSERVATION_UNPROVEN",
                                        f"owner evidence did not compose a valid draft: {exc}") from exc
        return draft

    def _finalize(self, scenario: dict, candidate: dict, experiment: dict | None, draft: dict) -> dict:
        seal = self._declaration.validator
        try:
            return validity.finalize_run_receipt(
                scenario, candidate, experiment, draft,
                validator_id=seal.validator_id, validator_version=seal.validator_version,
                validator_code_ref=seal.validator_code_ref, validated_at=seal.validated_at,
                created_at=seal.created_at,
            )
        except contracts.ContractError as exc:
            raise AdmittedPortGateError("EVAL_FINALIZE_REFUSED", str(exc)) from exc

    def _require_valid(self, run: dict) -> None:
        _gate(run["validity"]["status"] == "VALID", "EVAL_RUN_NOT_VALID",
              ",".join(run["validity"]["reason_codes"]))
        _gate(run["effect"]["state"] == _NO_EFFECT, "TAINTED_OR_UNKNOWN_EFFECT")

    def _retain(self, scenario: dict, candidate: dict, experiment: dict | None, run: dict) -> None:
        documents = [scenario, candidate] + ([experiment] if experiment is not None else []) + [run]
        try:
            receipts = self._owner.retain_evaluation_documents(tuple(documents))
        except Exception as exc:  # noqa: BLE001 - the owner's own refusal is the typed gate
            raise AdmittedPortGateError("EVAL_RETENTION_REFUSED", str(exc)) from exc
        _gate(type(receipts) is tuple and len(receipts) == len(documents),
              "EVAL_RETENTION_REFUSED", "owner returned an incomplete retention set")
        digest_fields = {"scenario": "scenario_digest", "configuration": "configuration_digest",
                         "experiment": "experiment_digest", "run": "run_digest"}
        for receipt, document in zip(receipts, documents):
            _gate(type(receipt) is store.WriteResult, "EVAL_RETENTION_REFUSED", "no canonical WriteResult")
            _gate(receipt.disposition in (store.WriteDisposition.CREATED,
                                          store.WriteDisposition.IDEMPOTENT),
                  "EVAL_RETENTION_REFUSED", str(receipt.disposition))
            if "validity" in document:
                kind = "run"
            elif "arms" in document:
                kind = "experiment"
            elif "capabilities" in document:
                kind = "configuration"
            else:
                kind = "scenario"
            _gate(receipt.artifact_digest == document[digest_fields[kind]],
                  "EVAL_RETENTION_REFUSED", f"retained {kind} digest drifted")

    def _retain_evidence(self, stage: str, receipt: AdmittedStageReceipt,
                         run: dict | None, bundle_digest: str | None) -> None:
        _gate(len(self._evidence) < _MAX_RETAINED_EVIDENCE, "EVIDENCE_LEDGER_BOUND")
        self._evidence = self._evidence + ({
            "stage": stage,
            "attempt_id": receipt.attempt.attempt_id,
            "job_id": receipt.job.job_id,
            "fence_generation": receipt.fence_generation,
            "role": receipt.job.orchestration_role,
            "raw_result_digest": receipt.raw.canonical_result_digest,
            "run_id": None if run is None else run["run_id"],
            "harness_digest": bundle_digest,
        },)
