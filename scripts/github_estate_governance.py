#!/usr/bin/env python3
"""Stateless, fail-closed interlocks for bounded GitHub administration.

This module is deliberately not a scheduler, credential store, desired-state
database, or authority plane.  The caller supplies a freshly observed baseline
and performs one named administration family at a time.  The interlock binds the
write to that baseline, sends no secret material, never retries a write, and
accepts the effect only after a fresh read-back.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol


class GovernanceRefusal(RuntimeError):
    """A required safety or evidence predicate was not established."""


class AdministrationFamily(str, Enum):
    REPOSITORY_MERGE_POLICY = "repository_merge_policy"
    ACTIONS_DEFAULT_PERMISSIONS = "actions_default_permissions"
    SECURITY_AND_ANALYSIS = "security_and_analysis"


@dataclass(frozen=True)
class GitHubResponse:
    status: int
    body: Mapping[str, Any] | None


@dataclass(frozen=True)
class AdministrationSpec:
    family: AdministrationFamily
    endpoint: str
    method: str
    expected_before_sha256: str
    payload: Mapping[str, Any]
    expected_after: Mapping[str, Any]


class GitHubTransport(Protocol):
    def read(self, endpoint: str) -> Mapping[str, Any]: ...

    def mutate(
        self, method: str, endpoint: str, payload: Mapping[str, Any]
    ) -> GitHubResponse: ...


_REPOSITORY_ENDPOINT = re.compile(r"repos/[^/]+/[^/]+\Z")
_ACTIONS_ENDPOINT = re.compile(
    r"repos/[^/]+/[^/]+/actions/permissions/workflow\Z"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SECRET_KEY = re.compile(
    r"(^|_)(token|secret|password|private_key|credential|authorization)($|_)",
    re.IGNORECASE,
)

_FAMILY_CONTRACTS: dict[AdministrationFamily, tuple[re.Pattern[str], str, set[str]]] = {
    AdministrationFamily.REPOSITORY_MERGE_POLICY: (
        _REPOSITORY_ENDPOINT,
        "PATCH",
        {
            "allow_merge_commit",
            "allow_rebase_merge",
            "allow_squash_merge",
            "delete_branch_on_merge",
        },
    ),
    AdministrationFamily.ACTIONS_DEFAULT_PERMISSIONS: (
        _ACTIONS_ENDPOINT,
        "PUT",
        {"default_workflow_permissions", "can_approve_pull_request_reviews"},
    ),
    AdministrationFamily.SECURITY_AND_ANALYSIS: (
        _REPOSITORY_ENDPOINT,
        "PATCH",
        {"security_and_analysis"},
    ),
}


def _plain_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise GovernanceRefusal("governance document is not a mapping")
    return {str(key): item for key, item in value.items()}


def canonical_digest(value: Mapping[str, Any]) -> str:
    """Return a stable digest for one complete observed document."""

    try:
        encoded = json.dumps(
            _plain_mapping(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise GovernanceRefusal("governance document is not canonical JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


def _assert_secret_free(value: Any, *, path: str = "payload") -> None:
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key)
            if _SECRET_KEY.search(key):
                raise GovernanceRefusal(f"secret-bearing field refused at {path}.{key}")
            _assert_secret_free(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_secret_free(item, path=f"{path}[{index}]")


def _assert_family_contract(spec: AdministrationSpec) -> None:
    if spec.family not in _FAMILY_CONTRACTS:
        raise GovernanceRefusal("administration family is not allowlisted")
    endpoint_pattern, method, allowed_keys = _FAMILY_CONTRACTS[spec.family]
    if endpoint_pattern.fullmatch(spec.endpoint) is None:
        raise GovernanceRefusal("administration endpoint is outside the family contract")
    if spec.method.upper() != method:
        raise GovernanceRefusal("administration method is outside the family contract")
    payload = _plain_mapping(spec.payload)
    _assert_secret_free(payload)
    if set(payload) != allowed_keys:
        raise GovernanceRefusal("administration payload keys drifted from the family contract")
    if _SHA256.fullmatch(spec.expected_before_sha256) is None:
        raise GovernanceRefusal("expected before digest is malformed")

    if spec.family is AdministrationFamily.REPOSITORY_MERGE_POLICY:
        if any(type(payload[key]) is not bool for key in allowed_keys):
            raise GovernanceRefusal("repository merge-policy values must be booleans")
        if payload["allow_squash_merge"] is not True:
            raise GovernanceRefusal("repository merge policy must retain squash merge")
        if payload["allow_merge_commit"] or payload["allow_rebase_merge"]:
            raise GovernanceRefusal("repository merge policy may not widen merge methods")
    elif spec.family is AdministrationFamily.ACTIONS_DEFAULT_PERMISSIONS:
        if payload != {
            "default_workflow_permissions": "read",
            "can_approve_pull_request_reviews": False,
        }:
            raise GovernanceRefusal("Actions default permissions may only be narrowed")
    elif spec.family is AdministrationFamily.SECURITY_AND_ANALYSIS:
        security = payload.get("security_and_analysis")
        if not isinstance(security, Mapping) or not security:
            raise GovernanceRefusal("security-and-analysis payload is malformed")
        allowed = {"secret_scanning", "secret_scanning_push_protection"}
        if not set(security).issubset(allowed):
            raise GovernanceRefusal("security-and-analysis payload widens the safe family")
        for feature in security.values():
            if feature != {"status": "enabled"}:
                raise GovernanceRefusal("security features may only be enabled")


def _matches_expected(current: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    for key, expected_value in expected.items():
        if key not in current or current[key] != expected_value:
            return False
    return True


def _receipt(
    *,
    spec: AdministrationSpec,
    verdict: str,
    effect: str,
    before: Mapping[str, Any],
    after: Mapping[str, Any] | None = None,
    reconciled: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": "mastermind.github_estate_administration_receipt.v1",
        "family": spec.family.value,
        "endpoint": spec.endpoint,
        "verdict": verdict,
        "effect": effect,
        "before_sha256": canonical_digest(before),
        "reconciled": reconciled,
        "mutation_attempts": 0 if verdict == "ALREADY_CONFIGURED" else 1,
    }
    if after is not None:
        result["after_sha256"] = canonical_digest(after)
    return result


def apply_administration_family(
    transport: GitHubTransport,
    spec: AdministrationSpec,
) -> dict[str, Any]:
    """Apply one exact family once and accept it only from fresh read-back.

    Explicit 4xx rejections are effect-none and are not reconciled.  A 5xx or
    otherwise ambiguous response triggers exactly one read-only reconciliation;
    the mutation is never retried.
    """

    _assert_family_contract(spec)
    before = _plain_mapping(transport.read(spec.endpoint))
    if canonical_digest(before) != spec.expected_before_sha256:
        raise GovernanceRefusal("before digest drifted; refusing stale administration")
    if _matches_expected(before, spec.expected_after):
        return _receipt(
            spec=spec,
            verdict="ALREADY_CONFIGURED",
            effect="NONE",
            before=before,
        )

    try:
        response = transport.mutate(spec.method.upper(), spec.endpoint, spec.payload)
    except Exception:  # noqa: BLE001 - the request may have crossed the effect boundary
        try:
            after = _plain_mapping(transport.read(spec.endpoint))
        except Exception:  # noqa: BLE001 - preserve effect-unknown without a retry
            return _receipt(
                spec=spec,
                verdict="EFFECT_UNKNOWN",
                effect="UNKNOWN",
                before=before,
                reconciled=True,
            )
        return _receipt(
            spec=spec,
            verdict=(
                "APPLIED_AFTER_RECONCILIATION"
                if _matches_expected(after, spec.expected_after)
                else "EFFECT_UNKNOWN"
            ),
            effect=(
                "CONFIRMED"
                if _matches_expected(after, spec.expected_after)
                else "UNKNOWN"
            ),
            before=before,
            after=after,
            reconciled=True,
        )
    if not isinstance(response, GitHubResponse):
        raise GovernanceRefusal("mutation response contract is malformed")
    if 400 <= response.status < 500:
        return _receipt(
            spec=spec,
            verdict="AUTH_REJECTED" if response.status in {401, 403} else "REJECTED",
            effect="NONE",
            before=before,
        )

    after = _plain_mapping(transport.read(spec.endpoint))
    matches = _matches_expected(after, spec.expected_after)
    ambiguous = not (200 <= response.status < 300)
    if matches:
        return _receipt(
            spec=spec,
            verdict=(
                "APPLIED_AFTER_RECONCILIATION" if ambiguous else "APPLIED"
            ),
            effect="CONFIRMED",
            before=before,
            after=after,
            reconciled=ambiguous,
        )
    return _receipt(
        spec=spec,
        verdict="EFFECT_UNKNOWN" if ambiguous else "READBACK_MISMATCH",
        effect="UNKNOWN",
        before=before,
        after=after,
        reconciled=ambiguous,
    )


_ADMIN_CAPABILITY_PROBES = {
    "organization_audit_log",
    "installed_app_inventory",
    "app_management",
    "app_creation",
    "app_installation",
    "private_key_custody",
}


def assess_github_admin_prerequisites(
    *,
    principal: Mapping[str, Any],
    capability_probes: Mapping[str, Any],
    installations: list[Mapping[str, Any]],
    expected_repository: str,
) -> dict[str, Any]:
    """Assess explicit admin probes without promoting OAuth scopes to authority."""

    identity = _plain_mapping(principal)
    probes = _plain_mapping(capability_probes)
    if not isinstance(identity.get("login"), str) or not identity["login"].strip():
        raise GovernanceRefusal("GitHub principal identity is missing")
    if identity.get("principal_type") != "oauth_user":
        raise GovernanceRefusal("GitHub principal type is not explicit")
    if set(probes) != _ADMIN_CAPABILITY_PROBES or any(
        value not in {"SATISFIED", "HELD"} for value in probes.values()
    ):
        raise GovernanceRefusal("GitHub capability probe results are not explicit")
    if not isinstance(installations, list):
        raise GovernanceRefusal("installed App census is not a list")
    _assert_secret_free(identity, path="principal")

    safe_rows: list[dict[str, Any]] = []
    qualified: list[dict[str, Any]] = []
    for raw in installations:
        app = _plain_mapping(raw)
        _assert_secret_free(app, path="installation")
        app_id = app.get("app_id")
        app_slug = app.get("app_slug")
        if type(app_id) is not int or app_id <= 0 or not isinstance(app_slug, str):
            raise GovernanceRefusal("installed App identity is malformed")
        safe_rows.append(
            {
                "app_id": app_id,
                "app_slug": app_slug,
                "repository_selection": app.get("repository_selection"),
                "permissions": app.get("permissions"),
            }
        )
        if app_slug == "macro-production-publisher":
            qualified.append(
                validate_publisher_app_installation(
                    app,
                    expected_repository=expected_repository,
                )
            )
    if len(qualified) > 1:
        raise GovernanceRefusal("publisher App installation is ambiguous")
    return {
        "schema": "mastermind.github_admin_prerequisite_census.v1",
        "principal": {
            "login": identity["login"],
            "principal_type": identity["principal_type"],
            "organization_role": identity.get("organization_role"),
            "oauth_scopes": identity.get("oauth_scopes", []),
        },
        "scope_inferred_from_oauth": False,
        "gates": dict(sorted(probes.items())),
        "installed_apps": safe_rows,
        "suitable_publisher_app_exists": len(qualified) == 1,
        "qualified_app_integration_id": (
            qualified[0]["app_integration_id"] if qualified else None
        ),
        "credential_material_observed": False,
    }


def validate_candidate_credential_denial(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Accept secret-free proof that candidate execution has no App credential seam."""

    observed = _plain_mapping(evidence)
    expected_keys = {
        "custody_kind",
        "repository_actions_secret_present",
        "organization_actions_secret_present",
        "environment_actions_secret_present",
        "candidate_checkout_material_present",
        "candidate_installation_token_minted",
        "credential_material_observed",
    }
    if set(observed) != expected_keys:
        raise GovernanceRefusal("candidate credential-denial evidence is incomplete")
    if observed["custody_kind"] not in {
        "operator_keychain",
        "publisher_host_keychain",
    }:
        raise GovernanceRefusal("publisher credential custody is candidate-reachable")
    if any(observed[key] is not False for key in expected_keys - {"custody_kind"}):
        raise GovernanceRefusal("candidate credential projection was observed")
    return {
        "schema": "mastermind.github_candidate_credential_denial.v1",
        "verdict": "PASS",
        "custody_kind": observed["custody_kind"],
        "candidate_credential_reachability": "DENIED",
        "credential_material_observed": False,
    }


