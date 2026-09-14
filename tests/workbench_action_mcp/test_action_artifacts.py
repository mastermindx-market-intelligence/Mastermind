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
                acquire_store_writer(store).release()
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
        absent = classify_action(store, identity)
        assert absent.effect_state == "EFFECT_UNKNOWN"
        assert absent.evidence_status == "absent" and absent.claimable
        first = claim_action(store, identity, claimed_at_ms=11)
        assert first.created is True
        second = claim_action(store, identity, claimed_at_ms=12)
        assert second.created is False
        assert second.uncertain is False
        pending = classify_action(store, identity)
        assert pending.effect_state == "EFFECT_UNKNOWN"
        assert pending.evidence_status == "pending" and not pending.claimable
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


def _completed_pair(store):
    identity = _identity(store_device=store.device, store_inode=store.inode)
    assert claim_action(store, identity, claimed_at_ms=100).created
    finalize_action(store, identity, effect_state="APPLIED", observed_sha256="d" * 64,
                    completed_at_ms=101, durability="durable")
    return identity


@pytest.mark.parametrize("boundary", ["result_file", "store_directory"])
def test_visible_result_requires_successful_qualification(tmp_path, monkeypatch, boundary):
    """A complete receipt can be visible while its writer fsync has not returned."""
    from integrations.workbench_action_mcp import action_artifacts as artifacts

    fd, store = _open_store(tmp_path / "store")
    identity = _identity(store_device=store.device, store_inode=store.inode)
    assert claim_action(store, identity, claimed_at_ms=100).created
    path = tmp_path / "store" / artifact_name(identity.action_id, "result")
    at_boundary, release = threading.Event(), threading.Event()
    real_fsync = os.fsync
    errors = []
    worker = None

    def fsync(selected):
        if path.exists():
            inode = os.fstat(selected).st_ino
            match = inode == (path.stat().st_ino if boundary == "result_file" else store.inode)
            if match:
                if threading.current_thread() is worker:
                    at_boundary.set()
                    if not release.wait(5):
                        raise TimeoutError("test did not release writer")
                raise OSError("injected durability failure")
        return real_fsync(selected)

    def finish():
        try:
            finalize_action(store, identity, effect_state="APPLIED", observed_sha256="d" * 64,
                            completed_at_ms=101, durability="durable")
        except BaseException as error:
            errors.append(error)

    try:
        monkeypatch.setattr(artifacts.os, "fsync", fsync)
        worker = threading.Thread(target=finish)
        worker.start()
        assert at_boundary.wait(5)
        assert json.loads(path.read_text())["durability"] == "durable"
        classified = classify_action(store, identity)
        assert classified.effect_state == "EFFECT_UNKNOWN"
        assert classified.evidence_status == "uncertain"
        assert not classified.claimable
    finally:
        release.set()
        if worker is not None:
            worker.join(5)
        monkeypatch.setattr(artifacts.os, "fsync", real_fsync)
        os.close(fd)
    assert not worker.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], ActionArtifactUncertain)
    # A later logical read may qualify the unchanged bytes, without creating files.
    reopened = os.open(tmp_path / "store", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        recovered = adopt_artifact_store(reopened)
        before = {p.name: p.read_bytes() for p in (tmp_path / "store").iterdir()}
        assert classify_action(recovered, identity).effect_state == "APPLIED"
        assert before == {p.name: p.read_bytes() for p in (tmp_path / "store").iterdir()}
    finally:
        os.close(reopened)


@pytest.mark.parametrize("damage", ["orphan", "corrupt_orphan", "corrupt_claim", "early_result", "foreign_claim"])
def test_uncertain_evidence_never_becomes_claimable(tmp_path, damage):
    fd, store = _open_store(tmp_path / "store")
    try:
        identity = _completed_pair(store)
        claim_path = tmp_path / "store" / artifact_name(identity.action_id, "claim")
        result_path = tmp_path / "store" / artifact_name(identity.action_id, "result")
        if damage in {"orphan", "corrupt_orphan"}:
            claim_path.unlink()
            if damage == "corrupt_orphan":
                result_path.write_text("{")
        elif damage == "corrupt_claim":
            claim_path.write_text("{")
        elif damage == "foreign_claim":
            body = json.loads(claim_path.read_text())
            body["identity"]["client_ref"] = "different-client"
            claim_path.write_text(json.dumps(body))
        else:
            body = json.loads(result_path.read_text())
            body["completed_at_ms"] = 99
            result_path.write_text(json.dumps(body))
        classified = classify_action(store, identity)
        assert classified.effect_state == "EFFECT_UNKNOWN"
        assert classified.evidence_status == "uncertain"
        assert not classified.claimable
        before = result_path.read_bytes()
        assert not claim_action(store, identity, claimed_at_ms=102).created
        assert result_path.read_bytes() == before
        if damage in {"orphan", "corrupt_orphan"}:
            assert not claim_path.exists()
    finally:
        os.close(fd)


def test_finalize_requires_matching_prior_claim(tmp_path):
    fd, store = _open_store(tmp_path / "store")
    try:
        identity = _identity(store_device=store.device, store_inode=store.inode)
        for claim_time in (None, 102):
            if claim_time is not None:
                assert claim_action(store, identity, claimed_at_ms=claim_time).created
            with pytest.raises(ActionArtifactUncertain):
                finalize_action(store, identity, effect_state="APPLIED", observed_sha256=None,
                                completed_at_ms=101, durability="durable")
            assert not (tmp_path / "store" / artifact_name(identity.action_id, "result")).exists()
    finally:
        os.close(fd)


@pytest.mark.parametrize("damage", ["duplicate_effect", "duplicate_identity", "duplicate_nested", "nan", "infinity", "overflow_float", "oversized_details"])
def test_strict_record_decoder_refuses_valid_shape_corruption(tmp_path, damage):
    fd, store = _open_store(tmp_path / "store")
    try:
        identity = _completed_pair(store)
        path = tmp_path / "store" / artifact_name(identity.action_id, "result")
        raw = path.read_text()
        if damage == "duplicate_effect":
            raw = raw.replace('"effect_state":"APPLIED"', '"effect_state":"EFFECT_UNKNOWN","effect_state":"APPLIED"')
        elif damage == "duplicate_identity":
            raw = raw.replace('"identity":{', '"identity":{"action_id":"' + 'e' * 32 + '",')
        else:
            detail = {"duplicate_nested": '{"nested":{"ok":false,"ok":true}}',
                      "nan": '{"n":NaN}', "infinity": '{"n":Infinity}',
                      "overflow_float": '{"n":1e999}',
                      "oversized_details": json.dumps({"x": "x" * 2048})}[damage]
            raw = raw.replace('"details":{}', '"details":' + detail)
        path.write_text(raw)
        classified = classify_action(store, identity)
        assert classified.effect_state == "EFFECT_UNKNOWN"
        assert classified.evidence_status == "uncertain"
        assert not classified.claimable
    finally:
        os.close(fd)


def test_claim_duplicate_fields_are_refused(tmp_path):
    fd, store = _open_store(tmp_path / "store")
    try:
        identity = _completed_pair(store)
        path = tmp_path / "store" / artifact_name(identity.action_id, "claim")
        path.write_text(path.read_text().replace('"phase":"claimed"', '"phase":"other","phase":"claimed"'))
        assert classify_action(store, identity).effect_state == "EFFECT_UNKNOWN"
        with pytest.raises(ActionArtifactUncertain):
            read_action_claim(store, identity)
    finally:
        os.close(fd)


def test_disappearing_artifact_does_not_turn_into_absence(tmp_path, monkeypatch):
    from integrations.workbench_action_mcp import action_artifacts as artifacts

    fd, store = _open_store(tmp_path / "store")
    try:
        identity = _identity(store_device=store.device, store_inode=store.inode)
        claim_action(store, identity, claimed_at_ms=10)
        path = tmp_path / "store" / artifact_name(identity.action_id, "claim")
        real_open = os.open

        def disappearing(name, flags, *args, **kwargs):
            if name == path.name:
                path.unlink()
            return real_open(name, flags, *args, **kwargs)

        monkeypatch.setattr(artifacts.os, "open", disappearing)
        classified = classify_action(store, identity)
        assert classified.evidence_status == "uncertain"
        assert not classified.claimable
    finally:
        os.close(fd)


def test_kernel_mutex_refuses_process_inheriting_borrowed_description(tmp_path):
    """No Python lock table can prove this; the child inherits the original fd."""
    import subprocess
    import sys

    fd, store = _open_store(tmp_path / "store")
    lock = None
    code = '''
import os, sys
from integrations.workbench_action_mcp.action_artifacts import adopt_artifact_store, acquire_store_writer, ActionArtifactBusy
fd = int(sys.argv[1])
os.set_inheritable(fd, False)
try:
    owned = acquire_store_writer(adopt_artifact_store(fd))
except ActionArtifactBusy:
    print("BUSY")
else:
    owned.release()
    print("ACQUIRED")
os.fstat(fd)
'''

    def contender():
        return subprocess.run([sys.executable, "-c", code, str(fd)], pass_fds=(fd,),
                              capture_output=True, text=True, timeout=10, check=True).stdout.strip()

    try:
        lock = acquire_store_writer(store)
        assert lock._fd != fd
        assert contender() == "BUSY"
        lock.release()
        lock = None
        assert contender() == "ACQUIRED"
        os.fstat(fd)
    finally:
        if lock is not None:
            lock.release()
        os.close(fd)


@pytest.mark.parametrize("boundary", ["reader_close", "writer_unlock", "writer_close"])
def test_cleanup_uncertainty_is_sticky_and_separate_from_effect(tmp_path, monkeypatch, boundary):
    from integrations.workbench_action_mcp import action_artifacts as artifacts

    fd, store = _open_store(tmp_path / "store")
    lock = None
    real_close, real_flock = os.close, artifacts.fcntl.flock
    try:
        identity = _completed_pair(store)
        lock = acquire_store_writer(store)
        fired = False

        def close(selected):
            nonlocal fired
            matches = selected == lock._fd if boundary == "writer_close" else stat.S_ISREG(os.fstat(selected).st_mode)
            real_close(selected)
            if not fired and matches and boundary != "writer_unlock":
                fired = True
                raise OSError("close acknowledgement uncertain")

        def flock(selected, operation):
            nonlocal fired
            real_flock(selected, operation)
            if boundary == "writer_unlock" and operation == artifacts.fcntl.LOCK_UN:
                fired = True
                raise OSError("unlock acknowledgement uncertain")

        monkeypatch.setattr(artifacts.os, "close", close)
        monkeypatch.setattr(artifacts.fcntl, "flock", flock)
        if boundary == "reader_close":
            assert classify_action(store, identity).effect_state == "EFFECT_UNKNOWN"
            lock.release()
        else:
            with pytest.raises(ActionArtifactUncertain):
                lock.release()
            with pytest.raises(ActionArtifactUncertain):
                lock.release()  # A second release must not manufacture clean cleanup.
        assert fired
        monkeypatch.setattr(artifacts.os, "close", real_close)
        monkeypatch.setattr(artifacts.fcntl, "flock", real_flock)
        assert store.cleanup_uncertain
        assert store.cleanup_reasons
        assert classify_action(store, identity).effect_state == "APPLIED"
        assert store.cleanup_uncertain
        with pytest.raises(ActionArtifactUncertain):
            store.raise_if_cleanup_uncertain()
        with pytest.raises(ActionArtifactUncertain):
            acquire_store_writer(store)
    finally:
        monkeypatch.setattr(artifacts.os, "close", real_close)
        monkeypatch.setattr(artifacts.fcntl, "flock", real_flock)
        if lock is not None and not lock._released:
            lock.release()
        real_close(fd)


@pytest.mark.parametrize("fault", ["claim_fsync", "receipt_replaced", "claim_inaccessible"])
def test_qualification_requires_both_matching_stable_readers(tmp_path, monkeypatch, fault):
    from integrations.workbench_action_mcp import action_artifacts as artifacts

    fd, store = _open_store(tmp_path / "store")
    try:
        identity = _completed_pair(store)
        claim_path = tmp_path / "store" / artifact_name(identity.action_id, "claim")
        result_path = tmp_path / "store" / artifact_name(identity.action_id, "result")
        real_fsync, real_open = os.fsync, os.open
        fired = False

        def fsync(selected):
            nonlocal fired
            inode = os.fstat(selected).st_ino
            if fault == "claim_fsync" and inode == claim_path.stat().st_ino:
                fired = True
                raise OSError("claim durability unqualified")
            real_fsync(selected)
            if fault == "receipt_replaced" and selected == store.dir_fd:
                replacement = tmp_path / "replacement"
                replacement.write_bytes(result_path.read_bytes())
                os.replace(replacement, result_path)
                fired = True

        def opened(name, flags, *args, **kwargs):
            nonlocal fired
            if fault == "claim_inaccessible" and name == claim_path.name:
                fired = True
                raise PermissionError("claim inaccessible")
            return real_open(name, flags, *args, **kwargs)

        monkeypatch.setattr(artifacts.os, "fsync", fsync)
        monkeypatch.setattr(artifacts.os, "open", opened)
        classified = classify_action(store, identity)
        assert fired
        assert classified.effect_state == "EFFECT_UNKNOWN"
        assert classified.evidence_status == "uncertain"
        assert not classified.claimable
    finally:
        os.close(fd)


def test_busy_mutex_acquisition_close_failure_poison_is_retained(tmp_path, monkeypatch):
    from integrations.workbench_action_mcp import action_artifacts as artifacts

    fd, store = _open_store(tmp_path / "store")
    owned = acquire_store_writer(store)
    real_close = os.close
    fired = False

    def close(selected):
        nonlocal fired
        real_close(selected)
        if selected not in {fd, owned._fd}:
            fired = True
            raise OSError("busy contender close uncertain")

    try:
        monkeypatch.setattr(artifacts.os, "close", close)
        with pytest.raises(ActionArtifactUncertain):
            acquire_store_writer(store)
        assert fired and store.cleanup_uncertain
        monkeypatch.setattr(artifacts.os, "close", real_close)
        owned.release()
        with pytest.raises(ActionArtifactUncertain):
            store.raise_if_cleanup_uncertain()
    finally:
        monkeypatch.setattr(artifacts.os, "close", real_close)
        owned.release()
        real_close(fd)


@pytest.mark.parametrize("details", [{"n": float("nan")}, {"n": float("inf")}, {"x": "x" * 2048}])
def test_result_writer_and_reader_share_closed_detail_bounds(tmp_path, details):
    fd, store = _open_store(tmp_path / "store")
    try:
        identity = _identity(store_device=store.device, store_inode=store.inode)
        assert claim_action(store, identity, claimed_at_ms=100).created
        with pytest.raises(ActionArtifactError):
            finalize_action(store, identity, effect_state="APPLIED", observed_sha256=None,
                            completed_at_ms=101, durability="durable", details=details)
        assert not (tmp_path / "store" / artifact_name(identity.action_id, "result")).exists()
    finally:
        os.close(fd)
