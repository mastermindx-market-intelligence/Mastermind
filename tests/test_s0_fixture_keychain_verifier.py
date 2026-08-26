from __future__ import annotations

import ctypes
import importlib
import io
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def _helper():
    return importlib.import_module('scripts.verify_s0_fixture_metadata_from_keychain')


def _token() -> bytes:
    return b'xoxb-' + b'A1-' * 12


def _pass_receipt(helper) -> bytes:
    return (
        json.dumps(
            {
                'bot_id': 'B0BRHCMFN6T',
                'bot_user_id': helper._EXPECTED_BOT_USER_ID,
                'schema': helper.verifier.RECEIPT_SCHEMA,
                'scopes': sorted(helper._EXPECTED_SCOPES),
                'status': 'PASS',
                'team_id': helper._EXPECTED_TEAM_ID,
            },
            sort_keys=True,
            separators=(',', ':'),
        ).encode('utf-8')
        + b'\n'
    )


def test_fixed_coordinates_and_login_keychain_path_ignore_ambient_search():
    helper = _helper()
    assert helper._KEYCHAIN_SERVICE == b'mastermind-s0-fixture-slack-bot-token'
    assert helper._KEYCHAIN_ACCOUNT == b'mastermind-s0-fixture-bot'

    record = SimpleNamespace(pw_dir='/Users/chris')
    path = helper._login_keychain_path(uid_fn=lambda: 501, pwd_lookup=lambda uid: record)
    assert path == b'/Users/chris/Library/Keychains/login.keychain-db'


