"""Pure tests for first-party ChatGPT Desktop provider identity evidence."""
from dataclasses import replace

import pytest

from control_plane.operator_harness_contract import (
    OperationId,
    OperationIntentReceipt,
    OperationIntentTarget,
    OperationKind,
    OperationResolution,
)
from integrations.chatgpt_desktop.provider_identity import (
    MAX_PROVIDER_LOG_LINE_BYTES,
    MAX_PROVIDER_LOG_LINES,
    NativeThreadIdentity,
    ProviderLogBinding,
    bind_native_turn_evidence,
    parse_native_thread_identities,
    parse_thread_items_observations,
    provider_log_binding,
    qualify_bound_thread,
    qualify_new_turn,
)
from integrations.chatgpt_desktop.turn import (
    DesktopSnapshot,
    DesktopTarget,
    EvidenceError,
    MessageEvidence,
    ModeSelection,
    prepare_turn,
    reconcile_turn,
)

APP_SESSION = "0e5071d2-6744-4025-be75-74a52d629fcd"
CONVERSATION = "01a0f046-2c55-74e3-a9da-5beb58a140f7"
OTHER_CONVERSATION = "01a0f4b0-23c8-70bb-a0e7-832e34f7e0c3"
TURN_1 = "01a0fac5-caaf-7613-a997-739a1fa4a049"
TURN_2 = "01a0fb13-94e8-77c3-b187-bb1002eed0fe"
OTHER_TURN = "01a0f4b0-2b47-77d2-a54e-c7bc2a46992f"
PID = 10061
LOG_NAME = (
    f"codex-desktop-{APP_SESSION}-{PID}-t0-i1-000006-0.log"
)
T0 = 1790913801.524
T1 = 1790913805.524


def _target(conversation=CONVERSATION, pid=PID):
    return DesktopTarget(
        OperationIntentTarget(
            OperationKind.BEGIN_TURN,
            "ATT-IDENTITY",
            "EPOCH-IDENTITY",
            "GEN-IDENTITY",
            "WORKER-IDENTITY",
            conversation,
        ),
        "bind-identity",
        1,
        "host-identity",
        "seat-identity",
        "project-identity",
        "com.openai.codex",
        "26.928.21956",
        pid,
        "process-start-identity",
        456,
    )


def _resume(
    conversation=CONVERSATION,
    turn=TURN_1,
    timestamp="2026-10-02T04:03:21.524Z",
    *,
    thread=None,
    visibility="visible",
    role="owner",
    settings="true",
):
    thread = conversation if thread is None else thread
    return (
        f"{timestamp} info [electron-message-handler] maybe_resume_success "
        "activePermissionProfileChanged=false "
        f"assignedStreamRole={role} conversationId={conversation} "
        f"documentVisibilityState={visibility} "
        f"hasLatestThreadSettings={settings} latestTurnId={turn} "
        f"threadId={thread}"
    )


def _items(
    conversation=CONVERSATION,
    timestamp="2026-10-02T04:03:22.000Z",
):
    return (
        f"{timestamp} info [AppServerConnection] response_routed "
        "broadcastFallback=false "
        f"conversationId={conversation} durationMs=10 "
        "method=thread/items/list requestId="
        "e84af317-4601-48ae-b123-af12cd05050a"
    )


def test_log_filename_binds_exact_app_session_and_pid():
    binding = provider_log_binding(LOG_NAME, expected_pid=PID)
    assert binding == ProviderLogBinding(LOG_NAME, PID, APP_SESSION)

    with pytest.raises(EvidenceError, match="provider_log_pid_mismatch"):
        provider_log_binding(LOG_NAME, expected_pid=PID + 1)

    for name in (
        "codex-desktop.log",
        f"codex-desktop-{APP_SESSION}-{PID}.log",
        f"other-{APP_SESSION}-{PID}-t0-i1-000006-0.log",
    ):
        with pytest.raises(EvidenceError, match="provider_log_name_invalid"):
            provider_log_binding(name, expected_pid=PID)


def test_parse_resume_emits_only_closed_native_identity_fields():
    binding = provider_log_binding(LOG_NAME, expected_pid=PID)
    source = _resume() + " prompt=SECRET transcript=DO_NOT_RETURN"
    rows = parse_native_thread_identities(binding, [source])
    assert len(rows) == 1
    row = rows[0]
    assert row.conversation_id == CONVERSATION
    assert row.thread_id == CONVERSATION
    assert row.latest_turn_id == TURN_1
    assert row.document_visibility == "visible"
    assert row.assigned_stream_role == "owner"
    assert row.has_latest_thread_settings is True
    assert "SECRET" not in repr(row)
    assert "DO_NOT_RETURN" not in repr(row)


