import dataclasses
import json
from types import SimpleNamespace

import pytest

from control_plane.dialogue_wake_canary_publication import canonical_digest
from control_plane.dialogue_wake_canary_activation import IDENTITY_FIELDS
from integrations.session_bridge.canary_source import CanaryGrantProposal
from ops.executive_os import autonomy_control as owner
from ops.executive_os import dialogue_wake_canary_control as canary
from tests.test_dialogue_wake_canary_activation import parsed
from tests.test_executive_autonomy_control import (
    SHA, NOW, FakeTransactionHost, _inprocess_marker_host,
)


def proposal():
    grant = parsed(installed_release_sha=SHA)
    return CanaryGrantProposal(
        grant=grant, read_ref="session-reply-" + "4" * 64,
        source_event_sha256="5" * 64,
        facts_sha256=canonical_digest({k: getattr(grant, k) for k in IDENTITY_FIELDS}),
    )


def configure(host, monkeypatch):
    monkeypatch.setattr(host, "effective_uid", lambda: 0)
    monkeypatch.setattr(host, "require_exact_install", lambda expected: expected)
    monkeypatch.setattr(host, "derive_proposal", lambda **kwargs: proposal())
    monkeypatch.setattr(host, "_loaded", lambda label: False)
    def validate(transaction):
        path, _ = host._candidate_paths(transaction.transaction_id)
        raw = path.read_bytes()
        return json.loads(raw), raw, owner.WORKER_CONFIG.read_bytes()
    monkeypatch.setattr(host, "_read_validated_control_candidate", validate)
    monkeypatch.setattr(host, "reconcile_control_service", lambda sha:
                        host._persist_phase(host._active_transaction, "CONTROL_RECONCILED"))
    monkeypatch.setattr(host, "prove_control_config_bound", lambda tx, **kwargs:
                        host._persist_phase(tx, "CONTROL_CONFIG_BOUND"))
    return host


@pytest.fixture
def installed(monkeypatch, tmp_path):
    root, marker = _inprocess_marker_host(monkeypatch, tmp_path)
    monkeypatch.setattr(canary, "RECEIPT_PATH", root / "dialogue-wake-canary-publication-v1.json")
    host = configure(canary.ProductionDialogueCanaryHost(), monkeypatch)
    before_control = owner.CONTROL_CONFIG.read_bytes()
    before_worker = owner.WORKER_CONFIG.read_bytes()
    return SimpleNamespace(host=host, root=root, marker=marker,
                           control=before_control, worker=before_worker)


def publish(host):
    p = proposal()
    return canary.execute_publication(
        host, expected_sha=SHA, read_ref=p.read_ref,
        validity_seconds=p.grant.expires_at_epoch_seconds - p.grant.valid_from_epoch_seconds,
    )


def test_real_global_owner_publication_changes_only_grant(installed):
    s = installed
    transaction_id = publish(s.host)
    after = json.loads(owner.CONTROL_CONFIG.read_bytes())
    grant = after.pop("dialogue_wake_canary_activation")
    assert after == json.loads(s.control)
    assert grant == proposal().grant.to_dict()
    assert owner.WORKER_CONFIG.read_bytes() == s.worker
    receipt, _ = canary._read_receipt()
    assert receipt.transaction_id == transaction_id
    profile = canary.load_verified_profile(
        control_sha256=owner.sha256_bytes(owner.CONTROL_CONFIG.read_bytes()),
        worker_sha256=owner.sha256_bytes(s.worker), release_sha=SHA,
        grant=proposal().grant,
    )
    assert profile.grant == proposal().grant
    assert not s.marker.exists() and s.host._transaction_owner_fd is None


