"""Optional literal GitHub review route in the existing Mastermind ASGI host.

No new server, port, queue, auth middleware or default route. An installed
operator may mount the single, explicitly enabled receiver beside the
existing Executive/MCP app after separate edge/secret review.

One installed endpoint may also serve several already-composed receivers.
The host owns the map from an exact ``(installation_id, repository)`` tenant
to that tenant's existing receiver. The mount selects at most one of them
and hands it the original bytes and the original headers, unchanged, so that
receiver keeps its own secret, signature, source, admission and Slack owners.
"""
from __future__ import annotations

import asyncio
from typing import Any

from control_plane.github_review_host_config import EXACT_REVIEW_DELIVERY_PATH
from integrations.github_review_asgi_routing import (
    DeliveryHintError,
    ROUTING_BODY_DEADLINE_SECONDS,
    RoutingIndex,
    parse_delivery_tenant,
    replay_request_body,
)
from integrations.github_review_ingress_asgi import (
    BODY_DISCONNECTED,
    BODY_INVALID,
    BODY_TIMEOUT,
    BODY_TOO_LARGE,
    GitHubReviewReceiver,
    parse_delivery_headers,
    read_bounded_request_body,
)


async def _refuse(send: Any, status: int, code: str, **kwargs: Any) -> None:
    """Answer with the receiver's own wire shape.

    One endpoint must look like one endpoint, so the routing refusals reuse
    the receiver's response writer instead of growing a second, subtly
    different response format.
    """

    await GitHubReviewReceiver._reply(send, status, code, **kwargs)


class GitHubReviewASGIMount:
    def __init__(
        self, *, existing_app: Any, receiver: GitHubReviewReceiver | None = None,
        receiver_map: Any | None = None,
    ) -> None:
        if not callable(existing_app):
            raise TypeError("existing Mastermind ASGI app must be supplied")
        if receiver is not None and receiver_map is not None:
            raise TypeError("mount one receiver or one receiver map, not both")
        if receiver is not None and not isinstance(receiver, GitHubReviewReceiver):
            raise TypeError("only the exact GithubReviewReceiver may be mounted")
        if receiver is not None and receiver._settings.delivery_path != EXACT_REVIEW_DELIVERY_PATH:
            raise ValueError("review path cannot shadow an existing Executive route")
        self._existing = existing_app
        self._receiver = receiver
        self._routing: RoutingIndex | None = None
        if receiver_map is not None:
            index = RoutingIndex.build(receiver_map)
            # An empty map is the default-off posture, not a route that
            # refuses everything: it leaves the incumbent app in charge.
            if index.tenant_count:
                self._routing = index

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if (
            scope.get("type") == "http"
            and scope.get("path") == EXACT_REVIEW_DELIVERY_PATH
        ):
            if self._receiver is not None:
                if self._receiver._settings.enabled:
                    # Same installed ASGI process. All auth, body bounds and
                    # admission are enforced by the injected receiver; no
                    # fallback to OAuth/MCP.
                    await self._receiver(scope, receive, send)
                    return
            elif self._routing is not None:
                await self._route(scope, receive, send)
                return
        await self._existing(scope, receive, send)

    async def _route(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        """Route one delivery to the one receiver that owns its tenant.

        The edge surface is validated first, so a malformed request never
        reaches a receiver and never costs a body read. No credential is
        read here: the receiver reads its own enrolled secret and uses it to
        verify the signature before authenticated-source reads or admission.
        """

        index = self._routing
        assert index is not None
        if not index.any_enabled:
            # Every routed receiver is closed. The mount must not intercept
            # and must not buffer a delivery body either: the incumbent
            # route stays in charge, exactly as it does for a closed
            # single-receiver mount.
            await self._existing(scope, receive, send)
            return
        if (
            scope.get("raw_path", EXACT_REVIEW_DELIVERY_PATH.encode("ascii"))
            != EXACT_REVIEW_DELIVERY_PATH.encode("ascii")
            or scope.get("query_string", b"")
        ):
            await _refuse(send, 404, "PATH_NOT_FOUND")
            return
        if scope.get("method") != "POST":
            await _refuse(send, 405, "METHOD_NOT_ALLOWED")
            return
        headers = parse_delivery_headers(scope)
        if headers is None:
            await _refuse(send, 400, "HEADERS_INVALID")
            return
        if headers.get("host", "").lower() != index.expected_host:
            await _refuse(send, 403, "HOST_NOT_ALLOWED")
            return
        if index.require_https and scope.get("scheme") != "https":
            await _refuse(send, 403, "TLS_REQUIRED")
            return
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            await _refuse(send, 415, "CONTENT_TYPE_INVALID")
            return
        signature = headers.get("x-hub-signature-256", "")
        event = headers.get("x-github-event", "")
        delivery_id = headers.get("x-github-delivery", "")
        if not signature or not event or not delivery_id:
            await _refuse(send, 400, "DELIVERY_HEADERS_MISSING")
            return
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                length = int(content_length)
            except ValueError:
                length = -1
            if length < 0 or length > index.max_body_bytes:
                await _refuse(send, 413, "BODY_TOO_LARGE")
                return

        # Bounded routing pressure. This is a fence, not a queue: a delivery
        # that cannot take a slot is refused now instead of being parked with
        # its body in memory.
        if not index.acquire():
            await _refuse(send, 503, "ROUTING_BUSY", retry_after_seconds=1)
            return
        try:
            receiver, body, failure = await self._select_from_body(index, receive, content_length)
        finally:
            index.release()
        # Body/parse capacity is released before any response, credential,
        # network or admission work. A slow tenant cannot monopolize routing.
        if failure is not None:
            await _refuse(send, *failure)
            return
        if receiver is None:  # client disconnected
            return
        assert body is not None
        await receiver(scope, replay_request_body((body,)), send)

    @staticmethod
    async def _select_from_body(index: RoutingIndex, receive: Any, content_length: str | None):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + ROUTING_BODY_DEADLINE_SECONDS
        body_read = await read_bounded_request_body(
            receive, max_bytes=index.max_body_bytes,
            deadline_seconds=ROUTING_BODY_DEADLINE_SECONDS,
        )
        if body_read.failure is not None:
            if body_read.failure == BODY_DISCONNECTED:
                return None, None, None
            failures = {
                BODY_TOO_LARGE: (413, "BODY_TOO_LARGE"),
                BODY_TIMEOUT: (408, "BODY_TIMEOUT"),
                BODY_INVALID: (400, "BODY_INVALID"),
            }
            return None, None, failures[body_read.failure]
        body = b"".join(body_read.chunks)
        if content_length is not None and len(body) != int(content_length):
            return None, None, (400, "CONTENT_LENGTH_MISMATCH")
        try:
            tenant = parse_delivery_tenant(body)
        except DeliveryHintError:
            return None, None, (400, "DELIVERY_BODY_INVALID")
        if loop.time() >= deadline:
            return None, None, (408, "BODY_TIMEOUT")
        try:
            receiver = index.select(tenant)
        except DeliveryHintError:
            return None, None, (503, "REVIEW_RECEIVER_BINDING_CHANGED")
        if receiver is None or not receiver._settings.enabled:
            # An active route never falls through to incumbent auth/MCP based
            # on an unsigned tenant hint. Only wholly inactive maps pass through.
            return None, None, (404, "REVIEW_RECEIVER_NOT_FOUND")
        return receiver, body, None
