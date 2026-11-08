"""Finite native receipt publication; real files/rename, virtual root and inert Node."""
import hashlib
import os
import stat

import pytest

from control_plane import native_provider_attestation as att
from integrations.deepseek_harness import package_attended as package
from ops.executive_os import capacity_host_artifacts
from test_native_deepseek_attestation import deepseek_installation


def inputs(i):
    return dict(receipt_path=i.receipt, binary_path=i.binary, release=i.release,
        source_repo=i.root, source_sha="a"*40, expected_owner_gid=os.getegid(),
        allowed_versions=frozenset({"v26.5.0"}))


def fresh(i):
    i.receipt.unlink()
    return inputs(i)


def test_root_publisher_feeds_original_reader_without_worker_or_provider_start(deepseek_installation):
    i = deepseek_installation
    args = fresh(i)
    before = list(i.calls)
    result = att.publish_native_deepseek_attestation(qualify_package=package.qualify_native_worker_package, **args)
    assert result["state"] == "PUBLISHED" and result["effect_state"] == "APPLIED"
    assert result["worker_observation"] == "NOT_OBSERVED"
    assert result["service_activated"] is False and result["provider_calls"] == 0
    assert i.calls == before + [[str(i.binary), "--version"]]
    info = i.receipt.lstat()
    assert (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), info.st_nlink) == (
        os.geteuid(), os.getegid(), 0o440, 1)
    installed = i.load()
    installed.require_current()
    assert installed.source_digest == result["receipt_sha256"] == hashlib.sha256(i.receipt.read_bytes()).hexdigest()
    before = list(i.calls)
    observed = att.reconcile_native_deepseek_attestation(**args,
        expected_receipt_sha256=result["receipt_sha256"])
    assert observed["state"] == "PRESENT_QUALIFIED" and observed["effect_state"] == "NONE"
    assert observed["receipt_identity"]["inode"] == info.st_ino
    assert i.calls == before
    assert not list(i.root.glob(".*.native-attestation.stage"))


@pytest.mark.parametrize("existing", ["receipt", "stage", "symlink"])
def test_prior_target_or_stage_refuses_before_build_without_overwrite(deepseek_installation, monkeypatch, existing):
    i = deepseek_installation
    args = inputs(i)
    _, stage = att._deepseek_publication_names(i.receipt, i.release)
    if existing != "receipt":
        i.receipt.unlink()
        if existing == "stage":
            stage.write_bytes(b"original pending bytes")
        else:
            i.receipt.symlink_to(i.payload)
    before = i.payload.read_bytes()
    monkeypatch.setattr(att, "build_native_deepseek_attestation",
        lambda **kw: pytest.fail("existing publication was rebuilt"))
    with pytest.raises(att.NativeAttestationError, match="reconciliation"):
        att.publish_native_deepseek_attestation(qualify_package=package.qualify_native_worker_package, **args)
    assert i.payload.read_bytes() == before
    if existing == "stage":
        assert stage.read_bytes() == b"original pending bytes"


def test_partial_private_write_stays_pending_and_is_not_replayed(deepseek_installation, monkeypatch):
    i = deepseek_installation
    args = fresh(i)
    original = att.os.write
    writes = []
    def fail_after_prefix(fd, raw):
        if not writes:
            writes.append(original(fd, raw[:19]))
            return writes[0]
        raise OSError("inert disk error")
    monkeypatch.setattr(att.os, "write", fail_after_prefix)
    with pytest.raises(att.NativeAttestationPublicationPending):
        att.publish_native_deepseek_attestation(qualify_package=package.qualify_native_worker_package, **args)
    assert not i.receipt.exists()
    _, stage = att._deepseek_publication_names(i.receipt, i.release)
    assert stage.stat().st_size == 19
    observed = att.reconcile_native_deepseek_attestation(**args)
    assert observed["state"] == "PENDING_PRIVATE"
    assert observed["stage_sha256"] == hashlib.sha256(stage.read_bytes()).hexdigest()
    before = stage.read_bytes(), stage.stat().st_ino
    with pytest.raises(att.NativeAttestationError, match="reconciliation"):
        att.publish_native_deepseek_attestation(qualify_package=package.qualify_native_worker_package, **args)
    assert (stage.read_bytes(), stage.stat().st_ino) == before


