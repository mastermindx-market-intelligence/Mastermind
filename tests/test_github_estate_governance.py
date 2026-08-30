from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.github_estate_governance import (
    AdministrationFamily,
    AdministrationSpec,
    GitHubResponse,
    GovernanceRefusal,
    apply_administration_family,
    canonical_digest,
    validate_disposable_private_repository,
    validate_publisher_app_installation,
    validate_ruleset_activation,
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


def _ruleset() -> dict:
    return {
        "id": 21813020,
        "name": "c0b-native-main-interlock",
        "target": "branch",
        "enforcement": "evaluate",
        "bypass_actors": [],
        "conditions": {
            "ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}
        },
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {
                "type": "pull_request",
                "parameters": {
                    "allowed_merge_methods": ["squash"],
                    "dismiss_stale_reviews_on_push": False,
                    "dismissal_restriction": {
                        "allowed_actors": [],
                        "enabled": False,
                    },
                    "require_code_owner_review": False,
                    "require_extra_approval_for_unattributed_changes": True,
                    "require_last_push_approval": False,
                    "required_approving_review_count": 0,
                    "required_review_thread_resolution": False,
                    "required_reviewers": [],
                },
            },
            {
                "type": "required_status_checks",
                "parameters": {
                    "required_status_checks": [
                        {"context": "fence-pack", "integration_id": 15368},
                        {"context": "ci-authority/main", "integration_id": 15368},
                        {"context": "ci-gate", "integration_id": 15368},
                    ],
                    "strict_required_status_checks_policy": False,
                    "do_not_enforce_on_create": True,
                },
            },
        ],
    }


def _activation_evidence() -> dict:
    return {
        "ruleset_id": 21813020,
        "candidate_denial": "PASS",
        "fork_denial": "PASS",
        "natural_evaluate_observations": "PASS",
        "natural_green_admission": "PASS",
        "ordinary_red_rejection": "PASS",
        "publisher_continuity": "PASS",
        "rollback_canary": "PASS",
        "disposable_private_repository": "PASS",
    }


def test_ruleset_activation_preserves_same_ruleset_and_requires_all_canaries():
    before = _ruleset()
    desired = {**deepcopy(before), "enforcement": "active"}

    payload = validate_ruleset_activation(
        before,
        desired,
        expected_ruleset_id=21813020,
        evidence=_activation_evidence(),
    )

    assert payload["enforcement"] == "active"
    assert payload["bypass_actors"] == []
    assert payload["rules"] == before["rules"]
    assert payload["conditions"] == before["conditions"]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda desired: desired.update(id=999), "ruleset id drifted"),
        (
            lambda desired: desired.update(
                bypass_actors=[{"actor_id": 1, "actor_type": "OrganizationAdmin"}]
            ),
            "bypass actors drifted",
        ),
        (lambda desired: desired.update(rules=[]), "rules drifted"),
        (lambda desired: desired.update(name="replacement"), "name drifted"),
    ],
)
def test_ruleset_activation_refuses_replacement_or_policy_drift(mutation, message):
    before = _ruleset()
    desired = {**deepcopy(before), "enforcement": "active"}
    mutation(desired)

    with pytest.raises(GovernanceRefusal, match=message):
        validate_ruleset_activation(
            before,
            desired,
            expected_ruleset_id=21813020,
            evidence=_activation_evidence(),
        )


def test_ruleset_activation_refuses_any_missing_canary():
    before = _ruleset()
    desired = {**deepcopy(before), "enforcement": "active"}
    evidence = _activation_evidence()
    evidence["ordinary_red_rejection"] = "NOT_RUN"

    with pytest.raises(GovernanceRefusal, match="activation evidence is incomplete"):
        validate_ruleset_activation(
            before,
            desired,
            expected_ruleset_id=21813020,
            evidence=evidence,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda ruleset: ruleset["conditions"]["ref_name"].update(
            include=["refs/heads/main"]
        ),
        lambda ruleset: ruleset["rules"][-1]["parameters"][
            "required_status_checks"
        ].append({"context": "broad-bypass", "integration_id": 15368}),
        lambda ruleset: ruleset["rules"][-1]["parameters"].update(
            strict_required_status_checks_policy=True
        ),
        lambda ruleset: ruleset["rules"][2]["parameters"].update(
            allowed_merge_methods=["merge", "squash"]
        ),
    ],
)
def test_ruleset_activation_refuses_a_preserved_but_wrong_policy(mutation):
    before = _ruleset()
    mutation(before)
    desired = {**deepcopy(before), "enforcement": "active"}

    with pytest.raises(GovernanceRefusal, match="ruleset policy is not exact"):
        validate_ruleset_activation(
            before,
            desired,
            expected_ruleset_id=21813020,
            evidence=_activation_evidence(),
        )


def test_publisher_app_must_be_repo_selected_and_exactly_least_privileged():
    receipt = validate_publisher_app_installation(
        {
            "app_slug": "macro-production-publisher",
            "repository_selection": "selected",
            "repositories": ["mastermindx-market-intelligence/macro"],
            "permissions": {"metadata": "read", "contents": "write"},
            "events": [],
        },
        expected_repository="mastermindx-market-intelligence/macro",
    )

    assert receipt["verdict"] == "PASS"
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
