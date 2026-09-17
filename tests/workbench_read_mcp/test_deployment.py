"""Deployment boundaries: no bootstrap, root grant or listener is implicit."""
from __future__ import annotations

import contextlib
import importlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest


def deployment(case):
    case.assertIsNotNone(importlib.util.find_spec('integrations.workbench_read_mcp.deployment'),
                         'the inert deployment composer is missing')
    return importlib.import_module('integrations.workbench_read_mcp.deployment')


class DeploymentTests(unittest.TestCase):
    def test_missing_services_refuse_without_acquiring_runtime(self):
        module = deployment(self)
        with self.assertRaisesRegex(ValueError, '^RUNTIME_SERVICES_REQUIRED$'):
            module.create_deployment(None)

    def test_describe_and_missing_config_work_without_optional_sdk(self):
        script = Path(__file__).resolve().parents[2] / 'scripts/mastermind_workbench_read_server.py'
        described = subprocess.run([sys.executable, '-S', str(script), '--describe'],
                                   capture_output=True, text=True, timeout=10)
        self.assertEqual(described.returncode, 0, described.stderr)
        self.assertEqual(json.loads(described.stdout), {
            'capability': 'BUILT_NOT_PROVEN',
            'mode': 'configured-loopback-service',
            'tool': 'read_project_file',
            'config_schema': 'mastermind.workbench_read_service.v1',
            'installed': False,
        })
        refused = subprocess.run([sys.executable, '-S', str(script)],
                                 capture_output=True, text=True, timeout=10)
        self.assertEqual(refused.returncode, 2)
        self.assertEqual(refused.stderr.strip(), 'SERVICE_CONFIGURATION_REQUIRED')
        self.assertEqual(refused.stdout, '')

    def test_launcher_rejects_parallel_authority_flags(self):
        deployment(self)
        launcher = importlib.import_module('scripts.mastermind_workbench_read_server')
        for args in (['--root', '/'], ['--factory', 'evil:main'],
                     ['--host', '127.0.0.1'], ['--port', '8765']):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as captured:
                    launcher.main(args)
                self.assertEqual(captured.exception.code, 2)

    def test_declared_output_schema_is_closed_and_requires_attribution(self):
        module = deployment(self)
        from jsonschema import Draft202012Validator
        schema = module.observation_schema()
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(set(schema['required']), set(schema['properties']))
        for key in ('context_ref', 'owner_ref', 'generation', 'file_identity_digest',
                    'observation_digest', 'committed_head', 'next_line', 'index_status'):
            self.assertIn(key, schema['required'])
        Draft202012Validator.check_schema(schema)
        schema['properties'].clear()
        self.assertIn('content', module.observation_schema()['properties'])


if __name__ == '__main__':
    unittest.main()
