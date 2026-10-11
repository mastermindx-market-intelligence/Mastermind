"""Synthetic consumer tests. No test opens an app or calls a provider."""
from dataclasses import replace
import importlib
import socket
import subprocess

import pytest

from control_plane.operator_harness_contract import (
    OperationId, OperationIntentReceipt, OperationIntentTarget, OperationKind,
    OperationResolution,
)
from integrations.chatgpt_desktop.turn import (
    DesktopSnapshot, DesktopTarget, EvidenceError, MessageEvidence, ModeSelection,
    MAX_TEXT_BYTES, prepare_turn, reconcile_turn, verify_pre_dispatch,
)

NOW = 1800000000.0


@pytest.fixture
def case():
    target = DesktopTarget(
        OperationIntentTarget(OperationKind.BEGIN_TURN, 'ATT-001', 'EPOCH-1',
                              'GEN-1', 'WORKER-1', 'conversation-1'),
        'bind-fixture', 1, 'host-fixture', 'seat-fixture', 'project-fixture',
        'fixture.chatgpt', 'fixture-build-1', 123, 'process-start-fixture', 456,
    )
    intent = OperationIntentReceipt(OperationId('ohf-op:fixture-turn-1'), target.intent_target)
    mode = ModeSelection('chat', 'Fixture Model', 'PRO')
    before = DesktopSnapshot(target, 'snapshot-before', NOW, 'semantic', True,
                             mode, 'idle', '', ())
    plan = prepare_turn(intent=intent, target=target, requested_mode=mode,
                        prompt='Reply with the canary result.', snapshot=before, now=NOW)
    user = MessageEvidence('user-1', 'user', plan.wire_text, True, 'native-turn-1')
    reply = MessageEvidence('assistant-1', 'assistant', 'Canary result.', True,
                            'native-turn-1', 'user-1')
    after = replace(before, snapshot_id='snapshot-after', observed_at=NOW + 1,
                    messages=(user, reply))
    return target, intent, mode, before, plan, user, reply, after


def test_completed_roundtrip_returns_exact_text_not_mission_acceptance(case):
    *_, plan, user, reply, after = case
    result = reconcile_turn(plan, after, now=NOW + 1)
    assert result.input_effect == OperationResolution.APPLIED
    assert result.response_state == 'complete'
    assert result.response_text == reply.text
    assert result.user_message_id == user.message_id
    assert result.as_turn_start().acknowledged is True
    assert result.as_turn_start().provider_native_turn_id == 'native-turn-1'
    assert result.served_model == 'UNKNOWN'


@pytest.mark.parametrize('surface,effort', [('chat', 'PRO'), ('chat', 'EXTRA_HIGH'),
                                          ('work', 'EXTRA_HIGH')])
def test_exact_mode_is_data_not_hardcoded_model_routing(case, surface, effort):
    target, intent, _, before, _, _, _, _ = case
    mode = ModeSelection(surface, 'Fixture Exact Model', effort)
    snapshot = replace(before, mode=mode)
    plan = prepare_turn(intent=intent, target=target, requested_mode=mode,
                        prompt='canary', snapshot=snapshot, now=NOW,
                        allowed_surfaces=frozenset({surface}))
    verify_pre_dispatch(plan, replace(snapshot, snapshot_id='fresh'), now=NOW)
    assert plan.requested_mode == mode


@pytest.mark.parametrize('model', ['Latest', 'latest', 'AUTO', 'UNKNOWN'])
def test_unattested_aliases_are_not_exact_model_evidence(model):
    with pytest.raises(EvidenceError, match='model_alias_not_attested'):
        ModeSelection('chat', model, 'PRO')


