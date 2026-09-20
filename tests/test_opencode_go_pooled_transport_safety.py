"""Safety regressions; credentials, model outputs and senders are synthetic."""
import json
import traceback
import pytest
import control_plane.opencode_go_pooled_transport as wire
GEN = "a" * 64


def request(body=None, headers=None, path='chat/completions'):
    return wire.ProviderRequest(path,'session-Case-1',headers or {'Content-Type':'application/json'},
        body if body is not None else b'{"model":"deepseek-v4.1-flash","messages":[{"role":"user","content":"remember alpha"}]}')


def quota():
    return wire.UpstreamResponse(429,{'retry-after':'120'},json.dumps({
        'type':'error','error':{'type':'GoUsageLimitError','message':'quota'},
        'metadata':{'workspace':'synthetic-workspace','limitName':'5 hour'}}).encode())


def transport(resolver=None, sender=None, loader=None, max_rollovers=2):
    return wire.OpenCodeGoPooledTransport(pool_id='opencode-go',
        resolver=resolver or (lambda _:wire.AccountChoice('opencode-go',GEN,'acct-a')),
        credential_loader=loader or (lambda _: 'synthetic-key'),
        sender=sender or (lambda _:wire.UpstreamResponse(200,{},b'{"ok":true}')),
        max_rollovers=max_rollovers)


def test_auth_error_never_rotates_including_provider_suspension():
    sent=[]
    def resolver(value):
        return wire.AccountChoice('opencode-go',GEN,'acct-b' if value.excluded_account_ids else 'acct-a')
    failure=wire.UpstreamResponse(401,{},b'{"type":"error","error":{"type":"AuthError","message":"account blocked"}}')
    result=transport(resolver=resolver,sender=lambda r: sent.append(r.account_id) or failure).execute(request())
    assert sent==['acct-a']
    assert result.response.status==401


def test_alternate_auth_cookie_and_hop_headers_are_not_forwarded():
    headers={'x-api-key':'caller-key','Cookie':'session=private','Proxy-Authorization':'private',
        'Connection':'x-private','X-Private':'private','Transfer-Encoding':'chunked',
        'x-zen-billing-source':'credit','Content-Type':'application/json'}
    prepared=wire.prepare_upstream_request(request(headers=headers),
        choice=wire.AccountChoice('opencode-go',GEN,'acct-a'),credential='synthetic-key')
    lowered={k.lower() for k in prepared.headers}
    assert not lowered.intersection(k.lower() for k in headers if k!='Content-Type')


def test_callback_cannot_change_logical_body_between_members():
    body=bytearray(request().body)
    original=bytes(body)
    sent=[]
    def resolve(value):
        return wire.AccountChoice('opencode-go',GEN,'acct-b' if value.excluded_account_ids else 'acct-a')
    def sender(value):
        sent.append(value.body)
        body[:]=b'{"model":"different","messages":[]}'
        return quota() if len(sent)==1 else wire.UpstreamResponse(200,{},b'{}')
    transport(resolver=resolve,sender=sender).execute(request(body=body))
    assert sent==[original,original]


def test_opaque_responses_state_refuses_before_any_callback():
    touched=[]
    client=transport(resolver=lambda _:touched.append('resolve'))
    with pytest.raises(wire.OpenCodeGoTransportContractError):
        client.execute(request(path='responses',body=b'{"model":"grok-4.6","previous_response_id":"private-response","input":"continue"}'))
    assert touched==[]


def test_invalid_request_refuses_before_credentials():
    touched=[]
    client=transport(loader=lambda _:touched.append('key') or 'synthetic-key')
    with pytest.raises(wire.OpenCodeGoTransportContractError):
        client.execute(request(body=b'not-json'))
    assert touched==[]


def test_secret_is_absent_from_default_repr():
    prepared=wire.prepare_upstream_request(request(),choice=wire.AccountChoice('opencode-go',GEN,'acct-a'),credential='SENSITIVE_TEST_TOKEN')
    assert 'SENSITIVE_TEST_TOKEN' not in repr(prepared)
    assert 'remember alpha' not in repr(prepared)


def test_exception_traceback_does_not_echo_sender_secret():
    def send(_):
        raise RuntimeError('SENSITIVE_TEST_TOKEN')
    with pytest.raises(wire.OpenCodeGoEffectUnknown) as caught:
        transport(sender=send).execute(request())
    assert 'SENSITIVE_TEST_TOKEN' not in ''.join(traceback.format_exception(caught.value))


def test_rollover_budget_is_not_whole_pool_exhaustion():
    receipt=transport(sender=lambda _:quota(),max_rollovers=0).execute(request())
    assert receipt.pool_exhausted is False
    assert receipt.stop_reason=='rollover_budget_exhausted'


def test_network_uncertainty_remains_no_replay():
    calls=[]
    def sender(r):
        calls.append(r.account_id)
        raise TimeoutError('connection lost')
    with pytest.raises(wire.OpenCodeGoEffectUnknown):
        transport(sender=sender).execute(request())
    assert calls==['acct-a']


@pytest.mark.parametrize("body", [
    b'{"model":"a","model":"b"}', b'{"model":"a","temperature":NaN}',
    b'[]', b'{"messages":[]}', b'{"model":""}',
])
def test_invalid_json_contract_is_rejected_before_selection(body):
    touched = []
    client = transport(resolver=lambda value: touched.append(value))
    with pytest.raises(wire.OpenCodeGoTransportContractError):
        client.execute(request(body=body))
    assert touched == []


@pytest.mark.parametrize("body", [
    b'{"type":"error","error":{"type":"GoUsageLimitError"}}',
    b'{"type":"error","error":{"type":"GoUsageLimitError"},"metadata":{"workspace":"test","limitName":"daily"}}',
    b'{"type":"error","error":{"type":"GoUsageLimitError"},"metadata":{"workspace":"","limitName":"5 hour"}}',
    b'{"type":"error","type":"error","error":{"type":"GoUsageLimitError"},"metadata":{"workspace":"test","limitName":"5 hour"}}',
])
def test_incomplete_or_ambiguous_error_metadata_does_not_rotate(body):
    assert wire.classify_pre_effect_refusal(wire.UpstreamResponse(429, {}, body)) is None


def test_tool_parameter_schema_is_not_mistaken_for_opaque_context():
    body = json.dumps({"model": "test", "input": "read the local file", "tools": [{
        "type": "function", "name": "read_file", "parameters": {"type": "object", "properties": {
            "file_id": {"type": "string"}, "encrypted_content": {"type": "string"}
        }}}]}).encode()
    assert transport().execute(request(body=body, path="responses")).response.status == 200


@pytest.mark.parametrize("item", [
    {"type": "item_reference", "id": "opaque"}, {"type": "input_file", "file_id": "opaque"},
    {"type": "reasoning", "encrypted_content": "opaque"},
])
def test_remote_account_scoped_context_is_not_rotated(item):
    body = json.dumps({"model": "test", "input": [item]}).encode()
    with pytest.raises(wire.OpenCodeGoTransportContractError, match="not replayable"):
        transport().execute(request(body=body, path="responses"))


def test_initial_pool_generation_must_match_callers_pinned_generation():
    touched = []
    client = transport(loader=lambda value: touched.append(value) or "synthetic")
    with pytest.raises(wire.OpenCodeGoTransportContractError, match="generation changed"):
        client.execute(request(), expected_pool_generation="f" * 64)
    assert touched == []
