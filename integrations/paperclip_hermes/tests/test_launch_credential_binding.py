"""Behavior of the generic finite binding used by the Paperclip integration."""
import base64
import copy
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context

import pytest

from agent import launch_credential_binding as binding


NOW = 1_800_000_000
AGENT = '00000000-0000-4000-8000-000000000001'
COMPANY = '00000000-0000-4000-8000-000000000002'
RUN = '00000000-0000-4000-8000-000000000003'


def encoded_jwt(**overrides):
    claims = {'sub': AGENT, 'company_id': COMPANY, 'run_id': RUN, 'exp': NOW + 3600, **overrides}
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
    return 'synthetic-header.' + payload + '.synthetic-signature'


@pytest.fixture
def spec(monkeypatch):
    monkeypatch.setattr(binding.time, 'time', lambda: NOW)
    return binding.declaration('test-orchestrator', {
        'version': 1, 'operation_env': 'ORCH_RUN_ID',
        'context_env': ['ORCH_RUN_ID', 'ORCH_AGENT_ID', 'ORCH_COMPANY_ID', 'ORCH_URL',
                        'ORCH_TOOLS_URL', 'ORCH_EXPIRES'],
        'required_context': ['ORCH_RUN_ID', 'ORCH_AGENT_ID', 'ORCH_COMPANY_ID', 'ORCH_URL'],
        'context_types': {'ORCH_RUN_ID': 'uuid', 'ORCH_AGENT_ID': 'uuid', 'ORCH_COMPANY_ID': 'uuid',
                          'ORCH_URL': 'http_url', 'ORCH_TOOLS_URL': 'http_url'},
        'same_origin': [['ORCH_URL', 'ORCH_TOOLS_URL']],
        'credentials': [
            {'env': 'ORCH_API_KEY', 'required': True, 'expiry_env': None, 'jwt_exp': True,
             'jwt_claims': {'sub': 'ORCH_AGENT_ID', 'company_id': 'ORCH_COMPANY_ID', 'run_id': 'ORCH_RUN_ID'},
             'required_context': []},
            {'env': 'ORCH_TOOLS_TOKEN', 'required': False, 'expiry_env': 'ORCH_EXPIRES', 'jwt_exp': False,
             'jwt_claims': {}, 'required_context': ['ORCH_TOOLS_URL']},
        ],
    })


@pytest.fixture
def env():
    return {'ORCH_RUN_ID': RUN, 'ORCH_AGENT_ID': AGENT, 'ORCH_COMPANY_ID': COMPANY,
            'ORCH_URL': 'http://127.0.0.1:3100', 'ORCH_TOOLS_URL': 'http://127.0.0.1:3100/mcp/tools',
            'ORCH_EXPIRES': '2027-01-15T08:30:00Z', 'ORCH_API_KEY': encoded_jwt(),
            'ORCH_TOOLS_TOKEN': 'synthetic-opaque-runtime-token', 'UNRELATED_PROVIDER_KEY': 'leave-it-alone'}


def lease_for(spec, env, session='parent', profile='profile'):
    values, context, public = binding.validate(spec, binding.collect(spec, env))
    return binding.CredentialLease(profile, 'principal', session, 'instance', 7, public, values, context)


def claim(lease, **overrides):
    return lease.claim(profile_id=lease.profile_id, principal_id='principal', session_id=lease.session_id,
                       instance_id='instance', owner_epoch=7, admission_id='admission', generation=4,
                       finite=True, **overrides)


def test_collection_has_exact_declared_scope_and_no_ambient_mutation(spec, env):
    before = dict(env)
    payload = binding.collect(spec, env)
    values, _context, public = binding.validate(spec, payload)
    assert set(values) == {'ORCH_API_KEY', 'ORCH_TOOLS_TOKEN'}
    assert 'UNRELATED_PROVIDER_KEY' not in payload['credentials']
    assert env == before and public['operation_id'] == RUN
    assert all(secret not in json.dumps(public) for secret in values.values())
    assert binding.collect(spec, {'UNRELATED_PROVIDER_KEY': 'untouched'}) is None


@pytest.mark.parametrize('change', ['run', 'company', 'agent', 'endpoint', 'partial', 'expired', 'malformed'])
def test_inconsistent_or_incomplete_issuer_context_is_refused(spec, env, change):
    mutations = {
        'run': lambda: env.update(ORCH_RUN_ID='00000000-0000-4000-8000-000000000099'),
        'company': lambda: env.update(ORCH_COMPANY_ID='00000000-0000-4000-8000-000000000099'),
        'agent': lambda: env.update(ORCH_AGENT_ID='00000000-0000-4000-8000-000000000099'),
        'endpoint': lambda: env.update(ORCH_TOOLS_URL='https://unrelated.invalid/mcp'),
        'partial': lambda: env.pop('ORCH_TOOLS_URL'),
        'expired': lambda: env.update(ORCH_API_KEY=encoded_jwt(exp=NOW)),
        'malformed': lambda: env.update(ORCH_API_KEY='synthetic-secret-invalid-jwt'),
    }
    mutations[change]()
    with pytest.raises(binding.LaunchCredentialError) as error:
        binding.collect(spec, env)
    assert env['ORCH_API_KEY'] not in str(error.value)


def test_unknown_private_values_and_changed_declaration_are_refused(spec, env):
    payload = binding.collect(spec, env)
    payload['credentials']['UNRELATED_PROVIDER_KEY'] = 'synthetic-forbidden-secret'
    with pytest.raises(binding.LaunchCredentialError):
        binding.validate(spec, payload)
    payload = binding.collect(spec, env)
    changed = copy.deepcopy(spec)
    changed['credentials'][0]['required'] = False
    with pytest.raises(binding.LaunchCredentialError, match='declaration_changed'):
        binding.validate(changed, payload)


