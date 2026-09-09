from __future__ import annotations

import fcntl
import json
import os
import stat
from pathlib import Path

import pytest

from integrations.business_mcp_auth import audit
from integrations.business_mcp_auth.audit import (
    AuditSinkPoisoned,
    DurableAuthAuditSink,
)
from integrations.business_mcp_auth.contracts import (
    AUTH_AUDIT_SCHEMA,
    AuthAuditEvent,
)

POLICY_ID = "mastermind-workbench-read-v1"


def event(code: str = "accepted", accepted: bool = True) -> AuthAuditEvent:
    return AuthAuditEvent(
        schema=AUTH_AUDIT_SCHEMA,
        policy_id=POLICY_ID,
        code=code,
        accepted=accepted,
    )


def open_directory(path: Path) -> int:
    path.mkdir(mode=0o700)
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)


def test_emit_is_one_named_durable_canonical_append(tmp_path: Path) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    try:
        sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
        sink.emit(event())
        sink.emit(event("scope_refused", False))
        sink.close()
        os.fstat(host_fd)  # Runtime-owned descriptions never consume host aliases.
    finally:
        os.close(host_fd)

    target = directory / "auth-audit.jsonl"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    lines = target.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [
        {
            "accepted": True,
            "code": "accepted",
            "policy_id": POLICY_ID,
            "schema": AUTH_AUDIT_SCHEMA,
        },
        {
            "accepted": False,
            "code": "scope_refused",
            "policy_id": POLICY_ID,
            "schema": AUTH_AUDIT_SCHEMA,
        },
    ]


def test_named_file_replacement_poisons_before_any_second_write(tmp_path: Path) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
    original = directory / "auth-audit.jsonl"
    orphan = directory / "orphaned.jsonl"
    original.rename(orphan)
    original.write_text("replacement\n", encoding="utf-8")
    original.chmod(0o600)

    with pytest.raises(AuditSinkPoisoned):
        sink.emit(event())
    before = original.read_bytes()
    with pytest.raises(AuditSinkPoisoned):
        sink.emit(event())
    assert original.read_bytes() == before
    assert orphan.read_bytes() == b""
    sink.close()
    os.close(host_fd)


@pytest.mark.parametrize("unsafe", ["mode", "hardlink", "symlink"])
def test_open_refuses_unsafe_named_file(tmp_path: Path, unsafe: str) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    target = directory / "auth-audit.jsonl"
    if unsafe == "symlink":
        elsewhere = tmp_path / "elsewhere"
        elsewhere.write_text("", encoding="utf-8")
        target.symlink_to(elsewhere)
    else:
        target.write_text("", encoding="utf-8")
        target.chmod(0o644 if unsafe == "mode" else 0o600)
        if unsafe == "hardlink":
            os.link(target, directory / "alias")

    with pytest.raises(AuditSinkPoisoned):
        DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
    os.close(host_fd)


def test_second_live_sink_is_refused_by_nonblocking_lock(tmp_path: Path) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    first = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
    with pytest.raises(AuditSinkPoisoned):
        DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
    first.close()
    os.close(host_fd)


def test_short_append_poisons_without_retry(tmp_path: Path, monkeypatch) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
    real_write = audit.os.write
    calls = 0

    def short_write(fd: int, payload: bytes) -> int:
        nonlocal calls
        calls += 1
        written = real_write(fd, payload[:-1])
        assert written == len(payload) - 1
        return written

    monkeypatch.setattr(audit.os, "write", short_write)
    with pytest.raises(AuditSinkPoisoned):
        sink.emit(event())
    with pytest.raises(AuditSinkPoisoned):
        sink.emit(event())
    assert calls == 1
    sink.close()
    os.close(host_fd)


def test_invalid_event_is_refused_without_append(tmp_path: Path) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
    invalid = AuthAuditEvent(
        schema=AUTH_AUDIT_SCHEMA,
        policy_id=POLICY_ID,
        code="accepted",
        accepted=False,
    )
    with pytest.raises(AuditSinkPoisoned):
        sink.emit(invalid)
    assert (directory / "auth-audit.jsonl").read_bytes() == b""
    sink.close()
    os.close(host_fd)


def test_fsync_failure_poisons_and_never_retries(tmp_path: Path, monkeypatch) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
    calls = 0

    def fail_fsync(_fd: int) -> None:
        nonlocal calls
        calls += 1
        raise OSError("synthetic fsync uncertainty")

    monkeypatch.setattr(audit.os, "fsync", fail_fsync)
    with pytest.raises(AuditSinkPoisoned):
        sink.emit(event())
    with pytest.raises(AuditSinkPoisoned):
        sink.emit(event())
    assert calls == 1
    sink.close()
    os.close(host_fd)


