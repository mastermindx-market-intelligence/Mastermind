"""Offline harness for Executive Ecosystem Completion journeys H3, H5, H6 and H7.

Each journey is split into two halves:

* a **driver** that runs the journey in-process against a synthetic
  ``Runtime.at(tmp_path, clock=<fixed>)`` control plane (no host, daemon,
  network, credential or Keychain), and
* a **completion predicate** (``assert_h*``) that checks the ledger's
  completion test against a plain-data observation.

The predicates read only typed states, ids, event ids and counts, never a
``Runtime`` object, so a later host-backed adapter can build the same
observation from the armed host's supported read API and reuse the predicate
unchanged.  The completion tests are quoted verbatim from
``research/EXECUTIVE_ECOSYSTEM_COMPLETION_CAPABILITY_LEDGER_2026-10-17.md``
(rows H3, H5, H6, H7) in ``JOURNEY_COMPLETION_TESTS``.

What is proven, and what is not
-------------------------------
Every observation field is read from runtime state (jobs, attempts, events,
handoff, inbox) *except* where an observation carries
``consumption_attested_by_fixture=True``.  In that case the parent's
"consumption" is only a fixture-written artifact reference; the predicate
asserts the runtime-proven part only (the parent is refused while the linked
child is living, and completes after it, in event order) and does not read the
fixture-written reference.  ``JOURNEY_PROOF_NOTES`` states the split per
journey:

* H3 -- COO-cycle test is the literal proof (handoff names the review).  The
  operator-path test proves gating, independence and ordering; the parent
  naming the review is fixture-attested.
* H5 -- declaration-time refusal, grant-time refusal and a touch-time
  rejection are all proven in-process.  Declaration/grant time: the Job is
  refused with a typed error and leaves no effect.  Touch time: a worker (the
  offline fake-Codex fixture of ``tests/test_executive_codex_worker.py``) that
  writes outside the Job's ``allowed_write_paths`` is rejected by the worker-side
  ``allowed_artifact_paths`` check (``control_plane/codex_worker.py:5205-5217``)
  with a typed ``INVALID_RESULT``; the allowlist is fed from the Job grant by
  ``Supervisor._launch_spec`` (``control_plane/executive_supervisor.py:2159-2163``)
  and the runtime Job terminalizes FAILED.  **At touch time "no effect" means the
  RESULT is rejected, not that nothing happened:** the offending bytes already
  exist in the workspace, so the ledger's literal "and no effect" is NOT met by
  that check (it is met only for the declaration/grant-time refusals).
* H6 -- the rejected flag is derived from the rejecting review's sealed verdict
  and the repair child's provenance.  The FAILED branch proves a typed BLOCKED
  ``child_terminal_adverse`` plus a surfaced inbox ``job_failed`` escalation
  item; it does not mint a repair or have a consumer act on the item.
* H7 -- cancellation path only.  Lease-expiry/LOST terminalization and the
  DECISION_REQUEST Sol/Slack carrier are not covered; the parent naming the
  correction is fixture-attested.

These tests extend, not duplicate, the existing unit coverage:
``tests/test_executive_os_phase1fb.py`` (shrink-only paths, independent
review), ``tests/test_executive_os_phase1fc.py`` (COO cycle review/repair/
aggregation, incl. ``:2946-3161`` which the H3-cycle and H6-repair drivers
here share a setup with) and ``tests/test_executive_inbox_phase1fb.py`` (inbox
kinds).  What they add is the journey shape as plain-data observations: runtime-
sourced worker ids and event ordering, refusals proven effect-free, and no
duplicate root.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from control_plane import codex_worker as cw
from control_plane.ceo_intent import submit_intent
from control_plane.executive_authority import AuthorityDenied
from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_inbox import build_inbox
from control_plane.executive_orchestration_result import canonical_digest
from control_plane.executive_runtime import (
    JobPayload,
    JobStatus,
    Runtime,
    StateConflict,
)
from control_plane.executive_supervisor import ExecutiveSupervisor
from tests.test_executive_codex_worker import _fake_binary, _schema, _workspace
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


JOURNEY_PROOF_NOTES = {
    "H3": (
        "Runtime-proven: COO-cycle handoff names the independent review Job "
        "(qualifying_review_job_id) and the root completes after it; operator "
        "path proves gating (parent refused while the linked review is living, "
        "no effect), INDEPENDENT review stamp, worker ids from attempts rows "
        "and event ordering. Fixture-attested: operator-path parent naming the "
        "review (artifacts reference)."
    ),
    "H5": (
        "Declaration-time refusal + touch-time rejection proven in-process. "
        "Declaration/grant time: escaping/absolute path declarations "
        "(non-orchestration branch; StateConflict chained from AuthorityDenied) and a child widening its parent's "
        "allowed_write_paths (StateConflict) are refused with no durable "
        "effect. Touch time: Job allowed_write_paths -> real "
        "Supervisor._launch_spec allowed_artifact_paths -> offline fake-Codex "
        "write outside the allowlist -> typed INVALID_RESULT "
        "(codex_worker.py:5205-5217) -> runtime Job FAILED. At touch time 'no "
        "effect' means the RESULT is rejected (INVALID_RESULT), NOT that the "
        "bytes are absent: the written file remains in the workspace, so the "
        "ledger's literal 'and no effect' is not met by that check. Fixture "
        "substitutions: the fake binary's prompt and its hard-coded result "
        "identity (run-1/job-1/codex-01); the INVALID_RESULT -> FAILED mapping "
        "is applied by this test via fail_attempt (the supervisor's own "
        "mapping is unit-proven at tests/test_executive_supervisor.py:1190-1255)."
    ),
    "H6": (
        "Runtime-proven: rejected flag from the rejecting review's sealed "
        "verdict plus the repair child's provenance source id; repair child "
        "bound into the handoff; FAILED branch yields a typed BLOCKED "
        "child_terminal_adverse and a surfaced inbox job_failed item. Not "
        "proven: a consumer acting on the escalation item, or a repair for a "
        "FAILED (non-rejected) child."
    ),
    "H7": (
        "Cancellation path only. Runtime-proven: exact-fence cancel, "
        "CANCEL_REQUESTED -> CANCELLED, parent gated while in flight and "
        "completing after the child's terminal event. Fixture-attested: "
        "parent naming the correction. Not covered: lease-expiry/LOST and the "
        "DECISION_REQUEST Sol/Slack carrier."
    ),
}

_TERMINAL = {"COMPLETED", "CANCELLED", "FAILED", "LOST", "RATE_LIMITED"}
_TERMINAL_EVENTS = {"JOB_COMPLETED", "JOB_CANCELLED", "JOB_FAILED"}
_NOW = "2026-11-02T12:00:00+00:00"
_FIXED_NOW = datetime(2026, 11, 2, 12, 0, 0, tzinfo=timezone.utc)
_SAFE_PATH = "control_plane/parser.py"


def _clock() -> datetime:
    return _FIXED_NOW


def _runtime(tmp_path: Path) -> Runtime:
    return Runtime.at(tmp_path, clock=_clock)


@pytest.fixture(autouse=True)
def _fixed_runtime_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give the phase1fc helpers (which call ``Runtime.at(tmp_path)``) the same fixed clock."""

    original = Runtime.at.__func__

    def at(cls, root=None, **kwargs):
        kwargs.setdefault("clock", _clock)
        return original(cls, root, **kwargs)

    monkeypatch.setattr(Runtime, "at", classmethod(at))


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


