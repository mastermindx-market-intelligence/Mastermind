"""Finite v5 project knowledge values on the incumbent COO/Workspace owners.

No I/O, compiler, authentication, source selection or durable state lives here.
Public checks qualify the original owner result; they never establish publication
or reconstruct a retained private body from its request hash.
"""
from __future__ import annotations

import hashlib
import json
import re

from common import coo_agentos_context_contract as context
from common import coo_discovery_contract as discovery
from common import workspace_discovery_correction_contract as correction
from common import workspace_project_knowledge_read_contract as reads
from common import workspace_project_knowledge_contract as bodies
from common.workspace_source_operation_contract import validate_status
from common.workspace_source_operation_wire import validate_knowledge_lookup, validate_witness

CATALOGUE = context.KNOWLEDGE_CATALOGUE
RESULT_SCHEMA = "mastermind.coo_project_knowledge_result.v1"
READ_TOOL = "executive_project_knowledge"
AUTHOR_TOOL = "executive_project_knowledge_authoring"
TOOLS = (*discovery.TOOLS, READ_TOOL, AUTHOR_TOOL)
SOURCE_TOOL = discovery.SOURCE_TOOL
CORRECTION_TOOL = discovery.CORRECTION_TOOL
READ_ACTION = "read_project_knowledge"
ADD_ACTION = "add_project_file"
PREFERENCE_ACTION = "set_project_communication_preference"
REQUIRED_ACTIONS = (context.CURRENT_ACTION, discovery.READ_ACTION, discovery.CORRECTION_ACTION,
                    READ_ACTION, ADD_ACTION, PREFERENCE_ACTION)
FILE_REQUEST_SCHEMA = "mastermind.project_file_add_request.v1"
PREFERENCE_REQUEST_SCHEMA = "mastermind.project_preference_set_request.v1"
MAX_RESULT_BYTES = discovery.MAX_RESULT_BYTES
# Same 64 KiB complete HTTP body ceiling. Tool parameters additionally
# reserve 1 KiB for original SDK framing; escaped notes are never truncated.
MAX_REQUEST_BYTES = 64 * 1024
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_READS = {"catalogue": "project_knowledge_catalogue",
          "memory": "project_knowledge_memory", "source": "project_knowledge_source"}
READ_ROUTES = {"catalogue": "/workspace/project-knowledge/current",
               "memory": "/workspace/project-memory/current",
               "source": "/workspace/project-source/current"}
ACTION_PREFIXES = {ADD_ACTION: "mmos-project-file-add-",
             PREFERENCE_ACTION: "mmos-project-preference-set-"}


def _fail():
    raise ValueError("invalid_project_knowledge_tool")


def _keys(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        _fail()


def _hex(value, size):
    if type(value) is not str or re.fullmatch("[0-9a-f]{" + str(size) + "}", value) is None:
        _fail()
    return value


def _text(value, limit, *, nonempty=True):
    if (type(value) is not str or (nonempty and not value.strip())
            or _CONTROL.search(value) or len(value.encode("utf-8", "strict")) > limit):
        _fail()
    return value


def validate_request(value):
    """Bound public values only; deeper recipe law stays with the compiler."""
    if type(value) is not dict:
        _fail()
    schema = value.get("schema")
    if schema == FILE_REQUEST_SCHEMA:
        action = ADD_ACTION
        _keys(value, {"schema", "request_id", "work_ref", "source_commit", "base_revision", "file"})
        item = value["file"]
        _keys(item, {"display_name", "media_type", "content_utf8"})
        name = _text(item["display_name"], 128)
        if any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in name) or "/" in name or "\\" in name:
            _fail()
        stem, dot, suffix = name.rpartition(".")
        if not stem or not dot or suffix.lower() not in {"md", "txt"}:
            _fail()
        if item["media_type"] != {"md": "text/markdown", "txt": "text/plain"}[suffix.lower()]:
            _fail()
        _text(item["content_utf8"], bodies.MAX_SOURCE_BODY)
    elif schema == PREFERENCE_REQUEST_SCHEMA:
        action = PREFERENCE_ACTION
        _keys(value, {"schema", "request_id", "work_ref", "source_commit", "base_revision",
                      "expected_preference_revision", "value"})
        _text(value["value"], bodies.MAX_MEMORY_VALUE)
        if value["expected_preference_revision"] is not None:
            _hex(value["expected_preference_revision"], 64)
    else:
        _fail()
    # The exact seven-field public lookup owner checks action/work/request
    # identity. It adds no source, actor or permission facts.
    validate_knowledge_lookup({
        "action": action, "request_id": value["request_id"], "work_ref": value["work_ref"],
        "source_commit": value["source_commit"], "base_revision": value["base_revision"],
        "request_sha256": hashlib.sha256(correction.canonical(value)).hexdigest(),
        "expected_preference_revision": value.get("expected_preference_revision")})
    return json.loads(correction.canonical(value))


