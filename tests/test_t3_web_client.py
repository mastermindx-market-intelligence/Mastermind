"""Hermetic native-CLI presentation proofs; no installed T3 or model is called."""
import asyncio
import dataclasses
import json
import unittest

from integrations.session_bridge.t3_web_client import (
    CliResult, HandoffBrief, NativeEffectUnknown, NativeUnavailable,
    ThreadReceipt, T3CliClient,
)

PROJECT = 'project-123'
THREAD = 'mcp:launch:abc'
RUN = 'run:thread:mcp%3Alaunch%3Aabc:ordinal:1'
NEXT = 'run:thread:mcp%3Alaunch%3Aabc:ordinal:2'
SOURCE = 'https://github.com/example/repo/blob/' + 'a' * 40 + '/docs/brief.md'


def brief(**changes):
    fields = dict(request_id='test-web-task', project_id=PROJECT,
                  objective='Inspect the parser and return concrete evidence.', source_ref=SOURCE,
                  acceptance_checks=('Report the inspected source revision.',),
                  stop_conditions=('Stop at any missing permission.',),
                  non_goals=('Do not change credentials or deploy.',))
    fields.update(changes)
    return HandoffBrief(**fields)


def receipt():
    return ThreadReceipt('test-web-task', PROJECT, THREAD, RUN, brief().fingerprint)


def observation(**thread_changes):
    thread = dict(threadId=THREAD, projectId=PROJECT, latestRunId=RUN,
                  activeRunId=None, pendingRequestCount=0, status='completed')
    thread.update(thread_changes)
    return {'thread': thread, 'messages': [
        {'role': 'user', 'runId': RUN, 'text': 'request'},
        {'role': 'assistant', 'runId': RUN, 'text': 'original answer'}]}


class FakeRunner:
    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error
        self.calls = []

    async def __call__(self, invocation):
        self.calls.append(invocation)
        if self.error:
            raise self.error
        if isinstance(self.value, CliResult):
            return self.value
        return CliResult(0, json.dumps(self.value))


