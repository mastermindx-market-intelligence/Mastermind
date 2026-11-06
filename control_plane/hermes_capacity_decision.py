"""H24-02: pure Hermes projection over explicitly acquired owner inputs.

No owner is opened here. There is no clock read, provider call, reservation,
claim, fallback, or store. A CANDIDATE is an offline observation, never a grant.
The host must acquire the inputs through their existing owners and repeat this
check at the incumbent Executive fresh-claim boundary.
"""
from __future__ import annotations

import copy
import dataclasses
import enum
import hashlib
import json
import re
from typing import Any

from control_plane import executive_physical_resources as physical
from control_plane import executive_placement_selection as placement
from control_plane import native_capacity_v2
from control_plane.executive_capacity_join import MAX_CANDIDATES, validate_capacity_join
from control_plane.executive_agent_capabilities import adapter_supports_execution_surface
from control_plane.executive_capacity_observation import (
    OBSERVATION_LIFETIME_MS,
    CapacityObservationError,
    validate_worker_capacity_observation,
)
from control_plane.executive_host_capacity import validate_host_capacity_snapshot, validate_hp0_binding
from control_plane.executive_host_pressure import BOOT_REF_RE, HOST_REF_RE, validate_host_pressure_snapshot
from control_plane.executive_physical_admission import _observed_pools
from control_plane.executive_runtime import (
    Attempt, AttemptStatus, ExpectedChildSelection, Job, JobStatus, Worker, WorkerQuotaClass,
    WorkerStatus, _assert_expected_child_selection, _capacity_matches_route,
    _normalise_work_placement_union, _project_work_placement,
)
from control_plane.executive_steward import ResponsibilityFact
from control_plane.model_router import ModelRouter, RouteMode, RoutingDecision, WorkRequest

SCHEMA = "mastermind.hermes_capacity_decision/v1"
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_SHA = re.compile(r"[0-9a-f]{64}")
_ROUTE_FIELDS = (
    "execution_profile_id", "execution_profile_digest", "capability_policy_version",
    "capability_policy_digest", "routing_policy_version",
)
_METADATA_FIELDS = (*_ROUTE_FIELDS, "model_alias", "attended_route", "paid_execution_route", "capacity_join")


class DecisionState(str, enum.Enum):
    CANDIDATE = "CANDIDATE"
    REFUSED = "REFUSED"
    UNAVAILABLE = "UNAVAILABLE"


