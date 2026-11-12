"""Paperclip edge contract checks; native Hermes qualification is recorded separately."""
import base64
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1] / 'integrations' / 'paperclip_hermes'
MODULE = '_paperclip_finite_launch_contract'
spec = importlib.util.spec_from_file_location(MODULE, ROOT / 'core_overlay/agent/launch_credential_binding.py')
binding = importlib.util.module_from_spec(spec)
sys.modules[MODULE] = binding
spec.loader.exec_module(binding)

NOW = 1_800_000_000
AGENT = '00000000-0000-4000-8000-000000000001'
COMPANY = '00000000-0000-4000-8000-000000000002'
RUN = '00000000-0000-4000-8000-000000000003'


def jwt(**updates):
    claims = {'sub': AGENT, 'company_id': COMPANY, 'run_id': RUN, 'exp': NOW + 3600, **updates}
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
    return 'synthetic-header.' + payload + '.synthetic-signature'


class PaperclipLaunchContractTests(unittest.TestCase):
    def setUp(self):
        clock = patch.object(binding.time, 'time', return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)
        # JSON is a YAML-compatible manifest format, parsed by native Hermes in qualification.
        manifest = json.loads((ROOT / 'paperclip_plugin/plugin.yaml').read_text())
        declarations = binding.manifest_bindings(manifest['launch_credentials'])
        self.spec = binding.declaration('paperclip-run', declarations['paperclip-run'])
        self.env = {
            'PAPERCLIP_API_URL': 'http://127.0.0.1:3100',
            'PAPERCLIP_AGENT_ID': AGENT, 'PAPERCLIP_COMPANY_ID': COMPANY, 'PAPERCLIP_RUN_ID': RUN,
            'PAPERCLIP_API_KEY': jwt(), 'PAPERCLIP_RUNTIME_TOOLS_TOKEN': 'synthetic-runtime-tools-token',
            'PAPERCLIP_RUNTIME_TOOLS_MCP_URL': 'http://127.0.0.1:3100/mcp/runtime-tools',
            'PAPERCLIP_RUNTIME_TOOLS_EXPIRES_AT': '2027-01-15T08:30:00.000Z',
            'PAPERCLIP_AGENT_PRIVATE_KEY': 'synthetic-managed-identity-private-key',
            'UNRELATED_PROVIDER_KEY': 'synthetic-provider-key',
        }

    def test_manifest_limits_private_values_to_issued_run_credentials(self):
        before = copy.deepcopy(self.env)
        payload = binding.collect(self.spec, self.env)
        values, context, public = binding.validate(self.spec, payload)
        self.assertEqual(set(values), {'PAPERCLIP_API_KEY', 'PAPERCLIP_RUNTIME_TOOLS_TOKEN'})
        self.assertEqual(context['PAPERCLIP_RUN_ID'], RUN)
        self.assertEqual(public['operation_id'], RUN)
        self.assertEqual(self.env, before)
        for value in values.values():
            self.assertNotIn(value, json.dumps(public))
        self.assertNotIn('UNRELATED_PROVIDER_KEY', json.dumps(payload))
        self.assertNotIn(self.env['PAPERCLIP_AGENT_PRIVATE_KEY'], json.dumps(payload))

    def test_issuer_identity_mismatch_is_refused_without_echo(self):
        for claim in ('sub', 'company_id', 'run_id'):
            with self.subTest(claim=claim):
                env = {**self.env, 'PAPERCLIP_API_KEY': jwt(**{claim: 'different-identity'})}
                with self.assertRaisesRegex(binding.LaunchCredentialError, 'identity_mismatch') as caught:
                    binding.collect(self.spec, env)
                self.assertNotIn(env['PAPERCLIP_API_KEY'], str(caught.exception))

    def test_runtime_tool_endpoint_and_partial_context_are_refused(self):
        for url in ('http://127.0.0.1:3100', 'http://127.0.0.1:3100/api'):
            self.assertIsNotNone(binding.collect(self.spec, {**self.env, 'PAPERCLIP_API_URL': url}))
        with self.assertRaisesRegex(binding.LaunchCredentialError, 'endpoint_mismatch'):
            binding.collect(self.spec, {**self.env, 'PAPERCLIP_RUNTIME_TOOLS_MCP_URL': 'https://other.invalid/mcp'})
        partial = dict(self.env)
        partial.pop('PAPERCLIP_RUNTIME_TOOLS_TOKEN')
        with self.assertRaisesRegex(binding.LaunchCredentialError, 'missing'):
            binding.collect(self.spec, partial)
        optional = {key: value for key, value in self.env.items() if not key.startswith('PAPERCLIP_RUNTIME_TOOLS_')}
        optional['PAPERCLIP_API_KEY'] = jwt(exp=NOW + 48 * 60 * 60)
        self.assertEqual(set(binding.collect(self.spec, optional)['credentials']), {'PAPERCLIP_API_KEY'})

    def test_expiry_and_undeclared_secret_values_fail_closed(self):
        with self.assertRaisesRegex(binding.LaunchCredentialError, 'expired'):
            binding.collect(self.spec, {**self.env, 'PAPERCLIP_API_KEY': jwt(exp=NOW)})
        payload = binding.collect(self.spec, self.env)
        payload['credentials']['UNRELATED_PROVIDER_KEY'] = self.env['UNRELATED_PROVIDER_KEY']
        with self.assertRaisesRegex(binding.LaunchCredentialError, 'values'):
            binding.validate(self.spec, payload)
        payload = binding.collect(self.spec, self.env)
        payload['credentials']['PAPERCLIP_RUNTIME_TOOLS_TOKEN'] = None
        with self.assertRaisesRegex(binding.LaunchCredentialError, 'values'):
            binding.validate(self.spec, payload)

    def test_changed_declaration_cannot_consume_an_old_payload(self):
        payload = binding.collect(self.spec, self.env)
        changed = copy.deepcopy(self.spec)
        changed['credentials'][0]['required'] = False
        with self.assertRaisesRegex(binding.LaunchCredentialError, 'declaration_changed'):
            binding.validate(changed, payload)

    def test_finite_lease_is_single_admission_and_retires_on_failure(self):
        values, context, public = binding.validate(self.spec, binding.collect(self.spec, self.env))
        lease = binding.CredentialLease('product', 'principal', 'session', 'instance', 4, public, values, context)
        scope = dict(profile_id='product', principal_id='principal', session_id='session',
                     instance_id='instance', owner_epoch=4, admission_id='first', generation=1, finite=True)
        claim = lease.claim(**scope)
        with self.assertRaisesRegex(binding.LaunchCredentialError, 'scope_mismatch'):
            lease.claim(**{**scope, 'profile_id': 'other-profile'})
        with self.assertRaisesRegex(binding.LaunchCredentialError, 'already_claimed'):
            lease.claim(**{**scope, 'admission_id': 'second', 'generation': 2})
        with self.assertRaisesRegex(RuntimeError, 'consumer-failed'):
            with binding.execution_scope(lease, claim):
                lease.retire()
                self.assertNotIn(self.env['PAPERCLIP_API_KEY'], binding.redact(self.env['PAPERCLIP_API_KEY']))
                raise RuntimeError('consumer-failed')
        self.assertFalse(lease._values or lease._context)
        with self.assertRaisesRegex(binding.LaunchCredentialError, 'unavailable'):
            lease.values(claim, session_id='session')


if __name__ == '__main__':
    unittest.main()
