from __future__ import annotations

import json
import plistlib
import stat
from pathlib import Path

import pytest

from ops.executive_os import subscription_broker_definitions as definitions
from scripts.executive_os_phase1c_worker import (
    WorkerConfigError,
    _assert_service_activation_allowed,
    _load_config,
)


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "ops" / "executive_os" / "com.mastermind.executive.worker.codex.plist.template"
GIDS = {
    "alibaba-token-01": [12, 61, 100],
    "minimax-token-01": [12, 61, 100],
}


def _build():
    return definitions.build_definitions(
        release_root=Path("/opt/mastermind/release"),
        template_bytes=TEMPLATE.read_bytes(),
        supplementary_gids=GIDS,
    )


def test_definitions_render_two_held_v5_brokers_without_capacity_authority() -> None:
    manifest, configs, plists = _build()
    assert manifest["schema_version"] == definitions.DEFINITIONS_SCHEMA
    assert manifest["start_authority"] is False
    assert manifest["credential_authority"] is False
    assert manifest["capacity_authority"] is False
    assert manifest["route_authority"] is False
    assert tuple(row["slot_id"] for row in manifest["definitions"]) == (
        "alibaba-token-01",
        "minimax-token-01",
    )
    assert set(configs) == set(plists) == set(GIDS)
    rendered = json.dumps(manifest, sort_keys=True)
    for forbidden in (
        "capacity_capability_id",
        "capability_generation",
        "account_label",
        "credential",
        "api_key",
        "auth.json",
    ):
        assert forbidden not in rendered


@pytest.mark.parametrize(
    ("slot_id", "binding_id"),
    (
        ("alibaba-token-01", "alibaba-token-plan-personal.codex-responses"),
        ("minimax-token-01", "minimax-token-plan.codex-responses"),
    ),
)
def test_rendered_config_is_valid_v5_but_autonomous_serve_refuses(
    tmp_path: Path, slot_id: str, binding_id: str
) -> None:
    _manifest, configs, _plists = _build()
    value = json.loads(configs[slot_id])
    assert value["schema_version"] == definitions.WORKER_CONFIG_SCHEMA
    assert value["harness_binding_id"] == binding_id
    assert value["worker_id"] == slot_id
    assert value["require_secret_canary"] is True
    assert value["operator_harness_armed"] is False

    path = tmp_path / f"{slot_id}.json"
    path.write_bytes(configs[slot_id])
    path.chmod(0o440)
    loaded = _load_config(path, require_root_owner=False)
    with pytest.raises(WorkerConfigError, match="not armed for autonomous service"):
        _assert_service_activation_allowed(loaded)


def test_plists_bind_exact_principals_and_remain_definitions_only() -> None:
    manifest, _configs, plists = _build()
    rows = {row["slot_id"]: row for row in manifest["definitions"]}
    expected = {
        "alibaba-token-01": "_mastermind_alibaba_01",
        "minimax-token-01": "_mastermind_minimax_01",
    }
    for slot_id, user in expected.items():
        value = plistlib.loads(plists[slot_id])
        assert value["Label"] == f"com.mastermind.executive.worker.{slot_id}"
        assert value["UserName"] == user
        assert value["GroupName"] == user
        assert value["EnvironmentVariables"]["HOME"].endswith(
            f"/workers/{slot_id}/provider-home"
        )
        assert value["ProgramArguments"][-2:] == [
            "--config",
            rows[slot_id]["config_path"],
        ]
        assert value.get("RunAtLoad") is not True
        assert value.get("KeepAlive") is not True
        assert rows[slot_id]["launchd_state"] == "disabled_unloaded"
        assert rows[slot_id]["worker_execution"] == "held_for_real_canary"
        assert rows[slot_id]["autonomous_allowed"] is False


def test_staging_writer_creates_only_private_inert_artifacts(tmp_path: Path) -> None:
    manifest, configs, plists = _build()
    destination = tmp_path / "stage"
    definitions.write_definitions(
        destination,
        manifest=manifest,
        configs=configs,
        plists=plists,
    )
    names = sorted(path.name for path in destination.iterdir())
    assert names == [
        "com.mastermind.executive.worker.alibaba-token-01.plist",
        "com.mastermind.executive.worker.minimax-token-01.plist",
        "subscription-broker-definitions.json",
        "worker-alibaba-token-01.json",
        "worker-minimax-token-01.json",
    ]
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o400 for path in destination.iterdir())


@pytest.mark.parametrize(
    "gids",
    (
        {"alibaba-token-01": [12, 61, 100]},
        {**GIDS, "unexpected": [12, 61, 100]},
        {"alibaba-token-01": [12, 61, 100], "minimax-token-01": []},
    ),
)
def test_definitions_refuse_incomplete_extra_or_invalid_supplementary_gids(gids) -> None:
    with pytest.raises((definitions.SubscriptionBrokerDefinitionError, ValueError)):
        definitions.build_definitions(
            release_root=Path("/opt/mastermind/release"),
            template_bytes=TEMPLATE.read_bytes(),
            supplementary_gids=gids,
        )
