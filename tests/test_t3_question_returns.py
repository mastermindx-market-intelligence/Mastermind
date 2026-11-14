"""Pending-question returns use real Runtime/client validation and fake native IO."""
import asyncio
import copy
import dataclasses
import json
from pathlib import Path
import tempfile
import unittest

from control_plane.executive_runtime import Runtime
from integrations.session_bridge.return_tools import NativeReplyReadTool
from integrations.executive_mcp.schemas import GatewayError
from integrations.session_bridge.t3_native_client import T3NativeClient, Run, Unavailable, Conflict
from integrations.session_bridge.t3_reply_events import (
    T3OriginalReplySource, QUESTION_READ_SCHEMA, validate_t3_public_reply,
)
from integrations.session_bridge.web_reply_subscription_owner import owner_key
from tests.test_t3_native_client import Native, SCHEMAS, SCOPE, THREAD, schema
from tests.test_t3_reply_events import NOW, principal


def execute(coroutine):
    return asyncio.run(coroutine)


class T3QuestionReturnTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.runtime = Runtime.at(Path(temp.name))
        self.now = NOW
        self.p = principal()
        self.denied = False
        self.native = Native()
        self.native.detail['thread'].update(status='running', activeRunId='run-1', pendingRequestCount=1)
        self.native.responses['t3_thread_wait'] = {'structuredContent': {
            'threadId': THREAD.thread_id, 'runId': 'run-1', 'status': 'running', 'timedOut': True}}
        self.questions = {'pending-1': self.question('pending-1', 'Which dataset should I use?')}
        self.native.responses['t3_pending_request'] = self.pending
        schemas = dict(SCHEMAS, t3_pending_request=schema('environmentId', 'threadId', 'action', 'requestId', 'answers'))
        self.client = T3NativeClient(SCOPE, self.native, schemas)
        async def native_client(p, scope):
            if self.denied or owner_key(p) != owner_key(self.p):
                raise Unavailable('current native grant unavailable')
            return self.client
        self.source = T3OriginalReplySource(self.runtime, native_client, current=lambda p: p,
            clock=lambda: self.now, enabled=True)
        self.run = Run(THREAD, 'run-1', 'original-request', 'launched')
        self.binding = execute(self.source.bind(self.p, self.run))

    @staticmethod
    def question(request_id, text):
        return {'threadId': THREAD.thread_id, 'runId': 'run-1', 'kind': 'user_input',
                'status': 'pending', 'requestId': request_id,
                'questions': [{'id': 'dataset', 'question': text, 'required': True}]}

    def pending(self, args):
        if args['action'] != 'read':
            raise AssertionError('notification must not answer or grant permission')
        return {'structuredContent': copy.deepcopy(self.questions[args['requestId']])}

    def observe(self, request_id='pending-1'):
        return execute(self.source.observe_question(self.p, self.binding['request_ref'], request_id))

    def read(self, receipt, principal_override=None):
        return execute(self.source.read(principal_override or self.p,
            {'read_ref': receipt['read_ref'], 'message_key': receipt['message_key']}))

    def test_question_is_exact_run_not_terminal_and_only_digest_is_persisted(self):
        receipt = self.observe()
        value = self.read(receipt)
        self.assertEqual(value['schema'], QUESTION_READ_SCHEMA)
        self.assertEqual(value['status'], 'question_pending')
        self.assertEqual(value['run_id'], self.run.run_id)
        self.assertEqual(value['pending_request_id'], 'pending-1')
        self.assertFalse(value['run_complete'])
        self.assertFalse(value['parent_consumed'])
        self.assertNotIn('answer', value)
        retained = json.dumps([event.to_dict() for event in self.runtime.store.list_events()])
        self.assertNotIn('Which dataset', retained)
        self.assertEqual(len(self.runtime.store.list_events()), 2)
        self.assertTrue(all(name not in {'t3_thread_launch', 't3_thread_send'} for name, _ in self.native.calls))

    def test_same_question_observation_reconciles_without_duplicate(self):
        first = self.observe()
        self.now += 1
        second = self.observe()
        self.assertEqual(first, second)
        self.assertEqual(len(self.runtime.store.list_events()), 2)

    def test_two_questions_have_distinct_exact_selectors_not_latest_text(self):
        first = self.observe()
        self.questions['pending-2'] = self.question('pending-2', 'Which date range?')
        second = self.observe('pending-2')
        self.assertNotEqual(first['message_key'], second['message_key'])
        self.assertEqual(self.read(first)['questions'][0]['question'], 'Which dataset should I use?')
        self.assertEqual(self.read(second)['questions'][0]['question'], 'Which date range?')

    def test_missing_or_wrong_native_provenance_does_not_commit(self):
        for field, value in [('runId', 'later-run'), ('threadId', 'other-thread'), ('kind', 'approval'),
                             ('status', 'resolved'), ('runId', None), ('threadId', None)]:
            with self.subTest(field=field, value=value):
                question = self.question('pending-1', 'Question')
                if value is None:
                    question.pop(field)
                else:
                    question[field] = value
                self.questions['pending-1'] = question
                with self.assertRaises(Conflict): self.observe()
                self.assertEqual(len(self.runtime.store.list_events()), 1)

    def test_terminal_run_cannot_emit_pending_question(self):
        self.native.responses['t3_thread_wait']['structuredContent']['status'] = 'completed'
        with self.assertRaises(Unavailable): self.observe()
        self.assertEqual(len(self.runtime.store.list_events()), 1)

    def test_changed_question_is_not_substituted_after_event(self):
        receipt = self.observe()
        self.questions['pending-1']['questions'][0]['question'] = 'Different request'
        with self.assertRaises(Conflict): self.read(receipt)
        with self.assertRaises(Conflict):
            execute(self.source.project(self.p, receipt['request_ref'], message_key=receipt['message_key']))
        self.assertEqual(len(self.runtime.store.list_events()), 2)

    def test_answered_question_is_unavailable_without_effect(self):
        receipt = self.observe()
        self.questions['pending-1']['status'] = 'resolved'
        with self.assertRaises(Conflict): self.read(receipt)
        self.assertEqual(len(self.runtime.store.list_events()), 2)

    def test_uncommitted_selector_never_creates_observation_on_read(self):
        with self.assertRaises(Conflict):
            self.read(dict(self.binding, message_key='t3-native-question-' + '0' * 64))
        self.assertEqual(len(self.runtime.store.list_events()), 1)

    def test_foreign_account_and_revoked_access_are_rejected(self):
        receipt = self.observe()
        other = dataclasses.replace(self.p, subject_digest='b' * 64)
        with self.assertRaises(Unavailable): self.read(receipt, other)
        self.denied = True
        with self.assertRaises(Unavailable): self.read(receipt)

    def test_expired_original_binding_cannot_send_or_read(self):
        receipt = self.observe()
        self.now += 3601
        with self.assertRaises(Unavailable): self.read(receipt)
        with self.assertRaises(Unavailable): self.observe()

    def test_question_cannot_be_read_as_default_completed_reply(self):
        receipt = self.observe()
        with self.assertRaises(Unavailable):
            execute(self.source.read(self.p, {'read_ref': receipt['read_ref']}))

    def test_reference_only_event_identifies_pending_question(self):
        receipt = self.observe()
        event = execute(self.source.project(self.p, receipt['request_ref'], message_key=receipt['message_key']))
        self.assertEqual(event.read_ref, self.binding['read_ref'])
        self.assertEqual(event.event['data']['message_key'], receipt['message_key'])
        self.assertIn('not a completed task', event.event['data']['summary'])
        self.assertNotIn('Which dataset', json.dumps(event.event))

    def test_public_reply_cannot_claim_completion_or_consumption(self):
        value = self.read(self.observe())
        for field in ('run_complete', 'parent_consumed'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_t3_public_reply(dict(value, **{field: True}))

    def test_exact_selector_contract_rejects_other_source_or_operation(self):
        receipt = self.observe()
        valid = {'read_ref': receipt['read_ref'], 'message_key': receipt['message_key']}
        self.assertEqual(NativeReplyReadTool.validate('session_reply_read', valid), valid)
        for wrong in ({'operation_key': 'old', 'message_key': receipt['message_key']},
                      dict(valid, read_ref='dialogue-read'), dict(valid, message_key='latest'),
                      dict(valid, unexpected=True)):
            with self.subTest(wrong=wrong), self.assertRaises(GatewayError):
                NativeReplyReadTool.validate('session_reply_read', wrong)

    def test_public_question_secret_like_content_is_redacted(self):
        self.questions['pending-1']['questions'][0]['question'] = 'Use sk-' + 'A' * 40
        value = self.read(self.observe())
        self.assertTrue(value['redacted'])
        self.assertNotIn('sk-' + 'A' * 40, json.dumps(value))


if __name__ == '__main__':
    unittest.main()
