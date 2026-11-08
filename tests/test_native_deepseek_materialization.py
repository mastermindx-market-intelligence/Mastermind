"""Real copy/promotion/reconciliation with inert OS identity and signed-image probes.

The original config/enrollment readers and filesystem effects are exercised.
Only root ownership, protected package qualification and system executable
inspection are virtual. No provider, Worker or service starts.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
import pytest

from integrations.deepseek_harness import package_attended as package
from integrations.deepseek_harness import native_materialization as material
from control_plane import native_provider_attestation as att
from test_native_deepseek_attestation import deepseek_installation
from test_native_deepseek_attestation_publication import original_worker_publication


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def artifacts(original_worker_publication, monkeypatch):
    i, _, config_path, original, args = original_worker_publication
    i.root.chmod(0o755)
    candidate = i.root/"operator package with spaces"
    node_input = i.root/"operator Node with spaces"
    i.release.rename(candidate)
    i.binary.rename(node_input)
    source = i.root/"protected source"
    source.mkdir(mode=0o755)
    config = {"schema": "mastermind.dsh_attended_package.v1", "donor_sha": package.PIN,
        "release": str(i.release), "node": str(i.binary), "node_sha256": digest(node_input),
        "state": None, "state_owner": "original-worker"}
    (candidate/"app.json").write_text(json.dumps(config))
    (candidate/"app.json").chmod(0o444)
    for path in (candidate, *(p for p in candidate.rglob("*") if p.is_dir() and not p.is_symlink())):
        path.chmod(0o755)
    manifest = candidate/"package-manifest.json"
    manifest.chmod(0o644)
    files = package.inventory(candidate)
    files.pop("package-manifest.json")
    manifest.write_text(json.dumps(dict(schema="mastermind.dsh_attended_package_closure.v1",
        donor_sha=package.PIN, files=files, installed=False), sort_keys=True))
    manifest.chmod(0o444)
    accepted = dict(schema="mastermind.dsh_attended_build.v1", donor_sha=package.PIN,
        package_manifest_sha256=digest(manifest), app_config_sha256=digest(candidate/"app.json"),
        installed=False, provider_calls=0)
    accepted_raw = json.dumps(accepted, sort_keys=True).encode()
    monkeypatch.setattr(package, "protected_build", lambda *a: (accepted_raw, accepted))
    qualifications = []
    def qualified(*, release, source_repo, source_sha, **kwargs):
        assert source_repo == source and source_sha == "a"*40
        assert release in (i.release, material._stage(i.release))
        is_stage = release == material._stage(i.release)
        assert kwargs == ({"_installation_root": i.release} if is_stage else {})
        assert digest(release/"package-manifest.json") == accepted["package_manifest_sha256"]
        qualifications.append((str(release), is_stage))
        return {**i.qualified,
            "schema": ("mastermind.dsh_native_worker_stage_qualification/v1" if is_stage
                       else "mastermind.dsh_native_worker_qualification/v1"),
            "package_manifest_sha256": accepted["package_manifest_sha256"]}
    monkeypatch.setattr(package, "qualify_native_worker_package", qualified)
    def sealed(path, *, mode=None, **kw):
        path = Path(path)
        info = path.lstat()
        assert path.is_dir() and not path.is_symlink() and info.st_uid == os.geteuid()
        assert not info.st_mode & 0o022
        if mode is not None:
            assert info.st_mode & 0o777 == mode
    monkeypatch.setattr(material.custody, "sealed_directory", sealed)
    monkeypatch.setattr(material.os, "fchown", lambda fd, uid, gid: None)
    monkeypatch.setattr(material.os, "chown", lambda *a, **kw: None)
    probes = []
    def inspect(argv, **kwargs):
        probes.append(list(argv))
        assert argv[0] in ("/usr/bin/otool", "/usr/bin/codesign"), "candidate runtime must not execute"
        if argv[0] == "/usr/bin/otool":
            return SimpleNamespace(stdout=str(argv[-1])+":\n\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0)\n")
        return SimpleNamespace(stdout=b"", stderr=b"")
    monkeypatch.setattr(material, "subprocess", SimpleNamespace(run=inspect, DEVNULL=att.subprocess.DEVNULL))
    inputs = {**args, "source_repo": source, "native_package": candidate,
              "native_node": node_input, "operator_uid": os.geteuid()}
    original_bytes = config_path.read_bytes(), i.receipt.read_bytes(), list(i.calls)
    return SimpleNamespace(i=i, candidate=candidate, node_input=node_input, source=source,
        inputs=inputs, accepted=accepted, original=original, config_path=config_path,
        qualifications=qualifications, probes=probes, original_bytes=original_bytes)


def reconcile(f):
    return material.native_materialization(**{k:v for k,v in f.inputs.items()
        if k not in ("native_package", "native_node", "operator_uid")}, reconcile=True)


def originals_unchanged(f):
    assert (f.config_path.read_bytes(), f.i.receipt.read_bytes(), f.i.calls) == f.original_bytes


def test_real_copy_publishes_same_parent_targets_and_reconciles_without_inputs(artifacts, monkeypatch):
    f = artifacts
    result = material.native_materialization(**f.inputs)
    assert result["state"] == "UNSELECTED_MATERIALIZED"
    assert [result["targets"][k]["effect_state"] for k in ("node", "package")] == ["APPLIED", "APPLIED"]
    assert f.i.binary.read_bytes() == f.node_input.read_bytes()
    assert f.i.binary.stat().st_mode & 0o777 == 0o555
    assert package.inventory(f.i.release) == package.inventory(f.candidate)
    assert os.readlink(f.i.release/"app/node_modules/pkg") == ".pnpm/pkg/node_modules/pkg"
    assert all(not result[k] for k in result if k.endswith("_changed"))
    assert result["worker_observation"] == result["account_eligibility"] == "NOT_OBSERVED"
    assert any(stage for _,stage in f.qualifications) and any(not stage for _,stage in f.qualifications)
    original_inodes = f.i.binary.stat().st_ino, f.i.release.stat().st_ino
    f.candidate.rename(f.candidate.with_name("moved external candidate"))
    f.node_input.rename(f.node_input.with_name("moved external Node"))
    monkeypatch.setattr(material, "_rename_exclusive", lambda *a: pytest.fail("reconciliation must not publish"))
    observed = reconcile(f)
    assert [observed["targets"][k]["state"] for k in ("node", "package")] == ["PRESENT_QUALIFIED"]*2
    assert all(row["effect_state"] == "NONE" for row in observed["targets"].values())
    assert original_inodes == (f.i.binary.stat().st_ino, f.i.release.stat().st_ino)
    originals_unchanged(f)


@pytest.mark.parametrize("key,canonical", [("node",False),("package",False),("node",True),("package",True)])
def test_original_private_stage_is_never_cleaned_or_replayed(artifacts, monkeypatch, key, canonical):
    f=artifacts
    target=f.i.binary if key=="node" else f.i.release
    stage=material._stage(target)
    stage.write_bytes(b"original partial preparation")
    if canonical:
        target.write_bytes(b"other original occupant")
    before=(stage.read_bytes(), target.read_bytes() if canonical else None)
    monkeypatch.setattr(material, "_copy_file", lambda *a: pytest.fail("unresolved stage replayed"))
    with pytest.raises(material.NativeMaterializationPending):
        material.native_materialization(**f.inputs)
    assert before==(stage.read_bytes(), target.read_bytes() if canonical else None)
    observed=reconcile(f)
    assert observed["targets"][key]["state"] == ("CONFLICTING_OCCUPANTS" if canonical else "PRIVATE_STAGE_PRESENT")
    originals_unchanged(f)


@pytest.mark.parametrize("which", ["node", "package"])
def test_lost_exclusive_rename_return_uses_original_postimage(artifacts, monkeypatch, which):
    f=artifacts
    rename=material._rename_exclusive
    calls=[]
    def lost(parent, old, target_parent, new):
        calls.append(new)
        rename(parent,old,target_parent,new)
        if new==(f.i.binary.name if which=="node" else f.i.release.name):
            raise OSError("lost original namespace return")
    monkeypatch.setattr(material,"_rename_exclusive",lost)
    with pytest.raises(material.NativeMaterializationUnknown) as caught:
        material.native_materialization(**f.inputs)
    row=caught.value.evidence["targets"][which]
    assert row["effect_state"]=="EFFECT_UNKNOWN"
    target=f.i.binary if which=="node" else f.i.release
    inode=target.stat().st_ino
    before=list(calls)
    observed=reconcile(f)
    assert observed["targets"][which]["state"]=="PRESENT_QUALIFIED"
    assert target.stat().st_ino==inode and calls==before
    originals_unchanged(f)


def test_late_destination_collision_is_not_overwritten(artifacts, monkeypatch):
    f=artifacts
    rename=material._rename_exclusive
    def collision(parent,old,target_parent,new):
        if new==f.i.release.name:
            f.i.release.mkdir()
            (f.i.release/"original.txt").write_text("concurrent original")
        return rename(parent,old,target_parent,new)
    monkeypatch.setattr(material,"_rename_exclusive",collision)
    with pytest.raises(material.NativeMaterializationUnknown):
        material.native_materialization(**f.inputs)
    assert (f.i.release/"original.txt").read_text()=="concurrent original"
    observed=reconcile(f)
    assert observed["targets"]["node"]["state"]=="PRESENT_QUALIFIED"
    assert observed["targets"]["package"]["state"]=="CONFLICTING_OCCUPANTS"
    originals_unchanged(f)


def test_node_success_and_package_copy_failure_retain_separate_known_effects(artifacts, monkeypatch):
    f=artifacts
    copy=material._copy_file
    payload=f.candidate/"app/node_modules/.pnpm/pkg/node_modules/pkg/index.js"
    payload_digest=digest(payload)
    def changed(source,target,before,expected):
        copy(source,target,before,expected)
        if expected==payload_digest:
            payload.chmod(0o644)
            payload.write_bytes(b"changed while source descriptor was held")
            payload.chmod(0o444)
    monkeypatch.setattr(material,"_copy_file",changed)
    with pytest.raises(material.NativeMaterializationPending) as caught:
        material.native_materialization(**f.inputs)
    effects=caught.value.evidence["targets"]
    assert effects["node"]["effect_state"]=="APPLIED"
    assert effects["package"]["effect_state"]=="NONE"
    assert not f.i.release.exists() and material._stage(f.i.release).is_dir()
    observed=reconcile(f)
    assert observed["targets"]["node"]["state"]=="PRESENT_QUALIFIED"
    assert observed["targets"]["package"]["state"]=="PRIVATE_STAGE_PRESENT"
    originals_unchanged(f)


@pytest.mark.parametrize("fault",["extra","hardlink","special","symlink-root"])
def test_untrusted_package_cannot_smuggle_objects_into_immutable_closure(artifacts, fault):
    f=artifacts
    if fault=="extra":
        (f.candidate/"unapproved.txt").write_text("foreign")
    elif fault=="hardlink":
        os.link(f.candidate/att.DSH_ENTRYPOINT,f.candidate/"foreign-hardlink")
    elif fault=="special":
        os.mkfifo(f.candidate/"foreign-fifo")
    else:
        moved=f.candidate.with_name("moved package")
        f.candidate.rename(moved)
        f.candidate.symlink_to(moved,target_is_directory=True)
    with pytest.raises((ValueError,OSError,material.NativeMaterializationPending)):
        material.native_materialization(**f.inputs)
    assert not f.i.release.exists()
    originals_unchanged(f)


def test_nested_stage_replacement_after_qualification_is_caught_before_rename(artifacts, monkeypatch):
    f=artifacts
    qualify=material._package
    def changed(path,*a,**kwargs):
        result=qualify(path,*a,**kwargs)
        if kwargs.get("stage"):
            entry=path/att.DSH_ENTRYPOINT
            data=entry.read_bytes()
            entry.unlink()
            entry.write_bytes(data)
            entry.chmod(0o444)
        return result
    monkeypatch.setattr(material,"_package",changed)
    with pytest.raises(material.NativeMaterializationPending):
        material.native_materialization(**f.inputs)
    assert f.i.binary.exists() and not f.i.release.exists()
    originals_unchanged(f)


def test_final_currentness_callback_cannot_replace_published_node(artifacts, monkeypatch):
    f=artifacts
    load=package._original_native_worker_input
    changed=False
    def inputs(*a):
        original,enrollment,slot,current=load(*a)
        def guarded():
            nonlocal changed
            current()
            if f.i.binary.exists() and f.i.release.exists() and not changed:
                changed=True
                data=f.i.binary.read_bytes()
                f.i.binary.unlink()
                f.i.binary.write_bytes(data)
                f.i.binary.chmod(0o555)
        return original,enrollment,slot,guarded
    monkeypatch.setattr(package,"_original_native_worker_input",inputs)
    with pytest.raises(material.NativeMaterializationUnknown):
        material.native_materialization(**f.inputs)
    originals_unchanged(f)


def test_node_enrollment_digest_and_manifest_are_not_caller_authority(artifacts):
    f=artifacts
    f.node_input.chmod(0o755)
    f.node_input.write_bytes(b"same named but unaccepted Node")
    with pytest.raises(ValueError,match="enrollment"):
        material.native_materialization(**f.inputs)
    assert not f.i.binary.exists() and not f.i.release.exists()
    assert not material._stage(f.i.binary).exists()
    originals_unchanged(f)


def test_reconciliation_refuses_replacement_inputs_and_performs_no_effect(artifacts):
    f=artifacts
    with pytest.raises(ValueError,match="replace"):
        material.native_materialization(**f.inputs,reconcile=True)
    observed=reconcile(f)
    assert all(row["state"]=="NOT_PUBLISHED" for row in observed["targets"].values())
    assert not f.i.binary.exists() and not f.i.release.exists()
    originals_unchanged(f)


def test_state_or_configuration_namespace_is_never_materialization_destination(artifacts):
    f=artifacts
    for key,path in [("deepseek_release",f.original["provider_home"]),
                     ("deepseek_node_binary",f.original["workspace_root"]),
                     ("deepseek_release",str(f.source)),
                     ("deepseek_release",str(f.config_path)),
                     ("deepseek_node_binary",f.original["deepseek_attestation_receipt"])]:
        value=dict(f.original,**{key:path})
        with pytest.raises(ValueError,match="overlap"):
            material._coordinates(value,f.config_path,f.source)
    originals_unchanged(f)


def test_stage_qualification_schema_is_not_an_installed_capability(deepseek_installation):
    i=deepseek_installation
    value=json.loads(json.dumps(i.document))
    value["qualification"]["schema"]="mastermind.dsh_native_worker_stage_qualification/v1"
    i.publish(value)
    with pytest.raises(att.NativeAttestationError):
        i.load()


def test_final_reconciliation_rechecks_nested_package_identity(artifacts, monkeypatch):
    f = artifacts
    material.native_materialization(**f.inputs)
    load = package._original_native_worker_input
    calls = 0
    def inputs(*args):
        original, enrollment, slot, current = load(*args)
        def guarded():
            nonlocal calls
            current()
            calls += 1
            if calls == 2:
                entry = f.i.release / att.DSH_ENTRYPOINT
                raw = entry.read_bytes()
                entry.unlink()
                entry.write_bytes(raw)
                entry.chmod(0o444)
        return original, enrollment, slot, guarded
    monkeypatch.setattr(package, "_original_native_worker_input", inputs)
    monkeypatch.setattr(material, "_rename_exclusive",
        lambda *args: pytest.fail("reconciliation cannot publish"))
    with pytest.raises(material.NativeMaterializationPending) as caught:
        reconcile(f)
    assert calls == 2
    assert all(row["effect_state"] == "NONE" for row in caught.value.evidence["targets"].values())
    originals_unchanged(f)


def test_node_stage_replacement_after_qualification_never_becomes_new_baseline(artifacts, monkeypatch):
    f = artifacts
    observe = material._node
    def replaced(path, *args):
        result = observe(path, *args)
        if path == material._stage(f.i.binary):
            raw = path.read_bytes()
            path.unlink()
            path.write_bytes(raw)
            path.chmod(0o555)
        return result
    monkeypatch.setattr(material, "_node", replaced)
    monkeypatch.setattr(material, "_rename_exclusive",
        lambda *args: pytest.fail("replaced Node must not be published"))
    with pytest.raises(material.NativeMaterializationPending):
        material.native_materialization(**f.inputs)
    assert not f.i.binary.exists() and not f.i.release.exists()
    assert material._stage(f.i.binary).exists()
    originals_unchanged(f)


def test_replaced_package_stage_receives_no_privileged_copy(artifacts, monkeypatch):
    f = artifacts
    stage = material._stage(f.i.release)
    displaced = stage.with_name("original private stage")
    opened = material.os.open
    replaced = False
    def race(path, flags, *args, **kwargs):
        nonlocal replaced
        if path == stage.name and flags & os.O_DIRECTORY and "dir_fd" in kwargs and not replaced:
            replaced = True
            stage.rename(displaced)
            stage.mkdir(mode=0o700)
        return opened(path, flags, *args, **kwargs)
    monkeypatch.setattr(material.os, "open", race)
    with pytest.raises(material.NativeMaterializationPending) as caught:
        material.native_materialization(**f.inputs)
    assert replaced and list(stage.iterdir()) == list(displaced.iterdir()) == []
    assert caught.value.evidence["targets"]["node"]["effect_state"] == "APPLIED"
    assert caught.value.evidence["targets"]["package"]["effect_state"] == "NONE"
    assert not f.i.release.exists()
    originals_unchanged(f)


def test_all_original_targets_and_private_stages_are_reserved_before_effects(artifacts):
    f = artifacts
    for value in (
        dict(f.original, deepseek_node_binary=str(material._stage(f.i.release))),
        dict(f.original, provider_home=str(material._stage(f.i.binary))),
        dict(f.original, workspace_root=str(material._stage(f.i.release))),
    ):
        with pytest.raises(ValueError, match="overlap"):
            material._coordinates(value, f.config_path, f.source)
    assert not f.i.binary.exists() and not f.i.release.exists()
    assert not material._stage(f.i.binary).exists()
    originals_unchanged(f)
