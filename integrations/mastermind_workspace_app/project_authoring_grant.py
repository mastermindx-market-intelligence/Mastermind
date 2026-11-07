"""Dormant project action grants in the existing sealed Workspace owner.

V4 extends the same sealed membership document V1/V2/V3 already validate with
an explicit source-author receipt, independently scoped suspension, resume,
plan-adoption, direction-acceptance, file-add and preference receipts, and one
stable workstream+instruction admission-suspension receipt. V4 is unreleased
and closed, so the eighth slot joins this same schema in place. Legacy schemas
stay accepted only through the base validator and always deny project actions.
V5 preserves V4 and adds explicit plan-proposal publication and latest canonical
DATA read receipts. An older revision-pinned READ grant never becomes latest-DATA
authority; that new stamp grants no source write, adoption or execution.
No READ fallback, action reuse, mint, enrollment, token cache, file or store is
introduced here; actual receipt provenance and sealed installation remain owner
duties.
"""
from __future__ import annotations
import copy
import re

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
SCHEMA_V5 = "mastermind.workspace_acquisition_bindings.v5"
PLAN_PROPOSAL_ACTION = "publish_project_plan_proposal"
LATEST_DATA_READ_ACTION = "read_latest_project_data"
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
INSTRUCTION_SUSPEND_ACTION = "pause_instruction_admission"
INSTRUCTION_SUSPEND_PERMISSION_SCHEMA = "mastermind.workspace_instruction_admission_suspend_permission.v1"
INSTRUCTION_REF_PREFIX = "INS:"
_ACTION_FIELDS = {PROJECT_AUTHOR_ACTION: "project_authoring", PROJECT_SUSPEND_ACTION: "project_admission_suspend",
                  PROJECT_RESUME_ACTION: "project_admission_resume", PLAN_ADOPT_ACTION: "plan_adoption",
                  ACCEPT_DIRECTION_ACTION: "direction_acceptance", ADD_PROJECT_FILE_ACTION: "project_file_add",
                  SET_PROJECT_PREFERENCE_ACTION: "project_preference_set",
                  INSTRUCTION_SUSPEND_ACTION: "instruction_admission_suspend"}
_V5_ACTION_FIELDS = {PLAN_PROPOSAL_ACTION: "project_plan_proposal_publish",
                     LATEST_DATA_READ_ACTION: "project_canonical_data_read"}
_ALL_ACTION_FIELDS = {**_ACTION_FIELDS, **_V5_ACTION_FIELDS}

_SCOPED_ACTIONS = {PROJECT_SUSPEND_ACTION, PROJECT_RESUME_ACTION, PLAN_ADOPT_ACTION, ACCEPT_DIRECTION_ACTION,
                   ADD_PROJECT_FILE_ACTION, SET_PROJECT_PREFERENCE_ACTION, PLAN_PROPOSAL_ACTION}
_INSTRUCTION_SCOPED_ACTIONS = {INSTRUCTION_SUSPEND_ACTION}
_SCOPED_FIELDS = {_ALL_ACTION_FIELDS[action] for action in _SCOPED_ACTIONS}
_INSTRUCTION_SCOPED_FIELDS = {_ACTION_FIELDS[action] for action in _INSTRUCTION_SCOPED_ACTIONS}
_STAMP_SCHEMAS = {PROJECT_AUTHOR_ACTION: PROJECT_PERMISSION_SCHEMA, PROJECT_SUSPEND_ACTION: PROJECT_SUSPEND_PERMISSION_SCHEMA,
                  PROJECT_RESUME_ACTION: PROJECT_RESUME_PERMISSION_SCHEMA,
                  PLAN_ADOPT_ACTION: PLAN_ADOPT_PERMISSION_SCHEMA, ACCEPT_DIRECTION_ACTION: ACCEPT_DIRECTION_PERMISSION_SCHEMA,
                  ADD_PROJECT_FILE_ACTION: ADD_PROJECT_FILE_PERMISSION_SCHEMA,
                  SET_PROJECT_PREFERENCE_ACTION: SET_PROJECT_PREFERENCE_PERMISSION_SCHEMA,
                  INSTRUCTION_SUSPEND_ACTION: INSTRUCTION_SUSPEND_PERMISSION_SCHEMA}
