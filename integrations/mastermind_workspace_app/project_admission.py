"""Fixed project control HTTP functions over the existing authenticated App.

Registration and installed v4 membership remain the incumbent bootstrap's
responsibility. No route, config, grant, service or dispatcher is installed here.
"""
from __future__ import annotations

import asyncio
import json
import re

from starlette.responses import JSONResponse
from common import executive_workspace_contract as workspace
from common import workspace_project_admission_contract as pause
from common import workspace_project_resumption_contract as resume
from common import workspace_project_admission_control_contract as control
from common.workspace_project_admission_selection import selection as project_selection
from integrations.mastermind_workspace_app.owner_context import workspace_owner_context
from control_plane.workspace_owned_task import await_owned
from integrations.mastermind_workspace_app.contract import principal_frame, permission_stamp
from integrations.mastermind_workspace_app.project_authoring_grant import (
    PROJECT_SUSPEND_ACTION, PROJECT_RESUME_ACTION, workspace_project_authorizers,
)

_ROUTE_KIND = {"pause": "project_pause", "resume": "project_resume"}


def _response(body, status=200):
    workspace.bounded_canonical(body, limit=32767)
    return JSONResponse(body, status_code=status, headers={"Cache-Control": "no-store"})


def _closed_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("invalid_input")
            result[key] = value
        return result
    def invalid(_):
        raise ValueError("invalid_input")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid)


