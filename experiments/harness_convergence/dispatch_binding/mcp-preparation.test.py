"""Real patch preparation and refusal tests, using disposable input artifacts."""
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import prepare_mcp as owner


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='mcp-prepare-test-', dir=owner.CACHE)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cache = self.root / '.cache'
        for entry in owner.MANIFEST['files']:
            target = self.cache / entry['folder'] / entry['name']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(owner.CACHE / entry['folder'] / entry['name'], target)
        shutil.copyfile(owner.ROOT / owner.MANIFEST['patch_file'],
                        self.root / owner.MANIFEST['patch_file'])
        self.addCleanup(patch.stopall)
        patch.object(owner, 'ROOT', self.root).start()
        patch.object(owner, 'CACHE', self.cache).start()
        self.network = patch.object(owner.urllib.request, 'urlopen',
                                    side_effect=AssertionError('Offline preparation used network')).start()

    def tearDown(self):
        self.network.assert_not_called()

    def test_exact_patch_and_repeat_are_identical(self):
        first = owner.prepare()
        snapshot = {p.name: p.read_bytes() for p in (self.cache / 'mcp-donor').iterdir()}
        self.assertFalse(first['runtime_started'])
        self.assertEqual(first, owner.prepare())
        self.assertEqual(snapshot, {p.name: p.read_bytes() for p in (self.cache / 'mcp-donor').iterdir()})

    def test_changed_source_is_preserved_and_refused(self):
        target = self.cache / 'mcp-pristine/tools.ts'
        target.write_text('changed source\n')
        with self.assertRaisesRegex(ValueError, 'Donor identity mismatch'):
            owner.prepare()
        self.assertEqual(target.read_text(), 'changed source\n')

    def test_changed_patch_is_refused(self):
        (self.root / owner.MANIFEST['patch_file']).write_text('changed patch\n')
        with self.assertRaisesRegex(ValueError, 'patch digest mismatch'):
            owner.prepare()

    def test_changed_patched_artifact_is_not_overwritten(self):
        owner.prepare()
        target = self.cache / 'mcp-donor/tools.ts'
        target.write_text('changed artifact\n')
        with self.assertRaisesRegex(ValueError, 'Unexpected existing artifact'):
            owner.prepare()
        self.assertEqual(target.read_text(), 'changed artifact\n')

    def test_missing_source_never_downloads_implicitly(self):
        (self.cache / 'mcp-pristine/tools.ts').unlink()
        with self.assertRaises(FileNotFoundError):
            owner.prepare()

    def test_symlink_source_is_refused_without_following_it(self):
        target = self.cache / 'mcp-pristine/tools.ts'
        content = target.read_bytes()
        elsewhere = self.root / 'same-content.ts'
        elsewhere.write_bytes(content)
        target.unlink()
        target.symlink_to(elsewhere)
        with self.assertRaisesRegex(ValueError, 'must not be a symlink'):
            owner.prepare()
        self.assertTrue(target.is_symlink())
        self.assertEqual(elsewhere.read_bytes(), content)


if __name__ == '__main__':
    unittest.main(verbosity=2)
