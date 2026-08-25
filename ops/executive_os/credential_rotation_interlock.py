#!/usr/bin/env python3
"""Fail-closed, secret-free interlock for Executive worker credential mutation."""
from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping


_ROOT = Path(__file__).resolve().parents[2]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from control_plane.executive_autonomy import (
    AutonomyRefusal,
    load_receipt_file,
    sha256_file,
    validate_disarmed_interlock_document,
)
from scripts.executive_os_phase1c import load_control_config
from scripts.executive_os_phase1c_worker import _load_config as load_worker_config


SYSTEM_ROOT = Path("/Library/Application Support/MastermindExecutive")
CONTROL_CONFIG = SYSTEM_ROOT / "config" / "control.json"
WORKER_CONFIG = SYSTEM_ROOT / "config" / "worker-codex.json"
AUTONOMY_RECEIPT = SYSTEM_ROOT / "config" / "autonomy-state-v1.json"
AUTONOMY_TRANSACTION = SYSTEM_ROOT / "config" / "autonomy-transaction.lock"


class CredentialInterlockError(RuntimeError):
    pass


def evaluate_credential_mutation_state(
    control: Mapping[str, Any],
    worker: Mapping[str, Any],
    *,
    transaction_present: bool,
) -> None:
    """Pure closed decision before any credential or readiness effect."""

    if transaction_present:
        raise CredentialInterlockError("autonomy transaction is incomplete")
    control_autonomy = control.get("coo_autonomy_armed")
    control_operator = control.get("coo_operator_harness_armed")
    worker_operator = worker.get("operator_harness_armed")
    if any(
        type(value) is not bool
        for value in (control_autonomy, control_operator, worker_operator)
    ):
        raise CredentialInterlockError("autonomy config arm fields are invalid")
    if control_autonomy or control_operator or worker_operator:
        raise CredentialInterlockError(
            "credential mutation requires verified autonomy disarm"
        )


def _has_acl(path: Path) -> bool:
    if sys.platform != "darwin":
        return False
    completed = subprocess.run(
        ["/usr/bin/stat", "-f", "%Sp", os.fspath(path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
        timeout=5,
    )
    if completed.returncode != 0:
        raise CredentialInterlockError("cannot inspect autonomy config ACL")
    return completed.stdout.strip().endswith("+")


def _require_safe_config(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise CredentialInterlockError("autonomy config is unavailable") from exc
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != 0
        or stat.S_IMODE(info.st_mode) != 0o440
        or info.st_nlink != 1
        or _has_acl(path)
    ):
        raise CredentialInterlockError("autonomy config metadata is unsafe")


def assert_credential_mutation_disarmed(
    *,
    control_config: Path = CONTROL_CONFIG,
    worker_config: Path = WORKER_CONFIG,
    autonomy_receipt: Path = AUTONOMY_RECEIPT,
    autonomy_transaction: Path = AUTONOMY_TRANSACTION,
) -> None:
    """Prove the fixed installed authority surface is shrink-only and current."""

    for path in (control_config, worker_config):
        _require_safe_config(path)
    transaction_present = autonomy_transaction.exists() or autonomy_transaction.is_symlink()
    try:
        control = load_control_config(control_config)
        worker = load_worker_config(worker_config, require_root_owner=True)
    except Exception as exc:
        raise CredentialInterlockError("autonomy config validation refused") from exc
    evaluate_credential_mutation_state(
        control,
        worker,
        transaction_present=transaction_present,
    )
    receipt_present = autonomy_receipt.exists() or autonomy_receipt.is_symlink()
    if not receipt_present:
        return
    try:
        payload, metadata = load_receipt_file(autonomy_receipt)
        validate_disarmed_interlock_document(
            payload,
            metadata=metadata,
            control_config_sha256=sha256_file(control_config),
            worker_config_sha256=sha256_file(worker_config),
        )
    except AutonomyRefusal as exc:
        raise CredentialInterlockError(
            "autonomy disarm receipt does not bind current configs"
        ) from exc


def main() -> int:
    try:
        if os.geteuid() != 0:
            raise CredentialInterlockError("credential interlock requires root")
        assert_credential_mutation_disarmed()
    except (CredentialInterlockError, OSError, ValueError):
        print(
            "credential mutation refused: run and verify autonomy disarm first",
            file=sys.stderr,
        )
        return 2
    print("credential mutation interlock: DISARMED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
