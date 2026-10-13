"""Pre-reply authorization through the existing Runtime owner, no callback effects.

Runtime, request/lease/harness/Wake records and Dialogue validation are real.
The carrier's authenticated read response and verified token issuance are fixtures.
"""
import asyncio
import copy
import dataclasses
import time
from types import SimpleNamespace

import pytest

from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.session_bridge import runtime_return as module
from integrations.session_bridge.schemas import BridgeError
from integrations.session_bridge.web_reply_subscription_owner import OriginalReplyGrant, owner_key
from integrations.slack_agent_dialogue.contract_v2 import build_message_v2, build_parent_v2
from integrations.slack_agent_dialogue.service import RELAY_PARENT_ATTESTATION
from tests.test_native_continuation_ack_ingress import native_case
from tests.test_session_bridge_installed import principal_frame


@pytest.fixture
def grant_source(native_case):
    s = native_case
    p = principal_frame()
    p.update(issued_at=int(time.time())-60, expires_at=int(time.time())+3600)
    p['scopes'] = tuple(p['scopes'])
    s.principal = principal_projection(VerifiedPrincipal(**p))
    s.event = s.f.runtime.events.get_event_by_command_id(
        module._PREFIX + module._request_key(s.args['operation_key']))
    s.request_ref = s.event.command_id
    s.calls, s.on_read = [], None
    s.parent = copy.deepcopy(s.f.parent)
    s.messages = [copy.deepcopy(s.prior), copy.deepcopy(s.request)]

    async def carrier(path, frame):
        s.calls.append(copy.deepcopy(frame))
        assert frame['operation'] in {'read_bound_parent', 'read_thread'}
        if s.on_read:
            s.on_read(frame['operation'])
        if frame['operation'] == 'read_bound_parent':
            return {'ok': True, 'result': {'attestation': RELAY_PARENT_ATTESTATION,
                'thread_ts': frame['args']['thread_ts'], 'parent': copy.deepcopy(s.parent)}}
        return {'ok': True, 'result': {'thread_ts': frame['args']['thread_ts'],
            'historical_messages': [], 'mutated_count': 0,
            'messages': [{'message': copy.deepcopy(m)} for m in s.messages]}}
    s.owner.service_call = carrier
    return s


def grant(s, principal=None, request_ref=None):
    return asyncio.run(s.owner.resolve_original_reply_grant(
        principal=s.principal if principal is None else principal,
        request_ref=s.request_ref if request_ref is None else request_ref))


def events(s):
    return [e.to_dict() for e in s.f.runtime.events.list_events()]


def test_actual_owner_grants_before_reply_and_has_zero_effects(grant_source):
    s = grant_source
    before = events(s)
    assert not any(e['event_type'] == module._NATIVE_COMMIT_EVENT for e in before)
    actual = grant(s)
    assert type(actual) is OriginalReplyGrant
    assert actual.owner_key == owner_key(s.principal)
    assert actual.request_ref == s.event.command_id
    assert actual.read_ref == s.ref and actual.access_current is True
    assert len(actual.revision) == 64
    assert actual.expires_at == s.principal.expires_at
    assert events(s) == before
    assert [c['operation'] for c in s.calls] == ['read_bound_parent', 'read_thread', 'read_bound_parent']
    with pytest.raises(BridgeError):
        asyncio.run(s.owner.resolve_read(principal=s.principal, read_ref=s.ref))


def test_concrete_adapter_resolver_uses_same_owner(grant_source):
    s = grant_source
    resolver = module.RuntimeOriginalRequestResolver(s.owner)
    assert asyncio.run(resolver.resolve(s.principal, s.request_ref)) == grant(s)
    with pytest.raises(TypeError):
        module.RuntimeOriginalRequestResolver(SimpleNamespace(resolve_original_reply_grant=lambda **kw: True))


@pytest.mark.parametrize('field,value', [('policy_id', 'foreign'), ('issuer_digest', '4'*64),
    ('resource', 'https://foreign.test/mcp'), ('subject_digest', '5'*64), ('client_ref', '6'*64)])
def test_foreign_account_issuer_client_refused_before_read(grant_source, field, value):
    s = grant_source
    with pytest.raises(BridgeError):
        grant(s, principal=dataclasses.replace(s.principal, **{field: value}))
    assert not s.calls


@pytest.mark.parametrize('change', [{'scopes': ()}, {'expires_at': 1},
    {'issued_at': 9999999999}, {'expires_at': True}])
def test_current_read_authorization_is_required(grant_source, change):
    s = grant_source
    with pytest.raises(BridgeError):
        grant(s, principal=dataclasses.replace(s.principal, **change))
    assert not s.calls


def test_send_only_revocation_does_not_revoke_original_read(grant_source):
    s = grant_source
    read_only = dataclasses.replace(s.principal, scopes=(module.READ_SCOPE,))
    assert grant(s, principal=read_only).read_ref == s.ref


@pytest.mark.parametrize('request_ref', [None, True, '', 'session-reply-'+'0'*64,
    'session-bridge-continue:'+'0'*64, 'x'*1000])
