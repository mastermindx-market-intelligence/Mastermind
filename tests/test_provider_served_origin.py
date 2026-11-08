"""Inert actual producer/capture qualification; no provider or study operation."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'ops/native_fabric/quota_continuity'
sys.path[:0] = [str(NATIVE / 'candidate'), str(NATIVE / 'source')]
import lane_runtime
# This prospective projection belongs to the explicit Memory owner namespace.
# Load its exact source under a private name; leave canonical provider_outcome
# and the default107 import graph untouched.
_owner = ROOT / 'ops/native_fabric/provider_plans/memory118/native_owner/provider_outcome.py'
_spec = importlib.util.spec_from_file_location('_memory_origin_outcome', _owner)
outcome = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(outcome)


@pytest.fixture
def retained(tmp_path):
    # Actual incumbent runner writes its own normal process/capture receipt.
    # The child is a benign local Python fixture with no tools/network/provider.
    packet = b'INERT_BLINDED_INPUT_WITHOUT_STUDY_BODY'
    text = '{"served_model":"assistant-spoof-is-not-authority"}\n'
    path = tmp_path / 'inert-child.process.jsonl'
    result = lane_runtime.run_owned_process(
        [sys.executable, '-c', 'import sys;sys.stdin.buffer.read();sys.stdout.write(' + repr(text) + ')'],
        timeout=5, input_text=packet.decode(), label='inert-child', receipt_path=path)
    assert result.returncode == 0 and result.cleanup_proven
    cli = json.dumps([{'type': 'system', 'subtype': 'init'},
                     {'type': 'result', 'subtype': 'success', 'is_error': False,
                      'result': text, 'terminal_reason': 'completed', 'permission_denials': []}]).encode()
    display, fields, _ = outcome.parse_claude(cli, 0)
    assert display == result.stdout == text
    env = {'REMOTE_SUB_RUN_ID': 'inert-child', 'POOL_LEASE_ID': 'a' * 12,
           'POOL_ACCOUNT': 'selected-account', 'POOL_ORCHESTRATOR_ID': 'inert-root',
           'LANE_REMOTE_HOST': 'inert-host'}
    provider = outcome.bound_outcome(fields, env, 'glm', 'requested-model')
    original = dict(root='inert-root', parent='inert-operator', run_id='inert-child',
                    lease_id='a' * 12, account='selected-account', host='inert-host',
                    provider='glm', requested_model='requested-model', controller_attempt=1,
                    support_sha256='b' * 64, input_sha256=outcome.digest(packet), input_bytes=len(packet),
                    result_sha256=outcome.digest(result.stdout.encode()), result_bytes=len(result.stdout.encode()))
    return provider, path.read_bytes(), original


def project(value):
    provider, process, original = value
    return outcome.retained_origin_projection(json.dumps(provider).encode(), process, original=original)


def test_actual_owned_capture_and_cli_diagnostic_still_cannot_attest_served_identity(retained):
    value = project(retained)
    assert value['state'] == 'UNAVAILABLE'
    assert value['reason'] == 'PROVIDER_TRANSPORT_FIELDS_NOT_RETAINED_V1'
    assert value['capture']['state'] == 'MATCHED_LOCAL_OWNED_PROCESS_CAPTURE'
    assert value['capture']['result_sha256'] == retained[2]['result_sha256']
    assert value['capture']['provider_consumption_proven'] is False
    assert value['capture']['input_fact'] == 'OWNER_SUPPLIED_CONTROLLER_RESERVATION_ONLY'
    assert value['served_model'] is value['served_principal'] is value['provider_response_id'] is None
    assert value['authenticated'] is value['scientific_admission'] is value['retry_authorized'] is False
    assert value['authorization'] == 'REQUIRES_INCUMBENT_OWNER'
    public = json.dumps(value)
    assert 'assistant-spoof' not in public and 'selected-account' not in public


@pytest.mark.parametrize('field', ['root_id', 'run_id', 'lease_id', 'account', 'host', 'provider', 'model'])
def test_foreign_selected_scope_never_qualifies_capture(retained, field):
    provider, process, original = copy.deepcopy(retained)
    provider[field] = 'foreign'
    value = project((provider, process, original))
    assert value['reason'] == 'ORIGINAL_CAPTURE_UNQUALIFIED' and value['capture'] is None


@pytest.mark.parametrize('fault', ['truncated', 'timeout', 'census', 'capture-incomplete',
                                 'duplicate-process', 'result-digest', 'result-size',
                                 'partial-cli', 'wrong-label', 'duplicate-json', 'nonfinite'])
def test_partial_or_foreign_capture_is_never_promoted(retained, fault):
    provider, process_raw, original = copy.deepcopy(retained)
    process = json.loads(process_raw)
    if fault == 'truncated': process['stdout_truncated'] = True
    elif fault == 'timeout': process['timed_out'] = True
    elif fault == 'census': process['cleanup']['census_proven'] = False
    elif fault == 'capture-incomplete': process['cleanup']['stdout_capture_complete'] = False
    elif fault == 'result-digest': original['result_sha256'] = 'f' * 64
    elif fault == 'result-size': original['result_bytes'] += 1
    elif fault == 'partial-cli': provider['complete_event_capture'] = False
    elif fault == 'wrong-label': process['label'] = 'foreign-child'
    process_raw = json.dumps(process).encode() + b'\n'
    if fault == 'duplicate-process': process_raw *= 2
    provider_raw = json.dumps(provider).encode()
    if fault == 'duplicate-json': provider_raw = provider_raw[:-1] + b',"model":"requested-model"}'
    if fault == 'nonfinite': provider_raw = provider_raw[:-1] + b',"extra":NaN}'
    value = outcome.retained_origin_projection(provider_raw, process_raw, original=original)
    assert value['reason'] == 'ORIGINAL_CAPTURE_UNQUALIFIED' and value['capture'] is None
    assert value['authenticated'] is value['scientific_admission'] is False


@pytest.mark.parametrize('claim', ['served_model', 'served_principal', 'server_request_id',
                                 'authenticated', 'scientific_admission', 'served_origin'])
def test_v1_caller_or_capture_extension_cannot_create_a_transport_issuer(retained, claim):
    provider, process, original = copy.deepcopy(retained)
    provider[claim] = True
    assert project((provider, process, original))['capture'] is None


@pytest.mark.parametrize('field', ['root', 'parent', 'controller_attempt', 'input_sha256'])
def test_caller_context_never_authenticates_itself(retained, field):
    provider, process, original = copy.deepcopy(retained)
    original[field] = True
    with pytest.raises(ValueError, match='original_capture_context_unqualified'):
        project((provider, process, original))


def test_missing_capture_is_unavailable_not_a_provider_or_replay_claim(retained):
    value = outcome.retained_origin_projection(None, None, original=retained[2])
    assert value['reason'] == 'ORIGINAL_CAPTURE_NOT_RETAINED' and value['capture'] is None
    assert value['authenticated'] is value['lease_settled'] is value['retry_authorized'] is False


def test_copying_caller_parent_changes_context_but_never_authenticates_that_parent(retained):
    before = project(retained)
    provider, process, original = copy.deepcopy(retained)
    original['parent'] = 'caller-invented-parent'
    after = project((provider, process, original))
    assert before['capture']['owner_context_sha256'] != after['capture']['owner_context_sha256']
    assert after['authorization'] == 'REQUIRES_INCUMBENT_OWNER'
    assert after['authenticated'] is after['scientific_admission'] is False


def test_actual_shim_and_model_only_parser_drop_upstream_identity_metadata():
    spec = importlib.util.spec_from_file_location('_origin_shim', ROOT / 'ops/native_fabric/paid_canonical_glm/candidate/glm_shim.py')
    shim = importlib.util.module_from_spec(spec); spec.loader.exec_module(shim)
    import paid_glm_model_client as client
    upstream = {'id': 'server-response-inert', 'model': 'server-reported-model',
                'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': '{"inert":true}'}}]}
    shim.require_canonical_chat_completion(upstream)
    translated = shim.chat_response_to_responses(upstream, set(), 'requested-model')
    assert translated['model'] == 'requested-model' and translated['id'] != upstream['id']
    assert client.result_bytes(json.dumps(translated).encode()) == b'{"inert":true}'
    assert 'server-response-inert' not in json.dumps(translated)