class ObservationCoverage(str, enum.Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    DISCONNECTED = "DISCONNECTED"


class EvaluationMode(str, enum.Enum):
    OWNER_QUALIFIED = "OWNER_QUALIFIED"
    FIXTURE_ONLY = "FIXTURE_ONLY"


@dataclasses.dataclass(frozen=True, slots=True)
class OwnerEpoch:
    """Opaque owner incarnation/revision, acquired independently of its facts.

    generation must advance on every relevant source change, including A-B-A.
    This adapter compares it; it neither creates nor persists the generation.
    """
    source_ref: str
    generation: int
    source_digest: str


@dataclasses.dataclass(frozen=True, slots=True)
class TaskRequirements:
    work: WorkRequest
    requires_tools: bool
    requires_vision: bool
    context_tokens: int
    required_profile_capabilities: frozenset[str] = frozenset()


@dataclasses.dataclass(frozen=True, slots=True)
class OriginalSelection:
    expected: ExpectedChildSelection
    child: Job
    planner_job: Job
    original_attempt: Attempt | None
    # Existing admitted-plan identity, not an admission invented by this module.
    admitted_plan_identity: dict[str, str]


@dataclasses.dataclass(frozen=True, slots=True)
class OwnerCapacityFacts:
    """Ephemeral, closed projection from qualified Capacity/Runtime owners.

    None means unknown, including cooldown. startable_jobs is the owner's
    finite, all-horizons estimate after its entitlement/account checks; it is
    not a token balance. V1 readiness/catalog membership cannot produce it.
    Tools/vision/context are bound to this exact model and execution profile.
    """
    epoch: OwnerEpoch
    observed_at_ms: int
    expires_at_ms: int
    coverage: ObservationCoverage
    worker_id: str
    quota_class: str
    quota_fence_generation: int
    model_alias: str
    execution_profile_digest: str
    host_ref: str
    boot_ref: str
    lane_id: str
    capacity_capability_id: str
    worker_source_config_digest: str
    model_enabled: bool | None
    model_entitled: bool | None
    supports_tools: bool | None
    supports_vision: bool | None
    context_window_tokens: int | None
    startable_jobs: int | None
    cooldown_active: bool | None
    lane_limit: int | None
    lane_in_use: int | None
    # Owner-qualified association of this worker/lane with the exact physical
    # profile, carrier, source and destination. Never infer a generic mapping.
    physical_request_fingerprint: str


@dataclasses.dataclass(frozen=True, slots=True)
class PhysicalInputs:
    request: dict[str, Any]
    policy: dict[str, Any]
    current_charges: tuple[dict[str, Any], ...] | None
    observations: dict[str, Any] | None
    pressure_snapshot: dict[str, Any] | None


@dataclasses.dataclass(frozen=True, slots=True)
class CandidateInputs:
    worker: Worker
    quota: WorkerQuotaClass | None
    placement_fact: placement.PlacementCandidateFact
    source_before: OwnerEpoch | None
    facts: OwnerCapacityFacts | None
    source_after: OwnerEpoch | None
    readiness: dict[str, Any] | None
    physical: PhysicalInputs
    # Preserve/revalidate the actual wire when the incumbent native V2 owner
    # supplied it. This is not a generic provider normalization/fallback path.
    native_snapshot: dict[str, Any] | None = None
    native_join: dict[str, Any] | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class HermesCapacityRequest:
    requirements: TaskRequirements
    suitability: RoutingDecision
    origin: OriginalSelection
    responsibility: ResponsibilityFact
    root_work_placement_union: tuple[dict[str, Any], ...]
    inherited_work_placement_union: tuple[dict[str, Any], ...]
    # One incumbent-selected member; no iteration/fallback across pools.
    selected_placement: dict[str, str]
    demand: placement.PlacementDemand
    candidates: tuple[CandidateInputs, ...]
    now_ms: int
    evaluation_mode: EvaluationMode = EvaluationMode.OWNER_QUALIFIED


@dataclasses.dataclass(frozen=True, slots=True)
class HermesCapacityDecision:
    """Immutable wire; each read returns a defensive copy of public fields."""
    state: DecisionState
    code: str
    _wire: str = dataclasses.field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self._wire)


class _Stop(Exception):
    def __init__(self, state: DecisionState, code: str):
        self.state, self.code = state, code


def _refuse(code: str) -> None:
    raise _Stop(DecisionState.REFUSED, code)


def _unavailable(code: str) -> None:
    raise _Stop(DecisionState.UNAVAILABLE, code)


def _token(value: object) -> str:
    if type(value) is not str or _TOKEN.fullmatch(value) is None:
        _refuse("INPUT_INVALID")
    return value


def _integer(value: object, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value < 2**63:
        _refuse("INPUT_INVALID")
    return value


def _sha(value: object) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        _refuse("INPUT_INVALID")
    return value


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("ascii")).hexdigest()


def _epoch(value: OwnerEpoch) -> None:
    if type(value) is not OwnerEpoch:
        _refuse("SOURCE_IDENTITY_INVALID")
    _token(value.source_ref)
    _integer(value.generation, 1)
    _sha(value.source_digest)


def _result(state, code, *, provenance=None, trace=(), candidate=None, selection=None):
    wire = {
        "schema": SCHEMA, "state": state.value, "code": code,
        "candidate": candidate, "trace": list(trace), "provenance": provenance,
        "incumbent_selection": selection,
        "selection_is_commitment": False, "capacity_reserved": False,
        "admitted_capacity": False, "worker_started": False,
        "claim_time_revalidation_required": True,
    }
    wire["decision_sha256"] = _digest(wire)
    return HermesCapacityDecision(state, code, _canonical(wire))


