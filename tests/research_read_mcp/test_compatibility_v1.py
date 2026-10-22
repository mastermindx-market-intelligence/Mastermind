"""Offline synthetic SDK tests; real item/search resolvers remain uninstalled."""
import asyncio
import copy
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sys

import httpx
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
import pytest

from integrations.research_read_mcp import app as app_module
from integrations.research_read_mcp.contracts import ContractViolation, TOOL_NAMES
from integrations.research_read_mcp.port_adapter import CanonicalReadContext

try:
    from integrations.research_read_mcp import compatibility_v1 as compat
    from integrations.research_read_mcp import bounded_item_v1 as item
except ImportError:
    compat = item = None

# Existing offline authentication harness; artifact harness pins its exact source.
from tests.research_read_mcp import test_app as legacy
ITEM = 'rvitem.v1.' + 'a' * 64
URL = 'https://mcp.mastermind-x.com/os/research/evidence/' + ITEM
DTO = {'id': ITEM, 'title': 'Synthetic note', 'text': 'SYNTHETIC_LITERAL_ITEM',
       'url': URL, 'metadata': {'coverage': 'COMPLETE_BOUNDED_ITEM'}}


def modules():
    assert compat is not None and item is not None, 'versioned compatibility implementation missing'
    return compat, item


def execute(awaitable):
    return asyncio.run(awaitable)


class Harness(legacy.Harness):
    def __init__(self, *, enabled=True, limit=8):
        super().__init__()
        self.item_calls = []
        self.search_state = 'QUALIFIED'
        self.items = [{k: DTO[k] for k in ('id', 'title', 'url')}]
        self.dto = copy.deepcopy(DTO)
        self.final_mode = None
        self.context_mode = None
        port = None
        if enabled:
            c, _ = modules()
            port = c.CompatibilityPortV1(search_items=self.search_items,
                                         resolve_item=self.resolve_item,
                                         context_type=CanonicalReadContext, result_limit=limit)
        self.app = app_module.create_authenticated_research_server(
            authenticator=self.auth, policy=self.policy, now=lambda: self.clock,
            audit_sink=self.audit, port=self._port, entitlement_resolver=self._resolver,
            context_builder=self._compat_context,
            allowed_hosts=('127.0.0.1', '127.0.0.1:*'), compatibility_port=port)

    def _compat_context(self, entitlement):
        if self.context_mode == 'slow-token':self.clock += 1000
        if self.context_mode == 'slow-grant':self.clock += 200
        scopes = {'status', 'search'}
        if 'evidence_passage' in entitlement.content_classes:
            scopes.add('find_evidence')
        return CanonicalReadContext(principal_id=('b' * 64 if self.context_mode == 'wrong' else entitlement.subject_digest),
                                    entitlement='pro' if 'find_evidence' in scopes else 'preview',
                                    scopes=frozenset(scopes), surface='mcp')

    def _resolver(self, projection):
        result = super()._resolver(projection)
        if getattr(self, 'final_mode', None) == 'token-expire' and self.resolver_calls >= 2:
            self.clock += 1000
        if getattr(self, 'final_mode', None) == 'grant-expire' and self.resolver_calls >= 2:
            self.clock += 200
        return result

    async def search_items(self, *, caller_context, query, limit):
        self.item_calls.append(('search', caller_context, query, limit))
        return {'state': self.search_state, 'results': copy.deepcopy(self.items)}

    async def resolve_item(self, *, caller_context, item_id):
        self.item_calls.append(('fetch', caller_context, item_id))
        return copy.deepcopy(self.dto)


async def call_once(h, name, arguments, *, token=True, **claims):
    await h.start()
    try:
        before = len(h.audit.events)
        raw = await h.call(name, arguments, token=h.token(**claims) if token else None)
        return raw, len(h.audit.events) - before
    finally:
        await h.stop()


def data(raw):
    result = legacy._result(raw)
    assert len(result['content']) == 1
    assert result['content'][0]['type'] == 'text'
    assert json.loads(result['content'][0]['text']) == result['structuredContent']
    return result


