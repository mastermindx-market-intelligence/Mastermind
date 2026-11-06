"""Pure, private projection of canonical Executive nested-delegation facts.

This is not an admission port. The installed owner must construct observations
from one coherent, complete Runtime read, after validating its retained plan,
permission, placement, terminal and review evidence. A digest or an instance of
one of these classes authenticates nothing. Recheck the observation and all
existing admission/lease guards in the OWNER'S transaction before any effect.

No Runtime, store, clock, callback, provider, registry or child creator is used.
All records are recursively immutable; only temporary copies reach the existing
pure hierarchy/policy validators. Public Hermes arguments remain action/command.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from control_plane.executive_coo_hierarchy import (
    HierarchyError, ancestors, assert_admission_open, descendant_ids,
    inherited_grant, validate_grant, validate_tree,
)
from control_plane.executive_coo_policy import (
    CooCyclePolicy, CooCyclePolicyError, HIERARCHY_POLICY_SHA256,
)
from integrations.hermes_delegate.schema import SubmissionError, parse_selected_child


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_JOB_STATES = frozenset({"QUEUED", "RUNNING", "CHECKPOINTED", "RATE_LIMITED",
                         "FAILED", "LOST", "CANCEL_REQUESTED", "COMPLETED", "CANCELLED"})
_ATTEMPT_STATES = (_JOB_STATES - {"QUEUED"}) | {"CLAIMED"}
_TERMINAL = frozenset({"COMPLETED", "FAILED", "LOST", "RATE_LIMITED", "CANCELLED"})
_ROLES = frozenset({"aggregation", "plan", "work", "repair", "review"})


class DelegationContractError(ValueError):
    """A bounded, secret-free contract refusal, not a lifecycle transition."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Grant:
    descendant_limit: int
    max_depth: int
    policy_sha256: str = HIERARCHY_POLICY_SHA256


@dataclass(frozen=True)
class AuthorityBinding:
    root_job_id: str
    coordinator_job_id: str
    permission_digest: str
    generation_digest: str


@dataclass(frozen=True)
class JobFact:
    job_id: str
    parent_job_id: str | None
    root_job_id: str
    depth: int
    orchestration_role: str
    status: str = "QUEUED"
    cancel_requested_at_ms: int | None = None
    current_attempt_id: str | None = None
    attempt_count: int = 0
    grant: Grant | None = None
    placement_union_digest: str | None = None
    plan_attempt_id: str | None = None
    plan_digest: str | None = None
    plan_step_id: str | None = None
    repair_round: int = 0
    reviews_job_id: str | None = None
    supersedes_job_id: str | None = None


@dataclass(frozen=True)
class StepFact:
    """Current repair revision plus the COMPLETE original reserved allowance.

    review_required is the owner's EFFECTIVE requirement (including inherited
    business impact), not the planner's unqualified preference.
    """

    step_id: str
    current_job_id: str | None
    current_repair_round: int
    review_required: bool
    reserved_slots: int
    initial_work_job_id: str | None
    initial_work_command_id: str | None
    delegation: Grant | None = None
    prerequisite_step_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanFact:
    root_job_id: str
    coordinator_job_id: str
    planner_job_id: str
    plan_attempt_id: str
    plan_digest: str
    reservation_digest: str
    reserved_children_total: int
    steps: tuple[StepFact, ...]
    schema_version: str = "mastermind.execution_plan/v5"


@dataclass(frozen=True)
class CommandFact:
    command: str
    job_id: str
    attempt_ordinal: int
    attempt_id: str | None
    attempt_status: str | None
    fence_generation: int | None
    effect_unknown: bool = False


@dataclass(frozen=True)
class RequeueFact:
    """Existing OWNER-validated JOB_REQUEUED evidence, never a retry grant issued here."""

    job_id: str
    previous_attempt_id: str
    previous_attempt_ordinal: int
    event_id: int
    latest_job_event_id: int
    evidence_digest: str


@dataclass(frozen=True)
class ResultFact:
    """References to OWNER-validated terminal and, if owed, review evidence.

    Review acceptance must already include Runtime's real principal independence
    checks. This bridge neither issues a review verdict nor validates identities.
    """

    job_id: str
    attempt_id: str
    command: str
    plan_attempt_id: str
    plan_digest: str
    plan_step_id: str
    repair_round: int
    fence_generation: int
    result_envelope_digest: str
    terminal_evidence_digest: str
    outcome: str
    review_attempt_id: str | None = None
    review_acceptance_digest: str | None = None
    reviewed_result_digest: str | None = None


