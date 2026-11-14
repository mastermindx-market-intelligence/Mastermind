"""Original return tools cross the actual private bridge, never a second endpoint."""
import asyncio
import copy
import dataclasses
from pathlib import Path

import jsonschema
import pytest

from common.session_bridge_private_contract import MODIFYING_TOOLS
from integrations.mastermind_executive_app.gateway import CeoIngressResponse, TRANSPORT_SENT_OK, TRANSPORT_SENT_UNKNOWN
from integrations.session_bridge.installed import InstalledSessionBridgeClient, build_runtime_session_bridge
from integrations.session_bridge.return_tools import NativeReplyReadTool
from integrations.session_bridge.t3_native_client import Run
from integrations.session_bridge.t3_return_tools import (
    T3ReturnTools, RuntimeT3ReturnControl, LINK, STATUS, validate_return_arguments, validate_observer,
)
from integrations.session_bridge.schemas import BridgeError
from tests import test_session_bridge_installed as installed
from tests.test_t3_reply_host import t3_host, pending_question
from tests.test_t3_native_client import THREAD
from tests.test_session_bridge_reply_event_host_integration import authenticated_receiver


@pytest.fixture
def return_tools(t3_host):
    case = t3_host
    control = RuntimeT3ReturnControl(case.host)
    bridge = build_runtime_session_bridge(case.runtime,
        dialogue_socket_path=case.owner.socket_path, codex_owner_configured=lambda: False,
        t3_replies=case.source, t3_return_control=control)
    calls = []
    class Peer:
        async def send_frame(self, path, frame):
            calls.append((path, frame))
            bridge.validate_frame(frame)
            return CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=True,
                                     result=await bridge.handle_frame(frame))
    client = InstalledSessionBridgeClient('/private/tmp/source-only-return-fixture.sock', client=Peer())
    return case, T3ReturnTools(client), client, calls


def args():
    return {'run': dataclasses.asdict(Run(THREAD, 'run-1', 'original-request', 'launched'))}


def test_link_uses_existing_bridge_and_never_launches_or_subscribes(return_tools):
    case, tools, client, calls = return_tools
    before = len(case.runtime.store.list_events())
    result = asyncio.run(tools.handle(installed.PRINCIPAL, LINK, args()))
    assert result['ok'] is True, result
    assert result['data']['binding']['request_ref'] == case.binding['request_ref']
    assert result['data']['binding']['read_ref'] == case.binding['read_ref']
    assert result['data']['binding']['native_execution'] == 'NOT_CREATED'
    assert result['data']['binding']['subscription'] == 'NOT_CREATED'
    assert result['data']['monitor_selected'] is False
    assert len(case.runtime.store.list_events()) == before  # Original link is reconciled, not duplicated.
    assert len(calls) == 1 and calls[0][1]['tool'] == LINK
    assert calls[0][1]['principal']['subject_digest'] == case.auth.principal.subject_digest
    assert not case.sent
    assert all(name not in {'t3_thread_launch', 't3_thread_send', 't3_thread_interrupt'} for name, _ in case.native.calls)


def test_status_reads_original_binding_without_writes_or_observer_start(return_tools):
    case, tools, _, calls = return_tools
    before = [event.to_dict() for event in case.runtime.store.list_events()]
    result = asyncio.run(tools.handle(installed.PRINCIPAL, STATUS, {'request_ref': case.binding['request_ref']}))
    assert result['ok'] is True, result
    assert result['data']['observer'] == {'state': 'NOT_SELECTED'}
    assert result['data']['access_current'] is True
    assert [event.to_dict() for event in case.runtime.store.list_events()] == before
    assert len(calls) == 1


def test_t3_canonical_read_does_not_enter_agent_dialogue_original_schema(return_tools):
    case, tools, client, calls = return_tools
    question = pending_question(case)
    receipt = asyncio.run(case.source.observe_question(case.auth.principal, case.binding['request_ref'], 'pending-1'))
    result = asyncio.run(NativeReplyReadTool(client).handle(installed.PRINCIPAL, 'session_reply_read',
        {'read_ref': receipt['read_ref'], 'message_key': receipt['message_key']}))
    assert result['ok'] is True, result
    assert result['data']['questions'] == question['questions']
    assert result['data']['run_complete'] is False
    assert calls[-1][1]['tool'] == 'session_reply_read'


def test_link_lost_ack_retains_exact_recovery_refs_without_retry_or_relaunch(t3_host):
    case = t3_host
    client, fake = installed.client(CeoIngressResponse(transport=TRANSPORT_SENT_UNKNOWN))
    result = asyncio.run(T3ReturnTools(client).handle(installed.PRINCIPAL, LINK, args()))
    assert result['ok'] is False and result['error']['code'] == 'effect_unknown'
    assert result['original'] == {key: case.binding[key] for key in ('request_ref', 'read_ref')}
    assert result['retry_allowed'] is False
    assert len(fake.calls) == 1


