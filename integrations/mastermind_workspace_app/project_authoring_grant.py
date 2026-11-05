"""Dormant project action grants in the existing sealed Workspace owner.

V4 extends the same sealed membership document V1/V2/V3 already validate with
an explicit source-author receipt and independently scoped suspension and
plan-adoption receipts. Legacy schemas stay accepted only through the base validator
and always deny project actions. No READ fallback,
action reuse, mint, enrollment, token cache, file or store is introduced here;
actual receipt provenance and sealed installation remain owner duties.
"""
from __future__ import annotations
import copy

from integrations.mastermind_workspace_app.contract import (
    ACTION_BINDINGS_SCHEMA,
    CONTROL_ROOM_ACTIONS,
    PRINCIPAL_KEYS,
    _HEX,
    digest,
    principal_frame,
    validate_workspace_bindings,
)
from common.workspace_project_journal_contract import validate_selection as validate_work

SCHEMA = "mastermind.workspace_acquisition_bindings.v4"
PROJECT_AUTHOR_ACTION = "publish_project_proposal"
PROJECT_PERMISSION_SCHEMA = "mastermind.workspace_project_author_permission.v1"
PROJECT_SUSPEND_ACTION = "pause_workstream_admission"
PROJECT_SUSPEND_PERMISSION_SCHEMA = "mastermind.workspace_project_admission_suspend_permission.v1"
PROJECT_RESUME_ACTION = "resume_workstream_admission"
PROJECT_RESUME_PERMISSION_SCHEMA = "mastermind.workspace_project_admission_resume_permission.v1"
PLAN_ADOPT_ACTION = "ADOPT_PLAN"
PLAN_ADOPT_PERMISSION_SCHEMA = "mastermind.workspace_plan_adoption_permission.v1"
ACCEPT_DIRECTION_ACTION = "ACCEPT_DIRECTION"
ACCEPT_DIRECTION_PERMISSION_SCHEMA = "mastermind.workspace_direction_acceptance_permission.v1"
ADD_PROJECT_FILE_ACTION = "add_project_file"
ADD_PROJECT_FILE_PERMISSION_SCHEMA = "mastermind.workspace_project_file_add_permission.v1"
SET_PROJECT_PREFERENCE_ACTION = "set_project_communication_preference"
SET_PROJECT_PREFERENCE_PERMISSION_SCHEMA = "mastermind.workspace_project_preference_set_permission.v1"
_ACTION_FIELDS = {PROJECT_AUTHOR_ACTION: "project_authoring", PROJECT_SUSPEND_ACTION: "project_admission_suspend",
                  PROJECT_RESUME_ACTION: "project_admission_resume", PLAN_ADOPT_ACTION: "plan_adoption",
                  ACCEPT_DIRECTION_ACTION: "direction_acceptance", ADD_PROJECT_FILE_ACTION: "project_file_add",
                  SET_PROJECT_PREFERENCE_ACTION: "project_preference_set"}
_SCOPED_ACTIONS = {PROJECT_SUSPEND_ACTION, PROJECT_RESUME_ACTION, PLAN_ADOPT_ACTION, ACCEPT_DIRECTION_ACTION,
                   ADD_PROJECT_FILE_ACTION, SET_PROJECT_PREFERENCE_ACTION}
_SCOPED_FIELDS = {_ACTION_FIELDS[action] for action in _SCOPED_ACTIONS}
_STAMP_SCHEMAS = {PROJECT_AUTHOR_ACTION: PROJECT_PERMISSION_SCHEMA, PROJECT_SUSPEND_ACTION: PROJECT_SUSPEND_PERMISSION_SCHEMA,
                  PROJECT_RESUME_ACTION: PROJECT_RESUME_PERMISSION_SCHEMA,
                  PLAN_ADOPT_ACTION: PLAN_ADOPT_PERMISSION_SCHEMA, ACCEPT_DIRECTION_ACTION: ACCEPT_DIRECTION_PERMISSION_SCHEMA,
                  ADD_PROJECT_FILE_ACTION: ADD_PROJECT_FILE_PERMISSION_SCHEMA,
                  SET_PROJECT_PREFERENCE_ACTION: SET_PROJECT_PREFERENCE_PERMISSION_SCHEMA}
_TOP_KEYS = frozenset({"schema", "profiles", "primary_profile"})
_SLOT_KEYS = frozenset({"enabled", "binding", "control_room_actions", "project_authoring", "project_admission_suspend",
                        "project_admission_resume", "plan_adoption", "direction_acceptance", "project_file_add", "project_preference_set"})


def _refuses_project_grant(slot, field):
    """The grant is optional, closed, and null for disabled or unbound slots."""
    grant = slot[field]
    if grant is None:
        return False
    if field in _SCOPED_FIELDS:
        if type(grant) is not dict or set(grant) != {"work_ref", "permission_digest"}:
            return True
        try:
            validate_work({"work_ref": grant["work_ref"]})
        except ValueError:
            return True
        grant = grant["permission_digest"]
    if type(grant) is not str or _HEX.fullmatch(grant) is None:
        return True
    if not slot["enabled"] or slot["binding"] is None:
        return True
    return (type(slot["binding"]) is dict
            and (grant == slot["binding"].get("permission_digest")
                 or grant in slot["control_room_actions"].values()
                 or any(grant == (slot[other].get("permission_digest") if type(slot[other]) is dict else slot[other])
                        for other in _ACTION_FIELDS.values() if other != field)))


