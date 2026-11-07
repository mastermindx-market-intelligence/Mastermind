"""Existing native publisher CAS, uncertainty, rollback and selected-code join.

Only disposable local installations and synthetic public routing data are used.
No provider, account, token, service or real generation is changed by these cases.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest

from ops.native_fabric.quota_continuity import policy_change, policy_publication as operator
from ops.native_fabric.quota_continuity.candidate import support_bundle as owner
from ops.native_fabric.quota_continuity.rollout import native_generation as generation
from ops.native_fabric.quota_continuity.source import fabric_policy_snapshot


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def document():
    return {"routing": {"execute_order": ["glm", "grok"], "grok_expiring_priority": {"enabled": False}},
            "pools": {"glm": {"models": {"executor": "qualified-model-a"}},
                      "grok": {"windows": {"weekly": {"limit": 100, "remaining_pct": 70}}}}}


def write(path, data, mode=0o600):
    path.write_bytes(data)
    path.chmod(mode)
    return path


@pytest.fixture
def installation(tmp_path):
    directory = (tmp_path / "owned_installation").resolve()
    directory.mkdir(mode=0o700)
    ext = directory / "ext"
    ext.mkdir(mode=0o700)
    active = ext / "active"
    active.mkdir(mode=0o700)
    lock = write(active / ".admission.lock", b"")
    parent = directory / "orch/fabric"
    parent.mkdir(parents=True, mode=0o700)
    (directory / "orch").chmod(0o700)
    baseline = document()
    changed = copy.deepcopy(baseline)
    changed["pools"]["grok"]["windows"]["weekly"]["remaining_pct"] = 35
    target = write(parent / "pools.yaml", raw(baseline))
    artifacts = directory / "operator_artifacts"
    artifacts.mkdir(mode=0o700)
    rollback = write(artifacts / "before.yaml", raw(baseline))
    candidate = write(artifacts / "candidate.yaml", raw(changed))
    return SimpleNamespace(directory=directory, ext=ext, active=active, lock=lock, target=target,
                           artifacts=artifacts, rollback=rollback, candidate=candidate,
                           before=raw(baseline), after=raw(changed))


def publish(value, **overrides):
    arguments = dict(expected_current_hash=digest(value.before), rollback_source=value.rollback)
    arguments.update(overrides)
    return owner.ensure_policy(value.candidate, value.ext, digest(value.after), **arguments)


def observe(value):
    return owner.policy_publication_status(value.ext, expected_current_hash=digest(value.before),
                                          expected_hash=digest(value.after))


def test_publication_uses_existing_target_lock_and_durable_receipt(installation):
    value = installation
    lock_inode = value.lock.stat().st_ino
    result = publish(value)
    assert result["state"] == "POLICY_PUBLISHED"
    assert result["directory_synced"] is True and result["writes_applied"] is True
    assert value.target.read_bytes() == value.after
    assert value.rollback.read_bytes() == value.before
    assert value.lock.stat().st_ino == lock_inode
    assert stat.S_IMODE(value.target.stat().st_mode) == 0o600
    assert sorted(p.name for p in value.target.parent.iterdir()) == ["pools.yaml"]
    for flag in ("model_activation_authorized", "generation_selected", "original_operations_rebound",
                 "credential_resolution_performed", "retry_authorized"):
        assert result[flag] is False
    assert result["account_configuration"] == "NOT_READ"
    readback = observe(value)
    assert readback["state"] == "CANDIDATE_BYTES_OBSERVED"
    assert readback["original_publication_proven"] is False
    assert readback["writes_applied"] is False


def test_rollback_is_same_owner_cas_in_reverse_not_pointer_rewind(installation):
    value = installation
    publish(value)
    result = owner.ensure_policy(value.rollback, value.ext, digest(value.before),
                                expected_current_hash=digest(value.after), rollback_source=value.candidate)
    assert result["state"] == "POLICY_PUBLISHED"
    assert value.target.read_bytes() == value.before
    assert value.candidate.read_bytes() == value.after
    assert result["generation_selected"] is False


def test_stale_expected_current_refuses_under_original_lock(installation):
    value = installation
    value.target.write_bytes(value.before + b"\n")
    with pytest.raises(owner.PolicyPublicationRefused, match="POLICY_EXPECTED_CURRENT_CHANGED"):
        publish(value)
    assert value.target.read_bytes() == value.before + b"\n"
    assert sorted(p.name for p in value.target.parent.iterdir()) == ["pools.yaml"]


def test_noop_has_no_write_or_activation(installation):
    value = installation
    value.candidate.write_bytes(value.before)
    before_inode = value.target.stat().st_ino
    result = owner.ensure_policy(value.candidate, value.ext, digest(value.before),
                                expected_current_hash=digest(value.before), rollback_source=value.rollback)
    assert result["state"] == "UNCHANGED" and result["writes_applied"] is False
    assert value.target.stat().st_ino == before_inode


@pytest.mark.parametrize("mutation", ["model", "pool", "quota_limit"])
def test_critical_change_cannot_silently_invalidate_native_snapshots(installation, mutation):
    value = installation
    proposed = document()
    if mutation == "model":
        proposed["pools"]["glm"]["models"]["executor"] = "different-model"
    elif mutation == "pool":
        proposed["pools"]["new-pool"] = {"enabled": False}
    else:
        proposed["pools"]["grok"]["windows"]["weekly"]["limit"] = 101
    value.after = raw(proposed)
    value.candidate.write_bytes(value.after)
    with pytest.raises(owner.PolicyPublicationRefused, match="CRITICAL_CHANGE_REQUIRES_NATIVE_GENERATION"):
        publish(value)
    assert value.target.read_bytes() == value.before


@pytest.mark.parametrize("entry", ["active-original", ".unrecognized-sidecar", ".original.preexec-settlement.json"])
def test_active_or_unknown_metadata_refuses_without_reaping(installation, entry):
    value = installation
    marker = write(value.active / entry, b"not-a-qualified-terminal-receipt")
    with pytest.raises(owner.PolicyPublicationRefused, match="POLICY_ACTIVE_BINDINGS_NOT_CLOSED"):
        publish(value)
    assert marker.read_bytes() == b"not-a-qualified-terminal-receipt"
    assert value.target.read_bytes() == value.before


def test_reconciler_observation_does_not_require_or_clear_idle_state(installation):
    value = installation
    marker = write(value.active / "existing-run", b"retained")
    assert observe(value)["state"] == "PREVIOUS_BYTES_OBSERVED"
    assert marker.read_bytes() == b"retained"


def test_lock_busy_never_creates_second_lock_or_rebinds(installation, monkeypatch):
    value = installation
    with value.lock.open("r+b") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        monkeypatch.setattr(owner, "_acquire_policy_lock", lambda descriptor: fcntl.flock(
            descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB))
        with pytest.raises(owner.PolicyPublicationRefused, match="POLICY_PUBLICATION_PREFLIGHT_REFUSED"):
            publish(value)
    assert value.target.read_bytes() == value.before


@pytest.mark.parametrize("operand", ["candidate", "rollback", "target", "lock"])
def test_symlink_final_operand_refuses(installation, operand):
    value = installation
    selected = getattr(value, operand)
    saved = selected.with_name(selected.name + ".saved")
    selected.rename(saved)
    selected.symlink_to(saved)
    with pytest.raises(owner.PolicyPublicationRefused):
        publish(value)
    assert value.target.read_bytes() == value.before


def test_rollback_cannot_be_the_live_inode(installation):
    with pytest.raises(owner.PolicyPublicationRefused, match="POLICY_RETAINED_ARTIFACT_REQUIRED"):
        publish(installation, rollback_source=installation.target)


def test_installer_lock_must_already_exist(installation):
    value = installation
    value.lock.unlink()
    with pytest.raises(owner.PolicyPublicationRefused):
        publish(value)
    assert not value.lock.exists()
    assert value.target.read_bytes() == value.before


@pytest.mark.parametrize("mode", [0o666, 0o664])
def test_writable_foreign_policy_is_refused(installation, mode):
    installation.target.chmod(mode)
    with pytest.raises(owner.PolicyPublicationRefused, match="POLICY_FILE_INVALID"):
        publish(installation)


def test_candidate_changed_before_commit_refuses(installation, monkeypatch):
    value = installation
    original = owner._policy_idle
    count = 0
    def drift(handles):
        nonlocal count
        count += 1
        original(handles)
        if count == 2:
            value.candidate.write_bytes(value.after + b"\n")
    monkeypatch.setattr(owner, "_policy_idle", drift)
    with pytest.raises(owner.PolicyPublicationRefused, match="POLICY_PREIMAGE_CHANGED"):
        publish(value)
    assert value.target.read_bytes() == value.before
    assert sorted(p.name for p in value.target.parent.iterdir()) == ["pools.yaml"]


def test_lost_replace_ack_retains_original_new_target_no_replay(installation, monkeypatch):
    value = installation
    actual = os.replace
    calls = []
    def lost(*args, **kwargs):
        calls.append(args)
        actual(*args, **kwargs)
        raise OSError("PRIVATE_REPLACE_DIAGNOSTIC")
    monkeypatch.setattr(owner.os, "replace", lost)
    with pytest.raises(owner.PolicyPublicationUnknown) as raised:
        publish(value)
    assert str(raised.value) == "POLICY_PUBLICATION_UNCERTAIN"
    assert raised.value.candidate_sha256 == digest(value.after)
    assert value.target.read_bytes() == value.after
    assert value.rollback.read_bytes() == value.before
    result = observe(value)
    assert result["state"] == "CANDIDATE_BYTES_OBSERVED"
    assert result["original_publication_proven"] is False and len(calls) == 1


def test_directory_sync_failure_is_unknown_not_success(installation, monkeypatch):
    value = installation
    actual = os.fsync
    target_parent = value.target.parent.stat()
    def failing(descriptor):
        info = os.fstat(descriptor)
        if stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino) == (target_parent.st_dev, target_parent.st_ino):
            raise OSError("PRIVATE_DIRECTORY_DIAGNOSTIC")
        actual(descriptor)
    monkeypatch.setattr(owner.os, "fsync", failing)
    with pytest.raises(owner.PolicyPublicationUnknown):
        publish(value)
    assert value.target.read_bytes() == value.after
    assert value.rollback.read_bytes() == value.before


def test_unknown_target_hash_is_not_exposed(installation):
    value = installation
    unexpected = b"Bearer unrelated-private-input"
    value.target.write_bytes(unexpected)
    result = observe(value)
    assert result["state"] == "OTHER_POLICY_OBSERVED"
    assert result["observed_policy_sha256"] is None
    assert digest(unexpected) not in json.dumps(result)
    assert result["original_publication_proven"] is False


@pytest.mark.parametrize("payload", [b"x: &x [*x]", b'{"pools":{},"pools":{}}', b"[]", b'"\\ud800"'])
def test_publication_validates_public_policy_before_replace(installation, payload):
    value = installation
    value.after = payload
    value.candidate.write_bytes(payload)
    with pytest.raises(owner.PolicyPublicationRefused):
        publish(value)
    assert value.target.read_bytes() == value.before


def test_even_noncritical_source_field_cannot_carry_a_secret(installation):
    value = installation
    proposed = document()
    proposed["pools"]["grok"]["windows"]["weekly"]["source"] = "Bearer PRIVATE_CANARY"
    value.after = raw(proposed)
    value.candidate.write_bytes(value.after)
    with pytest.raises(owner.PolicyPublicationRefused, match="POLICY_CREDENTIAL_MATERIAL_REFUSED"):
        publish(value)
    assert value.target.read_bytes() == value.before


def selected_generation(value, *, old_owner=False):
    staging = value.directory / "source_stage"
    (staging / "ext").mkdir(parents=True, mode=0o700)
    source = Path(owner.__file__).read_bytes()
    if old_owner:
        source = source.replace(b"NATIVE_POLICY_PUBLICATION_API = 1", b"NATIVE_POLICY_PUBLICATION_API = 0")
    files = {"pool": b"#!/bin/bash\nexit 0\n", "ext/fabric_task.py": b"# inert fixture\n",
             "ext/remote_sub.sh": b"#!/bin/bash\nexit 0\n", "ext/support_bundle.py": source,
             "ext/fabric_policy_snapshot.py": Path(fabric_policy_snapshot.__file__).read_bytes()}
    for name, content in files.items():
        write(staging / name, content)
    release = generation.publish(staging, value.ext, {name: digest(content) for name, content in files.items()})
    store = generation.store_path(value.ext)
    generation.select(store, release.name, None)
    return store, release.name


def test_operator_uses_real_selected_publisher_and_observes_same_target(installation):
    value = installation
    _store, selected = selected_generation(value)
    result = operator.publish_or_observe(stable_ext=value.ext, expected_generation=selected,
        previous=digest(value.before), candidate=digest(value.after),
        candidate_path=value.candidate, rollback_source=value.rollback)
    assert result["state"] == "POLICY_PUBLISHED", result
    assert result["native_generation"] == selected
    assert result["publisher_source_sha256"] == digest(Path(owner.__file__).read_bytes())
    status = operator.publish_or_observe(stable_ext=value.ext, expected_generation=selected,
        previous=digest(value.before), candidate=digest(value.after))
    assert status["state"] == "CANDIDATE_BYTES_OBSERVED", status
    assert status["original_publication_proven"] is False
    assert value.target.read_bytes() == value.after


def test_older_installed_owner_is_not_replaced_with_checkout_code(installation, monkeypatch):
    value = installation
    _store, selected = selected_generation(value, old_owner=True)
    monkeypatch.setattr(operator.subprocess, "run", lambda *a, **k: pytest.fail("unqualified publisher executed"))
    with pytest.raises(operator.PublicationUnavailable, match="NATIVE_POLICY_PUBLISHER_UPGRADE_REQUIRED"):
        operator.publish_or_observe(stable_ext=value.ext, expected_generation=selected,
            previous=digest(value.before), candidate=digest(value.after),
            candidate_path=value.candidate, rollback_source=value.rollback)
    assert value.target.read_bytes() == value.before


def test_changed_selected_generation_cannot_dispatch(installation, monkeypatch):
    value = installation
    selected_generation(value)
    monkeypatch.setattr(operator.subprocess, "run", lambda *a, **k: pytest.fail("wrong generation executed"))
    with pytest.raises(operator.PublicationUnavailable, match="NATIVE_GENERATION_CHANGED"):
        operator.publish_or_observe(stable_ext=value.ext, expected_generation="f" * 64,
            previous=digest(value.before), candidate=digest(value.after),
            candidate_path=value.candidate, rollback_source=value.rollback)
    assert value.target.read_bytes() == value.before


def test_lost_owner_reply_is_unknown_and_never_resent(installation, monkeypatch):
    value = installation
    _store, selected = selected_generation(value)
    calls = []
    def no_reply(command, **kwargs):
        calls.append(command)
        raise subprocess.TimeoutExpired(command, 20)
    monkeypatch.setattr(operator.subprocess, "run", no_reply)
    result = operator.publish_or_observe(stable_ext=value.ext, expected_generation=selected,
        previous=digest(value.before), candidate=digest(value.after),
        candidate_path=value.candidate, rollback_source=value.rollback)
    assert len(calls) == 1 and result["state"] == "EFFECT_UNKNOWN"
    assert result["writes_applied"] is None and result["retry_authorized"] is False


def test_real_operator_cli_fixed_refusal_does_not_echo_invalid_digest(installation, capsys):
    value = installation
    code = policy_change.main(["publication-status", "--stable-ext", str(value.ext),
        "--expected-native-generation", "f" * 64, "--expected-current-sha256", digest(value.before),
        "--expected-candidate-sha256", "Bearer PRIVATE_CANARY"])
    result = capsys.readouterr().out
    assert code == 2 and "PRIVATE_CANARY" not in result
    assert json.loads(result)["candidate_sha256"] is None


def test_legacy_three_argument_policy_consumer_keeps_its_contract(installation):
    value = installation
    assert owner.ensure_policy(value.candidate, value.ext, digest(value.after)) == "POLICY_REFRESHED_IDLE"
    assert owner.ensure_policy(value.candidate, value.ext, digest(value.after)) == "POLICY_CURRENT"


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_cancelled_modifying_owner_call_stays_unknown(installation, monkeypatch, interruption):
    value = installation
    _store, selected = selected_generation(value)
    calls = []
    def cancelled(command, **kwargs):
        calls.append(command)
        raise interruption()
    monkeypatch.setattr(operator.subprocess, "run", cancelled)
    result = operator.publish_or_observe(stable_ext=value.ext, expected_generation=selected,
        previous=digest(value.before), candidate=digest(value.after),
        candidate_path=value.candidate, rollback_source=value.rollback)
    assert result["state"] == "EFFECT_UNKNOWN" and result["writes_applied"] is None
    assert result["retry_authorized"] is False and len(calls) == 1


def test_lost_lock_close_ack_after_replace_keeps_unknown_and_original_target(installation, monkeypatch):
    value = installation
    actual = os.close
    lock_identity = (value.lock.stat().st_dev, value.lock.stat().st_ino)
    raised = []
    def close_once(descriptor):
        info = os.fstat(descriptor)
        actual(descriptor)
        if (info.st_dev, info.st_ino) == lock_identity and not raised:
            raised.append(True)
            raise OSError("PRIVATE_CLOSE_ACK")
    monkeypatch.setattr(owner.os, "close", close_once)
    with pytest.raises(owner.PolicyPublicationUnknown) as result:
        publish(value)
    assert str(result.value) == "POLICY_PUBLICATION_UNCERTAIN"
    assert value.target.read_bytes() == value.after and value.rollback.read_bytes() == value.before
    status = observe(value)
    assert status["state"] == "CANDIDATE_BYTES_OBSERVED"
    assert status["original_publication_proven"] is False


def _publisher_source_manifest():
    from ops.native_fabric.quota_continuity.rollout import build_review_stage as builder
    native = Path(builder.__file__).resolve().parent.parent
    manifest = json.loads((native / "rollout/native-manifest.json").read_bytes())
    current = (native / "candidate/support_bundle.py").read_bytes()
    assert digest(current) == builder.APPLICATION_POOL_COMPOSITION_DIGESTS["ext/support_bundle.py"]
    assert manifest["ext/support_bundle.py"] == digest(current)
    return builder, manifest


def test_publisher_successor_preserves_actual_manifest_and_prior_go_validator():
    builder, manifest = _publisher_source_manifest()
    before = copy.deepcopy(manifest)
    publisher_parent = builder.before_host_pull_integrity(manifest)
    assert publisher_parent is not manifest and manifest == before
    assert set(publisher_parent) == set(manifest)
    assert digest((json.dumps(publisher_parent, sort_keys=True, indent=2) + "\n").encode()) == "bcfb8c961c51a491cf66faaf697585675152bb6827ae1c070b9efcf5c7018c8e"
    previous = builder.before_application_pool_composition(publisher_parent)
    assert previous is not manifest and manifest == before
    assert {name for name in publisher_parent if publisher_parent[name] != previous[name]} == set(builder.APPLICATION_POOL_COMPOSITION_DIGESTS)
    assert digest((json.dumps(previous, sort_keys=True, indent=2) + "\n").encode()) == builder.APPLICATION_POOL_COMPOSITION_SPARSE_SUCCESSOR_PARENT_SHA256
    before_sparse = builder.before_sparse_commit_preflight(previous)
    assert digest((json.dumps(before_sparse, sort_keys=True, indent=2) + "\n").encode()) == builder.APPLICATION_POOL_COMPOSITION_SUCCESSOR_PARENT_SHA256
    dependencies = {name: manifest["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    builder.validate_go_base_manifest(manifest, dependencies)
    builder.validate_go_base_manifest(previous, {name: previous["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES})
    assert manifest == before
    assert builder.before_application_pool_composition(previous) == previous


@pytest.mark.parametrize("mutation", ["other_member", "missing_member", "renamed_member", "added_member"])
def test_publisher_forward_transform_refuses_partial_or_mixed_closures(mutation):
    builder, manifest = _publisher_source_manifest()
    manifest = builder.before_host_pull_integrity(manifest)
    if mutation == "other_member":
        manifest["ext/pick.py"] = "f" * 64
    elif mutation == "missing_member":
        del manifest["ext/pick.py"]
    elif mutation == "renamed_member":
        manifest["ext/unqualified.py"] = manifest.pop("ext/pick.py")
    else:
        manifest["ext/unqualified.py"] = "e" * 64
    with pytest.raises(ValueError, match="application pool composition parent closure"):
        builder.before_application_pool_composition(manifest)


def test_unknown_publisher_never_receives_forward_compatibility():
    builder, manifest = _publisher_source_manifest()
    current = copy.deepcopy(manifest)
    manifest = builder.before_host_pull_integrity(manifest)
    manifest["ext/support_bundle.py"] = "f" * 64
    dependencies = {name: manifest["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    with pytest.raises(ValueError, match="application pool composition cohort"):
        builder.before_application_pool_composition(manifest)
    with pytest.raises(ValueError, match="native scoped-model parent closure"):
        builder.validate_go_base_manifest(manifest, dependencies)

    # The actual current cohort rejects the same unknown publisher at its
    # outer host-pull boundary, separately from the historical scoped guard.
    current["ext/support_bundle.py"] = "f" * 64
    current_dependencies = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    with pytest.raises(ValueError, match="native host-pull integrity parent closure"):
        builder.validate_go_base_manifest(current, current_dependencies)