def _origin(value: OriginalSelection) -> dict[str, Any]:
    if (type(value) is not OriginalSelection or type(value.expected) is not ExpectedChildSelection
            or type(value.child) is not Job or type(value.planner_job) is not Job):
        _refuse("ORIGIN_INVALID")
    expected, child, planner, attempt = value.expected, value.child, value.planner_job, value.original_attempt
    if attempt is None:
        _refuse("ORIGINAL_ATTEMPT_MISSING")
    if type(attempt) is not Attempt:
        _refuse("ORIGIN_INVALID")
    public = dataclasses.asdict(expected)
    for key in ("root_job_id", "parent_job_id", "job_id", "plan_attempt_id", "plan_step_id", "command_id"):
        _token(public[key])
    _sha(expected.plan_digest)
    _integer(expected.repair_round)
    _integer(expected.attempt_ordinal, 1)
    if expected.expected_current_attempt_id is not None or child.current_attempt_id is not None:
        _refuse("EXISTING_ATTEMPT_REQUIRES_REOBSERVATION")
    if child.orchestration_role not in {"work", "repair"} or child.status is not JobStatus.QUEUED:
        _refuse("FRESH_WORK_CHILD_REQUIRED")
    if (attempt.attempt_id != expected.plan_attempt_id or attempt.job_id != planner.job_id
            or planner.current_attempt_id != attempt.attempt_id
            or planner.root_job_id != expected.root_job_id
            or planner.parent_job_id != expected.parent_job_id
            or planner.orchestration_role != "plan"):
        _refuse("ORIGINAL_ATTEMPT_MISMATCH")
    if attempt.status is not AttemptStatus.COMPLETED or planner.status is not JobStatus.COMPLETED:
        _unavailable("ORIGINAL_PLAN_UNFINISHED")
    if (type(value.admitted_plan_identity) is not dict
            or set(value.admitted_plan_identity) != {"plan_attempt_id", "plan_digest"}):
        _refuse("ADMITTED_PLAN_IDENTITY_INVALID")
    # This incumbent validator is storeless despite accepting an unused
    # connection argument. It binds the exact child, original command and plan.
    row = {key: getattr(child, key) for key in (
        "job_id", "parent_job_id", "root_job_id", "plan_attempt_id", "plan_digest",
        "plan_step_id", "repair_round", "current_attempt_id", "attempt_count", "orchestration_role",
    )}
    _assert_expected_child_selection(None, row, expected, admission=value.admitted_plan_identity)
    public["original_attempt_version"] = _integer(attempt.version, 1)
    public["original_attempt_fence_generation"] = _integer(attempt.fence_generation, 1)
    return public


