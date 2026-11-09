"""Authenticated, bounded source preflight for the incumbent Executive owner.

The host supplies exact GitHub API/configuration bindings and a LOCAL current-
binding fence. This module neither discovers credentials nor installs a socket
handler. GitHub reads run once before Runtime admission. The returned immutable
check performs only local binding, policy and observation-age checks at commit.
"""
from __future__ import annotations

import dataclasses
import math
import time
from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType

from control_plane.github_review_host_config import ReviewHostSettings
from control_plane.github_review_intent import (
    IntentSource, PERMISSION_RANK, PullRequestFacts, ReviewIntentDecision,
    ReviewIntentPolicy, build_review_objective,
)
from control_plane.github_review_socket_contract import (
    MAX_SOURCE_OBSERVATION_SECONDS, PreparedReviewSourceCheck,
)
from integrations.github_review_api import GitHubReviewAPI

MAX_SOURCE_BINDINGS = 32


class GitHubReviewSourceUnavailable(ValueError):
    """Opaque source eligibility or binding failure; no retry authority."""


@dataclasses.dataclass(frozen=True)
class GitHubReviewSourceBinding:
    """One host-owned repository/install/API and its local enrollment fence.

    ``current_binding_guard`` must check the incumbent host's current binding
    or configuration generation without network, credential or database work.
    Returning anything except None refuses. This is not a new grant store.
    """

    settings: ReviewHostSettings
    github: GitHubReviewAPI = dataclasses.field(repr=False)
    current_binding_guard: Callable[[], None] = dataclasses.field(repr=False, compare=False)

    def __post_init__(self) -> None:
        settings = self.settings
        if (type(settings) is not ReviewHostSettings
                or type(self.github) is not GitHubReviewAPI
                or not callable(self.current_binding_guard)
                or any(type(getattr(settings, name)) is not frozenset for name in (
                    "repositories", "installation_ids", "authorized_actors", "allowed_associations"))
                or len(settings.repositories) != 1
                or self.github.repository != next(iter(settings.repositories))
                or self.github.installation_id != settings.installation_id):
            raise GitHubReviewSourceUnavailable("REVIEW_SOURCE_BINDING_INVALID")
        settings.review_policy()


