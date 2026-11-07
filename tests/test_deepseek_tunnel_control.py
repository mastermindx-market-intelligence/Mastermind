"""DSH uses the incumbent finite transport owner with isolated fixed identity.

Root fixtures exercise real source seals, locks, journals and file publication.
Only service/process observations are synthetic; no live tunnel is started.
"""
import json
import os
from pathlib import Path

import pytest

from ops.executive_os import application_tunnel_control as control
from ops.executive_os import os_tunnel_entry as entry
from tests.test_application_tunnel_control import (
    FakeSystem, Harness, INCUMBENT, _own, sealed_root,
)

pytestmark = pytest.mark.skipif(os.geteuid() != 0, reason="isolated root transport fixture")
DSH = entry.DEEPSEEK_APPLICATION
FABRIC = entry.FABRIC_APPLICATION


def _case(root, purpose, host_root=None):
    return Harness(root, purpose=purpose, host_root=host_root)


def _server(harness):
    return FakeSystem(purpose=harness.purpose, unit={
        "active": True, "main_pid": 4242, "argv": control._server_expected_argv(harness.paths),
    })


def _apply(harness, *, reconcile=False):
    raw, expected = harness.bundle()
    bundle = harness.root / "carried-bundle.json"
    if not bundle.exists():
        bundle.write_bytes(raw)
        _own(bundle, 0o600)
    action = control.reconcile_server if reconcile else control.apply_server
    return action(bundle_path=bundle, expected_digest=expected,
                  paths=harness.paths, system=_server(harness))


def _receipt_path(harness, receipt):
    path = harness.root / "carried-receipt.json"
    path.write_bytes(control.canonical(receipt))
    _own(path, 0o600)
    return path


def test_deepseek_closed_reverse_has_distinct_identity_and_target():
    config = {"schema": DSH.client_schema, "binary_sha256": "b" * 64,
              "server_fingerprint": "F" * 43 + "="}
    secret = (DSH.audience + ":" + "x" * 48).encode()
    _, argv, env = entry.deepseek_launch_spec(config, secret)
    assert argv[-1] == "R:127.0.0.1:4181:127.0.0.1:4180"
    assert env["AUTH"] == secret.decode()
    assert DSH.remote_regex == r"^R:127\.0\.0\.1:4181$"
    assert control.operation_identity(purpose=DSH) != control.operation_identity()
    with pytest.raises(ValueError):
        entry.deepseek_launch_spec(config, (FABRIC.audience + ":" + "x" * 48).encode())
    with pytest.raises(ValueError):
        entry.deepseek_launch_spec({**config, "target_port": 4142}, secret)
    with pytest.raises(ValueError):
        entry.closed_application_purpose(DSH._replace(target_port=4142))
    assert control.Paths.deepseek().credential != control.Paths().credential


def test_deepseek_real_stage_apply_start_stop_preserves_native_owner(sealed_root):
    h = _case(sealed_root / "dsh-lifecycle", DSH)
    h.stage()
    h.write_authfile()
    server = _apply(h)
    assert server["state"] == "GRANT_FILE_APPLIED"
    assert server["schema"] == DSH.receipt_schema
    client = FakeSystem(purpose=DSH)
    control.apply_client(paths=h.paths, system=client)
    receipt = _receipt_path(h, server)
    started = control.start_client(server_receipt=receipt, paths=h.paths, system=client)
    assert started["state"] == "STARTED"
    assert started["commands"] == 1
    assert client.calls == [("bootstrap", str(h.paths.plist))]
    assert not started["tunnel_proven"] and not started["application_proven"]
    control.stop_client(paths=h.paths, system=client)
    assert client.calls[-1] == ("bootout", DSH.label)
    assert not control.Paths.fixture(h.root / "host").credential.exists()


def test_fabric_settled_deepseek_adds_fabric_observes_without_writes(sealed_root):
    base = sealed_root / "additive"
    fabric = _case(base / "fabric", FABRIC, base / "host")
    dsh = _case(base / "dsh", DSH, base / "host")
    fabric.stage()
    dsh.stage()
    fabric.write_authfile()
    original = _apply(fabric)
    journal = fabric.paths.server_operation_root / "operation" / "server-receipt.json"
    historical = journal.read_bytes()
    _apply(dsh)
    before = fabric.paths.server_authfile.read_bytes()
    observed = _apply(fabric, reconcile=True)
    assert observed["authfile_observation"] == "OWN_GRANT_PRESENT_AUTHFILE_ADVANCED"
    assert {key: observed[key] for key in original} == original
    assert observed["current_authfile_sha256"] == control.digest(before)
    assert journal.read_bytes() == historical
    assert fabric.paths.server_authfile.read_bytes() == before
    entries = json.loads(before)
    assert all(entries[key] == value for key, value in INCUMBENT.items())
    assert sum(key.startswith(DSH.audience + ":") for key in entries) == 1
    assert sum(key.startswith(FABRIC.audience + ":") for key in entries) == 1
    assert observed["server_reload_proven"] is False


