"""Structural four-realm projection, not subscription enrollment or capacity."""
from __future__ import annotations

import dataclasses
import json

import pytest

from control_plane import codex_provider_realm as realm
from ops.executive_os import provider_worker_slots as slots
from test_native_provider_realm_owner import enrolled  # Existing owner fixture.


NATIVE_IDS = tuple(f"claude-native-{index:02d}" for index in range(1, 5))


def config(slot_id, index=1):
    return {
        "native_provider": "claude", "control_uid": 450,
        "worker_uid": 2000 + index, "worker_gid": 2000 + index,
        "worker_user": f"_mastermind_claude_{index:02d}",
        "native_realm_enrollment": {"slot_id": slot_id},
    }


@pytest.mark.parametrize("slot_id", NATIVE_IDS)
def test_root_config_projects_each_native_slot_without_global_enrollment(slot_id):
    before = slots.all_slots()
    row = slots.native_slot_from_config(config(slot_id))
    assert row.slot_id == slot_id and row.provider_family == "anthropic"
    assert row.provider_home == slots.RUNTIME_WORKER_ROOT / slot_id / "provider-home"
    assert row.auth_path == row.provider_home / ".claude" / ".credentials.json"
    assert row.readiness_receipt == slots.SYSTEM_CONFIG_ROOT / f"provider-readiness-{slot_id}.json"
    assert row.oauth_seat_ref is None  # Slot names never select a numbered login.
    assert row.allowed_credential_kinds == ("claudeai-subscription",)
    assert slots.all_slots() == before and len(before) == 4
    with pytest.raises(slots.SlotCatalogError, match="unknown_slot"):
        slots.get_slot(slot_id)


def test_four_explicit_native_configs_have_disjoint_local_coordinates():
    rows = [slots.native_slot_from_config(config(name, index))
            for index, name in enumerate(NATIVE_IDS, 1)]
    for field in ("slot_id", "worker_user", "worker_uid", "worker_gid",
                  "provider_home", "readiness_receipt", "auth_path"):
        assert len({getattr(row, field) for row in rows}) == 4
    for row in rows:
        public = row.public_descriptor()
        assert "capacity_capability_id" not in public
        assert "available" not in public and "enrolled" not in public


def test_legacy_native_coordinates_remain_compatible():
    row = slots.native_slot_from_config(config("claude8-native-01"))
    assert row.oauth_seat_ref == "claude8"
    assert row.provider_home == slots.RUNTIME_WORKER_ROOT / "claude8-native-01" / "provider-home"


@pytest.mark.parametrize("slot_id", [
    None, True, 1, [], {}, "", "claude-native-00", "claude-native-05",
    "claude-native-1", "CLAUDE-NATIVE-01", " claude-native-01",
    "claude-native-01\n", "../claude-native-01", "claude8-native-02",
    "claude-pro-01", "codex-01",
])
def test_unreviewed_or_noncanonical_slot_refuses_without_echo(slot_id):
    with pytest.raises(slots.SlotCatalogError, match="^native_slot_inventory_invalid$"):
        slots.native_slot_from_config(config(slot_id))


@pytest.mark.parametrize("field,value", [
    ("worker_uid", 450), ("worker_uid", 451), ("worker_uid", True),
    ("worker_gid", 451), ("worker_gid", 0), ("worker_user", "_mastermind_worker"),
])
def test_expanded_slot_does_not_relax_principal_or_codex_collision_checks(field, value):
    candidate = config(NATIVE_IDS[1])
    candidate[field] = value
    with pytest.raises(slots.SlotCatalogError):
        slots.native_slot_from_config(candidate)


@pytest.mark.parametrize("slot_id", NATIVE_IDS)
def test_existing_realm_owner_consumes_explicit_native_identity(enrolled, slot_id):
    # Reuse virtual root custody, but real config/binary bytes and digest checks.
    enrolled.config["native_realm_enrollment"]["slot_id"] = slot_id
    owner = enrolled.load()
    observed = owner.observe()
    assert observed.slot_id == slot_id and observed.generation == 1
    assert owner.require_current_identity(observed.host_ref, observed.os_principal_ref) is None
    public = json.dumps(dataclasses.asdict(observed))
    assert str(enrolled.home) not in public and "credentials" not in public


def test_native_slot_change_cannot_retarget_an_existing_owner(enrolled):
    enrolled.config["native_realm_enrollment"]["slot_id"] = NATIVE_IDS[0]
    owner = enrolled.load()
    assert owner.observe().slot_id == NATIVE_IDS[0]
    enrolled.config["native_realm_enrollment"]["slot_id"] = NATIVE_IDS[1]
    enrolled.path.write_text(json.dumps(enrolled.config))
    with pytest.raises(realm.ProviderRealmError, match="^NATIVE_REALM_IDENTITY_UNAVAILABLE$"):
        owner.observe()
