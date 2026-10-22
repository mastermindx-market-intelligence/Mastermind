"""Unanswered source semantics with real Relay reads and no Wake binding."""
import dataclasses

import pytest

from integrations.slack_agent_dialogue.contract_v2 import build_message_v2
from integrations.slack_agent_dialogue.engine import ReadMessage
from integrations.slack_agent_dialogue.principal_current_reader import PrincipalCurrentSourceRead, _wire
from integrations.slack_agent_dialogue.principal_pending_decision import (
    PrincipalDecisionSourceUnavailable, require_unanswered_principal_decision,
)
from tests import test_principal_current_reader as current
from tests import test_principal_source_reader as relay
from tests.test_slack_agent_dialogue_turn_watcher import _body


def message(base, kind, **changes):
    value = _wire(base)
    value.pop('fingerprint', None)
    value.update(message_type=kind, body=_body(kind),
                 requires_response=kind in {'DECISION_REQUEST', 'BLOCKED'}, **changes)
    return build_message_v2(value)


def acquired(tmp_path, monkeypatch):
    request = message(relay.PREDECESSOR, 'DECISION_REQUEST')
    progress = message(relay.LATER, 'PROGRESS',
                       reply_to_message_key=request['message_key'])
    monkeypatch.setattr(relay, 'PREDECESSOR', request)
    monkeypatch.setattr(relay, 'LATER', progress)
    read, calls = current.run(tmp_path, current.prepared(monkeypatch))
    assert type(read) is PrincipalCurrentSourceRead
    assert len(calls) == 1
    return read


def with_messages(read, messages, **thread_changes):
    items = tuple(ReadMessage(value, relay.PREDECESSOR_TS, ()) for value in messages)
    return dataclasses.replace(read, source=dataclasses.replace(read.source,
        thread=dataclasses.replace(read.source.thread, messages=items, **thread_changes)))


def test_real_unwatched_source_keeps_exact_request_across_quiet_update(tmp_path, monkeypatch):
    read = acquired(tmp_path, monkeypatch)
    assert read.source.parent['watch_mode'] is None
    assert read.observation.target_bindings == {}
    assert require_unanswered_principal_decision(read) is read.source.predecessor


@pytest.mark.parametrize('kind', ['RULING', 'STOP', 'CONTINUE'])
def test_any_disposition_prevents_reusing_original_request(tmp_path, monkeypatch, kind):
    read = acquired(tmp_path, monkeypatch)
    original = read.source.predecessor.message
    reply = message(relay.LATER, kind, actor_ref=dict(read.binding.actor_ref),
                    reply_to_message_key=original['message_key'])
    with pytest.raises(PrincipalDecisionSourceUnavailable):
        require_unanswered_principal_decision(with_messages(read, [original, reply]))


@pytest.mark.parametrize('fault', ['second_request', 'foreign_quiet', 'fork', 'mutation',
                                  'wrong_original', 'non_request'])
def test_ambiguous_or_changed_source_cannot_be_called_unanswered(tmp_path, monkeypatch, fault):
    read = acquired(tmp_path, monkeypatch)
    original = read.source.predecessor.message
    quiet = read.source.thread.messages[-1].message
    if fault == 'second_request':
        candidate = with_messages(read, [original, message(quiet, 'DECISION_REQUEST')])
    elif fault == 'foreign_quiet':
        candidate = with_messages(read, [original, message(quiet, 'PROGRESS',
            actor_ref={**quiet['actor_ref'], 'worker_id': 'another-worker'},
            applies_to={**quiet['applies_to'], 'worker_id': 'another-worker'})])
    elif fault == 'fork':
        other = message(quiet, 'PROGRESS', message_key='asd-other-progress')
        candidate = with_messages(read, [original, quiet, other])
    elif fault == 'mutation':
        candidate = with_messages(read, [original, quiet], mutated_count=1)
    elif fault == 'wrong_original':
        candidate = dataclasses.replace(read, binding=dataclasses.replace(read.binding,
            reply_to_message_key='asd-other-request'))
    else:
        replacement = message(original, 'PROGRESS')
        candidate = with_messages(read, [replacement])
        candidate = dataclasses.replace(candidate, source=dataclasses.replace(candidate.source,
            predecessor=ReadMessage(replacement, relay.PREDECESSOR_TS, ())))
    with pytest.raises(PrincipalDecisionSourceUnavailable) as error:
        require_unanswered_principal_decision(candidate)
    assert str(error.value) == 'PRINCIPAL_DECISION_SOURCE_UNAVAILABLE'
    assert error.value.__cause__ is None
