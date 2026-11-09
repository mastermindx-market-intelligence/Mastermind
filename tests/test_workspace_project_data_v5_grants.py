"""Distinct dormant v5 data-read/proposal grants; no issuance or live receipt."""
import copy
import pytest

from integrations.mastermind_workspace_app import project_authoring_grant as grant
from ops.executive_os.workspace_project_action_enrollment import compile_project_action_bindings
from ops.executive_os.workspace_owner_enrollment import WorkspaceOwnerCompilerError
from tests.test_workspace_project_authoring_grant import project_bindings, verified, GRANT
from tests.test_workspace_member_bindings import principal


def v5():
    policy, doc = project_bindings()
    doc["schema"] = grant.SCHEMA_V5
    for slot in doc["profiles"].values():
        slot.update(project_plan_proposal_publish=None, project_canonical_data_read=None)
    return policy, doc


def gate(policy, doc, action, work=None):
    return grant.workspace_project_authorizers(policy=policy, load_bindings=lambda: doc,
        action=action, work_ref=work)


def test_v4_never_inherits_latest_data_or_plan_proposal_authority():
    policy, doc = project_bindings()
    who = verified(policy, principal(doc))
    assert gate(policy, doc, "publish_project_proposal")[0](who)
    for action, work in [(grant.LATEST_DATA_READ_ACTION,None),(grant.PLAN_PROPOSAL_ACTION,"WS:TEST")]:
        a,b = gate(policy,doc,action,work)
        assert not a(who) and not b(principal(doc)) and a.binding_digest(who) is None


def test_v5_distinct_current_global_data_and_work_scoped_proposal_stamps():
    policy, doc = v5(); who = verified(policy, principal(doc))
    original = grant.legacy_workspace_document(doc,policy)
    slot = doc["profiles"]["member-0"]
    slot["project_canonical_data_read"] = "d" * 64
    slot["project_plan_proposal_publish"] = {"work_ref":"WS:TEST","permission_digest":"e"*64}
    assert grant.legacy_workspace_document(doc,policy) == original
    read,_ = gate(policy,doc,grant.LATEST_DATA_READ_ACTION)
    publish,_ = gate(policy,doc,grant.PLAN_PROPOSAL_ACTION,"WS:TEST")
    assert read(who) and publish(who) and read.binding_digest(who) != publish.binding_digest(who)
    assert not gate(policy,doc,grant.PLAN_PROPOSAL_ACTION,"WS:FOREIGN")[0](who)
    with pytest.raises(ValueError): gate(policy,doc,grant.LATEST_DATA_READ_ACTION,"WS:TEST")
    slot["project_canonical_data_read"] = None
    assert not read(who) and publish(who)
    slot["project_plan_proposal_publish"] = None
    assert not publish(who)


@pytest.mark.parametrize("source", ["read", "create", "sibling", "ccr"])
def test_v5_never_reuses_revision_read_or_write_or_control_grants(source):
    policy,doc = v5(); slot=doc["profiles"]["member-0"]
    if source == "read": digest=slot["binding"]["permission_digest"]
    elif source == "create": digest=GRANT
    elif source == "sibling":
        digest="d"*64;slot["project_plan_proposal_publish"]={"work_ref":"WS:TEST","permission_digest":digest}
    else:
        digest="d"*64;slot["control_room_actions"]["discover"]=digest
    slot["project_canonical_data_read"]=digest
    with pytest.raises(ValueError): grant.validate_project_bindings(doc,policy)


@pytest.mark.parametrize("change", [
    {"project_canonical_data_read":{"permission_digest":"d"*64}},
    {"project_plan_proposal_publish":{"work_ref":"WS:TEST","permission_digest":"e"*64,"revision":"a"*40}},
    {"project_canonical_data_read":"d"*64,"enabled":False},
])
def test_malformed_or_disabled_v5_scope_is_not_a_grant(change):
    policy,doc=v5();doc["profiles"]["member-0"].update(change)
    with pytest.raises(ValueError): grant.validate_project_bindings(doc,policy)


def test_explicit_v5_compile_requires_complete_ten_action_map_and_preserves_read_membership():
    policy,old=project_bindings()
    fields=grant.project_action_fields(grant.SCHEMA_V5)
    receipts={name:dict.fromkeys(fields) for name in old["profiles"]}
    receipts["member-0"][grant.LATEST_DATA_READ_ACTION]=b"explicit latest canonical DATA only"
    receipts["member-0"][grant.PLAN_PROPOSAL_ACTION]={"work_ref":"WS:TEST","receipt":b"explicit draft plan publication only"}
    result=compile_project_action_bindings(policy,old,receipts,schema=grant.SCHEMA_V5)
    assert result["schema"]==grant.SCHEMA_V5
    assert result["profiles"]["member-0"]["binding"]==old["profiles"]["member-0"]["binding"]
    who=verified(policy,principal(result))
    assert gate(policy,result,grant.LATEST_DATA_READ_ACTION)[0](who)
    assert gate(policy,result,grant.PLAN_PROPOSAL_ACTION,"WS:TEST")[0](who)
    assert not gate(policy,result,"publish_project_proposal")[0](who)
    with pytest.raises(WorkspaceOwnerCompilerError): compile_project_action_bindings(policy,old,receipts)
    incomplete=copy.deepcopy(receipts)
    del incomplete["member-0"][grant.LATEST_DATA_READ_ACTION]
    with pytest.raises(WorkspaceOwnerCompilerError): compile_project_action_bindings(policy,old,incomplete,schema=grant.SCHEMA_V5)