def test_authfile_advance_refuses_same_username_other_password(sealed_root):
    h = _case(sealed_root / "conflicting-user", FABRIC)
    h.stage()
    h.write_authfile()
    _apply(h)
    value = json.loads(h.paths.server_authfile.read_bytes())
    value[FABRIC.audience + ":" + "q" * 48] = [DSH.remote_regex]
    h.paths.server_authfile.write_bytes(control.canonical(value))
    with pytest.raises(ValueError, match="conflicting existing application identity"):
        _apply(h, reconcile=True)


def test_unresolved_peer_blocks_new_intent_but_original_can_reconcile(sealed_root, monkeypatch):
    base = sealed_root / "uncertain-peer"
    fabric = _case(base / "fabric", FABRIC, base / "host")
    dsh = _case(base / "dsh", DSH, base / "host")
    fabric.stage()
    dsh.stage()
    fabric.write_authfile()
    install = control._install

    def interrupted(*args, **kwargs):
        raise OSError("fixture interrupted before replacement")

    monkeypatch.setattr(control, "_install", interrupted)
    with pytest.raises(OSError, match="fixture interrupted"):
        _apply(fabric)
    monkeypatch.setattr(control, "_install", install)
    with pytest.raises(ValueError, match="requires reconciliation"):
        _apply(dsh)
    assert not (dsh.paths.server_operation_root / "operation" / "server-intent.json").exists()
    assert _apply(fabric, reconcile=True)["state"] == "NOT_APPLIED"
    assert _apply(fabric)["state"] == "GRANT_FILE_APPLIED"
    assert _apply(dsh)["state"] == "GRANT_FILE_APPLIED"


def test_lost_ack_peer_allows_original_postimage_receipt_repair(sealed_root, monkeypatch):
    base = sealed_root / "lost-ack-peer"
    fabric = _case(base / "fabric", FABRIC, base / "host")
    dsh = _case(base / "dsh", DSH, base / "host")
    fabric.stage()
    dsh.stage()
    fabric.write_authfile()
    install = control._install

    def lost_ack(*args, **kwargs):
        install(*args, **kwargs)
        raise OSError("fixture lost acknowledgement after replacement")

    monkeypatch.setattr(control, "_install", lost_ack)
    with pytest.raises(OSError, match="lost acknowledgement"):
        _apply(fabric)
    monkeypatch.setattr(control, "_install", install)
    with pytest.raises(ValueError, match="requires reconciliation"):
        _apply(dsh)
    original_bytes = fabric.paths.server_authfile.read_bytes()
    assert _apply(fabric, reconcile=True)["state"] == "GRANT_FILE_APPLIED"
    assert fabric.paths.server_authfile.read_bytes() == original_bytes
    assert _apply(dsh)["state"] == "GRANT_FILE_APPLIED"


def test_shared_authfile_lock_excludes_other_purpose(sealed_root):
    base = sealed_root / "shared-lock"
    fabric = _case(base / "fabric", FABRIC, base / "host")
    dsh = _case(base / "dsh", DSH, base / "host")
    dsh.stage()
    dsh.write_authfile()
    with control._PurposeLock(fabric.paths, create=True, server=True, shared_authfile=True):
        with pytest.raises(ValueError, match="custody is busy"):
            _apply(dsh)
    assert not (dsh.paths.server_operation_root / "operation" / "server-intent.json").exists()


def test_peer_receipt_must_describe_retained_candidate(sealed_root):
    base = sealed_root / "receipt-identity"
    fabric = _case(base / "fabric", FABRIC, base / "host")
    dsh = _case(base / "dsh", DSH, base / "host")
    fabric.stage()
    dsh.stage()
    fabric.write_authfile()
    _apply(fabric)
    journal = fabric.paths.server_operation_root / "operation" / "server-receipt.json"
    record = json.loads(journal.read_bytes())
    record["authfile_identity"]["sha256"] = "0" * 64
    journal.write_bytes(control.canonical(record))
    with pytest.raises(ValueError, match="historical authfile identity"):
        _apply(dsh)
    assert not (dsh.paths.server_operation_root / "operation" / "server-intent.json").exists()
