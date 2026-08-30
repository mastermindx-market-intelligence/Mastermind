from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.github_estate_governance import (
    AdministrationFamily,
    AdministrationSpec,
    GitHubRead,
    GitHubResponse,
    GovernanceRefusal,
    assess_github_admin_prerequisites,
    apply_administration_family,
    canonical_digest,
    validate_candidate_credential_denial,
    validate_disposable_private_repository,
    validate_publisher_app_installation,
)


class FakeTransport:
    def __init__(
        self,
        before: dict,
        *,
        after: dict | None = None,
        response: GitHubResponse | None = None,
        before_etag: str = '"before-v1"',
        after_etag: str = '"after-v1"',
    ) -> None:
        self.before = deepcopy(before)
        self.after = deepcopy(after if after is not None else before)
        self.response = response or GitHubResponse(status=200, body={"ok": True})
        self.before_etag = before_etag
        self.after_etag = after_etag
        self.read_count = 0
        self.mutations: list[tuple[str, str, dict, str]] = []

    def read(self, endpoint: str) -> GitHubRead:
        self.read_count += 1
        return GitHubRead(
            body=deepcopy(self.before if self.read_count == 1 else self.after),
            etag=(self.before_etag if self.read_count == 1 else self.after_etag),
        )

    def mutate(
        self,
        method: str,
        endpoint: str,
        payload: dict,
        *,
        if_match: str,
    ) -> GitHubResponse:
        self.mutations.append((method, endpoint, deepcopy(payload), if_match))
        return self.response


class RaisingMutationTransport(FakeTransport):
    def mutate(
        self,
        method: str,
        endpoint: str,
        payload: dict,
        *,
        if_match: str,
    ) -> GitHubResponse:
        self.mutations.append((method, endpoint, deepcopy(payload), if_match))
        raise TimeoutError("response boundary was not observed")


class RaisingReadbackTransport(FakeTransport):
    def read(self, endpoint: str) -> GitHubRead:
        if self.read_count == 1:
            raise TimeoutError("read-back boundary was not observed")
        return super().read(endpoint)


class MalformedResponseTransport(FakeTransport):
    def mutate(self, method, endpoint, payload, *, if_match):
        self.mutations.append((method, endpoint, deepcopy(payload), if_match))
        return {"status": 200}


class NonMappingReadbackTransport(FakeTransport):
    def read(self, endpoint: str) -> GitHubRead:
        if self.read_count == 1:
            self.read_count += 1
            return GitHubRead(body=[], etag=self.after_etag)  # type: ignore[arg-type]
        return super().read(endpoint)


class ConcurrentWriteTransport(FakeTransport):
    """Model a server that atomically rejects the stale If-Match version."""

    def mutate(
        self,
        method: str,
        endpoint: str,
        payload: dict,
        *,
        if_match: str,
    ) -> GitHubResponse:
        self.mutations.append((method, endpoint, deepcopy(payload), if_match))
        assert if_match == self.before_etag
        return GitHubResponse(status=412, body={"message": "stale precondition"})


def _repo_merge_spec(before: dict) -> AdministrationSpec:
    return AdministrationSpec(
        family=AdministrationFamily.REPOSITORY_MERGE_POLICY,
        endpoint="repos/mastermindx-market-intelligence/Mastermind",
        method="PATCH",
        expected_before_sha256=canonical_digest(before),
        payload={
            "allow_merge_commit": False,
            "allow_rebase_merge": False,
            "allow_squash_merge": True,
            "delete_branch_on_merge": True,
        },
        expected_after={
            "allow_merge_commit": False,
            "allow_rebase_merge": False,
            "allow_squash_merge": True,
            "delete_branch_on_merge": True,
        },
    )


def _actions_spec(before: dict) -> AdministrationSpec:
    payload = {
        "default_workflow_permissions": "read",
        "can_approve_pull_request_reviews": False,
    }
    return AdministrationSpec(
        family=AdministrationFamily.ACTIONS_DEFAULT_PERMISSIONS,
        endpoint=(
            "repos/mastermindx-market-intelligence/Mastermind/"
            "actions/permissions/workflow"
        ),
        method="PUT",
        expected_before_sha256=canonical_digest(before),
        payload=payload,
        expected_after=payload,
    )


