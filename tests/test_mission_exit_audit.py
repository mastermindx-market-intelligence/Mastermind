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
PROPHET_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "research/fixtures/mission_exit_prophet10289_20261102.json"
)

# Exit-claim discrimination flags, present only when the snapshot carries a
# ``lanes`` section (additive; the incumbent contract without lanes is pinned
# by test_lanes_absent_keeps_incumbent_output_contract).
LANE_FLAGS = (
    "lane_local_wait_blocks_only_its_lane",
    "remaining_safe_work",
    "scope_evidence_structurally_bound",
    "all_lanes_proven_blocked",
    "all_external_waits_proven_blocked",
    "checkpoint_continuation_verified",
    "wait_executor_verified",
    "no_delta_loop_forces_tactic_change",
    "status_summary_is_not_continuation",
    "owner_only_handoff_is_not_continuation",
    "wait_requires_started_durable_executor",
    "premature_exit_detected",
)


def snapshot():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def prophet_snapshot():
    return json.loads(PROPHET_FIXTURE.read_text(encoding="utf-8"))



def _attest_complete_lanes(data):
    """Synthetic shape for tests, not an authentic Agent OS receipt."""
    data["lanes"]["scope_evidence"] = {
        "source_ref": "agentos:program-waves",
        "owner_readback_ref": "agentos:current-compiled",
        "source_revision": "a" * 40,
        "source_observed": True,
        "all_dependencies_checked": True,
        "canonical_lane_ids": [x["id"] for x in data["lanes"]["items"]],
    }
    return data

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


# ---------------------------------------------------------------------------
# Lane-local WAITING_EXTERNAL vs status/checkpoint/CI-summary exit, and the
# lawful all-lanes stop / safety-effect fence (2026-11-02 discriminator slice).
# Source-contract regressions over operator-supplied observations only; these
# are NOT served-model behavioral proof -- the fresh-session evaluation owner
# (SXA01–SXA07 packets) still owes that separate evidence gate.
# ---------------------------------------------------------------------------


def test_prophet10289_sanitized_local_passes_are_not_acceptance_or_release():
    report = audit(prophet_snapshot())
    assert report["disposition"] == "INCOMPLETE"
    # 142 local passes and rc0 do not close any required proof gate.
    assert report["checks_passed"] == []
    assert {g["requirement"] for g in report["gaps"]} == {
        "accepted_worker_result", "source_implementation",
        "current_head_ci", "independent_source_review",
    }
    assert report["terminal_exit_is_not_acceptance"] is True
    assert report["analysis_is_not_implementation"] is False
    # Lane discrimination: CI/review are lane-local waits, the unstaged
    # 145-test guard suite is remaining safe work, so the sanitized observed
    # exit (a checkpoint/status-summary stop after two no-delta support
    # cycles) is a premature exit, not continuation or a fenced stop.
    assert report["lane_local_wait_blocks_only_its_lane"] is True
    assert report["remaining_safe_work"] is True
    assert report["all_lanes_proven_blocked"] is False
    assert report["no_delta_loop_forces_tactic_change"] is True
    assert report["status_summary_is_not_continuation"] is True
    assert report["premature_exit_detected"] is True
    assert all(report[flag] is False for flag in (
        "source_write_authorized", "dispatch_authorized", "retry_authorized",
        "merge_authorized", "production_activation_authorized"
    ))
    assert report["fresh_owner_readback_required"] is True


def test_sanitized_fixture_pins_incident_numbers_in_refs():
    data = prophet_snapshot()
    assert "142" in data["worker"]["result_ref"]
    assert "145" in data["lanes"]["items"][2]["id"]
    assert data["lanes"]["items"][0]["id"].startswith("macro:pr-10289-hosted")
    assert data["lanes"]["items"][1]["state"] == "WAITING_EXTERNAL"


def test_same_facts_with_continue_claim_is_not_premature():
    # The discriminator: identical mission/lane facts, only the claimed exit
    # changes. Continuing the unstaged guard-test lane is lawful continuation
    # after a lane-local WAITING_EXTERNAL; the summary stop was not.
    data = prophet_snapshot()
    data["lanes"]["exit_claim"] = "CONTINUE"
    report = audit(data)
    assert report["premature_exit_detected"] is False
    assert report["status_summary_is_not_continuation"] is False
    assert report["lane_local_wait_blocks_only_its_lane"] is True
    assert report["remaining_safe_work"] is True
    assert report["no_delta_loop_forces_tactic_change"] is True


