from __future__ import annotations

from copy import deepcopy
from enum import Enum

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
        before_etag: str = '"before-v1"',
    ) -> None:
        self.before = deepcopy(before)
        self.before_etag = before_etag
        self.read_count = 0
        self.mutations: list[tuple[str, str, dict, str]] = []

    def read(self, endpoint: str) -> GitHubRead:
        self.read_count += 1
        return GitHubRead(body=deepcopy(self.before), etag=self.before_etag)

    def mutate(
        self,
        method: str,
        endpoint: str,
        payload: dict,
        *,
        if_match: str,
    ) -> GitHubResponse:
        self.mutations.append((method, endpoint, deepcopy(payload), if_match))
        return GitHubResponse(status=200, body={"ok": True})


def _repo_merge_spec(before: dict) -> AdministrationSpec:
    payload = {
        "allow_merge_commit": False,
        "allow_rebase_merge": False,
        "allow_squash_merge": True,
        "delete_branch_on_merge": True,
    }
    return AdministrationSpec(
        family=AdministrationFamily.REPOSITORY_MERGE_POLICY,
        endpoint="repos/mastermindx-market-intelligence/Mastermind",
        method="PATCH",
        expected_before_sha256=canonical_digest(before),
        payload=payload,
        expected_after=payload,
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


def _drift_cases():
    repo = {
        "allow_merge_commit": True,
        "allow_rebase_merge": True,
        "allow_squash_merge": True,
        "delete_branch_on_merge": False,
    }
    actions = {
        "default_workflow_permissions": "write",
        "can_approve_pull_request_reviews": True,
    }
    security = {
        "security_and_analysis": {
            "secret_scanning": {"status": "disabled"},
            "secret_scanning_push_protection": {"status": "disabled"},
        }
    }
    return [
        pytest.param(repo, _repo_merge_spec(repo), id="repository-merge-policy"),
        pytest.param(actions, _actions_spec(actions), id="actions-default-permissions"),
        pytest.param(security, _security_spec(security), id="security-and-analysis"),
    ]


def _configured_cases():
    repo = {
        "allow_merge_commit": False,
        "allow_rebase_merge": False,
        "allow_squash_merge": True,
        "delete_branch_on_merge": True,
    }
    actions = {
        "default_workflow_permissions": "read",
        "can_approve_pull_request_reviews": False,
    }
    security = {
        "security_and_analysis": {
            "secret_scanning": {"status": "enabled"},
            "secret_scanning_push_protection": {"status": "enabled"},
            "dependabot_security_updates": {"status": "disabled"},
        }
    }
    return [
        pytest.param(repo, _repo_merge_spec(repo), id="repository-merge-policy"),
        pytest.param(actions, _actions_spec(actions), id="actions-default-permissions"),
        pytest.param(security, _security_spec(security), id="security-and-analysis"),
    ]


@pytest.mark.parametrize(("before", "spec"), _drift_cases())
def test_drifted_current_family_refuses_unsupported_conditional_write_before_mutation(
    before: dict,
    spec: AdministrationSpec,
):
    transport = FakeTransport(before, before_etag='"strong-v1"')

    with pytest.raises(
        GovernanceRefusal,
        match="UNSAFE_CONDITIONAL_WRITE_UNSUPPORTED",
    ):
        apply_administration_family(transport, spec)

    assert transport.read_count == 1
    assert transport.mutations == []


@pytest.mark.parametrize(("before", "spec"), _drift_cases())
def test_weak_etag_drift_refuses_for_unsupported_method_not_weak_syntax(
    before: dict,
    spec: AdministrationSpec,
):
    transport = FakeTransport(before, before_etag='W/"weak-v1"')

    with pytest.raises(
        GovernanceRefusal,
        match="UNSAFE_CONDITIONAL_WRITE_UNSUPPORTED",
    ) as exc:
        apply_administration_family(transport, spec)

    assert "strong atomic server version" not in str(exc.value)
    assert transport.read_count == 1
    assert transport.mutations == []


@pytest.mark.parametrize(("current", "spec"), _configured_cases())
def test_exact_existing_configuration_is_truthful_zero_write_assessment(
    current: dict,
    spec: AdministrationSpec,
):
    transport = FakeTransport(current, before_etag='W/"assessment-v1"')

    receipt = apply_administration_family(transport, spec)

    assert receipt["schema"] == "mastermind.github_estate_administration_receipt.v1"
    assert receipt["family"] == spec.family.value
    assert receipt["endpoint"] == spec.endpoint
    assert receipt["verdict"] == "ALREADY_CONFIGURED"
    assert receipt["effect"] == "NONE"
    assert receipt["mutation_attempts"] == 0
    assert "mutation_precondition" not in receipt
    assert receipt["before_sha256"] == canonical_digest(current)
    assert transport.read_count == 1
    assert transport.mutations == []


@pytest.mark.parametrize("invalid_etag", ["", "*", "not-an-entity-tag", '"unterminated'])
def test_invalid_server_entity_tag_refuses_before_assessment(invalid_etag: str):
    current = {
        "allow_merge_commit": False,
        "allow_rebase_merge": False,
        "allow_squash_merge": True,
        "delete_branch_on_merge": True,
    }
    spec = _repo_merge_spec(current)
    transport = FakeTransport(current, before_etag=invalid_etag)

    with pytest.raises(GovernanceRefusal, match="server entity tag"):
        apply_administration_family(transport, spec)

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


@pytest.mark.parametrize(
    "payload",
    [
        {
            "allow_merge_commit": True,
            "allow_rebase_merge": False,
            "allow_squash_merge": True,
            "delete_branch_on_merge": True,
        },
        {
            "allow_merge_commit": False,
            "allow_rebase_merge": False,
            "allow_squash_merge": False,
            "delete_branch_on_merge": True,
        },
        {
            "allow_merge_commit": False,
            "allow_rebase_merge": False,
            "allow_squash_merge": True,
            "delete_branch_on_merge": 1,
        },
    ],
)
def test_repository_merge_policy_contract_cannot_widen_or_malform(payload):
    before = {
        "allow_merge_commit": True,
        "allow_rebase_merge": True,
        "allow_squash_merge": True,
        "delete_branch_on_merge": False,
    }
    original = _repo_merge_spec(before)
    spec = AdministrationSpec(
        **{**original.__dict__, "payload": payload, "expected_after": payload}
    )
    transport = FakeTransport(before)

    with pytest.raises(GovernanceRefusal):
        apply_administration_family(transport, spec)

    assert transport.read_count == 0
    assert transport.mutations == []


@pytest.mark.parametrize(
    "payload",
    [
        {
            "default_workflow_permissions": "write",
            "can_approve_pull_request_reviews": False,
        },
        {
            "default_workflow_permissions": "read",
            "can_approve_pull_request_reviews": True,
        },
    ],
)
def test_actions_permission_contract_can_only_narrow(payload):
    before = {
        "default_workflow_permissions": "write",
        "can_approve_pull_request_reviews": True,
    }
    original = _actions_spec(before)
    spec = AdministrationSpec(
        **{**original.__dict__, "payload": payload, "expected_after": payload}
    )
    transport = FakeTransport(before)

    with pytest.raises(GovernanceRefusal, match="may only be narrowed"):
        apply_administration_family(transport, spec)

    assert transport.read_count == 0
    assert transport.mutations == []


@pytest.mark.parametrize(
    "security",
    [
        {},
        {"dependabot_security_updates": {"status": "enabled"}},
        {"secret_scanning": {"status": "disabled"}},
        {"secret_scanning": {"status": "enabled"}, "extra": {"status": "enabled"}},
    ],
)
def test_security_family_allows_only_safe_enablement_projection(security):
    before = {"security_and_analysis": {}}
    payload = {"security_and_analysis": security}
    original = _security_spec(before)
    spec = AdministrationSpec(
        **{**original.__dict__, "payload": payload, "expected_after": payload}
    )
    transport = FakeTransport(before)

    with pytest.raises(GovernanceRefusal):
        apply_administration_family(transport, spec)

    assert transport.read_count == 0
    assert transport.mutations == []


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
    payload = {**spec.payload, key: "raw-secret"}
    spec = AdministrationSpec(
        **{**spec.__dict__, "payload": payload, "expected_after": payload}
    )

    with pytest.raises(GovernanceRefusal, match="secret-bearing"):
        apply_administration_family(transport, spec)

    assert transport.read_count == 0
    assert transport.mutations == []


def _capability_probes(value: str = "SATISFIED") -> dict[str, str]:
    return {
        "organization_audit_log": value,
        "installed_app_inventory": value,
        "app_management": value,
        "app_creation": value,
        "app_installation": value,
        "private_key_custody": value,
    }


def _principal() -> dict:
    return {
        "login": "admin",
        "principal_type": "oauth_user",
        "organization_role": "admin",
        "oauth_scopes": ["admin:org"],
    }


def _installed_apps() -> list[dict]:
    return [
        {
            "app_id": 1,
            "app_slug": "chatgpt-codex-connector",
            "repository_selection": "all",
            "permissions": {
                "contents": "write",
                "pull_requests": "write",
                "secret_scanning_alerts": "read",
            },
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


def _assess(installations: list[dict], *, probes: dict[str, str] | None = None):
    return assess_github_admin_prerequisites(
        principal=_principal(),
        capability_probes=probes or _capability_probes(),
        installations=installations,
        expected_repository="mastermindx-market-intelligence/macro",
        expected_publisher_app_id=None,
        expected_publisher_installation_id=None,
    )


def test_admin_census_accepts_public_secret_scanning_permission_metadata():
    result = _assess(_installed_apps())

    first = result["installed_apps"][0]
    assert first["permissions"] == {
        "contents": "write",
        "pull_requests": "write",
        "secret_scanning_alerts": "read",
    }
    assert result["suitable_publisher_app_exists"] is False
    assert result["scope_inferred_from_oauth"] is False


@pytest.mark.parametrize(
    "permissions",
    [
        None,
        [],
        {"contents": {"access": "write"}},
        {"contents": "admin"},
        {"contents": "ghp_not_metadata"},
        {"": "read"},
        {"Content": "read"},
        {"contents/write": "read"},
        {1: "read"},
        {"client_secret": "read"},
        {"secret_scanning_alerts": {"access": "read"}},
    ],
)
def test_admin_census_refuses_malformed_or_secret_bearing_permission_metadata(
    permissions,
):
    app = _installed_apps()[0]
    app["permissions"] = permissions

    with pytest.raises(GovernanceRefusal, match="permission|secret-bearing"):
        _assess([app])


@pytest.mark.parametrize("field", ["token", "client_secret", "private_key"])
def test_public_permission_exception_does_not_weaken_other_installation_secret_checks(
    field: str,
):
    app = _installed_apps()[0]
    app[field] = "raw-secret"

    with pytest.raises(GovernanceRefusal, match="secret-bearing field"):
        _assess([app])


def test_admin_prerequisite_census_does_not_promote_oauth_scopes_to_app_authority():
    probes = _capability_probes()
    probes.update(
        {
            "app_management": "HELD",
            "app_creation": "HELD",
            "app_installation": "HELD",
            "private_key_custody": "HELD",
        }
    )
    result = assess_github_admin_prerequisites(
        principal={
            "login": "chriswong6031-creator",
            "principal_type": "oauth_user",
            "organization_role": "admin",
            "oauth_scopes": ["admin:org", "repo", "workflow"],
        },
        capability_probes=probes,
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
        principal=_principal(),
        capability_probes=_capability_probes(),
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
        principal=_principal(),
        capability_probes=_capability_probes("HELD"),
        installations=[_publisher_installation()],
        expected_repository="mastermindx-market-intelligence/macro",
        expected_publisher_app_id=48151623,
        expected_publisher_installation_id=152000001,
    )

    assert result["publisher_configuration_matches_policy"] is False
    assert result["suitable_publisher_app_exists"] is False
    assert result["qualified_app_integration_id"] is None


def test_admin_prerequisite_census_refuses_missing_or_claimed_probe_results():
    probes = _capability_probes()
    probes["app_management"] = "CLAIMED_FROM_SCOPE"

    with pytest.raises(GovernanceRefusal, match="capability probe"):
        _assess([], probes=probes)


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
    assert receipt["permissions"] == {"contents": "write", "metadata": "read"}
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
        lambda app: app["repositories"].append(
            "mastermindx-market-intelligence/Mastermind"
        ),
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


def test_publisher_app_permission_metadata_uses_same_narrow_validator():
    app = _publisher_installation()
    app["permissions"] = {"contents": {"access": "write"}, "metadata": "read"}

    with pytest.raises(GovernanceRefusal, match="permission"):
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
def test_disposable_private_repository_canary_fails_closed(
    repository,
    security,
    actions,
):
    with pytest.raises(GovernanceRefusal):
        validate_disposable_private_repository(
            repository=repository,
            security_and_analysis=security,
            actions_permissions=actions,
        )


class _ForeignAdministrationFamily(str, Enum):
    REPOSITORY_MERGE_POLICY = "repository_merge_policy"
    ACTIONS_DEFAULT_PERMISSIONS = "actions_default_permissions"
    SECURITY_AND_ANALYSIS = "security_and_analysis"


def _spec_with_family(spec: AdministrationSpec, family: object) -> AdministrationSpec:
    return AdministrationSpec(**{**spec.__dict__, "family": family})  # type: ignore[arg-type]


def _family_lookalike_cases():
    configured = _configured_cases()
    by_family = {
        AdministrationFamily.REPOSITORY_MERGE_POLICY: configured[0].values,
        AdministrationFamily.ACTIONS_DEFAULT_PERMISSIONS: configured[1].values,
        AdministrationFamily.SECURITY_AND_ANALYSIS: configured[2].values,
    }
    foreign = {
        AdministrationFamily.REPOSITORY_MERGE_POLICY: (
            _ForeignAdministrationFamily.REPOSITORY_MERGE_POLICY
        ),
        AdministrationFamily.ACTIONS_DEFAULT_PERMISSIONS: (
            _ForeignAdministrationFamily.ACTIONS_DEFAULT_PERMISSIONS
        ),
        AdministrationFamily.SECURITY_AND_ANALYSIS: (
            _ForeignAdministrationFamily.SECURITY_AND_ANALYSIS
        ),
    }
    cases = []
    for family, (current, spec) in by_family.items():
        cases.append(
            pytest.param(
                current,
                _spec_with_family(spec, family.value),
                id=f"plain-string-{family.value}",
            )
        )
        cases.append(
            pytest.param(
                current,
                _spec_with_family(spec, foreign[family]),
                id=f"foreign-enum-{family.value}",
            )
        )
    return cases


@pytest.mark.parametrize(("current", "spec"), _family_lookalike_cases())
def test_family_lookalikes_refuse_before_transport(
    current: dict,
    spec: AdministrationSpec,
):
    transport = FakeTransport(current)

    with pytest.raises(
        GovernanceRefusal,
        match="AdministrationFamily",
    ):
        apply_administration_family(transport, spec)

    assert transport.read_count == 0
    assert transport.mutations == []


@pytest.mark.parametrize(
    "invalid_family",
    [
        None,
        True,
        1,
        1.5,
        [],
        {},
        "",
        "not-a-family",
        b"bytes",
    ],
)
def test_invalid_family_values_are_typed_refusals_before_transport(invalid_family):
    current, spec = _configured_cases()[0].values
    transport = FakeTransport(current)

    with pytest.raises(
        GovernanceRefusal,
        match="AdministrationFamily",
    ):
        apply_administration_family(
            transport,
            _spec_with_family(spec, invalid_family),
        )

    assert transport.read_count == 0
    assert transport.mutations == []


def _unsafe_family_cases():
    repo_before, repo_spec = _drift_cases()[0].values
    repo_payload = {
        **repo_spec.payload,
        "allow_merge_commit": True,
    }
    actions_before, actions_spec = _drift_cases()[1].values
    actions_payload = {
        **actions_spec.payload,
        "default_workflow_permissions": "write",
    }
    security_before, security_spec = _drift_cases()[2].values
    security_payload = {
        "security_and_analysis": {
            "dependabot_security_updates": {"status": "enabled"},
        }
    }
    return [
        pytest.param(
            repo_before,
            AdministrationSpec(
                **{
                    **repo_spec.__dict__,
                    "payload": repo_payload,
                    "expected_after": repo_payload,
                }
            ),
            id="repository-merge-policy",
        ),
        pytest.param(
            actions_before,
            AdministrationSpec(
                **{
                    **actions_spec.__dict__,
                    "payload": actions_payload,
                    "expected_after": actions_payload,
                }
            ),
            id="actions-default-permissions",
        ),
        pytest.param(
            security_before,
            AdministrationSpec(
                **{
                    **security_spec.__dict__,
                    "payload": security_payload,
                    "expected_after": security_payload,
                }
            ),
            id="security-and-analysis",
        ),
    ]


@pytest.mark.parametrize(("before", "spec"), _unsafe_family_cases())
def test_real_family_values_still_enforce_family_specific_restrictions(
    before: dict,
    spec: AdministrationSpec,
):
    transport = FakeTransport(before)

    with pytest.raises(GovernanceRefusal):
        apply_administration_family(transport, spec)

    assert transport.read_count == 0
    assert transport.mutations == []


@pytest.mark.parametrize(("current", "spec"), _configured_cases())
def test_real_family_values_remain_useful_zero_write_assessments(
    current: dict,
    spec: AdministrationSpec,
):
    transport = FakeTransport(current)

    receipt = apply_administration_family(transport, spec)

    assert receipt["verdict"] == "ALREADY_CONFIGURED"
    assert receipt["effect"] == "NONE"
    assert receipt["mutation_attempts"] == 0
    assert transport.read_count == 1
    assert transport.mutations == []