@pytest.mark.parametrize('field,value', [
    ('binding_id', 'bind-other'), ('binding_generation', 2), ('host_ref', 'other-host'),
    ('seat_ref', 'other-seat'), ('project_ref', 'other-project'),
    ('app_bundle_id', 'other.app'), ('app_version', 'next-build'), ('pid', 124),
    ('process_start_ref', 'reused-pid-new-process'), ('window_id', 457),
])
def test_every_target_axis_is_exact_before_and_after_dispatch(case, field, value):
    target, intent, mode, before, plan, _, _, after = case
    wrong = replace(target, **{field: value})
    with pytest.raises(EvidenceError, match='exact_target_mismatch'):
        prepare_turn(intent=intent, target=target, requested_mode=mode, prompt='x',
                     snapshot=replace(before, target=wrong), now=NOW)
    result = reconcile_turn(plan, replace(after, target=wrong), now=NOW + 1)
    assert result.input_effect == OperationResolution.EFFECT_UNKNOWN
    assert result.response_text is None


@pytest.mark.parametrize('field,value', [
    ('attempt_id', 'ATT-OTHER'), ('session_epoch_id', 'EPOCH-OTHER'),
    ('process_generation_id', 'GEN-OTHER'), ('worker_id', 'WORKER-OTHER'),
    ('provider_session_id', 'conversation-other'),
])
def test_runtime_identity_cannot_retarget_a_prepared_turn(case, field, value):
    target, intent, mode, before, plan, _, _, after = case
    wrong = replace(target, intent_target=replace(target.intent_target, **{field: value}))
    with pytest.raises(EvidenceError, match='intent_target_mismatch'):
        prepare_turn(intent=intent, target=wrong, requested_mode=mode, prompt='x',
                     snapshot=replace(before, target=wrong), now=NOW)
    assert reconcile_turn(plan, replace(after, target=wrong), now=NOW + 1).response_text is None


@pytest.mark.parametrize('source,complete', [('ocr', True), ('unknown', True), ('semantic', False)])
def test_ocr_and_incomplete_capture_cannot_prove_delivery(case, source, complete):
    target, intent, mode, before, plan, _, _, after = case
    with pytest.raises(EvidenceError, match='insufficient_semantic_evidence'):
        prepare_turn(intent=intent, target=target, requested_mode=mode, prompt='x',
                     snapshot=replace(before, source=source, scope_complete=complete), now=NOW)
    result = reconcile_turn(plan, replace(after, source=source, scope_complete=complete), now=NOW + 1)
    assert result.input_effect == OperationResolution.EFFECT_UNKNOWN


@pytest.mark.parametrize('state', ['generating', 'failed', 'blocked', 'unknown'])
def test_prepare_never_interrupts_an_active_or_unknown_turn(case, state):
    target, intent, mode, before, *_ = case
    with pytest.raises(EvidenceError, match='surface_not_ready'):
        prepare_turn(intent=intent, target=target, requested_mode=mode, prompt='x',
                     snapshot=replace(before, state=state), now=NOW)


@pytest.mark.parametrize('reason', ['safety', 'permission', 'auth', 'quota', 'transport', 'unknown'])
def test_block_reason_prevents_prepare_and_never_erases_confirmed_input(case, reason):
    target, intent, mode, before, plan, _, _, after = case
    with pytest.raises(EvidenceError, match='surface_not_ready'):
        prepare_turn(intent=intent, target=target, requested_mode=mode, prompt='x',
                     snapshot=replace(before, block_reason=reason), now=NOW)
    result = reconcile_turn(plan, replace(after, block_reason=reason), now=NOW + 1)
    assert result.input_effect == OperationResolution.APPLIED
    assert result.response_state == 'error'
    assert result.requested_next_mode is None


def test_existing_draft_is_not_overwritten(case):
    target, intent, mode, before, *_ = case
    with pytest.raises(EvidenceError, match='existing_composer_draft'):
        prepare_turn(intent=intent, target=target, requested_mode=mode, prompt='x',
                     snapshot=replace(before, composer_text='user owned draft'), now=NOW)


