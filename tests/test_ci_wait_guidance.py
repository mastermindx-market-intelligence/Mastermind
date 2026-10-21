"""Real guard decisions plus instruction/installer contracts, not model-behavior proof."""
import ast
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import install_ci_wait_guidance as installer

FIXTURE = installer.ROOT / 'research/execution_friction_20261011/fixtures/installed_routing_guard.py'


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        source = FIXTURE.read_text()
        if not os.environ.get('MMX_TEST_ORIGINAL_GUIDANCE'):
            source = installer.render('guard', source)
        self.guard = {'__name__': 'test_guard'}
        exec(compile(source, str(FIXTURE), 'exec'), self.guard)
        self.guard['POLL_STATE_DIR'] = self.tmp.name
        self.payload = {'session_id': 'test-original-root', 'turn_id': 'turn',
                        'cwd': '/Users/chriswong/Documents/Cluade/Mastermind'}
        self.command = 'gh run view 38544421037 --repo example/repo --json status,conclusion'

    def read(self, now, command=None):
        return self.guard['_repeat_poll_reason'](self.payload, command or self.command, now)

    def invoke(self, command):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit):
            self.guard['guard_bash'](self.payload, {'command': command})
        return json.loads(output.getvalue())['hookSpecificOutput']

    def test_read_is_allowed_after_original_window_not_last_denial(self):
        self.assertIsNone(self.read(1000))
        self.assertIsNotNone(self.read(1100))
        self.assertIsNotNone(self.read(1299))
        self.assertIsNone(self.read(1300))
        self.assertIsNotNone(self.read(1301))

    def test_api_alias_does_not_escape_same_run_cooldown(self):
        self.read(1000)
        self.assertIsNotNone(self.read(1001, 'gh api repos/example/repo/actions/runs/38544421037'))

    def test_another_run_does_not_inherit_old_run_hold(self):
        self.read(1000)
        self.assertIsNone(self.read(1001, 'gh run view 42 --json status'))

    def test_message_explains_finite_scope_and_no_bypass(self):
        self.read(1000)
        reason = self.read(1001)
        for phrase in ('READ_COOLDOWN_ONLY', 'not a permanent permission denial',
                       'same-carrier', 'after expiry', 'genuine permission',
                       'Do not sleep/retry, switch readers, reset guard state, or mutate'):
            self.assertIn(phrase, reason)
        self.assertNotIn('Do not wait for the timer', reason)

    def test_admission_does_not_claim_a_running_watcher(self):
        result = self.invoke('gh run watch 42 --interval 150 --exit-status')
        self.assertNotIn('permissionDecision', result)
        message = result['additionalContext']
        self.assertIn('launch is NOT yet verified', message)
        self.assertIn('supported result-consumption path', message)
        self.assertNotIn('ARMED ASYNC', message)

    def test_real_mutation_refusal_remains_a_denial(self):
        result = self.invoke('gh run watch 42 --interval 150; gh pr merge 5 --squash')
        self.assertEqual(result['permissionDecision'], 'deny')
        self.assertIn('OBSERVATION-ONLY', result['permissionDecisionReason'])
        self.assertNotIn('READ_COOLDOWN_ONLY', result['permissionDecisionReason'])

    def test_hot_watch_still_denied(self):
        result = self.invoke('gh run watch 42 --interval 3')
        self.assertEqual(result['permissionDecision'], 'deny')

    def test_sleep_and_read_still_denied(self):
        result = self.invoke('sleep 300; gh run view 42')
        self.assertEqual(result['permissionDecision'], 'deny')

    def test_guard_ast_changes_only_guidance_and_native_surface_classification(self):
        # Joined-string text has different segmentation; normalize entire returned
        # guidance expressions only, then require all other AST nodes unchanged.
        old = ast.parse(FIXTURE.read_text())
        new = ast.parse(installer.render('guard', FIXTURE.read_text()))
        for tree in (old, new):
            fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_repeat_poll_reason')
            conditional = next(n for n in fn.body if isinstance(n, ast.If) and isinstance(n.test, ast.BoolOp))
            conditional.body[-1].value = ast.Constant(value='<cooldown guidance>')
            bash = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'guard_bash')
            calls = [n for n in ast.walk(bash) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'allow_context']
            self.assertEqual(len(calls), 1)
            calls[0].args = [ast.Constant(value='<watch request guidance>')]
            native = next(n for n in bash.body if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == 'codex_native' for t in n.targets))
            native.value = ast.Constant(value='<documented native surface>')
        self.assertEqual(ast.dump(old), ast.dump(new))


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'home'
        patches = json.loads((installer.ROOT / 'scripts/ci_wait_guidance_replacements.json').read_text())
        source = {'guard': FIXTURE.read_text(),
                  'context': "print('''\n" + patches['context'][0]['old'] + "\n''')\n",
                  'codex': 'Before\n' + installer.ANCHOR + '\nAfter\n',
                  'claude': 'Before\n' + installer.ANCHOR + '\nAfter\n'}
        for kind, relative in installer.TARGETS.items():
            path = self.home / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source[kind])
            path.chmod(0o640)

    def test_dry_run_makes_no_changes(self):
        before = {p: p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        plan = installer.prepare(self.home)
        self.assertEqual(len(plan), 4)
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_install_backs_up_preserves_modes_and_is_idempotent(self):
        plan = installer.prepare(self.home)
        evidence = Path(self.tmp.name) / 'evidence'
        result = installer.apply(plan, evidence)
        self.assertEqual(result['status'], 'INSTALLED')
        self.assertEqual(len(result['written']), 4)
        self.assertFalse(result['runtime_verified'])
        for p in plan:
            self.assertEqual(p['path'].read_bytes(), p['after'])
            self.assertEqual(p['path'].stat().st_mode & 0o777, 0o640)
            self.assertEqual((evidence / (p['kind'] + '.before')).read_bytes(), p['before'])
        again = installer.prepare(self.home)
        self.assertTrue(all(p['before'] == p['after'] for p in again))

    def test_drift_in_last_target_refuses_before_any_install(self):
        path = self.home / installer.TARGETS['claude']
        path.write_text('foreign instructions')
        before = (self.home / installer.TARGETS['guard']).read_bytes()
        with self.assertRaises(ValueError):
            installer.prepare(self.home)
        self.assertEqual((self.home / installer.TARGETS['guard']).read_bytes(), before)

    def test_concurrent_edit_after_plan_is_preserved(self):
        plan = installer.prepare(self.home)
        plan[-1]['path'].write_text('concurrent owner change')
        evidence = Path(self.tmp.name) / 'evidence'
        with self.assertRaises(ValueError):
            installer.apply(plan, evidence)
        self.assertFalse(evidence.exists())
        self.assertEqual(plan[0]['path'].read_bytes(), plan[0]['before'])

    def test_mid_install_failure_reports_partial_without_false_completion(self):
        plan = installer.prepare(self.home)
        evidence = Path(self.tmp.name) / 'evidence'
        original = installer.atomic_write
        def fail_second(path, data, mode):
            if path == plan[1]['path']:
                raise OSError('injected write failure')
            original(path, data, mode)
        with patch.object(installer, 'atomic_write', side_effect=fail_second):
            with self.assertRaises(OSError):
                installer.apply(plan, evidence)
        receipt = json.loads((evidence / 'install.json').read_text())
        self.assertEqual(receipt['status'], 'PARTIAL_FAILURE')
        self.assertEqual(receipt['written'], [str(plan[0]['path'])])
        self.assertEqual(plan[1]['path'].read_bytes(), plan[1]['before'])

    def test_unknown_guard_or_duplicate_anchor_refused(self):
        with self.assertRaises(ValueError):
            installer.render('guard', 'print("unrecognized guard")')
        with self.assertRaises(ValueError):
            installer.render('codex', installer.ANCHOR * 2)

    def test_symlink_target_refused(self):
        target = self.home / installer.TARGETS['codex']
        target.unlink()
        target.symlink_to(self.home / installer.TARGETS['claude'])
        with self.assertRaises(ValueError):
            installer.prepare(self.home)

    def test_unrelated_instruction_bytes_preserved(self):
        source = 'untouched prefix\n' + installer.ANCHOR + '\nuntouched suffix\n'
        result = installer.render('codex', source)
        self.assertEqual(result.replace('\n\n' + installer.guidance(), ''), source)

    def test_shared_liveness_contract_has_return_path_and_backoff(self):
        block = installer.guidance()
        for phrase in ('not a launched', 'not a\ncompletion-event source',
                       '15m -> 30m -> 60m', 'two equivalent no-progress',
                       'elapsed time does not clear', 'original owners, roots, grants'):
            self.assertIn(phrase, block)


if __name__ == '__main__':
    unittest.main()
