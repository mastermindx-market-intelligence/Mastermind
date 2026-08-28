from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


_ROOT = Path(__file__).resolve().parents[1]
_MODULE_PATH = _ROOT / "ops" / "executive_os" / "claude-worker-preflight.py"


def _load():
    spec = importlib.util.spec_from_file_location("claude_worker_preflight", _MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _receipt(module, **overrides):
    value = {
        "schema": module.SCHEMA,
        "realm_label": "claude-pro-01",
        "host_ref": "host-01234567",
        "os_principal_ref": "principal-01234567",
        "observed_at": "2026-08-27T23:30:00Z",
        "claude_binary_sha256": "a" * 64,
        "claude_version": "2.1.0",
        "auth_ready": True,
        "auth_method": "claudeai",
        "api_provider": "first_party",
        "auth_identity_confidence": "SLOT_ONLY",
        "macos_credential_isolation_basis": "OS_PRINCIPAL_KEYCHAIN",
        "execution_context": "INTERACTIVE_PRINCIPAL",
        "worker_id": None,
        "quota_class": None,
        "verdict": "INTERACTIVE_AUTH_READY",
        "reason_codes": [],
    }
    value.update(overrides)
    return value


def _executable(tmp_path: Path, body: bytes = b"#!/bin/sh\n") -> Path:
    binary = tmp_path / "claude"
    binary.write_bytes(body)
    binary.chmod(0o700)
    return binary


def test_command_builder_allows_only_provider_work_free_observations(tmp_path: Path):
    module = _load()
    binary = _executable(tmp_path)

    assert module.build_allowed_argv(binary, "version") == (str(binary), "--version")
    assert module.build_allowed_argv(binary, "auth_status") == (
        str(binary),
        "auth",
        "status",
    )
    for forbidden in (
        "print",
        "prompt",
        "resume",
        "continue",
        "fork",
        "respawn",
        "agents",
        "mcp",
        "browser",
    ):
        with pytest.raises(module.PreflightError, match="COMMAND_NOT_ALLOWED"):
            module.build_allowed_argv(binary, forbidden)


def test_auth_status_normalizes_only_native_subscription_selection():
    module = _load()
    normalized = module.normalize_auth_status(
        {
            "loggedIn": True,
            "authMethod": "claude.ai",
            "apiProvider": "firstParty",
            "subscriptionType": "max",
        }
    )
    assert normalized == module.AuthObservation(
        auth_ready=True,
        auth_method="claudeai",
        api_provider="first_party",
        reason_codes=(),
    )

    not_native = module.normalize_auth_status(
        {
            "loggedIn": True,
            "authMethod": "api_key",
            "apiProvider": "firstParty",
        }
    )
    assert not_native.auth_ready is False
    assert "NATIVE_AUTH_NOT_SELECTED" in not_native.reason_codes


def test_native_login_managed_key_source_does_not_override_selected_native_auth():
    module = _load()
    normalized = module.normalize_auth_status(
        {
            "loggedIn": True,
            "authMethod": "claude.ai",
            "apiProvider": "firstParty",
            "subscriptionType": None,
            "apiKeySource": "/login managed key",
        }
    )
    assert normalized == module.AuthObservation(
        auth_ready=True,
        auth_method="claudeai",
        api_provider="first_party",
        reason_codes=(),
    )


def test_unknown_selected_auth_values_fail_closed():
    module = _load()
    normalized = module.normalize_auth_status(
        {
            "loggedIn": True,
            "authMethod": "future_auth_surface",
            "apiProvider": "futureProvider",
        }
    )
    assert normalized.auth_ready is False
    assert normalized.auth_method == "non_native"
    assert normalized.api_provider == "non_native"
    assert normalized.reason_codes == ("NATIVE_AUTH_NOT_SELECTED",)


def test_auth_status_fails_closed_on_unknown_wire_and_discards_pii():
    module = _load()
    with pytest.raises(module.PreflightError, match="AUTH_STATUS_UNSUPPORTED"):
        module.normalize_auth_status(
            {
                "loggedIn": True,
                "authMethod": "claude.ai",
                "apiProvider": "firstParty",
                "newCredentialMode": "surprise",
            }
        )

    normalized = module.normalize_auth_status(
        {
            "loggedIn": True,
            "authMethod": "claude.ai",
            "apiProvider": "firstParty",
            "email": "private@example.com",
            "organization": "private-org",
        }
    )
    assert normalized.auth_ready is True
    assert "private@example.com" not in repr(normalized)
    assert "private-org" not in repr(normalized)


def test_auth_status_exit_one_is_logged_out_not_transport_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv,
            1,
            stdout='{"loggedIn":false,"authMethod":"none","apiProvider":"firstParty"}',
            stderr="not logged in",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    observed = module.observe_auth(binary)
    assert observed == module.AuthObservation(
        auth_ready=False,
        auth_method="unknown",
        api_provider="unknown",
        reason_codes=("LOGIN_REQUIRED",),
    )


def test_auth_status_rejects_malformed_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 0, stdout="not-json", stderr="provider prose"
        ),
    )
    with pytest.raises(module.PreflightError, match="AUTH_STATUS_UNSUPPORTED"):
        module.observe_auth(binary)


def test_auth_status_rejects_unexpected_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv,
            2,
            stdout='{"loggedIn":false}',
            stderr="provider failed with private@example.com",
        ),
    )
    with pytest.raises(module.PreflightError, match="PROVIDER_COMMAND_FAILED") as exc:
        module.observe_auth(binary)
    assert "private@example.com" not in str(exc.value)