def test_owner_only_handoff_cannot_close_a_mission_with_safe_work():
    # Regression: the session completed CI, then assigned runtime and review
    # next steps to historical role names without a live receiver or uptake.
    data = prophet_snapshot()
    data["lanes"]["exit_claim"] = "OWNER_HANDOFF_STOP"
    report = audit(data)
    assert report["owner_only_handoff_is_not_continuation"] is True
    assert report["remaining_safe_work"] is True
    assert report["premature_exit_detected"] is True
    assert report["all_lanes_proven_blocked"] is False
    assert report["merge_authorized"] is False
    assert report["production_activation_authorized"] is False


def test_proof_complete_packet_with_owner_handoff_fails_closed_in_cli(tmp_path, capsys):
    data = prophet_snapshot()
    data["mission"]["requires"] = ["current_head_ci"]
    data["source"].update(
        ci_conclusion="SUCCESS", ci_head=data["source"]["head"],
        ci_run_ref="github:run-completed",
    )
    data["lanes"]["exit_claim"] = "OWNER_HANDOFF_STOP"
    result = audit(data)
    assert result["checks_passed"] == ["current_head_ci"]
    assert result["gaps"] == []
    assert result["premature_exit_detected"] is True
    assert result["disposition"] == "INCOMPLETE"
    file = tmp_path / "ghost-owner.json"
    file.write_text(json.dumps(data), encoding="utf-8")
    assert main([str(file)]) == 1
    assert json.loads(capsys.readouterr().out)["disposition"] == "INCOMPLETE"
    # The same source evidence can still be adjudicated if the session acts.
    data["lanes"]["exit_claim"] = "CONTINUE"
    assert audit(data)["disposition"] == "READY_FOR_CANONICAL_ADJUDICATION"


def test_proof_complete_packet_with_checkpoint_summary_cannot_be_ready():
    data = prophet_snapshot()
    data["mission"]["requires"] = ["current_head_ci"]
    data["source"].update(
        ci_conclusion="SUCCESS", ci_head=data["source"]["head"],
        ci_run_ref="github:run-completed",
    )
    data["lanes"]["exit_claim"] = "CHECKPOINT_SUMMARY_STOP"
    result = audit(data)
    assert result["gaps"] == []
    assert result["premature_exit_detected"] is True
    assert result["disposition"] == "INCOMPLETE"


def test_owner_only_handoff_is_not_durable_executor_or_verified_checkpoint():
    data = prophet_snapshot()
    data["lanes"]["items"] = [
        {"id": "github:review-request", "state": "WAITING_EXTERNAL",
         "blocker_ref": "github:requested-review", "blocker_owner_ref": "github:review-role",
         "blocker_observed": True},
    ]
    _attest_complete_lanes(data)
    data["lanes"]["exit_claim"] = "OWNER_HANDOFF_STOP"
    report = audit(data)
    assert report["owner_only_handoff_is_not_continuation"] is True
    assert report["all_external_waits_proven_blocked"] is True
    assert report["wait_executor_verified"] is False
    assert report["checkpoint_continuation_verified"] is False
    assert report["premature_exit_detected"] is True


def test_staging_the_guard_lane_removes_remaining_safe_work_flag():
    data = prophet_snapshot()
    data["lanes"]["items"][2]["state"] = "DONE"
    data["lanes"]["items"][2]["completion_ref"] = "github:guard-suite-commit"
    report = audit(data)
    assert report["remaining_safe_work"] is False
    assert report["lane_local_wait_blocks_only_its_lane"] is False
    # A checkpoint-summary exit still is not continuation: the CI/review waits
    # have no started durable executor to hand the mission to.
    assert report["status_summary_is_not_continuation"] is True
    assert report["premature_exit_detected"] is True


