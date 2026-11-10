"""Fixed authenticated Workspace reads and explicit Control Room actions.

Existing READ routes retain their bounded projection and release-time
authorization checks. The four fixed Control Room POST routes additionally
require the selected operator grant, derive their private principal/expiry
from the existing A1 JWT owner, and preserve the original action's disposition.

All routes use the same installed client and exact-path fences. This module
owns transport framing only: no Runtime, durable state, cache or token store.
"""
from __future__ import annotations

import asyncio
import dataclasses
import inspect
import json
import time
from http import HTTPStatus
from collections.abc import Callable, Mapping
from typing import Any
from types import MappingProxyType
from urllib.parse import unquote

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.mastermind_executive_app.app import _authenticate
from integrations.mastermind_workspace_app import contract
from common import workspace_control_room_action_contract as ccr_action
from control_plane.workspace_owned_task import await_owned

__all__ = ["WorkspaceAppConfig", "create_workspace_app"]


#: Marker bytes the raw-path fence must reject (mirrors BSC-E1 fence).
_SUSPICIOUS_RAW_PATH_MARKERS = (b"%2f", b"%5c", b"//")

#: HTTP status code → client envelope status mapping (closed vocabulary).
_ENVELOPE_STATUS_TO_HTTP: dict[int, int] = {400: 400, 403: 403, 404: 404, 503: 503}

#: Routes — fixed, full /workspace/... prefix preserved verbatim for parent
#: mounting at any depth.  No path parameters, no template substitution.
_PROGRAMS_ROUTE = "/workspace/programs/current"
_WORK_ROUTE = "/workspace/work/current"
_MISSION_ROUTE = "/workspace/mission/current"
_MISSION_V3_ROUTE = "/workspace/mission/v3/current"
_MISSION_V4_ROUTE = "/workspace/mission/v4/current"
_RESULT_ROUTE = "/workspace/result/current"
_EXECUTION_RETURN_ROUTE = "/workspace/execution-return/current"
_MISSION_RESULT_ROUTE = "/workspace/mission-result/current"
_RESULT_REFERENCES_ROUTE = "/workspace/result-references/current"
_PLAN_ROUTE = "/workspace/plan/current"
_PROJECT_PLAN_ROUTE = "/workspace/project-plan/current"
_PROJECT_JOURNAL_ROUTE = "/workspace/project-journal/current"
_PROJECT_KNOWLEDGE_CATALOGUE_ROUTE = "/workspace/project-knowledge/current"
_PROJECT_KNOWLEDGE_MEMORY_ROUTE = "/workspace/project-memory/current"
_PROJECT_KNOWLEDGE_SOURCE_ROUTE = "/workspace/project-source/current"
_PROJECT_DISCOVERY_SOURCE_ROUTE = "/workspace/project-discovery-source/current"
_PROJECT_SESSION_ROUTE = "/workspace/project-session/current"
_PROJECT_DIRECTION_ROUTE = "/workspace/project-direction/current"
_PROJECT_ARCHIVE_ROUTE = "/workspace/projects/archive/current"
_AUTONOMY_ROUTE = "/workspace/autonomy/current"
_RESOURCE_CAPACITY_ROUTE = "/workspace/resources/capacity/current"
_MODEL_CONFIGURATION_ROUTE = "/workspace/resources/models/current"
_CAPACITY_FABRIC_ROUTE = "/workspace/resources/fabric/current"
_T3_ATTEMPT_FLEET_ROUTE = "/workspace/resources/t3/attempts/current"
_HOST_OBSERVATION_ROUTE = "/workspace/resources/host-observation/current"
_ACTIVITY_ROUTE = "/workspace/operator/activity/current"
_FABRIC_CATALOG_ROUTE = "/workspace/fabric/catalog/current"
_FABRIC_STATUS_ROUTE = "/workspace/fabric/status/current"
_ACTIVITY_QUERY_KEYS = frozenset({"work_ref", "root_job_id", "job_id", "attempt_id"})
_BYOK_ROLES_ROUTE = "/workspace/byok/roles/current"
_CCR_STATE_ROUTE = "/workspace/control-room/state/current"
_CCR_DISCOVER_ROUTE = "/workspace/control-room/discover/current"
_CCR_ACTION_ROUTES = MappingProxyType({
    operation: "/workspace/control-room/" + operation
    for operation in ("open", "bind", "unbind", "refresh-builds")
})
_MISSION_QUERY_KEYS = frozenset({"work_ref", "root_job_id"})
_RESULT_QUERY_KEYS = frozenset(
    {"work_ref", "root_job_id", "job_id", "attempt_id", "result_envelope_digest"}
)
_RESULT_REFERENCES_QUERY_KEYS = frozenset({"work_ref", "root_job_id"})


def _envelope_response(envelope: Mapping[str, Any]) -> JSONResponse:
    """Translate one closed-client envelope into the only legal HTTP shape.

    On ``ok: True``, the HTTP body is the result dict itself (the contract's
    "exact result" rule — never the wrapper that encloses it).  On refusal,
    the HTTP body is the closed envelope the client returned verbatim, so
    callers see the same ``{ok, status, error}`` shape they sent.
    """

    if type(envelope) is not dict:
        return _refuse_json(503, "internal_error")
    ok = envelope.get("ok")
    if ok is True:
        if set(envelope) != {"ok", "result"}:
            return _refuse_json(503, "internal_error")
        result = envelope.get("result")
        if not isinstance(result, Mapping):
            return _refuse_json(503, "internal_error")
        try:
            body = contract.bounded_canonical(dict(result))
        except (TypeError, ValueError):
            return _refuse_json(503, "source_unavailable")
        status = 503 if (result.get("schema") in (contract.PROGRAMS_SCHEMA, contract.WORK_SCHEMA)
                         and result.get("availability") == "UNAVAILABLE") else 200
        return Response(body, status_code=status, media_type="application/json", headers={"Cache-Control": "no-store"})
    if ok is False:
        if set(envelope) != {"ok", "status", "error"}:
            return _refuse_json(503, "internal_error")
        error_obj = envelope.get("error")
        status = envelope.get("status")
        if (type(error_obj) is not dict or set(error_obj) != {"code", "message"}
                or error_obj.get("code") not in {"invalid_input", "access_denied", "selection_not_found", "source_unavailable", "internal_error"}
                or type(status) is not int):
            return _refuse_json(503, "internal_error")
        try:
            status_code = int(status)
        except (TypeError, ValueError):
            return _refuse_json(503, "internal_error")
        http_status = _ENVELOPE_STATUS_TO_HTTP.get(status_code)
        if http_status is None:
            return _refuse_json(503, "internal_error")
        return JSONResponse(
            {"ok": False, "error": {"code": error_obj["code"], "message": "workspace read refused"}},
            status_code=http_status,
            headers={"Content-Type": "application/json", "Cache-Control": "no-store"},
        )
    return _refuse_json(503, "internal_error")


def _v2_envelope_response(envelope: Mapping[str, Any], *, operation: str) -> JSONResponse:
    """Translate a v2 closed-client envelope into the legal HTTP shape.

    The v2 routes' success path returns the body dict directly with HTTP
    200/503 mapping driven by the result body availability field.  The
    refusal path mirrors v1's typed envelope mapping without leaking
    dependency text.  The serialized-body ceiling is the operation's own
    frozen ceiling — 16384 for ``result``, the Mission 2 MiB for
    ``mission_v3`` — selected exactly once here.
    """

    if type(envelope) is not dict:
        return _refuse_json(503, "internal_error")
    ok = envelope.get("ok")
    if ok is True:
        if set(envelope) != {"ok", "result"}:
            return _refuse_json(503, "internal_error")
        result = envelope.get("result")
        if not isinstance(result, Mapping):
            return _refuse_json(503, "internal_error")
        # Public HTTP body is BODY alone, bounded a second time here as a
        # defense in depth under the operation's own ceiling; the result
        # adapter inside the read service already measured the whole
        # {ok:true,result:BODY}+LF envelope under the same ceiling.
        ceiling = contract.response_ceiling_for(operation)
        try:
            body = contract.bounded_canonical(dict(result), limit=ceiling)
        except (TypeError, ValueError):
            return _refuse_json(503, "source_unavailable")
        availability = result.get("availability")
        status = 503 if availability == "UNAVAILABLE" else 200
        return Response(body, status_code=status, media_type="application/json",
                        headers={"Cache-Control": "no-store"})
    if ok is False:
        if set(envelope) != {"ok", "status", "error"}:
            return _refuse_json(503, "internal_error")
        error_obj = envelope.get("error")
        status = envelope.get("status")
        if (type(error_obj) is not dict or set(error_obj) != {"code", "message"}
                or type(error_obj.get("code")) is not str
                or error_obj.get("code") not in {"invalid_input", "access_denied", "selection_not_found", "source_unavailable", "internal_error"}
                or type(status) is not int):
            return _refuse_json(503, "internal_error")
        try:
            status_code = int(status)
        except (TypeError, ValueError):
            return _refuse_json(503, "internal_error")
        http_status = _ENVELOPE_STATUS_TO_HTTP.get(status_code)
        if http_status is None:
            return _refuse_json(503, "internal_error")
        return JSONResponse(
            {"ok": False, "error": {"code": error_obj["code"], "message": "workspace read refused"}},
            status_code=http_status,
            headers={"Content-Type": "application/json", "Cache-Control": "no-store"},
        )
    return _refuse_json(503, "internal_error")


def _refuse_json(status: int, code: str) -> JSONResponse:
    """One closed HTTP refusal with no leakage of dependency detail."""

    return JSONResponse(
        {"ok": False, "error": {"code": code, "message": "workspace read refused"}},
        status_code=_ENVELOPE_STATUS_TO_HTTP.get(status, 503),
        headers={"Content-Type": "application/json", "Cache-Control": "no-store"},
    )


def _decode_query(query_string: bytes) -> dict[str, str]:
    """Decode one ASGI ``query_string`` into a single-occurrence dict.

    Percent-decodes both key and value.  Rejects duplicates and any
    percent-encoding that fails to decode cleanly.  Does NOT touch the
    raw-path / encoded-separator fence — that lives in :class:`_RawPathFence`,
    so ``?work_ref=WS%3AAB12cd`` (colon percent-encoded) is fine, while
    ``/path%2Fother`` (slash percent-encoded in the path) is not.
    """
    if not query_string:
        return {}
    if len(query_string) > contract.MAX_REQUEST_BYTES:
        return {"__invalid__": True}
    try:
        decoded = query_string.decode("ascii")
    except UnicodeDecodeError:
        return {"__invalid__": True}  # type: ignore[dict-item]
    parsed_raw: list[tuple[str, str]] = []
    for pair in decoded.split("&"):
        if not pair:
            return {"__invalid__": True}
        try:
            if "=" in pair:
                raw_key, raw_value = pair.split("=", 1)
            else:
                raw_key, raw_value = pair, ""
            key = unquote(raw_key.replace("+", " "))
            value = unquote(raw_value.replace("+", " "))
        except (ValueError, UnicodeDecodeError):
            return {"__invalid__": True}  # type: ignore[dict-item]
        parsed_raw.append((key, value))
    result: dict[str, str] = {}
    for key, value in parsed_raw:
        if key in result:
            return {"__invalid__": True}  # type: ignore[dict-item]
        result[key] = value
    return result


