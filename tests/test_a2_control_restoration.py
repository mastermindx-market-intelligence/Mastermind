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

from ops.executive_os import autonomy_control as owner
from ops.executive_os import a2_control_restoration as restore
from ops.executive_os import a2_agent_relay_enrollment as a2
from tests.test_executive_autonomy_control import SHA, _inprocess_marker_host


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
    prior_sha = a2.OLD if hasattr(a2, "OLD") else "9" * 40
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
    segment = content.split("  start-restored-a2-readside)", 1)[1].split(
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