_STAMP_SCHEMAS.update({PLAN_PROPOSAL_ACTION: "mastermind.workspace_project_plan_proposal_publish_permission.v1",
                      LATEST_DATA_READ_ACTION: "mastermind.workspace_project_canonical_data_read_permission.v1"})

_TOP_KEYS = frozenset({"schema", "profiles", "primary_profile"})
_SLOT_KEYS = frozenset({"enabled", "binding", "control_room_actions", "project_authoring", "project_admission_suspend",
                        "project_admission_resume", "plan_adoption", "direction_acceptance", "project_file_add",
                        "project_preference_set", "instruction_admission_suspend"})
_INSTRUCTION_GRANT_KEYS = frozenset({"work_ref", "instruction_ref", "permission_digest"})
_INSTRUCTION_KEY_PATTERN = re.compile(r"[A-Z0-9]+(?:-[A-Z0-9]+)*")


def valid_instruction_ref(value):
    """Exact stable instruction selector: INS: plus an UPPER-KEBAB key of 2..64 chars.

    The selector is stable identity, not a revision: no revision, hash or
    mutable counter field exists anywhere in the grant shape. The source
    revision stays a command-level CAS outside this gate and never resumes or
    mutates a stable suspension.
    """
    if type(value) is not str or not value.startswith(INSTRUCTION_REF_PREFIX):
        return False
    key = value[len(INSTRUCTION_REF_PREFIX):]
    if not 2 <= len(key) <= 64:
        return False
    return _INSTRUCTION_KEY_PATTERN.fullmatch(key) is not None


def project_action_fields(schema):
    """Closed versioned selection; this projection issues no receipt/grant."""
    if schema == SCHEMA:
        return dict(_ACTION_FIELDS)
    if schema == SCHEMA_V5:
        return dict(_ALL_ACTION_FIELDS)
    raise ValueError("access_denied")


def _refuses_project_grant(slot, field):
    """The grant is optional, closed, and null for disabled or unbound slots."""
    grant = slot[field]
    if grant is None:
        return False
    if field in _INSTRUCTION_SCOPED_FIELDS:
        if type(grant) is not dict or set(grant) != _INSTRUCTION_GRANT_KEYS:
            return True
        try:
            validate_work({"work_ref": grant["work_ref"]})
        except ValueError:
            return True
        if not valid_instruction_ref(grant["instruction_ref"]):
            return True
        grant = grant["permission_digest"]
    elif field in _SCOPED_FIELDS:
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
                        for other in _ALL_ACTION_FIELDS.values() if other != field and other in slot)))


def validate_project_bindings(value, policy):
    """Validate explicit v4/v5 project extensions of the existing sealed owner.

    Non-v4/v5 documents are accepted only through the existing base validator and
    never carry a project grant. A v4 document keeps the exact base shape plus
    closed independent project action grants per slot; the base validator
    still owns every identity, revocation, disabled-slot and exact-key guard
    through a detached v3 projection. The instruction suspension slot follows
    the same closed rules with an exact stable workstream+instruction selector
    pair. Unknown or malformed fields fail closed and the input is never
    mutated.
    """
    if type(value) is not dict or value.get("schema") not in {SCHEMA, SCHEMA_V5}:
        return validate_workspace_bindings(value, policy)
    if set(value) != _TOP_KEYS or type(value["profiles"]) is not dict:
        raise ValueError("access_denied")
    fields = project_action_fields(value["schema"])
    slot_keys = _SLOT_KEYS | (set(_V5_ACTION_FIELDS.values()) if value["schema"] == SCHEMA_V5 else set())
    slots = value["profiles"]
    for slot in slots.values():
        if (type(slot) is not dict or set(slot) != slot_keys
                or type(slot["enabled"]) is not bool
                or type(slot["control_room_actions"]) is not dict
                or set(slot["control_room_actions"]) != CONTROL_ROOM_ACTIONS
                or any(item is not None and (type(item) is not str or _HEX.fullmatch(item) is None)
                       for item in slot["control_room_actions"].values())
                or any(_refuses_project_grant(slot, field) for field in fields.values())):
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
        "schema": value["schema"],
        "primary_profile": validated["primary_profile"],
        "profiles": {name: dict(slot, **{field: copy.deepcopy(slots[name][field]) for field in fields.values()})
                     for name, slot in validated["profiles"].items()},
    }


