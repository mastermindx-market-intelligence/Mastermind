"""Inert full-receipt examples, never original-run settlement or admission.

Tests substitute the closed hash table only in memory to exercise synthetic
receipt bytes. The CLI has no digest override and keeps the three actual hashes.
"""
import copy
import hashlib
import json
from unittest import mock

import pytest

from test_post_failure_phase_integration import fixture, response, phase, owner, WITNESS
from lane_runtime import cleanup_receipt_is_proven


def original_row(run):
    return dict(schema='mastermind.local_owned_process_receipt.v1', label=run,
        pid=12345, pgid=12345, started_at='2026-11-05T12:00:00+00:00',
        ended_at='2026-11-05T12:01:00+00:00', returncode=1, timed_out=False,
        runtime_failure_code='process_census_nonzero', stdout_bytes=0, stderr_bytes=0,
        stdout_sha256=hashlib.sha256(b'').hexdigest(),
        stdout_truncated=False, stderr_truncated=False,
        cleanup=dict(status='not_needed', census_proven=True, identity_verified=True,
            residual_count=0, error_code=None, stdin_delivery_complete=True,
            stdout_capture_complete=True, stderr_capture_complete=True,
            stdin_delivery_error=None, stdout_capture_error=None, stderr_capture_error=None))


def detail_fixture(monkeypatch, mutate=None):
    request, contract, packet = fixture()
    row = original_row(request['run_id'])
    if mutate: mutate(row)
    raw = phase.canonical(row) + b'\n'
    digest = hashlib.sha256(raw).hexdigest()
    monkeypatch.setitem(phase.RECEIPT_DIGESTS, request['run_id'], digest)
    request.update(receipt_metadata_only=True, expected_process_sha256=digest)
    return request, contract, packet, row, raw


def original_report(request, row, raw):
    report = copy.deepcopy(WITNESS['report'])
    report['observations']['marker'] = {'status':'absent'}
    report['observations']['returncode'] = {'status':'observed', 'returncode':76}
    report['observations']['process_receipt'] = dict(status='observed',
        receipt_sha256=hashlib.sha256(raw).hexdigest(), last_record=dict(pid=row['pid'],
            recorded_pgid=row['pgid'], recorded_sid=row['cleanup'].get('session_id'),
            recorded_cleanup={k:row['cleanup'].get(k) for k in (
                'identity_verified','stdout_capture_complete','stderr_capture_complete','stdin_delivery_complete')}))
    return report


def projected(monkeypatch, mutate=None):
    request, contract, packet, row, raw = detail_fixture(monkeypatch, mutate)
    report = original_report(request, row, raw)
    report['observations']['process_receipt']['receipt_detail'] = phase.receipt_detail(request, raw)
    return request, contract, packet, phase.project_report(request, report), row, raw


def bundle(request, contract, report):
    return dict(report=report, files=[], original_contract=contract,
        snapshot_state='PARTIAL_UNSETTLED', source_adoption_allowed=False)


def test_original_cleanup_predicate_can_qualify_recorded_failure_without_boot_or_hold(monkeypatch):
    req, contract, _, report, row, _ = projected(monkeypatch)
    assert cleanup_receipt_is_proven(row['cleanup']) is True
    assert report['state'] == 'RECORDED_TERMINAL_FAILURE'
    assert report['original_hold_observed'] is False
    assert report['recorded_predicates'] == dict(cleanup_predicate=True,
        cleanup_errors_and_session=True, recorded_capture_fields_complete=True,
        historical_permission='NO_PERMISSION_ERROR_RECORDED')
    assert report['receipt_detail']['stderr_sha256'] == {'present':False,'value':None}
    assert not any('GENERATION' in x or 'BOOT' in x for x in report['reason_codes'])
    for field in ('outcome_accepted','lease_released','export_authorized','effect_state_changed',
                  'execution_replayed','stream_content_read','pid_probe_performed'):
        assert report[field] is False
    assert owner.validate_response(response(req, bundle(req, contract, report)), req)['files'] == []


@pytest.mark.parametrize('key,value', [('census_proven',False), ('identity_verified',False),
    ('residual_count',1), ('status','process_census_unproven')])
def test_real_original_predicate_and_projected_failures_agree(monkeypatch, key, value):
    req, _, _, report, row, _ = projected(monkeypatch, lambda r:r['cleanup'].update({key:value}))
    assert cleanup_receipt_is_proven(row['cleanup']) is False
    assert report['recorded_predicates']['cleanup_predicate'] is False
    assert report['recorded_predicates']['cleanup_errors_and_session'] is False
    assert report['state']=='RECORDED_TERMINAL_FAILURE'  # recorded failure, not cleanup success


@pytest.mark.parametrize('status,session', [('terminated',12345), ('not_needed',12345),
    ('terminated',None), ('not_needed',None), ('terminated',12346)])
