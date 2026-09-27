"""Read-only implementation of the existing GithubTokenProvider contract.

Custody supplies the signer and current service binding. No credential file,
environment, user login, registration, listener, renewal daemon or persistent
store is discovered or created. Token issuance is a credential effect: any
uncertain issuance seals this instance and must return to the existing owner.
A process restart is NOT reconciliation; deployment must preserve that fence.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Protocol

from cryptography.hazmat.primitives.asymmetric import rsa
import jwt

from .github_port import API_VERSION, REST_ROOT, HttpResponse, HttpTransport, UrllibHttpTransport

READ_PERMISSIONS = (("administration", "read"), ("contents", "read"), ("metadata", "read"))
_CODES = frozenset({"PRODUCTION_DISARMED", "BINDING_REFUSED", "AUTHORITY_EXPIRED",
    "AUTHORITY_CHANGED", "CLOCK_REFUSED", "SIGNING_REFUSED", "INSTALLATION_REFUSED",
    "CREDENTIAL_HTTP_REFUSED", "TOKEN_EVIDENCE_REFUSED", "TOKEN_ISSUANCE_UNKNOWN",
    "ISSUANCE_RECONCILIATION_REQUIRED"})
_REPO = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}$")
_GENERATION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,95}$")


class InstallationCredentialError(RuntimeError):
    def __init__(self, code: str, *, issuance_possible: bool = False):
        self.code = code if code in _CODES else "BINDING_REFUSED"
        self.issuance_possible = issuance_possible
        super().__init__(self.code)


@dataclass(frozen=True)
class ReadInstallationBinding:
    app_id: int
    installation_id: int
    account_id: int
    account_login: str
    repository_id: int
    repository: str
    generation: str
    expires_at: int


class AppJwtSigner(Protocol):
    def sign_app_jwt(self, *, app_id: int, issued_at: int, expires_at: int) -> str: ...


class RsaAppJwtSigner:
    """Use an already-admitted in-memory custody key, never select its location."""
    def __init__(self, key: rsa.RSAPrivateKey):
        if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
            raise InstallationCredentialError("SIGNING_REFUSED")
        self._key = key

    def sign_app_jwt(self, *, app_id: int, issued_at: int, expires_at: int) -> str:
        if (type(app_id) is not int or app_id <= 0 or type(issued_at) is not int
                or type(expires_at) is not int or issued_at < 0
                or not 0 < expires_at - issued_at <= 600):
            raise InstallationCredentialError("SIGNING_REFUSED")
        try:
            return jwt.encode({"iss": str(app_id), "iat": issued_at, "exp": expires_at},
                              self._key, algorithm="RS256")
        except Exception:
            raise InstallationCredentialError("SIGNING_REFUSED") from None


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate field")
        value[key] = item
    return value


def _nonfinite(_value):
    raise ValueError("nonfinite value")


class ReadInstallationTokenProvider:
    """One fixed read-service binding, a current credential cache, and no retry.

    The cache is not authority: the existing owner is read on every access.
    A changed binding or uncertain POST cannot silently retarget or reissue.
    """
    def __init__(self, *, resolve_binding: Callable[[], Awaitable[ReadInstallationBinding]],
                 signer: AppJwtSigner, clock: Callable[[], int],
                 transport: HttpTransport | None = None, production_armed: bool = False):
        if (not callable(resolve_binding) or not callable(clock)
                or not callable(getattr(signer, "sign_app_jwt", None))
                or type(production_armed) is not bool):
            raise InstallationCredentialError("BINDING_REFUSED")
        self._resolve = resolve_binding
        self._signer = signer
        self._clock = clock
        self._transport = transport if transport is not None else UrllibHttpTransport()
        if not callable(getattr(self._transport, "request", None)):
            raise InstallationCredentialError("BINDING_REFUSED")
        self._armed = production_armed
        self._lock = asyncio.Lock()
        self._last_now = 0
        self._bound: ReadInstallationBinding | None = None
        self._token: str | None = None
        self._expires = 0
        self._sealed = False

    def _now(self) -> int:
        now = self._clock()
        if type(now) is not int or not 60 <= now <= 253402297199 or now < self._last_now:
            raise InstallationCredentialError("CLOCK_REFUSED")
        self._last_now = now
        return now

    async def _current(self) -> ReadInstallationBinding:
        try:
            bound = await self._resolve()
            now = self._now()
            if (type(bound) is not ReadInstallationBinding
                    or any(type(v) is not int or not 0 < v < 2**53 for v in (
                        bound.app_id, bound.installation_id, bound.account_id, bound.repository_id))
                    or type(bound.repository) is not str or _REPO.fullmatch(bound.repository) is None
                    or type(bound.account_login) is not str
                    or bound.account_login != bound.repository.split("/", 1)[0]
                    or type(bound.generation) is not str or not _GENERATION.fullmatch(bound.generation)
                    or type(bound.expires_at) is not int):
                raise InstallationCredentialError("BINDING_REFUSED")
            if now >= bound.expires_at:
                raise InstallationCredentialError("AUTHORITY_EXPIRED")
            if self._bound is not None and self._bound != bound:
                raise InstallationCredentialError("AUTHORITY_CHANGED")
            return bound
        except InstallationCredentialError:
            raise
        except Exception:
            raise InstallationCredentialError("BINDING_REFUSED") from None

    async def _request(self, *, method: str, endpoint: str, auth: str,
                       expected_status: int, binding: ReadInstallationBinding, body=None) -> dict:
        now = self._now()
        if now >= binding.expires_at:
            raise InstallationCredentialError("AUTHORITY_EXPIRED")
        response = await self._transport.request(method=method, url=REST_ROOT + endpoint,
            headers={"Authorization": "Bearer " + auth, "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION, "User-Agent": "Mastermind-Read-Installation/1",
                **({"Content-Type": "application/json"} if body is not None else {})},
            body=None if body is None else json.dumps(body, separators=(",", ":"), allow_nan=False).encode(),
            timeout_seconds=min(20, binding.expires_at - now))
        if (type(response) is not HttpResponse or type(response.status) is not int
                or response.status != expected_status or type(response.body) is not bytes
                or len(response.body) > 65536 or not isinstance(response.headers, Mapping)
                or any(type(k) is not str or type(v) is not str for k, v in response.headers.items())
                or any(k.lower() == "link" and v.strip() for k, v in response.headers.items())):
            raise InstallationCredentialError("CREDENTIAL_HTTP_REFUSED")
        try:
            document = json.loads(response.body.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_nonfinite)
        except (ValueError, UnicodeError):
            raise InstallationCredentialError("CREDENTIAL_HTTP_REFUSED") from None
        if type(document) is not dict:
            raise InstallationCredentialError("CREDENTIAL_HTTP_REFUSED")
        return document

    @staticmethod
    def _installation(document: dict, bound: ReadInstallationBinding) -> None:
        account = document.get("account")
        if (any(type(document.get(k)) is not int for k in ("id", "app_id", "target_id"))
                or type(account) is not dict or type(account.get("id")) is not int or account.get("id") != bound.account_id
                or account.get("login") != bound.account_login or account.get("type") != "Organization"
                or document.get("id") != bound.installation_id or document.get("app_id") != bound.app_id
                or document.get("target_id") != bound.account_id or document.get("target_type") != "Organization"
                or "suspended_at" not in document or document["suspended_at"] is not None
                or document.get("repository_selection") != "selected"
                or document.get("permissions") != dict(READ_PERMISSIONS)):
            raise InstallationCredentialError("INSTALLATION_REFUSED")

    def _credential(self, document: dict, bound: ReadInstallationBinding) -> tuple[str, int]:
        token = document.get("token")
        repos = document.get("repositories")
        if (type(token) is not str or not 1 <= len(token) <= 8192 or not token.isascii()
                or any(ord(c) <= 32 or ord(c) >= 127 for c in token)
                or document.get("permissions") != dict(READ_PERMISSIONS)
                or document.get("repository_selection") != "selected"
                or type(repos) is not list or len(repos) != 1 or type(repos[0]) is not dict
                or type(repos[0].get("id")) is not int or repos[0].get("id") != bound.repository_id or repos[0].get("full_name") != bound.repository
                or type(document.get("expires_at")) is not str):
            raise InstallationCredentialError("TOKEN_EVIDENCE_REFUSED")
        try:
            raw = document["expires_at"]
            if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", raw):
                raise ValueError("expiry")
            expiry = int(datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())
        except (ValueError, OverflowError):
            raise InstallationCredentialError("TOKEN_EVIDENCE_REFUSED") from None
        now = self._now()
        if not now + 5 < expiry <= now + 3600:
            raise InstallationCredentialError("TOKEN_EVIDENCE_REFUSED")
        return token, min(expiry, bound.expires_at)

    async def installation_token(self) -> str:
        if not self._armed:
            raise InstallationCredentialError("PRODUCTION_DISARMED")
        async with self._lock:
            if self._sealed:
                raise InstallationCredentialError("ISSUANCE_RECONCILIATION_REQUIRED", issuance_possible=True)
            bound = await self._current()
            if self._token is not None:
                if self._now() >= self._expires:
                    # Credential renewal requires a new owner-qualified lifecycle,
                    # never an implicit repeat of a previous issuance operation.
                    raise InstallationCredentialError("AUTHORITY_EXPIRED")
                return self._token
            self._bound = bound
            try:
                now = self._now()
                app_jwt = self._signer.sign_app_jwt(app_id=bound.app_id, issued_at=now - 60, expires_at=now + 300)
                if (type(app_jwt) is not str or not 1 <= len(app_jwt) <= 8192 or not app_jwt.isascii()
                        or any(ord(c) <= 32 or ord(c) >= 127 for c in app_jwt)):
                    raise InstallationCredentialError("SIGNING_REFUSED")
                await self._current()
                installation = await self._request(method="GET", endpoint=f"/repos/{bound.repository}/installation",
                    auth=app_jwt, expected_status=200, binding=bound)
                self._installation(installation, bound)
                await self._current()
                if self._now() >= now + 300:
                    raise InstallationCredentialError("AUTHORITY_EXPIRED")
            except InstallationCredentialError:
                raise
            except Exception:
                raise InstallationCredentialError("CREDENTIAL_HTTP_REFUSED") from None
            # The only credential-mutating request. Seal before awaiting it, so
            # cancellation or malformed success cannot leave an open retry path.
            self._sealed = True
            try:
                document = await self._request(method="POST",
                    endpoint=f"/app/installations/{bound.installation_id}/access_tokens",
                    auth=app_jwt, expected_status=201, binding=bound,
                    body={"repository_ids": [bound.repository_id], "permissions": dict(READ_PERMISSIONS)})
                token, expiry = self._credential(document, bound)
                await self._current()
                self._token, self._expires = token, expiry
                self._sealed = False
                return token
            except InstallationCredentialError as error:
                raise InstallationCredentialError(error.code, issuance_possible=True) from None
            except Exception:
                raise InstallationCredentialError("TOKEN_ISSUANCE_UNKNOWN", issuance_possible=True) from None

    def evidence(self) -> dict[str, object]:
        """Non-authoritative, secret-free current component evidence only."""
        return {"credential_obtained": self._token is not None,
            "requires_owner_reconciliation": self._sealed,
            "repository_id": None if self._bound is None else self._bound.repository_id,
            "usable_until": self._expires or None, "permissions": dict(READ_PERMISSIONS),
            "production_armed": self._armed}
