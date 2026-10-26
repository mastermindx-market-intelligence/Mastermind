"""Hermetic source-only regression: never invoke the installed cleaner or any SSH command."""
import ast
import contextlib
import io
import json
import os
import shlex
import pathlib
import subprocess
import unittest
from unittest import mock

SOURCE = pathlib.Path(__file__).resolve().parents[1] / 'ops/fleet_storage_cleanup/pull_remote_archive.py'
TREE = ast.parse(SOURCE.read_text())
FIND = ast.literal_eval(next(n.value for n in TREE.body
    if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'FIND' for t in n.targets)))
FN = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == 'verified_probe_rows')
namespace = {'json': json, 'Path': pathlib.Path}
exec(compile(ast.Module(body=[FN], type_ignores=[]), str(SOURCE), 'exec'), namespace)
verified_probe_rows = namespace['verified_probe_rows']


class RemoteInventoryCompleteness(unittest.TestCase):
    def run_embed(self, bad=None, empty=False):
        seen = []
        def fake_run(argv, *args, **kwargs):
            name = argv[0]
            seen.append(name)
            self.assertIn(name, ('lsof', 'find', 'git', 'du'))
            if name == 'lsof':
                return subprocess.CompletedProcess(argv, int(bad == 'lsof'), 'n/other\n', '')
            if name == 'find':
                return subprocess.CompletedProcess(argv, int(bad == 'find'),
                    '' if empty else '/testroot/scripts/worktree_sparse.py\n', '')
            if name == 'git':
                return subprocess.CompletedProcess(argv, 1, '', '')
            if name == 'du':
                return subprocess.CompletedProcess(argv, int(bad == 'du'),
                    'INVALID' if bad == 'invalid_du' else '600000 /testroot\n', '')
            raise AssertionError('unreachable')
        out = io.StringIO()
        with mock.patch('subprocess.run', side_effect=fake_run),              mock.patch('os.path.isdir', return_value=True),              mock.patch('os.path.exists', side_effect=lambda path: not str(path).endswith('/.git')),              contextlib.redirect_stdout(out):
            if bad is None:
                exec(FIND, {})
            else:
                with self.assertRaises(RuntimeError):
                    exec(FIND, {})
        return out.getvalue(), seen

    def test_complete_empty_is_valid(self):
        out, seen = self.run_embed(empty=True)
        self.assertEqual(json.loads(out), [])
        self.assertIn('lsof', seen)
        self.assertIn('find', seen)

    def test_valid_candidate_keeps_true_size(self):
        out, seen = self.run_embed()
        self.assertEqual(json.loads(out), [{'path': '/testroot', 'kb': 600000}])
        self.assertIn('du', seen)

    def test_lsof_failure_refuses_even_if_find_would_be_empty(self):
        _, seen = self.run_embed(bad='lsof')
        self.assertEqual(seen, ['lsof'])

    def test_find_failure_refuses(self):
        _, seen = self.run_embed(bad='find')
        self.assertEqual(seen, ['lsof', 'find'])

    def test_du_failure_refuses(self):
        _, seen = self.run_embed(bad='du')
        self.assertIn('du', seen)

    def test_du_malformed_size_refuses(self):
        _, seen = self.run_embed(bad='invalid_du')
        self.assertIn('du', seen)


class ParentReceiptContract(unittest.TestCase):
    def test_empty_ssh_success_is_not_zero_inventory(self):
        for raw in ('', ' ', '\n'):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, 'no stdout'):
                verified_probe_rows(raw, 500)

    def test_explicit_complete_zero_is_only_valid_zero(self):
        self.assertEqual(verified_probe_rows('[]\n', 500), [])

    def test_valid_row_and_size_cutoff(self):
        rows = '[{"path":"/safe/orphan","kb":700000},{"path":"/small","kb":20}]'
        self.assertEqual(verified_probe_rows(rows, 500), [{'path':'/safe/orphan','kb':700000}])

    def test_wrong_shapes_fail_closed(self):
        invalid = ['{}', 'null', 'true', '[null]', '[123]',
                   '[{"path":"/safe","kb":false}]',
                   '[{"path":"/safe","kb":"700000"}]',
                   '[{"path":"/safe","kb":-1}]',
                   '[{"path":"relative","kb":700000}]',
                   '[{"path":"/safe/../unsafe","kb":700000}]',
                   '[{"path":"/unsafe\\nname","kb":700000}]', 'not json']
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises((ValueError, TypeError, KeyError)):
                verified_probe_rows(raw, 500)


class RemoteApplyShellArgumentSafety(unittest.TestCase):
    """Pure source regression: no SSH, filesystem deletion, or cleaner execution."""

    @classmethod
    def setUpClass(cls):
        funcs = [node for node in TREE.body if isinstance(node, ast.FunctionDef)
                 and node.name in ('remote_archive_command', 'remote_remove_command')]
        if len(funcs) != 2:
            raise AssertionError('both remote command builders must exist')
        ns = {'os': os, 'shlex': shlex}
        exec(compile(ast.Module(body=funcs, type_ignores=[]), str(SOURCE), 'exec'), ns)
        cls.archive_cmd = staticmethod(ns['remote_archive_command'])
        cls.remove_cmd = staticmethod(ns['remote_remove_command'])

    def test_metacharacters_and_dash_prefix_are_literal_arguments(self):
        for path in (
            '/private/tmp/scratch$(touch /tmp/forbidden)',
            '/private/tmp/scratch`touch-forbidden`',
            "/private/tmp/a'b",
            '/private/tmp/space with tabs',
            '/private/tmp/-rf',
            '/Users/example/lanes/name;echo-forbidden',
        ):
            with self.subTest(path=path):
                a = self.archive_cmd(path)
                r = self.remove_cmd(path)
                self.assertEqual(
                    a, 'tar -czf - -C ' + shlex.quote(os.path.dirname(path))
                       + ' -- ' + shlex.quote(os.path.basename(path)))
                self.assertEqual(r, 'rm -rf -- ' + shlex.quote(path))
                self.assertEqual(
                    shlex.split(a),
                    ['tar', '-czf', '-', '-C', os.path.dirname(path),
                     '--', os.path.basename(path)])
                self.assertEqual(shlex.split(r), ['rm', '-rf', '--', path])


if __name__ == '__main__':
    unittest.main()
