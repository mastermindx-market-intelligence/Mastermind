"""Scoped peer messaging on the existing four-tool Company consultation facet.

No endpoint, credential, identity registry, queue, message store or retry loop is
created here. The installed authenticated host supplies current Runtime facts and
its existing dispatcher. A public caller cannot select its role or membership.
The incumbent effect owner must still fence its own commit and native delivery.
"""
from __future__ import annotations

import contextvars
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Any

from control_plane.fabric_coordination_policy import (
    CoordinationIdentity, CoordinationRefused, CoordinationSnapshot,
    MAX_PARTICIPANTS, authorize_coordination,
)
from integrations.mastermind_company_mcp.consultation import CompanyConsultationGateway
from integrations.slack_agent_dialogue.company_consultation_peer_resolver import (
    CompanyConsultationPeerResolver, ConsultationPeer, ConsultationPeerRefused,
)

_PEER_REF = re.compile(r"peer-[0-9a-f]{32}\Z", re.ASCII)
_CONSULT_REF = re.compile(r"consult-[0-9a-f]{32}\Z", re.ASCII)


def _identity(peer: ConsultationPeer) -> CoordinationIdentity:
    if type(peer) is not ConsultationPeer:
        raise CoordinationRefused("INVALID_OWNER_FACTS")
    CompanyConsultationPeerResolver._validate(peer)
    if set(peer.actor_ref) != {"kind", "job_id", "attempt_id", "worker_id"}:
        raise CoordinationRefused("INVALID_OWNER_FACTS")
    return CoordinationIdentity(
        peer.actor_ref["job_id"], peer.actor_ref["attempt_id"],
        peer.actor_ref["worker_id"], peer.binding["binding_id"],
        peer.binding["binding_generation"],
    )


def _freeze_peer(peer: ConsultationPeer) -> ConsultationPeer:
    _identity(peer)
    if type(peer.display_name) is not str or not 1 <= len(peer.display_name) <= 128 or not peer.display_name.isprintable():
        raise CoordinationRefused("INVALID_OWNER_FACTS")
    return ConsultationPeer(
        peer.peer_ref, peer.display_name, peer.program_ref,
        MappingProxyType(dict(peer.actor_ref)), MappingProxyType(dict(peer.binding)),
    )


@dataclass(frozen=True, slots=True)
class CoordinationObservation:
    """One coherent owner observation. Not accepted from a tool argument."""
    snapshot: CoordinationSnapshot
    peers: tuple[ConsultationPeer, ...]

    def __post_init__(self) -> None:
        if type(self.snapshot) is not CoordinationSnapshot or type(self.peers) is not tuple or len(self.peers) > MAX_PARTICIPANTS:
            raise CoordinationRefused("INVALID_OWNER_FACTS")
        peers = tuple(_freeze_peer(peer) for peer in self.peers)
        if len({peer.peer_ref for peer in peers}) != len(peers) or len({_identity(peer) for peer in peers}) != len(peers):
            raise CoordinationRefused("AMBIGUOUS_OWNER_FACTS")
        object.__setattr__(self, "peers", peers)


@dataclass(frozen=True, slots=True)
class CoordinationConsultationParties:
    consultation_ref: str
    requester: CoordinationIdentity
    recipient: CoordinationIdentity
    topic_ref: str

    def __post_init__(self) -> None:
        if type(self.consultation_ref) is not str or _CONSULT_REF.fullmatch(self.consultation_ref) is None:
            raise CoordinationRefused("INVALID_OWNER_FACTS")
        if type(self.requester) is not CoordinationIdentity or type(self.recipient) is not CoordinationIdentity or self.requester == self.recipient:
            raise CoordinationRefused("INVALID_OWNER_FACTS")
        if type(self.topic_ref) is not str or not self.topic_ref:
            raise CoordinationRefused("INVALID_OWNER_FACTS")


@dataclass(frozen=True, slots=True)
class _Selection:
    peer_ref: str
    identity: CoordinationIdentity