@dataclass(frozen=True)
class OwnerObservation:
    authority: AuthorityBinding
    snapshot_digest: str
    complete: bool
    may_read: bool
    may_submit: bool
    jobs: tuple[JobFact, ...]
    plans: tuple[PlanFact, ...]
    commands: tuple[CommandFact, ...] = ()
    results: tuple[ResultFact, ...] = ()
    requeues: tuple[RequeueFact, ...] = ()


@dataclass(frozen=True)
class FrozenChild:
    authority: AuthorityBinding
    parent_job_id: str
    job_id: str
    plan_attempt_id: str
    plan_digest: str
    plan_step_id: str
    repair_round: int
    reservation_digest: str
    placement_union_digest: str | None
    command: str
    attempt_ordinal: int
    expected_current_attempt_id: str | None = None
    original_attempt_id: str | None = None


@dataclass(frozen=True)
class TreeProjection:
    root_job_id: str
    total_descendants: int
    maximum_observed_depth: int
    reservations: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class OwnerRequest:
    """An inert owner request. Even FRESH_REQUEST is NOT a reservation/claim."""

    action: str
    command: str
    disposition: str
    selection: FrozenChild
    expected_snapshot_digest: str
    original_attempt_id: str | None
    fence_generation: int | None
    attempt_status: str | None
    result_envelope_digest: str | None = None
    terminal_evidence_digest: str | None = None
    requeue_evidence_digest: str | None = None

    def public_request(self) -> dict[str, str]:
        return {"action": self.action, "command": self.command}


@dataclass(frozen=True)
class AggregateProjection:
    coordinator_job_id: str
    expected_snapshot_digest: str
    ready_for_owner_handoff: bool
    pending_job_ids: tuple[str, ...]
    pending_steps: tuple[tuple[str, str], ...]
    unresolved_commands: tuple[str, ...]
    accepted_result_digests: tuple[str, ...]


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise DelegationContractError(code)


def _text(value: Any, *, digest: bool = False) -> None:
    _require(type(value) is str and bool((_DIGEST if digest else _ID).fullmatch(value)),
             "DIGEST_INVALID" if digest else "IDENTITY_INVALID")


def _integer(value: Any, minimum: int = 0, maximum: int = 2**63 - 1) -> None:
    _require(type(value) is int and minimum <= value <= maximum, "INTEGER_INVALID")


def _tuple(value: Any, kind: type, maximum: int) -> None:
    _require(type(value) is tuple and len(value) <= maximum
             and all(type(item) is kind for item in value), "IMMUTABLE_SHAPE_INVALID")


def _binding(value: AuthorityBinding) -> None:
    _require(type(value) is AuthorityBinding, "AUTHORITY_SHAPE_INVALID")
    _text(value.root_job_id)
    _text(value.coordinator_job_id)
    _text(value.permission_digest, digest=True)
    _text(value.generation_digest, digest=True)


def _grant(value: Grant) -> dict[str, Any]:
    _require(type(value) is Grant, "GRANT_MISSING")
    return validate_grant(asdict(value))


