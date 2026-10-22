"""Recover only the original committed ruling; no sender or principal lease.

The host authority/kernel guard and Relay are fixtures; Runtime and COMMIT
records are real. This does not qualify an installed caller or provider.
"""
import asyncio

import pytest

from control_plane.coo_principal_host import CooHostProvider
from integrations.product_acceptance_qualification_recovery import ProductAcceptanceQualificationRecovery
from integrations.product_acceptance_ruling_owner import ProductAcceptanceRulingReceiptReader, AGGREGATE
from tests.test_product_acceptance_ruling_owner import ready


@pytest.mark.parametrize('fault', ['none', 'uncommitted', 'principal_revoked', 'caller_after_read'])
def test_original_reply_recovery_only_qualifies_under_current_authority(tmp_path, monkeypatch, fault):
    values = ready(tmp_path, monkeypatch, commit=fault != 'uncommitted')
    runtime, requester, binding, target, basis, prepared, original, relay, resolver = values
    authority = object.__new__(CooHostProvider)
    observed = []

    def principal_guard(**kwargs):
        observed.append(kwargs)
        if fault == 'principal_revoked': raise ValueError('fixture principal revoked')

    monkeypatch.setattr(authority, 'guard_dialogue', principal_guard)
    current = [True]
    def request_guard():
        if not current[0]: raise ValueError('fixture caller rotated')

    async def transport(path, request):
        assert request['operation'] in {'read_thread', 'wait_for_reply'}
        result = await relay(path, request)
        if fault == 'caller_after_read': current[0] = False
        return result

    def no_commit(*args, **kwargs): pytest.fail('recovery must never COMMIT')
    monkeypatch.setattr(type(original.principal_owner), 'before_commit', no_commit)
    recovery = ProductAcceptanceQualificationRecovery(requester=requester,
        authority=authority, socket_path=original.principal_owner.socket_path)
    async def run():
        return await recovery.recover(binding=binding, message_key=prepared.message['message_key'],
            receiving_request_guard=request_guard, service_call=transport)

    if fault == 'none':
        result = asyncio.run(run())
        assert result['state'] == 'RULING_QUALIFIED_PARENT_RETURN_PENDING'
        assert len(runtime.events.list_events(aggregate_type=AGGREGATE)) == 1
        assert ProductAcceptanceRulingReceiptReader(requester).observe_qualified(
            binding=binding, message_key=prepared.message['message_key']) == result
        assert observed[-1]['root_job_id'] == requester._test_root.job_id
    else:
        with pytest.raises(Exception): asyncio.run(run())
        assert runtime.events.list_events(aggregate_type=AGGREGATE) == []
    assert all(call['operation'] != 'send_message' for call in relay.calls)
