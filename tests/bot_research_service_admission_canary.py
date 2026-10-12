"""Cross-PR source admission canary, not an installed service or worker proof.

Runs the real Bot producer, recovered service client, canonical ingress and
SQLite Runtime from an explicitly exported integration tree. The authenticated
transport/host grant is an in-process fixture. No provider or HTTP server runs.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import sys
import tempfile

BOT_HEAD = '67d7c2a8799ddab24146ab610f22e40af8d1c355'
SERVICE_HEAD = '09719bb76d19cfd8bccb28a8759540acbafb0c81'
INTEGRATION_TREE = '3540d69ab01a0a3bae3ffc19f10d7191c95581a9'


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit('Provide the explicitly exported source integration directory')
    root = Path(sys.argv[1]).resolve()
    provenance = json.loads((root / '.source-proof.json').read_text())
    assert provenance['bot_head'] == BOT_HEAD and provenance['service_head'] == SERVICE_HEAD
    assert provenance['integration_tree'] == INTEGRATION_TREE
    for file, digest in provenance['files'].items():
        assert hashlib.sha256((root / file).read_bytes()).hexdigest() == digest, file
    sys.path[:0] = [str(root), str(root / 'tests')]

    from brain import decision_research as research
    from brain.fabric_inference_client import FabricInferenceClient, FabricConflict, EffectUnknown, FabricUnavailable
    from control_plane import executive_inference_ingress as service
    from control_plane import executive_service_principal as esp
    from control_plane.executive_ceo_ingress import CeoIngressError
    from control_plane.executive_inference_contract import intent_id
    from control_plane.executive_inference_execution import build_execution_binding
    from control_plane.executive_runtime import Runtime
    from portfolio import decision_snapshot_contracts as contracts
    from test_decision_research import fixture

    for module in [research, service, esp, contracts]:
        assert Path(module.__file__).resolve().is_relative_to(root)
    snapshot = fixture(rows=12)
    for section in snapshot['sections'].values():
        for row in section['rows']:
            row['text'] = 'SYNTHETIC SOURCE CANARY ONLY; no real portfolio. ' * 35
    snapshot.pop('snapshot_id')
    snapshot = contracts.seal_snapshot(snapshot)
    context = research.prepare_context(snapshot, question='Identify reported evidence and uncertainty; do not size a trade.',
        section_ids=['book_truth', 'risk_truth'], purpose='compare', rows_per_section=6, max_request_bytes=32 * 1024)
    wire = research.inference_request(context, task_aware=True)
    assert wire['task_kind'] == 'comparative_analysis'
    assert len(wire['input_text']) > 8192
    observations = []
    grounding = {'mastermind_sha': SERVICE_HEAD, 'macro_sha': '2' * 40,
                 'boot_packet_schema': 'mastermind.ceo_boot_packet.v1'}

    class Grounding:
        def observe(self):
            return grounding

    with tempfile.TemporaryDirectory(prefix='mmx-bot-service-source-canary-') as directory:
        temporary = Path(directory)
        runtime = Runtime.at(temporary / 'runtime')
        calls = []; grants = []; bindings = []
        mode = {'drop_reply': False, 'tamper_reply': False, 'armed': True, 'binding_request': None}

        def guard(envelope):
            assert mode['armed'], 'no fresh admission while disarmed'
            grants.append(envelope['intent_id'])

        def binding(identity):
            assert mode['armed'], 'duplicate/status must not rebind routing'
            bindings.append(identity)
            return build_execution_binding(intent_id=identity, workspace_root=temporary / 'workspaces',
                base_sha=SERVICE_HEAD, eligible_quota_classes=('fixture-source-only',),
                inference_request=mode['binding_request'])

        async def authenticated_transport_fixture(tool, arguments):
            nonlocal runtime
            calls.append(tool)
            assert tool in {'submit_service_intent', 'service_intent_status'}, 'no worker-result read is admitted'
            operation = arguments['operation_key']
            common = dict(runtime=runtime, grounding_provider=Grounding(), workspace_root=temporary / 'workspaces',
                          admission_guard=guard, execution_binding_provider=binding)
            if tool == 'submit_service_intent':
                mode['binding_request'] = arguments['inference_request']
                try:
                    receipt = await service.handle_frame(dict(schema=service.SUBMIT_SCHEMA,
                        request=arguments, observed_grounding=grounding), **common)
                except CeoIngressError as exc:
                    if exc.code == 'operation_conflict':
                        return {'ok': False, 'status': 'conflict', 'request_ref': intent_id(operation),
                                'error': {'code': 'operation_conflict'}}
                    raise
                if mode['drop_reply']:
                    raise TimeoutError('fixture response lost after durable admission')
                if mode['tamper_reply']:
                    receipt = dict(receipt, fingerprint='f' * 64)
                return {'ok': True, 'status': 'accepted', 'request_ref': intent_id(operation), 'receipt': receipt}
            response = await service.handle_frame(dict(schema=service.STATUS_SCHEMA, operation_key=operation), **common)
            return {'ok': True, 'status': 'accepted', 'request_ref': intent_id(operation), **response}

        async def exercise():
            nonlocal runtime
            client = FabricInferenceClient(authenticated_transport_fixture)
            first = await client.submit('bot-source-canary', 'Inspect one preserved Bot research context.', wire)
            job = runtime.jobs.get_job(first['job_id'])
            stamp = esp.durable_provenance(runtime, job.job_id)['provenance']
            assert stamp['inference_request'] == wire
            assert json.loads(stamp['inference_request']['input_text'])['snapshot_id'] == snapshot['snapshot_id']
            assert job.objective == 'Inspect one preserved Bot research context.'
            assert not job.allowed_write_paths and not job.validation_commands
            assert not runtime.attempts.list_attempts(job_id=job.job_id)
            observations.append({'case': 'prepared_context_reaches_original_job_losslessly', 'passed': True,
                'request_bytes': len(contracts.canonical_json_bytes(wire)), 'job_id': job.job_id,
                'snapshot_id': snapshot['snapshot_id'], 'context_id': context['context_id'], 'dispatch': False})

            mode['armed'] = False
            grant_count, binding_count = len(grants), len(bindings)
            duplicate = await client.submit('bot-source-canary', job.objective, wire)
            assert duplicate['job_id'] == job.job_id and duplicate['duplicate'] is True
            assert (len(grants), len(bindings)) == (grant_count, binding_count)
            assert len(runtime.jobs.list_jobs()) == 1
            observations.append({'case': 'exact_duplicate_reconciles_while_disarmed_without_new_route', 'passed': True})

            changed = research.prepare_context(snapshot, question='A changed question under the same operation must conflict.',
                section_ids=['book_truth', 'risk_truth'], purpose='compare', max_request_bytes=32 * 1024)
            try:
                await client.submit('bot-source-canary', job.objective, research.inference_request(changed, task_aware=True))
            except FabricConflict:
                pass
            else:
                raise AssertionError('changed context did not conflict')
            assert len(runtime.jobs.list_jobs()) == 1
            assert esp.durable_provenance(runtime, job.job_id)['provenance']['inference_request'] == wire
            observations.append({'case': 'changed_context_same_operation_cannot_overwrite_original', 'passed': True})

            runtime = Runtime.at(temporary / 'runtime')
            resumed = FabricInferenceClient(authenticated_transport_fixture)
            before = len(calls)
            state = await resumed.reconcile('bot-source-canary')
            assert state['receipt']['job_id'] == job.job_id and state['terminal_result_ref'] is None
            assert calls[before:] == ['service_intent_status']
            try:
                await resumed.result('bot-source-canary')
            except FabricUnavailable:
                pass
            else:
                raise AssertionError('queued job was presented as a finished answer')
            assert 'executive_fabric' not in calls
            observations.append({'case': 'restart_reads_original_receipt_and_refuses_unfinished_answer', 'passed': True})

            mode['armed'] = True; mode['drop_reply'] = True
            try:
                await resumed.submit('bot-lost-reply-canary', job.objective, wire)
            except EffectUnknown as exc:
                assert exc.operation_key == 'bot-lost-reply-canary'
            else:
                raise AssertionError('lost committed reply was made retryable')
            mode['armed'] = False; mode['drop_reply'] = False
            runtime = Runtime.at(temporary / 'runtime')
            recovered = FabricInferenceClient(authenticated_transport_fixture)
            before = len(calls)
            recovered_state = await recovered.reconcile('bot-lost-reply-canary')
            assert recovered_state['receipt']['job_id'] != job.job_id
            assert len(runtime.jobs.list_jobs()) == 2 and calls[before:] == ['service_intent_status']
            observations.append({'case': 'lost_reply_reconciles_same_durable_operation_without_resubmit', 'passed': True})

            before = len(calls)
            try:
                await recovered.submit('bad-selector-canary', job.objective, dict(wire, provider='forbidden'))
            except ValueError:
                pass
            else:
                raise AssertionError('unknown provider selector was accepted')
            assert len(calls) == before and len(runtime.jobs.list_jobs()) == 2
            observations.append({'case': 'provider_selector_refuses_before_transport', 'passed': True})

            mode['armed'] = True; mode['tamper_reply'] = True
            try:
                await recovered.submit('bot-tampered-receipt', job.objective, wire)
            except EffectUnknown:
                pass
            else:
                raise AssertionError('foreign fingerprint was accepted')
            mode['tamper_reply'] = False; mode['armed'] = False
            state = await recovered.reconcile('bot-tampered-receipt')
            assert state['receipt']['fingerprint'] != 'f' * 64 and len(runtime.jobs.list_jobs()) == 3
            observations.append({'case': 'tampered_reply_is_uncertain_and_exact_status_recovers_receipt', 'passed': True})

            desired = research.work_request(context)
            assert desired.risk == job.constraints['risk'] == 'elevated'
            assert job.constraints['preferred_model_aliases'] == ['standard.research']
            observations.append({'case': 'comparison_task_survives_client_sink_and_canonical_job_route', 'passed': True,
                'capability_state': 'SOURCE_ADMISSION_PROVEN_NOT_PROVIDER_EXECUTED',
                'application_risk': desired.risk, 'service_host_risk': job.constraints['risk'],
                'qualified_tier': job.constraints['preferred_model_aliases']})

            routine = research.prepare_context(snapshot, question='Extract the reported observations.',
                section_ids=['book_truth', 'risk_truth'], purpose='extract')
            mode['armed'] = True
            routine_receipt = await recovered.submit('bot-routine-v2', job.objective,
                research.inference_request(routine, task_aware=True))
            routine_job = runtime.jobs.get_job(routine_receipt['job_id'])
            assert routine_job.constraints['risk'] == 'routine'
            assert routine_job.constraints['preferred_model_aliases'] == ['fast.research', 'standard.research']
            assert not runtime.attempts.list_attempts(job_id=routine_job.job_id)
            observations.append({'case': 'routine_task_retains_economical_first_lawful_tier', 'passed': True,
                'qualified_tier': routine_job.constraints['preferred_model_aliases'], 'dispatch': False})

            prior_jobs = len(runtime.jobs.list_jobs())
            judgment = research.prepare_context(snapshot, question='Adjudicate the conflicting risk observations.',
                section_ids=['book_truth', 'risk_truth'], purpose='adjudicate')
            try:
                await recovered.submit('bot-frontier-refusal', job.objective,
                    research.inference_request(judgment, task_aware=True))
            except EffectUnknown:
                pass
            else:
                raise AssertionError('frontier judgment was silently admitted into the ordinary worker lane')
            assert len(runtime.jobs.list_jobs()) == prior_jobs
            observations.append({'case': 'frontier_judgment_does_not_downgrade_into_ordinary_job', 'passed': True,
                'existing_governed_judgment_path': 'REQUIRED_NOT_PROVEN'})

        asyncio.run(exercise())
    print(json.dumps({'scope': 'Cross-PR source client-to-canonical-admission proof with real temporary SQLite; fixture transport and host grant; no installed auth, provider, worker or production proof',
        'bot_head': BOT_HEAD, 'service_head': SERVICE_HEAD, 'integration_tree': INTEGRATION_TREE,
        'passed': len(observations), 'cases': observations}, indent=2))


if __name__ == '__main__':
    main()
