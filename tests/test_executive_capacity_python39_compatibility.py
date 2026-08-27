from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from ops.executive_os import capacity_source_contract as contract


ROOT = Path(__file__).resolve().parents[1]
SYSTEM_PYTHON = Path("/usr/bin/python3")
TOPOLOGY = ROOT / "ops/executive_os/capacity_broker_topology.py"
CONTRACT = ROOT / "ops/executive_os/capacity_source_contract.py"
TEMPLATE = ROOT / "ops/executive_os/com.mastermind.executive.worker.codex.plist.template"
RELEASE = Path("/Library/Application Support/MastermindExecutive/releases") / ("a" * 40)
GIDS = {
    "codex-pro-01": [12, 61, 100, 396],
    "codex-pro-02": [12, 61, 100, 396],
    "codex-pro-03": [12, 61, 100, 396],
}


def _system_python(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SYSTEM_PYTHON), "-I", "-S", "-B", *args],
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(not SYSTEM_PYTHON.is_file(), reason="system Python is unavailable")
def test_h0_topology_and_contract_clis_run_with_macos_system_python(
    tmp_path: Path,
) -> None:
    gids_path = tmp_path / "supplementary-gids.json"
    gids_path.write_text(json.dumps(GIDS, sort_keys=True), encoding="utf-8")
    topology_root = tmp_path / "topology"
    rendered_topology = _system_python(
        str(TOPOLOGY),
        "--release-root",
        str(RELEASE),
        "--template",
        str(TEMPLATE),
        "--attestation-sha256",
        "b" * 64,
        "--supplementary-gids-json",
        str(gids_path),
        "--legacy-state-digest",
        "c" * 64,
        "--destination",
        str(topology_root),
    )
    assert rendered_topology.returncode == 0, rendered_topology.stderr

    topology = json.loads((topology_root / "broker-topology.json").read_text())
    rollback = json.loads((topology_root / "rollback-contract.json").read_text())
    assert [row["slot_id"] for row in topology["brokers"]] == [
        "codex-pro-01",
        "codex-pro-02",
        "codex-pro-03",
    ]
    assert [row["capacity_capability_id"] for row in topology["brokers"]] == [
        "codex_account",
        "codex_account_2",
        "codex_account_3",
    ]
    assert topology["runtime_composition"] == "held_for_cf2_i_b"
    assert topology["worker_execution"] == "held"
    assert len(list(topology_root.glob("worker-*.json"))) == 3
    assert len(list(topology_root.glob("*.plist"))) == 3
    assert len(rollback["movable_artifacts"]) == 9
    assert rollback["start_authority"] is False

    rendered_contract = _system_python(
        str(CONTRACT),
        "render",
        "--material-source-digest",
        contract.PRODUCER_MATERIAL_SOURCE_DIGEST,
        "--pyyaml-record-sha256",
        contract.PYYAML_RECORD_SHA256,
        "--runtime-tree-sha256",
        contract.RUNTIME_TREE_SHA256,
        "--mastermind-commit",
        "d" * 40,
        "--broker-topology-digest",
        hashlib.sha256((topology_root / "broker-topology.json").read_bytes()).hexdigest(),
        "--rollback-contract-digest",
        hashlib.sha256((topology_root / "rollback-contract.json").read_bytes()).hexdigest(),
        "--rollback-drill-receipt-digest",
        "e" * 64,
    )
    assert rendered_contract.returncode == 0, rendered_contract.stderr
    rendered = json.loads(rendered_contract.stdout)
    assert [row["slot_id"] for row in rendered["components"]["inventory_config"]["realms"]] == [
        "codex-pro-01",
        "codex-pro-02",
        "codex-pro-03",
    ]
    assert rendered["host_receipt"]["outcome"] == "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED"

    components_path = tmp_path / "components.json"
    config_path = tmp_path / "source-config.json"
    receipt_path = tmp_path / "host-preparation-receipt.json"
    components_path.write_text(json.dumps(rendered["components"]), encoding="utf-8")
    config_path.write_text(json.dumps(rendered["source_config"]), encoding="utf-8")
    receipt_path.write_text(json.dumps(rendered["host_receipt"]), encoding="utf-8")
    verified_contract = _system_python(
        str(CONTRACT),
        "verify",
        "--components",
        str(components_path),
        "--config",
        str(config_path),
        "--receipt",
        str(receipt_path),
    )
    assert verified_contract.returncode == 0, verified_contract.stderr
    assert json.loads(verified_contract.stdout) == rendered
