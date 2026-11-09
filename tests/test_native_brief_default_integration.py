"""Source-only default-selection/fence regressions; no installed paths."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('candidate_writer', ROOT / 'scripts/project_execution_brief.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def block(name, body):
    return f'<!-- {name} -->\n{body}\n<!-- /{name} -->'


class MarkerSelectionTests(unittest.TestCase):
    def test_fenced_current_marker_refused(self):
        for profile in ['codex', 'claude', 'memory']:
            marker = M.MEMORY_MARKER if profile == 'memory' else M.MARKER
            for fence in ['```markdown', '~~~', '   ````']:
                with self.subTest(profile=profile, fence=fence), self.assertRaisesRegex(ValueError, 'fenced'):
                    M.project(fence + '\n' + block(marker, 'Example') + '\n```\n', 'New', profile)

    def test_every_fenced_legacy_marker_is_preserved_by_refusal(self):
        for name in M.LEGACY_BLOCKS:
            for profile in ['codex', 'claude']:
                with self.subTest(name=name, profile=profile), self.assertRaisesRegex(ValueError, 'fenced'):
                    M.project('```\n' + block(name, 'Do not delete sample') + '\n```', 'New', profile)

    def test_fenced_supplier_continuity_block_is_refused(self):
        old = block('mastermind-leadership-continuity-20261024', 'Independent REVIEW is still required.')
        for profile in ['codex', 'claude']:
            with self.subTest(profile=profile), self.assertRaisesRegex(ValueError, 'fenced'):
                M.project('```md\n' + old + '\n```', 'New', profile)

    def test_incomplete_short_and_wrong_fence_closers_refused(self):
        for prefix in ['~~~\n', '````\n```\n', '```\n~~~\n', '```\n```info\n']:
            with self.subTest(prefix=prefix), self.assertRaisesRegex(ValueError, 'fenced'):
                M.project(prefix + block(M.MARKER, 'Example'), 'New', 'codex')

    def test_real_block_after_closed_fence_works(self):
        prefix = '```md\nOrdinary documentation\n```\n'
        out = M.project(prefix + block(M.MARKER, 'Old') + '\nUnknown tail', 'New', 'codex')
        self.assertIn(prefix, out)
        self.assertIn('Unknown tail', out)
        self.assertIn('New', out)

    def test_fenced_commands_in_real_managed_body_work(self):
        old = block(M.MARKER, 'Commands:\n```sh\necho example\n```')
        self.assertIn('New', M.project(old, 'New', 'claude'))

    def test_inline_marker_is_not_a_managed_block(self):
        with self.assertRaisesRegex(ValueError, 'standalone'):
            M.project('Quoted ' + block(M.MARKER, 'Old'), 'New', 'codex')

    def test_nested_unknown_comment_is_not_silently_deleted(self):
        with self.assertRaisesRegex(ValueError, 'Nested'):
            M.project(block(M.MARKER, 'Host <!-- personal --> rule'), 'New', 'codex')

    def test_crlf_real_block_and_unknown_tail_preserved(self):
        old = block(M.MARKER, 'Old').replace('\n', '\r\n')
        out = M.project(old + '\r\nUnknown unicode: \u4fdd\u7559', 'New', 'claude')
        self.assertIn('Unknown unicode: \u4fdd\u7559', out)
        self.assertEqual(out.count('<!-- ' + M.MARKER + ' -->'), 1)


class LegacyHeadingTests(unittest.TestCase):
    def test_quoted_legacy_title_is_not_an_installed_section(self):
        text = '```md\n# Execution-first defaults for assigned work\n## Act under the assignment\nSample only\n```'
        with self.assertRaisesRegex(ValueError, 'fenced'):
            M.project(text, 'New', 'codex')

    def test_quoted_named_legacy_section_is_not_removed(self):
        text = '# Execution-first defaults for assigned work\nUnknown preamble\n```md\n## Act under the assignment\nSample only\n```'
        with self.assertRaisesRegex(ValueError, 'fenced'):
            M.project(text, 'New', 'codex')

    def test_inline_legacy_title_is_not_an_installed_heading(self):
        with self.assertRaisesRegex(ValueError, 'standalone'):
            M.project('User quotation: # Execution-first defaults for assigned work', 'New', 'codex')

    def test_unrelated_fenced_heading_stays_byte_intact(self):
        example = '```md\n## Unclassified example\nKeep every byte\n```'
        text = '# Execution-first defaults for assigned work\n' + example
        self.assertIn(example, M.project(text, 'New', 'codex'))


class NativeDefaultCliTests(unittest.TestCase):
    def invoke(self, path, profile, *extra):
        return subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/project_execution_brief.py'),
            '--path', str(path), '--profile', profile, *extra],
            text=True, capture_output=True, timeout=20, cwd=path.parent)

    def test_both_native_defaults_select_compact_source_and_preview_does_not_write(self):
        brief = (ROOT / 'docs/NATIVE_EXECUTION_BRIEF.md').read_text()
        for profile in ['codex', 'claude']:
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'instructions.md'; old = 'Host-specific content.\n'; path.write_text(old)
                result = self.invoke(path, profile)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                expected = M.project(old, brief, profile)
                self.assertEqual(report['after_sha256'], M.digest(expected.encode()))
                self.assertEqual(report['after_bytes'], len(expected.encode()))
                self.assertTrue(report['preview_only'])
                self.assertEqual(path.read_text(), old)

    def test_explicit_native_brief_override_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / 'instructions.md'; path.write_text('Host content')
            brief = root / 'selected.md'; brief.write_text('Explicit current source.')
            result = self.invoke(path, 'claude', '--brief', str(brief))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['after_sha256'],
                M.digest(M.project('Host content', brief.read_text(), 'claude').encode()))

    def test_memory_uses_builtin_notice_not_native_or_missing_brief(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / 'memory.md'; original = 'v1\nHistorical evidence'; path.write_text(original)
            result = self.invoke(path, 'memory', '--brief', str(root / 'nonexistent.md'))
            self.assertEqual(result.returncode, 0, result.stderr)
            expected = M.project(original, '', 'memory')
            self.assertEqual(json.loads(result.stdout)['after_sha256'], M.digest(expected.encode()))
            self.assertTrue(expected.startswith('v1\n'))
            self.assertEqual(path.read_text(), original)

    def test_actual_cli_apply_readback_backup_idempotence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / 'instructions.md'; old = 'Host content survives.\n'; path.write_text(old)
            result = self.invoke(path, 'codex', '--apply', '--expected-sha256', M.digest(old.encode()),
                                 '--backup-dir', str(root / 'backup'))
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertEqual(Path(receipt['backup']).read_text(), old)
            self.assertIn('Host content survives.', path.read_text())
            self.assertEqual(M.digest(path.read_bytes()), receipt['after_sha256'])
            again = self.invoke(path, 'codex', '--apply', '--expected-sha256', receipt['after_sha256'],
                                '--backup-dir', str(root / 'backup'))
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertFalse(json.loads(again.stdout)['changed'])

    def test_actual_cli_fenced_refusal_leaves_target_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / 'instructions.md'
            original = '```md\n' + block(M.MARKER, 'Only a sample') + '\n```';path.write_text(original)
            result = self.invoke(path, 'claude', '--apply', '--expected-sha256', M.digest(original.encode()),
                                 '--backup-dir', str(root / 'backup'))
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(path.read_text(), original)
            self.assertFalse((root / 'backup').exists())


class CreateTargetCliTests(unittest.TestCase):
    def invoke(self, path, profile, *extra):
        return subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/project_execution_brief.py'),
            '--path', str(path), '--profile', profile, *extra],
            text=True, capture_output=True, timeout=20, cwd=path.parent if path.parent.is_dir() else Path(directory := tempfile.gettempdir()))

    def test_missing_target_refused_without_explicit_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'instructions.md'
            result = self.invoke(path, 'claude')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('--create-target', result.stderr)
            self.assertFalse(path.exists())

    def test_create_preview_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'instructions.md'
            result = self.invoke(path, 'claude', '--create-target')
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report['preview_only'])
            self.assertTrue(report['would_create'])
            self.assertFalse(path.exists())

    def test_create_apply_installs_block_with_readback_and_stays_idempotent(self):
        brief = (ROOT / 'docs/NATIVE_EXECUTION_BRIEF.md').read_text()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'instructions.md'
            result = self.invoke(path, 'claude', '--create-target', '--apply',
                                 '--backup-dir', str(root / 'backup'))
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertTrue(receipt['created'])
            self.assertIsNone(receipt['backup'])
            expected = M.project('', brief, 'claude')
            self.assertEqual(receipt['after_sha256'], M.digest(expected.encode()))
            self.assertEqual(path.read_text(), expected)
            self.assertTrue(expected.startswith('<!-- ' + M.MARKER + ' -->\n# '))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            again = self.invoke(path, 'claude', '--create-target', '--apply',
                                '--expected-sha256', receipt['after_sha256'],
                                '--backup-dir', str(root / 'backup'))
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertFalse(json.loads(again.stdout)['changed'])
            self.assertEqual(path.read_text(), expected)

    def test_create_refuses_preimage_memory_profile_and_missing_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'instructions.md'
            refused = self.invoke(path, 'claude', '--create-target', '--apply',
                                  '--expected-sha256', '0' * 64, '--backup-dir', str(root / 'backup'))
            self.assertNotEqual(refused.returncode, 0)
            self.assertFalse(path.exists())
            memory = self.invoke(path, 'memory', '--create-target')
            self.assertNotEqual(memory.returncode, 0)
            self.assertFalse(path.exists())
            orphan = self.invoke(root / 'missing' / 'instructions.md', 'claude',
                                 '--create-target', '--apply', '--backup-dir', str(root / 'backup'))
            self.assertNotEqual(orphan.returncode, 0)
            self.assertFalse((root / 'missing').exists())


if __name__ == '__main__':
    unittest.main()