def _security_spec(before: dict) -> AdministrationSpec:
    payload = {
        "security_and_analysis": {
            "secret_scanning": {"status": "enabled"},
            "secret_scanning_push_protection": {"status": "enabled"},
        }
    }
    return AdministrationSpec(
        family=AdministrationFamily.SECURITY_AND_ANALYSIS,
        endpoint="repos/mastermindx-market-intelligence/Mastermind",
        method="PATCH",
        expected_before_sha256=canonical_digest(before),
        payload=payload,
        expected_after=payload,
    )


def test_administration_family_reads_before_once_mutates_once_and_reads_back_once():
    before = {
        "allow_merge_commit": True,
        "allow_rebase_merge": True,
        "allow_squash_merge": True,
        "delete_branch_on_merge": False,
    }
    after = deepcopy(before)
    after.update(_repo_merge_spec(before).expected_after)
    transport = FakeTransport(before, after=after)

    receipt = apply_administration_family(transport, _repo_merge_spec(before))

    assert receipt["verdict"] == "APPLIED"
    assert receipt["effect"] == "CONFIRMED"
    assert receipt["before_sha256"] == canonical_digest(before)
    assert receipt["after_sha256"] == canonical_digest(after)
    assert transport.read_count == 2
    assert len(transport.mutations) == 1


def test_actions_family_applies_and_reads_back_exact_safe_projection():
    before = {
        "default_workflow_permissions": "write",
        "can_approve_pull_request_reviews": True,
    }
    after = dict(_actions_spec(before).expected_after)
    transport = FakeTransport(before, after=after)

    receipt = apply_administration_family(transport, _actions_spec(before))

    assert receipt["verdict"] == "APPLIED"
    assert receipt["effect"] == "CONFIRMED"
    assert len(transport.mutations) == 1


def test_security_family_allows_only_governance_feature_names_and_nested_readback():
    before = {
        "security_and_analysis": {
            "secret_scanning": {"status": "disabled"},
            "secret_scanning_push_protection": {"status": "disabled"},
            "dependabot_security_updates": {"status": "disabled"},
        }
    }
    after = {
        "security_and_analysis": {
            "secret_scanning": {"status": "enabled"},
            "secret_scanning_push_protection": {"status": "enabled"},
            "dependabot_security_updates": {"status": "disabled"},
            "secret_scanning_validity_checks": {"status": "enabled"},
        }
    }
    transport = FakeTransport(before, after=after)

    receipt = apply_administration_family(transport, _security_spec(before))

    assert receipt["verdict"] == "APPLIED"
    assert receipt["effect"] == "CONFIRMED"
    assert len(transport.mutations) == 1


def test_security_family_is_idempotent_with_additional_server_fields():
    current = {
        "security_and_analysis": {
            "secret_scanning": {"status": "enabled"},
            "secret_scanning_push_protection": {"status": "enabled"},
            "dependabot_security_updates": {"status": "disabled"},
        }
    }
    transport = FakeTransport(current)

    receipt = apply_administration_family(transport, _security_spec(current))

    assert receipt["verdict"] == "ALREADY_CONFIGURED"
    assert receipt["effect"] == "NONE"
    assert transport.mutations == []


def test_security_family_readback_mismatch_is_not_confirmed():
    before = {
        "security_and_analysis": {
            "secret_scanning": {"status": "disabled"},
            "secret_scanning_push_protection": {"status": "disabled"},
        }
    }
    after = {
        "security_and_analysis": {
            "secret_scanning": {"status": "enabled"},
            "secret_scanning_push_protection": {"status": "disabled"},
        }
    }
    transport = FakeTransport(before, after=after)

    receipt = apply_administration_family(transport, _security_spec(before))

    assert receipt["verdict"] == "READBACK_MISMATCH"
    assert receipt["effect"] == "UNKNOWN"
    assert len(transport.mutations) == 1


