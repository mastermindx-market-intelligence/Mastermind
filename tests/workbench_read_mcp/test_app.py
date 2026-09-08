"""Development HTTP/auth composition tests using ephemeral RSA test credentials.

The callback uses actual disposable files to qualify the AUTH/SDK boundary.
It is not the descriptor-based production observer and must not be installed.
No HTTP listener, real OAuth account, production token or new permission store.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import pathlib
import tempfile
import time
import unittest

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from integrations.business_mcp_auth.contracts import load_resource_policy, subject_digest
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.workbench_read_mcp.app import create_authenticated_read_server, ProjectReadRefused

ISSUER = 'https://identity.workbench.example'
RESOURCE = 'https://workbench.example/mcp'
SCOPE = 'workbench.read'
OUTPUT = {
    'type': 'object',
    'properties': {'status': {'const': 'OK'}, 'content': {'type': 'string'},
                   'project_ref': {'type': 'string'},
                   'file_sha256': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}},
    'required': ['status', 'content', 'project_ref', 'file_sha256'],
    'additionalProperties': False,
}


class Keys:
    def __init__(self, jwk):
        self.jwk = jwk
        self.calls = 0
    async def key_for(self, kid):
        self.calls += 1
        if kid != 'fixture-key':
            raise ValueError('synthetic unknown key')
        return self.jwk


class Audit:
    def __init__(self):
        self.events = []
        self.fail = False
    def emit(self, event):
        if self.fail:
            raise RuntimeError('PRIVATE_AUDIT_FAILURE')
        self.events.append(dataclasses.asdict(event))


class AuthenticatedReadTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='mmx-auth-read-test-')
        self.root = pathlib.Path(self.directory.name)
        for project, text in [('alpha', 'Alpha project instructions\n'), ('beta', 'Beta project instructions\n')]:
            (self.root / project).mkdir()
            (self.root / project / 'CLAUDE.md').write_text(text)
        self.clock = int(time.time())
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.pem = self.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption())
        self.public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        self.public.update(kid='fixture-key', alg='RS256', use='sig')
        self.keys = Keys(self.public)
        self.audit = Audit()
        self.subjects = {u: subject_digest(issuer=ISSUER, subject=u) for u in ['reader-a', 'reader-b']}
        self.policy = load_resource_policy({
            'schema': 'mastermind.business_mcp_auth_policy.v1', 'policy_id': 'fixture.workbench.read',
            'resource': RESOURCE, 'resource_metadata_url': 'https://workbench.example/.well-known/oauth-protected-resource/mcp',
            'issuer': ISSUER, 'authorization_servers': [ISSUER], 'jwks_uri': ISSUER + '/jwks',
            'required_scopes': [SCOPE], 'allowed_subject_digests': sorted(self.subjects.values()),
            'allowed_algorithms': ['RS256'], 'clock_skew_seconds': 0,
            'max_token_lifetime_seconds': 3600, 'jwks_cache_ttl_seconds': 60,
            'unknown_kid_refresh_cooldown_seconds': 1, 'fetch_failure_backoff_seconds': 1,
        })
        self.auth = JwtAuthenticator(policy=self.policy, jwks_cache=self.keys)
        self.port_calls = 0
        self.file_reads = 0
        self.mode = 'normal'
        self.seen_callers = []
        async def port(caller, request):
            self.port_calls += 1
            self.seen_callers.append(caller)
            allowed = {self.subjects['reader-a']: 'alpha', self.subjects['reader-b']: 'beta'}
            project = allowed.get(caller.subject_digest)
            if project != request['project_ref'] or request['relative_path'] != 'CLAUDE.md':
                raise ProjectReadRefused()
            if self.mode == 'exception':
                raise RuntimeError('PRIVATE_PORT_EXCEPTION')
            await asyncio.sleep(0)
            self.file_reads += 1
            data = (self.root / project / 'CLAUDE.md').read_bytes()
            result = {'status': 'OK', 'content': data.decode(), 'project_ref': project,
                      'file_sha256': hashlib.sha256(data).hexdigest()}
            if self.mode == 'wrong-project':
                result['project_ref'] = 'beta'
            elif self.mode == 'wrong-hash':
                result['file_sha256'] = '0' * 64
            elif self.mode == 'mutate-request':
                request['project_ref'] = 'beta'
                result['project_ref'] = 'beta'
            elif self.mode == 'expire':
                self.clock += 7200
            elif self.mode == 'bad-output':
                result['private'] = 'PRIVATE_OUTPUT'
            elif self.mode == 'large-output':
                result['content'] = 'x' * 100000
            elif self.mode == 'audit-fail':
                self.audit.fail = True
            elif self.mode == 'policy-drift':
                self.auth._policy = dataclasses.replace(self.policy, policy_id='changed.policy')
            return result
        self.server = create_authenticated_read_server(
            authenticator=self.auth, policy=self.policy, now=lambda: self.clock,
            audit_sink=self.audit, read_port=port, output_schema=OUTPUT,
            allowed_hosts=('127.0.0.1', '127.0.0.1:*'),
        )
        self.app = self.server.streamable_http_app()
        self.lifespan_ready = asyncio.Event()
        self.lifespan_stop = asyncio.Event()
        async def own_lifespan():
            # AnyIO scopes must enter/exit in the SAME task; unittest setup
            # and teardown are distinct tasks despite sharing an event loop.
            async with self.app.router.lifespan_context(self.app):
                self.lifespan_ready.set()
                await self.lifespan_stop.wait()
        self.lifespan_task = asyncio.create_task(own_lifespan())
        await asyncio.wait_for(self.lifespan_ready.wait(), timeout=5)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://127.0.0.1')

    async def asyncTearDown(self):
        await self.client.aclose()
        self.lifespan_stop.set()
        await asyncio.wait_for(self.lifespan_task, timeout=5)
        self.directory.cleanup()

    def token(self, user='reader-a', **changes):
        payload = {'iss': ISSUER, 'sub': user, 'aud': RESOURCE, 'iat': self.clock - 1,
                   'exp': self.clock + 600, 'scope': SCOPE, 'client_id': 'fixture-client'}
        payload.update(changes)
        return jwt.encode(payload, self.pem, algorithm='RS256', headers={'kid': 'fixture-key'})

    async def rpc(self, method, params=None, token=None, origin=None):
        headers = {'Accept': 'application/json, text/event-stream', 'MCP-Protocol-Version': '2025-03-26'}
        if token is not None:
            headers['Authorization'] = 'Bearer ' + token
        if origin:
            headers['Origin'] = origin
        return await self.client.post('/mcp', headers=headers,
                                      json={'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}})

    async def read(self, token=None, project='alpha', extra=None):
        args = {'project_ref': project, 'relative_path': 'CLAUDE.md'}
        args.update(extra or {})
        return await self.rpc('tools/call', {'name': 'read_project_file', 'arguments': args},
                              token=self.token() if token is None else token)

    def result(self, response):
        self.assertEqual(response.status_code, 200, response.text[:200])
        body = response.json()
        self.assertIn('result', body, body)
        return body['result']

    async def test_initialize_uses_actual_sdk(self):
        r = await self.rpc('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                                         'clientInfo': {'name': 'test', 'version': '1'}}, token=self.token())
        self.assertIn('serverInfo', self.result(r))
        self.assertEqual(self.file_reads, 0)

    async def test_tool_discovery_exposes_one_read_only_tool(self):
        data = self.result(await self.rpc('tools/list', token=self.token()))
        self.assertEqual([r['name'] for r in data['tools']], ['read_project_file'])
        row = data['tools'][0]
        self.assertFalse(row['inputSchema']['additionalProperties'])
        self.assertTrue(row['annotations']['readOnlyHint'])
        self.assertFalse(row['annotations']['destructiveHint'])
        self.assertEqual(self.file_reads, 0)

    async def test_real_signature_allows_correct_real_file(self):
        data = self.result(await self.read())
        self.assertFalse(data.get('isError', False), data)
        self.assertEqual(data['structuredContent']['content'], 'Alpha project instructions\n')
        self.assertEqual(self.file_reads, 1)

    async def test_two_authenticated_users_do_not_share_project_selection(self):
        a, b = await asyncio.gather(self.read(self.token('reader-a'), 'alpha'),
                                    self.read(self.token('reader-b'), 'beta'))
        self.assertEqual(self.result(a)['structuredContent']['project_ref'], 'alpha')
        self.assertEqual(self.result(b)['structuredContent']['project_ref'], 'beta')
        self.assertEqual({c.subject_digest for c in self.seen_callers}, set(self.subjects.values()))
        self.assertEqual(self.file_reads, 2)

    async def test_valid_identity_cannot_read_other_project(self):
        data = self.result(await self.read(project='beta'))
        self.assertTrue(data['isError'])
        self.assertEqual(self.file_reads, 0)

    async def test_missing_auth_never_reaches_port(self):
        r = await self.rpc('tools/call', {'name': 'read_project_file', 'arguments': {'project_ref': 'alpha', 'relative_path': 'CLAUDE.md'}})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.port_calls, 0)

    async def test_bad_signature_never_reaches_port(self):
        token = self.token().split('.')
        token[2] = ('A' if token[2][0] != 'A' else 'B') + token[2][1:]
        r = await self.read('.'.join(token))
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.port_calls, 0)

    async def test_wrong_subject_never_reaches_port(self):
        r = await self.read(self.token('unapproved-user'))
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.port_calls, 0)

    async def test_wrong_audience_never_reaches_port(self):
        r = await self.read(self.token(aud='https://executive.example/mcp'))
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.port_calls, 0)

    async def test_wrong_issuer_never_reaches_port(self):
        r = await self.read(self.token(iss='https://other.example'))
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.port_calls, 0)

    async def test_wrong_scope_never_reaches_port(self):
        r = await self.read(self.token(scope='executive.write'))
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.port_calls, 0)

    async def test_extra_tool_scope_never_reaches_port(self):
        r = await self.read(self.token(scope='executive.write workbench.read'))
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.port_calls, 0)

    async def test_expired_token_never_reaches_port(self):
        r = await self.read(self.token(iat=self.clock - 600, exp=self.clock - 1))
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.port_calls, 0)

    async def test_model_root_or_principal_fields_are_rejected(self):
        r = await self.read(extra={'root': '/', 'subject_digest': self.subjects['reader-b']})
        body = r.json()
        self.assertTrue('error' in body or body.get('result', {}).get('isError'))
        self.assertEqual(self.port_calls, 0)

    async def test_read_scope_expiry_after_await_withholds_result(self):
        self.mode = 'expire'
        r = self.result(await self.read())
        self.assertTrue(r['isError'])
        self.assertNotIn('Alpha project', json.dumps(r))
        self.assertEqual(self.file_reads, 1)

    async def test_policy_drift_after_await_withholds_result(self):
        self.mode = 'policy-drift'
        r = self.result(await self.read())
        self.assertTrue(r['isError'])
        self.assertNotIn('Alpha project', json.dumps(r))

    async def test_audit_failure_denies_read_result(self):
        self.mode = 'audit-fail'
        r = self.result(await self.read())
        self.assertTrue(r['isError'])
        self.assertNotIn('PRIVATE_AUDIT', json.dumps(r))

    async def test_callback_exception_is_not_disclosed(self):
        self.mode = 'exception'
        r = self.result(await self.read())
        self.assertTrue(r['isError'])
        self.assertNotIn('PRIVATE_PORT_EXCEPTION', json.dumps(r))

    async def test_malformed_output_is_not_disclosed(self):
        self.mode = 'bad-output'
        r = self.result(await self.read())
        self.assertTrue(r['isError'])
        self.assertNotIn('PRIVATE_OUTPUT', json.dumps(r))

    async def test_oversize_output_is_refused(self):
        self.mode = 'large-output'
        r = self.result(await self.read())
        self.assertTrue(r['isError'])
        self.assertLess(len(json.dumps(r).encode()), 4096)

    async def test_forbidden_origin_never_reads_file(self):
        r = await self.rpc('tools/list', token=self.token(), origin='https://hostile.example')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.file_reads, 0)

    async def test_audit_contains_no_raw_subjects_or_credentials(self):
        token = self.token()
        self.result(await self.read(token))
        text = json.dumps(self.audit.events)
        self.assertNotIn(token, text)
        self.assertNotIn('reader-a', text)
        self.assertNotIn('Alpha project', text)
        self.assertTrue(self.audit.events)


    async def test_wrong_project_result_is_withheld(self):
        self.mode = 'wrong-project'
        r = self.result(await self.read())
        self.assertTrue(r['isError'])
        self.assertNotIn('Alpha project', json.dumps(r))

    async def test_expected_hash_mismatch_cannot_be_reported_success(self):
        self.mode = 'wrong-hash'
        expected = hashlib.sha256(b'Alpha project instructions\n').hexdigest()
        r = self.result(await self.read(extra={'expected_sha256': expected}))
        self.assertTrue(r['isError'])
        self.assertNotIn('Alpha project', json.dumps(r))

    async def test_port_cannot_mutate_selected_project(self):
        self.mode = 'mutate-request'
        r = self.result(await self.read())
        self.assertTrue(r['isError'])
        self.assertNotIn('Alpha project', json.dumps(r))

    async def test_project_ref_terminal_control_refuses_before_port(self):
        r = self.result(await self.read(project='alpha\n'))
        self.assertTrue(r['isError'])
        self.assertEqual(self.port_calls, 0)

    async def test_hash_terminal_control_refuses_before_port(self):
        h = hashlib.sha256(b'Alpha project instructions\n').hexdigest()
        r = self.result(await self.read(extra={'expected_sha256': h+'\n'}))
        self.assertTrue(r['isError'])
        self.assertEqual(self.port_calls, 0)


    async def test_invalid_argument_error_does_not_echo_caller_payload(self):
        marker = 'PRIVATE_CALLER_PAYLOAD'
        r = self.result(await self.read(project=marker + '!'))
        self.assertTrue(r['isError'])
        self.assertNotIn(marker, json.dumps(r))
        self.assertEqual(self.port_calls, 0)

    async def test_invalid_large_argument_error_is_bounded_before_port(self):
        marker = 'UNTRUSTED_OVERLONG_PROJECT_' * 512
        r = self.result(await self.read(project=marker))
        self.assertTrue(r['isError'])
        self.assertLess(len(json.dumps(r).encode('utf-8')), 512)
        self.assertEqual(self.port_calls, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
