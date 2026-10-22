"""Host-administered gates for the GitHub App independent-review receiver.

:mod:`control_plane.github_review_intent` (pure) and
:mod:`control_plane.github_review_intent_ingress` (composition + Protocol ports)
own the decision and the walk.  This module owns only the *host* half that a
binding host must satisfy before a single delivery is even read: which
installation, which repositories, which reviewer, which actors, which exact
ingress host/path, and — the two gates that must both be open before any
public edge exists — whether the receiver is enabled at all and whether the
delivery endpoint may be published.

This module owns no secret, no listener, no transport, no ledger, no client,
no queue, and no policy inference.  It reads nothing from a webhook payload and
from no environment variable: every value arrives from the operator who
administers the GitHub App.

Two independent gates, both default-off
---------------------------------------
``enabled``
    Master switch for the whole receiver.  While it is ``False`` the ASGI app
    answers every request with a typed refusal and touches no GitHub read, no
    ledger, and no Slack surface.

``publication_enabled``
    The *endpoint publication* gate.  It is checked separately and is refused
    while ``False`` even if ``enabled`` is ``True``.  A host that has bound the
    receiver for internal use does not thereby publish a public route; the
    existing Caddy public edge keeps its closed ``@post`` allowlist, which this
    module never widens (see ``docs/GITHUB_REVIEW_HOST_BINDING.md``).

Secret custody
--------------
The webhook secret is deliberately **not** a field of :class:`ReviewHostSettings`.
Anything reachable from configuration is representable, loggable, and
copy-pasteable into a receipt; a webhook secret is a credential and belongs to
the host's own credential source.  The receiver therefore takes a callable that
returns the secret for the exact expected hook installation, and this module
only names that contract (:class:`DeliverySecretSource`).
"""
from __future__ import annotations

import dataclasses
import re
from typing import Protocol, runtime_checkable

from control_plane.github_review_intent import (
    DEFAULT_ALLOWED_ASSOCIATIONS,
    DEFAULT_INTENT_COMMAND,
    DEFAULT_INTENT_LABEL,
    ReviewIntentError,
    ReviewIntentPolicy,
)


SCHEMA = "mastermind.github_review_host_config.v1"

#: The only accepted ingress host header.  ``127.0.0.1`` is accepted **only**
#: together with ``require_https=False``, which is the explicit local-binding
#: posture used by hermetic tests and by an operator who fronts the receiver
#: with a private listener.
LOOPBACK_HOST = "127.0.0.1"

#: GitHub's exact PR permission vocabulary.  The receiver's closed
#: current-permission gate clears ``push`` and ``admin`` only.
_PERMISSION_RE = re.compile(r"^[a-z]{1,20}\Z")
MINIMUM_ACTOR_PERMISSION = frozenset({"push", "admin", "maintain"})

#: Mirrors ``executive_runtime._MAX_…`` free bounds; a delivery is small.
DEFAULT_MAX_BODY_BYTES = 1 << 20

_HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,61}[a-z0-9])?(:[0-9]{1,5})?\Z")
_PATH_RE = re.compile(r"^/[A-Za-z0-9._~-]*(/[A-Za-z0-9._~-]+)*\Z")
_SHA40_RE = re.compile(r"^[0-9a-f]{40}\Z")


class ReviewHostConfigError(ValueError):
    """A host configuration is malformed, or a gate refused to open."""


class ReviewHostGateRefused(ReviewHostConfigError):
    """A default-off gate is closed.  Fails closed with no side effect."""


@runtime_checkable
class DeliverySecretSource(Protocol):
    """The host's own credential source for one GitHub App webhook secret.

    Implementations read the secret from the host's credential custody (an
    OS keychain, a sealed environment binding, a secret manager) and return it
    for one exact hook identity.  The receiver calls this per delivery and never
    stores, caches, logs, or compares the value itself.
    """

    def webhook_secret(self, *, installation_id: int) -> str:
        """Return the webhook secret for this exact installation, or raise."""


