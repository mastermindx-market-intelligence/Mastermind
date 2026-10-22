"""Default-off GitHub independent-review HTTP ingress for the existing Executive/Fabric owner.

ASGI is a transport adapter only. The existing github_review_intent_ingress
makes all policy/authorization/admission decisions. This module does not create
a scheduler, database, queue, provider session or GitHub App credential.

Deployment requires an explicitly enrolled installation secret, an authorized
Executive/Fabric Job admission port, and a separately reviewed public edge route.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any

from control_plane.github_review_intent import ReviewIntentSignatureError
from control_plane.github_review_intent_ingress import (
    ActorPermissionPort,
    FabricJobAdmissionPort,
    PullRequestReadPort,
    ReviewIngressError,
    VisibilityPort,
    admit_review_intent,
)
from control_plane.github_review_host_config import (
    DeliverySecretSource,
    ReviewHostSettings,
)


MAX_HEADER_BYTES = 8192
READ_DEADLINE_SECONDS = 8.0
_SCHEMA = "mastermind.github_review_delivery_http.v1"


class GitHubReviewReceiver:
    """One exact POST route, no request-derived destination and no enabled default."""

    def __init__(
        self,
        *,
        settings: ReviewHostSettings,
        secret_source: DeliverySecretSource,
        pull_requests: PullRequestReadPort,
        actors: ActorPermissionPort,
        fabric: FabricJobAdmissionPort,
        visibility: VisibilityPort | None = None,
    ) -> None:
        if not isinstance(settings, ReviewHostSettings):
            raise TypeError("expected enrolled review host settings")
        self._settings = settings
        self._secrets = secret_source
        self._pulls = pull_requests
        self._actors = actors
        self._fabric = fabric
        self._visibility = visibility

    @staticmethod
    async def _reply(send: Any, status: int, code: str, *, job_id: str | None = None) -> None:
        response: dict[str, str] = {"schema": _SCHEMA, "status": code}
        if job_id is not None:
            response["job_id"] = job_id
        body = json.dumps(response, sort_keys=True, separators=(",", ":")).encode("ascii")
        await send({
            "type": "http.response.start", "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"cache-control", b"no-store"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        })
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    def _headers(scope: Mapping[str, object]) -> dict[str, str] | None:
        raw = scope.get("headers")
        if not isinstance(raw, (tuple, list)):
            return None
        values: dict[str, str] = {}
        size = 0
        try:
            for key, value in raw:
                if not isinstance(key, bytes) or not isinstance(value, bytes):
                    return None
                size += len(key) + len(value)
                if size > MAX_HEADER_BYTES:
                    return None
                name = key.decode("ascii").lower()
                content = value.decode("ascii")
                if name in values or "\n" in content or "\r" in content:
                    return None
                values[name] = content
        except (ValueError, UnicodeError, TypeError):
            return None
        return values

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            raise RuntimeError("the GitHub review ingress serves HTTP only")

        settings = self._settings
        # A default-off receiver must never acquire a credential or call a port.
        if not settings.enabled or not settings.publication_enabled:
            await self._reply(send, 404, "RECEIVER_DISABLED")
            return
        if scope.get("path") != settings.delivery_path or scope.get("query_string", b""):
            await self._reply(send, 404, "PATH_NOT_FOUND")
            return
        if scope.get("method") != "POST":
            await self._reply(send, 405, "METHOD_NOT_ALLOWED")
            return
        headers = self._headers(scope)
        if headers is None:
            await self._reply(send, 400, "HEADERS_INVALID")
            return
        if headers.get("host", "").lower() != settings.expected_host.lower():
            await self._reply(send, 403, "HOST_NOT_ALLOWED")
            return
        if settings.require_https and scope.get("scheme") != "https":
            await self._reply(send, 403, "TLS_REQUIRED")
            return
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            await self._reply(send, 415, "CONTENT_TYPE_INVALID")
            return
        signature = headers.get("x-hub-signature-256", "")
        event = headers.get("x-github-event", "")
        delivery_id = headers.get("x-github-delivery", "")
        if not signature or not event or not delivery_id:
            await self._reply(send, 400, "DELIVERY_HEADERS_MISSING")
            return
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                length = int(content_length)
            except ValueError:
                length = -1
            if length < 0 or length > settings.max_body_bytes:
                await self._reply(send, 413, "BODY_TOO_LARGE")
                return
        body = bytearray()
        try:
            while True:
                message = await receive()
                if message.get("type") == "http.disconnect":
                    return
                if message.get("type") != "http.request":
                    await self._reply(send, 400, "BODY_INVALID")
                    return
                chunk = message.get("body", b"")
                if not isinstance(chunk, bytes) or len(body) + len(chunk) > settings.max_body_bytes:
                    await self._reply(send, 413, "BODY_TOO_LARGE")
                    return
                body.extend(chunk)
                if not message.get("more_body", False):
                    break
        except Exception:
            await self._reply(send, 400, "BODY_INVALID")
            return
        if content_length is not None and len(body) != int(content_length):
            await self._reply(send, 400, "CONTENT_LENGTH_MISMATCH")
            return

        try:
            # The installation id comes from the enrolled host, NEVER the untrusted
            # body. Secret selection cannot be used as a cross-tenant probe oracle.
            secret = self._secrets.webhook_secret(installation_id=settings.installation_id)
            if not isinstance(secret, str) or not secret:
                raise ValueError("secret unavailable")
            outcome = await asyncio.wait_for(
                asyncio.to_thread(
                    admit_review_intent,
                    secret=secret,
                    body=bytes(body),
                    delivery_id=delivery_id,
                    event=event,
                    signature_header=signature,
                    policy=settings.review_policy(),
                    pull_requests=self._pulls,
                    fabric=self._fabric,
                    actors=self._actors,
                    visibility=self._visibility,
                ),
                timeout=READ_DEADLINE_SECONDS,
            )
        except ReviewIntentSignatureError:
            await self._reply(send, 401, "SIGNATURE_INVALID")
            return
        except asyncio.TimeoutError:
            # The worker thread may still commit admission after timeout:
            # never assert that no effect occurred. The canonical command_id
            # UNIQUE key must reconcile a redelivery.
            await self._reply(send, 503, "ADMISSION_EFFECT_UNKNOWN")
            return
        except (ReviewIngressError, ValueError, TypeError):
            await self._reply(send, 422, "ADMISSION_REFUSED")
            return
        except Exception:
            await self._reply(send, 503, "ADMISSION_UNAVAILABLE")
            return

        state = outcome.state.value
        if state == "ADMITTED":
            await self._reply(send, 202, "ADMITTED", job_id=outcome.job_id)
        elif state == "ALREADY_ADMITTED":
            await self._reply(send, 200, "ALREADY_ADMITTED")
        else:
            await self._reply(send, 200, "REFUSED")
