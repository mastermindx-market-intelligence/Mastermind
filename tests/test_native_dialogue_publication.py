"""Same root publication owner; installed host/transport remain fixture seams."""
import dataclasses
import json

import pytest

from control_plane.dialogue_wake_canary_publication import NativeDialogueCanaryPublication
from control_plane.executive_service import ExecutiveDialogueWakeBridge
from control_plane.dialogue_wake_canary_activation import DialogueWakeCanaryProfile
from control_plane.wake_ledger import WakeRetryPolicy
from ops.executive_os import autonomy_control as owner
from ops.executive_os import dialogue_wake_canary_control as canary
from tests.test_dialogue_wake_canary_control import installed, proposal, configure
from tests.test_executive_autonomy_control import SHA


def native_case(s, monkeypatch):
    control = json.loads(s.control)
    control.update(coo_operator_model_alias="coo.operator.native-return", coo_autonomy_armed=True,
        coo_operator_harness_armed=True, company_consultation={"armed":True,"native_return_armed":True})
    worker = json.loads(s.worker)
    worker["operator_harness_armed"] = True
    owner._atomic_file(owner.CONTROL_CONFIG, owner.encode_config(control), mode=0o440, uid=0, gid=0, replace=True)
    owner._atomic_file(owner.WORKER_CONFIG, owner.encode_config(worker), mode=0o440, uid=0, gid=0, replace=True)
    # Ambient full-arm receipt/launchd observation are fixed host fixtures;
    # publication's global marker, archives and file effects remain real.
    receipt={"fixture_full_arm":True}
    owner._atomic_file(owner.AUTONOMY_RECEIPT, owner._encoded_json(receipt), mode=0o444, uid=0, gid=0, replace=False)
    monkeypatch.setattr(owner,"load_receipt_file",lambda path:(receipt,object()))
    monkeypatch.setattr(owner,"coexistence_receipt_eligible",lambda *args,**kwargs:True)
    monkeypatch.setattr(owner.ProductionCeoSubmitHost,"_read_control_launchd_disabled_override",staticmethod(lambda:False))
    p = proposal()
    p = dataclasses.replace(p, grant=dataclasses.replace(p.grant, target_attempt_id=p.grant.source_attempt_id))
    from control_plane.dialogue_wake_canary_publication import canonical_digest
    from control_plane.dialogue_wake_canary_activation import IDENTITY_FIELDS
    p = dataclasses.replace(p, facts_sha256=canonical_digest({k:getattr(p.grant,k) for k in IDENTITY_FIELDS}))
    monkeypatch.setattr(s.host, "derive_proposal", lambda **kwargs:p)
    for method in ("write_candidates", "validate_candidates", "replace_control_config", "reconcile_control_service"):
        monkeypatch.setattr(s.host, method, lambda *a, _method=method, **k:pytest.fail("native publication called "+_method))
    return p, owner.CONTROL_CONFIG.read_bytes(), owner.WORKER_CONFIG.read_bytes()


def publish(s, p):
    return canary.execute_publication(s.host, expected_sha=SHA, read_ref=p.read_ref,
        validity_seconds=p.grant.expires_at_epoch_seconds-p.grant.valid_from_epoch_seconds, native_return=True)


def test_native_publication_retains_control_worker_bytes_inodes_and_service(installed, monkeypatch):
    s=installed
    p,control,worker=native_case(s,monkeypatch)
    inodes=(owner.CONTROL_CONFIG.stat().st_ino,owner.WORKER_CONFIG.stat().st_ino)
    transaction=publish(s,p)
    publication,_raw=canary._read_receipt()
    assert type(publication) is NativeDialogueCanaryPublication
    assert publication.receipt.transaction_id==transaction and publication.grant==p.grant
    assert owner.CONTROL_CONFIG.read_bytes()==control and owner.WORKER_CONFIG.read_bytes()==worker
    assert (owner.CONTROL_CONFIG.stat().st_ino,owner.WORKER_CONFIG.stat().st_ino)==inodes
    assert not s.marker.exists()
    # Root source/installed writer is a separate fixture boundary here.
    monkeypatch.setattr(canary,"require_native_publication_source",lambda runtime,value:None)
    loaded=canary.load_native_verified_profile(object(),control_sha256=owner.sha256_bytes(control),release_sha=SHA)
    assert loaded.grant==p.grant
    assert canary.load_native_verified_profile(object(),control_sha256="f"*64,release_sha=SHA).grant is None
    assert canary.load_verified_profile(control_sha256=owner.sha256_bytes(control),release_sha=SHA,grant=p.grant).grant is None


