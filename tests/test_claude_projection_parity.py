"""Adversarial source-only parity tests; no native/provider or runtime proof."""
from __future__ import annotations

import copy
import dataclasses
import json
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from scripts import check_claude_projection_parity as checker

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "operator.appserver.readonly.docs-mcp.v1"
COMPANY_PROFILE = "operator.appserver.interactive.company-mcp.v1"


@pytest.fixture
def manifest():
    return checker.load_manifest(ROOT / checker.MANIFEST)


def test_committed_manifest_matches_canonical_registry_and_projector(manifest):
    result = checker.validate_manifest(manifest, source_root=ROOT)
    assert result["ok"] is True
    assert result["surface_counts"]["configuration_supported"] > 0
    assert result["production_armed"] is False
    assert result["native_admission_proven"] is False
    assert result["observed_tool_catalog_attested"] is False


@pytest.mark.parametrize("field,value", [
    ("schema_version", "future"),
    ("claim_scope", "native_admission"),
    ("production_armed", True),
    ("production_armed", 0),
    ("policy_path", "scripts/ohf/fixtures/executive_agent_capabilities_v4_mastermind_operator.json"),
    ("policy_schema_version", "future"),
    ("projection_source_sha256", "0" * 64),
])
def test_root_claim_and_source_drift_refuse(manifest, field, value):
    manifest[field] = value
    with pytest.raises(checker.ParityError):
        checker.validate_manifest(manifest, source_root=ROOT)


def test_unknown_root_authority_field_refuses(manifest):
    manifest["auto_admit"] = True
    with pytest.raises(checker.ParityError, match="fields"):
        checker.validate_manifest(manifest, source_root=ROOT)


@pytest.mark.parametrize("change", ["remove", "add"])
def test_profile_inventory_requires_explicit_reclassification(manifest, change):
    if change == "remove":
        del manifest["profiles"][PROFILE]
    else:
        manifest["profiles"]["principal.claude.coo.future.v2"] = {}
    with pytest.raises(checker.ParityError, match="inventory"):
        checker.validate_manifest(manifest, source_root=ROOT)


@pytest.mark.parametrize("field,value", [
    ("profile_digest", "0" * 64),
    ("package_generation_digests", {"unknown-package": "0" * 64}),
])
def test_exact_profile_and_package_generations_refuse_drift(manifest, field, value):
    manifest["profiles"][PROFILE][field] = value
    with pytest.raises(checker.ParityError, match="generation drift"):
        checker.validate_manifest(manifest, source_root=ROOT)


@pytest.mark.parametrize("surface", checker.SURFACES)
def test_every_surface_requires_a_classification(manifest, surface):
    del manifest["profiles"][PROFILE]["surfaces"][surface]
    with pytest.raises(checker.ParityError, match="every Claude surface"):
        checker.validate_manifest(manifest, source_root=ROOT)


@pytest.mark.parametrize("value", [True, [], "live", "", None])
def test_unknown_status_cannot_silently_widen_support(manifest, value):
    manifest["profiles"][PROFILE]["surfaces"]["cli"]["status"] = value
    with pytest.raises(checker.ParityError, match="classification"):
        checker.validate_manifest(manifest, source_root=ROOT)


@pytest.mark.parametrize("value", ["", "  ", None, False])
def test_classification_requires_nonempty_reason(manifest, value):
    manifest["profiles"][PROFILE]["surfaces"]["cli"]["reason"] = value
    with pytest.raises(checker.ParityError, match="reason"):
        checker.validate_manifest(manifest, source_root=ROOT)


@pytest.mark.parametrize("field,value", [
    ("configuration_sha256", "0" * 64),
    ("source_profile_id", "wrong-principal"),
    ("source_profile_digest", "0" * 64),
    ("source_grant_digests", []),
    ("source_tool_schema_digests", []),
    ("enabled_tools", ["mcp__executive__submit_ceo_intent"]),
    ("auto_approved_tools", []),
    ("denied_tools", ["different"]),
    ("cli_arguments_sha256", "0" * 64),
    ("production_armed", True),
    ("production_armed", 0),
])
def test_projection_output_or_security_schema_drift_refuses(manifest, field, value):
    manifest["profiles"][PROFILE]["surfaces"]["cli"]["projection"][field] = value
    with pytest.raises(checker.ParityError, match="projection drift"):
        checker.validate_manifest(manifest, source_root=ROOT)