def test_all_lanes_proven_blocked_stop_is_lawful_fence():
    data = prophet_snapshot()
    data["effect"] = {
        "class": "SAFETY_DENIED",
        "action_id": "macro:held-source-write",
        "carrier": "macro:original-pr-carrier",
        "dispatched": False,
    }
    data["lanes"] = {
        "items": [
            {"id": "macro:source-write-lane", "state": "FENCED",
             "effect_action_id": "macro:held-source-write",
             "effect_carrier": "macro:original-pr-carrier"},
            {"id": "macro:permission-ceremony-lane", "state": "BLOCKED_PROVEN",
             "blocker_ref": "studio:permission-denial", "blocker_owner_ref": "studio:owner",
             "blocker_observed": True, "negative_capability_verified": True},
            {"id": "macro:finished-read-lane", "state": "DONE",
             "completion_ref": "github:reviewed-read"},
        ],
        "exit_claim": "ALL_LANES_BLOCKED_STOP",
        "wait_executor": {"started": False, "ref": None},
        "support_cycles_without_delta": 2,
    }
    _attest_complete_lanes(data)
    report = audit(data)
    assert report["all_lanes_proven_blocked"] is True
    # A truthful proven-blocked terminal is the incumbent ALL_SCOPED_LANES_BLOCKED
    # shape, not a support loop and not a premature exit.
    assert report["no_delta_loop_forces_tactic_change"] is False
    assert report["premature_exit_detected"] is False
    assert report["held_actions"][0]["instruction"] == (
        "do not retry the denied action through any carrier"
    )


def test_one_fenced_lane_with_independent_work_is_not_mission_stop():
    # The safety/effect-unknown fence is lane-scoped: it holds the denied or
    # uncertain effect on its original carrier while independent lanes advance.
    data = prophet_snapshot()
    data["effect"] = {
        "class": "EFFECT_UNKNOWN",
        "action_id": "macro:deployment-mutation",
        "carrier": "studio:original-carrier",
        "dispatched": None,
    }
    data["lanes"] = {
        "items": [
            {"id": "macro:uncertain-deployment-lane", "state": "FENCED",
             "effect_action_id": "macro:deployment-mutation",
             "effect_carrier": "studio:original-carrier"},
            {"id": "macro:independent-review-lane", "state": "SAFE_WORK_REMAINING",
             "next_action_ref": "github:read-disjoint-diff"},
        ],
        "exit_claim": "ALL_LANES_BLOCKED_STOP",
    }
    report = audit(data)
    assert report["all_lanes_proven_blocked"] is False
    assert report["premature_exit_detected"] is True
    assert report["held_actions"][0]["instruction"] == (
        "reconcile only through original carrier; no replay or failover"
    )
    assert report["retry_authorized"] is False


def test_fenced_lane_without_held_effect_refused():
    data = prophet_snapshot()
    data["lanes"]["items"] = [{"id": "macro:claimed-fence", "state": "FENCED"}]
    with pytest.raises(InvalidSnapshot):
        audit(data)


@pytest.mark.parametrize("mutation", [
    lambda d: d["lanes"].update(items=[]),
    lambda d: d["lanes"].update(items=[{"id": "macro:one", "state": "DONE"},
                                       {"id": "macro:one", "state": "DONE"}]),
    lambda d: d["lanes"]["items"][0].update(state="MAYBE_BLOCKED"),
    lambda d: d["lanes"].update(exit_claim="STOP_BECAUSE_CI_GREEN"),
    lambda d: d["lanes"].update(support_cycles_without_delta=-1),
    lambda d: d["lanes"].update(support_cycles_without_delta="2"),
    lambda d: d["lanes"].update(support_cycles_without_delta=True),
    lambda d: d["lanes"].update(wait_executor={"started": True, "ref": None}),
    lambda d: d["lanes"].update(wait_executor={"started": True, "ref": 123}),
    lambda d: d["lanes"].update(wait_executor={"started": False, "ref": ["x"]}),
    lambda d: d["lanes"].update(items="macro:not-a-list"),
    lambda d: d.update(lanes=["not-an-object"]),
])
def test_malformed_lane_evidence_refused(mutation):
    data = prophet_snapshot()
    mutation(data)
    with pytest.raises(InvalidSnapshot):
        audit(data)