def test_runtime_bound_conversation_wins_over_prefetch_recency():
    binding = provider_log_binding(LOG_NAME, expected_pid=PID)
    lines = [
        _resume(
            OTHER_CONVERSATION,
            OTHER_TURN,
            "2026-10-02T04:03:22.000Z",
        ),
        _resume(
            CONVERSATION,
            TURN_1,
            "2026-10-02T04:03:21.524Z",
        ),
        _resume(
            OTHER_CONVERSATION,
            OTHER_TURN,
            "2026-10-02T04:03:23.000Z",
        ),
    ]
    observed = qualify_bound_thread(_target(), binding, lines)
    assert observed.conversation_id == CONVERSATION
    assert observed.latest_turn_id == TURN_1


def test_runtime_provider_session_must_be_provider_uuid():
    binding = provider_log_binding(LOG_NAME, expected_pid=PID)
    with pytest.raises(EvidenceError, match="provider_session_identity_unqualified"):
        qualify_bound_thread(_target("conversation-title"), binding, [_resume()])


def test_bound_target_pid_must_match_provider_log_pid():
    binding = provider_log_binding(LOG_NAME, expected_pid=PID)
    with pytest.raises(EvidenceError, match="provider_log_pid_mismatch"):
        qualify_bound_thread(_target(pid=PID + 1), binding, [_resume()])


@pytest.mark.parametrize(
    "line,reason",
    [
        (
            _resume(thread=OTHER_CONVERSATION),
            "provider_conversation_thread_mismatch",
        ),
        (
            _resume(visibility="hidden"),
            "provider_thread_not_visible",
        ),
        (
            _resume(role="observer"),
            "provider_thread_not_owned",
        ),
        (
            _resume(settings="false"),
            "provider_thread_settings_unqualified",
        ),
    ],
)
def test_unqualified_resume_identity_refuses(line, reason):
    binding = provider_log_binding(LOG_NAME, expected_pid=PID)
    with pytest.raises(EvidenceError, match=reason):
        parse_native_thread_identities(binding, [line])


def test_non_resume_lines_cannot_mint_thread_identity():
    binding = provider_log_binding(LOG_NAME, expected_pid=PID)
    lookalike = _resume().replace(
        "[electron-message-handler] maybe_resume_success",
        "[arbitrary-component] not_a_resume",
    )
    assert parse_native_thread_identities(binding, [lookalike]) == ()


def test_thread_items_parser_is_content_free_and_method_exact():
    binding = provider_log_binding(LOG_NAME, expected_pid=PID)
    rows = parse_thread_items_observations(
        binding,
        [
            _items() + " transcript=SECRET",
            _items().replace("method=thread/items/list", "method=thread/delete"),
        ],
    )
    assert len(rows) == 1
    assert rows[0].conversation_id == CONVERSATION
    assert "SECRET" not in repr(rows[0])


def test_bound_thread_not_before_blocks_stale_identity():
    binding = provider_log_binding(LOG_NAME, expected_pid=PID)
    with pytest.raises(EvidenceError, match="provider_bound_thread_not_observed"):
        qualify_bound_thread(
            _target(),
            binding,
            [_resume()],
            not_before=T0 + 1,
        )
    assert qualify_bound_thread(
        _target(),
        binding,
        [_resume()],
        not_before=T0,
    ).latest_turn_id == TURN_1


def test_new_turn_requires_same_bound_conversation_and_changed_native_turn():
    binding = provider_log_binding(LOG_NAME, expected_pid=PID)
    advanced = _resume(
        CONVERSATION,
        TURN_2,
        "2026-10-02T04:03:25.524Z",
    )
    observed = qualify_new_turn(
        _target(),
        binding,
        [advanced],
        previous_turn_id=TURN_1,
        not_before=T1,
    )
    assert observed.latest_turn_id == TURN_2
    assert observed.conversation_id == CONVERSATION

    with pytest.raises(EvidenceError, match="provider_turn_not_advanced"):
        qualify_new_turn(
            _target(),
            binding,
            [_resume(timestamp="2026-10-02T04:03:25.524Z")],
            previous_turn_id=TURN_1,
            not_before=T1,
        )

    with pytest.raises(EvidenceError, match="provider_bound_thread_not_observed"):
        qualify_new_turn(
            _target(),
            binding,
            [_resume(
                OTHER_CONVERSATION,
                OTHER_TURN,
                "2026-10-02T04:03:25.524Z",
            )],
            previous_turn_id=TURN_1,
            not_before=T1,
        )