def _request(request: HermesCapacityRequest, router: ModelRouter):
    if type(request) is not HermesCapacityRequest or type(router) is not ModelRouter:
        _refuse("INPUT_INVALID")
    _integer(request.now_ms, 1)
    if type(request.evaluation_mode) is not EvaluationMode:
        _refuse("INPUT_INVALID")
    requirements = request.requirements
    if (type(requirements) is not TaskRequirements or type(requirements.work) is not WorkRequest
            or type(requirements.requires_tools) is not bool or type(requirements.requires_vision) is not bool
            or type(requirements.required_profile_capabilities) is not frozenset):
        _refuse("INPUT_INVALID")
    _integer(requirements.context_tokens, 1)
    for capability in requirements.required_profile_capabilities:
        _token(capability)
    if type(request.suitability) is not RoutingDecision or request.suitability.mode is not RouteMode.WORKER:
        _refuse("WORKER_ROUTE_REQUIRED")
    incumbent = router.route(requirements.work)
    if request.suitability != incumbent:
        _refuse("SUITABILITY_CHANGED")
    constraints = incumbent.job_constraints()
    origin = _origin(request.origin)
    if (type(request.root_work_placement_union) is not tuple
            or type(request.inherited_work_placement_union) is not tuple):
        _refuse("PLACEMENT_UNION_INVALID")
    root = _normalise_work_placement_union(copy.deepcopy(request.root_work_placement_union))
    inherited = _normalise_work_placement_union(copy.deepcopy(request.inherited_work_placement_union))
    if any(member not in root for member in inherited):
        _refuse("PLACEMENT_UNION_WIDENED")
    selected = request.selected_placement
    if (type(selected) is not dict
            or set(selected) not in ({"provider_realm", "quota_class"}, {"provider_realm", "quota_class", "model"})):
        _refuse("PLACEMENT_INVALID")
    for item in selected.values():
        _token(item)
    if type(request.demand) is not placement.PlacementDemand:
        _refuse("DEMAND_INVALID")
    if (request.demand.provider != selected["provider_realm"]
            or request.demand.quota_class != selected["quota_class"]
            or not set(incumbent.required_capabilities).issubset(request.demand.required_capabilities)):
        _refuse("DEMAND_MISMATCH")
    projected = _project_work_placement(
        constraints, {}, copy.deepcopy(selected),
        raw_root_constraints={"work_placement_union": inherited},
        plan_schema_version="mastermind.execution_plan/v5",
    )
    if (any(projected.get(key) != constraints.get(key) for key in _ROUTE_FIELDS)
            or not set(projected["preferred_model_aliases"]).issubset(incumbent.preferred_model_aliases)):
        _refuse("PLACEMENT_ROUTE_WIDENED")
    # Respect the child's inherited requirements and all route narrowing. The
    # caller must ask the incumbent Router about the actual child, not an
    # easier WorkRequest. We never repair a stale suitability result ourselves.
    child_constraints = request.origin.child.constraints
    if type(child_constraints) is not dict:
        _refuse("INPUT_INVALID")
    for key in ("task_kind", "risk", "ambiguity"):
        if key in child_constraints and child_constraints[key] != constraints[key]:
            _refuse("INHERITED_REQUIREMENTS_MISMATCH")
    for key in ("required_capabilities", "excluded_worker_ids"):
        if key in child_constraints:
            values = child_constraints[key]
            if type(values) is not list or any(type(value) is not str for value in values):
                _refuse("INPUT_INVALID")
            if not set(values).issubset(constraints[key]):
                _refuse("INHERITED_REQUIREMENTS_MISMATCH")
    if "work_placement_union" in child_constraints:
        child_union = _normalise_work_placement_union(copy.deepcopy(child_constraints["work_placement_union"]))
        if any(member not in child_union for member in inherited):
            _refuse("PLACEMENT_UNION_WIDENED")
    for key in ("paid_execution_route", "attended_route"):
        if key in child_constraints and child_constraints[key] != projected.get(key):
            _refuse("INHERITED_ROUTE_MISMATCH")
    for key in (*_ROUTE_FIELDS, "provider", "model", "effort", "cost_class"):
        if key in child_constraints and key in projected and child_constraints[key] != projected[key]:
            _refuse("INHERITED_ROUTE_MISMATCH")
    if "preferred_model_aliases" in child_constraints:
        aliases = child_constraints["preferred_model_aliases"]
        if type(aliases) is not list or not aliases or not set(aliases).issubset(incumbent.preferred_model_aliases):
            _refuse("INHERITED_ROUTE_MISMATCH")
        projected["preferred_model_aliases"] = [alias for alias in projected["preferred_model_aliases"] if alias in aliases]
        if not projected["preferred_model_aliases"]:
            _refuse("INHERITED_ROUTE_MISMATCH")
    if "eligible_quota_classes" in child_constraints and selected["quota_class"] not in child_constraints["eligible_quota_classes"]:
        _refuse("INHERITED_ROUTE_MISMATCH")
    for key in ("model", "effort", "cost_class"):
        if key in child_constraints:
            projected[key] = child_constraints[key]
    if type(request.responsibility) is not ResponsibilityFact or request.responsibility.root_job_id != origin["root_job_id"]:
        _refuse("RESPONSIBILITY_ROOT_MISMATCH")
    if type(request.candidates) is not tuple or len(request.candidates) > MAX_CANDIDATES:
        _refuse("CANDIDATE_SET_INVALID")
    provenance = {
        "origin": origin, "router_decision_sha256": _digest(incumbent.to_dict()),
        "requirements_sha256": _digest({
            "work": dataclasses.asdict(requirements.work), "requires_tools": requirements.requires_tools,
            "requires_vision": requirements.requires_vision, "context_tokens": requirements.context_tokens,
            "required_profile_capabilities": sorted(requirements.required_profile_capabilities),
        }),
        "root_union_sha256": _digest(root), "inherited_union_sha256": _digest(inherited),
        "selected_placement": copy.deepcopy(selected), "decision_time_ms": request.now_ms,
        "effective_constraints_sha256": _digest(projected),
        "evaluation_mode": request.evaluation_mode.value,
    }
    return projected, provenance


