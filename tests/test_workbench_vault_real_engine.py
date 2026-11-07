"""Pinned donor/receiver qualification in the ordinary pull-request CI job.

This test owns synthetic inputs and a disposable Chromium context. It does not
qualify the macOS installation manifest or the authenticated service deployment.
The in-process relay seam avoids claiming a live host/socket acceptance result.
"""
from __future__ import annotations

from contextlib import nullcontext
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from urllib.parse import quote, urlencode

import pytest

from control_plane.executive_agent_capabilities import observed_mcp_tool_schema_digest
from integrations.workbench_browser_mcp.contracts import ALLOWED_BROWSER_TOOLS
from integrations.workbench_browser_mcp.relay import McpStdioSession, BrowserRelayServer, BrowserRelayError
from integrations.workbench_browser_mcp.vault_files import capture_existing_vault
from tests.fixtures.hermes_vault.fixture_writer import write_login
from tests.test_workbench_browser_credential import grant, private_use

ROOT = Path(__file__).resolve().parents[1]
RECEIVER = ROOT / "integrations/worker_browser_runtime/vault/child.cjs"
RUNTIME = ROOT / "integrations/worker_browser_runtime"
FIXTURES = ROOT / "tests/fixtures/hermes_vault"
pytestmark = pytest.mark.skipif(os.environ.get("MASTERMIND_PINNED_VAULT_ENGINE_TEST") != "1",
    reason="ordinary pinned-engine CI job installs and qualifies the exact dependencies")


def selected_vault(tmp_path, password):
    root = tmp_path / "vault"
    item = write_login(root, password=password)
    selected = grant(root, expires=int(time.time() * 1000) + 120_000)
    selected["item_ref"] = item.id
    return selected


def session_for(tmp_path):
    node = shutil.which("node")
    assert node, "CI must install the selected Node interpreter"
    output = tmp_path / "browser-output"
    output.mkdir(mode=0o700)
    catalog = json.loads((ROOT / "research/evidence/claude_browser_mcp_tools_0_0_79.json").read_text())
    selected = {r["name"]: r for r in catalog["tools"] if r["name"] in ALLOWED_BROWSER_TOOLS}
    digest = observed_mcp_tool_schema_digest({"tools": selected})
    resource_id = "c" * 32
    expiry = int(time.time() * 1000) + 180_000
    argv = (node, str(FIXTURES / "pinned_browser_child.cjs"), str(RECEIVER), str(RUNTIME), str(output), resource_id, str(expiry))
    env = {key: os.environ[key] for key in ("HOME", "PATH", "PLAYWRIGHT_BROWSERS_PATH") if key in os.environ}
    env.update({"LANG": "C.UTF-8", "NO_COLOR": "1", "TMPDIR": str(tmp_path)})
    # Deliberate fixture launch seam: actual McpStdioSession/Popen/protocol and
    # engines execute; installed B1 descriptor attestation is tested separately.
    session = McpStdioSession(argv=argv, env=env, allowed_tools=ALLOWED_BROWSER_TOOLS,
        expected_tool_schema_digest=digest, rpc_timeout_seconds=30,
        credential_enabled=True, credential_launch_guard=lambda: nullcontext({"argv": argv, "env": env, "pass_fds": ()}))
    return session, output


