#!/usr/bin/env python3
"""Inert diagnostics tests for fabric_operator_stop. Fake network and temp dirs only."""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import fabric_operator_stop as fos

TOKEN = 'ab' * 32
ROOT = 'test_root'
PARENT = 'test_parent'
CHILD = 'test_child'
DIGEST = 'cd' * 32
SECRET = 'SECRETTOKEN_inert_fixture_only'
PRIVATE_PATH = '/inert/private/fixture-path'


class FakeHeaders:
    def __init__(self, items=None):
        self._items = dict(items or {})

    def get(self, key, default=None):
        return self._items.get(key, default)


class FakeResponse:
    def __init__(self, body=b'{}', headers=None):
        self._body = body if isinstance(body, bytes) else body.encode('utf-8')
        self.headers = FakeHeaders(headers)

    def read(self, n=-1):
        if n is None or n < 0:
            return self._body
        return self._body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeOpener:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def open(self, req, timeout=None):
        method = req.get_method() if hasattr(req, 'get_method') else 'GET'
        self.calls.append((method, timeout))
        if not self.script:
            raise OSError('inert_exhausted')
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def _tool_body(summary):
    inner = json.dumps(summary)
    return json.dumps({'result': {'content': [{'text': inner}]}}).encode()


def _mcp_ok(children):
    session = {'Mcp-Session-Id': 'inert-session'}
    summary = {'root': ROOT, 'parent': PARENT, 'children': children}
    return [
        FakeResponse(b'{"result":{}}', session),
        FakeResponse(b'{}'),
        FakeResponse(_tool_body(summary)),
        FakeResponse(b''),
    ]


@contextmanager
def _stdio(raw):
    if isinstance(raw, str):
        raw = raw.encode('utf-8')
    old = sys.stdin, sys.stdout, sys.stderr
    sys.stdin = io.TextIOWrapper(io.BytesIO(raw), encoding='utf-8')
    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()
    try:
        yield sys.stdout, sys.stderr
    finally:
        sys.stdin, sys.stdout, sys.stderr = old


def _env():
    return {
        'FABRIC_OPERATOR_CAPABILITY': TOKEN,
        'POOL_ORCHESTRATOR_ID': ROOT,
        'REMOTE_SUB_RUN_ID': PARENT,
    }


def _codes(err):
    return [line for line in err.getvalue().splitlines() if line]


def _assert_redacted(test, text):
    test.assertNotIn(SECRET, text)
    test.assertNotIn(PRIVATE_PATH, text)
    test.assertNotIn(TOKEN, text)
    test.assertNotIn(fos.ENDPOINT, text)
    for line in text.splitlines():
        if line:
            test.assertIn(line, fos.EVENTS)


