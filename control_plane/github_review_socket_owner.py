"""Narrow GitHub-review admission over the INCUMBENT Executive CEO Unix socket.

This is a leaf of the current ExecutiveControlService, not a new listener or
admission database. Only the installed kernel-authenticated app UID can reach
its host invocation, and the host must separately arm/guard exact review
source admission. GitHub never supplies the socket target or trust callbacks.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping

from control_plane.executive_runtime import Runtime
from control_plane.github_review_intent import (
    COMMAND_ID_RE, IntentSource, ReviewIntentDecision, ReviewIntentError,
    review_command_id, review_intent_id,
)
from control_plane.github_review_runtime_adapter import (
    ExecutiveReviewJobAdmission, ReviewAdmissionUnavailable,
)

from control_plane.github_review_socket_contract import (
    FRAME_SCHEMA, RESPONSE_SCHEMA, MAX_FRAME_BYTES,
    REVIEW_SLACK_CHANNEL_ID, SlackParentMessage, review_parent_body,
)
_SUPPORTED_ACTIONS = frozenset({"status", "admit", "record_parent"})
_DECISION_KEYS = frozenset({
    "schema", "admitted", "refusal", "intent_source", "intent_id",
    "command_id", "delivery_command_id", "repository", "pull_number",
    "frozen_head_sha", "actor", "already_admitted",
})


class GitHubReviewSocketRefused(ValueError):
    """An opaque, closed exact frame or authority refusal."""


def _closed_command(value: object) -> str:
    if type(value) is not str or COMMAND_ID_RE.fullmatch(value) is None:
        raise GitHubReviewSocketRefused("REVIEW_SOCKET_COMMAND_INVALID")
    return value


def _closed_decision(raw: object) -> ReviewIntentDecision:
    if not isinstance(raw, dict) or set(raw) != _DECISION_KEYS:
        raise GitHubReviewSocketRefused("REVIEW_SOCKET_DECISION_INVALID")
    if raw.get("schema") != "mastermind.github_review_intent.v1":
        raise GitHubReviewSocketRefused("REVIEW_SOCKET_DECISION_INVALID")
    if raw.get("admitted") is not True or raw.get("refusal") is not None:
        raise GitHubReviewSocketRefused("REVIEW_SOCKET_DECISION_REFUSED")
    if raw.get("already_admitted") is not False:
        raise GitHubReviewSocketRefused("REVIEW_SOCKET_DECISION_INVALID")
    try:
        event_source = IntentSource(raw.get("intent_source"))
        chosen = ReviewIntentDecision(
            admitted=True, refusal=None, intent_source=event_source,
            intent_id=raw.get("intent_id"),
            command_id=raw.get("command_id"),
            delivery_command_id=raw.get("delivery_command_id"),
            repository=raw.get("repository"),
            pull_number=raw.get("pull_number"),
            frozen_head_sha=raw.get("frozen_head_sha"),
            actor=raw.get("actor"),
            already_admitted=False,
        )
        if (
            chosen.intent_id != review_intent_id(
                repository=chosen.repository,
                pull_number=chosen.pull_number,
                head_sha=chosen.frozen_head_sha,
            )
            or chosen.command_id != review_command_id(chosen.intent_id)
            or type(chosen.delivery_command_id) is not str
            or re.fullmatch(r"gh-review-delivery:[0-9a-f]{32}", chosen.delivery_command_id) is None
            or type(chosen.actor) is not str
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", chosen.actor) is None
        ):
            raise ValueError("identity mismatch")
        return chosen
    except (ValueError, TypeError, ReviewIntentError):
        raise GitHubReviewSocketRefused("REVIEW_SOCKET_DECISION_INVALID") from None


class ExecutiveGitHubReviewSocketOwner:
    """One bounded typed status/admit frame, using existing canonical ledger."""

    def __init__(
        self,
        *,
        runtime: Runtime,
        admission_guard: Callable[[], None],
        source_guard: Callable[[ReviewIntentDecision], None],
        repositories: frozenset[str],
        relay_bot_user_id: str | None = None,
        worker_constraints: Mapping[str, object] | None = None,
        parent_message_reader: Callable[[ReviewIntentDecision, str, str], SlackParentMessage] | None = None,
        parent_recorder: Callable[..., None] | None = None,
    ) -> None:
        if not isinstance(runtime, Runtime):
            raise TypeError("canonical Executive Runtime required")
        if not callable(admission_guard) or not callable(source_guard):
            raise TypeError("both installed host admission and source guards required")
        if (not isinstance(repositories, frozenset)
                or not repositories
                or any(not isinstance(r, str)
                       or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", r) is None
                       for r in repositories)):
            raise ValueError("review repository allowlist required")
        self._runtime = runtime
        self._admission_guard = admission_guard
        if relay_bot_user_id is not None and (
            type(relay_bot_user_id) is not str
            or re.fullmatch(r"[UW][A-Z0-9]{8,31}", relay_bot_user_id) is None
        ):
            raise ValueError("Relay bot identity must be host-verified")
        self._source_guard = source_guard
        self._repositories = repositories
        # Parent capture remains default-off until the installed owner supplies
        # its exact enrolled Relay bot identity; never trust the GitHub frame.
        self._relay_bot_user_id = relay_bot_user_id
        if parent_message_reader is not None and not callable(parent_message_reader):
            raise ValueError("trusted Slack parent reader must be a callable")
        # This MUST be implemented by the installed host using authenticated
        # Relay Slack readback, never a receipt fabricated from socket fields.
        self._parent_message_reader = parent_message_reader
        if parent_recorder is not None and not callable(parent_recorder):
            raise ValueError("trusted canonical parent recorder must be callable")
        # Host injects EXISTING ExecutiveSlackReviewThreads.record_parent;
        # a public frame cannot select a different Runtime/EventStore writer.
        self._parent_recorder = parent_recorder
        # Only the installed Executive host selects existing worker quota
        # classes. Never accept worker placement or account/model hints from
        # a public webhook/Unix frame. Empty keeps source tests QUEUED-only.
        if worker_constraints is None:
            self._worker_constraints = {}
        else:
            if (not isinstance(worker_constraints, Mapping)
                    or set(worker_constraints) != {"eligible_quota_classes"}):
                raise ValueError("review worker route must be host-selected")
            classes = worker_constraints.get("eligible_quota_classes")
            if (type(classes) not in {list, tuple}
                    or not 1 <= len(classes) <= 8
                    or any(type(q) is not str or re.fullmatch(
                        r"[a-z0-9][a-z0-9_.-]{0,63}", q
                    ) is None for q in classes)
                    or len(set(classes)) != len(classes)):
                raise ValueError("review worker quota classes invalid")
            self._worker_constraints = {"eligible_quota_classes": list(classes)}
        # Admission is bound to an individual immutable request when handled;
        # never retain mutable per-request authority on this shared owner.

    def handle_frame(self, frame: object) -> dict[str, object]:
        if not isinstance(frame, dict) or frame.get("schema") != FRAME_SCHEMA:
            raise GitHubReviewSocketRefused("REVIEW_SOCKET_FRAME_INVALID")
        try:
            raw = json.dumps(
                frame, separators=(",", ":"), sort_keys=True,
                ensure_ascii=True, allow_nan=False,
            ).encode("ascii") + b"\n"
        except (TypeError, ValueError, OverflowError):
            raise GitHubReviewSocketRefused("REVIEW_SOCKET_FRAME_INVALID") from None
        if len(raw) > MAX_FRAME_BYTES:
            raise GitHubReviewSocketRefused("REVIEW_SOCKET_FRAME_OVER_BOUND")
        action = frame.get("action")
        if action not in _SUPPORTED_ACTIONS:
            raise GitHubReviewSocketRefused("REVIEW_SOCKET_ACTION_REFUSED")
        try:
            if self._admission_guard() is not None:
                raise ValueError("guard refused")
        except Exception:
            raise GitHubReviewSocketRefused("REVIEW_RUNTIME_ADMISSION_UNARMED") from None
        if action == "status":
            if set(frame) != {"schema", "action", "command_id"}:
                raise GitHubReviewSocketRefused("REVIEW_SOCKET_FRAME_INVALID")
            command = _closed_command(frame.get("command_id"))
            event = self._runtime.store.get_event_by_command_id(command)
            if event is None:
                return {"schema": RESPONSE_SCHEMA, "state": "ABSENT"}
            if event.event_type != "JOB_CREATED" or not event.job_id:
                raise GitHubReviewSocketRefused("REVIEW_SOCKET_COMMAND_CONFLICT")
            provenance = event.payload.get("provenance")
            if (not isinstance(provenance, dict)
                    or provenance.get("schema") != "mastermind.github_review_runtime_admission.v1"
                    or provenance.get("command_id") != command
                    or provenance.get("repository") not in self._repositories):
                raise GitHubReviewSocketRefused("REVIEW_SOCKET_COMMAND_CONFLICT")
            return {"schema": RESPONSE_SCHEMA, "state": "EXISTS", "job_id": event.job_id}
        if action == "record_parent":
            if set(frame) != {
                "schema", "action", "decision", "job_id",
                "channel_id", "thread_ts", "author_user_id",
            }:
                raise GitHubReviewSocketRefused("REVIEW_SOCKET_FRAME_INVALID")
            if (self._relay_bot_user_id is None
                    or self._parent_message_reader is None
                    or self._parent_recorder is None):
                raise GitHubReviewSocketRefused("REVIEW_SLACK_PROVENANCE_UNBOUND")
            chosen = _closed_decision(frame.get("decision"))
            job_id = frame.get("job_id")
            if (chosen.repository not in self._repositories
                    or type(job_id) is not str
                    or re.fullmatch(r"JOB-[0-9]+", job_id) is None
                    or frame.get("channel_id") != REVIEW_SLACK_CHANNEL_ID
                    or frame.get("author_user_id") != self._relay_bot_user_id):
                raise GitHubReviewSocketRefused("REVIEW_SLACK_PARENT_IDENTITY_REFUSED")
            # The public webhook cannot name an arbitrary Job/thread: capture
            # only against the immutable canonical admission for this PR head.
            event = self._runtime.store.get_event_by_command_id(
                chosen.command_id
            )
            provenance = (event.payload.get("provenance")
                          if event is not None else None)
            if (
                event is None or event.event_type != "JOB_CREATED"
                or event.job_id != job_id or not isinstance(provenance, dict)
                or provenance.get("schema") != "mastermind.github_review_runtime_admission.v1"
                or provenance.get("command_id") != chosen.command_id
                or provenance.get("repository") != chosen.repository
                or provenance.get("pull_number") != chosen.pull_number
                or provenance.get("frozen_head_sha") != chosen.frozen_head_sha
                or provenance.get("actor") != chosen.actor
            ):
                raise GitHubReviewSocketRefused("REVIEW_SLACK_PARENT_JOB_MISMATCH")
            ts = frame.get("thread_ts")
            if type(ts) is not str or re.fullmatch(
                r"[0-9]{10,16}[.][0-9]{6}", ts
            ) is None:
                raise GitHubReviewSocketRefused("REVIEW_SLACK_PARENT_INVALID")
            # Both remote source recheck and trusted Slack GET are outside the
            # SQLite EventStore transaction. The public caller cannot supply
            # bot authorship, message text or evidence of an actual Slack POST.
            try:
                if self._source_guard(chosen) is not None:
                    raise ValueError("review source no longer current")
                receipt = self._parent_message_reader(chosen, job_id, ts)
            except Exception:
                raise GitHubReviewSocketRefused(
                    "REVIEW_SLACK_PARENT_SOURCE_UNVERIFIED"
                ) from None
            if (
                not isinstance(receipt, SlackParentMessage)
                or receipt.ts != ts
                or receipt.author_user_id != self._relay_bot_user_id
                or receipt.thread_ts is not None or receipt.edited or receipt.deleted
                or receipt.text not in {
                    review_parent_body(
                        decision=chosen, job_id=job_id,
                        public_repository_names_authorized=False,
                    ),
                    review_parent_body(
                        decision=chosen, job_id=job_id,
                        public_repository_names_authorized=True,
                    ),
                }
            ):
                raise GitHubReviewSocketRefused(
                    "REVIEW_SLACK_PARENT_SOURCE_UNVERIFIED"
                )
            try:
                self._parent_recorder(
                    decision=chosen, job_id=job_id, message=receipt
                )
            except Exception:
                raise GitHubReviewSocketRefused(
                    "REVIEW_SLACK_PARENT_INVALID_OR_CONFLICT"
                ) from None
            return {
                "schema": RESPONSE_SCHEMA, "state": "PARENT_RECORDED",
                "job_id": job_id,
            }
        if set(frame) != {"schema", "action", "decision", "objective"}:
            raise GitHubReviewSocketRefused("REVIEW_SOCKET_FRAME_INVALID")
        chosen = _closed_decision(frame.get("decision"))
        if chosen.repository not in self._repositories:
            raise GitHubReviewSocketRefused("REVIEW_REPOSITORY_NOT_AUTHORIZED")
        objective = frame.get("objective")
        if (type(objective) is not str or not objective
                or len(objective.encode("utf-8")) > 4000):
            raise GitHubReviewSocketRefused("REVIEW_OBJECTIVE_INVALID")
        try:
            if self._source_guard(chosen) is not None:
                raise ValueError("source guard refused")
        except Exception:
            raise GitHubReviewSocketRefused("REVIEW_SOURCE_NOT_VERIFIED") from None
        # Bind the ORIGINAL immutable source identity into the canonical
        # JobRegistry's own commit-time guard. A source revocation between
        # preflight and SQLite commit must not admit a new review Job.
        def current_request_authority() -> None:
            if self._admission_guard() is not None:
                raise ValueError("review admission guard refused")
            if self._source_guard(chosen) is not None:
                raise ValueError("review source guard refused")

        try:
            job = ExecutiveReviewJobAdmission(
                runtime=self._runtime,
                admission_guard=current_request_authority,
                constraints=self._worker_constraints,
            ).admit_review_intent(decision=chosen, objective=objective)
        except ReviewAdmissionUnavailable:
            raise GitHubReviewSocketRefused("REVIEW_RUNTIME_ADMISSION_REFUSED") from None
        return {"schema": RESPONSE_SCHEMA, "state": "ADMITTED", "job_id": job}
