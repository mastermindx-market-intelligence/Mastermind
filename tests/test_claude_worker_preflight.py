from __future__ import annotations

import importlib.util
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


def test_command_builder_allows_only_provider_work_free_observations(tmp_path: Path):
    module = _load()
    binary = tmp_path / "claude"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o700)

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


def test_receipt_is_closed_secret_free_and_context_bound():
    module = _load()
    value = _receipt(module)
    assert module.validate_receipt(value) == value

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


def test_host_and_principal_refs_fail_closed_instead_of_being_invented():
    module = _load()
    with pytest.raises(module.PreflightError, match="HOST_IDENTITY_SEAM_UNAVAILABLE"):
        module.require_canonical_identity("local-unbound", "principal-01234567")
    with pytest.raises(module.PreflightError, match="PRINCIPAL_IDENTITY_SEAM_UNAVAILABLE"):
        module.require_canonical_identity("host-01234567", "")
    assert module.require_canonical_identity(
        "host-01234567", "principal-01234567"
    ) == ("host-01234567", "principal-01234567")