def test_exact_existing_configuration_is_idempotent_without_mutation():
    current = {
        "allow_merge_commit": False,
        "allow_rebase_merge": False,
        "allow_squash_merge": True,
        "delete_branch_on_merge": True,
    }
    transport = FakeTransport(current)

    receipt = apply_administration_family(transport, _repo_merge_spec(current))

    assert receipt["verdict"] == "ALREADY_CONFIGURED"
    assert receipt["effect"] == "NONE"
    assert transport.read_count == 1
    assert transport.mutations == []


@pytest.mark.parametrize(
    "expected_after",
    [
        {},
        {"allow_squash_merge": True},
        {"unrelated": True},
        {
            "allow_merge_commit": True,
            "allow_rebase_merge": False,
            "allow_squash_merge": True,
            "delete_branch_on_merge": True,
        },
    ],
)
def test_expected_after_must_exactly_equal_the_family_payload(expected_after):
    before = {
        "allow_merge_commit": True,
        "allow_rebase_merge": True,
        "allow_squash_merge": True,
        "delete_branch_on_merge": False,
    }
    original = _repo_merge_spec(before)
    spec = AdministrationSpec(**{**original.__dict__, "expected_after": expected_after})
    transport = FakeTransport(before)

    with pytest.raises(GovernanceRefusal, match="expected after"):
        apply_administration_family(transport, spec)

    assert transport.read_count == 0
    assert transport.mutations == []


def test_changed_before_digest_refuses_without_mutation():
    expected = {
        "allow_merge_commit": True,
        "allow_rebase_merge": True,
        "allow_squash_merge": True,
        "delete_branch_on_merge": False,
    }
    drifted = {**expected, "delete_branch_on_merge": True}
    transport = FakeTransport(drifted)

    with pytest.raises(GovernanceRefusal, match="before digest drifted"):
        apply_administration_family(transport, _repo_merge_spec(expected))

    assert transport.read_count == 1
    assert transport.mutations == []


def test_ambiguous_mutation_reads_back_once_and_never_retries():
    before = {
        "allow_merge_commit": True,
        "allow_rebase_merge": True,
        "allow_squash_merge": True,
        "delete_branch_on_merge": False,
    }
    transport = FakeTransport(
        before,
        after=before,
        response=GitHubResponse(status=503, body=None),
    )

    receipt = apply_administration_family(transport, _repo_merge_spec(before))

    assert receipt["verdict"] == "EFFECT_UNKNOWN"
    assert receipt["effect"] == "UNKNOWN"
    assert receipt["reconciled"] is True
    assert transport.read_count == 2
    assert len(transport.mutations) == 1


def test_ambiguous_mutation_can_be_confirmed_only_by_readback():
    before = {
        "allow_merge_commit": True,
        "allow_rebase_merge": True,
        "allow_squash_merge": True,
        "delete_branch_on_merge": False,
    }
    after = deepcopy(before)
    after.update(_repo_merge_spec(before).expected_after)
    transport = FakeTransport(
        before,
        after=after,
        response=GitHubResponse(status=503, body=None),
    )

    receipt = apply_administration_family(transport, _repo_merge_spec(before))

    assert receipt["verdict"] == "APPLIED_AFTER_RECONCILIATION"
    assert receipt["effect"] == "CONFIRMED"
    assert receipt["reconciled"] is True
    assert len(transport.mutations) == 1


def test_mutation_transport_exception_reconciles_once_and_never_retries():
    before = {
        "allow_merge_commit": True,
        "allow_rebase_merge": True,
        "allow_squash_merge": True,
        "delete_branch_on_merge": False,
    }
    after = deepcopy(before)
    after.update(_repo_merge_spec(before).expected_after)
    transport = RaisingMutationTransport(before, after=after)

    receipt = apply_administration_family(transport, _repo_merge_spec(before))

    assert receipt["verdict"] == "APPLIED_AFTER_RECONCILIATION"
    assert receipt["effect"] == "CONFIRMED"
    assert receipt["reconciled"] is True
    assert transport.read_count == 2
    assert len(transport.mutations) == 1


