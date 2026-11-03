"""Offline harness for Executive Ecosystem Completion journeys H3, H5, H6 and H7.

Each journey is split into two halves:

* a **driver** that runs the journey in-process against a synthetic
  ``Runtime.at(tmp_path)`` control plane (no host, daemon, network, credential
  or Keychain), and
* a **completion predicate** (``assert_h*_complete``) that checks the ledger's
  completion test literally against a plain-data observation.

The predicates read only typed states, ids, event types and counts, never a
``Runtime`` object, so a later host-backed adapter can build the same
observation from the armed host's supported read API and reuse the predicate
unchanged.  The completion tests are quoted verbatim from
``research/EXECUTIVE_ECOSYSTEM_COMPLETION_CAPABILITY_LEDGER_2026-10-17.md``
(rows H3, H5, H6, H7) in ``JOURNEY_COMPLETION_TESTS``.

These tests extend, not duplicate, the existing unit coverage:
``tests/test_executive_os_phase1fb.py`` (shrink-only paths, independent
review), ``tests/test_executive_os_phase1fc.py`` (COO cycle review/repair/
aggregation) and ``tests/test_executive_inbox_phase1fb.py`` (inbox kinds).
What they add is the end-to-end journey shape: the parent actually consumes the
return, refusals are proven effect-free, and no duplicate root appears.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from control_plane.ceo_intent import submit_intent
from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_inbox import build_inbox
from control_plane.executive_orchestration_result import canonical_digest
from control_plane.executive_runtime import (
    JobPayload,
    JobStatus,
    Runtime,
    StateConflict,
)
from tests.test_executive_os_phase1fc import (
    _complete_ohf_role,
    _cycle_through_completed_work,
    _register as _register_cycle_worker,
    _review_body,
    _v2_intent,
)


JOURNEY_COMPLETION_TESTS = {
    "H3": (
        "a review Job linked by `reviews_job_id` completes and the parent "
        "consumes it"
    ),
    "H5": (
        "a Job touching a path outside `allowed_write_paths` is refused with a "
        "typed error and no effect"
    ),
    "H6": (
        "a failed child yields a repair child or an escalation item consumed by "
        "the parent; no duplicate root"
    ),
    "H7": (
        "a correction on a RUNNING Job terminalizes it with a typed state and "
        "the parent consumes the correction"
    ),
}

_TERMINAL = {"COMPLETED", "CANCELLED", "FAILED", "LOST", "RATE_LIMITED"}
_NOW = "2026-11-02T12:00:00+00:00"


# --------------------------------------------------------------------------
# Plain-data observation helpers (the only place a Runtime is read).
# --------------------------------------------------------------------------


def _register_generic(runtime: Runtime, worker_id: str) -> None:
    runtime.workers.register_worker(
        worker_id,
        provider="codex",
        account_label=f"{worker_id}-account",
        worker_type="fixture",
        capabilities=["code", "research", "review"],
    )


def _lease_token(runtime: Runtime, attempt_id: str) -> str:
    with runtime.store.read() as connection:
        row = connection.execute(
            "SELECT lease_token FROM attempts WHERE attempt_id=?", (attempt_id,)
        ).fetchone()
    assert row is not None and row[0] is not None
    return str(row[0])


def _effect_snapshot(runtime: Runtime) -> dict[str, Any]:
    """Every durable effect a refused request could leave behind."""

    with runtime.store.read() as connection:
        return {
            "jobs": [
                tuple(row)
                for row in connection.execute(
                    "SELECT job_id,status,version FROM jobs ORDER BY job_id"
                ).fetchall()
            ],
            "attempts": [
                tuple(row)
                for row in connection.execute(
                    "SELECT attempt_id,status,version FROM attempts ORDER BY attempt_id"
                ).fetchall()
            ],
            "event_count": connection.execute(
                "SELECT COUNT(*) FROM events"
            ).fetchone()[0],
            "max_event_id": connection.execute(
                "SELECT COALESCE(MAX(event_id),0) FROM events"
            ).fetchone()[0],
        }


def _job_view(runtime: Runtime, job_id: str) -> dict[str, Any]:
    job = runtime.jobs.get_job(job_id)
    assert job is not None
    with runtime.store.read() as connection:
        cancel_at = connection.execute(
            "SELECT cancel_requested_at_ms FROM jobs WHERE job_id=?", (job_id,)
        ).fetchone()[0]
    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "parent_job_id": job.parent_job_id,
        "root_job_id": job.root_job_id,
        "reviews_job_id": job.reviews_job_id,
        "review_required": job.review_required,
        "orchestration_role": job.orchestration_role,
        "supersedes_job_id": job.supersedes_job_id,
        "repair_round": job.repair_round,
        "escalation_target": job.escalation_target,
        "cancel_requested_at_ms": cancel_at,
        "result": job.result,
        "event_types": [
            event.event_type for event in runtime.events.list_events(job_id=job_id)
        ],
    }


def _root_ids(runtime: Runtime) -> list[str]:
    return sorted(job.job_id for job in runtime.jobs.list_jobs() if job.parent_job_id is None)


def _runtime_inbox_items(root: Path) -> dict[str, dict[str, Any]]:
    inbox = build_inbox(
        repo_root=root, include_boot_packet=False, environ={}, now=_NOW
    )
    return {
        item["job_id"]: item
        for item in inbox["attention"]
        if item.get("source") == "runtime"
    }


# --------------------------------------------------------------------------
# Completion predicates: literal ledger completion tests over plain data.
# --------------------------------------------------------------------------


def assert_h3_complete(observation: dict[str, Any]) -> None:
    """H3: a review Job linked by reviews_job_id completes and the parent consumes it."""

    review = observation["review"]
    reviewed = observation["reviewed_child"]
    parent = observation["parent"]
    # "a review Job linked by reviews_job_id"
    assert review["reviews_job_id"] == reviewed["job_id"]
    assert reviewed["review_required"] is True
    assert review["parent_job_id"] == reviewed["parent_job_id"] == parent["job_id"]
    # "... completes" (independently: a self-review is VOID, not a completion)
    assert review["status"] == "COMPLETED"
    assert review["worker_id"] != reviewed["worker_id"]
    # "... and the parent consumes it": the parent's terminal result names the
    # exact review it consumed, and nothing in the tree is left living.
    assert parent["status"] == "COMPLETED"
    assert review["job_id"] in parent["consumed_review_job_ids"]
    assert all(status in _TERMINAL for status in observation["tree_statuses"].values())
    assert observation["root_ids"] == [parent["root_job_id"]]


def assert_h5_complete(observation: dict[str, Any]) -> None:
    """H5: a Job touching a path outside allowed_write_paths is refused, typed, no effect."""

    refusal = observation["refusal"]
    assert refusal["requested_paths"], "the probe must request a write path"
    assert not set(refusal["requested_paths"]) <= set(refusal["allowed_write_paths"])
    # "refused with a typed error"
    assert refusal["error_type"] in observation["typed_error_names"]
    assert refusal["error_contains"] in refusal["message"]
    # "and no effect"
    assert observation["effects_after"] == observation["effects_before"]


def assert_h6_complete(observation: dict[str, Any]) -> None:
    """H6: failed child yields a repair child or an escalation item consumed by the parent; no duplicate root."""

    failed = observation["failed_child"]
    assert failed["status"] in {"FAILED", "COMPLETED"}  # COMPLETED == rejected by review
    assert failed["rejected"] is True
    repair = observation.get("repair_child")
    escalation = observation.get("escalation_item")
    assert (repair is None) != (escalation is None), "exactly one lawful outcome"
    if repair is not None:
        assert repair["supersedes_job_id"] == failed["job_id"]
        assert repair["parent_job_id"] == failed["parent_job_id"]
        assert repair["repair_round"] == (failed["repair_round"] or 0) + 1
        # consumed by the parent: the parent's handoff/aggregation is bound to
        # the repair, not to the rejected child.
        assert observation["parent_consumed_job_id"] == repair["job_id"]
    else:
        assert escalation["job_id"] == failed["job_id"]
        assert escalation["kind"] in {"job_failed", "escalated_exception"}
        # consumed by the parent: the parent's next cycle reads the failure as
        # a typed, replay-stable block naming the failed child instead of
        # silently requeueing it or minting a replacement root.
        consumption = observation["parent_consumption"]
        assert consumption["action"] == "BLOCKED"
        assert consumption["reason"] == "child_terminal_adverse"
        assert consumption["selected_job_id"] == failed["job_id"]
        assert consumption["replay_identical"] is True
        assert "JOB_REQUEUED" not in failed["event_types"]
    # "no duplicate root"
    assert observation["root_ids_after"] == observation["root_ids_before"]
    assert len(observation["root_ids_after"]) == 1


def assert_h7_complete(observation: dict[str, Any]) -> None:
    """H7: a correction on a RUNNING Job terminalizes it typed; the parent consumes it."""

    target = observation["corrected_child"]
    assert observation["status_at_correction"] == "RUNNING"
    # "terminalizes it with a typed state"
    assert observation["status_after_request"] == "CANCEL_REQUESTED"
    assert target["cancel_requested_at_ms"] is not None
    assert target["status"] == "CANCELLED"
    assert target["event_types"][-2:] == ["JOB_CANCEL_REQUESTED", "JOB_CANCELLED"]
    # the parent cannot consume while the correction is still in flight ...
    refusal = observation["parent_refusal_while_in_flight"]
    assert "child job(s) are living" in refusal and target["job_id"] in refusal
    # ... and "the parent consumes the correction" once it is typed-terminal.
    parent = observation["parent"]
    assert parent["status"] == "COMPLETED"
    assert target["job_id"] in parent["consumed_correction_job_ids"]
    assert observation["root_ids"] == [parent["job_id"]]


# --------------------------------------------------------------------------
# H3 — operator -> child -> original-parent reviewed return
# --------------------------------------------------------------------------


def test_journey_h3_cycle_review_linked_by_reviews_job_id_is_consumed_by_parent(
    tmp_path: Path,
) -> None:
    """JOURNEY H3 (COO cycle path): review -> handoff -> parent aggregation."""

    runtime, cycle, dispatches, root, planner, work, work_seal = (
        _cycle_through_completed_work(
            tmp_path,
            intent_id="CEO-JOURNEY-H3",
            review_workers=["worker-b"],
        )
    )
    assert cycle.run_once(root.job_id).action == "REVIEW_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    review_dispatch = dispatches[-1]
    plan_digest = str(runtime.jobs.get_job(work.attempt.job_id).plan_digest)
    review_body = _review_body(
        root_id=root.job_id,
        plan_attempt_id=planner.attempt.attempt_id,
        plan_digest=plan_digest,
        target_job_id=work.attempt.job_id,
        target_attempt_id=work.attempt.attempt_id,
        target_result_digest=work_seal["role_result_digest"],
        repair_round=0,
        verdict="approve",
    )
    review_seal, _ = _complete_ohf_role(
        runtime, review_dispatch, review_body, identity_seed=3301
    )
    assert cycle.run_once(root.job_id).action == "HANDOFF_CREATED"
    handoff = runtime.jobs.get_cycle_handoff(root.job_id)
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    aggregation_dispatch = dispatches[-1]
    revision_keys = (
        "ordinal", "plan_step_id", "current_job_id", "current_attempt_id",
        "current_result_digest", "repair_round", "review_required",
        "qualifying_review_job_id", "qualifying_review_attempt_id",
        "qualifying_review_result_digest",
    )
    aggregation_body = {
        "schema_version": "mastermind.aggregation_result/v1",
        "root_job_id": root.job_id,
        "handoff_digest": handoff["handoff_digest"],
        "policy_sha": handoff["policy_sha"],
        "plan_attempt_id": handoff["plan_attempt_id"],
        "plan_digest": handoff["plan_digest"],
        "revisions": [
            {key: item[key] for key in revision_keys} for item in handoff["revisions"]
        ],
        "aggregate_summary": "One reviewed return consumed by the original parent.",
        "evidence_digests": [],
    }
    _complete_ohf_role(
        runtime, aggregation_dispatch, aggregation_body, identity_seed=3302
    )
    assert cycle.run_once(root.job_id).action == "NO_ACTION"

    review_job_id = review_dispatch.attempt.job_id
    review_view = _job_view(runtime, review_job_id)
    work_view = _job_view(runtime, work.attempt.job_id)
    root_view = _job_view(runtime, root.job_id)
    tree = [job for job in runtime.jobs.list_jobs() if job.root_job_id == root.job_id]
    observation = {
        "review": {**review_view, "worker_id": review_dispatch.attempt.worker_id},
        "reviewed_child": {**work_view, "worker_id": work.attempt.worker_id},
        "parent": {
            **root_view,
            # The parent consumed the handoff whose qualifying review is this
            # exact review Job/result digest.
            "consumed_review_job_ids": [
                item["qualifying_review_job_id"] for item in handoff["revisions"]
                if item["qualifying_review_result_digest"]
                == review_seal["role_result_digest"]
            ],
        },
        "tree_statuses": {job.job_id: job.status.value for job in tree},
        "root_ids": _root_ids(runtime),
    }
    # Planner/work/review/aggregation all hang off the original root.
    assert review_view["parent_job_id"] == root.job_id
    assert review_view["orchestration_role"] == "review"
    assert_h3_complete(observation)


def test_journey_h3_generic_review_is_consumed_and_parent_waits_for_it(
    tmp_path: Path,
) -> None:
    """JOURNEY H3 (operator path): parent aggregation is refused until the linked review completes."""

    runtime = Runtime.at(tmp_path)
    _register_generic(runtime, "worker-a")
    _register_generic(runtime, "worker-b")
    parent = runtime.jobs.create_job("Operator parent")
    child = runtime.jobs.create_job(
        "Reviewed child", parent_job_id=parent.job_id, review_required=True
    )
    review = runtime.jobs.create_job(
        "Linked review", parent_job_id=parent.job_id, reviews_job_id=child.job_id
    )
    child_lease = runtime.attempts.claim_job(child.job_id, worker_id="worker-a")
    assert child_lease is not None
    runtime.jobs.complete_job(
        child.job_id, JobPayload(summary="child result", current_state="complete")
    )

    # The parent cannot take the return while the linked review is still living.
    before_early = _effect_snapshot(runtime)
    with pytest.raises(StateConflict, match="child job\\(s\\) are living"):
        runtime.attempts.claim_job(parent.job_id, worker_id="worker-a")
    assert _effect_snapshot(runtime) == before_early

    review_lease = runtime.attempts.claim_job(review.job_id, worker_id="worker-b")
    assert review_lease is not None
    runtime.jobs.complete_job(
        review.job_id,
        JobPayload(summary="independent review", current_state="complete", verdict="approve"),
    )
    parent_lease = runtime.attempts.claim_job(parent.job_id, worker_id="worker-a")
    assert parent_lease is not None
    consumed = runtime.jobs.complete_job(
        parent.job_id,
        JobPayload(
            summary="parent consumed reviewed return",
            current_state="complete",
            artifacts=[f"review:{review.job_id}", f"child:{child.job_id}"],
        ),
    )
    assert consumed.status is JobStatus.COMPLETED

    parent_view = _job_view(runtime, parent.job_id)
    observation = {
        "review": {**_job_view(runtime, review.job_id), "worker_id": "worker-b"},
        "reviewed_child": {**_job_view(runtime, child.job_id), "worker_id": "worker-a"},
        "parent": {
            **parent_view,
            "consumed_review_job_ids": [
                ref.split(":", 1)[1]
                for ref in (parent_view["result"] or {}).get("artifacts", [])
                if ref.startswith("review:")
            ],
        },
        "tree_statuses": {
            job_id: _job_view(runtime, job_id)["status"]
            for job_id in (parent.job_id, child.job_id, review.job_id)
        },
        "root_ids": _root_ids(runtime),
    }
    assert_h3_complete(observation)


# --------------------------------------------------------------------------
# H5 — conflicting source writer / permission -> fail-closed
# --------------------------------------------------------------------------


def _h5_refusal(runtime: Runtime, call, *, allowed, requested, error_contains):
    before = _effect_snapshot(runtime)
    with pytest.raises(Exception) as excinfo:
        call()
    after = _effect_snapshot(runtime)
    return {
        "refusal": {
            "allowed_write_paths": list(allowed),
            "requested_paths": list(requested),
            "error_type": type(excinfo.value).__name__,
            "message": str(excinfo.value),
            "error_contains": error_contains,
        },
        "typed_error_names": {"StateConflict", "AuthorityDenied", "SupervisorError"},
        "effects_before": before,
        "effects_after": after,
    }


def test_journey_h5_child_write_outside_parent_paths_is_refused_typed_without_effect(
    tmp_path: Path,
) -> None:
    """JOURNEY H5: a child Job declaring a path outside its parent's allowed_write_paths."""

    runtime = Runtime.at(tmp_path)
    worktree = str(tmp_path / "wt")
    writer = runtime.jobs.create_job(
        "Writer parent",
        worktree=worktree,
        requested_authorities=["READ", "WRITE_BRANCH"],
        allowed_write_paths=["control_plane/parser.py"],
    )
    observation = _h5_refusal(
        runtime,
        lambda: runtime.jobs.create_job(
            "Conflicting writer child",
            parent_job_id=writer.job_id,
            worktree=worktree,
            requested_authorities=["READ", "WRITE_BRANCH"],
            allowed_write_paths=["control_plane/parser.py", "control_plane/other.py"],
        ),
        allowed=writer.allowed_write_paths,
        requested=["control_plane/parser.py", "control_plane/other.py"],
        error_contains="allowed_write_paths",
    )
    assert observation["refusal"]["error_type"] == "StateConflict"
    assert_h5_complete(observation)


