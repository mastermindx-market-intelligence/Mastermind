"""Opt-in authenticated host composition for hierarchy-scoped target reads.

One canonical organization membership owner selects the actor domain; the
incumbent Executive Runtime and Session Bridge owners attest current sessions.
Only the existing host can supply the authenticated *current* caller; public
request arguments never carry caller, role, principal or provider coordinates.
No message commit, queue, worker admission or transport is added here.
"""
from __future__ import annotations

from collections.abc import Callable
import inspect

from control_plane.executive_runtime import Runtime
from control_plane.fabric_coordination_policy import (
    CoordinationActorIdentity, CoordinationIdentity, CoordinationNativeIdentity,
    CoordinationRefused, CoordinationSnapshot, authorize_coordination,
)
from integrations.fabric_coordination_composite import CompositeCoordinationObservationSource
from integrations.fabric_coordination_native import NativeCoordinationObservationSource
from integrations.fabric_coordination_runtime import RuntimeCoordinationObservationSource
from integrations.fabric_coordination_single import SingleDomainCoordinationObservationSource
from integrations.fabric_coordination_targets import (
    ScopedSessionTarget, ScopedSessionTargetResolver,
    _grant_digest, _authorization_context_digest,
)
from integrations.session_bridge.claude_native import ClaudeNativeTargetProjector
from integrations.session_bridge.runtime_owner import RuntimeFabricTargetProjector


class ScopedHostUnavailable(CoordinationRefused):
    """One opaque refusal across all unavailable or stale owner facts."""


def _refuse() -> None:
    raise ScopedHostUnavailable("SCOPED_COORDINATION_HOST_UNAVAILABLE")


def _domain(snapshot: CoordinationSnapshot) -> str:
    if type(snapshot) is not CoordinationSnapshot:
        _refuse()
    # Dormant records remain in the attested organizational scope but must
    # not demand an unused provider backend. Any dormant member becoming
    # active changes the domain and is checked again after target discovery.
    actors = {type(p.identity) for p in snapshot.participants if p.active}
    if not actors or not actors <= {CoordinationIdentity, CoordinationNativeIdentity}:
        _refuse()
    if actors == {CoordinationIdentity}:
        return "worker"
    if actors == {CoordinationNativeIdentity}:
        return "native"
    return "mixed"


