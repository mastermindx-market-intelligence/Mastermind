"""Select one already-composed receiver for a mounted multi-repository endpoint.

One installed ASGI host may serve several GitHub App installations and
repositories on one delivery path.  The host owns the map from an exact
``(installation_id, canonical repository)`` tenant to that tenant's existing
:class:`~integrations.github_review_ingress_asgi.GitHubReviewReceiver`.

This module only *selects*.  It owns no credential, no policy, no ledger and
no effect: the selected receiver keeps its own secret, signature, source,
admission and Slack owners, and its own repository/installation scope.  The
tenant hint read from the delivery body is a hint, never an authority — it
picks one pre-enrolled receiver, and that receiver still verifies the
signature and the authenticated source itself.  No receiver is ever tried a
second time after a refusal, a timeout, an unknown effect or any error.
"""
from __future__ import annotations

import dataclasses
import json
import math
import re
from collections.abc import Mapping
from threading import BoundedSemaphore
from types import MappingProxyType
from typing import Any

from control_plane.github_review_host_config import EXACT_REVIEW_DELIVERY_PATH, ReviewHostSettings
from integrations.github_review_ingress_asgi import GitHubReviewReceiver


#: The routing phase may hold at most this many delivery bodies at once.
#: This is a backpressure fence, never a queue: a delivery that cannot take a
#: slot is refused immediately instead of being parked, so pending body memory
#: stays bounded no matter how many deliveries arrive at once.
MAX_ACTIVE_ROUTINGS = 4
MAX_ROUTED_RECEIVERS = 32

#: The elapsed budget for the routing phase's own body read.  It matches the
#: receiver's body budget: the routing phase must not outlive the read it
#: fronts.
ROUTING_BODY_DEADLINE_SECONDS = 2.0

#: The same canonical ``owner/name`` shape the decision core accepts.
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")


@dataclasses.dataclass(frozen=True, order=True)
class DeliveryTenant:
    """The exact ``(installation_id, repository)`` pair one delivery claims."""

    installation_id: int
    repository: str