def _attempt_rows(runtime: Runtime, job_id: str) -> list[dict[str, Any]]:
    with runtime.store.read() as connection:
        rows = connection.execute(
            "SELECT attempt_id,worker_id,status FROM attempts "
            "WHERE job_id=? ORDER BY attempt_number",
            (job_id,),
        ).fetchall()
    return [
        {"attempt_id": row[0], "worker_id": row[1], "status": row[2]} for row in rows
    ]


def _role_verdict(result: dict[str, Any] | None) -> str | None:
    """The sealed verdict: the role-result envelope, else a plain payload verdict."""

    result = result or {}
    envelope = (result.get("result_envelope") or {}).get("role_result") or {}
    return envelope.get("verdict") or result.get("verdict")


def _job_view(runtime: Runtime, job_id: str) -> dict[str, Any]:
    job = runtime.jobs.get_job(job_id)
    assert job is not None
    with runtime.store.read() as connection:
        cancel_at = connection.execute(
            "SELECT cancel_requested_at_ms FROM jobs WHERE job_id=?", (job_id,)
        ).fetchone()[0]
    events = runtime.events.list_events(job_id=job_id)
    completed = [event for event in events if event.event_type == "JOB_COMPLETED"]
    terminal_ids = [
        event.event_id for event in events if event.event_type in _TERMINAL_EVENTS
    ]
    attempts = _attempt_rows(runtime, job_id)
    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "parent_job_id": job.parent_job_id,
        "root_job_id": job.root_job_id,
        "reviews_job_id": job.reviews_job_id,
        "review_required": job.review_required,
        "orchestration_role": job.orchestration_role,
        "provenance_source_id": (job.orchestration_provenance or {}).get("source_id"),
        "supersedes_job_id": job.supersedes_job_id,
        "repair_round": job.repair_round,
        "escalation_target": job.escalation_target,
        "cancel_requested_at_ms": cancel_at,
        "result": job.result,
        "verdict": _role_verdict(job.result),
        # Runtime-stamped on JOB_COMPLETED of a review Job: INDEPENDENT or VOID.
        "completion_review_status": (
            (completed[-1].payload.get("review") or {}).get("status")
            if completed
            else None
        ),
        "attempts": attempts,
        "worker_ids": [row["worker_id"] for row in attempts],
        "terminal_event_id": max(terminal_ids) if terminal_ids else None,
        "event_types": [event.event_type for event in events],
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
# Completion predicates: ledger completion tests over plain data.
# --------------------------------------------------------------------------


