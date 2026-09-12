from __future__ import annotations

import fcntl
import json
import os
import stat
from pathlib import Path

import pytest

from integrations.business_mcp_auth import audit
from integrations.business_mcp_auth.audit import (
    AuditAcquisitionUncertain,
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
    with pytest.raises(AuditSinkPoisoned, match="audit close is uncertain"):
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


# RS0_F7_AUDIT_ACQUISITION_REDS_20260909
def test_owned_directory_rollback_close_failure_is_acquisition_uncertainty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    real_check_directory = DurableAuthAuditSink._check_directory_stat
    real_close = audit.os.close
    validations = 0
    close_calls: list[int] = []

    def refuse_owned_directory(value) -> None:
        nonlocal validations
        validations += 1
        real_check_directory(value)
        if validations == 2:
            raise AuditSinkPoisoned(
                "synthetic post-directory-acquisition refusal"
            )

    def close_then_fail(descriptor: int) -> None:
        close_calls.append(descriptor)
        real_close(descriptor)
        raise OSError("synthetic owned-directory rollback close failure")

    monkeypatch.setattr(
        DurableAuthAuditSink,
        "_check_directory_stat",
        staticmethod(refuse_owned_directory),
    )
    monkeypatch.setattr(audit.os, "close", close_then_fail)
    try:
        with pytest.raises(AuditSinkPoisoned) as caught:
            DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
    finally:
        monkeypatch.setattr(audit.os, "close", real_close)

    assert type(caught.value).__name__ == "AuditAcquisitionUncertain"
    assert isinstance(caught.value.primary_error, AuditSinkPoisoned)
    assert len(caught.value.cleanup_errors) == 1
    assert validations == 2 and len(close_calls) == 1
    os.fstat(host_fd)
    real_close(host_fd)


def test_audit_file_rollback_close_failure_is_acquisition_uncertainty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    real_close = audit.os.close
    close_calls: list[int] = []

    def refuse_flags(_descriptor: int) -> None:
        raise AuditSinkPoisoned("synthetic post-file-acquisition refusal")

    def close_with_first_failure(descriptor: int) -> None:
        close_calls.append(descriptor)
        real_close(descriptor)
        if len(close_calls) == 1:
            raise OSError("synthetic audit-file rollback close failure")

    monkeypatch.setattr(
        DurableAuthAuditSink, "_check_file_flags", staticmethod(refuse_flags)
    )
    monkeypatch.setattr(audit.os, "close", close_with_first_failure)
    try:
        with pytest.raises(AuditSinkPoisoned) as caught:
            DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
    finally:
        monkeypatch.setattr(audit.os, "close", real_close)

    assert type(caught.value).__name__ == "AuditAcquisitionUncertain"
    assert isinstance(caught.value.primary_error, AuditSinkPoisoned)
    assert len(caught.value.cleanup_errors) == 1
    assert len(close_calls) == 2 and close_calls[0] != close_calls[1]
    os.fstat(host_fd)
    real_close(host_fd)


# RS0_F7_ROLLBACK_ORDER_DISCRIMINATOR_20260909
def test_partial_acquisition_releases_file_then_directory_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    real_close = audit.os.close
    release_kinds: list[str] = []

    def refuse_after_file_acquisition(_descriptor: int) -> None:
        raise AuditSinkPoisoned("synthetic post-file-acquisition refusal")

    def classify_close_then_fail_first(descriptor: int) -> None:
        mode = audit.os.fstat(descriptor).st_mode
        release_kinds.append(
            "file"
            if stat.S_ISREG(mode)
            else "directory"
            if stat.S_ISDIR(mode)
            else "other"
        )
        real_close(descriptor)
        if len(release_kinds) == 1:
            raise OSError("synthetic first rollback close failure")

    monkeypatch.setattr(
        DurableAuthAuditSink,
        "_check_file_flags",
        staticmethod(refuse_after_file_acquisition),
    )
    monkeypatch.setattr(audit.os, "close", classify_close_then_fail_first)
    try:
        with pytest.raises(AuditAcquisitionUncertain) as caught:
            DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
    finally:
        monkeypatch.setattr(audit.os, "close", real_close)

    assert release_kinds == ["file", "directory"]
    assert len(caught.value.cleanup_errors) == 1
    os.fstat(host_fd)
    real_close(host_fd)


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
    with pytest.raises(AuditSinkPoisoned, match="audit close is uncertain"):
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
    with pytest.raises(AuditSinkPoisoned, match="audit close is uncertain"):
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
    with pytest.raises(AuditSinkPoisoned, match="audit close is uncertain"):
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
    with pytest.raises(AuditSinkPoisoned, match="audit close is uncertain"):
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
    with pytest.raises(AuditSinkPoisoned, match="audit close is uncertain"):
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
    with pytest.raises(AuditSinkPoisoned, match="audit close is uncertain"):
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
        with pytest.raises(AuditSinkPoisoned, match="audit close is uncertain"):
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
    with pytest.raises(AuditSinkPoisoned, match="audit close is uncertain"):
        sink.close()
    os.close(host_fd)


# RS0_F6_INDEPENDENT_REVIEW_RED_20260909
def test_already_poisoned_sink_still_attests_final_custody(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
    audit_fd = sink._audit_fd
    directory_fd = sink._directory_fd
    invalid = AuthAuditEvent(
        schema=AUTH_AUDIT_SCHEMA,
        policy_id=POLICY_ID,
        code="accepted",
        accepted=False,
    )
    with pytest.raises(AuditSinkPoisoned):
        sink.emit(invalid)

    fcntl.flock(audit_fd, fcntl.LOCK_UN)
    with pytest.raises(AuditSinkPoisoned, match="audit close is uncertain"):
        sink.close()
    with pytest.raises(AuditSinkPoisoned, match="audit close is uncertain"):
        sink.close()

    with pytest.raises(OSError):
        os.fstat(audit_fd)
    with pytest.raises(OSError):
        os.fstat(directory_fd)
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


def test_uncertain_close_remains_uncertain_on_later_calls(tmp_path: Path) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
    audit_fd = sink._audit_fd
    directory_fd = sink._directory_fd
    fcntl.flock(audit_fd, fcntl.LOCK_UN)

    with pytest.raises(AuditSinkPoisoned, match="audit close is uncertain"):
        sink.close()
    with pytest.raises(AuditSinkPoisoned, match="audit close is uncertain"):
        sink.close()

    with pytest.raises(OSError):
        os.fstat(audit_fd)
    with pytest.raises(OSError):
        os.fstat(directory_fd)
    os.close(host_fd)


def test_emit_witness_close_uncertainty_stays_uncertain_through_two_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "audit"
    host_fd = open_directory(directory)
    sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
    audit_fd = sink._audit_fd
    directory_fd = sink._directory_fd
    real_close = audit.os.close
    witness_fds: list[int] = []

    def fail_first_witness_close(descriptor: int) -> None:
        if descriptor not in {host_fd, audit_fd, directory_fd} and not witness_fds:
            witness_fds.append(descriptor)
            raise OSError("synthetic witness close uncertainty")
        real_close(descriptor)

    monkeypatch.setattr(audit.os, "close", fail_first_witness_close)
    try:
        with pytest.raises(AuditSinkPoisoned):
            sink.emit(event())
        with pytest.raises(AuditSinkPoisoned, match="audit close is uncertain"):
            sink.close()
        with pytest.raises(AuditSinkPoisoned, match="audit close is uncertain"):
            sink.close()
        with pytest.raises(OSError):
            os.fstat(audit_fd)
        with pytest.raises(OSError):
            os.fstat(directory_fd)
    finally:
        monkeypatch.setattr(audit.os, "close", real_close)
        for descriptor in witness_fds:
            try:
                real_close(descriptor)
            except OSError:
                pass
        real_close(host_fd)


def test_owner_proof_retains_unlock_and_close_failures_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_close = audit.os.close
    real_flock = audit.fcntl.flock
    host_fd = open_directory(tmp_path / "audit")
    sink = None
    injected_witness: list[int] = []
    witness_close_calls = 0
    primary_close_calls: dict[int, int] = {}
    primary_unlock_calls = 0
    primary_failure: BaseException | None = None
    fixture_cleanup_failures: list[BaseException] = []
    unlock_failure = OSError("synthetic witness unlock failure")
    close_failure = OSError("synthetic witness close failure")

    try:
        sink = DurableAuthAuditSink.open(host_fd, policy_id=POLICY_ID)
        audit_fd, directory_fd = sink._audit_fd, sink._directory_fd
        protected_fds = {host_fd, audit_fd, directory_fd}
        primary_close_calls = {audit_fd: 0, directory_fd: 0}
        # This affects only the test-owned sink. It forces the existing owner
        # proof to acquire its witness and record the primary proof failure.
        real_flock(audit_fd, fcntl.LOCK_UN)

        def injected_flock(descriptor: int, operation: int) -> None:
            nonlocal primary_unlock_calls
            if operation == fcntl.LOCK_UN and descriptor not in protected_fds:
                if not injected_witness:
                    injected_witness.append(descriptor)
                if descriptor == injected_witness[0]:
                    # Guaranteed NO syscall: fixture teardown retains ownership.
                    raise unlock_failure
            if descriptor == audit_fd and operation == fcntl.LOCK_UN:
                primary_unlock_calls += 1
            real_flock(descriptor, operation)

        def injected_close(descriptor: int) -> None:
            nonlocal witness_close_calls
            if injected_witness and descriptor == injected_witness[0]:
                witness_close_calls += 1
                # Every target attempt is observed and has NO physical effect.
                # Teardown's real_close is therefore not an uncertain retry.
                raise close_failure
            if descriptor in primary_close_calls:
                primary_close_calls[descriptor] += 1
            real_close(descriptor)

        with monkeypatch.context() as patch:
            patch.setattr(audit.fcntl, "flock", injected_flock)
            patch.setattr(audit.os, "close", injected_close)
            with pytest.raises(AuditAcquisitionUncertain) as captured:
                sink.emit(event())
            proof_failure = captured.value

            # Exercise release before asserting the new evidence tuple. The old
            # one-error candidate should fail at the tuple assertion, after the
            # primary descriptors have already had their one release attempt.
            with pytest.raises(AuditSinkPoisoned, match="audit close is uncertain"):
                sink.close()
            with pytest.raises(AuditSinkPoisoned, match="audit close is uncertain"):
                sink.close()

            assert isinstance(proof_failure.primary_error, AuditSinkPoisoned)
            assert "owner lock is absent" in str(proof_failure.primary_error)
            assert proof_failure.cleanup_errors == (unlock_failure, close_failure)
            assert proof_failure.cleanup_errors[0] is unlock_failure
            assert proof_failure.cleanup_errors[1] is close_failure
            assert proof_failure.__cause__ is unlock_failure
            assert witness_close_calls == 1
            assert primary_unlock_calls == 1
            assert primary_close_calls == {audit_fd: 1, directory_fd: 1}
            with pytest.raises(OSError):
                os.fstat(audit_fd)
            with pytest.raises(OSError):
                os.fstat(directory_fd)
            os.fstat(host_fd)  # The caller's descriptor remains caller-owned.
    except BaseException as error:
        primary_failure = error
    finally:
        # The local monkeypatch context has already restored the actual APIs.
        # Only the exact descriptor whose injected close never made a syscall
        # is cleaned here; there is no search for, adoption of, or retry of an
        # unobserved descriptor. No unrelated process or descriptor is touched.
        for descriptor in injected_witness:
            try:
                real_close(descriptor)
            except BaseException as error:
                fixture_cleanup_failures.append(error)
        if sink is not None and not sink._closed:
            try:
                sink.close()
            except BaseException as error:
                fixture_cleanup_failures.append(error)
        try:
            real_close(host_fd)
        except BaseException as error:
            fixture_cleanup_failures.append(error)

    if primary_failure is not None:
        if fixture_cleanup_failures:
            raise BaseExceptionGroup(
                "regression failure and distinct fixture cleanup failures",
                [primary_failure, *fixture_cleanup_failures],
            )
        raise primary_failure.with_traceback(primary_failure.__traceback__)
    if fixture_cleanup_failures:
        raise BaseExceptionGroup("fixture cleanup failures", fixture_cleanup_failures)