def _decode_v2_query(query_string: bytes, *, required_keys: frozenset[str]) -> dict[str, str]:
    """Strict v2-only query decoder.

    Rejects ``+`` substitution, missing '=', empty pairs/values, encoded key
    aliases, malformed percent escapes, duplicate keys, unknown/missing fields,
    semicolons, fragments, controls, and any non-ASCII bytes.  Decodes
    percent-encoded values exactly once with strict UTF-8 token validation
    so v1's lenient ``+`` space shortcut and empty-value tolerance never leak
    into the v2 routes.  Order independence is preserved because the returned
    dict's keys are the canonical set.
    """
    if not query_string:
        return {"__invalid__": True}
    if len(query_string) > contract.MAX_REQUEST_BYTES:
        return {"__invalid__": True}
    if any(byte > 127 for byte in query_string):
        return {"__invalid__": True}
    try:
        decoded = query_string.decode("ascii")
    except UnicodeDecodeError:
        return {"__invalid__": True}
    if ";" in decoded or "#" in decoded:
        return {"__invalid__": True}
    if not decoded or decoded.endswith("&"):
        return {"__invalid__": True}
    pairs = decoded.split("&")
    seen: set[str] = set()
    result: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            return {"__invalid__": True}
        raw_key, raw_value = pair.split("=", 1)
        if not raw_key or not raw_value:
            return {"__invalid__": True}
        # v2 keys must appear literally in ASCII: no percent decoding, no
        # '+' substitution, no whitespace trimming, no normalization.
        if not raw_key.isascii() or not raw_key.replace("_", "").replace("-", "").isalnum():
            return {"__invalid__": True}
        if raw_key in seen:
            return {"__invalid__": True}
        seen.add(raw_key)
        try:
            value = unquote(raw_value, errors="strict")
        except (ValueError, UnicodeDecodeError):
            return {"__invalid__": True}
        if not value:
            return {"__invalid__": True}
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            return {"__invalid__": True}
        result[raw_key] = value
    if set(result) != required_keys:
        return {"__invalid__": True}
    return result


def _v2_selection(query: Mapping[str, str]) -> dict[str, str] | None:
    """Validate the v2 result route's query exactly.  None on any deviation."""
    if query.get("__invalid__") is True:
        return None
    if set(query) != _RESULT_QUERY_KEYS:
        return None
    return {
        "work_ref": query["work_ref"],
        "root_job_id": query["root_job_id"],
        "job_id": query["job_id"],
        "attempt_id": query["attempt_id"],
        "result_envelope_digest": query["result_envelope_digest"],
    }


def _mission_v3_selection(query: Mapping[str, str]) -> dict[str, str] | None:
    """Validate the v2 Mission route's query exactly.  None on any deviation."""
    if query.get("__invalid__") is True:
        return None
    if set(query) != _MISSION_QUERY_KEYS:
        return None
    return {"work_ref": query["work_ref"], "root_job_id": query["root_job_id"]}


def _mission_selection(query: Mapping[str, str]) -> tuple[dict[str, str] | None, bool]:
    """Validate the mission route's query string exactly.

    Returns ``(selection, ok)``.  When ``ok`` is False the request refuses
    400; ``selection`` is None for the empty / no-keys cases (which is also
    a 400 because the mission endpoint requires both keys).
    """
    invalid = query.get("__invalid__") is True
    if invalid:
        return None, False
    keys = set(query)
    if keys != _MISSION_QUERY_KEYS:
        return None, False
    return {"work_ref": query["work_ref"], "root_job_id": query["root_job_id"]}, True


def _dispatch_v2_selection(operation: str, query: Mapping[str, str]) -> dict[str, str] | None:
    """Dispatch fixed read selectors through their own closed contract."""
    if operation == "project_session":
        from common.workspace_project_session_contract import selection
        try: return selection(dict(query))
        except (TypeError, ValueError): return None
    if operation == "project_direction":
        from common.workspace_project_direction_contract import selection
        try:
            return selection(dict(query))
        except (TypeError, ValueError):
            return None
    if operation in ("project_knowledge_catalogue", "project_knowledge_memory", "project_knowledge_source", "project_discovery_source"):
        from common.workspace_project_knowledge_read_contract import selection
        try: return selection(dict(query), operation=operation)
        except (TypeError, ValueError): return None
    if operation == "project_instructions":
        from common.workspace_project_instructions_contract import validate_selection
        try: return validate_selection(dict(query))
        except (TypeError, ValueError): return None
    if operation == "project_plan":
        from common.workspace_project_plan_contract import validate_selection
        try:
            return validate_selection(dict(query))
        except (TypeError, ValueError):
            return None
    if operation == "project_journal":
        from common.workspace_project_journal_contract import validate_selection
        try:
            return validate_selection(dict(query))
        except (TypeError, ValueError):
            return None
    if operation == "mission_v4_original":
        from common.product_acceptance_acquisition_contract import selection
        try:
            if (set(query) != {"work_ref", "root_job_id", "read_mode"}
                    or query["read_mode"] != "original_owner"):
                return None
            return selection({k: query[k] for k in ("work_ref", "root_job_id")})
        except (TypeError, ValueError):
            return None
    if operation in ("result", "mission_result", "execution_return"):
        return _v2_selection(query)
    if operation == "result_references":
        return _mission_v3_selection(query)
    if operation == "resource_capacity":
        from common.workspace_resource_capacity_contract import selection
        try:
            return selection(dict(query))
        except (TypeError, ValueError):
            return None
    if operation == "retained_activity":
        from common import executive_workspace_activity_contract as activity
        try:
            return activity.selection(dict(query))
        except (TypeError, ValueError):
            return None
    if operation in ("mission_v3", "admitted_plan", "autonomy"):
        return _mission_v3_selection(query)
    if operation == "mission_v4":
        from common.product_acceptance_read_contract import selection
        try:
            return selection(dict(query))
        except (TypeError, ValueError):
            return None
    return None


@dataclasses.dataclass(frozen=True)
class WorkspaceAppConfig:
    """One host-closed configuration bundle for the existing Workspace App.

    Every field is operator-supplied; none is read from a request.  The
    constructor rigidly enforces the closed binding between the
    :class:`JwtAuthenticator` policy and :mod:`contract`'s resource / scope:
    a different ``resource`` or different ``required_scopes`` is refused at
    construction so the edge cannot be instantiated with the wrong policy.
    """

    authenticator: JwtAuthenticator
    now: Callable[[], int] = dataclasses.field(default=lambda: int(time.time()))
    authorize_principal: Callable[[VerifiedPrincipal], bool] | None = None
    client: Any = None
    project_admission_load_bindings: Callable[[], Any] | None = None
    authorize_discovery: Callable[[VerifiedPrincipal], bool] | None = None
    authorize_actions: Mapping[str, Callable[[VerifiedPrincipal], bool]] | None = None
    source_operation_context: Any = None
    paperclip: Any = None

    def __post_init__(self) -> None:
        if self.paperclip is not None:
            from integrations.paperclip_control.installed import PaperclipWorkspaceBinding
            if type(self.paperclip) is not PaperclipWorkspaceBinding or self.paperclip.policy_id != self.authenticator.policy.policy_id:
                raise ValueError("Paperclip must bind the same Workspace principal policy")
        if self.project_admission_load_bindings is not None and not callable(self.project_admission_load_bindings):
            raise ValueError("sealed current project membership loader required")
        if self.source_operation_context is not None:
            from integrations.mastermind_workspace_app.source_operation_context import WorkspaceSourceOperationContextFactory
            if (type(self.source_operation_context) is not WorkspaceSourceOperationContextFactory
                    or self.source_operation_context.policy != self.authenticator.policy):
                raise ValueError("source operation context must bind the same installed Workspace policy")
        if self.authorize_discovery is not None and not callable(self.authorize_discovery):
            raise ValueError("authorize_discovery must be callable or absent")
        if self.authorize_actions is not None:
            if (type(self.authorize_actions) is not dict
                    or set(self.authorize_actions) != ccr_action.OPERATIONS
                    or any(not callable(value) for value in self.authorize_actions.values())):
                raise ValueError("authorize_actions must select exactly four callable owners")
            object.__setattr__(self, "authorize_actions", MappingProxyType(dict(self.authorize_actions)))
        if not isinstance(self.authenticator, JwtAuthenticator):
            raise ValueError("authenticator must be a JwtAuthenticator")
        if self.now is None or not callable(self.now):
            raise ValueError("now must be a callable returning an int second")
        if self.authorize_principal is None or not callable(self.authorize_principal):
            raise ValueError("authorize_principal must be callable")
        if self.client is None or not callable(getattr(self.client, "request", None)):
            raise ValueError("client must expose an async request(frame) method")
        if not inspect.iscoroutinefunction(getattr(self.client, "request", None)):
            raise ValueError("client.request must be a coroutine function")
        # Revalidate the authenticator's policy first — a frozen dataclass can
        # still be substituted or low-level mutated, and the wiring contract
        # below requires the immutable ResourcePolicy it claims to bind.
        from integrations.business_mcp_auth.contracts import validate_resource_policy

        try:
            policy = validate_resource_policy(self.authenticator.policy)
        except Exception as exc:
            raise ValueError(f"authenticator policy refused: {exc}") from exc
        if policy.resource != contract.RESOURCE:
            raise ValueError(
                f"authenticator resource {policy.resource!r} does not equal "
                f"contract.RESOURCE {contract.RESOURCE!r}"
            )
        if tuple(policy.required_scopes) != (contract.SCOPE,):
            raise ValueError(
                f"authenticator required_scopes {tuple(policy.required_scopes)!r} "
                f"does not equal ({contract.SCOPE!r},)"
            )


async def _reject_any_body(request: Request) -> JSONResponse | None:
    """Refuse on the first non-empty body chunk, BEFORE the client is read.

    Returns the refusal JSONResponse (caller sends + returns), or None.
    Only an empty body (or no body) is permitted; chunked transfer or any
    non-empty payload - including a stray single byte - is a 400.
    """
    received_nonempty = False
    try:
        async for chunk in request.stream():
            if chunk:
                return _refuse_json(400, "invalid_input")
    except Exception:
        # A malformed stream counts as a body present, refusing as 400.
        return _refuse_json(400, "invalid_input")
    if received_nonempty:
        return _refuse_json(400, "invalid_input")
    return None


def _check_authorize(
    authorize_principal: Callable[[VerifiedPrincipal], bool], principal: VerifiedPrincipal,
) -> JSONResponse | None:
    """Return None iff the installed owner client permits this principal."""
    try:
        permitted = authorize_principal(principal) is True
    except Exception:
        return _refuse_json(503, "internal_error")
    if not permitted:
        return _refuse_json(403, "access_denied")
    return None