def test_lost_rename_return_reconciles_original_inode_without_republication(deepseek_installation, monkeypatch):
    i = deepseek_installation
    args = fresh(i)
    rename = capacity_host_artifacts._rename_exclusive
    calls = []
    def lost(*argv):
        calls.append(argv)
        rename(*argv)
        raise OSError("lost return after original rename")
    monkeypatch.setattr(capacity_host_artifacts, "_rename_exclusive", lost)
    with pytest.raises(att.NativeAttestationPublicationUnknown):
        att.publish_native_deepseek_attestation(qualify_package=package.qualify_native_worker_package, **args)
    before = i.receipt.read_bytes(), i.receipt.stat().st_ino, list(i.calls)
    observed = att.reconcile_native_deepseek_attestation(**args)
    assert observed["state"] == "PRESENT_QUALIFIED"
    assert len(calls) == 1
    assert (i.receipt.read_bytes(), i.receipt.stat().st_ino, i.calls) == before


def test_late_collision_never_overwrites_either_original_carrier(deepseek_installation, monkeypatch):
    i = deepseek_installation
    args = fresh(i)
    rename = capacity_host_artifacts._rename_exclusive
    def collide(*argv):
        i.receipt.write_bytes(b"foreign canonical occupant")
        rename(*argv)
    monkeypatch.setattr(capacity_host_artifacts, "_rename_exclusive", collide)
    with pytest.raises(att.NativeAttestationPublicationUnknown):
        att.publish_native_deepseek_attestation(qualify_package=package.qualify_native_worker_package, **args)
    _, stage = att._deepseek_publication_names(i.receipt, i.release)
    assert i.receipt.read_bytes() == b"foreign canonical occupant" and stage.exists()
    assert att.reconcile_native_deepseek_attestation(**args)["state"] == "COLLISION"


@pytest.mark.parametrize("change", ["package", "config", "source"])
def test_currentness_changes_after_staging_refuse_before_canonical_effect(deepseek_installation, monkeypatch, change):
    i = deepseek_installation
    args = fresh(i)
    _, stage = att._deepseek_publication_names(i.receipt, i.release)
    if change == "source":
        from ops.executive_os import install_source_policy
        monkeypatch.setattr(install_source_policy, "validate_acceptance_source",
            lambda **kw: "d"*40 if stage.exists() else "b"*40)
    def current():
        if stage.exists():
            if change == "config":
                raise ValueError("original config changed")
    if change == "package":
        original = att.load_native_deepseek_attestation
        def drift(*argv, **kw):
            i.payload.chmod(0o644)
            i.payload.write_bytes(b"changed after root qualification")
            i.payload.chmod(0o444)
            return original(*argv, **kw)
        monkeypatch.setattr(att, "load_native_deepseek_attestation", drift)
    with pytest.raises(att.NativeAttestationPublicationPending):
        att.publish_native_deepseek_attestation(qualify_package=package.qualify_native_worker_package, **args, current=current)
    assert stage.exists() and not i.receipt.exists()


def test_reconciliation_never_claims_other_bytes_or_stale_source(deepseek_installation, monkeypatch):
    i = deepseek_installation
    args = inputs(i)
    before = i.receipt.read_bytes(), list(i.calls)
    with pytest.raises(att.NativeAttestationError, match="expected bytes"):
        att.reconcile_native_deepseek_attestation(**args, expected_receipt_sha256="f"*64)
    from ops.executive_os import install_source_policy
    monkeypatch.setattr(install_source_policy, "validate_acceptance_source", lambda **kw: "d"*40)
    with pytest.raises(att.NativeAttestationError, match="source"):
        att.reconcile_native_deepseek_attestation(**args)
    assert (i.receipt.read_bytes(), i.calls) == before


def test_absent_original_target_is_read_only_not_published(deepseek_installation):
    i = deepseek_installation
    args = fresh(i)
    before = list(i.calls), sorted(p.name for p in i.root.iterdir())
    result = att.reconcile_native_deepseek_attestation(**args)
    assert result["state"] == "NOT_PUBLISHED" and result["effect_state"] == "NONE"
    assert (i.calls, sorted(p.name for p in i.root.iterdir())) == before


@pytest.fixture
def original_worker_publication(deepseek_installation, monkeypatch):
    import json
    from control_plane import codex_provider_realm as realm
    from integrations.deepseek_harness import package_attended as package
    from scripts import executive_os_phase1c_worker as worker
    from test_native_deepseek_worker_factory import config
    i = deepseek_installation
    value = config(i)
    value.update(worker_uid=os.geteuid(), worker_gid=os.getegid(),
                 worker_user="_mastermind_deepseek_original")
    value["native_realm_enrollment"] = dict(
        schema_version=realm.NATIVE_REALM_ENROLLMENT_SCHEMA,
        slot_id="deepseek-native-original", host_ref="host-"+"1"*64,
        os_principal_ref="principal-"+"2"*64, config_custody_ref="custody-"+"3"*64,
        generation=1, enrollment_state="enrolled",
        provider_binary_sha256=i.document["node"]["sha256"])
    path = i.root/"original-worker.json"
    path.write_text(json.dumps(value))
    path.chmod(0o440)
    monkeypatch.setattr(realm, "_native_open", att._native_open)
    original = worker._load_config
    def configured(path, *, require_root_owner):
        assert require_root_owner is True
        return original(path, require_root_owner=False)
    monkeypatch.setattr(worker, "_load_config", configured)
    args = dict(worker_config=path, worker_config_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                source_repo=i.root, source_sha="a"*40)
    return i, package, path, value, args


