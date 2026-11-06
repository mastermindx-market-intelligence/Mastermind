"""Typed private Knowledge recipes over the nominal installed source facade.

Code qualification belongs to its sealed collector/child. A module object,
source-reference dictionary or UI grant label cannot substitute for that facade.
Private restoration preserves the original actor/stamp/code/preimages/date; it
never acquires today's record or silently rebases an original operation.
"""
from __future__ import annotations
import hashlib
import json
import re
from datetime import date

from control_plane.installed_project_knowledge_compiler import InstalledProjectKnowledgeCompiler
from integrations.mastermind_workspace_app.source_operation_context import WorkspaceSourceOperationPermission
from integrations.mastermind_workspace_app.source_operation_principal import source_principal_scope

_REPO = "mastermindx-market-intelligence/macro"
_ACTIONS = {
    "mastermind.project_file_add_request.v1": ("add_project_file", "project_file_add"),
    "mastermind.project_preference_set_request.v1": ("set_project_communication_preference", "project_preference_set"),
}
_PRIVATE_SCHEMA = "mastermind.project_source_original_input.v1"
_REF_PATHS = {"compiler": "scripts/project_knowledge_recipes.py", "owner": "scripts/agentos.py"}


def _fail():
    raise ValueError("PROJECT_KNOWLEDGE_RECIPE_INVALID")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _detach(value):
    count = [0]
    def walk(item, depth=0):
        count[0] += 1
        if count[0] > 8192 or depth > 48:
            _fail()
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                _fail()
            return {key: walk(child, depth+1) for key, child in item.items()}
        if type(item) is list:
            return [walk(child, depth+1) for child in item]
        if item is None or type(item) in (str, bool, int):
            return item
        _fail()
    try:
        result = walk(value)
        if len(_canonical(result)) > 524288:
            _fail()
        return result
    except (UnicodeError, RecursionError, OverflowError, TypeError):
        _fail()


def _keys(value, names):
    if type(value) is not dict or set(value) != set(names):
        _fail()


def _hex(value, length):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value) is None:
        _fail()
    return value


def _sha(value):
    if type(value) is not str:
        _fail()
    try:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
    except UnicodeError:
        _fail()


class PreparedProjectKnowledge:
    """Detached prepared material; only its original adapter may publish it."""
    __slots__ = ("_owner", "_private", "_recipe", "fingerprint_sha256", "request_sha256")
    def __init__(self, owner, payload, recipe):
        self._owner = owner
        self._private, self._recipe = _canonical(payload), _canonical(recipe)
        self.fingerprint_sha256 = recipe["request_fingerprint"]
        self.request_sha256 = hashlib.sha256(_canonical(payload["request"])).hexdigest()

    def private_payload(self):
        return json.loads(self._private)


