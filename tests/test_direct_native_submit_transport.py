"""Closed direct-submit transport tests; no socket/Runtime/provider effects."""
import asyncio
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from control_plane import ceo_request, executive_ceo_ingress as ingress
from control_plane.direct_native_execution import SUBMIT_SCHEMA
from integrations.mastermind_executive_app.gateway import (
    CeoIngressClient, TRANSPORT_NOT_SENT, TRANSPORT_SENT_OK, TRANSPORT_SENT_UNKNOWN,
)
from tests.test_direct_native_result_transport import Writer


class DirectSubmitTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        high=ceo_request.normalize_high_level_request(dict(operation_key='direct-transport-test',
            objective='Read the admitted research commission.',department='executive-infrastructure',
            priority=0,execution_profile='native_research_only',workstream='WS:H2',attempt_limit=1))
        self.frame=dict(schema=SUBMIT_SCHEMA,
            request_ref=ceo_request.app_request_ref(high.pop('operation_key')),
            observed_grounding=dict(mastermind_sha='a'*40,macro_sha='b'*40,
                boot_packet_schema=ingress.BOOT_PACKET_SCHEMA),
            request=high,principal_scope='c'*64)

    async def exchange(self, raw, *, frame=None):
        reader=asyncio.StreamReader();reader.feed_data(raw);reader.feed_eof()
        writer=Writer();client=CeoIngressClient()
        with patch('asyncio.open_unix_connection',new=AsyncMock(return_value=(reader,writer))) as opened:
            response=await client.send_frame(Path('/fixture/ceo-ingress.sock'),self.frame if frame is None else frame)
        return response,writer,opened.await_count

    async def test_actual_canonical_submit_frame_serialized_once_without_private_selectors(self):
        raw=b'{"ok":true,"result":{"schema":"test-only-transport-object","job_id":"JOB-h2"}}\n'
        response,writer,calls=await self.exchange(raw)
        self.assertEqual(response.transport,TRANSPORT_SENT_OK)
        self.assertEqual(calls,1);self.assertEqual(len(writer.frames),1)
        expected=json.dumps(self.frame,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()+b'\n'
        self.assertEqual(writer.frames,[expected])
        self.assertEqual(set(json.loads(writer.frames[0])),{'schema','request_ref','observed_grounding','request','principal_scope'})
        self.assertNotIn('operation_key',json.loads(writer.frames[0])['request'])
        self.assertTrue(writer.closed)

    async def test_exact_keys_refuse_caller_execution_host_or_account_selectors_before_connect(self):
        for key in ('worker_id','provider','account_label','host_ref','execution_access','lease_token','authority'):
            for at_top in (True,False):
                frame=copy.deepcopy(self.frame)
                (frame if at_top else frame['request'])[key]='DO_NOT_RETURN_SECRET_SENTINEL'
                with self.subTest(key=key,top=at_top):
                    response,writer,calls=await self.exchange(b'',frame=frame)
                    self.assertEqual(response.transport,TRANSPORT_NOT_SENT)
                    self.assertEqual(calls,0);self.assertEqual(writer.frames,[])
                    self.assertNotIn('DO_NOT_RETURN',response.detail)

    async def test_only_canonical_app_request_ref_shape_is_admitted(self):
        for ref in ('historical-ref','req-'+('a'*31),'req-'+('A'*32),'req-'+('a'*33),True,None):
            frame=copy.deepcopy(self.frame);frame['request_ref']=ref
            with self.subTest(ref=ref):
                response,_,calls=await self.exchange(b'',frame=frame)
                self.assertEqual(response.transport,TRANSPORT_NOT_SENT);self.assertEqual(calls,0)

    async def test_scope_and_grounding_are_closed_shape_not_caller_authority(self):
        mutations=[dict(principal_scope='C'*64),dict(principal_scope='c'*63),dict(principal_scope=True),
            dict(observed_grounding={**self.frame['observed_grounding'],'host':'DO_NOT_RETURN'}),
            dict(observed_grounding={**self.frame['observed_grounding'],'mastermind_sha':'A'*40})]
        for mutation in mutations:
            frame=copy.deepcopy(self.frame);frame.update(mutation)
            with self.subTest(keys=list(mutation)):
                response,_,calls=await self.exchange(b'',frame=frame)
                self.assertEqual(response.transport,TRANSPORT_NOT_SENT);self.assertEqual(calls,0)
                self.assertNotIn('DO_NOT_RETURN',response.detail)

    async def test_profile_scope_normalization_and_nonfinite_fields_refuse_before_connect(self):
        mutations=[dict(execution_profile='research_only'),dict(attempt_limit=2),dict(priority=True),
            dict(priority=float('nan')),dict(priority=float('inf')),dict(objective=' unnormalized '),
            dict(allowed_write_paths=['write.txt']),dict(validation={'compileall_paths':['control_plane']})]
        for mutation in mutations:
            frame=copy.deepcopy(self.frame);frame['request'].update(mutation)
            with self.subTest(keys=list(mutation)):
                response,_,calls=await self.exchange(b'',frame=frame)
                self.assertEqual(response.transport,TRANSPORT_NOT_SENT);self.assertEqual(calls,0)

    async def test_duplicate_nonfinite_overflow_surrogate_extra_and_lost_reply_are_unknown_once(self):
        raws=[b'{"ok":true,"ok":false,"result":{}}\n',
              b'{"ok":true,"result":{"job_id":"JOB-a","job_id":"JOB-b"}}\n',
              b'{"ok":true,"result":{"value":NaN}}\n',
              b'{"ok":true,"result":{"value":1e999}}\n',
              b'{"ok":true,"result":{"value":"\\ud800"}}\n',
              b'{"ok":true,"result":{},"secret":"DO_NOT_RETURN"}\n',b'']
        for raw in raws:
            with self.subTest(raw=raw):
                response,writer,calls=await self.exchange(raw)
                self.assertEqual(response.transport,TRANSPORT_SENT_UNKNOWN)
                self.assertIsNone(response.result);self.assertEqual(calls,1)
                self.assertEqual(len(writer.frames),1);self.assertNotIn('DO_NOT_RETURN',response.detail)

    async def test_clean_receiving_owner_refusal_keeps_existing_transport_classification(self):
        response,writer,calls=await self.exchange(b'{"ok":false,"error":{"code":"backend_refused"}}\n')
        self.assertEqual(response.transport,TRANSPORT_SENT_OK)
        self.assertFalse(response.ok);self.assertEqual(response.error,{'code':'backend_refused'})
        self.assertEqual(calls,1);self.assertEqual(len(writer.frames),1)


if __name__=='__main__':unittest.main()
