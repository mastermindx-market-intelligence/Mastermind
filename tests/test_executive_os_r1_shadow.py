from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from scripts.executive_os_r1_shadow import run_r1_shadow


def test_r1_shadow_registers_logical_luna_terra_and_completes_four_cases(tmp_path):
    evidence = run_r1_shadow(tmp_path)

    assert evidence["schema"] == "mastermind.executive_os_r1_shadow_evidence/v1"
    assert evidence["routing_policy_version"] == "2026-10-14.attended-qualification"
    assert evidence["acceptance"]["r1_shadow_pass"] is True
    assert {row["worker_id"] for row in evidence["jobs"]} == {
        "fixture-luna-r1",
        "fixture-terra-r1",
    }
    assert {row["assigned_model_alias"] for row in evidence["jobs"]} == {
        "fast.engineering",
        "fast.research",
        "standard.review",
    }
    assert all(row["status"] == "COMPLETED" for row in evidence["jobs"])
    assert all(row["adapter_invoked"] is False for row in evidence["jobs"])
    assert evidence["guards"]["router_policy_production_armed"] is False
    assert evidence["guards"]["mcp_write_authority"] is False
    assert evidence["guards"]["live_worker_slots_activated"] is False
    assert evidence["guards"]["phase_1c_a_hold_preserved"] is True
    assert evidence["guards"]["phase_1f_c_started"] is False


def test_r1_shadow_metrics_match_the_declared_fixture_envelope(tmp_path):
    evidence = run_r1_shadow(tmp_path)
    metrics = evidence["metrics"]

    assert metrics["baseline"]["frontier_tokens_total"] == 5100
    assert metrics["shadow"]["frontier_tokens_total"] == 1770
    assert metrics["frontier_token_savings"] == {
        "baseline_basis": "previous_all_sol_reference_fixture",
        "rate": 0.652941,
        "telemetry_status": "fixture_estimate_not_provider_billing",
        "tokens": 3330,
    }
    assert metrics["shadow"]["validation_pass_rate"] == 1.0
    assert metrics["shadow"]["repair_rate"] == 0.5
    assert metrics["shadow"]["latency_ms_mean"] == 1600.0


def test_r1_shadow_is_byte_deterministic_for_same_fixture_inputs(tmp_path):
    first = run_r1_shadow(tmp_path / "first")
    second = run_r1_shadow(tmp_path / "second")
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_r1_shadow_refuses_unreviewed_policy_before_runtime(tmp_path, monkeypatch):
    from scripts import executive_os_r1_shadow as shadow

    monkeypatch.setattr(shadow.ModelRouter, "load", classmethod(
        lambda cls: SimpleNamespace(policy_version="unreviewed.fixture")))
    root = tmp_path / "not-created"
    with pytest.raises(RuntimeError, match="R1 fixture expects routing policy"):
        run_r1_shadow(root)
    assert not root.exists()
