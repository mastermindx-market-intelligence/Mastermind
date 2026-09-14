from __future__ import annotations

from pathlib import Path

import pytest

from control_plane.executive_privileged_action import (
    REQUEST_SCHEMA,
    STATUS_REQUEST_SCHEMA,
    PrivilegedActionError,
    build_argv,
    canonical_request_bytes,
    validate_request,
    validate_status_request,
)


def _request(action: str, args: dict[str, object] | None = None, request_id: str = "req-001") -> dict[str, object]:
    return {
        "schema": REQUEST_SCHEMA,
        "request_id": request_id,
        "action": action,
        "args": args or {},
    }


def test_unknown_action_refuses() -> None:
    with pytest.raises(PrivilegedActionError, match="unknown privileged action"):
        validate_request(_request("shell"))


def test_request_shape_is_exact() -> None:
    request = _request("executive.services.start")
    request["command"] = "/bin/sh"
    with pytest.raises(PrivilegedActionError, match="request keys"):
        validate_request(request)


@pytest.mark.parametrize(
    "request_id",
    ["ab", "-bad", ".bad", "bad space", "a" * 65],
)
def test_request_id_must_be_bounded_safe_token(request_id: str) -> None:
    with pytest.raises(PrivilegedActionError, match="request_id"):
        validate_request(_request("executive.services.start", request_id=request_id))


def test_service_start_has_fixed_argv(tmp_path: Path) -> None:
    request = validate_request(_request("executive.services.start"))
    assert build_argv(request, tmp_path) == (
        "/bin/bash",
        str(tmp_path / "ops/executive_os/service-control.sh"),
        "start",
    )


@pytest.mark.parametrize("verb", ["start", "stop", "restart"])
def test_service_actions_reject_all_arguments(verb: str) -> None:
    with pytest.raises(PrivilegedActionError, match="arguments"):
        validate_request(_request(f"executive.services.{verb}", {"shell": "/bin/sh"}))


def test_verify_only_uses_reviewed_worker_auth_script(tmp_path: Path) -> None:
    request = validate_request(
        _request("executive.worker_auth.verify_only", {"slot_id": "codex-pro-02"})
    )
    assert build_argv(request, tmp_path) == (
        "/bin/bash",
        str(tmp_path / "ops/executive_os/provision-worker-auth.sh"),
        "--verify-only",
        "--slot-id",
        "codex-pro-02",
    )


def test_verify_only_can_target_company_default_without_slot(tmp_path: Path) -> None:
    request = validate_request(_request("executive.worker_auth.verify_only"))
    assert build_argv(request, tmp_path) == (
        "/bin/bash",
        str(tmp_path / "ops/executive_os/provision-worker-auth.sh"),
        "--verify-only",
    )


@pytest.mark.parametrize("slot", ["codex-pro-00", "codex-pro-04", "worker-01", "../codex-pro-01"])
def test_slot_id_is_closed_reviewed_inventory(slot: str) -> None:
    with pytest.raises(PrivilegedActionError, match="slot_id"):
        validate_request(_request("executive.worker_auth.verify_only", {"slot_id": slot}))


def test_verify_ready_slot_builds_only_slot_and_expiry(tmp_path: Path) -> None:
    request = validate_request(
        _request(
            "executive.worker_auth.verify_ready",
            {
                "slot_id": "codex-pro-01",
                "credential_expires_at": "2026-09-14T00:00:00Z",
            },
        )
    )
    assert build_argv(request, tmp_path) == (
        "/bin/bash",
        str(tmp_path / "ops/executive_os/provision-worker-auth.sh"),
        "--verify-ready",
        "--slot-id",
        "codex-pro-01",
        "--credential-expires-at",
        "2026-09-14T00:00:00Z",
    )


def test_verify_ready_company_binding_has_closed_policy_values(tmp_path: Path) -> None:
    request = validate_request(
        _request(
            "executive.worker_auth.verify_ready",
            {
                "expected_credential_kind": "service-account",
                "workspace_binding_class": "company-workspace-admin-attested",
                "credential_expires_at": "2026-09-14T00:00:00Z",
            },
        )
    )
    assert build_argv(request, tmp_path) == (
        "/bin/bash",
        str(tmp_path / "ops/executive_os/provision-worker-auth.sh"),
        "--verify-ready",
        "--expected-credential-kind",
        "service-account",
        "--workspace-binding-class",
        "company-workspace-admin-attested",
        "--credential-expires-at",
        "2026-09-14T00:00:00Z",
    )


def test_verify_ready_refuses_slot_plus_policy_override() -> None:
    with pytest.raises(PrivilegedActionError, match="slot_id.*policy"):
        validate_request(
            _request(
                "executive.worker_auth.verify_ready",
                {
                    "slot_id": "codex-pro-01",
                    "expected_credential_kind": "device-auth",
                    "workspace_binding_class": "company-workspace-admin-attested",
                    "credential_expires_at": "2026-09-14T00:00:00Z",
                },
            )
        )


