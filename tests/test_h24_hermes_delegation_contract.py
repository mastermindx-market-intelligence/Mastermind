"""Hermetic H24-07 fixture and owner transaction-sequence specimen.

The specimen below MODELS the existing owner's recheck boundary. It does not
instantiate Runtime, create real Jobs/Attempts, acquire leases or call Hermes.
The test suite is also runnable with stdlib unittest; no installation is needed.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
import unittest

from control_plane.executive_coo_policy import CooCyclePolicy
from control_plane.hermes_delegation_contract import (
    AggregateProjection, AuthorityBinding, CommandFact, DelegationContractError,
    FrozenChild, Grant, JobFact, OwnerObservation, PlanFact, RequeueFact, ResultFact, StepFact,
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
    return observation, selection_for(observation, "JOB-W0")


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
                        7, digest(f"result-{job_id}"), digest(f"terminal-{job_id}"), outcome)
    jobs, commands = observation.jobs, observation.commands + (command,)
    if reviewed:
        review_id, review_attempt = f"REV-{job_id}", f"ATT-REV-{job_id}"
        review_job = replace(original, job_id=review_id, orchestration_role="review",
                              status="COMPLETED", current_attempt_id=review_attempt,
                              attempt_count=1, reviews_job_id=job_id)
        jobs += (review_job,)
        commands += (CommandFact(command_for(review_job), review_id, 1, review_attempt,
                                  "COMPLETED", 8),)
        result = replace(result, review_attempt_id=review_attempt,
                          review_acceptance_digest=digest(f"review-{job_id}"),
                          reviewed_result_digest=result.result_envelope_digest)
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
        root_only = replace(observation, jobs=observation.jobs[:1], plans=())
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
        validate_observation(observation, policy=POLICY)
        self.assertEqual(submit(selection_for(observation, "JOB-W0"), observation).selection.plan_step_id,
                          "phase:research")
        observation = settle(observation, "JOB-W0")
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
                                plans=(replace(plan, steps=plan.steps[:2] + (deferred,)),))
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
        self.assertEqual(submit(waiting, settle(observation, selected.job_id)).disposition, "FRESH_REQUEST")


if __name__ == "__main__":
    unittest.main()
