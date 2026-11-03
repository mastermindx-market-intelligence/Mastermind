"""Deterministic regressions for the read-only mission-exit evidence auditor."""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
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


def test_cli_fifo_rejected_without_blocking(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("POSIX FIFO unavailable")
    fifo = tmp_path / "unopened.fifo"
    os.mkfifo(fifo)
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.ohf.mission_exit_audit", str(fifo)],
        cwd=FIXTURE.parents[2], text=True, capture_output=True, timeout=3,
    )
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["disposition"] == "INPUT_UNVERIFIED"
    assert proc.stderr == ""


def test_cli_symlink_not_followed(tmp_path, capsys):
    target = tmp_path / "private.json"
    target.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    link = tmp_path / "alias.json"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    assert main([str(link)]) == 2
    assert json.loads(capsys.readouterr().out)["disposition"] == "INPUT_UNVERIFIED"


def test_cli_oversized_regular_file_rejected(tmp_path, capsys):
    p = tmp_path / "too_big.json"
    p.write_bytes(b" " * 131073)
    assert main([str(p)]) == 2
    assert json.loads(capsys.readouterr().out)["disposition"] == "INPUT_UNVERIFIED"


def test_cli_growth_race_rejected(tmp_path, monkeypatch, capsys):
    import scripts.ohf.mission_exit_audit as module
    p = tmp_path / "growing.json"
    p.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    original = module.os.open

    def growing_open(file, flags, *args, **kwargs):
        p.write_bytes(b" " * 131073)
        return original(file, flags, *args, **kwargs)

    monkeypatch.setattr(module.os, "open", growing_open)
    assert main([str(p)]) == 2
    assert json.loads(capsys.readouterr().out)["disposition"] == "INPUT_UNVERIFIED"


@pytest.mark.parametrize("field,value", [
    ("action_id", "sk-abcdefghij"),
    ("carrier", "/Users/private/secret-file"),
    ("carrier", "file:///home/private"),
    ("action_id", "ghp_AbCdEfGhIjKl"),
    ("action_id", "xpl_" + "b" * 42),
    ("carrier", "token-" + "x" * 40),
])
def test_held_effect_refs_cannot_print_secret_or_path(tmp_path, capsys, field, value):
    d = snapshot()
    d["effect"][field] = value
    with pytest.raises(InvalidSnapshot):
        audit(d)
    p = tmp_path / "packet.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    assert main([str(p)]) == 2
    emitted = capsys.readouterr().out
    assert value not in emitted
    assert json.loads(emitted)["disposition"] == "INPUT_UNVERIFIED"


def test_safe_opaque_effect_identifiers_survive_exactly():
    d = snapshot()
    d["effect"].update(action_id="fabric:run", carrier="studio:carrier")
    held = audit(d)["held_actions"]
    assert held[0]["action_id"] == "fabric:run"
    assert held[0]["carrier"] == "studio:carrier"