def test_actual_session_presence_is_preserved_not_replaced_by_absence(monkeypatch, status, session):
    _, _, _, report, _, _ = projected(monkeypatch,
        lambda r:r['cleanup'].update(status=status, session_id=session))
    assert report['receipt_detail']['cleanup']['session_id_present'] is True
    assert report['recorded_predicates']['cleanup_predicate'] is True
    assert report['recorded_predicates']['cleanup_errors_and_session'] is (session==12345)


def test_actual_own_incomplete_flags_cannot_be_promoted_to_recorded_cleanup(monkeypatch):
    _, _, _, report, _, _ = projected(monkeypatch,
        lambda r:r['cleanup'].update(identity_verified=False, stderr_capture_complete=False))
    assert report['recorded_predicates']['cleanup_predicate'] is False
    assert report['recorded_predicates']['recorded_capture_fields_complete'] is False


@pytest.mark.parametrize('fault', ['missing-error','permission','unknown-error','truncated','missing-digest'])
def test_capture_and_historical_permission_remain_separate_closed_facts(monkeypatch, fault):
    def mutate(r):
        if fault=='missing-error': del r['cleanup']['stderr_capture_error']
        elif fault=='permission': r['cleanup']['stderr_capture_error']='PermissionError'
        elif fault=='unknown-error': r['cleanup']['stderr_capture_error']='INERT_PRIVATE_CANARY'
        elif fault=='truncated': r['stderr_truncated']=True
        else: del r['stdout_sha256']
    _, _, _, report, _, _ = projected(monkeypatch, mutate)
    assert report['recorded_predicates']['recorded_capture_fields_complete'] is False
    expected = ('RECORDED_PERMISSION_ERROR' if fault=='permission' else
        'UNDETERMINED' if fault in ('missing-error','unknown-error') else 'NO_PERMISSION_ERROR_RECORDED')
    assert report['recorded_predicates']['historical_permission']==expected
    assert report['permission_refusal_observed'] is False
    assert b'INERT_PRIVATE_CANARY' not in phase.canonical(report)


@pytest.mark.parametrize('fault', ['changed-hash','foreign-label','bool-count','bool-residual','time-order',
    'bad-digest','duplicate-key','raw-secret-key'])
def test_hash_scope_and_strict_types_stop_unqualified_receipt(monkeypatch, fault):
    request, _, _, row, raw = detail_fixture(monkeypatch)
    if fault=='changed-hash': raw+=b' '
    else:
        if fault=='foreign-label': row['label']='other'
        elif fault=='bool-count': row['stdout_bytes']=True
        elif fault=='bool-residual': row['cleanup']['residual_count']=False
        elif fault=='time-order': row['ended_at']='2025-01-01T00:00:00Z'
        elif fault=='bad-digest': row['stdout_sha256']='PRIVATE'
        elif fault=='raw-secret-key':
            # Unknown original producer fields are not output fields.
            row['private_message']='INERT_PRIVATE_CANARY'
        raw=phase.canonical(row)+b'\n'
        if fault=='duplicate-key':raw=raw[:-2]+b',"pid":12345}\n'
        digest=hashlib.sha256(raw).hexdigest()
        monkeypatch.setitem(phase.RECEIPT_DIGESTS, request['run_id'],digest)
        request['expected_process_sha256']=digest
    if fault=='raw-secret-key':
        assert b'INERT_PRIVATE_CANARY' not in phase.canonical(phase.receipt_detail(request,raw))
    else:
        with pytest.raises((ValueError,TypeError)):phase.receipt_detail(request,raw)


@pytest.mark.parametrize('fault', ['derived','bool-as-int','state','same-hash','pgid','sid','flags','secret','artifact','nonce'])
def test_wire_recomputes_predicates_and_rejects_artifact_or_authority_injection(monkeypatch, fault):
    req, contract, _, report, _, _ = projected(monkeypatch)
    value=bundle(req,contract,report)
    if fault=='derived':report['recorded_predicates']['cleanup_predicate']=False
    elif fault=='bool-as-int':report['recorded_predicates']['cleanup_predicate']=1
    elif fault=='state':report['state']='UNKNOWN'
    elif fault=='same-hash':report['receipt_detail']['record_sha256']='0'*64
    elif fault=='pgid':report['recorded_completion']['recorded_pgid']=22222
    elif fault=='sid':report['recorded_completion']['recorded_sid']=22222
    elif fault=='flags':report['recorded_completion']['recorded_cleanup']['identity_verified']=False
    elif fault=='secret':report['receipt_detail']['message']='INERT_PRIVATE_CANARY'
    elif fault=='artifact':value['files']=[{'path':'/tmp/not-a-request','status':'NOT_FOUND','reason':'missing_at_read'}]
    raw=response(req,value)
    if fault=='nonce':req['invocation_id']='f'*32
    with pytest.raises(ValueError):owner.validate_response(raw,req)