@pytest.mark.parametrize("status", [200, 503])
def test_readback_failure_after_write_preserves_effect_unknown(status: int):
    before = {
        "allow_merge_commit": True,
        "allow_rebase_merge": True,
        "allow_squash_merge": True,
        "delete_branch_on_merge": False,
    }
    transport = RaisingReadbackTransport(
        before,
        response=GitHubResponse(status=status, body=None),
    )

    receipt = apply_administration_family(transport, _repo_merge_spec(before))

    assert receipt["verdict"] == "EFFECT_UNKNOWN"
    assert receipt["effect"] == "UNKNOWN"
    assert receipt["reconciled"] is True
    assert receipt["mutation_attempts"] == 1
    assert transport.read_count == 1
    assert len(transport.mutations) == 1


def test_malformed_response_after_write_preserves_effect_unknown():
    before = {
        "allow_merge_commit": True,
        "allow_rebase_merge": True,
        "allow_squash_merge": True,
        "delete_branch_on_merge": False,
    }
    transport = MalformedResponseTransport(before)

    receipt = apply_administration_family(transport, _repo_merge_spec(before))

    assert receipt["verdict"] == "EFFECT_UNKNOWN"
    assert receipt["effect"] == "UNKNOWN"
    assert receipt["mutation_attempts"] == 1
    assert len(transport.mutations) == 1


def test_malformed_status_after_write_preserves_effect_unknown():
    before = {
        "allow_merge_commit": True,
        "allow_rebase_merge": True,
        "allow_squash_merge": True,
        "delete_branch_on_merge": False,
    }
    transport = FakeTransport(
        before,
        response=GitHubResponse(status="200", body={}),  # type: ignore[arg-type]
    )

    receipt = apply_administration_family(transport, _repo_merge_spec(before))

    assert receipt["verdict"] == "EFFECT_UNKNOWN"
    assert receipt["effect"] == "UNKNOWN"
    assert len(transport.mutations) == 1


def test_nonmapping_readback_after_write_preserves_effect_unknown():
    before = {
        "allow_merge_commit": True,
        "allow_rebase_merge": True,
        "allow_squash_merge": True,
        "delete_branch_on_merge": False,
    }
    transport = NonMappingReadbackTransport(before)

    receipt = apply_administration_family(transport, _repo_merge_spec(before))

    assert receipt["verdict"] == "EFFECT_UNKNOWN"
    assert receipt["effect"] == "UNKNOWN"
    assert len(transport.mutations) == 1


def test_atomic_if_match_precondition_rejects_concurrent_change_without_readback():
    before = {
        "allow_merge_commit": True,
        "allow_rebase_merge": True,
        "allow_squash_merge": True,
        "delete_branch_on_merge": False,
    }
    transport = ConcurrentWriteTransport(before, before_etag='"baseline-v1"')

    receipt = apply_administration_family(transport, _repo_merge_spec(before))

    assert receipt["verdict"] == "REJECTED"
    assert receipt["effect"] == "NONE"
    assert transport.read_count == 1
    assert transport.mutations == [
        (
            "PATCH",
            "repos/mastermindx-market-intelligence/Mastermind",
            dict(_repo_merge_spec(before).payload),
            '"baseline-v1"',
        )
    ]


def test_missing_server_version_refuses_before_mutation():
    before = {
        "allow_merge_commit": True,
        "allow_rebase_merge": True,
        "allow_squash_merge": True,
        "delete_branch_on_merge": False,
    }
    transport = FakeTransport(before, before_etag="")

    with pytest.raises(GovernanceRefusal, match="server version"):
        apply_administration_family(transport, _repo_merge_spec(before))

    assert transport.mutations == []


@pytest.mark.parametrize("invalid_etag", ["*", "not-an-entity-tag", '"unterminated'])
def test_non_entity_tag_server_version_refuses_before_mutation(invalid_etag: str):
    before = {
        "allow_merge_commit": True,
        "allow_rebase_merge": True,
        "allow_squash_merge": True,
        "delete_branch_on_merge": False,
    }
    transport = FakeTransport(before, before_etag=invalid_etag)

    with pytest.raises(GovernanceRefusal, match="server version"):
        apply_administration_family(transport, _repo_merge_spec(before))

    assert transport.mutations == []


