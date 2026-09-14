from __future__ import annotations

import json
import os
import stat
import threading
from pathlib import Path

import pytest

from integrations.workbench_action_mcp.action_artifacts import (
    ACTION_PURPOSE_CLOSED_COMMAND,
    ACTION_PURPOSE_TEXT_PATCH,
    ActionArtifactBusy,
    ActionArtifactError,
    ActionArtifactIdentity,
    ActionArtifactUncertain,
    ActionHostBinding,
    acquire_store_writer,
    adopt_artifact_store,
    artifact_name,
    claim_action,
    classify_action,
    finalize_action,
    read_action_blob,
    read_action_claim,
    write_action_blob,
    validate_host_binding,
)


def _identity(**overrides: object) -> ActionArtifactIdentity:
    values: dict[str, object] = {
        "action_id": "a" * 32,
        "purpose": ACTION_PURPOSE_TEXT_PATCH,
        "subject_digest": "b" * 64,
        "client_ref": "client-ref",
        "resource": "https://workbench.example.test/mcp",
        "project_ref": "project:alpha",
        "context_ref": "context:alpha",
        "responsibility_ref": "responsibility:alpha",
        "operation_ref": "operation:alpha",
        "owner_ref": "owner:alpha",
        "generation": "generation:alpha",
        "root_device": 1,
        "root_inode": 2,
        "store_device": 0,
        "store_inode": 0,
        "host_id": "c" * 64,
        "boot_session_id": "boot-session-alpha",
        "relative_path": "sample.py",
        "source_identity": None,
    }
    values.update(overrides)
    return ActionArtifactIdentity(**values)  # type: ignore[arg-type]


def _open_store(path: Path):
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    os.set_inheritable(fd, False)
    store = adopt_artifact_store(fd)
    return fd, store