def validate_project_bindings(value, policy):
    """Validate the v4 source-author extension of the existing sealed owner.

    Non-v4 documents are accepted only through the existing base validator and
    never carry a project grant. A v4 document keeps the exact base shape plus
    closed independent project action grants per slot; the base validator
    still owns every identity, revocation, disabled-slot and exact-key guard
    through a detached v3 projection. Unknown or malformed fields fail closed
    and the input is never mutated.
    """
    if type(value) is not dict or value.get("schema") != SCHEMA:
        return validate_workspace_bindings(value, policy)
    if set(value) != _TOP_KEYS or type(value["profiles"]) is not dict:
        raise ValueError("access_denied")
    slots = value["profiles"]
    for slot in slots.values():
        if (type(slot) is not dict or set(slot) != _SLOT_KEYS
                or type(slot["enabled"]) is not bool
                or type(slot["control_room_actions"]) is not dict
                or set(slot["control_room_actions"]) != CONTROL_ROOM_ACTIONS
                or any(item is not None and (type(item) is not str or _HEX.fullmatch(item) is None)
                       for item in slot["control_room_actions"].values())
                or any(_refuses_project_grant(slot, field) for field in _ACTION_FIELDS.values())):
            raise ValueError("access_denied")
    validated = validate_workspace_bindings({
        "schema": ACTION_BINDINGS_SCHEMA,
        "primary_profile": value["primary_profile"],
        "profiles": {name: {
            "enabled": slot["enabled"], "binding": slot["binding"],
            "control_room_actions": dict(slot["control_room_actions"]),
        } for name, slot in slots.items()},
    }, policy)
    return {
        "schema": SCHEMA,
        "primary_profile": validated["primary_profile"],
        "profiles": {name: dict(slot, **{field: copy.deepcopy(slots[name][field]) for field in _ACTION_FIELDS.values()})
                     for name, slot in validated["profiles"].items()},
    }


def legacy_workspace_document(value, policy):
    """Explicit installed composition for unchanged READ/Control Room gates.

    Validate the entire same sealed document first, then strip only the new
    action fields. This does not admit v4 to the old base validator implicitly.
    An installed owner must deliberately bind this wrapper to its actual loader.
    """
    validated = validate_project_bindings(value, policy)
    if validated["schema"] != SCHEMA:
        return validated
    return validate_workspace_bindings({"schema": ACTION_BINDINGS_SCHEMA,
        "primary_profile": validated["primary_profile"],
        "profiles": {name: {key: item for key, item in slot.items() if key not in _ACTION_FIELDS.values()}
                     for name, slot in validated["profiles"].items()}}, policy)


def workspace_project_authorizers(*, policy, load_bindings, action=PROJECT_AUTHOR_ACTION, work_ref=None):
    """Bind an exact project action to the existing sealed membership owner.

    Legacy membership always denies project authoring; only a currently valid
    v4 document with its distinct action receipt for exactly one enabled
    enrollment qualifies. Suspension and adoption match one explicit WS each.
    Every check reloads the same owner; no grant
    cache, supplemental file or permission fallback is introduced. The stamp
    binds this action, member and grant, so unrelated membership or action
    changes stay independent. Actual receipt provenance and sealed
    installation remain owner duties.
    """
    if type(action) is not str or action not in _ACTION_FIELDS or not callable(load_bindings):
        raise ValueError("access_denied")
    if action in _SCOPED_ACTIONS:
        validate_work({"work_ref": work_ref})
    elif work_ref is not None:
        raise ValueError("access_denied")
    validate_project_bindings(load_bindings(), policy)

    def binding_digest(principal):
        try:
            if type(principal) is not dict:
                principal = principal_frame(principal)
            if set(principal) != PRINCIPAL_KEYS:
                return None
            bindings = validate_project_bindings(load_bindings(), policy)
            if bindings["schema"] != SCHEMA:
                return None
            matches = [slot for slot in bindings["profiles"].values()
                       if slot["enabled"] and slot["binding"] is not None
                       and all(principal[key] == slot["binding"][key] for key in PRINCIPAL_KEYS)]
            if len(matches) != 1:
                return None
            grant = matches[0][_ACTION_FIELDS[action]]
            if grant is None:
                return None
            if action in _SCOPED_ACTIONS:
                if grant["work_ref"] != work_ref:
                    return None
                grant = grant["permission_digest"]
            stamp = {
                "schema": _STAMP_SCHEMAS[action],
                "binding": matches[0]["binding"], "action": action,
                "permission_digest": grant,
            }
            if action in _SCOPED_ACTIONS:
                stamp["work_ref"] = work_ref
            return digest(stamp)
        except Exception:
            return None

    def authorize_frame(principal):
        return type(principal) is dict and binding_digest(principal) is not None

    def authorize_principal(principal):
        try:
            return authorize_frame(principal_frame(principal))
        except Exception:
            return False

    authorize_principal.binding_digest = binding_digest
    authorize_frame.binding_digest = binding_digest
    return authorize_principal, authorize_frame
