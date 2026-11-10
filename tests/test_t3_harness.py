"""Closed browser/context adapter contracts; fixture effects are not live T3 proof."""
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import sys

import pytest

from integrations.t3_harness import runtime as h
from integrations.session_bridge import project_task_context as plan_context
from tests.test_project_task_context import plan, raw

ROOT = Path(__file__).resolve().parents[1]


def deployment(tmp_path, *, binding=True, bridge_source="# fixture\n"):
    browser_root = tmp_path / "browser"
    schema = {"name": "mmx_browser", "description": "Fixture original browser protocol", "parameters": {
        "type": "object", "additionalProperties": False, "required": ["action"], "properties": {
            "action": {"type": "string", "enum": ["browsers", "status", "click", "screenshot"]},
            "browser_id": {"type": "string"}, "connection_id": {"type": "string"}}}}
    for relative in h.BROWSER_FILES:
        p = browser_root / relative; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(schema) if relative.endswith("browser_tool_schema.json") else
                     bridge_source if relative.endswith("browser_bridge.py") else "# fixture\n")
    browser = {"schema": "mastermind.hermes_browser.local_runtime/v1", "release_commit": "b" * 40,
               "source_root": str(browser_root), "source_files": {p: hashlib.sha256((browser_root / p).read_bytes()).hexdigest()
                   for p in h.BROWSER_FILES}, "profile_home": str(tmp_path), "python_executable": sys.executable,
               "bindings_path": str(tmp_path / "bindings.json"), "upload_roots": [], "artifact_root": str(tmp_path / "artifacts"),
               "host_ref": "fixture"}
    descriptor = tmp_path / "browser-runtime.json"; descriptor.write_bytes(h.encode(browser))
    plan_path = tmp_path / "docs/plans/mission.md"; plan_path.parent.mkdir(parents=True); plan_path.write_bytes(raw(plan()))
    bindings = {"thread-1": {"workspace_root": str(tmp_path), "plan_path": "docs/plans/mission.md",
                "workstream": "WS:FIXTURE", "plan_contract_sha256": plan_context.contract_digest(plan())}} if binding else {}
    config = {"schema": h.SCHEMA, "source_root": str(ROOT), "source_files": {
        p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in h.SOURCE_FILES},
        "browser_descriptor": str(descriptor), "browser_descriptor_sha256": hashlib.sha256(descriptor.read_bytes()).hexdigest(),
        "namespace": "t3:fixture", "local_browser_only": True, "session_bindings": bindings}
    path = tmp_path / "runtime.json"; path.write_bytes(h.encode(config))
    return path, config, browser


def load(path, sid="thread-1"):
    return h.Runtime.load(str(path), hashlib.sha256(path.read_bytes()).hexdigest(), {"T3CODE_THREAD_ID": sid})


def test_exact_bound_context_and_unbound_child_have_distinct_outcomes(tmp_path):
    path, _, _ = deployment(tmp_path)
    value = load(path).project_context({})
    assert value["state"] == "OBSERVED"
    assert len(value["project"]["requirements"]) == 3
    assert value["mission_accepted"] is False and value["native_action"] == "NONE"
    assert load(path, "child-thread").project_context({})["state"] == "UNBOUND"
    assert load(path).project_context({"session_id": "child-thread"})["state"] == "REFUSED"


def test_current_progress_is_reread_without_replacing_contract(tmp_path):
    path, _, _ = deployment(tmp_path); runtime = load(path)
    document = plan();document["tasks"][0]["state"] = "blocked";document["tasks"][0]["blocker"] = "Requires original receipt"
    (tmp_path / "docs/plans/mission.md").write_bytes(raw(document))
    result = runtime.project_context({})
    assert result["state"] == "OBSERVED" and result["project"]["focus"]["id"] == "P1.T3"
    document["requirements"][0]["text"] = "Changed scope without approved binding"
    (tmp_path / "docs/plans/mission.md").write_bytes(raw(document))
    assert runtime.project_context({})["state"] == "REFUSED"


