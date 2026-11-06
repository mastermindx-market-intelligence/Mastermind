"""Join source-qualified native task, shell transport and Broker CLI/claim.

No provider/installed host/credential/real lease/SSH/work effect. Uses only the
existing protected prospective and synthetic native-broker test fixtures.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import socket
import subprocess

import pytest

from tests.test_native_fabric_protected_broker_composition import (
    BUNDLE, _apply, complete_broker,
)
from tests.test_native_fabric_quota_admission_composition import current_candidate
from tests.test_native_fabric_quota_pinned_reclaim_composition import joined_candidate
from tests.test_native_fabric_advisory_reset_boundary import advisory_reader
from tests.test_native_fabric_quota_waiter_transition import quota_yield_candidate
from tests.test_native_fabric_pinned_ready_memo import optimized_module

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "integrations/session_bridge/prospective_completion"


@pytest.fixture(autouse=True)
def no_provider_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("cross-module ABI test attempted network")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture
def routed_sources(tmp_path):
    qualified = json.loads((RELEASE / "QUALIFICATION.json").read_text())
    root = tmp_path / "transport-source"
    ext = root / "ext"
    ext.mkdir(parents=True)
    task = ext / "fabric_task.py"
    launch = ext / "remote_sub.sh"
    original_task = RELEASE / "candidate/fabric_task.py"
    original_launch = RELEASE / "candidate/remote_sub.sh"
    assert hashlib.sha256(original_task.read_bytes()).hexdigest() == qualified["files"]["fabric_task.py"]["postimage_sha256"]
    assert hashlib.sha256(original_launch.read_bytes()).hexdigest() == qualified["files"]["remote_sub.sh"]["postimage_sha256"]
    shutil.copyfile(original_task, task)
    shutil.copyfile(original_launch, launch)
    _apply(root, BUNDLE / "protected_composition/selector_after_prospective.patch")
    _apply(root, BUNDLE / "logical_job_priority.patch", "--include=ext/remote_sub.sh")
    _apply(root, BUNDLE / "request_waiters/request_waiters_wiring.patch",
           "--include=ext/remote_sub.sh")
    _apply(root, BUNDLE / "protected_composition/native_support_after_prospective.patch")
    syntax = subprocess.run(["bash", "-n", str(launch)], capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr
    return task.read_text(), launch.read_text()


def test_compatible_controller_launcher_broker_wire(routed_sources, optimized_module):
    task, launcher = routed_sources
    assert 'p_preview = sub.add_parser("preview"' in task
    assert 'p_request.add_argument("--host", default="auto"' in task
    assert 'host=selected_host, pool=pool' in task
    assert 'env["POOL_TASK_CLASS"] = task_class' in task
    assert 'RECOVERABLE_RETURN_PINNED_HOST_REFUSED' in task
    dollar = chr(36)
    commands = [line for line in launcher.splitlines()
                if 'broker acquire ' in line or 'show_args "<broker>" acquire' in line]
    assert len(commands) == 3
    for command in commands:
        flags = [
            '--task-class "remote-' + dollar + 'MODE"',
            '--job-class "' + dollar + '{POOL_TASK_CLASS:-}"',
            '--request-id "' + dollar + 'ID"',
            '--model "' + dollar + 'MODEL"',
        ]
        assert all(flag in command for flag in flags), command
    assert "POOL_ORCHESTRATOR_ID" in launcher and "CLAUDE_SESSION_ID" in launcher
    assert '"$REMOTE_SUB_BROKER_CMD" "$@"' in launcher
    closure = launcher.split("SUPPORT_FILES=(", 1)[1].split(")", 1)[0].split()
    for name in ("lease_broker.py", "native_broker_admission.py", "pick.py",
                 "pool_ledger.py", "remote_sub_exec.py"):
        assert closure.count(name) == 1
    import inspect
    assert {"job_class", "request_id"} <= set(
        inspect.signature(optimized_module.Broker.acquire).parameters)
    assert "native_binding" in inspect.signature(
        optimized_module.Broker._try_acquire).parameters


def test_original_parent_read_branch_precedes_acquire(routed_sources):
    task, launcher = routed_sources
    start = 'if [ "' + chr(36) + '{1:-}" = "--collect-existing" ]; then'
    assert launcher.count(start) == 1
    branch = launcher.split(start, 1)[1].split("\nfi", 1)[0]
    assert "broker acquire" not in branch
    assert launcher.index(start) < launcher.index("broker acquire ")
    assert "collect-prospective" in task and "original_delivery_collector.begin_completion" in task
    assert "pass_fds" in task and '"--recoverable-return"' in task


def test_broker_cli_forwards_stable_id_and_logical_priority(
    optimized_module, monkeypatch, capsys
):
    seen = []
    class Recorder:
        def acquire(self, **kwargs):
            seen.append(kwargs)
            return optimized_module.AcquireResult(
                ok=True, lease_id="synthetic-lease", account="synthetic",
                orchestrator_id=kwargs["orchestrator_id"], pool=kwargs["pool"],
            )
    monkeypatch.setattr(optimized_module, "default_broker", lambda: Recorder())
    code = optimized_module.main([
        "acquire", "--orchestrator-id", "original-root", "--pool", "minimax",
        "--task-class", "remote-minimax", "--job-class", "heal",
        "--request-id", "stable-child", "--model", "MiniMax-M3",
        "--host", "synthetic", "--pid", "1234", "--ttl", "180", "--wait", "0",
    ])
    assert code == 0 and "LEASE=synthetic-lease" in capsys.readouterr().out
    assert len(seen) == 1
    expected = {"orchestrator_id": "original-root", "task_class": "remote-minimax",
                "job_class": "heal", "request_id": "stable-child",
                "model": "MiniMax-M3", "host": "synthetic"}
    for key, value in expected.items():
        assert seen[0][key] == value


def test_temporary_real_broker_grant_keeps_root_and_native_fence(optimized_module, tmp_path):
    config = tmp_path / "accounts.yaml"
    config.write_text(json.dumps({"providers": {"minimax": {"enabled": True,
        "accounts": [{"name": "synthetic", "per_account_cap": 2}]}}}))
    broker = optimized_module.Broker(
        db_path=str(tmp_path / "leases.sqlite"),
        lock_path=str(tmp_path / "leases.lock"),
        accounts_path=str(config), status_json=str(tmp_path / "status.json"),
        hosts_path=str(tmp_path / "hosts.json"), grok_marker=str(tmp_path / "absent"),
        this_host="synthetic", external_gates=False, check_pid=False,
        now_fn=lambda: 2_000_000_000.0,
    )
    granted = broker.acquire("original-root", "minimax",
                             task_class="remote-minimax", job_class="heal",
                             request_id="stable-child", model="MiniMax-M3", host="synthetic")
    assert granted.ok and granted.account == "synthetic"
    with broker._conn() as conn:
        row = conn.execute("SELECT * FROM leases WHERE id=?", (granted.lease_id,)).fetchone()
        assert row["orchestrator_id"] == "original-root"
        assert row["task_class"] == "remote-minimax"
        assert row["native_binding"] is None and row["native_key"] is None
    assert broker.release(granted.lease_id, "original-root")