def test_deliberate_defer_is_supported_without_auto_adding_tools(manifest):
    manifest["profiles"][PROFILE]["surfaces"]["cli"] = {
        "status": "deferred", "reason": "Exact new generation needs owner qualification.",
    }
    assert checker.validate_manifest(manifest, source_root=ROOT)["ok"] is True


def test_new_company_mcp_profile_is_explicitly_deferred_for_every_claude_surface(manifest):
    registry = ExecutionCapabilityRegistry.load(ROOT / checker.POLICY, source_root=ROOT)
    profile = registry.profiles[COMPANY_PROFILE]
    assert profile.enabled is False
    assert profile.execution_surface == "codex-app-server"
    assert profile.mcp_servers == ("company-consultation-mcp-v1",)
    row = manifest["profiles"][COMPANY_PROFILE]
    assert row["profile_digest"] == profile.profile_digest
    assert row["package_generation_digests"] == {}
    for surface in checker.SURFACES:
        entry = row["surfaces"][surface]
        assert entry["status"] == "deferred"
        assert "separate reviewed profile/native binding qualification" in entry["reason"]
        assert "projection" not in entry


def test_deferral_cannot_retain_a_stale_projection(manifest):
    manifest["profiles"][PROFILE]["surfaces"]["cli"]["status"] = "deferred"
    with pytest.raises(checker.ParityError, match="fields"):
        checker.validate_manifest(manifest, source_root=ROOT)


def test_sealed_workers_cannot_gain_a_supported_extension_by_manifest(manifest):
    sealed = "sealed.worker.claude.readonly.no-extensions.v1"
    manifest["profiles"][sealed]["surfaces"]["cli"] = copy.deepcopy(
        manifest["profiles"][PROFILE]["surfaces"]["cli"])
    with pytest.raises(checker.ParityError, match="sealed"):
        checker.validate_manifest(manifest, source_root=ROOT)


def test_desktop_or_inline_cannot_inherit_static_cli_qualification(manifest):
    manifest["profiles"][PROFILE]["surfaces"]["desktop-local"] = copy.deepcopy(
        manifest["profiles"][PROFILE]["surfaces"]["cli"])
    with pytest.raises(checker.ParityError, match="only qualifies CLI"):
        checker.validate_manifest(manifest, source_root=ROOT)


def test_existing_v4_package_generation_is_in_parity_closure():
    registry = ExecutionCapabilityRegistry.load(
        ROOT / "scripts/ohf/fixtures/executive_agent_capabilities_v4_mastermind_operator.json",
        source_root=ROOT,
    )
    profile = registry.resolve("operator.appserver.readonly.mastermind-operator.v1")
    before = checker.profile_expectation(registry, profile)
    packages = dict(registry.capability_packages)
    key = profile.skill_grants[0].package_capability_id
    packages[key] = dataclasses.replace(packages[key], package_generation_digest="0" * 64)
    changed = dataclasses.replace(registry, capability_packages=packages)
    assert checker.profile_expectation(changed, profile) != before


def test_duplicate_json_keys_refuse(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text('{"production_armed":false,"production_armed":true}')
    with pytest.raises(checker.ParityError, match="duplicate"):
        checker.load_manifest(path)


def test_cli_reports_inert_scope_and_never_updates_manifest(capsys):
    before = (ROOT / checker.MANIFEST).read_bytes()
    assert checker.main(["--source-root", str(ROOT)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["native_admission_proven"] is False
    assert (ROOT / checker.MANIFEST).read_bytes() == before


def test_cli_missing_manifest_fails_closed(capsys):
    assert checker.main(["--manifest", "does-not-exist.json"]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_source_path_cannot_escape_repository(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "outside.json").write_text("{}")
    with pytest.raises(checker.ParityError, match="inside"):
        checker._inside(root, "../outside.json")


def test_checker_cannot_claim_another_checkout(manifest, tmp_path):
    with pytest.raises(checker.ParityError, match="checkout"):
        checker.validate_manifest(manifest, source_root=tmp_path)


def test_new_guard_is_in_existing_ci_gate():
    from scripts.ci_pytest import resolve_gate

    gate = resolve_gate(ROOT)
    assert "tests/test_claude_projection_parity.py" in gate["included"]
