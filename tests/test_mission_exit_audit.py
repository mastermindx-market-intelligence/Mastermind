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
    "all_lanes_proven_blocked",
    "all_external_waits_proven_blocked",
    "checkpoint_continuation_verified",
    "wait_executor_verified",
    "no_delta_loop_forces_tactic_change",
    "status_summary_is_not_continuation",
    "wait_requires_started_durable_executor",
    "premature_exit_detected",
)


def snapshot():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def prophet_snapshot():
    return json.loads(PROPHET_FIXTURE.read_text(encoding="utf-8"))


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
    data["lanes"]["wait_executor"] = {"started": True, "ref": "fabric:nightly-guard-run",
                                    "return_path_ref": "fabric:result-return",
                                    "owner_observed": True}
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
    }
    report = audit(data)
    assert report["wait_executor_verified"] is True
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
    assert audit(data)["premature_exit_detected"] is False
