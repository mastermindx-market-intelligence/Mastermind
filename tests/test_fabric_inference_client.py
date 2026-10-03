import asyncio
import ast
import importlib
from pathlib import Path

import pytest


def service_receipt(tmp_path, operation_key, objective):
    from control_plane.executive_inference_contract import derive
    from control_plane.ceo_intent import submit_intent
    from control_plane.executive_runtime import Runtime
    from tests.test_vps_inference_service import GROUND, host_execution_binding
    envelope = derive(
        {"operation_key": operation_key, "objective": objective},
        GROUND,
    )["envelope"]
    return submit_intent(
        Runtime.at(tmp_path / "runtime"),
        envelope,
        workspace_root=tmp_path,
        service_admission_guard=lambda _: None,
        service_execution_binding=host_execution_binding(
            tmp_path, envelope["intent_id"]
        ),
    )


def test_submit_loss_reconcile_reads_only():
    from brain.fabric_inference_client import FabricInferenceClient, EffectUnknown, FabricUnavailable
    calls = []
    async def tool(name, arguments):
        calls.append((name, arguments))
        if name == 'submit_service_intent': raise TimeoutError('private transport detail')
        return {'ok': False, 'status':'refused', 'error': {'code':'not_found'}}
    async def run():
        client = FabricInferenceClient(tool)
        with pytest.raises(EffectUnknown) as error:
            await client.submit('stable-operation', 'Read supplied data')
        assert error.value.operation_key == 'stable-operation'
        assert 'private' not in str(error.value)
        with pytest.raises(FabricUnavailable):
            await client.reconcile('stable-operation')
    asyncio.run(run())
    assert [name for name, _ in calls] == ['submit_service_intent', 'service_intent_status']
    assert all(args['operation_key'] == 'stable-operation' for _, args in calls)


def test_submit_cancellation_is_effect_unknown_not_replayable():
    from brain.fabric_inference_client import FabricInferenceClient, EffectUnknown
    calls = []
    async def tool(name, arguments):
        calls.append((name, arguments))
        raise asyncio.CancelledError()
    async def run():
        with pytest.raises(EffectUnknown) as error:
            await FabricInferenceClient(tool).submit(
                'cancelled-operation', 'Read supplied data')
        assert error.value.operation_key == 'cancelled-operation'
    asyncio.run(run())
    assert [name for name, _ in calls] == ['submit_service_intent']


def result(selection):
    from control_plane.executive_orchestration_result import canonical_digest
    role_result = {'answer': 'observed'}
    return {'schema':'mastermind.executive_mcp_result.v1', 'tool':'executive_fabric', 'ok':True,
        'server_version':'fixture', 'mode':'read_only', 'generated_at':'fixture', 'grounding':{}, 'error':None,
        'bounded':[], 'degraded':[], 'data':{'schema':'mastermind.fabric_role_result_view.v1',
        'selection':selection, 'availability':'AVAILABLE', 'content_complete':True,
        'role':'aggregation', 'acceptance':'NOT_PROJECTED', 'role_result_digest':canonical_digest(role_result),
        'review':None, 'counts':{'findings':None, 'next_actions':0},
        'execution_status':'COMPLETED', 'omitted':[],
        'generation':{'schema':'mastermind.runtime_read_observation.v1', 'state':'SAME',
            'source_identity':'a'*32, 'before':1, 'after':1},
        'content':{'role_result':role_result, 'summary':'done', 'next_actions':[]}}}


@pytest.mark.parametrize('fault', ['none', 'attempt', 'digest', 'root', 'job', 'partial', 'generation',
    'bounded', 'unavailable', 'review', 'work', 'plan', 'repair', 'acceptance', 'extra', 'missing',
    'review-block', 'counts', 'source', 'generation-extra', 'omitted', 'execution', 'role-digest', 'over-budget'])
def test_result_exactness(fault):
    from control_plane.executive_inference_contract import validate_result
    selection = dict(root_job_id='JOB-1', job_id='JOB-1', attempt_id='ATT-'+'a'*32, result_envelope_digest='b'*64)
    response = result(dict(selection))
    data = response['data']
    if fault in ('attempt','digest','root','job'):
        data['selection'][{'attempt':'attempt_id','digest':'result_envelope_digest','root':'root_job_id','job':'job_id'}[fault]] = 'foreign'
    if fault == 'partial': data['content_complete'] = False
    if fault == 'generation': data['generation']['after'] = 2
    if fault == 'bounded': response['bounded'] = ['content']
    if fault == 'unavailable': data['availability'] = 'UNAVAILABLE'
    if fault in ('review', 'work', 'plan', 'repair'): data['role'] = fault
    if fault == 'acceptance': data['acceptance'] = 'ACCEPTED'
    if fault == 'extra': data['extra'] = 'injected'
    if fault == 'missing': del data['acceptance']
    if fault == 'review-block': data['review'] = {}
    if fault == 'counts': data['counts']['next_actions'] = 1
    if fault == 'source': data['generation']['source_identity'] = None
    if fault == 'generation-extra': data['generation']['extra'] = True
    if fault == 'omitted': data['omitted'] = ['summary']
    if fault == 'execution': data['execution_status'] = 'RUNNING'
    if fault == 'role-digest': data['role_result_digest'] = 'c'*64
    if fault == 'over-budget': data['content']['summary'] = 'x' * (256 * 1024)
    if fault == 'none':
        value = validate_result(response, selection)
        assert value == data and value is not data
        assert value['acceptance'] == 'NOT_PROJECTED'
    else:
        with pytest.raises(ValueError): validate_result(response, selection)