def test_same_timestamp_duplicate_bound_identity_is_ambiguous():
    binding = provider_log_binding(LOG_NAME, expected_pid=PID)
    lines = [
        _resume(CONVERSATION, TURN_1),
        _resume(CONVERSATION, TURN_2),
    ]
    with pytest.raises(EvidenceError, match="provider_bound_thread_ambiguous"):
        qualify_bound_thread(_target(), binding, lines)


@pytest.mark.parametrize("previous", ["", "not-a-uuid", True, None])
def test_previous_turn_must_be_provider_uuid(previous):
    binding = provider_log_binding(LOG_NAME, expected_pid=PID)
    with pytest.raises(EvidenceError, match="provider_previous_turn_invalid"):
        qualify_new_turn(
            _target(),
            binding,
            [_resume()],
            previous_turn_id=previous,
            not_before=T0,
        )


@pytest.mark.parametrize("value", [True, 0, -1, "now"])
def test_not_before_is_not_coerced(value):
    binding = provider_log_binding(LOG_NAME, expected_pid=PID)
    with pytest.raises(EvidenceError, match="provider_identity_time_invalid"):
        qualify_bound_thread(
            _target(),
            binding,
            [_resume()],
            not_before=value,
        )


def test_line_and_collection_budgets_are_closed():
    binding = provider_log_binding(LOG_NAME, expected_pid=PID)
    with pytest.raises(EvidenceError, match="provider_log_line_invalid"):
        parse_native_thread_identities(
            binding,
            ["x" * (MAX_PROVIDER_LOG_LINE_BYTES + 1)],
        )
    with pytest.raises(EvidenceError, match="provider_log_line_budget_exceeded"):
        parse_native_thread_identities(
            binding,
            ["irrelevant"] * (MAX_PROVIDER_LOG_LINES + 1),
        )


@pytest.mark.parametrize("lines", ["a line", b"bytes", [b"bytes"], [None]])
def test_log_input_shape_is_not_coerced(lines):
    binding = provider_log_binding(LOG_NAME, expected_pid=PID)
    with pytest.raises(EvidenceError):
        parse_native_thread_identities(binding, lines)


def test_timestamp_and_native_ids_are_strict():
    binding = provider_log_binding(LOG_NAME, expected_pid=PID)
    bad_time = _resume().replace(
        "2026-10-02T04:03:21.524Z",
        "not-a-time",
    )
    with pytest.raises(EvidenceError, match="provider_log_timestamp_invalid"):
        parse_native_thread_identities(binding, [bad_time])

    bad_turn = _resume().replace(TURN_1, "not-a-turn")
    with pytest.raises(EvidenceError, match="provider_latest_turn_id_missing"):
        parse_native_thread_identities(binding, [bad_turn])


def test_native_thread_identity_constructor_does_not_accept_mismatched_thread():
    binding = provider_log_binding(LOG_NAME, expected_pid=PID)
    with pytest.raises(EvidenceError, match="provider_conversation_thread_mismatch"):
        NativeThreadIdentity(
            binding=binding,
            observed_at=T0,
            conversation_id=CONVERSATION,
            thread_id=OTHER_CONVERSATION,
            latest_turn_id=TURN_1,
            document_visibility="visible",
            assigned_stream_role="owner",
            has_latest_thread_settings=True,
        )


def test_other_provider_session_cannot_be_retargeted_after_plan_creation():
    binding = provider_log_binding(LOG_NAME, expected_pid=PID)
    target = _target()
    wrong = replace(
        target,
        intent_target=replace(
            target.intent_target,
            provider_session_id=OTHER_CONVERSATION,
        ),
    )
    rows = [_resume(CONVERSATION, TURN_1)]
    assert qualify_bound_thread(target, binding, rows).conversation_id == CONVERSATION
    with pytest.raises(EvidenceError, match="provider_bound_thread_not_observed"):
        qualify_bound_thread(wrong, binding, rows)


def _unbound_turn_case():
    target = _target()
    intent = OperationIntentReceipt(
        OperationId("ohf-op:provider-identity-turn"),
        target.intent_target,
    )
    mode = ModeSelection("chat", "Fixture Exact Model", "PRO")
    before = DesktopSnapshot(
        target,
        "snapshot-before-provider-identity",
        T0,
        "semantic",
        True,
        mode,
        "idle",
        "",
        (),
    )
    plan = prepare_turn(
        intent=intent,
        target=target,
        requested_mode=mode,
        prompt="Return the canary result.",
        snapshot=before,
        now=T0,
    )
    user = MessageEvidence(
        "user-provider-identity",
        "user",
        plan.wire_text,
        True,
    )
    reply = MessageEvidence(
        "assistant-provider-identity",
        "assistant",
        "Canary result.",
        True,
        reply_to_user_id=user.message_id,
    )
    after = replace(
        before,
        snapshot_id="snapshot-after-provider-identity",
        observed_at=T1,
        messages=(user, reply),
    )
    binding = provider_log_binding(LOG_NAME, expected_pid=PID)
    identity = NativeThreadIdentity(
        binding=binding,
        observed_at=T1,
        conversation_id=CONVERSATION,
        thread_id=CONVERSATION,
        latest_turn_id=TURN_2,
        document_visibility="visible",
        assigned_stream_role="owner",
        has_latest_thread_settings=True,
    )
    return plan, after, identity, user, reply