def representations(value):
    values = {value, json.dumps(value, ensure_ascii=False)[1:-1], value.replace("'", "''"),
              quote(value, safe="~()*!.'-"), urlencode({"v": value})[2:],
              value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")}
    return values | {json.dumps(v, ensure_ascii=False)[1:-1] for v in values}


@pytest.mark.parametrize("password", ['fixture-"quote\' &<xml>\\slash\\n雪', "FILLED"])
def test_actual_writer_fernet_mcp_dom_and_persisted_redaction(tmp_path, password):
    selected = selected_vault(tmp_path, password)
    use = private_use(selected, expires=selected["expires_at_ms"])
    session, output = session_for(tmp_path)
    responses = []
    child = None
    try:
        session.start()
        child = session._process
        responses.append(session.call("browser_navigate", {"url": "https://vault.test/login"}))
        relay = BrowserRelayServer(resource_id=use["resource_id"], socket_path=Path("/tmp/unused-vault-fixture.sock"),
            session=session, owner_pid=os.getpid(), parent_pid=os.getppid(),
            clock_ms=lambda: int(time.time() * 1000), expires_at_ms=selected["expires_at_ms"])
        result = relay._handle({"schema": "mastermind.workbench_browser_relay_request.v1", "kind": "credential_fill",
            "request_id": "d" * 32, "resource_id": use["resource_id"], "use": use})
        assert result["ok"] and result["result"]["effect_state"] == "APPLIED"
        assert result["result"]["code"] == "FILLED"
        responses.append(session.call("browser_snapshot", {}))
        # Known aliases/values cannot be supplied back to native generic tools.
        for tool, args in (("browser_type", {"target": "input", "text": password}),
                           ("browser_take_screenshot", {"scale": "css"}),
                           ("browser_console_messages", {"level": "info"}),
                           ("browser_press_key", {"key": "ControlOrMeta+C"})):
            with pytest.raises(BrowserRelayError): session.call(tool, args)
    finally:
        session.close()
    assert child is not None and child.poll() is not None
    outward = json.dumps(responses, ensure_ascii=False)
    assert "MMX_PRIVATE_" not in outward
    artifacts = [p for p in output.rglob("*") if p.is_file()]
    assert artifacts, "must inspect actual native persisted artifacts, not only tool text"
    persisted = b"\n".join(p.read_bytes() for p in artifacts).decode("utf-8")
    assert "<secret>" in persisted, "native shared-map redactor must actually be exercised"
    for value in representations(password) | representations(selected["account_identifier"]):
        assert value not in outward
        assert value not in persisted


@pytest.mark.parametrize("path,expected", [
    ("partial", "EFFECT_UNKNOWN"), ("override", "EFFECT_UNKNOWN"),
    ("ambiguous", "NOT_APPLIED"), ("new-password", "NOT_APPLIED"),
])
def test_actual_dom_target_changes_never_create_false_applied(tmp_path, path, expected):
    selected = selected_vault(tmp_path, "fixture-target-password")
    session, _output = session_for(tmp_path)
    try:
        session.start()
        session.call("browser_navigate", {"url": "https://vault.test/" + path})
        use = private_use(selected, expires=selected["expires_at_ms"])
        result = session.credential_fill(use, action_id="a" * 32, clock_ms=lambda: int(time.time() * 1000))
        assert result["effect_state"] == expected
    finally:
        session.close()


@pytest.mark.parametrize("fault", ["none", "wrong-key", "truncated", "tampered", "wrong-item", "wrong-account", "wrong-origin", "newline"])
def test_actual_node_fernet_decodes_only_the_selected_hermes_record(tmp_path, fault):
    from cryptography.fernet import Fernet
    password = "fixture-cryptographic-canary"
    selected = selected_vault(tmp_path, password + ("\n" if fault == "newline" else ""))
    material = capture_existing_vault(selected)
    if fault == "wrong-key": material["key"] = Fernet.generate_key().decode()
    elif fault == "truncated": material["ciphertext"] = "gAAAAA=="
    elif fault == "tampered": material["ciphertext"] = material["ciphertext"][:30] + ("A" if material["ciphertext"][30] != "A" else "B") + material["ciphertext"][31:]
    elif fault == "wrong-item": selected["item_ref"] = "vault_ffffffffffff"
    elif fault == "wrong-account": selected["account_identifier"] = "other@example.test"
    elif fault == "wrong-origin": selected["origin"] = "https://other.test"
    script = """const fs=require('node:fs');const path=require('node:path');
const p=JSON.parse(fs.readFileSync(0,'utf8'));
const receiver=require(p.receiver);const fernet=require(path.join(p.runtime,'node_modules/fernet'));
let matched=false;try{const r=receiver.decodeLogin(fernet,p.material,p.grant);matched=r.password===p.expected&&r.identifier==='fixture@example.test';}catch{}
process.stdout.write(JSON.stringify({matched}));"""
    completed = subprocess.run([shutil.which("node"), "-e", script], text=True, capture_output=True, timeout=15,
        input=json.dumps({"receiver": str(RECEIVER), "runtime": str(RUNTIME), "material": material,
                         "grant": selected, "expected": password}))
    assert completed.returncode == 0
    assert json.loads(completed.stdout) == {"matched": fault == "none"}
    assert password not in completed.stdout + completed.stderr


@pytest.mark.parametrize("mode", ["navigation", "replacement", "hidden", "new-password", "form-origin", "second-page", "expiry"])
def test_actual_held_target_rechecked_after_preparation(tmp_path, mode):
    selected = selected_vault(tmp_path, "fixture-held-target-password")
    output = tmp_path / "browser-output"
    output.mkdir(mode=0o700)
    use = private_use(selected, expires=selected["expires_at_ms"])
    completed = subprocess.run([shutil.which("node"), str(FIXTURES / "pinned_target_cases.cjs")],
        input=json.dumps({"source": str(RECEIVER), "runtime": str(RUNTIME), "output": str(output),
                         "use": use, "material": capture_existing_vault(selected), "mode": mode}),
        text=True, capture_output=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"effect_state": "NOT_APPLIED", "browser_closed": True}


def test_actual_installed_dependency_bytes_match_selected_source_pins():
    import hashlib
    from control_plane.worker_browser_b1 import _WORKBENCH_CREDENTIAL_SOURCE_PINS
    for relative, expected in _WORKBENCH_CREDENTIAL_SOURCE_PINS.items():
        if relative.endswith("@mastermind/workbench-vault/child.cjs"):
            path = RECEIVER
        else:
            path = RUNTIME / relative
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
