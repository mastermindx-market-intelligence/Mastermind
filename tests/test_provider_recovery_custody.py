"""Preventive custody checks exercise real filesystem and broker boundaries."""
from pathlib import Path
import os
import stat

import pytest

from tests.test_provider_incident_recovery import (
    state, custody_root, recovery, incident_policy, incident_request_raw,
    make_broker, ISSUER_REQUEST_ID, rec, broker_module, PrivilegedBrokerError,
    EffectUnknownError,
)


def assert_unreserved(broker):
    assert not broker.inflight_path(ISSUER_REQUEST_ID).exists()
    assert not broker.receipt_path(ISSUER_REQUEST_ID).exists()


@pytest.mark.parametrize("missing", ["current-pin", "provider-recovery"])
def test_missing_hierarchy_refuses_before_original_marker(recovery, monkeypatch, missing):
    monkeypatch.setattr(rec, "PRODUCTION_INCIDENT_POLICY", incident_policy(recovery))
    rec.RECOVERY_STATE_ROOT.rmdir()
    if missing == "provider-recovery":
        rec.RECOVERY_STATE_ROOT.parent.rmdir()
    broker = make_broker(recovery)
    with pytest.raises(PrivilegedBrokerError, match="recovery_custody_parent_missing"):
        broker.handle(incident_request_raw(), peer_uid=501)
    assert_unreserved(broker)
    assert not rec.RECOVERY_INCIDENT_GRANT_PATH.exists()


@pytest.mark.parametrize("slot", ["grant.json", "incident-grant.json",
                                  "incident-commitment.json", "allocation.json"])
@pytest.mark.parametrize("kind", ["malformed", "symlink", "fifo"])
def test_any_slot_occupant_refuses_before_marker(recovery, monkeypatch, slot, kind):
    monkeypatch.setattr(rec, "PRODUCTION_INCIDENT_POLICY", incident_policy(recovery))
    path = rec.RECOVERY_STATE_ROOT / slot
    if kind == "malformed":
        path.write_bytes(b"unparsed incumbent bytes")
    elif kind == "symlink":
        path.symlink_to(path.parent / "missing-target")
    else:
        os.mkfifo(path)
    before = path.lstat()
    broker = make_broker(recovery)
    with pytest.raises(PrivilegedBrokerError):
        broker.handle(incident_request_raw(), peer_uid=501)
    assert_unreserved(broker)
    assert path.lstat() == before


