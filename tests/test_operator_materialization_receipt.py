"""Strict durability and identity proofs for Operator materialization receipts."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

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
            "auth": {"worker_id": "codex-01", "auth_class": "oauth"},
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
    values["observed_attestation"] = {"access_token": "must-not-land"}
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
