"""Closed, dormant source-author grants in the existing sealed Workspace owner.

Synthetic principals/receipts only: no JWT mint, credentials, installed
config, filesystem or socket call.
"""
import copy
import hashlib

import pytest

from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.mastermind_workspace_app import contract
from integrations.mastermind_workspace_app.project_authoring_grant import (
    PROJECT_AUTHOR_ACTION, PROJECT_PERMISSION_SCHEMA,
    SCHEMA as V4, validate_project_bindings, workspace_project_authorizers,
)
from tests.test_workspace_control_room_action_grants import compile_source
from tests.test_workspace_member_bindings import fixture, principal

GRANT = hashlib.sha256(b"fixture-project-authoring").hexdigest()
ROTATED = "e" * 64


def project_bindings(selected="member-0", grant=GRANT):
    """Extend the actually compiled v3 owner: explicit deepcopy, a null grant
    for every slot, then one explicit unique grant for the selected profile."""
    policy, _, _, source = compile_source()
    source = copy.deepcopy(source)
    source["schema"] = V4
    for slot in source["profiles"].values():
        slot["project_authoring"] = None
        slot["project_admission_suspend"] = None
        slot["project_admission_resume"] = None
        slot["plan_adoption"] = None
        slot["direction_acceptance"] = None
        slot["project_file_add"] = None
        slot["project_preference_set"] = None
        slot["instruction_admission_suspend"] = None
    if selected is not None:
        source["profiles"][selected]["project_authoring"] = grant
    return policy, source


def gates(policy, source):
    return workspace_project_authorizers(policy=policy, load_bindings=lambda: source)


def verified(policy, frame):
    return VerifiedPrincipal(
        **dict(frame, issuer=policy.issuer, scopes=tuple(frame["scopes"])),
        issued_at=1, expires_at=9999999999, jti_digest=None,
    )


def test_v4_extends_the_compiled_v3_owner_without_touching_shared_auth():
    policy, source = project_bindings()
    slot = source["profiles"]["member-0"]
    assert slot["project_authoring"] == GRANT
    assert GRANT != slot["binding"]["permission_digest"]
    assert GRANT not in slot["control_room_actions"].values()
    before = copy.deepcopy(source)
    result = validate_project_bindings(source, policy)
    assert source == before  # validation never mutates the input
    projected = contract.validate_workspace_bindings(
        {"schema": contract.ACTION_BINDINGS_SCHEMA,
         "profiles": {name: {key: item for key, item in bound.items()
                             if key not in {"project_authoring", "project_admission_suspend", "project_admission_resume", "plan_adoption", "direction_acceptance", "project_file_add", "project_preference_set", "instruction_admission_suspend"}}
                      for name, bound in source["profiles"].items()},
         "primary_profile": source["primary_profile"]}, policy)
    assert result == {"schema": V4, "primary_profile": projected["primary_profile"],
                      "profiles": {name: dict(bound, project_authoring=GRANT if name == "member-0" else None,
                                               project_admission_suspend=None, project_admission_resume=None,
                                               plan_adoption=None, direction_acceptance=None, project_file_add=None, project_preference_set=None, instruction_admission_suspend=None)
                                   for name, bound in projected["profiles"].items()}}
    assert all(set(bound) == {"enabled", "binding", "control_room_actions", "project_authoring", "project_admission_suspend", "project_admission_resume", "plan_adoption", "direction_acceptance", "project_file_add", "project_preference_set", "instruction_admission_suspend"}
               for bound in result["profiles"].values())
    # Detached closed bytes: mutating the result cannot change the input.
    result["profiles"]["member-0"]["project_authoring"] = "9" * 64
    result["profiles"]["member-0"]["binding"]["permission_digest"] = "9" * 64
    assert source == before
    # Dormant by construction: the existing shared auth rejects v4 documents
    # until an independently reviewed shared registration admits the schema.
    with pytest.raises(ValueError, match="access_denied"):
        contract.validate_workspace_bindings(source, policy)


@pytest.mark.parametrize("schema", ["v1", "v2", "v3"])
def test_read_and_legacy_membership_never_grants_project_authoring(schema):
    policy, source = fixture(2)
    if schema == "v1":
        source = {"schema": contract.BINDINGS_SCHEMA, "profiles": {
            "web": source["profiles"]["member-0"],
            "mac": {"enabled": False, "binding": None},
        }}
        frame = principal(source, "web")
    else:
        if schema == "v3":
            policy, _, _, source = compile_source()
        frame = principal(source)
    assert validate_project_bindings(source, policy)["schema"] == source["schema"]
    _, read = contract.workspace_authorizers(policy=policy, load_bindings=lambda: source)
    _, authorize = gates(policy, source)
    assert read(frame) is True  # membership still authenticates READ
    assert authorize(frame) is False  # ...but never project authoring
    assert authorize.binding_digest(frame) is None
    with pytest.raises(ValueError, match="access_denied"):
        contract.permission_stamp(authorize, frame)