async def programs_current(
    request: Request, *, config: WorkspaceAppConfig,
) -> JSONResponse:
    """Handle ``GET /workspace/programs/current``.

    Sequence (each stage refuses before the next runs):

    1. Authenticate the bearer via the shared ``_authenticate`` (any failure
       here is an existing A1 error envelope).
    2. Refuse a non-empty body.
    3. The programs endpoint carries no selection; any query string is 400.
    4. Reject unless the installed owner client permits the principal.
    5. Build and validate the closed frame; dispatch via ``client.request``.
    6. Recheck the bearer ``expires_at`` against ``config.now()`` and the
       installed owner permission once more before returning the client
       envelope — a permission revocation or clock expiry that happens
       during the read produces a 403, never an unauthorized disclosure.
    """
    principal_or_response = await _authenticate(
        request, config.authenticator, clock=config.now,
    )
    if isinstance(principal_or_response, JSONResponse):
        # Re-attach the canonical Cache-Control so an A1 refusal is
        # never cached. _authenticate leaves its own (correct) status code.
        return _with_no_store(principal_or_response)
    principal = principal_or_response

    body_response = await _reject_any_body(request)
    if body_response is not None:
        return body_response

    raw_query = request.scope.get("query_string") or b""
    if raw_query:
        return _refuse_json(400, "invalid_input")

    permit = _check_authorize(config.authorize_principal, principal)
    if permit is not None:
        return permit

    try:
        permission_before = contract.permission_stamp(config.authorize_principal, principal)
        principal_frame = contract.principal_frame(principal)
    except ValueError:
        return _refuse_json(403, "access_denied")

    try:
        frame = contract.validate_frame({
            "schema": contract.FRAME_SCHEMA,
            "operation": "programs",
            "selection": None,
            "principal": principal_frame,
        })
    except ValueError:
        return _refuse_json(400, "invalid_input")

    try:
        envelope = await config.client.request(frame)
    except Exception:
        # Cancellation or any other request-stage exception: a closed 503,
        # never a leaked traceback.  Note: ``asyncio.CancelledError`` is a
        # ``BaseException`` subclass on Python 3.8+; this branch will NOT
        # catch it, so it propagates upwards and cancels this task cleanly.
        return _refuse_json(503, "internal_error")

    try:
        instant = config.now()
        if type(instant) is not int or instant >= principal.expires_at:
            return _refuse_json(403, "access_denied")
    except Exception:
        return _refuse_json(503, "internal_error")

    permit_after = _check_authorize(config.authorize_principal, principal)
    if permit_after is not None:
        return permit_after

    try:
        if contract.permission_stamp(config.authorize_principal, principal) != permission_before:
            return _refuse_json(403, "access_denied")
    except Exception:
        return _refuse_json(403, "access_denied")
    return _envelope_response(envelope)


async def work_current(
    request: Request, *, config: WorkspaceAppConfig,
) -> JSONResponse:
    """Handle ``GET /workspace/work/current``.

    Same envelope as :func:`programs_current`; no selection, no query
    string, no body.  Operates on the closed ``operation: "work"`` frame
    that the read service turns into a work-queue projection through the
    existing workspace read seam.
    """
    principal_or_response = await _authenticate(
        request, config.authenticator, clock=config.now,
    )
    if isinstance(principal_or_response, JSONResponse):
        return _with_no_store(principal_or_response)
    principal = principal_or_response

    body_response = await _reject_any_body(request)
    if body_response is not None:
        return body_response

    raw_query = request.scope.get("query_string") or b""
    if raw_query:
        return _refuse_json(400, "invalid_input")

    permit = _check_authorize(config.authorize_principal, principal)
    if permit is not None:
        return permit

    try:
        permission_before = contract.permission_stamp(config.authorize_principal, principal)
        principal_frame = contract.principal_frame(principal)
    except ValueError:
        return _refuse_json(403, "access_denied")

    try:
        frame = contract.validate_frame({
            "schema": contract.FRAME_SCHEMA,
            "operation": "work",
            "selection": None,
            "principal": principal_frame,
        })
    except ValueError:
        return _refuse_json(400, "invalid_input")

    try:
        envelope = await config.client.request(frame)
    except Exception:
        return _refuse_json(503, "internal_error")

    try:
        instant = config.now()
        if type(instant) is not int or instant >= principal.expires_at:
            return _refuse_json(403, "access_denied")
    except Exception:
        return _refuse_json(503, "internal_error")

    permit_after = _check_authorize(config.authorize_principal, principal)
    if permit_after is not None:
        return permit_after

    try:
        if contract.permission_stamp(config.authorize_principal, principal) != permission_before:
            return _refuse_json(403, "access_denied")
    except Exception:
        return _refuse_json(403, "access_denied")
    return _envelope_response(envelope)


async def mission_current(
    request: Request, *, config: WorkspaceAppConfig,
) -> JSONResponse:
    """Handle ``GET /workspace/mission/current?work_ref=WS:...&root_job_id=JOB-...``.

    Same envelope as :func:`programs_current`; selection parsed and
    validated through :func:`contract.selection` exactly once, here, before
    any client call.
    """
    principal_or_response = await _authenticate(
        request, config.authenticator, clock=config.now,
    )
    if isinstance(principal_or_response, JSONResponse):
        return _with_no_store(principal_or_response)
    principal = principal_or_response

    body_response = await _reject_any_body(request)
    if body_response is not None:
        return body_response

    raw_query: bytes = request.scope.get("query_string") or b""
    if not raw_query:
        return _refuse_json(400, "invalid_input")
    parsed_query = _decode_query(raw_query)
    selection_value, ok = _mission_selection(parsed_query)
    if not ok:
        return _refuse_json(400, "invalid_input")
    assert selection_value is not None

    permit = _check_authorize(config.authorize_principal, principal)
    if permit is not None:
        return permit

    try:
        permission_before = contract.permission_stamp(config.authorize_principal, principal)
        principal_frame = contract.principal_frame(principal)
    except ValueError:
        return _refuse_json(403, "access_denied")

    try:
        frame = contract.validate_frame({
            "schema": contract.FRAME_SCHEMA,
            "operation": "mission",
            "selection": contract.selection(selection_value),
            "principal": principal_frame,
        })
    except ValueError:
        return _refuse_json(400, "invalid_input")

    try:
        envelope = await config.client.request(frame)
    except Exception:
        return _refuse_json(503, "internal_error")

    try:
        instant = config.now()
        if type(instant) is not int or instant >= principal.expires_at:
            return _refuse_json(403, "access_denied")
    except Exception:
        return _refuse_json(503, "internal_error")

    permit_after = _check_authorize(config.authorize_principal, principal)
    if permit_after is not None:
        return permit_after

    try:
        if contract.permission_stamp(config.authorize_principal, principal) != permission_before:
            return _refuse_json(403, "access_denied")
    except Exception:
        return _refuse_json(403, "access_denied")
    return _envelope_response(envelope)


async def byok_roles_current(request: Request, *, config: WorkspaceAppConfig) -> Response:
    """One fixed metadata read; no body, selection, credential or action input."""
    from common import workspace_byok_read_contract as wire
    principal = await _authenticate(request, config.authenticator, clock=config.now)
    if isinstance(principal, JSONResponse):
        return _with_no_store(principal)
    refused = await _reject_any_body(request)
    if refused is not None:
        return refused
    if request.scope.get("query_string"):
        return _refuse_json(HTTPStatus.BAD_REQUEST, "invalid_input")
    authorizer, client = config.authorize_principal, config.client
    try:
        stamps = _control_room_permissions((authorizer,), principal)
        frame = wire.validate_frame({"schema": wire.FRAME_SCHEMA, "operation": wire.OPERATION,
                                     "principal": contract.principal_frame(principal)})
    except Exception:
        return _refuse_json(HTTPStatus.FORBIDDEN, "access_denied")
    try:
        envelope = await client.request(frame)
    except Exception:
        return _refuse_json(HTTPStatus.SERVICE_UNAVAILABLE, "source_unavailable")
    try:
        if (config.authorize_principal is not authorizer or config.client is not client
                or _control_room_permissions((authorizer,), principal) != stamps):
            raise ValueError("access_denied")
        instant = config.now()
        if type(instant) is not int or not 0 <= instant < principal.expires_at:
            raise ValueError("access_denied")
    except Exception:
        return _refuse_json(HTTPStatus.FORBIDDEN, "access_denied")
    if type(envelope) is dict and envelope.get("ok") is False:
        return _envelope_response(envelope)
    try:
        if type(envelope) is not dict or set(envelope) != {"ok", "result"} or envelope["ok"] is not True:
            raise ValueError("source_unavailable")
        body = wire.validate_body(envelope["result"])
        if not wire.current(body, now_ms=instant * 1000):
            body = wire.unavailable("SOURCE_STALE")
        raw = contract.bounded_canonical(body, limit=wire.MAX_RESPONSE_BYTES - 1)
    except Exception:
        raw = contract.canonical(wire.unavailable())
    return Response(raw, media_type="application/json", headers={"Cache-Control": "no-store"})


async def control_room_current(
    request: Request, *, config: WorkspaceAppConfig, operation: str,
) -> JSONResponse:
    """Authenticated incumbent CCR READ with a separate Discovery grant."""
    from common.workspace_control_room_read_contract import (
        FRAME_SCHEMA as CCR_READ_FRAME_SCHEMA, validate_frame as validate_ccr_read_frame,
    )
    if operation not in {"state", "discover"}:
        return _refuse_json(400, "invalid_input")
    principal_or_response = await _authenticate(
        request, config.authenticator, clock=config.now,
    )
    if isinstance(principal_or_response, JSONResponse):
        return _with_no_store(principal_or_response)
    principal = principal_or_response
    refused = await _reject_any_body(request)
    if refused is not None:
        return refused
    if request.scope.get("query_string"):
        return _refuse_json(400, "invalid_input")
    authorizers = ((config.authorize_principal, config.authorize_discovery)
                   if operation == "discover" else (config.authorize_principal,))
    try:
        stamps = _control_room_permissions(authorizers, principal)
        frame = validate_ccr_read_frame({
            "schema": CCR_READ_FRAME_SCHEMA, "operation": operation,
            "principal": contract.principal_frame(principal),
        })
    except Exception:
        return _refuse_json(403, "access_denied")
    try:
        envelope = await config.client.request(frame)
    except Exception:
        return _refuse_json(503, "internal_error")
    try:
        if _control_room_permissions(authorizers, principal) != stamps:
            raise ValueError("access_denied")
        if (config.authorize_principal is not authorizers[0]
                or (operation == "discover" and config.authorize_discovery is not authorizers[1])):
            raise ValueError("access_denied")
        # Permission loaders may block. Expiry is sampled after both gates,
        # immediately before READ release, never used to rewrite an action.
        current = config.now()
        if type(current) is not int or not 0 <= current < principal.expires_at:
            raise ValueError("access_denied")
    except Exception:
        return _refuse_json(403, "access_denied")
    return _envelope_response(envelope)


