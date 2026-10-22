"""Bounded GitHub review Job admission through canonical Executive Runtime.

GitHub PRs that did not originate inside Executive OS have no native builder
Job. Do NOT fabricate one or pretend these are native sibling review Jobs.
This adapter admits a read-only, ordinary root Job with source-bound provenance;
the existing broker/supervisor exclusively owns Attempts, Workers and START.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from typing import Any

from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.github_review_intent import ReviewIntentDecision

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
        return job.job_id

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
        existing = self._reconcile(decision=decision, objective=objective)
        if existing is not None:
            return existing
        provenance = {
            "schema": SCHEMA,
            "repository": decision.repository,
            "pull_number": decision.pull_number,
            "frozen_head_sha": decision.frozen_head_sha,
            "actor": decision.actor,
            "intent_id": decision.intent_id,
            "command_id": decision.command_id,
        }
        try:
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
            )
            return job.job_id
        except StateConflict:
            # Creation may have committed in a concurrent first delivery.
            # Reconcile the exact object instead of making a second Job.
            existing = self._reconcile(decision=decision, objective=objective)
            if existing is not None:
                return existing
            raise ReviewAdmissionUnavailable("REVIEW_RUNTIME_ADMISSION_REFUSED") from None