def _facts(value: CandidateInputs, request: HermesCapacityRequest):
    facts = value.facts
    if facts is None or value.source_before is None or value.source_after is None:
        _unavailable("SOURCE_UNAVAILABLE")
    if type(facts) is not OwnerCapacityFacts:
        _refuse("INPUT_INVALID")
    for epoch in (facts.epoch, value.source_before, value.source_after):
        _epoch(epoch)
    if not value.source_before == facts.epoch == value.source_after:
        _unavailable("SOURCE_CHANGED_OR_ABA")
    if type(facts.coverage) is not ObservationCoverage:
        _refuse("INPUT_INVALID")
    if facts.coverage is not ObservationCoverage.COMPLETE:
        _unavailable("OBSERVATION_INCOMPLETE")
    observed = _integer(facts.observed_at_ms, 1)
    expires = _integer(facts.expires_at_ms, 1)
    if not 0 < expires - observed <= OBSERVATION_LIFETIME_MS:
        _refuse("OBSERVATION_TTL_INVALID")
    if not observed <= request.now_ms < expires:
        _unavailable("OBSERVATION_EXPIRED")
    for field in ("worker_id", "quota_class", "model_alias", "lane_id", "capacity_capability_id"):
        _token(getattr(facts, field))
    for field in ("execution_profile_digest", "worker_source_config_digest", "physical_request_fingerprint"):
        _sha(getattr(facts, field))
    if (type(facts.host_ref) is not str or HOST_REF_RE.fullmatch(facts.host_ref) is None
            or type(facts.boot_ref) is not str or BOOT_REF_RE.fullmatch(facts.boot_ref) is None):
        _refuse("PHYSICAL_IDENTITY_INVALID")
    _integer(facts.quota_fence_generation)
    for field in ("model_enabled", "model_entitled", "supports_tools", "supports_vision", "cooldown_active"):
        if getattr(facts, field) is not None and type(getattr(facts, field)) is not bool:
            _refuse("INPUT_INVALID")
    for field in ("context_window_tokens", "startable_jobs", "lane_limit", "lane_in_use"):
        if getattr(facts, field) is not None:
            _integer(getattr(facts, field))
    if facts.model_enabled is False or facts.model_entitled is False:
        _refuse("MODEL_DISABLED_OR_UNENTITLED")
    if facts.model_enabled is None or facts.model_entitled is None:
        _unavailable("MODEL_ENTITLEMENT_UNKNOWN")
    for required, supported in ((request.requirements.requires_tools, facts.supports_tools),
                                (request.requirements.requires_vision, facts.supports_vision)):
        if required and supported is None:
            _unavailable("MODEL_CAPABILITY_UNKNOWN")
        if required and supported is False:
            _refuse("MODEL_CAPABILITY_MISMATCH")
    if facts.context_window_tokens is None:
        _unavailable("MODEL_CONTEXT_UNKNOWN")
    if facts.context_window_tokens < request.requirements.context_tokens:
        _refuse("MODEL_CONTEXT_INSUFFICIENT")
    if (facts.startable_jobs is None or facts.cooldown_active is None
            or facts.lane_limit is None or facts.lane_in_use is None):
        _unavailable("CAPACITY_UNKNOWN")
    if facts.cooldown_active:
        _unavailable("CAPACITY_COOLDOWN")
    if facts.startable_jobs == 0 or facts.lane_in_use >= facts.lane_limit:
        _unavailable("CAPACITY_EXHAUSTED")
    return facts