def test_wait_claim_requires_started_durable_executor():
    # Ending solely to wait is lawful only with a real accepted/started durable
    # executor with a lawful return path; a request, notification, delivery, or
    # trigger is not that executor.
    data = prophet_snapshot()
    data["lanes"]["items"] = [
        {"id": "macro:pr-10289-hosted-exact-head-ci", "state": "WAITING_EXTERNAL",
         "blocker_ref": "github:ci-pending-10289", "blocker_owner_ref": "github:actions",
         "blocker_observed": True},
        {"id": "macro:pr-10289-independent-review", "state": "WAITING_EXTERNAL",
         "blocker_ref": "github:review-pending-10289", "blocker_owner_ref": "github:reviewer",
         "blocker_observed": True},
    ]
    data["lanes"]["exit_claim"] = "WAIT_EXTERNAL_EXECUTOR"
    data["lanes"].pop("support_cycles_without_delta")
    report = audit(data)
    assert report["wait_requires_started_durable_executor"] is True
    assert report["premature_exit_detected"] is True
    assert report["remaining_safe_work"] is False
    data["lanes"]["wait_executor"] = {
        "started": True, "ref": "github:ci-pending-10289",
        "lane_id": "macro:pr-10289-hosted-exact-head-ci",
        "return_path_ref": "github:ci-result-return", "owner_observed": True,
        "state": "RUNNING", "state_ref": "fabric:current-runtime-observation",
        "state_observed": True,
    }
    _attest_complete_lanes(data)
    report = audit(data)
    assert report["wait_requires_started_durable_executor"] is False
    assert report["premature_exit_detected"] is False


def test_verified_checkpoint_without_running_worker_is_lawful():
    data = prophet_snapshot()
    data["lanes"]["exit_claim"] = "CHECKPOINTED_CONTINUATION"
    assert audit(data)["premature_exit_detected"] is True
    data["lanes"]["checkpoint"] = {
        "persisted": True, "receipt_ref": "agentos:verified-handoff",
        "revision": "a" * 64, "continuity_reason": "CONTEXT_PRESSURE",
        "observed_continuity_risk": True, "next_action_ref": "macro:guard-suite-step",
        "resume_surface_ref": "chatgpt:fresh-session",
        "effects_accounted": True, "custody_preserved": True, "mission_complete": False,
    }
    report = audit(data)
    assert report["checkpoint_continuation_verified"] is True
    assert report["premature_exit_detected"] is False
    assert report["remaining_safe_work"] is True


def test_status_summary_is_premature_even_with_unrelated_started_executor():
    data = prophet_snapshot()
    data["lanes"]["items"] = [
        {"id": "macro:pr-10289-hosted-exact-head-ci", "state": "WAITING_EXTERNAL",
         "blocker_ref": "github:ci-pending-10289", "blocker_owner_ref": "github:actions",
         "blocker_observed": True}
    ]
    data["lanes"]["wait_executor"] = {
        "started": True, "ref": "fabric:unrelated-worker",
        "return_path_ref": "fabric:unrelated-wake", "owner_observed": True,
        "state": "RUNNING", "state_ref": "fabric:current-runtime-observation",
        "state_observed": True,
    }
    report = audit(data)
    assert report["wait_executor_verified"] is False
    assert report["status_summary_is_not_continuation"] is True
    assert report["premature_exit_detected"] is True


def test_checkpoint_requires_actual_pressure_and_immutable_readback():
    data = prophet_snapshot()
    data["lanes"]["exit_claim"] = "CHECKPOINTED_CONTINUATION"
    cp = data["lanes"]["checkpoint"] = {
        "persisted": True, "receipt_ref": "agentos:verified-handoff",
        "revision": "b" * 64, "continuity_reason": "CONTEXT_PRESSURE",
        "observed_continuity_risk": True, "next_action_ref": "macro:guard-145",
        "resume_surface_ref": "chatgpt:next-chat", "effects_accounted": True,
        "custody_preserved": True, "mission_complete": False,
    }
    assert audit(data)["premature_exit_detected"] is False
    cp["continuity_reason"] = "CLEAN_PHASE_ONLY"
    assert audit(data)["premature_exit_detected"] is True
    cp["continuity_reason"] = "CONTEXT_PRESSURE"
    cp["revision"] = None
    assert audit(data)["premature_exit_detected"] is True




@pytest.mark.parametrize("cycles,expected", [(0, False), (1, False), (2, True), (5, True)])
def test_no_delta_loop_requires_two_support_cycles(cycles, expected):
    data = prophet_snapshot()
    data["lanes"]["support_cycles_without_delta"] = cycles
    assert audit(data)["no_delta_loop_forces_tactic_change"] is expected