def test_review_child_cannot_be_terminal_service_answer():
    """Regression: old validator accepted this matching complete review child."""
    from control_plane.executive_inference_contract import validate_result
    child = dict(root_job_id='JOB-1', job_id='JOB-2', attempt_id='ATT-'+'a'*32, result_envelope_digest='b'*64)
    value = result(child)
    value['data']['role'] = 'review'
    value['data']['review'] = {'verdict':'PASS', 'reviewed_job_id':'JOB-3',
        'reviewed_attempt_id':'ATT-'+'c'*32, 'reviewed_result_digest':'d'*64,
        'latest_revision_currentness':'UNPROVEN'}
    value['data']['counts']['findings'] = {'total':0, 'blocking':0, 'warning':0, 'info':0}
    with pytest.raises(ValueError): validate_result(value, child)


@pytest.mark.parametrize('fault', ['none', 'null', 'child', 'foreign', 'validated', 'role', 'extra'])
def test_client_discovers_only_operation_bound_terminal_ref(tmp_path, fault):
    from brain.fabric_inference_client import FabricInferenceClient, FabricUnavailable
    from control_plane.executive_inference_contract import intent_id
    receipt = service_receipt(tmp_path, 'stable-operation', 'Original research')
    selection = dict(root_job_id=receipt['job_id'], job_id=receipt['job_id'],
        attempt_id='ATT-'+'a'*32, result_envelope_digest='b'*64)
    ref = dict(selection, orchestration_role='aggregation', validation='UNVALIDATED')
    if fault == 'null': ref = None
    if fault == 'child': ref['job_id'] = 'JOB-999'
    if fault == 'foreign': ref.update(root_job_id='JOB-999', job_id='JOB-999')
    if fault == 'validated': ref['validation'] = 'VALIDATED'
    if fault == 'role': ref['orchestration_role'] = 'review'
    if fault == 'extra': ref['extra'] = True
    calls = []
    async def tool(name, args):
        calls.append(name)
        if name == 'service_intent_status':
            assert args == {'operation_key':'stable-operation'}
            return {'ok':True, 'status':'accepted', 'request_ref':intent_id('stable-operation'),
                    'receipt':receipt, 'terminal_result_ref':ref}
        assert name == 'executive_fabric' and args == dict(selection, view='result', operation_key='stable-operation')
        return result(selection)
    async def run():
        client = FabricInferenceClient(tool)
        if fault == 'none':
            answer = await client.result('stable-operation')
            assert answer['role'] == 'aggregation' and answer['acceptance'] == 'NOT_PROJECTED'
        else:
            with pytest.raises(FabricUnavailable): await client.result('stable-operation')
    asyncio.run(run())
    assert calls == (['service_intent_status', 'executive_fabric'] if fault == 'none' else ['service_intent_status'])


def test_no_direct_provider_import_or_fallback():
    module = importlib.import_module('brain.fabric_inference_client')
    source = Path(module.__file__).read_text()
    tree = ast.parse(source)
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
    assert set(imports) <= {'__future__', 'asyncio', 'collections.abc', 'typing',
        'control_plane.executive_inference_contract'}
    for forbidden in ('cli_bridge', 'provider_waterfall', 'anthropic', 'subprocess', 'codex'):
        assert forbidden not in source.lower()


def test_explicit_conflict_is_not_transport_uncertainty():
    from brain.fabric_inference_client import FabricInferenceClient, FabricConflict
    from control_plane.executive_inference_contract import intent_id
    async def tool(name, args):
        return {'ok':False, 'status':'conflict', 'request_ref':intent_id(args['operation_key']),
                'error':{'code':'operation_conflict'}}
    with pytest.raises(FabricConflict):
        asyncio.run(FabricInferenceClient(tool).submit('stable-operation', 'Different research'))


def test_receipt_must_match_submitted_semantics(tmp_path):
    from brain.fabric_inference_client import FabricInferenceClient, EffectUnknown
    from control_plane.executive_inference_contract import intent_id
    receipt = service_receipt(tmp_path, 'stable-operation', 'Original research')
    async def tool(name, args):
        return {'ok':True, 'status':'accepted', 'request_ref':intent_id(args['operation_key']), 'receipt':receipt}
    with pytest.raises(EffectUnknown):
        asyncio.run(FabricInferenceClient(tool).submit('stable-operation', 'Different research'))


