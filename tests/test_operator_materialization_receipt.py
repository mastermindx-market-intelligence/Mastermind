"""Strict durability and identity proofs for Operator materialization receipts."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from control_plane import operator_materialization_receipt as receipt_module

from control_plane.operator_materialization_receipt import (
    MATERIALIZATION_RECEIPT_SCHEMA,
    MAX_MATERIALIZATION_RECEIPT_BYTES,
    MaterializationReceiptConflict,
    OperatorMaterializationReceiptError,
    build_operator_materialization_receipt,
    canonical_json_bytes,
    load_operator_materialization_receipt,
    materialization_receipt_path,
    persist_operator_materialization_receipt,
    read_operator_materialization_receipt,
    requested_profile_digest,
    validate_materialization_request,
)


def _inputs(*, resume: bool = False) -> dict[str, object]:
    attempt_id = "ATT-RECEIPT"
    generation_number = 2 if resume else 1
    provider_session_id = "thread-receipt"
    process_identity = {
        "pid": 7001,
        "pgid": 7001,
        "process_start_identity": "start-7001",
        "boot_id": "boot-receipt",
    }
    return {
        "operation_command_id": (
            f"ohf-op:recover-resume:{attempt_id}"
            if resume
            else f"ohf-op:start:{attempt_id}"
        ),
        "operation_kind": "resume_session" if resume else "start_session",
        "attempt_id": attempt_id,
        "worker_id": "codex-01",
        "session_epoch_id": "epoch-receipt",
        "process_generation_id": f"generation-{generation_number}",
        "generation_number": generation_number,
        "requested_profile_digest": "a" * 64,
        "provider_session_id": provider_session_id,
        "expected_provider_session_id": provider_session_id if resume else None,
        "process_identity": process_identity,
        "observed_attestation": {
            "served_model": "gpt-5.6-sol",
            "harness_version": "0.147.0",
            "harness_binary_digest": "b" * 64,
            "capabilities": [],
            "effective_skills": [],
            "effective_mcp": [],
            "effective_plugins_or_apps": [],
            "sandbox_state": "read-only",
            "approval_state": "never",
            "network_state": "disabled",
            "effective_config_digest": "c" * 64,
            "auth": {
                "worker_id": "codex-01",
                "provider": "openai-codex",
                "auth_class": "oauth",
                "plan_type": None,
                "nonsecret_provider_account_id": None,
                "identity_confidence": "UNKNOWN",
                "attestation_status": "ACCOUNT_REALM_ATTESTATION_UNPROVEN",
            },
            "workspace": {
                "workspace_path": "/var/empty/workspace",
                "base_sha": "d" * 40,
                "device": 1,
                "inode": 3,
                "uid": os.geteuid(),
                "gid": os.getegid(),
            },
            "supports_subagent_capability_ceiling": "FALSE",
            "unknown_fields": [],
        },
        "process_credentials": {
            "process_identity": process_identity,
            "os_principal_name": "fixture-worker",
            "os_principal_uid": os.geteuid(),
        },
        "provider_home_identity": {
            "path": "/var/empty/codex-01",
            "device": 1,
            "inode": 2,
            "uid": os.geteuid(),
            "gid": os.getegid(),
            "mode": 0o700,
        },
        "created_at": "2026-09-03T00:00:00+00:00",
    }


def _receipt(*, resume: bool = False):
    values = _inputs(resume=resume)
    expected = values.pop("expected_provider_session_id")
    validate_materialization_request(
        operation_command_id=str(values["operation_command_id"]),
        operation_kind=str(values["operation_kind"]),
        attempt_id=str(values["attempt_id"]),
        worker_id=str(values["worker_id"]),
        session_epoch_id=str(values["session_epoch_id"]),
        process_generation_id=str(values["process_generation_id"]),
        generation_number=int(values["generation_number"]),
        expected_provider_session_id=expected,
    )
    return build_operator_materialization_receipt(**values)


def test_receipt_is_closed_canonical_digest_bound_json() -> None:
    receipt = _receipt()
    raw = canonical_json_bytes(receipt.to_dict())
    assert len(raw) < MAX_MATERIALIZATION_RECEIPT_BYTES
    assert raw == json.dumps(
        receipt.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    assert receipt.schema == MATERIALIZATION_RECEIPT_SCHEMA
    unsigned = receipt.to_dict()
    digest = unsigned.pop("receipt_digest")
    assert digest == hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()
    assert load_operator_materialization_receipt(raw) == receipt


@pytest.mark.parametrize(
    ("resume", "change", "match"),
    [
        (False, {"generation_number": 2}, "generation 1"),
        (False, {"operation_command_id": "ohf-op:start:OTHER"}, "command"),
        (False, {"expected_provider_session_id": "thread-receipt"}, "must be absent"),
        (True, {"generation_number": 1}, "generation 2"),
        (True, {"expected_provider_session_id": None}, "is required"),
        (True, {"expected_provider_session_id": "thread-other"}, "handoff"),
    ],
)
def test_request_validation_enforces_exact_g1_g2_law(
    resume: bool, change: dict[str, object], match: str
) -> None:
    values = _inputs(resume=resume)
    values.update(change)
    with pytest.raises(OperatorMaterializationReceiptError, match=match):
        validate_materialization_request(
            operation_command_id=str(values["operation_command_id"]),
            operation_kind=str(values["operation_kind"]),
            attempt_id=str(values["attempt_id"]),
            worker_id=str(values["worker_id"]),
            session_epoch_id=str(values["session_epoch_id"]),
            process_generation_id=str(values["process_generation_id"]),
            generation_number=int(values["generation_number"]),
            expected_provider_session_id=values["expected_provider_session_id"],
            observed_provider_session_id="thread-receipt",
        )


def test_profile_digest_is_canonical_and_order_independent() -> None:
    assert requested_profile_digest({"worker_id": "codex-01", "nested": {"b": 2, "a": 1}}) == requested_profile_digest(
        {"nested": {"a": 1, "b": 2}, "worker_id": "codex-01"}
    )


def test_parser_refuses_duplicate_noncanonical_oversized_and_digest_drift() -> None:
    receipt = _receipt().to_dict()
    canonical = canonical_json_bytes(receipt)
    duplicate = canonical[:-1] + b',"schema":"mastermind.operator_materialization_receipt/v1"}'
    with pytest.raises(OperatorMaterializationReceiptError, match="duplicate"):
        load_operator_materialization_receipt(duplicate)
    with pytest.raises(OperatorMaterializationReceiptError, match="canonical"):
        load_operator_materialization_receipt(b" " + canonical)
    with pytest.raises(OperatorMaterializationReceiptError, match="ceiling"):
        load_operator_materialization_receipt(b" " * (MAX_MATERIALIZATION_RECEIPT_BYTES + 1))
    receipt["provider_session_id"] = "thread-drift"
    with pytest.raises(OperatorMaterializationReceiptError, match="digest"):
        load_operator_materialization_receipt(canonical_json_bytes(receipt))


def test_builder_refuses_secret_shaped_attestation_and_cross_identity_drift() -> None:
    values = _inputs()
    values.pop("expected_provider_session_id")
    values["observed_attestation"] = {
        **values["observed_attestation"],
        "access_token": "must-not-land",
    }
    with pytest.raises(OperatorMaterializationReceiptError, match="credential-shaped"):
        build_operator_materialization_receipt(**values)

    values = _inputs()
    values.pop("expected_provider_session_id")
    values["process_credentials"] = dict(values["process_credentials"])
    values["process_credentials"]["process_identity"] = {
        **values["process_identity"],
        "pid": 9999,
    }
    with pytest.raises(OperatorMaterializationReceiptError, match="process identity"):
        build_operator_materialization_receipt(**values)

    values = _inputs()
    values.pop("expected_provider_session_id")
    values["provider_home_identity"] = {
        **values["provider_home_identity"],
        "path": "/var/empty/../private/codex-01",
    }
    with pytest.raises(OperatorMaterializationReceiptError, match="canonical absolute"):
        build_operator_materialization_receipt(**values)

    values = _inputs()
    values.pop("expected_provider_session_id")
    values["observed_attestation"] = {1: "integer key"}
    with pytest.raises(OperatorMaterializationReceiptError, match="keys must be strings"):
        build_operator_materialization_receipt(**values)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("process_identity", {"pid": 7999}),
        ("observed_attestation", {"served_model": "gpt-drift"}),
        ("process_credentials", {"os_principal_name": "drift-worker"}),
        ("provider_home_identity", {"inode": 9999}),
    ],
)
def test_persistence_revalidates_mutated_nested_receipt_before_path_creation(
    tmp_path: Path,
    field: str,
    replacement: dict[str, object],
) -> None:
    receipt = _receipt()
    nested = getattr(receipt, field)
    nested.update(replacement)
    path = materialization_receipt_path(tmp_path, receipt.operation_command_id)

    with pytest.raises(OperatorMaterializationReceiptError):
        persist_operator_materialization_receipt(
            tmp_path, receipt, expected_owner_uid=os.geteuid()
        )

    assert not path.exists()
    clean = _receipt()
    assert persist_operator_materialization_receipt(
        tmp_path, clean, expected_owner_uid=os.geteuid()
    ) == clean


def test_persistence_refuses_direct_stale_digest_before_path_creation(
    tmp_path: Path,
) -> None:
    receipt = _receipt()
    forged = receipt_module.OperatorMaterializationReceipt(
        **{
            **receipt.to_dict(),
            "provider_session_id": "thread-forged",
        }
    )
    path = materialization_receipt_path(tmp_path, receipt.operation_command_id)

    with pytest.raises(OperatorMaterializationReceiptError, match="digest"):
        persist_operator_materialization_receipt(
            tmp_path, forged, expected_owner_uid=os.geteuid()
        )

    assert not path.exists()


def test_persistence_detaches_snapshot_before_caller_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = _receipt()
    original_pid = receipt.process_identity["pid"]
    original_canonical_json_bytes = receipt_module.canonical_json_bytes
    mutated = False

    def mutate_after_serialization(value: object) -> bytes:
        nonlocal mutated
        raw = original_canonical_json_bytes(value)
        if (
            not mutated
            and isinstance(value, dict)
            and "receipt_digest" in value
        ):
            mutated = True
            receipt.process_identity["pid"] = 7999
        return raw

    monkeypatch.setattr(
        receipt_module, "canonical_json_bytes", mutate_after_serialization
    )
    persisted = persist_operator_materialization_receipt(
        tmp_path, receipt, expected_owner_uid=os.geteuid()
    )

    assert mutated is True
    assert persisted.process_identity["pid"] == original_pid
    assert read_operator_materialization_receipt(
        tmp_path,
        receipt.operation_command_id,
        expected_owner_uid=os.geteuid(),
    ) == persisted


def _redigest_with_attestation(
    receipt: dict[str, object], attestation: object
) -> bytes:
    value = {**receipt, "observed_attestation": attestation}
    unsigned = {key: item for key, item in value.items() if key != "receipt_digest"}
    value["receipt_digest"] = hashlib.sha256(
        canonical_json_bytes(unsigned)
    ).hexdigest()
    return canonical_json_bytes(value)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: {**value, "unknown": "field"},
        lambda value: {key: item for key, item in value.items() if key != "served_model"},
        lambda value: {**value, "served_model": 123},
        lambda value: {
            **value,
            "supports_subagent_capability_ceiling": "MAYBE",
        },
        lambda value: {**value, "auth": []},
        lambda value: {
            **value,
            "auth": {**value["auth"], "worker_id": "codex-other"},
        },
        lambda value: {
            **value,
            "workspace": {**value["workspace"], "device": True},
        },
        lambda value: {
            **value,
            "capabilities": [
                {
                    "kind": "resource",
                    "name": "fixture",
                    "skill_content_digest": None,
                    "tool_schema_digest": None,
                    "mcp_server_identity": None,
                    "mcp_server_version": None,
                    "mcp_auth_status": None,
                    "resource_contract_digest": "not-a-digest",
                }
            ],
        },
        lambda value: {**value, "effective_mcp": "not-an-array"},
    ],
)
def test_loader_refuses_noncanonical_or_cross_spliced_attestation(
    mutate,
) -> None:
    receipt = _receipt().to_dict()
    attestation = mutate(dict(receipt["observed_attestation"]))
    with pytest.raises(OperatorMaterializationReceiptError):
        load_operator_materialization_receipt(
            _redigest_with_attestation(receipt, attestation)
        )


@pytest.mark.parametrize(
    "key",
    ["oauthToken", "x-api-key", "credentials", "client-secret"],
)
def test_attestation_refuses_normalized_credential_aliases_without_echo(
    key: str,
) -> None:
    values = _inputs()
    values.pop("expected_provider_session_id")
    secret = "sk-" + "secret-value-that-must-not-echo"
    values["observed_attestation"] = {
        **values["observed_attestation"],
        key: secret,
    }
    with pytest.raises(OperatorMaterializationReceiptError) as failed:
        build_operator_materialization_receipt(**values)
    assert secret not in str(failed.value)


@pytest.mark.parametrize(
    "secret",
    [
        "ghp_" + "abcdefghijklmnopqrstuvwxyz1234567890",
        "xoxb-" + "123456789012-abcdefghijklmnopqrstuv",
        "Bearer " + "abcdefghijklmnopqrstuvwxyz123456",
        ".".join(
            (
                "eyJhbGciOiJIUzI1NiJ9",
                "eyJzdWIiOiIxMjM0NTY3ODkwIn0",
                "signature123456",
            )
        ),
        "-----BEGIN " + "PRIVATE KEY-----",
    ],
)
def test_attestation_refuses_secret_shaped_leaf_values_without_echo(
    secret: str,
) -> None:
    values = _inputs()
    values.pop("expected_provider_session_id")
    values["observed_attestation"] = {
        **values["observed_attestation"],
        "served_model": secret,
    }
    with pytest.raises(OperatorMaterializationReceiptError) as failed:
        build_operator_materialization_receipt(**values)
    assert secret not in str(failed.value)


def test_create_only_persistence_round_trips_and_exact_replay_is_noop(
    tmp_path: Path,
) -> None:
    receipt = _receipt()
    path = materialization_receipt_path(tmp_path, receipt.operation_command_id)
    persisted = persist_operator_materialization_receipt(
        tmp_path, receipt, expected_owner_uid=os.geteuid()
    )
    assert persisted == receipt
    assert path.is_file()
    assert path.stat().st_mode & 0o777 == 0o600
    before = path.stat().st_mtime_ns
    assert persist_operator_materialization_receipt(
        tmp_path, receipt, expected_owner_uid=os.geteuid()
    ) == receipt
    assert path.stat().st_mtime_ns == before
    assert read_operator_materialization_receipt(
        tmp_path, receipt.operation_command_id, expected_owner_uid=os.geteuid()
    ) == receipt


def test_create_only_persistence_refuses_semantic_overwrite(tmp_path: Path) -> None:
    receipt = _receipt()
    persist_operator_materialization_receipt(
        tmp_path, receipt, expected_owner_uid=os.geteuid()
    )
    changed = receipt.to_dict()
    changed["provider_session_id"] = "thread-other"
    changed.pop("receipt_digest")
    changed_receipt = build_operator_materialization_receipt(**changed)
    with pytest.raises(MaterializationReceiptConflict, match="conflicts"):
        persist_operator_materialization_receipt(
            tmp_path, changed_receipt, expected_owner_uid=os.geteuid()
        )


def test_reader_refuses_symlinked_or_linked_receipt(tmp_path: Path) -> None:
    receipt = _receipt()
    path = materialization_receipt_path(tmp_path, receipt.operation_command_id)
    path.parent.parent.mkdir(mode=0o700)
    path.parent.mkdir(mode=0o700)
    target = tmp_path / "target.json"
    target.write_bytes(canonical_json_bytes(receipt.to_dict()))
    target.chmod(0o600)
    path.symlink_to(target)
    with pytest.raises(OperatorMaterializationReceiptError, match="receipt"):
        read_operator_materialization_receipt(
            tmp_path, receipt.operation_command_id, expected_owner_uid=os.geteuid()
        )

    path.unlink()
    os.link(target, path)
    with pytest.raises(OperatorMaterializationReceiptError, match="link count"):
        read_operator_materialization_receipt(
            tmp_path, receipt.operation_command_id, expected_owner_uid=os.geteuid()
        )


def test_persistence_refuses_directory_mode_drift(tmp_path: Path) -> None:
    receipt = _receipt()
    root = tmp_path / ".operator-materializations"
    root.mkdir(mode=0o755)
    with pytest.raises(OperatorMaterializationReceiptError, match="mode"):
        persist_operator_materialization_receipt(
            tmp_path, receipt, expected_owner_uid=os.geteuid()
        )


@pytest.mark.parametrize("replacement", ["identical", "conflicting", "symlink", "fifo"])
def test_reader_refuses_receipt_name_replacement_while_retained_file_is_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replacement: str,
) -> None:
    receipt = _receipt()
    path = materialization_receipt_path(tmp_path, receipt.operation_command_id)
    persist_operator_materialization_receipt(
        tmp_path, receipt, expected_owner_uid=os.geteuid()
    )
    original_read = receipt_module.os.read
    raced = False

    def replace_then_read(descriptor: int, size: int) -> bytes:
        nonlocal raced
        if not raced and stat.S_ISREG(os.fstat(descriptor).st_mode):
            raced = True
            retained_name = path.with_name("retained-receipt.json")
            path.rename(retained_name)
            if replacement == "identical":
                path.write_bytes(retained_name.read_bytes())
                path.chmod(0o600)
            elif replacement == "conflicting":
                path.write_bytes(b"foreign evidence")
                path.chmod(0o600)
            elif replacement == "symlink":
                path.symlink_to(retained_name)
            else:
                os.mkfifo(path, 0o600)
        return original_read(descriptor, size)

    monkeypatch.setattr(receipt_module.os, "read", replace_then_read)
    with pytest.raises(OperatorMaterializationReceiptError):
        read_operator_materialization_receipt(
            tmp_path,
            receipt.operation_command_id,
            expected_owner_uid=os.geteuid(),
        )
    assert raced is True


def test_reader_refuses_operation_directory_replacement_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = _receipt()
    path = materialization_receipt_path(tmp_path, receipt.operation_command_id)
    raw = canonical_json_bytes(receipt.to_dict())
    persist_operator_materialization_receipt(
        tmp_path, receipt, expected_owner_uid=os.geteuid()
    )
    original_read = receipt_module.os.read
    raced = False

    def replace_directory_then_read(descriptor: int, size: int) -> bytes:
        nonlocal raced
        if not raced and stat.S_ISREG(os.fstat(descriptor).st_mode):
            raced = True
            retained_directory = path.parent.with_name("retained-operation")
            path.parent.rename(retained_directory)
            path.parent.mkdir(mode=0o700)
            path.write_bytes(raw)
            path.chmod(0o600)
        return original_read(descriptor, size)

    monkeypatch.setattr(
        receipt_module.os, "read", replace_directory_then_read
    )
    with pytest.raises(OperatorMaterializationReceiptError):
        read_operator_materialization_receipt(
            tmp_path,
            receipt.operation_command_id,
            expected_owner_uid=os.geteuid(),
        )
    assert raced is True


def test_reader_refuses_materialization_parent_replacement_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = _receipt()
    path = materialization_receipt_path(tmp_path, receipt.operation_command_id)
    raw = canonical_json_bytes(receipt.to_dict())
    persist_operator_materialization_receipt(
        tmp_path, receipt, expected_owner_uid=os.geteuid()
    )
    original_read = receipt_module.os.read
    raced = False

    def replace_parent_then_read(descriptor: int, size: int) -> bytes:
        nonlocal raced
        if not raced and stat.S_ISREG(os.fstat(descriptor).st_mode):
            raced = True
            parent = path.parent.parent
            parent.rename(tmp_path / "retained-materializations")
            path.parent.mkdir(parents=True, mode=0o700)
            path.write_bytes(raw)
            path.chmod(0o600)
        return original_read(descriptor, size)

    monkeypatch.setattr(receipt_module.os, "read", replace_parent_then_read)
    with pytest.raises(OperatorMaterializationReceiptError):
        read_operator_materialization_receipt(
            tmp_path,
            receipt.operation_command_id,
            expected_owner_uid=os.geteuid(),
        )
    assert raced is True


def test_persistence_retains_created_file_across_final_name_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = _receipt()
    path = materialization_receipt_path(tmp_path, receipt.operation_command_id)
    original_fsync = receipt_module.os.fsync
    raced = False

    def replace_after_file_fsync(descriptor: int) -> None:
        nonlocal raced
        original_fsync(descriptor)
        info = os.fstat(descriptor)
        if not raced and stat.S_ISREG(info.st_mode) and info.st_size > 0:
            raced = True
            retained_name = path.with_name("retained-created.json")
            path.rename(retained_name)
            path.write_bytes(retained_name.read_bytes())
            path.chmod(0o600)

    monkeypatch.setattr(receipt_module.os, "fsync", replace_after_file_fsync)
    with pytest.raises(OperatorMaterializationReceiptError):
        persist_operator_materialization_receipt(
            tmp_path, receipt, expected_owner_uid=os.geteuid()
        )
    assert raced is True


def test_receipt_open_uses_nonblocking_mode_before_file_type_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = _receipt()
    path = materialization_receipt_path(tmp_path, receipt.operation_command_id)
    path.parent.parent.mkdir(mode=0o700)
    path.parent.mkdir(mode=0o700)
    os.mkfifo(path, 0o600)
    original_open = receipt_module.os.open

    def require_nonblocking(name, flags, *args, **kwargs):
        if name == "receipt.json" and not flags & os.O_NONBLOCK:
            raise AssertionError("receipt open must be nonblocking before fstat")
        return original_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(receipt_module.os, "open", require_nonblocking)
    with pytest.raises(OperatorMaterializationReceiptError):
        read_operator_materialization_receipt(
            tmp_path,
            receipt.operation_command_id,
            expected_owner_uid=os.geteuid(),
        )


@pytest.mark.parametrize("failing_fsync", [1, 2, 3])
def test_failed_create_cleans_only_its_owned_coordinates_and_allows_clean_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failing_fsync: int,
) -> None:
    receipt = _receipt()
    path = materialization_receipt_path(tmp_path, receipt.operation_command_id)
    original_fsync = receipt_module.os.fsync
    fsync_calls = 0

    def fail_after_create(descriptor: int) -> None:
        nonlocal fsync_calls
        fsync_calls += 1
        if fsync_calls == failing_fsync:
            raise OSError("injected post-create failure")
        original_fsync(descriptor)

    monkeypatch.setattr(receipt_module.os, "fsync", fail_after_create)
    with pytest.raises(OperatorMaterializationReceiptError):
        persist_operator_materialization_receipt(
            tmp_path, receipt, expected_owner_uid=os.geteuid()
        )
    assert not path.exists()
    assert not path.parent.exists()
    assert not path.parent.parent.exists()

    monkeypatch.setattr(receipt_module.os, "fsync", original_fsync)
    assert persist_operator_materialization_receipt(
        tmp_path, receipt, expected_owner_uid=os.geteuid()
    ) == receipt


def test_ambiguous_cleanup_never_unlinks_a_foreign_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = _receipt()
    path = materialization_receipt_path(tmp_path, receipt.operation_command_id)
    original_fsync = receipt_module.os.fsync
    replaced = False

    def replace_then_fail(descriptor: int) -> None:
        nonlocal replaced
        info = os.fstat(descriptor)
        if not replaced and stat.S_ISREG(info.st_mode) and info.st_size > 0:
            replaced = True
            path.rename(path.with_name("retained-owned.json"))
            path.write_bytes(b"foreign replacement")
            path.chmod(0o600)
            raise OSError("injected ambiguous failure")
        original_fsync(descriptor)

    monkeypatch.setattr(receipt_module.os, "fsync", replace_then_fail)
    with pytest.raises(OperatorMaterializationReceiptError):
        persist_operator_materialization_receipt(
            tmp_path, receipt, expected_owner_uid=os.geteuid()
        )
    assert replaced is True
    assert path.read_bytes() == b"foreign replacement"


def test_failure_paths_balance_retained_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fd_root = Path("/dev/fd")
    if not fd_root.is_dir():
        pytest.skip("descriptor census is unavailable")
    receipt = _receipt()
    path = materialization_receipt_path(tmp_path, receipt.operation_command_id)
    persist_operator_materialization_receipt(
        tmp_path, receipt, expected_owner_uid=os.geteuid()
    )
    before = len(list(fd_root.iterdir()))
    original_read = receipt_module.os.read
    raced = False

    def replace_then_read(descriptor: int, size: int) -> bytes:
        nonlocal raced
        if not raced and stat.S_ISREG(os.fstat(descriptor).st_mode):
            raced = True
            path.rename(path.with_name("retained-balance.json"))
            path.write_bytes(b"foreign replacement")
            path.chmod(0o600)
        return original_read(descriptor, size)

    monkeypatch.setattr(receipt_module.os, "read", replace_then_read)
    with pytest.raises(OperatorMaterializationReceiptError):
        read_operator_materialization_receipt(
            tmp_path,
            receipt.operation_command_id,
            expected_owner_uid=os.geteuid(),
        )
    assert len(list(fd_root.iterdir())) == before