def request_lookup(value):
    value = validate_request(value)
    return validate_knowledge_lookup({
        "action": ADD_ACTION if value["schema"] == FILE_REQUEST_SCHEMA else PREFERENCE_ACTION,
        **{key: value[key] for key in ("request_id", "work_ref", "source_commit", "base_revision")},
        "request_sha256": hashlib.sha256(correction.canonical(value)).hexdigest(),
        "expected_preference_revision": value.get("expected_preference_revision")})


def arguments(tool, value):
    if tool in discovery.TOOLS:
        return discovery.arguments(tool, value)
    if tool == READ_TOOL:
        if type(value) is not dict or type(value.get("mode")) is not str or value["mode"] not in _READS:
            _fail()
        reads.selection({k: v for k, v in value.items() if k != "mode"}, operation=_READS[value["mode"]])
    elif tool == AUTHOR_TOOL:
        if type(value) is not dict or type(value.get("operation")) is not str:
            _fail()
        mode = value["operation"]
        if mode == "prepare":
            _keys(value, {"operation", "request"})
            validate_request(value["request"])
        elif mode in {"read", "reconcile", "submit"}:
            _keys(value, {"operation", "lookup", "preview_witness"} if mode == "submit" else {"operation", "lookup"})
            selected = validate_knowledge_lookup(value["lookup"])
            if selected["action"] not in ACTION_PREFIXES:
                _fail()
            if mode == "submit":
                validate_witness(value["preview_witness"])
        else:
            _fail()
    else:
        _fail()
    # Charge the complete bodies used by the original adapters, including JSON
    # escaping and framing, rather than just the visible note character count.
    context.encode({"arguments": value}, limit=MAX_REQUEST_BYTES)
    context.encode({"name": tool, "arguments": value}, limit=MAX_REQUEST_BYTES - 1024)
    return json.loads(correction.canonical(value))


def operation(tool, value):
    if tool in discovery.TOOLS:
        return discovery.operation(tool, value)
    return value["mode"] if tool == READ_TOOL else value["operation"]


def lookup(tool, value):
    value = arguments(tool, value)
    if tool in discovery.TOOLS:
        return discovery.lookup(tool, value)
    if tool == READ_TOOL:
        return {k: v for k, v in value.items() if k != "mode"}
    return request_lookup(value["request"]) if value["operation"] == "prepare" else value["lookup"]


def action(tool, value):
    if tool in discovery.TOOLS:
        return discovery.action(tool, value)
    return READ_ACTION if tool == READ_TOOL else lookup(tool, value)["action"]


def mutating(tool, value):
    if tool in discovery.TOOLS:
        return discovery.mutating(tool, value)
    return tool == AUTHOR_TOOL and value["operation"] in {"prepare", "submit", "reconcile"}


def _ws_path(selected):
    return "agentos/workstreams/WS-" + selected["work_ref"][3:] + ".md"


def _preference_path(selected):
    return "agentos/decisions/DEC-PROJECT-COMMUNICATION-PREFERENCE-" + selected["work_ref"][3:] + ".md"


def _file_stem(selected, principal_scope):
    identity = {"principal_scope": principal_scope, "request_id": selected["request_id"],
                "work_ref": selected["work_ref"]}
    return ("agentos/project-files/WS-" + selected["work_ref"][3:] + "/"
            + hashlib.sha256(correction.canonical(identity)).hexdigest())


def validate_sources(selected, principal_scope, sources):
    """Exactly the selected WS and one scoped note/preference, at one commit.

    A body-free file lookup intentionally cannot recover the original suffix or
    body. Its request hash/owner joins remain required, and only one permitted
    suffix for the deterministic stem is admitted.
    """
    if type(sources) is not list or len(sources) != 2:
        _fail()
    paths = {item["path"] for item in sources}
    expected = ({_preference_path(selected)} if selected["action"] == PREFERENCE_ACTION
                else {_file_stem(selected, principal_scope) + suffix for suffix in (".md", ".txt")})
    if (len(paths) != 2 or _ws_path(selected) not in paths
            or len(paths & expected) != 1
            or len({item["commit"] for item in sources}) != 1):
        _fail()


