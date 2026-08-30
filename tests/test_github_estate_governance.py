from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.github_estate_governance import (
    AdministrationFamily,
    AdministrationSpec,
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
    ) -> None:
        self.before = deepcopy(before)
        self.after = deepcopy(after if after is not None else before)
        self.response = response or GitHubResponse(status=200, body={"ok": True})
        self.read_count = 0
        self.mutations: list[tuple[str, str, dict]] = []

    def read(self, endpoint: str) -> dict:
        self.read_count += 1
        return deepcopy(self.before if self.read_count == 1 else self.after)

    def mutate(self, method: str, endpoint: str, payload: dict) -> GitHubResponse:
        self.mutations.append((method, endpoint, deepcopy(payload)))
        return self.response


class RaisingMutationTransport(FakeTransport):
    def mutate(self, method: str, endpoint: str, payload: dict) -> GitHubResponse:
        self.mutations.append((method, endpoint, deepcopy(payload)))
        raise TimeoutError("response boundary was not observed")


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


def test_admin_prerequisite_census_qualifies_one_exact_publisher_app():
    publisher = {
        "app_id": 48151623,
        "app_slug": "macro-production-publisher",
        "repository_selection": "selected",
        "repositories": ["mastermindx-market-intelligence/macro"],
        "permissions": {"metadata": "read", "contents": "write"},
        "events": [],
    }
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
    )

    assert result["suitable_publisher_app_exists"] is True
    assert result["qualified_app_integration_id"] == 48151623


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

    assert receipt["verdict"] == "PASS"
    assert receipt["candidate_credential_reachability"] == "DENIED"


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
        {
            "app_id": 48151623,
            "app_slug": "macro-production-publisher",
            "repository_selection": "selected",
            "repositories": ["mastermindx-market-intelligence/macro"],
            "permissions": {"metadata": "read", "contents": "write"},
            "events": [],
        },
        expected_repository="mastermindx-market-intelligence/macro",
    )

    assert receipt["verdict"] == "PASS"
    assert receipt["app_integration_id"] == 48151623
    assert receipt["credential_material_observed"] is False


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
    app = {
        "app_id": 48151623,
        "app_slug": "macro-production-publisher",
        "repository_selection": "selected",
        "repositories": ["mastermindx-market-intelligence/macro"],
        "permissions": {"metadata": "read", "contents": "write"},
        "events": [],
    }
    mutation(app)

    with pytest.raises(GovernanceRefusal):
        validate_publisher_app_installation(
            app,
            expected_repository="mastermindx-market-intelligence/macro",
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