def _physical(value: PhysicalInputs, facts: OwnerCapacityFacts, request_context: HermesCapacityRequest):
    if type(value) is not PhysicalInputs:
        _refuse("INPUT_INVALID")
    if value.current_charges is None or value.observations is None or value.pressure_snapshot is None:
        _unavailable("PHYSICAL_OBSERVATION_UNAVAILABLE")
    if type(value.current_charges) is not tuple:
        _refuse("INPUT_INVALID")
    request, policy, observations = copy.deepcopy((value.request, value.policy, value.observations))
    charges = copy.deepcopy(value.current_charges)
    expected = request_context.origin.expected
    if (request["operation_key"] != f"finite-initial:{expected.job_id}"
            or request["command_id"] != f"physical:{expected.command_id}:reserve"):
        _refuse("PHYSICAL_ORIGIN_MISMATCH")
    pressure = validate_host_pressure_snapshot(value.pressure_snapshot)
    if (request["host_id"] != facts.host_ref or request["boot_id"] != facts.boot_ref
            or pressure["host_ref"] != facts.host_ref or pressure["boot_ref"] != facts.boot_ref):
        _unavailable("PHYSICAL_GENERATION_CHANGED")
    snapshot = validate_host_capacity_snapshot(observations["host_capacity_evidence"]["snapshot"])
    if (snapshot["telemetry_status"] != "COMPLETE" or snapshot["hp0_telemetry_status"] != "COMPLETE"
            or pressure["telemetry_status"] != "COMPLETE"):
        _unavailable("PHYSICAL_OBSERVATION_INCOMPLETE")
    bound = validate_hp0_binding(pressure, facts.host_ref, facts.boot_ref)
    if any(snapshot[key] != val for key, val in bound.items()):
        _refuse("PHYSICAL_OBSERVATION_MISMATCH")
    # Existing owner validation and measured-pool projection, never new pressure
    # thresholds or treating absent metrics/charges as zero utilization.
    production = request_context.evaluation_mode is EvaluationMode.OWNER_QUALIFIED
    if not production and policy.get("qualification") != "SYNTHETIC_TEST_ONLY":
        _refuse("FIXTURE_POLICY_REQUIRED")
    physical._validate_policy(policy, allow_synthetic=not production)
    normalized = physical.validate_physical_request(request)
    if physical.physical_request_fingerprint(normalized) != facts.physical_request_fingerprint:
        _refuse("PHYSICAL_LANE_BINDING_MISMATCH")
    host, _ = physical._select_host_qualification(normalized, policy)
    if host is None:
        _unavailable("HOST_QUALIFICATION_UNAVAILABLE")
    measured = {}
    for phase in normalized["phases"]:
        profile = next(item for item in host["profiles"] if item["profile"] == phase["profile"])
        pools = _observed_pools(profile, host, snapshot, pressure,
                                normalized["source_binding"]["destination"]["capacity_pool_id"])
        for key, entry in pools.items():
            if key in measured and measured[key] != entry:
                _refuse("PHYSICAL_OBSERVATION_MISMATCH")
            measured[key] = entry
    if observations.get("pools") != measured:
        _refuse("PHYSICAL_OBSERVATION_MISMATCH")
    result = physical.evaluate_reservation(normalized, policy=policy, current_charges=charges,
        observations=observations, decision_time_ms=request_context.now_ms, production=production)
    # RESERVED here is the pure evaluator's hypothetical result, never a
    # reservation receipt. Only its digest is projected.
    return {"physical_evaluation_sha256": _digest(result),
            "physical_inputs_sha256": _digest([normalized, policy, charges, observations, pressure]),
            "physical_qualification": policy["qualification"]}


