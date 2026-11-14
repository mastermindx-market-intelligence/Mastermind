"""Existing Runtime -> sealed subscription -> signed fake HTTPS -> canonical read.

The native transport and HTTPS peer are simulated. This is integration proof,
not a production subscription, native execution, or actual ChatGPT Dot wake.
"""
import asyncio
import base64
import dataclasses
import hashlib
import json
import socket
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from control_plane.executive_runtime import Runtime
from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.session_bridge.runtime_owner import RuntimeFabricTargetProjector, RuntimeCodexTargetProjector
from integrations.session_bridge.runtime_return import RuntimeSessionReturn, RuntimeOriginalRequestResolver
from integrations.session_bridge.native_read import NativeReplyReader
from integrations.session_bridge.return_tools import NativeReplyReadTool
from integrations.session_bridge.t3_native_client import T3NativeClient, Run, Unavailable
from integrations.session_bridge.t3_reply_events import T3OriginalReplySource, T3ReturnEffectUnknown, READ_PREFIX, REQUEST_PREFIX
from integrations.session_bridge.runtime_reply_delivery import build_runtime_reply_delivery
from integrations.session_bridge.runtime_reply_subscriptions import ExecutiveReplyCipher, RuntimeReplySubscriptionStore
from integrations.session_bridge.web_reply_subscription_owner import StoredReplySubscription, owner_key, _subscription_id
from tests.test_session_bridge_installed import principal_frame
from tests.test_t3_native_client import Native, SCHEMAS, SCOPE, THREAD

NOW = 1794580000
URL = 'https://receiver.example.com/original-dot-fixture'
SECRET = 'whsec_' + base64.b64encode(b'a'*32).decode()


def run(value): return asyncio.run(value)


