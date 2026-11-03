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
from types import MappingProxyType

from control_plane.executive_runtime import Runtime
from control_plane.github_review_intent import (
    COMMAND_ID_RE, AutomaticReviewOrigin, ReviewIntentDecision, ReviewIntentError, ReviewIntentPolicy,
)
from control_plane.github_review_runtime_adapter import (
    ExecutiveReviewJobAdmission, ReviewAdmissionUnavailable,
)
from control_plane.github_review_intent_ingress import ExistingReviewDecisionUnavailable

from control_plane.github_review_socket_contract import (
    FRAME_SCHEMA, RESPONSE_SCHEMA, MAX_FRAME_BYTES,
    REVIEW_SLACK_CHANNEL_ID, SlackParentMessage, PreparedReviewSourceCheck,
)
_SUPPORTED_ACTIONS = frozenset({"status", "admit", "admit_or_join", "reserve_parent", "record_parent"})


class GitHubReviewSocketRefused(ValueError):
    """An opaque, closed exact frame or authority refusal."""


def _closed_command(value: object) -> str:
    if type(value) is not str or COMMAND_ID_RE.fullmatch(value) is None:
        raise GitHubReviewSocketRefused("REVIEW_SOCKET_COMMAND_INVALID")
    return value


def _closed_decision(raw: object) -> ReviewIntentDecision:
    if isinstance(raw, dict) and (raw.get("admitted") is not True or raw.get("refusal") is not None):
        raise GitHubReviewSocketRefused("REVIEW_SOCKET_DECISION_REFUSED")
    try:
        return ReviewIntentDecision.from_admitted_dict(raw)
    except (ValueError, TypeError, ReviewIntentError):
        raise GitHubReviewSocketRefused("REVIEW_SOCKET_DECISION_INVALID") from None


