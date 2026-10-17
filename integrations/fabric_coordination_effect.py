"""Advisory hierarchy revalidation hook for the EXISTING message effect owner.

This module does not own, begin, commit, retry, or publish a transaction.
The incumbent consultation/dialogue owner must call this validation *inside*
its current-writer-fenced COMMIT operation, immediately before mutation;
it must also check its canonical message and sender/recipient binding. No
read-only target proof is a bearer authorization to dispatch.
"""
from __future__ import annotations

from control_plane.fabric_coordination_policy import (
    CoordinationActorIdentity, CoordinationIdentity,
    CoordinationNativeIdentity, CoordinationRefused,
)
from integrations.fabric_coordination_host import AuthenticatedScopedTargetHost
from integrations.fabric_coordination_targets import ScopedSessionTarget


class ScopedEffectRefused(CoordinationRefused):
    """Uniform rejection; do not disclose a foreign target or live session."""


def _refuse() -> None:
    raise ScopedEffectRefused("SCOPED_EFFECT_UNAVAILABLE")


class HierarchyEffectOwnerGuard:
    """Recheck a pinned advisory edge at the incumbent owner's effect boundary.

    The original sender and target are immutable host-owned observations from
    the accepted consultation intent, not public arguments or a cached model
    choice. Call verification for *each* canonical effect, including reply
    and read/consumption as appropriate; the existing owner is responsible
    for the persisted consultation's original parties and operation identity.

    The guard alone cannot make two independent owner reads transaction-atomic.
    It intentionally exposes no send/write/commit operation and no receipt.
    """

    def __init__(
        self, *,
        host: AuthenticatedScopedTargetHost,
        original_sender: CoordinationActorIdentity,
        original_target: ScopedSessionTarget,
        original_topic_ref: str,
    ) -> None:
        if (
            type(host) is not AuthenticatedScopedTargetHost
            or type(original_sender) not in (CoordinationIdentity, CoordinationNativeIdentity)
            or type(original_target) is not ScopedSessionTarget
            or original_sender == original_target.recipient
            or type(original_topic_ref) is not str or original_topic_ref != host._topic
        ):
            raise TypeError("canonical accepted sender, target and topic are required")
        self._host = host
        self._sender = original_sender
        self._recipient = original_target

    def verify_inside_owner_effect(self) -> None:
        """Fail unless exact sender/recipient, relation and grant still match.

        Must be invoked UNDER the incumbent's live writer/authorization fence;
        this does not open or hold the owner's transaction.
        """
        try:
            # Host.resolve uses current authenticated caller, organizational
            # scope, Runtime/native owner and exact Session Bridge reference.
            # Its own after-read callback refuses mid-lookup caller rotation.
            current = self._host.resolve(self._recipient.target_ref)
            if (
                self._host._authenticated_caller() != self._sender
                or current.target_ref != self._recipient.target_ref
                or current.recipient != self._recipient.recipient
                or current.role is not self._recipient.role
                or current.relation != self._recipient.relation
                or current.authorization_context_digest
                != self._recipient.authorization_context_digest
                or current.grant_ref != self._recipient.grant_ref
                or current.grant_digest != self._recipient.grant_digest
            ):
                _refuse()
            # Owner scope is short-lived and legitimately refreshed during
            # a long bounded task. A fresh, currently permitted observation
            # can extend the window; never use the ORIGINAL expired scope as
            # a cached authorization. An exact grant's immutable payload is
            # still pinned by grant_digest across observations. The existing
            # owner verifies persisted consultation and operation correlation.
        except Exception:
            _refuse()
