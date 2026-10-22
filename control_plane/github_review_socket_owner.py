"""Narrow GitHub-review admission over the INCUMBENT Executive CEO Unix socket.

This is a leaf of the current ExecutiveControlService, not a new listener or
admission database. Only the installed kernel-authenticated app UID can reach
its host invocation, and the host must separately arm/guard exact review
source admission. GitHub never supplies the socket target or trust callbacks.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable

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
)
_SUPPORTED_ACTIONS = frozenset({"status", "admit"})
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
        self._source_guard = source_guard
        self._repositories = repositories
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
            ).admit_review_intent(decision=chosen, objective=objective)
        except ReviewAdmissionUnavailable:
            raise GitHubReviewSocketRefused("REVIEW_RUNTIME_ADMISSION_REFUSED") from None
        return {"schema": RESPONSE_SCHEMA, "state": "ADMITTED", "job_id": job}
