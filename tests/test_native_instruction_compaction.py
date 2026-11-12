"""Compaction must remove bytes, not source custody, user text or real controls."""
import ast
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


C = load('native_instruction_compaction', 'scripts/native_instruction_compaction.py')


def block(marker, body):
    return f'<!-- {marker} -->\n{body}\n<!-- /{marker} -->'


class CompactionTests(unittest.TestCase):
    def setUp(self):
        self.old = block(C.MARKER, 'Existing reviewed source guidance.')
        self.brief = '# Compact execution\nPreserve real consent and EFFECT_UNKNOWN.\n'
        self.text = 'User prefix.\n' + self.old + '\nUser suffix.\n'
        self.marker = 'mastermind-leadership-continuity-20261024'
        self.retired = block(self.marker, 'Reviewed duplicate, not host policy.')

    def plan(self, text=None, **overrides):
        text = self.text if text is None else text
        args = dict(expected_preimage_sha256=C.digest(text),
                    expected_brief_sha256=C.digest(self.brief),
                    reviewed_managed_sha256=[C.digest(self.old)])
        args.update(overrides)
        return C.plan_compaction(text, self.brief, 'codex', **args)

    def test_replaces_only_reviewed_main_and_preserves_unknown_bytes(self):
        result = self.plan()
        self.assertTrue(result['text'].startswith('User prefix.\n'))
        self.assertTrue(result['text'].endswith('\nUser suffix.\n'))
        self.assertIn('EFFECT_UNKNOWN', result['text'])
        self.assertEqual(result['effect'], 'NONE')
        self.assertEqual(result['runtime_loading'], 'UNOBSERVED')
        self.assertEqual(result['runtime_behavior'], 'UNOBSERVED')

    def test_claude_has_the_same_safety_boundary(self):
        result = C.plan_compaction(self.text, self.brief, 'claude',
            expected_preimage_sha256=C.digest(self.text), expected_brief_sha256=C.digest(self.brief),
            reviewed_managed_sha256=[C.digest(self.old)])
        self.assertEqual(result['profile'], 'claude')
        self.assertEqual(result['text'], self.plan()['text'])

    def test_explicit_exact_block_retirement(self):
        text = self.text + self.retired + '\n'
        result = self.plan(text, retirements={self.marker: C.digest(self.retired)})
        self.assertNotIn(self.retired, result['text'])
        self.assertEqual(result['retired_blocks'][0]['sha256'], C.digest(self.retired))
        self.assertEqual(result['bytes_removed'], len(text.encode()) - len(result['text'].encode()))

    def test_named_but_unrequested_old_block_is_preserved(self):
        text = self.text + self.retired
        self.assertIn(self.retired, self.plan(text)['text'])

    def test_changed_old_block_cannot_be_retired(self):
        text = self.text + self.retired.replace('duplicate', 'NEW USER RULE')
        with self.assertRaisesRegex(ValueError, 'Historical block changed'):
            self.plan(text, retirements={self.marker: C.digest(self.retired)})

    def test_unknown_and_host_control_names_have_no_deletion_path(self):
        for marker in ['personal-policy', 'mastermind-external-worktree-storage',
                       'claude-parall-launch-isolation-20261019',
                       'mastermind-codex-continuity-harness-20261024', C.MARKER]:
            with self.subTest(marker=marker), self.assertRaisesRegex(ValueError, 'protected'):
                self.plan(retirements={marker: 'a' * 64})

    def test_reviewed_main_hash_is_required(self):
        with self.assertRaisesRegex(ValueError, 'reviewed preimage'):
            self.plan(reviewed_managed_sha256=['a' * 64])

    def test_stale_whole_file_preimage_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'preimage differs'):
            self.plan(expected_preimage_sha256='0' * 64)

    def test_changed_source_brief_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'source brief differs'):
            self.plan(expected_brief_sha256='0' * 64)

    def test_no_main_block_is_not_host_enrollment(self):
        with self.assertRaisesRegex(ValueError, 'does not enroll'):
            self.plan('Personal policy only.\n')

    def test_missing_retirement_is_idempotent(self):
        first = self.plan(self.text + self.retired, retirements={self.marker: C.digest(self.retired)})
        second = self.plan(first['text'], retirements={self.marker: C.digest(self.retired)})
        self.assertEqual(first['text'], second['text'])
        self.assertFalse(second['changed'])
        self.assertEqual(second['already_absent'], [self.marker])

    def test_repeated_main_preview_is_idempotent(self):
        first = self.plan()['text']
        self.assertEqual(first, self.plan(first)['text'])

    def test_duplicate_main_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.plan(self.text + self.old)

    def test_unbalanced_main_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Malformed'):
            self.plan(f'<!-- {C.MARKER} -->\nunknown')

    def test_reversed_main_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Reversed'):
            self.plan(f'<!-- /{C.MARKER} -->\n<!-- {C.MARKER} -->')

    def test_inline_markers_cannot_delete_quoted_user_text(self):
        with self.assertRaisesRegex(ValueError, 'standalone'):
            self.plan('Quoted ' + self.old)

    def test_nested_comment_in_main_is_preserved_by_refusal(self):
        nested = block(C.MARKER, 'new <!-- private --> rule')
        with self.assertRaisesRegex(ValueError, 'Nested'):
            self.plan(nested, reviewed_managed_sha256=[C.digest(nested)])

    def test_nested_retirement_is_rejected(self):
        old = block(self.marker, '<!-- personal --> unknown <!-- /personal -->')
        with self.assertRaisesRegex(ValueError, 'Nested'):
            self.plan(self.text + old, retirements={self.marker: C.digest(old)})

    def test_fenced_main_example_is_not_an_installed_block(self):
        for fence in ['```', '~~~~', '   ```markdown']:
            text = fence + '\n' + self.old + '\n```\n'
            with self.subTest(fence=fence), self.assertRaisesRegex(ValueError, 'fenced'):
                self.plan(text)

    def test_fenced_retirement_example_is_not_deleted(self):
        text = self.text + '\n```markdown\n' + self.retired + '\n```\n'
        with self.assertRaisesRegex(ValueError, 'fenced'):
            self.plan(text, retirements={self.marker: C.digest(self.retired)})

    def test_unclosed_fence_before_main_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'fenced'):
            self.plan('~~~markdown\nExample\n' + self.old)

    def test_shorter_closer_does_not_end_long_fence(self):
        with self.assertRaisesRegex(ValueError, 'fenced'):
            self.plan('````markdown\n```\n' + self.old + '\n````\n')

    def test_other_fence_kind_does_not_end_open_fence(self):
        with self.assertRaisesRegex(ValueError, 'fenced'):
            self.plan('~~~markdown\n```\n' + self.old + '\n~~~\n')

    def test_closer_with_info_text_does_not_end_fence(self):
        with self.assertRaisesRegex(ValueError, 'fenced'):
            self.plan('```markdown\n```not-a-close\n' + self.old + '\n```\n')

    def test_closed_fence_before_real_block_is_preserved(self):
        for prefix in ['```md\nExample\n```\n', '~~~\nExample\n~~~~\n',
                       '   ````md\n```\n   ````\n']:
            with self.subTest(prefix=prefix):
                result = self.plan(prefix + self.text)
                self.assertTrue(result['text'].startswith(prefix + 'User prefix.\n'))

    def test_fenced_main_body_without_markers_remains_supported(self):
        old = block(C.MARKER, 'Example:\n```bash\necho sample\n```\nDone.')
        result = self.plan(old + '\nTail\n', reviewed_managed_sha256=[C.digest(old)])
        self.assertTrue(result['text'].endswith('\nTail\n'))

    def test_crlf_unknown_content_is_byte_preserved(self):
        text = 'User\r\n' + self.old.replace('\n', '\r\n') + '\r\nTail\r\n'
        reviewed = self.old.replace('\n', '\r\n')
        out = self.plan(text, reviewed_managed_sha256=[C.digest(reviewed)])['text']
        self.assertTrue(out.startswith('User\r\n'))
        self.assertTrue(out.endswith('\r\nTail\r\n'))

    def test_utf8_byte_accounting_not_character_count(self):
        result = self.plan(self.text + '\u4fdd\u7559\u89c4\u5219\n')
        self.assertEqual(result['after_bytes'], len(result['text'].encode('utf-8')))
        self.assertGreater(result['after_bytes'], len(result['text']))

    def test_automatic_import_is_not_claimed_as_compaction(self):
        for text in ['@long-policy.md\n', '  @/absolute/policy.md\n']:
            with self.subTest(text=text):
                self.brief = text
                with self.assertRaisesRegex(ValueError, 'automatic imports'):
                    self.plan()

    def test_comment_in_replacement_is_rejected(self):
        self.brief = 'Keep <!-- another-block --> private rules.'
        with self.assertRaisesRegex(ValueError, 'managed comments'):
            self.plan()

    def test_byte_target_is_a_source_authoring_limit_not_runtime_gate(self):
        self.brief = 'x' * (C.BRIEF_TARGET_BYTES + 1)
        with self.assertRaisesRegex(ValueError, 'authoring byte target'):
            self.plan()
        report = C.inspect_text('x' * 9000)
        self.assertEqual(report['effect'], 'NONE')
        self.assertIn('ABOVE_ADVISORY_BYTE_TARGET', report['findings'])

    def test_empty_brief_is_rejected(self):
        self.brief = ' \n'
        with self.assertRaisesRegex(ValueError, 'empty'):
            self.plan()

    def test_bad_digest_types_and_values(self):
        for value in [None, False, '', 'A' * 64, 'x' * 64]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.plan(expected_preimage_sha256=value)

    def test_bad_reviewed_identity_sequence(self):
        for value in ['a' * 64, None, [True], [0], ['A' * 64]]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.plan(reviewed_managed_sha256=value)

    def test_bad_retirement_mapping_and_digest(self):
        for value in [[], [(self.marker, 'a' * 64)], {self.marker: None}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.plan(retirements=value)

    def test_oversized_or_nontext_input_is_rejected(self):
        for text in [None, b'not text', 'x' * (C.MAX_INPUT_BYTES + 1)]:
            with self.subTest(kind=type(text).__name__), self.assertRaises(ValueError):
                C.plan_compaction(text, self.brief, 'codex', expected_preimage_sha256='a' * 64,
                    expected_brief_sha256=C.digest(self.brief), reviewed_managed_sha256=[])

    def test_wrong_profile_is_rejected(self):
        with self.assertRaises(ValueError):
            C.plan_compaction(self.text, self.brief, 'memory',
                expected_preimage_sha256=C.digest(self.text),
                expected_brief_sha256=C.digest(self.brief), reviewed_managed_sha256=[])

    def test_advisories_do_not_assert_mount_or_permission(self):
        result = C.inspect_text('### TEMPORARY OVERRIDE\nIndependent REVIEW is still required.\n@large.md\n')
        self.assertIn('CONDITIONAL_STORAGE_EXCEPTION', result['findings'])
        self.assertIn('BLANKET_REVIEW_WORDING', result['findings'])
        self.assertIn('AUTO_IMPORT_REQUIRES_LOAD_AUDIT', result['findings'])
        self.assertEqual(result['runtime_behavior'], 'UNOBSERVED')
        self.assertNotIn('allowed', result)
        self.assertNotIn('mount_state', result)

    def test_bad_advisory_targets(self):
        for value in [True, 0, -1, '8', None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                C.inspect_text('text', target_bytes=value)


class SourceContractTests(unittest.TestCase):
    def test_compact_source_budget_and_no_auto_imports(self):
        text = (ROOT / 'docs/NATIVE_EXECUTION_BRIEF.md').read_text()
        self.assertLessEqual(len(text.encode('utf-8')), C.BRIEF_TARGET_BYTES)
        self.assertLess(len(text.splitlines()), 200)
        self.assertNotIn('AUTO_IMPORT_REQUIRES_LOAD_AUDIT', C.inspect_text(text)['findings'])

    def test_core_semantic_boundaries_stay_immediate(self):
        text = (ROOT / 'docs/NATIVE_EXECUTION_BRIEF.md').read_text()
        for requirement in ['EFFECT_UNKNOWN', 'same healthy turn', 'current direct',
                            'protected queue', 'merge-on-green', 'not a stop',
                            'SELF_REVIEWED', 'not automatically formal',
                            'not governing law', 'Do not preload',
                            'one commit', 'not worker START', 'Codex/Work',
                            'no blanket independent', 'independent release',
                            'actual protected release path', 'No new paid credits',
                            'COMMERCIAL_DATA_RIGHTS.md', 'DO_NOT_REDO']:
            with self.subTest(requirement=requirement):
                self.assertIn(requirement.lower(), text.lower())

    def test_renderer_has_no_effect_primitives(self):
        tree = ast.parse((ROOT / 'scripts/native_instruction_compaction.py').read_text())
        imports = {a.name.split('.')[0] for node in ast.walk(tree)
                   if isinstance(node, (ast.Import, ast.ImportFrom))
                   for a in node.names}
        modules = {node.module.split('.')[0] for node in ast.walk(tree)
                   if isinstance(node, ast.ImportFrom) and node.module}
        self.assertFalse((imports | modules) & {'os', 'pathlib', 'subprocess', 'socket', 'requests', 'urllib'})
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, {'open', 'exec', 'eval', 'compile', '__import__'})


class ExistingWriterIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.writer = load('existing_execution_brief_writer', 'scripts/project_execution_brief.py')

    def test_existing_writer_applies_plan_with_private_backup_and_exact_readback(self):
        old = block(C.MARKER, 'Previously reviewed source.') + '\nHost guard remains.\n'
        brief = 'New compact instructions.\n'
        plan = C.plan_compaction(old, brief, 'codex', expected_preimage_sha256=C.digest(old),
            expected_brief_sha256=C.digest(brief),
            reviewed_managed_sha256=[C.digest(block(C.MARKER, 'Previously reviewed source.'))])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); target = root / 'AGENTS.md'; target.write_text(old)
            receipt = self.writer.apply(target, plan['text'], plan['before_sha256'], root / 'backups')
            self.assertEqual(receipt['after_sha256'], plan['after_sha256'])
            self.assertEqual(target.read_text(), plan['text'])
            self.assertEqual(Path(receipt['backup']).read_text(), old)
            self.assertEqual(Path(receipt['backup']).stat().st_mode & 0o777, 0o600)
            repeated = self.writer.apply(target, plan['text'], plan['after_sha256'], root / 'backups')
            self.assertFalse(repeated['changed'])

    def test_concurrent_target_change_is_rejected_by_existing_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); target = root / 'CLAUDE.md'; target.write_text('Newer user instructions.')
            with self.assertRaisesRegex(ValueError, 'preimage'):
                self.writer.apply(target, 'Replacement', C.digest('Old instructions.'), root / 'backups')
            self.assertEqual(target.read_text(), 'Newer user instructions.')

    def test_symlink_refused_without_mutating_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); actual = root / 'actual.md'; actual.write_text('preserve')
            target = root / 'AGENTS.md'; target.symlink_to(actual)
            with self.assertRaises(ValueError):
                self.writer.apply(target, 'replace', C.digest('preserve'), root / 'backups')
            self.assertEqual(actual.read_text(), 'preserve')

    def test_backup_disagreement_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); target = root / 'AGENTS.md'; target.write_text('original')
            backup = root / 'backups'; backup.mkdir()
            identity = self.writer.digest(str(target.absolute()).encode())[:16]
            (backup / f'{identity}-{C.digest("original")}.md').write_text('different')
            with self.assertRaisesRegex(ValueError, 'backup disagrees'):
                self.writer.apply(target, 'replacement', C.digest('original'), backup)
            self.assertEqual(target.read_text(), 'original')

    def test_rollback_uses_current_after_hash_and_existing_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); target = root / 'CLAUDE.md'; target.write_text('before')
            first = self.writer.apply(target, 'after', C.digest('before'), root / 'backups')
            restored = self.writer.apply(target, Path(first['backup']).read_text(),
                                         first['after_sha256'], root / 'backups')
            self.assertEqual(restored['after_sha256'], first['before_sha256'])
            self.assertEqual(target.read_text(), 'before')


if __name__ == '__main__':
    unittest.main()