class ProjectKnowledgeRecipeAdapter:
    def __init__(self, compiler):
        if type(compiler) is not InstalledProjectKnowledgeCompiler:
            raise TypeError("actual installed Knowledge compiler facade required")
        self._compiler, self._owner = compiler, object()

    @staticmethod
    def _actor(request, principal, permission):
        if (type(permission) is not WorkspaceSourceOperationPermission
                or not permission.check() or request.get("schema") not in _ACTIONS):
            raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        scope = source_principal_scope(principal)
        action, _ = _ACTIONS[request["schema"]]
        if (permission.action != action or permission.work_ref != request.get("work_ref")
                or permission.principal_scope != scope):
            raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        return {"principal_scope": scope, "actor_ref": "workspace:" + scope,
                "permission_binding_digest": permission.permission_binding_digest}

    def prepare(self, *, request, principal, permission, decision_date):
        public = _detach(request)
        if type(public) is not dict:
            _fail()
        actor = self._actor(public, principal, permission)
        try:
            if type(decision_date) is not str or date.fromisoformat(decision_date).isoformat() != decision_date:
                _fail()
        except (ValueError, TypeError):
            _fail()
        captured = self._compiler.compile(public, actor_ref=actor["actor_ref"],
            permission_binding_digest=actor["permission_binding_digest"], decision_date=decision_date)
        if not permission.check():
            raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        if type(captured) is not dict or type(captured.get("initial_snapshot")) is not dict or captured["initial_snapshot"].get("decision_date") != decision_date:
            _fail()
        return self._prepared(public, actor, captured)

    def restore(self, *, private_payload, trusted_recipe_fingerprint, principal, permission):
        payload = _detach(private_payload)
        _keys(payload, {"schema", "action", "request", "actor", "initial_snapshot", "source_binding"})
        if payload["schema"] != _PRIVATE_SCHEMA or type(payload["request"]) is not dict:
            _fail()
        actor = self._actor(payload["request"], principal, permission)
        if payload["actor"] != actor or payload["action"] != permission.action:
            raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        captured = self._compiler.restore(payload["request"], actor_ref=actor["actor_ref"],
            permission_binding_digest=actor["permission_binding_digest"],
            initial_snapshot=payload["initial_snapshot"], source_binding=payload["source_binding"])
        prepared = self._prepared(payload["request"], actor, captured)
        if (prepared.private_payload() != payload
                or prepared.fingerprint_sha256 != _hex(trusted_recipe_fingerprint, 64)):
            _fail()
        if not permission.check():
            raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        return prepared

    def recipe(self, prepared):
        if type(prepared) is not PreparedProjectKnowledge or prepared._owner is not self._owner:
            _fail()
        return json.loads(prepared._recipe)

    def _prepared(self, request, actor, captured):
        captured = _detach(captured)
        _keys(captured, {"schema", "recipe", "initial_snapshot", "source_binding"})
        if captured["schema"] != "mastermind.project_knowledge_recipe_capture.v1":
            _fail()
        recipe, snapshot, refs = (captured[key] for key in ("recipe", "initial_snapshot", "source_binding"))
        _keys(recipe, {"schema", "state", "action", "work_ref", "request_id", "request_fingerprint",
                       "captured_commit", "permission_binding_digest", "postimages"})
        _keys(snapshot, {"workstream_text", "decision_text", "decision_date"})
        _keys(refs, _REF_PATHS)
        action, recipe_action = _ACTIONS[request["schema"]]
        if (recipe["schema"] != "mastermind.project_knowledge_recipe.v1" or recipe["state"] != "DRAFT_ONLY"
                or recipe["action"] != recipe_action or recipe["work_ref"] != request["work_ref"]
                or recipe["request_id"] != request["request_id"]
                or recipe["captured_commit"] != request["source_commit"]
                or recipe["permission_binding_digest"] != actor["permission_binding_digest"]
                or _sha(snapshot["workstream_text"]) != request["base_revision"]):
            _fail()
        _hex(recipe["request_fingerprint"], 64)
        # Only the nominal issued facade can return this capture. CODE C refs
        # are paired with each other, while captured_commit/CAS is actual DATA N.
        # Public requests never select C; private restoration retains exact refs.
        for role, path in _REF_PATHS.items():
            ref = refs[role]
            _keys(ref, {"repository", "commit", "path", "content_sha256"})
            if ref["repository"] != _REPO or ref["path"] != path or ref["commit"] != refs["compiler"]["commit"]:
                _fail()
            _hex(ref["commit"], 40); _hex(ref["content_sha256"], 64)
        images = recipe["postimages"]
        if type(images) is not list or len(images) != 2:
            _fail()
        key = request["work_ref"][3:]
        ws_path = "agentos/workstreams/WS-" + key + ".md"
        if action == "add_project_file":
            if snapshot["decision_text"] is not None:
                _fail()
            identity = {"principal_scope": actor["principal_scope"], "request_id": request["request_id"], "work_ref": request["work_ref"]}
            suffix = request["file"]["display_name"].rsplit(".",1)[-1].lower()
            path = "agentos/project-files/WS-" + key + "/" + hashlib.sha256(_canonical(identity)).hexdigest() + "." + suffix
            other_preimage = None
        else:
            path = "agentos/decisions/DEC-PROJECT-COMMUNICATION-PREFERENCE-" + key + ".md"
            other_preimage = _sha(snapshot["decision_text"]) if snapshot["decision_text"] is not None else None
            if other_preimage != request["expected_preference_revision"]:
                _fail()
        if {image.get("path") for image in images if type(image) is dict} != {ws_path, path}:
            _fail()
        for image in images:
            _keys(image, {"path", "content_utf8", "content_sha256", "expected_preimage_sha256"})
            if (_sha(image["content_utf8"]) != image["content_sha256"] or
                    image["expected_preimage_sha256"] != (request["base_revision"] if image["path"] == ws_path else other_preimage)):
                _fail()
            if action == "add_project_file" and image["path"] == path and image["content_utf8"] != request["file"]["content_utf8"]:
                _fail()
        payload = {"schema": _PRIVATE_SCHEMA, "action": action, "request": request, "actor": actor,
                   "initial_snapshot": snapshot, "source_binding": refs}
        return PreparedProjectKnowledge(self._owner, payload, recipe)
