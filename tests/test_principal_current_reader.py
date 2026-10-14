"""Real Relay read joined to synthetic, typed Executive observation facts.

These are source composition checks, not installed admission or Runtime proof.
"""
import asyncio
import dataclasses
import json
from types import SimpleNamespace

import pytest

from control_plane.executive_dialogue_observation import ACTIVE_CURRENT_WORKER, DialogueCandidateReference
from integrations.slack_agent_dialogue.company_dialogue_runtime_binding import (
    require_company_dialogue_principal_binding,
)
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
from integrations.slack_agent_dialogue.executive_observation_client import ResolvedDialogueObservation
from integrations.slack_agent_dialogue.fake_slack import InMemorySlackClient
from integrations.slack_agent_dialogue.principal_current_reader import (
    PrincipalCurrentSourceRead, PrincipalCurrentSourceUnavailable,
    read_current_principal_source,
)
from integrations.slack_agent_dialogue.contract_v2 import build_parent_v2, validate_parent_v2
from tests import test_principal_source_reader as relay
from tests import test_company_dialogue_runtime_binding as binding


def prepared(monkeypatch):
    # Use the canonical Runtime operation/session derivation, preserving the
    # Relay fixture's original source and synthetic attempted worker identity.
    parent = relay._parent()
    parent.pop("fingerprint")
    parent["operation_key"] = binding.identity().operation_key
    parent = build_parent_v2(parent)
    monkeypatch.setattr(relay, "_parent", lambda: json.loads(json.dumps(parent)))
    physical = relay._physical()
    current = binding.snapshot(attempt_id=physical.candidate.attempt_id,
                               parent_fingerprint=parent["fingerprint"])
    caller = binding.principal_caller()
    resolved = require_company_dialogue_principal_binding(
        delegation_identity=binding.identity(), dialogue_parent=parent,
        thread_ts=relay.THREAD, current=current, actor=caller,
        reply_to_message_key=physical.predecessor_message_key)
    context = DialogueContextV2(work_ref=resolved.work_ref,
        commission_ref=dict(resolved.commission_ref), session_ref=resolved.session_ref,
        operation_key=resolved.operation_key, watch_mode=resolved.watch_mode,
        actor_ref=dict(resolved.actor_ref), applies_to=dict(resolved.applies_to))
    observed = ResolvedDialogueObservation(state="RESOLVED", mode=ACTIVE_CURRENT_WORKER,
        dialogue_parent=parent, thread_ts=relay.THREAD,
        delegation_identity=binding.identity(),
        candidate=DialogueCandidateReference(**physical.candidate.to_dict()),
        target_bindings={}, current_worker=current, actor=None)
    return caller, context, physical, observed


def run(tmp_path, facts, *, observer_change=None, caller_change=None, context_change=None):
    caller, context, physical, observed = facts
    calls = []
    if caller_change is not None:
        caller = caller_change(caller)
    if context_change is not None:
        context = context_change(context)
    async def resolve(*, parent, thread_ts):
        # Frozen Relay mappings must cross the existing JSON contract intact.
        assert validate_parent_v2(json.loads(json.dumps(parent))) == parent
        calls.append((parent, thread_ts))
        return observer_change(observed) if observer_change else observed
    async def scenario():
        client = InMemorySlackClient(relay_bot_user_id=relay.BOT)
        relay._seed(client)
        path = tmp_path / "relay.sock"
        service = await relay._start_relay(path, client)
        try:
            try:
                result = await read_current_principal_source(caller=caller, context=context,
                    physical_source=physical, socket_path=path,
                    observation_client=SimpleNamespace(resolve=resolve))
            except PrincipalCurrentSourceUnavailable as error:
                result = error
        finally:
            await service.close()
        assert client.post_call_count == client.parent_post_call_count == 0
        return result
    return asyncio.run(scenario()), calls


def test_exact_source_joins_current_child_and_preserves_original_predecessor(tmp_path, monkeypatch):
    facts = prepared(monkeypatch)
    result, calls = run(tmp_path, facts)
    assert isinstance(result, PrincipalCurrentSourceRead)
    assert len(calls) == 1
    assert result.binding.reply_to_message_key == relay.PREDECESSOR["message_key"]
    assert result.binding.reply_to_message_key != relay.LATER["message_key"]
    assert result.binding.actor_ref["principal_binding_digest"] == facts[0].admission_context.principal_binding_digest
    assert result.binding.applies_to["attempt_id"] == facts[2].candidate.attempt_id
    assert result.source.parent["fingerprint"] == facts[2].parent_fingerprint