def _candidate(value: CandidateInputs, request: HermesCapacityRequest, router: ModelRouter, constraints: dict):
    if (type(value) is not CandidateInputs or type(value.worker) is not Worker
            or type(value.placement_fact) is not placement.PlacementCandidateFact):
        _refuse("INPUT_INVALID")
    if value.quota is None:
        _unavailable("REGISTERED_QUOTA_MISSING")
    if type(value.quota) is not WorkerQuotaClass:
        _refuse("INPUT_INVALID")
    worker, quota = value.worker, value.quota
    # Do not copy/project unrelated metadata, provider homes or arbitrary owner
    # records. Only this closed subset reaches route matching or a digest.
    metadata = {key: copy.deepcopy(quota.metadata[key]) for key in _METADATA_FIELDS if key in quota.metadata}
    fact = dataclasses.replace(value.placement_fact)
    facts = _facts(value, request)
    if (worker.worker_id != quota.worker_id or worker.worker_id != fact.worker_id
            or worker.worker_id != facts.worker_id or quota.quota_class != fact.quota_class
            or quota.quota_class != facts.quota_class or worker.provider != quota.provider
            or worker.provider != fact.provider or worker.account_label != fact.account_label
            or quota.fence_generation != facts.quota_fence_generation):
        _refuse("REGISTERED_IDENTITY_MISMATCH")
    if (worker.status is not WorkerStatus.AVAILABLE or quota.status is not WorkerStatus.AVAILABLE
            or worker.active_job_id is not None or quota.active_job_id is not None or quota.active_attempt_id is not None):
        _unavailable("REGISTERED_LANE_UNAVAILABLE")
    if (not fact.capabilities.issubset(worker.capabilities) or not fact.capabilities.issubset(quota.capabilities)
            or not request.demand.required_capabilities.issubset(fact.capabilities)):
        _refuse("REGISTERED_CAPABILITY_MISMATCH")
    if fact.observed_at_ms != facts.observed_at_ms:
        _refuse("PLACEMENT_OBSERVATION_MISMATCH")
    if facts.model_alias not in constraints["preferred_model_aliases"]:
        _refuse("MODEL_OUTSIDE_INCUMBENT_TIER")
    model = router.resolve_model_alias(facts.model_alias)
    provider = router.providers[model.provider_alias]
    if provider.enabled is not True or provider.autonomous_allowed is not True:
        _refuse("PROVIDER_DISABLED")
    profile = router.capability_registry.resolve(model.execution_profile_id)
    if (worker.worker_type != model.adapter_id or provider.adapter_id != model.adapter_id
            or not adapter_supports_execution_surface(model.adapter_id, profile.execution_surface)):
        _refuse("WORKER_ADAPTER_MISMATCH")
    if (profile.profile_digest != model.execution_profile_digest
            or model.execution_profile_digest != facts.execution_profile_digest
            or model.capability_policy_version != router.capability_registry.policy_version
            or model.capability_policy_digest != router.capability_registry.policy_digest
            or model.provider_alias != worker.provider or quota.model != model.model
            or quota.effort != model.effort or quota.cost_class != model.cost_class
            or metadata.get("model_alias") != facts.model_alias):
        _refuse("MODEL_BINDING_MISMATCH")
    if not request.requirements.required_profile_capabilities.issubset(profile.required_capability_names):
        _refuse("PROFILE_CAPABILITY_MISMATCH")
    if any(key in constraints and getattr(quota, key) != constraints[key] for key in ("model", "effort", "cost_class")):
        _refuse("INHERITED_ROUTE_MISMATCH")
    if not _capacity_matches_route({"worker_id": worker.worker_id, "metadata_json": _canonical(metadata)}, constraints):
        _refuse("REGISTERED_ROUTE_MISMATCH")
    join = validate_capacity_join(metadata.get("capacity_join"))
    if (join.host_ref != facts.host_ref or join.capacity_capability_id != facts.capacity_capability_id
            or join.worker_source_config_digest != facts.worker_source_config_digest):
        _refuse("CAPACITY_JOIN_MISMATCH")
    if value.readiness is None:
        _unavailable("READINESS_UNAVAILABLE")
    readiness = validate_worker_capacity_observation(copy.deepcopy(value.readiness),
        expected_host_ref=join.host_ref, expected_capacity_capability_id=join.capacity_capability_id,
        expected_source_config_digest=join.worker_source_config_digest, trusted_current_ms=request.now_ms)
    native_digest = None
    if value.native_snapshot is not None or value.native_join is not None:
        if value.native_snapshot is None or value.native_join is None:
            _unavailable("NATIVE_CAPACITY_INCOMPLETE")
        row = native_capacity_v2.known_admissible(copy.deepcopy(value.native_snapshot),
            copy.deepcopy(value.native_join), now_ms=request.now_ms)
        if (row["host_ref"] != facts.host_ref or row["boot_ref"] != facts.boot_ref
                or row["provider"] != worker.provider
                or row["capacity_capability_id"] != facts.capacity_capability_id
                or row["worker_source_config_digest"] != facts.worker_source_config_digest):
            _refuse("NATIVE_CAPACITY_IDENTITY_MISMATCH")
        native_digest = value.native_snapshot["snapshot_hash"]
    evidence = _physical(value.physical, facts, request)
    public = {
        "worker_id": worker.worker_id, "quota_class": quota.quota_class,
        "provider": worker.provider, "account_label": worker.account_label,
        "model_alias": facts.model_alias, "model": model.model, "effort": model.effort,
        "execution_profile_id": model.execution_profile_id,
        "execution_profile_digest": model.execution_profile_digest,
        "host_ref": facts.host_ref, "boot_ref": facts.boot_ref, "lane_id": facts.lane_id,
        "capacity_capability_id": facts.capacity_capability_id,
        "quota_fence_generation": facts.quota_fence_generation,
        "source": dataclasses.asdict(facts.epoch), "observed_at_ms": facts.observed_at_ms,
        "expires_at_ms": facts.expires_at_ms, "owner_facts_sha256": _digest(dataclasses.asdict(facts)),
        "registry_route_sha256": _digest(metadata), "readiness_sha256": readiness.observation_digest,
        "native_snapshot_sha256": native_digest, **evidence,
    }
    return fact, public


