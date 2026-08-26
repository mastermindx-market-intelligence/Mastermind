from __future__ import annotations

import hashlib
import json
import plistlib
from pathlib import Path

import pytest

from ops.executive_os import capacity_broker_topology as topology


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (
    ROOT / "ops/executive_os/com.mastermind.executive.worker.codex.plist.template"
).read_bytes()
RELEASE = Path("/Library/Application Support/MastermindExecutive/releases") / ("a" * 40)
GIDS = {
    "codex-pro-01": [12, 61, 100],
    "codex-pro-02": [12, 61, 100, 396],
    "codex-pro-03": [12, 61, 100],
}
ATTESTATION_DIGEST = "b" * 64


def _built():
    return topology.build_topology(
        release_root=RELEASE,
        template_bytes=TEMPLATE,
        supplementary_gids=GIDS,
        attestation_sha256=ATTESTATION_DIGEST,
        legacy_state_digest="c" * 64,
    )


def test_topology_is_exact_three_realm_bijection_and_runtime_held() -> None:
    value, configs, plists = _built()
    assert value["schema_version"] == "mastermind.executive_capacity_broker_topology/v1"
    assert value["runtime_composition"] == "held_for_cf2_i_b"
    assert value["worker_execution"] == "held"
    assert value["legacy_phase1c_state_digest"] == "c" * 64
    assert [row["slot_id"] for row in value["brokers"]] == [
        "codex-pro-01",
        "codex-pro-02",
        "codex-pro-03",
    ]
    assert [row["capacity_capability_id"] for row in value["brokers"]] == [
        "codex_account",
        "codex_account_2",
        "codex_account_3",
    ]
    assert list(configs) == list(plists) == ["codex-pro-01", "codex-pro-02", "codex-pro-03"]
    assert len({row["label"] for row in value["brokers"]}) == 3
    assert len({row["socket_path"] for row in value["brokers"]}) == 3


def test_configs_reuse_closed_broker_family_without_cross_realm_paths() -> None:
    value, configs, _ = _built()
    for row in value["brokers"]:
        config = json.loads(configs[row["slot_id"]])
        assert config["schema_version"] == "mastermind.executive_worker_broker_config/v4"
        assert config["control_uid"] == 450
        assert config["worker_uid"] == row["worker_uid"]
        assert config["worker_gid"] == row["worker_gid"]
        assert config["worker_user"] == row["worker_user"]
        assert config["worker_id"] == row["slot_id"]
        assert config["provider_home"] == row["provider_home"]
        assert config["workspace_root"] == "/var/db/mastermind-executive/jobs/workspaces"
        assert config["run_root"] == "/var/db/mastermind-executive/jobs/runs"
        assert row["workspace_root"] == config["workspace_root"]
        assert row["run_root"] == config["run_root"]
        assert config["operator_harness_armed"] is False
        assert config["require_secret_canary"] is True
        assert config["codex_attestation_receipt"] == row["attestation_path"]
        encoded = configs[row["slot_id"]].decode()
        for sibling in {"codex-pro-01", "codex-pro-02", "codex-pro-03"} - {row["slot_id"]}:
            assert sibling not in encoded


def test_plists_preserve_template_isolation_and_define_private_absent_sockets() -> None:
    value, _, plists = _built()
    template = plistlib.loads(TEMPLATE)
    for row in value["brokers"]:
        plist = plistlib.loads(plists[row["slot_id"]])
        assert plist["Label"] == row["label"]
        assert plist["RunAtLoad"] is template["RunAtLoad"] is True
        assert plist["KeepAlive"] is template["KeepAlive"] is True
        assert plist["InitGroups"] is False
        assert plist["UserName"] == row["worker_user"]
        assert plist["GroupName"] == row["worker_group"]
        assert plist["WorkingDirectory"] == str(RELEASE)
        assert plist["ProgramArguments"][-1] == row["config_path"]
        socket = plist["Sockets"]["WorkerBroker"]
        assert socket == {
            "SockPathName": row["socket_path"],
            "SockType": "stream",
            "SockPassive": True,
            "SockPathOwner": 450,
            "SockPathGroup": 450,
            "SockPathMode": 0o600,
        }
        assert row["launchd_state"] == "disabled_unloaded"
        assert row["socket_node_state"] == "absent"


@pytest.mark.parametrize(
    "gids",
    [[], [12, 61], [12, 61, 100, 450], [12, 61, 100, 100], [100, 61, 12]],
)
def test_topology_refuses_unreviewed_ambient_group_vectors(gids: list[int]) -> None:
    invalid = dict(GIDS, **{"codex-pro-01": gids})
    with pytest.raises(topology.CapacityBrokerTopologyError, match="SUPPLEMENTARY"):
        topology.build_topology(
            release_root=RELEASE,
            template_bytes=TEMPLATE,
            supplementary_gids=invalid,
            attestation_sha256=ATTESTATION_DIGEST,
            legacy_state_digest="c" * 64,
        )


def test_topology_and_rollback_receipts_bind_every_artifact_without_start_authority() -> None:
    value, configs, plists = _built()
    for row in value["brokers"]:
        assert row["config_sha256"] == hashlib.sha256(configs[row["slot_id"]]).hexdigest()
        assert row["plist_sha256"] == hashlib.sha256(plists[row["slot_id"]]).hexdigest()
        assert row["attestation_sha256"] == ATTESTATION_DIGEST
    rollback = topology.build_rollback_contract(topology=value)
    assert rollback["start_authority"] is False
    assert rollback["delete_authority"] is False
    assert rollback["postcondition"] == "all_h0_labels_disabled_unloaded_socket_nodes_absent"
    assert len(rollback["labels"]) == 3
    assert len(rollback["movable_artifacts"]) == 9
    assert "credentials" in rollback["preserve"]
