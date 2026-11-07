"""Bounded, secret-separated HTTP composition for one Grok routine target.

The module owns no route, retry, target registration, implementation bit,
provider session, or completion truth.  It resolves one opaque native handle to
one credential generation and delegates exactly one POST to an injected poster.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit

from control_plane.wake_dispatcher import WakePreSubmitError
from control_plane.wake_events import canonical_json_bytes
from integrations.executive_wake.grok_bot_routine import GrokRoutineWakeObservation


GROK_WAKE_SCHEMA = "mastermind.grok_bot_wake.v1"
MAX_REQUEST_BYTES = 16 * 1024
MAX_RESPONSE_BYTES = 16 * 1024
POST_TIMEOUT_SECONDS = 15.0

# HTTP response status classes span 1xx through 5xx.
_HTTP_STATUS_MAX_EXCLUSIVE = 6 * 100
_MAX_URL_CHARS = 2048
_MAX_TOKEN_CHARS = 8192
_MAX_OPAQUE_CHARS = 256
_MAX_OPAQUE_IDS = 256
_NUDGE_ID_RE = re.compile(r"^NUDGE-[0-9a-f]{32}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _bounded_opaque(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Grok routine {field} must be a bounded string")
    if (
        not value
        or value.strip() != value
        or len(value) > _MAX_OPAQUE_CHARS
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"Grok routine {field} must be a bounded string")
    return value


def _validated_url(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Grok routine URL must be an HTTPS URL")
    if (
        not value
        or value.strip() != value
        or len(value) > _MAX_URL_CHARS
        or any(
            character.isspace()
            or ord(character) < 32
            or ord(character) == 127
            for character in value
        )
    ):
        raise ValueError("Grok routine URL must be an HTTPS URL")
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        raise ValueError("Grok routine URL must be an HTTPS URL") from None
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Grok routine URL must use HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Grok routine URL must not contain credentials")
    if parsed.query:
        raise ValueError("Grok routine URL must not contain a query")
    if parsed.fragment:
        raise ValueError("Grok routine URL must not contain a fragment")
    return value


def _validated_token(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Grok routine bearer token is invalid")
    if (
        not value
        or len(value) > _MAX_TOKEN_CHARS
        or any(
            character.isspace()
            or ord(character) < 33
            or ord(character) == 127
            for character in value
        )
    ):
        raise ValueError("Grok routine bearer token is invalid")
    return value


def _validated_generation(value: object) -> int:
    if type(value) is not int or value < 1:
        raise ValueError("Grok routine generation must be a positive integer")
    return value


def _validated_target_digest(value: object) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError("Grok routine target digest must be lowercase SHA-256")
    return value


def _validated_request_id(value: object) -> str | None:
    if value is None:
        return None
    try:
        return _bounded_opaque(value, field="request id")
    except ValueError:
        raise ValueError("Grok routine request id is invalid") from None


def grok_routine_target_digest(native_handle: str) -> str:
    """Bind a secret record to one exact opaque native target handle."""

    native = _bounded_opaque(native_handle, field="native handle")
    return hashlib.sha256(
        canonical_json_bytes({"native_handle": native})
    ).hexdigest()


def grok_wake_payload(
    *,
    native_handle: str,
    nudge_id: str,
    binding_id: str,
    binding_generation: int,
    opaque_ids: Sequence[str],
) -> bytes:
    """Build the one closed, prose-free provider payload."""

    native = _bounded_opaque(native_handle, field="native handle")
    if not isinstance(nudge_id, str) or _NUDGE_ID_RE.fullmatch(nudge_id) is None:
        raise ValueError("Grok routine payload requires a canonical nudge id")
    binding = _bounded_opaque(binding_id, field="binding id")
    generation = _validated_generation(binding_generation)
    if isinstance(opaque_ids, (str, bytes, bytearray)) or not isinstance(
        opaque_ids, Sequence
    ):
        raise ValueError("Grok routine payload requires opaque ids")
    if not opaque_ids or len(opaque_ids) > _MAX_OPAQUE_IDS:
        raise ValueError("Grok routine payload requires bounded opaque ids")
    resolved_ids = tuple(
        _bounded_opaque(value, field="opaque id") for value in opaque_ids
    )
    body = canonical_json_bytes(
        {
            "schema": GROK_WAKE_SCHEMA,
            "nudge_id": nudge_id,
            "binding_id": binding,
            "binding_generation": generation,
            "native_handle": native,
            "opaque_ids": list(resolved_ids),
        }
    )
    if len(body) > MAX_REQUEST_BYTES:
        raise ValueError("Grok routine payload exceeds the request ceiling")
    return body


@dataclasses.dataclass(frozen=True, repr=False)
class GrokRoutineCredential:
    """Ephemeral credential material resolved outside durable Wake identity."""

    url: str
    bearer_token: str = dataclasses.field(repr=False)
    generation: int
    target_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "url", _validated_url(self.url))
        object.__setattr__(self, "bearer_token", _validated_token(self.bearer_token))
        object.__setattr__(self, "generation", _validated_generation(self.generation))
        object.__setattr__(
            self,
            "target_digest",
            _validated_target_digest(self.target_digest),
        )


@runtime_checkable
class GrokRoutineCredentialSource(Protocol):
    """Existing secret owner resolving one opaque native handle at call time."""

    def resolve(self, native_handle: str) -> GrokRoutineCredential: ...


@dataclasses.dataclass(frozen=True)
class BoundedHttpResult:
    """One redirect-disabled POST result; body is never represented or logged."""

    status_code: int
    body: bytes = dataclasses.field(repr=False)
    request_id: str | None = None

    def __post_init__(self) -> None:
        if (
            type(self.status_code) is not int
            or not 100 <= self.status_code < _HTTP_STATUS_MAX_EXCLUSIVE
        ):
            raise ValueError("Grok routine HTTP status is invalid")
        if not isinstance(self.body, bytes):
            raise ValueError("Grok routine HTTP body must be bytes")
        object.__setattr__(self, "request_id", _validated_request_id(self.request_id))


@runtime_checkable
class BoundedJsonPoster(Protocol):
    """Injected single-POST transport with redirects and retries disabled."""

    async def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> BoundedHttpResult: ...


class GrokRoutineHttpClient:
    """Resolve one target generation and issue exactly one bounded webhook POST."""

    def __init__(
        self,
        credential_source: GrokRoutineCredentialSource,
        poster: BoundedJsonPoster,
    ) -> None:
        if credential_source is None or not callable(
            getattr(credential_source, "resolve", None)
        ):
            raise ValueError("Grok routine HTTP client requires a credential source")
        if poster is None or not callable(getattr(poster, "post_json", None)):
            raise ValueError("Grok routine HTTP client requires a poster")
        self.credential_source = credential_source
        self.poster = poster

    async def deliver_wake(
        self,
        *,
        native_handle: str,
        nudge_id: str,
        binding_id: str,
        binding_generation: int,
        opaque_ids: Sequence[str],
    ) -> GrokRoutineWakeObservation:
        """Perform one call; only explicit provider non-start is terminal."""

        payload_invalid = False
        try:
            target_digest = grok_routine_target_digest(native_handle)
            body = grok_wake_payload(
                native_handle=native_handle,
                nudge_id=nudge_id,
                binding_id=binding_id,
                binding_generation=binding_generation,
                opaque_ids=opaque_ids,
            )
        except Exception:
            payload_invalid = True
        if payload_invalid:
            raise WakePreSubmitError(
                "Grok routine payload is invalid before submission"
            )

        credential_cancelled = False
        credential_unavailable = False
        credential = None
        try:
            credential = self.credential_source.resolve(native_handle)
        except asyncio.CancelledError:
            credential_cancelled = True
        except Exception:
            credential_unavailable = True
        if credential_cancelled or credential_unavailable:
            raise WakePreSubmitError(
                "Grok routine credential unavailable before submission"
            )
        if not isinstance(credential, GrokRoutineCredential):
            raise WakePreSubmitError(
                "Grok routine credential unavailable before submission"
            )
        if credential.target_digest != target_digest:
            raise WakePreSubmitError(
                "Grok routine credential target mismatch before submission"
            )
        if credential.generation != binding_generation:
            raise WakePreSubmitError(
                "Grok routine credential generation mismatch before submission"
            )

        submission_cancelled = False
        submission_unknown = False
        result = None
        try:
            result = await self.poster.post_json(
                url=credential.url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {credential.bearer_token}",
                },
                body=body,
                timeout_seconds=POST_TIMEOUT_SECONDS,
                max_response_bytes=MAX_RESPONSE_BYTES,
            )
        except asyncio.CancelledError:
            submission_cancelled = True
        except Exception:
            submission_unknown = True
        if submission_cancelled:
            raise asyncio.CancelledError()
        if submission_unknown:
            raise RuntimeError(
                "Grok routine submission result is unavailable after POST began"
            )
        if not isinstance(result, BoundedHttpResult):
            raise RuntimeError("Grok routine poster returned an invalid result")
        if result.status_code != 200:
            raise WakePreSubmitError(
                "Grok routine provider reported a definite no-start outcome"
            )
        if len(result.body) > MAX_RESPONSE_BYTES:
            raise RuntimeError("Grok routine response exceeds the response ceiling")

        return GrokRoutineWakeObservation(
            native_handle=native_handle,
            nudge_id=nudge_id,
            accepted=True,
            request_id=result.request_id,
        )


__all__ = [
    "BoundedHttpResult",
    "BoundedJsonPoster",
    "GROK_WAKE_SCHEMA",
    "GrokRoutineCredential",
    "GrokRoutineCredentialSource",
    "GrokRoutineHttpClient",
    "MAX_REQUEST_BYTES",
    "MAX_RESPONSE_BYTES",
    "POST_TIMEOUT_SECONDS",
    "grok_routine_target_digest",
    "grok_wake_payload",
]
