"""App selected-session HTTP transport for the installed v3 OS composition.

This module owns four fixed authenticated HTTPS POST routes around
the actual :class:`InstalledSessionBridgeClient`.  It registers no routes and
constructs no Runtime, socket listener, provider or credential; it remains
disconnected until the integrator supplies the protected composition and the
host qualifies it.  It never decodes JWTs, stores credentials, injects a
principal into ASGI state, or takes a caller-selected private route.

* ``/os/executive/session/context`` resolves one canonical fabric target for
  an exact work/root selection through ``bridge.targets`` only.
* ``/os/executive/session/send`` commits one continuation with precisely the
  four validated existing arguments, passed once to ``bridge.send``.
* ``/os/executive/session/references`` discovers bounded original-request
  references through the same read-only bridge; never commits or acknowledges.
* ``/os/executive/session/reply`` recovers the committed native reply by the
  exact original operation key through ``bridge.reply_read`` only.  It never
  reads targets, never sends, and never marks ``parent_consumed``.

Closed effect mapping: every recognized route answers with the fixed
``mastermind.os.executive.session_result.v1`` envelope.  Context failures and
send failures detected before ``bridge.send`` carry ``effect=NONE`` (this
invocation did not send and says nothing about any prior invocation); every
uncertainty after a send may have begun, and every reply failure, carries
``UNKNOWN``.  A validated continuation commit settles ``accepted`` and proves
only the continuation's canonical effect -- never attention, Worker
execution, a send result, or parent consumption.  Recovery reuses the exact
original operation key; nothing is retried to discover an outcome.

The same exact ``MastermindTokenVerifier``/``JwtAuthenticator`` pairs as the
existing v3 composition are reused.  The read path selects the exact submit
pair only on a read ``SCOPE_REFUSED`` so a combined token retains its
submit-policy principal identity; audit, signature, subject, issuer,
resource, expiry and matching AccessToken/VerifiedPrincipal checks remain
mandatory.  The same bearer is re-verified after body receipt, before the
private call, and after it; any drift withholds context and turns send and
reply evidence into ``UNKNOWN``.  Wrong methods, paths, schemes, query
strings and refused encodings fail closed.

This is an HTTP leaf, not a standalone ASGI root application.  The integrator
must route only these HTTP paths here and retain lifespan and WebSocket
ownership in the existing host/router.  Non-HTTP scopes return without
consuming or emitting events; mounting this leaf as the lifespan or WebSocket
handler is unsupported.  No lifecycle or socket ownership is added here.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from http import HTTPStatus
from typing import Any

from starlette.responses import Response

from integrations.business_mcp_auth.contracts import (
    AuthErrorCode,
    VerifiedPrincipal,
    validate_resource_policy,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.executive_mcp.e1_http import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
)
from integrations.mastermind_executive_app.os_transport import (
    RECEIVE_DEADLINE_SECONDS,
    _OS_HTTP_HEADERS,
    _NoStoreRefusal,
    _access_matches_principal,
    _bearer_token,
    _bounded_receive_body,
    _parse_body,
    principal_scope,
)
from integrations.session_bridge.installed import InstalledSessionBridgeClient
from integrations.session_bridge.schemas import (
    validate_tool_arguments as _validate_bridge_arguments,
)

#: Fixed route -> closed operation name.  Nothing here is request-selectable.
_OPERATIONS: dict[str, str] = {
    "/os/executive/session/context": "context",
    "/os/executive/session/send": "send",
    "/os/executive/session/reply": "reply",
    "/os/executive/session/references": "references",
}

_RESULT_SCHEMA = "mastermind.os.executive.session_result.v1"
_CONTEXT_SCHEMA = "mastermind.os.executive.session_context.v1"
_NATIVE_REPLY_SCHEMA = "mastermind.native_reply_read.v1"
_REFERENCE_SCHEMA = "mastermind.session_reply_references.v1"

#: The existing exact read policy and the existing exact read+intent.submit
#: policy.  Both must concern the same configured resource/issuer/subjects.
_READ_POLICY_SCOPES = frozenset({"mastermind.executive.read"})
_SUBMIT_POLICY_SCOPES = frozenset((
    "mastermind.executive.read",
    "mastermind.executive.intent.submit",
))

_WORK_REF_RE = re.compile(r"^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ROOT_JOB_RE = re.compile(r"^JOB-[A-Za-z0-9][A-Za-z0-9._:-]{0,250}$")
_FABRIC_REF_RE = re.compile(r"^fabric_attempt:[0-9a-f]{64}$")
_CONTINUE_KEY_RE = re.compile(r"^session-continue-[0-9a-f]{64}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GENERATION_RE = re.compile(r"^[0-9a-f]{24}$")
_THREAD_TS_RE = re.compile(r"^[0-9]{10,16}\.[0-9]{6}$")
#: Read-reference syntax only; a read_ref is never derived or minted here.
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")

_MAX_TARGETS = 256
_MAX_REPLY_TEXT_CHARS = 8192
_MAX_REPLY_JSON_BYTES = 16384

#: Closed public failure vocabulary with fixed status and generic message.
_FAILURES: dict[str, tuple[int, str]] = {
    "invalid_input": (HTTPStatus.BAD_REQUEST, "invalid request"),
    "authentication_required": (HTTPStatus.UNAUTHORIZED, "authentication required"),
    "transport_refused": (HTTPStatus.FORBIDDEN, "fixed OS session transport refused"),
    "session_unavailable": (
        HTTPStatus.SERVICE_UNAVAILABLE,
        "selected session is unavailable",
    ),
    "effect_unknown": (
        HTTPStatus.ACCEPTED,
        "operation outcome is unknown; reconcile the original operation",
    ),
}

#: The exact seven-field canonical fabric target row, including the producer
#: projection slice (work_ref, root_job_id) this transport filters on.
_CANONICAL_TARGET_FIELDS = frozenset((
    "target_ref",
    "generation",
    "addressable",
    "kind",
    "continuation_operation_key",
    "work_ref",
    "root_job_id",
))


class _ProjectionRefusal(Exception):
    """The authorized target projection is malformed or internally duplicated."""


class _ForeignReceipt(Exception):
    """A bridge result failed closed-form validation after a possible effect."""


def _continue_message_key(operation_key: str) -> str:
    """Owner CONTINUE key formula, used solely to validate receipt binding."""

    material = "mastermind.session_bridge.continue.v1\n" + operation_key
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return "asd-dot-continue-" + digest[:40]


def _original_request_digest(operation_key: str) -> str:
    """Exact canonical Runtime request digest, used only as a READ verifier.

    This does not mint identifiers or authorize an operation. Public original
    references must remain tied to the stored immutable request key.
    """
    if type(operation_key) is not str or _CONTINUE_KEY_RE.fullmatch(operation_key) is None:
        raise ValueError("invalid original operation key")
    material = json.dumps(
        {"schema": "mastermind.session_bridge.continue_request.v1",
         "operation_key": operation_key},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(material).hexdigest()


def _native_reply_message_key(operation_key: str) -> str:
    """Owner native-reply key formula, used solely to validate recovery."""

    material = "mastermind.session_bridge.native_reply.v1\n" + operation_key
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return "asd-native-reply-" + digest[:40]


def _result(
    operation: str,
    *,
    ok: bool,
    effect: str,
    operation_key: str | None = None,
    data: Any = None,
    error: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "schema": _RESULT_SCHEMA,
        "operation": operation,
        "ok": ok,
        "effect": effect,
        "operation_key": operation_key,
        "data": data,
        "error": error,
    }


def _json_response(payload: dict[str, Any], status: int, *, operation: str) -> Response:
    """Emit one bounded canonical JSON response under the fixed headers."""

    body = json.dumps(
        payload, ensure_ascii=True, allow_nan=False, separators=(",", ":")
    ).encode("utf-8")
    if len(body) > MAX_RESPONSE_BYTES:
        # A malformed or oversize release is UNKNOWN once an effect may have
        # happened; context never has an effect and reports the projection
        # unusable instead.
        if operation in ("context", "references"):
            return _failure_response(operation, "session_unavailable", effect="NONE")
        return _failure_response(
            operation, "effect_unknown", effect="UNKNOWN",
            operation_key=payload.get("operation_key"),
        )
    headers = dict(_OS_HTTP_HEADERS)
    if status == HTTPStatus.UNAUTHORIZED:
        headers["WWW-Authenticate"] = "Bearer"
    return Response(
        content=body,
        status_code=status,
        media_type="application/json",
        headers=headers,
    )


def _failure_response(
    operation: str,
    code: str,
    *,
    effect: str,
    operation_key: str | None = None,
) -> Response:
    status, message = _FAILURES[code]
    payload = _result(
        operation,
        ok=False,
        effect=effect,
        operation_key=operation_key,
        data=None,
        error={"code": code, "message": message},
    )
    return _json_response(payload, status, operation=operation)


def _validated_targets(rows: Any) -> list[dict[str, Any]]:
    """Validate every projected row; any defect fails the projection closed."""

    if not isinstance(rows, (list, tuple)) or len(rows) > _MAX_TARGETS:
        raise _ProjectionRefusal("target projection is unusable")
    canonical: list[dict[str, Any]] = []
    seen_refs: set[str] = set()
    seen_keys: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping) or frozenset(row) != _CANONICAL_TARGET_FIELDS:
            raise _ProjectionRefusal("canonical target row is malformed")
        target_ref = row["target_ref"]
        generation = row["generation"]
        continuation_key = row["continuation_operation_key"]
        if (
            not isinstance(target_ref, str)
            or _FABRIC_REF_RE.fullmatch(target_ref) is None
            or not isinstance(generation, str)
            or _GENERATION_RE.fullmatch(generation) is None
            or generation != target_ref.removeprefix("fabric_attempt:")[:24]
            or not isinstance(continuation_key, str)
            or _CONTINUE_KEY_RE.fullmatch(continuation_key) is None
            or row["addressable"] is not True
            or row["kind"] != "fabric_attempt"
            or not isinstance(row["work_ref"], str)
            or _WORK_REF_RE.fullmatch(row["work_ref"]) is None
            or not isinstance(row["root_job_id"], str)
            or _ROOT_JOB_RE.fullmatch(row["root_job_id"]) is None
        ):
            raise _ProjectionRefusal("canonical target row is malformed")
        if target_ref in seen_refs or continuation_key in seen_keys:
            raise _ProjectionRefusal("duplicate canonical target")
        seen_refs.add(target_ref)
        seen_keys.add(continuation_key)
        canonical.append({name: row[name] for name in sorted(row)})
    return canonical


def _validated_send_receipt(
    validated: Mapping[str, Any], receipt: Any
) -> dict[str, Any]:
    """Closed validation of the canonical continuation carrier receipt.

    A malformed or foreign receipt is UNKNOWN even if it carries an
    ``ok``-shaped field; nothing is inferred from error text or phases.
    """

    if not isinstance(receipt, Mapping) or frozenset(receipt) != frozenset((
            "target_ref", "reply_committed", "carrier", "attention", "read_ref")):
        raise _ForeignReceipt("send receipt is malformed")
    if (
        receipt["target_ref"] != validated["target_ref"]
        or receipt["reply_committed"] is not True
    ):
        raise _ForeignReceipt("send receipt is foreign to the original send")
    carrier = receipt["carrier"]
    if not isinstance(carrier, Mapping) or frozenset(carrier) != frozenset((
            "reply_committed", "action", "message_key", "fingerprint", "thread_ts")):
        raise _ForeignReceipt("carrier receipt is malformed")
    if (
        carrier["reply_committed"] is not True
        or carrier["action"] not in ("POSTED", "RECOVERED", "DUPLICATE")
        or carrier["message_key"] != _continue_message_key(validated["operation_key"])
        or not isinstance(carrier["fingerprint"], str)
        or _SHA256_RE.fullmatch(carrier["fingerprint"]) is None
        or not isinstance(carrier["thread_ts"], str)
        or _THREAD_TS_RE.fullmatch(carrier["thread_ts"]) is None
    ):
        raise _ForeignReceipt(
            "carrier receipt does not bind the original continuation"
        )
    attention = receipt["attention"]
    if (
        not isinstance(attention, Mapping)
        or frozenset(attention) != frozenset({"state"})
        or attention["state"] not in ("UNAVAILABLE", "EFFECT_UNKNOWN")
    ):
        raise _ForeignReceipt("attention is not an installed state")
    read_ref = receipt["read_ref"]
    if not isinstance(read_ref, str) or _ID_RE.fullmatch(read_ref) is None:
        raise _ForeignReceipt("read reference is malformed")
    return {
        "target_ref": receipt["target_ref"],
        "reply_committed": True,
        "carrier": {name: carrier[name] for name in sorted(carrier)},
        "attention": {"state": attention["state"]},
        "read_ref": read_ref,
    }


_NATIVE_REPLY_FIELDS = frozenset((
    "schema",
    "read_ref",
    "request_ref",
    "in_reply_to",
    "message_key",
    "fingerprint",
    "text",
    "next_step",
    "primary_ts",
    "reply_committed",
    "parent_consumed",
    "operation_key",
))


def _validated_native_reply(operation_key: str, native: Any) -> dict[str, Any]:
    """Validate and preserve the complete committed native reply."""

    if not isinstance(native, Mapping) or frozenset(native) != _NATIVE_REPLY_FIELDS:
        raise _ForeignReceipt("native reply is malformed")
    data = dict(native)
    if (
        data["schema"] != _NATIVE_REPLY_SCHEMA
        or data["operation_key"] != operation_key
        or data["in_reply_to"] != _continue_message_key(operation_key)
        or data["message_key"] != _native_reply_message_key(operation_key)
        or data["reply_committed"] is not True
        or data["parent_consumed"] is not False
    ):
        raise _ForeignReceipt("native reply is foreign to the original operation")
    for field in ("read_ref", "request_ref"):
        value = data[field]
        if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
            raise _ForeignReceipt("native reply reference is malformed")
    if (
        not isinstance(data["fingerprint"], str)
        or _SHA256_RE.fullmatch(data["fingerprint"]) is None
        or not isinstance(data["primary_ts"], str)
        or _THREAD_TS_RE.fullmatch(data["primary_ts"]) is None
    ):
        raise _ForeignReceipt("native reply provenance is malformed")
    for field in ("text", "next_step"):
        value = data[field]
        if not isinstance(value, str) or not value or len(value) > _MAX_REPLY_TEXT_CHARS:
            raise _ForeignReceipt("native reply text is not bounded")
    try:
        encoded = json.dumps(
            data, sort_keys=True, ensure_ascii=True, allow_nan=False,
            separators=(",", ":"),
        ).encode("ascii")
    except (ValueError, UnicodeEncodeError, TypeError):
        raise _ForeignReceipt("native reply is not bounded compact ascii") from None
    if len(encoded) > _MAX_REPLY_JSON_BYTES:
        raise _ForeignReceipt("native reply exceeds the 16KiB bound")
    return data


class OsSessionTransportApp:
    """Four fixed selected-session routes around the installed bridge client.

    No inner app is wrapped: unrecognized scopes, methods, paths, schemes and
    query strings fail closed here, and the private bridge call is reached
    only through the exact fixed route with a fully validated body.
    """

    ROUTES: tuple[str, ...] = tuple(_OPERATIONS)

    def __init__(
        self,
        bridge: InstalledSessionBridgeClient,
        *,
        read_verifier: MastermindTokenVerifier,
        read_authenticator: JwtAuthenticator,
        submit_verifier: MastermindTokenVerifier,
        submit_authenticator: JwtAuthenticator,
        clock: Callable[[], int],
    ) -> None:
        if type(bridge) is not InstalledSessionBridgeClient:
            raise TypeError("installed InstalledSessionBridgeClient required")
        for verifier in (read_verifier, submit_verifier):
            if type(verifier) is not MastermindTokenVerifier:
                raise TypeError("audited MastermindTokenVerifier required")
        for authenticator in (read_authenticator, submit_authenticator):
            if not isinstance(authenticator, JwtAuthenticator):
                raise TypeError("JwtAuthenticator required")
        if not callable(clock):
            raise TypeError("clock must be callable")
        try:
            read_policy = validate_resource_policy(read_authenticator.policy)
            submit_policy = validate_resource_policy(submit_authenticator.policy)
        except Exception:
            raise ValueError("exact audited read and submit policies required") from None
        if (
            frozenset(read_policy.required_scopes) != _READ_POLICY_SCOPES
            or frozenset(submit_policy.required_scopes) != _SUBMIT_POLICY_SCOPES
            or read_policy.resource != submit_policy.resource
            or read_policy.issuer != submit_policy.issuer
            or read_policy.allowed_subject_digests != submit_policy.allowed_subject_digests
        ):
            raise ValueError(
                "read and submit policies must concern one configured resource"
            )
        for verifier, authenticator in (
            (read_verifier, read_authenticator),
            (submit_verifier, submit_authenticator),
        ):
            composition = getattr(verifier, "_authenticator_policy_matches", None)
            if (
                getattr(verifier, "_authenticator", None) is not authenticator
                or not callable(composition)
                or composition() is not True
            ):
                raise ValueError("verifier and authenticator must be one composition")
        self._bridge = bridge
        self._read_pair = (read_verifier, read_authenticator)
        self._submit_pair = (submit_verifier, submit_authenticator)
        self._clock = clock

    # ------------------------------------------------------------------ ASGI

    async def __call__(
        self,
        scope: Mapping[str, Any],
        receive: Callable[[], Awaitable[Mapping[str, Any]]],
        send: Callable[[Mapping[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            # The host/router owns non-HTTP protocols; this is an HTTP leaf.
            return
        path = scope.get("path")
        operation = _OPERATIONS.get(path) if isinstance(path, str) else None
        if operation is None or not self._framing_ok(scope):
            await Response(
                status_code=HTTPStatus.NOT_FOUND, headers=_OS_HTTP_HEADERS
            )(scope, receive, send)
            return
        response = await self._request(operation, scope, receive)
        await response(scope, receive, send)

    @staticmethod
    def _framing_ok(scope: Mapping[str, Any]) -> bool:
        """Reuse the fixed Launch transport host/path/scheme rules."""

        try:
            path = scope.get("path", "")
            return (
                scope.get("method") == "POST"
                and isinstance(scope.get("raw_path"), (bytes, bytearray))
                and bytes(scope["raw_path"]) == path.encode("ascii")
                and not (scope.get("query_string") or b"")
                and scope.get("scheme") == "https"
            )
        except Exception:
            return False

    async def _request(
        self,
        operation: str,
        scope: Mapping[str, Any],
        receive: Callable[[], Awaitable[Mapping[str, Any]]],
    ) -> Response:
        effect = "UNKNOWN" if operation == "reply" else "NONE"
        headers = scope.get("headers") or ()
        if not isinstance(headers, (list, tuple)) or any(
            not isinstance(entry, (list, tuple))
            or len(entry) != 2
            or not all(isinstance(value, bytes) for value in entry)
            for entry in headers
        ):
            return _failure_response(operation, "transport_refused", effect=effect)
        hosts = [v for k, v in headers if k.lower() == b"host"]
        origins = [v for k, v in headers if k.lower() == b"origin"]
        authorizations = [v for k, v in headers if k.lower() == b"authorization"]
        if (
            hosts != [b"mcp.mastermind-x.com"]
            or len(origins) > 1
            or (origins and origins != [b"https://mcp.mastermind-x.com"])
            or len(authorizations) != 1
        ):
            return _failure_response(operation, "transport_refused", effect=effect)
        if not self._json_content_type(headers):
            return _failure_response(operation, "invalid_input", effect=effect)
        try:
            token = _bearer_token(bytes(authorizations[0]))
        except _NoStoreRefusal:
            return _failure_response(operation, "authentication_required", effect=effect)
        chain = self._authentication_chain(operation)
        principal = await self._authenticate(token, chain)
        if principal is None:
            return _failure_response(operation, "authentication_required", effect=effect)
        try:
            raw = await _bounded_receive_body(
                receive, deadline_seconds=RECEIVE_DEADLINE_SECONDS
            )
        except Exception:
            return _failure_response(operation, "invalid_input", effect=effect)
        try:
            body = _parse_body(raw)
        except Exception:
            return _failure_response(operation, "invalid_input", effect=effect)
        try:
            return await self._dispatch(operation, scope, body, principal, chain)
        except Exception:
            # No phase may be inferred from an unexpected internal failure.
            if operation in ("context", "references"):
                return _failure_response(operation, "session_unavailable", effect="NONE")
            return _failure_response(
                operation,
                "effect_unknown",
                effect="UNKNOWN",
                operation_key=self._retained_key(operation, body),
            )

    @staticmethod
    def _json_content_type(headers) -> bool:
        if any(key.lower() == b"content-encoding" for key, _value in headers):
            return False
        content_types = [v for k, v in headers if k.lower() == b"content-type"]
        if len(content_types) != 1:
            return False
        try:
            return bytes(content_types[0]).decode("ascii").lower() == "application/json"
        except UnicodeDecodeError:
            return False

    def _authentication_chain(self, operation: str) -> tuple[tuple[Any, Any], ...]:
        if operation == "send":
            return (self._submit_pair,)
        # Read paths select the exact submit pair only on read SCOPE_REFUSED.
        return (self._read_pair, self._submit_pair)

    async def _authenticate(
        self,
        token: str,
        chain: tuple[tuple[Any, Any], ...],
    ) -> VerifiedPrincipal | None:
        try:
            for verifier, authenticator in chain:
                access, code = await verifier.verify_token_with_code(token)
                if access is None:
                    if code == AuthErrorCode.SCOPE_REFUSED:
                        continue
                    return None
                now = self._clock()
                if type(now) is not int:
                    return None
                principal = await authenticator.verify_token(token, now=now)
                released_at = self._clock()
                if (
                    type(principal) is VerifiedPrincipal
                    and type(released_at) is int
                    and now <= released_at < principal.expires_at
                    and _access_matches_principal(access, principal)
                ):
                    return principal
                return None
        except Exception:
            return None
        return None

    @staticmethod
    def _bearer_from_scope(scope: Mapping[str, Any]) -> str:
        headers = scope.get("headers") or ()
        authorizations = [v for k, v in headers if k.lower() == b"authorization"]
        if len(authorizations) != 1:
            raise _NoStoreRefusal("authorization count changed")
        return _bearer_token(bytes(authorizations[0]))

    async def _same_principal(
        self,
        scope: Mapping[str, Any],
        principal: VerifiedPrincipal,
        chain: tuple[tuple[Any, Any], ...],
    ) -> bool:
        try:
            token = self._bearer_from_scope(scope)
        except Exception:
            return False
        current = await self._authenticate(token, chain)
        return current is not None and current == principal

    @staticmethod
    def _retained_key(operation: str, body: Any) -> str | None:
        """Retain a validated original key for recovery where available."""

        if operation == "context" or not isinstance(body, Mapping):
            return None
        arguments = body.get("arguments")
        if not isinstance(arguments, Mapping):
            return None
        key = arguments.get("operation_key")
        if isinstance(key, str) and _CONTINUE_KEY_RE.fullmatch(key) is not None:
            return key
        return None

    # -------------------------------------------------------------- dispatch

    async def _dispatch(
        self,
        operation: str,
        scope: Mapping[str, Any],
        body: dict[str, Any],
        principal: VerifiedPrincipal,
        chain: tuple[tuple[Any, Any], ...],
    ) -> Response:
        if operation == "context":
            return await self._context(scope, body, principal, chain)
        if operation == "send":
            return await self._send(scope, body, principal, chain)
        if operation == "references":
            return await self._references(scope, body, principal, chain)
        return await self._reply(scope, body, principal, chain)

    async def _context(
        self,
        scope: Mapping[str, Any],
        body: dict[str, Any],
        principal: VerifiedPrincipal,
        chain: tuple[tuple[Any, Any], ...],
    ) -> Response:
        selection = (
            body.get("selection")
            if isinstance(body, Mapping) and set(body) == {"selection"}
            else None
        )
        if (
            not isinstance(selection, Mapping)
            or frozenset(selection) != frozenset(("work_ref", "root_job_id"))
        ):
            return _failure_response("context", "invalid_input", effect="NONE")
        work_ref = selection["work_ref"]
        root_job_id = selection["root_job_id"]
        if (
            not isinstance(work_ref, str)
            or _WORK_REF_RE.fullmatch(work_ref) is None
            or not isinstance(root_job_id, str)
            or _ROOT_JOB_RE.fullmatch(root_job_id) is None
        ):
            return _failure_response("context", "invalid_input", effect="NONE")
        if not await self._same_principal(scope, principal, chain):
            return _failure_response(
                "context", "authentication_required", effect="NONE"
            )
        try:
            rows = await self._bridge.targets(principal, kind="fabric_attempt")
        except Exception:
            return _failure_response("context", "session_unavailable", effect="NONE")
        try:
            targets = _validated_targets(rows)
        except _ProjectionRefusal:
            return _failure_response("context", "session_unavailable", effect="NONE")
        matches = [
            row
            for row in targets
            if row["work_ref"] == work_ref and row["root_job_id"] == root_job_id
        ]
        if not matches:
            state, target = "UNAVAILABLE", None
        elif len(matches) == 1:
            state, target = "RESOLVED", matches[0]
        else:
            state, target = "AMBIGUOUS", None
        if not await self._same_principal(scope, principal, chain):
            return _failure_response(
                "context", "authentication_required", effect="NONE"
            )
        data = {
            "schema": _CONTEXT_SCHEMA,
            "principal_scope": principal_scope(principal),
            "verified_expiry": principal.expires_at,
            "selection": {"work_ref": work_ref, "root_job_id": root_job_id},
            "selection_state": state,
            "target": target,
            "capabilities": {
                "send": (
                    state == "RESOLVED"
                    and frozenset(principal.scopes) == _SUBMIT_POLICY_SCOPES
                ),
                "reply_read": True,
                "stop": False,
            },
        }
        return _json_response(
            _result("context", ok=True, effect="NONE", data=data),
            HTTPStatus.OK,
            operation="context",
        )

    async def _send(
        self,
        scope: Mapping[str, Any],
        body: dict[str, Any],
        principal: VerifiedPrincipal,
        chain: tuple[tuple[Any, Any], ...],
    ) -> Response:
        arguments = (
            body.get("arguments")
            if isinstance(body, Mapping) and set(body) == {"arguments"}
            else None
        )
        if not isinstance(arguments, Mapping):
            return _failure_response("send", "invalid_input", effect="NONE")
        try:
            validated = _validate_bridge_arguments("session_send", arguments)
        except Exception:
            return _failure_response(
                "send",
                "invalid_input",
                effect="NONE",
                operation_key=self._retained_key("send", body),
            )
        operation_key = validated["operation_key"]
        if (
            _FABRIC_REF_RE.fullmatch(validated["target_ref"]) is None
            or _CONTINUE_KEY_RE.fullmatch(operation_key) is None
        ):
            return _failure_response(
                "send", "invalid_input", effect="NONE",
                operation_key=self._retained_key("send", body),
            )
        if not await self._same_principal(scope, principal, chain):
            return _failure_response(
                "send", "authentication_required", effect="NONE",
                operation_key=operation_key,
            )
        try:
            # Precisely the four validated arguments, passed once.
            receipt = await self._bridge.send(principal, validated)
        except Exception:
            return _failure_response(
                "send", "effect_unknown", effect="UNKNOWN", operation_key=operation_key
            )
        if not await self._same_principal(scope, principal, chain):
            return _failure_response(
                "send", "effect_unknown", effect="UNKNOWN", operation_key=operation_key
            )
        try:
            data = _validated_send_receipt(validated, receipt)
        except _ForeignReceipt:
            return _failure_response(
                "send", "effect_unknown", effect="UNKNOWN", operation_key=operation_key
            )
        return _json_response(
            _result(
                "send",
                ok=True,
                effect="CONTINUATION_COMMITTED",
                operation_key=operation_key,
                data=data,
            ),
            HTTPStatus.OK,
            operation="send",
        )

    async def _references(
        self, scope: Mapping[str, Any], body: dict[str, Any],
        principal: VerifiedPrincipal, chain: tuple[tuple[Any, Any], ...],
    ) -> Response:
        """READ-only original reference lookup; never consults the active slot."""
        from integrations.session_bridge.reference_tools import NativeReplyReferencesTool
        arguments = body.get("arguments") if isinstance(body, dict) and set(body) == {"arguments"} else None
        try:
            validated = NativeReplyReferencesTool.validate("session_reply_references", arguments)
            if (_WORK_REF_RE.fullmatch(validated["work_ref"]) is None
                    or ("root_job_id" in validated
                        and _ROOT_JOB_RE.fullmatch(validated["root_job_id"]) is None)):
                raise ValueError("invalid OS selection")
        except Exception:
            return _failure_response("references", "invalid_input", effect="NONE")
        if not await self._same_principal(scope, principal, chain):
            return _failure_response("references", "authentication_required", effect="NONE")
        try:
            data = await self._bridge.reply_references(principal, validated)
            if (type(data) is not dict
                    or set(data) != {"schema", "status", "references", "next_cursor", "high_water"}
                    or data["schema"] != _REFERENCE_SCHEMA
                    or data["status"] not in ("PARTIAL", "COMPLETE")
                    or type(data["references"]) is not list
                    or len(data["references"]) > validated.get("page_size", 16)
                    or type(data["high_water"]) is not int
                    or data["high_water"] < 0
                    or (data["status"] == "PARTIAL") != (data["next_cursor"] is not None)
                    or (data["next_cursor"] is not None and (
                        type(data["next_cursor"]) is not str
                        or len(data["next_cursor"]) > 2048
                        or re.fullmatch(r"[A-Za-z0-9_=-]+", data["next_cursor"]) is None))):
                raise ValueError("invalid reference response")
            for row in data["references"]:
                expected = {"read_ref", "operation_key", "request_ref",
                            "request_event_id", "request_revision", "requested_at",
                            "work_ref", "root_job_id", "target_ref", "reference_only"}
                if (type(row) is not dict or set(row) != expected
                        or row["reference_only"] is not True
                        or row["work_ref"] != validated["work_ref"]
                        or ("root_job_id" in validated
                            and row["root_job_id"] != validated["root_job_id"])
                        or type(row["request_event_id"]) is not int
                        or not 1 <= row["request_event_id"] <= data["high_water"]
                        or any(type(row[key]) is not str or not row[key]
                               or len(row[key]) > 256
                               for key in expected - {"reference_only", "request_event_id"})
                        or _CONTINUE_KEY_RE.fullmatch(row["operation_key"]) is None
                        or row["read_ref"] != ("session-reply-" +
                            _original_request_digest(row["operation_key"]))
                        or row["request_ref"] != ("session-bridge-continue:" +
                            _original_request_digest(row["operation_key"]))
                        or _SHA256_RE.fullmatch(row["request_revision"]) is None
                        or _WORK_REF_RE.fullmatch(row["work_ref"]) is None
                        or _ROOT_JOB_RE.fullmatch(row["root_job_id"]) is None
                        or _FABRIC_REF_RE.fullmatch(row["target_ref"]) is None):
                    raise ValueError("foreign reference")
        except Exception:
            return _failure_response("references", "session_unavailable", effect="NONE")
        if not await self._same_principal(scope, principal, chain):
            return _failure_response("references", "authentication_required", effect="NONE")
        return _json_response(
            _result("references", ok=True, effect="NONE", data=data),
            HTTPStatus.OK, operation="references")

    async def _reply(
        self,
        scope: Mapping[str, Any],
        body: dict[str, Any],
        principal: VerifiedPrincipal,
        chain: tuple[tuple[Any, Any], ...],
    ) -> Response:
        # Every reply failure remains UNKNOWN; only input/auth/transport may
        # retain 400/401/403.
        arguments = (
            body.get("arguments")
            if isinstance(body, Mapping) and set(body) == {"arguments"}
            else None
        )
        retained = self._retained_key("reply", body)
        if (
            not isinstance(arguments, Mapping)
            or frozenset(arguments) != frozenset(("operation_key",))
        ):
            return _failure_response(
                "reply", "invalid_input", effect="UNKNOWN", operation_key=retained
            )
        operation_key = arguments["operation_key"]
        if not isinstance(operation_key, str) or _CONTINUE_KEY_RE.fullmatch(operation_key) is None:
            return _failure_response(
                "reply", "invalid_input", effect="UNKNOWN", operation_key=retained
            )
        if not await self._same_principal(scope, principal, chain):
            return _failure_response(
                "reply",
                "authentication_required",
                effect="UNKNOWN",
                operation_key=operation_key,
            )
        try:
            native = await self._bridge.reply_read(
                principal, {"operation_key": operation_key}
            )
        except Exception:
            return _failure_response(
                "reply",
                "effect_unknown",
                effect="UNKNOWN",
                operation_key=operation_key,
            )
        if not await self._same_principal(scope, principal, chain):
            return _failure_response(
                "reply",
                "effect_unknown",
                effect="UNKNOWN",
                operation_key=operation_key,
            )
        try:
            data = _validated_native_reply(operation_key, native)
        except _ForeignReceipt:
            return _failure_response(
                "reply",
                "effect_unknown",
                effect="UNKNOWN",
                operation_key=operation_key,
            )
        return _json_response(
            _result(
                "reply",
                ok=True,
                effect="CONTINUATION_COMMITTED",
                operation_key=operation_key,
                data=data,
            ),
            HTTPStatus.OK,
            operation="reply",
        )


# ---------------------------------------------------------------------------
# exported surface
# ---------------------------------------------------------------------------


__all__ = [
    "MAX_REQUEST_BYTES",
    "MAX_RESPONSE_BYTES",
    "OsSessionTransportApp",
]