def test_default_four_tools_and_sdk_compatibility_census():
    modules()
    async def check(enabled):
        h = Harness(enabled=enabled)
        await h.start()
        try:
            def factory(headers=None, timeout=None, auth=None):
                return httpx.AsyncClient(transport=httpx.ASGITransport(app=h.app), headers=headers,
                                         timeout=timeout, auth=auth)
            async with factory(headers={'Authorization': 'Bearer '+h.token()}, timeout=10) as client:
                async with streamable_http_client('http://127.0.0.1'+legacy.RESOURCE_PATH,
                        http_client=client) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools = (await session.list_tools()).tools
                        assert [x.name for x in tools] == list(TOOL_NAMES) + (['search', 'fetch'] if enabled else [])
                        if enabled:
                            for t in tools[-2:]:
                                assert t.inputSchema['additionalProperties'] is False
                                assert t.outputSchema['additionalProperties'] is False
                                assert t.annotations.readOnlyHint is True
                                assert t.annotations.destructiveHint is False
                            result = await session.call_tool('fetch', {'id': ITEM})
                            assert result.structuredContent == DTO
                            assert json.loads(result.content[0].text) == DTO
            assert h.port_calls == 0
        finally:
            await h.stop()
    execute(check(False))
    execute(check(True))


@pytest.mark.parametrize('name,args,want', [('search', {'query': 'Public synthetic query'}, {'results': [{k: DTO[k] for k in ('id', 'title', 'url')}]}), ('fetch', {'id': ITEM}, DTO)])
def test_same_handler_returns_matching_structured_json_with_one_audit(name,args,want):
    modules()
    h = Harness()
    raw, audit_count = execute(call_once(h,name,args))
    result = data(raw)
    assert result['isError'] is False
    assert result['structuredContent'] == want
    assert len(raw.content) <= 128*1024
    assert audit_count == 1
    assert h.port_calls == 0
    assert type(h.item_calls[0][1]) is CanonicalReadContext
    if name == 'search':
        assert h.item_calls[0][-1] == 8


@pytest.mark.parametrize('state', ['STALE','UNAVAILABLE'])
def test_unqualified_empty_search_is_closed_refusal(state):
    modules(); h=Harness(); h.search_state=state; h.items=[]
    raw,_=execute(call_once(h,'search',{'query':'Public query'}))
    assert data(raw)['structuredContent']['code'] == 'SOURCE_UNAVAILABLE'


def test_qualified_empty_search_is_valid():
    modules(); h=Harness(); h.items=[]
    raw,_=execute(call_once(h,'search',{'query':'Public query'}))
    assert data(raw)['structuredContent'] == {'results':[]}


@pytest.mark.parametrize('name,args', [('search', {'query':'q','limit':20}), ('search', {'query':' '}),
                                      ('fetch', {'id':URL}), ('fetch', {'id':ITEM,'url':URL}),
                                      ('fetch', {'id':ITEM+'\n'})])
def test_closed_invalid_arguments_refuse_before_service(name,args):
    modules(); h=Harness(); raw,_=execute(call_once(h,name,args))
    assert data(raw)['structuredContent']['code'] == 'INVALID_REQUEST'
    assert h.item_calls == []


@pytest.mark.parametrize('mode', ['catalog-only','zero-quote','expired-grant','wrong-context'])
def test_content_quote_expiry_context_gates_refuse_before_service(mode):
    modules();h=Harness()
    if mode == 'catalog-only':h.resolver_mode='catalog-only'
    if mode == 'zero-quote':h.full=replace(h.full,quote_limit_chars=0)
    if mode == 'expired-grant':h.full=replace(h.full,expires_at=h.clock)
    if mode == 'wrong-context':h.context_mode='wrong'
    raw,_=execute(call_once(h,'fetch',{'id':ITEM}))
    assert data(raw)['structuredContent']['code'] == 'NOT_ENTITLED'
    assert h.item_calls == []


def test_missing_auth_never_reaches_item_service():
    modules();h=Harness();raw,_=execute(call_once(h,'fetch',{'id':ITEM},token=False))
    assert raw.status_code == 401
    assert h.item_calls == []


@pytest.mark.parametrize('mode,claims,code', [('token-expire',{},'AUTHENTICATION_REQUIRED'),
                                           ('grant-expire',{},'NOT_ENTITLED')])
def test_final_sync_grant_owner_time_advance_refuses_body(mode,claims,code):
    modules();h=Harness();h.final_mode=mode
    if mode == 'grant-expire':h.full=replace(h.full,expires_at=h.clock+100)
    raw,audits=execute(call_once(h,'fetch',{'id':ITEM},**claims))
    assert data(raw)['structuredContent']['code'] == code
    assert 'SYNTHETIC_LITERAL_ITEM' not in raw.text
    assert audits == 1


