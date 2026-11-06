"""Join protected prospective original-parent return with the existing selector.

Source-only, no native worker, installed host, credential, lease, provider
request, admission, or new retry. Uses exact protected repository fixture.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "integrations/session_bridge/prospective_completion"
PATCH = ROOT / "ops/native_fabric/routing_audit_20261013/protected_composition/selector_after_prospective.patch"


@pytest.fixture
def composed(tmp_path):
    src = RELEASE / "candidate/fabric_task.py"
    qualified = json.loads((RELEASE / "QUALIFICATION.json").read_text())
    assert hashlib.sha256(src.read_bytes()).hexdigest() == qualified["files"]["fabric_task.py"]["postimage_sha256"]
    ext = tmp_path / "ext"
    ext.mkdir()
    dest = ext / "fabric_task.py"
    shutil.copyfile(src, dest)
    result = subprocess.run(["git", "apply", str(PATCH)], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    before = src.read_text()
    after = dest.read_text()
    ast.parse(after)
    def funcs(code):
        return {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(code).body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    old, new = funcs(before), funcs(after)
    assert set(new) - set(old) == {"_selection_host", "_selection_auto", "preview_route"}
    assert {name for name in old if old[name] != new[name]} == {"request", "main"}
    assert after.count("original_delivery_collector.completion_caller(") == before.count(
        "original_delivery_collector.completion_caller(") == 1
    assert after.count("original_delivery_collector.begin_completion(") == before.count(
        "original_delivery_collector.begin_completion(") == 1
    assert after.count('"--collect-existing"') == before.count('"--collect-existing"')
    assert after.count("pass_fds") == before.count("pass_fds")
    assert after.count('{"required_modes": ["glm","minimax","qwen"],"required_platforms": ["linux"]}') == 1
    assert "RECOVERABLE_RETURN_PINNED_HOST_REFUSED" in after
    assert "PREVIEW_ONLY" in after and '"reserved": False' in after
    return dest


@pytest.fixture
def module(composed, monkeypatch):
    names = (
        "pick", "pool_ledger", "a04_terminal_reconcile", "native_completion_reconcile",
        "native_prestart_reconcile", "native_preexec_reconcile",
        "native_host_review_controller_reconcile",
    )
    modules = {name: types.ModuleType(name) for name in names}
    for name, fake in modules.items():
        monkeypatch.setitem(sys.modules, name, fake)
    requests = []
    def pick_route(task, **kw):
        requests.append((task, dict(kw)))
        host = kw["host"] if kw["host"] != "auto" else "ubuntu1"
        return f"POOL=glm MODEL=glm-5.3-flash HOST={host} MODE=glm REASON=qualified"
    modules["pick"].format_pick = pick_route
    modules["pick"].launch_policy = lambda *args, **kwargs: {"allowed": True}
    name = "_fabric_prospective_selector_test"
    spec = importlib.util.spec_from_file_location(name, composed)
    assert spec is not None and spec.loader is not None
    result = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, result)
    spec.loader.exec_module(result)
    result._audit_pick_calls = requests
    return result


def test_preview_is_unreserved_and_uses_qualified_picker_without_exec(module, monkeypatch, capsys):
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **kw:
                        (_ for _ in ()).throw(AssertionError("preview attempted subprocess")))
    assert module.main(["preview", "--id", "sample-1", "--class", "review",
                        "--host", "ubuntu1", "--pool", "auto", "--model", "auto"]) == 0
    response = json.loads(capsys.readouterr().out)
    assert response["state"] == "PREVIEW_ONLY" and response["reserved"] is False
    assert response["host"] == "ubuntu1" and response["selection_rechecked_at_request"] is True
    task, forwarded = module._audit_pick_calls[-1]
    assert task == "review" and forwarded["host"] == "ubuntu1"
    assert forwarded["pool"] is None and forwarded["requested_model"] is None
    assert forwarded["route_key"] == "sample-1"


@pytest.mark.parametrize("host", ["../outside", "bad/host", "!invalid", "", " "])
def test_invalid_pin_refuses_before_selection(module, host):
    before = len(module._audit_pick_calls)
    with pytest.raises(module.FabricTaskError, match="INVALID_HOST_SELECTOR"):
        module.preview_route("sample-1", "review", host=host)
    assert len(module._audit_pick_calls) == before


def test_recoverable_return_rejects_pin_before_collector_or_picker(module, monkeypatch):
    collector = types.ModuleType("original_delivery_collector")
    called = []
    collector.completion_caller = lambda *args: called.append(args)
    monkeypatch.setitem(sys.modules, "original_delivery_collector", collector)
    before = len(module._audit_pick_calls)
    with pytest.raises(module.FabricTaskError, match="RECOVERABLE_RETURN_PINNED_HOST_REFUSED"):
        module.request("sample-2", "mechanical", cwd=".", packet=None, stdin_bytes=b"task",
                       host="ubuntu1", root_id="root-1", parent_run_id="parent-1",
                       recoverable_return=True)
    assert called == [] and len(module._audit_pick_calls) == before


def test_qualified_mac_and_pinned_host_cannot_mix(module):
    with pytest.raises(module.FabricTaskError, match="HOST_QUALIFICATION_CONFLICT"):
        module.request("sample-3", "mechanical", cwd=".", packet=None, stdin_bytes=b"task",
                       host="ubuntu1", qualification_host="mb", pool="grok")


def test_existing_recoverable_auto_preserves_restricted_linux_modes(module, monkeypatch):
    collector = types.ModuleType("original_delivery_collector")
    collector.completion_caller = lambda *args: None
    monkeypatch.setitem(sys.modules, "original_delivery_collector", collector)
    class StopAfterSelection(Exception):
        pass
    record = []
    def stop(task, **kwargs):
        record.append(kwargs)
        raise StopAfterSelection()
    monkeypatch.setattr(sys.modules["pick"], "format_pick", stop)
    with pytest.raises(StopAfterSelection):
        module.request("sample-4", "mechanical", cwd=".", packet=None, stdin_bytes=b"task",
                       host="auto", recoverable_return=True, root_id="root-1",
                       parent_run_id="parent-1")
    assert len(record) == 1
    assert record[0]["host"] == "auto"
    assert record[0]["required_modes"] == ["glm", "minimax", "qwen"]
    assert record[0]["required_platforms"] == ["linux"]


def test_normal_request_passes_host_to_qualified_picker_not_to_new_owner(module, monkeypatch, tmp_path):
    packet = tmp_path / "packet.txt"
    packet.write_text("bounded mechanical task")
    dispatched = []
    def stop(argv, **kwargs):
        dispatched.append((argv, kwargs))
        return types.SimpleNamespace(returncode=0)
    monkeypatch.setattr(module.subprocess, "run", stop)
    assert module.request("sample-5", "mechanical", cwd=str(tmp_path), packet=packet,
                          stdin_bytes=None, pool="auto", host="ubuntu1",
                          requested_model="auto", root_id="root-1") == 0
    task, options = module._audit_pick_calls[-1]
    assert task == "mechanical" and options["host"] == "ubuntu1"
    assert options["pool"] is None and options["requested_model"] is None
    argv, opts = dispatched[0]
    assert argv[0] == "/bin/bash" and argv[2] == "ubuntu1"
    assert "--run-id" in argv and "sample-5" in argv
    assert opts["env"]["POOL_TASK_CLASS"] == "mechanical"
