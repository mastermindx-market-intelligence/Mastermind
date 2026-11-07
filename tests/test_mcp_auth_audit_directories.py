"""Real absent-only directory effects within the existing gateway transaction.

Root/MCP identities are modeled by the incumbent disposable gateway fixture;
its files, descriptors, original marker, CAS targets and reconciliation are real.
No audit sink, live gateway, provider, service or installed path is opened.
"""
import copy
import json
import os
import stat

import pytest

from ops.executive_os import autonomy_control as control
from ops.executive_os import mcp_auth_audit_directories as audit
from tests.test_os_gateway_publication_owner import gateway, gateway_tmp_path
from tests.os_gateway_policy_mount_fixtures import add_existing_mounts


def original_targets(s):
    return tuple(path.read_bytes() if path.exists() else None for path in s.target_paths())


def directory_image(path):
    info = path.lstat()
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid,
            stat.S_IMODE(info.st_mode), sorted(child.name for child in path.iterdir()),
            info.st_mtime_ns, info.st_ctime_ns)


def test_dormant_content_policies_select_both_required_audit_leaves(gateway):
    add_existing_mounts(gateway)
    names = audit.required_names(gateway.mcp_bytes)
    assert names == ("content", "read", "steward", "submit", "workspace")
    observed = audit.observe(names)
    assert observed["leaves"]["content"] is observed["leaves"]["steward"] is None
    assert all(observed["leaves"][name] for name in ("read", "submit", "workspace"))


def test_publication_retains_both_audit_preimages_and_postimages_before_first_target(gateway, monkeypatch):
    from integrations.business_mcp_auth.audit import DurableAuthAuditSink
    s = gateway
    add_existing_mounts(s)
    monkeypatch.setattr(DurableAuthAuditSink, "open", lambda *a, **kw: pytest.fail("sink acquired"))
    old_log = audit.ROOT / "read" / "auth-audit.jsonl"
    old_log.write_bytes(b"existing original log bytes\n")
    old_log.chmod(0o600)
    existing = {name: directory_image(audit.ROOT / name) for name in ("read", "submit", "workspace")}
    before = original_targets(s)
    observed = []
    original_grant = s.host._publish_gateway_grant

    def first_target(transaction, preparation):
        manifest = s.host._manifest()
        assert manifest["phase"] == "AUDIT_DIRECTORY_READY"
        prior = manifest[control._MCP_AUDIT_BEFORE_FIELD]
        after = manifest[control._MCP_AUDIT_AFTER_FIELD]
        assert prior["leaves"]["content"] is prior["leaves"]["steward"] is None
        audit.validate_transition(prior, after)
        audit.verify(after)
        assert original_targets(s) == before
        for name in ("content", "steward"):
            image = directory_image(audit.ROOT / name)
            assert image[2:6] == (458, 458, 0o700, [])
            assert list(image[:2]) == after["leaves"][name]
        observed.append(copy.deepcopy(manifest))
        return original_grant(transaction, preparation)

    monkeypatch.setattr(s.host, "_publish_gateway_grant", first_target)
    result = s.publish()
    assert result.state == "PUBLISHED" and len(observed) == 1
    assert not control.AUTONOMY_TRANSACTION.exists()
    assert not (audit.ROOT / "coo").exists()
    assert old_log.read_bytes() == b"existing original log bytes\n"
    assert {name: directory_image(audit.ROOT / name) for name in existing} == existing


