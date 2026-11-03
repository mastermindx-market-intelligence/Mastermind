"""Persistent Browser runtime generation, incomplete evidence and source binding."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from ops.executive_os import company_mcp_edge as owner
from ops.executive_os import workbench_mcp_runtime as runtime


@pytest.fixture
def qualified(tmp_path, monkeypatch):
    source = tmp_path / "releases" / ("a" * 40)
    (source / "ops/executive_os").mkdir(parents=True)
    (source / runtime.ENTRY_RELATIVE).write_bytes(b"qualified entry")
    root = tmp_path / "workbench-mcp-runtimes/501" / source.name
    (root / "bin").mkdir(parents=True)
    (root / "bin/python3.12").write_bytes(b"attested Python")
    (root / "bin/python3.12").chmod(0o555)
    for name in ("python", "python3"):
        (root / "bin" / name).symlink_to("python3.12")
    (root / "bin").chmod(0o555)
    root.chmod(0o555)
    monkeypatch.setattr(owner, "SYSTEM", tmp_path)
    monkeypatch.setattr(owner, "SOURCE", source)
    monkeypatch.setattr(owner, "sealed", lambda path, **kwargs: Path(path))
    monkeypatch.setattr(owner, "_security", lambda: lambda *args, **kwargs: False)
    actual = Path.lstat
    def root_owned(path, *args, **kwargs):
        values = list(actual(path, *args, **kwargs))
        values[4] = values[5] = 0
        return os.stat_result(values)
    monkeypatch.setattr(Path, "lstat", root_owned)
    evidence = {"release_sha": source.name, "tree_sha": "b" * 40,
                "source_manifest_sha256": "c" * 64, "lock_sha256": "d" * 64}
    def source_evidence(selected, lock):
        assert selected == source
        assert lock == runtime.LOCK_RELATIVE
        return evidence
    monkeypatch.setattr(owner, "_source_evidence_at", source_evidence)
    monkeypatch.setattr(owner, "verify_base", lambda base: None)
    entries = owner.inventory(root, kind="workbench-browser")
    raw = dict(schema=runtime.SCHEMA, source=evidence, base={"fixture": True},
               service_uid=501, inventory_sha256=hashlib.sha256(owner.encoded(entries)).hexdigest(),
               inventory_entries=len(entries), pip_check_passed=True)
    root.chmod(0o755)
    receipt = root / runtime.RECEIPT
    receipt.write_bytes(owner.encoded(raw))
    receipt.chmod(0o444)
    root.chmod(0o555)
    binding = runtime._binding(source, root, 501)
    return SimpleNamespace(source=source, root=root, receipt=receipt, raw=raw,
                           binding=binding, evidence=evidence)


def test_distinct_workbench_runtime_verifies_complete_generation(qualified):
    value = runtime.verify(qualified.source.name, 501, binding=qualified.binding)
    assert value["runtime_root"] == str(qualified.root)
    assert value["service_uid"] == 501
    assert value["schema"] != owner.SCHEMA
    assert value["python_executable"] == str(qualified.root / "bin/python3.12")


@pytest.mark.parametrize("change", ["kind", "uid", "source", "entry", "receipt", "extra", "tree", "marker"])
def test_runtime_refuses_cross_product_or_changed_generation(qualified, change):
    binding = dict(qualified.binding)
    if change == "kind":
        binding["schema"] = owner.SCHEMA
    elif change == "uid":
        binding["service_uid"] = 502
    elif change == "source":
        binding["release_sha"] = "f" * 40
    elif change == "entry":
        (qualified.source / runtime.ENTRY_RELATIVE).write_bytes(b"changed")
    elif change == "receipt":
        binding["receipt_sha256"] = "0" * 64
    elif change == "extra":
        binding["control_uid"] = 450
    elif change == "tree":
        executable = qualified.root / "bin/python3.12"
        executable.chmod(0o755)
        executable.write_bytes(b"changed Python")
        executable.chmod(0o555)
    elif change == "marker":
        qualified.root.chmod(0o755)
        (qualified.root / owner.INCOMPLETE).write_bytes(b"incomplete")
    with pytest.raises(owner.EdgeError):
        runtime.verify(qualified.source.name, 501, binding=binding)


@pytest.mark.parametrize("uid", [0, 450, True, "501", -1])
def test_runtime_requires_real_browser_user_namespace(uid):
    with pytest.raises(owner.EdgeError):
        runtime._identity("a" * 40, uid)


def test_materializer_cannot_cross_company_namespace(qualified, monkeypatch):
    calls = []
    monkeypatch.setattr(owner, "run", lambda command: calls.append(command))
    with pytest.raises(owner.EdgeError):
        owner._materialize_sdk(owner.SYSTEM / "mcp-runtimes" / qualified.source.name,
                               qualified.evidence, {"service_uid": 501}, kind="workbench-browser")
    with pytest.raises(owner.EdgeError):
        owner._materialize_sdk(qualified.root, qualified.evidence,
                               {"control_uid": 450, "worker_uid": 451}, kind="company")
    assert calls == []


def test_failed_build_retains_marker_without_publishing_receipt(qualified, monkeypatch):
    root = owner.SYSTEM / "workbench-mcp-runtimes/502" / qualified.source.name
    root.parent.mkdir()
    calls = []
    def fail(command):
        calls.append(command)
        raise RuntimeError("synthetic install failure")
    monkeypatch.setattr(owner, "run", fail)
    with pytest.raises(RuntimeError, match="synthetic"):
        owner._materialize_sdk(root, qualified.evidence, {"service_uid": 502}, kind="workbench-browser")
    assert len(calls) == 1
    assert (root / owner.INCOMPLETE).read_bytes() == b"build in progress\n"
    assert not (root / runtime.RECEIPT).exists()


def test_explicit_incomplete_recovery_archives_original_inode(qualified):
    root = owner.SYSTEM / "workbench-mcp-runtimes/502" / qualified.source.name
    root.mkdir(parents=True, mode=0o700)
    marker = root / owner.INCOMPLETE
    marker.write_bytes(b"retained partial build")
    marker.chmod(0o600)
    original = root.stat()
    result = runtime._archive_incomplete(root, 502)
    archived = Path(result["archive"])
    assert not root.exists()
    assert (archived.stat().st_dev, archived.stat().st_ino) == (original.st_dev, original.st_ino)
    assert (archived / owner.INCOMPLETE).read_bytes() == b"retained partial build"


def test_recovery_refuses_a_complete_tree(qualified):
    with pytest.raises(owner.EdgeError, match="incomplete"):
        runtime._archive_incomplete(qualified.root, 501)


def test_launch_argv_has_fixed_isolated_source_and_no_selectable_config(qualified):
    argv = runtime.launch_argv(qualified.source.name, 501)
    assert argv[:5] == [str(owner.BASE_PYTHON), "-I", "-S", "-B", "-c"]
    assert argv[5] == runtime.BOOTSTRAP
    assert argv[6:] == [str(qualified.source), "serve", "--release", qualified.source.name]
    assert "--service-uid" not in argv and "--config" not in argv


@pytest.mark.parametrize("source_pin,python_pin", [("/fixed/source", None), (None, "/fixed/python")])
def test_service_runtime_pins_must_be_a_pair(monkeypatch, source_pin, python_pin):
    from integrations.workbench_action_mcp import service
    monkeypatch.setattr(service, "load_service_config", lambda path: pytest.fail("must refuse before config read"))
    assert service.run_configured_service("/unused", expected_browser_source=source_pin,
                                          expected_browser_python=python_pin) == 2


@pytest.mark.parametrize("browser", [
    None,
    SimpleNamespace(source_root="/fixed/source", python_executable="/fixed/python"),
])
def test_persistent_serve_refuses_absent_or_legacy_browser(monkeypatch, browser):
    from integrations.workbench_action_mcp import service
    monkeypatch.setattr(service, "load_service_config", lambda path: SimpleNamespace(browser=browser))
    monkeypatch.setattr(service, "run_service", lambda config: pytest.fail("no service effect"))
    assert service.run_configured_service("/unused", expected_browser_source="/fixed/source",
                                          expected_browser_python="/fixed/python") == 2


def test_runtime_pins_bind_one_loaded_snapshot(monkeypatch):
    from integrations.workbench_action_mcp import service
    browser = service.BrowserLinkServiceConfig("/fixed/source", "/fixed/python", "/r", "/o", 1, "/p")
    selected = SimpleNamespace(browser=browser)
    loads = []
    def load(path):
        loads.append(path)
        return selected
    async def run(config):
        assert config is selected
        return 0
    monkeypatch.setattr(service, "load_service_config", load)
    monkeypatch.setattr(service, "run_service", run)
    assert service.run_configured_service("/config", expected_browser_source="/fixed/source",
                                          expected_browser_python="/fixed/python") == 0
    assert loads == ["/config"]


@pytest.mark.parametrize("failure", [None, "release", "install"])
def test_sdk_serve_passes_verified_install_acquisition_once(qualified, monkeypatch, failure):
    from integrations.studio_direct_mcp import workbench_host_service as host
    from integrations.workbench_action_mcp import service
    from integrations.workbench_action_mcp.acquisition import projection
    selected = runtime.verify(qualified.source.name, 501, binding=qualified.binding)
    monkeypatch.setattr(runtime, "verify", lambda sha, uid: selected)
    monkeypatch.setattr(runtime.os, "geteuid", lambda: 501)
    monkeypatch.setattr(runtime, "sys", SimpleNamespace(
        flags=SimpleNamespace(isolated=True, no_site=True), dont_write_bytecode=True,
        executable=str(qualified.root / "bin/python3.12"), base_prefix=str(owner.BASE_PYTHON.parents[1]), path=[]))
    monkeypatch.setattr(runtime, "configuration_path", lambda uid: Path("/fixed/config.json"))
    target = object()
    monkeypatch.setattr(host, "target", lambda: target)
    plan = {"release_sha": "f" * 40 if failure == "release" else qualified.source.name,
            "config_sha256": "c" * 64, "persistent": {"exact": "directories-and-key"},
            "dependencies": {"exact": "consumed-documents"}}
    def installed(value):
        assert value is target
        if failure == "install":
            raise host.LifecycleError("WORKBENCH_INSTALL_REFUSED")
        return {"plan": plan}, object()
    monkeypatch.setattr(host, "_verify_install", installed)
    calls = []
    monkeypatch.setattr(service, "run_configured_service", lambda *args, **kwargs: calls.append((args, kwargs)) or 0)
    if failure:
        with pytest.raises((owner.EdgeError, host.LifecycleError)):
            runtime.main(["sdk-serve", "--release", qualified.source.name])
        assert calls == []
    else:
        assert runtime.main(["sdk-serve", "--release", qualified.source.name]) == 0
        assert calls == [(("/fixed/config.json",), {
            "expected_browser_source": str(qualified.source),
            "expected_browser_python": str(qualified.root / "bin/python3.12"),
            "expected_acquisition": projection(plan["config_sha256"], plan["persistent"], plan["dependencies"])})]