def assert_h3_complete(observation: dict[str, Any]) -> None:
    """H3: a review Job linked by reviews_job_id completes and the parent consumes it.

    Runtime-proven: link, independent completion, worker separation (attempts
    rows) and parent-after-review event order.  With
    ``consumption_attested_by_fixture`` the parent naming the review is a
    fixture-written artifact reference and is NOT read; the runtime-proven
    substitute is that the parent was refused while the review was living.
    """

    review = observation["review"]
    reviewed = observation["reviewed_child"]
    parent = observation["parent"]
    # "a review Job linked by reviews_job_id"
    assert review["reviews_job_id"] == reviewed["job_id"]
    assert reviewed["review_required"] is True
    assert review["parent_job_id"] == reviewed["parent_job_id"] == parent["job_id"]
    # "... completes" (independently: a self-review is VOID, not a completion)
    assert review["status"] == "COMPLETED"
    assert review["completion_review_status"] == "INDEPENDENT"
    assert review["worker_ids"] and reviewed["worker_ids"]
    assert set(review["worker_ids"]).isdisjoint(reviewed["worker_ids"])
    # "... and the parent consumes it": the parent completes strictly after the
    # review (and the reviewed child) and nothing in the tree is left living.
    assert parent["status"] == "COMPLETED"
    assert (
        parent["terminal_event_id"]
        > review["terminal_event_id"]
        > reviewed["terminal_event_id"]
    )
    if observation["consumption_attested_by_fixture"]:
        refusal = observation["parent_refusal_while_review_living"]
        assert "child job(s) are living" in refusal and review["job_id"] in refusal
    else:
        assert review["job_id"] in parent["consumed_review_job_ids"]
    assert all(status in _TERMINAL for status in observation["tree_statuses"].values())
    assert observation["root_ids"] == [parent["root_job_id"]]


def assert_h5_declaration_and_grant_time_fail_closed(
    observation: dict[str, Any],
) -> None:
    """H5 (declaration / grant time): an out-of-bounds write path is refused, typed, no effect.

    The refusal's type is pinned where it is raised (``pytest.raises`` on the
    ``_h5_refusal`` call); here only the plain-data parts are checked.  Here "no
    effect" is literal: the durable store is byte-for-byte unchanged.
    """

    probe = observation["probe_precondition"]
    refusal = observation["refusal"]
    assert probe["allowed"], "the probe needs a real allowed set"
    assert probe["requested"], "the probe must request a write path"
    assert not set(probe["requested"]) <= set(probe["allowed"])
    # "refused with a typed error" -- the specific type is pinned at the call site
    assert refusal["error_contains"] in refusal["message"]
    # "and no effect"
    assert observation["effects_after"] == observation["effects_before"]


def assert_h5_touch_time_rejected(observation: dict[str, Any]) -> None:
    """H5 (touch time): a write outside ``allowed_write_paths`` is rejected, typed.

    "No effect" is NOT met literally at touch time: the check rejects the RESULT
    (``INVALID_RESULT``) after the bytes already exist in the workspace.  This
    predicate therefore asserts the rejection and asserts, explicitly, that the
    bytes remain.
    """

    job_allowed = observation["job_allowed_write_paths"]
    assert job_allowed, "the Job needs a real write allowlist"
    # the worker-side allowlist is fed from the Job grant by the real supervisor
    assert observation["spec_allowed_artifact_paths"] == job_allowed
    written = observation["workspace_paths_written"]
    assert written and not set(written) <= set(job_allowed)
    # "refused with a typed error"
    adapter = observation["adapter_result"]
    assert adapter["status"] == "INVALID_RESULT"
    assert "unauthorized path(s)" in adapter["error"]
    assert all(path in adapter["error"] for path in written)
    # the runtime Job terminalizes with a typed state: FAILED, never COMPLETED
    before, after = observation["job_before"], observation["job_after"]
    assert before["status"] == "RUNNING"
    assert after["status"] == "FAILED"
    assert [row["status"] for row in after["attempts"]] == ["FAILED"]
    assert after["event_types"][-1] == "JOB_FAILED"
    assert "JOB_COMPLETED" not in after["event_types"]
    # ... and the ledger's literal "and no effect" is NOT met at touch time
    assert observation["bytes_remain_in_workspace"] is True


