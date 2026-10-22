"""Opt-in static completeness checks must not claim runtime admission."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/audit_execution_instructions.py'


class InstructionAuditCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.home = self.base / 'home'
        self.repo = self.base / 'repo'
        self.home.mkdir()
        self.repo.mkdir()

    def put(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def invoke(self, *extra):
        return subprocess.run(
            [sys.executable, str(SCRIPT), '--codex-home', str(self.home),
             '--repo-root', str(self.repo), *extra],
            text=True, capture_output=True, timeout=10, check=False,
        )

    def test_complete_check_returns_zero_but_never_runtime_verified(self):
        self.put(self.repo / 'AGENTS.md', 'Work in the assigned repository.\n')
        result = self.invoke('--check')
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report['completeness']['complete'])
        self.assertFalse(report['runtime_verified'])
        self.assertEqual(report['completeness']['scope'], 'STATIC_FILE_EVIDENCE_ONLY')

    def test_truncated_project_returns_one_with_machine_readable_evidence(self):
        self.put(self.home / 'config.toml', 'project_doc_max_bytes = 8\n')
        self.put(self.repo / 'AGENTS.md', '0123456789abcdef')
        result = self.invoke('--check')
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        finding = report['completeness']['findings'][0]
        self.assertEqual(finding['code'], 'PROJECT_BUDGET_TRUNCATION')
        self.assertEqual(finding['omitted_bytes'], 8)
        self.assertFalse(report['runtime_verified'])

    def test_default_report_mode_preserves_success_exit_and_reports_gap(self):
        self.put(self.home / 'config.toml', 'project_doc_max_bytes = 2\n')
        self.put(self.repo / 'AGENTS.md', 'abcdef')
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)['completeness']['complete'])

    def test_explicit_expected_brief_missing_returns_one(self):
        expected = self.put(self.base / 'expected.md', 'Required current guidance.')
        self.put(self.home / 'AGENTS.md', 'Other instructions.')
        result = self.invoke('--check', '--expected-brief', str(expected))
        self.assertEqual(result.returncode, 1, result.stderr)
        codes = [f['code'] for f in json.loads(result.stdout)['completeness']['findings']]
        self.assertIn('EXPECTED_BRIEF_NOT_ELIGIBLE', codes)

    def test_global_only_has_separate_budget_and_does_not_require_managed_block(self):
        self.put(self.home / 'config.toml', 'project_doc_max_bytes = 0\n')
        self.put(self.home / 'AGENTS.md', 'Global instructions are not project budget.')
        result = self.invoke('--check')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['completeness']['complete'])

    def test_scan_limit_is_incomplete_without_printing_content(self):
        self.put(self.home / 'AGENTS.md', 'x' * 65536 + 'private-tail-marker')
        result = self.invoke('--check')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn('private-tail-marker', result.stdout)
        codes = [f['code'] for f in json.loads(result.stdout)['completeness']['findings']]
        self.assertIn('CONTENT_SCAN_INCOMPLETE', codes)

    def test_check_never_edits_config_or_instructions(self):
        config = self.put(self.home / 'config.toml', 'project_doc_max_bytes = 3\n')
        doc = self.put(self.repo / 'AGENTS.md', 'longer instructions')
        before = [(p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) for p in (config, doc)]
        self.invoke('--check')
        after = [(p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) for p in (config, doc)]
        self.assertEqual(before, after)

    def test_nested_file_starved_by_budget_is_reported(self):
        self.put(self.home / 'config.toml', 'project_doc_max_bytes = 4\n')
        self.put(self.repo / 'AGENTS.md', 'root')
        nested = self.put(self.repo / 'pkg/AGENTS.md', 'child')
        result = self.invoke('--check', '--cwd', str(nested.parent))
        self.assertEqual(result.returncode, 1, result.stderr)
        findings = json.loads(result.stdout)['completeness']['findings']
        self.assertTrue(any(f['path'] == str(nested) and f['omitted_bytes'] == 5 for f in findings))

    def managed(self, text):
        return '<!-- mastermind-assigned-execution-v1 -->\n' + text + '\n<!-- /mastermind-assigned-execution-v1 -->\n'

    def test_malformed_selected_managed_block_is_reported(self):
        self.put(self.home / 'AGENTS.md', '<!-- mastermind-assigned-execution-v1 -->\nincomplete')
        result = self.invoke('--check')
        self.assertEqual(result.returncode, 1, result.stderr)
        codes = [f['code'] for f in json.loads(result.stdout)['completeness']['findings']]
        self.assertIn('MANAGED_BRIEF_MALFORMED', codes)

    def test_matching_expected_global_brief_is_complete(self):
        expected = self.put(self.base / 'expected.md', 'Current reviewed guidance.')
        self.put(self.home / 'AGENTS.md', self.managed(expected.read_text()))
        result = self.invoke('--check', '--expected-brief', str(expected))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['expected_brief_selected'])

    def test_selected_mismatch_is_not_hidden_by_another_matching_block(self):
        expected = self.put(self.base / 'expected.md', 'Current reviewed guidance.')
        self.put(self.home / 'AGENTS.md', self.managed('Older reviewed guidance.'))
        self.put(self.repo / 'AGENTS.md', self.managed(expected.read_text()))
        result = self.invoke('--check', '--expected-brief', str(expected))
        self.assertEqual(result.returncode, 1, result.stderr)
        codes = [f['code'] for f in json.loads(result.stdout)['completeness']['findings']]
        self.assertIn('EXPECTED_BRIEF_CONTENT_MISMATCH', codes)

    def test_unselected_additional_markdown_does_not_make_chain_incomplete(self):
        self.put(self.repo / 'AGENTS.md', 'Complete selected guidance.')
        extra = self.put(self.base / 'reference.md', 'x' * 65537)
        result = self.invoke('--check', '--additional-markdown', str(extra))
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report['additional_markdown'][0]['content_scan_truncated'])
        self.assertTrue(report['completeness']['complete'])


if __name__ == '__main__':
    unittest.main()