def validate_preview(body, *, request, principal_scope):
    request = validate_request(request)
    selected = request_lookup(request)
    _hex(principal_scope, 64)
    _keys(body, {"schema", "selection", "owner_context", "request_sha256",
                 "recipe_fingerprint_sha256", "preview_witness", "preview"})
    if (body["schema"] != "mastermind.workspace_source_operation_preview.v1"
            or body["selection"] != {k: selected[k] for k in ("action", "request_id", "work_ref")}
            or body["owner_context"] != {"principal_scope": principal_scope}
            or body["request_sha256"] != selected["request_sha256"]):
        _fail()
    _hex(body["recipe_fingerprint_sha256"], 64)
    validate_witness(body["preview_witness"])
    if (body["recipe_fingerprint_sha256"] == body["request_sha256"]
            or body["preview_witness"]["recipe_fingerprint_sha256"] != body["recipe_fingerprint_sha256"]):
        _fail()
    if selected["action"] == ADD_ACTION:
        file = request["file"]
        target = _file_stem(selected, principal_scope) + "." + file["display_name"].rsplit(".", 1)[1].lower()
        change = {"kind": "FILE_ADD", "display_name": file["display_name"],
                  "size_bytes": len(file["content_utf8"].encode("utf-8"))}
        other_preimage = None
    else:
        target, other_preimage = _preference_path(selected), request["expected_preference_revision"]
        change = {"kind": "COMMUNICATION_PREFERENCE", "value": request["value"]}
    preview = body["preview"]
    _keys(preview, {"schema", "state", "action", "work_ref", "source_commit", "change", "postimages"})
    if (preview["schema"] != "mastermind.project_knowledge_preview.v1" or preview["state"] != "DRAFT_ONLY"
            or preview["action"] != selected["action"] or preview["work_ref"] != selected["work_ref"]
            or preview["source_commit"] != selected["source_commit"] or preview["change"] != change):
        _fail()
    images = preview["postimages"]
    preimages = {_ws_path(selected): selected["base_revision"], target: other_preimage}
    if (type(images) is not list or len(images) != 2
            or any(type(image) is not dict or type(image.get("path")) is not str for image in images)
            or {image["path"] for image in images} != set(preimages)):
        _fail()
    for image in images:
        _keys(image, {"path", "content_sha256", "expected_preimage_sha256"})
        _hex(image["content_sha256"], 64)
        if image["expected_preimage_sha256"] != preimages[image["path"]]:
            _fail()
        if (selected["action"] == ADD_ACTION and image["path"] == target
                and image["content_sha256"] != hashlib.sha256(request["file"]["content_utf8"].encode("utf-8")).hexdigest()):
            _fail()
    return context.decode(context.encode(body, limit=32 * 1024), limit=32 * 1024)


def _current_read(tool_value, body):
    mode = tool_value["mode"]
    body = reads.validate_body(body, operation=_READS[mode])
    selected = {k: v for k, v in tool_value.items() if k != "mode"}
    if body["selection"] != reads.result_selection(selected):
        _fail()
    if body["availability"] != "UNAVAILABLE":
        if body.get("code_context") is None or body.get("data_observation") is None:
            _fail()
        if mode == "source":
            raw = body["document"]["content_utf8"].encode("utf-8", "strict")
            blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\x00" + raw).hexdigest()
            if body["source"]["revision"] != selected["expected_revision"] or blob != selected["expected_revision"]:
                _fail()
    return body


def validate_prepare_current(request, catalogue, memory=None):
    """Join original explicit preimages to fresh authenticated DATA reads."""
    request = validate_request(request)
    selected = request_lookup(request)
    catalogue = _current_read({"mode": "catalogue", "work_ref": request["work_ref"]}, catalogue)
    if (catalogue["availability"] != "AVAILABLE"
            or catalogue["source"]["commit"] != request["source_commit"]
            or catalogue["source"]["workstream_sha256"] != request["base_revision"]):
        _fail()
    if selected["action"] == PREFERENCE_ACTION:
        memory = _current_read({"mode": "memory", "work_ref": request["work_ref"]}, memory)
        if memory["availability"] == "UNAVAILABLE":
            _fail()
        snapshot = ("repository", "default_ref", "executable_macro_commit", "canonical_data_commit",
                    "reader_closure_sha256")
        if (catalogue["code_context"] != memory["code_context"]
                or any(catalogue["data_observation"][key] != memory["data_observation"][key] for key in snapshot)):
            _fail()
        summary = catalogue["project"]["memory"]
        if summary["state"] != memory["availability"]:
            _fail()
        if memory["availability"] == "EMPTY":
            if request["expected_preference_revision"] is not None:
                _fail()
        elif (memory["source"]["commit"] != request["source_commit"]
                or memory["source"]["path"] != _preference_path(selected)
                or memory["source"]["content_sha256"] != request["expected_preference_revision"]
                or summary["revision"] != memory["source"]["revision"]):
            _fail()
    return request