def test_adopt_requires_same_uid_and_private_directory(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    store_dir.mkdir(mode=0o755)
    os.chmod(store_dir, 0o773)
    fd = os.open(store_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    os.set_inheritable(fd, False)
    try:
        with pytest.raises(ActionArtifactError):
            adopt_artifact_store(fd)
    finally:
        os.close(fd)


def test_helper_does_not_close_borrowed_store_fd(tmp_path: Path) -> None:
    fd, store = _open_store(tmp_path / "store")
    try:
        identity = _identity(store_device=store.device, store_inode=store.inode)
        claim_action(store, identity, claimed_at_ms=10)
        os.fstat(fd)
        assert os.fstat(fd).st_ino == store.inode
    finally:
        os.close(fd)


def test_directory_fd_flock_is_exclusive_on_this_host(tmp_path: Path) -> None:
    fd, store = _open_store(tmp_path / "store")
    other = -1
    lock = None
    try:
        lock = acquire_store_writer(store)
        other = os.open(tmp_path / "store", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        os.set_inheritable(other, False)
        second = adopt_artifact_store(other)
        with pytest.raises(ActionArtifactBusy):
            acquire_store_writer(second)
        busy = threading.Event()
        released = threading.Event()

        def attempt() -> None:
            try:
                acquire_store_writer(store)
            except ActionArtifactBusy:
                busy.set()
            finally:
                released.set()

        worker = threading.Thread(target=attempt)
        try:
            worker.start()
            assert released.wait(5)
            assert busy.is_set()
        finally:
            worker.join(timeout=5)
    finally:
        if lock is not None:
            lock.release()
        if other >= 0:
            os.close(other)
        os.close(fd)


def test_claim_is_one_shot_and_absence_is_unknown(tmp_path: Path) -> None:
    fd, store = _open_store(tmp_path / "store")
    try:
        identity = _identity(store_device=store.device, store_inode=store.inode)
        assert classify_action(store, identity).effect_state == "EFFECT_UNKNOWN"
        first = claim_action(store, identity, claimed_at_ms=11)
        assert first.created is True
        second = claim_action(store, identity, claimed_at_ms=12)
        assert second.created is False
        assert second.uncertain is False
        assert classify_action(store, identity).effect_state == "EFFECT_UNKNOWN"
        finalize_action(
            store,
            identity,
            effect_state="APPLIED",
            observed_sha256="d" * 64,
            completed_at_ms=13,
            durability="durable",
        )
        assert classify_action(store, identity).effect_state == "APPLIED"
        with pytest.raises((ActionArtifactError, ActionArtifactUncertain, FileExistsError)):
            finalize_action(
                store,
                identity,
                effect_state="APPLIED",
                observed_sha256="d" * 64,
                completed_at_ms=14,
                durability="durable",
            )
    finally:
        os.close(fd)


def test_corrupt_and_replaced_store_are_unknown(tmp_path: Path) -> None:
    fd, store = _open_store(tmp_path / "store")
    replacement_fd = -1
    try:
        identity = _identity(store_device=store.device, store_inode=store.inode)
        claim_action(store, identity, claimed_at_ms=21)
        claim_path = tmp_path / "store" / artifact_name(identity.action_id, "claim")
        claim_path.write_text("{not-json")
        with pytest.raises(ActionArtifactUncertain):
            read_action_claim(store, identity)
        assert classify_action(store, identity).effect_state == "EFFECT_UNKNOWN"

        other = tmp_path / "replacement"
        replacement_fd, replaced = _open_store(other)
        foreign = _identity(
            store_device=replaced.device,
            store_inode=replaced.inode,
            action_id="e" * 32,
        )
        classified = classify_action(replaced, identity)
        assert classified.effect_state == "EFFECT_UNKNOWN"
        assert classified.store_valid is False
        assert classify_action(replaced, foreign).effect_state == "EFFECT_UNKNOWN"
    finally:
        if replacement_fd >= 0:
            os.close(replacement_fd)
        os.close(fd)


def test_command_purpose_reuses_same_claim_and_blob_operations(tmp_path: Path) -> None:
    fd, store = _open_store(tmp_path / "store")
    try:
        identity = _identity(
            store_device=store.device,
            store_inode=store.inode,
            purpose=ACTION_PURPOSE_CLOSED_COMMAND,
            action_id="f" * 32,
        )
        assert claim_action(store, identity, claimed_at_ms=31).created is True
        write_action_blob(store, identity.action_id, "stdout", b"line\n")
        assert read_action_blob(store, identity.action_id, "stdout") == b"line\n"
        finalize_action(
            store,
            identity,
            effect_state="APPLIED",
            observed_sha256=None,
            completed_at_ms=32,
            durability="durable",
            details={"exit_code": 0},
        )
        classified = classify_action(store, identity)
        assert classified.effect_state == "APPLIED"
        assert classified.result is not None
        assert classified.result.details["exit_code"] == 0
    finally:
        os.close(fd)


def test_uncertain_durability_cannot_be_applied(tmp_path: Path) -> None:
    fd, store = _open_store(tmp_path / "store")
    try:
        identity = _identity(store_device=store.device, store_inode=store.inode)
        claim_action(store, identity, claimed_at_ms=41)
        with pytest.raises(ActionArtifactError):
            finalize_action(
                store,
                identity,
                effect_state="APPLIED",
                observed_sha256="d" * 64,
                completed_at_ms=42,
                durability="uncertain",
            )
    finally:
        os.close(fd)


def test_host_binding_and_identity_are_closed(tmp_path: Path) -> None:
    with pytest.raises(ActionArtifactError):
        validate_host_binding(ActionHostBinding(host_id="nope", boot_session_id="boot"))
    fd, store = _open_store(tmp_path / "store")
    try:
        raw = json.dumps({"schema": "nope"})
        with pytest.raises(ActionArtifactError):
            claim_action(
                store,
                _identity(action_id="ZZ"),
                claimed_at_ms=1,
            )
        assert isinstance(raw, str)
        assert not stat.S_ISREG(os.fstat(fd).st_mode)
    finally:
        os.close(fd)
