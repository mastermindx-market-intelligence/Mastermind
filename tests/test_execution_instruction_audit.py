"""Static instruction-loading evidence, never runtime admission or a gate."""
from pathlib import Path
import tempfile
import unittest

from scripts.audit_execution_instructions import codex_chain, inspect_markdown


class InstructionAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # macOS exposes /tmp through /private/tmp; compare canonical paths.
        self.home = Path(self.tmp.name).resolve() / 'provider'
        self.root = Path(self.tmp.name).resolve() / 'repo'
        self.home.mkdir()
        self.root.mkdir()

    def put(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def audit(self, cwd=None, **kwargs):
        return codex_chain(self.home, self.root, cwd or self.root, **kwargs)

    def test_global_override_wins_without_claiming_runtime_load(self):
        self.put(self.home / 'AGENTS.md', 'ordinary')
        winner = self.put(self.home / 'AGENTS.override.md', 'override')
        report = self.audit()
        self.assertEqual(report['chain'][0]['path'], str(winner))
        self.assertFalse(report['runtime_verified'])
        self.assertEqual(report['effect'], 'READ_ONLY')

    def test_empty_override_falls_back_to_nonempty_agents(self):
        self.put(self.home / 'AGENTS.override.md', '')
        winner = self.put(self.home / 'AGENTS.md', 'active')
        self.assertEqual(self.audit()['chain'][0]['path'], str(winner))

    def test_nested_rules_appear_after_repository_rules(self):
        outer = self.put(self.root / 'AGENTS.md', 'root')
        inner = self.put(self.root / 'pkg/AGENTS.md', 'nested')
        result = self.audit(self.root / 'pkg')
        self.assertEqual([x['path'] for x in result['chain']], [str(outer), str(inner)])

    def test_project_budget_is_shared_and_global_is_separate(self):
        self.put(self.home / 'AGENTS.md', 'global-long')
        self.put(self.root / 'AGENTS.md', '123456')
        self.put(self.root / 'pkg/AGENTS.md', 'abcdef')
        report = self.audit(self.root / 'pkg', project_max_bytes=8)
        self.assertEqual([x['eligible_bytes'] for x in report['chain']], [11, 6, 2])
        self.assertTrue(report['chain'][-1]['truncated_by_project_budget'])

    def test_exhausted_budget_still_reports_unselected_nested_file(self):
        self.put(self.root / 'AGENTS.md', '12345678')
        inner = self.put(self.root / 'pkg/AGENTS.md', 'not injected')
        report = self.audit(self.root / 'pkg', project_max_bytes=8)
        self.assertEqual(report['chain'][-1]['eligible_bytes'], 0)
        self.assertEqual(report['chain'][-1]['path'], str(inner))

    def test_fallback_does_not_override_standard_name(self):
        first = self.put(self.root / 'AGENTS.md', 'primary')
        self.put(self.root / 'TEAM.md', 'fallback')
        self.assertEqual(self.audit(fallback_names=['TEAM.md'])['chain'][0]['path'], str(first))

    def test_selected_fallback_is_reported(self):
        first = self.put(self.root / 'TEAM.md', 'fallback')
        self.assertEqual(self.audit(fallback_names=['TEAM.md'])['chain'][0]['path'], str(first))

    def test_cwd_outside_declared_repository_is_rejected(self):
        with self.assertRaises(ValueError):
            self.audit(self.home)

    def test_fallback_cannot_escape_directory(self):
        with self.assertRaises(ValueError):
            self.audit(fallback_names=['../other.md'])

    def test_audit_never_modifies_instruction_files(self):
        p = self.put(self.root / 'AGENTS.md', 'unchanged\n')
        before = (p.read_bytes(), p.stat().st_mtime_ns)
        self.audit()
        self.assertEqual((p.read_bytes(), p.stat().st_mtime_ns), before)

    def test_metadata_reports_stale_literal_without_emitting_file_content(self):
        p = self.put(self.root / 'CLAUDE.md', 'No one-shot strategic builds\nprivate unrelated prose\n')
        report = inspect_markdown(p)
        self.assertIn('blanket_one_shot_ban', report['legacy_signals'])
        self.assertNotIn('private unrelated prose', str(report))
        self.assertEqual(report['line_count'], 2)

    def test_non_markdown_target_is_rejected(self):
        p = self.put(self.root / 'credentials.json', '{}')
        with self.assertRaises(ValueError):
            inspect_markdown(p)


if __name__ == '__main__':
    unittest.main()

class ManagedBriefAuditTests(InstructionAuditTests):
    brief = 'Proceed with assigned work. Preserve real permission gates.'

    def block(self, body=None):
        return ('<!-- mastermind-assigned-execution-v1 -->\n' +
                (self.brief if body is None else body) +
                '\n<!-- /mastermind-assigned-execution-v1 -->\n')

    def test_marker_alone_is_not_complete_managed_brief(self):
        p = self.put(self.root / 'AGENTS.md', '<!-- mastermind-assigned-execution-v1 -->\nincomplete')
        r = inspect_markdown(p)
        self.assertEqual(r.get('execution_brief', {}).get('state'), 'MALFORMED')

    def test_balanced_block_has_digest_and_exact_offsets(self):
        data = 'é user preference\n' + self.block() + 'tail\n'
        p = self.put(self.root / 'AGENTS.md', data)
        r = inspect_markdown(p)
        b = r.get('execution_brief', {})
        self.assertEqual(b.get('state'), 'PRESENT_UNCOMPARED')
        self.assertEqual(b.get('start_byte'), len('é user preference\n'.encode()))
        self.assertEqual(b.get('end_byte'), len(('é user preference\n' + self.block()).encode()) - 1)
        self.assertEqual(b.get('body_sha256'), __import__('hashlib').sha256(self.brief.encode()).hexdigest())

    def test_budget_cut_cannot_claim_complete_brief_selection(self):
        self.put(self.root / 'AGENTS.md', 'x' * 100 + self.block())
        r = self.audit(project_max_bytes=20)['chain'][0]
        self.assertFalse(r.get('execution_brief_fully_eligible', True))
        self.assertFalse(r.get('assigned_execution_marker_eligible', True))

    def test_override_records_shadowed_expected_file(self):
        expected = self.put(self.home / 'AGENTS.md', self.block())
        self.put(self.home / 'AGENTS.override.md', 'old unrelated rules')
        r = self.audit()
        self.assertEqual(r.get('shadowed_files', [{}])[0].get('path'), str(expected))
        self.assertEqual(r.get('shadowed_files', [{}])[0].get('reason'), 'HIGHER_PRIORITY_FILENAME')
