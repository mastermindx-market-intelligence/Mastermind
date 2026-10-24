"""Regression checks for task-scoped execution and ephemeral session guidance."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ExecutionPolicyContractTests(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text()

    def test_account_kernel_does_not_ban_direct_delivery(self):
        text = self.read('docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md')
        self.assertNotIn('Your primary job is not to code', text)
        self.assertNotIn('No one-shot strategic builds', text)
        self.assertNotIn('## Required sequence for major programs', text)
        self.assertIn('same healthy turn', text)

    def test_account_kernel_has_no_permanent_web_principal(self):
        text = self.read('docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md')
        self.assertIn('A role is not a persistent conversation', text)
        self.assertIn('archived', text)
        self.assertIn('new session', text)
        self.assertIn('EFFECT_UNKNOWN', text)

    def test_native_entrypoints_do_not_hardcode_ceo_model(self):
        for path in ['AGENTS.md', 'CLAUDE.md']:
            with self.subTest(path=path):
                text = self.read(path)
                self.assertNotIn('AI CEO — GPT-5.6 Sol', text)
                self.assertNotIn('AI CEO **GPT-5.6 Sol**', text)
                self.assertIn('A role is not a persistent conversation', text)
                self.assertIn('source-only', text)

    def test_claude_source_does_not_command_forbidden_native_defaults(self):
        text = self.read('CLAUDE.md')
        self.assertNotIn('Bias toward delegating non-Opus subtasks to Sonnet/Haiku subagents', text)
        self.assertIn('existing admitted routing', text)

    def test_delivery_is_scoped_not_unconditional_service_restart(self):
        text = self.read('docs/DELIVERY_WORKFLOW.md')
        self.assertIn('Deploy only when the assigned change requires runtime rollout', text)
        self.assertIn('source-only', text)
        self.assertNotIn('merge_sha="$(git rev-parse origin/master)"', text)
        self.assertIn('mergeCommit.oid', text)

    def test_test_evidence_must_be_relevant_not_repeated_by_habit(self):
        text = self.read('docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md')
        self.assertIn('relevant source, input, dependency or acceptance requirement changes', text)
        self.assertIn('one proportionate review', text)

    def test_real_permissions_and_effect_fences_are_preserved(self):
        text = self.read('docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md')
        for invariant in ['explicit permission or safety refusal', 'human-only',
                          'release protections', 'active writer', 'EFFECT_UNKNOWN']:
            self.assertIn(invariant, text)


    def test_system_boundary_is_not_a_callable_approver(self):
        for path in ['docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md', 'AGENTS.md', 'CLAUDE.md']:
            with self.subTest(path=path):
                source = ' '.join(self.read(path).split())
                self.assertIn('An architectural owner is not a live session', source)
                self.assertIn('Data OS', source)
                self.assertIn('current assigned session', source)

    def test_blocker_has_an_action_not_a_department_name(self):
        source = ' '.join(self.read('docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md').split())
        self.assertIn('exact blocked action', source)
        self.assertIn('source-contract work', source)
        self.assertIn('not a new approval form', source)

    def test_web_kernel_removes_nonexistent_owner_dependency_within_budget(self):
        source = self.read('docs/sol_skills/BOOTSTRAP_KERNEL.md')
        kernel = source.split('```text\n', 1)[1].split('```', 1)[0]
        self.assertLessEqual(len(kernel), 8000)
        self.assertIn('system names are not live approvers', kernel)
        self.assertIn('actual missing evidence', kernel)

    def test_action_scoped_refusal_does_not_freeze_independent_work(self):
        active = ' '.join(self.read('docs/sol_skills/ACTIVE_EXECUTION.md').split())
        self.assertIn('Action-scoped refusal is not mission-wide refusal.', active)
        self.assertIn('genuinely separable in authority, target, and intended', active)
        self.assertIn('no replay of the denied effect', active)
        self.assertIn('`EFFECT_UNKNOWN` must be reconciled at the original target', active)


    def test_missing_implementation_is_not_mislabeled_permission_wait(self):
        for name in ('docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md', 'AGENTS.md', 'CLAUDE.md'):
            with self.subTest(path=name):
                text = ' '.join(self.read(name).split())
                self.assertTrue('Missing implementation is engineering work' in text,
                                name + ': distinguish unfinished code from human permission')
                self.assertTrue('enrollment alone' in text,
                                name + ': confirm the enabling path exists before enrollment is the next step')
                self.assertTrue('Do not remove refusal guards' in text,
                                name + ': repair the implementation, never counterfeit admission')


if __name__ == '__main__':
    unittest.main()
