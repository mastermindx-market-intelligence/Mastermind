"""Inert failure-stage discrimination: no original read, SSH, or settlement.

Synthetic exceptions execute in a local generated-code subprocess. The actual
87676 failure remains unclassified: this prospective wire cannot recover it.
"""
import copy
import hashlib
import json
import os
import subprocess
import sys
from unittest import mock

import pytest

from test_post_failure_receipt_detail import detail_fixture, projected, bundle
from test_post_failure_phase_integration import owner, phase, response


@pytest.fixture(autouse=True)
def inert_destination(tmp_path,monkeypatch):
    # Only test-owned temporary bytes; never the approved original evidence root.
    class Chain:
        def __init__(self): self.fd=os.open(tmp_path,os.O_RDONLY|os.O_DIRECTORY)
        def verify(self): pass
        def close(self): os.close(self.fd)
    monkeypatch.setattr(owner.delivery,'reserve_destination',lambda p:Chain())


@pytest.mark.parametrize('expression,expected,permission', [
    ("ValueError('original_lease_projection')", 'REMOTE_MARKER_PROJECTION_INVALID', False),
    ("ValueError('same_record_projection_mismatch')", 'REMOTE_RECEIPT_PROJECTION_INVALID', False),
    ("ValueError('original_remote_packet_unqualified')", 'REMOTE_ORIGINAL_PACKET_INVALID', False),
    ("FileNotFoundError('INERT_PRIVATE_CANARY')", 'REMOTE_ORIGINAL_INPUT_NOT_FOUND', False),
    ("PermissionError(13,'INERT_PRIVATE_CANARY')", 'REMOTE_READ_PERMISSION_REFUSED', True),
    ("ValueError('INERT_PRIVATE_CANARY')", 'REMOTE_OBSERVATION_FAILED', False),
])
def test_actual_generated_runner_returns_only_bound_closed_error(monkeypatch, expression, expected, permission):
    request, _, _, _, _ = detail_fixture(monkeypatch)
    here = owner.delivery.HERE
    sources = {n: (here/n if (here/n).exists() else here.parent/'source'/n).read_bytes() for n in (
        'run_observation.py','post_failure_observation.py','artifact_reader.py')}
    # The only substitute is an inert observation function; original readers
    # and every actual held path remain uncalled. No native-parent mock claim.
    sources['post_failure_observation.py'] += (
        '\ndef observe_original(*args):\n raise '+expression+'\n').encode()
    hashes = {n: hashlib.sha256(b).hexdigest() for n,b in sources.items()}
    monkeypatch.setattr(owner, 'qualify', lambda req: {'source_sha256': hashes})
    monkeypatch.setattr(owner.delivery, 'local_file', lambda p, cap: sources[p.name])
    code = owner.code_for_request(request, expected_sources=hashes)
    result = subprocess.run([sys.executable,'-I','-S','-c',code],
        input=phase.canonical(request), capture_output=True, timeout=10)
    assert result.returncode == 0
    assert b'INERT_PRIVATE_CANARY' not in result.stdout+result.stderr
    value = owner.validate_response(result.stdout, request)
    assert value == {'diagnostic': {'stage':'REMOTE_OBSERVATION',
        'code':expected, 'permission_refusal':permission}}


@pytest.mark.parametrize('fault', ['unknown-code','raw-field','integer-permission','wrong-stage',
                                  'permission-contradiction','wrong-request','report-and-diagnostic'])
def test_remote_diagnostic_binding_and_privacy_fail_closed(monkeypatch, fault):
    request, _, _, _, _ = detail_fixture(monkeypatch)
    item = dict(stage='REMOTE_OBSERVATION',code='REMOTE_MARKER_PROJECTION_INVALID',permission_refusal=False)
    wire = dict(schema=phase.SCHEMA,request_sha256=hashlib.sha256(phase.canonical(request)).hexdigest(),diagnostic=item)
    if fault=='unknown-code': item['code']='INERT_PRIVATE_CANARY'
    elif fault=='raw-field': item['message']='INERT_PRIVATE_CANARY'
    elif fault=='integer-permission': item['permission_refusal']=0
    elif fault=='wrong-stage': item['stage']='REMOTE_REQUEST'
    elif fault=='permission-contradiction': item['permission_refusal']=True
    elif fault=='wrong-request': wire['request_sha256']='0'*64
    else: wire['report']={}
    with pytest.raises(ValueError): owner.validate_response(phase.canonical(wire), request)