def test_explicit_grant_qualifies_only_the_selected_member_with_one_stamp():
    _, _, _, v3 = compile_source()
    policy, source = project_bindings()
    frame, other = principal(source), principal(source, "member-1")
    # The shared base auth still rejects v4 documents, so the existing READ
    # gate keeps running on the membership-identical v3 owner until an
    # independently reviewed shared registration admits the v4 schema.
    _, read = contract.workspace_authorizers(policy=policy, load_bindings=lambda: v3)
    app, authorize = gates(policy, source)
    expected = contract.digest({
        "schema": PROJECT_PERMISSION_SCHEMA,
        "binding": source["profiles"]["member-0"]["binding"],
        "action": PROJECT_AUTHOR_ACTION, "permission_digest": GRANT,
    })
    assert app(verified(policy, frame)) and authorize(frame)
    assert contract.permission_stamp(authorize, frame) == expected
    assert contract.permission_stamp(app, verified(policy, frame)) == expected
    assert not authorize(other)
    assert authorize.binding_digest(other) is None
    assert read(frame) and read(other)  # the same members still authenticate READ


def test_verified_principal_adapter_and_frame_share_one_project_stamp():
    policy, source = project_bindings()
    frame = principal(source)
    app, authorize = gates(policy, source)
    assert app(verified(policy, frame)) and authorize(frame)
    assert (contract.permission_stamp(app, verified(policy, frame))
            == contract.permission_stamp(authorize, frame))
    assert not app(frame) and not authorize(verified(policy, frame))
    assert not authorize("admin@mastermind-x.com")
    assert authorize.binding_digest(5) is None


@pytest.mark.parametrize("field,value", [
    ("email", "admin@mastermind-x.com"), ("role", "admin"),
    ("policy_id", "foreign-policy"), ("issuer_digest", "0" * 64),
    ("subject_digest", "0" * 64), ("client_ref", "0" * 64),
    ("resource", "https://foreign.example.test"),
    ("scopes", [contract.SCOPE, "mastermind.executive.intent.submit"]),
])
def test_grants_bind_only_the_exact_verified_principal_frame(field, value):
    policy, source = project_bindings()
    forged = dict(principal(source), **{field: value})
    _, authorize = gates(policy, source)
    assert not authorize(forged)
    assert authorize.binding_digest(forged) is None


def test_grant_rotation_and_revocation_change_only_the_selected_member():
    _, _, _, v3 = compile_source()
    policy, source = project_bindings()
    source["profiles"]["member-1"]["project_authoring"] = "f" * 64
    frame, second = principal(source), principal(source, "member-1")
    membership = copy.deepcopy({name: bound["binding"] for name, bound in source["profiles"].items()})
    _, read = contract.workspace_authorizers(policy=policy, load_bindings=lambda: v3)
    _, authorize = gates(policy, source)
    read_stamp = contract.permission_stamp(read, frame)
    first_stamp = contract.permission_stamp(authorize, frame)
    second_stamp = contract.permission_stamp(authorize, second)

    source["profiles"]["member-0"]["project_authoring"] = ROTATED
    assert contract.permission_stamp(authorize, frame) != first_stamp
    assert contract.permission_stamp(authorize, second) == second_stamp

    source["profiles"]["member-0"]["project_authoring"] = None
    assert not authorize(frame)
    assert authorize.binding_digest(frame) is None
    with pytest.raises(ValueError, match="access_denied"):
        contract.permission_stamp(authorize, frame)
    assert authorize(second)
    assert contract.permission_stamp(authorize, second) == second_stamp
    # The grant changes never touch the sealed membership itself.
    assert {name: bound["binding"] for name, bound in source["profiles"].items()} == membership
    assert read(frame) and contract.permission_stamp(read, frame) == read_stamp


def test_disabled_or_unbound_profiles_cannot_hold_or_use_a_grant():
    policy, source = project_bindings()
    slot = source["profiles"]["member-0"]
    slot["enabled"] = False
    slot["control_room_actions"] = dict.fromkeys(contract.CONTROL_ROOM_ACTIONS)
    with pytest.raises(ValueError, match="access_denied"):
        validate_project_bindings(source, policy)  # a disabled member cannot retain the grant
    slot["project_authoring"] = None
    validated = validate_project_bindings(source, policy)
    assert validated["profiles"]["member-0"]["project_authoring"] is None
    _, authorize = gates(policy, source)
    assert not authorize(principal(source))  # a disabled member never qualifies
    unbound = copy.deepcopy(source)
    unbound["profiles"]["member-0"].update({"binding": None, "project_authoring": GRANT})
    with pytest.raises(ValueError, match="access_denied"):
        validate_project_bindings(unbound, policy)  # an unbound member cannot hold the grant
    unbound["profiles"]["member-0"]["project_authoring"] = None
    assert validate_project_bindings(unbound, policy)["schema"] == V4


