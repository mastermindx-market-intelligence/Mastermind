"""Hierarchy-filtered exact Session Bridge targets from existing owner projections.

Read-only composition: the installed host authenticates the caller, supplies
the canonical mixed organizational observation, and retains the existing
Session Bridge dispatcher and commit authority. This module does not send
messages, enroll or wake sessions, grant permissions, or create a target store.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import re

from control_plane.fabric_coordination_policy import (
    CoordinationActorIdentity, CoordinationIdentity, CoordinationNativeIdentity,
    CoordinationRefused, CoordinationRole, CoordinationSnapshot,
    authorize_coordination,
)
from control_plane.operator_harness_contract import runtime_binding_id_for
from integrations.fabric_coordination_composite import (
    CompositeCoordinationEvidence, CompositeCoordinationObservationSource,
)
from integrations.fabric_coordination_single import (
    SingleDomainCoordinationObservationSource,
)
from integrations.session_bridge.claude_native import (
    ClaudeNativeTarget, ClaudeNativeTargetProjector,
)
from integrations.session_bridge.runtime_owner import (
    RuntimeFabricTarget, RuntimeFabricTargetProjector,
)

_TARGET_RE = re.compile(r"\A(?:claude|fabric_attempt):[0-9a-f]{64}\Z")


class ScopedTargetUnavailable(CoordinationRefused):
    """Opaque failure. Foreign peers and stale targets have the same result."""


def _refuse() -> None:
    raise ScopedTargetUnavailable("SCOPED_TARGET_UNAVAILABLE")


def _authorization_context_digest(
    scope: CoordinationSnapshot,
    sender: CoordinationActorIdentity,
    recipient: CoordinationActorIdentity,
    topic_ref: str,
) -> str:
    """Pin original exact party scope, NOT expiring snapshot clocks/revision.

    This is evidence from the host-authenticated membership owner, never
    supplied as a public target argument or a reusable authorization token.
    """
    if type(scope) is not CoordinationSnapshot or type(topic_ref) is not str:
        _refuse()
    source = scope.participant(sender, now=scope.observed_at)
    target = scope.participant(recipient, now=scope.observed_at)
    data = json.dumps({
        "topic": topic_ref,
        "sender_scope": asdict(source),
        "recipient_scope": asdict(target),
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
       allow_nan=False).encode("ascii")
    return hashlib.sha256(data).hexdigest()


def _grant_digest(scope: CoordinationSnapshot, grant_ref: str | None) -> str | None:
    if grant_ref is None:
        return None
    matches = [grant for grant in scope.grants if grant.grant_ref == grant_ref]
    if len(matches) != 1:
        _refuse()
    data = json.dumps(
        asdict(matches[0]), sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True, slots=True)
class ScopedSessionTarget:
    target_ref: str
    recipient: CoordinationActorIdentity
    role: CoordinationRole
    relation: str
    evidence_digest: str
    valid_until: int
    authorization_context_digest: str
    grant_ref: str | None = None
    grant_digest: str | None = None

    def __post_init__(self) -> None:
        if (
            type(self.target_ref) is not str
            or _TARGET_RE.fullmatch(self.target_ref) is None
            or type(self.recipient) not in (CoordinationIdentity, CoordinationNativeIdentity)
            or type(self.role) is not CoordinationRole
            or type(self.relation) is not str
            or type(self.evidence_digest) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", self.evidence_digest)
            or type(self.valid_until) is not int
            or type(self.authorization_context_digest) is not str
            or re.fullmatch(r"[0-9a-f]{64}", self.authorization_context_digest) is None
            or (self.grant_ref is None) != (self.grant_digest is None)
            or (self.grant_ref is not None
                and (type(self.grant_ref) is not str
                     or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}", self.grant_ref) is None))
            or (self.grant_digest is not None
                and (type(self.grant_digest) is not str
                     or re.fullmatch(r"[0-9a-f]{64}", self.grant_digest) is None))
        ):
            _refuse()

    def public_projection(self) -> dict[str, str | bool]:
        return {
            "target_ref": self.target_ref,
            "kind": self.target_ref.split(":", 1)[0],
            "relation": self.relation,
            "role": self.role.value,
            "addressable": True,
        }


class ScopedSessionTargetResolver:
    """Same-policy discovery and exact re-resolution for an authenticated actor.

    The worker and native projectors must be the incumbent Session Bridge
    owners. A target is accepted only after it matches the active, independently
    attested organizational identity and policy relation. An old target ref
    never falls back to a newer session. The results are NOT reusable grants:
    the installed message-commit owner must fence policy and writer identity.
    """

    def __init__(
        self, *,
        owner: CompositeCoordinationObservationSource | SingleDomainCoordinationObservationSource,
        worker_targets: RuntimeFabricTargetProjector | None = None,
        native_targets: ClaudeNativeTargetProjector | None = None,
        caller: CoordinationActorIdentity,
        topic_ref: str,
        now: Callable[[], int],
    ) -> None:
        valid_mixed = (
            type(owner) is CompositeCoordinationObservationSource
            and type(worker_targets) is RuntimeFabricTargetProjector
            and type(native_targets) is ClaudeNativeTargetProjector
        )
        valid_single = (
            type(owner) is SingleDomainCoordinationObservationSource
            and (
                (owner.domain == "worker"
                 and type(worker_targets) is RuntimeFabricTargetProjector
                 and native_targets is None)
                or
                (owner.domain == "native"
                 and type(native_targets) is ClaudeNativeTargetProjector
                 and worker_targets is None)
            )
        )
        if (
            not (valid_mixed or valid_single)
            or type(caller) not in (CoordinationIdentity, CoordinationNativeIdentity)
            or type(topic_ref) is not str or not topic_ref
            or not callable(now)
        ):
            raise TypeError("installed owner-backed target readers and caller required")
        self._owner = owner
        self._workers = worker_targets
        self._natives = native_targets
        self._caller = caller
        self._topic = topic_ref
        self._now = now

    def _candidates(self, evidence: CompositeCoordinationEvidence) -> list[tuple[str, CoordinationActorIdentity]]:
        scope = evidence.snapshot
        active = {p.identity: p for p in scope.participants if p.active}
        native_verified = set(evidence.native_ids)
        refs: set[str] = set()
        actors: set[CoordinationActorIdentity] = set()
        found: list[tuple[str, CoordinationActorIdentity]] = []

        for target in (self._workers.list_targets() if self._workers is not None else ()):
            if type(target) is not RuntimeFabricTarget:
                _refuse()
            epoch = target.epoch
            owners = [a for a in active if type(a) is CoordinationIdentity
                      and a.job_id == epoch.job_id]
            if not owners:
                continue
            if len(owners) != 1:
                _refuse()
            actor = owners[0]
            if (
                actor.attempt_id != epoch.attempt_id
                or actor.worker_id != epoch.worker_id
                or actor.binding_id != runtime_binding_id_for(
                    epoch.attempt_id, epoch.harness_session_epoch_id)
                or actor.binding_generation != epoch.harness_generation_number
            ):
                _refuse()
            if target.target_ref in refs or actor in actors:
                _refuse()
            refs.add(target.target_ref)
            actors.add(actor)
            found.append((target.target_ref, actor))

        for target in (self._natives.list_targets() if self._natives is not None else ()):
            if type(target) is not ClaudeNativeTarget:
                _refuse()
            owners = [a for a in active if type(a) is CoordinationNativeIdentity
                      and a.session_id == target.session_id]
            if not owners:
                continue
            if len(owners) != 1:
                _refuse()
            actor = owners[0]
            if (
                actor not in native_verified
                or actor.generation != target.generation
                or actor.host_ref != target.host_ref
            ):
                _refuse()
            if target.target_ref in refs or actor in actors:
                _refuse()
            refs.add(target.target_ref)
            actors.add(actor)
            found.append((target.target_ref, actor))
        return found

    def _read(self) -> tuple[ScopedSessionTarget, ...]:
        try:
            evidence = self._owner.observe()
            if type(evidence) is not CompositeCoordinationEvidence:
                _refuse()
            now = self._now()
            if type(now) is not int:
                _refuse()
            scope = evidence.snapshot
            scope.participant(self._caller, now=now)
            initial_candidates = self._candidates(evidence)
            permitted: list[ScopedSessionTarget] = []
            for ref, actor in initial_candidates:
                if actor == self._caller:
                    continue
                try:
                    decision = authorize_coordination(
                        scope, self._caller, actor,
                        topic_ref=self._topic, now=now,
                    )
                except CoordinationRefused:
                    continue
                permitted.append(ScopedSessionTarget(
                    ref, actor, scope.participant(actor, now=now).role,
                    decision.relation, evidence.evidence_digest, scope.valid_until,
                    authorization_context_digest=_authorization_context_digest(
                        scope, self._caller, actor, self._topic,
                    ),
                    grant_ref=decision.grant_ref,
                    grant_digest=_grant_digest(scope, decision.grant_ref),
                ))
            # Recheck after both native/Runtime Session Bridge target projections:
            # an owner drift must not create an authorization snapshot.
            checked = self._owner.observe()
            checked_time = self._now()
            if (
                type(checked) is not CompositeCoordinationEvidence
                or checked.evidence_digest != evidence.evidence_digest
                or type(checked_time) is not int
                or not scope.observed_at <= checked_time < scope.valid_until
                or not checked.snapshot.observed_at <= checked_time < checked.snapshot.valid_until
            ):
                _refuse()
            # Runtime's physical dialogue carrier can rotate without changing
            # the underlying Job/Attempt binding or membership digest. Recheck
            # only authorized recipients' exact target refs after both sources.
            permitted_actors = {item.recipient for item in permitted}
            expected = {(ref, actor) for ref, actor in initial_candidates
                        if actor in permitted_actors}
            current = {(ref, actor) for ref, actor in self._candidates(checked)
                       if actor in permitted_actors}
            if current != expected:
                _refuse()
            expiry = min(scope.valid_until, checked.snapshot.valid_until)
            return tuple(sorted(
                (replace(item, valid_until=expiry) for item in permitted),
                key=lambda item: item.target_ref,
            ))
        except Exception:
            _refuse()

    def visible_targets(self) -> tuple[dict[str, str | bool], ...]:
        return tuple(target.public_projection() for target in self._read())

    def resolve(self, target_ref: str) -> ScopedSessionTarget:
        """Re-resolve exact target, never redirect to a replacement session."""
        try:
            if type(target_ref) is not str or _TARGET_RE.fullmatch(target_ref) is None:
                _refuse()
            selected = [t for t in self._read() if t.target_ref == target_ref]
            if len(selected) != 1:
                _refuse()
            target = selected[0]
            current = (
                self._natives.resolve(target_ref) if target_ref.startswith("claude:")
                else self._workers.resolve(target_ref)
            )
            if current.target_ref != target_ref:
                _refuse()
            after = [t for t in self._read() if t.target_ref == target_ref]
            if len(after) != 1 or after[0] != target:
                _refuse()
            return target
        except Exception:
            _refuse()
