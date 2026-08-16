from __future__ import annotations

import json
from pathlib import Path

from scripts.ohf.codex_app_server_probe import run_codex_app_server_probe
from scripts.ohf.fake_app_server import SECRET_FIXTURE
from scripts.ohf.laboratory import Laboratory
from scripts.ohf.probe_schema import observation_status, validate_probe
from scripts.ohf.redaction import evidence_contains_secret


def _run(tmp_path: Path, monkeypatch=None) -> dict:
    lab = Laboratory(root=tmp_path, backend="fake")
    return run_codex_app_server_probe(lab)


def test_fake_commission_answers_p0_questions(tmp_path):
    probe = _run(tmp_path)
    assert validate_probe(probe) == []
    assert probe["capabilities"]["persistent_session"] == "pass"
    assert probe["capabilities"]["resume"] == "pass"
    assert probe["capabilities"]["fork"] == "pass"
    assert probe["capabilities"]["skills"] == "pass"
    assert probe["capabilities"]["mcp"] == "pass"
    assert probe["recovery"]["process_restart"] == "pass"
    assert probe["recovery"]["session_resume"] == "pass"
    assert probe["recovery"]["workspace_continuity"] == "pass"
    assert probe["usage"]["classification"] == "provider_reported"
    assert probe["usage"]["used_percent"] == 11
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
    notes = " ".join(probe["notes"])
    assert "process died; native session survived" in notes
    assert "missing native session reference failed closed" in notes
    assert "workspace disappearance failed closed" in notes
    assert "MCP disappearance reported as degraded capability" in notes


def test_leaked_harness_secrets_never_reach_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("OHF_FAKE_LEAK", "1")
    probe = _run(tmp_path, monkeypatch)
    blob = json.dumps(probe)
    assert SECRET_FIXTURE not in blob
    assert not evidence_contains_secret(probe)
    assert probe["security"]["credential_exposure"] is False