def test_weak_entity_tag_refuses_before_mutation():
    before = {
        "allow_merge_commit": True,
        "allow_rebase_merge": True,
        "allow_squash_merge": True,
        "delete_branch_on_merge": False,
    }
    transport = FakeTransport(before, before_etag='W/"before-v1"')

    with pytest.raises(GovernanceRefusal, match="strong atomic server version"):
        apply_administration_family(transport, _repo_merge_spec(before))

    assert transport.mutations == []


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_definitive_rejection_has_no_readback_or_retry(status: int):
    before = {
        "allow_merge_commit": True,
        "allow_rebase_merge": True,
        "allow_squash_merge": True,
        "delete_branch_on_merge": False,
    }
    transport = FakeTransport(
        before,
        response=GitHubResponse(status=status, body={"message": "refused"}),
    )

    receipt = apply_administration_family(transport, _repo_merge_spec(before))

    assert receipt["verdict"] == (
        "AUTH_REJECTED" if status in {401, 403} else "REJECTED"
    )
    assert receipt["effect"] == "NONE"
    assert transport.read_count == 1
    assert len(transport.mutations) == 1


@pytest.mark.parametrize("key", ["token", "private_key", "client_secret", "password"])
def test_secret_bearing_payload_is_refused_before_any_network_effect(key: str):
    before = {
        "allow_merge_commit": True,
        "allow_rebase_merge": True,
        "allow_squash_merge": True,
        "delete_branch_on_merge": False,
    }
    transport = FakeTransport(before)
    spec = _repo_merge_spec(before)
    spec = AdministrationSpec(
        **{**spec.__dict__, "payload": {**spec.payload, key: "raw-secret"}}
    )

    with pytest.raises(GovernanceRefusal, match="secret-bearing"):
        apply_administration_family(transport, spec)

    assert transport.read_count == 0
    assert transport.mutations == []


def _installed_apps() -> list[dict]:
    return [
        {
            "app_id": 1,
            "app_slug": "chatgpt-codex-connector",
            "repository_selection": "all",
            "permissions": {"contents": "write", "pull_requests": "write"},
        },
        {
            "app_id": 2,
            "app_slug": "linear-code",
            "repository_selection": "all",
            "permissions": {"issues": "write", "metadata": "read"},
        },
    ]


def _publisher_installation() -> dict:
    return {
        "installation_id": 152000001,
        "app_id": 48151623,
        "app_slug": "macro-production-publisher",
        "account_login": "mastermindx-market-intelligence",
        "target_type": "Organization",
        "suspended_at": None,
        "repository_selection": "selected",
        "repositories": ["mastermindx-market-intelligence/macro"],
        "permissions": {"metadata": "read", "contents": "write"},
        "events": [],
        "observed_at": "2026-08-30T04:00:00Z",
        "source_endpoints": [
            "GET /orgs/mastermindx-market-intelligence/installations",
            "GET /user/installations/152000001/repositories",
        ],
    }


def test_admin_prerequisite_census_does_not_promote_oauth_scopes_to_app_authority():
    result = assess_github_admin_prerequisites(
        principal={
            "login": "chriswong6031-creator",
            "principal_type": "oauth_user",
            "organization_role": "admin",
            "oauth_scopes": ["admin:org", "repo", "workflow"],
        },
        capability_probes={
            "organization_audit_log": "SATISFIED",
            "installed_app_inventory": "SATISFIED",
            "app_management": "HELD",
            "app_creation": "HELD",
            "app_installation": "HELD",
            "private_key_custody": "HELD",
        },
        installations=_installed_apps(),
        expected_repository="mastermindx-market-intelligence/macro",
        expected_publisher_app_id=None,
        expected_publisher_installation_id=None,
    )

    assert result["suitable_publisher_app_exists"] is False
    assert result["qualified_app_integration_id"] is None
    assert result["gates"]["organization_audit_log"] == "SATISFIED"
    assert result["gates"]["app_creation"] == "HELD"
    assert result["scope_inferred_from_oauth"] is False
    assert [row["app_slug"] for row in result["installed_apps"]] == [
        "chatgpt-codex-connector",
        "linear-code",
    ]