class DeliveryHintError(ValueError):
    """The delivery body carries no usable tenant hint.

    The message names the shape only.  It never quotes the payload: a decoded
    delivery body is untrusted input and must not reach a log or an error
    string.
    """


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject a repeated JSON key instead of silently keeping the last one."""

    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DeliveryHintError("delivery body repeats a JSON key")
        result[key] = value
    return result


def _strict_float(text: str) -> float:
    """Reject a number that is not finite, including ``1e999``."""

    value = float(text)
    if not math.isfinite(value):
        raise DeliveryHintError("delivery body carries a non-finite number")
    return value


def _strict_constant(name: str) -> Any:
    """Reject the ``NaN``/``Infinity``/``-Infinity`` literals."""

    raise DeliveryHintError(f"delivery body carries the non-finite constant {name}")


def parse_delivery_tenant(body: bytes) -> DeliveryTenant:
    """Read the untrusted tenant hint out of the exact delivery bytes.

    Strict on purpose.  A repeated key, a non-finite number or a malformed
    document fails closed here rather than being silently resolved by a
    lenient parser further down the path — the receiver's own parser keeps
    the last of a repeated key, and a routing decision must never be taken
    from an ambiguous document.

    The result is a *hint*.  It selects at most one pre-enrolled receiver and
    grants nothing: the receiver re-reads the same bytes and applies its own
    signature and authenticated-source checks.
    """

    try:
        parsed = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_float=_strict_float,
            parse_constant=_strict_constant,
        )
    except DeliveryHintError:
        raise
    except (ValueError, RecursionError) as exc:
        raise DeliveryHintError("delivery body is not strict JSON") from exc
    if not isinstance(parsed, dict):
        raise DeliveryHintError("delivery body must be a JSON object")
    installation = parsed.get("installation")
    repository = parsed.get("repository")
    if not isinstance(installation, dict) or not isinstance(repository, dict):
        raise DeliveryHintError("delivery body carries no installation or repository")
    installation_id = installation.get("id")
    if type(installation_id) is not int or installation_id <= 0:
        raise DeliveryHintError("delivery body carries no positive installation id")
    full_name = repository.get("full_name")
    if not isinstance(full_name, str) or _REPOSITORY_RE.fullmatch(full_name) is None:
        raise DeliveryHintError("delivery body carries no canonical repository")
    return DeliveryTenant(installation_id=installation_id, repository=full_name)


def replay_request_body(chunks: tuple[bytes, ...]) -> Any:
    """Return a ``receive()`` that replays the exact original bytes.

    Chunk boundaries are transport details. Coalesce once and replay once so
    fragmented input cannot cause quadratic list shifting or empty-chunk growth.
    """

    body = b"".join(chunks)
    pending = True

    async def receive() -> dict[str, Any]:
        nonlocal pending
        if pending:
            pending = False
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.request", "body": b"", "more_body": False}

    return receive


def _tenant_key(key: Any) -> tuple[int, str]:
    """Read one routing key as an exact ``(installation_id, repository)``."""

    if isinstance(key, DeliveryTenant):
        installation_id, repository = key.installation_id, key.repository
    elif isinstance(key, tuple) and len(key) == 2:
        installation_id, repository = key
    else:
        raise TypeError(
            "routing keys are exact (installation_id, repository) pairs"
        )
    if type(installation_id) is not int or installation_id <= 0:
        raise ValueError("a routing key installation_id must be one positive integer")
    if not isinstance(repository, str) or _REPOSITORY_RE.fullmatch(repository) is None:
        raise ValueError("a routing key repository must be canonical owner/name")
    return installation_id, repository


def _entries(receiver_map: Any) -> list[tuple[Any, Any]]:
    """Accept a host-owned mapping or an explicit sequence of key/receiver pairs.

    A sequence is accepted so a duplicated tenant is *visible* here.  A
    mapping cannot express one: its later entry silently replaces the
    earlier one, and the host would never learn that a receiver was dropped.
    """

    if not isinstance(receiver_map, Mapping) and type(receiver_map) not in {list, tuple}:
        raise TypeError("receiver_map must be a bounded mapping or list/tuple of pairs")
    if len(receiver_map) > MAX_ROUTED_RECEIVERS:
        raise ValueError("too many routed receivers")
    source = receiver_map.items() if isinstance(receiver_map, Mapping) else receiver_map
    items = []
    for item in source:
        if len(items) >= MAX_ROUTED_RECEIVERS:
            raise ValueError("too many routed receivers")
        if type(item) is not tuple or len(item) != 2:
            raise TypeError("receiver_map entries must be (key, receiver) pairs")
        items.append(item)
    return items


class RoutingIndex:
    """The host-owned map from an exact tenant to that tenant's receiver.

    Every receiver keeps its own owners; this index only records which
    receiver already holds which tenant.  It never widens a receiver's
    repository or installation permission, and it never holds a secret.
    """

    __slots__ = (
        "_enabled", "_selected", "_settings", "_slots", "expected_host", "max_body_bytes",
        "require_https",
    )

    def __init__(
        self, selected: dict[tuple[int, str], GitHubReviewReceiver], *,
        enabled: set[tuple[int, str]], expected_host: str, require_https: bool,
        max_body_bytes: int,
    ) -> None:
        self._selected = MappingProxyType(dict(selected))
        self._settings = MappingProxyType({key: receiver._settings for key, receiver in selected.items()})
        self._enabled = frozenset(enabled)
        self.expected_host = expected_host
        self.require_https = require_https
        self.max_body_bytes = max_body_bytes
        self._slots = BoundedSemaphore(MAX_ACTIVE_ROUTINGS)

    @classmethod
    def build(cls, receiver_map: Any) -> "RoutingIndex":
        """Validate the host's map and return the index it describes.

        Every ambiguity is refused here, at construction, rather than being
        resolved at request time: a duplicated tenant, a case-folded tenant
        collision, a key that does not exactly match its receiver's host
        configuration, a receiver that is not bound to exactly one tenant,
        and receivers that disagree about the edge surface they share.
        """

        selected: dict[tuple[int, str], GitHubReviewReceiver] = {}
        enabled: set[tuple[int, str]] = set()
        folded: set[tuple[int, str]] = set()
        owners: list[tuple[GitHubReviewReceiver, tuple[int, str]]] = []
        hosts: set[str] = set()
        https: set[bool] = set()
        limits: list[int] = []

        for key, receiver in _entries(receiver_map):
            installation_id, repository = _tenant_key(key)
            if type(receiver) is not GitHubReviewReceiver:
                raise TypeError("only the exact GithubReviewReceiver may be routed")
            settings = receiver._settings
            if (type(settings) is not ReviewHostSettings
                    or any(type(getattr(settings, name)) is not frozenset for name in (
                        "repositories", "installation_ids", "authorized_actors", "allowed_associations"))):
                raise TypeError("routed settings must be exact and immutable")
            if settings.delivery_path != EXACT_REVIEW_DELIVERY_PATH:
                raise ValueError("review path cannot shadow an existing Executive route")
            if len(settings.repositories) != 1:
                raise ValueError(
                    "a routed receiver must be bound to exactly one repository"
                )
            if next(iter(settings.repositories)) != repository:
                raise ValueError(
                    "a routing key must exactly match its receiver's enrolled repository"
                )
            if settings.installation_id != installation_id:
                raise ValueError(
                    "a routing key must exactly match its receiver's installation"
                )
            policy = settings.review_policy()
            if (policy.installation_ids != frozenset({installation_id})
                    or policy.repositories != frozenset({repository})):
                raise ValueError("a routed receiver policy must bind one active installation/repository")

            tenant = (installation_id, repository)
            if tenant in selected:
                raise ValueError("a tenant may be routed exactly once")
            collision = (installation_id, repository.casefold())
            if collision in folded:
                raise ValueError("a tenant may not collide once case-folded")
            for existing, _existing_tenant in owners:
                if existing is receiver:
                    raise ValueError("one receiver may serve exactly one tenant")
            folded.add(collision)
            owners.append((receiver, tenant))
            selected[tenant] = receiver
            if settings.enabled:
                enabled.add(tenant)
            hosts.add(settings.expected_host.lower())
            https.add(bool(settings.require_https))
            limits.append(settings.max_body_bytes)

        if len(hosts) > 1:
            raise ValueError("routed receivers must share one expected ingress host")
        if len(https) > 1:
            raise ValueError("routed receivers must share one TLS posture")
        if len(set(limits)) > 1:
            raise ValueError("routed receivers must share one body limit")

        return cls(
            selected,
            enabled=enabled,
            expected_host=next(iter(hosts), ""),
            require_https=next(iter(https), True),
            max_body_bytes=limits[0] if limits else 0,
        )

    @property
    def tenant_count(self) -> int:
        return len(self._selected)

    @property
    def any_enabled(self) -> bool:
        """Whether any routed receiver has its master gate open.

        While every routed receiver is closed the mount must not intercept at
        all, and must not buffer a delivery body either.
        """

        return bool(self._enabled)

    def select(self, tenant: DeliveryTenant) -> GitHubReviewReceiver | None:
        """Return the one receiver enrolled for this exact tenant, or None."""

        key = (tenant.installation_id, tenant.repository)
        receiver = self._selected.get(key)
        if receiver is not None and receiver._settings is not self._settings[key]:
            raise DeliveryHintError("routed receiver binding changed")
        return receiver

    def acquire(self) -> bool:
        """Take a routing slot, or refuse when the routing phase is saturated."""

        return self._slots.acquire(blocking=False)

    def release(self) -> None:
        self._slots.release()


__all__ = [
    "DeliveryHintError",
    "DeliveryTenant",
    "MAX_ACTIVE_ROUTINGS",
    "MAX_ROUTED_RECEIVERS",
    "ROUTING_BODY_DEADLINE_SECONDS",
    "RoutingIndex",
    "parse_delivery_tenant",
    "replay_request_body",
]
