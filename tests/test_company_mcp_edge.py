"""Immutable SDK edge publication and distinct capability boundaries."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
from types import SimpleNamespace

import pytest

from ops.executive_os import company_mcp_edge as edge
from control_plane.executive_agent_capabilities import (
    CapabilityPolicyError, COMPANY_EXECUTION_PROFILE, COMPANY_MCP_ARGS,
    ExecutionCapabilityRegistry,
)

ROOT = Path(__file__).resolve().parents[1]


def policy():
    return json.loads((ROOT / "config/executive_agent_capabilities.json").read_text())


def test_company_is_a_distinct_closed_profile():
    registry = ExecutionCapabilityRegistry.load()
    ordinary = registry.profiles["operator.appserver.interactive.v1"]
    company = registry.profiles[COMPANY_EXECUTION_PROFILE]
    assert not company.enabled  # Host admission owner is a separate reviewed stage.
    assert ordinary.mcp_servers == ()
    assert company.mcp_servers == ("company-consultation-mcp-v1",)
    assert company.skills == company.plugins == company.resource_grants == ()
    grant = company.mcp_server_grants[0]
    assert grant.args == COMPANY_MCP_ARGS
    assert grant.config_name == "company-consultation-v1"
    assert ordinary.expected_config_digest != company.expected_config_digest


@pytest.mark.parametrize("field,value", [
    ("command", "/tmp/python"), ("args", ["-c", "pass"]),
    ("config_name", "ambient"), ("transport", "streamable-http"),
    ("auth_status", "bearerToken"), ("server_identity", "different"),
    ("server_version", "2.0.0"), ("enabled_tools", ["company.consult"]),
    ("tool_schema_digest", "f" * 64), ("default_tools_approval_mode", "prompt"),
])
def test_company_grant_refuses_binding_drift(tmp_path, field, value):
    raw = policy()
    raw["mcp_servers"]["company-consultation-mcp-v1"][field] = value
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(CapabilityPolicyError):
        ExecutionCapabilityRegistry.load(path)


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    source = tmp_path / "releases" / ("a" * 40)
    source.mkdir(parents=True)
    root = tmp_path / "mcp-runtimes" / source.name
    root.mkdir(parents=True)
    (root / "bin").mkdir()
    (root / "bin/python3.12").write_bytes(b"attested executable")
    (root / "bin/python3.12").chmod(0o555)
    for name in ("python", "python3"):
        (root / "bin" / name).symlink_to("python3.12")
    (root / "bin").chmod(0o555)
    root.chmod(0o555)
    monkeypatch.setattr(edge, "SOURCE", source)
    monkeypatch.setattr(edge, "SYSTEM", tmp_path)
    monkeypatch.setattr(edge, "CONFIG", tmp_path / "edge.json")
    monkeypatch.setattr(edge, "sealed", lambda path, **kwargs: Path(path))
    monkeypatch.setattr(edge, "_security", lambda: lambda *args, **kwargs: False)
    actual = Path.lstat
    def root_owned(path, *args, **kwargs):
        values = list(actual(path, *args, **kwargs))
        values[4] = values[5] = 0
        return os.stat_result(values)
    monkeypatch.setattr(Path, "lstat", root_owned)
    evidence = {"release_sha": source.name, "tree_sha": "b" * 40,
                "source_manifest_sha256": "c" * 64, "lock_sha256": "d" * 64}
    monkeypatch.setattr(edge, "source_evidence", lambda: evidence)
    monkeypatch.setattr(edge, "verify_base", lambda base: None)
    entries = edge.inventory(root)
    raw = dict(schema=edge.SCHEMA, source=evidence, base={"fixture": True},
               control_uid=450, worker_uid=451,
               inventory_sha256=hashlib.sha256(edge.encoded(entries)).hexdigest(),
               inventory_entries=len(entries), pip_check_passed=True)
    receipt = root / edge.RECEIPT
    root.chmod(0o755)
    receipt.write_bytes(edge.encoded(raw)); receipt.chmod(0o444)
    root.chmod(0o555)
    config = dict(schema=edge.SCHEMA, release_sha=source.name, control_uid=450,
                  worker_uid=451, receipt_sha256=edge.digest(receipt),
                  entry_sha256=edge.digest(Path(edge.__file__)))
    return root, config, raw


def test_runtime_receipt_binds_actual_tree(runtime):
    root, config, _ = runtime
    assert edge.verify(config)[0] == root


@pytest.mark.parametrize("change", ["bytes", "mode", "link", "extra", "incomplete", "receipt", "uid", "source"])
def test_runtime_refuses_drift_before_sdk_load(runtime, change):
    root, config, raw = runtime
    root.chmod(0o755)
    (root / "bin").chmod(0o755)
    if change == "bytes":
        (root / "bin/python3.12").chmod(0o755)
        (root / "bin/python3.12").write_bytes(b"replaced")
        (root / "bin/python3.12").chmod(0o555)
    elif change == "mode":
        (root / "bin/python3.12").chmod(0o755)
    elif change == "link":
        (root / "bin/python").unlink()
        (root / "bin/python").symlink_to("/tmp/foreign")
    elif change == "extra":
        (root / "injected.py").write_bytes(b"pass")
        (root / "injected.py").chmod(0o444)
    elif change == "incomplete":
        (root / edge.INCOMPLETE).write_bytes(b"pending")
    elif change == "receipt":
        (root / edge.RECEIPT).chmod(0o644)
        (root / edge.RECEIPT).write_bytes(b"{}")
        (root / edge.RECEIPT).chmod(0o444)
    elif change == "uid":
        config["worker_uid"] = 452
    else:
        config["release_sha"] = "e" * 40
    root.chmod(0o555)
    (root / "bin").chmod(0o555)
    with pytest.raises(edge.EdgeError):
        edge.verify(config)


def test_acl_and_special_nodes_refused(runtime, monkeypatch):
    root, _, _ = runtime
    monkeypatch.setattr(edge, "_security", lambda: lambda path, **kwargs: path.name == "python3.12")
    with pytest.raises(edge.EdgeError, match="custody"):
        edge.inventory(root)
    monkeypatch.setattr(edge, "_security", lambda: lambda *args, **kwargs: False)
    root.chmod(0o755)
    os.mkfifo(root / "unexpected-pipe", 0o444)
    root.chmod(0o555)
    with pytest.raises(edge.EdgeError, match="unsupported"):
        edge.inventory(root)


def test_publication_is_atomic_and_never_overwrites(tmp_path):
    tmp_path = tmp_path / "publication"
    tmp_path.mkdir()
    target = tmp_path / "edge.json"
    edge.publish(target, {"first": True})
    before = target.read_bytes()
    assert stat.S_IMODE(target.stat().st_mode) == 0o444
    assert target.stat().st_nlink == 1
    with pytest.raises(edge.EdgeError, match="already exists"):
        edge.publish(target, {"second": True})
    assert target.read_bytes() == before
    assert list(tmp_path.iterdir()) == [target]


def test_failed_python_owner_prevents_any_runtime_mutation(tmp_path, monkeypatch):
    tmp_path = tmp_path / "provision"
    tmp_path.mkdir()
    monkeypatch.setattr(edge, "SYSTEM", tmp_path)
    monkeypatch.setattr(edge.os, "geteuid", lambda: 0)
    monkeypatch.setattr(edge.sys, "platform", "darwin")
    monkeypatch.setattr(edge, "source_evidence", lambda: {})
    seen = []
    def refuse(command):
        seen.append(command)
        raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(edge, "run", refuse)
    with pytest.raises(subprocess.CalledProcessError):
        edge.provision()
    assert seen == [["/bin/bash", edge.SOURCE / "ops/executive_os/provision-python-runtime.sh", "--verify-only"]]
    assert list(tmp_path.iterdir()) == []


def test_sdk_exec_uses_only_exact_venv_isolated_interpreter(runtime, monkeypatch):
    root, config, _ = runtime
    monkeypatch.setattr(edge, "read_config", lambda: config)
    monkeypatch.setattr(edge.sys, "flags", SimpleNamespace(isolated=1))
    monkeypatch.setattr(edge.sys, "dont_write_bytecode", True)
    monkeypatch.setattr(edge.os, "geteuid", lambda: config["worker_uid"])
    calls = []
    class Executed(Exception):
        pass
    def execute(path, argv, env):
        calls.append((path, argv, env))
        raise Executed()
    monkeypatch.setattr(edge.os, "execve", execute)
    with pytest.raises(Executed):
        edge.main(["stdio"])
    python = root / "bin/python3.12"
    assert calls == [(python, [str(python), "-I", "-B", edge.__file__, "sdk-stdio"], edge.ENV)]
    monkeypatch.setattr(edge.os, "geteuid", lambda: 452)
    with pytest.raises(edge.EdgeError, match="worker UID"):
        edge.main(["stdio"])
    assert len(calls) == 1


@pytest.mark.parametrize("name", ["foreign.pth", "sitecustomize.py", "usercustomize.py", "cached.pyc", "__pycache__"])
def test_sdk_refuses_startup_hooks_before_site_processing(runtime, name):
    root, config, _ = runtime
    root.chmod(0o755)
    (root / name).write_bytes(b"import foreign")
    (root / name).chmod(0o444)
    root.chmod(0o555)
    with pytest.raises(edge.EdgeError, match="startup code"):
        edge.verify(config)


def test_sealed_accepts_normal_admin_group_ancestor_but_not_writable_ancestor(tmp_path, monkeypatch):
    ancestor = tmp_path / "Application Support"
    leaf = ancestor / "MastermindExecutive"
    leaf.mkdir(parents=True)
    monkeypatch.setattr(edge, "SYSTEM", leaf)
    monkeypatch.setattr(edge, "_security", lambda: lambda *args, **kwargs: False)
    actual = Path.lstat
    writable = False
    def observed(path, *args, **kwargs):
        values = list(actual(path, *args, **kwargs))
        values[4] = 0
        values[5] = 80 if path == ancestor else 0
        values[0] &= ~0o022
        if writable and path == ancestor:
            values[0] |= 0o020
        return os.stat_result(values)
    monkeypatch.setattr(Path, "lstat", observed)
    assert edge.sealed(leaf, directory=True) == leaf
    writable = True
    with pytest.raises(edge.EdgeError, match="custody"):
        edge.sealed(leaf, directory=True)


def test_incomplete_recovery_preserves_all_partial_bytes(tmp_path, monkeypatch):
    system = tmp_path / "system"
    root = system / "mcp-runtimes" / ("a" * 40)
    root.mkdir(parents=True)
    (root / edge.INCOMPLETE).write_text("partial")
    (root / "wheel-partial").write_bytes(b"preserved")
    monkeypatch.setattr(edge, "SYSTEM", system)
    monkeypatch.setattr(edge, "SOURCE", Path("a" * 40))
    monkeypatch.setattr(edge, "sealed", lambda path, **kwargs: Path(path))
    edge._archive_incomplete(root)
    assert not root.exists()
    archives = list((system / "mcp-runtime-archive").iterdir())
    assert len(archives) == 1
    assert (archives[0] / edge.INCOMPLETE).read_text() == "partial"
    assert (archives[0] / "wheel-partial").read_bytes() == b"preserved"


@pytest.mark.parametrize("contents", ["empty", "foreign"])
def test_recovery_covers_only_exact_empty_pre_marker_window(tmp_path, monkeypatch, contents):
    system = tmp_path / "system"
    root = system / "mcp-runtimes" / ("a" * 40)
    root.mkdir(parents=True, mode=0o700)
    root.chmod(0o700)
    if contents == "foreign":
        (root / "unknown").write_bytes(b"preserve without moving")
    monkeypatch.setattr(edge, "SYSTEM", system)
    monkeypatch.setattr(edge, "SOURCE", Path("a" * 40))
    monkeypatch.setattr(edge, "sealed", lambda path, **kwargs: Path(path))
    if contents == "foreign":
        with pytest.raises(edge.EdgeError, match="pre-marker"):
            edge._archive_incomplete(root)
        assert (root / "unknown").exists()
    else:
        edge._archive_incomplete(root)
        assert not root.exists()
        assert len(list((system / "mcp-runtime-archive").iterdir())) == 1


def test_provision_restores_caller_umask_on_failure(monkeypatch):
    def fail(**kwargs):
        observed = os.umask(0o077)
        assert observed == 0o077
        raise edge.EdgeError("injected")
    monkeypatch.setattr(edge, "_provision", fail)
    previous = os.umask(0o022)
    try:
        with pytest.raises(edge.EdgeError, match="injected"):
            edge.provision()
        assert os.umask(0o022) == 0o022
    finally:
        os.umask(previous)


def test_publication_persists_mode_before_linking(tmp_path, monkeypatch):
    events = []
    chmod, fsync, link = os.fchmod, os.fsync, os.link
    def recorded_chmod(*args, **kwargs):
        events.append("chmod")
        return chmod(*args, **kwargs)
    def recorded_fsync(*args, **kwargs):
        events.append("fsync")
        return fsync(*args, **kwargs)
    def recorded_link(*args, **kwargs):
        events.append("link")
        return link(*args, **kwargs)
    monkeypatch.setattr(edge.os, "fchmod", recorded_chmod)
    monkeypatch.setattr(edge.os, "fsync", recorded_fsync)
    monkeypatch.setattr(edge.os, "link", recorded_link)
    edge.publish(tmp_path / "mode-receipt.json", {"sealed": True})
    assert events[:3] == ["chmod", "fsync", "link"]