class HierarchyScopedPeerResolver:
    """Request-local authorization using current, authenticated owner observations."""

    def __init__(
        self, *, caller: CoordinationIdentity, program_ref: str, topic_ref: str,
        observe: Callable[[], CoordinationObservation],
        consultation_parties: Callable[[str], CoordinationConsultationParties],
        now: Callable[[], int],
    ) -> None:
        if type(caller) is not CoordinationIdentity or not all(callable(value) for value in (observe, consultation_parties, now)):
            raise TypeError("authenticated owner identity and readers are required")
        if type(program_ref) is not str or not program_ref or type(topic_ref) is not str or not topic_ref:
            raise TypeError("owner-bound program and topic are required")
        self.caller = caller
        self.program_ref = program_ref
        self.topic_ref = topic_ref
        self._observe = observe
        self._consultation_parties = consultation_parties
        self._now = now
        self._selection: contextvars.ContextVar[_Selection | None] = contextvars.ContextVar("coordination_selection", default=None)

    def _current(self, program_ref: str) -> tuple[CoordinationObservation, int]:
        if program_ref != self.program_ref:
            raise CoordinationRefused("CALLER_SCOPE_MISMATCH")
        observation = self._observe()
        if type(observation) is not CoordinationObservation:
            raise CoordinationRefused("INVALID_OWNER_FACTS")
        now = self._now()
        caller = observation.snapshot.participant(self.caller, now=now)
        if caller.program_ref != self.program_ref:
            raise CoordinationRefused("CALLER_SCOPE_MISMATCH")
        return observation, now

    def _allowed(self, observation: CoordinationObservation, peer: ConsultationPeer, now: int) -> None:
        identity = _identity(peer)
        participant = observation.snapshot.participant(identity, now=now)
        if participant.program_ref != peer.program_ref:
            raise CoordinationRefused("PEER_SCOPE_MISMATCH")
        authorize_coordination(observation.snapshot, self.caller, identity, topic_ref=self.topic_ref, now=now)

    def visible_peers(self, *, program_ref: str) -> tuple[ConsultationPeer, ...]:
        try:
            observation, now = self._current(program_ref)
            permitted = []
            for peer in observation.peers:
                try:
                    self._allowed(observation, peer, now)
                except CoordinationRefused:
                    continue
                permitted.append(peer)
            return tuple(sorted(permitted, key=lambda peer: peer.peer_ref))
        except Exception:
            raise ConsultationPeerRefused("BINDING_UNAVAILABLE") from None

    def _resolve_current(self, alias: str, *, program_ref: str) -> ConsultationPeer:
        if type(alias) is not str or _PEER_REF.fullmatch(alias) is None:
            raise CoordinationRefused("PEER_UNAVAILABLE")
        observation, now = self._current(program_ref)
        matches = [peer for peer in observation.peers if peer.peer_ref == alias]
        if len(matches) != 1:
            raise CoordinationRefused("PEER_UNAVAILABLE")
        self._allowed(observation, matches[0], now)
        return matches[0]

    def resolve(self, alias: str, *, program_ref: str) -> ConsultationPeer:
        try:
            peer = self._resolve_current(alias, program_ref=program_ref)
            self._selection.set(_Selection(peer.peer_ref, _identity(peer)))
            return peer
        except Exception:
            self._selection.set(None)
            raise ConsultationPeerRefused("BINDING_UNAVAILABLE") from None

    def before_dispatch(self, tool_name: str, request: Mapping[str, Any]) -> None:
        """Recheck after discovery and before invoking the incumbent dispatcher.

        This is not a reusable capability or the effect owner's transaction fence.
        Unknown owner facts and rejected calls never invoke the dispatcher.
        """
        try:
            if tool_name == "company.consult":
                selected = self._selection.get()
                target = request["semantic"]["to"]
                if selected is None or selected.peer_ref != target:
                    raise CoordinationRefused("SELECTION_UNAVAILABLE")
                current = self._resolve_current(target, program_ref=self.program_ref)
                if _identity(current) != selected.identity:
                    raise CoordinationRefused("TARGET_CHANGED")
                return
            if tool_name not in {"company.reply", "company.consultation"}:
                raise CoordinationRefused("UNSUPPORTED_OPERATION")
            reference = request["semantic"]["consultation_ref"]
            parties = self._consultation_parties(reference)
            if type(parties) is not CoordinationConsultationParties or parties.consultation_ref != reference or parties.topic_ref != self.topic_ref:
                raise CoordinationRefused("CONSULTATION_UNAVAILABLE")
            if self.caller not in (parties.requester, parties.recipient):
                raise CoordinationRefused("CONSULTATION_UNAVAILABLE")
            if tool_name == "company.reply" and self.caller != parties.recipient:
                raise CoordinationRefused("CONSULTATION_UNAVAILABLE")
            observation, now = self._current(self.program_ref)
            authorize_coordination(observation.snapshot, parties.requester, parties.recipient, topic_ref=self.topic_ref, now=now)
        except Exception:
            raise ConsultationPeerRefused("BINDING_UNAVAILABLE") from None


class HierarchyCompanyConsultationGateway(CompanyConsultationGateway):
    """Existing wire contract with scoped discovery, sending, replies and reads."""

    def __init__(
        self, *, peer_resolver: HierarchyScopedPeerResolver,
        dispatcher: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
        observed_tool_schema_digest: str, utc_now: Callable[[], str],
    ) -> None:
        if type(peer_resolver) is not HierarchyScopedPeerResolver:
            raise TypeError("hierarchy resolver is required")
        super().__init__(
            peer_resolver=peer_resolver, dispatcher=dispatcher,
            observed_tool_schema_digest=observed_tool_schema_digest,
            utc_now=utc_now, program_ref=peer_resolver.program_ref,
            before_dispatch=peer_resolver.before_dispatch,
        )

    async def call(self, tool_name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        token = self.peer_resolver._selection.set(None)
        try:
            return await super().call(tool_name, arguments)
        finally:
            self.peer_resolver._selection.reset(token)
