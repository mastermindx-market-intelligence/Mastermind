"""Markdown-only projection must preserve real guards and unrelated user content."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('execution_brief_projection', ROOT / 'scripts/project_execution_brief.py')


class ProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assert_source_exists = SPEC.origin

    def module(self):
        self.assertTrue(Path(SPEC.origin).is_file(), 'Markdown projection utility is not implemented')
        mod = importlib.util.module_from_spec(SPEC)
        SPEC.loader.exec_module(mod)
        return mod

    def test_removes_only_named_obsolete_claude_blocks(self):
        mod = self.module()
        old = ('Personal preference stays.\n'
               '<!-- mastermind-ceo-forward-execution -->\nold duplicate\n<!-- /mastermind-ceo-forward-execution -->\n'
               '<!-- mastermind-claude-fabric-routing -->\nNative model restriction stays.\n<!-- /mastermind-claude-fabric-routing -->\n')
        new = mod.project(old, 'Current brief.', 'claude')
        self.assertNotIn('old duplicate', new)
        self.assertIn('Native model restriction stays.', new)
        self.assertIn('Personal preference stays.', new)
        self.assertIn('Current brief.', new)

    def test_codex_keeps_modal_and_transport_instructions(self):
        mod = self.module()
        old = ('# Execution-first defaults for assigned work\nold intro\n'
               '## Act under the assignment\nold duplicate\n'
               '## Codex Desktop inter-thread approval discipline\nReal modal must be respected.\n'
               '## Repair real failures; scope real barriers\nold repeated section\n'
               '## Installed Fabric adapter operations\nExact admitted carrier stays.\n'
               '## Unrelated user section\nUser data stays.\n')
        new = mod.project(old, 'Current brief.', 'codex')
        self.assertNotIn('old duplicate', new)
        self.assertNotIn('old repeated section', new)
        self.assertIn('Real modal must be respected.', new)
        self.assertIn('Exact admitted carrier stays.', new)
        self.assertIn('User data stays.', new)

    def test_codex_preserves_unknown_preamble_under_legacy_heading(self):
        mod = self.module()
        old = ('# Execution-first defaults for assigned work\n'
               'User-specific recovery location: /safe/current-checkpoint.md\n\n'
               '## Act under the assignment\nRetired duplicate.\n'
               '## Personal note\nKeep this too.\n')
        first = mod.project(old, 'Current brief.', 'codex')
        self.assertIn('User-specific recovery location: /safe/current-checkpoint.md', first)
        self.assertIn('Keep this too.', first)
        self.assertNotIn('Retired duplicate.', first)
        self.assertEqual(mod.project(first, 'Current brief.', 'codex'), first)

    def test_codex_legacy_heading_without_sections_preserves_its_body(self):
        mod = self.module()
        old = '# Execution-first defaults for assigned work\nA personal instruction must survive.\n'
        new = mod.project(old, 'Current brief.', 'codex')
        self.assertIn('A personal instruction must survive.', new)

    def test_projection_is_idempotent(self):
        mod = self.module()
        for profile in ['codex', 'claude', 'memory']:
            first = mod.project('Existing content.\n', 'Brief.', profile)
            self.assertEqual(mod.project(first, 'Brief.', profile), first)


    def test_current_owner_takeover_block_replaced_not_duplicated(self):
        mod = self.module()
        marker = 'mastermind-active-owner-takeover-20261102'
        old = ('# Local host storage restrictions\n'
               'Never use internal SSD for worktrees.\n'
               f'<!-- {marker} -->\n'
               'Old rollout owner guidance; do not keep a second copy.\n'
               f'<!-- /{marker} -->\n'
               '<!-- non-mastermind-host-policy -->\n'
               'Local SSH policy stays.\n'
               '<!-- /non-mastermind-host-policy -->\n')
        for profile in ('codex', 'claude'):
            brief = 'Active assigned session owns recovery and protects EFFECT_UNKNOWN.'
            first = mod.project(old, brief, profile)
            self.assertNotIn('Old rollout owner guidance', first)
            self.assertNotIn(marker, first)
            self.assertEqual(first.count('<!-- mastermind-assigned-execution-v1 -->'), 1)
            self.assertIn('Never use internal SSD for worktrees.', first)
            self.assertIn('Local SSH policy stays.', first)
            self.assertIn('Active assigned session owns recovery', first)
            self.assertEqual(mod.project(first, brief, profile), first)

    def test_unbalanced_new_owner_block_fails_closed(self):
        mod = self.module()
        for profile in ('codex', 'claude'):
            with self.assertRaises(ValueError):
                mod.project('<!-- mastermind-active-owner-takeover-20261102 -->\nUnbalanced',
                            'Current brief.', profile)

    def test_continuity_review_sentence_updated_without_removing_host_controls(self):
        mod = self.module()
        marker = 'mastermind-leadership-continuity-20261024'
        obsolete = ('Independent REVIEW is still\n   required from any fresh '
                    'non-authoring reviewer (never a specific named owner); never\n   '
                    'self-merge or self-approve.')
        old = (f'<!-- {marker} -->\nLeadership and EFFECT_UNKNOWN stay.\n'
               f'{obsolete}\nNo purchases or paid credits.\n<!-- /{marker} -->\n'
               f'Personal quotation: {obsolete}\n')
        for profile in ('codex', 'claude'):
            new = mod.project(old, 'Current brief.', profile)
            managed = new.split(f'<!-- {marker} -->', 1)[1].split(
                f'<!-- /{marker} -->', 1)[0]
            self.assertNotIn(obsolete, managed)
            self.assertIn('ordinary self-check and protected automation', managed)
            self.assertIn('native/automatic CRITICAL requires one distinct technical review', managed)
            self.assertIn('attended Web all-tier waiver remains', managed)
            self.assertIn('no self-merge outside the protected controller', managed)
            self.assertIn('Leadership and EFFECT_UNKNOWN stay.', managed)
            self.assertIn('No purchases or paid credits.', managed)
            self.assertIn(f'Personal quotation: {obsolete}', new)
            self.assertEqual(mod.project(new, 'Current brief.', profile), new)

    def test_unbalanced_continuity_block_fails_closed(self):
        mod = self.module()
        with self.assertRaises(ValueError):
            mod.project('<!-- mastermind-leadership-continuity-20261024 -->',
                        'Current brief.', 'codex')

    def test_memory_preserves_header_and_historical_effects(self):
        mod = self.module()
        old = 'v1\n\n## History\nEFFECT_UNKNOWN: operation-123 needs reconciliation.\n'
        new = mod.project(old, 'Brief.', 'memory')
        self.assertTrue(new.startswith('v1\n'))
        self.assertIn('EFFECT_UNKNOWN: operation-123 needs reconciliation.', new)
        self.assertIn('historical evidence', new)
        self.assertIn('not live authority', new)
        self.assertIn('without mandatory independent review', new)
        self.assertNotIn('one proportionate review', new)

    def test_unbalanced_marker_is_not_silently_deleted(self):
        mod = self.module()
        with self.assertRaises(ValueError):
            mod.project('<!-- mastermind-ceo-forward-execution -->\nunknown end', 'Brief.', 'claude')

    def test_duplicate_managed_block_requires_reconciliation(self):
        mod = self.module()
        block = '<!-- mastermind-assigned-execution-v1 -->\nx\n<!-- /mastermind-assigned-execution-v1 -->\n'
        with self.assertRaises(ValueError):
            mod.project(block + block, 'Brief.', 'codex')

    def test_write_requires_exact_preimage_and_preserves_backup(self):
        mod = self.module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); target = root / 'AGENTS.md'; target.write_text('original\n')
            with self.assertRaises(ValueError):
                mod.apply(target, 'new\n', '0' * 64, root / 'backups')
            self.assertEqual(target.read_text(), 'original\n')
            receipt = mod.apply(target, 'new\n', mod.digest(b'original\n'), root / 'backups')
            self.assertEqual(target.read_text(), 'new\n')
            self.assertEqual(Path(receipt['backup']).read_text(), 'original\n')
            self.assertEqual(receipt['after_sha256'], mod.digest(target.read_bytes()))

    def test_non_markdown_and_symlink_targets_refused(self):
        mod = self.module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); target = root / 'settings.json'; target.write_text('{}')
            with self.assertRaises(ValueError):
                mod.apply(target, 'changed', mod.digest(b'{}'), root / 'backups')
            actual = root / 'actual.md'; actual.write_text('old')
            link = root / 'AGENTS.md'; link.symlink_to(actual)
            with self.assertRaises(ValueError):
                mod.apply(link, 'new', mod.digest(b'old'), root / 'backups')
            self.assertEqual(actual.read_text(), 'old')


if __name__ == '__main__':
    unittest.main()