def test_auth_status_timeout_is_typed_and_does_not_echo_provider_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)

    def timeout(argv, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=argv,
            timeout=kwargs.get("timeout", 1),
            output="private@example.com",
            stderr="sk-" + "x" * 30,
        )

    monkeypatch.setattr(module.subprocess, "run", timeout)
    with pytest.raises(module.PreflightError, match="PROVIDER_TIMEOUT") as exc:
        module.observe_auth(binary)
    assert "private@example.com" not in str(exc.value)
    assert "sk-" not in str(exc.value)


def test_auth_status_exit_code_must_match_logged_in_boolean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv,
            1,
            stdout='{"loggedIn":true,"authMethod":"claude.ai","apiProvider":"firstParty"}',
            stderr="",
        ),
    )
    with pytest.raises(module.PreflightError, match="AUTH_STATUS_UNSUPPORTED"):
        module.observe_auth(binary)


def test_auth_status_discards_known_pii_and_raw_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)
    secretish = "Bearer " + "x" * 24

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(
                {
                    "loggedIn": True,
                    "authMethod": "claude.ai",
                    "apiProvider": "firstParty",
                    "email": "private@example.com",
                    "organization": "private-org",
                }
            ),
            stderr=secretish,
        ),
    )
    observed = module.observe_auth(binary)
    rendered = repr(observed)
    assert observed.auth_ready is True
    assert "private@example.com" not in rendered
    assert "private-org" not in rendered
    assert secretish not in rendered


def test_receipt_is_closed_secret_free_and_context_bound():
    module = _load()
    value = _receipt(module)
    assert module.validate_receipt(value) == value

    # The closed V1 wire already reserves future worker-context receipts. Wire
    # validation is not authority to mint one from an arbitrary shell.
    worker_value = _receipt(
        module,
        execution_context="WORKER_BROKER",
        worker_id="claude-worker-01",
        quota_class="default",
        verdict="WORKER_CONTEXT_AUTH_READY",
    )
    assert module.validate_receipt(worker_value) == worker_value

    with pytest.raises(module.PreflightError, match="RECEIPT_INVALID"):
        module.validate_receipt({**value, "email": "private@example.com"})
    with pytest.raises(module.PreflightError, match="RECEIPT_INVALID"):
        module.validate_receipt(
            {**value, "execution_context": "WORKER_BROKER", "worker_id": None}
        )
    with pytest.raises(module.PreflightError, match="SECRET_SHAPED_VALUE"):
        module.validate_receipt({**value, "realm_label": "sk-" + "x" * 30})


def test_receipt_rejects_false_ready_contradiction():
    module = _load()
    contradictory = _receipt(
        module,
        auth_ready=False,
        auth_method="unknown",
        api_provider="unknown",
        verdict="INTERACTIVE_AUTH_READY",
        reason_codes=[],
    )
    with pytest.raises(module.PreflightError, match="RECEIPT_INVALID"):
        module.validate_receipt(contradictory)


def test_builder_cannot_mint_worker_context_ready_before_broker_slice():
    module = _load()
    auth = module.AuthObservation(
        auth_ready=True,
        auth_method="claudeai",
        api_provider="first_party",
        reason_codes=(),
    )
    with pytest.raises(module.PreflightError, match="EXECUTION_CONTEXT_UNPROVEN"):
        module.build_ready_receipt(
            realm_label="claude-pro-01",
            host_ref="host-01234567",
            os_principal_ref="principal-01234567",
            execution_context="WORKER_BROKER",
            worker_id="claude-worker-01",
            quota_class="default",
            binary_sha256="a" * 64,
            version="2.1.0",
            auth=auth,
            observed_at="2026-08-27T23:30:00Z",
        )


def test_cli_refuses_caller_declared_identity_until_owner_seam_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)

    def provider_must_not_run(*args, **kwargs):
        pytest.fail("provider metadata commands ran before canonical identity ownership was proven")

    monkeypatch.setattr(module, "observe_binary", provider_must_not_run)
    monkeypatch.setattr(module, "observe_auth", provider_must_not_run)

    with pytest.raises(module.PreflightError, match="HOST_IDENTITY_SEAM_UNAVAILABLE"):
        module.main(
            [
                "--realm-label",
                "claude-pro-01",
                "--host-ref",
                "host-01234567",
                "--os-principal-ref",
                "principal-01234567",
                "--execution-context",
                "INTERACTIVE_PRINCIPAL",
                "--claude-binary",
                str(binary),
            ]
        )


def test_binary_observation_is_size_bounded_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path, b"123456789")
    monkeypatch.setattr(module, "MAX_BINARY_BYTES", 8, raising=False)

    def provider_must_not_run(*args, **kwargs):
        pytest.fail("oversized provider binary was executed")

    monkeypatch.setattr(module, "_run", provider_must_not_run)
    with pytest.raises(module.PreflightError, match="BINARY_INVALID"):
        module.observe_binary(binary)


def test_missing_binary_is_typed_refusal(tmp_path: Path):
    module = _load()
    with pytest.raises(module.PreflightError, match="BINARY_UNAVAILABLE"):
        module.observe_binary((tmp_path / "missing-claude").resolve())


def test_host_and_principal_refs_fail_closed_instead_of_being_invented():
    module = _load()
    with pytest.raises(module.PreflightError, match="HOST_IDENTITY_SEAM_UNAVAILABLE"):
        module.require_canonical_identity("local-unbound", "principal-01234567")
    with pytest.raises(module.PreflightError, match="PRINCIPAL_IDENTITY_SEAM_UNAVAILABLE"):
        module.require_canonical_identity("host-01234567", "")
    assert module.require_canonical_identity(
        "host-01234567", "principal-01234567"
    ) == ("host-01234567", "principal-01234567")