class GitHubReviewSourcePreflight:
    """Prepare one exact request, with no shared per-request mutable state."""

    def __init__(
        self, *, bindings: Sequence[GitHubReviewSourceBinding],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if (type(bindings) not in {list, tuple} or not 1 <= len(bindings) <= MAX_SOURCE_BINDINGS
                or not callable(clock)):
            raise GitHubReviewSourceUnavailable("REVIEW_SOURCE_BINDINGS_INVALID")
        selected = {}
        folded = set()
        for binding in bindings:
            if type(binding) is not GitHubReviewSourceBinding:
                raise GitHubReviewSourceUnavailable("REVIEW_SOURCE_BINDING_INVALID")
            repository = next(iter(binding.settings.repositories))
            # V1 decisions have no installation field. One repository must
            # resolve to exactly one enrolled reader, never a fallback list.
            if repository.casefold() in folded:
                raise GitHubReviewSourceUnavailable("REVIEW_SOURCE_BINDING_AMBIGUOUS")
            selected[repository] = binding
            folded.add(repository.casefold())
        self._bindings = MappingProxyType(selected)
        self._clock = clock

    @property
    def automatic_policies(self) -> Mapping[tuple[int, str], ReviewIntentPolicy]:
        """Exact immutable policy map for this same incumbent socket owner."""
        return MappingProxyType({
            (binding.settings.installation_id, repository): binding.settings.review_policy()
            for repository, binding in self._bindings.items()
            if binding.settings.enabled and binding.settings.allow_lifecycle_review
            and binding.settings.allow_repository_policy_review
        })

    @staticmethod
    def _check_policy(
        decision: ReviewIntentDecision, policy: ReviewIntentPolicy, installation_id: int,
    ) -> None:
        if not policy.is_allowlisted(repository=decision.repository, installation_id=installation_id):
            raise GitHubReviewSourceUnavailable("REVIEW_SOURCE_SCOPE_NOT_ENROLLED")
        authority = decision.policy_authority
        if authority is not None:
            if (authority.installation_id != installation_id
                    or authority.policy_digest != policy.repository_policy_digest(
                        repository=decision.repository, installation_id=installation_id)):
                raise GitHubReviewSourceUnavailable("REVIEW_SOURCE_POLICY_NOT_ENROLLED")
        else:
            if decision.intent_source is IntentSource.OPEN_PR_RECONCILIATION:
                raise GitHubReviewSourceUnavailable("REVIEW_SOURCE_POLICY_NOT_ENROLLED")
            if (decision.intent_source is IntentSource.PR_LIFECYCLE
                    and not policy.allow_lifecycle_review):
                raise GitHubReviewSourceUnavailable("REVIEW_SOURCE_LIFECYCLE_DISABLED")
            if not policy.actor_is_listed(login=decision.actor):
                raise GitHubReviewSourceUnavailable("REVIEW_SOURCE_ACTOR_NOT_ENROLLED")

    def __call__(self, decision: ReviewIntentDecision) -> PreparedReviewSourceCheck:
        if type(decision) is not ReviewIntentDecision:
            raise GitHubReviewSourceUnavailable("REVIEW_SOURCE_DECISION_INVALID")
        # Validate all source/actor/delivery/origin fields, without inventing a
        # webhook or reconstructing trigger fields missing from a v1 decision.
        try:
            closed = ReviewIntentDecision.from_admitted_dict(decision.to_dict())
        except (TypeError, ValueError):
            raise GitHubReviewSourceUnavailable("REVIEW_SOURCE_DECISION_INVALID") from None
        if closed != decision:
            raise GitHubReviewSourceUnavailable("REVIEW_SOURCE_DECISION_INVALID")
        binding = self._bindings.get(decision.repository)
        if binding is None:
            raise GitHubReviewSourceUnavailable("REVIEW_SOURCE_SCOPE_NOT_ENROLLED")
        settings, github = binding.settings, binding.github
        policy = settings.review_policy()
        observed = self._clock()
        if type(observed) not in {int, float} or not math.isfinite(observed) or observed < 0:
            raise GitHubReviewSourceUnavailable("REVIEW_SOURCE_CLOCK_INVALID")

        def binding_is_current() -> None:
            # These are local checks only. A host that replaces enrollment
            # must revoke its supplied generation fence before accepting work.
            if binding.current_binding_guard() is not None:
                raise GitHubReviewSourceUnavailable("REVIEW_SOURCE_BINDING_REVOKED")
            if (self._bindings.get(decision.repository) is not binding
                    or not settings.enabled
                    or github.repository != decision.repository
                    or github.installation_id != settings.installation_id
                    or settings.repositories != frozenset({decision.repository})
                    or settings.review_policy() != policy):
                raise GitHubReviewSourceUnavailable("REVIEW_SOURCE_BINDING_REVOKED")
            self._check_policy(decision, policy, settings.installation_id)

        prepared = PreparedReviewSourceCheck(
            decision=closed, observed_at=observed,
            deadline=observed + MAX_SOURCE_OBSERVATION_SECONDS,
            current_binding_guard=binding_is_current, clock=self._clock,
        )
        prepared.verify(decision)
        # V2 authority is the enrolled standing policy. A bot or reconciliation
        # origin must not be reinterpreted as a human collaborator.
        if decision.policy_authority is None:
            permission = github.read_current_permission(
                repository=decision.repository, login=decision.actor,
            )
            prepared.verify(decision)
            if (type(permission) is not str or permission not in PERMISSION_RANK
                    or PERMISSION_RANK[permission] < PERMISSION_RANK[policy.minimum_permission]):
                raise GitHubReviewSourceUnavailable("REVIEW_SOURCE_PERMISSION_NOT_VERIFIED")
        current = github.read_pull_request(
            repository=decision.repository, pull_number=decision.pull_number,
        )
        prepared.verify(decision)
        if (type(current) is not PullRequestFacts
                or current.repository != decision.repository
                or type(current.number) is not int or current.number != decision.pull_number
                or current.head_sha != decision.frozen_head_sha
                or current.state != "open"
                or current.head_repository != decision.repository
                or current.base_repository != decision.repository
                or type(current.draft) is not bool):
            raise GitHubReviewSourceUnavailable("REVIEW_SOURCE_PR_CHANGED")
        if (current.draft and decision.intent_source not in {
                IntentSource.INTENT_LABEL, IntentSource.COMMAND_COMMENT}):
            raise GitHubReviewSourceUnavailable("REVIEW_SOURCE_DRAFT_REFUSED")
        build_review_objective(pull_request=current, intent_source=decision.intent_source)
        prepared.verify(decision)
        return prepared
