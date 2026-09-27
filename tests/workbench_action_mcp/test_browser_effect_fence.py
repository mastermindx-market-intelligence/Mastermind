"""Durable Browser issuance fence: real owner artifacts, no external browser."""
from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from integrations.workbench_action_mcp import action_artifacts as aa


def _store(tmp_path: Path):
    root = tmp_path / "artifacts"
    root.mkdir(mode=0o700)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    store = aa.adopt_artifact_store(fd)
    identity = aa.ActionArtifactIdentity(
        action_id="a" * 32, purpose="browser_action", subject_digest="b" * 64,
        client_ref="client:test", resource="https://example.invalid/browser",
        project_ref="project:test", context_ref="context:test", responsibility_ref="responsibility:test",
        operation_ref="operation:test", owner_ref="owner:test", generation="generation:test",
        root_device=1, root_inode=2, store_device=store.device, store_inode=store.inode,
        host_id="c" * 64, boot_session_id="boot:test", relative_path="browser:test:browser_click",
        source_identity="d" * 64,
    )
    return fd, store, identity, root


def _terminal(store, identity):
    assert aa.claim_action(store, identity, claimed_at_ms=1000).created
    aa.finalize_action(store, identity, effect_state="APPLIED", observed_sha256="e" * 64,
                       completed_at_ms=2000, durability="durable")


def test_fence_is_read_only_and_repeated_census_never_skips_existing_records(tmp_path: Path):
    fd, store, identity, root = _store(tmp_path)
    try:
        with aa.acquire_store_writer(store) as writer:
            _terminal(store, identity)
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            aa.require_terminal_store_effects(store, writer)
            aa.require_terminal_store_effects(store, writer)
            assert {p.name: p.read_bytes() for p in root.iterdir()} == before
            aa.claim_action(store, dataclasses.replace(identity, action_id="f" * 32), claimed_at_ms=2000)
            with pytest.raises(aa.ActionArtifactUncertain):
                aa.require_terminal_store_effects(store, writer)
    finally:
        os.close(fd)


@pytest.mark.parametrize("damage", ["malformed", "different_identity", "foreign_store", "unknown", "symlink", "oversized"])
def test_damaged_evidence_never_clears_issuance(tmp_path: Path, damage: str):
    fd, store, identity, root = _store(tmp_path)
    try:
        with aa.acquire_store_writer(store) as writer:
            _terminal(store, identity)
            result = root / aa.artifact_name(identity.action_id, "result")
            body = json.loads(result.read_text())
            if damage == "malformed":
                result.write_text("{")
            elif damage == "different_identity":
                body["identity"]["action_id"] = "f" * 32
                result.write_text(json.dumps(body))
            elif damage == "foreign_store":
                for kind in ("claim", "result"):
                    path = root / aa.artifact_name(identity.action_id, kind)
                    value = json.loads(path.read_text())
                    value["identity"]["store_inode"] += 1
                    path.write_text(json.dumps(value))
            elif damage == "unknown":
                body["effect_state"] = "EFFECT_UNKNOWN"
                result.write_text(json.dumps(body))
            elif damage == "symlink":
                target = tmp_path / "external-result"
                result.rename(target)
                result.symlink_to(target)
            else:
                result.write_bytes(b"x" * (aa.MAX_RESULT_BYTES + 1))
            with pytest.raises(aa.ActionArtifactUncertain):
                aa.require_terminal_store_effects(store, writer)
    finally:
        os.close(fd)


@pytest.mark.parametrize("budget", ["MAX_EFFECT_FENCE_ENTRIES", "MAX_EFFECT_FENCE_BYTES"])
def test_partial_census_refuses_on_budget_exhaustion(tmp_path: Path, monkeypatch, budget: str):
    fd, store, identity, _root = _store(tmp_path)
    try:
        with aa.acquire_store_writer(store) as writer:
            _terminal(store, identity)
            monkeypatch.setattr(aa, budget, 1)
            with pytest.raises(aa.ActionArtifactUncertain):
                aa.require_terminal_store_effects(store, writer)
    finally:
        os.close(fd)


def test_fence_requires_live_matching_writer(tmp_path: Path):
    fd, store, _identity, _root = _store(tmp_path)
    try:
        with aa.acquire_store_writer(store) as writer:
            other_view = aa.adopt_artifact_store(fd)
            with pytest.raises(aa.ActionArtifactUncertain):
                aa.require_terminal_store_effects(other_view, writer)
        with pytest.raises(aa.ActionArtifactUncertain):
            aa.require_terminal_store_effects(store, writer)
    finally:
        os.close(fd)


def test_fresh_process_still_reads_original_pending_claim(tmp_path: Path):
    fd, store, identity, root = _store(tmp_path)
    try:
        with aa.acquire_store_writer(store):
            aa.claim_action(store, identity, claimed_at_ms=1000)
        script = '''
import os,sys
from integrations.workbench_action_mcp import action_artifacts as aa
fd=os.open(sys.argv[1], os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
try:
    store=aa.adopt_artifact_store(fd)
    with aa.acquire_store_writer(store) as writer:
        try:
            aa.require_terminal_store_effects(store, writer)
        except aa.ActionArtifactUncertain:
            print("BLOCKED_ORIGINAL_EVIDENCE")
        else:
            raise SystemExit("unsafe clearance")
finally:
    os.close(fd)
'''
        result = subprocess.run([sys.executable, "-c", script, str(root)],
                                capture_output=True, text=True, timeout=10, check=False)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "BLOCKED_ORIGINAL_EVIDENCE"
        assert sorted(p.name for p in root.iterdir()) == [identity.action_id + ".claim"]
    finally:
        os.close(fd)