async def fabric_current(request: Request, *, config: WorkspaceAppConfig, operation: str) -> Response:
    """Fixed metadata GETs; current entitlement is checked on both boundaries."""
    from common import executive_workspace_fabric_contract as fabric
    principal = await _authenticate(request, config.authenticator, clock=config.now)
    if isinstance(principal, JSONResponse):
        return _with_no_store(principal)
    refused = await _reject_any_body(request)
    if refused is not None:
        return refused
    raw_query = request.scope.get("query_string") or b""
    try:
        if operation == fabric.CATALOG_OPERATION:
            if raw_query:
                raise ValueError("invalid_input")
            selected = None
        elif operation == fabric.STATUS_OPERATION:
            selected = fabric.selection(dict(_decode_query(raw_query)))
        else:
            raise ValueError("invalid_input")
    except (TypeError, ValueError):
        return _refuse_json(400, "invalid_input")
    try:
        authorizer, client = config.authorize_principal, config.client
        stamps = _control_room_permissions((authorizer,), principal)
        frame = fabric.validate_frame({"schema": fabric.FRAME_SCHEMA, "operation": operation,
            "selection": selected, "principal": contract.principal_frame(principal)})
    except Exception:
        return _refuse_json(403, "access_denied")
    try:
        envelope = await client.request(frame)
    except Exception:
        return _refuse_json(503, "source_unavailable")
    try:
        if (config.authorize_principal is not authorizer or config.client is not client
                or _control_room_permissions((authorizer,), principal) != stamps):
            raise ValueError("access_denied")
        current = config.now()
        if type(current) is not int or not 0 <= current < principal.expires_at:
            raise ValueError("access_denied")
    except Exception:
        return _refuse_json(403, "access_denied")
    if type(envelope) is dict and envelope.get("ok") is False:
        return _envelope_response(envelope)
    try:
        if type(envelope) is not dict or set(envelope) != {"ok", "result"} or envelope["ok"] is not True:
            raise ValueError("source_unavailable")
        result = (fabric.validate_catalog(envelope["result"]) if operation == fabric.CATALOG_OPERATION
            else fabric.status_metadata(envelope["result"], **selected))
        # Native extra fields are stripped before the public response, even if
        # an otherwise valid private producer accidentally includes raw fields.
        raw = contract.bounded_canonical(result, limit=fabric.ceiling(operation))
    except (TypeError, ValueError, KeyError):
        return _refuse_json(503, "source_unavailable")
    return Response(raw, status_code=200, media_type="application/json", headers={"Cache-Control": "no-store"})


def _control_room_permissions(authorizers, principal):
    """Current selected grants on the existing sealed membership owner."""
    stamps = []
    for authorize in authorizers:
        if not callable(authorize) or authorize(principal) is not True:
            raise ValueError("access_denied")
        stamp = contract.permission_stamp(authorize, principal)
        if stamp is None:
            raise ValueError("access_denied")
        stamps.append(stamp)
    return tuple(stamps)


def _action_http_response(result):
    """Expose the qualified action result itself, retaining its disposition."""
    return Response(
        ccr_action.canonical(result), status_code=result["status"],
        media_type="application/json", headers={"Cache-Control": "no-store"},
    )


def _action_refusal(operation, *, code, status):
    return _action_http_response(ccr_action.refused_result(
        operation, code=code, status=status,
    ))


async def control_room_action(request: Request, *, config: WorkspaceAppConfig,
                              operation: str) -> Response:
    """One fixed action on the existing authenticated App transport.

    Authentication is admission authority. Once the client is invoked, this
    edge preserves its original effect outcome rather than applying the
    READ release-time withholding rule to a potentially modifying operation.
    """
    if operation not in ccr_action.OPERATIONS:
        return _refuse_json(400, "invalid_input")
    principal_or_response = await _authenticate(
        request, config.authenticator, clock=config.now,
    )
    if isinstance(principal_or_response, JSONResponse):
        return _with_no_store(principal_or_response)
    principal = principal_or_response
    if request.scope.get("query_string"):
        return _action_refusal(operation, code="invalid_input", status=400)

    # Capture both permission and transport selections before streaming.
    try:
        client = config.client
        request_owner = client.request
        selected = (config.authorize_actions.get(operation)
                    if config.authorize_actions is not None else None)
        authorizers = (config.authorize_principal, selected)
        initial_permission = _control_room_permissions(authorizers, principal)
    except Exception:
        return _action_refusal(operation, code="access_denied", status=403)

    content_types = [
        value for name, value in request.scope.get("headers", ())
        if name.lower() == b"content-type"
    ]
    if (len(content_types) != 1
            or content_types[0].split(b";", 1)[0].strip().lower() != b"application/json"):
        return _action_refusal(operation, code="invalid_input", status=400)

    body = bytearray()
    try:
        async for chunk in request.stream():
            if len(body) + len(chunk) > ccr_action.MAX_REQUEST_BYTES:
                return _action_refusal(operation, code="invalid_input", status=400)
            body.extend(chunk)
        payload = ccr_action.decode_payload(bytes(body), operation=operation)
        frame = ccr_action.validate_frame({
            "schema": ccr_action.FRAME_SCHEMA, "operation": operation,
            "principal": contract.principal_frame(principal),
            "admission_expires_at": principal.expires_at, "payload": payload,
        })
    except Exception:
        return _action_refusal(operation, code="invalid_input", status=400)

    try:
        if _control_room_permissions(authorizers, principal) != initial_permission:
            raise ValueError("access_denied")
        if (config.authorize_principal is not authorizers[0]
                or config.authorize_actions is None
                or config.authorize_actions.get(operation) is not authorizers[1]):
            raise ValueError("access_denied")
    except Exception:
        return _action_refusal(operation, code="access_denied", status=403)
    try:
        if config.client is not client or client.request != request_owner:
            raise ValueError("source_unavailable")
    except Exception:
        return _action_refusal(operation, code="source_unavailable", status=503)
    try:
        instant = config.now()
        if type(instant) is not int or not 0 <= instant < principal.expires_at:
            raise ValueError("access_denied")
    except Exception:
        return _action_refusal(operation, code="access_denied", status=403)

    # Invocation starts here. No exception after this boundary proves that
    # the original operation was not dispatched, and there is no retry.
    try:
        owned = asyncio.create_task(request_owner(frame))
        try:
            envelope = await await_owned(owned)
        except asyncio.CancelledError:
            # await_owned retains the same child until terminal. A qualified
            # completed response survives remembered parent cancellation.
            if not owned.done() or owned.cancelled():
                raise
            envelope = owned.result()
        if (type(envelope) is not dict or set(envelope) != {"ok", "result"}
                or envelope["ok"] is not True):
            raise ValueError("source_unavailable")
        result = ccr_action.validate_result(envelope["result"], operation=operation)
    except (Exception, asyncio.CancelledError):
        result = ccr_action.unknown_result(operation)
    return _action_http_response(result)


def _with_no_store(response: JSONResponse) -> JSONResponse:
    """Attach the canonical ``Cache-Control: no-store`` to an A1 JSONResponse
    in place.  Starlette's :class:`MutableHeaders` supports in-place update,
    so we never rebuild the response body."""

    response.headers["Cache-Control"] = "no-store"
    response.headers.setdefault("content-type", "application/json")
    return response


async def _dispatch_v2(
    request: Request,
    *,
    config: WorkspaceAppConfig,
    operation: str,
    required_keys: frozenset[str],
    response_fn,
) -> JSONResponse:
    """Shared v2 handler skeleton for ``mission_v3`` and ``result``.

    Mirrors the v1 envelope pipeline: A1 authentication, body refusal, raw
    query parsing through the strict v2 decoder, exact selection validation,
    owner permission gate, frame build/dispatch, post-read permission recheck,
    and finally the operation-specific envelope translation.  The two
    operations differ only in their closed selection grammar and the body's
    HTTP status mapping.
    """

    principal_or_response = await _authenticate(
        request, config.authenticator, clock=config.now,
    )
    if isinstance(principal_or_response, JSONResponse):
        return _with_no_store(principal_or_response)
    principal = principal_or_response

    body_response = await _reject_any_body(request)
    if body_response is not None:
        return body_response

    raw_query: bytes = request.scope.get("query_string") or b""
    if not raw_query:
        return _refuse_json(400, "invalid_input")
    parsed_query = _decode_v2_query(raw_query, required_keys=required_keys)
    selection_value = _dispatch_v2_selection(operation, parsed_query)
    if selection_value is None:
        return _refuse_json(400, "invalid_input")

    permit = _check_authorize(config.authorize_principal, principal)
    if permit is not None:
        return permit

    try:
        permission_before = contract.permission_stamp(config.authorize_principal, principal)
        principal_frame = contract.principal_frame(principal)
        latest_gate = None
        latest_before = None
        if operation in {"project_knowledge_catalogue", "project_knowledge_memory", "project_knowledge_source", "project_discovery_source"}:
            context = config.source_operation_context
            if context is not None and context.policy == config.authenticator.policy:
                from integrations.mastermind_workspace_app.project_authoring_grant import workspace_project_authorizers
                latest_gate, _ = workspace_project_authorizers(policy=context.policy,
                    load_bindings=context._load_bindings,action="read_latest_project_data")
                if latest_gate(principal) is True:
                    latest_before = latest_gate.binding_digest(principal)
            if operation == "project_discovery_source" and latest_before is None:
                return _refuse_json(HTTPStatus.FORBIDDEN, "access_denied")
    except ValueError:
        return _refuse_json(403, "access_denied")

    try:
        if operation == "project_direction":
            from common import workspace_project_direction_contract as direction_wire
            frame = direction_wire.validate_frame({"schema": direction_wire.FRAME_SCHEMA,
                "operation": direction_wire.OPERATION, "selection": selection_value, "principal": principal_frame})
        elif operation == "autonomy":
            from common import workspace_autonomy_read_contract as autonomy_wire
            frame = autonomy_wire.validate_frame({"schema": autonomy_wire.FRAME_SCHEMA,
                "operation": autonomy_wire.OPERATION, "selection": selection_value,
                "principal": principal_frame})
        elif operation == "project_session":
            from common import workspace_project_session_contract as session_wire
            frame = session_wire.validate_frame({"schema": session_wire.FRAME_SCHEMA,
                "operation": session_wire.OPERATION, "selection": selection_value, "principal": principal_frame})
        elif operation in ("project_knowledge_catalogue", "project_knowledge_memory", "project_knowledge_source", "project_discovery_source"):
            from common import workspace_project_knowledge_read_contract as knowledge_wire
            frame = knowledge_wire.validate_frame({"schema": knowledge_wire.frame_schema(operation),
                "operation": operation, "selection": selection_value, "principal": principal_frame})
        elif operation == "project_journal":
            from common import workspace_project_journal_contract as plan_wire
            frame = plan_wire.validate_frame({
                "schema": plan_wire.FRAME_SCHEMA, "operation": plan_wire.OPERATION,
                "selection": selection_value, "principal": principal_frame,
            })
        elif operation == "project_instructions":
            from common import workspace_project_instructions_contract as instructions_wire
            frame = instructions_wire.validate_frame({"schema": instructions_wire.FRAME_SCHEMA,
                "operation": instructions_wire.OPERATION, "selection": selection_value, "principal": principal_frame})
        elif operation == "project_plan":
            from common import workspace_project_plan_contract as plan_wire
            frame = plan_wire.validate_frame({
                "schema": plan_wire.FRAME_SCHEMA, "operation": plan_wire.OPERATION,
                "selection": selection_value, "principal": principal_frame,
            })
        elif operation == "mission_v4_original":
            from common import product_acceptance_acquisition_contract as acquisition_contract
            frame = acquisition_contract.validate_frame({
                "schema": acquisition_contract.FRAME_SCHEMA, "operation": operation,
                "selection": selection_value, "principal": principal_frame,
            })
        elif operation == "mission_v4":
            from common import product_acceptance_read_contract as acceptance_contract
            frame = acceptance_contract.validate_frame({
                "schema": acceptance_contract.FRAME_SCHEMA, "operation": operation,
                "selection": selection_value, "principal": principal_frame,
            })
        elif operation == "resource_capacity":
            from common import workspace_resource_capacity_contract as capacity_wire
            frame = capacity_wire.validate_frame({"schema": capacity_wire.FRAME_SCHEMA, "operation": operation,
                     "selection": selection_value, "principal": principal_frame})
        elif operation == "execution_return":
            from common import workspace_execution_return_contract as return_wire
            frame = return_wire.validate_frame({"schema": return_wire.FRAME_SCHEMA,
                "operation": return_wire.OPERATION, "selection": selection_value, "principal": principal_frame})
        elif operation == "retained_activity":
            from common import executive_workspace_activity_contract as activity
            frame = activity.validate_frame({
                "schema": activity.FRAME_SCHEMA, "operation": activity.OPERATION,
                "selection": activity.selection(selection_value), "principal": principal_frame,
            })
        elif operation == "admitted_plan":
            frame = contract.validate_v3_frame({
                "schema": contract.FRAME_SCHEMA_V3, "operation": operation,
                "selection": contract.v3_selection(selection_value), "principal": principal_frame,
            })
        elif operation == "mission_result":
            frame = contract.validate_mission_result_frame({
                "schema": contract.MISSION_RESULT_FRAME_SCHEMA,
                "operation": contract.MISSION_RESULT_OPERATION,
                "selection": contract.v2_selection(selection_value, "result"),
                "principal": principal_frame,
            })
        else:
            frame = contract.validate_v2_frame({
                "schema": contract.FRAME_SCHEMA_V2,
                "operation": operation,
                "selection": contract.v2_selection(selection_value, operation),
                "principal": principal_frame,
            })
    except ValueError:
        return _refuse_json(400, "invalid_input")

    try:
        envelope = await config.client.request(frame)
    except Exception:
        # Cancellation or any other request-stage exception: a closed 503,
        # never a leaked traceback.  ``asyncio.CancelledError`` propagates.
        return _refuse_json(503, "internal_error")

    try:
        instant = config.now()
        if type(instant) is not int or instant >= principal.expires_at:
            return _refuse_json(403, "access_denied")
    except Exception:
        return _refuse_json(503, "internal_error")

    permit_after = _check_authorize(config.authorize_principal, principal)
    if permit_after is not None:
        return permit_after

    try:
        if contract.permission_stamp(config.authorize_principal, principal) != permission_before:
            return _refuse_json(403, "access_denied")
        if latest_before is not None and (latest_gate(principal) is not True
                or latest_gate.binding_digest(principal) != latest_before):
            return _refuse_json(403, "access_denied")
        if (operation in {"project_knowledge_catalogue", "project_knowledge_memory", "project_knowledge_source", "project_discovery_source"}
                and type(envelope) is dict and type(envelope.get("result")) is dict
                and envelope["result"].get("data_observation") is not None and latest_before is None):
            return _refuse_json(403, "access_denied")
    except Exception:
        return _refuse_json(403, "access_denied")
    if operation in ("execution_return", "admitted_plan", "retained_activity", "resource_capacity", "result_references", "project_plan", "project_journal", "project_session", "project_direction", "project_knowledge_catalogue", "project_knowledge_memory", "project_knowledge_source", "project_discovery_source", "autonomy", "project_instructions") and isinstance(envelope, dict) and envelope.get("ok") is True:
        body = envelope.get("result")
        expected_selection = ({key: item for key, item in selection_value.items() if key not in {"expected_revision", "expected_source_commit"}}
                              if operation in {"project_knowledge_source", "project_discovery_source"} else selection_value)
        if type(body) is not dict or body.get("selection") != expected_selection:
            return _refuse_json(503, "source_unavailable")
        if (operation == "project_knowledge_source" and body.get("availability") == "AVAILABLE"
                and (type(body.get("source")) is not dict
                     or body["source"].get("revision") != selection_value["expected_revision"])):
            return _refuse_json(503, "source_unavailable")
        if (operation == "project_discovery_source" and body.get("availability") == "AVAILABLE"
                and (type(body.get("source")) is not dict
                     or body["source"].get("commit") != selection_value["expected_source_commit"])):
            return _refuse_json(HTTPStatus.SERVICE_UNAVAILABLE, "source_unavailable")
    if operation == "mission_v4":
        return _mission_v4_envelope_response(envelope, selection_value)
    if operation == "mission_v4_original":
        return _mission_v4_original_envelope_response(envelope, selection_value)
    if operation == "project_instructions":
        response=_project_instructions_envelope_response(envelope,principal=principal)
        # Identity is published only by the real authenticated READ owner,
        # after source qualification and a final current grant/expiry fence.
        try:
            if (type(config.now()) is not int or not 0<=config.now()<principal.expires_at
                    or _check_authorize(config.authorize_principal,principal) is not None
                    or contract.permission_stamp(config.authorize_principal,principal)!=permission_before):
                return _refuse_json(403,"access_denied")
        except Exception:return _refuse_json(403,"access_denied")
        return response
    return response_fn(envelope)