def test_visible_operation_is_not_prepared_twice(case):
    target, intent, mode, before, plan, user, *_ = case
    with pytest.raises(EvidenceError, match='operation_already_visible'):
        prepare_turn(intent=intent, target=target, requested_mode=mode, prompt='changed payload',
                     snapshot=replace(before, messages=(user,)), now=NOW)


def test_mode_mismatch_is_not_a_silent_fallback(case):
    target, intent, mode, before, *_ = case
    with pytest.raises(EvidenceError, match='mode_not_verified'):
        prepare_turn(intent=intent, target=target, requested_mode=mode, prompt='x',
                     snapshot=replace(before, mode=ModeSelection('work', 'Fixture Model', 'EXTRA_HIGH')),
                     now=NOW)


@pytest.mark.parametrize('observed', [NOW - 6, NOW + 2])
def test_stale_or_future_evidence_is_unknown(case, observed):
    *_, plan, _, _, after = case
    result = reconcile_turn(plan, replace(after, observed_at=observed), now=NOW)
    assert result.input_effect == OperationResolution.EFFECT_UNKNOWN


@pytest.mark.parametrize('bad', [True, 0, -1, float('nan'), float('inf'), 'now'])
def test_bad_clocks_are_rejected(case, bad):
    before = case[3]
    with pytest.raises(EvidenceError, match='invalid_observation_time'):
        replace(before, observed_at=bad)


def test_second_observation_is_required_before_dispatch(case):
    before, plan = case[3:5]
    verify_pre_dispatch(plan, replace(before, snapshot_id='fresh', observed_at=NOW + 1), now=NOW + 1)
    with pytest.raises(EvidenceError, match='pre_dispatch_state_changed'):
        verify_pre_dispatch(plan, replace(before, snapshot_id='fresh', composer_text='new human draft'), now=NOW)
    with pytest.raises(EvidenceError, match='prepared_turn_expired'):
        verify_pre_dispatch(plan, replace(before, snapshot_id='fresh', observed_at=NOW + 6), now=NOW + 6)


def test_missing_response_or_disconnection_never_proves_no_effect(case):
    *_, plan, user, _, after = case
    for snapshot in (None, replace(after, messages=())):
        result = reconcile_turn(plan, snapshot, now=NOW + 1)
        assert result.input_effect == OperationResolution.EFFECT_UNKNOWN
        assert result.as_turn_start().acknowledged is False
    result = reconcile_turn(plan, replace(after, messages=(user,)), now=NOW + 1)
    assert result.input_effect == OperationResolution.APPLIED
    assert result.response_state == 'active'


def test_old_snapshot_cannot_confirm_dispatch(case):
    before, plan = case[3:5]
    result = reconcile_turn(plan, before, now=NOW)
    assert result.reason == 'pre_dispatch_observation_reused'


@pytest.mark.parametrize('changes', [
    {'text': 'different content'}, {'complete': False}, {'native_turn_id': None},
])
def test_full_user_payload_and_native_turn_identity_are_required(case, changes):
    *_, plan, user, reply, after = case
    changed = replace(user, **changes)
    result = reconcile_turn(plan, replace(after, messages=(changed, reply)), now=NOW + 1)
    assert result.input_effect == OperationResolution.EFFECT_UNKNOWN


def test_duplicate_operation_bubbles_are_ambiguous_not_success(case):
    *_, plan, user, reply, after = case
    duplicate = replace(user, message_id='user-2')
    result = reconcile_turn(plan, replace(after, messages=(user, duplicate, reply)), now=NOW + 1)
    assert result.response_state == 'ambiguous'
    assert result.input_effect == OperationResolution.EFFECT_UNKNOWN


@pytest.mark.parametrize('role', ['assistant', 'tool', 'system'])
def test_quoted_prompt_in_other_roles_cannot_confirm_input(case, role):
    *_, plan, user, _, after = case
    result = reconcile_turn(plan, replace(after, messages=(replace(user, role=role),)), now=NOW + 1)
    assert result.input_effect == OperationResolution.EFFECT_UNKNOWN


