"""Official Codex usage-wire projection. Pure arithmetic, no provider calls."""
from __future__ import annotations

import copy
import importlib.util
import json

import pytest


def project(params, **overrides):
    name = "control_plane.codex_context_projection"
    assert importlib.util.find_spec(name) is not None, "native context usage projection is missing"
    module = __import__(name, fromlist=["project_codex_context_usage"])
    return module.project_codex_context_usage(params,
        expected_thread_id=overrides.get("thread", "thread-a"),
        expected_turn_id=overrides.get("turn", "turn-a"))


def notification():
    return {"threadId": "thread-a", "turnId": "turn-a", "tokenUsage": {
        "last": {"inputTokens": 600, "outputTokens": 40, "totalTokens": 640,
                 "cachedInputTokens": 450, "reasoningOutputTokens": 20},
        "total": {"totalTokens": 9_000_000}, "modelContextWindow": 1000}}


def test_last_request_not_lifetime_spend_or_double_counted_cache_drives_observation():
    value = project(notification())
    assert value["state"] == "OBSERVED"
    assert value["last_request_tokens"] == 640
    assert value["context_window_tokens"] == 1000
    assert value["basis"] == "LAST_REQUEST_NOT_CUMULATIVE"
    assert value["auto_compaction_threshold_tokens"] is None
    assert value["authority_effect"] == "NONE"


def test_numeric_only_projection_never_copies_prompt_or_provider_extra_fields():
    params = notification()
    params["tokenUsage"]["last"]["prompt"] = "confidential source text"
    params["tokenUsage"]["metadata"] = {"access_token": "private-token-value"}
    params["text"] = "private message"
    before = copy.deepcopy(params)
    result = project(params)
    encoded = json.dumps(result)
    for secret in ("confidential", "private-token", "private message", "thread-a", "turn-a"):
        assert secret not in encoded
    assert params == before


@pytest.mark.parametrize("field", ["threadId", "turnId"])
@pytest.mark.parametrize("bad", [None, "other", "", [], 4, True, " thread-a"])
def test_foreign_or_missing_native_identity_does_not_become_parent_context(field, bad):
    params = notification()
    params[field] = bad
    assert project(params) is None


@pytest.mark.parametrize("bad", [None, [], "event", 42])
def test_non_object_notification_has_no_scoped_observation(bad):
    assert project(bad) is None


@pytest.mark.parametrize("field", ["inputTokens", "outputTokens", "totalTokens", "cachedInputTokens", "reasoningOutputTokens"])
@pytest.mark.parametrize("bad", [-1, True, "640", 1.5, 2 ** 63])
def test_malformed_numeric_usage_is_unknown_not_zero_or_available(field, bad):
    params = notification()
    params["tokenUsage"]["last"][field] = bad
    value = project(params)
    assert value["state"] == "UNKNOWN"
    assert value["last_request_tokens"] is None
    assert value["context_window_tokens"] is None


@pytest.mark.parametrize("window", [None, "absent"])
def test_unknown_window_is_not_inferred_from_model_name(window):
    params = notification()
    if window == "absent":
        del params["tokenUsage"]["modelContextWindow"]
    else:
        params["tokenUsage"]["modelContextWindow"] = None
    value = project(params)
    assert value["state"] == "WINDOW_UNKNOWN"
    assert value["context_window_tokens"] is None
    assert value["last_request_tokens"] == 640


@pytest.mark.parametrize("bad", [0, -1, True, "1000", 2 ** 63])
def test_invalid_window_is_not_a_model_capacity_claim(bad):
    params = notification()
    params["tokenUsage"]["modelContextWindow"] = bad
    assert project(params)["state"] == "UNKNOWN"


def test_after_compaction_smaller_last_request_replaces_large_lifetime_total():
    params = notification()
    before = project(params)
    params["tokenUsage"]["last"]["inputTokens"] = 100
    params["tokenUsage"]["last"]["totalTokens"] = 140
    params["tokenUsage"]["last"]["cachedInputTokens"] = 0
    after = project(params)
    assert after["last_request_tokens"] < before["last_request_tokens"]
    assert after["last_request_tokens"] == 140


@pytest.mark.parametrize("identity", ["", None, [], " ", "x" * 257])
def test_caller_must_supply_an_exact_known_binding(identity):
    with pytest.raises((ValueError, TypeError)):
        project(notification(), thread=identity)


def test_observation_can_feed_existing_context_planner_without_new_threshold_policy():
    from control_plane.executive_session_recovery import context_plan
    observed = project(notification())
    result = context_plan(context_limit=observed["context_window_tokens"],
        used_tokens=observed["last_request_tokens"], next_input_tokens=100,
        response_reserve=100, tool_reserve=100, compaction_reserve=100,
        native_compaction_supported=True, durable_checkpoint_available=True)
    assert result["next_action"] == "COMPACT_SAME_SESSION"
    assert result["operation_performed"] is False


@pytest.mark.parametrize("total", [0, 10, 599])
def test_underreported_total_does_not_invent_free_context(total):
    params = notification()
    params["tokenUsage"]["last"]["totalTokens"] = total
    assert project(params)["state"] == "UNKNOWN"


@pytest.mark.parametrize("bad_usage", [None, [], {}, {"last": {}}, {"last": None}])
def test_missing_usage_does_not_turn_into_zero_tokens(bad_usage):
    params = notification()
    params["tokenUsage"] = bad_usage
    assert project(params)["state"] == "UNKNOWN"


def test_optional_cache_write_counter_is_not_double_counted():
    params = notification()
    params["tokenUsage"]["last"]["cacheWriteInputTokens"] = 100
    assert project(params)["last_request_tokens"] == 640
    params["tokenUsage"]["last"]["cacheWriteInputTokens"] = -1
    assert project(params)["state"] == "UNKNOWN"
