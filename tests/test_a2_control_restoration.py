"""Native global-config owner drill for the separately governed A2 rollback.

No live service, token, Slack or provider. Only the macOS root identity and
launchd postcondition are translated; real marker, archive, atomic candidate,
file readback and reconciliation paths execute on isolated fixture files.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from control_plane import executive_control_observation as contract
from ops.executive_os import autonomy_control as owner
from ops.executive_os import a2_control_restoration as restore
from ops.executive_os import a2_agent_relay_enrollment as a2
from tests.test_executive_autonomy_control import SHA, _inprocess_marker_host
from ops.executive_os import control_observation as _original_control_observer
_REAL_ORIGINAL_PUBLISHER = _original_control_observer.publish_for_transaction


OLD = "3" * 40
TREE = "4" * 40
DIGEST = "a" * 64
BOT = "U0BT71H4FQE"


def _intent(control_hash):
    return SimpleNamespace(
        expected_sha=SHA, control_hash=control_hash,
        previous_sha=OLD, previous_tree=TREE,
        config_hash=DIGEST, plist_hash="b" * 64, bot=BOT,
    )


@pytest.fixture
def staged(monkeypatch, tmp_path):
    root, marker = _inprocess_marker_host(monkeypatch, tmp_path)
    control_file = owner.CONTROL_CONFIG
    control_doc = json.loads(control_file.read_bytes())
    control_doc.update(
        terminal_return_armed=False, coo_foreground_only=False,
        terminal_return_socket_path=restore.PERSISTENT_SOCKET,
        control_uid=contract.CONTROL_UID, python_runtime_provenance_digest="b" * 64,
    )
    control_file.chmod(0o640)
    control_file.write_bytes(owner.encode_config(control_doc))
    control_file.chmod(0o440)
    host = restore.ProductionA2ControlRestorationHost()
    monkeypatch.setattr(host, "effective_uid", lambda: 0)
    monkeypatch.setattr(host, "require_exact_install", lambda sha: sha)
    monkeypatch.setattr(host, "require_services_already_stopped", lambda: None)
    monkeypatch.setattr(host, "require_service_uids_quiescent", lambda: None)
    monkeypatch.setattr(host, "require_runtime_quiescent", lambda configs: None)

    def source_candidate(tx):
        source = host._candidate_paths(tx.transaction_id)[0]
        data = source.read_bytes()
        return json.loads(data), data, tx.prior_configs.worker_bytes

    monkeypatch.setattr(host, "_read_validated_control_candidate", source_candidate)
    a2_state = {"valid": True}

    def check_old_a2():
        if not a2_state["valid"]:
            raise a2.A2EnrollmentError("A2_REBIND_STATE_REFUSED")

    monkeypatch.setattr(restore, "_require_old_a2_pair", lambda i: check_old_a2())
    yield SimpleNamespace(
        host=host, root=root, marker=marker, control=control_file,
        old=control_file.read_bytes(), worker=owner.WORKER_CONFIG.read_bytes(),
        a2_state=a2_state, current_hash=owner.sha256_bytes(control_file.read_bytes()),
    )
    if host._transaction_owner_fd is not None:
        host._release_transaction_owner()


def retained_disarm(s):
    prior = s.host.checked_configs(SHA)
    unchanged = owner.CandidateConfigs(
        prior.control, prior.worker, prior.control_bytes, prior.worker_bytes,
        prior.control_sha256, prior.worker_sha256,
    )
    tx = owner.TransactionContext("autonomy-" + "1" * 12, SHA, prior, unchanged, None)
    receipt = owner.build_transaction_receipt(
        tx, state="DISARMED", now=datetime.now(timezone.utc),
    )
    owner.AUTONOMY_RECEIPT.write_bytes(owner._encoded_json(receipt))
    owner.AUTONOMY_RECEIPT.chmod(0o444)
    return receipt


def test_one_native_owner_rebinds_controller_socket_without_other_writes(staged):
    s = staged
    other = (s.root / "unrelated-root-entry.json").read_bytes()
    tx = restore.execute(s.host, _intent(s.current_hash))
    assert tx.startswith("autonomy-")
    assert not s.marker.exists()
    result = json.loads(s.control.read_bytes())
    before = json.loads(s.old)
    assert result == {**before, "terminal_return_socket_path": restore.LEGACY_SOCKET}
    assert owner.WORKER_CONFIG.read_bytes() == s.worker
    assert (s.root / "unrelated-root-entry.json").read_bytes() == other
    assert restore.execute(s.host, _intent(s.current_hash)) is None
    assert not s.marker.exists()


def test_a2_rebind_state_refused_fixture_prevents_control_publication(staged):
    s = staged
    s.a2_state["valid"] = False
    with pytest.raises(a2.A2EnrollmentError, match="A2_REBIND_STATE_REFUSED"):
        restore.execute(s.host, _intent(s.current_hash))
    assert s.control.read_bytes() == s.old
    assert owner.WORKER_CONFIG.read_bytes() == s.worker
    assert not s.marker.exists()


@pytest.mark.parametrize("fault", ["wrong_control_digest", "armed", "foreign_socket", "foreign_marker"])
def test_unsafe_restore_refuses_before_control_write(staged, fault):
    s = staged
    intent = _intent(s.current_hash)
    if fault == "wrong_control_digest":
        intent.control_hash = "0" * 64
    if fault in {"armed", "foreign_socket"}:
        old = json.loads(s.control.read_bytes())
        if fault == "armed":
            old["terminal_return_armed"] = True
        else:
            old["terminal_return_socket_path"] = "/tmp/foreign.sock"
        s.control.chmod(0o640)
        s.control.write_bytes(owner.encode_config(old))
        s.control.chmod(0o440)
    if fault == "foreign_marker":
        s.marker.mkdir()
    before = s.control.read_bytes()
    with pytest.raises(Exception):
        restore.execute(s.host, intent)
    assert s.control.read_bytes() == before
    if fault != "foreign_marker":
        assert not s.marker.exists()


def test_lost_ack_after_control_publication_retains_only_original_marker(staged, monkeypatch):
    s = staged
    old_receipt = retained_disarm(s)
    real = s.host.replace_control_config
    def acknowledged_then_lost(tx):
        real(tx)
        raise OSError("lost after rename")
    monkeypatch.setattr(s.host, "replace_control_config", acknowledged_then_lost)
    with pytest.raises(owner.TransactionEffectUnknown):
        restore.execute(s.host, _intent(s.current_hash))
    assert s.marker.exists()
    assert json.loads(s.control.read_bytes())["terminal_return_socket_path"] == restore.LEGACY_SOCKET
    before = s.control.read_bytes()
    s.host._release_transaction_owner()
    # Recovery must refuse to repeat the original write when the paired
    # disarm receipt is still the old preimage. Keep the original marker.
    with pytest.raises(owner.TransactionEffectUnknown):
        s.host.reconcile(_intent(s.current_hash))
    assert s.control.read_bytes() == before
    assert json.loads(owner.AUTONOMY_RECEIPT.read_bytes()) == old_receipt
    assert s.marker.exists()


def test_cli_closed_parser_requires_exact_target_witness():
    p = owner._parser()
    arguments = [
        "a2-restore-controller-socket",
        "--expected-sha", SHA, "--expected-control-sha256", "a" * 64,
        "--expected-previous-release-sha", OLD,
        "--expected-previous-tree-sha", TREE,
        "--expected-previous-config-sha256", "b" * 64,
        "--expected-previous-plist-sha256", "c" * 64,
        "--expected-bot-user-id", BOT,
    ]
    assert p.parse_args(arguments).command == "a2-restore-controller-socket"
    assert p.parse_args(["a2-restore-controller-socket-reconcile", *arguments[1:]]).command.endswith("reconcile")
    for argument in ("--token", "--config", "--plist", "--service", "--enable-w3c"):
        with pytest.raises(SystemExit):
            p.parse_args([*arguments, argument])



def test_disarmed_receipt_is_rebound_and_not_rearmed(staged):
    s = staged
    old_receipt = retained_disarm(s)
    tx = restore.execute(s.host, _intent(s.current_hash))
    actual, metadata = owner.load_receipt_file(owner.AUTONOMY_RECEIPT)
    from control_plane.executive_autonomy import validate_disarmed_interlock_document
    validate_disarmed_interlock_document(
        actual, metadata=metadata,
        control_config_sha256=owner.sha256_bytes(s.control.read_bytes()),
        worker_config_sha256=owner.sha256_bytes(s.worker),
    )
    assert actual["state"] == "DISARMED"
    assert actual["transaction_id"] == tx
    assert {k:v for k,v in actual.items() if k not in {
        "control_config_sha256", "prior_control_config_sha256", "transaction_id"
    }} == {k:v for k,v in old_receipt.items() if k not in {
        "control_config_sha256", "prior_control_config_sha256", "transaction_id"
    }}
    assert not s.marker.exists()


def test_lost_receipt_ack_reconciles_read_only_once(staged, monkeypatch):
    s = staged
    retained_disarm(s)
    real = owner._atomic_file
    writes = []
    def lose_ack(path, payload, **kw):
        real(path, payload, **kw)
        if path == owner.AUTONOMY_RECEIPT:
            writes.append(payload)
            raise OSError("lost after original receipt publication")
    monkeypatch.setattr(owner, "_atomic_file", lose_ack)
    with pytest.raises(owner.TransactionEffectUnknown):
        restore.execute(s.host, _intent(s.current_hash))
    assert len(writes) == 1 and s.marker.exists()
    s.host._release_transaction_owner()
    tx = s.host.reconcile(_intent(s.current_hash))
    assert tx.startswith("autonomy-")
    assert len(writes) == 1
    assert not s.marker.exists()


def test_real_a2_reverse_drill_state_refused_then_restored_pair(
    monkeypatch, tmp_path,
):
    """A2 CAS is real; wrong fixture witness refuses before Control recovery."""
    import asyncio
    from tests.test_a2_relay_release_rebind import (
        host as a2_host_fixture, _prepare_reverse, _reverse_witness,
        pair as actual_pair,
    )
    # pytest FixtureFunctionDefinition cannot be called directly, use the
    # public wrapped function with the identical temporary-root setup.
    seed = a2_host_fixture.__wrapped__(monkeypatch, tmp_path)
    old_pair, new_pair = _prepare_reverse(seed, monkeypatch)
    monkeypatch.setattr(owner, "SYSTEM_ROOT", a2.SYSTEM_ROOT)
    witness = _reverse_witness(old_pair)
    intent = SimpleNamespace(
        expected_sha=witness["expected_current_release_sha"],
        previous_sha=witness["expected_previous_release_sha"],
        previous_tree=witness["expected_previous_tree_sha"],
        config_hash=witness["expected_previous_config_sha256"],
        plist_hash=witness["expected_previous_plist_sha256"],
        bot=BOT,
    )
    with pytest.raises(owner.TransactionEffectUnknown):
        restore._require_old_a2_pair(intent)
    stale = {**witness, "expected_previous_config_sha256": "0" * 64}
    with pytest.raises(a2.A2EnrollmentError, match="A2_REBIND_STATE_REFUSED"):
        asyncio.run(a2._reverse_rebind(**stale))
    assert actual_pair() == new_pair
    assert asyncio.run(a2._reverse_rebind(**witness))["action"] == "reversed"
    assert actual_pair() == old_pair
    restore._require_old_a2_pair(intent)


def test_service_restore_owner_refuses_untrusted_or_incomplete_arguments():
    from pathlib import Path
    import subprocess
    script = Path(__file__).parents[1] / "ops/executive_os/service-control.sh"
    content = script.read_text()
    # Two deliberate appearances: bounded upfront argument dispatch and
    # the actual fixed-label lifecycle case. Read the latter.
    segment = content.rsplit("  start-restored-a2-readside)", 1)[1].split(
        "  start-agent-relay)", 1)[0]
    assert segment.index("readside_preflight") < segment.index("start_agent_relay")
    assert segment.index("a2-restored-readside-preflight") < segment.index("start_agent_relay")
    assert segment.index("start_agent_relay") < segment.index('ensure_running "$RELAY_LABEL"')
    assert segment.index('ensure_running "$RELAY_LABEL"') < segment.index('ensure_running "$CONTROL_LABEL"')
    bad = subprocess.run(
        ["/bin/bash", str(script), "start-restored-a2-readside",
         "--expected-sha", "not-an-installed-sha"],
        capture_output=True, text=True, check=False,
    )
    assert bad.returncode == 64
    assert "usage:" in bad.stderr or "usage:" in bad.stdout


def test_preflight_requires_settled_exact_controller_and_receipt(staged):
    s = staged
    intent = _intent(s.current_hash)
    with pytest.raises(owner.TransactionEffectUnknown):
        restore.qualify_restored_readside(s.host, intent)
    retained_disarm(s)
    restore.execute(s.host, intent)
    restore.qualify_restored_readside(s.host, intent)
    assert not s.marker.exists()


def test_preflight_refuses_loaded_or_foreign_a2_after_success(staged):
    s = staged
    intent = _intent(s.current_hash)
    restore.execute(s.host, intent)
    s.a2_state["valid"] = False
    with pytest.raises(a2.A2EnrollmentError, match="A2_REBIND_STATE_REFUSED"):
        restore.qualify_restored_readside(s.host, intent)


def test_controller_restore_refuses_foreign_autonomy_receipt(staged):
    s = staged
    retained_disarm(s)
    old = json.loads(owner.AUTONOMY_RECEIPT.read_bytes())
    owner.AUTONOMY_RECEIPT.chmod(0o644)
    owner.AUTONOMY_RECEIPT.write_bytes(owner._encoded_json(dict(old, state="ARMED")))
    owner.AUTONOMY_RECEIPT.chmod(0o444)
    with pytest.raises(Exception):
        restore.execute(s.host, _intent(s.current_hash))
    assert s.control.read_bytes() == s.old
    assert not s.marker.exists()


def test_fully_reverted_target_is_idempotent_only_if_preflight_passes(staged):
    s = staged
    intent = _intent(s.current_hash)
    restore.execute(s.host, intent)
    before = s.control.stat().st_ino
    restore.execute(s.host, intent)
    assert s.control.stat().st_ino == before
    s.a2_state["valid"] = False
    with pytest.raises(a2.A2EnrollmentError, match="A2_REBIND_STATE_REFUSED"):
        restore.execute(s.host, intent)
    assert s.control.stat().st_ino == before


def test_settled_restored_readside_witness_binds_preimage_sha(staged):
    s = staged
    intent = _intent(s.current_hash)
    restore.execute(s.host, intent)
    assert json.loads(s.control.read_bytes())["terminal_return_socket_path"] == restore.LEGACY_SOCKET
    # The terminal-reading carrier must not accept arbitrary user supplied
    # "preimage" digests merely because the final config looks disarmed.
    forged = _intent("0" * 64)
    with pytest.raises(owner.TransactionEffectUnknown):
        restore.qualify_restored_readside(s.host, forged)
    with pytest.raises(owner.TransactionEffectUnknown):
        restore.execute(s.host, forged)
    restore.qualify_restored_readside(s.host, intent)

def test_seven_valid_restore_witnesses_reach_privilege_gate_not_usage():
    import os
    import sys
    import subprocess
    from pathlib import Path
    # Never execute a lifecycle test while root on a production macOS host.
    if os.geteuid() == 0 and sys.platform == "darwin":
        pytest.skip("real root macOS service controller may have effects")
    script = Path(__file__).parents[1] / "ops/executive_os/service-control.sh"
    args = [
        "start-restored-a2-readside",
        "--expected-sha", SHA,
        "--expected-control-sha256", "a"*64,
        "--expected-previous-release-sha", OLD,
        "--expected-previous-tree-sha", TREE,
        "--expected-previous-config-sha256", "b"*64,
        "--expected-previous-plist-sha256", "c"*64,
        "--expected-bot-user-id", BOT,
    ]
    assert len(args)==15
    result = subprocess.run(["/bin/bash", str(script), *args],
                            text=True, capture_output=True, check=False)
    assert result.returncode in (69, 77), (result.returncode, result.stderr)
    assert "usage:" not in result.stderr


@pytest.mark.parametrize("projection_failure", ["none", "lost-after-write", "refused-before-write"])
def test_fresh_recovery_uses_original_observation_owner_once(
    staged, monkeypatch, projection_failure,
):
    """Real publisher/marker/CAS/receipt on disposable files across host objects.

    Only installed-source identity and the physical macOS Control UID are
    adapted; the canonical publisher and original atomic-file implementation
    execute, and no staged source is published into a real host.
    """
    import hashlib
    import os
    import stat
    from ops.executive_os import control_observation as publisher
    from control_plane import executive_control_observation as contract

    s = staged
    intent = _intent(s.current_hash)
    original_publisher = publisher._publish_for_transaction
    original_read = owner._read_root_file
    original_atomic = owner._atomic_file
    out = s.root / "control-observation-fixture.json"
    monkeypatch.setattr(contract, "OBSERVATION_PATH", str(out))
    writes = []

    def installed_source_probe(sha):
        assert sha == SHA

    def observation_target(sha):
        assert sha == SHA
        raw = owner.CONTROL_CONFIG.read_bytes()
        info = owner.CONTROL_CONFIG.stat()
        identity = (
            info.st_dev, info.st_ino, info.st_mode, 0,
            contract.CONTROL_UID, info.st_nlink, len(raw),
            info.st_mtime_ns, info.st_ctime_ns,
        )
        return contract.encode_observation(raw, identity, sha), ()

    def read_observation():
        if not out.exists():
            return None
        raw = out.read_bytes()
        contract.parse_observation(raw)
        return raw

    def read_control(path, *, modes, uid=0, gid=None):
        # Marker fixture's simulated root/control group is 0; production
        # publisher requires the existing fixed Control gid.
        if path == owner.CONTROL_CONFIG and gid == contract.CONTROL_UID:
            gid = 0
        return original_read(path, modes=modes, uid=uid, gid=gid)

    def observe_write(path, raw, **kwargs):
        if path == out:
            writes.append(raw)
            if projection_failure == "refused-before-write":
                raise OSError("first original observation publication refused")
        original_atomic(path, raw, **kwargs)
        if path == out and projection_failure == "lost-after-write":
            raise OSError("lost acknowledgement after one original publication")

    monkeypatch.setattr(publisher, "_source", installed_source_probe)
    monkeypatch.setattr(publisher, "_snapshot", observation_target)
    monkeypatch.setattr(publisher, "_retained", read_observation)
    monkeypatch.setattr(publisher, "_publish_for_transaction", original_publisher)
    monkeypatch.setattr(publisher, "publish_for_transaction", publisher.publish_for_transaction.__wrapped__
                        if hasattr(publisher.publish_for_transaction, "__wrapped__")
                        else _REAL_ORIGINAL_PUBLISHER)
    monkeypatch.setattr(owner, "_read_root_file", read_control)
    monkeypatch.setattr(owner, "_atomic_file", observe_write)

    retained_disarm(s)
    # Simulate an original-process crash after *both* Control+DISARMED receipt
    # are published, but before the original observation path has started.
    def crash_before_observation(_tx):
        raise RuntimeError("original process exited before original observation")
    monkeypatch.setattr(s.host, "settle_readback", crash_before_observation)
    with pytest.raises(owner.TransactionEffectUnknown):
        restore.execute(s.host, intent)
    assert s.marker.exists() and len(writes) == 0
    assert json.loads(s.control.read_bytes())["terminal_return_socket_path"] == restore.LEGACY_SOCKET
    s.host._release_transaction_owner()

    def fresh_host():
        recovered = restore.ProductionA2ControlRestorationHost()
        monkeypatch.setattr(recovered, "effective_uid", lambda: 0)
        monkeypatch.setattr(recovered, "require_exact_install", lambda sha: sha)
        monkeypatch.setattr(recovered, "require_services_already_stopped", lambda: None)
        monkeypatch.setattr(recovered, "require_service_uids_quiescent", lambda: None)
        monkeypatch.setattr(recovered, "require_runtime_quiescent", lambda configs: None)
        return recovered

    first = fresh_host()
    if projection_failure == "none":
        assert first.reconcile(intent).startswith("autonomy-")
        assert not s.marker.exists()
    else:
        with pytest.raises(owner.TransactionEffectUnknown):
            first.reconcile(intent)
        assert s.marker.exists()
        assert json.loads((s.marker / "transaction.json").read_bytes())["phase"] == publisher.PUBLICATION_PHASE
        first._release_transaction_owner()
        second = fresh_host()
        if projection_failure == "lost-after-write":
            assert second.reconcile(intent).startswith("autonomy-")
            assert not s.marker.exists()
        else:
            with pytest.raises(owner.TransactionEffectUnknown):
                second.reconcile(intent)
            assert s.marker.exists()
            second._release_transaction_owner()
    assert len(writes) == 1
    if projection_failure != "refused-before-write":
        assert out.exists()
        assert contract.parse_observation(out.read_bytes())["control_sha256"] == hashlib.sha256(
            s.control.read_bytes()
        ).hexdigest()
    else:
        assert not out.exists()

def test_fabric_bridge_armed_refuses_before_creating_a_global_marker(staged):
    s = staged
    config = json.loads(s.control.read_bytes())
    config["fabric_bridge_armed"] = True
    s.control.chmod(0o640)
    s.control.write_bytes(owner.encode_config(config))
    s.control.chmod(0o440)
    before = s.control.read_bytes()
    with pytest.raises(owner.TransactionEffectUnknown):
        restore.execute(s.host, _intent(owner.sha256_bytes(before)))
    assert s.control.read_bytes() == before
    assert not s.marker.exists()


@pytest.mark.parametrize("bad", ["wrong-flag-order", "invalid-config-digest", "duplicated-flag"])
def test_seven_witness_service_invocation_rejects_malformed_full_width(bad):
    import subprocess
    from pathlib import Path
    script = Path(__file__).parents[1] / "ops/executive_os/service-control.sh"
    args = [
        "start-restored-a2-readside",
        "--expected-sha", SHA,
        "--expected-control-sha256", "a"*64,
        "--expected-previous-release-sha", OLD,
        "--expected-previous-tree-sha", TREE,
        "--expected-previous-config-sha256", "b"*64,
        "--expected-previous-plist-sha256", "c"*64,
        "--expected-bot-user-id", BOT,
    ]
    if bad == "wrong-flag-order":
        args[9], args[11] = args[11], args[9]
    elif bad == "invalid-config-digest":
        args[10] = "not-a-hex-digest"
    else:
        args[9] = "--expected-control-sha256"
    assert len(args) == 15
    result = subprocess.run(["/bin/bash", str(script), *args],
                            text=True, capture_output=True, check=False)
    assert result.returncode == 64
    assert "usage:" in result.stderr