@pytest.mark.parametrize("damage", ["mode", "file", "symlink", "uid", "gid", "acl", "parent_mode"])
def test_unsafe_existing_custody_refuses_before_marker_or_directory_effect(gateway, monkeypatch, damage):
    s = gateway
    add_existing_mounts(s)
    bad = audit.ROOT / "steward"
    if damage == "file":
        bad.write_bytes(b"not a directory")
    elif damage == "symlink":
        bad.symlink_to(audit.ROOT / "read", target_is_directory=True)
    else:
        bad.mkdir(mode=0o755 if damage == "mode" else 0o700)
        bad.chmod(0o755 if damage == "mode" else 0o700)
    if damage == "parent_mode":
        audit.ROOT.chmod(0o777)
    elif damage in {"uid", "gid"}:
        original = os.fstat
        bad_ino = bad.lstat().st_ino
        def wrong(descriptor):
            info = original(descriptor)
            if info.st_ino == bad_ino:
                values = list(info)
                values[4 if damage == "uid" else 5] = 0
                return os.stat_result(values, {"st_atime_ns": info.st_atime_ns,
                    "st_mtime_ns": info.st_mtime_ns, "st_ctime_ns": info.st_ctime_ns})
            return info
        monkeypatch.setattr(os, "fstat", wrong)
    elif damage == "acl":
        original_acl = audit.has_macos_acl
        bad_ino = bad.lstat().st_ino
        def acl(path, **kwargs):
            info = kwargs.get("expected_identity")
            return bool(info and info.st_ino == bad_ino) or original_acl(path, **kwargs)
        monkeypatch.setattr(audit, "has_macos_acl", acl)
    before = original_targets(s)
    with pytest.raises(control.GatewayPublicationError) as exc:
        s.publish()
    assert exc.value.code == "gateway_audit_directory_invalid"
    assert not control.AUTONOMY_TRANSACTION.exists()
    assert not (audit.ROOT / "content").exists()
    assert original_targets(s) == before
    assert bad.exists() or bad.is_symlink()


def test_policy_id_collision_is_a_prepublication_refusal(gateway):
    s = gateway
    add_existing_mounts(s)
    value = json.loads(s.mcp_bytes)
    value["steward"]["content_policy"]["policy_id"] = value["policies"]["read"]["policy_id"]
    with pytest.raises(audit.AuditDirectoryError):
        audit.required_names(control._encoded_json(value))
    assert not (audit.ROOT / "content").exists()


def test_held_absence_cannot_adopt_an_outside_creation(gateway):
    add_existing_mounts(gateway)
    before = audit.observe(audit.required_names(gateway.mcp_bytes))
    (audit.ROOT / "content").mkdir(mode=0o700)
    identity = directory_image(audit.ROOT / "content")
    with pytest.raises(audit.AuditDirectoryError):
        audit.establish(before)
    assert directory_image(audit.ROOT / "content") == identity
    assert not (audit.ROOT / "steward").exists()


def test_observed_parent_replacement_refuses_before_any_leaf_creation(gateway):
    add_existing_mounts(gateway)
    before = audit.observe(audit.required_names(gateway.mcp_bytes))
    audit.ROOT.rename(audit.ROOT.with_name("retained-original-mcp-auth"))
    audit.ROOT.mkdir(mode=0o755)
    audit.ROOT.chmod(0o755)
    for name in ("read", "submit", "workspace"):
        (audit.ROOT / name).mkdir(mode=0o700)
    with pytest.raises(audit.AuditDirectoryError):
        audit.establish(before)
    assert not (audit.ROOT / "content").exists()


def test_partial_directory_effect_preserves_unknown_original_marker_and_never_replays(gateway, monkeypatch):
    s = gateway
    add_existing_mounts(s)
    before = original_targets(s)
    original_fsync = os.fsync
    injected = []
    def interrupted(fd):
        info = os.fstat(fd)
        content = audit.ROOT / "content"
        if content.exists() and info.st_ino == content.lstat().st_ino:
            injected.append(True)
            raise OSError("TESTDATA interrupted directory durability")
        return original_fsync(fd)
    monkeypatch.setattr(os, "fsync", interrupted)
    with pytest.raises(control.TransactionEffectUnknown):
        s.publish()
    assert injected == [True]
    manifest = s.host._manifest()
    assert manifest["phase"] == "LOCKED" and manifest[control._MCP_AUDIT_AFTER_FIELD] is None
    assert (audit.ROOT / "content").is_dir() and not (audit.ROOT / "steward").exists()
    assert original_targets(s) == before
    with pytest.raises(control.CeoSubmitAdmissionError) as exc:
        s.publish()
    assert exc.value.code == "ceo_submit_transaction_incomplete"
    s.host._release_transaction_owner()
    new_host = s.fresh_host(monkeypatch)
    try:
        with pytest.raises(control.TransactionEffectUnknown):
            s.reconcile(host=new_host, transaction_id=manifest["transaction_id"])
    finally:
        if new_host._transaction_owner_fd is not None:
            new_host._release_transaction_owner()
    assert not (audit.ROOT / "steward").exists() and original_targets(s) == before


