"""Closed, dormant action grants in the existing sealed Workspace owner.

Synthetic principals/receipts only; no issuer, installed enrollment or action.
"""
import copy
import hashlib

import pytest

from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.mastermind_workspace_app import contract
from ops.executive_os import workspace_owner_enrollment as compiler
from tests.test_workspace_member_bindings import fixture, principal

V3 = "mastermind.workspace_acquisition_bindings.v3"
ACTIONS = ("discover", "open", "bind", "unbind", "refresh-builds")


def receipts(source, selected=()):
    return {
        name: {action: (
            f"fixture-action-receipt:{name}:{action}".encode()
            if name == "member-0" and action in selected else None
        ) for action in ACTIONS}
        for name in source["profiles"]
    }


def compile_source(selected=ACTIONS):
    policy, source = fixture(2)
    values = receipts(source, selected)
    compiled = compiler.compile_control_room_action_bindings(policy, source, values)
    return policy, source, values, compiled


def gates(policy, source, action):
    return contract.workspace_control_room_authorizers(
        policy=policy, load_bindings=lambda: source, action=action,
    )


def stamp(authorize, frame):
    return contract.permission_stamp(authorize, frame)


@pytest.mark.parametrize("schema", ["v1", "v2"])
@pytest.mark.parametrize("action", ACTIONS)
def test_legacy_read_membership_never_grants_an_action(schema, action):
    policy, source = fixture(2)
    if schema == "v1":
        source = {"schema": contract.BINDINGS_SCHEMA, "profiles": {
            "web": source["profiles"]["member-0"],
            "mac": {"enabled": False, "binding": None},
        }}
    frame = principal(source, "web" if schema == "v1" else "member-0")
    _, read = contract.workspace_authorizers(policy=policy, load_bindings=lambda: source)
    _, authorize = gates(policy, source, action)
    assert read(frame) is True
    assert authorize(frame) is False
    with pytest.raises(ValueError, match="access_denied"):
        stamp(authorize, frame)


@pytest.mark.parametrize("selected", ACTIONS)
def test_explicit_grant_only_enables_its_action_and_preserves_read(selected):
    policy, before, values, source = compile_source((selected,))
    frame = principal(source)
    _, old_read = contract.workspace_authorizers(policy=policy, load_bindings=lambda: before)
    _, read = contract.workspace_authorizers(policy=policy, load_bindings=lambda: source)
    assert source["schema"] == V3
    assert source["primary_profile"] == before["primary_profile"]
    assert read(frame) and stamp(read, frame) == stamp(old_read, frame)
    for action in ACTIONS:
        _, authorize = gates(policy, source, action)
        assert authorize(frame) is (action == selected)
    for name in source["profiles"]:
        assert source["profiles"][name]["binding"] == before["profiles"][name]["binding"]
    assert source["profiles"]["member-0"]["control_room_actions"][selected] == hashlib.sha256(
        values["member-0"][selected],
    ).hexdigest()


def test_action_rotation_and_revocation_do_not_change_sibling_or_read_stamps():
    policy, _, _, source = compile_source()
    frame = principal(source)
    _, read = contract.workspace_authorizers(policy=policy, load_bindings=lambda: source)
    _, discover = gates(policy, source, "discover")
    _, opened = gates(policy, source, "open")
    read_stamp, discover_stamp, open_stamp = stamp(read, frame), stamp(discover, frame), stamp(opened, frame)

    source["profiles"]["member-0"]["control_room_actions"]["discover"] = None
    assert not discover(frame)
    assert opened(frame) and stamp(opened, frame) == open_stamp
    assert stamp(read, frame) == read_stamp

    source["profiles"]["member-0"]["control_room_actions"]["discover"] = "d" * 64
    assert stamp(discover, frame) != discover_stamp
    assert stamp(opened, frame) == open_stamp
    source["primary_profile"] = "member-1"
    assert stamp(opened, frame) == open_stamp and stamp(read, frame) == read_stamp


def test_valid_membership_revocation_removes_all_actions_without_revoking_siblings():
    policy, _, _, source = compile_source()
    source["profiles"]["member-1"]["control_room_actions"]["open"] = "e" * 64
    first, second = principal(source), principal(source, "member-1")
    _, opened = gates(policy, source, "open")
    old_second = stamp(opened, second)
    source["profiles"]["member-0"]["enabled"] = False
    source["profiles"]["member-0"]["control_room_actions"] = dict.fromkeys(ACTIONS)
    assert not opened(first)
    assert opened(second) and stamp(opened, second) == old_second
    for action in ACTIONS:
        assert gates(policy, source, action)[1](first) is False


@pytest.mark.parametrize("field,value", [
    ("email", "admin@mastermind-x.com"),
    ("role", "admin"),
    ("policy_id", "foreign-policy"),
    ("issuer_digest", "0" * 64),
    ("subject_digest", "0" * 64),
    ("client_ref", "0" * 64),
    ("resource", "https://foreign.example.test"),
    ("scopes", [contract.SCOPE, "mastermind.executive.intent.submit"]),
])
def test_grants_bind_only_the_exact_verified_principal_frame(field, value):
    policy, _, _, source = compile_source()
    frame = dict(principal(source), **{field: value})
    _, authorize = gates(policy, source, "open")
    assert not authorize(frame)
    assert authorize.binding_digest(frame) is None
    assert not authorize("admin@mastermind-x.com")
    assert not authorize(principal(source, "member-1"))