@pytest.mark.parametrize(
    "write_path",
    ["/absolute/outside.py", "../outside.py", "control_plane/../../outside.py"],
)
def test_journey_h5_escaping_write_path_is_refused_typed_without_effect(
    tmp_path: Path, write_path: str
) -> None:
    """JOURNEY H5: a root Job whose declared write path escapes its workspace."""

    runtime = Runtime.at(tmp_path)
    runtime.jobs.create_job("Unrelated existing job")
    observation = _h5_refusal(
        runtime,
        lambda: runtime.jobs.create_job(
            "Escaping writer",
            worktree=str(tmp_path / "wt"),
            requested_authorities=["READ", "WRITE_BRANCH"],
            allowed_write_paths=[write_path],
        ),
        allowed=[],
        requested=[write_path],
        error_contains="unsafe assigned write path",
    )
    assert_h5_complete(observation)


def test_journey_h5_widened_effective_grant_path_is_refused_without_effect(
    tmp_path: Path,
) -> None:
    """JOURNEY H5: an Attempt grant naming a path outside the Job's allowed_write_paths."""

    import dataclasses

    from control_plane import executive_supervisor
    from tests.test_executive_supervisor import _p2_grant_fixture

    job, attempt, decision = _p2_grant_fixture(tmp_path)
    runtime = Runtime.at(tmp_path)
    outside = "not-authorized.py"
    assert outside not in job.allowed_write_paths
    widened = dataclasses.replace(
        attempt,
        effective_grant={
            **attempt.effective_grant,
            "write_paths": [*attempt.effective_grant["write_paths"], outside],
        },
    )
    observation = _h5_refusal(
        runtime,
        lambda: executive_supervisor.validate_effective_grant(job, widened, decision),
        allowed=job.allowed_write_paths,
        requested=[*job.allowed_write_paths, outside],
        error_contains="malformed or widened",
    )
    assert observation["refusal"]["error_type"] == "SupervisorError"
    assert_h5_complete(observation)