def assert_h6_complete(observation: dict[str, Any]) -> None:
    """H6: failed child yields a repair child or a surfaced escalation item; no duplicate root.

    Repair branch: the child is rejected by an independent review (runtime
    verdict) and the repair child's provenance names that review.  Escalation
    branch: the child is FAILED, the COO inbox surfaces a ``job_failed`` item
    and the parent cycle returns a typed BLOCKED ``child_terminal_adverse``.
    That is "escalation surfaced + typed block", not a consumer acting on it.
    """

    failed = observation["failed_child"]
    repair = observation.get("repair_child")
    escalation = observation.get("escalation_item")
    assert (repair is None) != (escalation is None), "exactly one lawful outcome"
    if repair is not None:
        rejecting = observation["rejecting_review"]
        assert failed["status"] == "COMPLETED"
        assert rejecting["reviews_job_id"] == failed["job_id"]
        assert rejecting["status"] == "COMPLETED"
        assert rejecting["verdict"] == "reject"
        assert repair["provenance_source_id"] == rejecting["job_id"]
        assert repair["supersedes_job_id"] == failed["job_id"]
        assert repair["parent_job_id"] == failed["parent_job_id"]
        assert repair["repair_round"] == (failed["repair_round"] or 0) + 1
        # consumed by the parent: the parent's handoff/aggregation is bound to
        # the repair, not to the rejected child.
        assert observation["parent_consumed_job_id"] == repair["job_id"]
    else:
        assert failed["status"] == "FAILED"
        assert escalation["job_id"] == failed["job_id"]
        assert escalation["kind"] == "job_failed"
        assert escalation["target"] == "coo"
        assert escalation["in_attention"] is True
        # the parent's next cycle reads the failure as a typed, replay-stable
        # block naming the failed child instead of silently requeueing it or
        # minting a replacement root.
        block = observation["parent_block"]
        assert block["action"] == "BLOCKED"
        assert block["reason"] == "child_terminal_adverse"
        assert block["selected_job_id"] == failed["job_id"]
        assert block["replay_identical"] is True
        assert "JOB_REQUEUED" not in failed["event_types"]
    # "no duplicate root"
    assert observation["root_ids_after"] == observation["root_ids_before"]
    assert len(observation["root_ids_after"]) == 1


def assert_h7_complete(observation: dict[str, Any]) -> None:
    """H7: a correction on a RUNNING Job terminalizes it typed; the parent completes after it.

    The parent naming the correction is fixture-attested and not read here.
    """

    target = observation["corrected_child"]
    assert observation["status_at_correction"] == "RUNNING"
    # "terminalizes it with a typed state"
    assert observation["status_after_request"] == "CANCEL_REQUESTED"
    assert target["cancel_requested_at_ms"] is not None
    assert target["status"] == "CANCELLED"
    assert target["event_types"][-2:] == ["JOB_CANCEL_REQUESTED", "JOB_CANCELLED"]
    assert [row["status"] for row in target["attempts"]] == ["CANCELLED"]
    # the parent cannot proceed while the correction is still in flight ...
    refusal = observation["parent_refusal_while_in_flight"]
    assert "child job(s) are living" in refusal and target["job_id"] in refusal
    # ... and completes after the child's typed terminal event.
    parent = observation["parent"]
    assert observation["consumption_attested_by_fixture"] is True
    assert parent["status"] == "COMPLETED"
    assert parent["terminal_event_id"] > target["terminal_event_id"]
    assert observation["root_ids"] == [parent["job_id"]]


# --------------------------------------------------------------------------
# Shared COO-cycle driver (H3 cycle path and H6 repair branch).
# --------------------------------------------------------------------------


def _drive_cycle_to_handoff(
    tmp_path: Path, *, intent_id: str, reject_first: bool
) -> dict[str, Any]:
    """work -> review [-> repair -> review] -> HANDOFF_CREATED, all through the COO cycle."""

    runtime, cycle, dispatches, root, planner, work, work_seal = (
        _cycle_through_completed_work(
            tmp_path,
            intent_id=intent_id,
            review_workers=["worker-b", "worker-b"] if reject_first else ["worker-b"],
        )
    )
    roots_before = _root_ids(runtime)
    plan_digest = str(runtime.jobs.get_job(work.attempt.job_id).plan_digest)

    def review_of(target, seal, *, repair_round, verdict, seed):
        assert cycle.run_once(root.job_id).action == "REVIEW_CREATED"
        assert cycle.run_once(root.job_id).action == "DISPATCHED"
        dispatch = dispatches[-1]
        review_seal, _ = _complete_ohf_role(
            runtime,
            dispatch,
            _review_body(
                root_id=root.job_id,
                plan_attempt_id=planner.attempt.attempt_id,
                plan_digest=plan_digest,
                target_job_id=target.attempt.job_id,
                target_attempt_id=target.attempt.attempt_id,
                target_result_digest=seal["role_result_digest"],
                repair_round=repair_round,
                verdict=verdict,
            ),
            identity_seed=seed,
        )
        return dispatch, review_seal

    first_review, first_seal = review_of(
        work,
        work_seal,
        repair_round=0,
        verdict="reject" if reject_first else "approve",
        seed=3601 if reject_first else 3301,
    )
    repair = None
    final_review, final_seal = first_review, first_seal
    if reject_first:
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
                "rejected_review_job_id": first_review.attempt.job_id,
                "rejected_review_result_digest": first_seal["role_result_digest"],
                "artifacts": [],
                "evidence_digests": [],
            },
            identity_seed=3602,
        )
        final_review, final_seal = review_of(
            repair, repair_seal, repair_round=1, verdict="approve", seed=3603
        )
    assert cycle.run_once(root.job_id).action == "HANDOFF_CREATED"
    return {
        "runtime": runtime,
        "cycle": cycle,
        "dispatches": dispatches,
        "root": root,
        "work": work,
        "first_review": first_review,
        "repair": repair,
        "final_review": final_review,
        "final_seal": final_seal,
        "handoff": runtime.jobs.get_cycle_handoff(root.job_id),
        "roots_before": roots_before,
    }


