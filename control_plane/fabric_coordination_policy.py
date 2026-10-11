"""Hierarchy policy over owner-supplied Runtime facts; no registry or transport.

Only the authenticated host may construct these observations. A role, identity,
relationship or grant supplied in a model tool argument is never an observation.
This module does not authorize operational effects, impersonation or forwarding.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re


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
class CoordinationParticipant:
    identity: CoordinationIdentity
    role: CoordinationRole
    tenant_ref: str
    portfolio_ref: str
    project_ref: str
    program_ref: str
    parent_job_id: str | None = None
    workstream_ref: str | None = None
    coordination_group_ref: str | None = None
    active: bool = True

    def __post_init__(self) -> None:
        if type(self.identity) is not CoordinationIdentity or type(self.role) is not CoordinationRole:
            raise CoordinationRefused("INVALID_OWNER_FACTS")
        for value in (self.tenant_ref, self.portfolio_ref, self.project_ref, self.program_ref):
            _token(value)
        for value in (self.parent_job_id, self.workstream_ref, self.coordination_group_ref):
            _token(value, optional=True)
        if type(self.active) is not bool or self.parent_job_id == self.identity.job_id:
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
    first: CoordinationIdentity
    second: CoordinationIdentity
    topic_ref: str
    approved_project_refs: tuple[str, ...]
    not_before: int
    valid_until: int
    revoked: bool = False

    def __post_init__(self) -> None:
        _token(self.grant_ref)
        _token(self.topic_ref)
        if type(self.first) is not CoordinationIdentity or type(self.second) is not CoordinationIdentity or self.first == self.second:
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
        for participant in self.participants:
            if type(participant) is not CoordinationParticipant:
                raise CoordinationRefused("INVALID_OWNER_FACTS")
            identity = participant.identity
            if identity.job_id in jobs or identity.binding_id in bindings:
                raise CoordinationRefused("AMBIGUOUS_OWNER_FACTS")
            jobs.add(identity.job_id)
            bindings.add(identity.binding_id)
        grant_refs: set[str] = set()
        for grant in self.grants:
            if type(grant) is not CoordinationGrant or grant.grant_ref in grant_refs:
                raise CoordinationRefused("AMBIGUOUS_OWNER_FACTS")
            grant_refs.add(grant.grant_ref)
        by_job = {p.identity.job_id: p for p in self.participants}
        for child in self.participants:
            parent = by_job.get(child.parent_job_id)
            if parent is not None and (
                _ORDER[parent.role] >= _ORDER[child.role]
                or parent.tenant_ref != child.tenant_ref
                or parent.portfolio_ref != child.portfolio_ref
                or parent.project_ref != child.project_ref
                or (parent.workstream_ref is not None and parent.workstream_ref != child.workstream_ref)
            ):
                raise CoordinationRefused("INVALID_PARENT_RELATION")

    def participant(self, identity: CoordinationIdentity, *, now: int) -> CoordinationParticipant:
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
    sender: CoordinationIdentity,
    recipient: CoordinationIdentity,
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
    if type(snapshot) is not CoordinationSnapshot or type(sender) is not CoordinationIdentity or type(recipient) is not CoordinationIdentity:
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
        if first.parent_job_id == second.identity.job_id or second.parent_job_id == first.identity.job_id:
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
