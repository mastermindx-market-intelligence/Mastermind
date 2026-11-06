"""Dormant project action enrollment in the existing sealed Workspace owner.

Pure compile extension of the same sealed membership document this owner
already validates. An explicit, complete, separately supplied per-profile
project receipt map compiles into the validated v4 document. Existing
v1/v2/v3/v4 membership is accepted only through the actual project grant
validator and its legacy projection, and legacy members without Control Room
fields enter through the actual incumbent transition with a complete explicit
all-null Control Room map, so no existing authority is ever invented. Every
project action field is replaced only from its own explicit receipt entry:
null denies, nothing is implicitly retained, inherited or issued, and the
existing READ receipts, Control Room grants, bindings and primary
designation are preserved unchanged.

The compiler does NOT mint, source-authenticate or semantically qualify a
permission receipt, and introduces no membership, policy, file, config,
enrollment, token, service, Root, Git or install edge. The installed sealed
owner must qualify actual receipt provenance before any configuration write.
"""
from __future__ import annotations

import hashlib

from integrations.business_mcp_auth.contracts import AuthError
from integrations.mastermind_workspace_app.contract import CONTROL_ROOM_ACTIONS
from integrations.mastermind_workspace_app import project_authoring_grant as project_grant
from ops.executive_os.workspace_owner_enrollment import (
    _MAX_RECEIPT_BYTES,
    ResourcePolicy,
    WorkspaceOwnerCompilerError,
    compile_control_room_action_bindings,
)

_SCOPED_RECEIPT_KEYS = frozenset({"work_ref", "receipt"})
_AUTH_ERRORS = (AuthError, ValueError, TypeError, KeyError)


def _refuse(code: str) -> "None":
    raise WorkspaceOwnerCompilerError(code)


def _receipt_digest(receipt) -> str:
    """Existing owner hashing convention over bounded opaque receipt bytes."""
    if not isinstance(receipt, (bytes, bytearray)):
        _refuse("action_receipt_type")
    raw = bytes(receipt)
    if not raw or len(raw) > _MAX_RECEIPT_BYTES:
        _refuse("action_receipt_size")
    return hashlib.sha256(raw).hexdigest()


def compile_project_action_bindings(policy, existing_bindings, action_receipts, *, schema=project_grant.SCHEMA) -> dict:
    """Compile an explicit project action selection without changing membership.

    The whole existing document — v1, v2, v3 or v4 — is validated first
    through the actual project grant validator and then projected through its
    legacy composition; v1/v2 slots without Control Room fields enter through
    the actual incumbent transition with a complete explicit all-null Control
    Room map. Receipts must carry the exact validated profile set and the
    complete closed complete action map per profile: null denies, unbounded or
    malformed input refuses, disabled or unbound members cannot act, and one
    bounded receipt hashes to at most its own single action field, strictly
    scoped to one canonical workstream. The actual v4 validator owns the
    closed document shape and every READ, Control Room and sibling project
    reuse fence. Caller inputs are never mutated and raw receipt bytes never
    appear in the compiled document or in an error.
    """
    if not isinstance(policy, ResourcePolicy):
        _refuse("policy_type")
    try:
        action_fields = project_grant.project_action_fields(schema)
    except ValueError:
        _refuse("action_selection")
    try:
        project_grant.validate_project_bindings(existing_bindings, policy)
    except _AUTH_ERRORS:
        _refuse("existing_bindings")
    try:
        base = project_grant.legacy_workspace_document(existing_bindings, policy)
    except _AUTH_ERRORS:
        _refuse("existing_bindings")
    if any("control_room_actions" not in slot for slot in base["profiles"].values()):
        base = compile_control_room_action_bindings(policy, existing_bindings, {
            name: {action: None for action in CONTROL_ROOM_ACTIONS}
            for name in base["profiles"]
        })
    if type(action_receipts) is not dict or set(action_receipts) != set(base["profiles"]):
        _refuse("action_profiles")

    profiles = {}
    for name, slot in base["profiles"].items():
        supplied = action_receipts[name]
        if type(supplied) is not dict or set(supplied) != set(action_fields):
            _refuse("action_selection")
        grants = {}
        for action in sorted(action_fields):
            field = action_fields[action]
            value = supplied[action]
            if value is None:
                grants[field] = None
                continue
            if not slot["enabled"] or slot["binding"] is None:
                _refuse("disabled_action_profile")
            if action in project_grant._INSTRUCTION_SCOPED_ACTIONS:
                if type(value) is not dict or set(value) != {"work_ref", "instruction_ref", "receipt"}:
                    _refuse("action_selection")
                try:
                    project_grant.validate_work({"work_ref": value["work_ref"]})
                except (ValueError, TypeError):
                    _refuse("work_ref")
                if not project_grant.valid_instruction_ref(value["instruction_ref"]):
                    _refuse("instruction_ref")
                grants[field] = {"work_ref": value["work_ref"], "instruction_ref": value["instruction_ref"],
                                 "permission_digest": _receipt_digest(value["receipt"])}
            elif action in project_grant._SCOPED_ACTIONS:
                if type(value) is not dict or set(value) != _SCOPED_RECEIPT_KEYS:
                    _refuse("action_selection")
                try:
                    project_grant.validate_work({"work_ref": value["work_ref"]})
                except (ValueError, TypeError):
                    _refuse("work_ref")
                grants[field] = {
                    "work_ref": value["work_ref"],
                    "permission_digest": _receipt_digest(value["receipt"]),
                }
            else:
                grants[field] = _receipt_digest(value)
        profiles[name] = dict(slot, **grants)
    document = {
        "schema": schema,
        "primary_profile": base["primary_profile"],
        "profiles": profiles,
    }
    try:
        return project_grant.validate_project_bindings(document, policy)
    except _AUTH_ERRORS:
        _refuse("project_bindings")
