from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "ops" / "executive_os" / "grok-build-preflight.py"


def load_module():
    spec = importlib.util.spec_from_file_location("grok_build_preflight", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def executable(tmp_path: Path, body: bytes = b"#!/bin/sh\necho ok\n") -> Path:
    path = tmp_path / "grok"
    path.write_bytes(body)
    path.chmod(0o700)
    return path


def test_command_allowlist_is_provider_work_free(tmp_path: Path):
    m = load_module()
    binary = executable(tmp_path)
    assert m.build_allowed_argv(binary, "version") == (
        str(binary), "--no-auto-update", "version"
    )
    assert m.build_allowed_argv(binary, "acp_stdio") == (
        str(binary), "--no-auto-update", "agent", "stdio"
    )
    for forbidden in ("prompt", "session_new", "resume", "login", "models"):
        with pytest.raises(m.PreflightError, match="COMMAND_NOT_ALLOWED"):
            m.build_allowed_argv(binary, forbidden)


def test_provider_env_drops_api_auth_and_unrelated_secrets():
    m = load_module()
    env = m.sanitized_provider_env(
        {
            "HOME": "/tmp/home",
            "PATH": "/bin",
            "GROK_HOME": "/tmp/grok-home",
            "XAI_API_KEY": "secret",
            "ANTHROPIC_AUTH_TOKEN": "secret",
            "RANDOM_SECRET": "secret",
        }
    )
    assert env == {"HOME": "/tmp/home", "PATH": "/bin", "GROK_HOME": "/tmp/grok-home"}


def test_requests_are_exact_and_have_no_session_methods():
    m = load_module()
    init = json.loads(m.initialize_request())
    auth = json.loads(m.authenticate_request())
    assert init["method"] == "initialize"
    assert init["params"]["protocolVersion"] == 1
    assert auth == {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "authenticate",
        "params": {"_meta": {"headless": True}, "methodId": "cached_token"},
    }
    assert "session/new" not in m.initialize_request() + m.authenticate_request()
    assert "session/prompt" not in m.initialize_request() + m.authenticate_request()


def test_initialize_outcomes_are_closed():
    m = load_module()
    assert m.normalize_initialize_response(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": 1,
                "authMethods": [{"id": "xai.api_key"}, {"id": "cached_token"}],
            },
        }
    ) is None
    assert m.normalize_initialize_response(
        {"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "no"}}
    ) is m.AcpOutcome.INITIALIZE_FAILED
    assert m.normalize_initialize_response(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"protocolVersion": 2, "authMethods": [{"id": "cached_token"}]},
        }
    ) is m.AcpOutcome.PROTOCOL_UNSUPPORTED
    assert m.normalize_initialize_response(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"protocolVersion": 1, "authMethods": [{"id": "device_flow"}]},
        }
    ) is m.AcpOutcome.CACHED_TOKEN_UNAVAILABLE


def test_authenticate_outcomes_are_closed():
    m = load_module()
    assert m.normalize_authenticate_response(
        {"jsonrpc": "2.0", "id": 2, "result": {}}
    ) is m.AcpOutcome.READY
    assert m.normalize_authenticate_response(
        {"jsonrpc": "2.0", "id": 2, "error": {"code": -1, "message": "no"}}
    ) is m.AcpOutcome.AUTHENTICATION_FAILED


def test_malformed_or_duplicate_methods_fail_closed():
    m = load_module()
    with pytest.raises(m.PreflightError, match="ACP_RESPONSE_INVALID"):
        m.normalize_initialize_response(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "protocolVersion": 1,
                    "authMethods": [{"id": "cached_token"}, {"id": "cached_token"}],
                },
            }
        )
    with pytest.raises(m.PreflightError, match="ACP_RESPONSE_INVALID"):
        m.normalize_initialize_response(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"protocolVersion": 1, "authMethods": ["cached_token"]},
            }
        )


def test_secret_shaped_provider_wire_fails_closed():
    m = load_module()
    with pytest.raises(m.PreflightError, match="SECRET_SHAPED_VALUE"):
        m.normalize_authenticate_response(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "error": {"code": -1, "message": "Bearer " + "x" * 30},
            }
        )


def test_binary_must_be_absolute_regular_executable_and_not_symlink(tmp_path: Path):
    m = load_module()
    binary = executable(tmp_path)
    resolved, _ = m._require_binary(binary)
    assert resolved == binary
    link = tmp_path / "link"
    link.symlink_to(binary)
    with pytest.raises(m.PreflightError, match="BINARY_INVALID"):
        m._require_binary(link)
    with pytest.raises(m.PreflightError, match="BINARY_INVALID"):
        m._require_binary(Path("grok"))


def test_binary_identity_detects_in_place_change(tmp_path: Path):
    m = load_module()
    binary = executable(tmp_path, b"#!/bin/sh\necho one\n")
    path, identity = m.snapshot_binary(binary)
    path.write_bytes(b"#!/bin/sh\necho two\n")
    path.chmod(0o700)
    with pytest.raises(m.PreflightError, match="BINARY_CHANGED_DURING_PREFLIGHT"):
        m.assert_binary_unchanged(path, identity)


def test_observe_version_suppresses_stderr_and_api_key(tmp_path: Path, monkeypatch):
    m = load_module()
    binary = executable(tmp_path)
    captured = {}

    def fake_run(argv, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, stdout="Grok Build 1.2.3\n", stderr="secret")

    monkeypatch.setenv("XAI_API_KEY", "secret")
    monkeypatch.setattr(m.subprocess, "run", fake_run)
    assert m.observe_version(binary) is None
    assert captured["stderr"] is subprocess.DEVNULL
    assert "XAI_API_KEY" not in captured["env"]