def test_admin_prerequisite_census_reports_only_a_static_configuration_match():
    publisher = _publisher_installation()
    result = assess_github_admin_prerequisites(
        principal={
            "login": "admin",
            "principal_type": "oauth_user",
            "organization_role": "admin",
            "oauth_scopes": ["admin:org"],
        },
        capability_probes={
            "organization_audit_log": "SATISFIED",
            "installed_app_inventory": "SATISFIED",
            "app_management": "SATISFIED",
            "app_creation": "SATISFIED",
            "app_installation": "SATISFIED",
            "private_key_custody": "SATISFIED",
        },
        installations=[publisher],
        expected_repository="mastermindx-market-intelligence/macro",
        expected_publisher_app_id=48151623,
        expected_publisher_installation_id=152000001,
    )

    assert result["publisher_configuration_matches_policy"] is True
    assert result["configuration_matching_app_integration_id"] == 48151623
    assert result["suitable_publisher_app_exists"] is False
    assert result["qualified_app_integration_id"] is None
    assert result["dynamic_candidate_denial_required"] is True


def test_admin_prerequisite_census_cannot_qualify_an_app_while_gates_are_held():
    result = assess_github_admin_prerequisites(
        principal={
            "login": "admin",
            "principal_type": "oauth_user",
            "organization_role": "admin",
            "oauth_scopes": ["admin:org"],
        },
        capability_probes={
            "organization_audit_log": "HELD",
            "installed_app_inventory": "HELD",
            "app_management": "HELD",
            "app_creation": "HELD",
            "app_installation": "HELD",
            "private_key_custody": "HELD",
        },
        installations=[_publisher_installation()],
        expected_repository="mastermindx-market-intelligence/macro",
        expected_publisher_app_id=48151623,
        expected_publisher_installation_id=152000001,
    )

    assert result["publisher_configuration_matches_policy"] is False
    assert result["suitable_publisher_app_exists"] is False
    assert result["qualified_app_integration_id"] is None


def test_admin_prerequisite_census_refuses_missing_or_claimed_probe_results():
    probes = {
        "organization_audit_log": "SATISFIED",
        "installed_app_inventory": "SATISFIED",
        "app_management": "CLAIMED_FROM_SCOPE",
        "app_creation": "HELD",
        "app_installation": "HELD",
        "private_key_custody": "HELD",
    }
    with pytest.raises(GovernanceRefusal, match="capability probe"):
        assess_github_admin_prerequisites(
            principal={
                "login": "admin",
                "principal_type": "oauth_user",
                "organization_role": "admin",
                "oauth_scopes": ["admin:org"],
            },
            capability_probes=probes,
            installations=[],
            expected_repository="mastermindx-market-intelligence/macro",
            expected_publisher_app_id=None,
            expected_publisher_installation_id=None,
        )


def test_candidate_credential_denial_requires_external_custody_and_zero_projection():
    receipt = validate_candidate_credential_denial(
        {
            "custody_kind": "operator_keychain",
            "repository_actions_secret_present": False,
            "organization_actions_secret_present": False,
            "environment_actions_secret_present": False,
            "candidate_checkout_material_present": False,
            "candidate_installation_token_minted": False,
            "credential_material_observed": False,
        }
    )

    assert receipt["verdict"] == "CLAIM_SHAPE_VALIDATED"
    assert receipt["candidate_credential_reachability"] == "UNPROVEN"
    assert receipt["dynamic_candidate_canary_required"] is True


