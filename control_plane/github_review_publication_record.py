"""Exactly-once review publication reservation in the EXISTING Executive event log.

GitHub is authoritative for actual review existence. The incumbent Exec
events.command_id UNIQUE constraint only arbitrates ONE publication attempt.
There is no new database, queue, dispatcher, retry, lease, or review approver.

A claim without verified GitHub readback stays EFFECT_UNKNOWN and never triggers
another POST automatically. This safety/availability tradeoff is deliberate.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable

from control_plane.executive_runtime import Runtime
from control_plane.github_review_intent import ReviewIntentDecision
from control_plane.github_review_intent_ingress import (
    ExpectedReviewPublisher,
    ExternalCommentAdvisory,
    FinalPullRequestCheck,
    PublicationEffectUnknown,
    PullRequestReadPort,
    ReconcilingReviewPublication,
    ReviewTransportPort,
    ReviewVerificationRefused,
    publication_command_id as expected_publication_command_id,
)

_RESERVE = "GITHUB_REVIEW_PUBLICATION_RESERVED"
_COMMIT = "GITHUB_REVIEW_PUBLICATION_CONFIRMED"
_SCHEMA = "mastermind.github_review_publication_event.v1"
_COMMAND_RE = re.compile(r"gh-review-publish:[0-9a-f]{32}\Z")
_REVIEW_ID_RE = re.compile(r"[A-Za-z0-9:._-]{1,128}\Z")


class ExecutiveReviewPublicationRecord:
    """One authoritative caller guard plus two append-only event receipts."""

    def __init__(
        self, *,
        runtime: Runtime,
        transport: ReviewTransportPort,
        job_id: str,
        expected_publisher: ExpectedReviewPublisher,
        decision: ReviewIntentDecision,
        pull_requests: PullRequestReadPort,
        publication_guard: Callable[[], None] | None = None,
    ) -> None:
        if not isinstance(runtime, Runtime):
            raise TypeError("canonical Executive Runtime required")
        if not isinstance(transport, ReviewTransportPort):
            raise TypeError("authenticated GitHub review transport required")
        if not isinstance(job_id, str) or not job_id:
            raise TypeError("an exact canonical Job identity is required")
        if not isinstance(expected_publisher, ExpectedReviewPublisher):
            raise TypeError("host-owned GitHub publisher identity is required")
        if not isinstance(decision, ReviewIntentDecision) or not decision.admitted:
            raise TypeError("admitted review decision is required")
        if not isinstance(pull_requests, PullRequestReadPort):
            raise TypeError("authenticated pull-request reader is required")
        self._runtime = runtime
        self._transport = transport
        self._job_id = job_id
        self._expected_publisher = expected_publisher
        self._decision = decision
        self._pull_requests = pull_requests
        self._guard = publication_guard
        self._advisory: ExternalCommentAdvisory | None = None

    def publishing_principal(self) -> ExpectedReviewPublisher:
        return self._expected_publisher

    def seal_external_comment_advisory(self, proof: ExternalCommentAdvisory) -> None:
        """Bind one verified COMMENT submitter proof for the final guard.

        Only ``publish_verified_review`` calls this after its authenticated
        submitter re-read. The final guard reads GitHub again and still refuses
        a draft when the proof, verb, or live submitter does not match.
        """

        if not isinstance(proof, ExternalCommentAdvisory):
            raise ReviewVerificationRefused("EXTERNAL_SOURCE_INVALID")
        self._advisory = proof

    def _authorize(self) -> None:
        if self._guard is None:
            raise ReviewVerificationRefused("GITHUB_REVIEW_PUBLICATION_UNARMED")
        try:
            value = self._guard()
        except Exception:
            raise ReviewVerificationRefused("GITHUB_REVIEW_PUBLICATION_NOT_AUTHORIZED") from None
        if value is not None:
            raise ReviewVerificationRefused("GITHUB_REVIEW_PUBLICATION_NOT_AUTHORIZED")

    @staticmethod
    def _identity(
        *, command_id: str, repository: str, pull_number: int,
        head_sha: str, event: str, body: str, job_id: str,
    ) -> dict:
        if not isinstance(command_id, str) or _COMMAND_RE.fullmatch(command_id) is None:
            raise ReviewVerificationRefused("GITHUB_PUBLICATION_COMMAND_INVALID")
        if command_id != expected_publication_command_id(
            repository=repository, pull_number=pull_number,
            head_sha=head_sha, job_id=job_id,
        ):
            raise ReviewVerificationRefused("GITHUB_PUBLICATION_IDENTITY_DRIFT")
        if event not in {"COMMENT", "REQUEST_CHANGES"}:
            raise ReviewVerificationRefused("GITHUB_REVIEW_VERB_REFUSED")
        if not isinstance(body, str) or not body or len(body) > 16_000:
            raise ReviewVerificationRefused("GITHUB_REVIEW_BODY_INVALID")
        return {
            "schema": _SCHEMA, "job_id": job_id,
            "repository": repository, "pull_number": pull_number,
            "head_sha": head_sha, "event": event,
            "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        }

    def published_command_ids(self) -> frozenset[str]:
        events = self._runtime.store.list_events(
            command_id_prefix="gh-review-publish:"
        )
        completed = set()
        for e in events:
            if e.event_type != _COMMIT or e.payload.get("schema") != _SCHEMA:
                continue
            command_id = e.payload.get("original_command_id")
            if isinstance(command_id, str) and _COMMAND_RE.fullmatch(command_id):
                completed.add(command_id)
        return frozenset(completed)

    def _observe(self, command_id: str, identity: dict) -> tuple[str, str | None]:
        """Return ABSENT / RESERVED / CONFIRMED from incumbent EventStore."""
        stored = self._runtime.store.get_event_by_command_id(command_id)
        if stored is None:
            return "ABSENT", None
        if stored.event_type != _RESERVE or stored.payload != identity:
            raise ReviewVerificationRefused("GITHUB_REVIEW_RESERVATION_CONFLICT")
        committed = self._runtime.store.get_event_by_command_id(command_id + ":confirmed")
        if committed is None:
            return "RESERVED", None
        if (
            committed.event_type != _COMMIT
            or committed.payload.get("original_command_id") != command_id
            or committed.payload.get("identity") != identity
            or not isinstance(committed.payload.get("review_id"), str)
            or _REVIEW_ID_RE.fullmatch(committed.payload["review_id"]) is None
        ):
            raise ReviewVerificationRefused("GITHUB_REVIEW_CONFIRMATION_CONFLICT")
        return "CONFIRMED", committed.payload["review_id"]

    def _reserve(self, command_id: str, identity: dict) -> str:
        self._authorize()
        with self._runtime.store.transaction() as conn:
            self._authorize()
            existing = self._runtime.store.get_event_by_command_id(
                command_id, connection=conn
            )
            if existing is None:
                self._runtime.store.append_event(
                    conn, aggregate_type="github_review_publication",
                    aggregate_id=command_id, event_type=_RESERVE,
                    command_id=command_id, actor="github-review-publisher",
                    payload=identity,
                )
                return "CREATED"
            if existing.event_type != _RESERVE or existing.payload != identity:
                raise ReviewVerificationRefused("GITHUB_REVIEW_RESERVATION_CONFLICT")
            return "EXISTING"

    def _confirm(self, command_id: str, identity: dict, review_id: str) -> None:
        if not isinstance(review_id, str) or _REVIEW_ID_RE.fullmatch(review_id) is None:
            raise PublicationEffectUnknown("GITHUB_REVIEW_RECEIPT_INVALID")
        self._authorize()
        with self._runtime.store.transaction() as conn:
            self._authorize()
            reserve = self._runtime.store.get_event_by_command_id(
                command_id, connection=conn
            )
            if reserve is None or reserve.event_type != _RESERVE or reserve.payload != identity:
                raise ReviewVerificationRefused("GITHUB_REVIEW_RESERVATION_MISSING")
            done = self._runtime.store.get_event_by_command_id(
                command_id + ":confirmed", connection=conn
            )
            material = {
                **identity, "identity": identity,
                "original_command_id": command_id, "review_id": review_id,
            }
            if done is not None:
                if done.event_type != _COMMIT or done.payload != material:
                    raise ReviewVerificationRefused("GITHUB_REVIEW_CONFIRMATION_CONFLICT")
                return
            self._runtime.store.append_event(
                conn, aggregate_type="github_review_publication",
                aggregate_id=command_id, event_type=_COMMIT,
                command_id=command_id + ":confirmed",
                actor="github-review-publisher", payload=material,
            )

    def reserve_publication(
        self, *, publication_command_id: str, repository: str,
        pull_number: int, head_sha: str, event: str, body: str,
    ) -> bool:
        """Commit one incumbent UNIQUE claim. True only for the first writer."""

        identity = self._identity(
            command_id=publication_command_id, repository=repository,
            pull_number=pull_number, head_sha=head_sha, event=event,
            body=body, job_id=self._job_id,
        )
        return self._reserve(publication_command_id, identity) == "CREATED"

    def confirm_publication(
        self, *, publication_command_id: str, repository: str,
        pull_number: int, head_sha: str, event: str, body: str, review_id: str,
    ) -> None:
        identity = self._identity(
            command_id=publication_command_id, repository=repository,
            pull_number=pull_number, head_sha=head_sha, event=event,
            body=body, job_id=self._job_id,
        )
        self._confirm(publication_command_id, identity, review_id)

    def _final_check(self, event: str) -> FinalPullRequestCheck:
        return FinalPullRequestCheck(
            decision=self._decision,
            pull_requests=self._pull_requests,
            event=event,
            advisory=self._advisory,
            host_guard=self._authorize,
        )

    def publish_review(
        self, *,
        publication_command_id: str,
        repository: str,
        pull_number: int,
        head_sha: str,
        event: str,
        body: str,
    ) -> str:
        identity = self._identity(
            command_id=publication_command_id, repository=repository,
            pull_number=pull_number, head_sha=head_sha, event=event,
            body=body, job_id=self._job_id,
        )
        status, review_id = self._observe(publication_command_id, identity)
        if status == "CONFIRMED":
            assert review_id is not None
            return review_id
        # One bridge owns the single reserve, the reviews GET, the typed final
        # check, and the POST. A second reserve here would turn the first
        # writer into EFFECT_UNKNOWN and suppress the publication.
        bridge = ReconcilingReviewPublication(
            transport=self._transport,
            published=self,
            expected_publisher=self._expected_publisher,
            before_post=self._final_check(event),
        )
        return bridge.publish_review(
            publication_command_id=publication_command_id,
            repository=repository, pull_number=pull_number,
            head_sha=head_sha, event=event, body=body,
        )