@pytest.mark.parametrize('changes,state', [
    ({'complete': False}, 'idle'), ({'text': ''}, 'idle'), ({}, 'generating'), ({}, 'unknown'),
])
def test_partial_empty_or_still_generating_answer_is_not_relayed(case, changes, state):
    *_, plan, user, reply, after = case
    result = reconcile_turn(plan, replace(after, state=state, messages=(user, replace(reply, **changes))), now=NOW + 1)
    assert result.response_state == 'active'
    assert result.response_text is None


def test_wrong_reply_or_native_turn_is_not_relayed(case):
    *_, plan, user, reply, after = case
    wrong = replace(reply, reply_to_user_id='other-user')
    assert reconcile_turn(plan, replace(after, messages=(user, wrong)), now=NOW + 1).response_text is None
    wrong = replace(reply, native_turn_id='other-turn')
    assert reconcile_turn(plan, replace(after, messages=(user, wrong)), now=NOW + 1).response_state == 'ambiguous'


def test_multiple_answer_branches_are_not_guessed(case):
    *_, plan, user, reply, after = case
    duplicate = replace(reply, message_id='assistant-2')
    result = reconcile_turn(plan, replace(after, messages=(user, reply, duplicate)), now=NOW + 1)
    assert result.response_state == 'ambiguous'
    assert result.response_text is None


@pytest.mark.parametrize('text,expected', [
    ('Analysis complete.\nREQUEST_MODE: EXTRA_HIGH', 'EXTRA_HIGH'),
    ('Analysis complete.\nREQUEST_MODE: PRO\n', 'PRO'),
    ('REQUEST_MODE: PRO\nThis is a quotation.', None),
    ('```\nREQUEST_MODE: PRO\n```', None),
    ('> REQUEST_MODE: EXTRA_HIGH', None),
    ('REQUEST_MODE: ADMIN', None),
    (' REQUEST_MODE: PRO', None),
])
def test_only_terminal_completed_assistant_line_is_advice(case, text, expected):
    *_, plan, user, reply, after = case
    snapshot = replace(after, messages=(user, replace(reply, text=text)))
    result = reconcile_turn(plan, snapshot, now=NOW + 1)
    assert result.requested_next_mode == expected
    assert result.served_model == 'UNKNOWN'
    assert reconcile_turn(plan, replace(snapshot, state='generating'), now=NOW + 1).requested_next_mode is None


@pytest.mark.parametrize('bad', [True, 0, -1, 1.0, '123'])
def test_pids_and_generations_are_not_coerced(case, bad):
    with pytest.raises(EvidenceError, match='invalid_target_generation'):
        replace(case[0], pid=bad)


def test_text_bounds_and_duplicate_ids_are_enforced(case):
    before, _, user = case[3:6]
    for value in ('x' * (MAX_TEXT_BYTES + 1), '\ud800', 'nul\x00text'):
        with pytest.raises(EvidenceError):
            replace(user, text=value)
    with pytest.raises(EvidenceError, match='duplicate_message_identity'):
        replace(before, messages=(user, user))


def test_payload_digest_changes_with_prompt_or_target(case):
    target, intent, mode, before, plan, *_ = case
    other = prepare_turn(intent=intent, target=target, requested_mode=mode,
                         prompt='a different prompt', snapshot=before, now=NOW)
    assert len(plan.payload_digest) == 64
    assert plan.payload_digest != other.payload_digest