@pytest.mark.parametrize('error,stage,code', [
    (ValueError('post_failure_local_preparation_failed'),'LOCAL_CODE_PREPARATION','LOCAL_SOURCE_QUALIFICATION_FAILED'),
    (ValueError('post_failure_local_preparation_permission_refused'),'LOCAL_CODE_PREPARATION','LOCAL_SOURCE_PERMISSION_REFUSED'),
    (ValueError('transport_unavailable'),'READ_TRANSPORT','READ_TRANSPORT_EXIT_UNCONFIRMED'),
    (ValueError('transport_timeout'),'READ_TRANSPORT','READ_TRANSPORT_TIMEOUT'),
    (ValueError('transport_output_limit'),'READ_TRANSPORT','READ_TRANSPORT_OUTPUT_LIMIT'),
    (ValueError('INERT_PRIVATE_CANARY'),'READ_TRANSPORT','POST_FAILURE_READ_UNCONFIRMED'),
])
def test_local_closed_stages_never_promote_or_repeat(tmp_path,monkeypatch,error,stage,code):
    request, _, _, _, _ = detail_fixture(monkeypatch)
    monkeypatch.setattr(owner,'qualify',lambda req:{'ssh_alias':'inert-unused','source_sha256':{}})
    with mock.patch.object(owner.delivery,'transport',side_effect=error) as transport:
        receipt=owner.observe(request,tmp_path/'one')
    assert transport.call_count==1
    assert receipt['diagnostic_stage']==stage and receipt['diagnostic_code']==code
    assert receipt['state']=='UNAVAILABLE' and receipt['report'] is None and receipt['files']==[]
    assert receipt['read_transport_state']==('NOT_ATTEMPTED' if stage=='LOCAL_CODE_PREPARATION' else 'ATTEMPTED_UNCONFIRMED')
    assert receipt['read_permission_refusal'] is (code=='LOCAL_SOURCE_PERMISSION_REFUSED')
    assert b'INERT_PRIVATE_CANARY' not in phase.canonical(receipt)
    for k in ('execution_replayed','effect_state_changed','outcome_accepted','source_adoption_allowed','retry_authorized'):
        assert receipt[k] is False


def test_remote_closed_error_has_response_but_no_adoption_or_republication(tmp_path,monkeypatch):
    request, _, _, _, _ = detail_fixture(monkeypatch)
    monkeypatch.setattr(owner,'qualify',lambda req:{'ssh_alias':'inert-unused','source_sha256':{}})
    wire=phase.canonical(dict(schema=phase.SCHEMA,
        request_sha256=hashlib.sha256(phase.canonical(request)).hexdigest(),
        diagnostic=dict(stage='REMOTE_OBSERVATION',code='REMOTE_MARKER_PROJECTION_INVALID',permission_refusal=False)))
    real=owner.delivery.publish_receipt
    with mock.patch.object(owner.delivery,'transport',return_value=wire) as transport, \
         mock.patch.object(owner.delivery,'publish_receipt',wraps=real) as publish:
        receipt=owner.observe(request,tmp_path/'one')
    assert transport.call_count==publish.call_count==1
    assert receipt['read_transport_state']=='RESPONSE_RECEIVED'
    assert receipt['diagnostic_code']=='REMOTE_MARKER_PROJECTION_INVALID'
    assert receipt['files']==[] and receipt['report'] is None
    assert receipt['state']=='UNAVAILABLE' and receipt['retry_authorized'] is False


def test_remote_error_publication_failure_has_no_second_publication(tmp_path,monkeypatch):
    request, _, _, _, _ = detail_fixture(monkeypatch)
    monkeypatch.setattr(owner,'qualify',lambda req:{'ssh_alias':'inert-unused','source_sha256':{}})
    wire=phase.canonical(dict(schema=phase.SCHEMA,
        request_sha256=hashlib.sha256(phase.canonical(request)).hexdigest(),
        diagnostic=dict(stage='REMOTE_OBSERVATION',code='REMOTE_OBSERVATION_FAILED',permission_refusal=False)))
    with mock.patch.object(owner.delivery,'transport',return_value=wire), \
         mock.patch.object(owner.delivery,'publish_receipt',side_effect=OSError('inert')) as publish:
        with pytest.raises(OSError): owner.observe(request,tmp_path/'one')
    assert publish.call_count==1


def test_received_invalid_response_is_not_relabelled_ssh_failure(tmp_path,monkeypatch):
    request, _, _, _, _=detail_fixture(monkeypatch)
    monkeypatch.setattr(owner,'qualify',lambda req:{'ssh_alias':'inert-unused','source_sha256':{}})
    monkeypatch.setattr(owner.delivery,'transport',lambda *a,**k:b'not-json')
    r=owner.observe(request,tmp_path/'one')
    assert r['read_transport_state']=='RESPONSE_RECEIVED'
    assert r['diagnostic_stage']=='RESPONSE_VALIDATION'
    assert r['diagnostic_code']=='POST_FAILURE_RESPONSE_UNQUALIFIED'


def test_local_preparation_drops_private_exception_and_prevents_transport(monkeypatch):
    request, _, _, _, _=detail_fixture(monkeypatch)
    monkeypatch.setattr(owner,'qualify',mock.Mock(side_effect=ValueError('INERT_PRIVATE_CANARY')))
    with pytest.raises(ValueError,match='^post_failure_local_preparation_failed$'):
        owner.code_for_request(request,expected_sources={})


def test_negative_original_flags_are_data_not_a_remote_exception(monkeypatch):
    _,_,_,report,_,_=projected(monkeypatch,lambda r:r['cleanup'].update(
        identity_verified=False,stderr_capture_complete=False,census_proven=False,residual_count=None))
    assert report['state']=='RECORDED_TERMINAL_FAILURE'
    assert report['recorded_predicates']['cleanup_predicate'] is False
    assert report['recorded_predicates']['recorded_capture_fields_complete'] is False
