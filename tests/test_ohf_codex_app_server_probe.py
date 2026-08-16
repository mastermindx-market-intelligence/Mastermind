from __future__ import annotations

import json
from pathlib import Path

from scripts.ohf.codex_app_server_probe import run_codex_app_server_probe
from scripts.ohf.laboratory import Laboratory
from scripts.ohf.probe_schema import OBSERVATION_STATUSES, observation_status, validate_probe
from scripts.ohf.redaction import evidence_contains_secret

UNTRUSTED_BLOB = "sk-ohf-probe-fixture-" + ("A" * 24)


def _run(tmp_path: Path) -> dict:
    lab = Laboratory(root=tmp_path, backend="fake")
    return run_codex_app_server_probe(lab)


def test_fake_commission_answers_p0_questions(tmp_path):
    probe = _run(tmp_path)
    assert validate_probe(probe) == []
    assert probe["schema_version"] == "mastermind.ohf_harness_probe/v1.1"
    assert probe["capabilities"]["persistent_session"] == "pass"
    assert probe["capabilities"]["resume"] == "pass"
    assert probe["capabilities"]["fork"] == "pass"
    assert probe["capabilities"]["skills"] == "pass"
    assert probe["capabilities"]["mcp"] == "pass"
    assert probe["recovery"]["process_sigkill_resume"] == "VERIFIED"
    assert probe["recovery"]["process_sigterm_resume"] == "VERIFIED"
    assert probe["recovery"]["malformed_rpc_recovery"] == "VERIFIED"
    assert probe["recovery"]["missing_session_fail_closed"] == "VERIFIED"
    assert probe["recovery"]["workspace_missing_fail_closed"] == "VERIFIED"
    assert probe["recovery"]["config_drift_detected"] == "VERIFIED"
    assert probe["recovery"]["mcp_disappearance_detected"] == "VERIFIED"
    assert probe["recovery"]["main_process_cleanup"] == "VERIFIED"
    assert probe["recovery"]["transitive_orphan_cleanup"] == "UNKNOWN"
    assert probe["usage"]["classification"] == "provider_reported"
    assert probe["quota"]["primary"]["used_percent"] == 11
    assert probe["quota"]["secondary"]["used_percent"] == 4
    assert observation_status(probe, "launch") == "VERIFIED"
    assert observation_status(probe, "durable_session") == "VERIFIED"
    assert observation_status(probe, "identify") == "VERIFIED"
    assert observation_status(probe, "process_restart") == "VERIFIED"
    assert observation_status(probe, "resume") == "VERIFIED"
    assert observation_status(probe, "fork") == "VERIFIED"
    assert observation_status(probe, "attest_skills") == "VERIFIED"
    assert observation_status(probe, "attest_mcp") == "VERIFIED"
    assert observation_status(probe, "config_drift") == "VERIFIED"
    assert observation_status(probe, "cleanup") == "VERIFIED"
    assert observation_status(probe, "inert") == "VERIFIED"
    assert probe["session_continuity"]["initial_pid"] != probe["session_continuity"]["replacement_pid"]
    assert probe["session_continuity"]["native_thread_survived"] is True
    assert probe["fork_proof"]["independent_continuation_proven"] is True
    assert probe["skill_attestation"]["invoked_successfully"] is True
    assert probe["mcp_attestation"]["tool_callable"] is True
    assert probe["attestation"]["config_attested"] is True
    assert probe["provider"]["auth_type"] == "chatgpt"
    assert probe["provider"]["plan_type"] == "plus"
    blob = json.dumps(probe)
    assert "probe-fixture@example.invalid" not in blob
    assert "authMode" not in blob
    assert probe["auth_isolation"]["auth_json_copied"] is False
    assert probe["auth_isolation"]["auth_json_symlinked"] is False
    assert probe["auth_isolation"]["implicit_default_home_fallback"] is False


def test_mcp_disappearance_does_not_rewrite_initial_capability(tmp_path):
    probe = _run(tmp_path)
    assert probe["capabilities"]["mcp"] == "pass"
    assert probe["recovery"]["mcp_disappearance_detected"] == "VERIFIED"
    notes = " ".join(probe["notes"])
    assert probe["recovery"]["mcp_disappearance_detected"] in OBSERVATION_STATUSES
    assert "mcp_disappearance_detected" not in notes or probe["recovery"]["mcp_disappearance_detected"] == "VERIFIED"


def test_leaked_harness_secrets_never_reach_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("OHF_FAKE_LEAK", "1")
    monkeypatch.setenv("OHF_FAKE_UNTRUSTED_BLOB", UNTRUSTED_BLOB)
    probe = _run(tmp_path)
    blob = json.dumps(probe)
    assert UNTRUSTED_BLOB not in blob
    assert not evidence_contains_secret(probe)
    assert probe["security"]["credential_exposure"] is False
