"""First release-owner bootstrap is fixed-path, root-only and permanently disarmed."""
from __future__ import annotations

import dataclasses
import importlib.util
import json
import os
from pathlib import Path
import stat

import pytest

import ops.executive_os.release_owner_bootstrap as subject
from ops.executive_os import release_owner_publication_plan as publication
from tests import test_executive_release_owner_publication_plan as plan_fixture
from tests import test_executive_release_owner_resident_inputs as resident_fixture


def _v1_plan():
    return publication.compile_resident_publication_plan(
        **plan_fixture._resident_values()
    )


def _prepare_root(monkeypatch, tmp_path: Path) -> Path:
    root = tmp_path / "config"
    root.mkdir(mode=0o755)
    monkeypatch.setattr(subject, "_CONFIG_ROOT", root)
    monkeypatch.setattr(subject, "_KEY_PATH", root / "release-owner-seal.key")
    info = root.stat()
    monkeypatch.setattr(subject, "_ROOT_UID", info.st_uid)
    monkeypatch.setattr(subject, "_WHEEL_GID", info.st_gid)

    # Functional publication tests use a direct descriptor for their isolated
    # pytest root. Production _open_config_root walks and holds every component
    # of the fixed /Library/.../config ancestry; /private/tmp is intentionally
    # world-writable and would correctly fail that production gate.
    def open_test_root():
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(root, flags)
        return (fd,), os.fstat(fd)

    monkeypatch.setattr(subject, "_open_config_root", open_test_root)
    return root


def _destinations(root: Path):
    return (
        root / "release-owner-registration.json",
        root / "release-owner-staged-transitions.json",
        root / "release-owner-installed-evidence.json",
        root / "release-owner-seal.key",
    )


def test_bootstrap_publisher_module_exists():
    assert importlib.util.find_spec("ops.executive_os.release_owner_bootstrap") is not None


def test_bootstrap_public_api_has_no_path_or_arm_parameters():
    import inspect

    function = subject.publish_initial_resident_plan
    assert list(inspect.signature(function).parameters) == ["plan"]
    assert subject.__all__ == (
        "BootstrapError",
        "BootstrapReceipt",
        "publish_initial_resident_plan",
    )


def test_bootstrap_refuses_non_root_before_observing_plan(monkeypatch):
    monkeypatch.setattr(subject, "_ROOT_UID", 0)
    monkeypatch.setattr(subject.os, "geteuid", lambda: 501)
    with pytest.raises(subject.BootstrapError, match="^BOOTSTRAP_ROOT_REQUIRED$"):
        subject.publish_initial_resident_plan(object())


def test_bootstrap_accepts_only_current_absent_v1_plan_and_preserves_v2_migration_guard(monkeypatch, tmp_path):
    root = _prepare_root(monkeypatch, tmp_path)
    plan = _v1_plan()
    assert json.loads(plan.manifest_bytes)["context"]["resident_preimage"] == "ABSENT"
    assert json.loads(dict((Path(item.path).name, item.data) for item in plan.payloads)["release-owner-installed-evidence.json"])["schema"] == "mastermind.executive_release_owner_installed_evidence/v1"

    with pytest.raises(publication.PublicationPlanError, match="^BOOTSTRAP_OR_MIGRATION_REQUIRED$"):
        publication.compile_resident_publication_plan(
            **plan_fixture._resident_values(
                physical_evidence=resident_fixture._physical_evidence()
            )
        )

    changed = dataclasses.replace(plan, kind="staged")
    with pytest.raises(subject.BootstrapError, match="^BOOTSTRAP_PLAN_INVALID$"):
        subject.publish_initial_resident_plan(changed)
    assert list(root.iterdir()) == []


