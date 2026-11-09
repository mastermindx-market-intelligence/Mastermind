"""Draft candidate identity is stable; authored metadata and actual auth stay owned."""
import copy
import json
from pathlib import Path

import pytest

from integrations.mastermind_workspace_app.project_proposal_request import REQUEST_SCHEMA, build_proposal_request, profile_digest
from tests.test_workspace_project_authoring_grant import project_bindings, verified
from tests.test_workspace_member_bindings import principal


def fixture():
    policy, bindings = project_bindings()
    who = verified(policy, principal(bindings))
    source = json.loads((Path(__file__).parent / "fixtures/project-authoring-proposal.json").read_text())
    profile = {k: v for k, v in source["request"]["record"].items() if k not in {"key", "objective", "status"}}
    request = {"schema": REQUEST_SCHEMA, "request_id": "synthetic-original-001", "goal": "  Literal goal\n保留原文  ",
               "expected_macro_sha": "a" * 40, "profile_sha256": profile_digest(profile)}
    return policy, bindings, who, profile, request


def test_goal_is_verbatim_and_profile_is_explicit_detached_authored_input():
    _, _, who, profile, request = fixture()
    before = copy.deepcopy((profile, request))
    output = build_proposal_request(request, principal=who, authored_profile=profile)
    assert output["record"]["objective"] == request["goal"] and output["record"]["status"] == "proposed"
    assert output["record"]["owner"] == profile["owner"] and output["record"]["program"] == profile["program"]
    assert (profile, request) == before
    profile["waves"][0]["title"] = "Changed by caller"
    assert output["record"]["waves"][0]["title"] != "Changed by caller"


def test_same_original_id_does_not_gain_a_second_candidate_when_goal_or_source_changes():
    _, _, who, profile, request = fixture()
    first = build_proposal_request(request, principal=who, authored_profile=profile)
    second = build_proposal_request({**request, "goal": "Edited goal", "expected_macro_sha": "b" * 40},
                                    principal=who, authored_profile=profile)
    assert first["record"]["key"] == second["record"]["key"]
    assert first != second  # The real publisher must conflict/reconcile their differing fingerprints.


def test_different_authenticated_members_have_independent_candidate_identity():
    policy, bindings, who, profile, request = fixture()
    other = verified(policy, principal(bindings, "member-1"))
    assert build_proposal_request(request, principal=who, authored_profile=profile)["record"]["key"] != \
        build_proposal_request(request, principal=other, authored_profile=profile)["record"]["key"]


@pytest.mark.parametrize("extra", ["owner", "path", "provider", "grant", "runtime_root_id"])
def test_public_goal_request_cannot_supply_owner_path_provider_grant_or_root(extra):
    _, _, who, profile, request = fixture()
    with pytest.raises(ValueError):
        build_proposal_request({**request, extra: "client-asserted"}, principal=who, authored_profile=profile)


def test_changed_profile_and_caller_principal_dict_do_not_become_owned_source():
    _, bindings, who, profile, request = fixture()
    profile["owner"] = "Different source owner"
    with pytest.raises(ValueError, match="source_changed"):
        build_proposal_request(request, principal=who, authored_profile=profile)
    _, _, _, profile, request = fixture()
    with pytest.raises(ValueError):
        build_proposal_request(request, principal=principal(bindings), authored_profile=profile)
