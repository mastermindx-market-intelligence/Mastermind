"""Manual cross-PR source-only OAuth App -> Unix -> Runtime -> Bot candidate canary.

This is a hermetic synthetic-terminal experiment, NOT a production model
execution, provider result authenticity, installed OAuth or trading acceptance.

Not auto-collected by CI because the service PR is not merged. Run only in an
exactly hashed combined-source export containing the original service and Bot
owner sources. No production profile or secret is used.
"""
import asyncio
import dataclasses
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tests.test_vps_inference_installed_socket import source_harness, short_socket_root, synthetic_distinct_service_peer
from tests.test_vps_inference_service import (
    rsa_key, setup_app, call, GROUND, service_request
)
from tests.test_vps_inference_runtime_projection import qualified_reader, cleanup
from tests.test_vps_inference_runtime_read import qualified_attempt
from tests.test_decision_research import fixture
from brain.decision_research import prepare_context, inference_request
from brain.decision_research_result import read_original_candidate_claims
from brain.fabric_inference_client import FabricInferenceClient, FabricUnavailable
from control_plane import executive_inference_io as io


@pytest.mark.usefixtures('synthetic_distinct_service_peer')
@pytest.mark.parametrize('purpose', ['extract', 'compare'])
def test_original_bot_candidate_to_authenticated_socket_and_back(
    purpose, rsa_key, tmp_path, short_socket_root
):
    original_context=prepare_context(
        fixture(rows=2),
        question="Inspect reported source facts and disclose contrary evidence.",
        section_ids=['book_truth','risk_truth'],purpose=purpose,
    )
    wire=inference_request(original_context,task_aware=True,max_output_chars=2000)
    operation='bot-full-socket-'+purpose
    objective='Inspect exactly the preserved Bot evidence and return citations.'
    app,token,_=setup_app(rsa_key,tmp_path)
    async def exercise():
        service,client,calls=await source_harness(tmp_path,short_socket_root,armed=True)
        binding=None
        try:
            app.settings=dataclasses.replace(app.settings,
                executive=dataclasses.replace(app.settings.executive,
                    ceo_ingress_socket_path=service._ceo_ingress_socket_path))
            submitted=await call(app,token,'submit_service_intent',
                service_request(operation,objective,request=wire))
            assert submitted.status_code==200,submitted.text
            receipt=submitted.json()['receipt']
            job=service.runtime.jobs.get_job(receipt['job_id'])
            assert job.constraints['risk']==('routine' if purpose=='extract' else 'elevated')
            assert not service.runtime.attempts.list_attempts(job_id=job.job_id)
            assert job.status.value=='QUEUED'

            async def admitted_app_read(name,args):
                return (await call(app,token,name,args)).json()
            # An admitted Job is NOT a returned answer. The actual App/socket
            # remains read-only, never starts another Job or invents a result.
            with pytest.raises(FabricUnavailable):
                await read_original_candidate_claims(
                    FabricInferenceClient(admitted_app_read),
                    original_context=original_context,
                    original_inference_request=wire,
                    operation_key=operation,objective=objective,
                    original_operation_ref=receipt['intent_id'],
                    original_request_fingerprint=receipt['fingerprint'],
                )
            assert len(service.runtime.jobs.list_jobs())==1
            assert not service.runtime.attempts.list_attempts(job_id=job.job_id)

            payload={
                'schema':'mastermind.bot_research_claims.v1',
                'context_id':original_context['context_id'],
                'snapshot_id':original_context['snapshot_id'],
                'claims':[{
                    'claim_id':'synthetic-cited-1',
                    'statement':'A synthetic preserved account line reports cash.',
                    'kind':'OBSERVATION','stance':'NEUTRAL','uncertainty':'UNQUANTIFIED',
                    'evidence_refs':['book_truth:0'],'contrary_refs':['risk_truth:0'],
                    'falsifier':'Independent corrected account evidence refutes the line.',
                }],
                'unknowns':['All uncovered domains and market outcomes remain unknown.'],
                'coverage_ack':{
                    'selection_complete':original_context['selection_complete'],
                    'selected_rows':sum(s['selected_rows'] for s in original_context['sections'].values()),
                    'unselected_domains':original_context['unselected_domains'],
                },
            }
            answer=json.dumps(payload,sort_keys=True)
            # No provider or Supervisor exists here. The temporary DB terminal
            # row simulates ONLY the later canonical read path.
            from control_plane.model_router import ModelRouter
            router=ModelRouter.load()
            alias='fast.research' if purpose=='extract' else 'standard.research'
            model=router.resolve_model_alias(alias)
            metadata={
                'adapter_id':model.adapter_id,'model_alias':model.model_alias,
                'provider_alias':model.provider_alias,'routing_policy_version':router.policy_version,
                'execution_profile_id':model.execution_profile_id,
                'execution_profile_digest':model.execution_profile_digest,
                'capability_policy_version':model.capability_policy_version,
                'capability_policy_digest':model.capability_policy_digest,
            }
            service.runtime.workers.register_worker('synthetic-worker',
                provider=model.provider_alias,account_label='synthetic-no-paid-provider',
                worker_type=model.adapter_id,capabilities=list(model.capabilities),
                quota_classes={'fixture':{'provider':model.provider_alias,
                    'model':model.model,'effort':model.effort,'cost_class':model.cost_class,
                    'capabilities':list(model.capabilities),'metadata':metadata}})
            lease=service.runtime.broker.claim(job.job_id,lease_owner='synthetic-fixture')
            assert lease is not None
            attempt=lease.attempt
            worker_result={
                'schema_version':io.WORKER_RESULT_SCHEMA,'job_id':job.job_id,
                'run_id':attempt.attempt_id,'worker_id':attempt.worker_id,
                'status':'COMPLETED','answer':answer,
            }
            ref=io.result_reference(job_id=job.job_id,
                attempt_id=attempt.attempt_id,worker_id=attempt.worker_id,
                result_sha256='a'*64,
                content_sha256=hashlib.sha256(io.canonical_bytes(worker_result)).hexdigest())
            doc=io.result_document(reference=ref,result=worker_result,
                raw_result_sha256='a'*64,max_output_chars=2000)
            encoded=io.canonical_bytes(doc).decode()
            with service.runtime.store.transaction() as db:
                db.execute("UPDATE attempts SET status='COMPLETED',result_json=?,exit_code=0,"
                           "lease_token=NULL,finished_at_ms=1000,updated_at_ms=1000 WHERE attempt_id=?",
                           (encoded,attempt.attempt_id))
                db.execute("UPDATE jobs SET status='COMPLETED',result_json=? WHERE job_id=?",
                           (encoded,job.job_id))
            read_runtime,binding=qualified_reader(service.runtime,service.config.runtime_root.parent)
            service._ceo_ingress_inference_binding=dataclasses.replace(
                service._ceo_ingress_inference_binding,result_read_runtime_factory=lambda _:read_runtime)
            calls_seen=[]
            async def authenticated_existing_app(name,args):
                calls_seen.append(name)
                response=await call(app,token,name,args)
                return response.json()
            candidate=await read_original_candidate_claims(
                FabricInferenceClient(authenticated_existing_app),
                original_context=original_context,original_inference_request=wire,
                operation_key=operation,objective=objective,
                original_operation_ref=receipt['intent_id'],
                original_request_fingerprint=receipt['fingerprint'],
            )
            assert calls_seen==['service_intent_status','executive_fabric']
            assert candidate['candidate_only'] is True
            assert candidate['claims'][0]['evidence_refs']==['book_truth:0']
            assert candidate['claims'][0]['contrary_refs']==['risk_truth:0']
            assert candidate['authority']=={'write_permitted':False,'execution_authority':False,
                                           'numeric_target_authority':False}
            assert candidate['snapshot_id']==original_context['snapshot_id']
            assert candidate['artifact_independence']=='NOT_ESTABLISHED'
            assert candidate['coverage']['snapshot_coverage']=='PARTIAL'
            return candidate['claim_set_id']
        finally:
            if binding is not None: cleanup(binding)
            await service.close()
    result=asyncio.run(exercise())
    assert result.startswith('sha256:')