def test_completed_publication_reconciliation_refuses_replaced_policy_directory(gateway, monkeypatch):
    s = gateway
    add_existing_mounts(s)
    def lose_closeout(*args):
        raise OSError("TESTDATA lost closeout")
    monkeypatch.setattr(s.host, "complete_transaction", lose_closeout)
    with pytest.raises(control.TransactionEffectUnknown):
        s.publish()
    manifest = s.host._manifest()
    assert manifest["phase"] == "GATEWAY_RECEIPT_REPLACED"
    original = audit.ROOT / "content"
    original.rename(audit.ROOT / "retained-original-content")
    original.mkdir(mode=0o700)
    receipt = control.OS_GATEWAY_RECEIPT.read_bytes()
    s.host._release_transaction_owner()
    new_host = s.fresh_host(monkeypatch)
    checked = []
    original_check = new_host._verify_mcp_auth_audit_directories
    def check_original(value):
        checked.append(value["transaction_id"])
        return original_check(value)
    monkeypatch.setattr(new_host, "_verify_mcp_auth_audit_directories", check_original)
    try:
        with pytest.raises(control.TransactionEffectUnknown):
            s.reconcile(host=new_host, transaction_id=manifest["transaction_id"])
        assert checked == [manifest["transaction_id"]]
        assert control.OS_GATEWAY_RECEIPT.read_bytes() == receipt
        assert control.AUTONOMY_TRANSACTION.exists()
    finally:
        if new_host._transaction_owner_fd is not None:
            new_host._release_transaction_owner()


def test_historical_marker_keeps_original_postimage_only_reconciliation(gateway, monkeypatch):
    s = gateway
    monkeypatch.setattr(s.host, "complete_transaction", lambda *a: (_ for _ in ()).throw(OSError("TESTDATA closeout")))
    with pytest.raises(control.TransactionEffectUnknown):
        s.publish()
    # Model the original historical marker shape, without relabeling it as a
    # new audit-preparation proof. Existing receipt/target bytes remain exact.
    path = control.AUTONOMY_TRANSACTION / "transaction.json"
    old = json.loads(path.read_bytes())
    for key in control._MCP_AUDIT_FIELDS:
        old.pop(key)
    path.chmod(0o600)
    path.write_bytes(control._encoded_json(old))
    path.chmod(0o400)
    receipt = control.OS_GATEWAY_RECEIPT.read_bytes()
    s.host._release_transaction_owner()
    new_host = s.fresh_host(monkeypatch)
    monkeypatch.setattr(audit, "establish", lambda *a: pytest.fail("historical recovery created audit directories"))
    try:
        assert s.reconcile(host=new_host, transaction_id=old["transaction_id"]) == old["transaction_id"]
        assert control.OS_GATEWAY_RECEIPT.read_bytes() == receipt
        assert not control.AUTONOMY_TRANSACTION.exists()
    finally:
        if new_host._transaction_owner_fd is not None:
            new_host._release_transaction_owner()


def test_helper_effect_requires_root_and_original_transaction_owner(gateway, monkeypatch):
    before = audit.observe(audit.required_names(gateway.mcp_bytes))
    monkeypatch.setattr(audit, "_effective_uid", lambda: 501)
    with pytest.raises(audit.AuditDirectoryError):
        audit.establish(before)
    with pytest.raises(control.TransactionEffectUnknown):
        gateway.host._establish_mcp_auth_audit_directories(None)


@pytest.mark.parametrize("change", [
    lambda d: d.update(root_identity=[True, 5]),
    lambda d: d["leaves"].update({"../foreign": None}),
    lambda d: d["leaves"].pop("read"),
    lambda d: d.update(extra=True),
])
def test_closed_retained_intent_refuses_foreign_or_untyped_directory_authority(gateway, change):
    before = audit.observe(audit.required_names(gateway.mcp_bytes))
    change(before)
    with pytest.raises(audit.AuditDirectoryError):
        audit.establish(before)