def _policy(policy: CooCyclePolicy) -> None:
    _require(type(policy) is CooCyclePolicy, "POLICY_INVALID")
    _tuple(policy.allowed_child_cost_classes, str, 2)
    material = json.dumps(policy.to_dict(), sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    _require(policy.policy_sha256 == HIERARCHY_POLICY_SHA256
             and hashlib.sha256(material).hexdigest() == HIERARCHY_POLICY_SHA256,
             "POLICY_NOT_V5_HIERARCHY")


def _parse(request: Mapping[str, Any]) -> dict[str, str]:
    _require(isinstance(request, Mapping) and set(request) == {"action", "command"}
             and type(request.get("action")) is str and type(request.get("command")) is str,
             "REQUEST_SHAPE_INVALID")
    try:
        return parse_selected_child(request)
    except SubmissionError as exc:
        raise DelegationContractError("REQUEST_INVALID") from exc


def _command_matches(command: str, job: JobFact, ordinal: int) -> None:
    _integer(ordinal, 1, 9_999_999_999)
    _parse({"action": "selected_child_status", "command": command})
    scope = job.job_id if job.orchestration_role == "aggregation" else job.parent_job_id
    _require(command == f"coo-cycle:{scope}:dispatch:{job.job_id}:attempt:{ordinal}",
             "COMMAND_SCOPE_MISMATCH")


def _lineage(job: JobFact) -> tuple[Any, ...]:
    return job.plan_attempt_id, job.plan_digest, job.plan_step_id, job.repair_round


def _validate(observation: OwnerObservation, policy: CooCyclePolicy):
    """Return ephemeral indexes only; never retain a second owner state."""
    _policy(policy)
    _require(type(observation) is OwnerObservation, "OBSERVATION_SHAPE_INVALID")
    _binding(observation.authority)
    _text(observation.snapshot_digest, digest=True)
    _require(observation.complete is True, "OBSERVATION_INCOMPLETE")
    _require(type(observation.may_read) is bool and type(observation.may_submit) is bool,
             "PERMISSION_INVALID")
    _tuple(observation.jobs, JobFact, 17)
    _tuple(observation.plans, PlanFact, 17)
    _tuple(observation.commands, CommandFact, 128)
    _tuple(observation.results, ResultFact, 128)
    _tuple(observation.requeues, RequeueFact, 17)
    rows = []
    for job in observation.jobs:
        for value in (job.job_id, job.root_job_id):
            _text(value)
        for value in (job.parent_job_id, job.current_attempt_id, job.reviews_job_id,
                      job.plan_attempt_id, job.plan_step_id, job.supersedes_job_id):
            if value is not None:
                _text(value)
        if job.plan_digest is not None:
            _text(job.plan_digest, digest=True)
        _integer(job.depth, 0, 3)
        _integer(job.attempt_count)
        _integer(job.repair_round, 0, policy.max_repair_rounds)
        if job.cancel_requested_at_ms is not None:
            _integer(job.cancel_requested_at_ms)
        _require(type(job.status) is str and job.status in _JOB_STATES
                 and type(job.orchestration_role) is str and job.orchestration_role in _ROLES,
                 "JOB_STATE_INVALID")
        if job.placement_union_digest is not None:
            _text(job.placement_union_digest, digest=True)
        if job.orchestration_role == "aggregation":
            _grant(job.grant)
        else:
            _require(job.grant is None, "LEAF_CANNOT_DELEGATE")
        rows.append(asdict(job))
    root_id = observation.authority.root_job_id
    current_attempts = [job.current_attempt_id for job in observation.jobs
                        if job.current_attempt_id is not None]
    _require(len(current_attempts) == len(set(current_attempts)), "CURRENT_ATTEMPT_ALIASED")
    jobs = {job.job_id: job for job in observation.jobs}
    tree = validate_tree(rows, root_id)
    root = jobs[root_id]
    _require(root.orchestration_role == "aggregation" and root.grant == Grant(16, 3),
             "ROOT_GRANT_INVALID")
    _require(observation.authority.coordinator_job_id in jobs
             and jobs[observation.authority.coordinator_job_id].orchestration_role == "aggregation",
             "AUTHORITY_COORDINATOR_INVALID")
    plans = {plan.coordinator_job_id: plan for plan in observation.plans}
    _require(len(plans) == len(observation.plans), "DUPLICATE_PLAN")
    _require(len({plan.plan_attempt_id for plan in observation.plans}) == len(plans)
             and len({plan.reservation_digest for plan in observation.plans}) == len(plans),
             "PLAN_RESERVATION_ALIASED")
    for job in observation.jobs:
        if job.orchestration_role == "aggregation":
            _require(len(descendant_ids(tree, job.job_id)) <= job.grant.descendant_limit,
                     "RETAINED_DESCENDANT_BUDGET_EXCEEDED")
        if job.parent_job_id is None:
            continue
        parent = jobs[job.parent_job_id]
        _require(job.depth <= parent.grant.max_depth, "ANCESTOR_DEPTH_EXCEEDED")
        if job.orchestration_role == "aggregation":
            expected = inherited_grant(parent.depth, _grant(parent.grant), {
                "descendant_limit": job.grant.descendant_limit,
                "max_depth": job.grant.max_depth,
            })
            _require(_grant(job.grant) == expected, "GRANT_WIDENED")
        if job.orchestration_role != "plan":
            for value in (job.plan_attempt_id, job.plan_step_id):
                _text(value)
            _text(job.plan_digest, digest=True)
            _require(parent.job_id in plans, "CHILD_RESERVATION_ABSENT")
        if job.orchestration_role == "review":
            _require(job.reviews_job_id in jobs, "REVIEW_TARGET_ABSENT")
        else:
            _require(job.reviews_job_id is None, "REVIEW_TARGET_INVALID")
        if job.orchestration_role != "repair":
            _require(job.supersedes_job_id is None, "REPAIR_PREDECESSOR_INVALID")
    for plan in observation.plans:
        _require(plan.schema_version == "mastermind.execution_plan/v5"
                 and plan.root_job_id == root_id and plan.coordinator_job_id in jobs,
                 "PLAN_SCOPE_INVALID")
        for value in (plan.coordinator_job_id, plan.planner_job_id, plan.plan_attempt_id):
            _text(value)
        for value in (plan.plan_digest, plan.reservation_digest):
            _text(value, digest=True)
        _integer(plan.reserved_children_total, 1, 16)
        _tuple(plan.steps, StepFact, 16)
        coordinator = jobs[plan.coordinator_job_id]
        _require(coordinator.orchestration_role == "aggregation", "PLAN_PARENT_INVALID")
        planner = jobs.get(plan.planner_job_id)
        _require(planner is not None and planner.parent_job_id == coordinator.job_id
                 and planner.orchestration_role == "plan"
                 and planner.current_attempt_id == plan.plan_attempt_id
                 and planner.status in {"COMPLETED", "RUNNING", "CHECKPOINTED"},
                 "PLAN_ATTEMPT_MISMATCH")
        previous: set[str] = set()
        current_ids: set[str] = set()
        reservation_steps = []
        for ordinal, step in enumerate(plan.steps):
            _text(step.step_id)
            if step.current_job_id is not None:
                _text(step.current_job_id)
            _integer(step.current_repair_round, 0, policy.max_repair_rounds)
            _integer(step.reserved_slots, 1, 16)
            _tuple(step.prerequisite_step_ids, str, 15)
            _require(type(step.review_required) is bool and step.step_id not in previous
                     and (step.current_job_id is None or step.current_job_id not in current_ids)
                     and len(set(step.prerequisite_step_ids)) == len(step.prerequisite_step_ids)
                     and set(step.prerequisite_step_ids) <= previous, "STEP_IDENTITY_INVALID")
            previous.add(step.step_id)
            if step.current_job_id is not None:
                current_ids.add(step.current_job_id)
            if step.prerequisite_step_ids:
                _require(step.initial_work_job_id is None and step.initial_work_command_id is None,
                         "DEFERRED_RESERVATION_CHANGED")
            else:
                _text(step.initial_work_job_id)
                _require(step.initial_work_command_id == (
                    f"coo-cycle:{coordinator.job_id}:admit-plan:{plan.plan_attempt_id}:member:{ordinal}"
                ), "INITIAL_RESERVATION_COMMAND_MISMATCH")
            delegation = None
            if step.delegation is not None:
                _grant(step.delegation)
                delegation = {"descendant_limit": step.delegation.descendant_limit,
                              "max_depth": step.delegation.max_depth}
            reserved = (1 + step.delegation.descendant_limit if step.delegation is not None
                        else policy.reserved_step_slots(review_required=step.review_required))
            _require(step.reserved_slots == reserved, "STEP_RESERVATION_MISMATCH")
            reservation_steps.append({"review_required": step.review_required,
                                      "delegation": delegation})
            members = [child for child in observation.jobs
                       if child.parent_job_id == coordinator.job_id and child.plan_step_id == step.step_id]
            revisions = sorted((child for child in members if child.orchestration_role in
                                {"work", "repair", "aggregation"}), key=lambda child: child.repair_round)
            reviews = [child for child in members if child.orchestration_role == "review"]
            if not revisions:
                _require(bool(step.prerequisite_step_ids) and step.current_job_id is None
                         and step.current_repair_round == 0 and not reviews,
                         "INITIAL_WORK_REVISION_MISSING")
            else:
                for index, revision in enumerate(revisions):
                    _require(revision.repair_round == index
                             and revision.orchestration_role == (
                                 ("aggregation" if delegation else "work") if index == 0 else "repair"
                             ) and revision.supersedes_job_id == (
                                 None if index == 0 else revisions[index - 1].job_id
                             ), "REPAIR_LINEAGE_FORKED_OR_SKIPPED")
                    _require(len([review for review in reviews if review.reviews_job_id == revision.job_id])
                             <= policy.max_review_attempts_per_job, "REVIEW_RESERVATION_EXCEEDED")
                current = revisions[-1]
                _require(current.job_id == step.current_job_id
                         and _lineage(current) == (plan.plan_attempt_id, plan.plan_digest,
                                                   step.step_id, step.current_repair_round),
                         "CURRENT_STEP_LINEAGE_MISMATCH")
                _require(current.grant == step.delegation, "CURRENT_STEP_GRANT_MISMATCH")
                _require(step.initial_work_job_id is None or step.initial_work_job_id == revisions[0].job_id,
                         "INITIAL_RESERVATION_JOB_MISMATCH")
            _require(step.review_required or (len(revisions) <= 1 and not reviews),
                     "UNRESERVED_REVIEW_OR_REPAIR")
            for review in reviews:
                target = jobs.get(review.reviews_job_id)
                _require(target in revisions and _lineage(review) == _lineage(target),
                         "REVIEW_BINDING_MISMATCH")
            charged = set()
            for child in observation.jobs:
                if child.parent_job_id == coordinator.job_id and child.plan_step_id == step.step_id:
                    _require(child.plan_attempt_id == plan.plan_attempt_id
                             and child.plan_digest == plan.plan_digest, "RETAINED_PLAN_MISMATCH")
                    charged.add(child.job_id)
                    if child.orchestration_role == "aggregation":
                        charged.update(descendant_ids(tree, child.job_id))
            _require(len(charged) <= reserved, "STEP_RETAINED_BUDGET_EXCEEDED")
        expected_total = policy.reserved_hierarchy_children(
            tuple(reservation_steps), coordinator_depth=coordinator.depth,
            descendant_limit=coordinator.grant.descendant_limit,
            max_depth=coordinator.grant.max_depth,
        )
        _require(expected_total == plan.reserved_children_total, "PLAN_RESERVATION_MISMATCH")
        for child in observation.jobs:
            if child.parent_job_id != coordinator.job_id:
                continue
            if child.orchestration_role == "plan":
                _require(child.job_id == plan.planner_job_id, "DUPLICATE_PLANNER_SLOT")
            else:
                _require(child.plan_step_id in previous, "UNRESERVED_CHILD")
    commands = {}
    attempt_ids: set[str] = set()
    ordinals: set[tuple[str, int]] = set()
    for command in observation.commands:
        _text(command.job_id)
        _require(type(command.effect_unknown) is bool and command.job_id in jobs,
                 "COMMAND_OBSERVATION_INVALID")
        job = jobs[command.job_id]
        _command_matches(command.command, job, command.attempt_ordinal)
        _require(command.command not in commands
                 and (command.job_id, command.attempt_ordinal) not in ordinals,
                 "DUPLICATE_ORIGINAL_COMMAND")
        commands[command.command] = command
        ordinals.add((command.job_id, command.attempt_ordinal))
        if command.attempt_id is None:
            _require(command.effect_unknown and command.attempt_status is None
                     and command.fence_generation is None, "UNKNOWN_EFFECT_MALFORMED")
        else:
            _text(command.attempt_id)
            _integer(command.fence_generation, 1)
            _require(command.attempt_id not in attempt_ids
                     and type(command.attempt_status) is str
                     and command.attempt_status in _ATTEMPT_STATES
                     and command.attempt_ordinal <= job.attempt_count,
                     "ORIGINAL_ATTEMPT_INVALID")
            attempt_ids.add(command.attempt_id)
            if command.attempt_ordinal == job.attempt_count and job.current_attempt_id is not None:
                _require(job.current_attempt_id == command.attempt_id, "CURRENT_ATTEMPT_MISMATCH")
            if job.current_attempt_id == command.attempt_id:
                _require(job.attempt_count == command.attempt_ordinal, "ATTEMPT_ORDINAL_MISMATCH")
    requeued_jobs = set()
    for requeue in observation.requeues:
        _text(requeue.job_id)
        _text(requeue.previous_attempt_id)
        _integer(requeue.previous_attempt_ordinal, 1)
        _integer(requeue.event_id, 1)
        _integer(requeue.latest_job_event_id, 1)
        _text(requeue.evidence_digest, digest=True)
        job = jobs.get(requeue.job_id)
        prior = next((item for item in commands.values()
                      if item.attempt_id == requeue.previous_attempt_id), None)
        _require(job is not None and job.job_id not in requeued_jobs
                 and job.status == "QUEUED" and job.current_attempt_id is None
                 and job.attempt_count == requeue.previous_attempt_ordinal
                 and requeue.event_id == requeue.latest_job_event_id
                 and prior is not None and prior.job_id == job.job_id
                 and prior.attempt_ordinal == requeue.previous_attempt_ordinal
                 and prior.attempt_status in _TERMINAL and not prior.effect_unknown,
                 "REQUEUE_EVIDENCE_INVALID")
        requeued_jobs.add(job.job_id)
    results = {}
    for result in observation.results:
        for value in (result.job_id, result.attempt_id, result.plan_attempt_id, result.plan_step_id):
            _text(value)
        _text(result.plan_digest, digest=True)
        _integer(result.repair_round, 0, policy.max_repair_rounds)
        _integer(result.fence_generation, 1)
        _parse({"action": "selected_child_status", "command": result.command})
        _require(result.job_id in jobs and result.command in commands,
                 "RESULT_OWNER_REFERENCE_ABSENT")
        job, command = jobs[result.job_id], commands[result.command]
        _require(_lineage(job) == (result.plan_attempt_id, result.plan_digest,
                                  result.plan_step_id, result.repair_round)
                 and command.job_id == result.job_id and command.attempt_id == result.attempt_id
                 and command.attempt_status == "COMPLETED"
                 and command.fence_generation == result.fence_generation, "RESULT_LINEAGE_MISMATCH")
        _text(result.result_envelope_digest, digest=True)
        _text(result.terminal_evidence_digest, digest=True)
        _require(type(result.outcome) is str and result.outcome in {"ACCEPTED", "PARTIAL", "REJECTED"}
                 and result.attempt_id not in results, "RESULT_IDENTITY_INVALID")
        if result.review_attempt_id is None:
            _require(result.review_acceptance_digest is None and result.reviewed_result_digest is None,
                     "REVIEW_EVIDENCE_INCOMPLETE")
        else:
            _text(result.review_attempt_id)
            _text(result.review_acceptance_digest, digest=True)
            _text(result.reviewed_result_digest, digest=True)
            review = next((item for item in observation.commands
                           if item.attempt_id == result.review_attempt_id), None)
            reviewer = jobs[review.job_id] if review is not None else None
            _require(review is not None and review.attempt_status == "COMPLETED"
                     and not review.effect_unknown and reviewer.orchestration_role == "review"
                     and reviewer.status == "COMPLETED" and reviewer.current_attempt_id == result.review_attempt_id
                     and review.attempt_ordinal <= policy.review_job_attempt_limit
                     and reviewer.reviews_job_id == job.job_id
                     and reviewer.parent_job_id == job.parent_job_id
                     and _lineage(reviewer) == _lineage(job)
                     and result.reviewed_result_digest == result.result_envelope_digest,
                     "REVIEW_BINDING_MISMATCH")
        results[result.attempt_id] = result
    return jobs, tree, plans, commands, results


def _checked(observation: OwnerObservation, policy: CooCyclePolicy):
    try:
        return _validate(observation, policy)
    except (HierarchyError, CooCyclePolicyError) as exc:
        raise DelegationContractError("HIERARCHY_OR_RESERVATION_INVALID") from exc
    except (TypeError, KeyError, AttributeError) as exc:
        raise DelegationContractError("OBSERVATION_SHAPE_INVALID") from exc


def validate_observation(observation: OwnerObservation, *, policy: CooCyclePolicy) -> TreeProjection:
    jobs, _, plans, _, _ = _checked(observation, policy)
    return TreeProjection(observation.authority.root_job_id, len(jobs) - 1,
                          max(job.depth for job in jobs.values()),
                          tuple(sorted((key, plan.reserved_children_total) for key, plan in plans.items())))


def _authorized(observation: OwnerObservation, binding: AuthorityBinding) -> None:
    _binding(binding)
    _require(observation.may_read and observation.authority == binding,
             "CURRENT_AUTHORITY_MISMATCH")


def _accepted(job: JobFact, step: StepFact, facts) -> bool:
    _, _, _, commands, results = facts
    result = results.get(job.current_attempt_id)
    return (job.status == "COMPLETED" and result is not None
            and result.outcome == "ACCEPTED" and not commands[result.command].effect_unknown
            and (not step.review_required or result.review_acceptance_digest is not None))


def _aggregate(coordinator_id: str, facts) -> tuple[set[str], set[tuple[str, str]], set[str], set[str]]:
    jobs, tree, plans, commands, results = facts
    descendants = descendant_ids(tree, coordinator_id)
    pending = {key for key in descendants if jobs[key].status not in _TERMINAL}
    unresolved = {item.command for item in commands.values()
                  if item.job_id in descendants and item.effect_unknown}
    accepted = set()
    pending_steps = set()
    plan = plans.get(coordinator_id)
    if plan is None:
        pending.add(coordinator_id)
    else:
        for step in plan.steps:
            if step.current_job_id is None:
                pending_steps.add((coordinator_id, step.step_id))
                continue
            job = jobs[step.current_job_id]
            if _accepted(job, step, facts):
                accepted.add(results[job.current_attempt_id].result_envelope_digest)
            else:
                pending.add(job.job_id)
            if job.orchestration_role == "aggregation":
                nested_pending, nested_steps, nested_unresolved, nested_accepted = _aggregate(job.job_id, facts)
                pending.update(nested_pending)
                pending_steps.update(nested_steps)
                unresolved.update(nested_unresolved)
                accepted.update(nested_accepted)
    return pending, pending_steps, unresolved, accepted


def project_aggregate(observation: OwnerObservation, binding: AuthorityBinding, *,
                      policy: CooCyclePolicy) -> AggregateProjection:
    facts = _checked(observation, policy)
    _authorized(observation, binding)
    pending, pending_steps, unresolved, accepted = _aggregate(binding.coordinator_job_id, facts)
    # Cancellation is an owner settlement path, never successful aggregation.
    for row in ancestors(facts[1], binding.coordinator_job_id):
        if row["cancel_requested_at_ms"] is not None or row["status"] in {"CANCELLED", "CANCEL_REQUESTED"}:
            pending.add(row["job_id"])
    return AggregateProjection(binding.coordinator_job_id, observation.snapshot_digest,
                               not pending and not pending_steps and not unresolved, tuple(sorted(pending)),
                               tuple(sorted(pending_steps)),
                               tuple(sorted(unresolved)), tuple(sorted(accepted)))


def project_request(request: Mapping[str, Any], selected: FrozenChild,
                    observation: OwnerObservation, *, policy: CooCyclePolicy) -> OwnerRequest:
    """Project one frozen command; replay/status never becomes a fresh claim.

    The public request supplies no root, grant, ordinal, generation or Attempt.
    Reconciliation is evaluated BEFORE fresh-admission/cancellation checks.
    """
    parsed = _parse(request)
    _require(type(selected) is FrozenChild, "SELECTION_SHAPE_INVALID")
    facts = _checked(observation, policy)
    jobs, tree, plans, commands, results = facts
    _authorized(observation, selected.authority)
    for value in (selected.parent_job_id, selected.job_id, selected.plan_attempt_id,
                  selected.plan_step_id):
        _text(value)
    for value in (selected.plan_digest, selected.reservation_digest):
        _text(value, digest=True)
    if selected.placement_union_digest is not None:
        _text(selected.placement_union_digest, digest=True)
    for value in (selected.expected_current_attempt_id, selected.original_attempt_id):
        if value is not None:
            _text(value)
    _integer(selected.repair_round, 0, policy.max_repair_rounds)
    _require(selected.job_id in jobs and selected.parent_job_id == selected.authority.coordinator_job_id
             and parsed["command"] == selected.command, "FROZEN_SELECTION_MISMATCH")
    job = jobs[selected.job_id]
    _require(job.parent_job_id == selected.parent_job_id
             and job.root_job_id == selected.authority.root_job_id
             and job.orchestration_role in {"work", "repair", "aggregation"}
             and _lineage(job) == (selected.plan_attempt_id, selected.plan_digest,
                                   selected.plan_step_id, selected.repair_round),
             "FROZEN_LINEAGE_MISMATCH")
    _command_matches(selected.command, job, selected.attempt_ordinal)
    plan = plans.get(selected.parent_job_id)
    _require(plan is not None and plan.plan_attempt_id == selected.plan_attempt_id
             and plan.plan_digest == selected.plan_digest
             and plan.reservation_digest == selected.reservation_digest, "FROZEN_PLAN_MISMATCH")
    original = commands.get(selected.command)
    if original is not None:
        _require(selected.original_attempt_id is None or selected.original_attempt_id == original.attempt_id,
                 "ORIGINAL_ATTEMPT_CHANGED")
        result = results.get(original.attempt_id)
        return OwnerRequest("selected_child_status", selected.command, "RECONCILE_ORIGINAL",
                            selected, observation.snapshot_digest, original.attempt_id,
                            original.fence_generation, original.attempt_status,
                            result.result_envelope_digest if result else None,
                            result.terminal_evidence_digest if result else None)
    _require(selected.original_attempt_id is None, "ORIGINAL_ATTEMPT_MISSING")
    _require(selected.attempt_ordinal > job.attempt_count, "ORIGINAL_COMMAND_OBSERVATION_MISSING")
    # A different unresolved ordinal cannot be converted into a no-claim result.
    _require(not any(item.job_id == job.job_id and item.effect_unknown for item in commands.values()),
             "ORIGINAL_EFFECT_UNRESOLVED")
    if parsed["action"] == "selected_child_status":
        return OwnerRequest("selected_child_status", selected.command, "OBSERVE_UNCLAIMED",
                            selected, observation.snapshot_digest, None, None, None)
    _require(observation.may_submit, "FRESH_AUTHORITY_CLOSED")
    requeue = None
    if job.attempt_count:
        requeue = next((item for item in observation.requeues if item.job_id == job.job_id), None)
        _require(requeue is not None,
                 "PRIOR_ATTEMPT_NOT_SETTLED")
    else:
        _require(job.current_attempt_id is None, "PRIOR_ATTEMPT_NOT_SETTLED")
    try:
        assert_admission_open(tree, selected.parent_job_id)
    except HierarchyError as exc:
        raise DelegationContractError("ANCESTOR_ADMISSION_CLOSED") from exc
    _require(job.status == "QUEUED" and job.cancel_requested_at_ms is None
             and job.current_attempt_id == selected.expected_current_attempt_id
             and selected.attempt_ordinal == job.attempt_count + 1
             and selected.attempt_ordinal <= policy.max_attempts_per_orchestration_job,
             "FRESH_ATTEMPT_MISMATCH")
    current = next((step for step in plan.steps if step.step_id == selected.plan_step_id), None)
    _require(current is not None and current.current_job_id == job.job_id
             and current.current_repair_round == selected.repair_round, "STEP_SUPERSEDED")
    for row in ancestors(tree, selected.parent_job_id):
        node = jobs[row["job_id"]]
        _require(node.placement_union_digest is not None, "PLACEMENT_UNION_ABSENT")
        if node.parent_job_id is not None:
            _require(node.placement_union_digest == jobs[node.parent_job_id].placement_union_digest,
                     "INHERITED_PLACEMENT_UNION_CHANGED")
    _require(selected.placement_union_digest == jobs[selected.parent_job_id].placement_union_digest,
             "FROZEN_PLACEMENT_UNION_CHANGED")
    if job.orchestration_role == "aggregation":
        _require(job.placement_union_digest == selected.placement_union_digest,
                 "INHERITED_PLACEMENT_UNION_CHANGED")
        pending, pending_steps, unresolved, _ = _aggregate(job.job_id, facts)
        _require(not pending and not pending_steps and not unresolved, "AGGREGATE_DEPENDENCIES_PENDING")
    for dependency in plan.steps:
        if dependency.step_id in current.prerequisite_step_ids:
            _require(dependency.current_job_id is not None, "DEPENDENCY_NOT_ACCEPTED")
            prerequisite = jobs[dependency.current_job_id]
            _require(_accepted(prerequisite, dependency, facts), "DEPENDENCY_NOT_ACCEPTED")
            if prerequisite.orchestration_role == "aggregation":
                pending, pending_steps, unresolved, _ = _aggregate(prerequisite.job_id, facts)
                _require(not pending and not pending_steps and not unresolved, "DEPENDENCY_NOT_ACCEPTED")
    return OwnerRequest("selected_child_submit", selected.command, "FRESH_REQUEST",
                        selected, observation.snapshot_digest, None, None, None,
                        requeue_evidence_digest=requeue.evidence_digest if requeue else None)