def decide_hermes_capacity(request: HermesCapacityRequest, *, router: ModelRouter) -> HermesCapacityDecision:
    """Return a closed CANDIDATE/REFUSED/UNAVAILABLE without touching owners.

    router must be the explicitly injected current preloaded incumbent. The
    caller owns acquisition/authentication/atomicity; this function owns only
    bounded consistency checking and composition of existing pure policies.
    """
    try:
        constraints, provenance = _request(request, router)
    except _Stop as exc:
        return _result(exc.state, exc.code)
    except (ValueError, TypeError, KeyError, AttributeError, RuntimeError, OverflowError):
        return _result(DecisionState.REFUSED, "OWNER_INPUT_INVALID")
    trace, eligible, projections, seen = [], [], {}, set()
    for value in request.candidates:
        if type(value) is not CandidateInputs or type(value.worker) is not Worker:
            return _result(DecisionState.REFUSED, "INPUT_INVALID", provenance=provenance)
        try:
            worker_id = _token(value.worker.worker_id)
        except _Stop as exc:
            return _result(exc.state, exc.code, provenance=provenance)
        if worker_id in seen:
            return _result(DecisionState.REFUSED, "DUPLICATE_WORKER", provenance=provenance)
        seen.add(worker_id)
        try:
            fact, public = _candidate(value, request, router, constraints)
            eligible.append(fact)
            projections[worker_id] = public
            trace.append({"worker_id": worker_id, "state": "QUALIFIED_INPUT", "code": "OWNER_CHECKS_PASSED",
                          "evidence_sha256": _digest(public)})
        except _Stop as exc:
            trace.append({"worker_id": worker_id, "state": exc.state.value, "code": exc.code, "evidence_sha256": None})
        except (physical.PhysicalResourceRefusal, CapacityObservationError, native_capacity_v2.NativeCapacityRefusal) as exc:
            # Owner reason codes are fixed identifiers; never serialize an
            # exception message that may contain a path or provider response.
            owner_code = exc.args[0] if type(exc) is native_capacity_v2.NativeCapacityRefusal else exc.code
            if type(owner_code) is not str or re.fullmatch(r"[A-Z][A-Z0-9_]{0,95}", owner_code) is None:
                owner_code = "OWNER_REFUSAL"
            trace.append({"worker_id": worker_id, "state": "UNAVAILABLE", "code": "OWNER_EVIDENCE_UNAVAILABLE",
                          "owner_code": owner_code, "evidence_sha256": None})
        except (ValueError, TypeError, KeyError, AttributeError, RuntimeError, OverflowError, StopIteration):
            trace.append({"worker_id": worker_id, "state": "REFUSED", "code": "OWNER_INPUT_INVALID", "evidence_sha256": None})
    trace.sort(key=lambda row: row["worker_id"])
    try:
        selection = placement.select_placement(responsibility=request.responsibility, demand=request.demand, candidates=eligible)
        wire = placement.validate_placement_selection(selection.to_dict())
    except (ValueError, TypeError):
        return _result(DecisionState.REFUSED, "PLACEMENT_INPUT_INVALID", provenance=provenance, trace=trace)
    if selection.state is placement.SelectionState.SELECTED:
        selected = projections[wire["selected"]["worker_id"]]
        return _result(DecisionState.CANDIDATE, "INCUMBENT_SELECTED", provenance=provenance,
                       trace=trace, candidate=selected, selection=wire)
    state = DecisionState.REFUSED if not eligible and any(row["state"] == "REFUSED" for row in trace) else DecisionState.UNAVAILABLE
    return _result(state, "NO_ELIGIBLE_CANDIDATE", provenance=provenance, trace=trace, selection=wire)


__all__ = ["CandidateInputs", "DecisionState", "EvaluationMode", "HermesCapacityDecision", "HermesCapacityRequest",
           "ObservationCoverage", "OriginalSelection", "OwnerCapacityFacts", "OwnerEpoch", "PhysicalInputs",
           "TaskRequirements", "decide_hermes_capacity"]