class AuthenticatedScopedTargetHost:
    """Read-only selected composition with freshly authenticated caller facts.

    The installed transport and authorization owner must still enforce current
    scope, principal and exact writer at the actual message COMMIT boundary.
    A valid target is evidence for discovery, never a bearer send capability.
    """

    def __init__(
        self, *,
        membership_reader: Callable[[], CoordinationSnapshot],
        authenticated_caller_reader: Callable[[], CoordinationActorIdentity],
        topic_ref: str,
        now: Callable[[], int],
        runtime: Runtime | None = None,
        worker_targets: RuntimeFabricTargetProjector | None = None,
        native_targets: ClaudeNativeTargetProjector | None = None,
        native_principal_reader: Callable[[str, str], str] | None = None,
    ) -> None:
        if any(
            not callable(v) or inspect.iscoroutinefunction(v)
            for v in (membership_reader, authenticated_caller_reader, now)
        ):
            raise TypeError("synchronous host-owned membership, caller and time required")
        if type(topic_ref) is not str or not topic_ref:
            raise TypeError("host-selected exact topic required")
        # Selection happens from the existing organizational owner. Never
        # downgrade a mixed scope when one modality's transport is unavailable.
        scope = membership_reader()
        domain = _domain(scope)
        uses_workers = domain in {"worker", "mixed"}
        uses_native = domain in {"native", "mixed"}
        if (
            (uses_workers and not isinstance(runtime, Runtime))
            or (uses_native and type(native_targets) is not ClaudeNativeTargetProjector)
            or (uses_native and not callable(native_principal_reader))
            or (not uses_workers and (runtime is not None or worker_targets is not None))
            or (not uses_native and (native_targets is not None or native_principal_reader is not None))
        ):
            raise TypeError("missing or unexpected incumbent owner for admitted domain")
        if uses_workers:
            if worker_targets is None:
                worker_targets = RuntimeFabricTargetProjector(runtime)
            if (
                type(worker_targets) is not RuntimeFabricTargetProjector
                or worker_targets._runtime is not runtime
            ):
                raise TypeError("Runtime target projector must use the incumbent Runtime")
        if domain == "mixed":
            observer = CompositeCoordinationObservationSource(
                runtime=runtime, native_projector=native_targets,
                membership_reader=membership_reader,
                native_principal_reader=native_principal_reader,
            )
        else:
            runtime_observer = (
                RuntimeCoordinationObservationSource(
                    runtime, membership_reader=membership_reader,
                ) if uses_workers else None
            )
            native_observer = (
                NativeCoordinationObservationSource(
                    projector=native_targets, membership_reader=membership_reader,
                    principal_reader=native_principal_reader, now=now,
                ) if uses_native else None
            )
            observer = SingleDomainCoordinationObservationSource(
                membership_reader=membership_reader, now=now,
                runtime_source=runtime_observer, native_source=native_observer,
            )
        self._domain = domain
        self._memberships = membership_reader
        self._authenticated_caller = authenticated_caller_reader
        self._now = now
        self._topic = topic_ref
        self._owner = observer
        self._workers = worker_targets
        self._native = native_targets

    def _resolver(self) -> ScopedSessionTargetResolver:
        try:
            # Fresh auth on EVERY read. Never persist an earlier principal or
            # silently switch modes after organizational membership changes.
            scope = self._memberships()
            if _domain(scope) != self._domain:
                _refuse()
            caller = self._authenticated_caller()
            if type(caller) not in (CoordinationIdentity, CoordinationNativeIdentity):
                _refuse()
            now = self._now()
            if type(now) is not int:
                _refuse()
            scope.participant(caller, now=now)
            return ScopedSessionTargetResolver(
                owner=self._owner, worker_targets=self._workers,
                native_targets=self._native, caller=caller,
                topic_ref=self._topic, now=self._now,
            )
        except Exception:
            _refuse()

    def _verify_caller_after_read(
        self, resolver: ScopedSessionTargetResolver,
        targets: tuple[ScopedSessionTarget, ...],
    ) -> None:
        # A caller, grant or parent relation can change AFTER the last target
        # projector read. Revalidate both ends of each selected advisory edge
        # against the final fresh organizational owner scope, not just the
        # caller's presence. This is a read-only privacy fence, NOT COMMIT.
        current = self._authenticated_caller()
        scope = self._memberships()
        now = self._now()
        if (
            type(current) not in (CoordinationIdentity, CoordinationNativeIdentity)
            or current != resolver._caller
            or _domain(scope) != self._domain
            or type(now) is not int
        ):
            _refuse()
        scope.participant(current, now=now)
        for target in targets:
            current_recipient = scope.participant(target.recipient, now=now)
            decision = authorize_coordination(
                scope, current, target.recipient,
                topic_ref=self._topic, now=now,
            )
            if (
                current_recipient.role is not target.role
                or decision.relation != target.relation
                or decision.grant_ref != target.grant_ref
                or _grant_digest(scope, decision.grant_ref) != target.grant_digest
                or _authorization_context_digest(
                    scope, current, target.recipient, self._topic,
                ) != target.authorization_context_digest
            ):
                _refuse()

    def visible_targets(self) -> tuple[dict[str, str | bool], ...]:
        try:
            resolver = self._resolver()
            selected = resolver._read()
            self._verify_caller_after_read(resolver, selected)
            return tuple(target.public_projection() for target in selected)
        except Exception:
            _refuse()

    def resolve(self, target_ref: str) -> ScopedSessionTarget:
        try:
            if type(target_ref) is not str:
                _refuse()
            resolver = self._resolver()
            target = resolver.resolve(target_ref)
            self._verify_caller_after_read(resolver, (target,))
            return target
        except Exception:
            _refuse()
