"""Original run-log fencing only; no provider, lease, process or host effects."""
from concurrent.futures import ThreadPoolExecutor
import json

import pytest

from integrations.session_bridge.bound_launch_capture import fabric_launch_reservation as fence


def binding():
    return dict(root_id="root-1", job_id="job-1", attempt_id="attempt-1",
                effective_grant_sha256="a" * 64, commission_sha256="b" * 64,
                physical_binding_sha256="c" * 64, start_request_sha256="d" * 64)


def reserve(path, value=None):
    return fence.reserve_bound_log(path, binding() if value is None else value,
                                   run_id="attempt-1", root_id="root-1")


def read(path, value=None):
    return fence.read_bound_log(path, expected=binding() if value is None else value,
                               run_id="attempt-1", root_id="root-1")


def test_competing_starts_cross_the_original_effect_boundary_once(tmp_path):
    log = tmp_path / "attempt-1.log"
    def original_owner(_):
        try:
            reserve(log)
        except FileExistsError:
            return "HELD_EXISTING"
        return "FIRST_RESERVATION_ONLY"
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(original_owner, range(2)))
    assert sorted(outcomes) == ["FIRST_RESERVATION_ONLY", "HELD_EXISTING"]
    with log.open("ab") as stream:
        stream.write(b"original controller progress\n")
    result = read(log)
    assert result["binding"] == binding()
    assert result["start_authorized"] is False
    assert result["effect_state"] == "UNRESOLVED_BY_RESERVATION"


@pytest.mark.parametrize("key", sorted(fence.DIGESTS | {"job_id"}))
def test_same_run_changed_request_or_route_never_reuses_a_reservation(tmp_path, key):
    log = tmp_path / "attempt-1.log"
    reserve(log)
    changed = dict(binding(), **{key: "other-job" if key == "job_id" else "e" * 64})
    with pytest.raises(FileExistsError):
        reserve(log, changed)
    with pytest.raises(fence.ReservationRefused, match="request_conflict"):
        read(log, changed)
    assert read(log)["binding"] == binding()


def test_failed_durability_never_erases_or_reuses_original_name(tmp_path, monkeypatch):
    log = tmp_path / "attempt-1.log"
    def fail(_):
        raise OSError("inert durability failure")
    monkeypatch.setattr(fence.os, "fsync", fail)
    with pytest.raises(OSError):
        reserve(log)
    assert log.exists()
    with pytest.raises(FileExistsError):
        reserve(log)


@pytest.mark.parametrize("raw", [b"", b"RUN_RESERVED\n", fence.PREFIX + b"{}", fence.PREFIX + b"{}\n"])
def test_legacy_empty_or_truncated_record_never_means_unstarted(tmp_path, raw):
    log = tmp_path / "attempt-1.log"
    log.write_bytes(raw)
    log.chmod(0o600)
    with pytest.raises(fence.ReservationRefused):
        read(log)
    with pytest.raises(FileExistsError):
        reserve(log)


def test_missing_record_does_not_create_or_authorize_a_launch(tmp_path):
    log = tmp_path / "absent.log"
    with pytest.raises(FileNotFoundError):
        read(log)
    assert not log.exists()


def test_partial_binding_refuses_before_any_reservation(tmp_path):
    log = tmp_path / "attempt-1.log"
    incomplete = binding()
    incomplete.pop("physical_binding_sha256")
    with pytest.raises(fence.ReservationRefused, match="identity_invalid"):
        reserve(log, incomplete)
    assert not log.exists()


def test_wrong_root_and_attempt_refuse_before_any_reservation(tmp_path):
    log = tmp_path / "attempt-1.log"
    for key in ("root_id", "attempt_id"):
        with pytest.raises(fence.ReservationRefused, match="identity_invalid"):
            reserve(log, dict(binding(), **{key: "foreign"}))
    assert not log.exists()


def test_shared_directory_symlink_and_input_mode_are_not_repaired(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o775)
    shared.chmod(0o775)
    with pytest.raises(fence.ReservationRefused, match="directory_unsafe"):
        reserve(shared / "attempt-1.log")
    assert shared.stat().st_mode & 0o777 == 0o775
    log = tmp_path / "attempt-1.log"
    target = tmp_path / "target"
    target.write_bytes(b"preserve")
    log.symlink_to(target)
    with pytest.raises(FileExistsError):
        reserve(log)
    assert target.read_bytes() == b"preserve"
    source = tmp_path / "binding.json"
    source.write_text(json.dumps(binding()))
    source.chmod(0o600)
    assert fence.load_binding(source, run_id="attempt-1", root_id="root-1") == binding()
    source.chmod(0o644)
    with pytest.raises(fence.ReservationRefused, match="file_unsafe"):
        fence.load_binding(source, run_id="attempt-1", root_id="root-1")
    assert source.stat().st_mode & 0o777 == 0o644


def test_duplicate_input_keys_refuse_without_reserving(tmp_path):
    source = tmp_path / "binding.json"
    source.write_text(json.dumps(binding())[:-1] + ', "attempt_id": "attempt-1"}')
    source.chmod(0o600)
    with pytest.raises(fence.ReservationRefused, match="json_invalid"):
        fence.load_binding(source, run_id="attempt-1", root_id="root-1")


def test_short_write_is_completed_and_directory_replacement_refuses(tmp_path, monkeypatch):
    original = fence.os.write
    monkeypatch.setattr(fence.os, "write", lambda fd, data: original(fd, data[:7]))
    log = tmp_path / "attempt-1.log"
    reserve(log)
    assert read(log)["binding"] == binding()
    source = tmp_path / "original"
    source.mkdir(mode=0o700)
    saved_fsync = fence.os.fsync
    calls = []
    def move_after_sync(fd):
        saved_fsync(fd)
        calls.append(fd)
        if len(calls) == 2:
            source.rename(tmp_path / "retained")
            source.mkdir(mode=0o700)
    monkeypatch.setattr(fence.os, "fsync", move_after_sync)
    with pytest.raises(fence.ReservationRefused, match="reservation_moved"):
        reserve(source / "attempt-1.log")
    assert (tmp_path / "retained" / "attempt-1.log").exists()
