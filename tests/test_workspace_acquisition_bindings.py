"""Pure existing-owner permission reload checks; no installed enrollments."""
import copy
import hashlib

import pytest

from integrations.mastermind_workspace_app.contract import (
    BINDINGS_SCHEMA, RESOURCE, SCOPE, validate_workspace_bindings,
    workspace_authorizers, permission_stamp,
)
from tests.test_workspace_read_app import _workspace_policy


def fixture():
    policy = _workspace_policy()
    binding = {"policy_id": policy.policy_id, "issuer_digest": hashlib.sha256(policy.issuer.encode()).hexdigest(),
        "subject_digest": policy.allowed_subject_digests[0], "client_ref": "a" * 64,
        "resource": RESOURCE, "scopes": [SCOPE], "permission_digest": "b" * 64}
    return policy, {"schema": BINDINGS_SCHEMA, "profiles": {
        "web": {"enabled": True, "binding": binding}, "mac": {"enabled": False, "binding": None}}}


def test_reload_enabled_and_exact_binding_fields():
    policy, source = fixture()
    _, authorize = workspace_authorizers(policy=policy, load_bindings=lambda: source)
    principal = {k:v for k,v in source["profiles"]["web"]["binding"].items() if k != "permission_digest"}
    assert authorize(principal)
    for key in principal:
        changed = dict(principal, **{key: [] if key == "scopes" else "wrong"})
        assert not authorize(changed)
    stamp = permission_stamp(authorize, principal)
    source["profiles"]["web"]["binding"]["permission_digest"] = "c" * 64
    assert authorize(principal) and permission_stamp(authorize, principal) != stamp
    source["profiles"]["web"]["enabled"] = False
    assert not authorize(principal)


@pytest.mark.parametrize("mutation", ["extra", "null_enabled", "duplicate_client", "bad_digest", "wrong_resource", "missing_slot", "content_scope"])
def test_closed_bindings_cannot_inherit_or_invent_permissions(mutation):
    policy, source = fixture()
    if mutation == "extra": source["extra"] = True
    if mutation == "null_enabled": source["profiles"]["mac"]["enabled"] = True
    if mutation == "duplicate_client": source["profiles"]["mac"] = copy.deepcopy(source["profiles"]["web"])
    if mutation == "bad_digest": source["profiles"]["web"]["binding"]["permission_digest"] = "receipt"
    if mutation == "wrong_resource": source["profiles"]["web"]["binding"]["resource"] += "/foreign"
    if mutation == "missing_slot": del source["profiles"]["mac"]
    if mutation == "content_scope": source["profiles"]["web"]["binding"]["scopes"] = ["mastermind.content.read"]
    with pytest.raises(ValueError): validate_workspace_bindings(source, policy)


def test_two_distinct_clients_keep_independent_revocation():
    policy, source = fixture()
    source["profiles"]["mac"] = copy.deepcopy(source["profiles"]["web"])
    source["profiles"]["mac"]["binding"]["client_ref"] = "c" * 64
    _, authorize = workspace_authorizers(policy=policy, load_bindings=lambda: source)
    def principal(slot): return {k:v for k,v in source["profiles"][slot]["binding"].items() if k != "permission_digest"}
    assert authorize(principal("web")) and authorize(principal("mac"))
    source["profiles"]["web"]["enabled"] = False
    assert not authorize(principal("web")) and authorize(principal("mac"))


@pytest.mark.parametrize("value", [None, "", "A" * 64, 17, "a" * 63])
def test_configured_stamp_requires_closed_digest(value):
    gate = lambda principal: True
    gate.binding_digest = lambda principal: value
    with pytest.raises(ValueError, match="access_denied"):
        permission_stamp(gate, {})


def test_configured_stamp_loader_exception_is_denial():
    gate = lambda principal: True
    def unavailable(principal):
        raise RuntimeError("fixture source unavailable")
    gate.binding_digest = unavailable
    with pytest.raises(ValueError, match="access_denied"):
        permission_stamp(gate, {})
