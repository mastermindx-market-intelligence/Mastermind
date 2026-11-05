"""No provider/host effects: preserve a genuine owner's receipt through the return."""
import asyncio
from types import SimpleNamespace
import pytest
from control_plane.broker_assignment_seal import validate_physical_release, AssignmentObservationError
from control_plane.executive_fabric_adapter import AttendedFabricWorkerAdapter
from control_plane.executive_worker_broker import BrokerProtocolError, BrokerStateError


def receipt():
    return dict(schema='mastermind.lane.owned_release/v1',key='original-attempt',
        marker_device=7,marker_inode=8,parent_device=7,parent_inode=9,
        released_at='2026-10-14T00:00:00+00:00',marker_absent=True,parent_synced=True)


@pytest.mark.parametrize('changes', [
    {'key':'another-attempt'}, {'marker_absent':False}, {'parent_synced':False},
    {'marker_inode':True}, {'parent_device':-1}, {'released_at':''}, {'extra':'field'},
])
def test_wrong_original_or_incomplete_release_is_refused(changes):
    with pytest.raises(AssignmentObservationError):
        validate_physical_release({**receipt(),**changes},run_id='original-attempt')


def test_source_only_digest_does_not_replace_actual_receipt():
    with pytest.raises(AssignmentObservationError):
        validate_physical_release({'physical_release_sha256':'a'*64},run_id='original-attempt')


@pytest.fixture
def adapter(monkeypatch):
    from test_executive_fabric_bridge_broker import start_result, start_payload
    from control_plane.executive_worker_broker import _process_ref_from_json
    # This is a transport fixture only, not a production Worker or lease proof.
    ref=_process_ref_from_json(start_result(start_payload())['process_ref'])
    value=object.__new__(AttendedFabricWorkerAdapter)
    value._physical_release_receipts={}
    value._known=lambda r:(None,None,None,SimpleNamespace(worker_id='worker'))
    value._validate_lease=lambda run_id:None
    ack=dict(run_id=ref.run_id,observation_sha256='a'*64,retention_sha256='b'*64)
    reply={'acknowledgement':ack,'physical_release':{**receipt(),'key':ref.run_id}}
    async def request(r,operation,**kwargs):
        assert r is ref and operation=='assignment-seal-finalize'
        return reply
    value._request=request
    return value,ref,ack,reply


def test_legacy_ack_does_not_create_physical_release_evidence(adapter):
    value,ref,ack,reply=adapter
    del reply['physical_release']
    assert asyncio.run(value.finalize_assignment(ref,ack))==ack
    with pytest.raises(BrokerStateError): value.assignment_physical_release(ref)


def test_original_receipt_is_detached_and_changed_readback_refuses(adapter):
    value,ref,ack,reply=adapter
    assert asyncio.run(value.finalize_assignment(ref,ack))==ack
    original=value.assignment_physical_release(ref)
    original['parent_inode']=999
    assert value.assignment_physical_release(ref)['parent_inode']==9
    reply['physical_release']['parent_inode']=999
    with pytest.raises(BrokerProtocolError,match='changed'):
        asyncio.run(value.finalize_assignment(ref,ack))
    assert value.assignment_physical_release(ref)['parent_inode']==9


def test_bad_response_is_not_retained(adapter):
    value,ref,ack,reply=adapter
    reply['physical_release']['marker_absent']=False
    with pytest.raises(BrokerProtocolError): asyncio.run(value.finalize_assignment(ref,ack))
    with pytest.raises(BrokerStateError): value.assignment_physical_release(ref)
