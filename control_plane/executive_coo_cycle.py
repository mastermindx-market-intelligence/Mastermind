"""Deterministic, production-inert Phase 1F-C COO run-once bookkeeping.

The cycle owns no durable state and performs at most one top-level mutation.
Every write delegates to the existing Executive Runtime command boundaries.
It never polls, selects a parent, invokes a model, or contacts a provider.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Callable, Mapping
from typing import Any

from control_plane.executive_coo_policy import (
    CooCyclePolicy,
    CooCyclePolicyError,
    EXPECTED_POLICY_SHA256,
)
from control_plane.executive_runtime import (
    COO_CYCLE_BLOCK_REASONS,
    AttemptStatus,
    Job,
    JobStatus,
    OrchestrationDispatchOutcome,
    Runtime,
    StateConflict,
    _current_orchestration_tree_material,
    _current_orchestration_tree_material_for_dispatch,
    _review_attempt_is_independent,
    _strict_canonical_json_loads,
    _validated_aggregation_handoff,
    _validated_plan_admission,
    _validated_role_completion_material,
)

CYCLE_OUTCOME_SCHEMA = "mastermind.executive_coo_cycle_outcome/v1"
_ROLE_PRECEDENCE = {"plan": 0, "work": 1, "repair": 2, "review": 3, "aggregation": 4}
_RECOVERABLE = {JobStatus.RATE_LIMITED, JobStatus.FAILED, JobStatus.LOST}

Dispatch = Callable[[str, str], OrchestrationDispatchOutcome | None]


@dataclasses.dataclass(frozen=True)
class CooCycleOutcome:
    root_job_id: str
    action: str
    selected_job_id: str | None
    command_id: str | None
    receipt: dict[str, Any]
    schema_version: str = CYCLE_OUTCOME_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        value["outcome_digest"] = hashlib.sha256(encoded).hexdigest()
        return value


def _job_sort_key(job: Job, ordinals: Mapping[str, int]) -> tuple[int, int, int, str]:
    ordinal = -1 if job.plan_step_id is None else int(ordinals.get(job.plan_step_id, 1 << 30))
    return (
        _ROLE_PRECEDENCE.get(str(job.orchestration_role), 99),
        ordinal,
        int(job.repair_round or 0),
        job.job_id,
    )


def _classify_invalid(exc: Exception) -> str:
    text = str(exc).lower()
    if "policy" in text:
        return "invalid_policy"
    if "fan-out" in text or "fan out" in text:
        return "fan_out_exceeded"
    if "reserved child" in text or "child total" in text:
        return "children_total_exceeded"
    if "capacity" in text or "reservation exceeds" in text:
        return "plan_capacity_exceeded"
    if "depth" in text or "non-direct child" in text:
        return "depth_exceeded"
    if "validation" in text:
        return "validation_contract_invalid"
    if "grant" in text or "authority" in text:
        return "effective_grant_invalid"
    if "principal" in text or "placement" in text:
        return "principal_snapshot_invalid"
    if any(word in text for word in ("result", "seal", "terminal evidence", "envelope")):
        return "result_protocol_invalid"
    if "plan" in text and "lineage" not in text:
        return "invalid_plan"
    if "handoff" in text:
        return "aggregation_handoff_invalid"
    if "lineage" in text or "revision" in text or "unexpected child" in text:
        return "lineage_invalid"
    return "state_conflict"


class CooCycle:
    """Choose and commit the first eligible mutation for one explicit root."""

    def __init__(self, runtime: Runtime, *, dispatcher: Dispatch | None = None) -> None:
        self.runtime = runtime
        self.dispatcher = dispatcher or self._dispatch_unavailable

    @staticmethod
    def _dispatch_unavailable(
        job_id: str, command_id: str
    ) -> OrchestrationDispatchOutcome | None:
        """The inert CLI has no accepted supervisor execution boundary."""

        return None

    def _outcome(
        self,
        root: str,
        action: str,
        selected: str | None,
        command: str | None,
        receipt: Any,
    ) -> CooCycleOutcome:
        if hasattr(receipt, "to_dict"):
            receipt = receipt.to_dict()
        elif dataclasses.is_dataclass(receipt):
            receipt = dataclasses.asdict(receipt)
        elif not isinstance(receipt, dict):
            receipt = {"value": receipt}
        return CooCycleOutcome(root, action, selected, command, dict(receipt))

    def _dispatch_none_was_preclaim(self, before: Job) -> bool:
        """True only when a ``None`` dispatcher result left the Job untouched."""

        after = self.runtime.jobs.get_job(before.job_id)
        return bool(
            after is not None
            and after.status == before.status
            and after.attempt_count == before.attempt_count
            and after.current_attempt_id == before.current_attempt_id
        )

    def _block(
        self,
        root: str,
        selected: str,
        reason: str,
        *,
        evidence: dict[str, Any] | None = None,
    ) -> CooCycleOutcome:
        if reason not in COO_CYCLE_BLOCK_REASONS:
            reason = "state_conflict"
        command = f"coo-cycle:{root}:block:{reason}:{selected}"
        receipt = self.runtime.jobs.block_cycle(
            root,
            selected_job_id=selected,
            reason=reason,
            command_id=command,
            evidence=evidence,
            policy_sha=EXPECTED_POLICY_SHA256,
        )
        return self._outcome(root, "BLOCKED", selected, command, receipt)

    def run_once(self, parent_job_id: str) -> CooCycleOutcome:
        root_id = str(parent_job_id or "").strip()
        root = self.runtime.jobs.get_job(root_id)
        if root is None:
            raise StateConflict(f"root job {root_id!r} does not exist")
        try:
            policy = CooCyclePolicy.load()
        except CooCyclePolicyError as exc:
            return self._block(
                root_id,
                root_id,
                "invalid_policy",
                evidence={"error_type": type(exc).__name__},
            )

        existing_blocks = [
            event
            for event in self.runtime.events.list_events(job_id=root_id)
            if event.event_type == "COO_CYCLE_BLOCKED"
        ]
        if existing_blocks:
            event = existing_blocks[0]
            return self._outcome(
                root_id,
                "BLOCKED",
                str(event.payload.get("selected_job_id") or root_id),
                event.command_id,
                event.payload,
            )

        provenance = root.orchestration_provenance
        if (
            root.parent_job_id is not None
            or root.root_job_id != root.job_id
            or root.depth != 0
            or root.orchestration_role != "aggregation"
            or not isinstance(provenance, dict)
            or provenance.get("schema_version")
            != "mastermind.executive_orchestration_provenance/v1"
            or provenance.get("creator") != "ceo_intent"
            or provenance.get("role") != "aggregation"
            or provenance.get("job_id") != root.job_id
            or provenance.get("root_job_id") != root.job_id
            or provenance.get("parent_job_id") is not None
            or not provenance.get("source_id")
            or not provenance.get("source_digest")
        ):
            return self._block(root_id, root_id, "invalid_root")

        all_jobs = [
            job
            for job in self.runtime.jobs.list_jobs()
            if job.root_job_id == root_id
        ]
        children = [job for job in all_jobs if job.job_id != root_id]
        events = self.runtime.events.list_events(job_id=root_id)
        admission_events = [event for event in events if event.event_type == "COO_PLAN_ADMITTED"]
        handoff_events = [
            event for event in events if event.event_type == "COO_AGGREGATION_HANDOFF_READY"
        ]
        if len(admission_events) > 1 or len(handoff_events) > 1:
            return self._block(root_id, root_id, "lineage_invalid")

        admission: dict[str, Any] | None = None
        plan_body: dict[str, Any] | None = None
        current_by_step: dict[str, dict[str, Any]] = {}
        try:
            with self.runtime.store.read() as connection:
                root_row = connection.execute(
                    "SELECT * FROM jobs WHERE job_id=?", (root_id,)
                ).fetchone()
                assert root_row is not None
                if admission_events:
                    admission, plan_body = _validated_plan_admission(connection, root_row)
                    current = _current_orchestration_tree_material_for_dispatch(
                        connection, root_row, admission, plan_body
                    )
                    current_by_step = {
                        str(item["plan_step_id"]): item for item in current
                    }
                if handoff_events:
                    _validated_aggregation_handoff(connection, root_row)
        except (StateConflict, CooCyclePolicyError) as exc:
            return self._block(
                root_id,
                root_id,
                _classify_invalid(exc),
                evidence={"error_type": type(exc).__name__},
            )

        ordinals: dict[str, int] = {}
        if plan_body is not None:
            ordinals = {
                str(step["step_id"]): index
                for index, step in enumerate(plan_body["steps"])
            }

        # A pre-admission root may contain only the exact cycle-created planner.
        # Prove this before requeue or dispatch so a queued forged/corrupt child
        # can never cross the claim boundary.
        if not admission_events and children:
            if len(children) != 1:
                return self._block(root_id, root_id, "unexpected_pre_admission_child")
            planner = children[0]
            planner_provenance = planner.orchestration_provenance
            expected_create_command = f"coo-cycle:{root_id}:create-planner:0"
            if (
                planner.orchestration_role != "plan"
                or planner.parent_job_id != root_id
                or planner.root_job_id != root_id
                or planner.depth != 1
                or planner.plan_attempt_id is not None
                or planner.plan_digest is not None
                or planner.plan_step_id is not None
                or planner.supersedes_job_id is not None
                or not isinstance(planner_provenance, dict)
                or planner_provenance.get("schema_version")
                != "mastermind.executive_orchestration_provenance/v1"
                or planner_provenance.get("creator") != "coo_cycle"
                or planner_provenance.get("command_id") != expected_create_command
                or planner_provenance.get("job_id") != planner.job_id
                or planner_provenance.get("parent_job_id") != root_id
                or planner_provenance.get("root_job_id") != root_id
                or planner_provenance.get("role") != "plan"
                or planner_provenance.get("source_id") != root_id
                or planner_provenance.get("source_digest")
                != root.orchestration_provenance_digest
            ):
                return self._block(root_id, planner.job_id, "lineage_invalid")

        # 2. One recoverable same-Job requeue precedes every create/dispatch.
        recoverable = sorted(
            [
                job
                for job in all_jobs
                if job.status in _RECOVERABLE and job.attempt_count < job.attempt_limit
            ],
            key=lambda job: _job_sort_key(job, ordinals),
        )
        if recoverable:
            selected = recoverable[0]
            if not selected.current_attempt_id:
                return self._block(root_id, selected.job_id, "state_conflict")
            command = (
                f"coo-cycle:{root_id}:requeue:{selected.job_id}:"
                f"{selected.current_attempt_id}"
            )
            try:
                receipt = self.runtime.jobs.requeue_job(
                    selected.job_id, command_id=command
                )
            except StateConflict as exc:
                return self._block(
                    root_id,
                    selected.job_id,
                    _classify_invalid(exc),
                    evidence={"error_type": type(exc).__name__},
                )
            return self._outcome(
                root_id, "REQUEUED", selected.job_id, command, receipt
            )

        # 3. Resolve one closed adverse terminal/review verdict.
        adverse: list[tuple[tuple[int, int, int, str], str, Job, dict[str, Any]]] = []
        for job in all_jobs:
            exhausted = job.attempt_count >= job.attempt_limit
            if job.orchestration_role == "plan" and (
                job.status == JobStatus.CANCELLED
                or (job.status in _RECOVERABLE and exhausted)
            ):
                adverse.append((_job_sort_key(job, ordinals), "block_plan", job, {}))
            elif job.orchestration_role in {"work", "repair"} and (
                job.status == JobStatus.CANCELLED
                or (job.status in _RECOVERABLE and exhausted)
            ):
                adverse.append((_job_sort_key(job, ordinals), "block_child", job, {}))
            elif job.orchestration_role == "aggregation" and (
                job.status == JobStatus.CANCELLED
                or (job.status in _RECOVERABLE and exhausted)
            ):
                adverse.append((_job_sort_key(job, ordinals), "block_root", job, {}))

        if admission is not None and plan_body is not None:
            with self.runtime.store.read() as connection:
                rows = {
                    str(row["job_id"]): row
                    for row in connection.execute(
                        "SELECT * FROM jobs WHERE root_job_id=?", (root_id,)
                    )
                }
                review_groups: dict[str, list[Job]] = {}
                for review in children:
                    if review.orchestration_role == "review" and review.reviews_job_id:
                        review_groups.setdefault(review.reviews_job_id, []).append(review)
                for target_id, unsorted_peers in review_groups.items():
                    target = next(
                        (candidate for candidate in children if candidate.job_id == target_id),
                        None,
                    )
                    if target is None or current_by_step.get(str(target.plan_step_id), {}).get(
                        "current_job_id"
                    ) != target.job_id:
                        continue
                    peers = sorted(unsorted_peers, key=lambda item: item.job_id)
                    approvals: list[Job] = []
                    rejects: list[tuple[Job, str]] = []
                    voids: list[Job] = []
                    terminal_adverse: list[Job] = []
                    invalid_results: list[Job] = []
                    living: list[Job] = []
                    for review in peers:
                        exhausted = review.attempt_count >= review.attempt_limit
                        if review.status == JobStatus.CANCELLED or (
                            review.status in _RECOVERABLE and exhausted
                        ):
                            terminal_adverse.append(review)
                            continue
                        if review.status != JobStatus.COMPLETED:
                            living.append(review)
                            continue
                        try:
                            attempt, seal, _terminal, completion_digest = (
                                _validated_role_completion_material(
                                    connection,
                                    job_row=rows[review.job_id],
                                    expected_role="review",
                                    root_job_id=root_id,
                                )
                            )
                            body = seal["result_envelope"]["role_result"]
                            independent = _review_attempt_is_independent(
                                connection,
                                review_attempt_id=str(attempt["attempt_id"]),
                                reviewed_attempt_id=str(body["reviewed_attempt_id"]),
                            )
                        except StateConflict:
                            invalid_results.append(review)
                            continue
                        if not independent:
                            voids.append(review)
                        elif body.get("verdict") == "approve":
                            approvals.append(review)
                        elif body.get("verdict") == "reject":
                            rejects.append((review, completion_digest))
                        else:
                            invalid_results.append(review)

                    # A qualifying replacement approval resolves the target as a
                    # set; a historical VOID or adverse record cannot veto it.
                    if approvals:
                        continue
                    if invalid_results:
                        selected = invalid_results[0]
                        adverse.append(
                            (_job_sort_key(selected, ordinals), "block_result", selected, {})
                        )
                        continue
                    if rejects:
                        selected, review_digest = rejects[0]
                        kind = (
                            "repair"
                            if int(target.repair_round or 0) < policy.max_repair_rounds
                            else "block_repairs"
                        )
                        adverse.append(
                            (
                                _job_sort_key(selected, ordinals),
                                kind,
                                selected,
                                {
                                    "target": target.job_id,
                                    "review_result_digest": review_digest,
                                },
                            )
                        )
                        continue
                    if living:
                        continue
                    closed = [*voids, *terminal_adverse]
                    if closed and len(peers) < policy.max_review_attempts_per_job:
                        selected = sorted(closed, key=lambda item: item.job_id)[0]
                        adverse.append(
                            (
                                _job_sort_key(selected, ordinals),
                                "replace_review",
                                selected,
                                {"target": target.job_id, "ordinal": len(peers) + 1},
                            )
                        )
                    elif voids:
                        selected = voids[0]
                        adverse.append(
                            (_job_sort_key(selected, ordinals), "block_independence", selected, {})
                        )
                    elif terminal_adverse:
                        selected = terminal_adverse[0]
                        adverse.append(
                            (_job_sort_key(selected, ordinals), "block_reviews", selected, {})
                        )

        if adverse:
            _key, kind, selected, data = sorted(adverse, key=lambda item: item[0])[0]
            reason = {
                "block_plan": "plan_terminal_adverse",
                "block_child": "child_terminal_adverse",
                "block_root": "aggregation_terminal_adverse",
                "block_reviews": "review_jobs_exhausted",
                "block_independence": "review_not_independent",
                "block_repairs": "repair_rounds_exhausted",
                "block_result": "result_protocol_invalid",
            }.get(kind)
            if reason:
                return self._block(root_id, selected.job_id, reason)
            if kind == "replace_review":
                target = str(data["target"])
                command = f"coo-cycle:{root_id}:create-review:{target}:{int(data['ordinal'])}"
                try:
                    receipt = self.runtime.jobs.create_cycle_review(
                        root_id, target, command_id=command
                    )
                except StateConflict as exc:
                    return self._block(root_id, selected.job_id, _classify_invalid(exc))
                return self._outcome(root_id, "REVIEW_CREATED", receipt.job_id, command, receipt)
            if kind == "repair":
                target = str(data["target"])
                next_round = int(
                    next(job for job in children if job.job_id == target).repair_round or 0
                ) + 1
                command = (
                    f"coo-cycle:{root_id}:create-repair:{target}:{selected.job_id}:"
                    f"{data['review_result_digest']}:{next_round}"
                )
                try:
                    receipt = self.runtime.jobs.create_cycle_repair(
                        root_id, target, selected.job_id, command_id=command
                    )
                except StateConflict as exc:
                    return self._block(root_id, selected.job_id, _classify_invalid(exc))
                return self._outcome(root_id, "REPAIR_CREATED", receipt.job_id, command, receipt)

        # 4. Create exactly the sole planner.
        if not children and not admission_events:
            command = f"coo-cycle:{root_id}:create-planner:0"
            planner = self.runtime.jobs.create_cycle_planner(root_id, command_id=command)
            return self._outcome(root_id, "PLANNER_CREATED", planner.job_id, command, planner)

        # 5. Reconcile an active exact dispatch before considering new work.
        # A supervisor may have durably claimed/launched the Job and then lost
        # its return path.  Replaying the original command lets that supervisor
        # resume or return the same Attempt without a second claim/mutation.
        active = sorted(
            [
                job
                for job in children
                if job.status in {JobStatus.RUNNING, JobStatus.CHECKPOINTED}
            ],
            key=lambda job: _job_sort_key(job, ordinals),
        )
        if active:
            selected = active[0]
            if selected.attempt_count < 1 or not selected.current_attempt_id:
                return self._block(root_id, selected.job_id, "state_conflict")
            command = (
                f"coo-cycle:{root_id}:dispatch:{selected.job_id}:attempt:"
                f"{selected.attempt_count}"
            )
            receipt = self.dispatcher(selected.job_id, command)
            if receipt is None:
                raise StateConflict(
                    "active exact dispatch returned no reconcilable outcome"
                )
            return self._outcome(root_id, "DISPATCHED", selected.job_id, command, receipt)

        # 6. Dispatch the first queued non-root by the closed total order.
        queued = sorted(
            [job for job in children if job.status == JobStatus.QUEUED],
            key=lambda job: _job_sort_key(job, ordinals),
        )
        if queued:
            selected = queued[0]
            command = (
                f"coo-cycle:{root_id}:dispatch:{selected.job_id}:attempt:"
                f"{selected.attempt_count + 1}"
            )
            # The dispatcher may have durably claimed the exact Job before its
            # local return/launch path raises.  Never append a second COO
            # mutation in that ambiguous state: propagate, then let the same
            # deterministic command reconcile the existing Attempt on replay.
            receipt = self.dispatcher(selected.job_id, command)
            if receipt is None:
                if not self._dispatch_none_was_preclaim(selected):
                    raise StateConflict(
                        "exact dispatch return is ambiguous after durable Job transition"
                    )
                return self._block(root_id, selected.job_id, "exact_dispatch_unavailable")
            return self._outcome(root_id, "DISPATCHED", selected.job_id, command, receipt)

        # 7. Admit the completed plan and its ordered initial work wave.
        if not admission_events:
            planners = [job for job in children if job.orchestration_role == "plan"]
            if len(planners) != 1 or len(children) != 1:
                return self._block(root_id, root_id, "unexpected_pre_admission_child")
            planner = planners[0]
            if planner.status == JobStatus.COMPLETED and planner.current_attempt_id:
                command = f"coo-cycle:{root_id}:admit-plan:{planner.current_attempt_id}"
                try:
                    members = self.runtime.jobs.admit_cycle_plan(root_id, command_id=command)
                except StateConflict as exc:
                    return self._block(root_id, planner.job_id, _classify_invalid(exc))
                return self._outcome(
                    root_id,
                    "PLAN_ADMITTED",
                    planner.job_id,
                    command,
                    {"work_job_ids": [member.job_id for member in members]},
                )

        # 8. Create one missing review for the lowest completed current revision.
        if admission is not None:
            missing: list[Job] = []
            for step_id, material in current_by_step.items():
                if not material["review_required"]:
                    continue
                current_job = next(
                    job for job in children if job.job_id == material["current_job_id"]
                )
                reviews = [job for job in children if job.reviews_job_id == current_job.job_id]
                if current_job.status == JobStatus.COMPLETED and not reviews:
                    missing.append(current_job)
            if missing:
                target = sorted(missing, key=lambda job: _job_sort_key(job, ordinals))[0]
                command = f"coo-cycle:{root_id}:create-review:{target.job_id}:1"
                review = self.runtime.jobs.create_cycle_review(
                    root_id, target.job_id, command_id=command
                )
                return self._outcome(root_id, "REVIEW_CREATED", review.job_id, command, review)

        # 9. Derived approvals flow directly to the immutable handoff mutation.
        if admission is not None and not handoff_events:
            living = [
                job
                for job in children
                if job.status not in {
                    JobStatus.RATE_LIMITED, JobStatus.FAILED, JobStatus.LOST,
                    JobStatus.COMPLETED, JobStatus.CANCELLED,
                }
            ]
            if not living:
                try:
                    with self.runtime.store.read() as connection:
                        root_row = connection.execute(
                            "SELECT * FROM jobs WHERE job_id=?", (root_id,)
                        ).fetchone()
                        assert root_row is not None and plan_body is not None
                        _current_orchestration_tree_material(
                            connection, root_row, admission, plan_body
                        )
                    command = f"coo-cycle:{root_id}:aggregation-handoff:1"
                    handoff = self.runtime.jobs.create_cycle_handoff(
                        root_id, command_id=command
                    )
                    return self._outcome(
                        root_id, "HANDOFF_CREATED", root_id, command, handoff
                    )
                except StateConflict as exc:
                    return self._block(root_id, root_id, _classify_invalid(exc))

        # 10. Dispatch/reconcile the exact root only after immutable handoff.
        if handoff_events and root.status in {
            JobStatus.RUNNING,
            JobStatus.CHECKPOINTED,
        }:
            if root.attempt_count < 1 or not root.current_attempt_id:
                return self._block(root_id, root_id, "state_conflict")
            command = (
                f"coo-cycle:{root_id}:dispatch:{root_id}:attempt:"
                f"{root.attempt_count}"
            )
            receipt = self.dispatcher(root_id, command)
            if receipt is None:
                raise StateConflict(
                    "active exact root dispatch returned no reconcilable outcome"
                )
            return self._outcome(root_id, "DISPATCHED", root_id, command, receipt)
        if handoff_events and root.status == JobStatus.QUEUED:
            command = (
                f"coo-cycle:{root_id}:dispatch:{root_id}:attempt:"
                f"{root.attempt_count + 1}"
            )
            receipt = self.dispatcher(root_id, command)
            if receipt is None:
                if not self._dispatch_none_was_preclaim(root):
                    raise StateConflict(
                        "exact root dispatch return is ambiguous after durable Job transition"
                    )
                return self._block(root_id, root_id, "exact_dispatch_unavailable")
            return self._outcome(root_id, "DISPATCHED", root_id, command, receipt)

        return self._outcome(
            root_id,
            "NO_ACTION",
            None,
            None,
            {"policy_sha": policy.policy_sha256},
        )


__all__ = ["CYCLE_OUTCOME_SCHEMA", "CooCycle", "CooCycleOutcome", "Dispatch"]