class ExecutiveGitHubReviewSocketOwner:
    """One bounded typed status/admit frame, using existing canonical ledger."""

    def __init__(
        self,
        *,
        runtime: Runtime,
        admission_guard: Callable[[], None],
        source_guard: Callable[[ReviewIntentDecision], None] | None = None,
        source_preflight: Callable[[ReviewIntentDecision], PreparedReviewSourceCheck] | None = None,
        repositories: frozenset[str],
        automatic_policy: ReviewIntentPolicy | None = None,
        automatic_policies: Mapping[tuple[int, str], ReviewIntentPolicy] | None = None,
        reconciliation_guard: Callable[[str], None] | None = None,
        relay_bot_user_id: str | None = None,
        worker_constraints: Mapping[str, object] | None = None,
        parent_message_reader: Callable[[ReviewIntentDecision, str, str], SlackParentMessage] | None = None,
        parent_recorder: Callable[..., None] | None = None,
        parent_reserver: Callable[..., bool] | None = None,
        parent_body_renderer: Callable[..., str] | None = None,
    ) -> None:
        if not isinstance(runtime, Runtime):
            raise TypeError("canonical Executive Runtime required")
        if not callable(admission_guard):
            raise TypeError("installed host admission guard required")
        if ((source_guard is None) == (source_preflight is None)
                or (source_guard is not None and not callable(source_guard))
                or (source_preflight is not None and not callable(source_preflight))):
            raise TypeError("exactly one installed source guard or preflight is required")
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
        self._source_preflight = source_preflight
        self._repositories = repositories
        if automatic_policy is not None and (
            type(automatic_policy) is not ReviewIntentPolicy
            or not automatic_policy.repositories.issubset(repositories)
        ):
            raise ValueError("automatic review policy must be host-bound to enrolled repositories")
        self._automatic_policy = automatic_policy
        if automatic_policies is not None:
            if (automatic_policy is not None or not isinstance(automatic_policies, Mapping)
                    or len(automatic_policies) > 32):
                raise ValueError("automatic review policy binding is ambiguous")
            selected = {}
            folded = set()
            for key, policy in automatic_policies.items():
                if (type(key) is not tuple or len(key) != 2
                        or type(key[0]) is not int or key[0] <= 0
                        or type(key[1]) is not str or key[1] not in repositories
                        or type(policy) is not ReviewIntentPolicy
                        or any(type(getattr(policy, name)) is not frozenset for name in (
                            "repositories", "installation_ids", "authorized_actors", "allowed_associations"))
                        or policy.repositories != frozenset({key[1]})
                        or policy.installation_ids != frozenset({key[0]})):
                    raise ValueError("automatic review policy must bind one exact source pair")
                normalized = (key[0], key[1].casefold())
                if normalized in folded:
                    raise ValueError("automatic review policy binding is ambiguous")
                selected[key] = policy
                folded.add(normalized)
            self._automatic_policies = MappingProxyType(selected)
        else:
            self._automatic_policies = None
        if reconciliation_guard is not None and not callable(reconciliation_guard):
            raise ValueError("reconciliation requires an incumbent owner guard")
        self._reconciliation_guard = reconciliation_guard
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
        if parent_reserver is not None and not callable(parent_reserver):
            raise ValueError("canonical Slack parent sender must be callable")
        # Installed owner supplies the SAME ExecutiveSlackReviewThreads
        # instance's reserve_parent_send; no public-supplied recorder or DB.
        self._parent_reserver = parent_reserver
        if parent_body_renderer is not None and not callable(parent_body_renderer):
            raise ValueError("trusted Slack parent renderer must be callable")
        self._parent_body_renderer = parent_body_renderer
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

    def _prepare_source_check(self, decision: ReviewIntentDecision) -> Callable[[], None]:
        if self._source_preflight is None:
            # Preserve the historical callback contract for existing callers.
            # Installed network-backed guards should use the prepared path.
            return lambda: self._source_guard(decision)
        prepared = self._source_preflight(decision)
        if type(prepared) is not PreparedReviewSourceCheck or prepared.decision != decision:
            raise ValueError("REVIEW_PREPARED_SOURCE_IDENTITY_MISMATCH")
        return lambda: prepared.verify(decision)

    def _check_policy_authority(self, decision: ReviewIntentDecision) -> None:
        authority = decision.policy_authority
        if authority is None:
            return
        try:
            policy = (self._automatic_policy if self._automatic_policies is None
                      else self._automatic_policies.get((authority.installation_id, decision.repository)))
            if policy is None or authority.policy_digest != policy.repository_policy_digest(
                repository=decision.repository, installation_id=authority.installation_id,
            ):
                raise ValueError("standing policy is not enrolled")
        except (ReviewIntentError, ValueError):
            raise GitHubReviewSocketRefused("REVIEW_REPOSITORY_POLICY_NOT_ENROLLED") from None
        if authority.origin is AutomaticReviewOrigin.AUTHENTICATED_RECONCILIATION:
            try:
                if (self._reconciliation_guard is None
                        or self._reconciliation_guard(authority.owner_execution_ref) is not None):
                    raise ValueError("reconciliation owner is not authenticated")
            except Exception:
                raise GitHubReviewSocketRefused("REVIEW_RECONCILIATION_OWNER_UNARMED") from None

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
        if action in {"reserve_parent", "record_parent"}:
            expected = {"schema", "action", "decision", "job_id", "channel_id"}
            if action == "record_parent":
                expected.update({"thread_ts", "author_user_id"})
            if set(frame) != expected:
                raise GitHubReviewSocketRefused("REVIEW_SOCKET_FRAME_INVALID")
            if action == "reserve_parent":
                if self._relay_bot_user_id is None or self._parent_reserver is None:
                    raise GitHubReviewSocketRefused("REVIEW_SLACK_PROVENANCE_UNBOUND")
            elif (self._relay_bot_user_id is None
                    or self._parent_message_reader is None
                    or self._parent_recorder is None
                    or self._parent_body_renderer is None):
                raise GitHubReviewSocketRefused("REVIEW_SLACK_PROVENANCE_UNBOUND")
            chosen = _closed_decision(frame.get("decision"))
            self._check_policy_authority(chosen)
            job_id = frame.get("job_id")
            if (chosen.repository not in self._repositories
                    or type(job_id) is not str
                    or re.fullmatch(r"JOB-[0-9]+", job_id) is None
                    or frame.get("channel_id") != REVIEW_SLACK_CHANNEL_ID
                    or (action == "record_parent"
                        and frame.get("author_user_id") != self._relay_bot_user_id)):
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
                or ("decision" in provenance and provenance["decision"] != chosen.to_dict())
            ):
                raise GitHubReviewSocketRefused("REVIEW_SLACK_PARENT_JOB_MISMATCH")
            if action == "reserve_parent":
                # The source/actor/PR head must still be authorized before
                # claiming a one-attempt Slack effect in canonical SQLite.
                try:
                    source_check = self._prepare_source_check(chosen)
                    if source_check() is not None:
                        raise ValueError("review source no longer current")
                except Exception:
                    raise GitHubReviewSocketRefused(
                        "REVIEW_SLACK_PARENT_SOURCE_UNVERIFIED"
                    ) from None
                try:
                    first = self._parent_reserver(
                        decision=chosen, job_id=job_id
                    )
                except Exception:
                    # Reservation may have committed; never POST without
                    # an authenticated positive reservation response.
                    raise GitHubReviewSocketRefused(
                        "REVIEW_SLACK_PARENT_RESERVATION_UNKNOWN"
                    ) from None
                if type(first) is not bool:
                    raise GitHubReviewSocketRefused(
                        "REVIEW_SLACK_PARENT_RESERVATION_UNKNOWN"
                    )
                return {
                    "schema": RESPONSE_SCHEMA,
                    "state": "PARENT_SEND_RESERVED" if first
                             else "PARENT_ALREADY_ATTEMPTED",
                    "job_id": job_id,
                }
            ts = frame.get("thread_ts")
            if type(ts) is not str or re.fullmatch(
                r"[0-9]{10,16}[.][0-9]{6}", ts
            ) is None:
                raise GitHubReviewSocketRefused("REVIEW_SLACK_PARENT_INVALID")
            # Both remote source recheck and trusted Slack GET are outside the
            # SQLite EventStore transaction. The public caller cannot supply
            # bot authorship, message text or evidence of an actual Slack POST.
            try:
                source_check = self._prepare_source_check(chosen)
                if source_check() is not None:
                    raise ValueError("review source no longer current")
                receipt = self._parent_message_reader(chosen, job_id, ts)
                expected_bodies = {
                    self._parent_body_renderer(
                        decision=chosen, job_id=job_id,
                        public_repository_names_authorized=authorized,
                    )
                    for authorized in (False, True)
                }
                if any(type(body) is not str for body in expected_bodies):
                    raise ValueError("trusted parent renderer invalid")
            except Exception:
                raise GitHubReviewSocketRefused(
                    "REVIEW_SLACK_PARENT_SOURCE_UNVERIFIED"
                ) from None
            if (
                not isinstance(receipt, SlackParentMessage)
                or receipt.ts != ts
                or receipt.author_user_id != self._relay_bot_user_id
                or receipt.thread_ts is not None or receipt.edited or receipt.deleted
                or receipt.text not in expected_bodies
            ):
                raise GitHubReviewSocketRefused(
                    "REVIEW_SLACK_PARENT_SOURCE_UNVERIFIED"
                )
            try:
                if self._source_preflight is not None:
                    source_check()
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
        self._check_policy_authority(chosen)
        if chosen.repository not in self._repositories:
            raise GitHubReviewSocketRefused("REVIEW_REPOSITORY_NOT_AUTHORIZED")
        objective = frame.get("objective")
        if (type(objective) is not str or not objective
                or len(objective.encode("utf-8")) > 4000):
            raise GitHubReviewSocketRefused("REVIEW_OBJECTIVE_INVALID")
        try:
            source_check = self._prepare_source_check(chosen)
            if source_check() is not None:
                raise ValueError("source guard refused")
        except Exception:
            raise GitHubReviewSocketRefused("REVIEW_SOURCE_NOT_VERIFIED") from None
        # Bind the ORIGINAL immutable source identity into the canonical
        # JobRegistry's own commit-time guard. The prepared path performs no
        # HTTP here: current host binding/arm/policy and the ORIGINAL bounded
        # observation age are checked after lock acquisition and before commit.
        def current_request_authority() -> None:
            if self._admission_guard() is not None:
                raise ValueError("review admission guard refused")
            if source_check() is not None:
                raise ValueError("review source guard refused")
            self._check_policy_authority(chosen)

        try:
            admission = ExecutiveReviewJobAdmission(
                runtime=self._runtime,
                admission_guard=current_request_authority,
                constraints=self._worker_constraints,
            )
            if action == "admit_or_join":
                receipt = admission.admit_or_join_review_intent(decision=chosen, objective=objective)
                return {
                    "schema": RESPONSE_SCHEMA,
                    "state": "ADMITTED" if receipt.created else "ALREADY_ADMITTED",
                    "job_id": receipt.job_id, "decision": receipt.decision.to_dict(),
                }
            job = admission.admit_review_intent(decision=chosen, objective=objective)
        except ExistingReviewDecisionUnavailable as existing:
            if action != "admit_or_join" or not existing.matches(chosen):
                raise GitHubReviewSocketRefused("REVIEW_RUNTIME_ADMISSION_REFUSED") from None
            return {
                "schema": RESPONSE_SCHEMA, "state": "EXISTS_WITHOUT_DECISION",
                "job_id": existing.job_id, "command_id": existing.command_id,
                "repository": existing.repository, "pull_number": existing.pull_number,
                "frozen_head_sha": existing.frozen_head_sha,
            }
        except ReviewAdmissionUnavailable:
            raise GitHubReviewSocketRefused("REVIEW_RUNTIME_ADMISSION_REFUSED") from None
        return {"schema": RESPONSE_SCHEMA, "state": "ADMITTED", "job_id": job}
