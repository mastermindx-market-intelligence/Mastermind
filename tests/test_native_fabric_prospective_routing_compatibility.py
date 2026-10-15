"""Protect current protected-master prospective return vs native routing CLI integration.

Versioned source-only composition: never touches installed Fabric, provider accounts,
live credentials, leases, services or worker processes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "integrations/session_bridge/prospective_completion"
PATCHES = ROOT / "ops/native_fabric/routing_audit_20261013"
NATIVE_SUPPORT = ROOT / "integrations/session_bridge/native_broker_admission/remote_sub.sh.patch"


def _apply(root: Path, patch: Path, *args: str) -> None:
    result = subprocess.run(["git", "apply", *args, str(patch)], cwd=root,
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, f"{patch}: {result.stderr}"


def test_latest_protected_prospective_launcher_accepts_route_flags_and_native_dependency(tmp_path):
    """A unified patch must preserve original-parent collection and native support."""
    source = RELEASE / "candidate/remote_sub.sh"
    qualified = json.loads((RELEASE / "QUALIFICATION.json").read_text())
    expected = qualified["files"]["remote_sub.sh"]["postimage_sha256"]
    original = source.read_bytes()
    assert hashlib.sha256(original).hexdigest() == expected
    assert original.count(b'--task-class "remote-$MODE" --model "$MODEL"') == 3
    ext = tmp_path / "ext"
    ext.mkdir()
    target = ext / "remote_sub.sh"
    shutil.copyfile(source, target)
    _apply(tmp_path, PATCHES / "logical_job_priority.patch",
           "--include=ext/remote_sub.sh")
    _apply(tmp_path, PATCHES / "request_waiters/request_waiters_wiring.patch",
           "--include=ext/remote_sub.sh")
    _apply(tmp_path, NATIVE_SUPPORT, "--directory=ext")
    proposed = target.read_text()
    commands = [line for line in proposed.splitlines()
                if 'broker acquire ' in line or 'show_args "<broker>" acquire' in line]
    assert len(commands) == 3
    for command in commands:
        assert '--task-class "remote-$MODE"' in command
        assert '--job-class "${POOL_TASK_CLASS:-}"' in command
        assert '--request-id "$ID"' in command
        assert '--model "$MODEL"' in command

    support = proposed.split("SUPPORT_FILES=(", 1)[1].split(")", 1)[0].split()
    assert support.count("lease_broker.py") == 1
    assert support.count("native_broker_admission.py") == 1
    # Prospective read/collect never acquires another provider lease.
    collection = 'if [ "${1:-}" = "--collect-existing" ]; then'
    assert proposed.count(collection) == 1
    assert proposed.index(collection) < proposed.index('broker acquire ')
    assert original.decode().split(collection, 1)[1].split("\nfi", 1)[0] == (
        proposed.split(collection, 1)[1].split("\nfi", 1)[0])
    # The external broker override remains separately version-gated at rollout.
    assert '"$REMOTE_SUB_BROKER_CMD" "$@"' in proposed
    syntax = subprocess.run(["bash", "-n", str(target)], capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr


def test_prospective_candidate_and_routing_share_original_transport_baseline():
    qualified = json.loads((RELEASE / "BASE.json").read_text())
    routed = json.loads((PATCHES / "manifest.json").read_text())
    assert qualified["remote_sub.sh"] == routed["files"]["remote_sub.sh"]["sha256"]
    assert qualified["fabric_task.py"] == routed["files"]["fabric_task.py"]["sha256"]
    # Matching historical preimages do not imply current installed bytes or writer custody.
