"""Optional, disabled-by-default Live Window mount for the Steward app.

The existing Steward factory can mount exactly one extra fixed HTTPS GET
resource on its own existing host. The mount is inert unless the application
owner passes one complete :class:`LiveWindowConfig`; with no option, the Steward
MCP policy, verifier, routes, middleware and lifespan are the same objects and
the same behavior as before.

Construction goes only through the accepted Reader seam
(``from_existing_business_owner``): the incumbent Business ``JwtAuthenticator``
bound to an explicit content policy, the current per-source access decision, the
bounded source read and the caller's existing closed audit sink. This module
accepts no caller-supplied reader, owner, route table, classifier, credential,
token store, transcript store or listener, mints no authority, and performs no
enrollment. The Reader owns authentication, current-access, source binding,
suppression and the positive response; this module owns only the exact dispatch
to it and the configuration refusals below.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence
from typing import Any
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Receive, Scope, Send

from integrations.business_mcp_auth.contracts import validate_resource_policy
from integrations.mastermind_window_reader.owner_read_resource import (
    CONTENT_SCOPE,
    from_existing_business_owner,
    snapshot_observation_binding,
)

LIVE_WINDOW_SOURCE_KIND = "live-window"
_REQUIRED_FIELDS = (
    "authenticator",
    "content_policy",
    "current_access",
    "read_source",
    "source_ref",
    "now",
    "allowed_origin",
    "audit_sink",
)

__all__ = [
    "LIVE_WINDOW_SOURCE_KIND",
    "LiveWindowConfig",
    "LiveWindowDispatch",
    "live_window_reader",
]


@dataclasses.dataclass(frozen=True)
class LiveWindowConfig:
    """One complete mount configuration supplied by the application owner.

    Every field is an existing owner's seam, not a new store: the content
    ``authenticator`` and ``content_policy`` are the Business pair, ``now`` and
    ``audit_sink`` come from that owner, ``current_access`` and ``read_source``
    are the current per-source grant and bounded read, and ``source_ref`` is the
    single fixed window identity. There is no default and no allow fallback.
    """

    authenticator: Any
    content_policy: Any
    current_access: Callable[[Any, str], Any]
    read_source: Callable[[], Any]
    source_ref: str
    now: Callable[[], int]
    allowed_origin: str
    audit_sink: Any
    source_kind: str = LIVE_WINDOW_SOURCE_KIND
    observation_binding: Any = None


class LiveWindowDispatch:
    """Send only the exact configured GET to the Reader's own checks.

    Dispatch requires all of: an HTTP scope, the GET method, the exact
    canonical raw path, no query string and no ``root_path``. Every other
    request, and every non-HTTP scope, reaches the original stack with the same
    scope/receive/send. There is no prefix match, redirect, second path,
    fallback route or generated response here, and the Reader is never
    constructed or called for a request this class does not dispatch.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        reader: ASGIApp,
        path: bytes,
        canonical_raw_path: Callable[[Scope], bytes],
    ) -> None:
        self.app = app
        self.reader = reader
        self.path = path
        self.canonical_raw_path = canonical_raw_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope.get("type") == "http"
            and scope.get("method") == "GET"
            and scope.get("query_string", b"") == b""
            and scope.get("root_path", "") == ""
            and self.canonical_raw_path(scope) == self.path
        ):
            await self.reader(scope, receive, send)
            return
        await self.app(scope, receive, send)


def live_window_reader(
    config: LiveWindowConfig,
    *,
    steward_resource: str,
    reserved_paths: Sequence[str],
) -> tuple[ASGIApp, bytes]:
    """Validate one mount configuration and build its accepted read resource.

    Returns the Reader resource and the exact raw path to dispatch. Refusals are
    typed and fail closed: an incomplete configuration, a non-live-window source
    kind, a content scope that is not the accepted content scope, another origin
    or host, or a path that would shadow an existing Steward route all raise
    before any reader exists. There is no fixture, recorded, widened or default
    fallback.
    """

    if not isinstance(config, LiveWindowConfig):
        raise TypeError("LiveWindowConfig required for the live window mount")
    for name in _REQUIRED_FIELDS:
        if getattr(config, name, None) is None:
            raise TypeError("incomplete live window configuration")
    if config.source_kind != LIVE_WINDOW_SOURCE_KIND:
        raise ValueError("live window mount requires the live-window source kind")
    policy = validate_resource_policy(config.content_policy)
    if tuple(policy.required_scopes) != (CONTENT_SCOPE,):
        raise ValueError(
            "live window content policy must require exactly the accepted content scope"
        )

    steward = urlsplit(steward_resource)
    if steward.scheme != "https" or not steward.netloc:
        raise ValueError("same existing host required")
    resource = urlsplit(policy.resource)
    if resource.netloc != steward.netloc:
        raise ValueError("same existing host required")
    if config.allowed_origin != f"{steward.scheme}://{steward.netloc}":
        raise ValueError("same existing host required")

    reserved = {value.rstrip("/") or "/" for value in reserved_paths}
    path = resource.path
    if (path.rstrip("/") or "/") in reserved:
        raise ValueError("reserved application path")

    reader = from_existing_business_owner(
        authenticator=config.authenticator,
        policy=policy,
        current_access=config.current_access,
        read_source=config.read_source,
        source_ref=config.source_ref,
        now=config.now,
        allowed_origin=config.allowed_origin,
        audit_sink=config.audit_sink,
        source_kind=LIVE_WINDOW_SOURCE_KIND,
        observation_binding=snapshot_observation_binding(config.observation_binding),
    )
    return reader, path.encode("ascii")