def _mission_v4_envelope_response(envelope, selected):
    from common import product_acceptance_read_contract as acceptance_contract
    if type(envelope) is dict and envelope.get("ok") is True:
        try:
            body = envelope["result"]
            if (type(body) is not dict or set(body) != {"schema", "mission", "product_acceptance"}
                    or body["schema"] != acceptance_contract.MISSION_SCHEMA):
                raise ValueError("source_unavailable")
            mission = body["mission"]
            if (type(mission) is not dict or mission.get("schema") != "mastermind.mission_workspace.v3"
                    or mission["program"]["work_ref"] != selected["work_ref"]
                    or mission["mission"]["root_job_id"] != selected["root_job_id"]):
                raise ValueError("source_unavailable")
            view = acceptance_contract.validate_view(body["product_acceptance"], selected=selected)
            if view["state"] == "ACCEPTED" and mission["read_state"]["state"] != "CURRENT":
                raise ValueError("source_unavailable")
        except (TypeError, ValueError, KeyError):
            return _refuse_json(503, "source_unavailable")
    # Same existing Mission ceiling and closed refusal projection.
    return _v2_envelope_response(envelope, operation="mission_v3")


def _mission_v4_original_envelope_response(envelope, selected):
    from common import product_acceptance_read_contract as acceptance_contract
    if type(envelope) is dict and envelope.get("ok") is True:
        try:
            canonical_selection = acceptance_contract.selection(
                envelope["result"]["product_acceptance"]["selection"])
            if {k: canonical_selection[k] for k in ("work_ref", "root_job_id")} != selected:
                raise ValueError("source_unavailable")
        except (TypeError, ValueError, KeyError):
            return _refuse_json(503, "source_unavailable")
        # The exact key came from the authenticated installed owner response,
        # never the query. Reuse all original Mission/receipt/body validation.
        return _mission_v4_envelope_response(envelope, canonical_selection)
    return _v2_envelope_response(envelope, operation="mission_v3")


async def mission_v4_current(request: Request, *, config: WorkspaceAppConfig) -> JSONResponse:
    # Only the explicit canonical mode key selects acquisition. Encoded aliases,
    # duplicates and mixed modes still fail the strict decoder before the owner.
    raw_query = request.scope.get("query_string") or b""
    if b"read_mode" in {part.partition(b"=")[0] for part in raw_query.split(b"&")}:
        return await _dispatch_v2(request, config=config, operation="mission_v4_original",
            required_keys=frozenset({"work_ref", "root_job_id", "read_mode"}), response_fn=None)
    return await _dispatch_v2(request, config=config, operation="mission_v4",
        required_keys=frozenset({"work_ref", "root_job_id", "request_message_key"}), response_fn=None)


async def mission_v3_current(
    request: Request, *, config: WorkspaceAppConfig,
) -> JSONResponse:
    """Handle ``GET /workspace/mission/v3/current``.

    Same envelope as v1 mission; the v3 selection grammar differs and the
    adapter below resolves canonical Mission v3 owner output once the
    composer is admitted by the parent.
    """
    return await _dispatch_v2(
        request,
        config=config,
        operation="mission_v3",
        required_keys=_MISSION_QUERY_KEYS,
        response_fn=lambda envelope: _v2_envelope_response(
            envelope, operation="mission_v3"),
    )


def _mission_result_envelope_response(envelope: Mapping[str, Any]) -> JSONResponse:
    """Return the compound BODY. The socket ceiling stays the incumbent 2_000_000."""

    if type(envelope) is dict and envelope.get("ok") is True:
        result = envelope.get("result")
        try:
            if set(envelope) != {"ok", "result"} or type(result) is not dict:
                raise ValueError("invalid_response")
            contract.validate_mission_result_body(result)
            body = contract.bounded_canonical(dict(result), limit=contract.MAX_COMPOUND_RESPONSE_BYTES)
        except (TypeError, ValueError):
            return _refuse_json(503, "source_unavailable")
        status = 503 if result.get("availability") == "UNAVAILABLE" else 200
        return Response(body, status_code=status, media_type="application/json",
                        headers={"Cache-Control": "no-store"})
    return _v2_envelope_response(envelope, operation="mission_v3")


async def mission_result_current(
    request: Request, *, config: WorkspaceAppConfig,
) -> JSONResponse:
    """Handle ``GET /workspace/mission-result/current``.

    The five-field Result selector, the existing authentication and permission
    recheck, and one App-peer Unix frame. No new account or grant rule.
    """

    return await _dispatch_v2(
        request,
        config=config,
        operation="mission_result",
        required_keys=_RESULT_QUERY_KEYS,
        response_fn=_mission_result_envelope_response,
    )


def _execution_return_envelope_response(envelope):
    from common import workspace_execution_return_contract as return_wire
    from control_plane.workspace_execution_return_read import validate_body
    if type(envelope) is dict and envelope.get("ok") is True:
        try:
            if set(envelope) != {"ok", "result"}:
                raise ValueError("invalid_envelope")
            result = validate_body(envelope["result"])
            body = contract.bounded_canonical(result, limit=return_wire.MAX_RESPONSE_BYTES)
        except (TypeError, ValueError):
            return _refuse_json(503, "source_unavailable")
        return Response(body, status_code=503 if result["availability"] == "UNAVAILABLE" else 200,
                        media_type="application/json", headers={"Cache-Control": "no-store"})
    return _v2_envelope_response(envelope, operation="result")


async def execution_return_current(request: Request, *, config: WorkspaceAppConfig) -> Response:
    """One exact retained return through the existing authenticated read pipeline."""
    return await _dispatch_v2(request, config=config, operation="execution_return",
        required_keys=_RESULT_QUERY_KEYS, response_fn=_execution_return_envelope_response)


async def result_current(
    request: Request, *, config: WorkspaceAppConfig,
) -> JSONResponse:
    """Handle ``GET /workspace/result/current``.

    Exact five-field selection grammar.  The result adapter bracket is the
    same five-stage pipeline as v1: authenticate, validate selection,
    qualify the CCR work/root join, read the bounded Runtime role result,
    and recheck the same principal + non-null permission stamp before HTTP
    release.  The 16384-byte closed response ceiling is enforced both by the
    read service and a defense-in-depth check in :func:`_v2_envelope_response`.
    """
    return await _dispatch_v2(
        request,
        config=config,
        operation="result",
        required_keys=_RESULT_QUERY_KEYS,
        response_fn=lambda envelope: _v2_envelope_response(
            envelope, operation="result"),
    )


