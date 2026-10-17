"""Compose two existing identity owners for mixed native/Runtime hierarchy policy.

The Runtime owner attests Job/Attempt/OHF-backed workers. The installed native
management owner attests canonical CEO/COO sessions plus the authenticated
host's principal refs. A *single* host-supplied membership scope is checked
before, during and after the joins. No endpoint, session registry, token, queue,
message store, transport, sender authorization or lifecycle is created here.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
import hashlib
import json

from control_plane.executive_runtime import Runtime
from control_plane.fabric_coordination_policy import (
    CoordinationIdentity, CoordinationNativeIdentity,
    CoordinationRefused, CoordinationSnapshot,
)
from integrations.fabric_coordination_native import (
    NativeCoordinationObservationSource, native_membership_digest,
)
from integrations.fabric_coordination_runtime import RuntimeCoordinationObservationSource
from integrations.session_bridge.claude_native import ClaudeNativeTargetProjector


class CompositeCoordinationUnavailable(CoordinationRefused):
    """One opaque failure boundary for incomplete/mutated owner facts."""


def _refuse() -> None:
    raise CompositeCoordinationUnavailable("COMPOSITE_COORDINATION_UNAVAILABLE")


@dataclass(frozen=True, slots=True)
class CompositeCoordinationEvidence:
    """Read-only admitted membership; NOT an authenticated sender or bearer grant."""
    snapshot: CoordinationSnapshot
    worker_peer_refs: tuple[str, ...]
    native_ids: tuple[CoordinationNativeIdentity, ...]
    evidence_digest: str

    def __post_init__(self) -> None:
        if (
            type(self.snapshot) is not CoordinationSnapshot
            or type(self.worker_peer_refs) is not tuple
            or any(type(x) is not str for x in self.worker_peer_refs)
            or type(self.native_ids) is not tuple
            or any(type(x) is not CoordinationNativeIdentity for x in self.native_ids)
            or type(self.evidence_digest) is not str
            or len(self.evidence_digest) != 64
        ):
            _refuse()


class CompositeCoordinationObservationSource:
    """Attest one mixed scope with existing Runtime and native management owners.

    This object cannot authorize a provider operation. The installed host still
    authenticates the sender and enforces a fresh authorization at the canonical
    commit boundary. Native transport enrollment/consumption is separate.
    """

    def __init__(
        self, *, runtime: Runtime,
        native_projector: ClaudeNativeTargetProjector,
        membership_reader: Callable[[], CoordinationSnapshot],
        native_principal_reader: Callable[[str, str], str],
    ) -> None:
        if (
            not isinstance(runtime, Runtime)
            or type(native_projector) is not ClaudeNativeTargetProjector
            or not callable(membership_reader)
            or not callable(native_principal_reader)
        ):
            raise TypeError("existing Runtime and native owner readers required")
        self._runtime = runtime
        self._native_projector = native_projector
        self._memberships = membership_reader
        self._principals = native_principal_reader

    def _scope(self) -> CoordinationSnapshot:
        snapshot = self._memberships()
        if type(snapshot) is not CoordinationSnapshot:
            _refuse()
        return snapshot

    def _subset(self, native: bool) -> CoordinationSnapshot:
        scope = self._scope()
        selected = tuple(p for p in scope.participants
                         if (type(p.identity) is CoordinationNativeIdentity) == native)
        if not selected:
            _refuse()
        return replace(scope, participants=selected)

    def observe(self) -> CompositeCoordinationEvidence:
        try:
            original = self._scope()
            now = self._runtime.store.now_ms() // 1000
            if not original.observed_at <= now < original.valid_until:
                _refuse()

            runtime_source = RuntimeCoordinationObservationSource(
                self._runtime, membership_reader=lambda: self._subset(False),
            )
            native_source = NativeCoordinationObservationSource(
                projector=self._native_projector,
                membership_reader=lambda: self._subset(True),
                principal_reader=self._principals, now=runtime_source.now,
            )
            workers = runtime_source.observe()
            native = native_source.observe()
            native_scope = replace(
                original, participants=tuple(
                    p for p in original.participants
                    if type(p.identity) is CoordinationNativeIdentity
                ),
            )
            if native.membership_digest != native_membership_digest(native_scope):
                _refuse()

            # Two independent joins are not atomic. No evidence is usable if
            # the organizational owner changes during either read.
            final = self._scope()
            end = runtime_source.now()
            if (
                original.revision != final.revision
                or original.participants != final.participants
                or original.grants != final.grants
                or not original.observed_at <= end < original.valid_until
                or not final.observed_at <= end < final.valid_until
            ):
                _refuse()
            current_workers = tuple(p for p in final.participants if p.active
                                    and type(p.identity) is CoordinationIdentity)
            current_native = tuple(p.identity for p in final.participants if p.active
                                   and type(p.identity) is CoordinationNativeIdentity)
            if (
                len(workers.peers) != len(current_workers)
                or set(native.identities) != set(current_native)
                or native.valid_until < end + 1
                or workers.snapshot.valid_until < end + 1
            ):
                _refuse()

            # A worker could rotate while the native source is checked;
            # conversely a native session can rotate while Runtime is reread.
            # Observe each owner again and require its exact attested identity.
            # This is best-effort read consistency, NOT an atomic commit fence.
            rechecked_workers = runtime_source.observe()
            if (
                rechecked_workers.snapshot.revision != workers.snapshot.revision
                or tuple(sorted(p.peer_ref for p in rechecked_workers.peers))
                != tuple(sorted(p.peer_ref for p in workers.peers))
            ):
                _refuse()
            rechecked_native = native_source.observe()
            if (
                rechecked_native.snapshot_revision != native.snapshot_revision
                or rechecked_native.membership_digest != native.membership_digest
                or rechecked_native.identities != native.identities
            ):
                _refuse()
            checked = self._scope()
            last_now = runtime_source.now()
            if (
                checked.revision != original.revision
                or checked.participants != original.participants
                or checked.grants != original.grants
                or not original.observed_at <= last_now < original.valid_until
                or not checked.observed_at <= last_now < checked.valid_until
                or rechecked_native.valid_until <= last_now
                or rechecked_workers.snapshot.valid_until <= last_now
            ):
                _refuse()
            # All returned roles/identity pairs come from one active owner scope
            # and two independently verified current implementation sources.
            # This digest is evidence, not a reusable capability or token.
            native_names = sorted(
                [x.session_id, x.generation, x.host_ref, x.principal_ref]
                for x in native.identities
            )
            worker_refs = tuple(sorted(p.peer_ref for p in workers.peers))
            document = json.dumps({
                "owner_scope": asdict(original),
                "worker_snapshot": workers.snapshot.revision,
                "native_ids": native_names,
                "worker_refs": worker_refs,
                "scope_time": [original.observed_at, original.valid_until],
            }, sort_keys=True, separators=(",", ":")).encode()
            return CompositeCoordinationEvidence(
                snapshot=replace(original, valid_until=min(
                    original.valid_until, final.valid_until, checked.valid_until,
                    native.valid_until, rechecked_native.valid_until,
                    workers.snapshot.valid_until, rechecked_workers.snapshot.valid_until,
                )),
                worker_peer_refs=worker_refs,
                native_ids=native.identities,
                evidence_digest=hashlib.sha256(document).hexdigest(),
            )
        except CompositeCoordinationUnavailable:
            raise
        except Exception:
            _refuse()
