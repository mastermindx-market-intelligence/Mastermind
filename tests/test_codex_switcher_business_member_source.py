"""Hosted-safe source-only proof for the Codex Switcher member token guard.

The native Mac Switcher checkout is intentionally NOT part of Mastermind CI.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ops.native_fabric.verify_codex_switcher_business_member_source import (
    MANIFEST,
    PATCH,
    PATHS,
    read_bundle,
    verify_original,
)


def test_exact_digest_bound_source_patch_is_present():
    document = read_bundle()
    assert document["schema"] == "mastermind.switcher_member_token_guard_source/v1"
    assert document["status"] == "candidate_not_installed"
    assert set(document["modified_paths"]) == PATHS
    assert document["source_base_git_sha"] != document["source_candidate_git_sha"]
    assert document["rust_unit_tests_passed"] == 78
    assert document["rust_unit_tests_failed"] == 0
    assert document["rust_unit_tests_ignored"] == 1
    assert document["installed_app_modified"] is False
    assert document["production_credentials_modified"] is False


def test_patch_only_changes_bounded_switcher_source_and_synthetic_tests():
    patch = PATCH.read_text()
    assert patch.count("diff --git a/") == 2
    for path in PATHS:
        assert f"diff --git a/{path} b/{path}" in patch
    for target in ("src-tauri/src/auth.json", "src-tauri/src/auth/accounts.json",
                   "Cargo.toml", "Cargo.lock", ".github/", "launchd",
                   "install.sh", "node_modules/"):
        assert f"diff --git a/{target}" not in patch
    assert "matching_oauth_subscription_member" in patch
    assert "replace_account_oauth_credentials" in patch
    assert "same_business_workspace_different_member_refuses_token_rebinding" in patch
    assert "direct_refresh_cannot_overwrite_different_business_member_credentials" in patch
    assert "same_business_workspace_same_member_preserves_single_use_rotation" in patch


def test_tampered_patch_bytes_are_never_authority(tmp_path):
    original = json.loads(MANIFEST.read_text())
    manifest_path = tmp_path / "manifest.json"
    patch_path = tmp_path / "candidate.patch"
    manifest_path.write_text(json.dumps(original))
    patch_path.write_bytes(PATCH.read_bytes() + b"\n# unexpected data\n")
    with pytest.raises(ValueError, match="BUNDLE_PATCH_CHANGED"):
        read_bundle(manifest_path, patch_path)


def test_fake_source_root_is_refused_without_rewriting_it(tmp_path):
    before = {}
    for path in PATHS:
        file = tmp_path / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("old-code")
        before[path] = file.read_bytes()
    with pytest.raises(ValueError, match="ORIGINAL_SOURCE_PREIMAGE_DRIFT"):
        verify_original(tmp_path)
    for path, body in before.items():
        assert (tmp_path / path).read_bytes() == body


def test_manifest_cannot_claim_installed_app_or_provider_execution(tmp_path):
    document = json.loads(MANIFEST.read_text())
    patch_path = tmp_path / "candidate.patch"
    patch_path.write_bytes(PATCH.read_bytes())
    for key, value in (
        ("installed_app_modified", True),
        ("production_credentials_modified", True),
        ("model_turns", 1),
        ("status", "installed"),
    ):
        changed = dict(document)
        changed[key] = value
        tmp_manifest = tmp_path / "manifest.json"
        tmp_manifest.write_text(json.dumps(changed))
        with pytest.raises(ValueError, match="BUNDLE_FIELDS_REFUSED"):
            read_bundle(tmp_manifest, patch_path)
