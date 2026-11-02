"""Strict terminal review extraction from canonical Executive Job/Attempt/Event facts.

This adapter never fabricates a builder worker. Native Executive review
requires a *real* separate completed builder Job for the exact PR/head.
Optional external GitHub PR source is a freshly authenticated PR submitter,
not a code-builder attestation, and allows only clearly labeled advisory
comments after source revalidation. No lifecycle, worker, or verdict invented.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

from control_plane.executive_runtime import AttemptStatus, JobStatus, Runtime
from control_plane.github_review_intent import assert_untrusted_text_admissible
from control_plane.github_review_intent_ingress import (
    ExternalGitHubSourceFacts, ExternalGitHubSourcePort, VerifiedReviewResult,
)

_SCHEMA = "mastermind.github_review_runtime_admission.v1"
_RESULT_VERDICTS = {"approve": "PASS", "reject": "REQUEST_CHANGES"}


class ExecutiveVerifiedReviewResults:
    """Read-only ReviewResultPort using accepted immutable Executive receipts."""

    def __init__(
        self,
        *,
        runtime: Runtime,
        builder_job_id_for_review: Callable[[str], str | None] | None = None,
        external_source: ExternalGitHubSourcePort | None = None,
        publisher_login: str | None = None,
    ) -> None:
        if not isinstance(runtime, Runtime):
            raise TypeError("canonical Runtime required")
        if external_source is not None:
            if (builder_job_id_for_review is not None
                    or not isinstance(external_source, ExternalGitHubSourcePort)
                    or not isinstance(publisher_login, str)
                    or not publisher_login or len(publisher_login) > 50):
                raise TypeError("external PR evidence requires one dedicated source")
        elif publisher_login is not None:
            raise TypeError("publisher cannot be bound without an external source")
        self._runtime = runtime
        self._builder_source = builder_job_id_for_review
        self._external_source = external_source
        self._publisher_login = publisher_login.casefold() if publisher_login else None

    def load_verified_result(self, *, job_id: str) -> VerifiedReviewResult | None:
        if not isinstance(job_id, str) or not job_id:
            return None
        job = self._runtime.jobs.get_job(job_id)
        if (
            job is None or job.status is not JobStatus.COMPLETED
            or job.orchestration_role is not None
            or not job.current_attempt_id or job.attempt_count != 1
            or not isinstance(job.result, dict)
            or job.requested_authorities != ["READ"]
            or job.allowed_write_paths or job.review_required
        ):
            return None
        attempt = self._runtime.attempts.get_attempt(job.current_attempt_id)
        if (
            attempt is None or attempt.status is not AttemptStatus.COMPLETED
            or attempt.job_id != job.job_id or attempt.result != job.result
            or not attempt.worker_id
        ):
            return None
        # Exactly one provenance-bearing admission and exact terminal event
        # must already exist in the immutable Runtime event log. A mutable
        # status field alone is insufficient proof of a qualified completion.
        events = self._runtime.store.list_events(job_id=job_id)
        creations = [e for e in events if e.event_type == "JOB_CREATED"]
        terminals = [
            e for e in events if e.event_type == "JOB_COMPLETED"
            and e.attempt_id == attempt.attempt_id
            and e.worker_id == attempt.worker_id
            and e.payload.get("status") == "COMPLETED"
        ]
        if len(creations) != 1 or len(terminals) != 1:
            return None
        provenance = creations[0].payload.get("provenance")
        if (
            not isinstance(provenance, dict)
            or provenance.get("schema") != _SCHEMA
            or creations[0].job_id != job_id
            or creations[0].aggregate_id != job_id
            or provenance.get("job_id") not in {None, job_id}
        ):
            return None

        # External GitHub PRs ordinarily have NO Executive builder Job. The
        # only permitted alternate provenance is an installation-authenticated
        # current PR submitter, expressly NOT a verified code-builder worker.
        # It allows a COMMENT-only advisory review, never native independent
        # review acceptance, approval, or a fabricated worker identity.
        if self._external_source is not None:
            try:
                source = self._external_source.read_external_source(
                    repository=provenance["repository"],
                    pull_number=provenance["pull_number"],
                )
            except Exception:
                return None
            if (
                not isinstance(source, ExternalGitHubSourceFacts)
                or source.repository != provenance.get("repository")
                or source.pull_number != provenance.get("pull_number")
                or source.head_sha != provenance.get("frozen_head_sha")
                or type(source.submitter_id) is not int
                or source.submitter_id <= 0
                or not isinstance(source.submitter_login, str)
                or not source.submitter_login
                or len(source.submitter_login) > 50
                or source.submitter_login.casefold() == self._publisher_login
            ):
                return None
            verdict = job.result.get("verdict")
            summary = job.result.get("summary")
            if (
                not isinstance(verdict, str)
                or verdict not in _RESULT_VERDICTS
                or not isinstance(summary, str)
                or not summary.strip() or len(summary) > 16000
            ):
                return None
            try:
                summary = assert_untrusted_text_admissible(
                    summary, name="review summary"
                )
                material = json.dumps(
                    job.result, sort_keys=True, ensure_ascii=False,
                    separators=(",", ":"), allow_nan=False,
                ).encode("utf-8")
            except Exception:
                return None
            return VerifiedReviewResult(
                job_id=job_id, attempt_id=attempt.attempt_id,
                verdict=_RESULT_VERDICTS[verdict],
                reviewer_worker_id=attempt.worker_id,
                builder_worker_id="",
                summary=summary,
                result_digest=hashlib.sha256(material).hexdigest(),
                source_basis="EXTERNAL_GITHUB_SUBMITTER",
                source_github_submitter_login=source.submitter_login,
                source_github_submitter_id=source.submitter_id,
            )

        # A verified reviewer without a verified *different* builder is not
        # independent. Never invent a builder Job for an external GitHub PR.
        if self._builder_source is None:
            return None
        try:
            builder_job_id = self._builder_source(job_id)
        except Exception:
            return None
        if not isinstance(builder_job_id, str) or not builder_job_id:
            return None
        builder = self._runtime.jobs.get_job(builder_job_id)
        if (
            builder is None or builder.status is not JobStatus.COMPLETED
            or builder.job_id == job_id or not builder.assigned_worker_id
            or builder.assigned_worker_id == attempt.worker_id
            or not builder.current_attempt_id
        ):
            return None
        # Worker difference is necessary but not sufficient. The reviewed
        # builder must carry an immutable, Executive-recorded source association
        # to the SAME repository, PR number and exact frozen head SHA.
        # A caller-selected completed job from an unrelated PR is not proof.
        builder_events = self._runtime.store.list_events(job_id=builder_job_id)
        origins = [e for e in builder_events
                   if e.event_type == "JOB_CREATED"
                   and e.job_id == builder_job_id]
        finishes = [e for e in builder_events
                    if e.event_type == "JOB_COMPLETED"
                    and e.job_id == builder_job_id
                    and e.attempt_id == builder.current_attempt_id
                    and e.worker_id == builder.assigned_worker_id
                    and e.payload.get("status") == "COMPLETED"]
        if len(origins) != 1 or len(finishes) != 1:
            return None
        source = origins[0].payload.get("provenance")
        if (
            not isinstance(source, dict)
            or source.get("schema") != "mastermind.github_review_builder_source.v1"
            or source.get("repository") != provenance.get("repository")
            or source.get("pull_number") != provenance.get("pull_number")
            or source.get("frozen_head_sha") != provenance.get("frozen_head_sha")
        ):
            return None
        builder_attempt = self._runtime.attempts.get_attempt(
            builder.current_attempt_id
        )
        if (
            builder_attempt is None
            or builder_attempt.status is not AttemptStatus.COMPLETED
            or builder_attempt.job_id != builder_job_id
            or builder_attempt.worker_id != builder.assigned_worker_id
        ):
            return None

        raw_verdict = job.result.get("verdict")
        if not isinstance(raw_verdict, str) or raw_verdict not in _RESULT_VERDICTS:
            return None
        summary = job.result.get("summary")
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 16000:
            return None
        try:
            summary = assert_untrusted_text_admissible(summary, name="review summary")
        except Exception:
            return None

        material = json.dumps(
            job.result, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        return VerifiedReviewResult(
            job_id=job_id, attempt_id=attempt.attempt_id,
            verdict=_RESULT_VERDICTS[raw_verdict],
            reviewer_worker_id=attempt.worker_id,
            builder_worker_id=builder.assigned_worker_id,
            summary=summary,
            result_digest=hashlib.sha256(material).hexdigest(),
        )
