"""One-owner hierarchy evidence for native-only or Runtime-only coordination.

An inactive layer must not disable peer discovery in another layer. Reuse the
same canonical owner observations as mixed mode, without forging a missing
session, launching a worker, or treating a member list as a bearer permission.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, replace
import hashlib
import json

from control_plane.fabric_coordination_policy import (
    CoordinationIdentity, CoordinationNativeIdentity, CoordinationRefused,
    CoordinationSnapshot,
)
from integrations.fabric_coordination_composite import CompositeCoordinationEvidence
from integrations.fabric_coordination_native import (
    NativeCoordinationObservationSource, NativeCoordinationAttestation,
    native_membership_digest,
)
from integrations.fabric_coordination_runtime import (
    RuntimeCoordinationObservationSource, CoordinationObservation,
)


class SingleDomainCoordinationUnavailable(CoordinationRefused):
    """Opaque refusal, not a session-missing disclosure."""


def _refuse() -> None:
    raise SingleDomainCoordinationUnavailable("SINGLE_DOMAIN_COORDINATION_UNAVAILABLE")


class SingleDomainCoordinationObservationSource:
    """Attest one populated, single-kind host scope using its incumbent owner.

    This source does not fallback on a failed mixed observation. Its domain
    is a host-construction fact: it refuses unexpected native/worker identities
    instead of treating the other owner as missing or unimportant.
    """

    def __init__(
        self, *,
        membership_reader: Callable[[], CoordinationSnapshot],
        now: Callable[[], int],
        runtime_source: RuntimeCoordinationObservationSource | None = None,
        native_source: NativeCoordinationObservationSource | None = None,
    ) -> None:
        if not callable(membership_reader) or not callable(now):
            raise TypeError("canonical host membership and time readers are required")
        if (type(runtime_source) is RuntimeCoordinationObservationSource) == (
            type(native_source) is NativeCoordinationObservationSource
        ):
            raise TypeError("exactly one incumbent identity owner must be selected")
        self._membership = membership_reader
        self._now = now
        self._runtime = runtime_source
        self._native = native_source
        self.domain = "worker" if runtime_source is not None else "native"

    def _scope(self) -> CoordinationSnapshot:
        scope = self._membership()
        if type(scope) is not CoordinationSnapshot:
            _refuse()
        expected_type = CoordinationIdentity if self.domain == "worker" else CoordinationNativeIdentity
        if (
            not any(p.active for p in scope.participants)
            or any(p.active and type(p.identity) is not expected_type
                   for p in scope.participants)
        ):
            _refuse()
        # Do not discard inactive identities/grants: their full original
        # membership bytes remain bound to this source's attestation.
        return scope

    def _attest(self, scope: CoordinationSnapshot):
        if self.domain == "worker":
            result = self._runtime.observe()
            if type(result) is not CoordinationObservation:
                _refuse()
            snapshot = result.snapshot
            if (
                snapshot.participants != scope.participants
                or snapshot.grants != scope.grants
                or snapshot.observed_at != scope.observed_at
                or snapshot.valid_until > scope.valid_until
                or len(result.peers) != sum(p.active for p in scope.participants)
            ):
                _refuse()
            peer_refs = tuple(sorted(peer.peer_ref for peer in result.peers))
            if len(peer_refs) != len(set(peer_refs)) or not peer_refs:
                _refuse()
            return peer_refs, (), snapshot.valid_until
        result = self._native.observe()
        if type(result) is not NativeCoordinationAttestation:
            _refuse()
        identities = tuple(p.identity for p in scope.participants if p.active)
        if (
            set(result.identities) != set(identities)
            or len(result.identities) != len(identities)
            or not identities
            or result.snapshot_revision != scope.revision
            or result.membership_digest != native_membership_digest(scope)
            or result.observed_at != scope.observed_at
            or result.valid_until > scope.valid_until
        ):
            _refuse()
        return (), result.identities, result.valid_until

    def observe(self) -> CompositeCoordinationEvidence:
        try:
            original = self._scope()
            now = self._now()
            if type(now) is not int or not original.observed_at <= now < original.valid_until:
                _refuse()
            peers, natives, validity = self._attest(original)
            refreshed = self._scope()
            then = self._now()
            if (
                original.revision != refreshed.revision
                or original.participants != refreshed.participants
                or original.grants != refreshed.grants
                or type(then) is not int
                or not original.observed_at <= then < original.valid_until
                or not refreshed.observed_at <= then < refreshed.valid_until
            ):
                _refuse()
            next_peers, next_natives, next_validity = self._attest(refreshed)
            checked = self._scope()
            finish = self._now()
            expiry = min(
                original.valid_until, refreshed.valid_until,
                checked.valid_until, validity, next_validity,
            )
            if (
                peers != next_peers
                or natives != next_natives
                or original.revision != checked.revision
                or original.participants != checked.participants
                or original.grants != checked.grants
                or type(finish) is not int
                or not original.observed_at <= finish < expiry
                or not checked.observed_at <= finish < checked.valid_until
            ):
                _refuse()
            digest_source = json.dumps({
                "domain": self.domain,
                "membership": asdict(original),
                "peers": peers,
                "native": [asdict(actor) for actor in natives],
                "expires": expiry,
            }, sort_keys=True, separators=(",", ":")).encode()
            return CompositeCoordinationEvidence(
                snapshot=replace(original, valid_until=expiry),
                worker_peer_refs=peers,
                native_ids=natives,
                evidence_digest=hashlib.sha256(digest_source).hexdigest(),
            )
        except SingleDomainCoordinationUnavailable:
            raise
        except Exception:
            _refuse()
