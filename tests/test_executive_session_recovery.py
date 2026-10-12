"""Deterministic context/recovery diagnostics; no model calls or reservations."""
import importlib.util

import pytest


def module():
    name = "control_plane.executive_session_recovery"
    assert importlib.util.find_spec(name) is not None, "session recovery diagnostics are missing"
    return __import__(name, fromlist=["context_plan"])


def plan(**changes):
    values = dict(context_limit=1000, used_tokens=400, next_input_tokens=100,
                  response_reserve=100, tool_reserve=100, compaction_reserve=100,
                  native_compaction_supported=True, durable_checkpoint_available=True)
    values.update(changes)
    return module().context_plan(**values)


def test_healthy_session_does_not_rotate_on_a_timer():
    assert plan()["next_action"] == "CONTINUE"


def test_compact_while_there_is_still_room():
    assert plan(used_tokens=750)["next_action"] == "COMPACT_SAME_SESSION"


def test_overflow_cannot_be_solved_by_an_extra_overfull_compaction_request():
    assert plan(used_tokens=950)["next_action"] == "RESUME_FROM_DURABLE_CHECKPOINT"


def test_no_native_compaction_uses_portable_frontier():
    assert plan(used_tokens=750, native_compaction_supported=False)["next_action"] == "RESUME_FROM_DURABLE_CHECKPOINT"


def test_missing_frontier_is_not_a_successful_handoff():
    assert plan(used_tokens=750, durable_checkpoint_available=False)["next_action"] == "SAVE_DURABLE_FRONTIER"
    assert plan(used_tokens=1100, durable_checkpoint_available=False)["next_action"] == "RECONCILE_DURABLE_FRONTIER"


@pytest.mark.parametrize("changes", [{"context_limit": None}, {"used_tokens": None}])
def test_unknown_context_measurements_do_not_invent_capacity(changes):
    assert plan(**changes)["next_action"] == "OBSERVE_CONTEXT"


@pytest.mark.parametrize("field", ["context_limit", "used_tokens", "next_input_tokens", "response_reserve",
                                  "tool_reserve", "compaction_reserve"])
@pytest.mark.parametrize("bad", [-1, True, 1.5, "100"])
def test_invalid_context_counts_are_rejected(field, bad):
    with pytest.raises((ValueError, TypeError)):
        plan(**{field: bad})


def test_exact_boundary_keeps_response_tool_and_recovery_reserves():
    assert plan(used_tokens=600)["next_action"] == "CONTINUE"
    assert plan(used_tokens=601)["next_action"] == "COMPACT_SAME_SESSION"


def test_next_turn_does_not_spend_the_last_compaction_headroom():
    result = plan(used_tokens=700)
    assert result["next_action"] == "COMPACT_SAME_SESSION"
    assert result["remeasure_before_next_turn"] is True


def test_oversized_next_turn_does_not_start_an_endless_compaction_loop():
    result = plan(used_tokens=0, next_input_tokens=901)
    assert result["next_action"] == "REBUILD_NEXT_TURN_CONTEXT"
    assert result["operation_performed"] is False


def test_impossible_next_turn_is_not_solved_by_forgetting_mandatory_reserves():
    result = plan(used_tokens=10, next_input_tokens=750)
    assert result["next_action"] == "REBUILD_NEXT_TURN_CONTEXT"
    assert result["max_next_input_tokens"] == 700


def test_healthy_plan_reports_its_retained_recovery_reserve():
    assert plan()["recovery_reserve_tokens"] == 100


def test_target_mandatory_state_never_silently_truncates():
    result = module().portable_context_fit(target_context_limit=1000, mandatory_tokens=800,
        optional_tokens=100, response_reserve=100, tool_reserve=150)
    assert result["next_action"] == "TARGET_CONTEXT_TOO_SMALL"
    assert result["mandatory_tokens_dropped"] == 0


def test_large_optional_history_becomes_references_not_lost_required_state():
    result = module().portable_context_fit(target_context_limit=1000, mandatory_tokens=400,
        optional_tokens=900, response_reserve=100, tool_reserve=150)
    assert result["next_action"] == "REBUILD_OPTIONAL_CONTEXT_FROM_REFS"
    assert result["max_optional_tokens"] == 350
    assert result["mandatory_tokens_dropped"] == 0


def test_projection_does_not_reserve_or_invoke_tools():
    result = plan(used_tokens=750)
    assert result["authority_effect"] == "NONE"
    assert result["operation_performed"] is False


@pytest.mark.parametrize("guard", ["permission", "safety", "authentication", "human_approval"])
def test_guard_refusal_is_never_a_pool_switch_signal(guard):
    assert hasattr(module(), "adapter_stop_diagnostic"), "typed stop triage is missing"
    result = module().adapter_stop_diagnostic(None, guard_refusal=guard)
    assert result["reassess_capacity"] is False
    assert result["retry_authorized"] is False


@pytest.mark.parametrize("failure,assessment", [
    ("QUOTA_OR_RATE_LIMIT", True), ("PROVIDER_CONCURRENCY", True),
    ("AUTH_FAILURE", False), ("ACTIVE_WRITER_CONFLICT", False),
    ("PROCESS_CRASH", False), ("SESSION_MISSING", False),
    ("CAPABILITY_ATTESTATION_FAILURE", False), ("MODEL_OR_WORK_RESULT_FAILURE", False),
])
def test_closed_adapter_causes_do_not_treat_every_stop_as_quota(failure, assessment):
    from control_plane.operator_harness_contract import AdapterFailureClass
    result = module().adapter_stop_diagnostic(AdapterFailureClass(failure))
    assert result["reassess_capacity"] is assessment
    assert result["retry_authorized"] is False


def test_free_text_quota_claim_is_not_a_typed_provider_observation():
    with pytest.raises(TypeError):
        module().adapter_stop_diagnostic("out of tokens; try another account")
