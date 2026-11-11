"""Actual HTTP authentication and one fixed private correction frame."""
import unittest
from unittest.mock import AsyncMock,patch
from common import direct_native_correction_contract as correction
from integrations.mastermind_executive_app.gateway import CeoIngressResponse,TRANSPORT_SENT_OK,TRANSPORT_SENT_UNKNOWN
from tests import test_direct_native_result_http as fixture

class CorrectionHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixture.DirectResultHttpTests.asyncSetUp
    post=fixture.DirectResultHttpTests.post

    async def test_authenticated_exact_request_transmits_once(self):
        body=dict(self.body,fence_generation=7,operation_key='original-correction')
        reply=correction.receipt(body,'CANCEL_REQUESTED')
        with patch.object(self.client,'send_frame',new=AsyncMock(return_value=CeoIngressResponse(transport=TRANSPORT_SENT_OK,ok=True,result=reply))) as send:
            response=await self.post(correction.PATH,dict(body,operation='request'))
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json(),reply)
        self.assertEqual(send.await_count,1)
        self.assertEqual(send.await_args.args[1]['operation'],'correct')
        self.assertFalse(response.json()['parent_consumed'])

    async def test_lost_response_retains_unknown_and_never_sends_again(self):
        body=dict(self.body,fence_generation=7,operation_key='original-correction',operation='request')
        with patch.object(self.client,'send_frame',new=AsyncMock(return_value=CeoIngressResponse(transport=TRANSPORT_SENT_UNKNOWN))) as send:
            response=await self.post(correction.PATH,body)
        self.assertEqual(response.status_code,202)
        self.assertEqual(response.json()['error']['code'],'effect_unknown')
        self.assertEqual(send.await_count,1)

    async def test_no_auth_and_extra_target_cannot_enter_private_owner(self):
        body=dict(self.body,fence_generation=7,operation_key='original-correction',operation='request')
        with patch.object(self.client,'send_frame',new=AsyncMock()) as send:
            unauth=await self.post(correction.PATH,body,headers={'host':'mcp.mastermind-x.com'})
            malformed=await self.post(correction.PATH,dict(body,worker_id='other-worker'))
        self.assertIn(unauth.status_code,(401,403))
        self.assertGreaterEqual(malformed.status_code,400)
        self.assertEqual(send.await_count,0)
