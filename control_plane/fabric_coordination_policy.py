"""Hierarchy policy over owner-supplied Runtime facts; no registry or transport.

Only the authenticated host may construct these observations. A role, identity,
relationship or grant supplied in a model tool argument is never an observation.
This module does not authorize operational effects, impersonation or forwarding.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from uuid import UUID


class CoordinationRefused(ValueError):
    """Closed, non-sensitive policy refusal; never disclose hidden peers."""


class CoordinationRole(str, Enum):
    PROJECT_CEO = "project_ceo"
    COO = "coo"
    TASK_OPERATOR = "task_operator"
    WORKER = "worker"


_ORDER = {role: index for index, role in enumerate(CoordinationRole)}
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z", re.ASCII)
MAX_PARTICIPANTS = 512
MAX_GRANTS = 1024
MAX_OBSERVATION_AGE_SECONDS = 30


def _token(value: object, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if type(value) is not str or _TOKEN.fullmatch(value) is None:
        raise CoordinationRefused("INVALID_OWNER_FACTS")


def _integer(value: object, *, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise CoordinationRefused("INVALID_OWNER_FACTS")


@dataclass(frozen=True, slots=True)
class CoordinationIdentity:
    job_id: str
    attempt_id: str
    worker_id: str
    binding_id: str
    binding_generation: int

    def __post_init__(self) -> None:
        for value in (self.job_id, self.attempt_id, self.worker_id, self.binding_id):
            _token(value)
        _integer(self.binding_generation, minimum=1)


@dataclass(frozen=True, slots=True)
class CoordinationNativeIdentity:
    """Host-attested native CEO/COO session; never a synthetic Runtime Job.

    The canonical native session-management/verified-principal owner must
    construct these facts. This class does not discover, authenticate or arm
    a provider session. Generation and principal are part of exact identity.
    """
    session_id: str
    generation: str
    host_ref: str
    principal_ref: str

    def __post_init__(self) -> None:
        if type(self.session_id) is not str:
            raise CoordinationRefused("INVALID_OWNER_FACTS")
        try:
            if str(UUID(self.session_id)) != self.session_id:
                raise ValueError("noncanonical UUID")
        except (ValueError, TypeError, AttributeError):
            raise CoordinationRefused("INVALID_OWNER_FACTS") from None
        for value in (self.generation, self.host_ref, self.principal_ref):
            _token(value)


CoordinationActorIdentity = CoordinationIdentity | CoordinationNativeIdentity
_ACTOR_TYPES = (CoordinationIdentity, CoordinationNativeIdentity)


def _actor_identity(value: object) -> bool:
    return type(value) in _ACTOR_TYPES


@dataclass(frozen=True, slots=True)
class CoordinationParticipant:
    identity: CoordinationActorIdentity
    role: CoordinationRole
    tenant_ref: str
    portfolio_ref: str
    project_ref: str
    program_ref: str
    parent_job_id: str | None = None
    workstream_ref: str | None = None
    coordination_group_ref: str | None = None
    active: bool = True
    parent_identity: CoordinationActorIdentity | None = None

    def __post_init__(self) -> None:
        if not _actor_identity(self.identity) or type(self.role) is not CoordinationRole:
            raise CoordinationRefused("INVALID_OWNER_FACTS")
        for value in (self.tenant_ref, self.portfolio_ref, self.project_ref, self.program_ref):
            _token(value)
        for value in (self.parent_job_id, self.workstream_ref, self.coordination_group_ref):
            _token(value, optional=True)
        if (
            type(self.active) is not bool
            or (self.parent_identity is not None and not _actor_identity(self.parent_identity))
            or (self.parent_identity is not None and self.parent_identity == self.identity)
            or (type(self.identity) is CoordinationIdentity
                and self.parent_job_id == self.identity.job_id)
            or (type(self.identity) is CoordinationNativeIdentity
                and (self.role not in {CoordinationRole.PROJECT_CEO, CoordinationRole.COO}
                     or self.parent_job_id is not None))
        ):
            raise CoordinationRefused("INVALID_OWNER_FACTS")
        if self.role in {CoordinationRole.TASK_OPERATOR, CoordinationRole.WORKER} and not self.workstream_ref:
            raise CoordinationRefused("INVALID_OWNER_FACTS")
        if self.role is CoordinationRole.WORKER and not self.coordination_group_ref:
            raise CoordinationRefused("INVALID_OWNER_FACTS")


@dataclass(frozen=True, slots=True)
class CoordinationGrant:
    """An exact-pair, topic-bound observation of an incumbent owner's grant.

    approved_project_refs is evidence read from the existing approval owner,
    never a list accepted from the public caller. No new grant issuer is added.
    """
    grant_ref: str
    first: CoordinationActorIdentity
    second: CoordinationActorIdentity
    topic_ref: str
    approved_project_refs: tuple[str, ...]
    not_before: int
    valid_until: int
    revoked: bool = False

    def __post_init__(self) -> None:
        _token(self.grant_ref)
        _token(self.topic_ref)
        if not _actor_identity(self.first) or not _actor_identity(self.second) or self.first == self.second:
            raise CoordinationRefused("INVALID_OWNER_FACTS")
        if type(self.approved_project_refs) is not tuple or not 1 <= len(self.approved_project_refs) <= 2:
            raise CoordinationRefused("INVALID_OWNER_FACTS")
        for value in self.approved_project_refs:
            _token(value)
        if len(set(self.approved_project_refs)) != len(self.approved_project_refs):
            raise CoordinationRefused("INVALID_OWNER_FACTS")
        _integer(self.not_before)
        _integer(self.valid_until)
        if self.valid_until <= self.not_before or type(self.revoked) is not bool:
            raise CoordinationRefused("INVALID_OWNER_FACTS")


@dataclass(frozen=True, slots=True)
class CoordinationSnapshot:
    """Ephemeral bounded projection of existing owner state, not a new store."""
    revision: str
    observed_at: int
    valid_until: int
    participants: tuple[CoordinationParticipant, ...]
    grants: tuple[CoordinationGrant, ...] = ()

    def __post_init__(self) -> None:
        _token(self.revision)
        _integer(self.observed_at)
        _integer(self.valid_until)
        if not 0 < self.valid_until - self.observed_at <= MAX_OBSERVATION_AGE_SECONDS:
            raise CoordinationRefused("INVALID_OWNER_FACTS")
        if type(self.participants) is not tuple or not 1 <= len(self.participants) <= MAX_PARTICIPANTS:
            raise CoordinationRefused("INVALID_OWNER_FACTS")
        if type(self.grants) is not tuple or len(self.grants) > MAX_GRANTS:
            raise CoordinationRefused("INVALID_OWNER_FACTS")
        jobs: set[str] = set()
        bindings: set[str] = set()
        native_sessions: set[str] = set()
        actor_ids: set[CoordinationActorIdentity] = set()
        for participant in self.participants:
            if type(participant) is not CoordinationParticipant:
                raise CoordinationRefused("INVALID_OWNER_FACTS")
            identity = participant.identity
            if identity in actor_ids:
                raise CoordinationRefused("AMBIGUOUS_OWNER_FACTS")
            actor_ids.add(identity)
            # Historical inactive generations are retained for audit and
            # grant binding, but cannot compete with the ONE active owner.
            # Exact duplicate identities remain ambiguous regardless of state.
            if not participant.active:
                continue
            if type(identity) is CoordinationIdentity:
                if identity.job_id in jobs or identity.binding_id in bindings:
                    raise CoordinationRefused("AMBIGUOUS_OWNER_FACTS")
                jobs.add(identity.job_id)
                bindings.add(identity.binding_id)
            else:
                # Reject simultaneous live provider generations/hosts/principals
                # for one UUID. An inactive prior generation has no addressability
                # or permission and must not veto a unique current generation.
                native_key = identity.session_id
                if native_key in native_sessions:
                    raise CoordinationRefused("AMBIGUOUS_OWNER_FACTS")
                native_sessions.add(native_key)
        grant_refs: set[str] = set()
        for grant in self.grants:
            if type(grant) is not CoordinationGrant or grant.grant_ref in grant_refs:
                raise CoordinationRefused("AMBIGUOUS_OWNER_FACTS")
            grant_refs.add(grant.grant_ref)
        by_job = {
            p.identity.job_id: p for p in self.participants
            if p.active and type(p.identity) is CoordinationIdentity
        }
        by_identity = {p.identity: p for p in self.participants}
        for child in self.participants:
            legacy = by_job.get(child.parent_job_id)
            explicit = by_identity.get(child.parent_identity)
            # An explicit immutable parent identity outranks the legacy
            # Job-only reference. A stale explicit pin must never be
            # redirected to the current generation of the same Job.
            if child.parent_identity is not None:
                if legacy is not None and explicit != legacy:
                    raise CoordinationRefused("INVALID_PARENT_RELATION")
                parent = explicit
            else:
                parent = legacy
            if parent is not None and (
                _ORDER[parent.role] >= _ORDER[child.role]
                or parent.tenant_ref != child.tenant_ref
                or parent.portfolio_ref != child.portfolio_ref
                or parent.project_ref != child.project_ref
                or (parent.workstream_ref is not None and parent.workstream_ref != child.workstream_ref)
            ):
                raise CoordinationRefused("INVALID_PARENT_RELATION")

    def participant(self, identity: CoordinationActorIdentity, *, now: int) -> CoordinationParticipant:
        _integer(now)
        if not self.observed_at <= now < self.valid_until:
            raise CoordinationRefused("STALE_OWNER_FACTS")
        for participant in self.participants:
            if participant.identity == identity and participant.active:
                return participant
        raise CoordinationRefused("CURRENT_PARTICIPANT_UNAVAILABLE")


@dataclass(frozen=True, slots=True)
class CoordinationDecision:
    relation: str
    snapshot_revision: str
    grant_ref: str | None = None
    operational_authority: bool = False
    forwarding_allowed: bool = False


def authorize_coordination(
    snapshot: CoordinationSnapshot,
    sender: CoordinationActorIdentity,
    recipient: CoordinationActorIdentity,
    *,
    topic_ref: str,
    now: int,
) -> CoordinationDecision:
    """Authorize an advisory exchange only. Deny by default, including self-send.

    Direct parent edges allow collapsed hierarchies. Same-level edges are scoped
    by portfolio/project/workstream/team. Explicit grants are exact-generation,
    same-rank, bilateral, topic-bound and time-bounded; they never cross tenants
    or portfolios. Underlying admission and native-channel isolation still apply.
    """
    if type(snapshot) is not CoordinationSnapshot or not _actor_identity(sender) or not _actor_identity(recipient):
        raise CoordinationRefused("INVALID_OWNER_FACTS")
    _token(topic_ref)
    first = snapshot.participant(sender, now=now)
    second = snapshot.participant(recipient, now=now)
    if sender == recipient:
        raise CoordinationRefused("RELATION_NOT_PERMITTED")
    if (first.tenant_ref, first.portfolio_ref) != (second.tenant_ref, second.portfolio_ref):
        raise CoordinationRefused("RELATION_NOT_PERMITTED")
    same_project = first.project_ref == second.project_ref
    if same_project:
        if (
            first.parent_identity == second.identity
            or second.parent_identity == first.identity
            or (first.parent_identity is None
                and type(second.identity) is CoordinationIdentity
                and first.parent_job_id == second.identity.job_id)
            or (second.parent_identity is None
                and type(first.identity) is CoordinationIdentity
                and second.parent_job_id == first.identity.job_id)
        ):
            return CoordinationDecision("direct_parent_child", snapshot.revision)
    if first.role is second.role:
        role = first.role
        if role is CoordinationRole.PROJECT_CEO:
            return CoordinationDecision("portfolio_ceo_peer", snapshot.revision)
        if same_project:
            if role is CoordinationRole.COO:
                return CoordinationDecision("project_coo_peer", snapshot.revision)
            same_workstream = first.workstream_ref == second.workstream_ref
            if same_workstream and role is CoordinationRole.TASK_OPERATOR:
                return CoordinationDecision("workstream_operator_peer", snapshot.revision)
            if same_workstream and role is CoordinationRole.WORKER and first.coordination_group_ref == second.coordination_group_ref:
                return CoordinationDecision("task_group_worker_peer", snapshot.revision)
        for grant in snapshot.grants:
            if (
                not grant.revoked
                and grant.not_before <= now < grant.valid_until
                and grant.topic_ref == topic_ref
                and {grant.first, grant.second} == {sender, recipient}
                and set(grant.approved_project_refs) == {first.project_ref, second.project_ref}
            ):
                return CoordinationDecision("explicit_dependency_peer", snapshot.revision, grant.grant_ref)
    raise CoordinationRefused("RELATION_NOT_PERMITTED")