# --------------------------------------------------------------------------
# H6 — rejected/failed worker -> lawful repair or escalation
# --------------------------------------------------------------------------


def test_journey_h6_rejected_child_yields_repair_consumed_by_parent_without_new_root(
    tmp_path: Path,
) -> None:
    """JOURNEY H6 (repair branch): independent reject -> repair child -> parent handoff."""

    runtime, cycle, dispatches, root, planner, work, work_seal = (
        _cycle_through_completed_work(
            tmp_path,
            intent_id="CEO-JOURNEY-H6-REPAIR",
            review_workers=["worker-b", "worker-b"],
        )
    )
    roots_before = _root_ids(runtime)
    assert cycle.run_once(root.job_id).action == "REVIEW_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    rejecting = dispatches[-1]
    plan_digest = str(runtime.jobs.get_job(work.attempt.job_id).plan_digest)
    reject_seal, _ = _complete_ohf_role(
        runtime,
        rejecting,
        _review_body(
            root_id=root.job_id,
            plan_attempt_id=planner.attempt.attempt_id,
            plan_digest=plan_digest,
            target_job_id=work.attempt.job_id,
            target_attempt_id=work.attempt.attempt_id,
            target_result_digest=work_seal["role_result_digest"],
            repair_round=0,
            verdict="reject",
        ),
        identity_seed=3601,
    )
    assert cycle.run_once(root.job_id).action == "REPAIR_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    repair = dispatches[-1]
    repair_seal, _ = _complete_ohf_role(
        runtime,
        repair,
        {
            "schema_version": "mastermind.repair_result/v1",
            "root_job_id": root.job_id,
            "plan_attempt_id": planner.attempt.attempt_id,
            "plan_digest": plan_digest,
            "plan_step_id": "step-1",
            "repair_round": 1,
            "supersedes_job_id": work.attempt.job_id,
            "rejected_review_job_id": rejecting.attempt.job_id,
            "rejected_review_result_digest": reject_seal["role_result_digest"],
            "artifacts": [],
            "evidence_digests": [],
        },
        identity_seed=3602,
    )
    assert cycle.run_once(root.job_id).action == "REVIEW_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    _complete_ohf_role(
        runtime,
        dispatches[-1],
        _review_body(
            root_id=root.job_id,
            plan_attempt_id=planner.attempt.attempt_id,
            plan_digest=plan_digest,
            target_job_id=repair.attempt.job_id,
            target_attempt_id=repair.attempt.attempt_id,
            target_result_digest=repair_seal["role_result_digest"],
            repair_round=1,
            verdict="approve",
        ),
        identity_seed=3603,
    )
    assert cycle.run_once(root.job_id).action == "HANDOFF_CREATED"
    handoff = runtime.jobs.get_cycle_handoff(root.job_id)

    # Re-submitting the same CEO intent must not mint a second root.
    resubmitted = submit_intent(runtime, _v2_intent(intent_id="CEO-JOURNEY-H6-REPAIR"))
    assert resubmitted["job_id"] == root.job_id

    work_view = _job_view(runtime, work.attempt.job_id)
    observation = {
        "failed_child": {**work_view, "rejected": True},
        "repair_child": _job_view(runtime, repair.attempt.job_id),
        "parent_consumed_job_id": handoff["revisions"][0]["current_job_id"],
        "root_ids_before": roots_before,
        "root_ids_after": _root_ids(runtime),
    }
    assert_h6_complete(observation)