def test_bootstrap_creates_exact_disabled_resident_set_and_private_seal(monkeypatch, tmp_path):
    root = _prepare_root(monkeypatch, tmp_path)
    plan = _v1_plan()
    payloads = {Path(item.path).name: item.data for item in plan.payloads}

    receipt = subject.publish_initial_resident_plan(plan)

    registration, registry, evidence, key = _destinations(root)
    assert registration.read_bytes() == payloads[registration.name]
    assert registry.read_bytes() == payloads[registry.name]
    assert evidence.read_bytes() == payloads[evidence.name]
    assert len(key.read_bytes()) == 32
    assert len(set(key.read_bytes())) > 1
    for target in _destinations(root):
        info = target.lstat()
        assert stat.S_ISREG(info.st_mode)
        assert stat.S_IMODE(info.st_mode) == 0o400
        assert (info.st_uid, info.st_gid, info.st_nlink) == (
            subject._ROOT_UID,
            subject._WHEEL_GID,
            1,
        )
    assert json.loads(registration.read_bytes())["enabled"] is False
    assert json.loads(registry.read_bytes())["transitions"] == []
    assert json.loads(evidence.read_bytes())["production_disarming"] == {
        "schema": "mastermind.executive_release_disarming/v1",
        "commit_prepared_release_transition": False,
        "installer_arming": False,
        "worker_start": False,
    }
    assert receipt.schema == "mastermind.executive_release_owner_bootstrap_receipt/v1"
    assert receipt.action == "BOOTSTRAPPED_DISARMED"
    assert receipt.owner_installation_id == json.loads(registration.read_bytes())[
        "owner_installation_id"
    ]
    assert receipt.target_ref == json.loads(registration.read_bytes())["target_ref"]
    assert receipt.release_commit == json.loads(evidence.read_bytes())["release_commit"]
    assert receipt.manifest_sha256 == plan.manifest_sha256


def test_bootstrap_refuses_any_preexisting_destination_without_mutation(monkeypatch, tmp_path):
    root = _prepare_root(monkeypatch, tmp_path)
    registration = root / "release-owner-registration.json"
    registration.write_bytes(b"foreign")
    before = registration.read_bytes()

    with pytest.raises(subject.BootstrapError, match="^BOOTSTRAP_DESTINATION_OCCUPIED$"):
        subject.publish_initial_resident_plan(_v1_plan())

    assert registration.read_bytes() == before
    assert sorted(item.name for item in root.iterdir()) == [registration.name]


