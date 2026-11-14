"""Disposable Runtime, real native client parsing, fake native transport only."""
import asyncio
import base64
import dataclasses
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from control_plane.executive_runtime import Runtime
from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.session_bridge.t3_native_client import T3NativeClient, Run, Unavailable, Conflict, Scope
from integrations.session_bridge.t3_reply_events import (
    T3OriginalReplySource, stored_t3_request, stored_original_reply_request,
    validate_t3_public_reply, REQUEST_PREFIX, READ_PREFIX,
)
from integrations.session_bridge.web_reply_subscription_owner import owner_key
from tests.test_session_bridge_installed import principal_frame
from tests.test_t3_native_client import Native, SCHEMAS, SCOPE, THREAD, observation, item

NOW = 1794580000


def run(value):
    return asyncio.run(value)


def principal():
    value = principal_frame()
    value.update(issued_at=NOW-60, expires_at=NOW+3600)
    value['scopes'] = tuple(value['scopes'])
    return principal_projection(VerifiedPrincipal(**value))


class T3ReplyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Runtime.at(Path(self.temp.name))
        self.now = NOW
        self.p = principal()
        self.native = Native()
        self.client = T3NativeClient(SCOPE, self.native, SCHEMAS)
        self.denied = False
        self.client_calls = 0
        async def native_client(p, scope):
            self.client_calls += 1
            if self.denied or owner_key(p) != owner_key(self.p):
                raise Unavailable('not granted')
            return self.client
        self.factory = native_client
        self.source = T3OriginalReplySource(self.runtime, native_client,
            current=lambda p: p, clock=lambda: self.now, enabled=True)
        self.run = Run(THREAD, 'run-1', 'original-request', 'launched')

    def bind(self):
        return run(self.source.bind(self.p, self.run))

    def observed(self):
        ref = self.bind()
        value = run(self.source.observe(self.p, ref['request_ref']))
        return ref, value

    def test_disabled_source_cannot_bind_read_or_observe(self):
        source = T3OriginalReplySource(self.runtime, self.factory, current=lambda p:p,
            clock=lambda: self.now)
        with self.assertRaises(Unavailable): run(source.bind(self.p, self.run))
        self.assertFalse(self.native.calls)
        self.assertEqual(self.runtime.store.list_events(), [])

    def test_no_caller_dict_or_account_string_is_authentication(self):
        for wrong in ({'policy_id': self.p.policy_id}, 'p:tunnel:account-a', None):
            with self.subTest(wrong=wrong), self.assertRaises(Unavailable):
                run(self.source.bind(wrong, self.run))
        self.assertFalse(self.native.calls)

    def test_bind_requires_real_exact_native_run_and_persists_only_refs(self):
        value = self.bind()
        self.assertTrue(value['request_ref'].startswith(REQUEST_PREFIX))
        self.assertTrue(value['read_ref'].startswith(READ_PREFIX))
        self.assertEqual(value['native_execution'], 'NOT_CREATED')
        self.assertEqual(value['subscription'], 'NOT_CREATED')
        event, payload = stored_t3_request(self.runtime, value['read_ref'])
        self.assertEqual(payload['run']['run_id'], 'run-1')
        self.assertEqual(payload['run']['thread']['scope']['environment_id'], SCOPE.environment_id)
        self.assertFalse(any(name == 't3_thread_launch' for name,_ in self.native.calls))
        self.assertEqual(len(self.runtime.store.list_events()), 1)

    def test_bind_foreign_run_cannot_create_original_return(self):
        self.native.responses['t3_thread_wait'] = {'structuredContent': {'threadId': THREAD.thread_id,
            'runId': 'wrong-run', 'status':'completed', 'pendingRequestCount':0}}
        with self.assertRaises((Unavailable, Conflict)): self.bind()
        self.assertEqual(self.runtime.store.list_events(), [])

    def test_same_original_bind_reconciles_no_duplicate_and_preserves_expiry(self):
        first = self.bind()
        self.now += 1
        second = self.bind()
        self.assertEqual(first, second)
        self.assertEqual(len(self.runtime.store.list_events()), 1)

    def test_another_account_cannot_resolve_original_request(self):
        value = self.bind()
        other = dataclasses.replace(self.p, subject_digest='a'*64)
        count = self.client_calls
        with self.assertRaises(Unavailable): run(self.source.resolve(other, value['request_ref']))
        self.assertEqual(self.client_calls, count)

    def test_actual_native_access_revoked_blocks_delivery_and_read(self):
        ref,_ = self.observed()
        self.denied = True
        with self.assertRaises(Unavailable): run(self.source.project(self.p,ref['request_ref']))
        with self.assertRaises(Unavailable): run(self.source.read(self.p, {'read_ref':ref['read_ref']}))

    def test_original_response_not_later_turn_is_committed(self):
        self.native.detail['thread']['latestRunId'] = 'run-2'
        ref,receipt = self.observed()
        self.assertTrue(receipt['reply_committed'])
        self.assertFalse(receipt['delivered'])
        result = run(self.source.read(self.p, {'read_ref':ref['read_ref']}))
        self.assertEqual(result['answer'], 'done')
        self.assertEqual(result['run_id'], 'run-1')
        self.assertFalse(result['parent_consumed'])

    def test_native_complete_without_producer_commit_cannot_be_projected(self):
        ref=self.bind(); before=len(self.runtime.store.list_events())
        with self.assertRaises(Unavailable): run(self.source.project(self.p, ref['request_ref']))
        with self.assertRaises(Unavailable): run(self.source.read(self.p, {'read_ref':ref['read_ref']}))
        self.assertEqual(len(self.runtime.store.list_events()), before)

    def test_pending_or_partial_answer_is_not_committed_reply(self):
        ref=self.bind()
        self.native.responses['t3_thread_wait'] = {'structuredContent': {'threadId': THREAD.thread_id,
            'runId':'run-1','status':'running','pendingRequestCount':0}}
        with self.assertRaises(Unavailable): run(self.source.observe(self.p,ref['request_ref']))
        self.assertEqual(len(self.runtime.store.list_events()), 1)

    def test_observe_idempotent_restart_retains_digest_not_answer(self):
        text='original durable response with confidential unrelated words'
        self.native.detail=observation([item(text)])
        ref,receipt=self.observed()
        self.now+=2
        again=run(self.source.observe(self.p,ref['request_ref']))
        self.assertEqual(again,receipt)
        self.assertEqual(len(self.runtime.store.list_events()),2)
        self.assertNotIn(text,json.dumps([e.to_dict() for e in self.runtime.store.list_events()]))
        reopened=T3OriginalReplySource(Runtime.at(Path(self.temp.name)),self.factory,
            current=lambda p:p,clock=lambda:self.now,enabled=True)
        result=run(reopened.read(self.p,{'read_ref':ref['read_ref']}))
        self.assertEqual(result['answer'],text)

    def test_original_reply_changed_requires_new_observed_digest(self):
        ref,_=self.observed()
        self.native.detail=observation([item('corrected native result')])
        with self.assertRaises(Unavailable): run(self.source.project(self.p,ref['request_ref']))
        run(self.source.observe(self.p,ref['request_ref']))
        self.assertEqual(len(self.runtime.store.list_events()),3)

    def test_stable_event_no_raw_result_or_parent_consumption(self):
        ref,_=self.observed()
        a=run(self.source.project(self.p,ref['request_ref']))
        self.now+=3
        b=run(self.source.project(self.p,ref['request_ref']))
        self.assertEqual(a,b)
        self.assertEqual(a.event['data']['in_reply_to'],ref['request_ref'])
        self.assertEqual(a.event['data']['read_ref'],ref['read_ref'])
        self.assertNotIn('answer',a.event['data'])
        self.assertFalse(a.event['data']['parent_consumed'])
        self.assertEqual(a.principal_ref,owner_key(self.p))

    def test_shared_signer_accepts_strict_t3_namespace_and_rejects_mixed_source(self):
        from integrations.session_bridge.web_reply_delivery import VerifiedReplySubscription, prepare_reply_webhook
        ref,_=self.observed()
        event=run(self.source.project(self.p,ref['request_ref'])).event
        secret='whsec_'+base64.b64encode(b'x'*32).decode()
        sub=VerifiedReplySubscription(subscription_id='sub_'+('a'*40), principal_ref=owner_key(self.p),
            request_ref=ref['request_ref'], event_name=event['name'], expires_at=NOW+1000,
            signing_secrets=(secret,),access_current=True,active=True)
        packet=prepare_reply_webhook(subscription=sub,event=event,signed_at=NOW)
        self.assertEqual(json.loads(packet.body)['data']['read_ref'],ref['read_ref'])
        altered=json.loads(json.dumps(event));altered['data']['read_ref']='session-reply-'+('f'*64)
        with self.assertRaises(ValueError): prepare_reply_webhook(subscription=sub,event=altered,signed_at=NOW)

    def test_expiry_fail_closed(self):
        ref=self.bind();self.now=NOW+3601
        with self.assertRaises(Unavailable): run(self.source.resolve(self.p,ref['request_ref']))

    def test_namespace_dispatch_never_relabels_dialogue_request(self):
        ref=self.bind()
        event,payload=stored_original_reply_request(self.runtime,ref['read_ref'])
        self.assertEqual(event.command_id,ref['request_ref'])
        with self.assertRaises(Exception): stored_original_reply_request(self.runtime,'session-reply-'+ref['read_ref'][len(READ_PREFIX):])

    def test_public_result_redaction_and_checksum_provenance(self):
        text='authorization=abcdefghijklmnop'
        self.native.detail=observation([item(text)])
        ref,_=self.observed(); result=run(self.source.read(self.p,{'read_ref':ref['read_ref']}))
        self.assertTrue(result['redacted']); self.assertEqual(result['answer'],'[REDACTED]')
        self.assertEqual(result['answer_sha256'],hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual(validate_t3_public_reply(result), result)


if __name__=='__main__': unittest.main()