def test_journey_h6_failed_child_yields_escalation_item_consumed_by_parent_without_new_root(
    tmp_path: Path,
) -> None:
    """JOURNEY H6 (escalation branch): FAILED work child -> inbox item + typed parent BLOCKED."""

    runtime = Runtime.at(tmp_path)
    _register_cycle_worker(runtime, "worker-a")
    receipt = submit_intent(runtime, _v2_intent(intent_id="CEO-JOURNEY-H6-FAILED"))
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    dispatches: list[Any] = []

    def dispatch(job_id: str, command_id: str):
        outcome = runtime.attempts.dispatch_cycle_job(
            job_id, command_id=command_id, worker_id="worker-a"
        )
        assert outcome is not None
        dispatches.append(outcome)
        return outcome

    cycle = CooCycle(runtime, dispatcher=dispatch)
    assert cycle.run_once(root.job_id).action == "PLANNER_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    planner = dispatches[-1]
    plan_body = {
        "schema_version": "mastermind.execution_plan/v1",
        "root_job_id": root.job_id,
        "plan_attempt_id": planner.attempt.attempt_id,
        "steps": [
            {
                "ordinal": 0,
                "step_id": "step-1",
                "objective": "Perform one bounded read-only task.",
                "business_impact": "routine",
                "review_required": True,
                "requested_authorities": ["READ"],
                "allowed_write_paths": [],
                "validation_ids": [],
                "attempt_limit": 1,
                "cost_class": "small",
            }
        ],
    }
    _complete_ohf_role(runtime, planner, plan_body, identity_seed=3611)
    assert cycle.run_once(root.job_id).action == "PLAN_ADMITTED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    work = dispatches[-1]
    roots_before = _root_ids(runtime)

    runtime.attempts.fail_attempt(
        work.attempt.attempt_id,
        fence_generation=work.attempt.fence_generation,
        lease_token=_lease_token(runtime, work.attempt.attempt_id),
        payload={"summary": "fixture worker failure", "errors": ["failed"]},
    )
    failed_view = _job_view(runtime, work.attempt.job_id)
    assert failed_view["status"] == "FAILED"

    blocked = cycle.run_once(root.job_id)
    events_after_block = runtime.events.list_events(job_id=root.job_id)
    replay = cycle.run_once(root.job_id)
    assert blocked.receipt["schema_version"] == "mastermind.coo_cycle_block/v1"

    items = _runtime_inbox_items(tmp_path)
    assert items[work.attempt.job_id]["kind"] == "job_failed"
    assert items[work.attempt.job_id]["target"] == "coo"
    resubmitted = submit_intent(runtime, _v2_intent(intent_id="CEO-JOURNEY-H6-FAILED"))
    assert resubmitted["job_id"] == root.job_id

    observation = {
        "failed_child": {**_job_view(runtime, work.attempt.job_id), "rejected": True},
        "escalation_item": {
            "job_id": items[work.attempt.job_id]["job_id"],
            "kind": items[work.attempt.job_id]["kind"],
        },
        "parent_consumption": {
            "action": blocked.action,
            "reason": blocked.receipt["reason"],
            "selected_job_id": blocked.receipt["selected_job_id"],
            "replay_identical": (
                replay.to_dict() == blocked.to_dict()
                and runtime.events.list_events(job_id=root.job_id) == events_after_block
            ),
        },
        "root_ids_before": roots_before,
        "root_ids_after": _root_ids(runtime),
    }
    assert_h6_complete(observation)


