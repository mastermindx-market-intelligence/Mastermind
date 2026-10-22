"""Host-credential-bound installation token issuer for the review GitHub App.

Uses the EXISTING host secret custodian via an injected private-key reader.
No private-key files or tokens are written by this module. The GitHub App,
its installation and grants require separate human-admin enrollment before use.
"""
from __future__ import annotations

import datetime
import re
import time
from collections.abc import Callable
from threading import RLock

import httpx

_REPO_RE = re.compile(r"\A[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}\Z")
_MAX_ISSUER_RESPONSE = 65536


class GitHubAppTokenUnavailable(RuntimeError):
    """Opaque failure, never with token or private-key bytes."""


class GitHubAppInstallationTokens:
    """Short-lived, repo-scoped installation token for one configured GitHub App."""

    def __init__(
        self,
        *,
        app_id: int,
        installation_id: int,
        repository: str,
        private_key_source: Callable[[], bytes],
        client: httpx.Client | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if type(app_id) is not int or app_id <= 0:
            raise GitHubAppTokenUnavailable("GITHUB_APP_ID_INVALID")
        if type(installation_id) is not int or installation_id <= 0:
            raise GitHubAppTokenUnavailable("GITHUB_INSTALLATION_ID_INVALID")
        if not isinstance(repository, str) or _REPO_RE.fullmatch(repository) is None:
            raise GitHubAppTokenUnavailable("GITHUB_REPOSITORY_INVALID")
        if not callable(private_key_source):
            raise GitHubAppTokenUnavailable("GITHUB_APP_KEY_SOURCE_UNBOUND")
        self._app_id = app_id
        self._installation_id = installation_id
        self._repository = repository
        self._private_key_source = private_key_source
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(4.0), follow_redirects=False
        )
        self._clock = clock
        self._lock = RLock()
        self._cached_token: str | None = None
        self._cached_until = 0.0

    def token_for_installation(self, *, installation_id: int) -> str:
        if installation_id != self._installation_id:
            raise GitHubAppTokenUnavailable("GITHUB_INSTALLATION_OUT_OF_SCOPE")
        with self._lock:
            now = float(self._clock())
            if self._cached_token and now < self._cached_until:
                return self._cached_token
            try:
                import jwt  # host-bundled PyJWT; no JWT fallback
                key = self._private_key_source()
                if not isinstance(key, bytes) or not key:
                    raise ValueError("no private key")
                signed = jwt.encode(
                    {"iat": int(now) - 60, "exp": int(now) + 480,
                     "iss": str(self._app_id)},
                    key, algorithm="RS256",
                )
                response = self._client.post(
                    "https://api.github.com/app/installations/"
                    + str(self._installation_id) + "/access_tokens",
                    headers={
                        "Authorization": "Bearer " + signed,
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2026-03-10",
                    },
                    json={
                        "repositories": [self._repository.split("/", 1)[1]],
                        "permissions": {
                            "contents": "read",
                            "pull_requests": "write",
                        },
                    },
                    follow_redirects=False,
                    timeout=4.0,
                )
                if response.status_code != 201 or len(response.content) > _MAX_ISSUER_RESPONSE:
                    raise ValueError("installation token request refused")
                result = response.json()
                if not isinstance(result, dict):
                    raise ValueError("invalid installation token response")
                token = result.get("token")
                expires = result.get("expires_at")
                permissions = result.get("permissions")
                repositories = result.get("repositories")
                if not isinstance(token, str) or not token or len(token) > 8192:
                    raise ValueError("missing installation token")
                if (not isinstance(permissions, dict)
                        or permissions not in (
                            {"contents": "read", "pull_requests": "write"},
                            {"contents": "read", "pull_requests": "write",
                             "metadata": "read"},
                        )):
                    raise ValueError("installation permission drift")
                if (
                    not isinstance(repositories, list)
                    or len(repositories) != 1
                    or not isinstance(repositories[0], dict)
                    or repositories[0].get("full_name") != self._repository
                ):
                    raise ValueError("installation repository drift")
                if not isinstance(expires, str) or not expires.endswith("Z"):
                    raise ValueError("installation expiry invalid")
                expiry = datetime.datetime.fromisoformat(
                    expires.replace("Z", "+00:00")
                ).timestamp()
                if expiry <= now + 60 or expiry > now + 7200:
                    raise ValueError("installation expiry outside bounds")
                self._cached_token = token
                self._cached_until = min(expiry - 60, now + 1800)
                return token
            except Exception:
                # Never forward a private-key parser, token endpoint or JWT error.
                raise GitHubAppTokenUnavailable("GITHUB_APP_TOKEN_UNAVAILABLE") from None

    def __repr__(self) -> str:
        return (
            "GitHubAppInstallationTokens("
            f"app_id={self._app_id}, installation_id={self._installation_id}, "
            f"repository={self._repository!r})"
        )