@pytest.mark.parametrize("sid", [None, "", "../other", "x\nother", "x" * 257])
def test_missing_or_invalid_native_thread_refuses(tmp_path, sid):
    path, _, _ = deployment(tmp_path)
    with pytest.raises((h.HarnessError, TypeError)):load(path, sid)


def test_config_change_revokes_cached_runtime_before_browser_call(tmp_path):
    path, config, _ = deployment(tmp_path); runtime = load(path); calls = []
    config["session_bindings"] = {};path.write_bytes(h.encode(config))
    async def exchange(envelope):calls.append(envelope);return {"state": "OBSERVED"}
    result = asyncio.run(runtime.browser_call({"action": "browsers"}, exchange=exchange))
    assert result["reason"] == "INSTALL_BINDING_CHANGED" and not calls


@pytest.mark.parametrize("change", ["extra_file", "missing_file", "digest", "source_root", "duplicate_json"])
def test_source_binding_is_exact(tmp_path, change):
    path, config, _ = deployment(tmp_path)
    if change == "extra_file":config["source_files"]["extra.py"] = "a" * 64
    elif change == "missing_file":config["source_files"].pop(next(iter(config["source_files"])))
    elif change == "digest":config["source_files"][next(iter(config["source_files"]))] = "a" * 64
    elif change == "source_root":config["source_root"] = str(tmp_path)
    else:
        path.write_text('{"schema":"a","schema":"b"}')
        with pytest.raises(h.HarnessError):load(path)
        return
    path.write_bytes(h.encode(config))
    with pytest.raises(h.HarnessError):load(path)


def test_browser_closure_symlink_and_source_drift_refuse(tmp_path):
    path, _, browser = deployment(tmp_path)
    target = Path(browser["source_root"]) / "integrations/hermes_harness/browser_bridge.py"
    original = target.read_bytes();target.write_bytes(original + b"# drift\n")
    with pytest.raises(h.HarnessError, match="SOURCE_DIGEST_MISMATCH"):load(path)
    target.unlink();outside = tmp_path / "outside.py";outside.write_bytes(original);target.symlink_to(outside)
    with pytest.raises(h.HarnessError, match="SYMLINK"):load(path)


def test_fifo_and_unsafe_file_permissions_refuse_without_open_read(tmp_path):
    path = tmp_path / "fifo";os.mkfifo(path)
    with pytest.raises(h.HarnessError):h.safe_bytes(path)
    path.unlink();path.write_text("data");path.chmod(0o666)
    with pytest.raises(h.HarnessError):h.safe_bytes(path)


@pytest.mark.parametrize("arguments", [{"action": "browsers", "session_id": "other"},
    {"action": "status", "operation_key": "replay"}, {"action": "spawn"}, {"action": "status", "command": "x"}])
def test_browser_arguments_cannot_supply_identity_or_execution(arguments, tmp_path):
    path, _, _ = deployment(tmp_path);calls = []
    async def exchange(envelope):calls.append(envelope);return {"state": "OBSERVED"}
    result = asyncio.run(load(path).browser_call(arguments, exchange=exchange))
    assert result["state"] == "REFUSED" and not calls


def test_native_thread_attribution_and_original_operation_are_not_model_parameters(tmp_path):
    path, _, _ = deployment(tmp_path);calls = []
    async def exchange(envelope):
        calls.append(envelope)
        return {"state": "RECEIPT", "receipt": {"action": "status", "operation_key": envelope["operation_key"],
            "nonce": envelope["nonce"], "status": "OK"}}
    a = asyncio.run(load(path).browser_call({"action": "status"}, exchange=exchange))
    b = asyncio.run(load(path, "thread-2").browser_call({"action": "status"}, exchange=exchange))
    assert [c["session_id"] for c in calls] == ["thread-1", "thread-2"]
    assert a["t3_request_ref"]["nonce"] != b["t3_request_ref"]["nonce"]
    assert a["caller_attribution"] == "NATIVE_PROCESS_ENV_NOT_AUTHENTICATION"


