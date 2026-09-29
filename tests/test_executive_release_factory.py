"""Factory composition tests; synthetic installed identity is not host proof."""
import copy
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import time
from types import SimpleNamespace

import pytest

from control_plane import executive_release_factory as f
from control_plane import executive_release_owner as owner
from control_plane import executive_release_ingress as ingress
from control_plane import executive_release_consumer as consumer
from control_plane import executive_privileged_broker as broker
from tests.test_executive_release_controller_policy import inputs, source
from tests.test_executive_release_consumer import installed, counts


def wire(value):
    return f.contract.canonical_release_bytes(value) + b"\n"


@pytest.fixture
def image(monkeypatch, inputs):
    principal, effect, policy = copy.deepcopy(inputs)
    files = {}
    now = [200]
    boot = "11111111-1111-4111-8111-111111111111"
    reg = dict(schema="mastermind.executive_release_owner_registration/v1",
               owner_installation_id=boot, target_ref="5" * 64, key_id="test-key",
               trust_generation=1, app_generation=1, registration_generation=1, enabled=True)
    config = broker.PrivilegedBrokerConfig(
        release_root=broker._RELEASE_PREFIX / effect["from_release_commit"],
        receipt_root=broker._RECEIPT_ROOT, allowed_peer_uids=(450,))
    def put(path, raw):
        files[Path(path)] = raw
    put(f._REGISTRATION, wire(reg))
    put(f._KEY, bytes(range(32)))
    control = {"proof_base_sha": effect["from_release_commit"], "control_uid": 450,
               "python_runtime_provenance_digest": "a" * 64}
    put(f._CONTROL, json.dumps(control).encode())
    broker_doc = {"schema": broker.BROKER_CONFIG_SCHEMA, "release_root": str(config.release_root),
                  "receipt_root": str(config.receipt_root), "allowed_peer_uids": [450],
                  "timeout_seconds": 120, "broker_version": "1"}
    put(f._BROKER_CONFIG, json.dumps(broker_doc).encode())
    profile = dict(schema="mastermind.executive_release_installer_profile/v1",
                   profile_id="synthetic", profile_version=1,
                   **{key: effect[key] for key in ("repository", "platform", "architecture",
                                                  "source_policy_mode", "action")})
    effect["installer_profile_digest"] = f._digest(profile)
    policy["installer_profile_digests"] = [f._digest(profile)]
    put(config.release_root / "config/authority_map.yml", source(policy))
    for name in (*f._DEPENDENCIES, *broker._TRUSTED_EFFECT_PATHS):
        put(config.release_root / name, ("synthetic " + name).encode())
    manifest = {"schema_version": "mastermind.executive_release_manifest/v1",
                "commit_sha": effect["from_release_commit"], "tree_sha": effect["from_release_tree"],
                "entries": [{"path": str(path.relative_to(config.release_root)), "mode": 0o444,
                             "uid": 0, "gid": 0, "type": "file", "size": len(raw),
                             "sha256": f._hash(raw)} for path, raw in files.items()
                            if path.is_relative_to(config.release_root)]}
    manifest_path = config.release_root / ".executive-release-manifest.json"
    put(manifest_path, json.dumps(manifest).encode())
    effect["from_installed_manifest_digest"] = f._hash(files[manifest_path])
    config_digest = f._digest({"schema": "mastermind.executive_installed_configuration_set/v1",
        "files": [{"path": name, "sha256": f._hash(files[path])} for name, path in (
            ("config/control.json", f._CONTROL),
            ("config/authority_map.yml", config.release_root / "config/authority_map.yml"),
            ("config/privileged-broker.json", f._BROKER_CONFIG))]})
    evidence = dict(schema="mastermind.executive_release_owner_installed_evidence/v1",
        owner_installation_id=boot, target_ref=reg["target_ref"], registration_generation=1,
        release_commit=effect["from_release_commit"], release_tree=effect["from_release_tree"],
        control_config_digest=f._hash(files[f._CONTROL]), broker_config_digest=f._hash(files[f._BROKER_CONFIG]),
        installed_configuration_digest=config_digest, python_runtime_provenance_digest="a" * 64,
        provider_binary_attestation_digest="b" * 64, provider_attestation_role="codex_worker",
        provider_attestation_boot_id=boot, issuer_binding_digest="c" * 64,
        issuer_binding_owner_installation_id=boot, issuer_binding_role="control",
        issuer_binding_release_commit=effect["from_release_commit"], issuer_binding_boot_id=boot,
        issuer_binding_observed_at="1970-01-01T00:03:00Z",
        provider_attestation_observed_at="1970-01-01T00:03:00Z", production_disarming=f._DISARMED)
    put(f._EVIDENCE, wire(evidence))
    docs = {"installer-profile.json": profile}
    artifact = b"synthetic artifact; never executable\n"
    docs["artifact-metadata.json"] = dict(schema="mastermind.executive_release_artifact_metadata/v1",
        artifact_filename="release-artifact.bin", media_type="application/vnd.mastermind.executive.release.v1",
        artifact_size_bytes=len(artifact), artifact_sha256=f._hash(artifact))
    docs["configuration-transition.json"] = dict(schema="mastermind.executive_release_configuration_transition/v1",
        from_configuration_digest=config_digest, to_configuration_digest="d" * 64,
        changed_keys=["synthetic"], restart_roles=["control"])
    identities = {key: effect[key] for key in (
        "from_release_commit", "from_release_tree", "to_release_commit", "to_release_tree")}
    docs["source-proof.json"] = dict(schema="mastermind.executive_release_source_proof/v1",
        **{key: effect[key] for key in ("repository", "source_policy_mode", "protected_source_sha",
            "installer_source_commit", "installer_source_tree", *identities)},
        protected_source_tree=effect["installer_source_tree"],
        producer="ops/executive_os/install.sh:protected-source-proof-v1", observed_at="1970-01-01T00:03:00Z")
    docs["compatibility-proof.json"] = dict(schema="mastermind.executive_release_compatibility_proof/v1",
        **identities, platform="darwin", architecture="arm64", installer_profile_digest=f._digest(profile),
        checks=["synthetic"], result="PASS", producer="ops/executive_os/install.sh:compatibility-proof-v1")
    docs["rollback-evidence.json"] = dict(schema="mastermind.executive_release_rollback_evidence/v1",
        action=effect["action"], **identities, checks=["synthetic"], result="PASS",
        producer="ops/executive_os/install.sh:rollback-evidence-v1")
    docs["preservation-plan.json"] = dict(schema="mastermind.executive_release_preservation_plan/v1",
        from_installed_manifest_digest=effect["from_installed_manifest_digest"],
        configuration_transition_digest=f._digest(docs["configuration-transition.json"]),
        retained_paths=["config/control.json"], excluded_secret_classes=["seal-key"],
        rollback_evidence_digest=f._digest(docs["rollback-evidence.json"]),
        producer="ops/executive_os/install.sh:preservation-plan-v1")
    effect.update(staged_artifact_digest=f._hash(artifact),
        staged_content_metadata_digest=f._digest(docs["artifact-metadata.json"]),
        configuration_transition_digest=f._digest(docs["configuration-transition.json"]),
        compatibility_proof_digest=f._digest(docs["compatibility-proof.json"]),
        preservation_plan_digest=f._digest(docs["preservation-plan.json"]),
        rollback_evidence={"kind": "upgrade", "rollback_readiness_digest": f._digest(docs["rollback-evidence.json"])})
    docs["effect.json"] = effect
    transition = f._digest(effect)
    directory = f._STAGING / transition
    docs["preconditions-template.json"] = dict(schema="mastermind.executive_release_preconditions/v1",
        owner_installation_id=boot, target_ref=reg["target_ref"], boot_id=boot,
        from_installed_manifest_digest=effect["from_installed_manifest_digest"],
        installed_configuration_digest=config_digest, python_runtime_provenance_digest="a" * 64,
        provider_binary_attestation_digest="b" * 64, authority_policy_hash=f._hash(source(policy)),
        issuer_binding_digest="c" * 64, admission_contract_digest=f._digest(f._ADMISSION_MAP),
        production_arming_digest=f._digest(f._DISARMED),
        **{key: effect[key] for key in ("staged_artifact_digest", "staged_content_metadata_digest",
                                       "compatibility_proof_digest", "preservation_plan_digest")})
    for name, value in docs.items():
        put(directory / name, wire(value))
    put(directory / "release-artifact.bin", artifact)
    put(f._REGISTRY, wire(dict(schema="mastermind.executive_release_owner_staged_registry/v1",
        registration_generation=1, registry_generation=1,
        transitions=[dict(transition_digest=transition, staging_generation=1, state="STAGED")])))
    class Reader:
        def __init__(self, **kwargs):
            self.deadline = time.monotonic() + 5
        check = f._Reader.check
        def observe(self, path, *, directory=False, retain=True, **kwargs):
            if directory:
                names = sorted(p.name for p in files if p.parent == path)
                if names != sorted(kwargs["names"]):
                    f._unavailable()
                return f._File(None, f._digest({"names": names}), (1,) * 9, ())
            raw = files[Path(path)]
            return f._File(raw if retain else None, f._hash(raw), (1, 2, 3, 0, 0, 1, len(raw), 4, 5), ())
    real_lstat = os.lstat
    monkeypatch.setattr(f.os, "lstat", lambda path, **kw: object() if Path(path) == f._REGISTRATION else real_lstat(path, **kw))
    monkeypatch.setattr(f.os, "geteuid", lambda: 0)
    # This fixture models a Darwin installed image even on Linux CI. Real
    # Darwin filesystem behavior is covered separately, not claimed here.
    monkeypatch.setattr(f, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(f, "_Reader", Reader)
    monkeypatch.setattr(f, "_boot_id", lambda: boot)
    monkeypatch.setattr(f.time, "time", lambda: now[0])
    monkeypatch.setattr(f.time, "time_ns", lambda: now[0] * 1_000_000_000)
    monkeypatch.setattr(broker, "verify_production_trust", lambda config: None)
    monkeypatch.setattr(owner, "_qualify_connection", lambda connection, role: None)
    return dict(files=files, now=now, config=config, transition=transition, principal=principal,
                effect=effect, docs=docs, directory=directory, reg=reg, evidence=evidence)


def test_real_factory_snapshot_approval_prepare_and_disarmed_commit(image):
    root = f.build_release_owner(image["config"])
    snapshot = root._snapshot(image["transition"])
    assert snapshot.effect.to_dict() == image["effect"]
    assert len(snapshot.input_identity_digest) == 64
    frame = ingress.project_frame("approve_release_transition",
        {"operation_key": "factory-proof", "action": image["effect"]["action"],
         "transition_digest": image["transition"]}, principal=image["principal"])
    raw = {**frame, "schema": consumer.BROKER_SCHEMA, "approval": None}
    approved = root.handle(raw, None)
    assert approved["ok"] is True
    prepare = ingress.project_frame("prepare_release_transition",
        {"operation_key": "factory-proof", "approved_transition_ref": f.contract.approval_ref_for("factory-proof")},
        principal=image["principal"])
    result = root.handle({**prepare, "schema": consumer.BROKER_SCHEMA, "approval": approved["approval"]}, None)
    assert result["ok"] is True
    assert result["result"]["prepared_token"]
    commit = ingress.project_frame("commit_prepared_release_transition",
        {"prepared_token": result["result"]["prepared_token"]}, principal=image["principal"])
    with pytest.raises(consumer.ReleaseConsumerError, match="RELEASE_COMMIT_DISARMED"):
        root.handle({**commit, "schema": consumer.BROKER_SCHEMA, "approval": None}, None)


@pytest.mark.parametrize("key", ["config/control.json", "config/authority_map.yml", "config/privileged-broker.json",
                                 ".executive-release-manifest.json", *f._DEPENDENCIES])
def test_history_detects_each_resident_drift_with_projection_unchanged(image, key):
    root = f.build_release_owner(image["config"])
    path = ({"config/control.json": f._CONTROL, "config/privileged-broker.json": f._BROKER_CONFIG}.get(key)
            or image["config"].release_root / key)
    image["files"][path] += b" "
    with pytest.raises(consumer.ReleaseConsumerError):
        root._history_trust()


@pytest.mark.parametrize("age", [86400, 86401, 172800])
def test_identical_restart_keeps_history_after_admission_expiry(image, age):
    original = f.build_release_owner(image["config"])
    before = original._history_trust().input_identity_digest
    image["now"][0] = 180 + age
    restarted = f.build_release_owner(image["config"])
    for path in list(image["files"]):
        if path.is_relative_to(f._STAGING) or path == f._REGISTRY:
            del image["files"][path]
    assert restarted._history_trust().input_identity_digest == before
    with pytest.raises(consumer.ReleaseConsumerError):
        restarted._snapshot(image["transition"])


@pytest.mark.parametrize("path", [f._KEY, f._REGISTRATION, f._EVIDENCE])
def test_resident_secret_or_registration_change_never_rebaselines(image, path):
    root = f.build_release_owner(image["config"])
    if path == f._KEY:
        image["files"][path] = bytes(reversed(range(32)))
    else:
        doc = f.file_document(image["files"][path])
        doc["registration_generation"] += 1
        image["files"][path] = wire(doc)
    with pytest.raises(consumer.ReleaseConsumerError):
        root._history_trust()


@pytest.mark.parametrize("name", sorted(f._STAGE_FILES - {"release-artifact.bin"}))
def test_every_staged_document_rejects_extra_fields(image, name):
    root = f.build_release_owner(image["config"])
    value = copy.deepcopy(image["docs"][name])
    value["extra"] = "PRIVATE_SENTINEL"
    image["files"][image["directory"] / name] = wire(value)
    with pytest.raises(consumer.ReleaseConsumerError) as caught:
        root._snapshot(image["transition"])
    assert "PRIVATE_SENTINEL" not in str(caught.value)


def test_factory_composes_existing_socket_and_runtime_owner(image, installed):
    installed["root_broker"]._release_owner = f.build_release_owner(image["config"])
    before = counts(installed["runtime"])
    args = {"operation_key": "factory-real-socket", "action": image["effect"]["action"],
            "transition_digest": image["transition"]}
    result = installed["call"]("approve_release_transition", args)
    assert result["ok"] is True
    assert installed["call"]("approve_release_transition", args) == result
    prepared = installed["call"]("prepare_release_transition", {
        "operation_key": args["operation_key"], "approved_transition_ref": result["approved_transition_ref"]})
    assert prepared["ok"] is True
    blocked = installed["call"]("commit_prepared_release_transition", {
        "prepared_token": prepared["prepared_token"]})
    assert blocked["error"]["code"] == "RELEASE_COMMIT_DISARMED"
    history = installed["call"]("reconcile_release_transition", {"operation_key": args["operation_key"]})
    assert history["ok"] is True
    assert history["approval"]["approved_transition_ref"] == result["approved_transition_ref"]
    assert counts(installed["runtime"]) == (before[0] + 1, before[1], before[2])
    assert {role for role, _pid in installed["peer_calls"]} == {"control", "gateway"}


def test_original_approval_verifies_after_identical_restart_and_expiry(image):
    root = f.build_release_owner(image["config"])
    frame = ingress.project_frame("approve_release_transition",
        {"operation_key": "factory-history", "action": image["effect"]["action"],
         "transition_digest": image["transition"]}, principal=image["principal"])
    approved = root.handle({**frame, "schema": consumer.BROKER_SCHEMA, "approval": None}, None)
    image["now"][0] = 180 + 86400
    restarted = f.build_release_owner(image["config"])
    for path in list(image["files"]):
        if path.is_relative_to(f._STAGING) or path == f._REGISTRY:
            del image["files"][path]
    current = dataclasses.replace(image["principal"], issued_at=image["now"][0] - 10,
                                  expires_at=image["now"][0] + 900)
    reconcile = ingress.project_frame("reconcile_release_transition",
        {"operation_key": "factory-history"}, principal=current)
    result = restarted.handle({**reconcile, "schema": consumer.BROKER_SCHEMA,
                               "approval": approved["approval"]}, None)
    assert result["approval"] == approved["approval"]
    with pytest.raises(consumer.ReleaseConsumerError):
        restarted._snapshot(image["transition"])
