"""Real verified-principal address law; no publication/Job/host effects."""
import hashlib

import pytest

from common.executive_workspace_contract import canonical
from integrations.mastermind_workspace_app.project_proposal_request import (
    creation_work_ref, build_proposal_request,
)
from integrations.mastermind_workspace_app.source_operation_principal import source_principal_frame
from tests.test_workspace_project_proposal_request import fixture
from tests.test_workspace_project_authoring_grant import verified
from tests.test_workspace_member_bindings import principal


def test_original_address_matches_existing_compiler_identity_exactly():
    _, _, who, profile, request = fixture()
    expected = hashlib.sha256(canonical({"principal": source_principal_frame(who),
                                       "request_id": request["request_id"]})).hexdigest()
    address = creation_work_ref(request["request_id"], principal=who)
    assert address == "WS:PROJECT-" + expected[:32].upper()
    assert address[3:] == build_proposal_request(request, principal=who, authored_profile=profile)["record"]["key"]


def test_address_needs_no_goal_profile_source_refresh_or_new_request():
    _, _, who, profile, request = fixture()
    before = creation_work_ref(request["request_id"], principal=who)
    changed = {**request, "goal": "A changed unsent draft", "expected_macro_sha": "e" * 40}
    assert build_proposal_request(changed, principal=who, authored_profile=profile)["record"]["key"] == before[3:]
    assert creation_work_ref(request["request_id"], principal=who) == before


def test_other_verified_principal_cannot_lookup_the_original_project():
    policy, bindings, who, _, request = fixture()
    other = verified(policy, principal(bindings, "member-1"))
    assert creation_work_ref(request["request_id"], principal=other) != creation_work_ref(request["request_id"], principal=who)


def test_unverified_principal_dto_cannot_derive_the_authenticated_address():
    _, bindings, _, _, request = fixture()
    with pytest.raises(ValueError):
        creation_work_ref(request["request_id"], principal=principal(bindings))


@pytest.mark.parametrize("request_id", [None, "", "bad/path", "x\n", "a" * 129])
def test_invalid_original_key_is_refused(request_id):
    _, _, who, _, _ = fixture()
    with pytest.raises(ValueError):
        creation_work_ref(request_id, principal=who)
