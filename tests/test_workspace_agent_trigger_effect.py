"""Adversarial contracts for Executive-owned Workspace trigger effects."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

from control_plane.executive_runtime import Runtime
from integrations.workspace_agent_api import TriggerObservation
from integrations.workspace_agent_trigger import build_trigger_plan
from integrations.workspace_agent_trigger_effect import (
    EFFECT_SCHEMA,
    WorkspaceTriggerEffectBinding,
    WorkspaceTriggerEffectError,
    WorkspaceTriggerEffectOwner,
)

CHANNEL = "agtch_synthetic"
OPERATION = "workspace-op-001"
TOKEN = "SYNTHETIC_SECRET_TOKEN"


def binding(**overrides) -> WorkspaceTriggerEffectBinding:
    values = {
        "event_ref": "workspace-event-0001",
        "operation_key": OPERATION,
        "activation_digest": "1" * 64,
        "current_binding_digest": "2" * 64,
        "economic_envelope_digest": "3" * 64,
        "package_digest": "4" * 64,
    }
    values.update(overrides)
    return WorkspaceTriggerEffectBinding(**values)


def plan(*, text="Review one bounded responsibility.", operation=OPERATION):
    return build_trigger_plan(
        channel_id=CHANNEL,
        operation_key=operation,
        input_text=text,
        conversation_key="workspace-responsibility-1",
    )


class TriggerRecorder:
    def __init__(self, observation=None, error=None):
        self.observation = observation or TriggerObservation(
            "accepted",
            "ACCEPTED_UNCORRELATED",
        )
        self.error = error
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(dict(kwargs))
        if self.error is not None:
            raise self.error
        return self.observation


def events(runtime: Runtime):
    return runtime.events.list_events(aggregate_type="workspace_agent_trigger")


def test_first_acceptance_persists_intent_dispatch_and_applied_once(tmp_path):
    runtime = Runtime.at(tmp_path)
    trigger = TriggerRecorder()
    owner = WorkspaceTriggerEffectOwner(runtime, trigger_call=trigger)

    result = owner.execute_once(binding=binding(), plan=plan(), token=TOKEN)

    assert result.state == "APPLIED"
    assert result.reason == "PROVIDER_ACCEPTED_UNCORRELATED"
    assert result.provider_call_invoked is True
    assert result.provider_request_state == "PROVEN_SENT"
    assert result.replayed is False
    assert result.terminal_persisted is True
    assert len(trigger.calls) == 1

    recorded = events(runtime)
    assert [item.event_type for item in recorded] == [
        "WORKSPACE_AGENT_TRIGGER_INTENT",
        "WORKSPACE_AGENT_TRIGGER_DISPATCH_COMMITTED",
        "WORKSPACE_AGENT_TRIGGER_APPLIED",
    ]
    rendered = repr([item.to_dict() for item in recorded]) + repr(result)
    assert TOKEN not in rendered
    assert "Review one bounded responsibility." not in rendered

    reconciled = owner.reconcile(binding=binding(), plan=plan())
    assert reconciled.state == "APPLIED"
    assert reconciled.replayed is True
    assert reconciled.provider_call_invoked is False
    assert reconciled.provider_request_state == "PROVEN_SENT"
    assert reconciled.terminal_command_id == result.terminal_command_id


def test_matching_execute_replay_never_calls_provider_again(tmp_path):
    runtime = Runtime.at(tmp_path)
    trigger = TriggerRecorder()
    owner = WorkspaceTriggerEffectOwner(runtime, trigger_call=trigger)

    first = owner.execute_once(binding=binding(), plan=plan(), token=TOKEN)
    second = owner.execute_once(binding=binding(), plan=plan(), token="DIFFERENT_SECRET")

    assert first.state == second.state == "APPLIED"
    assert second.replayed is True
    assert second.provider_call_invoked is False
    assert second.provider_request_state == "PROVEN_SENT"
    assert len(trigger.calls) == 1
    assert len(events(runtime)) == 3


def test_same_event_changed_plan_or_economic_binding_conflicts_before_io(tmp_path):
    runtime = Runtime.at(tmp_path)
    trigger = TriggerRecorder()
    owner = WorkspaceTriggerEffectOwner(runtime, trigger_call=trigger)
    owner.execute_once(binding=binding(), plan=plan(), token=TOKEN)
    assert len(trigger.calls) == 1

    with pytest.raises(WorkspaceTriggerEffectError, match="EFFECT_EVENT_CONFLICT"):
        owner.execute_once(
            binding=binding(),
            plan=plan(text="Changed payload under same event."),
            token=TOKEN,
        )
    with pytest.raises(WorkspaceTriggerEffectError, match="EFFECT_EVENT_CONFLICT"):
        owner.execute_once(
            binding=binding(economic_envelope_digest="5" * 64),
            plan=plan(),
            token=TOKEN,
        )
    assert len(trigger.calls) == 1
    assert len(events(runtime)) == 3


def test_binding_operation_must_equal_plan_operation_before_runtime_write(tmp_path):
    runtime = Runtime.at(tmp_path)
    trigger = TriggerRecorder()
    owner = WorkspaceTriggerEffectOwner(runtime, trigger_call=trigger)

    with pytest.raises(WorkspaceTriggerEffectError, match="INVALID_EFFECT_BINDING"):
        owner.execute_once(
            binding=binding(operation_key="workspace-op-002"),
            plan=plan(),
            token=TOKEN,
        )
    assert events(runtime) == []
    assert trigger.calls == []


def test_known_provider_rejection_is_terminal_refusal_without_retry(tmp_path):
    runtime = Runtime.at(tmp_path)
    trigger = TriggerRecorder(
        TriggerObservation("rejected", "PROVIDER_REJECTED_401")
    )
    owner = WorkspaceTriggerEffectOwner(runtime, trigger_call=trigger)

    result = owner.execute_once(binding=binding(), plan=plan(), token=TOKEN)
    replay = owner.execute_once(binding=binding(), plan=plan(), token=TOKEN)

    assert result.state == "REFUSED"
    assert result.reason == "PROVIDER_REJECTED_401"
    assert replay.state == "REFUSED"
    assert replay.provider_call_invoked is False
    assert replay.provider_request_state == "PROVEN_SENT"
    assert len(trigger.calls) == 1
    assert [item.event_type for item in events(runtime)][-1] == (
        "WORKSPACE_AGENT_TRIGGER_REFUSED"
    )


def test_local_invalid_token_is_known_refusal_and_never_opens_network(tmp_path):
    runtime = Runtime.at(tmp_path)
    owner = WorkspaceTriggerEffectOwner(runtime)

    result = owner.execute_once(binding=binding(), plan=plan(), token="bad\nheader")

    assert result.state == "REFUSED"
    assert result.reason == "LOCAL_TRIGGER_REFUSED"
    assert result.provider_call_invoked is True
    assert result.provider_request_state == "PROVEN_NOT_SENT"
    # "sent" means this effect owner crossed its provider-call boundary; trigger_once
    # itself refused before creating a connection.
    assert [item.event_type for item in events(runtime)][-1] == (
        "WORKSPACE_AGENT_TRIGGER_REFUSED"
    )


@pytest.mark.parametrize(
    "observation",
    [
        TriggerObservation("unknown", "TRIGGER_EFFECT_UNKNOWN"),
        TriggerObservation(
            "accepted",
            "ACCEPTED_UNCORRELATED",
            run_id="apirun_fabricated",
            correlation_available=True,
        ),
        TriggerObservation("accepted", "OLD_BETA_REASON"),
    ],
)
def test_uncertain_or_correlation_shaped_observation_is_effect_unknown(
    tmp_path,
    observation,
):
    runtime = Runtime.at(tmp_path)
    trigger = TriggerRecorder(observation)
    owner = WorkspaceTriggerEffectOwner(runtime, trigger_call=trigger)

    result = owner.execute_once(binding=binding(), plan=plan(), token=TOKEN)

    assert result.state == "EFFECT_UNKNOWN"
    assert result.reason == "TRIGGER_EFFECT_UNKNOWN"
    assert len(trigger.calls) == 1
    assert [item.event_type for item in events(runtime)][-1] == (
        "WORKSPACE_AGENT_TRIGGER_EFFECT_UNKNOWN"
    )


def test_unexpected_trigger_exception_is_effect_unknown_and_not_retried(tmp_path):
    runtime = Runtime.at(tmp_path)
    trigger = TriggerRecorder(error=RuntimeError("SECRET_PROVIDER_EXCEPTION"))
    owner = WorkspaceTriggerEffectOwner(runtime, trigger_call=trigger)

    result = owner.execute_once(binding=binding(), plan=plan(), token=TOKEN)
    replay = owner.execute_once(binding=binding(), plan=plan(), token=TOKEN)

    assert result.state == "EFFECT_UNKNOWN"
    assert replay.state == "EFFECT_UNKNOWN"
    assert replay.provider_call_invoked is False
    assert replay.provider_request_state == "UNKNOWN"
    assert len(trigger.calls) == 1
    rendered = repr(result) + repr([item.to_dict() for item in events(runtime)])
    assert "SECRET_PROVIDER_EXCEPTION" not in rendered


def test_crash_after_provider_call_before_terminal_write_blocks_resend(tmp_path):
    runtime = Runtime.at(tmp_path)
    trigger = TriggerRecorder()
    owner = WorkspaceTriggerEffectOwner(runtime, trigger_call=trigger)
    original_transaction = runtime.store.transaction
    transaction_calls = 0

    @contextmanager
    def crash_on_terminal_transaction():
        nonlocal transaction_calls
        transaction_calls += 1
        if transaction_calls == 2:
            raise RuntimeError("synthetic process loss before terminal receipt")
        with original_transaction() as connection:
            yield connection

    runtime.store.transaction = crash_on_terminal_transaction
    with pytest.raises(RuntimeError, match="synthetic process loss"):
        owner.execute_once(binding=binding(), plan=plan(), token=TOKEN)
    runtime.store.transaction = original_transaction

    assert len(trigger.calls) == 1
    assert [item.event_type for item in events(runtime)] == [
        "WORKSPACE_AGENT_TRIGGER_INTENT",
        "WORKSPACE_AGENT_TRIGGER_DISPATCH_COMMITTED",
    ]

    recovered = owner.execute_once(binding=binding(), plan=plan(), token=TOKEN)
    assert recovered.state == "EFFECT_UNKNOWN"
    assert recovered.reason == "DISPATCH_COMMITTED_WITHOUT_TERMINAL"
    assert recovered.provider_call_invoked is False
    assert recovered.provider_request_state == "UNKNOWN"
    assert recovered.terminal_persisted is False
    assert len(trigger.calls) == 1
    assert len(events(runtime)) == 2


def test_duplicate_during_inflight_call_does_not_send_and_outer_can_finish(tmp_path):
    runtime = Runtime.at(tmp_path)
    nested_results = []
    calls = []
    owner = None

    def trigger_call(**kwargs):
        calls.append(dict(kwargs))
        nested_results.append(
            owner.execute_once(binding=binding(), plan=plan(), token="NESTED_SECRET")
        )
        return TriggerObservation("accepted", "ACCEPTED_UNCORRELATED")

    owner = WorkspaceTriggerEffectOwner(runtime, trigger_call=trigger_call)
    result = owner.execute_once(binding=binding(), plan=plan(), token=TOKEN)

    assert len(calls) == 1
    assert len(nested_results) == 1
    nested = nested_results[0]
    assert nested.state == "EFFECT_UNKNOWN"
    assert nested.reason == "DISPATCH_COMMITTED_WITHOUT_TERMINAL"
    assert nested.provider_call_invoked is False
    assert nested.provider_request_state == "UNKNOWN"
    assert nested.terminal_persisted is False
    assert result.state == "APPLIED"
    assert [item.event_type for item in events(runtime)] == [
        "WORKSPACE_AGENT_TRIGGER_INTENT",
        "WORKSPACE_AGENT_TRIGGER_DISPATCH_COMMITTED",
        "WORKSPACE_AGENT_TRIGGER_APPLIED",
    ]


def test_reconcile_before_intent_is_read_only_not_started(tmp_path):
    runtime = Runtime.at(tmp_path)
    trigger = TriggerRecorder()
    owner = WorkspaceTriggerEffectOwner(runtime, trigger_call=trigger)

    result = owner.reconcile(binding=binding(), plan=plan())

    assert result.state == "NOT_STARTED"
    assert result.provider_call_invoked is False
    assert result.provider_request_state == "PROVEN_NOT_SENT"
    assert result.terminal_persisted is False
    assert events(runtime) == []
    assert trigger.calls == []


def test_event_payload_is_secret_free_digest_only_manifest(tmp_path):
    runtime = Runtime.at(tmp_path)
    trigger = TriggerRecorder()
    owner = WorkspaceTriggerEffectOwner(runtime, trigger_call=trigger)
    task = "HIGHLY_PRIVATE_SUPERVISORY_PROMPT"
    built = plan(text=task)

    owner.execute_once(binding=binding(), plan=built, token=TOKEN)
    rendered = repr([item.payload for item in events(runtime)])

    assert TOKEN not in rendered
    assert task not in rendered
    assert built.payload_sha256 in rendered
    assert built.idempotency_key in rendered
    assert binding().economic_envelope_digest in rendered


def test_source_adds_no_workspace_state_or_retry_plane():
    source = (
        Path(__file__).resolve().parents[1]
        / "integrations"
        / "workspace_agent_trigger_effect.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "CREATE TABLE",
        "import sqlite3",
        "time.sleep",
        "requests.",
        "http.client",
        "read_run_once",
        "decode_run",
    )
    for item in forbidden:
        assert item not in source
    assert "events.command_id" in source
    assert "DISPATCH_COMMITTED" in source
    assert "trigger_once" in source
    assert EFFECT_SCHEMA in source