def test_all_public_receipts_contain_only_closed_fields():
    m = load_module()
    digest = "a" * 64
    observed = "2026-08-30T21:50:00Z"
    renderers = [
        m.render_ready_receipt,
        m.render_cached_unavailable_receipt,
        m.render_auth_failed_receipt,
        m.render_initialize_failed_receipt,
        m.render_protocol_unsupported_receipt,
    ]
    allowed = {
        "schema",
        "observed_at",
        "grok_binary_sha256",
        "acp_protocol_version",
        "cached_token_offered",
        "oauth_ready",
        "model_turn_performed",
        "executive_routing_ready",
        "verdict",
        "reason_codes",
    }
    for renderer in renderers:
        payload = json.loads(renderer(digest, observed))
        assert set(payload) == allowed
        assert payload["model_turn_performed"] is False
        assert payload["executive_routing_ready"] is False
        raw = json.dumps(payload).lower()
        for forbidden in ("token_value", "email", "grok_version", "home_path", "session_id"):
            assert forbidden not in raw


def test_main_provider_state_selects_constant_renderer_only(tmp_path: Path, monkeypatch, capsys):
    m = load_module()
    binary = executable(tmp_path)
    _, identity = m.snapshot_binary(binary)
    monkeypatch.setattr(m, "snapshot_binary", lambda path: (binary, identity))
    monkeypatch.setattr(m, "observe_version", lambda path: None)
    monkeypatch.setattr(m, "assert_binary_unchanged", lambda path, ident: None)
    monkeypatch.setattr(m, "now_iso", lambda: "2026-08-30T21:50:00Z")

    for outcome, expected_code, expected_ready in (
        (m.AcpOutcome.READY, 0, True),
        (m.AcpOutcome.CACHED_TOKEN_UNAVAILABLE, 1, False),
        (m.AcpOutcome.AUTHENTICATION_FAILED, 1, False),
        (m.AcpOutcome.INITIALIZE_FAILED, 1, False),
        (m.AcpOutcome.PROTOCOL_UNSUPPORTED, 1, False),
    ):
        monkeypatch.setattr(m, "observe_acp_cached_oauth", lambda path, o=outcome: o)
        assert m.main(["--grok-binary", str(binary)]) == expected_code
        payload = json.loads(capsys.readouterr().out)
        assert payload["oauth_ready"] is expected_ready
        assert payload["grok_binary_sha256"] == identity.sha256


def test_main_exception_output_is_fixed_and_opaque(tmp_path: Path, monkeypatch, capsys):
    m = load_module()
    binary = executable(tmp_path)

    def explode(path):
        raise m.PreflightError("Bearer " + "s" * 40)

    monkeypatch.setattr(m, "snapshot_binary", explode)
    assert m.main(["--grok-binary", str(binary)]) == 2
    assert json.loads(capsys.readouterr().out) == {"ok": False, "error": "PREFLIGHT_FAILED"}


def test_main_unexpected_exception_output_is_fixed_and_opaque(
    tmp_path: Path, monkeypatch, capsys
):
    m = load_module()
    binary = executable(tmp_path)

    def explode(path):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid provider output")

    monkeypatch.setattr(m, "snapshot_binary", explode)
    assert m.main(["--grok-binary", str(binary)]) == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {"ok": False, "error": "PREFLIGHT_FAILED"}


def test_main_parser_failure_is_fixed_opaque_and_provider_free(monkeypatch, capsys):
    m = load_module()

    def unexpected_provider_observation(*args, **kwargs):
        pytest.fail("parser failure must not perform provider observation")

    monkeypatch.setattr(m, "snapshot_binary", unexpected_provider_observation)
    monkeypatch.setattr(m, "observe_version", unexpected_provider_observation)
    monkeypatch.setattr(m, "observe_acp_cached_oauth", unexpected_provider_observation)

    assert m.main(["--grok-binary"]) == 2
    captured = capsys.readouterr()
    assert captured.out == '{"error": "PREFLIGHT_FAILED", "ok": false}\n'
    assert captured.err == ""


def test_acp_probe_emits_only_initialize_then_authenticate(tmp_path: Path, monkeypatch):
    m = load_module()
    binary = executable(tmp_path)
    sent = []
    responses = iter(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"protocolVersion": 1, "authMethods": [{"id": "cached_token"}]},
            },
            {"jsonrpc": "2.0", "id": 2, "result": {}},
        ]
    )

    class FakeProc:
        stdin = object()
        stdout = object()
        pid = 424242

        def __init__(self):
            self.running = True

        def poll(self):
            return None if self.running else 0

        def terminate(self):
            self.running = False

        def wait(self, timeout=None):
            self.running = False
            return 0

        def kill(self):
            self.running = False

    monkeypatch.setattr(m.subprocess, "Popen", lambda *args, **kwargs: FakeProc())
    monkeypatch.setattr(m.os, "killpg", lambda pid, sig: None)
    monkeypatch.setattr(m, "_send_json_line", lambda stream, payload: sent.append(payload))
    monkeypatch.setattr(m, "_read_json_line", lambda stream, timeout: next(responses))
    assert m.observe_acp_cached_oauth(binary) is m.AcpOutcome.READY
    assert [json.loads(item)["method"] for item in sent] == ["initialize", "authenticate"]
    source = MODULE_PATH.read_text()
    assert '"session/new"' not in source
    assert '"session/prompt"' not in source