def test_bootstrap_refuses_symlink_config_root(monkeypatch, tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "config"
    link.symlink_to(real, target_is_directory=True)
    monkeypatch.setattr(subject, "_CONFIG_ROOT", link)
    monkeypatch.setattr(subject, "_KEY_PATH", link / "release-owner-seal.key")
    info = real.stat()
    monkeypatch.setattr(subject, "_ROOT_UID", info.st_uid)
    monkeypatch.setattr(subject, "_WHEEL_GID", info.st_gid)

    with pytest.raises(subject.BootstrapError, match="^BOOTSTRAP_ROOT_UNSAFE$"):
        subject.publish_initial_resident_plan(_v1_plan())
    assert list(real.iterdir()) == []


def test_bootstrap_preserves_residual_state_on_mid_publish_failure(
    monkeypatch, tmp_path
):
    root = _prepare_root(monkeypatch, tmp_path)
    real_publish = subject._rename_no_replace
    calls = 0

    def fail_second_publish(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected")
        return real_publish(*args, **kwargs)

    monkeypatch.setattr(subject, "_rename_no_replace", fail_second_publish)
    with pytest.raises(subject.BootstrapError, match="^BOOTSTRAP_EFFECT_UNKNOWN$"):
        subject.publish_initial_resident_plan(_v1_plan())

    names = {item.name for item in root.iterdir()}
    destination_names = {path.name for path in _destinations(root)}
    assert len(names) == 4
    assert len(names & destination_names) == 1
    assert sum(name.startswith(subject._TEMP_PREFIX) for name in names) == 3


def test_bootstrap_refuses_exact_replay_instead_of_rotating_secret(monkeypatch, tmp_path):
    root = _prepare_root(monkeypatch, tmp_path)
    subject.publish_initial_resident_plan(_v1_plan())
    before = {path.name: path.read_bytes() for path in _destinations(root)}

    with pytest.raises(subject.BootstrapError, match="^BOOTSTRAP_DESTINATION_OCCUPIED$"):
        subject.publish_initial_resident_plan(_v1_plan())

    assert {path.name: path.read_bytes() for path in _destinations(root)} == before


def test_bootstrap_refuses_forged_manifest_or_payload_before_host_mutation(monkeypatch, tmp_path):
    root = _prepare_root(monkeypatch, tmp_path)
    plan = _v1_plan()
    forged_manifest = dataclasses.replace(plan, manifest_sha256="0" * 64)
    with pytest.raises(subject.BootstrapError, match="^BOOTSTRAP_PLAN_INVALID$"):
        subject.publish_initial_resident_plan(forged_manifest)

    payloads = list(plan.payloads)
    payloads[0] = dataclasses.replace(payloads[0], data=payloads[0].data + b" ")
    forged_payload = dataclasses.replace(plan, payloads=tuple(payloads))
    with pytest.raises(subject.BootstrapError, match="^BOOTSTRAP_PLAN_INVALID$"):
        subject.publish_initial_resident_plan(forged_payload)
    assert list(root.iterdir()) == []


def test_bootstrap_refuses_exact_preimage_plan_as_first_publication(monkeypatch, tmp_path):
    root = _prepare_root(monkeypatch, tmp_path)
    first = _v1_plan()
    values = {Path(item.path).name: item.data for item in first.payloads}
    exact = publication.compile_resident_publication_plan(
        **plan_fixture._resident_values(
            existing_registration_bytes=values["release-owner-registration.json"],
            existing_registry_bytes=values["release-owner-staged-transitions.json"],
            existing_installed_evidence_bytes=values["release-owner-installed-evidence.json"],
        )
    )
    assert json.loads(exact.manifest_bytes)["context"]["resident_preimage"] == "EXACT"
    with pytest.raises(subject.BootstrapError, match="^BOOTSTRAP_PLAN_INVALID$"):
        subject.publish_initial_resident_plan(exact)
    assert list(root.iterdir()) == []


def test_bootstrap_refuses_orphan_temp_as_unknown_prior_effect(monkeypatch, tmp_path):
    root = _prepare_root(monkeypatch, tmp_path)
    orphan = root / ".release-owner-bootstrap.interrupted.release-owner-seal.key.tmp"
    orphan.write_bytes(b"unresolved")
    before = orphan.read_bytes()
    with pytest.raises(subject.BootstrapError, match="^BOOTSTRAP_EFFECT_UNKNOWN$"):
        subject.publish_initial_resident_plan(_v1_plan())
    assert orphan.read_bytes() == before
    assert [item.name for item in root.iterdir()] == [orphan.name]


def test_bootstrap_preserves_all_finals_if_readback_fails(monkeypatch, tmp_path):
    root = _prepare_root(monkeypatch, tmp_path)
    real_readback = subject._readback
    real_unlink = subject.os.unlink
    calls = 0
    failure_seen = False
    post_failure_unlinks = []

    def fail_second_readback(*args, **kwargs):
        nonlocal calls, failure_seen
        calls += 1
        if calls == 2:
            failure_seen = True
            raise OSError("injected")
        return real_readback(*args, **kwargs)

    def record_unlink(*args, **kwargs):
        if failure_seen:
            post_failure_unlinks.append(args[0] if args else None)
        return real_unlink(*args, **kwargs)

    monkeypatch.setattr(subject, "_readback", fail_second_readback)
    monkeypatch.setattr(subject.os, "unlink", record_unlink)
    with pytest.raises(subject.BootstrapError, match="^BOOTSTRAP_EFFECT_UNKNOWN$"):
        subject.publish_initial_resident_plan(_v1_plan())
    assert post_failure_unlinks == []
    assert {item.name for item in root.iterdir()} == {
        path.name for path in _destinations(root)
    }


def test_bootstrap_refuses_canonical_v1_evidence_with_extra_field_even_when_plan_hashes_are_rebuilt(monkeypatch, tmp_path):
    root = _prepare_root(monkeypatch, tmp_path)
    plan = _v1_plan()
    payloads = list(plan.payloads)
    files = list(plan.files)
    index = next(i for i, item in enumerate(payloads) if Path(item.path).name == "release-owner-installed-evidence.json")
    evidence = json.loads(payloads[index].data)
    evidence["unexpected"] = "inert-but-unreviewed"
    from ops.executive_os.release_owner_resident_inputs import canonical_file_bytes
    forged_data = canonical_file_bytes(evidence)
    payloads[index] = dataclasses.replace(payloads[index], data=forged_data)
    import hashlib
    files[index] = dataclasses.replace(
        files[index], length=len(forged_data), sha256=hashlib.sha256(forged_data).hexdigest()
    )
    manifest = json.loads(plan.manifest_bytes)
    manifest["files"][index]["length"] = len(forged_data)
    manifest["files"][index]["sha256"] = hashlib.sha256(forged_data).hexdigest()
    manifest_bytes = canonical_file_bytes(manifest)
    forged = dataclasses.replace(
        plan,
        files=tuple(files),
        payloads=tuple(payloads),
        manifest_bytes=manifest_bytes,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
    )
    with pytest.raises(subject.BootstrapError, match="^BOOTSTRAP_PLAN_INVALID$"):
        subject.publish_initial_resident_plan(forged)
    assert list(root.iterdir()) == []


def test_production_directory_trust_refuses_extended_acl(monkeypatch, tmp_path):
    root = tmp_path / "root"
    root.mkdir(mode=0o755)
    info = root.stat()
    fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    monkeypatch.setattr(subject, "_ROOT_UID", info.st_uid)
    monkeypatch.setattr(subject, "_WHEEL_GID", info.st_gid)
    monkeypatch.setattr(subject, "_has_acl", lambda descriptor, observed: True)
    try:
        with pytest.raises(subject.BootstrapError, match="^BOOTSTRAP_ROOT_UNSAFE$"):
            subject._trust_directory(info, fd, final=True)
    finally:
        os.close(fd)


def test_bootstrap_refuses_inherited_acl_on_created_file(monkeypatch, tmp_path):
    root = _prepare_root(monkeypatch, tmp_path)
    real_acl = subject._has_acl

    def acl_only_on_files(descriptor, info):
        if stat.S_ISREG(info.st_mode):
            return True
        return real_acl(descriptor, info)

    monkeypatch.setattr(subject, "_has_acl", acl_only_on_files)
    with pytest.raises(subject.BootstrapError, match="^BOOTSTRAP_EFFECT_UNKNOWN$"):
        subject.publish_initial_resident_plan(_v1_plan())
    preserved = list(root.glob(".release-owner-bootstrap.*.tmp"))
    assert len(preserved) == 1


def test_bootstrap_close_failure_after_create_preserves_temp_and_reports_unknown(monkeypatch, tmp_path):
    root = _prepare_root(monkeypatch, tmp_path)
    real_close = subject.os.close
    injected = False

    def close_regular_then_fail(fd):
        nonlocal injected
        if not injected:
            info = os.fstat(fd)
            if stat.S_ISREG(info.st_mode):
                injected = True
                real_close(fd)
                raise OSError("injected close failure")
        return real_close(fd)

    monkeypatch.setattr(subject.os, "close", close_regular_then_fail)
    with pytest.raises(subject.BootstrapError, match="^BOOTSTRAP_EFFECT_UNKNOWN$"):
        subject.publish_initial_resident_plan(_v1_plan())
    assert injected is True
    preserved = list(root.glob(".release-owner-bootstrap.*.tmp"))
    assert len(preserved) == 1


def test_bootstrap_preserves_substituted_final_and_reports_unknown(monkeypatch, tmp_path):
    root = _prepare_root(monkeypatch, tmp_path)
    real_readback = subject._readback
    calls = 0
    foreign = b"foreign-root-maintenance-secret"

    def substitute_then_fail(directory_fd, directory, entry, expected):
        nonlocal calls
        calls += 1
        if calls == 2:
            victim = root / "release-owner-registration.json"
            victim.unlink()
            victim.write_bytes(foreign)
            victim.chmod(0o400)
            raise OSError("injected after foreign substitution")
        return real_readback(directory_fd, directory, entry, expected)

    monkeypatch.setattr(subject, "_readback", substitute_then_fail)
    with pytest.raises(subject.BootstrapError, match="^BOOTSTRAP_EFFECT_UNKNOWN$"):
        subject.publish_initial_resident_plan(_v1_plan())
    assert (root / "release-owner-registration.json").read_bytes() == foreign


def test_bootstrap_preserves_substituted_temp_and_reports_unknown(monkeypatch, tmp_path):
    root = _prepare_root(monkeypatch, tmp_path)
    real_fsync = subject.os.fsync
    substituted = False
    foreign = b"foreign-temporary"

    def replace_temp_before_failed_fsync(fd):
        nonlocal substituted
        if not substituted:
            temps = list(root.glob(".release-owner-bootstrap.*.tmp"))
            if temps:
                victim = temps[0]
                victim.unlink()
                victim.write_bytes(foreign)
                substituted = True
                raise OSError("injected after temp substitution")
        return real_fsync(fd)

    monkeypatch.setattr(subject.os, "fsync", replace_temp_before_failed_fsync)
    with pytest.raises(subject.BootstrapError, match="^BOOTSTRAP_EFFECT_UNKNOWN$"):
        subject.publish_initial_resident_plan(_v1_plan())
    preserved = list(root.glob(".release-owner-bootstrap.*.tmp"))
    assert len(preserved) == 1
    assert preserved[0].read_bytes() == foreign