def test_security_framework_reads_only_explicit_login_keychain_ref():
    helper = _helper()
    token = _token()
    backing = ctypes.create_string_buffer(token)
    calls = []

    class Fn:
        def __init__(self, fn):
            self.fn = fn
            self.argtypes = None
            self.restype = None

        def __call__(self, *args):
            return self.fn(*args)

    def open_keychain(path, out_ref):
        calls.append(('open', path))
        ctypes.cast(out_ref, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(0xA11CE)
        return 0

    def find_password(
        keychain,
        service_len,
        service,
        account_len,
        account,
        password_len,
        password_data,
        item_ref,
    ):
        calls.append(('find', keychain.value, service, account))
        assert keychain.value == 0xA11CE
        ctypes.cast(password_len, ctypes.POINTER(ctypes.c_uint32))[0] = len(token)
        ctypes.cast(password_data, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(
            ctypes.addressof(backing)
        )
        return 0

    def free_content(_attrs, data):
        calls.append(('free', data.value))
        return 0

    def release(ref):
        calls.append(('release', ref.value))

    security = SimpleNamespace(
        SecKeychainOpen=Fn(open_keychain),
        SecKeychainFindGenericPassword=Fn(find_password),
        SecKeychainItemFreeContent=Fn(free_content),
    )
    core = SimpleNamespace(CFRelease=Fn(release))

    def loader(path):
        if path == helper._SECURITY_FRAMEWORK:
            return security
        if path == helper._CORE_FOUNDATION:
            return core
        raise AssertionError(path)

    api = helper._SecurityFramework(
        loader=loader,
        login_keychain_path_fn=lambda: b'/Users/chris/Library/Keychains/login.keychain-db',
    )
    secret = api.read_secret()
    assert bytes(secret) == token
    assert calls[0] == ('open', b'/Users/chris/Library/Keychains/login.keychain-db')
    assert calls[1] == (
        'find',
        0xA11CE,
        helper._KEYCHAIN_SERVICE,
        helper._KEYCHAIN_ACCOUNT,
    )
    assert calls[-1] == ('release', 0xA11CE)


def test_cli_refuses_any_caller_selected_coordinate_before_keychain_access():
    helper = _helper()
    out = io.StringIO()
    code = helper.main(
        ['--keychain', 'System', '--service', 'other'],
        stdout=out,
        api_factory=lambda: (_ for _ in ()).throw(AssertionError('must not open Keychain')),
    )
    assert code == 2
    assert json.loads(out.getvalue()) == {
        'error': 'METADATA_ARGUMENTS_REFUSED',
        'schema': helper.verifier.RECEIPT_SCHEMA,
        'status': 'ERROR',
    }


def test_valid_secret_reaches_verifier_only_through_anonymous_stdin_pipe_and_is_zeroed():
    helper = _helper()
    token = _token()
    secret = bytearray(token)
    captured = {}

    class Api:
        def read_secret(self):
            return secret

    def runner(argv, **kwargs):
        captured['argv'] = list(argv)
        captured['input_ref'] = kwargs['input']
        captured['input_snapshot'] = bytes(kwargs['input'])
        captured['env'] = kwargs['env']
        captured['shell'] = kwargs['shell']
        captured['stdin_via_input'] = 'stdin' not in kwargs
        return subprocess.CompletedProcess(argv, 0, _pass_receipt(helper), b'')

    out = io.StringIO()
    code = helper.main([], stdout=out, api_factory=Api, runner=runner)
    assert code == 0
    assert captured['input_snapshot'] == token
    assert captured['input_ref'] is secret
    assert secret == bytearray(b'\x00' * len(token))
    assert captured['env'] == {}
    assert captured['shell'] is False
    assert captured['stdin_via_input'] is True
    assert not any(token.decode('ascii') in arg for arg in captured['argv'])
    assert captured['argv'] == [
        sys.executable,
        str(helper._VERIFIER_SCRIPT),
        '--expected-team-id',
        'T0BRD2AQXQV',
        '--expected-bot-user-id',
        'U0BST4WG996',
        '--expected-scope',
        'groups:history',
        '--expected-scope',
        'chat:write',
    ]
    assert json.loads(out.getvalue())['status'] == 'PASS'
    assert token.decode('ascii') not in out.getvalue()


@pytest.mark.parametrize(
    'value',
    [
        b'not-a-token',
        b'xoxp-' + b'a' * 30,
        b'xoxb-short',
        b'xoxb-' + b'a' * 1001,
        b'xoxb-' + b'a' * 30 + b'\n',
    ],
)
def test_malformed_secret_never_reaches_network_verifier(value):
    helper = _helper()
    out = io.StringIO()

    class Api:
        def read_secret(self):
            return bytearray(value)

    code = helper.main(
        [],
        stdout=out,
        api_factory=Api,
        runner=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError('malformed secret reached verifier')
        ),
    )
    assert code == 2
    assert json.loads(out.getvalue())['error'] == 'METADATA_INPUT_REFUSED'
    assert value.decode('ascii', errors='ignore') not in out.getvalue()


@pytest.mark.parametrize('leak_surface', ['stdout', 'stderr'])
def test_synthetic_credential_shaped_child_leak_is_replaced_with_fixed_error(leak_surface):
    helper = _helper()
    token = _token()
    canary = b'xoxb-LEAKCANARY-12345678901234567890'

    class Api:
        def read_secret(self):
            return bytearray(token)

    def runner(argv, **kwargs):
        if leak_surface == 'stdout':
            return subprocess.CompletedProcess(argv, 2, b'{"debug":"' + canary + b'"}\n', b'')
        return subprocess.CompletedProcess(argv, 2, b'', canary)

    out = io.StringIO()
    code = helper.main([], stdout=out, api_factory=Api, runner=runner)
    assert code == 2
    assert json.loads(out.getvalue()) == {
        'error': 'SECRET_SURFACE_REFUSED',
        'schema': helper.verifier.RECEIPT_SCHEMA,
        'status': 'ERROR',
    }
    assert canary.decode('ascii') not in out.getvalue()


def test_unexpected_child_stderr_or_extra_receipt_fields_fail_closed():
    helper = _helper()
    token = _token()

    class Api:
        def read_secret(self):
            return bytearray(token)

    def stderr_runner(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 2, b'', b'opaque child noise')

    out = io.StringIO()
    assert helper.main([], stdout=out, api_factory=Api, runner=stderr_runner) == 2
    assert json.loads(out.getvalue())['error'] == 'METADATA_RESPONSE_REFUSED'

    payload = json.loads(_pass_receipt(helper))
    payload['debug'] = 'not allowed'

    def extra_runner(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv,
            0,
            (json.dumps(payload) + '\n').encode('utf-8'),
            b'',
        )

    out = io.StringIO()
    assert helper.main([], stdout=out, api_factory=Api, runner=extra_runner) == 2
    assert json.loads(out.getvalue())['error'] == 'METADATA_RESPONSE_REFUSED'


def test_static_fences_forbid_ambient_keychain_shell_temp_and_secret_carriers():
    helper = _helper()
    text = Path(helper.__file__).read_text(encoding='utf-8')
    lowered = text.lower()
    assert 'SecKeychainOpen' in text
    assert 'SecKeychainFindGenericPassword' in text
    assert 'login.keychain-db' in text
    for forbidden in (
        'seckeychaincopydefault',
        'seckeychaincopysearchlist',
        'system.keychain',
        '/usr/bin/security',
        'find-generic-password',
        'security ... -w',
        'shell=true',
        'tempfile',
        'namedtemporaryfile',
        'mkstemp',
        '--token',
        'os.environ',
        'os.getenv(',
        'logging.',
    ):
        assert forbidden not in lowered