@pytest.mark.parametrize(
    "expiry",
    [
        "2026-09-14 00:00:00Z",
        "2026-9-14T00:00:00Z",
        "2026-09-14T00:00:00+00:00",
        "2026-02-30T00:00:00Z",
    ],
)
def test_verify_ready_requires_exact_valid_utc_expiry(expiry: str) -> None:
    with pytest.raises(PrivilegedActionError, match="credential_expires_at"):
        validate_request(
            _request(
                "executive.worker_auth.verify_ready",
                {
                    "slot_id": "codex-pro-03",
                    "credential_expires_at": expiry,
                },
            )
        )


def test_verify_ready_company_mode_requires_all_policy_fields() -> None:
    with pytest.raises(PrivilegedActionError, match="arguments"):
        validate_request(
            _request(
                "executive.worker_auth.verify_ready",
                {"credential_expires_at": "2026-09-14T00:00:00Z"},
            )
        )


@pytest.mark.parametrize("kind", ["token", "api-key", "password"])
def test_verify_ready_company_mode_rejects_unreviewed_credential_kind(kind: str) -> None:
    with pytest.raises(PrivilegedActionError, match="expected_credential_kind"):
        validate_request(
            _request(
                "executive.worker_auth.verify_ready",
                {
                    "expected_credential_kind": kind,
                    "workspace_binding_class": "company-workspace-admin-attested",
                    "credential_expires_at": "2026-09-14T00:00:00Z",
                },
            )
        )


def test_recover_transaction_has_fixed_argv(tmp_path: Path) -> None:
    request = validate_request(
        _request("executive.worker_auth.recover_transaction", {"slot_id": "codex-pro-03"})
    )
    assert build_argv(request, tmp_path) == (
        "/bin/bash",
        str(tmp_path / "ops/executive_os/provision-worker-auth.sh"),
        "--recover-readiness-transaction",
        "--slot-id",
        "codex-pro-03",
    )


def test_exactly_six_actions_are_accepted() -> None:
    cases = {
        "executive.services.start": {},
        "executive.services.stop": {},
        "executive.services.restart": {},
        "executive.worker_auth.verify_only": {},
        "executive.worker_auth.verify_ready": {
            "slot_id": "codex-pro-01",
            "credential_expires_at": "2026-09-14T00:00:00Z",
        },
        "executive.worker_auth.recover_transaction": {},
    }
    assert {validate_request(_request(action, args)).action for action, args in cases.items()} == set(cases)


def _status_request(request_id: str = "req-001") -> dict[str, object]:
    return {"schema": STATUS_REQUEST_SCHEMA, "request_id": request_id}


def test_status_request_accepts_exact_keys() -> None:
    status = validate_status_request(_status_request())
    assert status.schema == STATUS_REQUEST_SCHEMA
    assert status.request_id == "req-001"
    assert status.to_dict() == {"schema": STATUS_REQUEST_SCHEMA, "request_id": "req-001"}


def test_status_request_rejects_wrong_schema() -> None:
    request = _status_request()
    request["schema"] = REQUEST_SCHEMA
    with pytest.raises(PrivilegedActionError, match="schema"):
        validate_status_request(request)


@pytest.mark.parametrize(
    "extra_or_missing",
    [
        {"schema": STATUS_REQUEST_SCHEMA, "request_id": "req-001", "action": "executive.services.start"},
        {"schema": STATUS_REQUEST_SCHEMA, "request_id": "req-001", "args": {}},
        {"schema": STATUS_REQUEST_SCHEMA},
        {"request_id": "req-001"},
    ],
)
def test_status_request_requires_exact_keys(extra_or_missing: dict[str, object]) -> None:
    with pytest.raises(PrivilegedActionError, match="keys"):
        validate_status_request(extra_or_missing)


@pytest.mark.parametrize(
    "request_id",
    ["ab", "-bad", ".bad", "bad space", "a" * 65, "../etc/passwd", "req; rm -rf /", "req`id`"],
)
def test_status_request_id_reuses_bounded_safe_token_grammar(request_id: str) -> None:
    with pytest.raises(PrivilegedActionError, match="request_id"):
        validate_status_request(_status_request(request_id))


def test_canonical_request_bytes_are_stable_across_mapping_order() -> None:
    left = validate_request(
        {
            "action": "executive.worker_auth.verify_only",
            "args": {"slot_id": "codex-pro-01"},
            "request_id": "req-stable",
            "schema": REQUEST_SCHEMA,
        }
    )
    right = validate_request(
        {
            "schema": REQUEST_SCHEMA,
            "request_id": "req-stable",
            "action": "executive.worker_auth.verify_only",
            "args": {"slot_id": "codex-pro-01"},
        }
    )
    assert canonical_request_bytes(left) == canonical_request_bytes(right)
    assert canonical_request_bytes(left).endswith(b"\n")