# --------------------------------------------------------------------------
# H3 — operator -> child -> original-parent reviewed return
# --------------------------------------------------------------------------


def test_journey_h3_cycle_review_linked_by_reviews_job_id_is_consumed_by_parent(
    tmp_path: Path,
) -> None:
    """JOURNEY H3 (COO cycle path, the literal proof): review -> handoff -> parent aggregation."""

    drive = _drive_cycle_to_handoff(
        tmp_path, intent_id="CEO-JOURNEY-H3", reject_first=False
    )
    runtime, cycle, root = drive["runtime"], drive["cycle"], drive["root"]
    handoff = drive["handoff"]
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    aggregation_dispatch = drive["dispatches"][-1]
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

    review_job_id = drive["final_review"].attempt.job_id
    work_job_id = drive["work"].attempt.job_id
    review_view = _job_view(runtime, review_job_id)
    work_view = _job_view(runtime, work_job_id)
    root_view = _job_view(runtime, root.job_id)
    tree = [job for job in runtime.jobs.list_jobs() if job.root_job_id == root.job_id]
    # The consumption link comes from the runtime-built handoff, bound to this
    # exact review result digest.
    consumed = [
        item["qualifying_review_job_id"]
        for item in handoff["revisions"]
        if item["qualifying_review_result_digest"]
        == drive["final_seal"]["role_result_digest"]
    ]
    observation = {
        "review": review_view,
        "reviewed_child": work_view,
        "parent": {**root_view, "consumed_review_job_ids": consumed},
        "consumption_attested_by_fixture": False,
        "tree_statuses": {job.job_id: job.status.value for job in tree},
        "root_ids": _root_ids(runtime),
    }
    assert review_view["parent_job_id"] == root.job_id
    assert review_view["orchestration_role"] == "review"
    assert_h3_complete(observation)


def test_journey_h3_generic_review_gates_the_parent_until_it_completes_independently(
    tmp_path: Path,
) -> None:
    """JOURNEY H3 (operator path): parent refused while the linked review is living.

    Fixture-attested: the parent's completion names the review in an
    ``artifacts`` reference.  Runtime-proven: the refusal (effect-free), the
    INDEPENDENT stamp, worker ids from attempts rows and event ordering.
    """

    runtime = _runtime(tmp_path)
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
    with pytest.raises(StateConflict, match="child job\\(s\\) are living") as early:
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

    observation = {
        "review": _job_view(runtime, review.job_id),
        "reviewed_child": _job_view(runtime, child.job_id),
        "parent": _job_view(runtime, parent.job_id),
        "consumption_attested_by_fixture": True,
        "parent_refusal_while_review_living": str(early.value),
        "tree_statuses": {
            job_id: _job_view(runtime, job_id)["status"]
            for job_id in (parent.job_id, child.job_id, review.job_id)
        },
        "root_ids": _root_ids(runtime),
    }
    assert_h3_complete(observation)


# --------------------------------------------------------------------------
# H5 — conflicting source writer / permission -> fail-closed
#      (declaration, grant time and touch time)
# --------------------------------------------------------------------------


def _h5_refusal(
    runtime: Runtime,
    call,
    *,
    expected_error,
    allowed,
    requested,
    error_contains,
    expected_cause=None,
):
    """Run ``call`` and pin its refusal to ``expected_error`` (an isinstance check).

    ``expected_cause`` additionally pins the chained ``__cause__`` where the
    runtime wraps the originating refusal (``raise StateConflict(...) from exc``).
    """

    before = _effect_snapshot(runtime)
    with pytest.raises(expected_error) as excinfo:
        call()
    assert isinstance(excinfo.value, expected_error)
    if expected_cause is not None:
        assert isinstance(excinfo.value.__cause__, expected_cause)
    after = _effect_snapshot(runtime)
    return {
        # Declared by the probe before the call; NOT observed runtime state.
        "probe_precondition": {"allowed": list(allowed), "requested": list(requested)},
        "refusal": {
            "message": str(excinfo.value),
            "error_contains": error_contains,
        },
        "effects_before": before,
        "effects_after": after,
    }