def _result_references_envelope_response(envelope):
    """Validate the closed retained-result-reference body before release.

    The producer's own closed validator re-checks the seven-key wrapper and
    its two-field selection, and the whole socket envelope must still fit
    the frozen 16384-byte ceiling.  A typed producer unavailable body keeps
    its single legal projection as an HTTP 503 through the shared v2
    translation; nothing outside the closed body escapes to HTTP.
    """
    from control_plane.workspace_result_references import validate_body
    if type(envelope) is dict and envelope.get("ok") is True:
        try:
            if set(envelope) != {"ok", "result"}:
                raise ValueError("invalid_response")
            body = envelope["result"]
            selected = contract.v2_selection(body["selection"], "result_references")
            validate_body(body, selected)
            contract.bounded_canonical(envelope, limit=contract.MAX_RESULT_RESPONSE_BYTES - 1)
        except (TypeError, ValueError, KeyError):
            return _refuse_json(503, "source_unavailable")
    return _v2_envelope_response(envelope, operation="result_references")


async def result_references_current(
    request: Request, *, config: WorkspaceAppConfig,
) -> JSONResponse:
    """Handle ``GET /workspace/result-references/current``.

    The retained-result navigation selector: the same authenticated v2
    pipeline as the result route under the closed two-field grammar only.
    No caller-supplied job, attempt, digest, path or URL field exists; the
    producer alone derives the actual completed references.
    """
    return await _dispatch_v2(
        request,
        config=config,
        operation="result_references",
        required_keys=_RESULT_REFERENCES_QUERY_KEYS,
        response_fn=_result_references_envelope_response,
    )


def _plan_envelope_response(envelope):
    """Bound the entire new response, retaining the producer's closed body."""
    if type(envelope) is dict and envelope.get("ok") is True:
        body = envelope.get("result")
        if (set(envelope) != {"ok", "result"} or type(body) is not dict
                or set(body) != {"schema", "selection", "availability", "reason_codes", "source_observation", "plan"}
                or body["schema"] != contract.PLAN_BODY_SCHEMA
                or body["availability"] not in ("AVAILABLE", "UNAVAILABLE")):
            return _refuse_json(503, "source_unavailable")
        try:
            selected = contract.v3_selection(body["selection"])
            if body["availability"] == "UNAVAILABLE":
                reasons = body["reason_codes"]
                if type(reasons) is not list or len(reasons) != 1 or envelope != contract.plan_unavailable(selected, reasons[0]):
                    return _refuse_json(503, "source_unavailable")
            else:
                if (body["reason_codes"] != [] or type(body["plan"]) is not dict
                        or body["plan"].get("root_job_id") != selected["root_job_id"]):
                    return _refuse_json(503, "source_unavailable")
                contract.validate_available_plan_observation(body["source_observation"], selected)
            try:
                contract.bounded_canonical(envelope, limit=contract.MAX_PLAN_RESPONSE_BYTES - 1)
            except (TypeError, ValueError):
                envelope = contract.plan_unavailable(selected, "RESPONSE_OVER_BUDGET")
        except (TypeError, ValueError):
            return _refuse_json(503, "source_unavailable")
    return _v2_envelope_response(envelope, operation="admitted_plan")


async def plan_current(request: Request, *, config: WorkspaceAppConfig) -> JSONResponse:
    return await _dispatch_v2(request, config=config, operation="admitted_plan",
                              required_keys=_MISSION_QUERY_KEYS, response_fn=_plan_envelope_response)


def _project_instructions_envelope_response(envelope,*,principal=None):
    from http import HTTPStatus
    from common import workspace_project_instructions_contract as wire
    if type(envelope) is not dict or envelope.get("ok") is not True:
        return _envelope_response(envelope)
    try:
        if set(envelope) != {"ok", "result"}: raise ValueError("invalid envelope")
        from integrations.mastermind_workspace_app.owner_context import workspace_owner_context
        body = wire.public_body(envelope["result"],recovery_identity=workspace_owner_context(principal))
        contract.bounded_canonical(envelope, limit=wire.MAX_RESPONSE_BYTES - 1)
        raw = contract.bounded_canonical(body, limit=wire.MAX_RESPONSE_BYTES - 1)
    except (TypeError, ValueError, KeyError, RecursionError): return _refuse_json(503, "source_unavailable")
    return Response(raw, status_code=HTTPStatus.OK if body["availability"] == "AVAILABLE" else HTTPStatus.SERVICE_UNAVAILABLE,
        media_type="application/json", headers={"Cache-Control": "no-store"})


async def project_instructions_current(request: Request, *, config: WorkspaceAppConfig):
    return await _dispatch_v2(request, config=config, operation="project_instructions",
        required_keys=frozenset({"work_ref"}), response_fn=_project_instructions_envelope_response)


def _project_plan_envelope_response(envelope):
    from common import workspace_project_plan_contract as plan_wire
    if type(envelope) is not dict or envelope.get("ok") is not True:
        return _envelope_response(envelope)
    try:
        if set(envelope) != {"ok", "result"}:
            raise ValueError("invalid envelope")
        body = plan_wire.validate_body(envelope["result"])
        contract.bounded_canonical(envelope, limit=plan_wire.MAX_RESPONSE_BYTES)
        raw = contract.bounded_canonical(body, limit=plan_wire.MAX_RESPONSE_BYTES)
    except (TypeError, ValueError, KeyError, RecursionError):
        return _refuse_json(503, "source_unavailable")
    return Response(raw, status_code=200 if body["availability"] == "AVAILABLE" else 503,
                    media_type="application/json", headers={"Cache-Control": "no-store"})


def _project_direction_envelope_response(envelope):
    from common import workspace_project_direction_contract as direction_wire
    if type(envelope) is not dict or envelope.get("ok") is not True:
        return _envelope_response(envelope)
    try:
        if set(envelope) != {"ok", "result"}:
            raise ValueError("invalid_response")
        body = direction_wire.validate_body(envelope["result"])
        contract.bounded_canonical(envelope, limit=direction_wire.MAX_RESPONSE_BYTES - 1)
        raw = contract.bounded_canonical(body, limit=direction_wire.MAX_RESPONSE_BYTES - 1)
    except (TypeError, ValueError, KeyError, RecursionError):
        return _refuse_json(503, "source_unavailable")
    return Response(raw, status_code=200 if body["availability"] == "AVAILABLE" else 503,
                    media_type="application/json", headers={"Cache-Control": "no-store"})


async def project_archive_current(request: Request, *, config: WorkspaceAppConfig) -> JSONResponse:
    """Existing READ authority, no caller catalogue/host/path/revision selectors."""
    from common import workspace_project_archive_contract as archive_wire
    principal = await _authenticate(request, config.authenticator, clock=config.now)
    if isinstance(principal, JSONResponse):
        return _with_no_store(principal)
    refusal = await _reject_any_body(request)
    if refusal is not None:
        return refusal
    cursor = None
    raw_query = request.scope.get("query_string") or b""
    if raw_query:
        try:
            cursor = archive_wire.page_selection(_decode_v2_query(raw_query,
                required_keys=frozenset({"after_work_ref", "catalogue_digest"})))
        except (ValueError, TypeError):
            return _refuse_json(400, "invalid_input")
    authorizer = config.authorize_principal
    refusal = _check_authorize(authorizer, principal)
    if refusal is not None:
        return refusal
    try:
        stamp = contract.permission_stamp(authorizer, principal)
        if stamp is None:
            return _refuse_json(403, "access_denied")
        if cursor is None:
            frame = archive_wire.validate_frame({"schema": archive_wire.FRAME_SCHEMA,
                "operation": archive_wire.OPERATION, "principal": contract.principal_frame(principal)})
        else:
            frame = archive_wire.validate_page_frame({"schema": archive_wire.PAGE_FRAME_SCHEMA,
                "operation": archive_wire.PAGE_OPERATION, "selection": cursor,
                "principal": contract.principal_frame(principal)})
    except (ValueError, TypeError):
        return _refuse_json(403, "access_denied")
    try:
        envelope = await config.client.request(frame)
    except Exception:
        return _refuse_json(503, "source_unavailable")
    try:
        now = config.now()
        if (type(now) is not int or now >= principal.expires_at or config.authorize_principal is not authorizer
                or authorizer(principal) is not True or contract.permission_stamp(authorizer, principal) != stamp):
            return _refuse_json(403, "access_denied")
    except Exception:
        return _refuse_json(403, "access_denied")
    if type(envelope) is not dict or envelope.get("ok") is not True:
        return _envelope_response(envelope)
    try:
        if set(envelope) != {"ok", "result"}:
            raise ValueError("source_unavailable")
        body = archive_wire.validate_body(envelope["result"])
        raw = contract.bounded_canonical(body, limit=archive_wire.MAX_RESPONSE_BYTES - 1)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return _refuse_json(503, "source_unavailable")
    return Response(raw, status_code=200 if body["availability"] == "AVAILABLE" else 503,
        media_type="application/json", headers={"Cache-Control": "no-store"})


async def project_direction_current(request: Request, *, config: WorkspaceAppConfig) -> JSONResponse:
    return await _dispatch_v2(request, config=config, operation="project_direction",
        required_keys=frozenset({"work_ref"}), response_fn=_project_direction_envelope_response)


async def project_plan_current(request: Request, *, config: WorkspaceAppConfig) -> JSONResponse:
    return await _dispatch_v2(request, config=config, operation="project_plan",
        required_keys=frozenset({"work_ref"}), response_fn=_project_plan_envelope_response)


def _project_knowledge_envelope_response(envelope, *, operation):
    from common import workspace_project_knowledge_read_contract as wire
    if type(envelope) is not dict or envelope.get("ok") is not True:
        return _envelope_response(envelope)
    try:
        if set(envelope) != {"ok", "result"}: raise ValueError("invalid envelope")
        body = wire.validate_body(envelope["result"], operation=operation)
        contract.bounded_canonical(envelope, limit=wire.MAX_RESPONSE_BYTES)
        raw = contract.bounded_canonical(body, limit=wire.MAX_RESPONSE_BYTES)
    except (TypeError, ValueError, KeyError, RecursionError):
        return _refuse_json(503, "source_unavailable")
    return Response(raw, status_code=200 if body["availability"] in ("AVAILABLE", "EMPTY") else 503,
                    media_type="application/json", headers={"Cache-Control": "no-store"})


async def project_knowledge_current(request: Request, *, config: WorkspaceAppConfig) -> JSONResponse:
    return await _dispatch_v2(request, config=config, operation="project_knowledge_catalogue",
        required_keys=frozenset({"work_ref"}),
        response_fn=lambda envelope: _project_knowledge_envelope_response(envelope, operation="project_knowledge_catalogue"))


async def project_memory_current(request: Request, *, config: WorkspaceAppConfig) -> JSONResponse:
    return await _dispatch_v2(request, config=config, operation="project_knowledge_memory",
        required_keys=frozenset({"work_ref"}),
        response_fn=lambda envelope: _project_knowledge_envelope_response(envelope, operation="project_knowledge_memory"))


async def project_source_current(request: Request, *, config: WorkspaceAppConfig) -> JSONResponse:
    return await _dispatch_v2(request, config=config, operation="project_knowledge_source",
        required_keys=frozenset({"work_ref", "source_ref", "expected_revision"}),
        response_fn=lambda envelope: _project_knowledge_envelope_response(envelope, operation="project_knowledge_source"))


