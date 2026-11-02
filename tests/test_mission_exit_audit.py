"""Deterministic regressions for the read-only mission-exit evidence auditor."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.ohf.mission_exit_audit import (
    REQUIREMENTS, InvalidSnapshot, audit, main, OUTPUT_SCHEMA,
)

FIXTURE = Path(__file__).resolve().parents[1] / "research/fixtures/mission_exit_byteplus_20261101.json"


def snapshot():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_byteplus_terminal_analysis_is_not_release_or_accepted_work():
    report = audit(snapshot())
    assert report["disposition"] == "INCOMPLETE"
    assert report["analysis_is_not_implementation"] is True
    assert report["terminal_exit_is_not_acceptance"] is True
    assert {g["requirement"] for g in report["gaps"]} == {
        "accepted_worker_result", "source_implementation",
        "credential_owner_attestation", "governed_production_result",
    }
    assert report["checks_passed"] == ["current_head_ci", "independent_source_review"]
    assert report["held_actions"][0]["effect_class"] == "SAFETY_DENIED"
    assert "do not retry" in report["held_actions"][0]["instruction"]
    assert all(report[flag] is False for flag in (
        "source_write_authorized", "dispatch_authorized", "retry_authorized",
        "merge_authorized", "production_activation_authorized"
    ))


def test_validated_analysis_without_implementation_still_has_source_gap():
    data = snapshot()
    data["worker"].update(accepted=True, result_ref="fabric:original-result", acceptance_ref="fabric:acceptance")
    report = audit(data)
    assert "accepted_worker_result" in report["checks_passed"]
    assert "source_implementation" in {g["requirement"] for g in report["gaps"]}


def test_source_head_or_ci_movement_invalidates_previous_proofs():
    data = snapshot()
    data["source"]["head"] = "0" * 40
    report = audit(data)
    assert "current_head_ci" in {g["requirement"] for g in report["gaps"]}
    assert "independent_source_review" in {g["requirement"] for g in report["gaps"]}


def test_self_review_not_independent():
    data = snapshot()
    data["source"]["reviewer_id"] = data["source"]["author_id"]
    assert "independent_source_review" in {g["requirement"] for g in audit(data)["gaps"]}


def test_implementation_requires_specific_current_head_and_scope_receipt():
    data = snapshot()
    data["source"].update(implementation_applied=True, implementation_ref="github:head", implementation_scope_matched=True)
    assert "source_implementation" in {g["requirement"] for g in audit(data)["gaps"]}
    data["source"]["implementation_head"] = data["source"]["head"]
    assert "source_implementation" in audit(data)["checks_passed"]


def test_production_requires_generation_attempt_and_parent_consumption():
    data = snapshot()
    data["production"].update(job_attempt_accepted=True, job_attempt_ref="exec:JOB-1")
    assert "governed_production_result" in {g["requirement"] for g in audit(data)["gaps"]}


def test_effect_unknown_is_sticky_and_not_reroutable():
    data = snapshot()
    data["effect"]["class"] = "EFFECT_UNKNOWN"
    data["effect"]["dispatched"] = None
    result = audit(data)
    assert result["retry_authorized"] is False
    assert "reconcile only through original carrier" in result["held_actions"][0]["instruction"]


def test_true_packet_only_ready_for_adjudication_not_automatically_approved():
    data = snapshot()
    data["effect"] = {"class": "NONE"}
    data["worker"].update(scope="implementation", accepted=True, acceptance_ref="fab:accepted", result_ref="fab:result")
    data["source"].update(implementation_applied=True, implementation_ref="git:subject", implementation_head=data["source"]["head"], implementation_scope_matched=True)
    data["credential"].update(issuer_activation_verified=True, issuer_evidence_ref="issuer:attested", owner_identified=True, owner_ref="realm:owner")
    data["production"].update(job_attempt_accepted=True, job_attempt_ref="exec:attempt", original_parent_consumed=True, parent_consumption_ref="exec:parent", installed_generation_qualified=True, generation_ref="install:sha")
    out = audit(data)
    assert out["disposition"] == "READY_FOR_CANONICAL_ADJUDICATION"
    assert out["gaps"] == []
    assert set(out["checks_passed"]) == set(REQUIREMENTS)
    assert out["fresh_owner_readback_required"] is True
    assert out["merge_authorized"] is False


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(schema="wrong"),
    lambda d: d["mission"].update(requires=[]),
    lambda d: d["mission"].update(requires=["source_implementation", "source_implementation"]),
    lambda d: d["mission"].update(requires=["new_unknown_gate"]),
    lambda d: d["worker"].update(scope="magic"),
    lambda d: d["worker"].update(scope=[]),
    lambda d: d["worker"].update(state="SUCCESS"),
    lambda d: d["worker"].update(state={}),
    lambda d: d["effect"].update(**{"class": []}),
    lambda d: d["worker"].update(exit_code=True),
    lambda d: d["source"].update(head="branch-name"),
    lambda d: d["effect"].update(action_id=None),
    lambda d: d["effect"].update(dispatched="unknown"),
    lambda d: d["effect"].update(dispatched=1),
])
def test_malformed_packets_refused(mutation):
    data = snapshot()
    mutation(data)
    with pytest.raises(InvalidSnapshot):
        audit(data)


def test_cli_negative_exit_without_secret_echo(tmp_path, capsys):
    file = tmp_path / "packet.json"
    file.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    assert main([str(file)]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["schema"] == OUTPUT_SCHEMA
    file.write_text('bad-json-sensitive_token_123', encoding="utf-8")
    assert main([str(file)]) == 2
    emitted = capsys.readouterr().out
    assert "sensitive_token" not in emitted
    assert json.loads(emitted)["disposition"] == "INPUT_UNVERIFIED"


def test_cli_unhashable_enum_is_typed_input_error(tmp_path, capsys):
    data = snapshot()
    data["worker"]["scope"] = []
    file = tmp_path / "packet.json"
    file.write_text(json.dumps(data), encoding="utf-8")
    assert main([str(file)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result == {"schema": OUTPUT_SCHEMA, "disposition": "INPUT_UNVERIFIED", "error": "invalid_or_unreadable_snapshot"}
