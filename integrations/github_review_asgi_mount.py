"""Optional literal GitHub review route in the existing Mastermind ASGI host.

No new server, port, queue, auth middleware or default route. An installed
operator may mount the single, explicitly enabled receiver beside the
existing Executive/MCP app after separate edge/secret review.
"""
from __future__ import annotations

from typing import Any

from control_plane.github_review_host_config import EXACT_REVIEW_DELIVERY_PATH
from integrations.github_review_ingress_asgi import GitHubReviewReceiver


class GitHubReviewASGIMount:
    def __init__(
        self, *, existing_app: Any, receiver: GitHubReviewReceiver | None = None
    ) -> None:
        if not callable(existing_app):
            raise TypeError("existing Mastermind ASGI app must be supplied")
        if receiver is not None and not isinstance(receiver, GitHubReviewReceiver):
            raise TypeError("only the exact GithubReviewReceiver may be mounted")
        if receiver is not None and receiver._settings.delivery_path != EXACT_REVIEW_DELIVERY_PATH:
            raise ValueError("review path cannot shadow an existing Executive route")
        self._existing = existing_app
        self._receiver = receiver

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if (
            scope.get("type") == "http"
            and scope.get("path") == EXACT_REVIEW_DELIVERY_PATH
            and self._receiver is not None
            and self._receiver._settings.enabled
        ):
            # Same installed ASGI process. All auth, body bounds and admission
            # are enforced by the injected receiver; no fallback to OAuth/MCP.
            await self._receiver(scope, receive, send)
            return
        await self._existing(scope, receive, send)
