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
        used_tokens=observed["context_occupancy_tokens"], next_input_tokens=100,
        response_reserve=100, tool_reserve=100, compaction_reserve=100,
        native_compaction_supported=True, durable_checkpoint_available=True)
    assert result["next_action"] == "OBSERVE_CONTEXT"
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


def test_installed_codex_01593_usage_schema_matches_the_projection_contract():
    """Frozen export from the observed native binary, not a hand-written schema."""
    import hashlib
    from pathlib import Path
    source = Path(__file__).parent / "fixtures/codex_context/ThreadTokenUsageUpdatedNotification-0.159.3.json"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == "aba4f6c7e4a19b2b842c08ee793b57000c07dafd57b922ad0d8e7c76609108c2"
    schema = json.loads(source.read_text())
    assert set(schema["required"]) == {"threadId", "turnId", "tokenUsage"}
    usage = schema["definitions"]["ThreadTokenUsage"]
    assert set(usage["required"]) == {"last", "total"}
    assert usage["properties"]["modelContextWindow"]["type"] == ["integer", "null"]
    breakdown = schema["definitions"]["TokenUsageBreakdown"]
    fields = {"inputTokens", "outputTokens", "totalTokens", "cachedInputTokens", "reasoningOutputTokens"}
    assert set(breakdown["required"]) == fields
    assert all(breakdown["properties"][field] == {"format": "int64", "type": "integer"} for field in fields)
    assert project(notification())["state"] == "OBSERVED"


def test_native_schema_receipt_does_not_claim_provider_or_installation_acceptance():
    from pathlib import Path
    path = Path(__file__).parents[1] / "research/evidence/fabric-context-native-schema-20261012.json"
    receipt = json.loads(path.read_text())
    assert receipt["codex_version"] == "0.159.3"
    assert receipt["native_package_version"] == "0.159.3-darwin-arm64"
    assert receipt["native_binary_sha256"] == "4d210f7c5a18fd0386434df23b5bdbb8c0e7257d3e8a2b30b0769c8bbe99a878"
    assert receipt["isolated_codex_home"] is True
    for flag in ("credential_files_present", "model_turn_requested", "compaction_requested", "production_runtime_mutated", "adapter_integrated"):
        assert receipt[flag] is False

def test_request_local_usage_must_not_impersonate_exact_context_occupancy():
    from control_plane.executive_session_recovery import context_plan
    observed = project(notification())
    assert observed["last_request_tokens"] == 640
    assert observed["context_occupancy_tokens"] is None
    assert observed["usable_as_context_plan_used_tokens"] is False
    # Until a provider adapter proves exact occupancy, we observe rather than
    # authorize compaction/switching based on a last-request usage counter.
    plan = context_plan(context_limit=observed["context_window_tokens"],
        used_tokens=observed["context_occupancy_tokens"], next_input_tokens=100,
        response_reserve=100, tool_reserve=100, compaction_reserve=100,
        native_compaction_supported=True, durable_checkpoint_available=True)
    assert plan["next_action"] == "OBSERVE_CONTEXT"

def test_async_compaction_notification_is_observation_not_state_change():
    from control_plane.codex_context_projection import project_codex_compaction_notification
    params={"threadId":"thread-a","turnId":"turn-a","providerText":"secret"}
    result=project_codex_compaction_notification(
        params, expected_thread_id="thread-a", expected_turn_id="turn-a")
    assert result["state"] == "NATIVE_COMPACTION_NOTIFIED"
    assert result["checkpoint_committed"] is False
    assert result["requires_remeasurement"] is True
    assert result["authority_effect"] == "NONE"
    assert result["auto_resume_permitted"] is False
    assert "secret" not in json.dumps(result)
    assert "thread-a" not in json.dumps(result)


@pytest.mark.parametrize("key,bad", [
    ("threadId","other"),("turnId","other"),("turnId",None),
    ("turnId",True),("threadId",None),("threadId",[])
])
def test_compaction_notification_cannot_bind_foreign_or_malformed_identity(key,bad):
    from control_plane.codex_context_projection import project_codex_compaction_notification
    params={"threadId":"thread-a","turnId":"turn-a"}
    params[key]=bad
    assert project_codex_compaction_notification(
        params, expected_thread_id="thread-a", expected_turn_id="turn-a") is None
