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

    def test_pr_numbers_in_distinct_repositories_do_not_collide(self):
        self.assertIsNone(self.read(1000, 'gh pr view 42 -R example/one --json state'))
        self.assertIsNone(self.read(1001, 'gh pr view 42 -R example/two --json state'))
        self.assertIsNotNone(self.read(1002, 'gh pr view 42 --repo EXAMPLE/ONE --json isDraft'))

    def test_new_source_facts_do_not_wait_for_previous_status_read(self):
        self.assertIsNone(self.read(1000, 'gh pr view 42 -R example/repo --json state'))
        source = 'gh pr view 42 -R example/repo --json state,isDraft,body,files,headRefOid'
        self.assertIsNone(self.read(1001, source))
        self.assertIsNotNone(self.read(1002, source))
        reordered = 'gh pr view 42 -R example/repo --json headRefOid,files,body,isDraft,state'
        self.assertIsNotNone(self.read(1003, reordered))

    def test_rotating_status_fields_does_not_bypass_cooldown(self):
        self.assertIsNone(self.read(1000, 'gh pr view 42 -R example/repo --json state'))
        self.assertIsNotNone(self.read(1001, 'gh pr view 42 -R example/repo --json statusCheckRollup'))

    def test_material_pr_mutation_invalidates_only_its_repository(self):
        one = 'gh pr view 42 -R example/one --json state,body'
        two = 'gh pr view 42 -R example/two --json state,body'
        self.read(1000, one)
        self.read(1000, two)
        self.guard['_clear_poll_state_for_mutation'](
            self.payload, 'gh pr edit 42 -R example/one --title changed'
        )
        self.assertIsNone(self.read(1001, one))
        self.assertIsNotNone(self.read(1001, two))

    def test_jq_text_does_not_turn_unrelated_metadata_into_ci_state(self):
        command = "gh pr view 42 -R example/repo --json url --jq '.state'"
        self.assertIsNone(self.read(1000, command))
        self.assertIsNone(self.read(1001, command))

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

    def test_guard_ast_changes_only_guidance_native_surface_and_pr_identity(self):
        # Joined-string text has different segmentation; normalize entire returned
        # guidance expressions only, then require all other AST nodes unchanged.
        old = ast.parse(FIXTURE.read_text())
        rendered = installer.render('guard', FIXTURE.read_text())
        helper_start = rendered.index(installer.POLL_IDENTITY_START)
        helper_end = rendered.index(installer.POLL_IDENTITY_END) + len(installer.POLL_IDENTITY_END)
        rendered = rendered[:helper_start] + rendered[helper_end:]
        self.assertEqual(rendered.count(installer.PR_MUTATION_UPDATE), 1)
        rendered = rendered.replace(installer.PR_MUTATION_UPDATE, '', 1)
        new = ast.parse(rendered)
        for tree in (old, new):
            identity = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_poll_key')
            identity.args = ast.arguments(posonlyargs=[], args=[], kwonlyargs=[],
                                          kw_defaults=[], defaults=[])
            identity.body = [ast.Expr(value=ast.Constant(value='<PR poll identity>'))]
            fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_repeat_poll_reason')
            fn.body[1].value = ast.Constant(value='<PR poll identity call>')
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

    def test_guard_only_preview_preserves_foreign_instruction_rollout(self):
        target = self.home / installer.TARGETS['codex']
        target.write_text('newer instruction owner')
        plan = installer.prepare(self.home, ['guard', 'guard'])
        self.assertEqual([item['kind'] for item in plan], ['guard'])
        self.assertEqual(target.read_text(), 'newer instruction owner')
        with self.assertRaises(ValueError):
            installer.prepare(self.home)

    def test_unknown_target_is_refused(self):
        with self.assertRaises(ValueError):
            installer.prepare(self.home, ['unowned-path'])

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
        # These are semantic clauses, not a canonical Markdown line-wrap format.
        block = ' '.join(installer.guidance().split())
        for phrase in ('not a launched', 'not a completion-event source',
                       '15m -> 30m -> 60m', 'two equivalent no-progress',
                       'elapsed time does not clear', 'original owners, roots, grants'):
            self.assertIn(phrase, block)

    def test_shared_liveness_contract_accepts_equivalent_line_wrapping(self):
        words = installer.guidance().split()
        for separator in (' ', '\n', ' \n\t '):
            with self.subTest(separator=repr(separator)):
                with patch.object(installer, 'guidance', return_value=separator.join(words)):
                    self.test_shared_liveness_contract_has_return_path_and_backoff()

    def test_shared_liveness_contract_still_rejects_each_missing_guard(self):
        block = ' '.join(installer.guidance().split())
        for phrase in ('not a launched', 'not a completion-event source',
                       '15m -> 30m -> 60m', 'two equivalent no-progress',
                       'elapsed time does not clear', 'original owners, roots, grants'):
            with self.subTest(missing=phrase):
                self.assertIn(phrase, block)
                with patch.object(installer, 'guidance', return_value=block.replace(phrase, '')):
                    with self.assertRaises(AssertionError):
                        self.test_shared_liveness_contract_has_return_path_and_backoff()


class AttendedValidationTests(unittest.TestCase):
    def previous(self):
        return (installer.ROOT / 'tests/fixtures/ci_wait_guidance_v1.md').read_text()

    def test_attended_guidance_fits_existing_source_budget(self):
        self.assertLessEqual(len(installer.guidance().encode()), len(self.previous().encode()))

    def test_previous_fixture_is_exact_accepted_migration(self):
        self.assertIn(installer.digest(self.previous().encode()), installer.PREVIOUS_GUIDANCE_SHA256)

    def test_known_previous_guidance_upgrades_once_and_preserves_surroundings(self):
        for kind in ('codex', 'claude'):
            with self.subTest(kind=kind):
                source = 'private prefix\n' + self.previous() + '\nprivate suffix'
                expected = 'private prefix\n' + installer.guidance() + '\nprivate suffix'
                actual = installer.render(kind, source)
                self.assertEqual(actual, expected)
                self.assertEqual(installer.render(kind, actual), actual)

    def test_unknown_modified_previous_block_cannot_be_overwritten(self):
        source = self.previous().replace('elapsed time does not clear', 'elapsed time clears')
        for kind in ('codex', 'claude'):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                installer.render(kind, source)

    def test_duplicate_missing_and_reversed_markers_refuse(self):
        old = self.previous()
        for text in (old + old, old.replace(installer.END, ''),
                     old.replace(installer.START, ''), installer.END + old,
                     installer.END + '\nforeign\n' + installer.START):
            with self.subTest(text=text[:70]), self.assertRaises(ValueError):
                installer.render('codex', text)

    def test_attended_fast_validation_contract(self):
        block = ' '.join(installer.guidance().split())
        for phrase in ('Short attended validation', 'seconds to minutes',
                       'same healthy session', 'consume the terminal result',
                       'not a reason to checkpoint and end', 'exact repository, PR, head and run',
                       'bounded wait', 'cooldown', 'No new watcher',
                       'genuine session boundary', 'not a background Web turn'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, block)

    def test_attended_rule_does_not_weaken_existing_refusal_guards(self):
        block = ' '.join(installer.guidance().split())
        for phrase in ('Permission, safety, custody and effect-unknown refusals remain binding',
                       '15m -> 30m -> 60m', 'two equivalent no-progress'):
            self.assertIn(phrase, block)


if __name__ == '__main__':
    unittest.main()