def test_final_decision_after_serialization_refuses_expired_token(monkeypatch):
    modules();h=Harness()
    original=app_module.compatibility_result
    def advance(*args,**kwargs):
        result=original(*args,**kwargs);h.clock+=1000;return result
    monkeypatch.setattr(app_module,'compatibility_result',advance)
    raw,audits=execute(call_once(h,'fetch',{'id':ITEM}))
    assert data(raw)['structuredContent']['code']=='AUTHENTICATION_REQUIRED'
    assert 'SYNTHETIC_LITERAL_ITEM' not in raw.text
    assert audits == 1


@pytest.mark.parametrize('change', [lambda d:d.update(url='https://example.invalid/item'),
                                   lambda d:d.update(text='é'*501),
                                   lambda d:d.update(text='x'*1001),
                                   lambda d:d.update(metadata={'coverage':'FULL_REPORT'}),
                                   lambda d:d.update(extra='PRIVATE_EXTRA')])
def test_complete_item_dto_is_closed_utf8_bounded_and_never_trimmed(change):
    modules();h=Harness();change(h.dto)
    raw,_=execute(call_once(h,'fetch',{'id':ITEM}))
    assert data(raw)['isError'] is True
    assert 'PRIVATE_EXTRA' not in raw.text


def test_whole_item_exceeding_current_quote_is_refused():
    modules();h=Harness();h.full=replace(h.full,quote_limit_chars=3)
    raw,_=execute(call_once(h,'fetch',{'id':ITEM}))
    assert data(raw)['isError'] is True
    assert DTO['text'] not in raw.text


def test_complete_wire_envelope_counts_both_json_copies():
    modules();h=Harness(limit=20);h.items=[]
    for n in range(20):
        identifier='rvitem.v1.'+format(n,'064x')
        h.items.append({'id':identifier,'title':'\x01'*1000,
                        'url':'https://mcp.mastermind-x.com/os/research/evidence/'+identifier})
    raw,_=execute(call_once(h,'search',{'query':'Public query'}))
    assert data(raw)['structuredContent']['code']=='INTERNAL_ERROR'
    assert len(raw.content)<=128*1024


@pytest.mark.parametrize('limit', [0,21,True])
def test_server_owned_result_limit_is_closed(limit):
    modules()
    with pytest.raises(ValueError):Harness(limit=limit)


def test_query_item_bodies_and_errors_are_not_logged(caplog):
    modules();h=Harness();h.dto['text']='PRIVATE_SYNTHETIC_BODY'
    raw,_=execute(call_once(h,'search',{'query':'PRIVATE_SYNTHETIC_QUERY'}))
    assert not any('PRIVATE_SYNTHETIC' in r.getMessage() for r in caplog.records)


def test_non_scalar_unicode_query_is_closed_at_the_argument_validator():
    modules()
    with pytest.raises(ContractViolation) as caught:
        compat.validate_arguments('search', {'query':'\ud800'})
    assert caught.value.code == 'INVALID_REQUEST'


@pytest.mark.parametrize('mode,code', [('slow-token','AUTHENTICATION_REQUIRED'), ('slow-grant','NOT_ENTITLED')])
def test_context_owner_time_advance_is_rechecked_before_any_body_read(mode,code):
    modules();h=Harness();h.context_mode=mode
    if mode == 'slow-grant':h.full=replace(h.full,expires_at=h.clock+100)
    raw,audits=execute(call_once(h,'fetch',{'id':ITEM}))
    assert data(raw)['structuredContent']['code']==code
    assert h.item_calls==[]
    assert audits==1


def test_fetch_rejects_another_valid_item_and_releases_no_body():
    modules();h=Harness()
    other='rvitem.v1.'+'b'*64
    h.dto.update(id=other,url='https://mcp.mastermind-x.com/os/research/evidence/'+other,
                 text='SYNTHETIC_OTHER_ITEM_BODY')
    raw,_=execute(call_once(h,'fetch',{'id':ITEM}))
    assert data(raw)['isError'] is True
    assert data(raw)['structuredContent']['code']=='INTERNAL_ERROR'
    assert 'SYNTHETIC_OTHER_ITEM_BODY' not in raw.text
    assert other not in raw.text
    assert h.item_calls[0][2]==ITEM
