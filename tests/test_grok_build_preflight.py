from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


_ROOT = Path(__file__).resolve().parents[1]
_MODULE_PATH = _ROOT / "ops" / "executive_os" / "grok-build-preflight.py"


def _load():
    spec = importlib.util.spec_from_file_location("grok_build_preflight", _MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _executable(tmp_path: Path, body: bytes = b"#!/bin/sh\n") -> Path:
    binary = tmp_path / "grok"
    binary.write_bytes(body)
    binary.chmod(0o700)
    return binary


def _receipt(module, **overrides):
    value = {
        "schema": module.SCHEMA,
        "observed_at": "2026-08-30T20:30:00Z",
        "grok_binary_sha256": "a" * 64,
        "acp_protocol_version": 1,
        "cached_token_offered": True,
        "oauth_ready": True,
        "model_turn_performed": False,
        "executive_routing_ready": False,
        "verdict": "LOCAL_OAUTH_ACP_READY_NOT_ROUTABLE",
        "reason_codes": [],
    }
    value.update(overrides)
    return value


def test_command_builder_is_provider_work_free(tmp_path: Path):
    module = _load()
    binary = _executable(tmp_path)
    assert module.build_allowed_argv(binary, "version") == (str(binary), "--no-auto-update", "version")
    assert module.build_allowed_argv(binary, "acp_stdio") == (
        str(binary),
        "--no-auto-update",
        "agent",
        "stdio",
    )
    for forbidden in (
        "prompt",
        "session_new",
        "session_prompt",
        "resume",
        "continue",
        "worktree",
        "models",
        "login",
        "logout",
    ):
        with pytest.raises(module.PreflightError, match="COMMAND_NOT_ALLOWED"):
            module.build_allowed_argv(binary, forbidden)


def test_provider_env_drops_api_key_and_unrelated_secrets():
    module = _load()
    env = module.sanitized_provider_env(
        {
            "HOME": "/tmp/home",
            "PATH": "/bin:/usr/bin",
            "HTTPS_PROXY": "http://127.0.0.1:9999",
            "GROK_HOME": "/tmp/grok-home",
            "XAI_API_KEY": "fake-secret-value",
            "ANTHROPIC_AUTH_TOKEN": "another-fake-secret",
            "RANDOM_SECRET": "do-not-forward",
        }
    )
    assert env == {
        "HOME": "/tmp/home",
        "PATH": "/bin:/usr/bin",
        "HTTPS_PROXY": "http://127.0.0.1:9999",
        "GROK_HOME": "/tmp/grok-home",
    }
    assert "XAI_API_KEY" not in env


def test_initialize_request_is_fixed_and_has_no_session_or_prompt():
    module = _load()
    payload = json.loads(module.initialize_request())
    assert payload["method"] == "initialize"
    assert payload["params"]["protocolVersion"] == 1
    assert payload["params"]["clientInfo"]["name"] == "mastermind-grok-preflight"
    raw = module.initialize_request()
    assert "session/new" not in raw
    assert "session/prompt" not in raw


def test_authenticate_request_uses_cached_token_headless_only():
    module = _load()
    payload = json.loads(module.authenticate_request())
    assert payload == {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "authenticate",
        "params": {"_meta": {"headless": True}, "methodId": "cached_token"},
    }


def test_initialize_accepts_cached_token_and_refuses_wrong_protocol():
    module = _load()
    ok, reason = module.normalize_initialize_response(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": 1,
                "authMethods": [
                    {"id": "xai.api_key", "name": "API key"},
                    {"id": "cached_token", "name": "Cached OAuth"},
                    {"id": "device_flow", "name": "Device"},
                ],
            },
        }
    )
    assert (ok, reason) == (True, None)

    ok, reason = module.normalize_initialize_response(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"protocolVersion": 2, "authMethods": [{"id": "cached_token"}]},
        }
    )
    assert (ok, reason) == (False, "ACP_PROTOCOL_UNSUPPORTED")


def test_initialize_without_cached_token_is_honest_not_ready():
    module = _load()
    ok, reason = module.normalize_initialize_response(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"protocolVersion": 1, "authMethods": [{"id": "device_flow"}]},
        }
    )
    assert ok is False
    assert reason == "CACHED_TOKEN_METHOD_UNAVAILABLE"


def test_initialize_rejects_duplicate_or_malformed_methods():
    module = _load()
    with pytest.raises(module.PreflightError, match="ACP_RESPONSE_INVALID"):
        module.normalize_initialize_response(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "protocolVersion": 1,
                    "authMethods": [{"id": "cached_token"}, {"id": "cached_token"}],
                },
            }
        )
    with pytest.raises(module.PreflightError, match="ACP_RESPONSE_INVALID"):
        module.normalize_initialize_response(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"protocolVersion": 1, "authMethods": ["cached_token"]},
            }
        )


def test_authenticate_success_and_failure_is_not_misclassified_as_login_required():
    module = _load()
    ready = module.normalize_authenticate_response(
        {"jsonrpc": "2.0", "id": 2, "result": {}}
    )
    assert ready == module.AcpAuthObservation(
        cached_token_offered=True,
        oauth_ready=True,
        verdict="LOCAL_OAUTH_ACP_READY_NOT_ROUTABLE",
        reason_codes=(),
    )

    missing = module.normalize_authenticate_response(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "error": {"code": -32000, "message": "authentication required"},
        }
    )
    assert missing.oauth_ready is False
    assert missing.verdict == "ACP_AUTHENTICATION_FAILED"
    assert missing.reason_codes == ("ACP_AUTHENTICATION_FAILED",)


