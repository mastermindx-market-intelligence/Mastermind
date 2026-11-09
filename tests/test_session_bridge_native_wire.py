"""Protocol compilation/evidence tests. These do not invoke native providers."""
import importlib
import json
import pytest

NATIVE = "11111111-2222-4444-8888-999999999999"
OTHER = "aaaaaaaa-1111-4444-8888-bbbbbbbbbbbb"
ENDPOINT = "unix:///private/tmp/existing-codex-owner.sock"


def api():
    spec = importlib.util.find_spec("integrations.session_bridge.native_wire")
    assert spec is not None, "native attention wire compiler is not implemented"
    return importlib.import_module(spec.name)


def reference():
    return api().AttentionReference(operation_key="native-op-001", message_key="asd-executive-request-001")


def test_codex_queue_requires_exact_uuid_and_explicit_existing_endpoint():
    argv = api().codex_queue_arguments(session_id=NATIVE, endpoint=ENDPOINT, reference=reference())
    assert argv[:5] == ("queue", "--thread", NATIVE, "--remote", ENDPOINT)
    assert argv[5] == "--message" and "asd-executive-request-001" in argv[6]
    assert not any(v in argv for v in ("resume", "app-server", "--model", "--dangerously-bypass-approvals-and-sandbox"))


@pytest.mark.parametrize("session", ["latest", "newest-tab", "a session name", OTHER.upper(), "../session", "", None])
def test_codex_never_guesses_a_session(session):
    with pytest.raises(ValueError):
        api().codex_queue_arguments(session_id=session, endpoint=ENDPOINT, reference=reference())


@pytest.mark.parametrize("endpoint", [None, "", "unix://", "unix://relative.sock", "unix:///tmp/../other.sock",
    "ws://127.0.0.1:1234", "wss://external.example", "unix:///tmp/a.sock?token=secret", "unix:///tmp/a\x00.sock"])
def test_codex_never_falls_back_to_another_endpoint(endpoint):
    with pytest.raises(ValueError):
        api().codex_queue_arguments(session_id=NATIVE, endpoint=endpoint, reference=reference())


def test_steer_requires_expected_turn_and_carries_no_permission_overrides():
    frame = api().codex_steer_request(session_id=NATIVE, expected_turn_id="turn-001", reference=reference())
    assert frame["method"] == "turn/steer"
    assert frame["params"]["threadId"] == NATIVE
    assert frame["params"]["expectedTurnId"] == "turn-001"
    assert set(frame["params"]) == {"threadId", "expectedTurnId", "input"}
    assert frame["params"]["input"][0]["type"] == "text"


@pytest.mark.parametrize("turn", [None, "", "wrong turn\n", "../turn"])
def test_steer_missing_active_turn_does_not_become_new_turn(turn):
    with pytest.raises(ValueError):
        api().codex_steer_request(session_id=NATIVE, expected_turn_id=turn, reference=reference())


def test_claude_channel_is_bound_to_the_enrolled_session():
    frame = api().claude_channel_notification(session_id=NATIVE, bound_session_id=NATIVE,
        enrolled=True, reference=reference())
    assert frame["method"] == "notifications/claude/channel"
    assert frame["params"]["meta"]["message_key"] == "asd-executive-request-001"
    assert all(isinstance(v, str) for v in frame["params"]["meta"].values())
    assert "permission" not in frame["method"]


@pytest.mark.parametrize("bound,enrolled", [(OTHER, True), (NATIVE, False), (NATIVE, 1)])
def test_missing_or_wrong_channel_binding_is_refused(bound, enrolled):
    with pytest.raises(ValueError):
        api().claude_channel_notification(session_id=NATIVE, bound_session_id=bound,
            enrolled=enrolled, reference=reference())


@pytest.mark.parametrize("exit_code,state", [(0, "CLIENT_REPORTED_QUEUED"), (1, "EFFECT_UNKNOWN"),
    (None, "EFFECT_UNKNOWN"), (False, "EFFECT_UNKNOWN")])
def test_queue_success_is_not_consumption(exit_code, state):
    result = api().codex_queue_evidence(exit_code)
    assert result == {"state": state, "target_consumed": False, "parent_consumed": False}


def test_channel_write_success_is_not_delivery_acknowledgement():
    assert api().claude_channel_evidence(True) == {"state": "TRANSPORT_WRITTEN",
        "target_consumed": False, "parent_consumed": False}


@pytest.mark.parametrize("response", [{"id": "native-op-001", "result": {"turnId": "turn-002"}},
    {"id": "foreign", "result": {"turnId": "turn-001"}}, {},
    {"id": "native-op-001", "error": {"message": "secret diagnostic"}},
    {"id": "native-op-001", "result": {"turnId": "turn-001", "huge": "x" * 9000}}])
def test_steer_mismatch_or_oversized_result_stays_effect_unknown(response):
    result = api().codex_steer_evidence(response, operation_key="native-op-001", expected_turn_id="turn-001")
    assert result["state"] == "EFFECT_UNKNOWN" and result["target_consumed"] is False
    assert "secret" not in json.dumps(result) and "huge" not in json.dumps(result)


def test_matching_steer_response_is_only_acceptance_not_completion():
    response = {"id": "native-op-001", "result": {"turnId": "turn-001"}}
    result = api().codex_steer_evidence(response, operation_key="native-op-001", expected_turn_id="turn-001")
    assert result == {"state": "ACTIVE_TURN_ACCEPTED", "target_consumed": False, "parent_consumed": False}