class T3ReturnIntegration(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.runtime=Runtime.at(Path(self.temp.name))
        raw=principal_frame(); raw.update(issued_at=NOW-60,expires_at=NOW+3600); raw['scopes']=tuple(raw['scopes'])
        self.verified=VerifiedPrincipal(**raw); self.principal=principal_projection(self.verified)
        self.native=Native(); self.client=T3NativeClient(SCOPE,self.native,SCHEMAS)
        self.denied=False
        async def factory(p,scope):
            if self.denied or owner_key(p)!=owner_key(self.principal): raise Unavailable('not granted')
            return self.client
        self.source=T3OriginalReplySource(self.runtime,factory,current=lambda p:p,clock=lambda:NOW,enabled=True)
        fabric=RuntimeFabricTargetProjector(self.runtime)
        codex=RuntimeCodexTargetProjector(fabric,owner_configured=lambda:False)
        async def no_dialogue(*args,**kwargs): raise AssertionError('T3 must not impersonate Dialogue')
        self.owner=RuntimeSessionReturn(self.runtime,fabric=fabric,codex=codex,
            socket_path=Path('/private/tmp/nonexistent-t3-fixture.sock'),service_call=no_dialogue,t3_replies=self.source)
        self.native_run=Run(THREAD,'run-1','request-1','launched')
        self.binding=run(self.source.bind(self.principal,self.native_run))
        run(self.source.observe(self.principal,self.binding['request_ref']))

    def delivery(self, *, lost=False):
        grant=run(RuntimeOriginalRequestResolver(self.owner).resolve(self.principal,self.binding['request_ref']))
        store=RuntimeReplySubscriptionStore(self.runtime,ExecutiveReplyCipher('fixture-key',b'k'*32),clock=lambda:NOW)
        record=StoredReplySubscription(subscription_id=_subscription_id(owner_key(self.principal),grant.request_ref,URL),
            owner_key=owner_key(self.principal),request_ref=grant.request_ref,read_ref=grant.read_ref,revision=grant.revision,
            expires_at=NOW+300,verified_at=NOW,callback_url_digest=hashlib.sha256(URL.encode()).hexdigest(),
            signing_secret_digest=hashlib.sha256(SECRET.encode()).hexdigest())
        run(store.commit(record,SECRET,callback_url=URL,expected_version='empty'))
        calls=[]
        class Connection:
            def request(self,*args,**kwargs):
                calls.append((args,kwargs))
                if lost: raise TimeoutError('simulated unknown external receipt')
            def getresponse(self): return SimpleNamespace(status=200,read=lambda _size:b'accepted')
            def close(self): pass
        def resolver(*args,**kwargs): return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443))]
        delivery=build_runtime_reply_delivery(self.owner,store,clock=lambda:NOW,enabled=True,
            resolver=resolver,connector=lambda *args:Connection())
        return delivery,store,record,calls

    def test_incumbent_signed_delivery_once_and_public_canonical_read(self):
        delivery,store,record,calls=self.delivery()
        result=run(delivery.deliver_current(self.verified,record.subscription_id))
        self.assertEqual(result['state'],'TRANSPORT_ACCEPTED_PARENT_UNPROVEN')
        self.assertFalse(result['parent_consumed']); self.assertEqual(len(calls),1)
        args,kwargs=calls[0]
        event=json.loads(args[2])
        self.assertEqual(event['data']['read_ref'],self.binding['read_ref'])
        self.assertEqual(event['data']['in_reply_to'],self.binding['request_ref'])
        self.assertIn('webhook-signature',kwargs['headers'])
        duplicate=run(delivery.deliver_current(self.verified,record.subscription_id))
        self.assertFalse(duplicate['fresh_send']); self.assertEqual(len(calls),1)
        reader=NativeReplyReader(self.owner,socket_path=self.owner.socket_path,clock=lambda:NOW,t3_replies=self.source)
        tool=NativeReplyReadTool(reader)
        response=run(tool.handle(self.verified,'session_reply_read',{'read_ref':self.binding['read_ref']}))
        self.assertTrue(response['ok']); self.assertEqual(response['data']['answer'],'done')
        self.assertEqual(response['data']['run_id'],'run-1'); self.assertFalse(response['data']['parent_consumed'])
        events=json.dumps([e.to_dict() for e in self.runtime.store.list_events()])
        self.assertNotIn(SECRET,events); self.assertNotIn(URL,events)

    def test_foreign_account_cannot_read_or_deliver(self):
        delivery,store,record,calls=self.delivery()
        foreign=dataclasses.replace(self.verified,subject_digest='a'*64)
        with self.assertRaises(ValueError): run(delivery.deliver_current(foreign,record.subscription_id))
        self.assertFalse(calls)
        reader=NativeReplyReader(self.owner,socket_path=self.owner.socket_path,clock=lambda:NOW,t3_replies=self.source)
        response=run(NativeReplyReadTool(reader).handle(foreign,'session_reply_read',{'read_ref':self.binding['read_ref']}))
        self.assertFalse(response['ok']); self.assertIsNone(response['data'])

    def test_lost_callback_receipt_is_not_replayed(self):
        delivery,store,record,calls=self.delivery(lost=True)
        result=run(delivery.deliver_current(self.verified,record.subscription_id))
        self.assertEqual(result['state'],'EFFECT_UNKNOWN'); self.assertEqual(len(calls),1)
        second=run(delivery.deliver_current(self.verified,record.subscription_id))
        self.assertFalse(second['fresh_send']); self.assertEqual(len(calls),1)

    def test_unsubscribe_blocks_delivery_without_native_authority_expansion(self):
        delivery,store,record,calls=self.delivery()
        snapshot=run(store.snapshot(record.subscription_id))
        run(store.remove(record.subscription_id,record.owner_key,request_ref=record.request_ref,
            callback_url_digest=record.callback_url_digest,expected_version=snapshot.version))
        with self.assertRaises(ValueError): run(delivery.deliver_current(self.verified,record.subscription_id))
        self.assertFalse(calls)

    def test_missing_host_source_does_not_fallback_to_another_reader(self):
        self.owner.t3_replies=None
        with self.assertRaises(Exception): run(RuntimeOriginalRequestResolver(self.owner).resolve(self.principal,self.binding['request_ref']))
        reader=NativeReplyReader(self.owner,socket_path=self.owner.socket_path,clock=lambda:NOW)
        response=run(NativeReplyReadTool(reader).handle(self.verified,'session_reply_read',{'read_ref':self.binding['read_ref']}))
        self.assertFalse(response['ok'])

    def test_persistence_lost_ack_reports_original_refs_without_retry(self):
        other=Run(THREAD,'run-2','request-2','queued')
        self.native.responses['t3_thread_wait']={'structuredContent':{'threadId':THREAD.thread_id,
            'runId':'run-2','status':'completed','pendingRequestCount':0,'timedOut':False}}
        with patch.object(self.runtime.store,'append_event',side_effect=TimeoutError('lost append receipt')) as append:
            with self.assertRaises(T3ReturnEffectUnknown) as observed:
                run(self.source.bind(self.principal,other))
            self.assertEqual(append.call_count,1)
            self.assertTrue(observed.exception.request_ref.startswith(REQUEST_PREFIX))
            self.assertTrue(observed.exception.read_ref.startswith(READ_PREFIX))
            self.assertFalse(observed.exception.retry_allowed)


if __name__=='__main__': unittest.main()
