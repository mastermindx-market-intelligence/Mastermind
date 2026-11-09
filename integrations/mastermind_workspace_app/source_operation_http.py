"""Fixed authenticated source commands over the existing App-peer client.

No public identity/grant/actor/expiry or publisher is accepted. Automatic GET
reads only retained Events; explicit reconcile POST may observe the original
publication and retain that observation, never publish or advance it.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import re

from starlette.responses import JSONResponse, Response
from common.executive_workspace_contract import canonical
from common.workspace_source_operation_contract import validate_status, validate_lookup
from common.workspace_source_operation_wire import (
    FRAME_SCHEMA, MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, validate_frame, operation_request_limit, operation_response_limit)
from control_plane.workspace_owned_task import await_owned
from integrations.mastermind_workspace_app.contract import principal_frame
from common import workspace_discovery_correction_contract as correction


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value: raise ValueError()
        value[key] = item
    return value


def _preview(body, request, scope):
    if request.get("action") == correction.ACTION:
        return correction.validate_preview(body, request=request["request"], principal_scope=scope)
    keys = {"schema", "selection", "owner_context", "request_sha256", "recipe_fingerprint_sha256", "preview_witness", "preview"}
    if (type(body) is not dict or set(body) != keys
            or body["schema"] != "mastermind.workspace_source_operation_preview.v1"
            or body["owner_context"] != {"principal_scope": scope}
            or body["request_sha256"] != hashlib.sha256(canonical(request["request"])).hexdigest()
            or type(body["recipe_fingerprint_sha256"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", body["recipe_fingerprint_sha256"]) is None
            or body["recipe_fingerprint_sha256"] == body["request_sha256"]):
        raise ValueError()
    selected = validate_lookup({"schema": "mastermind.workspace_source_operation_lookup.v1", **body["selection"]})
    if selected["action"] != request["action"] or selected["request_id"] != request["request"]["request_id"]:
        raise ValueError()
    from common.workspace_source_operation_wire import validate_witness
    validate_witness(body["preview_witness"])
    if body["preview_witness"]["recipe_fingerprint_sha256"] != body["recipe_fingerprint_sha256"]:
        raise ValueError()
    if selected["action"] in {"add_project_file", "set_project_communication_preference", correction.ACTION}:
        _knowledge_preview(body["preview"], request["request"], selected, scope)
        return body
    if selected["action"] == "ADOPT_PLAN":
        from integrations.mastermind_workspace_app.project_plan_adoption_preview import validate_plan_adoption_preview
        validate_plan_adoption_preview(body["preview"], request["request"], selected)
        return body
    preview = body["preview"]
    if (selected["action"] != "publish_project_proposal" or type(preview) is not dict
            or set(preview) != {"schema", "state", "work_ref", "source_commit", "canonical_path", "content_sha256", "goal", "profile"}
            or preview["schema"] != "mastermind.project_creation_preview.v1" or preview["state"] != "DRAFT_ONLY"
            or preview["work_ref"] != selected["work_ref"]
            or preview["source_commit"] != request["request"]["expected_macro_sha"]
            or preview["goal"] != request["request"]["goal"]
            or preview["canonical_path"] != "agentos/workstreams/WS-" + selected["work_ref"][3:] + ".md"
            or type(preview["content_sha256"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", preview["content_sha256"]) is None):
        raise ValueError()
    profile = preview["profile"]
    if (type(profile) is not dict or set(profile) != {"id", "revision", "title", "owner", "program", "repos", "classification", "blast_radius", "ambiguity", "waves", "next_action"}
            or profile["id"] != request["request"]["profile_id"]
            or profile["revision"] != request["request"]["profile_sha256"]
            or any(type(profile[k]) is not str for k in {"title", "owner", "program", "classification", "blast_radius", "ambiguity", "next_action"})
            or type(profile["repos"]) is not list or any(type(x) is not str for x in profile["repos"])
            or type(profile["waves"]) is not list or len(profile["waves"]) > 16
            or any(type(w) is not dict or set(w) != {"id", "title", "status"}
                   or any(type(v) is not str for v in w.values()) for w in profile["waves"])):
        raise ValueError()
    return body


def _knowledge_preview(preview, request, selected, scope):
    """Closed safe summary paired to the exact reviewed public request."""
    if (type(preview) is not dict or set(preview) != {"schema", "state", "action", "work_ref", "source_commit", "change", "postimages"}
            or preview["schema"] != "mastermind.project_knowledge_preview.v1" or preview["state"] != "DRAFT_ONLY"
            or preview["action"] != selected["action"] or preview["work_ref"] != selected["work_ref"]
            or preview["work_ref"] != request.get("work_ref") or preview["source_commit"] != request.get("source_commit")):
        raise ValueError()
    ws_path = "agentos/workstreams/WS-" + selected["work_ref"][3:] + ".md"
    if selected["action"] == "add_project_file":
        file = request["file"]
        change = {"kind": "FILE_ADD", "display_name": file["display_name"],
                  "size_bytes": len(file["content_utf8"].encode("utf-8"))}
        identity = {"principal_scope": scope, "request_id": selected["request_id"], "work_ref": selected["work_ref"]}
        path = ("agentos/project-files/WS-" + selected["work_ref"][3:] + "/"
                + hashlib.sha256(canonical(identity)).hexdigest() + "." + file["display_name"].rsplit(".", 1)[-1].lower())
        preimage = None
        content_sha = hashlib.sha256(file["content_utf8"].encode("utf-8")).hexdigest()
    else:
        change = {"kind": "COMMUNICATION_PREFERENCE", "value": request["value"]}
        path = "agentos/decisions/DEC-PROJECT-COMMUNICATION-PREFERENCE-" + selected["work_ref"][3:] + ".md"
        preimage, content_sha = request["expected_preference_revision"], None
    if preview["change"] != change or type(preview["postimages"]) is not list or len(preview["postimages"]) != 2:
        raise ValueError()
    seen = set()
    for image in preview["postimages"]:
        if (type(image) is not dict or set(image) != {"path", "content_sha256", "expected_preimage_sha256"}
                or type(image["path"]) is not str or image["path"] not in {ws_path, path} or image["path"] in seen
                or type(image["content_sha256"]) is not str or re.fullmatch(r"[0-9a-f]{64}", image["content_sha256"]) is None
                or image["expected_preimage_sha256"] != (request["base_revision"] if image["path"] == ws_path else preimage)
                or (image["path"] == path and content_sha is not None and image["content_sha256"] != content_sha)):
            raise ValueError()
        seen.add(image["path"])


async def source_operation_http(request, *, config, operation):
    from integrations.mastermind_workspace_app.app import (
        _authenticate, _with_no_store, _refuse_json, _reject_any_body, _decode_v2_query, _envelope_response)
    principal = await _authenticate(request, config.authenticator, clock=config.now)
    if isinstance(principal, JSONResponse): return _with_no_store(principal)
    client, factory = config.client, config.source_operation_context
    if factory is None or factory.policy != config.authenticator.policy:
        return _refuse_json(503, "source_unavailable")
    try:
        if operation in {"read", "read_original", "options"}:
            refused = await _reject_any_body(request)
            if refused is not None: return refused
            raw_query = request.scope.get("query_string", b"")
            # Read only exact selectors. Knowledge's full original tuple stays
            # separate from basic CREATE/ADOPT/Direction lookup.
            from urllib.parse import parse_qsl
            pairs = parse_qsl(raw_query.decode("ascii"), keep_blank_values=True, strict_parsing=True)
            if len({k for k, _ in pairs}) != len(pairs): raise ValueError()
            value = dict(pairs)
            if "schema" in value: raise ValueError()
            if value.get("action") in {"add_project_file", "set_project_communication_preference", correction.ACTION}:
                if value.get("action") != correction.ACTION and value.get("expected_preference_revision") == "null": value["expected_preference_revision"] = None
            elif operation != "options": value["schema"] = "mastermind.workspace_source_operation_lookup.v1"
        else:
            if request.scope.get("query_string"): raise ValueError()
            content_types = [v for k, v in request.scope.get("headers", ()) if k.lower() == b"content-type"]
            if len(content_types) != 1 or content_types[0].split(b";", 1)[0].strip().lower() != b"application/json": raise ValueError()
            raw = bytearray()
            async for chunk in request.stream():
                if len(raw) + len(chunk) > MAX_REQUEST_BYTES: raise ValueError()
                raw.extend(chunk)
            def nonfinite(_): raise ValueError()
            value = json.loads(bytes(raw).decode("utf-8"), object_pairs_hook=_unique, parse_constant=nonfinite)
            if len(raw)>operation_request_limit(operation,value):raise ValueError()
        if operation == "read" and value.get("action") == "publish_project_proposal" and value.get("work_ref") == "null":
            from integrations.mastermind_workspace_app.project_proposal_request import creation_work_ref
            value["work_ref"] = creation_work_ref(value["request_id"],principal=principal)
        frame = validate_frame({"schema": FRAME_SCHEMA, "operation": operation,
            "principal": principal_frame(principal), "verified_expires_at": principal.expires_at, "request": value})
        action = value["action"]
        work_ref = None if operation == "options" else value["request"].get("work_ref") if operation == "prepare" else value["work_ref"]
        permission = factory.bind(principal, action=action, work_ref=work_ref)
        scope = permission.principal_scope
        latest_gate = None
        latest_stamp = None
        if action in {"add_project_file", "set_project_communication_preference", correction.ACTION} and operation in {"prepare", "submit"}:
            from integrations.mastermind_workspace_app.project_authoring_grant import workspace_project_authorizers
            latest_gate, _ = workspace_project_authorizers(policy=factory.policy,
                load_bindings=factory._load_bindings,action="read_latest_project_data")
            if latest_gate(principal) is True:
                latest_stamp = latest_gate.binding_digest(principal)
        request_owner = client.request
    except PermissionError: return _refuse_json(403, "access_denied")
    except Exception: return _refuse_json(400, "invalid_input")
    def current():
        instant = config.now()
        return (config.client is client and client.request == request_owner
                and config.source_operation_context is factory and permission.check()
                and (latest_stamp is None or (latest_gate(principal) is True
                     and latest_gate.binding_digest(principal) == latest_stamp))
                and type(instant) is int and 0 <= instant < principal.expires_at)
    if not current(): return _refuse_json(403, "access_denied")
    try:
        # One original invocation remains owned through parent cancellation.
        owned = asyncio.create_task(request_owner(frame))
        try: envelope = await await_owned(owned)
        except asyncio.CancelledError:
            if not owned.done() or owned.cancelled(): raise
            envelope = owned.result()
        if not current(): return _refuse_json(403, "access_denied")
        if type(envelope) is dict and envelope.get("ok") is False:
            return _envelope_response(envelope)
        if type(envelope) is not dict or set(envelope) != {"ok", "result"} or envelope["ok"] is not True: raise ValueError()
        result = envelope["result"]
        if operation == "options":
            if (type(result) is not dict or set(result)!={'schema','expected_macro_sha','profiles','owner_context','grounding'}
                    or result['schema']!='mastermind.project_creation_options.v1'
                    or result['owner_context']!={'principal_scope':scope}
                    or type(result['expected_macro_sha']) is not str
                    or re.fullmatch(r'[a-f0-9]{40}',result['expected_macro_sha']) is None
                    or type(result['profiles']) is not list or not 1<=len(result['profiles'])<=8):raise ValueError()
        elif operation == "prepare": result = _preview(result, value, scope)
        elif operation == "read_original":
            from common.workspace_discovery_original_contract import validate as validate_original
            result = validate_original(result, lookup=value, principal_scope=scope)
        else:
            result = validate_status(result)
            if (result["selection"] != {k: value[k] for k in ("action", "request_id", "work_ref")}
                    or result["owner_context"] != {"principal_scope": scope}): raise ValueError()
        raw = canonical(result)
        if len(raw) + 1 > operation_response_limit(operation): raise ValueError()
        return Response(raw, status_code=200, media_type="application/json", headers={"Cache-Control": "no-store"})
    except (Exception, asyncio.CancelledError):
        # No transport exception proves no effect. The durable original hint
        # stays with the existing controller for an explicit same-ID check.
        return _refuse_json(503, "source_unavailable")
