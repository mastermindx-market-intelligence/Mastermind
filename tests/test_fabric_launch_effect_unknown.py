"""Installer interruption semantics, against only isolated fixture consumers.

An OS error at or immediately after atomic replacement does NOT establish that
the original launcher is still installed. Keep the release effect UNKNOWN and
require original-owner readback/reconciliation before any retry.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ops.fabric_launch import install


@pytest.fixture
def fixture_release(tmp_path, monkeypatch):
    wrapper = tmp_path / "pool"
    original = b'#!/bin/bash\nCMD="$1";shift\ncase "$CMD" in\n  status) echo original;;\nesac\n'
    wrapper.write_bytes(original)
    wrapper.chmod(0o700)
    release = tmp_path / "release"
    release.mkdir()
    candidate = install.wrapper_content(original, release)
    studio = tmp_path / "private-studio"
    consumer = studio / "one"
    consumer.mkdir(parents=True)
    (consumer / "config.json").write_text(json.dumps({
        "fleetStatus": {
            "enabled": True,
            "fabricLauncherPath": str(wrapper),
            "fabricLauncherSha256": install.sha(candidate),
        }
    }))
    monkeypatch.setattr(install, "STUDIO_CONSUMER_ROOT", studio)
    return wrapper, original, candidate, release


@pytest.mark.parametrize("replace_first", [False, True])
def test_installer_rename_error_reports_effect_unknown(fixture_release, monkeypatch, replace_first):
    wrapper, original, candidate, release = fixture_release
    original_replace = install.os.replace

    def injected_replace(src, dst):
        if Path(dst) == wrapper:
            if replace_first:
                original_replace(src, dst)
            raise OSError("INJECTED_REPLACE_EXCEPTION")
        return original_replace(src, dst)

    monkeypatch.setattr(install.os, "replace", injected_replace)
    with pytest.raises(ValueError, match="WRAPPER_ACTIVATION_EFFECT_UNKNOWN"):
        install.activate(wrapper, release, install.sha(original))

    # An exception is not a proof of NOT_APPLIED. Both original and new
    # outcomes are possible depending on where the actual OS failure occurred.
    assert wrapper.read_bytes() == (candidate if replace_first else original)
    backup = wrapper.with_name("pool.pre-worker-bootstrap-" + install.sha(original)[:12])
    assert backup.read_bytes() == original
    assert not list(wrapper.parent.glob(".pool-worker-bootstrap-*"))


def test_installer_post_replace_read_error_reports_effect_unknown(fixture_release, monkeypatch):
    wrapper, original, candidate, release = fixture_release
    original_replace = install.os.replace
    original_read = Path.read_bytes
    state = {"replaced": False}

    def observed_replace(src, dst):
        original_replace(src, dst)
        if Path(dst) == wrapper:
            state["replaced"] = True

    def read_with_post_replace_error(self):
        if self == wrapper and state["replaced"]:
            raise OSError("INJECTED_POST_REPLACE_READ_EXCEPTION")
        return original_read(self)

    monkeypatch.setattr(install.os, "replace", observed_replace)
    monkeypatch.setattr(Path, "read_bytes", read_with_post_replace_error)
    with pytest.raises(ValueError, match="WRAPPER_ACTIVATION_EFFECT_UNKNOWN"):
        install.activate(wrapper, release, install.sha(original))
    assert state["replaced"] is True
    assert original_read(wrapper) == candidate
    assert not list(wrapper.parent.glob(".pool-worker-bootstrap-*"))


def test_installer_post_replace_drift_reports_effect_unknown(fixture_release, monkeypatch):
    wrapper, original, candidate, release = fixture_release
    original_replace = install.os.replace
    original_read = Path.read_bytes
    state = {"replaced": False}

    def replace_then_observe(src, dst):
        original_replace(src, dst)
        if Path(dst) == wrapper:
            state["replaced"] = True

    def corrupt_readback(self):
        if self == wrapper and state["replaced"]:
            return b"INJECTED_READBACK_MISMATCH"
        return original_read(self)

    monkeypatch.setattr(install.os, "replace", replace_then_observe)
    monkeypatch.setattr(Path, "read_bytes", corrupt_readback)
    with pytest.raises(ValueError, match="WRAPPER_ACTIVATION_EFFECT_UNKNOWN"):
        install.activate(wrapper, release, install.sha(original))
    assert state["replaced"] is True
    assert original_read(wrapper) == candidate
    assert not list(wrapper.parent.glob(".pool-worker-bootstrap-*"))
