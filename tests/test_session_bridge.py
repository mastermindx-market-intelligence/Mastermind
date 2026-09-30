import asyncio

from integrations.session_bridge.gateway import SessionBridgeGateway
from integrations.session_bridge.schemas import tool_names, validate_tool_arguments


def test_closed_tool_surface():
    assert tool_names() == ("session_targets", "session_send", "session_summon")


def test_send_requires_exact_target_and_governed_continue_fields():
    args = validate_tool_arguments(
        "session_send",
        {
            "target_ref": "codex:attempt-7:g3",
            "instruction": "Continue the bounded repair.",
            "stop_condition": "Stop after the next validated result.",
            "operation_key": "dot-send-001",
        },
    )
    assert args["target_ref"] == "codex:attempt-7:g3"
    assert args["instruction"] == "Continue the bounded repair."


def test_send_refuses_extra_routing_fields():
    try:
        validate_tool_arguments(
            "session_send",
            {
                "target_ref": "codex:attempt-7:g3",
                "instruction": "Continue.",
                "stop_condition": "Stop after one result.",
                "operation_key": "dot-send-001",
                "fallback_target": "claude:any",
            },
        )
    except Exception as exc:
        assert "unexpected fields" in str(exc)
    else:
        raise AssertionError("fallback routing field must be refused")


def test_send_refuses_raw_message_side_channel():
    try:
        validate_tool_arguments(
            "session_send",
            {
                "target_ref": "codex:attempt-7:g3",
                "message": "inject this directly",
                "operation_key": "dot-send-001",
            },
        )
    except Exception:
        pass
    else:
        raise AssertionError("raw provider message input must be refused")


def test_summon_is_delegated_not_provider_spawned():
    seen = []

    async def summon(arguments):
        seen.append(arguments)
        return {"accepted": True, "job_id": "JOB-7", "dispatched": False}

    gateway = SessionBridgeGateway(
        target_reader=lambda _kind: [],
        reply_sender=lambda *_args: {"reply_committed": True},
        summoner=summon,
    )
    result = asyncio.run(
        gateway.call(
            "session_summon",
            {
                "objective": "inspect the failing integration",
                "execution_profile": "bounded_code_change",
                "operation_key": "dot-summon-001",
            },
        )
    )
    assert result["ok"] is True
    assert result["data"]["job_id"] == "JOB-7"
    assert seen == [
        {
            "objective": "inspect the failing integration",
            "execution_profile": "bounded_code_change",
            "operation_key": "dot-summon-001",
        }
    ]


def test_summon_refuses_model_visible_provider_selection():
    try:
        validate_tool_arguments(
            "session_summon",
            {
                "objective": "inspect the failing integration",
                "execution_profile": "bounded_code_change",
                "operation_key": "dot-summon-001",
                "preferred_surface": "codex",
            },
        )
    except Exception as exc:
        assert "unexpected fields" in str(exc)
    else:
        raise AssertionError("Dot must not bypass Capacity provider selection")


def test_reply_sender_receives_one_exact_target_only():
    calls = []

    def reply_sender(target_ref, instruction, stop_condition, operation_key):
        calls.append((target_ref, instruction, stop_condition, operation_key))
        return {"reply_committed": True, "target_ref": target_ref}

    gateway = SessionBridgeGateway(
        target_reader=lambda _kind: [],
        reply_sender=reply_sender,
        summoner=lambda _args: None,
    )
    result = asyncio.run(
        gateway.call(
            "session_send",
            {
                "target_ref": "claude:session:abc",
                "instruction": "Continue from the current canonical return.",
                "stop_condition": "Stop after the next result.",
                "operation_key": "dot-send-claude-001",
            },
        )
    )
    assert result["ok"] is True
    assert calls == [
        (
            "claude:session:abc",
            "Continue from the current canonical return.",
            "Stop after the next result.",
            "dot-send-claude-001",
        )
    ]


def test_summon_refuses_non_executive_profile():
    try:
        validate_tool_arguments(
            "session_summon",
            {
                "objective": "repair the failing integration",
                "execution_profile": "direct_provider_spawn",
                "operation_key": "dot-summon-invalid-001",
            },
        )
    except Exception as exc:
        assert "execution_profile is unsupported" in str(exc)
    else:
        raise AssertionError("invented summon profiles must be refused")
