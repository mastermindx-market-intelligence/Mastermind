"""In-process source qualification, never a production account or tunnel.

The only executor/policy/project state here belongs to disposable test fixtures.
Every positive uses signed JWT, real ASGI MCP, port and descriptor observer.
"""
from __future__ import annotations

import asyncio
import contextlib
from concurrent.futures import ThreadPoolExecutor
import dataclasses
import hashlib
import importlib
import importlib.util
import inspect
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from integrations.business_mcp_auth.contracts import load_resource_policy, subject_digest
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.workbench_read_mcp.observer import ReadScope
from integrations.workbench_read_mcp.read_port import ProjectReadBinding

ISSUER = 'https://identity.read0.example'
RESOURCE = 'https://read0.example/mcp'
SENTINEL = 'alpha source\nsecond line\n'


class Keys:
    def __init__(self, key):
        self.key = key

    async def key_for(self, kid):
        if kid != 'read0-test':
            raise ValueError('unknown fixture key')
        return self.key


class Audit:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(dataclasses.asdict(event))


class CompositionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertIsNotNone(importlib.util.find_spec('integrations.workbench_read_mcp.deployment'),
                             'the inert deployment composer is missing')
        self.deployment = importlib.import_module('integrations.workbench_read_mcp.deployment')
        self.temp = tempfile.TemporaryDirectory(prefix='read0-composition-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fds = []
        self.clock = int(time.time())
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        public.update(kid='read0-test', alg='RS256', use='sig')
        self.subjects = {p: subject_digest(issuer=ISSUER, subject=p) for p in ('alpha', 'beta')}
        self.policy = load_resource_policy({
            'schema': 'mastermind.business_mcp_auth_policy.v1', 'policy_id': 'read0.fixture',
            'resource': RESOURCE, 'resource_metadata_url': 'https://read0.example/.well-known/oauth-protected-resource/mcp',
            'issuer': ISSUER, 'authorization_servers': [ISSUER], 'jwks_uri': ISSUER + '/jwks',
            'required_scopes': ['workbench.read'], 'allowed_subject_digests': sorted(self.subjects.values()),
            'allowed_algorithms': ['RS256'], 'clock_skew_seconds': 0,
            'max_token_lifetime_seconds': 3600, 'jwks_cache_ttl_seconds': 60,
            'unknown_kid_refresh_cooldown_seconds': 1, 'fetch_failure_backoff_seconds': 1,
        })
        self.auth = JwtAuthenticator(policy=self.policy, jwks_cache=Keys(public))
        self.audit = Audit()
        self.scopes = {}
        for project, text in [('alpha', SENTINEL), ('beta', 'beta source\n')]:
            directory = self.root / project
            directory.mkdir()
            (directory / 'source.txt').write_text(text)
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            self.fds.append(fd)
            self.addCleanup(os.close, fd)
            info = os.fstat(fd)
            self.scopes[project] = ReadScope(fd, info.st_dev, info.st_ino,
                'context-' + project, 'owner-' + project, 'generation-1',
                ('source.txt',), (self.clock + 500) * 1000, '1' * 40)
        self.active = True
        self.resolves = 0
        self.io_calls = 0
        self.observations = 0
        self.observer_threads = []
        self.loop_thread = threading.get_ident()
        self.before_io = asyncio.Event()
        self.before_io.set()
        self.entered = asyncio.Event()
        self.completed = asyncio.Event()
        self.return_gate = asyncio.Event()
        self.return_gate.set()
        self.transform = lambda value: value
        self.after_read = lambda: None
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='read0-fixture')
        self.addCleanup(self.pool.shutdown, True)
        self.slots = asyncio.Semaphore(2)
        self.futures = []
        self.tasks = []
        self.services = self.deployment.RuntimeServices(
            authenticator=self.auth, policy=self.policy, now=lambda: self.clock,
            clock_ms=lambda: self.clock * 1000, audit_sink=self.audit,
            resolve_binding=self.resolve, run_io=self.run_io,
            allowed_hosts=('127.0.0.1',), allowed_origins=(),
        )
        self.server = self.deployment.create_deployment(self.services)
        self.app = self.server.streamable_http_app()
        ready, self.stop = asyncio.Event(), asyncio.Event()

        async def lifespan():
            async with self.app.router.lifespan_context(self.app):
                ready.set()
                await self.stop.wait()

        self.life = asyncio.create_task(lifespan())
        self.addAsyncCleanup(self.close_runtime)
        await asyncio.wait_for(ready.wait(), 5)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),
                                       base_url='http://127.0.0.1')
        self.addAsyncCleanup(self.client.aclose)

    async def close_runtime(self):
        self.before_io.set()
        self.return_gate.set()
        for task in self.tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await asyncio.gather(*self.futures, return_exceptions=True)
        self.stop.set()
        await asyncio.wait_for(self.life, 5)
        self.assertTrue(self.life.done())
        self.assertTrue(all(f.done() for f in self.futures))
        # App lifecycle borrows these roots; only fixture cleanup closes them.
        for fd in self.fds:
            os.fstat(fd)

    def resolve(self, caller, project):
        self.resolves += 1
        if (not self.active or self.subjects.get(project) != caller.subject_digest
                or caller.client_ref != hashlib.sha256((ISSUER + '\nclient\nread0-client').encode()).hexdigest()
                or caller.resource != RESOURCE):
            return None
        return ProjectReadBinding(caller, project, self.scopes[project])

    async def run_io(self, operation):
        self.io_calls += 1
        self.entered.set()
        await self.before_io.wait()
        await self.slots.acquire()

        def observe():
            self.observations += 1
            self.observer_threads.append(threading.get_ident())
            return operation()

        future = asyncio.get_running_loop().run_in_executor(self.pool, observe)
        self.futures.append(future)
        future.add_done_callback(lambda _: self.slots.release())
        value = await asyncio.shield(future)
        self.completed.set()
        await self.return_gate.wait()
        self.after_read()
        return self.transform(value)

    def token(self, project='alpha', **changes):
        claims = {'iss': ISSUER, 'sub': project, 'aud': RESOURCE, 'iat': self.clock - 1,
                  'exp': self.clock + 300, 'scope': 'workbench.read', 'client_id': 'read0-client'}
        claims.update(changes)
        return jwt.encode(claims, self.key, algorithm='RS256', headers={'kid': 'read0-test'})

    async def rpc(self, method, params, token):
        return await self.client.post('/mcp', headers={
            'Accept': 'application/json, text/event-stream', 'MCP-Protocol-Version': '2025-03-26',
            'Authorization': 'Bearer ' + token,
        }, json={'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params})

    async def read(self, project='alpha', token=None, **extra):
        args = {'project_ref': project, 'relative_path': 'source.txt'}
        args.update(extra)
        return await self.rpc('tools/call', {'name': 'read_project_file', 'arguments': args},
                              token or self.token(project))

    def result(self, response):
        self.assertEqual(response.status_code, 200, response.text[:200])
        self.assertIn('result', response.json())
        return response.json()['result']

    def withheld(self, response, code=None):
        body = self.result(response)
        self.assertTrue(body.get('isError'), body)
        self.assertNotIn('structuredContent', body)
        self.assertNotIn('alpha source', response.text)
        self.assertNotIn('beta source', response.text)
        self.assertNotIn(str(self.root), response.text)
        if code:
            self.assertEqual(json.loads(body['content'][0]['text'])['code'], code)

    async def test_initialize_list_and_real_attributed_read(self):
        token = self.token()
        hello = self.result(await self.rpc('initialize', {'protocolVersion': '2025-03-26',
            'capabilities': {}, 'clientInfo': {'name': 'read0-test', 'version': '1'}}, token))
        self.assertIn('serverInfo', hello)
        tools = self.result(await self.rpc('tools/list', {}, token))['tools']
        self.assertEqual([t['name'] for t in tools], ['read_project_file'])
        self.assertTrue(tools[0]['annotations']['readOnlyHint'])
        self.assertFalse(tools[0]['inputSchema']['additionalProperties'])
        self.assertEqual(self.io_calls, 0)
        body = self.result(await self.read(token=token, line_count=1,
                                           expected_sha256=hashlib.sha256(SENTINEL.encode()).hexdigest()))
        self.assertFalse(body['isError'], body)
        value = body['structuredContent']
        for key, expected in {'content': 'alpha source\n', 'context_ref': 'context-alpha',
            'owner_ref': 'owner-alpha', 'generation': 'generation-1', 'project_ref': 'alpha',
            'committed_head': '1' * 40, 'line_start': 0, 'line_end': 1, 'next_line': 1,
            'truncated': True, 'index_status': 'NOT_OBSERVED', 'atomic_workspace_snapshot': False}.items():
            self.assertEqual(value[key], expected)
        self.assertEqual(value['file_sha256'], hashlib.sha256(SENTINEL.encode()).hexdigest())
        self.assertEqual(value['content_bytes'], len(b'alpha source\n'))
        self.assertEqual(self.observations, 1)
        self.assertTrue(all(t != self.loop_thread for t in self.observer_threads))

    async def test_constructor_is_inert_and_missing_service_has_no_fallback(self):
        self.assertEqual((self.io_calls, self.resolves, self.observations), (0, 0, 0))
        for field in ('run_io', 'resolve_binding', 'audit_sink', 'authenticator', 'now', 'clock_ms'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.deployment.create_deployment(dataclasses.replace(self.services, **{field: None}))
        for hosts in ((), ('*',), ('127.0.0.1:*',)):
            with self.subTest(hosts=hosts), self.assertRaises(ValueError):
                self.deployment.create_deployment(dataclasses.replace(self.services, allowed_hosts=hosts))
        self.assertEqual((self.io_calls, self.resolves, self.observations), (0, 0, 0))

    async def test_closed_authority_fields_and_foreign_identity_refuse_before_io(self):
        for changes in ({'root': '/'}, {'subject_digest': self.subjects['beta']},
                        {'generation': 'generation-2'}, {'line_count': True}):
            self.withheld(await self.read(**changes), 'INVALID_REQUEST')
        self.withheld(await self.read('beta', token=self.token('alpha')))
        self.withheld(await self.read(token=self.token(client_id='wrong-client')))
        self.assertEqual((self.io_calls, self.observations), (0, 0))

    async def test_bad_signature_identity_resource_scope_and_expiry_never_reach_binding(self):
        for token in (self.token('stranger'), self.token(aud='https://other.example/mcp'),
                      self.token(scope='executive.read'), self.token(exp=self.clock - 1),
                      self.token()[:-20] + 'invalid-signature'):
            r = await self.read(token=token)
            self.assertIn(r.status_code, (401, 403))
            self.assertNotIn('alpha source', r.text)
        self.assertEqual((self.resolves, self.io_calls, self.observations), (0, 0, 0))

    async def test_hash_and_path_adversaries_withhold_real_file(self):
        for args in ({'expected_sha256': '0' * 64}, {'relative_path': '/etc/passwd'},
                     {'relative_path': '../beta/source.txt'}, {'relative_path': 'undeclared.txt'}):
            self.withheld(await self.read(**args))

    async def test_symlink_nonregular_hardlink_and_overflow_are_refused(self):
        path = self.root / 'alpha/source.txt'
        path.unlink()
        path.symlink_to(self.root / 'beta/source.txt')
        self.withheld(await self.read())
        path.unlink()
        path.mkdir()
        self.withheld(await self.read())
        path.rmdir()
        os.link(self.root / 'beta/source.txt', path)
        self.withheld(await self.read())
        path.unlink()
        path.write_bytes(b'x' * (1024 * 1024 + 1))
        self.withheld(await self.read())

    async def test_post_read_binding_revocation_withholds_completed_observation(self):
        self.return_gate.clear()
        task = asyncio.create_task(self.read())
        self.tasks.append(task)
        await asyncio.wait_for(self.completed.wait(), 5)
        self.assertEqual(self.observations, 1)
        self.active = False
        self.return_gate.set()
        self.withheld(await task)

    async def test_post_read_auth_policy_change_has_independent_withholding_fence(self):
        # Binding remains valid; only the real verifier's post-port policy changes.
        self.after_read = lambda: setattr(self.auth, '_policy',
            dataclasses.replace(self.policy, policy_id='changed.fixture'))
        response = await self.read()
        self.assertEqual(self.observations, 1)
        self.assertTrue(self.active)
        self.withheld(response, 'AUTHENTICATION_CHANGED')

    async def test_queued_revocation_refuses_without_file_content(self):
        self.before_io.clear()
        task = asyncio.create_task(self.read())
        self.tasks.append(task)
        await asyncio.wait_for(self.entered.wait(), 5)
        self.assertEqual(self.observations, 0)
        self.active = False
        self.before_io.set()
        self.withheld(await task)

    async def test_concurrent_readers_keep_roots_and_event_loop_progress(self):
        self.before_io.clear()
        a = asyncio.create_task(self.read('alpha'))
        b = asyncio.create_task(self.read('beta'))
        self.tasks.extend((a, b))
        await asyncio.wait_for(self.entered.wait(), 5)
        self.assertEqual(self.observations, 0)
        pulse = []
        asyncio.get_running_loop().call_soon(pulse.append, 'responsive')
        await asyncio.sleep(0)
        self.assertEqual(pulse, ['responsive'])
        self.before_io.set()
        av, bv = [self.result(r)['structuredContent'] for r in await asyncio.gather(a, b)]
        self.assertEqual(av['content'], SENTINEL)
        self.assertEqual(bv['content'], 'beta source\n')
        self.assertNotEqual(av['context_ref'], bv['context_ref'])
        self.assertNotEqual(av['file_identity_digest'], bv['file_identity_digest'])
        self.assertEqual(self.observations, 2)

    async def test_cancel_queued_request_does_not_admit_an_observer(self):
        self.before_io.clear()
        task = asyncio.create_task(self.read())
        self.tasks.append(task)
        await asyncio.wait_for(self.entered.wait(), 5)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.before_io.set()
        self.assertEqual(self.observations, 0)
        self.assertEqual(self.futures, [])

    async def test_malformed_observation_and_schema_widening_are_withheld(self):
        for mutation in ({'context_ref': 'wrong'}, {'project_ref': 'beta'},
                         {'index_status': 'OBSERVED'}, {'atomic_workspace_snapshot': True},
                         {'content': 'x' * 262144}, {'private': str(self.root)},
                         {'next_line': 999}, {'file_identity_digest': 'invalid'}):
            with self.subTest(mutation=next(iter(mutation))):
                self.transform = lambda result, change=mutation: {**result, **change}
                self.withheld(await self.read())

    async def test_audit_is_real_and_never_contains_credentials_or_roots(self):
        token = self.token()
        self.assertFalse(self.result(await self.read(token=token))['isError'])
        self.assertTrue(self.audit.events)
        audit = json.dumps(self.audit.events)
        for secret in (token, str(self.root), 'alpha source'):
            self.assertNotIn(secret, audit)
        self.assertTrue(all(set(event) == {'schema', 'policy_id', 'code', 'accepted'}
                            for event in self.audit.events))

    async def test_launch_requires_valid_policy_and_explicit_owner_callback(self):
        from scripts.mastermind_workbench_read_server import main
        import contextlib
        import io
        calls = []
        def serve(app, *, host, port):
            self.assertTrue(callable(app))
            calls.append((host, port))
        bad = dataclasses.replace(self.services,
                                  policy=dataclasses.replace(self.policy, policy_id='other.policy'))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['--port', '8765'], runtime_services=bad, serve=serve), 2)
            self.assertEqual(main(['--port', '8765'], runtime_services=self.services), 2)
        self.assertEqual(calls, [])
        self.assertEqual(main(['--port', '8765'], runtime_services=self.services, serve=serve), 0)
        self.assertEqual(calls, [('127.0.0.1', 8765)])
        self.assertEqual((self.resolves, self.io_calls), (0, 0))
        for fd in self.fds:
            os.fstat(fd)

    async def test_null_baseline_and_final_page_have_exact_schema_parity(self):
        self.scopes['alpha'] = dataclasses.replace(self.scopes['alpha'], committed_head=None)
        value = self.result(await self.read(line_start=1))['structuredContent']
        self.assertEqual(value['content'], 'second line\n')
        self.assertIsNone(value['committed_head'])
        self.assertFalse(value['truncated'])
        self.assertIsNone(value['next_line'])
        self.assertEqual(set(value), set(self.deployment.observation_schema()['properties']))

    async def test_real_observer_source_race_and_descriptor_cleanup(self):
        from integrations.workbench_read_mcp import read_port
        original = read_port.observe_file
        before = set(os.listdir('/dev/fd'))
        def raced(request, resolve_scope, *, clock_ms):
            return original(request, resolve_scope, clock_ms=clock_ms,
                _before_final=lambda: (self.root / 'alpha/source.txt').write_text('changed\n'))
        with patch.object(read_port, 'observe_file', raced):
            self.withheld(await self.read(), 'READ_SOURCE_CHANGED')
        # The real observer's duplicated root/file descriptors were closed.
        self.assertEqual(set(os.listdir('/dev/fd')), before)
        self.assertEqual(self.observations, 1)

    async def test_running_cancel_withholds_response_and_keeps_work_draining(self):
        from integrations.workbench_read_mcp import read_port
        original = read_port.observe_file
        started = asyncio.Event()
        release = threading.Event()
        loop = asyncio.get_running_loop()
        def barrier():
            loop.call_soon_threadsafe(started.set)
            if not release.wait(5):
                raise RuntimeError('fixture release timeout')
        def blocked(request, resolve_scope, *, clock_ms):
            return original(request, resolve_scope, clock_ms=clock_ms, _before_final=barrier)
        with patch.object(read_port, 'observe_file', blocked):
            task = asyncio.create_task(self.read())
            self.tasks.append(task)
            try:
                await asyncio.wait_for(started.wait(), 5)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertEqual(self.observations, 1)
                self.assertFalse(self.futures[0].done())
                self.assertEqual(self.slots._value, 1)
            finally:
                release.set()
            await asyncio.wait_for(asyncio.gather(*self.futures), 5)
            await asyncio.sleep(0)
            self.assertEqual(self.slots._value, 2)

    async def test_existing_executor_capacity_and_deadline_do_not_release_running_work(self):
        from integrations.workbench_read_mcp import read_port
        original = read_port.observe_file
        saturated = asyncio.Event()
        release = threading.Event()
        lock = threading.Lock()
        running = 0
        loop = asyncio.get_running_loop()
        def barrier():
            nonlocal running
            with lock:
                running += 1
                if running == 2:
                    loop.call_soon_threadsafe(saturated.set)
            if not release.wait(5):
                raise RuntimeError('fixture release timeout')
        def blocked(request, resolve_scope, *, clock_ms):
            return original(request, resolve_scope, clock_ms=clock_ms, _before_final=barrier)
        with patch.object(read_port, 'observe_file', blocked):
            tasks = [asyncio.create_task(self.read()) for _ in range(3)]
            self.tasks.extend(tasks)
            try:
                await asyncio.wait_for(saturated.wait(), 5)
                self.assertEqual(self.observations, 2)
                self.assertEqual(self.slots._value, 0)
                with self.assertRaises(asyncio.TimeoutError):
                    await asyncio.wait_for(asyncio.shield(tasks[0]), 0.01)
                self.assertFalse(tasks[0].done())
                self.assertTrue(all(not f.done() for f in self.futures))
                self.assertEqual(self.observations, 2)
            finally:
                release.set()
            results = await asyncio.wait_for(asyncio.gather(*tasks), 5)
            for result in results:
                self.assertFalse(self.result(result)['isError'])
            self.assertEqual(self.observations, 3)
            self.assertEqual(self.slots._value, 2)


class MutationDiscriminators(unittest.TestCase):
    """Run identical real tests against baseline and process-local bypasses.

    A kill requires one intended assertion failure and no setup/runtime errors.
    These controls change only in-memory test bindings; protected files stay intact.
    """

    def test_same_assertions_detect_seven_real_boundary_bypasses(self):
        from integrations.workbench_read_mcp import deployment, read_port, app
        from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
        original_observer = read_port.observe_file
        original_verify = MastermindTokenVerifier.verify_token
        original_resolver = CompositionTests.resolve

        def fabricated(request, resolve_scope, *, clock_ms):
            scope = resolve_scope()
            # Deliberately disconnect the descriptor observer, while presenting a
            # complete schema-valid page. Content assertion must expose the fake.
            return {'status': 'OK', 'relative_path': request['relative_path'],
                'context_ref': scope.context_ref, 'owner_ref': scope.owner_ref,
                'generation': scope.generation, 'view_kind': 'WORKING_TREE',
                'committed_head': scope.committed_head,
                'file_sha256': hashlib.sha256(SENTINEL.encode()).hexdigest(),
                'file_identity_digest': '0' * 64, 'observation_digest': '0' * 64,
                'file_bytes': len(SENTINEL.encode()), 'content': 'wrong source\n',
                'content_bytes': len(b'wrong source\n'), 'total_lines': 2,
                'line_start': 0, 'line_end': 1, 'truncated': True, 'next_line': 1,
                'observed_at_ms': clock_ms(), 'index_status': 'NOT_OBSERVED',
                'atomic_workspace_snapshot': False}

        async def synchronous(case, operation):
            case.io_calls += 1
            case.observations += 1
            case.observer_threads.append(threading.get_ident())
            return operation()

        def crosswired(case, caller, project):
            binding = original_resolver(case, caller, project)
            return dataclasses.replace(binding, scope=case.scopes['beta']) if binding else None

        source = inspect.getsource(read_port.create_descriptor_read_port)
        target = '            current_scope()\n'
        self.assertEqual(source.count(target), 1)
        namespace = dict(read_port.__dict__)
        exec(compile(source.replace(target, '', 1), '<read0-post-await-control>', 'exec'), namespace)

        cached = {}
        async def bypass_post_auth(verifier, token):
            access = await original_verify(verifier, token)
            if access is not None:
                cached[(id(verifier), token)] = access
                return access
            return cached.get((id(verifier), token))

        def forged_hash(request, resolve_scope, *, clock_ms):
            # Corrupt the observer's expected-hash enforcement and reported hash,
            # without replacing signature verification, port or actual file I/O.
            value = original_observer({k: v for k, v in request.items() if k != 'expected_sha256'},
                                      resolve_scope, clock_ms=clock_ms)
            return {**value, 'file_sha256': '0' * 64}

        @contextlib.contextmanager
        def authority_bypass():
            schema = json.loads(json.dumps(app.INPUT_SCHEMA))
            schema['properties']['root'] = {'type': 'string'}
            with patch.object(app, 'INPUT_SCHEMA', schema), \
                 patch.object(read_port, '_REQUEST_KEYS', read_port._REQUEST_KEYS | {'root'}):
                yield

        positive = 'test_initialize_list_and_real_attributed_read'
        controls = [
            ('fake-observer', positive, lambda: patch.object(read_port, 'observe_file', fabricated),
             "'wrong source\\n' != 'alpha source\\n'"),
            ('synchronous-executor', positive, lambda: patch.object(CompositionTests, 'run_io', synchronous),
             'False is not true'),
            ('crosswired-binding', 'test_concurrent_readers_keep_roots_and_event_loop_progress',
             lambda: patch.object(CompositionTests, 'resolve', crosswired),
             "'beta source\\n' != 'alpha source\\nsecond line\\n'"),
            ('post-await-binding', 'test_post_read_binding_revocation_withholds_completed_observation',
             lambda: patch.object(deployment, 'create_descriptor_read_port', namespace['create_descriptor_read_port']),
             'False is not true'),
            ('post-read-auth', 'test_post_read_auth_policy_change_has_independent_withholding_fence',
             lambda: patch.object(MastermindTokenVerifier, 'verify_token', bypass_post_auth),
             'False is not true'),
            ('model-authority', 'test_closed_authority_fields_and_foreign_identity_refuse_before_io',
             authority_bypass, 'False is not true'),
            ('forged-observer-hash', 'test_hash_and_path_adversaries_withhold_real_file',
             lambda: patch.object(read_port, 'observe_file', forged_hash), 'False is not true'),
        ]
        for name, method, mutation, assertion in controls:
            with self.subTest(control=name):
                baseline = unittest.TextTestRunner(stream=io.StringIO()).run(
                    unittest.TestSuite([CompositionTests(method)]))
                self.assertTrue(baseline.wasSuccessful(), baseline.errors or baseline.failures)
                output = io.StringIO()
                with mutation():
                    mutant = unittest.TextTestRunner(stream=output).run(
                        unittest.TestSuite([CompositionTests(method)]))
                # Shape checks are outside the changed test's assertion handling.
                self.assertEqual(mutant.testsRun, 1)
                self.assertEqual(mutant.errors, [], output.getvalue())
                self.assertEqual(len(mutant.failures), 1, output.getvalue())
                self.assertIn(assertion, mutant.failures[0][1])
                print(json.dumps({'mutation': name, 'same_test': method, 'baseline': 'PASS',
                                  'mutant': 'INTENDED_ASSERTION_FAILURE',
                                  'failure': mutant.failures[0][1]}, sort_keys=True))


if __name__ == '__main__':
    unittest.main()
