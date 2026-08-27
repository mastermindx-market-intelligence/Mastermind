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


@pytest.mark.skipif(not SYSTEM_PYTHON.is_file(), reason="system Python is unavailable")
def test_python39_runs_v2_manifest_inventory_closure_intent_receipt_and_recovery(
    tmp_path: Path,
) -> None:
    probe = tmp_path / "python39-capacity-probe.py"
    probe.write_text(
        """
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1])
workspace = Path(sys.argv[2])
workspace.mkdir()
sys.path.insert(0, str(root))
from ops.executive_os import capacity_host_artifacts as artifacts
from ops.executive_os import capacity_source_contract as contract

repository = workspace / "source"
repository.mkdir()
environment = {
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    "LANG": "C",
    "LC_ALL": "C",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
}

def git(*arguments):
    completed = subprocess.run(
        ["/usr/bin/git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        env=environment,
    )
    return completed.stdout.decode("utf-8").strip()

git("init", "-q")
git("config", "user.name", "Fixture")
git("config", "user.email", "fixture@example.invalid")
for index, relative in enumerate(contract.PRODUCER_MATERIAL_PATHS):
    path = repository / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("material-%d\\n" % index, encoding="utf-8")
    if relative.startswith("scripts/"):
        path.chmod(0o755)
history = repository / "docs/nonmaterial-history.txt"
history.parent.mkdir(parents=True, exist_ok=True)
history.write_text("old\\n", encoding="utf-8")
git("add", "--all")
git("commit", "-qm", "fixture parent")
history.write_text("new\\n", encoding="utf-8")
git("add", "--all")
git("commit", "-qm", "fixture complete")
commit = git("rev-parse", "HEAD")
artifacts.PRODUCER_COMMIT = commit
contract.PRODUCER_COMMIT = commit

transport = workspace / "transport.zip"
manifest = artifacts.build_source_transport_v2(repository, transport, commit=commit)
rows = artifacts.enumerate_reachable_objects(repository, commit)
expected_inventory = b"".join(
    ("%s %s %d\\n" % (row.oid, row.object_type, row.size)).encode("ascii")
    for row in rows
)
assert manifest["object_count"] == len(rows)
assert manifest["object_inventory_sha256"] == hashlib.sha256(expected_inventory).hexdigest()

installed = workspace / "installed"
artifacts.materialize_source_transport_v2(transport, installed, expected_commit=commit)
evidence = artifacts.verify_complete_repository(installed, manifest)
assert evidence.object_count == manifest["object_count"]
assert evidence.object_inventory_sha256 == manifest["object_inventory_sha256"]

repair_commit = "d" * 40
intent = artifacts.build_source_repair_intent(
    source_closure_repair_commit=repair_commit,
    generation_repair_commit=repair_commit,
    expected_uid=0,
    expected_gid=0,
    filesystem_device=workspace.stat().st_dev,
    observed_old_source_tree_sha256="3" * 64,
    candidate_transport_sha256=hashlib.sha256(transport.read_bytes()).hexdigest(),
    candidate_transport_manifest_sha256=hashlib.sha256(
        artifacts.canonical_json(manifest)
    ).hexdigest(),
    candidate_object_count=evidence.object_count,
    candidate_object_inventory_sha256=evidence.object_inventory_sha256,
    candidate_source_tree_sha256=evidence.source_tree_sha256,
)
receipt = artifacts.build_source_repair_receipt(
    intent=intent,
    archived_generation_tree_sha256="6" * 64,
    new_source_config_digest="7" * 64,
    new_component_manifest_digest="8" * 64,
)
assert contract.validate_source_repair_intent(intent) == intent
assert contract.validate_source_repair_receipt(receipt, intent=intent) == receipt

publication = workspace / "publication"
publication.mkdir(mode=0o700)
target = publication / "source-repair-intent.json"
candidate = publication / ".source-repair-intent.json.candidate"
payload = artifacts.canonical_json(intent) + b"\\n"
candidate.write_bytes(payload[: len(payload) // 2])
candidate.chmod(0o400)
artifacts._publish_resumable_canonical_file(
    target,
    payload,
    mode=0o400,
    expected_uid=os.getuid(),
)
assert target.read_bytes() == payload
assert not candidate.exists()
print(json.dumps({"schema": manifest["schema_version"], "status": "pass"}, sort_keys=True))
""",
        encoding="utf-8",
    )
    completed = _system_python(str(probe), str(ROOT), str(tmp_path / "workspace"))
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "schema": "mastermind.capacity_source_transport/v2",
        "status": "pass",
    }