def validate_publisher_app_installation(
    installation: Mapping[str, Any],
    *,
    expected_repository: str,
) -> dict[str, Any]:
    """Accept only the dedicated repository-selected publisher authority."""

    app = _plain_mapping(installation)
    if type(app.get("app_id")) is not int or app["app_id"] <= 0:
        raise GovernanceRefusal("publisher App Integration ID is not exact")
    if app.get("app_slug") != "macro-production-publisher":
        raise GovernanceRefusal("publisher App identity is not exact")
    if app.get("repository_selection") != "selected":
        raise GovernanceRefusal("publisher App is not repository-selected")
    if app.get("repositories") != [expected_repository]:
        raise GovernanceRefusal("publisher App repository scope is not exact")
    if app.get("permissions") != {"metadata": "read", "contents": "write"}:
        raise GovernanceRefusal("publisher App permissions are not least-privileged")
    if app.get("events") != []:
        raise GovernanceRefusal("publisher App subscribes to events")
    _assert_secret_free(app)
    return {
        "schema": "mastermind.github_publisher_app_validation.v1",
        "verdict": "PASS",
        "app_integration_id": app["app_id"],
        "app_slug": app["app_slug"],
        "repository": expected_repository,
        "permissions": app["permissions"],
        "events": [],
        "credential_material_observed": False,
    }


def validate_disposable_private_repository(
    *,
    repository: Mapping[str, Any],
    security_and_analysis: Mapping[str, Any],
    actions_permissions: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the safe baseline of a disposable private-repository canary."""

    repo = _plain_mapping(repository)
    security = _plain_mapping(security_and_analysis)
    actions = _plain_mapping(actions_permissions)
    secret_scanning = security.get("secret_scanning")
    push_protection = security.get("secret_scanning_push_protection")
    predicates = (
        repo.get("private") is True,
        repo.get("visibility") == "private",
        repo.get("archived") is False,
        secret_scanning == {"status": "enabled"},
        push_protection == {"status": "enabled"},
        actions.get("default_workflow_permissions") == "read",
        actions.get("can_approve_pull_request_reviews") is False,
    )
    if not all(predicates):
        raise GovernanceRefusal("disposable private-repository canary is not safe")
    return {
        "verdict": "PASS",
        "private": True,
        "secret_scanning": "enabled",
        "push_protection": "enabled",
        "actions_default": "read",
        "actions_can_approve_pull_requests": False,
    }