def test_provider_wire_secret_shape_is_never_accepted():
    module = _load()
    with pytest.raises(module.PreflightError, match="SECRET_SHAPED_VALUE"):
        module.normalize_authenticate_response(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "error": {"code": -1, "message": "Bearer " + "x" * 30},
            }
        )


def test_receipt_never_claims_model_turn_or_routing_ready():
    module = _load()
    assert module.validate_receipt(_receipt(module))["oauth_ready"] is True
    for key in ("model_turn_performed", "executive_routing_ready"):
        with pytest.raises(module.PreflightError, match="RECEIPT_INVALID"):
            module.validate_receipt(_receipt(module, **{key: True}))


def test_nonready_receipt_requires_reason_and_consistent_auth_state():
    module = _load()
    value = _receipt(
        module,
        cached_token_offered=False,
        oauth_ready=False,
        verdict="CACHED_TOKEN_METHOD_UNAVAILABLE",
        reason_codes=["CACHED_TOKEN_METHOD_UNAVAILABLE"],
    )
    assert module.validate_receipt(value)["oauth_ready"] is False

    with pytest.raises(module.PreflightError, match="RECEIPT_INVALID"):
        module.validate_receipt(_receipt(module, oauth_ready=False))


def test_binary_must_be_absolute_regular_and_not_symlink(tmp_path: Path):
    module = _load()
    binary = _executable(tmp_path)
    assert module._require_binary(binary) == binary
    link = tmp_path / "grok-link"
    link.symlink_to(binary)
    with pytest.raises(module.PreflightError, match="BINARY_INVALID"):
        module._require_binary(link)
    with pytest.raises(module.PreflightError, match="BINARY_INVALID"):
        module._require_binary(Path("grok"))


def test_observe_version_uses_sanitized_env_and_discards_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = tuple(argv)
        captured["env"] = dict(kwargs["env"])
        captured["stderr"] = kwargs["stderr"]
        return subprocess.CompletedProcess(argv, 0, stdout="Grok Build 9.8.7\n", stderr="secret")

    monkeypatch.setenv("XAI_API_KEY", "fake-secret")
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    assert module.observe_version(binary) == "Grok Build 9.8.7"
    assert "XAI_API_KEY" not in captured["env"]
    assert captured["stderr"] is subprocess.DEVNULL


def test_build_receipt_does_not_leak_provider_or_account_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path, b"#!/bin/sh\necho ok\n")
    monkeypatch.setattr(module, "observe_version", lambda path: "Grok Build 1.0.0")
    monkeypatch.setattr(
        module,
        "observe_acp_cached_oauth",
        lambda path: module.AcpAuthObservation(
            cached_token_offered=True,
            oauth_ready=True,
            verdict="LOCAL_OAUTH_ACP_READY_NOT_ROUTABLE",
            reason_codes=(),
        ),
    )
    receipt = module.build_receipt(binary)
    assert set(receipt) == module._RECEIPT_KEYS
    raw = json.dumps(receipt, sort_keys=True).lower()
    for forbidden in (
        "email",
        "account_id",
        "organization",
        "home_path",
        "session_id",
        "provider_account",
        "grok_version",
    ):
        assert forbidden not in raw
    assert receipt["model_turn_performed"] is False
    assert receipt["executive_routing_ready"] is False


def test_public_exception_channel_never_echoes_arbitrary_text():
    module = _load()
    rogue = module.PreflightError("Bearer " + "s" * 40)
    assert rogue.public_code == module.PUBLIC_FAILURE
    assert str(rogue) == module.PUBLIC_FAILURE


def test_cli_errors_are_opaque_and_do_not_echo_path_contents(tmp_path: Path, capsys):
    module = _load()
    missing = tmp_path / "private-user@example.com-grok"
    assert module.main(["--grok-binary", str(missing)]) == 2
    output = capsys.readouterr().out
    assert "private-user@example.com" not in output
    assert json.loads(output) == {"ok": False, "error": module.PUBLIC_FAILURE}


def test_acp_probe_emits_only_initialize_and_authenticate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)
    sent: list[str] = []
    responses = iter(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "protocolVersion": 1,
                    "authMethods": [{"id": "cached_token"}],
                },
            },
            {"jsonrpc": "2.0", "id": 2, "result": {}},
        ]
    )

    class FakeProc:
        stdin = object()
        stdout = object()
        pid = 424242

        def __init__(self):
            self._running = True

        def poll(self):
            return None if self._running else 0

        def terminate(self):
            self._running = False

        def wait(self, timeout=None):
            self._running = False
            return 0

        def kill(self):
            self._running = False

    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: FakeProc())
    monkeypatch.setattr(module.os, "killpg", lambda pid, sig: None)
    monkeypatch.setattr(module, "_send_json_line", lambda stream, payload: sent.append(payload))
    monkeypatch.setattr(module, "_read_json_line", lambda stream, timeout: next(responses))

    observed = module.observe_acp_cached_oauth(binary)
    assert observed.oauth_ready is True
    assert [json.loads(item)["method"] for item in sent] == ["initialize", "authenticate"]
    source = _MODULE_PATH.read_text(encoding="utf-8")
    assert '"session/new"' not in source
    assert '"session/prompt"' not in source