def test_verified_principal_adapter_and_frame_share_one_action_stamp():
    policy, _, _, source = compile_source()
    frame = principal(source)
    verified = VerifiedPrincipal(
        **dict(frame, issuer=policy.issuer, scopes=tuple(frame["scopes"])),
        issued_at=1, expires_at=9999999999, jti_digest=None,
    )
    app_gate, frame_gate = gates(policy, source, "open")
    assert app_gate(verified) and frame_gate(frame)
    assert stamp(app_gate, verified) == stamp(frame_gate, frame)
    assert not app_gate(frame)


@pytest.mark.parametrize("mutation", [
    "missing_action", "unknown_action", "bad_digest", "bool_digest",
    "read_receipt", "disabled_with_grant", "extra_slot_key", "wrong_action_map",
])
def test_v3_validator_is_closed_and_does_not_promote_read_receipts(mutation):
    policy, _, _, source = compile_source()
    slot = source["profiles"]["member-0"]
    grants = slot["control_room_actions"]
    if mutation == "missing_action": del grants["open"]
    if mutation == "unknown_action": grants["send"] = None
    if mutation == "bad_digest": grants["open"] = "not-a-digest"
    if mutation == "bool_digest": grants["open"] = True
    if mutation == "read_receipt": grants["open"] = slot["binding"]["permission_digest"]
    if mutation == "disabled_with_grant": slot["enabled"] = False
    if mutation == "extra_slot_key": slot["operator"] = True
    if mutation == "wrong_action_map": slot["control_room_actions"] = None
    with pytest.raises(ValueError, match="access_denied"):
        contract.validate_workspace_bindings(source, policy)


def test_every_authorization_reloads_the_same_owner_and_failures_deny():
    policy, _, _, source = compile_source()
    current = [source]
    calls = []

    def loader():
        calls.append(True)
        if current[0] is None:
            raise OSError("fixture sealed owner unavailable")
        return current[0]

    _, authorize = contract.workspace_control_room_authorizers(
        policy=policy, load_bindings=loader, action="open",
    )
    frame = principal(source)
    assert authorize(frame)
    current[0] = None
    assert not authorize(frame)
    assert authorize.binding_digest(frame) is None
    assert len(calls) == 4


@pytest.mark.parametrize("bad", ["missing_profile", "missing_action", "unknown_action",
                                  "text_receipt", "empty_receipt", "oversized_receipt",
                                  "read_receipt", "disabled_profile"])
def test_compiler_requires_complete_separate_bounded_action_inputs(bad):
    policy, source = fixture(2)
    values = receipts(source)
    if bad == "missing_profile": del values["member-1"]
    if bad == "missing_action": del values["member-0"]["open"]
    if bad == "unknown_action": values["member-0"]["send"] = None
    if bad == "text_receipt": values["member-0"]["open"] = "digest-is-not-receipt-bytes"
    if bad == "empty_receipt": values["member-0"]["open"] = b""
    if bad == "oversized_receipt": values["member-0"]["open"] = b"x" * (compiler._MAX_RECEIPT_BYTES + 1)
    if bad == "read_receipt": values["member-0"]["open"] = b"enrollment-0"
    if bad == "disabled_profile":
        source["profiles"]["member-0"]["enabled"] = False
        values["member-0"]["open"] = b"fixture-action"
    with pytest.raises(compiler.WorkspaceOwnerCompilerError):
        compiler.compile_control_room_action_bindings(policy, source, values)


def test_compiler_preserves_existing_v1_binding_and_returns_detached_bytes():
    policy, source = fixture(1)
    legacy = {"schema": contract.BINDINGS_SCHEMA, "profiles": {
        "web": source["profiles"]["member-0"], "mac": {"enabled": False, "binding": None},
    }}
    before = copy.deepcopy(legacy)
    values = {name: dict.fromkeys(ACTIONS) for name in legacy["profiles"]}
    values["web"]["open"] = bytearray(b"fixture-action")
    result = compiler.compile_control_room_action_bindings(policy, legacy, values)
    assert legacy == before
    assert result["primary_profile"] is None
    assert result["profiles"]["mac"] == dict(
        legacy["profiles"]["mac"], control_room_actions=dict.fromkeys(ACTIONS),
    )
    result["profiles"]["web"]["binding"]["permission_digest"] = "f" * 64
    values["web"]["open"][:] = b"changed"
    assert legacy == before
    assert result["profiles"]["web"]["control_room_actions"]["open"] == hashlib.sha256(
        b"fixture-action",
    ).hexdigest()


@pytest.mark.parametrize("action", ["send", "", None, True])
def test_unknown_action_has_no_authorizer(action):
    policy, source = fixture()
    with pytest.raises(ValueError, match="access_denied"):
        gates(policy, source, action)