def test_reference_text_never_confers_authority(grant_source, request_ref):
    s = grant_source
    # None is an explicit invalid argument, not the helper's omitted default.
    with pytest.raises(BridgeError):
        asyncio.run(s.owner.resolve_original_reply_grant(principal=s.principal, request_ref=request_ref))
    assert not s.calls


@pytest.mark.parametrize('timing', ['before', 'during'])
@pytest.mark.parametrize('fault', ['writer', 'epoch', 'event'])
def test_owner_or_immutable_request_drift_refused(grant_source, monkeypatch, timing, fault):
    s = grant_source
    lookup = s.f.runtime.events.get_event_by_command_id
    def mutate():
        if fault == 'writer':
            facts = s.f.runtime.current_harness_binding_source(s.f.sealed.attempt_id)
            monkeypatch.setattr(type(s.f.runtime), 'current_harness_binding_source',
                lambda *a, **kw: dataclasses.replace(facts, process_generation_id='retired-process'))
        elif fault == 'epoch':
            epoch = module._read_current_target(s.f.runtime, s.event.payload['context']['operation_key'])
            monkeypatch.setattr(module, '_read_current_target',
                lambda *a: dataclasses.replace(epoch, harness_generation_number=epoch.harness_generation_number+1))
        else:
            monkeypatch.setattr(s.f.runtime.events, 'get_event_by_command_id',
                lambda command: dataclasses.replace(s.event, actor='foreign')
                    if command == s.request_ref else lookup(command))
    if timing == 'before':
        mutate()
    else:
        state = [False]
        def during(operation):
            if not state[0]:
                state[0] = True
                mutate()
        s.on_read = during
    before = events(s)
    with pytest.raises(BridgeError):
        grant(s)
    assert events(s) == before
    if timing == 'before':
        assert not s.calls


@pytest.mark.parametrize('fault', ['parent', 'continue', 'expiry'])
def test_bound_source_or_token_drift_during_await_refused(grant_source, monkeypatch, fault):
    s = grant_source
    def mutate(operation):
        if operation != 'read_thread':
            return
        if fault == 'parent':
            raw = {k:v for k,v in s.parent.items() if k != 'fingerprint'}
            raw['created_at'] = '2026-09-03T00:59:00Z'
            s.parent = build_parent_v2(raw)
        elif fault == 'continue':
            raw = copy.deepcopy(s.request)
            raw.pop('fingerprint')
            raw['body']['instruction'] = 'A plausible but foreign instruction.'
            s.messages[-1] = build_message_v2(raw)
        else:
            monkeypatch.setattr(module, 'time', SimpleNamespace(time=lambda: s.principal.expires_at))
    s.on_read = mutate
    before = events(s)
    with pytest.raises(BridgeError):
        grant(s)
    assert events(s) == before


def test_refresh_token_does_not_rebind_revision(grant_source):
    s = grant_source
    first = grant(s)
    refreshed = dataclasses.replace(s.principal, expires_at=s.principal.expires_at+60)
    second = grant(s, principal=refreshed)
    assert first.revision == second.revision
    assert second.expires_at == refreshed.expires_at


def test_original_requested_event_without_canonical_continue_is_insufficient(grant_source):
    s = grant_source
    s.messages = [s.prior]
    with pytest.raises(BridgeError):
        grant(s)


@pytest.mark.parametrize('fault', [None, 'read', 'reference'])
def test_existing_subscription_adapter_consumes_concrete_pre_reply_owner(grant_source, fault):
    # Storage and challenge ports remain explicit fakes. Authorization is the
    # concrete Runtime owner rather than the older synthetic Access fixture.
    from integrations.session_bridge.web_reply_subscription_owner import (
        OriginalReplySubscriptionAdapter, SubscriptionUnavailable,
    )
    from tests.test_session_bridge_web_reply_subscription_owner import (
        ExistingStore, Callback, subscribe,
    )
    s = grant_source
    store, sender = ExistingStore(), Callback()
    adapter = OriginalReplySubscriptionAdapter(
        resolver=module.RuntimeOriginalRequestResolver(s.owner), storage=store,
        challenge_sender=sender, clock=lambda: int(time.time()), enabled=True)
    request = dataclasses.replace(subscribe(), request_ref=s.request_ref)
    principal = s.principal
    if fault == 'read':
        principal = dataclasses.replace(principal, scopes=())
    elif fault == 'reference':
        request = dataclasses.replace(request, request_ref=module._PREFIX+'0'*64)
    before = events(s)
    if fault:
        with pytest.raises(SubscriptionUnavailable):
            asyncio.run(adapter.subscribe(principal, request))
        assert not store.calls and not sender.calls
    else:
        result = asyncio.run(adapter.subscribe(principal, request))
        assert result.callback_verified and result.persisted and result.original_request_current
        record = store.rows[result.subscription_id]
        assert record.request_ref == s.request_ref and record.read_ref == s.ref
        assert record.owner_key == owner_key(s.principal)
        assert len(sender.calls) == 1
        assert not any(e['event_type'] == module._NATIVE_COMMIT_EVENT for e in events(s))
    assert events(s) == before