class OperatorStopDiagnosticsTest(unittest.TestCase):
    def test_secret_exception_redaction(self):
        opener = FakeOpener([RuntimeError('token=' + SECRET + ' path=' + PRIVATE_PATH)])
        with mock.patch.dict(os.environ, _env()), _stdio(json.dumps({'hook_event_name': 'Stop'})) as (out, err):
            fos.run(opener=opener, directory=Path(tempfile.gettempdir()))
        self.assertEqual(out.getvalue().strip(), '{}')
        codes = _codes(err)
        self.assertIn('operator_stop:hook_entered', codes)
        self.assertIn('operator_stop:mcp_initialize', codes)
        self.assertIn('operator_stop:mcp_error', codes)
        self.assertIn('operator_stop:observation_error', codes)
        _assert_redacted(self, err.getvalue())

    def test_parse_failure(self):
        with mock.patch.dict(os.environ, _env()), _stdio(b'not-json{'):
            out, err = sys.stdout, sys.stderr
            fos.run(opener=FakeOpener([]), directory=Path(tempfile.gettempdir()))
        self.assertEqual(out.getvalue().strip(), '{}')
        codes = _codes(err)
        self.assertEqual(codes[0], 'operator_stop:hook_entered')
        self.assertIn('operator_stop:parse_failure', codes)
        self.assertIn('operator_stop:observation_error', codes)
        self.assertNotIn('operator_stop:decision_block', codes)
        _assert_redacted(self, err.getvalue())

    def test_missing_binding(self):
        env = _env()
        env['REMOTE_SUB_RUN_ID'] = ''
        with mock.patch.dict(os.environ, env, clear=False), _stdio(json.dumps({'hook_event_name': 'Stop'})) as (out, err):
            fos.run(opener=FakeOpener([]), directory=Path(tempfile.gettempdir()))
        self.assertEqual(out.getvalue(), '')
        codes = _codes(err)
        self.assertIn('operator_stop:hook_entered', codes)
        self.assertIn('operator_stop:exit_no_binding', codes)
        self.assertNotIn('operator_stop:mcp_initialize', codes)
        self.assertNotIn('operator_stop:observation_error', codes)
        _assert_redacted(self, err.getvalue())

    def test_successful_no_child(self):
        opener = FakeOpener(_mcp_ok([]))
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, _env()), _stdio(json.dumps({'hookEventName': 'stop'})) as (out, err):
                fos.run(opener=opener, directory=Path(tmp))
            self.assertEqual(out.getvalue(), '')
            self.assertEqual(os.listdir(tmp), [])
        codes = _codes(err)
        self.assertIn('operator_stop:hook_entered', codes)
        self.assertIn('operator_stop:mcp_initialize', codes)
        self.assertIn('operator_stop:mcp_query', codes)
        self.assertIn('operator_stop:decision_quiet', codes)
        self.assertNotIn('operator_stop:decision_block', codes)
        self.assertNotIn('operator_stop:mcp_error', codes)
        self.assertNotIn('operator_stop:observation_error', codes)
        _assert_redacted(self, err.getvalue())

    def test_decision_persist_result(self):
        children = [{'run_id': CHILD, 'result_available': True, 'sha256': DIGEST, 'bytes': 4}]
        opener = FakeOpener(_mcp_ok(children))
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            with mock.patch.dict(os.environ, _env()), _stdio(json.dumps({'hook_event_name': 'Stop'})) as (out, err):
                fos.run(opener=opener, directory=directory)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload['decision'], 'block')
            self.assertIn('unacknowledged work', payload['reason'])
            names = os.listdir(tmp)
            self.assertEqual(len(names), 1)
            self.assertTrue(names[0].startswith(PARENT + '.operator-attention.'))
            self.assertTrue(names[0].endswith('.json'))
            receipt = json.loads((directory / names[0]).read_text())
            self.assertEqual(receipt['decision'], 'block')
            self.assertTrue(receipt['attention_only'])
            self.assertEqual(receipt['root'], ROOT)
            self.assertEqual(receipt['parent'], PARENT)
        codes = _codes(err)
        self.assertIn('operator_stop:hook_entered', codes)
        self.assertIn('operator_stop:mcp_initialize', codes)
        self.assertIn('operator_stop:mcp_query', codes)
        self.assertIn('operator_stop:decision_block', codes)
        self.assertIn('operator_stop:attention_persist', codes)
        self.assertNotIn('operator_stop:observation_error', codes)
        self.assertEqual([n for t, n in opener.calls if t == 'POST'], [4, 4, 4])
        self.assertIn(('DELETE', 2), opener.calls)
        _assert_redacted(self, err.getvalue())

    def test_observation_error_phase(self):
        opener = FakeOpener([FakeResponse(b'{"error":{"code":-1}}')])
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, _env()), _stdio(json.dumps({'hook_event_name': 'Stop'})) as (out, err):
                fos.run(opener=opener, directory=Path(tmp))
            self.assertEqual(os.listdir(tmp), [])
        self.assertEqual(out.getvalue().strip(), '{}')
        codes = _codes(err)
        self.assertIn('operator_stop:hook_entered', codes)
        self.assertIn('operator_stop:mcp_initialize', codes)
        self.assertIn('operator_stop:mcp_error', codes)
        self.assertIn('operator_stop:observation_error', codes)
        self.assertNotIn('operator_stop:mcp_query', codes)
        self.assertNotIn('operator_stop:decision_block', codes)
        self.assertNotIn('operator_stop:attention_persist', codes)
        _assert_redacted(self, err.getvalue())

    def test_attention_error_phase(self):
        children = [{'run_id': CHILD, 'result_available': True, 'sha256': DIGEST, 'bytes': 4}]
        opener = FakeOpener(_mcp_ok(children))
        fd, name = tempfile.mkstemp()
        os.close(fd)
        try:
            with mock.patch.dict(os.environ, _env()), _stdio(json.dumps({'hook_event_name': 'Stop'})) as (out, err):
                fos.run(opener=opener, directory=Path(name))
        finally:
            os.unlink(name)
        self.assertEqual(out.getvalue().strip(), '{}')
        codes = _codes(err)
        self.assertIn('operator_stop:decision_block', codes)
        self.assertIn('operator_stop:attention_error', codes)
        self.assertIn('operator_stop:observation_error', codes)
        self.assertNotIn('operator_stop:attention_persist', codes)
        _assert_redacted(self, err.getvalue())

    def test_exit_non_stop(self):
        with mock.patch.dict(os.environ, _env()), _stdio(json.dumps({'hook_event_name': 'Prompt'})) as (out, err):
            fos.run(opener=FakeOpener([]), directory=Path(tempfile.gettempdir()))
        self.assertEqual(out.getvalue(), '')
        codes = _codes(err)
        self.assertIn('operator_stop:exit_non_stop', codes)
        self.assertNotIn('operator_stop:mcp_initialize', codes)


if __name__ == '__main__':
    unittest.main()