# --------------------------------------------------------------------------
# H7 — Chairman correction in flight
# --------------------------------------------------------------------------


def test_journey_h7_correction_on_running_child_terminalizes_typed_and_parent_consumes(
    tmp_path: Path,
) -> None:
    """JOURNEY H7: exact-attempt cancel on a RUNNING child -> CANCELLED -> parent consumes."""

    runtime = Runtime.at(tmp_path)
    _register_generic(runtime, "worker-a")
    _register_generic(runtime, "worker-b")
    parent = runtime.jobs.create_job("Parent awaiting child")
    child = runtime.jobs.create_job("Child to be corrected", parent_job_id=parent.job_id)
    lease = runtime.attempts.claim_job(child.job_id, worker_id="worker-a")
    assert lease is not None
    runtime.attempts.record_process(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="journey-h7-provider-session",
    )
    attempt = runtime.attempts.mark_running(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    status_at_correction = _job_view(runtime, child.job_id)["status"]

    # A stale correction (wrong fence) is refused and leaves no effect.
    before_stale = _effect_snapshot(runtime)
    with pytest.raises(StateConflict, match="exact cancellation Attempt or fence changed"):
        runtime.jobs.cancel_job(
            child.job_id,
            expected_attempt_id=attempt.attempt_id,
            expected_fence_generation=attempt.fence_generation + 1,
        )
    assert _effect_snapshot(runtime) == before_stale

    requested = runtime.jobs.cancel_job(
        child.job_id,
        expected_attempt_id=attempt.attempt_id,
        expected_fence_generation=attempt.fence_generation,
    )
    status_after_request = requested.status.value
    inbox_in_flight = _runtime_inbox_items(tmp_path)
    assert inbox_in_flight[child.job_id]["kind"] == "cancel_requested"

    # CANCEL_REQUESTED is not terminal: the parent cannot take the return yet.
    before_in_flight = _effect_snapshot(runtime)
    with pytest.raises(StateConflict) as in_flight:
        runtime.attempts.claim_job(parent.job_id, worker_id="worker-b")
    assert _effect_snapshot(runtime) == before_in_flight

    # The worker acknowledges on its own fenced lease: typed terminal state.
    terminal = runtime.attempts.acknowledge_cancel(
        attempt.attempt_id,
        fence_generation=attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    assert terminal.status is JobStatus.CANCELLED
    # Re-issuing the same correction after the terminal is a no-op.
    assert runtime.jobs.cancel_job(
        child.job_id,
        expected_attempt_id=attempt.attempt_id,
        expected_fence_generation=attempt.fence_generation,
    ).status is JobStatus.CANCELLED

    parent_lease = runtime.attempts.claim_job(parent.job_id, worker_id="worker-b")
    assert parent_lease is not None
    consumed = runtime.jobs.complete_job(
        parent.job_id,
        JobPayload(
            summary="parent consumed the in-flight correction",
            current_state="complete",
            artifacts=[f"cancelled:{child.job_id}"],
        ),
    )
    assert consumed.status is JobStatus.COMPLETED

    parent_view = _job_view(runtime, parent.job_id)
    observation = {
        "status_at_correction": status_at_correction,
        "status_after_request": status_after_request,
        "corrected_child": _job_view(runtime, child.job_id),
        "parent_refusal_while_in_flight": str(in_flight.value),
        "parent": {
            **parent_view,
            "consumed_correction_job_ids": [
                ref.split(":", 1)[1]
                for ref in (parent_view["result"] or {}).get("artifacts", [])
                if ref.startswith("cancelled:")
            ],
        },
        "root_ids": _root_ids(runtime),
    }
    assert_h7_complete(observation)


def test_journey_completion_tests_match_the_capability_ledger() -> None:
    """The quoted completion tests stay byte-identical to the ledger rows."""

    ledger = (
        Path(__file__).resolve().parents[1]
        / "research"
        / "EXECUTIVE_ECOSYSTEM_COMPLETION_CAPABILITY_LEDGER_2026-10-17.md"
    )
    if not ledger.exists():
        pytest.skip("capability ledger not materialized in this checkout")
    rows = {
        line.split("|")[1].strip(): line.split("|")[5].strip()
        for line in ledger.read_text(encoding="utf-8").splitlines()
        if line.startswith("| H") and line.count("|") >= 6
    }
    for journey, completion_test in JOURNEY_COMPLETION_TESTS.items():
        assert rows[journey] == completion_test, journey
    assert canonical_digest(JOURNEY_COMPLETION_TESTS)  # stable, JSON-canonical