def legacy_workspace_document(value, policy):
    """Explicit installed composition for unchanged READ/Control Room gates.

    Validate the entire same sealed document first, then strip only the new
    action fields, now including the instruction suspension slot. This does not
    admit v4 to the old base validator implicitly, and no READ or sibling
    action authority is inferred in either direction. An installed owner must
    deliberately bind this wrapper to its actual loader.
    """
    validated = validate_project_bindings(value, policy)
    if validated["schema"] not in {SCHEMA, SCHEMA_V5}:
        return validated
    return validate_workspace_bindings({"schema": ACTION_BINDINGS_SCHEMA,
        "primary_profile": validated["primary_profile"],
        "profiles": {name: {key: item for key, item in slot.items() if key not in _ALL_ACTION_FIELDS.values()}
                     for name, slot in validated["profiles"].items()}}, policy)


def workspace_project_authorizers(*, policy, load_bindings, action=PROJECT_AUTHOR_ACTION, work_ref=None,
                                  instruction_ref=None):
    """Bind an exact project action to the existing sealed membership owner.

    Legacy membership always denies project authoring; only a currently valid
    v4/v5 document with its distinct action receipt for exactly one enabled
    enrollment qualifies. Suspension and adoption match one explicit WS each.
    The instruction suspension action requires the exact stable selector pair
    (work_ref, instruction_ref) and its binding_digest compares both stable
    tuple fields; every other action rejects a non-null instruction_ref. The
    grant is bound to the stable pair, never to a revision: the source revision
    stays a command-level CAS and editing a source never auto-resumes a stable
    gate. Every check reloads the same owner; no grant
    cache, supplemental file or permission fallback is introduced. The stamp
    binds this action, member and grant, so unrelated membership or action
    changes stay independent. Actual receipt provenance and sealed
    installation remain owner duties.
    """
    if type(action) is not str or action not in _ALL_ACTION_FIELDS or not callable(load_bindings):
        raise ValueError("access_denied")
    if action in _INSTRUCTION_SCOPED_ACTIONS:
        validate_work({"work_ref": work_ref})
        if not valid_instruction_ref(instruction_ref):
            raise ValueError("access_denied")
    elif action in _SCOPED_ACTIONS:
        if instruction_ref is not None:
            raise ValueError("access_denied")
        validate_work({"work_ref": work_ref})
    elif work_ref is not None or instruction_ref is not None:
        raise ValueError("access_denied")
    validate_project_bindings(load_bindings(), policy)

    def binding_digest(principal):
        try:
            if type(principal) is not dict:
                principal = principal_frame(principal)
            if set(principal) != PRINCIPAL_KEYS:
                return None
            bindings = validate_project_bindings(load_bindings(), policy)
            if bindings["schema"] not in {SCHEMA, SCHEMA_V5}:
                return None
            matches = [slot for slot in bindings["profiles"].values()
                       if slot["enabled"] and slot["binding"] is not None
                       and all(principal[key] == slot["binding"][key] for key in PRINCIPAL_KEYS)]
            if len(matches) != 1:
                return None
            grant = matches[0].get(_ALL_ACTION_FIELDS[action])
            if grant is None:
                return None
            if action in _INSTRUCTION_SCOPED_ACTIONS:
                if grant["work_ref"] != work_ref or grant["instruction_ref"] != instruction_ref:
                    return None
                grant = grant["permission_digest"]
            elif action in _SCOPED_ACTIONS:
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
            if action in _INSTRUCTION_SCOPED_ACTIONS:
                stamp["work_ref"] = work_ref
                stamp["instruction_ref"] = instruction_ref
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
