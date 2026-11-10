"""Packaging admission for the one flat host-pull launchd template.

These tests enroll no live generation. They check the sealed file_name
exception, the two new manifest rows, and the immutable ProgramArguments.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import plistlib
import pytest

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "ops/native_fabric/quota_continuity/candidate"
DAEMON = CANDIDATE / "host_pull_daemon.sh"
TEMPLATE = CANDIDATE / "host_pull_launchd.plist.template"
PUBLISHER = ROOT / "ops/native_fabric/quota_continuity/rollout/native_generation.py"
MANIFEST_PATH = ROOT / "ops/native_fabric/quota_continuity/rollout/native-manifest.json"
INVENTORY_PATH = ROOT / "ops/native_fabric/quota_continuity/rollout/native-source-inventory.json"
HOST_PULL_SHA = "464d9a5522a61311d5e8c2b7495a6297c86300d611903ad56524d4aa2e574e72"
HOST_PULL_PREIMAGE = "65b294a5ea2d17a9d7832307372bdb07262da62b5106a1ecad9ffa6c2b5cd9ad"
MANIFEST_SHA256 = "22905ae361e7076226aa239e947553433274c56f0c3db73c51cad0a317754ada"
PROGRAM_ARGUMENTS = [
    "/usr/bin/lockf", "-t", "0", "__LOCK__", "/bin/bash", "__HOST_PULL__",
    "__COLLECTOR_OPTION__",
]
HISTORICAL_ALLOWLIST = (
    'or parts[1] in {"yes", "host_pull_probe.template",\n'
    '                        "paid_pyyaml_6_0_3.zip", "paid_pyyaml_provenance.json"})'
)


def _generation():
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location("host_pull_admission_generation", PUBLISHER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GENERATION = _generation()


def test_file_name_admits_only_the_one_flat_plist():
    publisher = PUBLISHER.read_text()
    assert HISTORICAL_ALLOWLIST in publisher
    assert publisher.count('if relative == "ext/host_pull_launchd.plist.template":') == 1
    for name in (
        "ext/host_pull_launchd.plist.template",
        "ext/host_pull_daemon.sh",
        "pool",
        "ext/paid_pyyaml_6_0_3.zip",
        "ext/paid_pyyaml_provenance.json",
        "ext/host_pull_probe.template",
        "ext/yes",
    ):
        GENERATION.file_name(name)
    rejected = (
        "ext/launchd/com.mastermind.host-pull.plist.template",
        "ext/launchd/host_pull_launchd.plist.template",
        "ext/nested/host_pull_launchd.plist.template",
        "ext/host_pull_launchd.plist",
        "ext/com.mastermind.host-pull.plist.template",
        "ext/other.plist.template",
        "ext/host_pull_launchd.plist.template.bak",
        "ext/../host_pull_launchd.plist.template",
        "host_pull_launchd.plist.template",
        "ext/host_pull_launchd.plist.template/extra",
        "ext/*.plist.template",
        "ext/pools.yaml",
        "ext/other.zip",
        "ext/other.json",
        None,
        12,
    )
    for name in rejected:
        with pytest.raises(ValueError):
            GENERATION.file_name(name)


def test_regular_bytes_rejects_a_symlink_plist(tmp_path):
    link = tmp_path / "host_pull_launchd.plist.template"
    link.symlink_to(TEMPLATE)
    with pytest.raises(OSError):
        GENERATION.regular_bytes(link)


def test_template_program_arguments_are_immutable():
    raw = TEMPLATE.read_bytes()
    plist = plistlib.loads(raw)
    assert plist["ProgramArguments"] == PROGRAM_ARGUMENTS
    assert plist["Label"] == "com.mastermind.host-pull"
    assert plist["KeepAlive"] is True and plist["RunAtLoad"] is True
    text = raw.decode()
    assert text.count("/usr/bin/lockf") == 1
    assert "/bin/sh" not in text
    assert "ADMITTED_TEMPLATE_SHA256" not in text


def test_manifest_pin_rejects_byte_drift(monkeypatch):
    original = Path.read_bytes
    def drift(path):
        raw = original(path)
        return raw + b"\n" if path == MANIFEST_PATH else raw
    monkeypatch.setattr(Path, "read_bytes", drift)
    with pytest.raises(AssertionError):
        test_manifest_enrolls_the_pair_without_an_installed_preimage()


def test_manifest_enrolls_the_pair_without_an_installed_preimage():
    assert hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest() == MANIFEST_SHA256
    manifest = json.loads(MANIFEST_PATH.read_text())
    inventory = json.loads(INVENTORY_PATH.read_text())
    assert len(manifest) == len(inventory["files"]) == 107
    assert inventory["native_code_files"] == 107
    assert inventory["baseline_code_files"] == 75
    for path in (DAEMON, TEMPLATE):
        raw = path.read_bytes()
        relative = "ext/" + path.name
        digest = hashlib.sha256(raw).hexdigest()
        assert manifest[relative] == digest
        row = inventory["files"][relative]
        assert row["sha256"] == digest
        assert row["bytes"] == len(raw)
        assert row["installed_preimage_sha256"] is None
        assert row["source"] == "candidate/" + path.name
        assert path.name in inventory["new_code_files"]
    host = inventory["files"]["ext/host_pull.sh"]
    assert host["sha256"] == HOST_PULL_SHA
    assert host["installed_preimage_sha256"] == HOST_PULL_PREIMAGE
    assert host["bytes"] == 15414
    assert manifest["ext/host_pull.sh"] == HOST_PULL_SHA
    assert not (CANDIDATE / "launchd").exists()
    daemon = DAEMON.read_text()
    assert hashlib.sha256(TEMPLATE.read_bytes()).hexdigest() in daemon



def _builder():
    import importlib.util
    import sys
    path = PUBLISHER.with_name("build_review_stage.py")
    spec = importlib.util.spec_from_file_location("host_pull_admission_builder", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BUILDER = _builder()
HOST_COHORT = ("ext/host_pull.sh", "ext/host_pull_backend.py", "ext/host_pull_daemon.sh")


def _host_pull_cohort(lineage="application"):
    current = json.loads(MANIFEST_PATH.read_text())
    assert hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest() == MANIFEST_SHA256
    if lineage == "worker":
        raw = (ROOT / "tests/fixtures/fabric-admission-integrity-worker107-3b2338d.json").read_bytes()
        assert hashlib.sha256(raw).hexdigest() == "8af7302990d7e77112457090767265d7eb43a4f544ec533bf9b517c5eb6c35c6"
        predecessor = json.loads(raw)
        successor = dict(predecessor)
        successor.update({name: current[name] for name in HOST_COHORT})
        expected_successor = "a42259df6aa9dc910abd3e6eacb75f30b9089663d569c88f946f965bc8ceedd3"
        expected_predecessor = "8af7302990d7e77112457090767265d7eb43a4f544ec533bf9b517c5eb6c35c6"
    else:
        assert lineage == "application"
        successor = current
        predecessor = dict(successor)
        predecessor.update(BUILDER.HOST_PULL_INTEGRITY_PREIMAGES)
        expected_successor = MANIFEST_SHA256
        # Historical host-pull parent stays accepted; the composed f57b085 x
        # d0c543 endpoint projects the same trio (plus the broker inverse)
        # onto its composed http parent. Foreign parents still fail below.
        expected_predecessor = (
            "bcfb8c961c51a491cf66faaf697585675152bb6827ae1c070b9efcf5c7018c8e",
            BUILDER.HOST_PULL_INTEGRITY_COMPOSED_HTTP_PARENT_MANIFEST_SHA256)
    for manifest, expected in ((predecessor, expected_predecessor), (successor, expected_successor)):
        digest_hex = hashlib.sha256((json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()).hexdigest()
        assert digest_hex in (expected if isinstance(expected, tuple) else (expected,))
    return predecessor, successor


def _go_dependency_bytes(lineage="application"):
    if lineage == "worker":
        predecessor, _ = _host_pull_cohort(lineage)
        return {name: predecessor["ext/" + name] for name in BUILDER.GO_APPLICATION_DEPENDENCIES}
    assert lineage == "application"
    predecessor, _ = _host_pull_cohort(lineage)
    return {name: predecessor["ext/" + name] for name in BUILDER.GO_APPLICATION_DEPENDENCIES}


@pytest.mark.parametrize("lineage", ["application", "worker"])
def test_host_pull_successor_reaches_existing_validation_without_relabeling(lineage):
    predecessor, successor = _host_pull_cohort(lineage)
    original = dict(successor)
    for relative in HOST_COHORT:
        raw = (CANDIDATE / relative.removeprefix("ext/")).read_bytes()
        assert successor[relative] == hashlib.sha256(raw).hexdigest()
        assert successor[relative] != predecessor[relative]
    # The unchanged previous owner refuses these genuinely new bytes.
    with pytest.raises(ValueError, match="admission integrity parent closure differs"):
        BUILDER.before_admission_integrity(successor)
    normalized = BUILDER.before_host_pull_integrity(successor)
    # The composed f57b085 x d0c543 carrier also projects the quiescence
    # broker successor back to its frozen preimage when the projected view
    # is an accepted parent; both endpoints normalize to the same cohort.
    composed_broker_preimage_view = {
        **predecessor,
        "ext/lease_broker.py": BUILDER.COMPOSED_JOIN_QUIESCENCE_BROKER_PREIMAGE,
    }
    assert normalized in (predecessor, composed_broker_preimage_view)
    assert normalized is not successor
    if lineage == "worker":
        historical = BUILDER.before_admission_integrity(normalized)
        expected_historical = "815ec3c880b5f66590b7dcc04ac42c6c5384ba296b44e83af7e96c23326f6347"
    else:
        historical = BUILDER.normalize_application_carrier_base_manifest(normalized)
        expected_historical = "a68a4af9834da02d85ac00300ccaf0540c0fbccedd9c3a7c883157696558df35"
    assert hashlib.sha256(
        (json.dumps(historical, sort_keys=True, indent=2) + "\n").encode()
    ).hexdigest() == expected_historical
    BUILDER.validate_go_base_manifest(successor, _go_dependency_bytes(lineage))
    assert successor == original


@pytest.mark.parametrize("lineage", ["application", "worker"])
def test_host_pull_predecessor_keeps_its_existing_validation_path(lineage):
    predecessor, _ = _host_pull_cohort(lineage)
    original = dict(predecessor)
    normalized = BUILDER.before_host_pull_integrity(predecessor)
    assert normalized == predecessor
    assert normalized is not predecessor
    BUILDER.validate_go_base_manifest(predecessor, _go_dependency_bytes(lineage))
    assert predecessor == original


@pytest.mark.parametrize("members", [
    (0,), (1,), (2,), (0, 1), (0, 2), (1, 2),
])
@pytest.mark.parametrize("lineage", ["application", "worker"])
def test_host_pull_partial_successor_is_refused(members, lineage):
    predecessor, successor = _host_pull_cohort(lineage)
    mixed = dict(predecessor)
    for index in members:
        mixed[HOST_COHORT[index]] = successor[HOST_COHORT[index]]
    original = dict(mixed)
    with pytest.raises(ValueError, match="host-pull integrity cohort"):
        BUILDER.validate_go_base_manifest(mixed, _go_dependency_bytes(lineage))
    assert mixed == original


@pytest.mark.parametrize("member", HOST_COHORT)
@pytest.mark.parametrize("lineage", ["application", "worker"])
def test_host_pull_foreign_member_is_refused(member, lineage):
    _, successor = _host_pull_cohort(lineage)
    successor[member] = "f" * 64
    with pytest.raises(ValueError, match="host-pull integrity cohort"):
        BUILDER.validate_go_base_manifest(successor, _go_dependency_bytes(lineage))


@pytest.mark.parametrize("drift", [
    "unrelated", "extra", "missing", "historical106", "historical104", "historical102",
])
@pytest.mark.parametrize("lineage", ["application", "worker"])
def test_host_pull_successor_cannot_relabel_another_complete_closure(drift, lineage):
    _, successor = _host_pull_cohort(lineage)
    if drift == "unrelated":
        successor["pool"] = "f" * 64
    elif drift == "extra":
        successor["ext/unreviewed.py"] = "f" * 64
    elif drift == "missing":
        del successor["pool"]
    else:
        for name in BUILDER.GO_ORIGINAL_ARTIFACT_ADDITIONS:
            del successor["ext/" + name]
        if drift in ("historical104", "historical102"):
            for name in BUILDER.GO_PARTICIPANT_ADDITIONS:
                del successor["ext/" + name]
        if drift == "historical102":
            for name in BUILDER.GO_POST_FAILURE_ADDITIONS:
                del successor["ext/" + name]
    with pytest.raises(ValueError, match="host-pull integrity parent closure differs"):
        BUILDER.validate_go_base_manifest(successor, _go_dependency_bytes(lineage))


@pytest.mark.parametrize("members", [
    ("ext/fabric_task.py",), ("ext/lane_runtime.py",),
    ("ext/fabric_task.py", "ext/lane_runtime.py"),
])
@pytest.mark.parametrize("lineage", ["application", "worker"])
def test_host_pull_successor_requires_current_admission_integrity_pair(members, lineage):
    _, successor = _host_pull_cohort(lineage)
    for member in members:
        successor[member] = BUILDER.ADMISSION_INTEGRITY_PREIMAGES[member]
    with pytest.raises(ValueError, match="host-pull integrity parent closure differs"):
        BUILDER.validate_go_base_manifest(successor, _go_dependency_bytes(lineage))


@pytest.mark.parametrize("manifest", [None, [], "not a manifest"])
def test_host_pull_manifest_type_is_closed(manifest):
    with pytest.raises(ValueError, match="host-pull integrity manifest invalid"):
        BUILDER.before_host_pull_integrity(manifest)


@pytest.mark.parametrize("lineage", ["application", "worker"])
def test_unrecognized_host_trio_still_fails_the_existing_complete_guard(lineage):
    predecessor, _ = _host_pull_cohort(lineage)
    for member in HOST_COHORT:
        predecessor[member] = "f" * 64
    expected = ("application pool composition parent closure differs" if lineage == "application"
                else "admission integrity parent closure differs")
    with pytest.raises(ValueError, match=expected):
        BUILDER.validate_go_base_manifest(predecessor, _go_dependency_bytes(lineage))