def test_deeply_nested_json_fails_closed_without_traceback(tmp_path, capsys):
    # Legal-sized malformed JSON must not escape as RecursionError or leak input.
    p = tmp_path / "deeply_nested.json"
    p.write_text("[" * 12000 + "0" + "]" * 12000, encoding="utf-8")
    assert p.stat().st_size < 131072
    assert main([str(p)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result == {"schema": OUTPUT_SCHEMA, "disposition": "INPUT_UNVERIFIED", "error": "invalid_or_unreadable_snapshot"}


# Pending evidence is not a reason to create another operation.
def _gap_guidance(data, requirement):
    report = audit(data)
    assert all(report[key] is False for key in (
        "source_write_authorized", "dispatch_authorized", "retry_authorized",
        "merge_authorized", "production_activation_authorized",
    ))
    return next(g["next_proof"] for g in report["gaps"]
                if g["requirement"] == requirement)


@pytest.mark.parametrize("state", ["QUEUED", "PENDING", "IN_PROGRESS", "WAITING", "REQUESTED"])
def test_pending_current_head_ci_consumes_original_run_without_rerun(state):
    data = snapshot()
    data["source"].update(ci_conclusion=state, ci_run_ref="github:existing-ci")
    guidance = _gap_guidance(data, "current_head_ci")
    assert "existing current-head CI run" in guidance
    assert "do not rerun" in guidance
    assert "original" in guidance
    assert "run and inspect CI" not in guidance
    assert "current_head_ci" not in audit(data)["checks_passed"]


@pytest.mark.parametrize("state", ["FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"])
def test_terminal_ci_failure_is_diagnosed_not_blindly_retried(state):
    data = snapshot()
    data["source"].update(ci_conclusion=state, ci_run_ref="github:existing-ci")
    guidance = _gap_guidance(data, "current_head_ci")
    assert "original CI result" in guidance
    assert "no blind retry" in guidance


def test_stale_current_head_ci_observation_requires_reconciliation_not_repair():
    data = snapshot()
    data["source"].update(ci_conclusion="STALE", ci_run_ref="github:existing-ci")
    guidance = _gap_guidance(data, "current_head_ci")
    assert "reconcile current-head CI identity and state with GitHub" in guidance
    assert "identify a permitted repair" not in guidance
    assert "current_head_ci" not in audit(data)["checks_passed"]
    assert audit(data)["retry_authorized"] is False


@pytest.mark.parametrize("state", [None, "unrecognized", [], {}])
def test_unknown_ci_state_requires_reconciliation_not_inferred_failure(state):
    data = snapshot()
    data["source"].update(ci_conclusion=state, ci_run_ref="github:existing-ci")
    guidance = _gap_guidance(data, "current_head_ci")
    assert "reconcile" in guidance
    assert "missing evidence is not a failed build" in guidance


def test_stale_or_unbound_pending_ci_never_looks_like_current_execution():
    for field, value in (("ci_head", "0" * 40), ("ci_run_ref", None)):
        data = snapshot()
        data["source"].update(ci_conclusion="IN_PROGRESS", ci_run_ref="github:existing-ci")
        data["source"][field] = value
        guidance = _gap_guidance(data, "current_head_ci")
        assert "existing current-head CI run" not in guidance
        assert "reconcile" in guidance
        assert "current_head_ci" not in audit(data)["checks_passed"]


@pytest.mark.parametrize("state", ["REQUESTED", "PENDING", "IN_PROGRESS"])
def test_pending_review_does_not_commission_duplicate_or_claim_approval(state):
    data = snapshot()
    data["source"].update(review_verdict=state, review_ref="github:original-review")
    guidance = _gap_guidance(data, "independent_source_review")
    if state == "IN_PROGRESS":
        assert "active current-head review" in guidance
        assert "original carrier" in guidance
        assert "execution is not approval" in guidance
    else:
        assert "existing current-head review request" in guidance
        assert "request is not execution or approval" in guidance
    assert "do not duplicate" in guidance
    assert "independent_source_review" not in audit(data)["checks_passed"]


def test_changes_requested_means_repair_findings_not_repeat_review():
    data = snapshot()
    data["source"].update(review_verdict="CHANGES_REQUESTED", review_ref="github:original-review")
    guidance = _gap_guidance(data, "independent_source_review")
    assert "repair the existing findings" in guidance
    assert "stable changed head" in guidance


@pytest.mark.parametrize("state", ["QUEUED", "STARTED", "UNKNOWN"])
def test_existing_worker_is_reconciled_without_replacement(state):
    data = snapshot()
    data["worker"].update(state=state, exit_code=None)
    guidance = _gap_guidance(data, "accepted_worker_result")
    assert "original worker" in guidance
    assert "do not submit a replacement" in guidance
    assert "accepted_worker_result" not in audit(data)["checks_passed"]


@pytest.mark.parametrize("exit_code", [0, 1, 78])
def test_terminal_worker_result_is_consumed_without_automatic_relaunch(exit_code):
    data = snapshot()
    data["worker"].update(state="TERMINAL", exit_code=exit_code, accepted=False)
    guidance = _gap_guidance(data, "accepted_worker_result")
    assert "original terminal" in guidance
    assert "do not relaunch" in guidance
    assert "accepted_worker_result" not in audit(data)["checks_passed"]


def test_dynamic_guidance_never_echoes_untrusted_refs_or_changes_denial_fence():
    data = snapshot()
    secret = "private-test-sentinel-not-for-output"
    data["source"].update(ci_conclusion="IN_PROGRESS", ci_run_ref=secret,
                          review_verdict="PENDING", review_ref=secret)
    result = audit(data)
    assert secret not in json.dumps(result)
    assert result["held_actions"][0]["effect_class"] == "SAFETY_DENIED"
    assert result["retry_authorized"] is False


@pytest.mark.parametrize("field,value", [
    ("review_head", "0" * 40), ("review_ref", None),
    ("reviewer_id", None), ("author_id", None),
])
def test_unbound_pending_review_requires_identity_reconciliation(field, value):
    data = snapshot()
    data["source"].update(review_verdict="PENDING", review_ref="github:original-review")
    data["source"][field] = value
    guidance = _gap_guidance(data, "independent_source_review")
    assert "existing current-head review" not in guidance
    assert "reconcile" in guidance


def test_self_requested_review_is_not_an_eligible_pending_independent_review():
    data = snapshot()
    data["source"].update(review_verdict="REQUESTED", review_ref="github:self-request")
    data["source"]["reviewer_id"] = data["source"]["author_id"]
    guidance = _gap_guidance(data, "independent_source_review")
    assert "existing current-head review" not in guidance
    assert "reconcile" in guidance


def test_cli_reports_original_pending_work_without_creating_authority(tmp_path):
    data = snapshot()
    data["source"].update(ci_conclusion="QUEUED", ci_run_ref="github:existing-ci",
                          review_verdict="REQUESTED", review_ref="github:existing-review")
    data["worker"].update(state="QUEUED", exit_code=None)
    path = tmp_path / "pending.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.ohf.mission_exit_audit", str(path)],
        cwd=FIXTURE.parents[2], text=True, capture_output=True, timeout=5,
    )
    assert proc.returncode == 1
    assert proc.stderr == ""
    report = json.loads(proc.stdout)
    assert report["disposition"] == "INCOMPLETE"
    guidance = {g["requirement"]: g["next_proof"] for g in report["gaps"]}
    assert "do not rerun" in guidance["current_head_ci"]
    assert "do not duplicate" in guidance["independent_source_review"]
    assert "do not submit a replacement" in guidance["accepted_worker_result"]
    assert report["retry_authorized"] is False
    assert report["dispatch_authorized"] is False


@pytest.mark.parametrize("state", ["REQUESTED", "PENDING"])
def test_unconsumed_independent_request_does_not_bind_original_session(state):
    data = snapshot()
    data["source"].update(review_verdict=state, review_ref="github:original-review")
    guidance = _gap_guidance(data, "independent_source_review")
    assert "any eligible independent non-author" in guidance
    assert "confirm no active review" in guidance
    assert "original reviewer" not in guidance
    assert "do not duplicate" in guidance
    assert "request is not execution or approval" in guidance


def test_started_review_retains_original_carrier_with_no_parallel_worker():
    data = snapshot()
    data["source"].update(review_verdict="IN_PROGRESS", review_ref="github:original-review")
    guidance = _gap_guidance(data, "independent_source_review")
    assert "active current-head review" in guidance
    assert "original carrier" in guidance
    assert "do not duplicate" in guidance
    assert "any eligible independent non-author" not in guidance