async def project_admission_http(request, *, config, load_bindings, mode):
    """Current/read-original or one explicit Pause/Resume invocation.

    ``config`` is the existing WorkspaceAppConfig; ``load_bindings`` is its
    actual sealed membership loader. Public payloads never supply identity,
    authority, expiry, path, Runtime actor, route or arbitrary action names.
    """
    from integrations.mastermind_workspace_app.app import (
        WorkspaceAppConfig, _authenticate, _decode_v2_query, _reject_any_body, _refuse_json, _with_no_store,
    )
    if type(config) is not WorkspaceAppConfig or mode not in {"current", "status", "pause", "resume"} or not callable(load_bindings):
        raise ValueError("fixed Workspace project owner required")
    principal = await _authenticate(request, config.authenticator, clock=config.now)
    if isinstance(principal, JSONResponse):
        return _with_no_store(principal)
    try:
        public = None
        raw_query = request.scope.get("query_string") or b""
        if mode in {"current", "status"}:
            if request.method != "GET":
                raise ValueError("invalid_input")
            body_refusal = await _reject_any_body(request)
            if body_refusal is not None:
                return _with_no_store(body_refusal)
            keys = {"work_ref"} | ({"kind", "command_id"} if mode == "status" else set())
            if any(part.startswith(b"root_job_id=") for part in raw_query.split(b"&")):
                keys.add("root_job_id")
            public = _decode_v2_query(raw_query, required_keys=frozenset(keys))
            selected = project_selection({key: public[key] for key in ("work_ref", "root_job_id") if key in public})
            kind = public.get("kind")
            if mode == "status" and kind not in _ROUTE_KIND.values():
                raise ValueError("invalid_input")
        else:
            if request.method != "POST" or raw_query:
                raise ValueError("invalid_input")
            headers = [value for name, value in request.scope.get("headers", ()) if name.lower() == b"content-type"]
            if len(headers) != 1 or headers[0].split(b";", 1)[0].strip().lower() != b"application/json":
                raise ValueError("invalid_input")
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > 16384:
                    raise ValueError("invalid_input")
                body.extend(chunk)
            public = _closed_json(bytes(body))
            expected = {"selection", "command_id"} | ({"pause_token"} if mode == "resume" else set())
            if type(public) is not dict or set(public) != expected:
                raise ValueError("invalid_input")
            selected = project_selection(public["selection"])
            kind = _ROUTE_KIND[mode]
        wire = control if mode == "current" else resume if kind == "project_resume" else pause
        if mode != "current":
            command = public["command_id"]
            prefix = "mmos-project-resume-" if kind == "project_resume" else "mmos-project-pause-"
            if type(command) is not str or re.fullmatch(re.escape(prefix) + r"[0-9a-f]{40}", command) is None:
                raise ValueError("invalid_input")
            selected = {**selected, "command_id": command}
        private = {"schema": wire.FRAME_SCHEMA, "operation": wire.OPERATION, "selection": selected,
                   "principal": principal_frame(principal), "admission_expires_at": principal.expires_at}
        if mode == "status":
            private.update(schema=wire.STATUS_FRAME_SCHEMA, operation=wire.STATUS_OPERATION)
        elif mode == "resume":
            private["pause_token"] = public["pause_token"]
        checked = wire.validate_frame(private) if mode == "current" else wire.validate_frame(private, status=mode == "status")
    except (Exception, asyncio.CancelledError):
        return _with_no_store(_refuse_json(400, "invalid_input"))

    read_authorize, client, request_owner = config.authorize_principal, config.client, config.client.request
    policy = config.authenticator.policy
    action = PROJECT_RESUME_ACTION if kind == "project_resume" else PROJECT_SUSPEND_ACTION
    authorizers = []
    for which in ((PROJECT_SUSPEND_ACTION, PROJECT_RESUME_ACTION) if mode == "current" else (action,)):
        try:
            authorize, _ = workspace_project_authorizers(policy=policy, load_bindings=load_bindings, action=which, work_ref=selected["work_ref"])
            if authorize(principal) is True:
                authorizers.append(authorize)
        except Exception:
            pass
    def permissions():
        if (not authorizers or config.authorize_principal is not read_authorize or read_authorize(principal) is not True
                or config.client is not client or config.client.request != request_owner or config.authenticator.policy is not policy
                or type(config.now()) is not int or not 0 <= config.now() < principal.expires_at):
            raise ValueError("access_denied")
        stamps = tuple(permission_stamp(authorize, principal) for authorize in (read_authorize, *authorizers))
        if any(stamp is None for stamp in stamps) or any(authorize(principal) is not True for authorize in authorizers):
            raise ValueError("access_denied")
        return stamps
    try:
        initial = permissions()
    except Exception:
        return _with_no_store(_refuse_json(403, "access_denied"))

    def withheld():
        if mode == "current":
            return {"schema": control.BODY_SCHEMA, "selection": dict(selected), "availability": "UNAVAILABLE", "state": None,
                "permissions": None, "owner_context": None, "current_receipt": None, "pause_token": None, "reason_codes": ["SOURCE_UNAVAILABLE"]}
        if mode == "status":
            return {"schema": wire.STATUS_RESULT_SCHEMA, "selection": dict(selected), "state": "UNAVAILABLE", "receipt": None, "reason_codes": ["SOURCE_UNAVAILABLE"]}
        return {"schema": wire.ACTION_RESULT_SCHEMA, "selection": dict(selected), "disposition": "EFFECT_UNKNOWN", "receipt": None,
            "reason_codes": ["OWNER_OUTCOME_UNCONFIRMED"]}
    # Invocation boundary: any failure from here is original-effect UNKNOWN,
    # or withheld read data. No automatic replay and no no-effect inference.
    try:
        owned = asyncio.create_task(request_owner(checked))
        envelope = await await_owned(owned)
        if type(envelope) is not dict or set(envelope) != {"ok", "result"} or envelope["ok"] is not True:
            raise ValueError("source_unavailable")
        if permissions() != initial:
            raise ValueError("access_denied")
        if mode == "current":
            result = control.validate_body(envelope["result"], selected)
            if result["availability"] == "AVAILABLE" and result["owner_context"] != workspace_owner_context(principal):
                raise ValueError("source_unavailable")
            # Every advertised permission must be qualified at this HTTP owner,
            # independently from its sibling. Never promote a socket-only flag.
            if result["availability"] == "AVAILABLE":
                for flag, which in (("pause", PROJECT_SUSPEND_ACTION), ("resume", PROJECT_RESUME_ACTION)):
                    authorize, _ = workspace_project_authorizers(policy=policy, load_bindings=load_bindings, action=which, work_ref=selected["work_ref"])
                    if result["permissions"][flag] and authorize(principal) is not True:
                        raise ValueError("access_denied")
        else:
            result = wire.validate_status_result(envelope["result"], selected) if mode == "status" else wire.validate_action_result(envelope["result"], selected)
        if permissions() != initial:
            raise ValueError("access_denied")
    except (Exception, asyncio.CancelledError):
        result = withheld()
    return _response(result)