@pytest.mark.parametrize("phase",["write_publication_receipt","prove_control_config_bound"])
def test_native_unknown_recovers_same_receipt_without_control_restart(installed,monkeypatch,phase):
    s=installed
    p,control,worker=native_case(s,monkeypatch)
    inode=owner.CONTROL_CONFIG.stat().st_ino
    original=getattr(s.host,phase)
    def crash(*args,**kwargs):
        original(*args,**kwargs)
        raise owner.TransactionEffectUnknown()
    monkeypatch.setattr(s.host,phase,crash)
    with pytest.raises(owner.TransactionEffectUnknown):publish(s,p)
    manifest=s.host._manifest()
    assert manifest["operation"]=="DIALOGUE_WAKE_CANARY_PUBLISH"
    assert manifest["prior_control_sha256"]==manifest["target_control_sha256"]
    assert canary.load_native_verified_profile(object(),control_sha256=owner.sha256_bytes(control),release_sha=SHA).grant is None
    s.host._release_transaction_owner()
    recovered=configure(canary.ProductionDialogueCanaryHost(),monkeypatch)
    monkeypatch.setattr(recovered,"reconcile_control_service",lambda *args:pytest.fail("native recovery restarted Control"))
    recovered.recover_publication(SHA)
    assert owner.CONTROL_CONFIG.read_bytes()==control and owner.WORKER_CONFIG.read_bytes()==worker
    assert owner.CONTROL_CONFIG.stat().st_ino==inode
    assert not s.marker.exists() and not canary.RECEIPT_PATH.exists()


def test_native_receipt_cannot_replace_an_unexpired_publication(installed,monkeypatch):
    s=installed
    p,_control,_worker=native_case(s,monkeypatch)
    monkeypatch.setattr(s.host,"now_epoch_seconds",lambda:p.grant.valid_from_epoch_seconds)
    publish(s,p)
    before=canary.RECEIPT_PATH.read_bytes()
    with pytest.raises(ValueError,match="unexpired native"):publish(s,p)
    assert canary.RECEIPT_PATH.read_bytes()==before and not s.marker.exists()


def test_legacy_publisher_cannot_restart_a_selected_native_session(installed,monkeypatch):
    s=installed
    p,_control,_worker=native_case(s,monkeypatch)
    with pytest.raises(ValueError,match="explicit same-process"):
        canary.execute_publication(s.host,expected_sha=SHA,read_ref=p.read_ref,validity_seconds=120)
    assert not canary.RECEIPT_PATH.exists() and not s.marker.exists()


def test_native_publication_keeps_the_existing_full_arm_receipt_gate(installed,monkeypatch):
    s=installed
    p,control,worker=native_case(s,monkeypatch)
    monkeypatch.setattr(owner,"coexistence_receipt_eligible",lambda *args,**kwargs:False)
    with pytest.raises(owner.TransactionEffectUnknown):publish(s,p)
    assert owner.CONTROL_CONFIG.read_bytes()==control and owner.WORKER_CONFIG.read_bytes()==worker
    assert not canary.RECEIPT_PATH.exists()


def test_hot_profile_never_uses_a_cached_grant_after_revocation():
    from tests.test_dialogue_wake_canary_activation import parsed
    values=[DialogueWakeCanaryProfile(parsed())]
    bridge=ExecutiveDialogueWakeBridge(target_provider=None,retry_policy=WakeRetryPolicy(armed=False),
        carrier_factory=lambda **kwargs:None, canary_profile=DialogueWakeCanaryProfile(None),
        installed_release_sha="a"*40,canary_now_epoch_seconds=lambda:1,
        native_canary_profile_loader=lambda:values[0])
    assert bridge.canary_profile.grant is not None
    values[0]=DialogueWakeCanaryProfile(None)
    assert bridge.canary_profile.grant is None
    values[0]=object()
    assert bridge.canary_profile.grant is None
