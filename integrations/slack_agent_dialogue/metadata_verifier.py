"""Credential-safe Slack metadata verification for ASD A0.

The verifier is intentionally narrower than a Slack client. It reads exactly one
bot token from stdin, calls Slack ``auth.test`` through a fixed HTTPS endpoint,
and emits only allowlisted non-secret identity/scope metadata or a fixed opaque
error code. It never accepts a token in argv or environment variables and never
forwards third-party exception text or response fields to its caller.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import BinaryIO, Mapping, Protocol, Sequence, TextIO

SLACK_AUTH_TEST_URL = "https://slack.com/api/auth.test"
RECEIPT_SCHEMA = "mastermind.slack_agent_dialogue.metadata_verification.v1"
MAX_TOKEN_BYTES = 1024
MAX_RESPONSE_BYTES = 16 * 1024
DEFAULT_TIMEOUT_SECONDS = 10.0

ERROR_CODES = frozenset(
    {
        "METADATA_ARGUMENTS_REFUSED",
        "METADATA_EXPECTATION_REFUSED",
        "METADATA_IDENTITY_MISMATCH",
        "METADATA_INPUT_REFUSED",
        "METADATA_RESPONSE_REFUSED",
        "METADATA_SCOPE_MISMATCH",
        "SECRET_SURFACE_REFUSED",
        "SLACK_AUTH_REFUSED",
        "SLACK_AUTH_UNAVAILABLE",
    }
)

_TOKEN_RE = re.compile(r"\Axoxb-[A-Za-z0-9-]{20,1000}\Z")
_TOKEN_SHAPED_RE = re.compile(r"(?i)(?:^|[^A-Za-z0-9])xox[abprs]-[A-Za-z0-9-]{10,}")
_TEAM_ID_RE = re.compile(r"\AT[A-Z0-9]{8,31}\Z")
_USER_ID_RE = re.compile(r"\A[UW][A-Z0-9]{8,31}\Z")
_BOT_ID_RE = re.compile(r"\AB[A-Z0-9]{8,31}\Z")
_SCOPE_RE = re.compile(r"\A[a-z][a-z0-9_.-]*(?::[a-z][a-z0-9_.-]*)?\Z")


class MetadataVerificationError(RuntimeError):
    """One closed caller-visible refusal code."""

    def __init__(self, code: str) -> None:
        if code not in ERROR_CODES:
            raise ValueError("unknown metadata-verification error code")
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class MetadataExpectation:
    team_id: str
    bot_user_id: str
    bot_id: str
    scopes: tuple[str, ...]


@dataclass(frozen=True)
class HttpResult:
    status_code: int
    final_url: str
    headers: Mapping[str, str]
    body: bytes


class SlackAuthTestTransport(Protocol):
    def request(self, *, token: str) -> HttpResult: ...


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


class UrllibSlackAuthTestTransport:
    """Fixed-endpoint stdlib transport; exception details never cross the seam."""

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._timeout_seconds = timeout_seconds
        self._ssl_context = ssl_context or ssl.create_default_context()

    def request(self, *, token: str) -> HttpResult:
        request = urllib.request.Request(
            SLACK_AUTH_TEST_URL,
            data=b"",
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
                "User-Agent": "Mastermind-ASD-A0-Metadata-Verifier/1",
            },
        )
        opener = urllib.request.build_opener(
            _NoRedirectHandler(), urllib.request.HTTPSHandler(context=self._ssl_context)
        )
        try:
            with opener.open(request, timeout=self._timeout_seconds) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise MetadataVerificationError("METADATA_RESPONSE_REFUSED")
                headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
                return HttpResult(
                    status_code=int(response.status),
                    final_url=str(response.geturl()),
                    headers=headers,
                    body=body,
                )
        except MetadataVerificationError:
            raise
        except Exception:
            raise MetadataVerificationError("SLACK_AUTH_UNAVAILABLE") from None


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _fixed_error_document(code: str) -> dict[str, object]:
    if code not in ERROR_CODES:
        raise ValueError("unknown metadata-verification error code")
    return {"error": code, "schema": RECEIPT_SCHEMA, "status": "ERROR"}


def _contains_token_shape(value: str) -> bool:
    return _TOKEN_SHAPED_RE.search(value) is not None


def assert_secret_surfaces_clean(
    *, argv: Sequence[str], environ: Mapping[str, str]
) -> None:
    """Refuse before parsing if a token-shaped value is present outside stdin."""

    if any(_contains_token_shape(str(item)) for item in argv):
        raise MetadataVerificationError("SECRET_SURFACE_REFUSED")
    if any(_contains_token_shape(str(value)) for value in environ.values()):
        raise MetadataVerificationError("SECRET_SURFACE_REFUSED")


def read_token_from_stdin(stream: BinaryIO) -> str:
    raw = stream.read(MAX_TOKEN_BYTES + 1)
    if not raw or len(raw) > MAX_TOKEN_BYTES:
        raise MetadataVerificationError("METADATA_INPUT_REFUSED")

    if raw.endswith(b"\n"):
        raw = raw[:-1]
        if raw.endswith(b"\r"):
            raw = raw[:-1]
    if not raw or b"\n" in raw or b"\r" in raw or any(byte in b" \t\v\f" for byte in raw):
        raise MetadataVerificationError("METADATA_INPUT_REFUSED")

    try:
        token = raw.decode("ascii")
    except UnicodeDecodeError:
        raise MetadataVerificationError("METADATA_INPUT_REFUSED") from None
    if _TOKEN_RE.fullmatch(token) is None:
        raise MetadataVerificationError("METADATA_INPUT_REFUSED")
    return token


def _normalize_scopes(value: Sequence[str]) -> tuple[str, ...]:
    scopes = tuple(sorted(set(value)))
    if not scopes or len(scopes) != len(tuple(value)):
        raise MetadataVerificationError("METADATA_EXPECTATION_REFUSED")
    if any(_SCOPE_RE.fullmatch(scope) is None for scope in scopes):
        raise MetadataVerificationError("METADATA_EXPECTATION_REFUSED")
    return scopes


def validate_expectation(expectation: MetadataExpectation) -> MetadataExpectation:
    if _TEAM_ID_RE.fullmatch(expectation.team_id) is None:
        raise MetadataVerificationError("METADATA_EXPECTATION_REFUSED")
    if _USER_ID_RE.fullmatch(expectation.bot_user_id) is None:
        raise MetadataVerificationError("METADATA_EXPECTATION_REFUSED")
    if _BOT_ID_RE.fullmatch(expectation.bot_id) is None:
        raise MetadataVerificationError("METADATA_EXPECTATION_REFUSED")
    return MetadataExpectation(
        team_id=expectation.team_id,
        bot_user_id=expectation.bot_user_id,
        bot_id=expectation.bot_id,
        scopes=_normalize_scopes(expectation.scopes),
    )


def _parse_scope_header(headers: Mapping[str, str]) -> tuple[str, ...]:
    lowered = {str(k).lower(): str(v) for k, v in headers.items()}
    raw = lowered.get("x-oauth-scopes")
    if raw is None:
        raise MetadataVerificationError("METADATA_RESPONSE_REFUSED")
    values = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not values or len(values) != len(set(values)):
        raise MetadataVerificationError("METADATA_RESPONSE_REFUSED")
    if any(_SCOPE_RE.fullmatch(scope) is None for scope in values):
        raise MetadataVerificationError("METADATA_RESPONSE_REFUSED")
    return tuple(sorted(values))


def verify_metadata(
    *,
    token: str,
    expectation: MetadataExpectation,
    transport: SlackAuthTestTransport,
) -> dict[str, object]:
    expected = validate_expectation(expectation)
    if _TOKEN_RE.fullmatch(token) is None:
        raise MetadataVerificationError("METADATA_INPUT_REFUSED")

    result = transport.request(token=token)
    if (
        result.status_code != 200
        or result.final_url != SLACK_AUTH_TEST_URL
        or len(result.body) > MAX_RESPONSE_BYTES
    ):
        raise MetadataVerificationError("METADATA_RESPONSE_REFUSED")

    try:
        payload = json.loads(result.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise MetadataVerificationError("METADATA_RESPONSE_REFUSED") from None
    if not isinstance(payload, dict):
        raise MetadataVerificationError("METADATA_RESPONSE_REFUSED")
    if payload.get("ok") is not True:
        raise MetadataVerificationError("SLACK_AUTH_REFUSED")

    team_id = payload.get("team_id")
    bot_user_id = payload.get("user_id")
    bot_id = payload.get("bot_id")
    if not all(isinstance(value, str) for value in (team_id, bot_user_id, bot_id)):
        raise MetadataVerificationError("METADATA_RESPONSE_REFUSED")
    observed_scopes = _parse_scope_header(result.headers)

    if (
        team_id != expected.team_id
        or bot_user_id != expected.bot_user_id
        or bot_id != expected.bot_id
    ):
        raise MetadataVerificationError("METADATA_IDENTITY_MISMATCH")
    if observed_scopes != expected.scopes:
        raise MetadataVerificationError("METADATA_SCOPE_MISMATCH")

    return {
        "bot_id": bot_id,
        "bot_user_id": bot_user_id,
        "schema": RECEIPT_SCHEMA,
        "scopes": list(observed_scopes),
        "status": "PASS",
        "team_id": team_id,
    }


class _OpaqueArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # pragma: no cover - behavior asserted through run()
        raise MetadataVerificationError("METADATA_ARGUMENTS_REFUSED")


def _build_parser() -> argparse.ArgumentParser:
    parser = _OpaqueArgumentParser(add_help=True)
    parser.add_argument("--expected-team-id", required=True)
    parser.add_argument("--expected-bot-user-id", required=True)
    parser.add_argument("--expected-bot-id", required=True)
    parser.add_argument("--expected-scope", action="append", required=True)
    return parser


def run(
    argv: Sequence[str],
    *,
    stdin: BinaryIO,
    stdout: TextIO,
    environ: Mapping[str, str],
    transport: SlackAuthTestTransport | None = None,
) -> int:
    try:
        assert_secret_surfaces_clean(argv=argv, environ=environ)
        namespace = _build_parser().parse_args(list(argv))
        expectation = MetadataExpectation(
            team_id=namespace.expected_team_id,
            bot_user_id=namespace.expected_bot_user_id,
            bot_id=namespace.expected_bot_id,
            scopes=tuple(namespace.expected_scope),
        )
        token = read_token_from_stdin(stdin)
        receipt = verify_metadata(
            token=token,
            expectation=expectation,
            transport=transport or UrllibSlackAuthTestTransport(),
        )
        stdout.write(_canonical_json(receipt) + "\n")
        return 0
    except MetadataVerificationError as exc:
        stdout.write(_canonical_json(_fixed_error_document(exc.code)) + "\n")
        return 2
    except Exception:
        stdout.write(
            _canonical_json(_fixed_error_document("METADATA_RESPONSE_REFUSED")) + "\n"
        )
        return 2


def main() -> int:
    return run(
        sys.argv[1:],
        stdin=sys.stdin.buffer,
        stdout=sys.stdout,
        environ=os.environ,
    )


__all__ = [
    "ERROR_CODES",
    "HttpResult",
    "MAX_RESPONSE_BYTES",
    "MAX_TOKEN_BYTES",
    "MetadataExpectation",
    "MetadataVerificationError",
    "RECEIPT_SCHEMA",
    "SLACK_AUTH_TEST_URL",
    "SlackAuthTestTransport",
    "UrllibSlackAuthTestTransport",
    "assert_secret_surfaces_clean",
    "main",
    "read_token_from_stdin",
    "run",
    "validate_expectation",
    "verify_metadata",
]