@pytest.mark.parametrize("phase", [
    "write_candidates", "validate_candidates", "replace_control_config",
    "write_publication_receipt", "reconcile_control_service", "prove_control_config_bound",
])
def test_unknown_publication_recovers_exact_preimages_through_same_owner(
    installed, monkeypatch, phase,
):
    s = installed
    original = getattr(s.host, phase)
    def crash(*args, **kwargs):
        original(*args, **kwargs)
        raise owner.TransactionEffectUnknown()
    monkeypatch.setattr(s.host, phase, crash)
    with pytest.raises(owner.TransactionEffectUnknown):
        publish(s.host)
    manifest = s.host._manifest()
    assert manifest["operation"] == "DIALOGUE_WAKE_CANARY_PUBLISH"
    assert (s.marker / owner._CANARY_RECEIPT_ARCHIVE).is_file()
    assert owner.WORKER_CONFIG.read_bytes() == s.worker
    s.host._release_transaction_owner()  # simulate loss of the original process
    recovered = configure(canary.ProductionDialogueCanaryHost(), monkeypatch)
    assert recovered.recover_publication(SHA) == manifest["transaction_id"]
    assert owner.CONTROL_CONFIG.read_bytes() == s.control
    assert owner.WORKER_CONFIG.read_bytes() == s.worker
    assert not canary.RECEIPT_PATH.exists() and not s.marker.exists()


def test_known_failure_rolls_back_without_worker_effect(installed, monkeypatch):
    s = installed
    def refuse(transaction):
        raise RuntimeError("receipt refusal before write")
    monkeypatch.setattr(s.host, "write_publication_receipt", refuse)
    with pytest.raises(ValueError, match="rolled back"):
        publish(s.host)
    assert owner.CONTROL_CONFIG.read_bytes() == s.control
    assert owner.WORKER_CONFIG.read_bytes() == s.worker
    assert not s.marker.exists()


def test_unknown_third_control_postimage_is_never_overwritten(installed, monkeypatch):
    s = installed
    def crash(transaction):
        raise owner.TransactionEffectUnknown()
    monkeypatch.setattr(s.host, "write_candidates", crash)
    with pytest.raises(owner.TransactionEffectUnknown):
        publish(s.host)
    # A foreign root mutation is not ours to repair.
    value = json.loads(s.control)
    value["foreign_root_change"] = True
    foreign = owner.encode_config(value)
    owner._atomic_file(owner.CONTROL_CONFIG, foreign, mode=0o440,
                       uid=0, gid=0, replace=True)
    s.host._release_transaction_owner()
    recovered = configure(canary.ProductionDialogueCanaryHost(), monkeypatch)
    with pytest.raises(owner.TransactionEffectUnknown):
        recovered.recover_publication(SHA)
    assert s.marker.exists() and owner.CONTROL_CONFIG.read_bytes() == foreign


def test_global_disarm_refuses_canary_before_stopping_services(installed, monkeypatch):
    s = installed
    monkeypatch.setattr(s.host, "write_candidates", lambda tx: (_ for _ in ()).throw(
        owner.TransactionEffectUnknown()))
    with pytest.raises(owner.TransactionEffectUnknown):
        publish(s.host)
    s.host._release_transaction_owner()
    disarm = owner.ProductionTransactionHost()
    monkeypatch.setattr(disarm, "existing_disarm", lambda *a, **k: None)
    monkeypatch.setattr(disarm, "require_exact_install", lambda sha: sha)
    effects = []
    monkeypatch.setattr(disarm, "stop_services", lambda sha: effects.append("stop"))
    with pytest.raises(owner.TransactionEffectUnknown):
        owner.execute_disarm(disarm, SHA, now=NOW)
    assert effects == [] and s.marker.exists()


def test_disarm_claims_before_stop_and_retains_owner_after_stop_failure():
    host = FakeTransactionHost()
    host.existing_disarm = lambda *a, **k: None
    events = []
    begin = host.begin_disarm
    def claim(*args):
        value = begin(*args)
        events.append("claim")
        return value
    def stop(sha):
        assert host.marker
        events.append("stop")
        raise RuntimeError("stop result unknown")
    host.begin_disarm, host.stop_services = claim, stop
    with pytest.raises(owner.TransactionEffectUnknown):
        owner.execute_disarm(host, SHA, now=NOW)
    assert events == ["claim", "stop"] and host.marker


@pytest.mark.parametrize("field", ["control", "worker", "release"])
def test_profile_fails_closed_when_publication_no_longer_matches(installed, field):
    publish(installed.host)
    values = dict(
        control_sha256=owner.sha256_bytes(owner.CONTROL_CONFIG.read_bytes()),
        worker_sha256=owner.sha256_bytes(installed.worker), release_sha=SHA,
        grant=proposal().grant,
    )
    key = {"control": "control_sha256", "worker": "worker_sha256", "release": "release_sha"}[field]
    values[key] = "f" * (40 if field == "release" else 64)
    assert canary.load_verified_profile(**values).grant is None