def test_append_flag_drift_poisons_before_write(tmp_path: Path) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
    flags = fcntl.fcntl(sink._audit_fd, fcntl.F_GETFL)
    fcntl.fcntl(sink._audit_fd, fcntl.F_SETFL, flags & ~os.O_APPEND)
    with pytest.raises(AuditSinkPoisoned):
        sink.emit(event())
    assert (directory / "auth-audit.jsonl").read_bytes() == b""
    sink.close()
    os.close(host_fd)


def test_directory_security_drift_poisons_before_write(tmp_path: Path) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
    directory.chmod(0o777)
    with pytest.raises(AuditSinkPoisoned):
        sink.emit(event())
    assert (directory / "auth-audit.jsonl").read_bytes() == b""
    sink.close()
    os.close(host_fd)


def test_line_and_file_budgets_poison_without_retry(tmp_path: Path) -> None:
    first_directory = tmp_path / "line"
    first_fd = open_directory(first_directory)
    line_sink = DurableAuthAuditSink.open(
        first_fd, policy_id=POLICY_ID, max_line_bytes=16, max_file_bytes=16
    )
    with pytest.raises(AuditSinkPoisoned):
        line_sink.emit(event())
    assert (first_directory / "auth-audit.jsonl").read_bytes() == b""
    line_sink.close()
    os.close(first_fd)

    second_directory = tmp_path / "file"
    second_fd = open_directory(second_directory)
    file_sink = DurableAuthAuditSink.open(
        second_fd, policy_id=POLICY_ID, max_line_bytes=200, max_file_bytes=200
    )
    file_sink.emit(event())
    with pytest.raises(AuditSinkPoisoned):
        file_sink.emit(event())
    assert len((second_directory / "auth-audit.jsonl").read_text().splitlines()) == 1
    file_sink.close()
    os.close(second_fd)


# RS0_AUDIT_FLOCK_REDS_20260909
def test_explicit_owner_unlock_poisons_before_append(tmp_path: Path) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
    fcntl.flock(sink._audit_fd, fcntl.LOCK_UN)
    with pytest.raises(AuditSinkPoisoned):
        sink.emit(event())
    assert (directory / "auth-audit.jsonl").read_bytes() == b""
    sink.close()
    os.close(host_fd)


def test_unlock_through_duplicate_descriptor_poisons_before_append(tmp_path: Path) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
    duplicate = os.dup(sink._audit_fd)
    try:
        fcntl.flock(duplicate, fcntl.LOCK_UN)
    finally:
        os.close(duplicate)
    with pytest.raises(AuditSinkPoisoned):
        sink.emit(event())
    assert (directory / "auth-audit.jsonl").read_bytes() == b""
    sink.close()
    os.close(host_fd)


def test_foreign_holder_after_owner_loss_poisons_without_append(tmp_path: Path) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
    fcntl.flock(sink._audit_fd, fcntl.LOCK_UN)
    foreign = os.open(
        directory / "auth-audit.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CLOEXEC
    )
    fcntl.flock(foreign, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(AuditSinkPoisoned):
            sink.emit(event())
        assert (directory / "auth-audit.jsonl").read_bytes() == b""
        sink.close()
    finally:
        fcntl.flock(foreign, fcntl.LOCK_UN)
        os.close(foreign)
        os.close(host_fd)


def test_lock_loss_during_single_write_is_uncertain_and_never_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
    real_write = audit.os.write
    calls = 0

    def write_then_unlock(fd: int, payload: bytes) -> int:
        nonlocal calls
        calls += 1
        written = real_write(fd, payload)
        duplicate = os.dup(fd)
        try:
            fcntl.flock(duplicate, fcntl.LOCK_UN)
        finally:
            os.close(duplicate)
        return written

    monkeypatch.setattr(audit.os, "write", write_then_unlock)
    with pytest.raises(AuditSinkPoisoned):
        sink.emit(event())
    with pytest.raises(AuditSinkPoisoned):
        sink.emit(event())
    assert calls == 1
    assert len((directory / "auth-audit.jsonl").read_text().splitlines()) == 1
    sink.close()
    os.close(host_fd)


def test_lock_loss_before_close_is_reported_and_descriptors_are_closed(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
    audit_fd = sink._audit_fd
    directory_fd = sink._directory_fd
    fcntl.flock(audit_fd, fcntl.LOCK_UN)
    with pytest.raises(AuditSinkPoisoned):
        sink.close()
    with pytest.raises(OSError):
        os.fstat(audit_fd)
    with pytest.raises(OSError):
        os.fstat(directory_fd)
    os.close(host_fd)
