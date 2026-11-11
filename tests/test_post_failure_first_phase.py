"""First source-only checks: retained metadata is not historical settlement."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT/'ops/native_fabric/quota_continuity'
spec = importlib.util.spec_from_file_location('post_failure_first_phase', NATIVE/'candidate/post_failure_observation.py')
phase = importlib.util.module_from_spec(spec)
spec.loader.exec_module(phase)

# Actual retained ordinary observation, not an invented current/run completion.
WITNESS = Path(__file__).parent/'fixtures/post-failure-routing-observation.json'


def witness():
    return json.loads(WITNESS.read_text())


def request():
    old = witness()['request']
    return {k: old[k] for k in ('run_id','root','parent','host','support_digest')} | {
        'artifact':{k:old['artifact'][k] for k in ('packet_sha256','support_files')},
        'request_record_sha256':'c'*64,'request_launch_sha256':'d'*64,'invocation_id':'e'*32,
        'schema':phase.SCHEMA,'launch_binding_sha256':'a'*64,'terminal_log_sha256':'b'*64,
        'prior_receipt_sha256':phase.SCOPES[old['run_id']]['prior_receipt_sha256']}


def test_retained_prefailure_absence_does_not_claim_final_absence_or_settlement():
    value = phase.project_report(request(), witness()['report'])
    assert value['state'] == 'UNKNOWN'
    assert value['earlier_absence_is_not_final_absence'] is True
    assert value['final_process_receipt_observed'] is False
    assert 'FINAL_ORIGINAL_PROCESS_RECEIPT_NOT_OBSERVED' in value['reason_codes']
    assert 'ORIGINAL_CHILD_START_GENERATION_NOT_PROVEN' in value['reason_codes']
    for field in ('pid_probe_performed','stream_content_read','effect_state_changed','lease_released','export_authorized','outcome_accepted'):
        assert value[field] is False


def test_later_record_can_be_observed_without_promoting_recorded_flags_to_settlement():
    report = copy.deepcopy(witness()['report'])
    report['observations']['process_receipt'] = {'status':'observed','receipt_sha256':'0'*64,'last_record':{
        'pid':12345,'recorded_cleanup':{'identity_verified':True,'stdout_capture_complete':True,
                                     'stderr_capture_complete':True,'stdin_delivery_complete':True}}}
    value = phase.project_report(request(), report)
    assert value['final_process_receipt_observed'] is True
    assert value['recorded_completion']['child_pid'] == 12345
    assert value['state'] == 'UNKNOWN' and value['export_authorized'] is False
    assert 'ORIGINAL_COMPLETION_RECORD_OBSERVED_NOT_SETTLEMENT' in value['reason_codes']


@pytest.mark.parametrize('field,value', [('parent','other'),('host','ubuntu2'),('support_digest','f'*64),('observe_pid',True)])
def test_request_substitution_never_becomes_a_remote_probe(field,value):
    req = request();req[field]=value
    with pytest.raises(ValueError): phase.validate_request(req)
