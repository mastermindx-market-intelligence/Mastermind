"""Actual incumbent policy/verified principal and eighth stable-tuple grant."""
import copy
import hashlib
import pytest
from integrations.mastermind_workspace_app import project_authoring_grant as grant
from integrations.mastermind_workspace_app.contract import principal_frame
from tests.test_workspace_project_authoring_grant import project_bindings, verified
from tests.test_workspace_member_bindings import principal
from ops.executive_os.workspace_project_action_enrollment import compile_project_action_bindings


def scope():
    policy, source = project_bindings()
    source["profiles"]["member-0"]["instruction_admission_suspend"] = {
        "work_ref": "WS:TEST", "instruction_ref": "INS:WEEKLY-UPDATE", "permission_digest": "f" * 64}
    return policy, source, verified(policy, principal(source))


def gates(policy, source, work="WS:TEST", instruction="INS:WEEKLY-UPDATE"):
    return grant.workspace_project_authorizers(policy=policy, load_bindings=lambda: source,
        action=grant.INSTRUCTION_SUSPEND_ACTION, work_ref=work, instruction_ref=instruction)


def test_exact_stable_tuple_and_real_verified_principal_are_required():
    policy, source, who = scope()
    caller, frame = gates(policy, source)
    assert caller(who) and frame(principal_frame(who))
    assert caller.binding_digest(who) == frame.binding_digest(principal_frame(who))
    assert not gates(policy, source, work="WS:FOREIGN")[0](who)
    assert not gates(policy, source, instruction="INS:OTHER")[0](who)
    assert not caller({"signed_in": True})


@pytest.mark.parametrize("value", [None, "INS:A", "INS:../path", "INS:lower", "INS:--BAD",
                                  "INS:AB\n", "INS:" + "A" * 65, "INS:AB:CD"])
def test_malformed_instruction_selector_fails_closed(value):
    policy, source, _ = scope()
    with pytest.raises(ValueError): gates(policy, source, instruction=value)


@pytest.mark.parametrize("field", [f for f in grant._ACTION_FIELDS.values() if f != "instruction_admission_suspend"])
def test_instruction_receipt_cannot_reuse_any_project_sibling(field):
    policy, source, _ = scope()
    slot = source["profiles"]["member-0"]
    other = slot[field]
    if other is None:
        other = {"work_ref": "WS:TEST", "permission_digest": "e" * 64} if field != "project_authoring" else "e" * 64
        slot[field] = other
    slot["instruction_admission_suspend"]["permission_digest"] = other["permission_digest"] if type(other) is dict else other
    with pytest.raises(ValueError): grant.validate_project_bindings(source, policy)


@pytest.mark.parametrize("change", ["revision", "disabled", "unbound", "read_reuse", "ccr_reuse"])
def test_no_revision_identity_or_cross_authority_reuse(change):
    policy, source, _ = scope()
    slot = source["profiles"]["member-0"]
    if change == "revision": slot["instruction_admission_suspend"]["revision"] = "a" * 64
    if change == "disabled": slot["enabled"] = False
    if change == "unbound": slot["binding"] = None
    if change == "read_reuse": slot["instruction_admission_suspend"]["permission_digest"] = slot["binding"]["permission_digest"]
    if change == "ccr_reuse":
        key = next(iter(slot["control_room_actions"]))
        slot["control_room_actions"][key] = "f" * 64
    with pytest.raises(ValueError): grant.validate_project_bindings(source, policy)


def test_current_owner_reload_withdraws_original_tuple_and_sibling_actions_reject_instruction_selector():
    policy, source, who = scope()
    caller, _ = gates(policy, source)
    old = caller.binding_digest(who)
    source["profiles"]["member-0"]["instruction_admission_suspend"]["permission_digest"] = "d" * 64
    assert caller.binding_digest(who) not in (None, old)
    source["profiles"]["member-0"]["instruction_admission_suspend"] = None
    assert not caller(who) and caller.binding_digest(who) is None
    for action in grant._ACTION_FIELDS:
        if action == grant.INSTRUCTION_SUSPEND_ACTION: continue
        with pytest.raises(ValueError):
            grant.workspace_project_authorizers(policy=policy, load_bindings=lambda: source,
                action=action, work_ref=None if action == grant.PROJECT_AUTHOR_ACTION else "WS:TEST",
                instruction_ref="INS:WEEKLY-UPDATE")


def test_actual_enrollment_compiler_preserves_stable_tuple_without_issuing_receipt():
    policy, source, who = scope()
    actions = {profile: {action: None for action in grant._ACTION_FIELDS} for profile in source["profiles"]}
    receipt = b"explicit-test-source-authorized-instruction-receipt"
    actions["member-0"][grant.INSTRUCTION_SUSPEND_ACTION] = {
        "work_ref": "WS:TEST", "instruction_ref": "INS:WEEKLY-UPDATE", "receipt": receipt}
    compiled = compile_project_action_bindings(policy, source, actions)
    assert compiled["profiles"]["member-0"]["instruction_admission_suspend"] == {
        "work_ref": "WS:TEST", "instruction_ref": "INS:WEEKLY-UPDATE",
        "permission_digest": hashlib.sha256(receipt).hexdigest()}
    assert gates(policy, compiled)[0](who)
    assert receipt.decode() not in str(compiled)