async def project_discovery_source_current(request: Request, *, config: WorkspaceAppConfig) -> JSONResponse:
    return await _dispatch_v2(request, config=config, operation="project_discovery_source",
        required_keys=frozenset({"work_ref", "discovery_ref", "expected_source_commit"}),
        response_fn=lambda envelope: _project_knowledge_envelope_response(envelope, operation="project_discovery_source"))


def _project_journal_envelope_response(envelope):
    from common import workspace_project_journal_contract as plan_wire
    if type(envelope) is not dict or envelope.get("ok") is not True:
        return _envelope_response(envelope)
    try:
        if set(envelope) != {"ok", "result"}:
            raise ValueError("invalid envelope")
        body = plan_wire.validate_body(envelope["result"])
        contract.bounded_canonical(envelope, limit=plan_wire.MAX_RESPONSE_BYTES)
        raw = contract.bounded_canonical(body, limit=plan_wire.MAX_RESPONSE_BYTES)
    except (TypeError, ValueError, KeyError, RecursionError):
        return _refuse_json(503, "source_unavailable")
    return Response(raw, status_code=200 if body["availability"] == "AVAILABLE" else 503,
                    media_type="application/json", headers={"Cache-Control": "no-store"})


async def project_journal_current(request: Request, *, config: WorkspaceAppConfig) -> JSONResponse:
    return await _dispatch_v2(request, config=config, operation="project_journal",
        required_keys=frozenset({"work_ref"}), response_fn=_project_journal_envelope_response)


def _project_session_envelope_response(envelope):
    from common import workspace_project_session_contract as plan_wire
    if type(envelope) is not dict or envelope.get("ok") is not True:
        return _envelope_response(envelope)
    try:
        if set(envelope) != {"ok", "result"}:
            raise ValueError("invalid envelope")
        body = plan_wire.validate_body(envelope["result"])
        contract.bounded_canonical(envelope, limit=plan_wire.MAX_RESPONSE_BYTES)
        raw = contract.bounded_canonical(body, limit=plan_wire.MAX_RESPONSE_BYTES)
    except (TypeError, ValueError, KeyError, RecursionError):
        return _refuse_json(503, "source_unavailable")
    return Response(raw, status_code=200 if body["availability"] == "AVAILABLE" else 503,
                    media_type="application/json", headers={"Cache-Control": "no-store"})


async def project_session_current(request: Request, *, config: WorkspaceAppConfig) -> JSONResponse:
    return await _dispatch_v2(request, config=config, operation="project_session",
        required_keys=frozenset({"work_ref", "root_job_id"}), response_fn=_project_session_envelope_response)


def _autonomy_envelope_response(envelope):
    from common import workspace_autonomy_read_contract as autonomy_wire
    if type(envelope) is not dict or envelope.get("ok") is not True:
        return _envelope_response(envelope)
    try:
        if set(envelope) != {"ok", "result"}:
            raise ValueError("invalid_input")
        body = autonomy_wire.validate_body(envelope["result"])
        contract.bounded_canonical(envelope, limit=autonomy_wire.MAX_RESPONSE_BYTES - 1)
        raw = contract.bounded_canonical(body, limit=autonomy_wire.MAX_RESPONSE_BYTES - 1)
    except (TypeError, ValueError, KeyError, RecursionError):
        return _refuse_json(503, "source_unavailable")
    return Response(raw, status_code=200 if body["availability"] == "AVAILABLE" else 503,
                    media_type="application/json", headers={"Cache-Control": "no-store"})


async def autonomy_current(request: Request, *, config: WorkspaceAppConfig) -> JSONResponse:
    return await _dispatch_v2(request, config=config, operation="autonomy",
        required_keys=_MISSION_QUERY_KEYS, response_fn=_autonomy_envelope_response)


def _capacity_envelope_response(envelope):
    from common import workspace_resource_capacity_contract as capacity_wire
    if type(envelope) is dict and envelope.get("ok") is True:
        try:
            if set(envelope) != {"ok", "result"}:
                raise ValueError("invalid_response")
            body = envelope["result"]
            capacity_wire.validate_result(body, body["selection"])
            contract.bounded_canonical(envelope, limit=capacity_wire.MAX_RESPONSE_BYTES - 1)
        except (TypeError, ValueError, KeyError):
            return _refuse_json(503, "source_unavailable")
    return _v2_envelope_response(envelope, operation="result")


async def resource_capacity_current(request: Request, *, config: WorkspaceAppConfig) -> JSONResponse:
    return await _dispatch_v2(request, config=config, operation="resource_capacity",
        required_keys=_ACTIVITY_QUERY_KEYS, response_fn=_capacity_envelope_response)


def _activity_envelope_response(envelope):
    """Closed 16KiB App boundary; never echo raw owner or provider fields."""
    from common import executive_workspace_activity_contract as activity
    if type(envelope) is dict and envelope.get("ok") is True:
        try:
            if set(envelope) != {"ok", "result"}:
                raise ValueError("invalid_response")
            body = envelope["result"]
            selected = activity.selection(body["selection"])
            activity.validate_result(body, selected)
            contract.bounded_canonical(envelope, limit=activity.MAX_RESPONSE_BYTES - 1)
        except (TypeError, ValueError, KeyError):
            return _refuse_json(503, "source_unavailable")
    return _v2_envelope_response(envelope, operation="result")


async def activity_current(request: Request, *, config: WorkspaceAppConfig) -> JSONResponse:
    """One original Executive OHF Attempt, not a native machine/Fabric catalog."""
    return await _dispatch_v2(
        request, config=config, operation="retained_activity",
        required_keys=_ACTIVITY_QUERY_KEYS, response_fn=_activity_envelope_response,
    )