def test_metadata_join_uses_only_existing_fixed_readers_and_never_reads_artifacts(monkeypatch):
    req, contract, packet, row, raw=detail_fixture(monkeypatch)
    original=original_report(req,row,raw);reads=[]
    class Reader:
        def __init__(self,*args):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def verify(self):pass
        def read(self,path,limit):
            reads.append(path)
            if path==('lanes','tmp',req['run_id']+'.txt'):return packet,None
            assert path==('lanes','ext','lanes',req['run_id']+'.process.jsonl')
            return raw,None
    def observe(*args,**kwargs):
        assert kwargs['observe_pid'] is False
        return copy.deepcopy(original)
    base={'Reader':Reader,'strict_json':json.loads,'observe':observe}
    forbidden=mock.Mock(side_effect=AssertionError('artifact reader invoked'))
    monkeypatch.setattr(phase,'snapshot_artifact',forbidden)
    result=phase.observe_original(base,{'MAX_TOTAL':1,'read_one':forbidden},req)
    assert len(reads)==2 and result['files']==[]
    assert result['report']['recorded_predicates']['cleanup_predicate'] is True
    forbidden.assert_not_called()
    owner.validate_response(response(req,result),req)


def test_metadata_owner_preserves_no_artifact_bytes_or_success_authority(tmp_path,monkeypatch):
    import os
    req,contract,_,report,_,_=projected(monkeypatch)
    value=bundle(req,contract,report)
    fd=os.open(tmp_path,os.O_RDONLY|os.O_DIRECTORY)
    class Chain:
        def verify(self):pass
        def close(self):os.close(fd)
    chain=Chain();chain.fd=fd;published=[]
    monkeypatch.setattr(owner,'qualify',lambda r:{'ssh_alias':'inert-only','source_sha256':{}})
    monkeypatch.setattr(owner.delivery,'reserve_destination',lambda p:chain)
    monkeypatch.setattr(owner.delivery,'transport',lambda *a,**k:response(req,value))
    monkeypatch.setattr(owner.delivery,'publish_receipt',lambda c,r,q,**k:published.append(copy.deepcopy(r)))
    result=owner.observe(req,tmp_path)
    assert result['state']=='METADATA_OBSERVED' and result['local_preservation_created'] is False
    assert result['files']==[] and not list(tmp_path.glob('unsettled-*'))
    assert (tmp_path/'request.json').is_file()
    for key in ('outcome_accepted','source_adoption_allowed','retry_authorized','effect_state_changed','execution_replayed'):
        assert result[key] is False
    assert published[-1]['state']=='METADATA_OBSERVED'


def test_fixed_actual_hash_binding_has_no_request_override(monkeypatch):
    request,_,_=fixture()
    request.update(receipt_metadata_only=True,expected_process_sha256='f'*64)
    with pytest.raises(ValueError,match='same_original_receipt_binding'):phase.validate_request(request)


@pytest.mark.parametrize('fault',['permission','support','missing-record'])
def test_unqualified_current_metadata_never_promotes_historical_disposition(monkeypatch, fault):
    req, _, _, row, raw=detail_fixture(monkeypatch)
    original=original_report(req,row,raw)
    original['observations']['process_receipt']['receipt_detail']=phase.receipt_detail(req,raw)
    if fault=='permission':original.update(status='unavailable',request_stopped=True,reason='os_permission_denied')
    elif fault=='support':original['observations']['support']['verified_code_files']=36
    else:original['observations']['process_receipt']={'status':'absent'}
    report=phase.project_report(req,original)
    assert report['state']=='UNKNOWN'
    if fault=='permission':assert report['receipt_detail'] is None


@pytest.mark.parametrize('state',['ABSENT_AT_OBSERVATION','ORDINARY_LEASE_MARKER','RECONCILIATION_HOLD'])
def test_marker_absence_and_original_lease_are_distinct_not_settlement(monkeypatch,state):
    req, _, _, report, _, _=projected(monkeypatch)
    item={'state':state,'marker_sha256':None,'original_lease':None}
    if state!='ABSENT_AT_OBSERVATION':
        item.update(marker_sha256='a'*64,original_lease=dict(schema='mastermind.local_lane_lease.v1',
            key=req['run_id'],label=req['run_id'],pid=12345,started_at='2026-11-05T12:00:00Z',
            host=req['host'],source_sha256=None,reconcile_unreleased=True))
    phase.validate_marker(req,item)
    assert report['lease_released'] is False
    if item['original_lease']:
        item['original_lease']['host']='foreign'
        with pytest.raises(ValueError):phase.validate_marker(req,item)
