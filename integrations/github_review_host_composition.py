"""One explicit GitHub Review host composition; no new runtime or credential store.

The installed Executive host, NOT webhook text, supplies every authority:
current runtime, runtime-admission guard, exact GitHub App id/installation,
host-owned private-key and webhook-secret readers, and the already-enrolled
Mastermind Executive Relay client. No top-level effect or automatic enrollment.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import httpx

from control_plane.executive_runtime import Runtime
from control_plane.github_review_host_config import DeliverySecretSource, ReviewHostSettings
from control_plane.github_review_runtime_adapter import ExecutiveReviewJobAdmission
from integrations.github_review_api import GitHubReviewAPI
from integrations.github_review_app_token import GitHubAppInstallationTokens
from integrations.github_review_ingress_asgi import GitHubReviewReceiver
from integrations.github_review_slack_visibility import SlackReviewVisibility
from integrations.slack_agent_dialogue.slack_web_api import SlackWebApiDialogueClient


class GitHubReviewHostCompositionUnavailable(RuntimeError):
    """A required bound host owner is absent or inconsistent."""


def compose_github_review_host(
    *,
    settings: ReviewHostSettings,
    app_id: int,
    private_key_source: Callable[[], bytes],
    webhook_secret_source: DeliverySecretSource,
    runtime: Runtime,
    admission_guard: Callable[[], None],
    relay_client: SlackWebApiDialogueClient,
    publisher_login: str,
    worker_constraints: Mapping[str, Any] | None = None,
    public_repository_names_authorized: bool = False,
    app_token_http_client: httpx.Client | None = None,
    github_http_client: httpx.Client | None = None,
) -> GitHubReviewReceiver:
    """Return an exact, default-off ASGI app, never start or publish it.

    Host installation must separately bind an approved Executive admission
    guard with a verifiable unarmed state, and use the existing HTTP/ASGI owner.
    A staged object is not a GitHub App installation or an enabled public route.
    """

    if not isinstance(settings, ReviewHostSettings):
        raise GitHubReviewHostCompositionUnavailable("REVIEW_SETTINGS_UNBOUND")
    if not callable(admission_guard):
        raise GitHubReviewHostCompositionUnavailable("EXECUTIVE_ADMISSION_GUARD_UNBOUND")
    if not isinstance(runtime, Runtime):
        raise GitHubReviewHostCompositionUnavailable("EXECUTIVE_RUNTIME_UNBOUND")
    if not isinstance(relay_client, SlackWebApiDialogueClient):
        raise GitHubReviewHostCompositionUnavailable("EXISTING_SLACK_CLIENT_UNBOUND")

    token_source = GitHubAppInstallationTokens(
        app_id=app_id,
        installation_id=settings.installation_id,
        repository=next(iter(settings.repositories)) if len(settings.repositories) == 1 else "",
        private_key_source=private_key_source,
        client=app_token_http_client,
    )
    github = GitHubReviewAPI(
        repository=next(iter(settings.repositories)),
        installation_id=settings.installation_id,
        token_source=token_source,
        publisher_login=publisher_login,
        client=github_http_client,
    )
    admission = ExecutiveReviewJobAdmission(
        runtime=runtime,
        admission_guard=admission_guard,
        constraints=worker_constraints,
    )
    visibility = SlackReviewVisibility(
        client=relay_client,
        public_repository_names_authorized=public_repository_names_authorized,
    )
    return GitHubReviewReceiver(
        settings=settings,
        secret_source=webhook_secret_source,
        pull_requests=github,
        actors=github,
        fabric=admission,
        visibility=visibility,
    )
