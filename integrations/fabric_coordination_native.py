"""Read-only native CEO/COO membership join to the existing Claude owner.

The authenticated composition host provides both canonical organizational scope
and the verified-principal observation for one exact provider session. Session
management remains with the existing Session Bridge Claude management port.
This join cannot send, start, enroll, wake, or authorize a provider session;
a native attestation alone is not a Company consultation dispatch capability.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
import hashlib
import inspect
import json
import re

from control_plane.fabric_coordination_policy import (
    CoordinationNativeIdentity, CoordinationRefused, CoordinationSnapshot,
)
from integrations.session_bridge.claude_native import (
    ClaudeNativeTarget, ClaudeNativeTargetProjector,
)


class NativeCoordinationUnavailable(CoordinationRefused):
    """Opaque refusal; never disclose sessions, principals or manager details."""


def _refuse() -> None:
    raise NativeCoordinationUnavailable("NATIVE_COORDINATION_UNAVAILABLE")


def native_membership_digest(scope: CoordinationSnapshot) -> str:
    """Bind an attestation to full owner facts, not a mutable revision label."""
    if type(scope) is not CoordinationSnapshot:
        _refuse()
    payload = json.dumps(asdict(scope), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class NativeCoordinationAttestation:
    """Per-read exact native owners, not a persistent registry or bearer grant."""
    snapshot_revision: str
    observed_at: int
    valid_until: int
    identities: tuple[CoordinationNativeIdentity, ...]
    membership_digest: str

    def __post_init__(self) -> None:
        if (
            type(self.snapshot_revision) is not str
            or not self.snapshot_revision
            or type(self.observed_at) is not int
            or type(self.valid_until) is not int
            or self.valid_until <= self.observed_at
            or type(self.membership_digest) is not str
            or re.fullmatch(r"[0-9a-f]{64}", self.membership_digest) is None
            or type(self.identities) is not tuple
            or not self.identities
            or any(type(identity) is not CoordinationNativeIdentity
                   for identity in self.identities)
        ):
            _refuse()


class NativeCoordinationObservationSource:
    """Join native membership to exact current Session Bridge management facts.

    No caller-supplied identity, role, host, latest-session alias, or arbitrary
    JSON file is a source of authority. All injected readers belong to the
    installed authenticated host; their availability is NOT attested by Python
    type checks. The host must also validate write authorization at its effect
    boundary and independently enroll a supported native dialogue consumer.
    """

    def __init__(
        self, *, projector: ClaudeNativeTargetProjector,
        membership_reader: Callable[[], CoordinationSnapshot],
        principal_reader: Callable[[str, str], str],
        now: Callable[[], int],
    ) -> None:
        if (
            type(projector) is not ClaudeNativeTargetProjector
            or not all(callable(fn) for fn in (membership_reader, principal_reader, now))
            or inspect.iscoroutinefunction(membership_reader)
            or inspect.iscoroutinefunction(principal_reader)
            or inspect.iscoroutinefunction(now)
        ):
            raise TypeError("synchronous admitted native source readers are required")
        self._projector = projector
        self._memberships = membership_reader
        self._principals = principal_reader
        self._now = now

    def _projected_targets(self) -> dict[tuple[str, str], ClaudeNativeTarget]:
        targets = self._projector.list_targets()
        if not isinstance(targets, list) or len(targets) > 256:
            _refuse()
        result: dict[tuple[str, str], ClaudeNativeTarget] = {}
        for target in targets:
            if type(target) is not ClaudeNativeTarget:
                _refuse()
            key = (target.host_ref, target.session_id)
            if key in result:
                _refuse()
            result[key] = target
        return result

    def _verify_members(self, snapshot, targets):
        current: list[CoordinationNativeIdentity] = []
        for participant in snapshot.participants:
            identity = participant.identity
            if type(identity) is not CoordinationNativeIdentity:
                # Only attest native members. Runtime members need their
                # independent, existing current Job/Attempt/OHF owner.
                continue
            if not participant.active:
                continue
            target = targets.get((identity.host_ref, identity.session_id))
            if target is None or target.generation != identity.generation:
                _refuse()
            resolved = self._projector.resolve(target.target_ref)
            if type(resolved) is not ClaudeNativeTarget or resolved != target:
                _refuse()
            principal = self._principals(identity.session_id, identity.host_ref)
            if type(principal) is not str or principal != identity.principal_ref:
                _refuse()
            current.append(identity)
        if not current:
            _refuse()
        return tuple(current)

    def observe(self) -> NativeCoordinationAttestation:
        try:
            initial = self._memberships()
            if type(initial) is not CoordinationSnapshot:
                _refuse()
            now = self._now()
            if type(now) is not int or not initial.observed_at <= now < initial.valid_until:
                _refuse()
            first_targets = self._projected_targets()
            identities = self._verify_members(initial, first_targets)
            refreshed = self._memberships()
            then = self._now()
            if (
                type(refreshed) is not CoordinationSnapshot
                or initial.revision != refreshed.revision
                or initial.participants != refreshed.participants
                or initial.grants != refreshed.grants
                or type(then) is not int
                or not initial.observed_at <= then < initial.valid_until
                or not refreshed.observed_at <= then < refreshed.valid_until
            ):
                _refuse()
            second_targets = self._projected_targets()
            if first_targets != second_targets:
                _refuse()
            second = self._verify_members(refreshed, second_targets)
            if second != identities:
                _refuse()
            return NativeCoordinationAttestation(
                initial.revision, initial.observed_at,
                min(initial.valid_until, refreshed.valid_until),
                identities,
                native_membership_digest(initial),
            )
        except NativeCoordinationUnavailable:
            raise
        except Exception:
            _refuse()