def test_lanes_absent_keeps_incumbent_output_contract():
    report = audit(snapshot())
    assert set(LANE_FLAGS).isdisjoint(report)
    assert set(LANE_FLAGS) <= set(audit(prophet_snapshot()))


def test_prophet10289_discriminator_via_cli(tmp_path, capsys):
    p = tmp_path / "prophet10289.json"
    p.write_text(PROPHET_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    assert main([str(p)]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["schema"] == OUTPUT_SCHEMA
    assert result["disposition"] == "INCOMPLETE"
    assert result["premature_exit_detected"] is True
    assert result["lane_local_wait_blocks_only_its_lane"] is True
    assert result["status_summary_is_not_continuation"] is True


def test_proven_external_waits_allow_a_genuine_all_lanes_stop():
    data = prophet_snapshot()
    data["lanes"]["items"] = [
        {"id": "macro:ci-queued", "state": "WAITING_EXTERNAL",
         "blocker_ref": "github:run-415", "blocker_owner_ref": "github:actions",
         "blocker_observed": True},
        {"id": "macro:review-awaited", "state": "WAITING_EXTERNAL",
         "blocker_ref": "github:review-request", "blocker_owner_ref": "github:reviewer",
         "blocker_observed": True},
    ]
    data["lanes"]["exit_claim"] = "ALL_LANES_BLOCKED_STOP"
    _attest_complete_lanes(data)
    result = audit(data)
    assert result["all_lanes_proven_blocked"] is True
    assert result["all_external_waits_proven_blocked"] is True
    assert result["premature_exit_detected"] is False
    assert result["no_delta_loop_forces_tactic_change"] is False


def test_claimed_external_wait_without_attributed_proof_is_invalid():
    data = prophet_snapshot()
    data["lanes"]["items"] = [{"id": "macro:claimed-review", "state": "WAITING_EXTERNAL"}]
    data["lanes"]["exit_claim"] = "ALL_LANES_BLOCKED_STOP"
    with pytest.raises(InvalidSnapshot):
        audit(data)


def test_proven_blocker_needs_real_negative_capability():
    data = prophet_snapshot()
    data["lanes"]["items"] = [
        {"id": "macro:claimed-block", "state": "BLOCKED_PROVEN",
         "blocker_ref": "studio:read-denied", "blocker_owner_ref": "studio:owner",
         "blocker_observed": True}
    ]
    data["lanes"]["exit_claim"] = "ALL_LANES_BLOCKED_STOP"
    with pytest.raises(InvalidSnapshot):
        audit(data)


def test_unrelated_held_effect_cannot_fence_a_separate_lane():
    data = prophet_snapshot()
    data["effect"] = {
        "class": "EFFECT_UNKNOWN", "action_id": "macro:old-mutation",
        "carrier": "studio:original-carrier", "dispatched": None,
    }
    data["lanes"]["items"] = [
        {"id": "macro:other-lane", "state": "FENCED",
         "effect_action_id": "macro:different-mutation",
         "effect_carrier": "studio:original-carrier"}
    ]
    data["lanes"]["exit_claim"] = "ALL_LANES_BLOCKED_STOP"
    with pytest.raises(InvalidSnapshot):
        audit(data)
    data["lanes"]["items"][0]["effect_action_id"] = "macro:old-mutation"
    data["lanes"]["items"][0]["effect_carrier"] = "studio:other-carrier"
    with pytest.raises(InvalidSnapshot):
        audit(data)


def test_started_wait_requires_canonical_return_path():
    data = prophet_snapshot()
    data["lanes"]["items"] = [
        {"id": "macro:ci-queued", "state": "WAITING_EXTERNAL",
         "blocker_ref": "github:run-415", "blocker_owner_ref": "github:actions",
         "blocker_observed": True}
    ]
    data["lanes"]["exit_claim"] = "WAIT_EXTERNAL_EXECUTOR"
    data["lanes"]["wait_executor"] = {"started": True, "ref": "fabric:unrelated-worker"}
    with pytest.raises(InvalidSnapshot):
        audit(data)
    data["lanes"]["wait_executor"]["return_path_ref"] = "fabric:real-return"
    data["lanes"]["wait_executor"]["owner_observed"] = True
    data["lanes"]["wait_executor"].update(
        state="RUNNING", state_ref="fabric:run-live-readback", state_observed=True
    )
    _attest_complete_lanes(data)
    assert audit(data)["premature_exit_detected"] is True
    data["lanes"]["wait_executor"]["lane_id"] = "macro:ci-queued"
    assert audit(data)["wait_executor_verified"] is False
    data["lanes"]["wait_executor"]["ref"] = "github:run-415"
    assert audit(data)["wait_executor_verified"] is True
    assert audit(data)["premature_exit_detected"] is False


def test_omitted_ready_lane_cannot_fake_an_all_blocked_stop():
    data = prophet_snapshot()
    canonical_ids = [row["id"] for row in data["lanes"]["items"]]
    data["lanes"]["items"] = [
        row for row in data["lanes"]["items"] if row["state"] != "SAFE_WORK_REMAINING"
    ]
    data["lanes"]["exit_claim"] = "ALL_LANES_BLOCKED_STOP"
    out = audit(data)
    assert out["scope_evidence_structurally_bound"] is False
    assert out["all_lanes_proven_blocked"] is False
    assert out["premature_exit_detected"] is True
    assert out["no_delta_loop_forces_tactic_change"] is True
    _attest_complete_lanes(data)
    data["lanes"]["scope_evidence"]["canonical_lane_ids"] = canonical_ids
    with pytest.raises(InvalidSnapshot, match="omit"):
        audit(data)


def test_durable_wait_cannot_hide_unlisted_ready_work():
    data = prophet_snapshot()
    data["lanes"]["items"] = [
        {"id": "github:ci-remaining", "state": "WAITING_EXTERNAL",
         "blocker_ref": "github:run-123", "blocker_owner_ref": "github:actions",
         "blocker_observed": True}
    ]
    data["lanes"]["exit_claim"] = "WAIT_EXTERNAL_EXECUTOR"
    data["lanes"]["wait_executor"] = {
        "started": True, "ref": "github:run-123",
        "lane_id": "github:ci-remaining",
        "return_path_ref": "github:verified-return", "owner_observed": True,
        "state": "RUNNING", "state_ref": "fabric:current-runtime-observation",
        "state_observed": True,
    }
    assert audit(data)["premature_exit_detected"] is True
    _attest_complete_lanes(data)
    assert audit(data)["premature_exit_detected"] is False


@pytest.mark.parametrize("change", [
    lambda d: d["lanes"]["scope_evidence"].update(source_revision="branch"),
    lambda d: d["lanes"]["scope_evidence"].update(source_observed=False),
    lambda d: d["lanes"]["scope_evidence"].update(all_dependencies_checked=False),
    lambda d: d["lanes"]["scope_evidence"].update(owner_readback_ref=None),
    lambda d: d["lanes"]["scope_evidence"].update(canonical_lane_ids=[]),
    lambda d: d["lanes"]["scope_evidence"].update(canonical_lane_ids=["github:duplicate", "github:duplicate"]),
])
def test_unqualified_scope_claim_fails_closed(change):
    data = _attest_complete_lanes(prophet_snapshot())
    change(data)
    with pytest.raises(InvalidSnapshot):
        audit(data)


def test_executor_must_match_waiting_dependency_red_regression():
    data = prophet_snapshot()
    data["lanes"]["items"] = [
        {"id": "macro:ci-queued", "state": "WAITING_EXTERNAL",
         "blocker_ref": "github:run-415", "blocker_owner_ref": "github:actions",
         "blocker_observed": True},
    ]
    data["lanes"]["exit_claim"] = "WAIT_EXTERNAL_EXECUTOR"
    data["lanes"]["wait_executor"] = {
        "started": True, "ref": "fabric:unrelated-worker",
        "lane_id": "macro:ci-queued",
        "return_path_ref": "fabric:unrelated-return",
        "owner_observed": True,
        "state": "RUNNING", "state_ref": "fabric:current-runtime-observation",
        "state_observed": True,
    }
    _attest_complete_lanes(data)
    report = audit(data)
    assert report["all_lanes_proven_blocked"] is True
    assert report["wait_executor_verified"] is False
    assert report["premature_exit_detected"] is True



def test_durable_wait_needs_existing_waiting_lane_not_finished_or_unknown_lane():
    data = prophet_snapshot()
    data["lanes"]["items"] = [
        {"id": "macro:review-awaited", "state": "WAITING_EXTERNAL",
         "blocker_ref": "github:review-415", "blocker_owner_ref": "github:reviewer",
         "blocker_observed": True},
        {"id": "macro:finished", "state": "DONE", "completion_ref": "github:done-415"},
    ]
    data["lanes"]["exit_claim"] = "WAIT_EXTERNAL_EXECUTOR"
    data["lanes"]["wait_executor"] = {
        "started": True, "ref": "github:review-415",
        "return_path_ref": "github:review-result", "owner_observed": True,
        "state": "RUNNING", "state_ref": "fabric:current-runtime-observation",
        "state_observed": True,
    }
    _attest_complete_lanes(data)
    assert audit(data)["premature_exit_detected"] is True
    data["lanes"]["wait_executor"]["lane_id"] = "macro:finished"
    assert audit(data)["wait_executor_verified"] is False
    data["lanes"]["wait_executor"]["lane_id"] = "macro:unknown"
    assert audit(data)["premature_exit_detected"] is True
    data["lanes"]["wait_executor"]["lane_id"] = "macro:review-awaited"
    assert audit(data)["wait_executor_verified"] is True
    assert audit(data)["premature_exit_detected"] is False


def test_distinct_blocker_receipt_needs_attributed_executor_ref_on_awaited_lane():
    data = prophet_snapshot()
    data["lanes"]["items"] = [
        {"id": "macro:nightly-guard", "state": "WAITING_EXTERNAL",
         "blocker_ref": "github:ci-step-receipt", "blocker_owner_ref": "github:actions",
         "blocker_observed": True},
    ]
    data["lanes"]["exit_claim"] = "WAIT_EXTERNAL_EXECUTOR"
    data["lanes"]["wait_executor"] = {
        "started": True, "ref": "fabric:nightly-guard-executor",
        "lane_id": "macro:nightly-guard",
        "return_path_ref": "fabric:original-result", "owner_observed": True,
        "state": "RUNNING", "state_ref": "fabric:current-runtime-observation",
        "state_observed": True,
    }
    _attest_complete_lanes(data)
    assert audit(data)["wait_executor_verified"] is False
    lane = data["lanes"]["items"][0]
    lane["executor_ref"] = "fabric:nightly-guard-executor"
    with pytest.raises(InvalidSnapshot, match="executor binding"):
        audit(data)
    lane["executor_binding_ref"] = "agentos:readback-run-association"
    lane["executor_binding_observed"] = True
    assert audit(data)["wait_executor_verified"] is True
    assert audit(data)["premature_exit_detected"] is False
    lane["executor_binding_observed"] = False
    with pytest.raises(InvalidSnapshot, match="executor binding"):
        audit(data)
    lane["executor_binding_observed"] = True
    lane["executor_ref"] = "fabric:another-run"
    assert audit(data)["wait_executor_verified"] is False
    assert audit(data)["premature_exit_detected"] is True


def test_unrelated_durable_worker_does_not_cancel_all_lanes_stop_classification():
    data = prophet_snapshot()
    data["lanes"]["items"] = [
        {"id": "macro:ci-queued", "state": "WAITING_EXTERNAL",
         "blocker_ref": "github:run-415", "blocker_owner_ref": "github:actions",
         "blocker_observed": True}
    ]
    data["lanes"]["wait_executor"] = {
        "started": True, "ref": "fabric:unrelated-worker",
        "lane_id": "macro:ci-queued",
        "return_path_ref": "fabric:unrelated-return", "owner_observed": True,
        "state": "RUNNING", "state_ref": "fabric:current-runtime-observation",
        "state_observed": True,
    }
    _attest_complete_lanes(data)
    data["lanes"]["exit_claim"] = "WAIT_EXTERNAL_EXECUTOR"
    assert audit(data)["premature_exit_detected"] is True
    data["lanes"]["exit_claim"] = "ALL_LANES_BLOCKED_STOP"
    assert audit(data)["all_lanes_proven_blocked"] is True
    assert audit(data)["premature_exit_detected"] is False


def test_terminal_executor_cannot_keep_session_open_regression():
    # A historical START does not prove the worker is still RUNNING.
    data = prophet_snapshot()
    data["lanes"]["items"] = [{
        "id": "macro:awaited-fabric-run", "state": "WAITING_EXTERNAL",
        "blocker_ref": "fabric:run-123", "blocker_owner_ref": "fabric:runtime",
        "blocker_observed": True,
    }]
    data["lanes"]["exit_claim"] = "WAIT_EXTERNAL_EXECUTOR"
    data["lanes"]["wait_executor"] = {
        "started": True, "ref": "fabric:run-123",
        "lane_id": "macro:awaited-fabric-run",
        "return_path_ref": "fabric:original-return",
        "owner_observed": True, "state": "TERMINAL",
        "state_ref": "fabric:terminal-readback", "state_observed": True,
    }
    _attest_complete_lanes(data)
    out = audit(data)
    assert out["all_lanes_proven_blocked"] is True
    assert out["wait_executor_verified"] is False
    assert out["premature_exit_detected"] is True



@pytest.mark.parametrize("state", [
    None, "NONE", "QUEUED", "TERMINAL", "FAILED", "CANCELED", "UNKNOWN",
])
def test_historical_start_with_nonlive_current_state_cannot_justify_wait(state):
    data = prophet_snapshot()
    data["lanes"]["items"] = [{
        "id": "macro:awaited-run", "state": "WAITING_EXTERNAL",
        "blocker_ref": "fabric:run-123", "blocker_owner_ref": "fabric:runtime",
        "blocker_observed": True,
    }]
    data["lanes"]["exit_claim"] = "WAIT_EXTERNAL_EXECUTOR"
    data["lanes"]["wait_executor"] = {
        "started": True, "ref": "fabric:run-123",
        "lane_id": "macro:awaited-run", "owner_observed": True,
        "return_path_ref": "fabric:original-return",
        "state_ref": "fabric:current-readback", "state_observed": True,
    }
    if state is not None:
        data["lanes"]["wait_executor"]["state"] = state
    _attest_complete_lanes(data)
    out = audit(data)
    assert out["scope_evidence_structurally_bound"] is True
    assert out["all_lanes_proven_blocked"] is True
    assert out["wait_executor_verified"] is False
    assert out["premature_exit_detected"] is True


@pytest.mark.parametrize("state", ["STARTED", "RUNNING"])
def test_active_state_requires_real_owner_readback_not_just_started_flag(state):
    data = prophet_snapshot()
    data["lanes"]["items"] = [{
        "id": "macro:awaited-run", "state": "WAITING_EXTERNAL",
        "blocker_ref": "fabric:run-123", "blocker_owner_ref": "fabric:runtime",
        "blocker_observed": True,
    }]
    data["lanes"]["exit_claim"] = "WAIT_EXTERNAL_EXECUTOR"
    data["lanes"]["wait_executor"] = {
        "started": True, "ref": "fabric:run-123",
        "lane_id": "macro:awaited-run", "owner_observed": True,
        "return_path_ref": "fabric:original-return", "state": state,
    }
    _attest_complete_lanes(data)
    with pytest.raises(InvalidSnapshot, match="state lacks current"):
        audit(data)
    data["lanes"]["wait_executor"]["state_ref"] = "fabric:latest-status-read"
    with pytest.raises(InvalidSnapshot, match="state lacks current"):
        audit(data)
    data["lanes"]["wait_executor"]["state_observed"] = True
    assert audit(data)["wait_executor_verified"] is True
    assert audit(data)["premature_exit_detected"] is False
    data["lanes"]["wait_executor"]["started"] = False
    assert audit(data)["wait_executor_verified"] is False


@pytest.mark.parametrize("state", ["SLEEPING", "DONE", True, [], {"status":"RUNNING"}])
def test_unrecognized_current_executor_states_are_rejected(state):
    data = prophet_snapshot()
    data["lanes"]["wait_executor"] = {
        "started": True, "ref": "fabric:run-123", "owner_observed": True,
        "return_path_ref": "fabric:return", "state": state,
    }
    with pytest.raises(InvalidSnapshot, match="current executor state"):
        audit(data)

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


@pytest.mark.parametrize("state", ["STALE", "SKIPPED", "NEUTRAL"])
def test_unproven_current_head_ci_observation_requires_reconciliation_not_repair(state):
    data = snapshot()
    data["source"].update(ci_conclusion=state, ci_run_ref="github:existing-ci")
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
