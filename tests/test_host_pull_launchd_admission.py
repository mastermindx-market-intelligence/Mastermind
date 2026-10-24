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
HOST_PULL_SHA = "eba14f067f9dd1a3f2d19e0c1204340fd0af560c03372ff6c5e68d22aa9b763a"
HOST_PULL_PREIMAGE = "65b294a5ea2d17a9d7832307372bdb07262da62b5106a1ecad9ffa6c2b5cd9ad"
PROGRAM_ARGUMENTS = [
    "/usr/bin/lockf", "-t", "0", "__LOCK__", "/bin/bash", "__HOST_PULL__",
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


def test_manifest_enrolls_the_pair_without_an_installed_preimage():
    manifest = json.loads(MANIFEST_PATH.read_text())
    inventory = json.loads(INVENTORY_PATH.read_text())
    assert len(manifest) == len(inventory["files"]) == 97
    assert inventory["native_code_files"] == 97
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
    assert host["bytes"] == 11854
    assert manifest["ext/host_pull.sh"] == HOST_PULL_SHA
    assert not (CANDIDATE / "launchd").exists()
    daemon = DAEMON.read_text()
    assert hashlib.sha256(TEMPLATE.read_bytes()).hexdigest() in daemon