@pytest.mark.parametrize(
    "mutation",
    [
        lambda evidence: evidence.update(custody_kind="repository_actions_secret"),
        lambda evidence: evidence.update(repository_actions_secret_present=True),
        lambda evidence: evidence.update(candidate_checkout_material_present=True),
        lambda evidence: evidence.update(candidate_installation_token_minted=True),
        lambda evidence: evidence.update(credential_material_observed=True),
    ],
)
def test_candidate_credential_denial_refuses_any_candidate_projection(mutation):
    evidence = {
        "custody_kind": "operator_keychain",
        "repository_actions_secret_present": False,
        "organization_actions_secret_present": False,
        "environment_actions_secret_present": False,
        "candidate_checkout_material_present": False,
        "candidate_installation_token_minted": False,
        "credential_material_observed": False,
    }
    mutation(evidence)

    with pytest.raises(GovernanceRefusal):
        validate_candidate_credential_denial(evidence)


def test_publisher_app_must_be_repo_selected_and_exactly_least_privileged():
    receipt = validate_publisher_app_installation(
        _publisher_installation(),
        expected_repository="mastermindx-market-intelligence/macro",
        expected_app_id=48151623,
        expected_installation_id=152000001,
    )

    assert receipt["verdict"] == "CONFIGURATION_MATCH"
    assert receipt["app_integration_id"] == 48151623
    assert receipt["installation_id"] == 152000001
    assert receipt["dynamic_candidate_denial_required"] is True


def test_publisher_app_refuses_an_unbound_arbitrary_positive_app_id():
    app = _publisher_installation()
    app["app_id"] = 99999999

    with pytest.raises(GovernanceRefusal, match="Integration ID"):
        validate_publisher_app_installation(
            app,
            expected_repository="mastermindx-market-intelligence/macro",
            expected_app_id=48151623,
            expected_installation_id=152000001,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda app: app.update(repository_selection="all"),
        lambda app: app["repositories"].append("mastermindx-market-intelligence/Mastermind"),
        lambda app: app["permissions"].update(workflows="write"),
        lambda app: app["permissions"].update(contents="read"),
        lambda app: app["events"].append("push"),
    ],
)
def test_publisher_app_refuses_broad_or_incomplete_authority(mutation):
    app = _publisher_installation()
    mutation(app)

    with pytest.raises(GovernanceRefusal):
        validate_publisher_app_installation(
            app,
            expected_repository="mastermindx-market-intelligence/macro",
            expected_app_id=48151623,
            expected_installation_id=152000001,
        )


def test_disposable_private_repository_canary_requires_private_security_and_read_actions():
    receipt = validate_disposable_private_repository(
        repository={"private": True, "visibility": "private", "archived": False},
        security_and_analysis={
            "secret_scanning": {"status": "enabled"},
            "secret_scanning_push_protection": {"status": "enabled"},
        },
        actions_permissions={
            "default_workflow_permissions": "read",
            "can_approve_pull_request_reviews": False,
        },
    )

    assert receipt == {
        "verdict": "PASS",
        "private": True,
        "secret_scanning": "enabled",
        "push_protection": "enabled",
        "actions_default": "read",
        "actions_can_approve_pull_requests": False,
    }


@pytest.mark.parametrize(
    ("repository", "security", "actions"),
    [
        (
            {"private": False, "visibility": "public", "archived": False},
            {
                "secret_scanning": {"status": "enabled"},
                "secret_scanning_push_protection": {"status": "enabled"},
            },
            {
                "default_workflow_permissions": "read",
                "can_approve_pull_request_reviews": False,
            },
        ),
        (
            {"private": True, "visibility": "private", "archived": False},
            {"secret_scanning": {"status": "disabled"}},
            {
                "default_workflow_permissions": "read",
                "can_approve_pull_request_reviews": False,
            },
        ),
        (
            {"private": True, "visibility": "private", "archived": False},
            {
                "secret_scanning": {"status": "enabled"},
                "secret_scanning_push_protection": {"status": "enabled"},
            },
            {
                "default_workflow_permissions": "write",
                "can_approve_pull_request_reviews": True,
            },
        ),
    ],
)
def test_disposable_private_repository_canary_fails_closed(repository, security, actions):
    with pytest.raises(GovernanceRefusal):
        validate_disposable_private_repository(
            repository=repository,
            security_and_analysis=security,
            actions_permissions=actions,
        )