def test_import_and_reconcile_are_production_inert(case, monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('No network or process execution permitted')
    monkeypatch.setattr(socket, 'socket', deny)
    monkeypatch.setattr(subprocess, 'Popen', deny)
    import integrations.chatgpt_desktop
    importlib.reload(integrations.chatgpt_desktop)
    *_, plan, _, _, after = case
    assert reconcile_turn(plan, after, now=NOW + 1).response_state == 'complete'


@pytest.mark.parametrize('text', [
    '```\nREQUEST_MODE: PRO', '~~~python\nREQUEST_MODE: EXTRA_HIGH',
    '````\n```\nREQUEST_MODE: PRO',
])
def test_open_code_fence_never_becomes_mode_advice(case, text):
    *_, plan, user, reply, after = case
    result = reconcile_turn(plan, replace(after, messages=(user, replace(reply, text=text))), now=NOW + 1)
    assert result.requested_next_mode is None


def test_overflow_clock_is_a_static_validation_error(case):
    with pytest.raises(EvidenceError, match='invalid_observation_time'):
        replace(case[3], observed_at=10 ** 1000)


def test_completed_answer_before_its_user_is_ambiguous(case):
    *_, plan, user, reply, after = case
    result = reconcile_turn(plan, replace(after, messages=(reply, user)), now=NOW + 1)
    assert result.response_state == 'ambiguous'
    assert result.response_text is None


def test_aggregate_capture_size_is_bounded(case):
    messages = tuple(MessageEvidence(f'm-{i}', 'user', 'x' * MAX_TEXT_BYTES, True) for i in range(5))
    with pytest.raises(EvidenceError, match='snapshot_text_budget_exceeded'):
        replace(case[3], messages=messages)


@pytest.mark.parametrize('change', [
    {'wire_text': 'not correlated'}, {'before_digest': 'not a digest'},
    {'before_message_ids': ('same', 'same')}, {'prepared_at': True},
])
def test_malformed_prepared_turn_is_rejected(case, change):
    with pytest.raises(EvidenceError):
        replace(case[4], **change)


def test_malformed_canonical_receipt_is_not_promoted_to_permission(case):
    target, _, mode, before, *_ = case
    receipt = OperationIntentReceipt('not-an-operation-id', target.intent_target)
    with pytest.raises(EvidenceError, match='intent_target_mismatch'):
        prepare_turn(intent=receipt, target=target, requested_mode=mode,
                     prompt='canary', snapshot=before, now=NOW)


def test_extra_high_does_not_silently_enter_work_credit_surface(case):
    target, intent, _, before, *_ = case
    mode = ModeSelection('work', 'Fixture Exact Model', 'EXTRA_HIGH')
    with pytest.raises(EvidenceError, match='surface_not_in_admitted_envelope'):
        prepare_turn(intent=intent, target=target, requested_mode=mode,
                     prompt='canary', snapshot=replace(before, mode=mode), now=NOW)


@pytest.mark.parametrize('surfaces', [True, {'chat'}, frozenset(), frozenset({'codex'})])
def test_invalid_surface_envelope_is_rejected(case, surfaces):
    target, intent, mode, before, *_ = case
    with pytest.raises(EvidenceError, match='invalid_surface_envelope'):
        prepare_turn(intent=intent, target=target, requested_mode=mode,
                     prompt='canary', snapshot=before, now=NOW, allowed_surfaces=surfaces)


def test_original_snapshot_cannot_be_reused_as_the_pre_dispatch_check(case):
    before, plan = case[3:5]
    with pytest.raises(EvidenceError, match='fresh_pre_dispatch_observation_required'):
        verify_pre_dispatch(plan, before, now=NOW)
    with pytest.raises(EvidenceError, match='fresh_pre_dispatch_observation_required'):
        verify_pre_dispatch(plan, replace(before, snapshot_id='old', observed_at=NOW - 1), now=NOW)


def test_whitespace_only_answer_is_not_a_completed_return(case):
    *_, plan, user, reply, after = case
    result = reconcile_turn(plan, replace(after, messages=(user, replace(reply, text=' \n\t'))), now=NOW + 1)
    assert result.response_state == 'active'
    assert result.response_text is None
