"""Bounded GitHub review Job admission through canonical Executive Runtime.

GitHub PRs that did not originate inside Executive OS have no native builder
Job. Do NOT fabricate one or pretend these are native sibling review Jobs.
This adapter admits a read-only, ordinary root Job with source-bound provenance;
the existing broker/supervisor exclusively owns Attempts, Workers and START.
"""
from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Callable, Mapping
from typing import Any

from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.github_review_intent import ReviewIntentDecision, ReviewIntentError
from control_plane.github_review_intent_ingress import (
    AdmittedJobFacts, ReviewAdmissionReceipt, ExistingReviewDecisionUnavailable,
)

PREFIX = "gh-review-intent:"
SCHEMA = "mastermind.github_review_runtime_admission.v1"


class ReviewAdmissionUnavailable(RuntimeError):
    """No authorized admission context or an unreconciled command effect."""


class ExecutiveReviewJobAdmission:
    """Existing JobRegistry and EventStore only: no second queue or dispatch."""

    def __init__(
        self,
        *,
        runtime: Runtime,
        admission_guard: Callable[[], None] | None = None,
        constraints: Mapping[str, Any] | None = None,
    ) -> None:
        self._runtime = runtime
        self._admission_guard = admission_guard
        self._constraints = dict(constraints or {})

    def _authorize(self) -> None:
        if self._admission_guard is None:
            raise ReviewAdmissionUnavailable("REVIEW_RUNTIME_ADMISSION_UNARMED")
        try:
            answer = self._admission_guard()
        except Exception:
            raise ReviewAdmissionUnavailable("REVIEW_RUNTIME_ADMISSION_REFUSED") from None
        if answer is not None:
            raise ReviewAdmissionUnavailable("REVIEW_RUNTIME_ADMISSION_REFUSED")

    def admitted_command_ids(self) -> frozenset[str]:
        # Existing Executive event index is canonical; this list is only a
        # preflight optimization. create_job's UNIQUE constraint settles races.
        self._authorize()
        events = self._runtime.store.list_events(command_id_prefix=PREFIX)
        return frozenset(e.command_id for e in events if e.event_type == "JOB_CREATED")

    def has_admitted_command(self, command_id: str) -> bool:
        """Exact read-only canonical command existence for FAST skip fencing.

        This uses the incumbent EventStore UNIQUE key, not a new cache or
        review registry. An inconsistent event refuses before any new Job.
        """
        self._authorize()
        if type(command_id) is not str or not command_id.startswith(PREFIX):
            raise ReviewAdmissionUnavailable("REVIEW_COMMAND_ID_INVALID")
        existing = self._runtime.store.get_event_by_command_id(command_id)
        if existing is None:
            return False
        if existing.event_type != "JOB_CREATED" or not existing.job_id:
            raise ReviewAdmissionUnavailable("REVIEW_COMMAND_ID_COLLISION")
        return True

    def _reconcile(
        self, *, decision: ReviewIntentDecision, objective: str
    ) -> str | None:
        command_id = decision.command_id
        if command_id is None:
            return None
        existing = self._runtime.store.get_event_by_command_id(command_id)
        if existing is None:
            return None
        if existing.event_type != "JOB_CREATED" or not existing.job_id:
            raise ReviewAdmissionUnavailable("REVIEW_COMMAND_ID_COLLISION")
        job = self._runtime.jobs.get_job(existing.job_id)
        if job.objective != objective or existing.command_id != command_id:
            raise ReviewAdmissionUnavailable("REVIEW_COMMAND_PAYLOAD_CONFLICT")
        provenance = existing.payload.get("provenance")
        if not isinstance(provenance, dict) or provenance.get("schema") != SCHEMA:
            raise ReviewAdmissionUnavailable("REVIEW_COMMAND_PROVENANCE_CONFLICT")
        if (
            provenance.get("repository") != decision.repository
            or provenance.get("pull_number") != decision.pull_number
            or provenance.get("frozen_head_sha") != decision.frozen_head_sha
            or provenance.get("actor") != decision.actor
        ):
            raise ReviewAdmissionUnavailable("REVIEW_COMMAND_IDENTITY_CONFLICT")
        if ("decision" in provenance and provenance["decision"] != decision.to_dict()):
            raise ReviewAdmissionUnavailable("REVIEW_COMMAND_PROVENANCE_CONFLICT")
        return job.job_id

    def read_existing_review(self, *, decision: ReviewIntentDecision) -> ReviewAdmissionReceipt | None:
        """Read the immutable first admission for this identity, never reattribute it.

        Legacy records establish existence but cannot reconstruct a delivery or
        channel they never recorded. Refuse that join rather than redispatch.
        """
        try:
            ReviewIntentDecision.from_admitted_dict(decision.to_dict())
        except (ReviewIntentError, AttributeError):
            raise ReviewAdmissionUnavailable("REVIEW_JOB_IDENTITY_INVALID") from None
        event = self._runtime.store.get_event_by_command_id(decision.command_id)
        if event is None:
            return None
        if (event.event_type != "JOB_CREATED" or not event.job_id
                or event.aggregate_type != "job" or event.aggregate_id != event.job_id):
            raise ReviewAdmissionUnavailable("REVIEW_COMMAND_ID_COLLISION")
        job = self._runtime.jobs.get_job(event.job_id)
        provenance = event.payload.get("provenance")
        if (job is None or job.job_id != event.job_id or not isinstance(provenance, dict)
                or provenance.get("schema") != SCHEMA):
            raise ReviewAdmissionUnavailable("REVIEW_COMMAND_PROVENANCE_CONFLICT")
        if "decision" not in provenance:
            if (any(provenance.get(field) != getattr(decision, field)
                    for field in ("repository", "pull_number", "frozen_head_sha", "intent_id", "command_id"))
                    or event.command_id != decision.command_id
                    or job.requested_authorities != ["READ"] or job.allowed_write_paths != []
                    or job.parent_job_id is not None or job.orchestration_role is not None):
                raise ReviewAdmissionUnavailable("REVIEW_COMMAND_PROVENANCE_CONFLICT")
            raise ExistingReviewDecisionUnavailable(
                job_id=job.job_id, command_id=event.command_id,
                repository=provenance["repository"], pull_number=provenance["pull_number"],
                frozen_head_sha=provenance["frozen_head_sha"],
            )
        try:
            original = ReviewIntentDecision.from_admitted_dict(provenance["decision"])
        except ReviewIntentError:
            raise ReviewAdmissionUnavailable("REVIEW_COMMAND_PROVENANCE_CONFLICT") from None
        for field in ("repository", "pull_number", "frozen_head_sha", "intent_id", "command_id"):
            if (getattr(original, field) != getattr(decision, field)
                    or provenance.get(field) != getattr(original, field)):
                raise ReviewAdmissionUnavailable("REVIEW_COMMAND_IDENTITY_CONFLICT")
        if (event.command_id != original.command_id
                or provenance.get("actor") != original.actor
                or provenance.get("objective_sha256") != hashlib.sha256(job.objective.encode("utf-8")).hexdigest()
                or job.requested_authorities != ["READ"] or job.allowed_write_paths != []
                or job.parent_job_id is not None or job.orchestration_role is not None):
            raise ReviewAdmissionUnavailable("REVIEW_COMMAND_PROVENANCE_CONFLICT")
        return ReviewAdmissionReceipt(job_id=job.job_id, decision=original, created=False)

    def admit_or_join_review_intent(
        self, *, decision: ReviewIntentDecision, objective: str,
    ) -> ReviewAdmissionReceipt:
        """Atomically create or join an authorized trigger for the same PR head."""
        self._authorize()
        if type(objective) is not str or not objective.strip():
            raise ReviewAdmissionUnavailable("REVIEW_JOB_IDENTITY_INVALID")
        objective = objective.strip()

        def existing_receipt() -> ReviewAdmissionReceipt | None:
            receipt = self.read_existing_review(decision=decision)
            if receipt is not None and receipt.decision == decision:
                # An exact submission replay must still reconcile its payload.
                self._reconcile(decision=decision, objective=objective)
            return receipt

        existing = existing_receipt()
        if existing is not None:
            return existing
        try:
            self._create(decision=decision, objective=objective)
        except StateConflict:
            existing = existing_receipt()
            if existing is not None:
                return existing
            raise ReviewAdmissionUnavailable("REVIEW_RUNTIME_ADMISSION_REFUSED") from None
        receipt = self.read_existing_review(decision=decision)
        if receipt is None:
            raise ReviewAdmissionUnavailable("REVIEW_RUNTIME_ADMISSION_UNRECONCILED")
        return dataclasses.replace(receipt, created=True)

    def read_admitted_job(self, *, command_id: str) -> AdmittedJobFacts | None:
        """Re-read the incumbent JOB_CREATED event, Job, and provenance.

        This is a publication-time source check, not a new admission. It does
        not arm or create a Job. Absence is None; the publisher refuses that.
        """

        if not isinstance(command_id, str) or not command_id.startswith(PREFIX):
            return None
        event = self._runtime.store.get_event_by_command_id(command_id)
        if (
            event is None
            or event.event_type != "JOB_CREATED"
            or event.command_id != command_id
            or not event.job_id
        ):
            return None
        job = self._runtime.jobs.get_job(event.job_id)
        if job is None or job.job_id != event.job_id:
            return None
        provenance = event.payload.get("provenance")
        if (
            not isinstance(provenance, dict)
            or provenance.get("schema") != SCHEMA
            or provenance.get("command_id") != command_id
        ):
            return None
        repository = provenance.get("repository")
        pull_number = provenance.get("pull_number")
        head_sha = provenance.get("frozen_head_sha")
        actor = provenance.get("actor")
        intent_id = provenance.get("intent_id")
        stored_decision = None
        if "decision" in provenance:
            try:
                stored_decision = ReviewIntentDecision.from_admitted_dict(provenance["decision"])
                if stored_decision.command_id != command_id:
                    return None
                receipt = self.read_existing_review(decision=stored_decision)
                if receipt is None or receipt.job_id != event.job_id:
                    return None
            except (ReviewIntentError, ReviewAdmissionUnavailable):
                return None
        if (
            not isinstance(repository, str) or not repository
            or type(pull_number) is not int or pull_number <= 0
            or not isinstance(head_sha, str) or not head_sha
            or (actor is None and (stored_decision is None or stored_decision.policy_authority is None))
            or (actor is not None and (not isinstance(actor, str) or not actor))
            or not isinstance(intent_id, str) or not intent_id
        ):
            return None
        return AdmittedJobFacts(
            job_id=job.job_id,
            command_id=command_id,
            repository=repository,
            pull_number=pull_number,
            frozen_head_sha=head_sha,
            actor=actor,
            intent_id=intent_id,
            decision=stored_decision,
        )

    def admit_review_intent(
        self, *, decision: ReviewIntentDecision, objective: str
    ) -> str:
        self._authorize()
        if (
            not isinstance(decision, ReviewIntentDecision)
            or not decision.admitted
            or not isinstance(decision.command_id, str)
            or not decision.command_id.startswith(PREFIX)
            or not isinstance(objective, str)
            or not objective
        ):
            raise ReviewAdmissionUnavailable("REVIEW_JOB_IDENTITY_INVALID")
        objective = objective.strip()
        existing = self._reconcile(decision=decision, objective=objective)
        if existing is not None:
            return existing
        try:
            return self._create(decision=decision, objective=objective)
        except StateConflict:
            existing = self._reconcile(decision=decision, objective=objective)
            if existing is not None:
                return existing
            raise ReviewAdmissionUnavailable("REVIEW_RUNTIME_ADMISSION_REFUSED") from None

    def _create(self, *, decision: ReviewIntentDecision, objective: str) -> str:
        try:
            ReviewIntentDecision.from_admitted_dict(decision.to_dict())
        except ReviewIntentError:
            raise ReviewAdmissionUnavailable("REVIEW_JOB_IDENTITY_INVALID") from None
        provenance = {
            "schema": SCHEMA,
            "repository": decision.repository,
            "pull_number": decision.pull_number,
            "frozen_head_sha": decision.frozen_head_sha,
            "actor": decision.actor,
            "intent_id": decision.intent_id,
            "command_id": decision.command_id,
            "decision": decision.to_dict(),
            "objective_sha256": hashlib.sha256(objective.encode("utf-8")).hexdigest(),
        }
        job = self._runtime.jobs.create_job(
                objective,
                department="engineering",
                priority=0,
                authority_level="A0",
                attempt_limit=1,
                constraints=dict(self._constraints),
                command_id=decision.command_id,
                provenance=provenance,
                requested_authorities=["READ"],
                allowed_write_paths=[],
                validation_commands=[],
                owner_seat="coo",
                escalation_target="coo",
                business_impact="routine",
                # This Job is the review itself, not a builder awaiting review.
                review_required=False,
                orchestration_role=None,
                _principal_commit_guard=self._authorize,
            )
        return job.job_id