def test_journey_h5_child_write_outside_parent_paths_is_refused_typed_without_effect(
    tmp_path: Path,
) -> None:
    """JOURNEY H5 (grant-time): a child Job declaring a path outside its parent's allowed_write_paths."""

    runtime = _runtime(tmp_path)
    worktree = str(tmp_path / "wt")
    writer = runtime.jobs.create_job(
        "Writer parent",
        worktree=worktree,
        requested_authorities=["READ", "WRITE_BRANCH"],
        allowed_write_paths=[_SAFE_PATH],
    )
    observation = _h5_refusal(
        runtime,
        lambda: runtime.jobs.create_job(
            "Conflicting writer child",
            parent_job_id=writer.job_id,
            worktree=worktree,
            requested_authorities=["READ", "WRITE_BRANCH"],
            allowed_write_paths=[_SAFE_PATH, "control_plane/other.py"],
        ),
        expected_error=StateConflict,
        allowed=writer.allowed_write_paths,
        requested=[_SAFE_PATH, "control_plane/other.py"],
        error_contains="allowed_write_paths",
    )
    assert_h5_declaration_and_grant_time_fail_closed(observation)


@pytest.mark.parametrize(
    "write_path",
    ["/absolute/outside.py", "../outside.py", "control_plane/../../outside.py"],
)
def test_journey_h5_escaping_write_path_is_refused_typed_without_effect(
    tmp_path: Path, write_path: str
) -> None:
    """JOURNEY H5 (declaration-time): a Job declaring a write path that escapes its workspace.

    ``control_plane/executive_authority.py:157`` raises ``AuthorityDenied``; the
    runtime surfaces it as ``StateConflict`` chained ``from`` it, so both are
    pinned.  The allowed/requested pair is a probe precondition.
    """

    runtime = _runtime(tmp_path)
    runtime.jobs.create_job("Unrelated existing job")
    observation = _h5_refusal(
        runtime,
        lambda: runtime.jobs.create_job(
            "Escaping writer",
            worktree=str(tmp_path / "wt"),
            requested_authorities=["READ", "WRITE_BRANCH"],
            allowed_write_paths=[_SAFE_PATH, write_path],
        ),
        # the runtime wraps the authority refusal: StateConflict from AuthorityDenied
        # (executive_runtime.py:16173 <- executive_authority.py:157)
        expected_error=StateConflict,
        expected_cause=AuthorityDenied,
        allowed=[_SAFE_PATH],
        requested=[_SAFE_PATH, write_path],
        error_contains="unsafe assigned write path",
    )
    assert_h5_declaration_and_grant_time_fail_closed(observation)


