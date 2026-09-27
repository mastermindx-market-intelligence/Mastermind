"""Production-inert pure browser cognition transport core contract."""
from __future__ import annotations

from pathlib import Path
import json
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
NODE_TEST = ROOT / "tests/web_sol_cognition_transport_core.test.cjs"
EXTENSION_NODE_TEST = ROOT / "tests/web_sol_cognition_extension.test.cjs"
CORE = ROOT / "integrations/chairman_surfaces/web_sol_extension/cognition_transport_core.js"


def test_cognition_transport_core_node_suite() -> None:
    node = shutil.which("node")
    assert node is not None
    completed = subprocess.run(
        [node, "--test", str(NODE_TEST)],
        cwd=ROOT,
        env={**__import__("os").environ, "COGNITION_CORE": str(CORE)},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def _real_extension_payload() -> dict:
    from tests.test_web_sol_cognition_transport import _submit
    from integrations.chairman_surfaces import web_sol_protocol as protocol

    payload = _submit(
        runtime_binding_id="bind-wsx-" + "a" * 48,
        runtime_binding_generation=1,
        runtime_binding_fingerprint="b" * 64,
    )
    request = {
        "schema": protocol.ACTION_SCHEMA,
        "binding_id": "11111111-1111-4111-8111-111111111111",
        "conversation_fingerprint": "c" * 64,
        "binding_fingerprint": "b" * 64,
        "action": protocol.SurfaceAction.SUBMIT_COGNITION_ASSIGNMENT.value,
        "operation_key": "web-sol-cognition-extension-test",
        "issued_at": "2026-09-27T00:00:00Z",
        "expires_at": "2026-09-27T00:00:30Z",
        "nonce": "cognition-extension-nonce-0001",
        "session_alias": "EXECUTIVE-CEO-A",
        "runtime_binding_id": "bind-wsx-" + "a" * 48,
        "runtime_binding_generation": 1,
        "runtime_binding_fingerprint": "b" * 64,
        "cognition_payload": payload,
    }
    protocol.validate_request(request)
    return payload


def test_cognition_extension_node_suite_uses_real_cores_and_python_fixture() -> None:
    node = shutil.which("node")
    assert node is not None
    from integrations.chairman_surfaces import web_sol_protocol as protocol

    completed = subprocess.run(
        [node, "--test", str(EXTENSION_NODE_TEST)],
        cwd=ROOT,
        env={
            **os.environ,
            "COGNITION_PAYLOAD": json.dumps(_real_extension_payload()),
            "CAPABILITY_DIGEST": protocol.transport_capability_digest(),
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_cognition_transport_core_is_pure_and_bounded() -> None:
    source = CORE.read_text(encoding="utf-8")
    assert len(source.encode("utf-8")) <= 24 * 1024
    for forbidden in (
        "document.querySelector",
        "fetch(",
        "chrome.runtime",
        "chrome.tabs",
        "localStorage",
        "sessionStorage",
        "document.cookie",
        "WebSocket",
        "XMLHttpRequest",
    ):
        assert forbidden not in source
    assert "SUBMIT_CONTINUATION" not in source
    assert "TYPED_REENTRY" not in source
