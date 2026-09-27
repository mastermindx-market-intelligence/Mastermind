"""Behavioral proof of the attended client bootstrap; no real provider or auth."""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import tomllib
import unittest

MODULE = 'ops.codex_fabric.attended_parent'
SPEC = importlib.util.find_spec(MODULE)
if SPEC is not None:
    from ops.codex_fabric import attended_parent as bootstrap
else:
    bootstrap = None
ROOT = Path(__file__).resolve().parents[1]
URL = 'http://127.0.0.1:8766/mcp'
TOOLS = ['executive_state', 'executive_inbox', 'executive_job',
         'ceo_intent_status', 'submit_ceo_intent']

class AttendedParentTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(bootstrap, 'attended bootstrap implementation is missing')
        self.temp = tempfile.TemporaryDirectory(prefix="codex bootstrap ' ; ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'reviewed source'
        self.module_dir = self.source / 'ops' / 'codex_fabric'
        self.module_dir.mkdir(parents=True)
        self.profile = self.module_dir / 'mastermind-astra.config.toml'
        self.profile.write_bytes((ROOT / 'ops/codex_fabric/mastermind-astra.config.toml').read_bytes())
        (self.module_dir / 'executive_mcp_auth.py').write_text('# never imported in preflight\n')
        self.project = self.root / 'actual project'
        self.project.mkdir()
        self.census_args = ['--cd', str(self.project), 'mcp', 'list', '--json']
        self.detail_args = ['--cd', str(self.project), 'mcp', 'get', 'mastermind-executive', '--json']
        self.detail = self.root / 'detail.json'
        self.calls = self.root / 'calls.jsonl'
        self.census = self.root / 'census.json'
        self.row = {'name': 'mastermind-executive', 'enabled': True,
                    'transport': {'type': 'streamable_http', 'url': URL},
                    'auth_status': 'not_logged_in'}
        self.census.write_text(json.dumps([self.row]))
        self.detail.write_text(json.dumps(dict(self.row, enabled_tools=None, disabled_tools=None)))
        self.codex = self.root / 'fake codex'
        self.codex.write_text('#!' + sys.executable + '\n' +
            'import json,pathlib,sys,os\n' +
            f'calls=pathlib.Path({str(self.calls)!r})\n' +
            'with calls.open("a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n')
        with self.codex.open('a') as f:
            f.write(f'if sys.argv[-3:]==["mcp","list","--json"]: print(pathlib.Path({str(self.census)!r}).read_text())\n')
            f.write(f'elif sys.argv[-4:]==["mcp","get","mastermind-executive","--json"]: print(pathlib.Path({str(self.detail)!r}).read_text())\n')
            f.write('else: print(json.dumps({"executed":sys.argv[1:],"cwd":os.getcwd()}))\n')
        self.codex.chmod(0o700)
        self.python = self.root / 'fake python'
        self.python.write_text('#!' + sys.executable + '\n' +
            'import json,os,sys\nprint(json.dumps({"cwd":os.getcwd(),"args":sys.argv[1:]}))\n')
        self.python.chmod(0o700)

    def prepare(self, **changes):
        kwargs = dict(codex_bin=self.codex, python_bin=self.python,
                      project_dir=self.project, source_root=self.source)
        kwargs.update(changes)
        return bootstrap.prepare_launch(URL, **kwargs)

    def calls_read(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def test_preflight_only_reads_census_and_builds_five_tool_invocation(self):
        before = self.profile.read_bytes()
        plan = self.prepare()
        self.assertEqual(self.calls_read(), [self.census_args, self.detail_args])
        self.assertEqual(self.profile.read_bytes(), before)
        self.assertEqual(plan.argv[0], str(self.codex))
        self.assertEqual(plan.argv[1:3], ('--cd', str(self.project)))
        overrides = {}
        for index, arg in enumerate(plan.argv):
            if arg == '-c':
                key, value = plan.argv[index + 1].split('=', 1)
                overrides[key] = tomllib.loads('value=' + value)['value']
        self.assertEqual(overrides['model'], 'gpt-6-astra')
        self.assertIs(overrides['agents.enabled'], False)
        self.assertEqual(overrides['agents.max_concurrent_threads_per_session'], 1)
        self.assertEqual(overrides['mcp_servers.mastermind-executive.enabled_tools'], TOOLS)
        self.assertIs(overrides['mcp_servers.mastermind-executive.required'], True)
        self.assertEqual(overrides['mcp_servers.mastermind-executive.http_headers_helper'], plan.helper_command)
        self.assertNotIn('sandbox_mode', overrides)
        self.assertNotIn('approval_policy', overrides)
        receipt = plan.to_dict()
        self.assertEqual(receipt['status'], 'PREPARED_NOT_AUTHENTICATED')
        self.assertIs(receipt['authenticated_tool_discovery_proven'], False)

    def test_generated_helper_runs_in_source_not_project_and_quotes_paths(self):
        plan = self.prepare()
        result = subprocess.run(shlex.split(plan.helper_command), cwd=self.project,
                                capture_output=True, text=True, check=True)
        observed = json.loads(result.stdout)
        self.assertEqual(observed['cwd'], str(self.source))
        self.assertEqual(observed['args'], ['-E', '-s', '-B', '-m',
                         'ops.codex_fabric.executive_mcp_auth', 'headers'])

    def test_conflicting_or_ambiguous_registration_refuses_without_launch(self):
        variants = [[], [self.row, self.row],
                    [dict(self.row, enabled=False)],
                    [dict(self.row, auth_status='authenticated')],
                    [dict(self.row, auth_status=None)],
                    [dict(self.row, disabled_tools=['submit_ceo_intent'])]]
        for field, value in [('url', 'http://127.0.0.1:9000/mcp'),
                             ('http_headers', {'Authorization': 'secret-sentinel'}),
                             ('bearer_token_env_var', 'SECRET_ENV'),
                             ('http_headers_helper', 'unreviewed-helper')]:
            variants.append([dict(self.row, transport=dict(self.row['transport'], **{field: value}))])
        for rows in variants:
            with self.subTest(rows=rows):
                self.census.write_text(json.dumps(rows))
                with self.assertRaises(bootstrap.BootstrapError) as caught:
                    self.prepare()
                self.assertNotIn('secret-sentinel', str(caught.exception))
        self.assertTrue(all(call in (self.census_args, self.detail_args) for call in self.calls_read()))

    def test_unsupported_auth_support_yields_an_explicit_held_plan(self):
        self.census.write_text(json.dumps([dict(self.row, auth_status='unsupported')]))
        try:
            plan = self.prepare()
        except bootstrap.BootstrapError:
            self.fail('offline auth support must yield a held preparation, not lose the plan')
        self.assertFalse(plan.launch_allowed)
        self.assertEqual(plan.native_auth_status, 'unsupported')
        self.assertEqual(plan.to_dict()['status'], 'PREPARED_AUTH_STATUS_UNRESOLVED')
        self.assertFalse(plan.to_dict()['launch_allowed'])
        self.assertEqual(plan.argv[0], str(self.codex))

    def test_unsupported_auth_cannot_launch_or_run_the_helper(self):
        self.census.write_text(json.dumps([dict(self.row, auth_status='unsupported')]))
        result = self.cli('--launch')
        self.assertEqual(result.returncode, 2)
        self.assertIn('authentication status is unresolved', result.stderr)
        self.assertEqual(self.calls_read(), [self.census_args, self.detail_args])

    def test_census_is_bound_to_the_same_project_as_launch(self):
        plan = self.prepare()
        self.assertEqual(self.calls_read()[0],
                         ['--cd', str(self.project), 'mcp', 'list', '--json'])
        self.assertEqual(plan.argv[1:3], ('--cd', str(self.project)))

    def test_detailed_tool_restrictions_cannot_be_widened_by_bootstrap(self):
        variants = [dict(self.row, enabled_tools=['executive_state'], disabled_tools=None),
                    dict(self.row, enabled_tools=None, disabled_tools=['submit_ceo_intent'])]
        for detail in variants:
            with self.subTest(detail=detail):
                self.detail.write_text(json.dumps(detail))
                with self.assertRaises(bootstrap.BootstrapError):
                    self.prepare()

    def test_detailed_registration_drift_and_missing_fields_refuse(self):
        baseline = dict(self.row, enabled_tools=None, disabled_tools=None)
        variants = [dict(baseline, name='other-server'), dict(baseline, enabled=False),
                    dict(baseline, transport=dict(self.row['transport'],
                         url='http://127.0.0.1:19000/mcp')),
                    {key: value for key, value in baseline.items() if key != 'enabled_tools'},
                    dict(baseline, disabled_tools='submit_ceo_intent')]
        for detail in variants:
            with self.subTest(detail=detail):
                self.detail.write_text(json.dumps(detail))
                with self.assertRaises(bootstrap.BootstrapError):
                    self.prepare()

    def test_prepared_invocation_pins_validated_endpoint(self):
        plan = self.prepare()
        expected = 'mcp_servers.mastermind-executive.url=' + json.dumps(URL)
        self.assertIn(expected, plan.argv)

    def test_helper_preserves_the_selected_virtual_environment(self):
        import venv
        environment = self.root / 'selected venv'
        venv.EnvBuilder(with_pip=False, symlinks=True).create(environment)
        interpreter = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        (self.module_dir / 'executive_mcp_auth.py').write_text(
            'import json,sys\nprint(json.dumps({"prefix":sys.prefix}))\n')
        plan = self.prepare(python_bin=interpreter)
        observed = subprocess.run(shlex.split(plan.helper_command), cwd=self.project,
                                  capture_output=True, text=True, check=True, timeout=10)
        self.assertEqual(Path(json.loads(observed.stdout)['prefix']).resolve(), environment)

    def test_malformed_detailed_metadata_never_launches(self):
        self.detail.write_text('private-sentinel malformed detail')
        result = self.cli('--launch')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertNotIn('private-sentinel', result.stderr)
        self.assertEqual(self.calls_read(), [self.census_args, self.detail_args])

    def test_bad_url_refuses_before_census(self):
        for url in ['https://example.com/mcp', URL + '?secret=x',
                    'http://127.0.0.1:8766/m\tcp', URL + '\n',
                    'http://user:password@127.0.0.1:8766/mcp']:
            with self.subTest(url=url), self.assertRaises(bootstrap.BootstrapError):
                bootstrap.prepare_launch(url, codex_bin=self.codex, python_bin=self.python,
                    project_dir=self.project, source_root=self.source)
        self.assertEqual(self.calls_read(), [])

    def test_missing_or_unsafe_profile_refuses_before_census(self):
        for content in ['not valid TOML =', '[agents]\nenabled=true',
                        self.profile.read_text().replace('enabled = false', 'enabled = true')]:
            self.profile.write_text(content)
            with self.assertRaises(bootstrap.BootstrapError):
                self.prepare()
        self.profile.unlink()
        with self.assertRaises(bootstrap.BootstrapError):
            self.prepare()
        self.assertEqual(self.calls_read(), [])

    def test_missing_paths_refuse_before_census(self):
        for change in [{'codex_bin': self.root / 'missing'},
                       {'python_bin': self.root / 'missing'},
                       {'project_dir': self.root / 'missing'}]:
            with self.subTest(change=change), self.assertRaises(bootstrap.BootstrapError):
                self.prepare(**change)
        self.assertEqual(self.calls_read(), [])

    def cli(self, *extra):
        return subprocess.run([sys.executable, '-m', MODULE, '--url', URL,
            '--codex-bin', str(self.codex), '--python-bin', str(self.python),
            '--project-dir', str(self.project), *extra], cwd=ROOT,
            capture_output=True, text=True, timeout=10)

    def test_cli_defaults_to_preflight_without_starting_codex_parent(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'PREPARED_NOT_AUTHENTICATED')
        self.assertEqual(self.calls_read(), [self.census_args, self.detail_args])

    def test_explicit_launch_executes_prepared_argv_once(self):
        result = self.cli('--launch')
        self.assertEqual(result.returncode, 0, result.stderr)
        executed = json.loads(result.stdout)['executed']
        self.assertEqual(executed[:2], ['--cd', str(self.project)])
        calls = self.calls_read()
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0], self.census_args)
        self.assertEqual(calls[1], self.detail_args)
        self.assertEqual(calls[2], executed)
        self.assertNotIn('login', executed)
        self.assertNotIn('add', executed)

    def test_malformed_census_refuses_without_leaking_payload(self):
        self.census.write_text('secret-sentinel malformed census')
        result = self.cli('--launch')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertNotIn('secret-sentinel', result.stderr)
        self.assertEqual(self.calls_read(), [self.census_args])

    def test_launch_exit_is_preserved_without_fallback_or_retry(self):
        with self.codex.open('a') as f:
            f.write('if sys.argv[-1:] != ["--json"]: raise SystemExit(29)\n')
        result = self.cli('--launch')
        self.assertEqual(result.returncode, 29)
        self.assertEqual(len(self.calls_read()), 3)

if __name__ == '__main__':
    unittest.main()