class BriefTests(unittest.TestCase):
    def test_deterministic_full_scope_fingerprint(self):
        a, b = brief(), brief()
        self.assertEqual(a.fingerprint, b.fingerprint)
        self.assertNotEqual(a.fingerprint, brief(objective='Different request.').fingerprint)
        self.assertNotEqual(a.fingerprint, brief(non_goals=('Do not edit files.',)).fingerprint)
        for value in (a.request_id, a.project_id, a.objective, a.source_ref,
                      *a.acceptance_checks, *a.stop_conditions, *a.non_goals):
            self.assertIn(value, a.render())
        self.assertIn('not additional permission', a.render())

    def test_immutable(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            brief().objective = 'changed'

    def test_invalid_request_and_project(self):
        for value in ('', '../other', 'a b', 'A_CAPS', '--provider', 'x' * 65):
            with self.subTest(value=value), self.assertRaises(ValueError):
                brief(request_id=value)
        for value in ('', '-provider', '../p', 'p\nother', 12):
            with self.subTest(project=value), self.assertRaises(ValueError):
                brief(project_id=value)

    def test_exact_source_not_mutable_branch_or_untrusted_url(self):
        for value in (SOURCE.replace('/' + 'a' * 40 + '/', '/master/'),
                      SOURCE + '?token=secret', SOURCE + '#section',
                      SOURCE.replace('github.com', 'evil.example'),
                      SOURCE.replace('https:', 'http:'),
                      SOURCE.replace('/docs/brief.md', '/../secret'), ''):
            with self.subTest(value=value), self.assertRaises(ValueError):
                brief(source_ref=value)

    def test_closed_nonempty_scope_lists(self):
        for field in ('acceptance_checks', 'stop_conditions', 'non_goals'):
            for value in ((), [], ('',), ('a',) * 17):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    brief(**{field: value})

    def test_write_scope_requires_native_isolation(self):
        with self.assertRaises(ValueError):
            brief(allowed_write_paths=('src/parser.py',))
        value = brief(allowed_write_paths=('src/parser.py',), worktree_base='b' * 40)
        self.assertEqual(value.worktree_base, 'b' * 40)

    def test_scope_traversal_and_ambiguous_paths_refused(self):
        for path in ('/etc', '../x', 'src/../x', './src', 'src//a', '.git/config',
                     'src/*.py', 'C:\\x', '.', 'src/[a]', 'src/a?'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                brief(allowed_write_paths=(path,), worktree_base='b' * 40)

    def test_no_secret_in_handoff(self):
        for value in ('sk-admin-' + 'a' * 40, 'Bearer ' + 'b' * 30):
            with self.subTest(value=value), self.assertRaises(ValueError):
                brief(objective=value)

    def test_bounded_message_and_base(self):
        with self.assertRaises(ValueError):
            brief(objective='x' * 9000)
        with self.assertRaises(ValueError):
            brief(worktree_base='master')

    def test_root_committed_brief_and_empty_answer(self):
        root = SOURCE.rsplit('/docs/', 1)[0] + '/BRIEF.md'
        self.assertEqual(brief(source_ref=root).source_ref, root)
        value = observation()
        value['messages'][-1]['text'] = '   '
        self.assertIsNone(T3CliClient.original_answer(receipt(), value))

    def test_observed_native_017_original_result_projection(self):
        # Reduced, non-secret projection read from the original native proof
        # thread on 2026-11-09. This is schema compatibility, not a new launch.
        native_thread = 'mcp:launch:716e98e8e078d44b16d16160280a135815e2bdd3ef02cb056ee7db124af347b8'
        native_run = ('run:thread:mcp%3Alaunch%3A716e98e8e078d44b16d16160280a135815e2bdd3ef02cb056ee7db124af347b8:ordinal:1')
        native_project = '9de77193-e68a-49fe-adee-f85406f04772'
        record = ThreadReceipt('retained-t3-proof-read', native_project, native_thread,
                               native_run, brief().fingerprint)
        observed = {'thread': {'threadId': native_thread, 'projectId': native_project,
                    'status': 'completed', 'latestRunId': native_run,
                    'activeRunId': None, 'pendingRequestCount': 0},
                    'messages': [{'role': 'assistant', 'runId': native_run,
                                  'text': 'T3-PROOF-OK'}]}
        self.assertEqual(T3CliClient.original_answer(record, observed), 'T3-PROOF-OK')


class NativeClientTests(unittest.IsolatedAsyncioTestCase):
    def make(self, value=None, error=None):
        runner = FakeRunner(value, error)
        return T3CliClient('/native/t3', runner), runner

    async def test_native_launch_once_no_model_or_credential_overrides(self):
        client, runner = self.make(dict(threadId=THREAD, projectId=PROJECT, runId=RUN))
        result = await client.launch(brief())
        self.assertEqual(result.thread_id, THREAD)
        self.assertEqual(result.run_id, RUN)
        self.assertEqual(len(runner.calls), 1)
        call = runner.calls[0]
        self.assertEqual(call.argv[-4:-2], (PROJECT, '-'))
        self.assertEqual(call.argv[-2:], ('--log-level', 'error'))
        self.assertEqual(call.stdin, brief().render())
        self.assertNotIn(brief().objective, call.argv)
        for flag in ('--provider', '--model', '--wait', '--token', '--runtime-mode'):
            self.assertNotIn(flag, call.argv)

    async def test_code_handoff_uses_exact_t3_worktree(self):
        client, runner = self.make(dict(threadId=THREAD, projectId=PROJECT, runId=RUN))
        await client.launch(brief(allowed_write_paths=('src/parser.py',), worktree_base='c' * 40))
        argv = runner.calls[0].argv
        self.assertEqual(argv[argv.index('--worktree') + 1], 'c' * 40)
        self.assertEqual(argv[argv.index('--branch') + 1], 'web/test-web-task')

    async def test_sync_runner_supported(self):
        client = T3CliClient('/native/t3', lambda _: CliResult(0, '[]'))
        self.assertEqual(await client.list_threads(PROJECT), ())

    async def test_invalid_cli_path_never_dispatches(self):
        for path in ('t3', '~/bin/t3', '', '/a\x00b'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                T3CliClient(path, lambda _: None)

    async def test_list_binds_exact_project(self):
        client, runner = self.make([dict(threadId=THREAD, projectId=PROJECT, status='running')])
        rows = await client.list_threads(PROJECT)
        self.assertEqual(rows[0]['threadId'], THREAD)
        self.assertEqual(runner.calls[0].argv, ('/native/t3', 'thread', 'list', '--project', PROJECT, '--json', '--log-level', 'error'))
        client, _ = self.make([dict(threadId=THREAD, projectId='foreign')])
        with self.assertRaises(NativeUnavailable):
            await client.list_threads(PROJECT)

    async def test_list_malformed_not_silent_empty(self):
        for value in (None, {}, [{'projectId': PROJECT}], [False],
                      [{'threadId': 'bad\nref', 'projectId': PROJECT}]):
            with self.subTest(value=value):
                client, _ = self.make(value)
                with self.assertRaises(NativeUnavailable):
                    await client.list_threads(PROJECT)

    async def test_lost_launch_is_unknown_and_not_replayed(self):
        client, runner = self.make(error=TimeoutError('may already have sent'))
        with self.assertRaises(NativeEffectUnknown) as caught:
            await client.launch(brief())
        self.assertEqual(caught.exception.request_id, brief().request_id)
        self.assertEqual(len(runner.calls), 1)
        self.assertIsNone(caught.exception.__cause__)

    async def test_cancelled_launch_is_unknown_not_a_safe_retry(self):
        client, runner = self.make(error=asyncio.CancelledError())
        with self.assertRaises(NativeEffectUnknown):
            await client.launch(brief())
        self.assertEqual(len(runner.calls), 1)

    async def test_cancelled_read_remains_cancellation(self):
        client, runner = self.make(error=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await client.read(receipt())
        self.assertEqual(len(runner.calls), 1)

    async def test_nonzero_launch_preserves_unknown_does_not_switch_provider(self):
        secret = 'sk-admin-' + 's' * 40
        client, runner = self.make(CliResult(1, '', secret))
        with self.assertRaises(NativeEffectUnknown) as caught:
            await client.launch(brief())
        self.assertNotIn(secret, str(caught.exception))
        self.assertEqual(len(runner.calls), 1)

    async def test_invalid_or_wrong_launch_result_is_unknown(self):
        for value in ({}, None, dict(threadId=THREAD, projectId='foreign', runId=RUN),
                      dict(threadId=THREAD, projectId=PROJECT),
                      dict(threadId='bad\nref', projectId=PROJECT, runId=RUN)):
            with self.subTest(value=value):
                client, runner = self.make(value)
                with self.assertRaises(NativeEffectUnknown):
                    await client.launch(brief())
                self.assertEqual(len(runner.calls), 1)

    async def test_bad_json_duplicate_keys_and_budget(self):
        for text in ('{', 'NaN', '{"threadId":"a","threadId":"b"}', ' ' * 262145):
            with self.subTest(text=text[:20]):
                client, _ = self.make(CliResult(0, text))
                with self.assertRaises(NativeEffectUnknown):
                    await client.launch(brief())

    async def test_same_thread_follow_up_is_native_queue_not_interrupt(self):
        for delivery in ('started', 'queued'):
            with self.subTest(delivery=delivery):
                client, runner = self.make(dict(threadId=THREAD, runId=NEXT, delivery=delivery))
                next_receipt = await client.send(receipt(), 'Continue with the original scope.')
                self.assertEqual(next_receipt.thread_id, THREAD)
                self.assertEqual(next_receipt.run_id, NEXT)
                self.assertEqual(next_receipt.delivery, delivery)
                self.assertEqual(runner.calls[0].argv, ('/native/t3', 'thread', 'send', '--json', THREAD, '-', '--log-level', 'error'))
                self.assertNotIn('interrupt', runner.calls[0].argv)

    async def test_followup_rejects_wrong_thread_steer_or_old_run(self):
        for changes in ({'threadId': 'other'}, {'delivery': 'steered'}, {'delivery': 'sent'}, {'runId': RUN}):
            with self.subTest(changes=changes):
                value = dict(threadId=THREAD, runId=NEXT, delivery='queued');value.update(changes)
                client, _ = self.make(value)
                with self.assertRaises(NativeEffectUnknown) as caught:
                    await client.send(receipt(), 'Continue')
                self.assertEqual(caught.exception.thread_id, THREAD)

    async def test_followup_transport_loss_keeps_original_thread(self):
        client, runner = self.make(error=ConnectionError())
        with self.assertRaises(NativeEffectUnknown) as caught:
            await client.send(receipt(), 'Continue')
        self.assertEqual(caught.exception.thread_id, THREAD)
        self.assertEqual(len(runner.calls), 1)

    async def test_empty_followup_never_sends(self):
        client, runner = self.make()
        with self.assertRaises(ValueError):
            await client.send(receipt(), '  ')
        self.assertEqual(runner.calls, [])

    async def test_read_is_exact_bounded_and_unmodified(self):
        value = observation();client, runner = self.make(value)
        read = await client.read(receipt(), messages=3)
        self.assertEqual(read, value)
        self.assertEqual(runner.calls[0].argv, ('/native/t3', 'thread', 'show', THREAD, '--messages', '3', '--json', '--log-level', 'error'))
        self.assertEqual(T3CliClient.original_answer(receipt(), read), 'original answer')

    async def test_read_wrong_thread_project_or_shape_refuses(self):
        for value in (observation(threadId='other'), observation(projectId='foreign'), {},
                      {'thread': observation()['thread'], 'messages': ['not an item']}):
            with self.subTest(value=value):
                client, _ = self.make(value)
                with self.assertRaises(NativeUnavailable):
                    await client.read(receipt())

    async def test_read_pending_failed_or_newer_turn_cannot_be_answer(self):
        for changes in ({'status': 'running'}, {'status': 'failed'}, {'status': 'waiting'},
                        {'pendingRequestCount': 1}, {'latestRunId': NEXT}, {'activeRunId': NEXT}):
            with self.subTest(changes=changes):
                self.assertIsNone(T3CliClient.original_answer(receipt(), observation(**changes)))

    async def test_foreign_message_not_original_answer(self):
        value = observation();value['messages'][1]['runId'] = NEXT
        self.assertIsNone(T3CliClient.original_answer(receipt(), value))

    async def test_unknown_read_not_completed(self):
        client, runner = self.make(error=TimeoutError())
        with self.assertRaises(NativeUnavailable):
            await client.read(receipt())
        self.assertEqual(len(runner.calls), 1)

    async def test_bounds_before_dispatch(self):
        client, runner = self.make()
        for count in (0, 41, True):
            with self.subTest(count=count), self.assertRaises(ValueError):
                await client.read(receipt(), messages=count)
        self.assertEqual(runner.calls, [])


if __name__ == '__main__':
    unittest.main()