@dataclasses.dataclass(frozen=True)
class ReviewHostSettings:
    """Operator-administered binding for one GitHub App independent review.

    Every field is host configuration.  No field is derived from a delivery,
    and no field is a secret.
    """

    # --- gates, both default-off -------------------------------------------
    enabled: bool = False
    publication_enabled: bool = False

    # --- exact ingress surface ---------------------------------------------
    expected_host: str = "127.0.0.1"
    delivery_path: str = "/internal/github/review-intent/delivery"
    require_https: bool = True
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES

    # --- the admin installation and secret ---------------------------------
    installation_id: int = 0
    repositories: frozenset[str] = frozenset()
    installation_ids: frozenset[int] = frozenset()

    # --- reviewer and actor authority --------------------------------------
    configured_reviewer: str = ""
    authorized_actors: frozenset[str] = frozenset()
    intent_label: str = DEFAULT_INTENT_LABEL
    intent_command: str = DEFAULT_INTENT_COMMAND
    allowed_associations: frozenset[str] = DEFAULT_ALLOWED_ASSOCIATIONS

    # --- closed current-permission gate -------------------------------------
    minimum_actor_permission: str = "push"

    # --- Fabric job admission shape (existing ledger only) -----------------
    job_department: str = "engineering"
    job_priority: int = 0
    job_authority_level: str = "A0"
    job_review_required: bool = True

    def __post_init__(self) -> None:
        for name in ("enabled", "publication_enabled", "require_https", "job_review_required"):
            value = getattr(self, name)
            if not isinstance(value, bool):
                raise ReviewHostConfigError(f"{name} must be a boolean")

        if not isinstance(self.expected_host, str) or _HOST_RE.fullmatch(self.expected_host) is None:
            raise ReviewHostConfigError("expected_host must be a canonical host[:port]")
        if self.expected_host == LOOPBACK_HOST and self.require_https:
            # A loopback listener cannot present a public certificate.  Making
            # that explicit prevents a "secure" setting that silently names a
            # plaintext local bind.
            raise ReviewHostConfigError(
                "the loopback bind requires require_https=False to be explicit"
            )
        if (
            not isinstance(self.delivery_path, str)
            or _PATH_RE.fullmatch(self.delivery_path) is None
            or self.delivery_path.endswith("/")
        ):
            raise ReviewHostConfigError("delivery_path must be one exact absolute path")
        if (
            not isinstance(self.max_body_bytes, int)
            or isinstance(self.max_body_bytes, bool)
            or not 0 < self.max_body_bytes <= DEFAULT_MAX_BODY_BYTES
        ):
            raise ReviewHostConfigError("max_body_bytes must be bounded and positive")

        if (
            not isinstance(self.installation_id, int)
            or isinstance(self.installation_id, bool)
            or self.installation_id <= 0
        ):
            raise ReviewHostConfigError("installation_id must be one positive integer")
        for value in self.installation_ids:
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ReviewHostConfigError("installation_ids must be positive integers")
        if self.installation_id not in self.installation_ids:
            raise ReviewHostConfigError(
                "installation_ids must include the exact admin installation_id"
            )
        for value in self.repositories:
            if not isinstance(value, str) or not value:
                raise ReviewHostConfigError("repositories must be canonical owner/name")

        if (
            not isinstance(self.minimum_actor_permission, str)
            or _PERMISSION_RE.fullmatch(self.minimum_actor_permission) is None
            or self.minimum_actor_permission not in MINIMUM_ACTOR_PERMISSION
        ):
            raise ReviewHostConfigError(
                "minimum_actor_permission must be push, maintain, or admin"
            )

        if (
            not isinstance(self.job_department, str)
            or not self.job_department
            or len(self.job_department) > 64
        ):
            raise ReviewHostConfigError("job_department must be a bounded department")
        if (
            not isinstance(self.job_priority, int)
            or isinstance(self.job_priority, bool)
            or not 0 <= self.job_priority <= 100
        ):
            raise ReviewHostConfigError("job_priority must be an integer in 0..100")
        if not isinstance(self.job_authority_level, str) or not re.fullmatch(
            r"A[0-3]", self.job_authority_level
        ):
            raise ReviewHostConfigError("job_authority_level must be A0..A3")

    # --- gates ---------------------------------------------------------------

    def require_enabled(self) -> None:
        """Refuse while the receiver master gate is closed."""

        if not self.enabled:
            raise ReviewHostGateRefused("the review delivery receiver is not enabled")

    def require_publication_enabled(self) -> None:
        """Refuse while the endpoint-publication gate is closed.

        Separate from :meth:`require_enabled` on purpose: binding the receiver
        for a private/localfronted mount is not authorization to publish a
        public delivery endpoint.
        """

        if not self.publication_enabled:
            raise ReviewHostGateRefused(
                "review delivery endpoint publication is not enabled"
            )

    # --- derived policy ------------------------------------------------------

    def review_policy(self) -> ReviewIntentPolicy:
        """Project these host settings onto the pure decision core's policy.

        The projection is total: every value the core validates is already
        validated here, and any drift is raised rather than defaulted.
        """

        try:
            return ReviewIntentPolicy(
                repositories=frozenset(self.repositories),
                installation_ids=frozenset(self.installation_ids),
                configured_reviewer=self.configured_reviewer,
                authorized_actors=frozenset(self.authorized_actors),
                intent_label=self.intent_label,
                intent_command=self.intent_command,
                allowed_associations=frozenset(self.allowed_associations),
            )
        except ReviewIntentError as exc:
            raise ReviewHostConfigError(f"host settings do not project a policy: {exc}") from exc

    def to_dict(self) -> dict[str, object]:
        """A secret-free receipt projection.  ``repr`` is overridden to match."""

        return {
            "schema": SCHEMA,
            "enabled": self.enabled,
            "publication_enabled": self.publication_enabled,
            "expected_host": self.expected_host,
            "delivery_path": self.delivery_path,
            "require_https": self.require_https,
            "max_body_bytes": self.max_body_bytes,
            "installation_id": self.installation_id,
            "repositories": sorted(self.repositories),
            "installation_ids": sorted(self.installation_ids),
            "configured_reviewer": self.configured_reviewer,
            "authorized_actors": sorted(self.authorized_actors),
            "intent_label": self.intent_label,
            "intent_command": self.intent_command,
            "minimum_actor_permission": self.minimum_actor_permission,
            "job_department": self.job_department,
            "job_priority": self.job_priority,
            "job_authority_level": self.job_authority_level,
            "job_review_required": self.job_review_required,
        }

    def __repr__(self) -> str:  # pragma: no cover - trivial delegation
        return f"ReviewHostSettings({self.to_dict()!r})"