@pytest.mark.parametrize("action,expected", [("status", "UNAVAILABLE"), ("click", "EFFECT_UNKNOWN")])
def test_lost_or_wrong_response_preserves_original_effect_without_retry(tmp_path, action, expected):
    path, _, _ = deployment(tmp_path);calls = []
    async def exchange(envelope):calls.append(envelope);raise TimeoutError()
    result = asyncio.run(load(path).browser_call({"action": action}, exchange=exchange))
    assert result["state"] == expected and result["retry_allowed"] is False
    assert result["request_ref"]["operation_key"] == calls[0]["operation_key"] and len(calls) == 1


def test_wrong_receipt_nonce_is_unknown_and_config_change_after_effect_is_unknown(tmp_path):
    path, config, _ = deployment(tmp_path); runtime = load(path)
    async def wrong(envelope):
        return {"state": "RECEIPT", "receipt": {"action": "click", "operation_key": envelope["operation_key"], "nonce": "wrong"}}
    assert asyncio.run(runtime.browser_call({"action": "click"}, exchange=wrong))["state"] == "EFFECT_UNKNOWN"
    async def revoked(envelope):
        config["namespace"] = "t3:changed";path.write_bytes(h.encode(config));return {"state": "OBSERVED"}
    assert asyncio.run(runtime.browser_call({"action": "click"}, exchange=revoked))["state"] == "EFFECT_UNKNOWN"


def test_actual_fixed_bridge_subprocess_does_not_inherit_provider_credentials(tmp_path, monkeypatch):
    source = 'import json,os; print(json.dumps({"state":"OBSERVED","secret_present":"MMX_TEST_PROVIDER_SECRET" in os.environ}))\n'
    path, _, _ = deployment(tmp_path, bridge_source=source)
    monkeypatch.setenv("MMX_TEST_PROVIDER_SECRET", "fixture-not-a-real-key")
    result = asyncio.run(load(path).browser_call({"action": "browsers"}))
    assert result["state"] == "OBSERVED" and result["secret_present"] is False


def test_actual_bridge_output_overflow_does_not_become_safe_retry(tmp_path):
    path, _, _ = deployment(tmp_path, bridge_source='print("x" * (2 * 1024 * 1024))\n')
    result = asyncio.run(load(path).browser_call({"action": "click"}))
    assert result["state"] == "EFFECT_UNKNOWN" and result["retry_allowed"] is False


def test_image_is_attached_without_repeating_base64_in_metadata():
    payload = base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode()
    output = {"state": "RECEIPT", "receipt": {"status": "OK", "action": "screenshot",
              "data": {"mime_type": "image/png", "base64": payload, "width": 1, "height": 1}}}
    value, images = h.present(output)
    assert images[0]["data"] == payload and "base64" not in value["receipt"]["data"]
    assert output["receipt"]["data"]["base64"] == payload
    output["receipt"]["data"]["mime_type"] = "image/jpeg"
    with pytest.raises(h.HarnessError):h.present(output)


def test_native_launcher_strips_provider_environment_and_preserves_only_thread_attribution(tmp_path, monkeypatch):
    from integrations.t3_harness.native_launch import launch_spec
    path, _, _ = deployment(tmp_path)
    environment = {"T3CODE_THREAD_ID": "thread-1", "ANTHROPIC_API_KEY": "fixture", "OPENAI_BASE_URL": "https://invalid.example",
                   "NODE_OPTIONS": "--inspect", "PYTHONPATH": "/wrong", "HOME": "/wrong"}
    executable, args, env = launch_spec("browser", str(path), hashlib.sha256(path.read_bytes()).hexdigest(), environment)
    assert args[1:3] == ["-I", "-B"] and args[3].endswith("integrations/t3_harness/server.py")
    assert env["T3CODE_THREAD_ID"] == "thread-1" and env["HOME"] != "/wrong"
    assert not set(environment).intersection(env) - {"T3CODE_THREAD_ID", "HOME"}
    assert executable == str(Path(sys.executable).absolute())
    with pytest.raises(h.HarnessError):launch_spec("agent", str(path), hashlib.sha256(path.read_bytes()).hexdigest(), environment)