def test_packager_derives_all_coordinates_from_original_pinned_worker(original_worker_publication):
    i, package, path, value, args = original_worker_publication
    i.receipt.unlink()
    result = package.native_attestation_publication(**args)
    assert result["receipt_path"] == value["deepseek_attestation_receipt"]
    assert result["worker_gid"] == value["worker_gid"]
    assert result["worker_config_sha256"] == args["worker_config_sha256"]
    assert result["worker_identity_observation"] == result["account_eligibility"] == "NOT_OBSERVED"
    before = i.receipt.read_bytes(), path.read_bytes(), list(i.calls)
    observed = package.native_attestation_publication(**args, reconcile=True,
        expected_receipt_sha256=result["receipt_sha256"])
    assert observed["state"] == "PRESENT_QUALIFIED"
    assert (i.receipt.read_bytes(), path.read_bytes(), i.calls) == before


@pytest.mark.parametrize("change", ["pin", "enrollment", "binary", "foreign-provider"])
def test_packager_refuses_foreign_original_owner_before_any_publication(original_worker_publication, change):
    import json
    i, package, path, value, args = original_worker_publication
    i.receipt.unlink()
    if change == "pin":
        args["worker_config_sha256"] = "e"*64
    else:
        if change == "enrollment":
            value["native_realm_enrollment"]["enrollment_state"] = "unenrolled"
        elif change == "binary":
            value["native_realm_enrollment"]["provider_binary_sha256"] = "e"*64
        else:
            value["native_provider"] = "codex"
        path.chmod(0o600)
        path.write_text(json.dumps(value))
        path.chmod(0o440)
        args["worker_config_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    before = list(i.calls)
    with pytest.raises(ValueError):
        package.native_attestation_publication(**args)
    assert i.calls == before and not i.receipt.exists()
    assert not list(i.root.glob(".*.native-attestation.stage"))


@pytest.mark.parametrize("when", ["private", "canonical"])
def test_final_callback_cannot_replace_exact_receipt_before_success(deepseek_installation, when):
    i = deepseek_installation
    args = fresh(i)
    _, stage = att._deepseek_publication_names(i.receipt, i.release)
    changed = []
    def current():
        path = stage if when == "private" else i.receipt
        if path.exists() and not changed:
            raw = path.read_bytes()
            path.unlink()
            path.write_bytes(raw)
            os.chown(path, -1, os.getegid())
            path.chmod(0o440)
            changed.append(path.stat().st_ino)
    error = att.NativeAttestationPublicationPending if when == "private" else att.NativeAttestationPublicationUnknown
    with pytest.raises(error) as caught:
        att.publish_native_deepseek_attestation(qualify_package=package.qualify_native_worker_package, **args, current=current)
    assert changed
    assert caught.value.evidence["receipt_path"] == str(i.receipt)
    assert len(caught.value.evidence["receipt_sha256"]) == 64
    assert i.receipt.exists() is (when == "canonical")


def test_reconcile_final_callback_cannot_report_replaced_original_inode(deepseek_installation):
    i = deepseek_installation
    calls = []
    def current():
        calls.append(1)
        if len(calls) == 2:
            raw = i.receipt.read_bytes()
            i.receipt.unlink()
            i.receipt.write_bytes(raw)
            os.chown(i.receipt, -1, os.getegid())
            i.receipt.chmod(0o440)
    with pytest.raises(att.NativeAttestationError, match="changed"):
        att.reconcile_native_deepseek_attestation(**inputs(i), current=current)


def test_packager_does_not_lose_applied_effect_when_final_config_check_fails(original_worker_publication, monkeypatch):
    i, package, path, value, args = original_worker_publication
    i.receipt.unlink()
    original = att.publish_native_deepseek_attestation
    def published_then_moved(**kw):
        result = original(**kw)
        raw = path.read_bytes()
        path.unlink()
        path.write_bytes(raw)
        path.chmod(0o440)
        return result
    monkeypatch.setattr(att, "publish_native_deepseek_attestation", published_then_moved)
    with pytest.raises(att.NativeAttestationPublicationUnknown) as caught:
        package.native_attestation_publication(**args)
    assert i.receipt.exists()
    assert caught.value.evidence["receipt_sha256"] == hashlib.sha256(i.receipt.read_bytes()).hexdigest()
    assert caught.value.evidence["effect_state"] == "EFFECT_UNKNOWN"