def validate_data(tool, value, body, *, workspace_principal):
    if tool in discovery.TOOLS:
        return discovery.validate_data(tool, value, body, workspace_principal=workspace_principal)
    if tool == READ_TOOL:
        return _current_read(value, body)
    selected, mode = lookup(tool, value), operation(tool, value)
    scope = discovery.workspace_scope(workspace_principal)
    if mode == "prepare":
        return validate_preview(body, request=value["request"], principal_scope=scope)
    body = validate_status(body)
    if (body["selection"] != {k: selected[k] for k in ("action", "request_id", "work_ref")}
            or body["owner_context"] != {"principal_scope": scope}
            or body["request_sha256"] not in (None, selected["request_sha256"])
            or (mode == "submit" and body["recipe_fingerprint_sha256"] not in
                (None, value["preview_witness"]["recipe_fingerprint_sha256"]))):
        _fail()
    receipt = body["receipt"]
    if receipt is not None:
        if body["request_sha256"] != selected["request_sha256"]:
            _fail()
        if receipt["sources"] or receipt["kind"] == "SOURCE_OBSERVED":
            validate_sources(selected, scope, receipt["sources"])
    return body


def result(tool, value, *, state, reason, principal_context=None, capability_profile_digest=None,
           workspace_principal=None, data=None):
    value = arguments(tool, value)
    selected = lookup(tool, value)
    pairs = {"OBSERVED": {"OWNER_RESULT"},
             "NOT_DISPATCHED": {"AUTHORITY_UNAVAILABLE", "INVALID_INPUT", "SOURCE_UNAVAILABLE", "ORIGINAL_OPERATION_UNRESOLVED"},
             "EFFECT_UNKNOWN": {"ORIGINAL_OUTCOME_UNKNOWN"},
             "UNAVAILABLE": {"SOURCE_UNAVAILABLE", "AUTHORITY_UNAVAILABLE"}}
    if type(state) is not str or type(reason) is not str or reason not in pairs.get(state, set()):
        _fail()
    if state == "EFFECT_UNKNOWN" and not mutating(tool, value) or state == "UNAVAILABLE" and mutating(tool, value):
        _fail()
    identities = (principal_context, capability_profile_digest, workspace_principal)
    if any(item is not None for item in identities):
        if any(item is None for item in identities):
            _fail()
        checked = context.context(principal_context)
        context._digest(capability_profile_digest)
        context.workspace_principal(workspace_principal)
        if checked.work_ref != selected["work_ref"]:
            _fail()
    if state == "OBSERVED":
        if any(item is None for item in identities):
            _fail()
        data = validate_data(tool, value, data, workspace_principal=workspace_principal)
    elif data is not None:
        _fail()
    body = {"schema": RESULT_SCHEMA, "catalogue": CATALOGUE, "tool": tool,
            "operation": operation(tool, value), "selection": selected, "state": state, "reason": reason,
            "principal_context": principal_context, "capability_profile_digest": capability_profile_digest,
            "workspace_principal": workspace_principal, "data": data}
    return context.decode(context.encode(body, limit=MAX_RESULT_BYTES), limit=MAX_RESULT_BYTES)


def validate_result(body, *, tool, value, expected_context, capability_profile_digest, workspace_principal):
    if type(body) is not dict:
        _fail()
    rebuilt = result(tool, value, **{k: body.get(k) for k in (
        "state", "reason", "principal_context", "capability_profile_digest", "workspace_principal", "data")})
    if rebuilt != body:
        _fail()
    if body["principal_context"] is not None and (
            body["principal_context"] != expected_context
            or body["capability_profile_digest"] != capability_profile_digest
            or body["workspace_principal"] != workspace_principal):
        _fail()
    return rebuilt
