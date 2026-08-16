from __future__ import annotations

from scripts.ohf.codex_app_server_probe import run_codex_app_server_probe
from scripts.ohf.laboratory import Laboratory
from scripts.ohf.probe_schema import (
    attest_manifests,
    requested_capability_manifest,
    observed_capability_manifest,
    validate_probe,
)


def _base_requested(**overrides):
    payload = requested_capability_manifest(
        model="gpt-5.6-sol",
        skills=["ohf-probe"],
        mcp_servers=["ohf_probe"],
        mcp_tools=["ohf_probe_echo"],
        plugins=[],
        approval_policy="never",
        sandbox_mode="read-only",
    )
    payload.update(overrides)
    return payload


def _base_observed(**overrides):
    payload = observed_capability_manifest(
        model="gpt-5.6-sol",
        skills=["ohf-probe"],
        mcp_servers=["ohf_probe"],
        mcp_tools=["ohf_probe_echo"],
        plugins=[],
        approval_policy="never",
        sandbox_mode="read-only",
        harness_version="ohf-fake-app-server/p0b",
    )
    payload.update(overrides)
    return payload


def test_missing_required_skill_fails_attestation():
    result = attest_manifests(_base_requested(), _base_observed(skills=[]))
    assert result["config_attested"] is False
    assert result["missing_required_skills"] == ["ohf-probe"]


def test_missing_required_mcp_fails_attestation():
    result = attest_manifests(_base_requested(), _base_observed(mcp_servers=[]))
    assert result["config_attested"] is False
    assert result["missing_required_mcp"] == ["ohf_probe"]


def test_served_model_mismatch_fails_attestation():
    result = attest_manifests(_base_requested(), _base_observed(model="gpt-4.1"))
    assert result["config_attested"] is False
    assert result["model_match"] is False
    assert result["unexpected_model_override"] is True


def test_unexpected_skill_fails_attestation():
    result = attest_manifests(_base_requested(), _base_observed(skills=["ohf-probe", "secret-skill"]))
    assert result["config_attested"] is False
    assert result["unexpected_skills"] == ["secret-skill"]


def test_unexpected_mcp_fails_attestation():
    result = attest_manifests(_base_requested(), _base_observed(mcp_servers=["ohf_probe", "github"]))
    assert result["config_attested"] is False
    assert result["unexpected_mcp"] == ["github"]


def test_unexpected_plugin_fails_attestation():
    result = attest_manifests(_base_requested(), _base_observed(plugins=["browser"]))
    assert result["config_attested"] is False
    assert result["unexpected_plugins"] == ["browser"]


def test_unobservable_model_is_not_implicitly_accepted():
    result = attest_manifests(_base_requested(), _base_observed(model=""), unobservable=["model"])
    assert result["model_match"] == "UNKNOWN"
    assert result["config_attested"] is False
    assert "model" in result["unobservable_dimensions"]


def test_flat_skills_env_prevents_skill_attestation(tmp_path, monkeypatch):
    monkeypatch.setenv("OHF_FAKE_FLAT_SKILLS", "1")
    probe = run_codex_app_server_probe(Laboratory(root=tmp_path, backend="fake"))
    assert probe["skill_attestation"]["discovered"] is False
    assert probe["attestation"]["config_attested"] is False
    assert "ohf-probe" in probe["attestation"]["missing_required_skills"]


def test_cleanup_verified_without_census_fails_schema(tmp_path):
    probe = run_codex_app_server_probe(Laboratory(root=tmp_path, backend="fake"))
    probe["recovery"]["transitive_orphan_cleanup"] = "VERIFIED"
    probe["cleanup_proof"]["descendant_census"] = False
    assert "recovery.transitive_orphan_cleanup_unproven" in validate_probe(probe)
    probe["recovery"]["main_process_cleanup"] = "VERIFIED"
    probe["cleanup_proof"]["main_pid_exited"] = False
    assert "recovery.main_process_cleanup_unproven" in validate_probe(probe)