def test_journey_h5_worker_write_outside_job_allowlist_is_rejected_invalid_result_at_touch_time(
    tmp_path: Path,
) -> None:
    """JOURNEY H5 (touch time): Job grant -> supervisor spec -> offline fake-Codex write -> INVALID_RESULT -> Job FAILED.

    Composes the pieces that are otherwise only unit-proven apart:
    ``Supervisor._launch_spec`` copies the Job's ``allowed_write_paths`` into
    ``allowed_artifact_paths`` (executive_supervisor.py:2159-2163); the worker-side
    check (codex_worker.py:5205-5217) rejects a write outside it with
    ``INVALID_RESULT`` (as in test_executive_codex_worker.py:1419-1433).
    Fixture substitutions: the fake binary's prompt and its hard-coded result
    identity.  The INVALID_RESULT -> FAILED mapping is applied here with
    ``fail_attempt``; the supervisor's own mapping is unit-proven at
    test_executive_supervisor.py:1190-1255.

    "No effect" is NOT achieved at touch time: the RESULT is rejected but the
    written file remains in the workspace; the observation asserts exactly that.
    """

    runtime = _runtime(tmp_path)
    runtime.workers.register_worker(
        "codex-01",
        provider="codex",
        account_label="journey-h5",
        worker_type="codex-cli",
        capabilities=["research", "code", "tests"],
        quota_classes={
            "codex-native": {
                "capabilities": ["research", "code", "tests"],
                "model": "gpt-5.6-sol",
                "effort": "xhigh",
                "cost_class": "standard",
            }
        },
    )
    workspace, head = _workspace(tmp_path / "workspaces")
    job = runtime.jobs.create_job(
        "Write only artifact.txt",
        worktree=str(workspace.resolve()),
        requested_authorities=["READ", "WRITE_BRANCH", "RUN_TESTS"],
        allowed_write_paths=["artifact.txt"],
        validation_commands=[["/usr/bin/true"]],
        constraints={
            "provider": "codex",
            "model": "gpt-5.6-sol",
            "effort": "xhigh",
            "cost_class": "standard",
            "base_sha": head,
            "eligible_quota_classes": ["codex-native"],
            "required_capabilities": ["research", "code", "tests"],
        },
        attempt_limit=1,
    )
    lease = runtime.attempts.claim_job(job.job_id, worker_id="codex-01")
    assert lease is not None
    attempt = lease.attempt
    runtime.attempts.record_process(
        attempt.attempt_id,
        fence_generation=attempt.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="journey-h5-provider-session",
    )
    attempt = runtime.attempts.mark_running(
        attempt.attempt_id,
        fence_generation=attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    job_before = _job_view(runtime, job.job_id)
    store_before = _effect_snapshot(runtime)

    codex_home = tmp_path / "codex-home"
    codex_home.mkdir(mode=0o700)
    (codex_home / "auth.json").write_text("{}", encoding="utf-8")
    (codex_home / "auth.json").chmod(0o600)
    binary, attestation = _fake_binary(tmp_path)
    adapter = cw.CodexWorkerAdapter(
        binary,
        codex_home=codex_home,
        binary_attestation=attestation,
        allowed_versions=frozenset({"test-0"}),
        required_team_identifier=None,
    )
    supervisor = ExecutiveSupervisor(
        runtime,
        adapter,
        runs_root=tmp_path / "runs",
        isolation_roots=(tmp_path / "workspaces", tmp_path / "runs"),
    )
    run_dir = supervisor._run_dir(attempt.attempt_id)
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(mode=0o700)
    (run_dir / "input").mkdir(mode=0o700)
    schema_path = run_dir / "input" / "worker-result.schema.json"
    schema_path.write_text(json.dumps(_schema()), encoding="utf-8")
    schema_path.chmod(0o600)
    persisted_job = runtime.jobs.get_job(job.job_id)
    assert persisted_job is not None
    spec = supervisor._launch_spec(persisted_job, lease, schema_path)
    spec_allowed = list(spec.allowed_artifact_paths)
    # Fixture substitutions (see docstring): prompt selects the fake's
    # out-of-allowlist write; identity constants match the fake's fixed result.
    spec = dataclasses.replace(
        spec,
        prompt="unauthorized-write",
        run_id="run-1",
        job_id="job-1",
        worker_id="codex-01",
    )

    async def run_worker():
        ref = await adapter.start(spec)
        return await adapter.collect_result(ref)

    receipt = asyncio.run(run_worker())
    assert receipt.result.status is cw.WorkerRunStatus.INVALID_RESULT
    written = sorted(
        entry.name
        for entry in workspace.iterdir()
        if entry.name not in {".git", ".codex", ".gitignore", "README.md"}
    )
    bytes_remain = all((workspace / name).is_file() for name in written)

    # Apply the typed rejection to the runtime Job (what the supervisor does).
    failed = runtime.attempts.fail_attempt(
        attempt.attempt_id,
        fence_generation=attempt.fence_generation,
        lease_token=lease.lease_token,
        payload={
            "summary": "worker result rejected",
            "errors": [str(receipt.result.error)],
        },
    )
    assert failed.status is JobStatus.FAILED
    store_after = _effect_snapshot(runtime)
    # M1: the typed rejection is read back from the runtime's stored record
    stored_job = runtime.jobs.get_job(job.job_id)
    assert stored_job is not None
    stored_failure = json.dumps(stored_job.result, sort_keys=True)
    assert "unauthorized path(s): ignored.tmp" in stored_failure
    # M2: store-wide delta -- only this job RUNNING->FAILED, only this attempt, and
    # only this job's terminal events
    changed_jobs = [
        (b, a)
        for b, a in zip(store_before["jobs"], store_after["jobs"], strict=True)
        if b != a
    ]
    assert len(store_before["jobs"]) == len(store_after["jobs"])
    assert [(b[0], b[1], a[1]) for b, a in changed_jobs] == [
        (job.job_id, "RUNNING", "FAILED")
    ]
    changed_attempts = [
        (b, a)
        for b, a in zip(store_before["attempts"], store_after["attempts"], strict=True)
        if b != a
    ]
    assert len(store_before["attempts"]) == len(store_after["attempts"])
    assert [(b[0], b[1], a[1]) for b, a in changed_attempts] == [
        (attempt.attempt_id, "RUNNING", "FAILED")
    ]
    new_events = [
        event
        for event in runtime.events.list_events(job_id=job.job_id)
        if event.event_id > store_before["max_event_id"]
    ]
    assert new_events, "the terminal call must emit events"
    assert (
        store_after["event_count"] - store_before["event_count"] == len(new_events)
    ), "events were emitted for another job"
    assert [e.event_type for e in new_events][-1] == "JOB_FAILED"
    assert "JOB_COMPLETED" not in [e.event_type for e in new_events]

    observation = {
        "job_allowed_write_paths": list(persisted_job.allowed_write_paths),
        "spec_allowed_artifact_paths": spec_allowed,
        "workspace_paths_written": written,
        "adapter_result": {
            "status": receipt.result.status.value,
            "error": receipt.result.error or "",
        },
        "job_before": job_before,
        "job_after": _job_view(runtime, job.job_id),
        "bytes_remain_in_workspace": bytes_remain,
    }
    assert_h5_touch_time_rejected(observation)


# --------------------------------------------------------------------------
# H6 — rejected/failed worker -> lawful repair or escalation
# --------------------------------------------------------------------------


def test_journey_h6_rejected_child_yields_repair_consumed_by_parent_without_new_root(
    tmp_path: Path,
) -> None:
    """JOURNEY H6 (repair branch): independent reject -> repair child -> parent handoff."""

    drive = _drive_cycle_to_handoff(
        tmp_path, intent_id="CEO-JOURNEY-H6-REPAIR", reject_first=True
    )
    runtime, root = drive["runtime"], drive["root"]
    handoff = drive["handoff"]

    # Re-submitting the same CEO intent must not mint a second root.
    resubmitted = submit_intent(runtime, _v2_intent(intent_id="CEO-JOURNEY-H6-REPAIR"))
    assert resubmitted["job_id"] == root.job_id

    observation = {
        "failed_child": _job_view(runtime, drive["work"].attempt.job_id),
        "rejecting_review": _job_view(runtime, drive["first_review"].attempt.job_id),
        "repair_child": _job_view(runtime, drive["repair"].attempt.job_id),
        "parent_consumed_job_id": handoff["revisions"][0]["current_job_id"],
        "root_ids_before": drive["roots_before"],
        "root_ids_after": _root_ids(runtime),
    }
    assert_h6_complete(observation)


def test_journey_h6_failed_child_surfaces_escalation_item_and_parent_blocks_typed_without_new_root(
    tmp_path: Path,
) -> None:
    """JOURNEY H6 (escalation branch): FAILED work child -> inbox job_failed item + typed parent BLOCKED."""

    runtime = _runtime(tmp_path)
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

    failed_items = [
        item
        for item in _runtime_inbox_items(tmp_path).values()
        if item.get("kind") == "job_failed"
    ]
    assert len(failed_items) == 1
    item = failed_items[0]
    resubmitted = submit_intent(runtime, _v2_intent(intent_id="CEO-JOURNEY-H6-FAILED"))
    assert resubmitted["job_id"] == root.job_id

    observation = {
        "failed_child": failed_view,
        "escalation_item": {
            # every field is read from the surfaced inbox item itself
            "job_id": item["job_id"],
            "kind": item["kind"],
            "target": item["target"],
            "in_attention": True,
        },
        "parent_block": {
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
# H7 — Chairman correction in flight (cancellation path only)
# --------------------------------------------------------------------------


def test_journey_h7_correction_on_running_child_terminalizes_typed_and_parent_follows(
    tmp_path: Path,
) -> None:
    """JOURNEY H7 (cancellation path only): exact-attempt cancel on a RUNNING child -> CANCELLED -> parent.

    Not covered: lease-expiry/LOST terminalization and the DECISION_REQUEST
    Sol/Slack carrier.  Fixture-attested: the parent's completion names the
    correction in an ``artifacts`` reference; the runtime proves the gating and
    the parent-after-child event order.
    """

    runtime = _runtime(tmp_path)
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
            summary="parent proceeded after the in-flight correction",
            current_state="complete",
            artifacts=[f"cancelled:{child.job_id}"],  # fixture attestation only
        ),
    )
    assert consumed.status is JobStatus.COMPLETED

    observation = {
        "status_at_correction": status_at_correction,
        "status_after_request": status_after_request,
        "corrected_child": _job_view(runtime, child.job_id),
        "parent_refusal_while_in_flight": str(in_flight.value),
        "consumption_attested_by_fixture": True,
        "parent": _job_view(runtime, parent.job_id),
        "root_ids": _root_ids(runtime),
    }
    assert_h7_complete(observation)


def test_journey_completion_tests_match_the_capability_ledger() -> None:
    """The quoted completion tests stay byte-identical to the ledger rows (fails, never skips)."""

    ledger = (
        Path(__file__).resolve().parents[1]
        / "research"
        / "EXECUTIVE_ECOSYSTEM_COMPLETION_CAPABILITY_LEDGER_2026-10-17.md"
    )
    assert ledger.exists(), f"capability ledger missing from this checkout: {ledger}"
    rows = {
        line.split("|")[1].strip(): line.split("|")[5].strip()
        for line in ledger.read_text(encoding="utf-8").splitlines()
        if line.startswith("| H") and line.count("|") >= 6
    }
    for journey, completion_test in JOURNEY_COMPLETION_TESTS.items():
        assert rows[journey] == completion_test, journey
    assert set(JOURNEY_PROOF_NOTES) == set(JOURNEY_COMPLETION_TESTS)
    h5_note = JOURNEY_PROOF_NOTES["H5"]
    assert "BUILT_NOT_PROVEN" not in h5_note
    assert "INVALID_RESULT" in h5_note and "bytes" in h5_note
    assert "is not met" in h5_note
    assert canonical_digest(JOURNEY_COMPLETION_TESTS)  # stable, JSON-canonical