class _RawPathFence:
    """Refuse path aliases and methods outside each fixed route before auth."""

    #: Starlette also binds HEAD for GET routes; the exact map refuses it.
    _READ_ROUTES = (
        "/workspace/native-draft-identity/current",
        "/workspace/native-authorization-identity/acquisition/current",
        _PROGRAMS_ROUTE,
        _WORK_ROUTE,
        _MISSION_ROUTE,
        _MISSION_V3_ROUTE,
        _MISSION_V4_ROUTE,
        _RESULT_ROUTE,
        _EXECUTION_RETURN_ROUTE,
        _MISSION_RESULT_ROUTE,
        _RESULT_REFERENCES_ROUTE,
        _PLAN_ROUTE,
        _PROJECT_PLAN_ROUTE,
        _PROJECT_JOURNAL_ROUTE,
        _PROJECT_DIRECTION_ROUTE,
        _PROJECT_ARCHIVE_ROUTE,
        _PROJECT_SESSION_ROUTE,
        _AUTONOMY_ROUTE,
        _ACTIVITY_ROUTE,
        _RESOURCE_CAPACITY_ROUTE,
        _MODEL_CONFIGURATION_ROUTE,
        _CAPACITY_FABRIC_ROUTE,
        _T3_ATTEMPT_FLEET_ROUTE,
        "/workspace/company/current",
        _HOST_OBSERVATION_ROUTE,
        _FABRIC_CATALOG_ROUTE,
        _FABRIC_STATUS_ROUTE,
        _BYOK_ROLES_ROUTE,
        _CCR_STATE_ROUTE,
        _CCR_DISCOVER_ROUTE,
    )
    _ROUTE_METHODS = {
        **{path: "GET" for path in _READ_ROUTES},
        **{path: "POST" for path in _CCR_ACTION_ROUTES.values()},
        "/workspace/company/command": "POST",
    }

    def __init__(self, app: Any) -> None:
        self._app = app

    async def __call__(self, scope: Mapping[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") == "http":
            raw_path = scope.get("raw_path") or b""
            lowered = bytes(raw_path).lower()
            if b"%" in lowered or any(marker in lowered for marker in _SUSPICIOUS_RAW_PATH_MARKERS):
                response = JSONResponse(
                    {"ok": False, "status": 400,
                     "error": {"code": "invalid_input",
                               "message": "path contains an unsupported encoded separator"}},
                    status_code=400,
                    headers={"Cache-Control": "no-store", "Content-Type": "application/json"},
                )
                await response(scope, receive, send)
                return
            method = str(scope.get("method") or "").upper()
            path = scope.get("path") or ""
            allowed = self._ROUTE_METHODS.get(path)
            if allowed is not None and method != allowed:
                response = JSONResponse(
                    {"ok": False, "status": 405,
                     "error": {"code": "not_found",
                               "message": "method not allowed"}},
                    status_code=405,
                    headers={"Cache-Control": "no-store", "Content-Type": "application/json", "Allow": allowed},
                )
                await response(scope, receive, send)
                return
        await self._app(scope, receive, send)


def create_workspace_app(config: WorkspaceAppConfig) -> Any:
    """Build the fixed authenticated reads and explicitly granted CCR actions."""

    async def programs_endpoint(request: Request) -> JSONResponse:
        return await programs_current(request, config=config)

    async def source_operation_context_endpoint(request: Request) -> JSONResponse:
        principal = await _authenticate(request, config.authenticator, clock=config.now)
        if isinstance(principal, JSONResponse):
            return _with_no_store(principal)
        refused = await _reject_any_body(request)
        if refused is not None:
            return refused
        query = _decode_v2_query(request.scope.get("query_string", b""),
            required_keys=frozenset({"action"} if b"work_ref=" not in request.scope.get("query_string", b"")
                                    else {"action", "work_ref"}))
        if set(query) not in ({"action"}, {"action", "work_ref"}):
            return _refuse_json(400, "invalid_input")
        if "work_ref" not in query and query["action"] != "publish_project_proposal":
            return _refuse_json(400, "invalid_input")
        if (config.source_operation_context is None
                or config.source_operation_context.policy != config.authenticator.policy):
            return _refuse_json(503, "source_unavailable")
        try:
            permission = config.source_operation_context.bind(principal,
                action=query["action"], work_ref=query.get("work_ref"))
            result = permission.public_context()
            if principal.expires_at <= config.now() or not permission.check():
                return _refuse_json(403, "access_denied")
            return JSONResponse(result, headers={"Cache-Control": "no-store"})
        except PermissionError:
            return _refuse_json(403, "access_denied")
        except ValueError:
            return _refuse_json(400, "invalid_input")
        except Exception:
            return _refuse_json(503, "source_unavailable")

    def source_operation_endpoint(operation):
        async def endpoint(request):
            from integrations.mastermind_workspace_app.source_operation_http import source_operation_http
            return await source_operation_http(request, config=config, operation=operation)
        return endpoint

    async def work_endpoint(request: Request) -> JSONResponse:
        return await work_current(request, config=config)

    async def mission_endpoint(request: Request) -> JSONResponse:
        return await mission_current(request, config=config)

    async def mission_v3_endpoint(request: Request) -> JSONResponse:
        return await mission_v3_current(request, config=config)

    async def mission_v4_endpoint(request: Request) -> JSONResponse:
        return await mission_v4_current(request, config=config)

    async def execution_return_endpoint(request: Request) -> Response:
        return await execution_return_current(request, config=config)

    async def result_endpoint(request: Request) -> JSONResponse:
        return await result_current(request, config=config)

    async def mission_result_endpoint(request: Request) -> JSONResponse:
        return await mission_result_current(request, config=config)

    async def result_references_endpoint(request: Request) -> JSONResponse:
        return await result_references_current(request, config=config)

    async def plan_endpoint(request: Request) -> JSONResponse:
        return await plan_current(request, config=config)

    async def native_authorization_identity_endpoint(request: Request):
        from .native_authorization_identity import acquisition_identity_current
        return await acquisition_identity_current(request, config=config)

    async def native_draft_identity_endpoint(request: Request):
        from .native_draft_identity import native_draft_identity_current
        return await native_draft_identity_current(request, config=config)

    async def project_access_endpoint(request: Request):
        from http import HTTPStatus
        from integrations.mastermind_workspace_app.project_access import project_access_current
        loader=config.project_admission_load_bindings
        if loader is None:return _with_no_store(_refuse_json(HTTPStatus.SERVICE_UNAVAILABLE,"source_unavailable"))
        return await project_access_current(request,config=config,load_bindings=loader)

    async def project_instructions_endpoint(request: Request):
        return await project_instructions_current(request, config=config)

    async def project_plan_endpoint(request: Request) -> JSONResponse:
        return await project_plan_current(request, config=config)
    async def project_session_endpoint(request: Request) -> JSONResponse:
        return await project_session_current(request, config=config)
    async def project_archive_endpoint(request: Request) -> JSONResponse:
        return await project_archive_current(request, config=config)
    async def project_direction_endpoint(request: Request) -> JSONResponse:
        return await project_direction_current(request, config=config)
    async def project_knowledge_endpoint(request: Request) -> JSONResponse:
        return await project_knowledge_current(request, config=config)
    async def project_memory_endpoint(request: Request) -> JSONResponse:
        return await project_memory_current(request, config=config)
    async def project_source_endpoint(request: Request) -> JSONResponse:
        return await project_source_current(request, config=config)
    async def project_discovery_source_endpoint(request: Request) -> JSONResponse:
        return await project_discovery_source_current(request, config=config)
    async def project_journal_endpoint(request: Request) -> JSONResponse:
        return await project_journal_current(request, config=config)

    async def admission_endpoint(request: Request, mode: str):
        from integrations.mastermind_workspace_app.project_admission import project_admission_http
        loader = config.project_admission_load_bindings
        if loader is None:
            return _with_no_store(_refuse_json(503, "source_unavailable"))
        return await project_admission_http(request, config=config, load_bindings=loader, mode=mode)
    async def project_admission_current(request: Request):
        return await admission_endpoint(request, "current")
    async def project_admission_status(request: Request):
        return await admission_endpoint(request, "status")
    async def project_admission_pause(request: Request):
        return await admission_endpoint(request, "pause")
    async def project_admission_resume(request: Request):
        return await admission_endpoint(request, "resume")
    async def instruction_endpoint(request: Request, mode: str):
        from integrations.mastermind_workspace_app.instruction_admission import instruction_admission_http
        loader=config.project_admission_load_bindings
        if loader is None:return _with_no_store(_refuse_json(503,"source_unavailable"))
        return await instruction_admission_http(request,config=config,load_bindings=loader,mode=mode)
    async def instruction_current(request: Request):return await instruction_endpoint(request,"current")
    async def instruction_status(request: Request):return await instruction_endpoint(request,"status")
    async def instruction_pause(request: Request):return await instruction_endpoint(request,"pause")
    async def autonomy_endpoint(request: Request) -> JSONResponse:
        return await autonomy_current(request, config=config)

    async def host_observation_endpoint(request: Request) -> Response:
        from .host_observation import host_observation_current
        return await host_observation_current(request, config=config)

    async def resource_capacity_endpoint(request: Request) -> JSONResponse:
        return await resource_capacity_current(request, config=config)

    async def model_configuration_endpoint(request: Request) -> Response:
        from integrations.mastermind_workspace_app.model_configuration import model_configuration_current
        return await model_configuration_current(request, config=config)

    async def capacity_fabric_endpoint(request: Request) -> Response:
        from integrations.mastermind_workspace_app.capacity_fabric import capacity_fabric_current
        return await capacity_fabric_current(request, config=config)

    async def t3_attempt_fleet_endpoint(request: Request) -> Response:
        from integrations.mastermind_workspace_app.t3_attempt_fleet import t3_attempt_fleet_current
        return await t3_attempt_fleet_current(request, config=config)

    async def activity_endpoint(request: Request) -> JSONResponse:
        return await activity_current(request, config=config)

    async def fabric_catalog_endpoint(request: Request) -> Response:
        from common.executive_workspace_fabric_contract import CATALOG_OPERATION
        return await fabric_current(request, config=config, operation=CATALOG_OPERATION)

    async def fabric_status_endpoint(request: Request) -> Response:
        from common.executive_workspace_fabric_contract import STATUS_OPERATION
        return await fabric_current(request, config=config, operation=STATUS_OPERATION)

    async def byok_roles_endpoint(request: Request) -> Response:
        return await byok_roles_current(request, config=config)

    async def ccr_state_endpoint(request: Request) -> JSONResponse:
        return await control_room_current(request, config=config, operation="state")

    async def ccr_discover_endpoint(request: Request) -> JSONResponse:
        return await control_room_current(request, config=config, operation="discover")

    routes = [
        Route(_BYOK_ROLES_ROUTE, byok_roles_endpoint, methods=["GET"]),
        Route("/workspace/source-operation/context", source_operation_context_endpoint, methods=["GET"]),
        Route("/workspace/source-operation/options", source_operation_endpoint("options"), methods=["GET"]),
        Route("/workspace/source-operation/operation", source_operation_endpoint("read"), methods=["GET"]),
        Route("/workspace/source-operation/original", source_operation_endpoint("read_original"), methods=["GET"]),
        Route("/workspace/source-operation/prepare", source_operation_endpoint("prepare"), methods=["POST"]),
        Route("/workspace/source-operation/submit", source_operation_endpoint("submit"), methods=["POST"]),
        Route("/workspace/source-operation/reconcile", source_operation_endpoint("reconcile"), methods=["POST"]),
        Route("/workspace/source-operation/advance", source_operation_endpoint("advance"), methods=["POST"]),
        Route(_PROGRAMS_ROUTE, programs_endpoint, methods=["GET"]),
        Route(_WORK_ROUTE, work_endpoint, methods=["GET"]),
        Route(_MISSION_ROUTE, mission_endpoint, methods=["GET"]),
        Route(_MISSION_V3_ROUTE, mission_v3_endpoint, methods=["GET"]),
        Route(_MISSION_V4_ROUTE, mission_v4_endpoint, methods=["GET"]),
        Route(_RESULT_ROUTE, result_endpoint, methods=["GET"]),
        Route(_EXECUTION_RETURN_ROUTE, execution_return_endpoint, methods=["GET"]),
        Route(_MISSION_RESULT_ROUTE, mission_result_endpoint, methods=["GET"]),
        Route(_RESULT_REFERENCES_ROUTE, result_references_endpoint, methods=["GET"]),
        Route(_PLAN_ROUTE, plan_endpoint, methods=["GET"]),
        Route("/workspace/native-draft-identity/current", native_draft_identity_endpoint, methods=["GET"]),
        Route("/workspace/native-authorization-identity/acquisition/current", native_authorization_identity_endpoint, methods=["GET"]),
        Route("/workspace/project-access/current", project_access_endpoint, methods=["GET"]),
        Route("/workspace/project-instructions/current", project_instructions_endpoint, methods=["GET"]),
        Route(_PROJECT_PLAN_ROUTE, project_plan_endpoint, methods=["GET"]),
        Route(_PROJECT_JOURNAL_ROUTE, project_journal_endpoint, methods=["GET"]),
        Route(_PROJECT_KNOWLEDGE_CATALOGUE_ROUTE, project_knowledge_endpoint, methods=["GET"]),
        Route(_PROJECT_KNOWLEDGE_MEMORY_ROUTE, project_memory_endpoint, methods=["GET"]),
        Route(_PROJECT_KNOWLEDGE_SOURCE_ROUTE, project_source_endpoint, methods=["GET"]),
        Route(_PROJECT_DISCOVERY_SOURCE_ROUTE, project_discovery_source_endpoint, methods=["GET"]),
        Route(_PROJECT_SESSION_ROUTE, project_session_endpoint, methods=["GET"]),
        Route(_PROJECT_DIRECTION_ROUTE, project_direction_endpoint, methods=["GET"]),
        Route(_PROJECT_ARCHIVE_ROUTE, project_archive_endpoint, methods=["GET"]),
        Route(_AUTONOMY_ROUTE, autonomy_endpoint, methods=["GET"]),
        Route("/workspace/project-admission/current", project_admission_current, methods=["GET"]),
        Route("/workspace/project-admission/operation", project_admission_status, methods=["GET"]),
        Route("/workspace/project-admission/pause", project_admission_pause, methods=["POST"]),
        Route("/workspace/project-admission/resume", project_admission_resume, methods=["POST"]),
        Route("/workspace/instruction-admission/current",instruction_current,methods=["GET"]),
        Route("/workspace/instruction-admission/operation",instruction_status,methods=["GET"]),
        Route("/workspace/instruction-admission/pause",instruction_pause,methods=["POST"]),

        Route(_ACTIVITY_ROUTE, activity_endpoint, methods=["GET"]),
        Route(_RESOURCE_CAPACITY_ROUTE, resource_capacity_endpoint, methods=["GET"]),
        Route(_MODEL_CONFIGURATION_ROUTE, model_configuration_endpoint, methods=["GET"]),
        Route(_CAPACITY_FABRIC_ROUTE, capacity_fabric_endpoint, methods=["GET"]),
        Route(_T3_ATTEMPT_FLEET_ROUTE, t3_attempt_fleet_endpoint, methods=["GET"]),
        Route(_HOST_OBSERVATION_ROUTE, host_observation_endpoint, methods=["GET"]),
        Route(_FABRIC_CATALOG_ROUTE, fabric_catalog_endpoint, methods=["GET"]),
        Route(_FABRIC_STATUS_ROUTE, fabric_status_endpoint, methods=["GET"]),
        Route(_CCR_STATE_ROUTE, ccr_state_endpoint, methods=["GET"]),
        Route(_CCR_DISCOVER_ROUTE, ccr_discover_endpoint, methods=["GET"]),
    ]
    for operation, path in _CCR_ACTION_ROUTES.items():
        async def action_endpoint(request: Request, *, operation=operation) -> Response:
            return await control_room_action(request, config=config, operation=operation)
        routes.append(Route(path, action_endpoint, methods=["POST"]))
    from integrations.mastermind_workspace_app.paperclip_http import paperclip_http
    async def company_read_endpoint(request):
        return await paperclip_http(request, config=config)
    async def company_command_endpoint(request):
        return await paperclip_http(request, config=config, command=True)
    routes.extend([
        Route("/workspace/company/current", company_read_endpoint, methods=["GET"]),
        Route("/workspace/company/command", company_command_endpoint, methods=["POST"]),
    ])
    application = Starlette(routes=routes)
    # Never silently rewrite a trailing-slash alias onto a different route:
    # an encoded/trailing-slash/raw-path ambiguity must refuse as a plain
    # 404 (trailing slash) or 400 (encoded separator), never be silently
    # redirected before auth has even run.
    application.router.redirect_slashes = False
    return _RawPathFence(application)
