"""Direct receipt DATA mapping; genuine lost-admission Job proof is joined elsewhere."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from control_plane import ceo_intent, ceo_request
from control_plane.executive_runtime import JobStatus
from integrations.executive_mcp.schemas import result_envelope, ServerMode
from integrations.mastermind_executive_app.gateway import (
    CeoIngressClient, CeoIngressResponse, CeoIngressReadGateway,
    WebCeoV2CeoIngressReadGateway, TRANSPORT_SENT_OK,
)


def native_receipt(*,schema=ceo_intent.RECEIPT_SCHEMA_DIRECT,with_work=True):
    job=SimpleNamespace(job_id='JOB-17',status=JobStatus.QUEUED,
        requested_authorities=['READ','RESEARCH'],authority_policy_hash='a'*64,authority_level='A1')
    intent=dict(schema=ceo_intent.INTENT_SCHEMA_DIRECT,intent_id=ceo_request.automated_intent_id(
        ceo_request.app_request_ref('direct-status-loss')),
        grounding=dict(mastermind_sha='b'*40,macro_sha='c'*40))
    if with_work:intent['workstream']='WS:H2'
    receipt=ceo_intent.build_receipt(job,intent=intent,fingerprint='d'*64,duplicate=True,created_at_ms=123)
    receipt['schema']=schema
    return receipt


class DirectStatusReceiptTests(unittest.TestCase):
    def valid(self,value):
        return CeoIngressReadGateway._valid_intent_receipt(value,arguments={'intent_id':native_receipt()['intent_id']})

    def test_real_receipt_builder_direct_schema_and_work_ref_are_preserved(self):
        value=native_receipt()
        self.assertTrue(self.valid(value))
        self.assertEqual(value['schema'],ceo_intent.RECEIPT_SCHEMA_DIRECT)
        self.assertEqual(value['work_ref'],'WS:H2')
        self.assertFalse(value['dispatched'])  # Admission receipt is not execution evidence.
        self.assertTrue(value['duplicate'])
        self.assertTrue(self.valid(dict(value,grounding={**value['grounding'],'boot_packet_schema':'mastermind.ceo_boot_packet.v1'})))

    def test_direct_requires_closed_keys_and_original_work_ref_shape(self):
        for work_ref in (None,'','WS:','WS:../../foreign','WS:H2\n','foreign','WS:'+'a'*80,True):
            with self.subTest(work_ref=work_ref):self.assertFalse(self.valid(dict(native_receipt(),work_ref=work_ref)))
        missing=native_receipt();missing.pop('work_ref')
        self.assertFalse(self.valid(missing))
        for key in ('worker_id','source_digest','principal_scope','execution_access','role_result'):
            with self.subTest(key=key):self.assertFalse(self.valid(dict(native_receipt(),**{key:'DO_NOT_RETURN'})))

    def test_wrong_intent_job_fingerprint_time_and_status_refuse(self):
        for changes in (dict(intent_id='auto-'+'e'*32),dict(job_id='JOB-other'),dict(job_id=True),
                        dict(fingerprint='D'*64),dict(created_at_ms=True),dict(status={}),
                        dict(status='PRODUCT_ACCEPTED'),dict(accepted=False),dict(dispatched=True)):
            with self.subTest(changes=changes):self.assertFalse(self.valid(dict(native_receipt(),**changes)))

    def test_direct_authority_and_malformed_source_cannot_pass_as_native(self):
        original=native_receipt()
        for authorities in ([],['READ'],['READ','RESEARCH','READ'],['READ','WRITE_BRANCH']):
            with self.subTest(authorities=authorities):
                value=copy.deepcopy(original);value['authority']['requested']=authorities
                self.assertFalse(self.valid(value))
        for grounding in ({'mastermind_sha':'B'*40,'macro_sha':'c'*40},
                          {'mastermind_sha':'b'*39,'macro_sha':'c'*40},
                          {'macro_sha':'c'*40},
                          {**original['grounding'],'source':'DO_NOT_RETURN'},
                          {**original['grounding'],'boot_packet_schema':None}):
            with self.subTest(keys=list(grounding)):
                self.assertFalse(self.valid(dict(original,grounding=grounding)))

    def test_existing_v2_optional_work_ref_contract_is_unchanged(self):
        value=native_receipt(schema=ceo_intent.RECEIPT_SCHEMA_V2,with_work=False)
        self.assertTrue(self.valid(value))
        self.assertTrue(self.valid(dict(value,work_ref=None)))
        self.assertTrue(self.valid(dict(value,work_ref='WS:H2')))


class DirectStatusGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def project(self,value):
        client=CeoIngressClient();gateway=WebCeoV2CeoIngressReadGateway('/fixture/ceo.sock',client)
        wrapped=result_envelope('ceo_intent_status',mode=ServerMode.READONLY,
            generated_at='2026-10-24T00:00:00Z',data=value,
            grounding={'runtime':'readonly:installed-executive-runtime','source':'inert-status-owner'})
        wrapped['server_version']=gateway._result_server_version()
        with patch.object(client,'send_frame',new=AsyncMock(return_value=CeoIngressResponse(
                transport=TRANSPORT_SENT_OK,ok=True,result=wrapped))) as send:
            result=await gateway.call('ceo_intent_status',{'intent_id':native_receipt()['intent_id']})
        self.assertEqual(send.await_count,1)
        self.assertEqual(send.await_args.args[1]['tool'],'ceo_intent_status')
        self.assertEqual(send.await_args.args[1]['arguments'],{'intent_id':native_receipt()['intent_id']})
        return result

    async def test_actual_existing_read_gateway_returns_native_receipt_instead_of_data_none(self):
        value=native_receipt();result=await self.project(value)
        self.assertTrue(result['ok']);self.assertEqual(result['data'],value)

    async def test_malformed_native_receipt_is_withheld_without_resubmit_or_selector(self):
        value=dict(native_receipt(),work_ref=None,secret='DO_NOT_RETURN')
        result=await self.project(value)
        self.assertFalse(result['ok']);self.assertIsNone(result['data'])
        self.assertNotIn('DO_NOT_RETURN',str(result))


if __name__=='__main__':unittest.main()
