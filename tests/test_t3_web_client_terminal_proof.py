"""Strict scope and terminal evidence, separate from native CLI transport tests."""
import unittest

from integrations.session_bridge.t3_web_client import HandoffBrief, ThreadReceipt, T3CliClient

SOURCE = 'https://github.com/example/repo/blob/' + 'a' * 40 + '/docs/brief.md'


def brief(**changes):
    fields = dict(request_id='strict-proof', project_id='project-123',
                  objective='Read the exact native result.', source_ref=SOURCE,
                  acceptance_checks=('Original result and run match.',),
                  stop_conditions=('Stop at any permission gate.',),
                  non_goals=('Do not change provider or credentials.',))
    fields.update(changes)
    return HandoffBrief(**fields)


class TerminalProofTests(unittest.TestCase):
    def test_encoded_and_control_source_paths_are_not_immutable_refs(self):
        for value in (SOURCE.replace('/docs/', '/%2e%2e/'), SOURCE + '\n',
                      SOURCE.replace('github.com', 'github.\tcom')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                brief(source_ref=value)

    def test_scope_paths_have_no_control_characters(self):
        for value in ('src/\nname', 'src/\tname', 'src/name\x7f'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                brief(allowed_write_paths=(value,), worktree_base='b' * 40)

    def test_unknown_or_malformed_pending_state_never_proves_completion(self):
        record = ThreadReceipt('strict-proof', 'project-123', 'thread-1', 'run-1', brief().fingerprint)
        def observation(count):
            return {'thread': {'threadId': 'thread-1', 'projectId': 'project-123',
                    'latestRunId': 'run-1', 'status': 'completed', 'activeRunId': None,
                    'pendingRequestCount': count}, 'messages': [
                    {'role': 'assistant', 'runId': 'run-1', 'text': 'observed answer'}]}
        for value in (False, None, '0', 0.0):
            with self.subTest(value=value):
                self.assertIsNone(T3CliClient.original_answer(record, observation(value)))
        value = observation(0)
        del value['thread']['activeRunId']
        self.assertIsNone(T3CliClient.original_answer(record, value))
        self.assertEqual(T3CliClient.original_answer(record, observation(0)), 'observed answer')


if __name__ == '__main__':
    unittest.main()
