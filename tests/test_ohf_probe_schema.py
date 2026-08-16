from __future__ import annotations

import json

from scripts.ohf.probe_schema import (
    SCHEMA_VERSION,
    new_probe,
    render_markdown,
    validate_probe,
    write_evidence,
    add_observation,
)


def test_new_probe_validates():
    probe = new_probe(probe_id="ohf-p0-test", harness_kind="codex-app-server")
    add_observation(probe, question_id="launch", status="VERIFIED", summary="started")
    assert validate_probe(probe) == []
    assert probe["schema_version"] == SCHEMA_VERSION
    assert probe["capabilities"]["fork"] == "unknown"
    assert probe["usage"]["classification"] == "unknown"


def test_markdown_uses_explicit_statuses_only():
    probe = new_probe(probe_id="ohf-p0-md", harness_kind="codex-app-server")
    add_observation(probe, question_id="launch", status="VERIFIED", summary="up")
    add_observation(probe, question_id="fork", status="NOT_SUPPORTED", summary="no fork rpc")
    add_observation(probe, question_id="usage_quota", status="NOT_TESTED", summary="no telemetry")
    add_observation(probe, question_id="attest_mcp", status="DEGRADED", summary="listed, not invoked")
    md = render_markdown(probe)
    assert "**VERIFIED**" in md
    assert "**NOT_SUPPORTED**" in md
    assert "**NOT_TESTED**" in md
    assert "**DEGRADED**" in md
    assert "probably" not in md.lower()
    assert "likely" not in md.lower()


def test_usage_percent_requires_provider_source():
    probe = new_probe(probe_id="ohf-p0-usage", harness_kind="codex-app-server")
    probe["usage"]["classification"] = "unknown"
    probe["usage"]["used_percent"] = 40
    assert "usage.used_percent_without_provider_source" in validate_probe(probe)
    probe["usage"]["classification"] = "provider_reported"
    assert "usage.used_percent_without_provider_source" not in validate_probe(probe)


def test_write_evidence_pair(tmp_path):
    probe = new_probe(probe_id="ohf-p0-write", harness_kind="codex-app-server")
    add_observation(probe, question_id="inert", status="VERIFIED", summary="no executive writes")
    json_path, md_path = write_evidence(probe, tmp_path)
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["probe_id"] == "ohf-p0-write"
    assert "OHF-P0" in md_path.read_text(encoding="utf-8")


def test_rejects_auth_material_in_document():
    probe = new_probe(probe_id="ohf-p0-bad", harness_kind="codex-app-server")
    probe["notes"].append("access_token=abc")
    assert any(item.startswith("forbidden_token:") for item in validate_probe(probe))