@pytest.mark.parametrize("change", [
    lambda o: dataclasses.replace(o, state="UNKNOWN"),
    lambda o: dataclasses.replace(o, mode="TERMINAL_RESULT"),
    lambda o: dataclasses.replace(o, current_worker=None),
    lambda o: dataclasses.replace(o, thread_ts=relay.FOREIGN_THREAD),
    lambda o: dataclasses.replace(o, dialogue_parent={**o.dialogue_parent, "work_ref": "WS:FOREIGN"}),
    lambda o: dataclasses.replace(o, candidate=dataclasses.replace(o.candidate, evidence_digest="c" * 64)),
    lambda o: dataclasses.replace(o, candidate=dataclasses.replace(o.candidate, attempt_id="ATT-" + "3" * 32)),
    lambda o: dataclasses.replace(o, candidate=relay._physical().candidate),
    lambda o: dataclasses.replace(o, current_worker=dataclasses.replace(o.current_worker, attempt_id="ATT-" + "3" * 32)),
    lambda o: dataclasses.replace(o, current_worker=dataclasses.replace(o.current_worker, worker_id="foreign-worker")),
    lambda o: dataclasses.replace(o, current_worker=dataclasses.replace(o.current_worker, root_job_id="JOB-999")),
    lambda o: dataclasses.replace(o, current_worker=dataclasses.replace(o.current_worker, company_dialogue_attested=False)),
    lambda o: {"state": "RESOLVED"},
])
def test_current_observation_drift_refuses_without_fallback(tmp_path, monkeypatch, change):
    result, calls = run(tmp_path, prepared(monkeypatch), observer_change=change)
    assert isinstance(result, PrincipalCurrentSourceUnavailable)
    assert str(result) == "PRINCIPAL_CURRENT_SOURCE_UNAVAILABLE"
    assert len(calls) == 1


@pytest.mark.parametrize("change", [
    lambda c: dataclasses.replace(c, root_job_id="JOB-999"),
    lambda c: dataclasses.replace(c, owed_seat="chairman"),
    lambda c: dataclasses.replace(c, admission_context=dataclasses.replace(c.admission_context,
        principal_binding_digest="8" * 64)),
    lambda c: dataclasses.replace(c, admission_context=dataclasses.replace(c.admission_context,
        authority_generation_digest="8" * 64)),
])
def test_caller_must_match_actual_read_context(tmp_path, monkeypatch, change):
    result, _ = run(tmp_path, prepared(monkeypatch), caller_change=change)
    assert isinstance(result, PrincipalCurrentSourceUnavailable)


def test_private_observation_failure_is_closed_without_second_read(tmp_path, monkeypatch):
    def failed(_observed):
        raise PermissionError("PRIVATE_CANARY /private/credentials")
    result, calls = run(tmp_path, prepared(monkeypatch), observer_change=failed)
    assert isinstance(result, PrincipalCurrentSourceUnavailable)
    assert str(result) == "PRINCIPAL_CURRENT_SOURCE_UNAVAILABLE"
    assert result.__cause__ is None
    assert len(calls) == 1


@pytest.mark.parametrize("change", [
    lambda c: dataclasses.replace(c, root_job_id="JOB-999"),
    lambda c: dataclasses.replace(c, owed_seat="chairman"),
    lambda c: dataclasses.replace(c, admission_context=dataclasses.replace(c.admission_context,
        principal_binding_digest="8" * 64)),
])
def test_foreign_principal_scope_refuses_before_any_source_io(tmp_path, monkeypatch, change):
    caller, context, physical, _ = prepared(monkeypatch)
    calls = []
    async def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("must not reach a source owner")
    with pytest.raises(PrincipalCurrentSourceUnavailable):
        asyncio.run(read_current_principal_source(caller=change(caller), context=context,
            physical_source=physical, socket_path=tmp_path / "unused.sock",
            observation_client=SimpleNamespace(resolve=forbidden), service_call=forbidden))
    assert calls == []
