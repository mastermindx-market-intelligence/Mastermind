from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from control_plane.subscription_harness_bindings import get_binding
from ops.executive_os import provider_worker_slots as slots


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "ops" / "executive_os" / "bootstrap-host.sh"


def test_legacy_codex_inventory_is_byte_contract_unchanged() -> None:
    assert tuple(row.slot_id for row in slots.all_slots()) == (
        "codex-01", "codex-pro-01", "codex-pro-02", "codex-pro-03"
    )
    assert tuple(row.worker_uid for row in slots.all_slots()) == (451, 454, 455, 456)


def test_subscription_inventory_has_two_held_codex_backed_realms() -> None:
    catalog = slots.subscription_slots()
    assert tuple(row.slot_id for row in catalog) == (
        "alibaba-token-01", "minimax-token-01"
    )
    assert tuple(row.worker_uid for row in catalog) == (459, 460)
    assert tuple(row.worker_gid for row in catalog) == (459, 460)
    assert tuple(row.worker_user for row in catalog) == (
        "_mastermind_alibaba_01", "_mastermind_minimax_01"
    )
    for row in catalog:
        binding = get_binding(row.harness_binding_id)
        assert binding.provider == row.provider
        assert binding.profile_id == row.profile_id
        assert binding.adapter_id == "codex-cli"
        assert binding.implementation_state == "BUILT_NOT_PROVEN"
        assert binding.autonomous_allowed is False


def test_subscription_inventory_is_collision_free_and_has_no_capacity_authority() -> None:
    legacy = slots.all_slots()
    subscription = slots.subscription_slots()
    assert not ({row.worker_uid for row in legacy} & {row.worker_uid for row in subscription})
    assert not ({row.worker_gid for row in legacy} & {row.worker_gid for row in subscription})
    assert not ({row.provider_home for row in legacy} & {row.provider_home for row in subscription})
    rendered = json.dumps([row.public_descriptor() for row in subscription])
    for forbidden in (
        "capacity_capability_id", "capability_generation", "account_label",
        "credential", "api_key", "auth.json", "/Library/", "/var/db/", "@",
    ):
        assert forbidden not in rendered
    assert all(row.public_descriptor()["admission_state"] == "HELD_FOR_REAL_CANARY" for row in subscription)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda rows: [replace(rows[0], worker_uid=458), rows[1]],
        lambda rows: [replace(rows[0], worker_gid=451), rows[1]],
        lambda rows: [replace(rows[0], worker_user="_mastermind_minimax_01"), rows[1]],
        lambda rows: [replace(rows[0], harness_binding_id="minimax-token-plan.codex-responses"), rows[1]],
        lambda rows: [rows[0], replace(rows[1], worker_uid=459)],
    ],
)
def test_subscription_inventory_refuses_identity_or_binding_mutation(mutation) -> None:
    with pytest.raises(slots.SlotCatalogError):
        slots.validate_subscription_slots(mutation(list(slots.subscription_slots())))


def test_subscription_cli_requires_explicit_catalog_switch() -> None:
    assert slots.main(["--subscription", "alibaba-token-01", "worker_uid"]) == 0
    assert slots.main(["alibaba-token-01", "worker_uid"]) == 2
    assert slots.main(["--subscription", "codex-pro-01", "worker_uid"]) == 2


def test_bootstrap_prepares_subscription_principals_without_capacity_or_service_arming() -> None:
    source = BOOTSTRAP.read_text(encoding="utf-8")
    assert 'SUBSCRIPTION_SLOT_IDS=("alibaba-token-01" "minimax-token-01")' in source
    assert 'subscription_slot_field()' in source
    assert 'for slot_id in "${SUBSCRIPTION_SLOT_IDS[@]}"; do' in source
    assert 'ensure_group "$slot_group" "$slot_gid"' in source
    assert 'ensure_user "$slot_user" "$slot_uid" "$slot_gid" "$slot_home"' in source
    assert '"/var/log/mastermind-executive/workers/$slot_id"' in source
    for forbidden in (
        "capacity_capability_id", "register-worker", "bootstrap system",
        "launchctl bootstrap", "subscription_provider_credential.py --enroll",
    ):
        assert forbidden not in source