def test_status_transport_loss_is_not_a_modifying_effect(t3_host):
    case = t3_host
    client, fake = installed.client(CeoIngressResponse(transport=TRANSPORT_SENT_UNKNOWN))
    result = asyncio.run(T3ReturnTools(client).handle(installed.PRINCIPAL, STATUS,
        {'request_ref': case.binding['request_ref']}))
    assert result['ok'] is False and result['error']['code'] != 'effect_unknown'
    assert len(fake.calls) == 1


def test_private_link_enforces_submit_scope_not_just_mcp_annotations(t3_host):
    case = t3_host
    read_policy = next(p for p in case.auth.policies.policies() if len(p.required_scopes) == 1)
    read_principal = dataclasses.replace(case.auth.principal, policy_id=read_policy.policy_id,
                                         scopes=tuple(read_policy.required_scopes))
    before = len(case.runtime.store.list_events())
    with pytest.raises(BridgeError) as caught:
        asyncio.run(RuntimeT3ReturnControl(case.host)(read_principal, LINK, args()))
    assert caught.value.code == 'scope_refused'
    assert len(case.runtime.store.list_events()) == before


@pytest.mark.parametrize('change', [
    {'ttl_seconds': True}, {'ttl_seconds': 0}, {'ttl_seconds': 86401}, {'token': 'untrusted'},
    {'callback_url': 'https://other.invalid'}, {'principal': 'someone'}, {'run': {}},
])
def test_link_closed_input_rejects_authority_callback_and_provider_injection(change):
    with pytest.raises((ValueError, TypeError, KeyError)):
        validate_return_arguments(LINK, {**args(), **change})


def test_tool_schema_contract_and_submit_scope_are_explicit(return_tools):
    _, tools, _, _ = return_tools
    specs = {spec.name: spec for spec in tools.specs()}
    assert specs[LINK].read_only is False and specs[STATUS].read_only is True
    assert LINK in MODIFYING_TOOLS and STATUS not in MODIFYING_TOOLS
    jsonschema.validate(args(), specs[LINK].input_schema)
    jsonschema.validate({'request_ref': 't3-request-' + 'a' * 64}, specs[STATUS].input_schema)
    for bad in ({**args(), 'callback_url': 'https://other.invalid'}, {**args(), 'ttl_seconds': True}):
        with pytest.raises(jsonschema.ValidationError): jsonschema.validate(bad, specs[LINK].input_schema)


def test_extension_preserves_incumbent_handler_and_marks_only_link_modifying(return_tools):
    import mcp.types as mt
    _, tools, _, _ = return_tools
    calls = []
    old = mt.Tool(name='incumbent', description='fixture', inputSchema={'type': 'object'})
    def valid(name, arguments): calls.append(('validate', name)); return arguments
    async def handle(principal, name, arguments): calls.append(('handle', name)); return {'old': True}
    def error(name, code, message): calls.append(('error', name)); return {'old_error': True}
    original = {'profile_tools': (old,), 'profile_validator': valid, 'direct_tool_names': ('incumbent',),
                'direct_submit_names': ('incumbent',), 'direct_handler': handle, 'direct_error_factory': error}
    extended = tools.extend_host_configuration(original)
    assert extended['profile_tools'][0] is old
    assert extended['direct_submit_names'] == ('incumbent', LINK)
    assert extended['direct_tool_names'] == ('incumbent', LINK, STATUS)
    assert extended['profile_tools'][1].annotations.idempotentHint is False
    assert extended['profile_tools'][2].annotations.readOnlyHint is True
    assert extended['profile_validator']('incumbent', {}) == {}
    assert asyncio.run(extended['direct_handler'](installed.PRINCIPAL, 'incumbent', {})) == {'old': True}
    assert extended['direct_error_factory']('incumbent', 'x', 'private') == {'old_error': True}
    assert len(calls) == 3
    with pytest.raises(ValueError): tools.extend_host_configuration(extended)


@pytest.mark.parametrize('bad', [
    {'state': 'READY', 'secret': 'private'}, {'state': 'SUCCEEDED'},
    {'state': 'NOT_SELECTED', 'message': 'raw host output'}, [], None,
])
def test_status_projection_does_not_expose_arbitrary_backend_fields(bad):
    with pytest.raises(ValueError): validate_observer(bad)


def test_foreign_account_cannot_link_or_inspect_original_return(return_tools):
    case, tools, _, _ = return_tools
    foreign = dataclasses.replace(installed.PRINCIPAL, subject_digest='c' * 64)
    before = len(case.runtime.store.list_events())
    for name, arguments in ((LINK, args()), (STATUS, {'request_ref': case.binding['request_ref']})):
        value = asyncio.run(tools.handle(foreign, name, arguments))
        assert value['ok'] is False
        assert value['data'] is None
    assert len(case.runtime.store.list_events()) == before