def test_unexpired_grant_cannot_be_replaced(installed, monkeypatch):
    s = installed
    publish(s.host)
    control_before = owner.CONTROL_CONFIG.read_bytes()
    receipt_before = canary.RECEIPT_PATH.read_bytes()
    monkeypatch.setattr(s.host, "now_epoch_seconds", lambda: proposal().grant.valid_from_epoch_seconds + 1)
    with pytest.raises(ValueError, match="unexpired"):
        publish(s.host)
    assert owner.CONTROL_CONFIG.read_bytes() == control_before
    assert canary.RECEIPT_PATH.read_bytes() == receipt_before
    assert not s.marker.exists()


def test_expired_replacement_failure_restores_prior_receipt_exactly(installed, monkeypatch):
    s = installed
    publish(s.host)
    prior_control = owner.CONTROL_CONFIG.read_bytes()
    prior_receipt = canary.RECEIPT_PATH.read_bytes()
    original = proposal()
    start = original.grant.expires_at_epoch_seconds + 1
    replacement = dataclasses.replace(original, grant=dataclasses.replace(
        original.grant, valid_from_epoch_seconds=start, expires_at_epoch_seconds=start + 120))
    monkeypatch.setattr(s.host, "derive_proposal", lambda **kwargs: replacement)
    monkeypatch.setattr(s.host, "now_epoch_seconds", lambda: start)
    original_write = s.host.write_publication_receipt
    def crash(tx):
        original_write(tx)
        raise owner.TransactionEffectUnknown()
    monkeypatch.setattr(s.host, "write_publication_receipt", crash)
    with pytest.raises(owner.TransactionEffectUnknown):
        publish(s.host)
    assert s.host._manifest()["prior_canary_receipt_present"] is True
    s.host._release_transaction_owner()
    recovered = configure(canary.ProductionDialogueCanaryHost(), monkeypatch)
    recovered.recover_publication(SHA)
    assert owner.CONTROL_CONFIG.read_bytes() == prior_control
    assert canary.RECEIPT_PATH.read_bytes() == prior_receipt
    assert owner.WORKER_CONFIG.read_bytes() == s.worker
    assert not s.marker.exists()


@pytest.mark.parametrize("ttl,ref", [(0, "session-reply-" + "4"*64), (901, "session-reply-" + "4"*64), (60, "invalid")])
def test_cli_invalid_scope_refuses_before_config_or_effects(capsys, ttl, ref):
    class Host:
        def effective_uid(self): return 0
        def require_exact_install(self, sha): raise AssertionError("no host effects")
    rc = owner.main(["dialogue-canary-publish", "--expected-sha", SHA,
                     "--read-ref", ref, "--validity-seconds", str(ttl)], host=Host())
    assert rc == 2
    assert json.loads(capsys.readouterr().out)["code"] == "dialogue_canary_unverified"


def test_cli_routes_publication_and_recovery_through_global_owner(installed, capsys, monkeypatch):
    args = ["dialogue-canary-publish", "--expected-sha", SHA,
            "--read-ref", proposal().read_ref, "--validity-seconds", "600"]
    assert owner.main(args, host=installed.host) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["code"] == "dialogue_canary_published"
    called = []
    monkeypatch.setattr(installed.host, "recover_publication",
                        lambda sha: called.append(sha) or document["transaction_id"])
    assert owner.main(["dialogue-canary-reconcile", "--expected-sha", SHA], host=installed.host) == 0
    assert called == [SHA]
    assert json.loads(capsys.readouterr().out)["code"] == "dialogue_canary_preimages_restored"


@pytest.mark.parametrize("argv", [
    ["dialogue-canary-publish", "--expected-sha", SHA, "--validity-seconds", "60"],
    ["dialogue-canary-reconcile", "--expected-sha", SHA, "--read-ref", "session-reply-" + "4"*64],
])
def test_cli_closed_argument_sets(argv):
    with pytest.raises(SystemExit):
        owner._parser().parse_args(argv)