@pytest.mark.parametrize("mutation", [
    "missing_slot_key", "unknown_slot_key", "unknown_top_key", "unknown_action_key",
    "missing_action_key", "wrong_action_map", "bool_grant", "int_grant",
    "bad_grant_text", "uppercase_grant", "short_grant", "long_grant",
    "read_receipt", "action_receipt", "disabled_with_grant", "unbound_with_grant",
    "bad_primary", "profiles_not_dict",
])
def test_v4_validator_is_closed_and_never_mutates_the_input(mutation):
    policy, source = project_bindings()
    slot = source["profiles"]["member-0"]
    if mutation == "missing_slot_key": del slot["project_authoring"]
    if mutation == "unknown_slot_key": slot["operator"] = True
    if mutation == "unknown_top_key": source["admin"] = True
    if mutation == "unknown_action_key": slot["control_room_actions"]["send"] = None
    if mutation == "missing_action_key": del slot["control_room_actions"]["open"]
    if mutation == "wrong_action_map": slot["control_room_actions"] = None
    if mutation == "bool_grant": slot["project_authoring"] = True
    if mutation == "int_grant": slot["project_authoring"] = 5
    if mutation == "bad_grant_text": slot["project_authoring"] = "not-a-digest"
    if mutation == "uppercase_grant": slot["project_authoring"] = "A" * 64
    if mutation == "short_grant": slot["project_authoring"] = "a" * 63
    if mutation == "long_grant": slot["project_authoring"] = "a" * 65
    if mutation == "read_receipt": slot["project_authoring"] = slot["binding"]["permission_digest"]
    if mutation == "action_receipt":
        slot["project_authoring"] = slot["control_room_actions"]["open"]
    if mutation == "disabled_with_grant": slot["enabled"] = False
    if mutation == "unbound_with_grant":
        slot["enabled"] = False; slot["binding"] = None
    if mutation == "bad_primary": source["primary_profile"] = "not-enrolled"
    if mutation == "profiles_not_dict": source["profiles"] = [slot]
    before = copy.deepcopy(source)
    with pytest.raises(ValueError, match="access_denied"):
        validate_project_bindings(source, policy)
    assert source == before
    with pytest.raises(ValueError, match="access_denied"):
        gates(policy, source)  # the constructor rejects the same documents


def test_unknown_schema_and_malformed_owner_fail_closed():
    policy, source = project_bindings()
    forged = dict(source, schema="mastermind.workspace_acquisition_bindings.v9")
    with pytest.raises(ValueError, match="access_denied"):
        validate_project_bindings(forged, policy)
    with pytest.raises(ValueError, match="access_denied"):
        gates(policy, forged)
    with pytest.raises(ValueError, match="access_denied"):
        gates(policy, {"schema": V4})
    with pytest.raises(ValueError, match="access_denied"):
        workspace_project_authorizers(policy=policy, load_bindings=None)


def test_every_check_reloads_the_same_owner_and_failures_deny_without_cache():
    policy, source = project_bindings()
    frame = principal(source)
    current, calls = [source], []

    def loader():
        calls.append(True)
        if current[0] is None:
            raise OSError("fixture sealed owner unavailable")
        return current[0]

    app, authorize = workspace_project_authorizers(policy=policy, load_bindings=loader)
    stamp = contract.permission_stamp(authorize, frame)
    assert app(verified(policy, frame)) and authorize(frame)
    current[0] = None
    assert not authorize(frame)
    assert authorize.binding_digest(frame) is None
    assert not app(verified(policy, frame))
    with pytest.raises(ValueError, match="access_denied"):
        contract.permission_stamp(authorize, frame)
    assert len(calls) == 8  # constructor + five checks, exactly one owner read each

    current[0] = source
    assert authorize(frame)
    assert contract.permission_stamp(authorize, frame) == stamp
    assert len(calls) == 10
    assert app.binding_digest(frame) == stamp  # both gates share one stamp path
    assert len(calls) == 11

    current[0] = {"schema": V4, "profiles": {}, "primary_profile": None}
    assert not authorize(frame)
    assert authorize.binding_digest(frame) is None
    assert len(calls) == 13


def test_project_stamp_is_independent_of_read_and_action_stamps():
    _, _, _, v3 = compile_source()
    policy, source = project_bindings()
    frame = principal(source)
    _, read = contract.workspace_authorizers(policy=policy, load_bindings=lambda: v3)
    _, opened = contract.workspace_control_room_authorizers(
        policy=policy, load_bindings=lambda: v3, action="open")
    _, authorize = gates(policy, source)
    stamps = {contract.permission_stamp(read, frame),
              contract.permission_stamp(opened, frame),
              contract.permission_stamp(authorize, frame)}
    assert len(stamps) == 3