def test_two_day_api_access_survives_optional_runtime_token_expiry(spec, env):
    env['ORCH_API_KEY'] = encoded_jwt(exp=NOW + 48 * 60 * 60)
    values, _context, public = binding.validate(spec, binding.collect(spec, env))
    assert set(values) == {'ORCH_API_KEY', 'ORCH_TOOLS_TOKEN'}
    assert public['expires_at'] == NOW + 48 * 60 * 60
    assert NOW < public['credential_expiries']['ORCH_TOOLS_TOKEN'] < NOW + 3600
    lease = lease_for(spec, env)
    owned = claim(lease)
    assert set(lease.values(owned, session_id='parent', now=NOW + 3601)) == {'ORCH_API_KEY'}
    assert set(lease.values(owned, session_id='parent')) == {'ORCH_API_KEY'}


def test_concurrent_profiles_get_only_their_own_values_and_redaction(spec, env):
    barrier = threading.Barrier(2)
    ambient = dict(os.environ)
    first, second = dict(env), dict(env, ORCH_TOOLS_TOKEN='second-synthetic-runtime-token')

    def execute(source, session, profile):
        lease = lease_for(spec, source, session, profile)
        with binding.execution_scope(lease, claim(lease), transcript_check=lambda sid: sid == session):
            with binding.tool_dispatch_scope(session, 'terminal', {}):
                barrier.wait(timeout=5)
                actual = binding.tool_environment()
                redacted = binding.redact({'output': actual['ORCH_TOOLS_TOKEN']})
                return actual, redacted

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(execute, first, 'first', 'first-profile')
        b = pool.submit(execute, second, 'second', 'second-profile')
        one, two = a.result(), b.result()
    assert one[0]['ORCH_TOOLS_TOKEN'] == first['ORCH_TOOLS_TOKEN']
    assert two[0]['ORCH_TOOLS_TOKEN'] == second['ORCH_TOOLS_TOKEN']
    assert one[1] == two[1] == {'output': '[REDACTED_LAUNCH_CREDENTIAL]'}
    assert dict(os.environ) == ambient and binding.tool_environment() == {}


def test_single_admission_scope_expiry_and_terminal_cleanup(spec, env):
    lease = lease_for(spec, env)
    owned = claim(lease)
    assert claim(lease) == owned
    with pytest.raises(binding.LaunchCredentialError, match='already_claimed'):
        lease.claim(profile_id='profile', principal_id='principal', session_id='parent',
                    instance_id='instance', owner_epoch=7, admission_id='second', generation=5, finite=True)
    with binding.execution_scope(lease, owned, transcript_check=lambda sid: sid == 'parent'):
        child = copy_context()
        assert child.run(binding.tool_environment) == {}
        with pytest.raises(binding.LaunchCredentialError, match='transcript_mismatch'):
            with binding.tool_dispatch_scope('delegated-child', 'terminal', {}):
                binding.tool_environment()
        assert env['ORCH_API_KEY'] not in repr(lease)
        with pytest.raises(binding.LaunchCredentialError, match='unavailable'):
            lease.values(owned, session_id='parent', now=NOW + 3601)
    assert not lease._values and not lease._context
    with pytest.raises(binding.LaunchCredentialError, match='unavailable'):
        lease.values(owned, session_id='parent')


def test_exception_and_explicit_cancel_retire_original_grant(spec, env):
    lease = lease_for(spec, env)
    with pytest.raises(RuntimeError, match='synthetic-execution-failure'):
        with binding.execution_scope(lease, claim(lease)):
            raise RuntimeError('synthetic-execution-failure')
    assert not lease._values and binding.bound_credentials() is None
    unused = lease_for(spec, env)
    unused.retire()
    with pytest.raises(binding.LaunchCredentialError, match='unavailable'):
        claim(unused)


@pytest.mark.parametrize('kind', ['null_optional', 'unicode_digest'])
def test_malformed_private_values_always_have_fixed_errors(spec, env, kind):
    payload = binding.collect(spec, env)
    if kind == 'null_optional':
        payload['credentials']['ORCH_TOOLS_TOKEN'] = None
    else:
        payload['declaration_digest'] = 'secret-é' * 8
    with pytest.raises(binding.LaunchCredentialError) as caught:
        binding.validate(spec, payload)
    assert 'secret-é' not in str(caught.value)


@pytest.mark.parametrize('scheme,default_port', [('http', 80), ('https', 443)])
def test_same_origin_accepts_only_omitted_default_port_equivalence(spec, env, scheme, default_port):
    env['ORCH_URL'] = f'{scheme}://orchestrator.invalid'
    env['ORCH_TOOLS_URL'] = f'{scheme}://orchestrator.invalid:{default_port}/mcp'
    values, context, _public = binding.validate(spec, binding.collect(spec, env))
    assert values['ORCH_API_KEY'] == env['ORCH_API_KEY']
    assert context['ORCH_TOOLS_URL'] == env['ORCH_TOOLS_URL']


@pytest.mark.parametrize('scheme,default_port', [('http', 80), ('https', 443)])
@pytest.mark.parametrize('zero_side', ['ORCH_URL', 'ORCH_TOOLS_URL'])
def test_same_origin_does_not_treat_explicit_zero_as_default(spec, env, scheme, default_port, zero_side):
    env['ORCH_URL'] = f'{scheme}://orchestrator.invalid:{default_port}'
    env['ORCH_TOOLS_URL'] = f'{scheme}://orchestrator.invalid:{default_port}/mcp'
    env[zero_side] = f'{scheme}://orchestrator.invalid:0'
    with pytest.raises(binding.LaunchCredentialError, match='launch_credentials_endpoint_mismatch'):
        binding.collect(spec, env)
