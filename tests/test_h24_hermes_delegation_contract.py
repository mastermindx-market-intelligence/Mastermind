"""Hermetic H24-07 fixture and owner transaction-sequence specimen.

The specimen below MODELS the existing owner's recheck boundary. It does not
instantiate Runtime, create real Jobs/Attempts, acquire leases or call Hermes.
The test suite is also runnable with stdlib unittest; no installation is needed.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, replace
import hashlib
import unittest

from control_plane.executive_coo_policy import CooCyclePolicy
from control_plane.executive_orchestration_principal import digest as orchestration_digest
from control_plane.executive_orchestration_result import canonical_digest
from control_plane.hermes_delegation_contract import (
    AcceptedRevisionFact, AggregateProjection, AggregationFact, AuthorityBinding, CommandFact, DelegationContractError,
    FrozenChild, Grant, JobFact, OwnerObservation, PlanFact, RequeueFact, ResultFact, StepFact,
    project_accepted_revision, project_admitted_plan, project_aggregation_handoff,
    project_child_result, project_dependency_manifest,
    project_aggregate, project_request, validate_observation,
)


def digest(label):
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


POLICY = CooCyclePolicy.load(version=2)
UNION = digest("owner-qualified exact work-placement union")


def command_for(job, ordinal=1):
    scope = job.job_id if job.orchestration_role == "aggregation" else job.parent_job_id
    return f"coo-cycle:{scope}:dispatch:{job.job_id}:attempt:{ordinal}"


def fixture(*, depth=1, leaves=1, reviewed=False):
    """An admitted complete bounded tree, including every planner slot."""
    root_id = "JOB-ROOT"
    jobs = [JobFact(root_id, None, root_id, 0, "aggregation", grant=Grant(16, 3),
                    placement_union_digest=UNION)]
    plans = []
    coordinator_id = root_id
    for level in range(depth):
        planner_id = f"JOB-PLAN-{level}"
        attempt_id = f"ATT-PLAN-{level}"
        plan_digest = digest(f"plan-{level}")
        reservation_digest = digest(f"owner-admission-{level}")
        jobs.append(JobFact(planner_id, coordinator_id, root_id, level + 1, "plan",
                            status="COMPLETED", current_attempt_id=attempt_id, attempt_count=1))
        if level + 1 < depth:
            child_id = f"JOB-C{level + 1}"
            grant = Grant(16 - 2 * (level + 1), 3)
            step = StepFact(f"STEP-C{level + 1}", child_id, 0, False,
                            1 + grant.descendant_limit, child_id,
                            f"coo-cycle:{coordinator_id}:admit-plan:{attempt_id}:member:0", grant)
            jobs.append(JobFact(child_id, coordinator_id, root_id, level + 1, "aggregation",
                                grant=grant, placement_union_digest=UNION,
                                plan_attempt_id=attempt_id, plan_digest=plan_digest,
                                plan_step_id=step.step_id))
            steps = (step,)
        else:
            steps = tuple(StepFact(f"STEP-{index}", f"JOB-W{index}", 0, reviewed,
                                   POLICY.reserved_step_slots(review_required=reviewed), f"JOB-W{index}",
                                   f"coo-cycle:{coordinator_id}:admit-plan:{attempt_id}:member:{index}")
                          for index in range(leaves))
            for step in steps:
                jobs.append(JobFact(step.current_job_id, coordinator_id, root_id, level + 1,
                                    "work", plan_attempt_id=attempt_id, plan_digest=plan_digest,
                                    plan_step_id=step.step_id))
        total = 1 + sum(step.reserved_slots for step in steps)
        plans.append(PlanFact(root_id, coordinator_id, planner_id, attempt_id, plan_digest,
                              reservation_digest, total, steps))
        if level + 1 < depth:
            coordinator_id = child_id
    authority = AuthorityBinding(root_id, coordinator_id, digest("permission"), digest("generation"))
    observation = OwnerObservation(authority, digest("snapshot-0"), True, True, True,
                                   tuple(jobs), tuple(plans))
    observation = replace(observation, dependencies=tuple(dependency_for(job) for job in jobs
                          if job.parent_job_id and job.orchestration_role in {"work", "aggregation"}))
    return observation, selection_for(observation, "JOB-W0")


def dependency_for(job, prerequisites=(), revisions=()):
    wire = {"schema_version": "mastermind.work_dependency_manifest/v2",
            "root_job_id": job.root_job_id, "coordinator_job_id": job.parent_job_id,
            "plan_attempt_id": job.plan_attempt_id, "plan_digest": job.plan_digest,
            "plan_step_id": job.plan_step_id, "prerequisite_step_ids": list(prerequisites),
            "revisions": [asdict(item) for item in revisions]}
    wire["dependency_manifest_digest"] = orchestration_digest(wire)
    return project_dependency_manifest(wire, job=job)


def bind_dependency(observation, job_id):
    job = next(item for item in observation.jobs if item.job_id == job_id)
    plan = next(item for item in observation.plans if item.coordinator_job_id == job.parent_job_id)
    step = next(item for item in plan.steps if item.step_id == job.plan_step_id)
    revisions = tuple(next(result.accepted_revision for result in observation.results
                           if result.job_id == next(item.current_job_id for item in plan.steps
                                                    if item.step_id == prerequisite))
                      for prerequisite in step.prerequisite_step_ids)
    fact = dependency_for(job, step.prerequisite_step_ids, revisions)
    return replace(observation, dependencies=tuple(item for item in observation.dependencies
                                                   if item.job_id != job_id) + (fact,))


def accepted_wire(job, attempt_id, role_digest, ordinal, *, reviewed=False):
    return dict(ordinal=ordinal, plan_step_id=job.plan_step_id, current_job_id=job.job_id,
                current_attempt_id=attempt_id, current_result_digest=role_digest,
                current_raw_result_digest=digest("raw"), effective_grant_digest=digest("grant"),
                artifact_receipt_digest=digest("artifact"), validation_receipt_digest=digest("validation"),
                placement_snapshot_digest=digest("placement"), execution_principal_snapshot_digest=digest("principal"),
                repair_round=job.repair_round, review_required=reviewed,
                qualifying_review_job_id=f"REV-{job.job_id}" if reviewed else None,
                qualifying_review_attempt_id=f"ATT-REV-{job.job_id}" if reviewed else None,
                qualifying_review_result_digest=digest(f"review-{job.job_id}") if reviewed else None,
                qualifying_review_effective_grant_digest=digest("review-grant") if reviewed else None,
                qualifying_review_principal_snapshot_digest=digest("review-principal") if reviewed else None)


def selection_for(observation, job_id):
    job = next(job for job in observation.jobs if job.job_id == job_id)
    plan = next(plan for plan in observation.plans if plan.coordinator_job_id == job.parent_job_id)
    parent = next(parent for parent in observation.jobs if parent.job_id == job.parent_job_id)
    binding = replace(observation.authority, coordinator_job_id=job.parent_job_id)
    return FrozenChild(binding, job.parent_job_id, job.job_id, job.plan_attempt_id,
                       job.plan_digest, job.plan_step_id, job.repair_round,
                       plan.reservation_digest, parent.placement_union_digest,
                       command_for(job), 1)


def change_job(observation, selected_job_id, **changes):
    return replace(observation, jobs=tuple(replace(job, **changes) if job.job_id == selected_job_id else job
                                           for job in observation.jobs))


def settle(observation, job_id, *, outcome="ACCEPTED", reviewed=False):
    """Owner-observed terminal references; every result joins its real fixture Attempt."""
    original = next(job for job in observation.jobs if job.job_id == job_id)
    attempt_id = f"ATT-{job_id}"
    observation = change_job(observation, job_id, status="COMPLETED",
                              current_attempt_id=attempt_id, attempt_count=1)
    command = CommandFact(command_for(original), job_id, 1, attempt_id, "COMPLETED", 7)
    result = ResultFact(job_id, attempt_id, command.command, original.plan_attempt_id,
                        original.plan_digest, original.plan_step_id, original.repair_round,
                        7, digest(f"envelope-{job_id}"), digest(f"role-{job_id}"),
                        digest(f"terminal-{job_id}"), outcome)
    jobs, commands = observation.jobs, observation.commands + (command,)
    if reviewed:
        review_id, review_attempt = f"REV-{job_id}", f"ATT-REV-{job_id}"
        review_job = replace(original, job_id=review_id, orchestration_role="review",
                              status="COMPLETED", current_attempt_id=review_attempt,
                              attempt_count=1, reviews_job_id=job_id, supersedes_job_id=None)
        jobs += (review_job,)
        commands += (CommandFact(command_for(review_job), review_id, 1, review_attempt,
                                  "COMPLETED", 8),)
        result = replace(result, review_attempt_id=review_attempt,
                          review_acceptance_digest=digest(f"review-{job_id}"),
                          reviewed_result_digest=result.role_result_digest)
    plan = next(item for item in observation.plans if item.coordinator_job_id == original.parent_job_id)
    ordinal, step = next((i, item) for i, item in enumerate(plan.steps) if item.step_id == original.plan_step_id)
    if outcome == "ACCEPTED" and (not step.review_required or reviewed):
        result = replace(result, accepted_revision=project_accepted_revision(
            accepted_wire(original, attempt_id, result.role_result_digest, ordinal, reviewed=reviewed)))
    if original.orchestration_role == "aggregation":
        local = next(item for item in observation.plans if item.coordinator_job_id == job_id)
        revisions = tuple(next((item.accepted_revision for item in observation.results
                                if item.job_id == step.current_job_id), None) for step in local.steps)
        if all(item is not None for item in revisions):
            result = replace(result, aggregation=AggregationFact(original.root_job_id, job_id,
                local.plan_attempt_id, local.plan_digest, local.reservation_digest,
                digest(f"handoff-{job_id}"), revisions, orchestration_digest([])))
    return replace(observation, jobs=jobs, commands=commands,
                    results=observation.results + (result,),
                    snapshot_digest=digest(observation.snapshot_digest + job_id))


def submit(selected, observation):
    return project_request({"action": "selected_child_submit", "command": selected.command},
                            selected, observation, policy=POLICY)


def status(selected, observation):
    return project_request({"action": "selected_child_status", "command": selected.command},
                            selected, observation, policy=POLICY)


def aggregate(observation, coordinator_id=None):
    binding = replace(observation.authority, coordinator_job_id=coordinator_id or "JOB-ROOT")
    observation = replace(observation, authority=binding)
    return project_aggregate(observation, binding, policy=POLICY)


def plan_wires(plan):
    body = {"schema_version": "mastermind.execution_plan/v5", "root_job_id": plan.root_job_id,
            "coordinator_job_id": plan.coordinator_job_id, "plan_attempt_id": plan.plan_attempt_id,
            "steps": [{"ordinal": ordinal, "step_id": step.step_id, "objective": "Bounded source work",
                       "business_impact": "routine", "review_required": step.review_required,
                       "requested_authorities": ["READ"], "allowed_write_paths": [], "validation_ids": [],
                       "attempt_limit": 1, "cost_class": "small",
                       "prerequisite_step_ids": list(step.prerequisite_step_ids),
                       "delegation": {"descendant_limit": step.delegation.descendant_limit,
                                      "max_depth": step.delegation.max_depth} if step.delegation else None}
                      for ordinal, step in enumerate(plan.steps)]}
    admission = {"schema_version": "mastermind.coo_plan_admission/v3", "root_job_id": plan.root_job_id,
                 "coordinator_job_id": plan.coordinator_job_id, "policy_sha": POLICY.policy_sha256,
                 "plan_attempt_id": plan.plan_attempt_id, "plan_digest": canonical_digest(body),
                 "reserved_children_total": plan.reserved_children_total,
                 "command_id": f"coo-cycle:{plan.coordinator_job_id}:admit-plan:{plan.plan_attempt_id}",
                 "steps": [{"ordinal": ordinal, "plan_step_id": step.step_id,
                            "step_slots": step.reserved_slots, "review_required": step.review_required,
                            "prerequisite_step_ids": list(step.prerequisite_step_ids),
                            "initial_work_job_id": step.initial_work_job_id,
                            "initial_work_command_id": step.initial_work_command_id}
                           for ordinal, step in enumerate(plan.steps)]}
    admission["reservation_digest"] = orchestration_digest(admission)
    return body, admission


def canonical_plan_fixture(observation):
    wires = {plan.coordinator_job_id: plan_wires(plan) for plan in observation.plans}
    jobs = tuple(replace(job, plan_digest=wires[job.parent_job_id][1]["plan_digest"])
                 if job.plan_digest is not None else job for job in observation.jobs)
    plans = tuple(project_admitted_plan(plan=wires[plan.coordinator_job_id][0],
                    admission=wires[plan.coordinator_job_id][1],
                    planner=next(job for job in jobs if job.job_id == plan.planner_job_id),
                    jobs=jobs, policy=POLICY) for plan in observation.plans)
    return replace(observation, jobs=jobs, plans=plans, dependencies=tuple(dependency_for(job) for job in jobs
                   if job.parent_job_id and job.orchestration_role in {"work", "aggregation"})), wires


def completion_wires(observation, job_id, *, body=None):
    job = next(item for item in observation.jobs if item.job_id == job_id)
    command = next(item for item in observation.commands if item.attempt_id == job.current_attempt_id)
    if body is None:
        body = {"schema_version": "mastermind.work_result/v1", "root_job_id": job.root_job_id,
                "plan_attempt_id": job.plan_attempt_id, "plan_digest": job.plan_digest,
                "plan_step_id": job.plan_step_id, "repair_round": job.repair_round,
                "artifacts": [], "evidence_digests": []}
    envelope = {"schema_version": "mastermind.executive_orchestration_result/v1", "job_id": job_id,
                "run_id": command.attempt_id, "worker_id": "WORKER-1", "role": job.orchestration_role,
                "status": "COMPLETED", "role_result": body, "summary": "Scoped source result",
                "current_state": "Completed", "next_actions": [], "errors": [], "validations": []}
    terminal = {"schema_version": "mastermind.orchestration_terminal_receipt/v1", "status": "COMPLETED",
                "job_id": job_id, "attempt_id": command.attempt_id, "orchestration_role": job.orchestration_role,
                "execution_mode": "OPERATOR_HARNESS", "result_seal_command_id": f"orchestration-result-seal:{command.attempt_id}",
                "result_evidence": None, "result_envelope": envelope, "result_envelope_digest": canonical_digest(envelope),
                "artifact_receipt_digest": digest("artifact"), "validation_receipt_digest": digest("validation"),
                "effective_grant_digest": digest("grant")}
    terminal["terminal_evidence_digest"] = orchestration_digest(terminal)
    return dict(job=job, command=command, worker_id="WORKER-1", envelope=envelope, terminal=terminal)


def handoff_wire(observation, coordinator_id):
    plan = next(item for item in observation.plans if item.coordinator_job_id == coordinator_id)
    revisions = [asdict(next(result.accepted_revision for result in observation.results
                            if result.job_id == step.current_job_id)) for step in plan.steps]
    wire = {"schema_version": "mastermind.aggregation_handoff/v2", "root_job_id": plan.root_job_id,
            "coordinator_job_id": coordinator_id, "policy_sha": POLICY.policy_sha256,
            "plan_attempt_id": plan.plan_attempt_id, "plan_digest": plan.plan_digest,
            "reservation_digest": plan.reservation_digest, "revisions": revisions, "rejected_history": [],
            "aggregate_result_schema": "mastermind.aggregation_result/v2",
            "allowed_evidence_reads": ["attempts", "events", "jobs"],
            "command_id": f"coo-cycle:{coordinator_id}:aggregation-handoff:1"}
    wire["handoff_digest"] = orchestration_digest(wire)
    return wire, plan


class OwnerTransactionSpecimen:
    """Deterministic interleaving model, NOT a Runtime implementation or race proof.

    A production join uses the incumbent transaction/claim/lease implementation.
    The second stale request is rejected, then freshly projected. No contract
    projection allocates a slot, chooses a worker or advances an Attempt itself.
    """

    def __init__(self, observation):
        self.observation = observation
        self.claim_count = 0

    def consume(self, projection):
        if projection.expected_snapshot_digest != self.observation.snapshot_digest:
            raise DelegationContractError("OWNER_SNAPSHOT_CHANGED")
        checked = project_request(projection.public_request(), projection.selection,
                                   self.observation, policy=POLICY)
        if checked.disposition != "FRESH_REQUEST":
            return checked
        self.claim_count += 1
        selected = checked.selection
        attempt_id = f"ATT-CLAIM-{self.claim_count}"
        observed = change_job(self.observation, selected.job_id, status="RUNNING",
                               current_attempt_id=attempt_id, attempt_count=selected.attempt_ordinal)
        claim = CommandFact(selected.command, selected.job_id, selected.attempt_ordinal,
                             attempt_id, "RUNNING", self.claim_count)
        self.observation = replace(observed, commands=observed.commands + (claim,),
                                    snapshot_digest=digest(f"owner-claim-{self.claim_count}"))
        return claim


class HierarchyTests(unittest.TestCase):
    def test_depth_zero_and_one_two_three_allowed(self):
        observation, _ = fixture()
        root_only = replace(observation, jobs=observation.jobs[:1], plans=(), dependencies=())
        self.assertEqual(validate_observation(root_only, policy=POLICY).maximum_observed_depth, 0)
        for depth in (1, 2, 3):
            with self.subTest(depth=depth):
                observation, selected = fixture(depth=depth)
                self.assertEqual(validate_observation(observation, policy=POLICY).maximum_observed_depth, depth)
                self.assertEqual(submit(selected, observation).disposition, "FRESH_REQUEST")

    def test_depth_four_denied(self):
        observation, selected = fixture(depth=3)
        observation = change_job(observation, selected.job_id, depth=4)
        with self.assertRaises(DelegationContractError):
            submit(selected, observation)

    def test_depth_three_cannot_become_coordinator(self):
        observation, selected = fixture(depth=3)
        observation = change_job(observation, selected.job_id, orchestration_role="aggregation",
                                  grant=Grant(2, 3))
        with self.assertRaises(DelegationContractError):
            validate_observation(observation, policy=POLICY)

    def test_full_four_level_tree_has_only_sixteen_descendants(self):
        observation, _ = fixture(depth=3, leaves=11)
        tree = validate_observation(observation, policy=POLICY)
        self.assertEqual(tree.total_descendants, 16)
        self.assertEqual(dict(tree.reservations), {"JOB-ROOT": 16, "JOB-C1": 14, "JOB-C2": 12})

    def test_terminal_slot_still_counted_and_seventeenth_denied(self):
        observation, _ = fixture(depth=3, leaves=11)
        observation = settle(observation, "JOB-W0")
        self.assertEqual(validate_observation(observation, policy=POLICY).total_descendants, 16)
        extra = replace(observation.jobs[-1], job_id="JOB-EXTRA")
        with self.assertRaises(DelegationContractError):
            validate_observation(replace(observation, jobs=observation.jobs + (extra,)), policy=POLICY)

    def test_terminal_history_cannot_spend_another_steps_reserve(self):
        observation, _ = fixture(leaves=2)
        old = replace(observation.jobs[-1], job_id="JOB-OLD", plan_step_id="STEP-0", status="FAILED")
        with self.assertRaises(DelegationContractError):
            validate_observation(replace(observation, jobs=observation.jobs + (old,)), policy=POLICY)

    def test_sibling_subtrees_cannot_each_take_root_allowance(self):
        observation, _ = fixture(depth=2)
        root_plan = observation.plans[0]
        first = root_plan.steps[0]
        sibling = replace(observation.jobs[2], job_id="JOB-SIBLING", plan_step_id="STEP-SIBLING")
        second = replace(first, step_id="STEP-SIBLING", current_job_id=sibling.job_id,
                          initial_work_job_id=sibling.job_id,
                          initial_work_command_id=first.initial_work_command_id[:-1] + "1")
        root_plan = replace(root_plan, steps=(first, second), reserved_children_total=16)
        observation = replace(observation, jobs=observation.jobs + (sibling,),
                                plans=(root_plan,) + observation.plans[1:])
        with self.assertRaisesRegex(DelegationContractError, "HIERARCHY_OR_RESERVATION"):
            validate_observation(observation, policy=POLICY)

    def test_reviewed_leaf_reserves_nine_plus_planner(self):
        observation, selected = fixture(reviewed=True)
        self.assertEqual(dict(validate_observation(observation, policy=POLICY).reservations)["JOB-ROOT"], 10)
        self.assertEqual(submit(selected, observation).disposition, "FRESH_REQUEST")
        observation, _ = fixture(reviewed=True, leaves=2)
        with self.assertRaises(DelegationContractError):
            validate_observation(observation, policy=POLICY)

    def test_missing_or_changed_reservation_refused(self):
        observation, selected = fixture()
        for change in (replace(observation, plans=()),
                       replace(observation, plans=(replace(observation.plans[0], reserved_children_total=1),))):
            with self.subTest(change=change.plans):
                with self.assertRaises(DelegationContractError):
                    submit(selected, change)
        with self.assertRaisesRegex(DelegationContractError, "FROZEN_PLAN"):
            submit(replace(selected, reservation_digest=digest("different")), observation)

    def test_duplicate_plan_slot_refused(self):
        observation, _ = fixture(leaves=2)
        plan = observation.plans[0]
        duplicate = replace(plan.steps[1], current_job_id=plan.steps[0].current_job_id)
        observation = replace(observation, plans=(replace(plan, steps=(plan.steps[0], duplicate)),))
        with self.assertRaisesRegex(DelegationContractError, "STEP_IDENTITY"):
            validate_observation(observation, policy=POLICY)

    def test_canonical_colon_step_identity_and_prerequisite_are_preserved(self):
        observation, _ = fixture(leaves=2)
        plan = observation.plans[0]
        first = replace(plan.steps[0], step_id="phase:research")
        second = replace(plan.steps[1], prerequisite_step_ids=(first.step_id,),
                           initial_work_job_id=None, initial_work_command_id=None)
        observation = change_job(observation, "JOB-W0", plan_step_id=first.step_id)
        observation = replace(observation, plans=(replace(plan, steps=(first, second)),))
        observation = bind_dependency(observation, "JOB-W0")
        validate_observation(observation, policy=POLICY)
        self.assertEqual(submit(selection_for(observation, "JOB-W0"), observation).selection.plan_step_id,
                          "phase:research")
        observation = settle(observation, "JOB-W0")
        observation = bind_dependency(observation, "JOB-W1")
        self.assertEqual(submit(selection_for(observation, "JOB-W1"), observation).disposition, "FRESH_REQUEST")

    def test_rollback_fork_or_skipped_repair_revision_refused(self):
        observation, _ = fixture(reviewed=True)
        old = next(job for job in observation.jobs if job.job_id == "JOB-W0")
        repaired = replace(old, job_id="JOB-R1", orchestration_role="repair", repair_round=1,
                            supersedes_job_id=old.job_id, status="FAILED")
        plan = observation.plans[0]
        step = replace(plan.steps[0], current_job_id=repaired.job_id, current_repair_round=1)
        valid = replace(observation, jobs=observation.jobs + (repaired,),
                         plans=(replace(plan, steps=(step,)),))
        validate_observation(valid, policy=POLICY)
        for malformed in (replace(valid, plans=observation.plans),
                          change_job(valid, repaired.job_id, repair_round=2),
                          change_job(valid, repaired.job_id, supersedes_job_id="FOREIGN"),
                          replace(valid, jobs=valid.jobs + (replace(repaired, job_id="JOB-FORK"),))):
            with self.assertRaises(DelegationContractError):
                validate_observation(malformed, policy=POLICY)

    def test_three_reviews_cannot_share_one_revisions_reserve(self):
        observation, _ = fixture(reviewed=True)
        observation = settle(observation, "JOB-W0", reviewed=True)
        review = observation.jobs[-1]
        extras = tuple(replace(review, job_id=f"JOB-REVIEW-{i}", current_attempt_id=None,
                                attempt_count=0, status="QUEUED") for i in range(2))
        with self.assertRaisesRegex(DelegationContractError, "REVIEW_RESERVATION_EXCEEDED"):
            validate_observation(replace(observation, jobs=observation.jobs + extras), policy=POLICY)

    def test_cycle_foreign_root_missing_parent_and_replacement_parent(self):
        observation, selected = fixture(depth=3)
        changes = [("JOB-C1", {"parent_job_id": "JOB-C2"}),
                   ("JOB-W0", {"root_job_id": "FOREIGN"}),
                   ("JOB-W0", {"parent_job_id": "MISSING"}),
                   ("JOB-W0", {"parent_job_id": "JOB-C1"})]
        for job_id, change in changes:
            with self.subTest(change=change):
                with self.assertRaises(DelegationContractError):
                    submit(selected, change_job(observation, job_id, **change))

    def test_child_cannot_widen_grant(self):
        observation, _ = fixture(depth=3)
        for grant in (Grant(16, 3), Grant(12, 4), Grant(True, 3), Grant(12, 3, digest("foreign-policy"))):
            with self.subTest(grant=grant):
                with self.assertRaises(DelegationContractError):
                    validate_observation(change_job(observation, "JOB-C1", grant=grant), policy=POLICY)

    def test_boolean_depth_numeric_identity_and_mutable_collections_refused(self):
        observation, _ = fixture()
        malformed = [change_job(observation, "JOB-ROOT", depth=False),
                     change_job(observation, "JOB-W0", job_id=123),
                     replace(observation, jobs=list(observation.jobs)),
                     replace(observation, plans=list(observation.plans))]
        for changed in malformed:
            with self.subTest(changed=type(changed.jobs)):
                with self.assertRaises(DelegationContractError):
                    validate_observation(changed, policy=POLICY)

    def test_incomplete_snapshot_cannot_prove_absence(self):
        observation, selected = fixture()
        with self.assertRaisesRegex(DelegationContractError, "OBSERVATION_INCOMPLETE"):
            status(selected, replace(observation, complete=False))

    def test_malformed_owner_fields_refuse_without_type_errors(self):
        observation, _ = fixture()
        for changed in (replace(observation, plans=(replace(observation.plans[0], coordinator_job_id=[]),)),
                        change_job(observation, "JOB-ROOT", plan_attempt_id={}),
                        replace(observation, commands=(CommandFact("bad", [], 1, None, None, None, True),))):
            with self.assertRaises(DelegationContractError):
                validate_observation(changed, policy=POLICY)

    def test_legacy_or_tampered_policy_cannot_expand_limits(self):
        observation, _ = fixture()
        for policy in (CooCyclePolicy.load(), replace(POLICY, max_children_total=160)):
            with self.assertRaisesRegex(DelegationContractError, "POLICY_NOT_V5"):
                validate_observation(observation, policy=policy)


class RequestAndRecoveryTests(unittest.TestCase):
    def test_closed_c17_wire_and_unhashable_action(self):
        observation, selected = fixture()
        for request in ({"action": [], "command": selected.command},
                        {"action": {}, "command": selected.command},
                        {"action": "selected_child_submit", "command": selected.command, "root_id": "OTHER"},
                        {"action": "delegate_task", "command": selected.command},
                        {"command": selected.command}):
            with self.subTest(request=request):
                with self.assertRaises(DelegationContractError):
                    project_request(request, selected, observation, policy=POLICY)

    def test_nested_command_uses_immediate_coordinator(self):
        observation, selected = fixture(depth=3)
        self.assertIn("coo-cycle:JOB-C2:", submit(selected, observation).command)
        wrong = replace(selected, command=selected.command.replace("JOB-C2", "JOB-ROOT"))
        with self.assertRaisesRegex(DelegationContractError, "COMMAND_SCOPE"):
            submit(wrong, observation)

    def test_model_cannot_choose_sibling_or_new_ordinal(self):
        observation, selected = fixture(leaves=2)
        for command in (selected.command.replace("JOB-W0", "JOB-W1"),
                        selected.command.replace("attempt:1", "attempt:2")):
            with self.subTest(command=command):
                with self.assertRaises(DelegationContractError):
                    project_request({"action": "selected_child_submit", "command": command},
                                     selected, observation, policy=POLICY)

    def test_duplicate_sibling_command_denied(self):
        observation, selected = fixture(leaves=2)
        observation = settle(observation, "JOB-W0")
        command = observation.commands[0]
        for duplicate in (command, replace(command, job_id="JOB-W1", attempt_id="ATT-OTHER")):
            with self.subTest(duplicate=duplicate.job_id):
                with self.assertRaises(DelegationContractError):
                    status(selected, replace(observation, commands=observation.commands + (duplicate,)))

    def test_permission_generation_and_parent_binding_must_be_current(self):
        observation, selected = fixture(depth=2)
        for binding in (replace(observation.authority, permission_digest=digest("revoked")),
                        replace(observation.authority, generation_digest=digest("new-generation")),
                        replace(observation.authority, coordinator_job_id="JOB-ROOT")):
            with self.subTest(binding=binding):
                with self.assertRaisesRegex(DelegationContractError, "CURRENT_AUTHORITY"):
                    submit(selected, replace(observation, authority=binding))
        with self.assertRaises(DelegationContractError):
            status(selected, replace(observation, may_read=False))

    def test_stale_plan_attempt_or_digest_refused(self):
        observation, selected = fixture()
        for change in ({"plan_attempt_id": "ATT-OLD"}, {"plan_digest": digest("old-plan")},
                       {"repair_round": 1}):
            with self.subTest(change=change):
                with self.assertRaisesRegex(DelegationContractError, "FROZEN_LINEAGE"):
                    submit(replace(selected, **change), observation)

    def test_superseded_child_cannot_dispatch_but_original_result_reconciles(self):
        observation, selected = fixture(reviewed=True)
        old = next(job for job in observation.jobs if job.job_id == "JOB-W0")
        repaired = replace(old, job_id="JOB-REPAIR", orchestration_role="repair", repair_round=1,
                            supersedes_job_id=old.job_id)
        plan = observation.plans[0]
        step = replace(plan.steps[0], current_job_id=repaired.job_id, current_repair_round=1)
        observation = replace(observation, jobs=observation.jobs + (repaired,),
                                plans=(replace(plan, steps=(step,)),))
        with self.assertRaisesRegex(DelegationContractError, "STEP_SUPERSEDED"):
            submit(selected, observation)
        observation = settle(observation, "JOB-W0", outcome="PARTIAL")
        self.assertEqual(submit(selected, observation).disposition, "RECONCILE_ORIGINAL")
        self.assertFalse(aggregate(observation).ready_for_owner_handoff)

    def test_absent_or_changed_inherited_union_never_selects_auto_capacity(self):
        observation, selected = fixture(depth=3)
        for job_id, union in (("JOB-ROOT", None), ("JOB-C1", None), ("JOB-C2", digest("widened"))):
            with self.subTest(job=job_id):
                with self.assertRaisesRegex(DelegationContractError, "PLACEMENT_UNION"):
                    submit(selected, change_job(observation, job_id, placement_union_digest=union))

    def test_cancelled_ancestor_stops_fresh_descendant(self):
        observation, selected = fixture(depth=3)
        for job_id in ("JOB-ROOT", "JOB-C1", "JOB-C2"):
            with self.subTest(job=job_id):
                changed = change_job(observation, job_id, cancel_requested_at_ms=123)
                with self.assertRaisesRegex(DelegationContractError, "ANCESTOR_ADMISSION_CLOSED"):
                    submit(selected, changed)
                self.assertEqual(status(selected, changed).disposition, "OBSERVE_UNCLAIMED")

    def test_running_parent_is_not_open_descendant_authority(self):
        observation, selected = fixture(depth=2)
        observation = change_job(observation, "JOB-C1", status="RUNNING",
                                  current_attempt_id="ATT-C1", attempt_count=1)
        with self.assertRaisesRegex(DelegationContractError, "ANCESTOR_ADMISSION_CLOSED"):
            submit(selected, observation)

    def test_cancelled_child_or_closed_submit_permission_refused(self):
        observation, selected = fixture()
        for changed in (change_job(observation, selected.job_id, cancel_requested_at_ms=1),
                        replace(observation, may_submit=False)):
            with self.assertRaises(DelegationContractError):
                submit(selected, changed)

    def test_lost_terminal_return_reconciles_same_attempt_after_restart_cancel(self):
        observation, selected = fixture()
        observation = settle(observation, selected.job_id)
        observation = change_job(observation, "JOB-ROOT", cancel_requested_at_ms=999)
        observation = replace(observation, may_submit=False)
        # Reconstructing the observation/selection represents host restart, with
        # no in-memory queue, original Attempt registry or bridge state to restore.
        returned = submit(replace(selected), replace(observation))
        self.assertEqual(returned.disposition, "RECONCILE_ORIGINAL")
        self.assertEqual(returned.action, "selected_child_status")
        self.assertEqual(returned.original_attempt_id, "ATT-JOB-W0")
        self.assertEqual(returned.fence_generation, 7)
        self.assertEqual(returned.command, selected.command)
        self.assertEqual(returned.result_envelope_digest, observation.results[0].result_envelope_digest)
        self.assertEqual(len(observation.commands), 1)

    def test_unknown_submit_keeps_command_and_never_manufactures_attempt(self):
        observation, selected = fixture()
        unknown = CommandFact(selected.command, selected.job_id, 1, None, None, None, True)
        observation = replace(observation, commands=(unknown,), may_submit=False)
        projected = submit(selected, observation)
        self.assertEqual(projected.action, "selected_child_status")
        self.assertEqual(projected.command, selected.command)
        self.assertIsNone(projected.original_attempt_id)
        self.assertFalse(aggregate(observation).ready_for_owner_handoff)

    def test_wrong_original_attempt_or_missing_attempt_is_never_replaced(self):
        observation, selected = fixture()
        selected = replace(selected, original_attempt_id="ATT-EXPECTED")
        with self.assertRaisesRegex(DelegationContractError, "ORIGINAL_ATTEMPT_MISSING"):
            submit(selected, observation)
        with self.assertRaisesRegex(DelegationContractError, "ORIGINAL_ATTEMPT_CHANGED"):
            submit(selected, settle(observation, "JOB-W0"))

    def test_unknown_earlier_ordinal_cannot_be_retried(self):
        observation, selected = fixture()
        unknown = CommandFact(selected.command, selected.job_id, 1, None, None, None, True)
        observation = replace(observation, commands=(unknown,))
        selected = replace(selected, attempt_ordinal=2, command=selected.command[:-1] + "2")
        with self.assertRaisesRegex(DelegationContractError, "ORIGINAL_EFFECT_UNRESOLVED"):
            submit(selected, observation)

    def test_missing_command_with_observed_attempt_is_not_unclaimed(self):
        observation, selected = fixture()
        observation = change_job(observation, "JOB-W0", status="RUNNING",
                                  attempt_count=1, current_attempt_id="ATT-EXISTS")
        with self.assertRaisesRegex(DelegationContractError, "ORIGINAL_COMMAND_OBSERVATION_MISSING"):
            status(selected, observation)

    def test_active_or_missing_prior_attempt_cannot_be_claimed_again(self):
        observation, selected = fixture()
        observation = change_job(observation, selected.job_id, attempt_count=1,
                                  current_attempt_id="ATT-PRIOR", status="QUEUED")
        next_selection = replace(selected, attempt_ordinal=2, command=selected.command[:-1] + "2",
                                  expected_current_attempt_id="ATT-PRIOR")
        prior = CommandFact(selected.command, selected.job_id, 1, "ATT-PRIOR", "RUNNING", 1)
        for changed in (observation, replace(observation, commands=(prior,))):
            with self.assertRaisesRegex(DelegationContractError, "PRIOR_ATTEMPT_NOT_SETTLED"):
                submit(next_selection, changed)

    def test_canonical_requeue_retains_old_status_and_requires_exact_evidence(self):
        observation, selected = fixture()
        observation = change_job(observation, selected.job_id, attempt_count=1,
                                  current_attempt_id=None, status="QUEUED")
        prior = CommandFact(selected.command, selected.job_id, 1, "ATT-PRIOR", "FAILED", 1)
        observation = replace(observation, commands=(prior,))
        self.assertEqual(status(selected, observation).original_attempt_id, "ATT-PRIOR")
        next_selection = replace(selected, attempt_ordinal=2, command=selected.command[:-1] + "2")
        with self.assertRaisesRegex(DelegationContractError, "PRIOR_ATTEMPT_NOT_SETTLED"):
            submit(next_selection, observation)
        requeue = RequeueFact(selected.job_id, "ATT-PRIOR", 1, 71, 71, digest("canonical-requeue"))
        allowed = replace(observation, requeues=(requeue,))
        self.assertEqual(submit(next_selection, allowed).requeue_evidence_digest, requeue.evidence_digest)
        self.assertEqual(status(selected, allowed).original_attempt_id, "ATT-PRIOR")
        for changed in (replace(requeue, latest_job_event_id=72),
                        replace(requeue, previous_attempt_id="OTHER")):
            with self.assertRaisesRegex(DelegationContractError, "REQUEUE_EVIDENCE_INVALID"):
                submit(next_selection, replace(observation, requeues=(changed,)))

    def test_unrelated_sibling_progress_does_not_stale_frozen_selection(self):
        observation, _ = fixture(leaves=2)
        selected = selection_for(observation, "JOB-W1")
        before = submit(selected, observation)
        observation = settle(observation, "JOB-W0")
        after = submit(selected, observation)
        self.assertEqual(before.selection, after.selection)
        self.assertNotEqual(before.expected_snapshot_digest, after.expected_snapshot_digest)
        self.assertEqual(after.disposition, "FRESH_REQUEST")

    def test_owner_rechecks_competing_snapshots_then_sibling_progresses(self):
        observation, first = fixture(leaves=2)
        second = selection_for(observation, "JOB-W1")
        owner = OwnerTransactionSpecimen(observation)
        first_request, second_request = submit(first, observation), submit(second, observation)
        self.assertEqual(owner.claim_count, 0)  # projection has no effect
        owner.consume(first_request)
        with self.assertRaisesRegex(DelegationContractError, "OWNER_SNAPSHOT_CHANGED"):
            owner.consume(second_request)
        owner.consume(submit(second, owner.observation))
        self.assertEqual(owner.claim_count, 2)
        replay = owner.consume(submit(first, owner.observation))
        self.assertEqual(replay.disposition, "RECONCILE_ORIGINAL")
        self.assertEqual(owner.claim_count, 2)
        self.assertEqual(validate_observation(owner.observation, policy=POLICY).total_descendants, 3)

    def test_owner_rechecks_cancellation_at_claim_boundary(self):
        observation, selected = fixture()
        owner = OwnerTransactionSpecimen(observation)
        request = submit(selected, observation)
        owner.observation = change_job(owner.observation, "JOB-ROOT", cancel_requested_at_ms=1)
        # Even an accidentally reused stamp cannot replace the actual recheck.
        with self.assertRaisesRegex(DelegationContractError, "ANCESTOR_ADMISSION_CLOSED"):
            owner.consume(request)
        self.assertEqual(owner.claim_count, 0)

    def test_records_and_projection_are_immutable_and_public_wire_is_detached(self):
        observation, selected = fixture()
        request = submit(selected, observation)
        with self.assertRaises(FrozenInstanceError):
            observation.jobs[0].depth = 3
        with self.assertRaises(FrozenInstanceError):
            request.selection.authority.generation_digest = digest("tampered")
        wire = request.public_request()
        wire["command"] = "different"
        self.assertEqual(request.command, selected.command)


class AggregateTests(unittest.TestCase):
    def test_partial_child_set_cannot_finalize_parent(self):
        observation, _ = fixture(leaves=2)
        observation = settle(observation, "JOB-W0")
        projection = aggregate(observation)
        self.assertIsInstance(projection, AggregateProjection)
        self.assertFalse(projection.ready_for_owner_handoff)
        self.assertIn("JOB-W1", projection.pending_job_ids)
        observation = settle(observation, "JOB-W1")
        self.assertTrue(aggregate(observation).ready_for_owner_handoff)
        self.assertEqual(observation.jobs[0].status, "QUEUED")  # no finalization

    def test_completed_without_terminal_receipts_or_partial_result_cannot_finalize(self):
        observation, _ = fixture()
        for changed in (change_job(observation, "JOB-W0", status="COMPLETED"),
                        settle(observation, "JOB-W0", outcome="PARTIAL"),
                        settle(observation, "JOB-W0", outcome="REJECTED")):
            with self.subTest(results=changed.results):
                self.assertFalse(aggregate(changed).ready_for_owner_handoff)

    def test_required_review_evidence_binds_exact_current_result(self):
        observation, _ = fixture(reviewed=True)
        self.assertFalse(aggregate(settle(observation, "JOB-W0")).ready_for_owner_handoff)
        completed = settle(observation, "JOB-W0", reviewed=True)
        self.assertTrue(aggregate(completed).ready_for_owner_handoff)
        altered = replace(completed.results[0], reviewed_result_digest=digest("other-result"))
        with self.assertRaisesRegex(DelegationContractError, "REVIEW_BINDING"):
            aggregate(replace(completed, results=(altered,)))

    def test_failed_or_replaced_review_attempt_cannot_approve(self):
        observation, _ = fixture(reviewed=True)
        observation = settle(observation, "JOB-W0", reviewed=True)
        review = observation.jobs[-1]
        for changes in ({"status": "FAILED"}, {"current_attempt_id": "ATT-REPLACEMENT"}):
            with self.assertRaises(DelegationContractError):
                aggregate(change_job(observation, review.job_id, **changes))

    def test_review_job_cannot_obtain_second_attempt(self):
        observation, _ = fixture(reviewed=True)
        observation = settle(observation, "JOB-W0", reviewed=True)
        review = observation.jobs[-1]
        observation = change_job(observation, review.job_id, current_attempt_id="ATT-REVIEW-2", attempt_count=2)
        second = replace(observation.commands[-1], command=command_for(review, 2), attempt_ordinal=2,
                           attempt_id="ATT-REVIEW-2")
        observation = replace(observation, commands=observation.commands + (second,),
                                results=(replace(observation.results[0], review_attempt_id=second.attempt_id),))
        with self.assertRaisesRegex(DelegationContractError, "REVIEW_BINDING"):
            aggregate(observation)

    def test_deferred_reservation_keeps_budget_and_independent_sibling_progress(self):
        observation, _ = fixture(leaves=3)
        future_job = observation.jobs[-1]
        plan = observation.plans[0]
        deferred = replace(plan.steps[2], current_job_id=None, prerequisite_step_ids=("STEP-0",),
                            initial_work_job_id=None, initial_work_command_id=None)
        observation = replace(observation, jobs=observation.jobs[:-1],
                                plans=(replace(plan, steps=plan.steps[:2] + (deferred,)),),
                                dependencies=observation.dependencies[:-1])
        self.assertEqual(dict(validate_observation(observation, policy=POLICY).reservations)["JOB-ROOT"], 4)
        self.assertEqual(submit(selection_for(observation, "JOB-W1"), observation).disposition, "FRESH_REQUEST")
        projection = aggregate(observation)
        self.assertIn(("JOB-ROOT", "STEP-2"), projection.pending_steps)
        self.assertFalse(projection.ready_for_owner_handoff)
        # Only the existing owner materializes it; this fixture supplies that
        # later observation without changing the original reservation.
        observation = settle(observation, "JOB-W0")
        materialized = replace(deferred, current_job_id=future_job.job_id)
        observation = replace(observation, jobs=observation.jobs + (future_job,),
                                plans=(replace(plan, steps=plan.steps[:2] + (materialized,)),))
        observation = bind_dependency(observation, future_job.job_id)
        self.assertEqual(submit(selection_for(observation, future_job.job_id), observation).disposition,
                          "FRESH_REQUEST")

    def test_missing_unconditional_work_cannot_be_relabelled_deferred(self):
        observation, _ = fixture(leaves=2)
        plan = observation.plans[0]
        missing = replace(plan.steps[1], current_job_id=None, initial_work_job_id=None,
                           initial_work_command_id=None)
        observation = replace(observation, jobs=observation.jobs[:-1],
                                plans=(replace(plan, steps=(plan.steps[0], missing)),))
        with self.assertRaises(DelegationContractError):
            aggregate(observation)

    def test_wrong_attempt_or_terminal_digest_refused(self):
        observation, _ = fixture()
        observation = settle(observation, "JOB-W0")
        for changed in (replace(observation.results[0], attempt_id="ATT-OTHER"),
                        replace(observation.results[0], terminal_evidence_digest="missing"),
                        replace(observation.results[0], fence_generation=6),
                        replace(observation.results[0], repair_round=False)):
            with self.assertRaises(DelegationContractError):
                aggregate(replace(observation, results=(changed,)))

    def test_duplicate_result_cannot_satisfy_two_dependencies(self):
        observation, _ = fixture(leaves=2)
        observation = settle(observation, "JOB-W0")
        with self.assertRaises(DelegationContractError):
            aggregate(replace(observation, results=observation.results * 2))

    def test_terminal_parent_cannot_hide_live_grandchild(self):
        observation, _ = fixture(depth=2)
        observation = settle(observation, "JOB-C1")
        projected = aggregate(observation)
        self.assertFalse(projected.ready_for_owner_handoff)
        self.assertIn("JOB-W0", projected.pending_job_ids)

    def test_aggregate_child_cannot_dispatch_before_its_descendants(self):
        observation, _ = fixture(depth=2)
        selected = selection_for(observation, "JOB-C1")
        observation = replace(observation, authority=selected.authority)
        with self.assertRaisesRegex(DelegationContractError, "AGGREGATE_DEPENDENCIES_PENDING"):
            submit(selected, observation)
        completed = settle(observation, "JOB-W0")
        self.assertEqual(submit(selected, completed).disposition, "FRESH_REQUEST")

    def test_unresolved_terminal_return_prevents_aggregate_success(self):
        observation, _ = fixture()
        observation = settle(observation, "JOB-W0")
        observation = replace(observation, commands=(replace(observation.commands[0], effect_unknown=True),))
        result = aggregate(observation)
        self.assertFalse(result.ready_for_owner_handoff)
        self.assertEqual(result.unresolved_commands, (observation.commands[0].command,))

    def test_cancelled_parent_cannot_project_success(self):
        observation, _ = fixture()
        observation = settle(observation, "JOB-W0")
        observation = change_job(observation, "JOB-ROOT", cancel_requested_at_ms=10)
        self.assertFalse(aggregate(observation).ready_for_owner_handoff)

    def test_dependency_blocks_only_dependent_sibling(self):
        observation, selected = fixture(leaves=3)
        plan = observation.plans[0]
        dependent = replace(plan.steps[2], prerequisite_step_ids=(plan.steps[0].step_id,),
                             initial_work_job_id=None, initial_work_command_id=None)
        observation = replace(observation, plans=(replace(plan, steps=plan.steps[:2] + (dependent,)),))
        sibling, waiting = selection_for(observation, "JOB-W1"), selection_for(observation, "JOB-W2")
        self.assertEqual(submit(sibling, observation).disposition, "FRESH_REQUEST")
        with self.assertRaisesRegex(DelegationContractError, "DEPENDENCY_NOT_ACCEPTED"):
            submit(waiting, observation)
        completed = bind_dependency(settle(observation, selected.job_id), waiting.job_id)
        self.assertEqual(submit(waiting, completed).disposition, "FRESH_REQUEST")


class CanonicalAdapterTests(unittest.TestCase):
    def test_full_v5_plan_and_v3_reservation_project_at_all_levels(self):
        observation, _ = fixture(depth=3, leaves=11)
        projected, wires = canonical_plan_fixture(observation)
        self.assertEqual(validate_observation(projected, policy=POLICY).total_descendants, 16)
        self.assertEqual(submit(selection_for(projected, "JOB-W0"), projected).disposition, "FRESH_REQUEST")
        for plan in projected.plans:
            body, admission = wires[plan.coordinator_job_id]
            self.assertEqual(plan.plan_digest, canonical_digest(body))
            self.assertEqual(plan.reservation_digest, admission["reservation_digest"])

    def test_plan_adapter_retains_deferred_slots_and_detaches_mutable_inputs(self):
        observation, _ = fixture(leaves=2)
        plan = observation.plans[0]
        deferred = replace(plan.steps[1], current_job_id=None, initial_work_job_id=None,
                           initial_work_command_id=None, prerequisite_step_ids=(plan.steps[0].step_id,))
        observation = replace(observation, jobs=observation.jobs[:-1],
                              plans=(replace(plan, steps=(plan.steps[0], deferred)),), dependencies=())
        projected, wires = canonical_plan_fixture(observation)
        self.assertEqual(projected.plans[0].reserved_children_total, 3)
        self.assertIsNone(projected.plans[0].steps[1].current_job_id)
        self.assertIn(("JOB-ROOT", "STEP-1"), aggregate(projected).pending_steps)
        wires["JOB-ROOT"][0]["steps"][1]["prerequisite_step_ids"].clear()
        wires["JOB-ROOT"][1]["steps"].clear()
        self.assertEqual(projected.plans[0].steps[1].prerequisite_step_ids, ("STEP-0",))

    def test_plan_adapter_refuses_tampered_digest_and_foreign_coordinator(self):
        observation, _ = fixture()
        plan, admission = plan_wires(observation.plans[0])
        planner = observation.jobs[1]
        for key, value in (("plan_digest", digest("other")), ("coordinator_job_id", "JOB-OTHER")):
            changed = dict(admission, **{key: value})
            if key == "coordinator_job_id":
                changed.pop("reservation_digest")
                changed["reservation_digest"] = orchestration_digest(changed)
            with self.assertRaises(DelegationContractError):
                project_admitted_plan(plan=plan, admission=changed, planner=planner,
                                      jobs=observation.jobs, policy=POLICY)

    def test_accepted_revision_is_closed_strict_and_immutable(self):
        observation, _ = fixture()
        job = observation.jobs[-1]
        wire = accepted_wire(job, "ATT-WORK", digest("role"), 0)
        projected = project_accepted_revision(wire)
        self.assertEqual(asdict(projected), wire)
        for altered in (dict(wire, ordinal=True), dict(wire, extra=True),
                        dict(wire, qualifying_review_result_digest=digest("unowed-review")),
                        dict(wire, current_raw_result_digest="missing")):
            with self.assertRaises(DelegationContractError):
                project_accepted_revision(altered)
        with self.assertRaises(FrozenInstanceError):
            projected.repair_round = 1

    def test_review_and_aggregate_use_role_digest_while_status_uses_envelope(self):
        observation, selected = fixture(reviewed=True)
        observation = settle(observation, selected.job_id, reviewed=True)
        args = completion_wires(observation, selected.job_id)
        role_digest = canonical_digest(args["envelope"]["role_result"])
        accepted = accepted_wire(args["job"], args["command"].attempt_id, role_digest, 0, reviewed=True)
        result = project_child_result(**args, accepted_revision=accepted)
        observation = replace(observation, results=(result,))
        self.assertNotEqual(result.result_envelope_digest, result.role_result_digest)
        self.assertEqual(result.reviewed_result_digest, role_digest)
        self.assertEqual(aggregate(observation).accepted_result_digests, (role_digest,))
        self.assertEqual(status(selected, observation).result_envelope_digest, canonical_digest(args["envelope"]))
        accepted["current_result_digest"] = canonical_digest(args["envelope"])
        with self.assertRaisesRegex(DelegationContractError, "ACCEPTED_REVISION"):
            project_child_result(**args, accepted_revision=accepted)
        wrong = replace(result, reviewed_result_digest=result.result_envelope_digest)
        with self.assertRaisesRegex(DelegationContractError, "REVIEW_BINDING"):
            aggregate(replace(observation, results=(wrong,)))

    def test_completed_wire_without_owner_acceptance_stays_partial(self):
        observation, _ = fixture()
        observation = settle(observation, "JOB-W0")
        args = completion_wires(observation, "JOB-W0")
        result = project_child_result(**args)
        self.assertEqual(result.outcome, "PARTIAL")
        self.assertFalse(aggregate(replace(observation, results=(result,))).ready_for_owner_handoff)
        args["envelope"]["summary"] = "Mutable source changed after projection"
        self.assertNotEqual(result.result_envelope_digest, canonical_digest(args["envelope"]))

    def test_terminal_wire_cannot_substitute_attempt_receipt_or_grant(self):
        observation, _ = fixture()
        observation = settle(observation, "JOB-W0")
        args = completion_wires(observation, "JOB-W0")
        accepted = accepted_wire(args["job"], args["command"].attempt_id,
                                 canonical_digest(args["envelope"]["role_result"]), 0)
        for name, value in (("attempt_id", "ATT-OTHER"), ("effective_grant_digest", digest("different-grant")),
                            ("artifact_receipt_digest", digest("different-artifact"))):
            terminal = dict(args["terminal"], **{name: value})
            terminal.pop("terminal_evidence_digest")
            terminal["terminal_evidence_digest"] = orchestration_digest(terminal)
            with self.assertRaises(DelegationContractError):
                project_child_result(**dict(args, terminal=terminal), accepted_revision=accepted)

    def test_nested_aggregate_preserves_parent_lineage_and_own_plan(self):
        observation, _ = fixture(depth=2)
        observation, _ = canonical_plan_fixture(observation)
        observation = settle(observation, "JOB-W0")
        args = completion_wires(observation, "JOB-W0")
        leaf = project_child_result(**args, accepted_revision=accepted_wire(args["job"], args["command"].attempt_id,
                                    canonical_digest(args["envelope"]["role_result"]), 0))
        observation = replace(observation, results=(leaf,))
        wire, plan = handoff_wire(observation, "JOB-C1")
        scope = project_aggregation_handoff(wire, plan=plan)
        keys = {"ordinal", "plan_step_id", "current_job_id", "current_attempt_id", "current_result_digest",
                "repair_round", "review_required", "qualifying_review_job_id", "qualifying_review_attempt_id",
                "qualifying_review_result_digest"}
        body = {key: wire[key] for key in ("root_job_id", "coordinator_job_id", "policy_sha",
                                          "plan_attempt_id", "plan_digest", "handoff_digest")}
        body.update(schema_version="mastermind.aggregation_result/v2", aggregate_summary="Scoped children accepted",
                    evidence_digests=[], revisions=[{key: value for key, value in item.items() if key in keys}
                                                    for item in wire["revisions"]])
        observation = settle(observation, "JOB-C1")
        args = completion_wires(observation, "JOB-C1", body=body)
        result = project_child_result(**args, aggregation=scope, accepted_revision=accepted_wire(
            args["job"], args["command"].attempt_id, canonical_digest(body), 0))
        self.assertNotEqual(result.plan_attempt_id, result.aggregation.plan_attempt_id)
        self.assertEqual(result.plan_attempt_id, observation.plans[0].plan_attempt_id)
        self.assertEqual(result.aggregation.plan_attempt_id, observation.plans[1].plan_attempt_id)
        observation = replace(observation, results=(leaf, result))
        self.assertTrue(aggregate(observation).ready_for_owner_handoff)
        stale = replace(scope.revisions[0], current_raw_result_digest=digest("new-raw-observation"))
        result = replace(result, aggregation=replace(scope, revisions=(stale,)))
        self.assertFalse(aggregate(replace(observation, results=(leaf, result))).ready_for_owner_handoff)
        with self.assertRaisesRegex(DelegationContractError, "AGGREGATION_RESULT"):
            project_child_result(**args, aggregation=replace(scope, plan_attempt_id=result.plan_attempt_id))

    def test_handoff_binds_rejected_history_and_order(self):
        observation, _ = fixture(leaves=2)
        observation = settle(settle(observation, "JOB-W0"), "JOB-W1")
        wire, plan = handoff_wire(observation, "JOB-ROOT")
        scope = project_aggregation_handoff(wire, plan=plan)
        self.assertEqual(scope.rejected_history_digest, orchestration_digest([]))
        for changed in (dict(wire, rejected_history=[{"changed": True}]),
                        dict(wire, revisions=list(reversed(wire["revisions"])))):
            with self.assertRaises(DelegationContractError):
                project_aggregation_handoff(changed, plan=plan)
        changed = dict(wire, revisions=list(reversed(wire["revisions"])))
        changed.pop("handoff_digest")
        changed["handoff_digest"] = orchestration_digest(changed)
        with self.assertRaisesRegex(DelegationContractError, "AGGREGATION_REVISION"):
            project_aggregation_handoff(changed, plan=plan)

    def test_root_planner_review_cannot_be_fabricated_as_child_results(self):
        observation, _ = fixture()
        observation = settle(observation, "JOB-W0")
        args = completion_wires(observation, "JOB-W0")
        for job in (observation.jobs[0], observation.jobs[1], replace(args["job"], orchestration_role="review")):
            with self.assertRaisesRegex(DelegationContractError, "CHILD_RESULT_ROLE"):
                project_child_result(**dict(args, job=job))

    def test_empty_dependency_manifest_required_for_fresh_but_not_status(self):
        observation, selected = fixture()
        missing = replace(observation, dependencies=())
        with self.assertRaisesRegex(DelegationContractError, "DEPENDENCY_MANIFEST_ABSENT"):
            submit(selected, missing)
        self.assertEqual(status(selected, missing).disposition, "OBSERVE_UNCLAIMED")
        completed = settle(missing, selected.job_id)
        self.assertEqual(submit(selected, completed).disposition, "RECONCILE_ORIGINAL")

    def test_creation_manifest_changes_only_through_owner_observation(self):
        observation, _ = fixture(leaves=2)
        plan = observation.plans[0]
        step = replace(plan.steps[1], prerequisite_step_ids=("STEP-0",),
                       initial_work_job_id=None, initial_work_command_id=None)
        observation = replace(observation, plans=(replace(plan, steps=(plan.steps[0], step)),))
        observation = bind_dependency(settle(observation, "JOB-W0"), "JOB-W1")
        selected = selection_for(observation, "JOB-W1")
        self.assertEqual(submit(selected, observation).disposition, "FRESH_REQUEST")
        result = observation.results[0]
        changed = replace(result, accepted_revision=replace(result.accepted_revision,
                          execution_principal_snapshot_digest=digest("new-principal")))
        stale = replace(observation, results=(changed,))
        with self.assertRaisesRegex(DelegationContractError, "DEPENDENCY_MANIFEST_STALE"):
            submit(selected, stale)
        # The prior accepted role digest alone is insufficient: exact provenance must agree.
        self.assertEqual(result.role_result_digest, changed.role_result_digest)
        model = OwnerTransactionSpecimen(observation)
        claim = model.consume(submit(selected, observation))
        restarted = replace(model.observation, results=(changed,))
        self.assertEqual(submit(selected, restarted).original_attempt_id, claim.attempt_id)

    def test_accepted_repair_invalidates_old_prerequisite_snapshot(self):
        observation, _ = fixture(leaves=2)
        plan = observation.plans[0]
        first = replace(plan.steps[0], review_required=True, reserved_slots=9)
        second = replace(plan.steps[1], prerequisite_step_ids=(first.step_id,),
                         initial_work_job_id=None, initial_work_command_id=None)
        observation = replace(observation, plans=(replace(plan, steps=(first, second), reserved_children_total=11),))
        observation = bind_dependency(settle(observation, "JOB-W0", reviewed=True), "JOB-W1")
        selected = selection_for(observation, "JOB-W1")
        self.assertEqual(submit(selected, observation).disposition, "FRESH_REQUEST")
        original = next(job for job in observation.jobs if job.job_id == "JOB-W0")
        repair = replace(original, job_id="JOB-REPAIR", orchestration_role="repair", repair_round=1,
                         supersedes_job_id=original.job_id, status="QUEUED", attempt_count=0, current_attempt_id=None)
        first = replace(first, current_job_id=repair.job_id, current_repair_round=1)
        observation = replace(observation, jobs=observation.jobs + (repair,),
                              plans=(replace(observation.plans[0], steps=(first, second)),))
        observation = settle(observation, repair.job_id, reviewed=True)
        with self.assertRaisesRegex(DelegationContractError, "DEPENDENCY_MANIFEST_STALE"):
            submit(selected, observation)

    def test_coordinator_own_unknown_command_blocks_aggregate_handoff(self):
        observation, _ = fixture(depth=2)
        observation = settle(observation, "JOB-W0")
        coordinator = next(job for job in observation.jobs if job.job_id == "JOB-C1")
        unknown = CommandFact(command_for(coordinator), coordinator.job_id, 1, None, None, None, True)
        observation = replace(observation, commands=observation.commands + (unknown,))
        scoped = aggregate(observation, "JOB-C1")
        self.assertFalse(scoped.ready_for_owner_handoff)
        self.assertEqual(scoped.unresolved_commands, (unknown.command,))

    def test_parent_unknown_command_does_not_block_independent_nested_progress(self):
        observation, _ = fixture(depth=2)
        observation = settle(observation, "JOB-W0")
        root = observation.jobs[0]
        unknown = CommandFact(command_for(root), root.job_id, 1, None, None, None, True)
        observation = replace(observation, commands=observation.commands + (unknown,))
        self.assertTrue(aggregate(observation, "JOB-C1").ready_for_owner_handoff)
        self.assertFalse(aggregate(observation).ready_for_owner_handoff)

    def test_unknown_ancestor_fences_fresh_descendants_without_erasing_status(self):
        observation, selected = fixture(depth=2)
        root = observation.jobs[0]
        unknown = CommandFact(command_for(root), root.job_id, 1, None, None, None, True)
        observation = replace(observation, commands=(unknown,))
        with self.assertRaisesRegex(DelegationContractError, "ANCESTOR_EFFECT_UNRESOLVED"):
            submit(selected, observation)
        completed = settle(observation, selected.job_id)
        self.assertEqual(submit(selected, completed).disposition, "RECONCILE_ORIGINAL")

    def test_unknown_sibling_does_not_fence_distinct_reserved_sibling(self):
        observation, _ = fixture(leaves=2)
        first, second = observation.jobs[-2:]
        unknown = CommandFact(command_for(first), first.job_id, 1, None, None, None, True)
        observation = replace(observation, commands=(unknown,))
        self.assertEqual(submit(selection_for(observation, second.job_id), observation).disposition, "FRESH_REQUEST")

    def test_dependency_snapshot_is_closed_digest_bound_and_exactly_owned(self):
        observation, _ = fixture()
        fact = observation.dependencies[0]
        for dependencies in ((fact, fact), (replace(fact, dependency_manifest_digest=digest("tampered")),),
                             (replace(fact, job_id="JOB-FOREIGN"),)):
            with self.assertRaises(DelegationContractError):
                validate_observation(replace(observation, dependencies=dependencies), policy=POLICY)

    def test_original_attempt_status_after_successor_started(self):
        observation, selected = fixture()
        prior = CommandFact(selected.command, selected.job_id, 1, "ATT-OLD", "FAILED", 1)
        successor = CommandFact(selected.command[:-1] + "2", selected.job_id, 2, "ATT-NEW", "RUNNING", 2)
        observation = change_job(observation, selected.job_id, status="RUNNING", attempt_count=2,
                                 current_attempt_id=successor.attempt_id)
        observation = replace(observation, commands=(prior, successor))
        returned = submit(selected, observation)
        self.assertEqual(returned.original_attempt_id, prior.attempt_id)
        self.assertEqual(returned.attempt_status, "FAILED")
        self.assertEqual(returned.fence_generation, 1)


if __name__ == "__main__":
    unittest.main()
