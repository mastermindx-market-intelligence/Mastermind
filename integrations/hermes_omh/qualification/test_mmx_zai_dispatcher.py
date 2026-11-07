"""Copy into a STAGED HAE tests directory and run with that pinned suite.

Uses HAE's reviewed no-network fixtures and Hermes' REAL plugin manager and
middleware dispatcher. The scorer is synthetic: this proves wiring, not live
Jev or provider behavior. All profile/state writes belong to pytest temp homes.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import pytest
from test_dispatcher_integration import dispatched  # native manager fixture

ROUTE = dict(provider="zai", model="glm-5.3", api_mode="chat_completions",
             base_url="https://api.z.ai/api/coding/paas/v4")


def _payload_module(home, suffix):
    from test_dispatcher_integration import _payload_module as resolve
    return resolve(home, suffix)


class Scorer:
    def __init__(self, failure=None, force=None):
        self.calls = []
        self.failure = failure
        self.force = force

    def classify_effort_detail(self, prompt, choices):
        self.calls.append(tuple(choices))
        assert tuple(choices) == ("low", "high", "max")
        if self.failure:
            return None, self.failure
        choice = self.force or ("low" if "marker-low" in prompt else "max")
        return choice, None

    def classify_detail(self, prompt):
        raise AssertionError("qualified direct-zai must use named choices, not legacy scores")


def prepare(dispatched, monkeypatch, scorer=None, mode="always"):
    middleware = dispatched["middleware"]
    middleware.reset_state()
    settings = {"mode": mode, "subagent_mode": "off", "dynamic_trial": False,
                "tool_error_escalation": False, "dialogue_context_messages": 0,
                "continuation_downgrade_votes": 0, "use_target_model_context": False}
    monkeypatch.setattr(middleware, "_settings_provider",
                        lambda key, default=None: settings.get(key, default))
    scorer = scorer or Scorer()
    monkeypatch.setattr(middleware, "_classifier_factory", lambda **kwargs: scorer)
    return middleware, scorer


def request(text="marker-low", effort="high"):
    return {"model": "glm-5.3", "reasoning_effort": effort,
            "messages": [{"role": "user", "content": text}],
            "extra_body": {"thinking": {"type": "enabled", "clear_thinking": False}},
            "temperature": 0.2, "metadata": {"original_request": "keep"}}


def dispatch(body, session="mmx-native-session", turn="turn-1", **overrides):
    from hermes_cli.middleware import apply_llm_request_middleware
    context = {**ROUTE, **overrides}
    return apply_llm_request_middleware(body, session_id=session, turn_id=turn, **context)


@pytest.mark.parametrize("choice,initial", [("low", "high"), ("high", "low"), ("max", "high")])
def test_real_dispatcher_applies_all_three_legal_levels(dispatched, monkeypatch, choice, initial):
    _, scorer = prepare(dispatched, monkeypatch, Scorer(force=choice))
    body = request(effort=initial); before = deepcopy(body)
    result = dispatch(body, session="legal-" + choice)
    expected = deepcopy(body); expected["reasoning_effort"] = choice
    assert result.changed and result.payload == expected
    assert body == before == result.original_payload
    assert result.trace[0]["source"] == "hermes-adaptive-effort"
    assert scorer.calls == [("low", "high", "max")]


def test_per_prompt_switching_and_tool_loop_reuse(dispatched, monkeypatch):
    _, scorer = prepare(dispatched, monkeypatch)
    first = dispatch(request("marker-low"), turn="1")
    loop = dispatch(request("marker-low plus tool result"), turn="1")
    hard = dispatch(request("marker-max"), turn="2")
    again = dispatch(request("marker-low"), turn="3")
    assert [x.payload["reasoning_effort"] for x in (first, loop, hard, again)] == ["low", "low", "max", "low"]
    assert len(scorer.calls) == 3


def test_manual_conversation_off_preserves_native_choice(dispatched, monkeypatch):
    middleware, scorer = prepare(dispatched, monkeypatch)
    middleware.set_conversation_mode("manual-session", "off")
    body = request("marker-low", effort="max")
    result = dispatch(body, session="manual-session")
    assert result.payload == body and not result.changed and not scorer.calls
    other = dispatch(request(), session="automatic-session")
    assert other.payload["reasoning_effort"] == "low"


def test_config_off_never_calls_scorer(dispatched, monkeypatch):
    _, scorer = prepare(dispatched, monkeypatch, mode="off")
    result = dispatch(request(), session="staged-off")
    assert not result.changed and not scorer.calls


def test_missing_scorer_key_preserves_original_request(dispatched, monkeypatch):
    _, scorer = prepare(dispatched, monkeypatch, Scorer(failure="missing_key"))
    body = request()
    result = dispatch(body, session="no-key")
    assert result.payload == body and not result.changed
    assert len(scorer.calls) == 1


def test_bad_scorer_choice_cannot_put_medium_on_wire(dispatched, monkeypatch):
    prepare(dispatched, monkeypatch, Scorer(force="medium"))
    body = request(effort="high")
    result = dispatch(body, session="bad-choice")
    assert result.payload == body and not result.changed


def test_unknown_route_without_control_is_untouched(dispatched, monkeypatch):
    _, scorer = prepare(dispatched, monkeypatch)
    body = {"model": "unknown", "messages": [{"role": "user", "content": "marker-low"}]}
    result = dispatch(body, session="unsupported", provider="custom", model="unknown",
                      base_url="https://not-qualified.example/v1")
    assert result.payload == body and not result.changed and not scorer.calls


def test_child_scoring_stays_off(dispatched, monkeypatch):
    middleware, scorer = prepare(dispatched, monkeypatch)
    middleware.on_subagent_start(parent_session_id="parent", child_session_id="child", child_goal="marker-low")
    result = dispatch(request(), session="child")
    assert not result.changed and not scorer.calls


def test_concurrent_conversations_are_isolated(dispatched, monkeypatch):
    _, scorer = prepare(dispatched, monkeypatch)
    def run(item):
        session, text = item
        return dispatch(request(text), session=session).payload["reasoning_effort"]
    with ThreadPoolExecutor(max_workers=2) as executor:
        values = list(executor.map(run, [("concurrent-a", "marker-low"), ("concurrent-b", "marker-max")]))
    assert values == ["low", "max"]
    assert len(scorer.calls) == 2


def test_same_turn_endpoint_change_cannot_reuse_qualified_choice(dispatched, monkeypatch):
    _, scorer = prepare(dispatched, monkeypatch)
    first = dispatch(request("marker-max"), session="route-change", turn="1")
    assert first.payload["reasoning_effort"] == "max"
    body = request("marker-max", effort="high")
    changed_endpoint = dispatch(body, session="route-change", turn="1",
                                base_url="https://relay.example/v1")
    assert not changed_endpoint.changed and changed_endpoint.payload == body
    assert len(scorer.calls) == 1


def test_native_zai_transport_to_effort_middleware(dispatched, monkeypatch):
    import importlib.util
    from pathlib import Path
    from conftest import HERMES_SOURCE_ROOT
    from agent.transports.chat_completions import ChatCompletionsTransport
    profile_path = Path(HERMES_SOURCE_ROOT) / "plugins/model-providers/zai/__init__.py"
    spec = importlib.util.spec_from_file_location("mmx_qualified_zai_profile", profile_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _, scorer = prepare(dispatched, monkeypatch, Scorer(force="max"))
    kwargs = ChatCompletionsTransport().build_kwargs(
        model="glm-5.3", messages=[{"role": "user", "content": "marker-max"}], tools=None,
        provider_profile=module.zai, reasoning_config={"enabled": True, "effort": "high"},
        base_url=ROUTE["base_url"], provider_name="zai")
    before = deepcopy(kwargs)
    result = dispatch(kwargs, session="native-transport")
    assert result.changed and result.payload["reasoning_effort"] == "max"
    assert result.payload["extra_body"]["thinking"] == {"type": "enabled", "clear_thinking": False}
    assert kwargs == before
    assert len(scorer.calls) == 1