def closed_pull_number(body: object, *, event: str) -> int | None:
    """Read the pull number a **signed** delivery body binds to.

    The number is taken from the signature-verified payload only.  The receiver
    route carries no pull number, so there is no second, unsigned place for one
    to arrive from and no way to retarget a signed delivery at another pull
    request.  Returns ``None`` when this event binds no pull request, which the
    caller refuses by name rather than guessing.
    """

    if not isinstance(body, dict) or not isinstance(event, str):
        return None

    container: object
    if event == "pull_request":
        container = body.get("pull_request")
    elif event == "issue_comment":
        issue = body.get("issue")
        if not isinstance(issue, dict):
            return None
        # A comment on an ordinary issue is not a pull request at all.
        if not isinstance(issue.get("pull_request"), dict):
            return None
        container = issue
    else:
        return None

    if not isinstance(container, dict):
        return None
    number = container.get("number")
    if type(number) is not int or number <= 0:
        return None
    return number


__all__ = [
    "DEFAULT_MAX_BODY_BYTES",
    "DeliverySecretSource",
    "LOOPBACK_HOST",
    "MINIMUM_ACTOR_PERMISSION",
    "ReviewHostConfigError",
    "ReviewHostGateRefused",
    "ReviewHostSettings",
    "SCHEMA",
    "closed_pull_number",
]