def test_provider_native_identity_joins_ax_turn_without_weakening_reconciler():
    plan, after, identity, user, reply = _unbound_turn_case()
    before_join = reconcile_turn(plan, after, now=T1)
    assert before_join.input_effect == OperationResolution.EFFECT_UNKNOWN

    joined = bind_native_turn_evidence(plan, after, identity)
    bound_user, bound_reply = joined.messages
    assert bound_user.message_id == user.message_id
    assert bound_reply.message_id == reply.message_id
    assert bound_user.native_turn_id == TURN_2
    assert bound_reply.native_turn_id == TURN_2

    result = reconcile_turn(plan, joined, now=T1)
    assert result.input_effect == OperationResolution.APPLIED
    assert result.response_state == "complete"
    assert result.provider_native_turn_id == TURN_2
    assert result.response_text == "Canary result."


def test_provider_join_can_confirm_input_before_assistant_exists():
    plan, after, identity, user, _ = _unbound_turn_case()
    user_only = replace(after, messages=(user,))
    joined = bind_native_turn_evidence(plan, user_only, identity)
    result = reconcile_turn(plan, joined, now=T1)
    assert result.input_effect == OperationResolution.APPLIED
    assert result.response_state == "active"
    assert result.provider_native_turn_id == TURN_2


def test_provider_join_refuses_wrong_native_conversation():
    plan, after, identity, *_ = _unbound_turn_case()
    wrong = replace(
        identity,
        conversation_id=OTHER_CONVERSATION,
        thread_id=OTHER_CONVERSATION,
    )
    with pytest.raises(EvidenceError, match="provider_turn_join_session_mismatch"):
        bind_native_turn_evidence(plan, after, wrong)


def test_provider_join_refuses_identity_from_before_prepared_turn():
    plan, after, identity, *_ = _unbound_turn_case()
    stale = replace(identity, observed_at=T0 - 1)
    with pytest.raises(EvidenceError, match="provider_turn_join_stale_identity"):
        bind_native_turn_evidence(plan, after, stale)


def test_provider_join_refuses_conflicting_ax_native_identity():
    plan, after, identity, user, reply = _unbound_turn_case()
    conflict = replace(user, native_turn_id=OTHER_TURN)
    with pytest.raises(EvidenceError, match="provider_turn_join_native_id_conflict"):
        bind_native_turn_evidence(
            plan,
            replace(after, messages=(conflict, reply)),
            identity,
        )


def test_provider_join_refuses_duplicate_marker_users():
    plan, after, identity, user, reply = _unbound_turn_case()
    duplicate = replace(user, message_id="user-provider-identity-2")
    with pytest.raises(EvidenceError, match="provider_turn_join_user_ambiguous"):
        bind_native_turn_evidence(
            plan,
            replace(after, messages=(user, duplicate, reply)),
            identity,
        )


def test_provider_join_refuses_multiple_reply_branches():
    plan, after, identity, user, reply = _unbound_turn_case()
    duplicate = replace(
        reply,
        message_id="assistant-provider-identity-2",
    )
    with pytest.raises(EvidenceError, match="provider_turn_join_reply_ambiguous"):
        bind_native_turn_evidence(
            plan,
            replace(after, messages=(user, reply, duplicate)),
            identity,
        )


def test_provider_join_does_not_stamp_unrelated_messages():
    plan, after, identity, user, reply = _unbound_turn_case()
    old = MessageEvidence(
        "old-message",
        "assistant",
        "Old response.",
        True,
        native_turn_id=TURN_1,
    )
    joined = bind_native_turn_evidence(
        plan,
        replace(after, messages=(old, user, reply)),
        identity,
    )
    assert joined.messages[0] == old
    assert joined.messages[1].native_turn_id == TURN_2
    assert joined.messages[2].native_turn_id == TURN_2


def test_provider_join_requires_exact_ax_payload_completion():
    plan, after, identity, user, reply = _unbound_turn_case()
    for changed in (
        replace(user, complete=False),
        replace(user, text=plan.wire_text + " changed"),
    ):
        with pytest.raises(EvidenceError, match="provider_turn_join_user_unverified"):
            bind_native_turn_evidence(
                plan,
                replace(after, messages=(changed, reply)),
                identity,
            )
