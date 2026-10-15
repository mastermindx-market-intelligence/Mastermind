"""The requester can consume a separately qualified ruling without a principal.

Runtime and COMMIT owners are real; Relay/source observations remain fixtures.
These checks establish no installed grant, authenticated ingress or live delivery.
"""

import asyncio
import dataclasses
from pathlib import Path

import pytest

from integrations.mastermind_company_mcp.adapter import CompanyDialogueGateway
from integrations.product_acceptance_request_owner import ProductAcceptanceRequestOwner
from tests.test_mastermind_company_mcp import _StaticResolver
from tests.test_product_acceptance_ruling_owner import ready, qualify, AGGREGATE


def requester_gateway(values, *, binding=None):
    runtime, requester, original, *_ = values
    # A separate requesting host has the exact Runtime/source reader, but never
    # receives a principal COMMIT owner or permission to impersonate one.
    owner = ProductAcceptanceRequestOwner(runtime, requester.reader)

    async def no_transport(*args, **kwargs):
        pytest.fail("retained receipt consumption must not send or poll Relay")

    return CompanyDialogueGateway(
        _StaticResolver(original if binding is None else binding),
        socket_path=Path('/private/tmp/phase-fixture.sock'),
        service_call=no_transport,
        product_acceptance_owner=owner,
    )


def call(gateway, values):
    return asyncio.run(gateway.call('request_decision', {
        'purpose': 'PRODUCT_ACCEPTANCE', 'subject_job_id': values[3].job_id,
    }))


def test_separate_requester_reads_exact_committed_receipt_without_principal(tmp_path, monkeypatch):
    values = ready(tmp_path, monkeypatch)
    qualified = qualify(values)
    events = values[0].events.list_events(aggregate_type=AGGREGATE)
    response = call(requester_gateway(values), values)
    assert response['ok'] is True, response
    assert response['data'] == qualified
    assert values[0].events.list_events(aggregate_type=AGGREGATE) == events


def test_visible_committed_ruling_without_qualification_stays_pending(tmp_path, monkeypatch):
    values = ready(tmp_path, monkeypatch)
    response = call(requester_gateway(values), values)
    assert response['ok'] is False
    assert response['error']['detail_code'] == 'PRODUCT_REQUEST_RECONCILIATION_REQUIRED'
    assert values[0].events.list_events(aggregate_type=AGGREGATE) == []


@pytest.mark.parametrize('field,value', [('thread_ts', '1787896100.123456'),
                                         ('session_ref', 'asd-session-productfixture02')])
def test_qualified_receipt_cannot_be_consumed_by_a_rebound_requester(
    tmp_path, monkeypatch, field, value,
):
    values = ready(tmp_path, monkeypatch)
    qualify(values)
    changed = dataclasses.replace(values[2], **{field: value})
    response = call(requester_gateway(values, binding=changed), values)
    assert response['ok'] is False
    assert response['error']['detail_code'] == 'PRODUCT_PARENT_BINDING_CHANGED'


def test_receiving_principal_qualifies_its_actual_reply_without_worker_send_grant(tmp_path, monkeypatch):
    values = ready(tmp_path, monkeypatch)
    owner = values[6]
    qualified = asyncio.run(owner.qualify_committed_request())
    assert qualified['request_message_key'] == values[5].message['message_key']
    assert call(requester_gateway(values), values)['data'] == qualified
    assert all(row['operation'] != 'send_message' for row in values[7].calls)


@pytest.mark.parametrize('failure', [False, True])
def test_app_receiving_phase_preserves_original_ruling_result(tmp_path, monkeypatch, failure):
    from types import SimpleNamespace
    from integrations import mastermind_company_principal_app_receiver as receiver
    from integrations.company_dialogue_principal_app_contract import encode_app_request
    from integrations.mastermind_company_mcp.principal_schemas import principal_result_envelope
    from tests.test_principal_app_dialogue_contract import caller, arguments
    from integrations.product_acceptance_request_owner import ProductAcceptanceRequestUnavailable

    values = ready(tmp_path, monkeypatch)
    result = principal_result_envelope('ruling', data={'message_key': 'original-result'})
    calls = []

    class Gateway:
        async def call(self, tool, arguments):
            calls.append((tool, arguments))
            return result

    owner = values[6]
    if failure:
        async def unavailable():
            raise ProductAcceptanceRequestUnavailable('PRODUCT_RULING_COMMIT_UNCONFIRMED')
        monkeypatch.setattr(owner, 'qualify_committed_request', unavailable)

    async def acquired(**kwargs):
        assert kwargs['product_acceptance_reader'] is values[1].reader
        return SimpleNamespace(gateway=Gateway(), request_owner=SimpleNamespace(ruling_owner=owner))

    # Only this receiving-phase test replaces source acquisition/the send; its
    # Runtime receipt/qualification and subsequent requester are real owners.
    monkeypatch.setattr(receiver, 'build_acquired_principal_decision_host', acquired)
    provider = receiver.PrincipalDialogueAppReceiver(values[0], None, None, None, values[1].reader)
    raw = encode_app_request(caller=caller(), obligation_id='WAKE-'+'d'*32,
        tool='ruling', arguments={**arguments(), 'selected_option': 'opt-product-accept'})
    response = asyncio.run(provider.ruling(raw, receiving_request_guard=lambda: None))
    assert len(calls) == 1 and response['ok'] is True
    assert response['data']['message_key'] == result['data']['message_key']
    if failure:
        assert response['data']['product_acceptance']['state'] == 'QUALIFICATION_PENDING'
        assert values[0].events.list_events(aggregate_type=AGGREGATE) == []
    else:
        assert response['data']['product_acceptance'] == call(requester_gateway(values), values)['data']