def test_peekaboo_launch_uses_only_exact_original_binary_and_socket(tmp_path):
    import socket
    from integrations.t3_harness.native_launch import launch_spec, executable_digest
    path, config, _ = deployment(tmp_path)
    binary = tmp_path / "peekaboo";binary.write_bytes(b"native executable fixture");binary.chmod(0o755)
    sockpath = tmp_path / "bridge.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.bind(str(sockpath))
        config["peekaboo"] = {"executable": str(binary), "executable_sha256": executable_digest(binary), "bridge_socket": str(sockpath)}
        path.write_bytes(h.encode(config));digest = hashlib.sha256(path.read_bytes()).hexdigest()
        executable, args, env = launch_spec("peekaboo", str(path), digest, {"T3CODE_THREAD_ID": "thread-1"})
        assert args == [str(binary), "mcp", "serve", "--bridge-socket", str(sockpath)]
        assert "--no-remote" not in args and not any("model" in a or "foreground" in a for a in args)
        binary.write_bytes(b"changed version")
        with pytest.raises(h.HarnessError, match="DIGEST_MISMATCH"):
            launch_spec("peekaboo", str(path), digest, {"T3CODE_THREAD_ID": "thread-1"})


def test_missing_peekaboo_binding_does_not_invent_fallback(tmp_path):
    from integrations.t3_harness.native_launch import launch_spec
    path, _, _ = deployment(tmp_path)
    with pytest.raises(h.HarnessError, match="BINDING_MISSING"):
        launch_spec("peekaboo", str(path), hashlib.sha256(path.read_bytes()).hexdigest(), {"T3CODE_THREAD_ID": "thread-1"})


def test_bundle_builder_copies_exact_committed_source_and_refuses_dirty_or_reused_destination(tmp_path):
    import subprocess
    from scripts.build_t3_harness_bundle import build, mcp_entries
    source = tmp_path / "source";source.mkdir()
    paths = set(h.SOURCE_FILES) | {"integrations/session_bridge/t3_orchestration.py",
        "integrations/session_bridge/t3_native_client.py", "integrations/session_bridge/t3_mission_brief.py",
        "skills/mastermind-long-horizon/SKILL.md"}
    for relative in paths:
        path = source / relative;path.parent.mkdir(parents=True, exist_ok=True);path.write_text("fixture\n")
    def git(*args):return subprocess.run(["git", *args], cwd=source, capture_output=True, text=True, check=True).stdout.strip()
    git("init", "-q");git("add", ".");git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
    sha = git("rev-parse", "HEAD");output = tmp_path / "bundle"
    manifest = build(output, sha, source_root=source)
    assert manifest["release_commit"] == sha and manifest["installation_performed"] is False
    assert manifest["source_sha256"]["integrations/t3_harness/server.py"] == hashlib.sha256(b"fixture\n").hexdigest()
    with pytest.raises(ValueError):build(output, sha, source_root=source)
    (source / "integrations/t3_harness/server.py").write_text("dirty\n")
    with pytest.raises(ValueError, match="Uncommitted"):
        build(tmp_path / "not-built", sha, source_root=source)
    assert not (tmp_path / "not-built").exists()
    entries = mcp_entries(output, Path(sys.executable).absolute(), tmp_path / "runtime.json", "a" * 64, include_peekaboo=True)
    assert set(entries) == {"mastermind-browser", "mastermind-peekaboo"}
    assert all(entry["env"] == {} for entry in entries.values())
    assert "T3CODE_THREAD_ID" not in json.dumps(entries)
