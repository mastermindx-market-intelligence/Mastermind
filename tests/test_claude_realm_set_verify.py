from __future__ import annotations

import builtins
import importlib.util
import json
import os
import socket
import sqlite3
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest


_ROOT = Path(__file__).resolve().parents[1]
_MODULE_PATH = _ROOT / "ops" / "executive_os" / "claude-realm-set-verify.py"
_VERIFIED_AT = "2026-08-28T12:00:01Z"
_OUTPUT_KEYS = {
    "schema",
    "verified_at",
    "observed_realm_count",
    "worker_ready_realm_count",
    "realm_labels",
    "worker_ready_realm_labels",
    "unique_host_principal_pairs",
    "identity_confidence_floor",
    "verdict",
    "reason_codes",
}


def _load():
    assert _MODULE_PATH.is_file(), "missing claude-realm-set-verify.py implementation"
    spec = importlib.util.spec_from_file_location("claude_realm_set_verify", _MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _receipt(
    realm_label: str,
    identity: int,
    *,
    execution_context: str = "WORKER_BROKER",
    observed_at: str = "2026-08-28T12:00:00Z",
    **overrides,
):
    worker_ready = execution_context == "WORKER_BROKER"
    value = {
        "schema": "mastermind.claude_worker_preflight.v1",
        "realm_label": realm_label,
        "host_ref": f"host-0000000{identity}",
        "os_principal_ref": f"principal-0000000{identity}",
        "observed_at": observed_at,
        "claude_binary_sha256": "a" * 64,
        "claude_version": "2.1.0",
        "auth_ready": True,
        "auth_method": "claudeai",
        "api_provider": "first_party",
        "auth_identity_confidence": "SLOT_ONLY",
        "macos_credential_isolation_basis": "OS_PRINCIPAL_KEYCHAIN",
        "execution_context": execution_context,
        "worker_id": f"claude-worker-{identity}" if worker_ready else None,
        "quota_class": "default" if worker_ready else None,
        "verdict": (
            "WORKER_CONTEXT_AUTH_READY"
            if worker_ready
            else "INTERACTIVE_AUTH_READY"
        ),
        "reason_codes": [],
    }
    value.update(overrides)
    return value


def _verify(module, receipts):
    return module.verify_realm_set(receipts, verified_at=_VERIFIED_AT)


def test_two_current_distinct_native_worker_realms_emit_only_the_closed_result():
    module = _load()

    result = _verify(
        module,
        [
            _receipt("claude-pro-b", 2),
            _receipt("claude-pro-a", 1),
        ],
    )

    assert set(result) == _OUTPUT_KEYS
    assert result == {
        "schema": "mastermind.claude_realm_set_verification.v1",
        "verified_at": _VERIFIED_AT,
        "observed_realm_count": 2,
        "worker_ready_realm_count": 2,
        "realm_labels": ["claude-pro-a", "claude-pro-b"],
        "worker_ready_realm_labels": ["claude-pro-a", "claude-pro-b"],
        "unique_host_principal_pairs": 2,
        "identity_confidence_floor": "SLOT_ONLY",
        "verdict": "DISTINCT_NATIVE_REALMS",
        "reason_codes": [],
    }
    rendered = json.dumps(result, sort_keys=True)
    assert "host-" not in rendered
    assert "principal-" not in rendered


def test_duplicate_realm_label_refuses_even_when_host_principal_pairs_differ():
    module = _load()

    with pytest.raises(module.RealmSetVerificationError, match="DUPLICATE_REALM_LABEL"):
        _verify(
            module,
            [
                _receipt("claude-pro-duplicate", 1),
                _receipt("claude-pro-duplicate", 2),
            ],
        )


def test_duplicate_host_principal_pair_refuses_as_a_realm_collision():
    module = _load()
    first = _receipt("claude-pro-a", 1)
    second = _receipt(
        "claude-pro-b",
        2,
        host_ref=first["host_ref"],
        os_principal_ref=first["os_principal_ref"],
    )

    with pytest.raises(module.RealmSetVerificationError, match="REALM_COLLISION"):
        _verify(module, [first, second])


@pytest.mark.parametrize(
    "receipts",
    [
        [],
        [_receipt(f"claude-pro-{number}", number) for number in range(1, 9)],
    ],
)
def test_receipt_count_outside_one_through_seven_refuses(receipts):
    module = _load()

    with pytest.raises(module.RealmSetVerificationError, match="RECEIPT_COUNT_OUT_OF_RANGE"):
        _verify(module, receipts)


@pytest.mark.parametrize(
    "receipt",
    [
        {**_receipt("claude-pro-extra", 1), "CLAUDE_CONFIG_DIR": "/private/realm-a"},
        _receipt("claude-pro-schema", 1, schema="wrong.schema.v1"),
        _receipt("claude-pro-confidence", 1, auth_identity_confidence="UNKNOWN"),
        _receipt(
            "claude-pro-nonnative",
            1,
            auth_ready=False,
            auth_method="non_native",
            api_provider="non_native",
            macos_credential_isolation_basis="UNKNOWN",
            verdict="NATIVE_AUTH_NOT_SELECTED",
            reason_codes=["NATIVE_AUTH_NOT_SELECTED"],
        ),
        _receipt(
            "claude-pro-unaccepted",
            1,
            auth_ready=False,
            auth_method="unknown",
            api_provider="unknown",
            macos_credential_isolation_basis="UNKNOWN",
            verdict="LOGIN_REQUIRED",
            reason_codes=["LOGIN_REQUIRED"],
        ),
    ],
)
def test_malformed_or_nonaccepted_preflight_receipt_refuses(receipt):
    module = _load()

    with pytest.raises(module.RealmSetVerificationError):
        _verify(module, [receipt])


@pytest.mark.parametrize(
    "observed_at",
    [
        "2026-08-27T12:00:00Z",
        "2026-08-28T12:00:02Z",
        "not-a-timestamp",
    ],
)
def test_stale_invalid_or_future_incoherent_observation_time_refuses(observed_at):
    module = _load()

    with pytest.raises(module.RealmSetVerificationError):
        _verify(module, [_receipt("claude-pro-time", 1, observed_at=observed_at)])


def test_interactive_native_readiness_is_not_worker_executable_capacity():
    module = _load()

    result = _verify(
        module,
        [
            _receipt(
                f"claude-pro-interactive-{identity}",
                identity,
                execution_context="INTERACTIVE_PRINCIPAL",
            )
            for identity in range(1, 6)
        ],
    )

    assert result["observed_realm_count"] == 5
    assert result["worker_ready_realm_count"] == 0
    assert result["worker_ready_realm_labels"] == []
    assert result["verdict"] == "EXECUTION_CONTEXT_UNPROVEN"
    assert result["reason_codes"] == ["EXECUTION_CONTEXT_UNPROVEN"]


def test_five_distinct_current_worker_realms_can_prove_a_five_realm_set():
    module = _load()

    result = _verify(
        module,
        [_receipt(f"claude-pro-{identity}", identity) for identity in range(1, 6)],
    )

    assert result["observed_realm_count"] == 5
    assert result["worker_ready_realm_count"] == 5
    assert result["verdict"] == "DISTINCT_NATIVE_REALMS"
    assert result["reason_codes"] == []


def test_five_labels_on_one_pair_cannot_manufacture_a_five_realm_set():
    module = _load()
    shared = _receipt("claude-pro-1", 1)
    receipts = [shared]
    for identity in range(2, 6):
        receipts.append(
            _receipt(
                f"claude-pro-{identity}",
                identity,
                host_ref=shared["host_ref"],
                os_principal_ref=shared["os_principal_ref"],
            )
        )

    with pytest.raises(module.RealmSetVerificationError, match="REALM_COLLISION"):
        _verify(module, receipts)


def test_verification_performs_no_filesystem_process_network_or_persistence_effects(
    monkeypatch: pytest.MonkeyPatch,
):
    module = _load()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("realm-set verification attempted a forbidden side effect")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(Path, "glob", forbidden)
    monkeypatch.setattr(Path, "iterdir", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    monkeypatch.setattr(os, "popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)

    result = _verify(module, [_receipt("claude-pro-pure", 1)])

    assert result["verdict"] == "DISTINCT_NATIVE_REALMS"
