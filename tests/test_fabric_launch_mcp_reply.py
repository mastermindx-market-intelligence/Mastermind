"""A host probe must not convert foreign/malformed MCP replies into readiness."""
import json
from types import SimpleNamespace
import pytest
from ops.fabric_launch.observe import ReadOnlyMcpProbe


class Response:
    def __init__(self, body):
        self.body=body
        self.headers={}
    def read(self, bound):
        return self.body[:bound]
    def __enter__(self):
        return self
    def __exit__(self,*args):
        return False


def probe(body):
    client=ReadOnlyMcpProbe('openai-docs')
    client.opener=SimpleNamespace(open=lambda *args,**kwargs:Response(body))
    return client


@pytest.mark.parametrize('identifier',[None,True,'1',2,[],{}])
def test_foreign_or_malformed_id_never_becomes_readiness(identifier):
    body=json.dumps({'jsonrpc':'2.0','id':identifier,'result':{'tools':[]}}).encode()
    with pytest.raises(ValueError):
        probe(body).call('tools/list',{},1)


@pytest.mark.parametrize('version',[None,'1.0',2])
def test_protocol_version_is_required(version):
    body=json.dumps({'jsonrpc':version,'id':1,'result':{'tools':[]}}).encode()
    with pytest.raises(ValueError):
        probe(body).call('tools/list',{},1)


@pytest.mark.parametrize('result',[None,True,[],42,'not-a-tool-result'])
def test_object_result_required(result):
    body=json.dumps({'jsonrpc':'2.0','id':1,'result':result}).encode()
    with pytest.raises(ValueError):
        probe(body).call('tools/list',{},1)


@pytest.mark.parametrize('body',[
    b'{"jsonrpc":"2.0","id":1,"id":2,"result":{}}',
    b'{"jsonrpc":"2.0","id":1,"result":{"x":NaN}}',
    b'{"jsonrpc":"2.0","id":1,"result":{},"error":null}',
])
def test_ambiguous_or_nonfinite_envelopes_refuse(body):
    with pytest.raises(ValueError):
        probe(body).call('tools/list',{},1)


def test_exact_matching_json_and_sse_result_work():
    body=b'{"jsonrpc":"2.0","id":1,"result":{"tools":[]}}'
    assert probe(body).call('tools/list',{},1)=={'tools':[]}
    sse=b'event: message\ndata: '+body+b'\n\n'
    assert probe(sse).call('tools/list',{},1)=={'tools':[]}