@pytest.mark.parametrize("missing", [1, 2])
def test_installer_creates_only_missing_private_directories(recovery, monkeypatch, missing):
    root = rec.RECOVERY_STATE_ROOT
    root.rmdir()
    if missing == 2:
        root.parent.rmdir()
    syncs = []
    real_fsync = os.fsync

    def synced(fd):
        syncs.append(os.fstat(fd).st_ino)
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", synced)
    rec.prepare_recovery_custody()
    for path in (root.parent, root):
        info = path.lstat()
        assert (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (
            os.getuid(), os.getgid(), 0o700)
    assert root.stat().st_ino in syncs
    assert root.parent.stat().st_ino in syncs
    assert len(syncs) == 2 * missing
    rec.preflight_recovery_custody()


def test_installer_preserves_existing_documents_and_directory_identity(recovery, monkeypatch):
    root = rec.RECOVERY_STATE_ROOT
    paths = [root.parent, root]
    for name in ("grant.json", "incident-grant.json", "incident-commitment.json", "allocation.json"):
        path = root / name
        path.write_bytes(b"immutable original evidence")
        path.chmod(0o400)
        paths.append(path)
    before = {path: path.lstat() for path in paths}
    monkeypatch.setattr(os, "mkdir", lambda *a, **k: pytest.fail("unexpected creation"))
    monkeypatch.setattr(os, "fchmod", lambda *a, **k: pytest.fail("normalization"))
    monkeypatch.setattr(os, "fchown", lambda *a, **k: pytest.fail("normalization"))
    rec.prepare_recovery_custody()
    assert {path: path.lstat() for path in paths} == before
    for path in paths[2:]:
        assert path.read_bytes() == b"immutable original evidence"


@pytest.mark.parametrize("level", [0, 1])
@pytest.mark.parametrize("mode", [0o755, 0o770])
def test_unsafe_existing_private_directory_is_not_normalized(recovery, level, mode):
    path = rec.RECOVERY_STATE_ROOT if level == 0 else rec.RECOVERY_STATE_ROOT.parent
    path.chmod(mode)
    before = path.lstat()
    with pytest.raises(rec.RecoveryError):
        rec.prepare_recovery_custody()
    assert path.lstat() == before
    with pytest.raises(rec.RecoveryError):
        rec.preflight_recovery_custody()


@pytest.mark.parametrize("kind", ["symlink", "file"])
def test_installer_refuses_wrong_type_without_touching_target(recovery, kind):
    root = rec.RECOVERY_STATE_ROOT
    root.rmdir()
    target = root.parent / "unrelated"
    target.mkdir(mode=0o700)
    if kind == "symlink":
        root.symlink_to(target)
    else:
        root.write_bytes(b"incumbent")
    before = root.lstat()
    with pytest.raises(rec.RecoveryError):
        rec.prepare_recovery_custody()
    assert root.lstat() == before
    assert list(target.iterdir()) == []


@pytest.mark.parametrize("field", ["CUSTODY_UID", "CUSTODY_GID"])
def test_wrong_owner_or_group_refuses_without_normalization(recovery, monkeypatch, field):
    root = rec.RECOVERY_STATE_ROOT
    before = root.lstat()
    monkeypatch.setattr(rec, field, getattr(rec, field) + 1)
    with pytest.raises(rec.RecoveryError):
        rec.preflight_recovery_custody()
    assert root.lstat() == before


def test_acl_and_identity_drift_are_typed_refusals(recovery, monkeypatch):
    root = rec.RECOVERY_STATE_ROOT

    def acl_denied(path):
        if path == root:
            raise rec._readiness.ReadinessError("identity_acl_unsafe")

    monkeypatch.setattr(rec._readiness, "_assert_no_macos_acl", acl_denied)
    with pytest.raises(rec.RecoveryError, match="recovery_custody_unreadable"):
        rec.preflight_recovery_custody()

    def replace_during_acl(path):
        if path == root and not root.with_name("old").exists():
            root.rename(root.with_name("old"))
            root.mkdir(mode=0o700)

    monkeypatch.setattr(rec._readiness, "_assert_no_macos_acl", replace_during_acl)
    with pytest.raises(rec.RecoveryError, match="recovery_custody_parent_changed"):
        rec.preflight_recovery_custody()


def test_unreadable_parent_is_not_an_empty_slot(recovery, monkeypatch):
    real_open = os.open

    def denied(path, *args, **kwargs):
        if path == rec.RECOVERY_STATE_ROOT.name:
            raise PermissionError("unreadable")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", denied)
    with pytest.raises(rec.RecoveryError, match="recovery_custody_unreadable"):
        rec.preflight_recovery_custody()


def test_installer_fsync_failure_refuses_without_removing_created_directory(recovery, monkeypatch):
    root = rec.RECOVERY_STATE_ROOT
    root.rmdir()

    def failed_sync(fd):
        raise OSError("fsync failed")

    monkeypatch.setattr(os, "fsync", failed_sync)
    with pytest.raises(rec.RecoveryError, match="recovery_custody_unreadable"):
        rec.prepare_recovery_custody()
    assert root.is_dir()
    assert list(root.iterdir()) == []


def test_occupancy_race_after_preflight_retains_unknown_marker(recovery, monkeypatch):
    monkeypatch.setattr(rec, "PRODUCTION_INCIDENT_POLICY", incident_policy(recovery))
    broker = make_broker(recovery)
    original = broker._write_inflight

    def raced(request, digest, started_at):
        original(request, digest, started_at)
        rec.RECOVERY_INCIDENT_GRANT_PATH.write_bytes(b"concurrent incumbent")

    monkeypatch.setattr(broker, "_write_inflight", raced)
    with pytest.raises(EffectUnknownError, match="cannot be replaced"):
        broker.handle(incident_request_raw(), peer_uid=501)
    assert broker.inflight_path(ISSUER_REQUEST_ID).is_file()
    assert rec.RECOVERY_INCIDENT_GRANT_PATH.read_bytes() == b"concurrent incumbent"
    assert not broker.receipt_path(ISSUER_REQUEST_ID).exists()


def test_existing_inflight_still_wins_before_missing_custody(recovery, monkeypatch):
    monkeypatch.setattr(rec, "PRODUCTION_INCIDENT_POLICY", incident_policy(recovery))
    broker = make_broker(recovery)
    request = broker_module.validate_request(incident_request_raw())
    broker._write_inflight(request, broker._request_digest(request), broker_module._utc_now())
    marker = broker.inflight_path(ISSUER_REQUEST_ID)
    before = marker.read_bytes()
    rec.RECOVERY_STATE_ROOT.rmdir()
    with pytest.raises(EffectUnknownError, match="stale in-flight"):
        broker.handle(incident_request_raw(), peer_uid=501)
    assert marker.read_bytes() == before


def test_installer_calls_real_helper_between_stop_and_bootstrap():
    source = (Path(__file__).parents[1] / "ops/executive_os/install.sh").read_text()
    call = source.index("prepare_recovery_custody()")
    assert source.index('/bin/launchctl bootout "system/$PRIVILEGED_LABEL"') < call
    assert call < source.index('/bin/launchctl bootstrap system "$PRIVILEGED_PLIST"')
    assert 'from ops.executive_os.provider_recovery import prepare_recovery_custody' in source
