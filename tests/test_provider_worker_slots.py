from __future__ import annotations

import json
from dataclasses import replace

import pytest

from ops.executive_os import provider_identity_policy as policy
from ops.executive_os import provider_worker_slots as slots


def test_catalog_has_exact_company_plus_three_personal_pro_realms() -> None:
    catalog = slots.all_slots()
    assert tuple(row.slot_id for row in catalog) == (
        "codex-01",
        "codex-pro-01",
        "codex-pro-02",
        "codex-pro-03",
    )
    assert tuple(row.worker_uid for row in catalog) == (451, 454, 455, 456)
    assert tuple(row.worker_gid for row in catalog) == (451, 454, 455, 456)
    assert tuple(row.worker_group for row in catalog) == (
        "_mastermind_worker",
        "_mastermind_codex_01",
        "_mastermind_codex_02",
        "_mastermind_codex_03",
    )
    assert tuple(row.oauth_seat_ref for row in catalog) == (
        None,
        "chatgpt1",
        "chatgpt2",
        "chatgpt3",
    )
    assert catalog[0].workspace_binding_class == policy.COMPANY_WORKSPACE_BINDING_CLASS
    assert all(
        row.workspace_binding_class == policy.PERSONAL_PRO_WORKER_BINDING_CLASS
        for row in catalog[1:]
    )
    assert all(row.allowed_credential_kinds == ("device-auth",) for row in catalog[1:])


def test_catalog_realms_have_unique_principals_homes_auth_and_receipts() -> None:
    catalog = slots.all_slots()
    for field in (
        "slot_id",
        "worker_user",
        "worker_group",
        "worker_uid",
        "worker_gid",
        "provider_home",
        "readiness_receipt",
    ):
        values = [getattr(row, field) for row in catalog]
        assert len(values) == len(set(values)), field
    assert len({row.auth_path for row in catalog}) == len(catalog)
    assert all(str(row.provider_home).startswith("/var/db/mastermind-executive/workers/") for row in catalog)
    assert all(
        str(row.readiness_receipt).startswith(
            "/Library/Application Support/MastermindExecutive/config/"
        )
        for row in catalog
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda rows: [rows[0], replace(rows[1], worker_uid=rows[0].worker_uid), *rows[2:]],
        lambda rows: [rows[0], replace(rows[1], worker_gid=rows[0].worker_gid), *rows[2:]],
        lambda rows: [rows[0], replace(rows[1], worker_group=rows[0].worker_group), *rows[2:]],
        lambda rows: [rows[0], replace(rows[1], provider_home=rows[0].provider_home), *rows[2:]],
        lambda rows: [rows[0], replace(rows[1], readiness_receipt=rows[0].readiness_receipt), *rows[2:]],
        lambda rows: [rows[0], replace(rows[1], oauth_seat_ref="chatgpt2"), *rows[2:]],
        lambda rows: [replace(rows[0], oauth_seat_ref="chatgpt1"), *rows[1:]],
    ],
)
def test_catalog_validation_refuses_cross_realm_aliases(mutation) -> None:
    catalog = list(slots.all_slots())
    with pytest.raises(slots.SlotCatalogError):
        slots.validate_slots(mutation(catalog))


def test_unknown_slot_refuses_without_fallback() -> None:
    with pytest.raises(slots.SlotCatalogError, match="unknown_slot"):
        slots.get_slot("codex-pro-04")
    with pytest.raises(slots.SlotCatalogError, match="unknown_slot"):
        slots.get_slot("")


def test_personal_pro_policy_is_device_oauth_only() -> None:
    assert policy.evaluate_identity_policy(
        expected_kind="device-auth",
        auth_mode="chatgpt",
        account_type="chatgpt",
        plan_type="pro",
        requires_openai_auth=True,
        workspace_binding_class=policy.PERSONAL_PRO_WORKER_BINDING_CLASS,
    ) is None
    for expected_kind, auth_mode in (
        ("service-account", "agentIdentity"),
        ("personal-access-token", "personalAccessToken"),
    ):
        assert policy.evaluate_identity_policy(
            expected_kind=expected_kind,
            auth_mode=auth_mode,
            account_type="chatgpt",
            plan_type="pro",
            requires_openai_auth=True,
            workspace_binding_class=policy.PERSONAL_PRO_WORKER_BINDING_CLASS,
        ) == "personal_pro_device_auth_required"


@pytest.mark.parametrize("plan", ["free", "go", "plus", "prolite", "business", "enterprise", "future", "unknown"])
def test_personal_pro_policy_is_exact_plan_not_consumer_or_company_widening(plan: str) -> None:
    assert policy.evaluate_identity_policy(
        expected_kind="device-auth",
        auth_mode="chatgpt",
        account_type="chatgpt",
        plan_type=plan,
        requires_openai_auth=True,
        workspace_binding_class=policy.PERSONAL_PRO_WORKER_BINDING_CLASS,
    ) == "personal_pro_plan_required"


def test_company_policy_still_rejects_pro() -> None:
    assert policy.evaluate_identity_policy(
        expected_kind="device-auth",
        auth_mode="chatgpt",
        account_type="chatgpt",
        plan_type="pro",
        requires_openai_auth=True,
        workspace_binding_class=policy.COMPANY_WORKSPACE_BINDING_CLASS,
    ) == "company_plan_required"


def test_policy_refuses_wrong_binding_and_never_renders_provider_identity() -> None:
    assert policy.evaluate_identity_policy(
        expected_kind="device-auth",
        auth_mode="chatgpt",
        account_type="chatgpt",
        plan_type="pro",
        requires_openai_auth=True,
        workspace_binding_class="future-or-caller-supplied",
    ) == "workspace_binding_class_unknown"
    rendered = json.dumps([row.public_descriptor() for row in slots.all_slots()])
    for forbidden in (
        "@",
        "account_id",
        "accountId",
        "email",
        "profile_id",
        "workspace_id",
        "auth.json",
        "/Users/",
        ".codex",
    ):
        assert forbidden not in rendered