@pytest.mark.parametrize('fault', ['none', 'null', 'child-only', 'duplicate', 'wrong-root',
    'truncated', 'generation', 'extra', 'validated'])
def test_future_resolver_uses_existing_canonical_reference_index(tmp_path, fault):
    from types import SimpleNamespace
    from control_plane import fabric_job_view as owner
    from control_plane.executive_inference_contract import terminal_result_ref_from_index
    operation = 'stable-operation'
    receipt = service_receipt(tmp_path, operation, 'Read research')
    root = receipt['job_id']
    attempt = 'ATT-'+'a'*32
    terminal = dict(schema_version=owner.ORCHESTRATION_TERMINAL_RECEIPT_SCHEMA,
        status='COMPLETED', job_id=root, attempt_id=attempt, orchestration_role='aggregation',
        execution_mode='OPERATOR_HARNESS', result_envelope_digest='b'*64,
        result_seal_command_id='fixture-seal', result_evidence={}, result_envelope={},
        artifact_receipt_digest='c'*64, validation_receipt_digest='d'*64,
        effective_grant_digest='e'*64, terminal_evidence_digest='f'*64)
    # Pure navigation fixture only: it does not turn this service Job into a root.
    mode = terminal['execution_mode']
    job = SimpleNamespace(job_id=root, root_job_id=root, current_attempt_id=attempt,
        orchestration_role='aggregation', status='COMPLETED', result=terminal)
    attempt_row = SimpleNamespace(attempt_id=attempt, job_id=root, status='COMPLETED',
        execution_mode=mode, result=terminal)
    generation = result({})['data']['generation']
    snapshot = SimpleNamespace(root_job_id=root, jobs=[job], attempts=[attempt_row],
        snapshot_digest='c'*64, jobs_truncated=False, attempts_truncated_job_ids=[])
    index = owner.compose_fabric_result_reference_index(snapshot, generation)
    assert index['schema'] == owner.RESULT_REFERENCE_INDEX_SCHEMA
    assert len(index['refs']) == 1
    expected = dict(index['refs'][0])
    if fault == 'null': index.update(refs=[], absent_job_ids=[root])
    if fault == 'child-only': index['refs'][0].update(job_id='JOB-999', orchestration_role='review')
    if fault == 'duplicate': index['refs'].append(dict(expected))
    if fault == 'wrong-root': index['root_job_id'] = 'JOB-999'
    if fault == 'truncated': index['truncated'] = True
    if fault == 'generation': index['generation']['state'] = 'UNKNOWN'
    if fault == 'extra': index['extra'] = True
    if fault == 'validated': index['refs'][0]['validation'] = 'VALIDATED'
    if fault in ('none', 'null', 'child-only'):
        assert terminal_result_ref_from_index(index, receipt, operation) == (expected if fault == 'none' else None)
    else:
        with pytest.raises(ValueError): terminal_result_ref_from_index(index, receipt, operation)


def test_actual_canonical_aggregation_projection_is_accepted(tmp_path, monkeypatch):
    from tests import test_fabric_result_projection as fixtures
    from control_plane import fabric_result_projection as projector
    from control_plane.executive_inference_contract import validate_result
    original = projector.project_fabric_role_result
    seen = []
    def checked(*args, **kwargs):
        projection = original(*args, **kwargs)
        response = result(projection.complete['selection'])
        response['data'] = projection.complete
        answer = validate_result(response, projection.complete['selection'])
        assert answer['acceptance'] == 'NOT_PROJECTED'
        seen.append(answer)
        return projection
    monkeypatch.setattr(projector, 'project_fabric_role_result', checked)
    fixtures.test_actual_aggregation_root_completion_projects(tmp_path, monkeypatch)
    assert len(seen) == 1


from tests.test_fabric_result_projection import bound_max_chain  # noqa: E402,F401


def test_real_completed_review_child_is_rejected(bound_max_chain):
    from tests.test_fabric_result_projection import _select_bound
    from control_plane.fabric_result_projection import project_fabric_role_result
    from control_plane.executive_inference_contract import validate_result
    _, root, _, completions, reader = bound_max_chain
    completion = completions[-1]
    snapshot, generation = _select_bound(reader, root.job_id, completion)
    data = project_fabric_role_result(snapshot, generation).complete
    assert data['role'] == 'review' and data['execution_status'] == 'COMPLETED'
    assert data['availability'] == 'AVAILABLE' and data['content_complete'] is True
    assert data['generation']['state'] == 'SAME' and data['omitted'] == []
    assert data['selection']['root_job_id'] != data['selection']['job_id']
    value = result(data['selection'])
    value['data'] = data
    # Every old predicate holds: matching selection, complete AVAILABLE/SAME
    # content, no bounds/degradation. The role/root repair is discriminating.
    with pytest.raises(ValueError): validate_result(value, data['selection'])
