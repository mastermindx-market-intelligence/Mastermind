"""Focused tests for the private project-conversation read wire contract."""

import hashlib
import json

import pytest

from common.project_conversation_read_contract import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    OPERATIONS,
    SCHEMA,
    arguments,
    decode_frame,
    encode_frame,
    frame,
)

FRESH_REFERENCE_SCHEMA = 'mastermind.fresh_conversation_reference.v1'
READ_SCOPE = 'mastermind.executive.read'
SCOPE_SUBMIT = 'mastermind.executive.intent.submit'


def hex64(seed=0):
    return format(seed, '064x')


def sha256_hex(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def legacy_work_ref():
    return 'WS:AB-CD01'


def fresh_work_ref():
    return 'WS:proj.alpha-1'


def principal():
    issuer = 'https://issuer.example.test'
    return {
        'policy_id': 'policy.read.v1',
        'issuer': issuer,
        'issuer_digest': sha256_hex(issuer),
        'resource': 'urn:mastermind:project-conversations',
        'subject_digest': hex64(1),
        'client_ref': 'client-alpha',
        'scopes': [READ_SCOPE],
        'issued_at': 1000,
        'expires_at': 2000,
        'jti_digest': hex64(2),
    }


def catalogue_args():
    return {'work_ref': legacy_work_ref()}


def read_args():
    return {
        'work_ref': legacy_work_ref(),
        'conversation_ref': 'conversation-' + hex64(3),
        'revision': hex64(4),
        'requests': [
            {'read_ref': 'session-reply-' + hex64(5), 'request_revision': hex64(6)},
        ],
    }


def fresh_references_args():
    return {'work_ref': fresh_work_ref()}


def fresh_read_args():
    return {
        'schema': FRESH_REFERENCE_SCHEMA,
        'work_ref': fresh_work_ref(),
        'root_job_id': 'JOB-123456',
        'root_event_id': 12345,
        'root_event_sha256': hex64(7),
        'principal_scope_sha256': hex64(8),
    }


def execution_references_args():
    return {'work_ref': legacy_work_ref()}


def execution_read_args():
    return {
        **fresh_read_args(),
        'schema': 'mastermind.project_execution_reference.v1',
        'work_ref': legacy_work_ref(),
        'project_execution_source_sha256': hex64(9),
    }


ARGS_FACTORIES = {
    'catalogue': catalogue_args,
    'read': read_args,
    'fresh_references': fresh_references_args,
    'fresh_read': fresh_read_args,
    'execution_references': execution_references_args,
    'execution_read': execution_read_args,
}


def make_frame(operation='read'):
    return {
        'schema': SCHEMA,
        'operation': operation,
        'principal': principal(),
        'arguments': ARGS_FACTORIES[operation](),
    }


def read_request(read_seed, revision_seed):
    return {
        'read_ref': 'session-reply-' + hex64(read_seed),
        'request_revision': hex64(revision_seed),
    }


def raw_of(value, **dumps_kwargs):
    return (json.dumps(value, **dumps_kwargs) + '\n').encode('utf-8')


def test_contract_constants():
    assert SCHEMA == 'mastermind.project_conversation_read.private.v1'
    assert OPERATIONS == ('catalogue', 'read', 'fresh_references', 'fresh_read',
                          'execution_references', 'execution_read')
    assert MAX_REQUEST_BYTES == 8192
    assert MAX_RESPONSE_BYTES == 32768


def test_positive_arguments_all_operations():
    for operation in OPERATIONS:
        value = ARGS_FACTORIES[operation]()
        result = arguments(value, operation)
        assert result == value
        assert type(result) is dict


def test_positive_cursor_explicit_none():
    value = {'work_ref': legacy_work_ref(), 'cursor': None}
    assert arguments(value, 'catalogue') == value
    padded = {'work_ref': legacy_work_ref(), 'cursor': 'ab_3-='}
    assert arguments(padded, 'catalogue') == padded


def test_positive_frame_all_operations():
    for operation in OPERATIONS:
        value = make_frame(operation)
        assert frame(value) == value


def test_encode_decode_roundtrip_all_operations():
    for operation in OPERATIONS:
        value = make_frame(operation)
        encoded = encode_frame(value)
        assert encoded.endswith(b'\n')
        assert not encoded.endswith(b'\n\n')
        assert b', ' not in encoded and b'": ' not in encoded
        assert encoded.index(b'"arguments"') < encoded.index(b'"operation"')
        assert encoded.index(b'"operation"') < encoded.index(b'"principal"')
        assert list(json.loads(encoded)) == ['arguments', 'operation', 'principal', 'schema']
        decoded = decode_frame(encoded)
        assert decoded == frame(value)
        assert decode_frame(encode_frame(decoded)) == decoded


def test_encode_is_utf8_and_not_ascii_escaped():
    value = make_frame('catalogue')
    value['principal']['policy_id'] = 'policy.read.wïth-ünïcode'
    encoded = encode_frame(value)
    assert 'wïth-ünïcode'.encode('utf-8') in encoded
    assert b'\\u' not in encoded
    assert decode_frame(encoded) == frame(value)


def test_frame_and_arguments_detached():
    value = make_frame('read')
    seen = frame(value)
    assert seen['principal'] is not value['principal']
    assert seen['arguments']['requests'][0] is not value['arguments']['requests'][0]
    value['principal']['policy_id'] = 'mutated'
    value['arguments']['requests'].append(read_request(9, 10))
    assert seen['principal']['policy_id'] == 'policy.read.v1'
    assert len(seen['arguments']['requests']) == 1
    seen['arguments']['work_ref'] = 'WS:MUTATED'
    assert value['arguments']['work_ref'] == legacy_work_ref()
    source = read_args()
    result = arguments(source, 'read')
    source['requests'].append(read_request(11, 12))
    assert len(result['requests']) == 1
    decoded = decode_frame(encode_frame(make_frame('read')))
    decoded['principal']['scopes'].append(SCOPE_SUBMIT)
    assert decode_frame(encode_frame(make_frame('read')))['principal']['scopes'] == [READ_SCOPE]


def test_decode_accepts_trailing_whitespace_and_internal_spaces():
    value = make_frame('catalogue')
    expected = frame(value)
    assert decode_frame(raw_of(value)) == expected
    assert decode_frame(raw_of(value) + b' \t\r\n') == expected
    assert decode_frame(raw_of(value, indent=None, separators=(', ', ': '))) == expected


def test_arguments_reject_unknown_operation():
    with pytest.raises(ValueError):
        arguments(catalogue_args(), 'write')
    with pytest.raises(ValueError):
        arguments(catalogue_args(), 'READ')
    with pytest.raises(ValueError):
        arguments(catalogue_args(), None)
    with pytest.raises(ValueError):
        arguments(catalogue_args(), 5)


def test_arguments_reject_non_object():
    for value in (None, ['work_ref'], 'WS:AB', 5, True):
        with pytest.raises(ValueError):
            arguments(value, 'catalogue')


def test_reject_extra_selectors():
    with pytest.raises(ValueError):
        arguments(dict(catalogue_args(), conversation_ref='conversation-' + hex64(3)), 'catalogue')
    with pytest.raises(ValueError):
        arguments(dict(catalogue_args(), requests=[read_request(5, 6)]), 'catalogue')
    with pytest.raises(ValueError):
        arguments(dict(read_args(), cursor='abc'), 'read')
    with pytest.raises(ValueError):
        arguments(dict(fresh_references_args(), cursor='abc'), 'fresh_references')
    with pytest.raises(ValueError):
        arguments(read_args(), 'fresh_references')
    extra_top = make_frame('read')
    extra_top['target'] = 'urn:example'
    with pytest.raises(ValueError):
        frame(extra_top)
    missing = make_frame('read')
    del missing['principal']
    with pytest.raises(ValueError):
        frame(missing)


def test_reject_workspace_principal_public_principal_and_token_fields():
    for extra in ('workspace', 'workspace_principal', 'public_principal', 'token', 'Workspace'):
        principal_value = principal()
        principal_value[extra] = 'urn:example'
        with pytest.raises(ValueError):
            frame(dict(make_frame('read'), principal=principal_value))
    with pytest.raises(ValueError):
        arguments(
            dict(catalogue_args(), workspace_principal='urn:example'),
            'catalogue',
        )
    with pytest.raises(ValueError):
        arguments(
            dict(fresh_read_args(), operation_key='read'),
            'fresh_read',
        )


def test_reject_operation_key_selector():
    with pytest.raises(ValueError):
        frame(dict(make_frame('read'), operation_key='read'))
    with pytest.raises(ValueError):
        arguments(dict(catalogue_args(), operation_key='catalogue'), 'catalogue')


def test_reject_mixed_reference_selectors():
    with pytest.raises(ValueError):
        arguments(dict(read_args(), root_job_id='JOB-1'), 'read')
    with pytest.raises(ValueError):
        arguments(dict(fresh_read_args(), conversation_ref='conversation-' + hex64(3)), 'fresh_read')
    with pytest.raises(ValueError):
        arguments(dict(read_args(), schema=FRESH_REFERENCE_SCHEMA), 'read')
    wrong_schema = fresh_read_args()
    wrong_schema['schema'] = SCHEMA
    with pytest.raises(ValueError):
        arguments(wrong_schema, 'fresh_read')
    with pytest.raises(ValueError):
        frame(dict(make_frame('catalogue'), arguments=read_args()))


def test_reject_bad_legacy_work_ref():
    bad = (
        'ws:AB-CD',
        'WS:ab',
        'WS:AB-CD\n',
        ' WS:AB-CD',
        'WS:AB-CD ',
        'WS:A',
        'WS:' + 'A' * 65,
        'WS:AB-',
        'WS:-AB',
        'WS:AB CD',
        'WS:AB_CD',
        'WS:',
        123,
        None,
    )
    for value in bad:
        with pytest.raises(ValueError):
            arguments({'work_ref': value}, 'catalogue')
    assert arguments({'work_ref': 'WS:AB-01-XY-99'}, 'catalogue') == {
        'work_ref': 'WS:AB-01-XY-99',
    }
    key_edge = 'WS:' + 'A' * 64
    assert arguments(dict(read_args(), work_ref=key_edge), 'read') == dict(read_args(), work_ref=key_edge)


def test_reject_bad_fresh_work_ref():
    bad = (
        'ws:abc',
        'WS:',
        'WS:/tmp',
        'WS:abc\n',
        'WS:' + 'a' * 70,
        'WS:abc def',
    )
    for value in bad:
        with pytest.raises(ValueError):
            arguments({'work_ref': value}, 'fresh_references')
    edge = 'WS:' + 'a' * 69
    assert len(edge) == 72
    assert arguments({'work_ref': edge}, 'fresh_references') == {'work_ref': edge}


def test_reject_bad_conversation_revision_and_read_refs():
    bad_conversation = (
        'CONVERSATION-' + hex64(0xab),
        'conversation-' + hex64(0xab).upper(),
        'conversation-' + hex64(3)[:63],
        hex64(3),
        'conversation-' + hex64(3) + '\n',
    )
    for value in bad_conversation:
        with pytest.raises(ValueError):
            arguments(dict(read_args(), conversation_ref=value), 'read')
    for value in (hex64(0xcd).upper(), hex64(4)[:63], 5, True):
        with pytest.raises(ValueError):
            arguments(dict(read_args(), revision=value), 'read')
    bad_read_ref = (
        'session-reply-' + hex64(0xab).upper(),
        'session-reply_' + hex64(5),
        'session-reply-' + hex64(5)[:63],
        'other-' + hex64(5),
    )
    for value in bad_read_ref:
        with pytest.raises(ValueError):
            arguments(
                dict(read_args(), requests=[{'read_ref': value, 'request_revision': hex64(6)}]),
                'read',
            )


def test_reject_bad_cursor():
    for value in ('', 'a b', 'a#b', 'a/b', 'a\nb', 'x' * 2049, 'ä'):
        with pytest.raises(ValueError):
            arguments({'work_ref': legacy_work_ref(), 'cursor': value}, 'catalogue')
    assert arguments({'work_ref': legacy_work_ref(), 'cursor': 'x' * 2048}, 'catalogue') == {
        'work_ref': legacy_work_ref(),
        'cursor': 'x' * 2048,
    }


def test_reject_bad_requests_array():
    base = read_args()
    for bad in (
        [],
        [read_request(5, 6), read_request(7, 8), read_request(9, 10), read_request(11, 12), read_request(13, 14)],
        [read_request(5, 6), read_request(5, 6)],
        [read_request(5, 6), read_request(5, 8)],
        {'read_ref': 'session-reply-' + hex64(5)},
        'session-reply-' + hex64(5),
        None,
        [dict(read_request(5, 6), extra=True)],
        [{'read_ref': 'session-reply-' + hex64(5)}],
        [{'request_revision': hex64(6)}],
    ):
        with pytest.raises(ValueError):
            arguments(dict(base, requests=bad), 'read')
    four = [read_request(5, 6), read_request(7, 8), read_request(9, 10), read_request(11, 12)]
    assert len(arguments(dict(base, requests=four), 'read')['requests']) == 4


def test_reject_bool_as_int():
    for field in ('issued_at', 'expires_at'):
        value = make_frame('read')
        value['principal'][field] = True
        with pytest.raises(ValueError):
            frame(value)
    with pytest.raises(ValueError):
        arguments(dict(fresh_read_args(), root_event_id=True), 'fresh_read')
    with pytest.raises(ValueError):
        arguments(dict(fresh_read_args(), root_event_id=0), 'fresh_read')
    with pytest.raises(ValueError):
        arguments(dict(fresh_read_args(), root_event_id=2 ** 53), 'fresh_read')
    assert arguments(dict(fresh_read_args(), root_event_id=2 ** 53 - 1), 'fresh_read') == dict(
        fresh_read_args(), root_event_id=2 ** 53 - 1
    )
    with pytest.raises(ValueError):
        arguments(dict(read_args(), revision=True), 'read')
    true_raw = raw_of(make_frame('catalogue'), separators=(',', ':')).replace(
        b'"issued_at":1000', b'"issued_at":true'
    )
    with pytest.raises(ValueError):
        decode_frame(true_raw)


def test_reject_bad_scopes():
    base = make_frame('read')
    for scopes in (
        [],
        [READ_SCOPE, READ_SCOPE],
        ['write'],
        [READ_SCOPE, 'write'],
        [SCOPE_SUBMIT],
        [READ_SCOPE, SCOPE_SUBMIT, READ_SCOPE],
        [READ_SCOPE, 5],
        [READ_SCOPE, None],
        'read',
        [READ_SCOPE, SCOPE_SUBMIT, 'write'],
    ):
        value = make_frame('read')
        value['principal']['scopes'] = scopes
        with pytest.raises(ValueError):
            frame(value)
    assert base['principal']['scopes'] == [READ_SCOPE]
    both = make_frame('read')
    both['principal']['scopes'] = [SCOPE_SUBMIT, READ_SCOPE]
    assert frame(both)['principal']['scopes'] == [SCOPE_SUBMIT, READ_SCOPE]


def test_reject_bad_issuer_digest():
    value = make_frame('read')
    value['principal']['issuer_digest'] = sha256_hex('https://other.example.test')
    with pytest.raises(ValueError):
        frame(value)
    for digest in (hex64(0xab).upper(), hex64(1)[:63], 'z' * 64, None, 5):
        value = make_frame('read')
        value['principal']['issuer_digest'] = digest
        with pytest.raises(ValueError):
            frame(value)
    unicode_issuer = 'https://issuer.example.test/ünï'
    bound = make_frame('catalogue')
    bound['principal']['issuer'] = unicode_issuer
    bound['principal']['issuer_digest'] = sha256_hex(unicode_issuer)
    assert frame(bound)['principal']['issuer_digest'] == sha256_hex(unicode_issuer)


def test_reject_principal_field_bounds():
    for field, limit in (('policy_id', 256), ('client_ref', 256)):
        value = make_frame('read')
        value['principal'][field] = 'p' * (limit + 1)
        with pytest.raises(ValueError):
            frame(value)
        value = make_frame('read')
        value['principal'][field] = 'p' * limit
        assert frame(value)['principal'][field] == 'p' * limit
    empty = make_frame('read')
    empty['principal']['policy_id'] = ''
    with pytest.raises(ValueError):
        frame(empty)
    empty = make_frame('read')
    empty['principal']['client_ref'] = ''
    with pytest.raises(ValueError):
        frame(empty)
    for field in ('issuer', 'resource'):
        value = make_frame('read')
        value['principal'][field] = 'x' * 2049
        with pytest.raises(ValueError):
            frame(value)
        value = make_frame('read')
        value['principal'][field] = 'x' * 2048
        if field == 'issuer':
            value['principal']['issuer_digest'] = sha256_hex('x' * 2048)
        assert frame(value)['principal'][field] == 'x' * 2048
    for control in ('\x00', '\x1f', '\x7f'):
        value = make_frame('read')
        value['principal']['resource'] = 'urn:example' + control
        with pytest.raises(ValueError):
            frame(value)


def test_reject_bad_expiry_pair():
    for issued_at, expires_at in ((-1, 2000), (2000, 2000), (1000, 1000), (2000, 1000), (1, 2 ** 53)):
        value = make_frame('read')
        value['principal']['issued_at'] = issued_at
        value['principal']['expires_at'] = expires_at
        with pytest.raises(ValueError):
            frame(value)
    value = make_frame('read')
    value['principal']['issued_at'] = 0
    value['principal']['expires_at'] = 2 ** 53 - 1
    assert frame(value)['principal']['expires_at'] == 2 ** 53 - 1


def test_reject_lone_surrogate_text():
    value = make_frame('read')
    value['principal']['issuer'] = 'https://issuer.example.test/\ud800'
    with pytest.raises(ValueError):
        frame(value)
    with pytest.raises(ValueError):
        encode_frame(value)
    with pytest.raises(ValueError):
        arguments({'work_ref': legacy_work_ref(), 'cursor': '\ud800'}, 'catalogue')


def test_decode_rejects_invalid_utf8_bytes():
    raw = raw_of(make_frame('catalogue'))
    with pytest.raises(ValueError):
        decode_frame(raw[:-1] + b'\xff')
    with pytest.raises(ValueError):
        decode_frame(b'\x80\x81')


def test_decode_rejects_duplicate_json_keys():
    principal_json = json.dumps(principal(), sort_keys=True)
    duplicated = principal_json[:-1] + ',"subject_digest":"' + hex64(1) + '"}'
    raw = (
        '{"schema":"' + SCHEMA + '","operation":"read","principal":' + duplicated
        + ',"arguments":' + json.dumps(read_args()) + '}\n'
    ).encode('utf-8')
    with pytest.raises(ValueError):
        decode_frame(raw)
    top_double = (
        '{"schema":"' + SCHEMA + '","schema":"' + SCHEMA + '","operation":"read",'
        '"principal":' + json.dumps(principal()) + ',"arguments":' + json.dumps(catalogue_args()) + '}\n'
    ).encode('utf-8')
    with pytest.raises(ValueError):
        decode_frame(top_double)
    arg_double = (
        '{"schema":"' + SCHEMA + '","operation":"catalogue","principal":' + json.dumps(principal())
        + ',"arguments":{"work_ref":"WS:AB","work_ref":"WS:AB"}}\n'
    ).encode('utf-8')
    with pytest.raises(ValueError):
        decode_frame(arg_double)


def test_decode_rejects_nonfinite_numbers():
    for literal in (b'NaN', b'Infinity', b'-Infinity', b'1e999'):
        raw = raw_of(make_frame('catalogue'), separators=(',', ':')).replace(
            b'"issued_at":1000', b'"issued_at":' + literal
        )
        with pytest.raises(ValueError):
            decode_frame(raw)
    value = make_frame('catalogue')
    value['principal']['issued_at'] = float('inf')
    with pytest.raises(ValueError):
        frame(value)
    value = make_frame('catalogue')
    value['principal']['issued_at'] = 1.5
    with pytest.raises(ValueError):
        frame(value)


def test_decode_rejects_trailing_garbage_and_second_object():
    value = make_frame('catalogue')
    body = json.dumps(value, separators=(',', ':'))
    with pytest.raises(ValueError):
        decode_frame((body + 'x\n').encode('utf-8'))
    with pytest.raises(ValueError):
        decode_frame((body + '\n' + body + '\n').encode('utf-8'))
    with pytest.raises(ValueError):
        decode_frame(b'')
    with pytest.raises(ValueError):
        decode_frame(b'   \n')
    with pytest.raises(ValueError):
        decode_frame('[]\n'.encode('utf-8'))
    with pytest.raises(ValueError):
        decode_frame('null\n'.encode('utf-8'))


def test_decode_rejects_non_bytes_overbudget_and_accepts_bytearray():
    with pytest.raises(ValueError):
        decode_frame(raw_of(make_frame('catalogue')).decode('utf-8'))
    with pytest.raises(ValueError):
        decode_frame(None)
    with pytest.raises(ValueError):
        decode_frame(b'x' * (MAX_REQUEST_BYTES + 1))
    assert decode_frame(bytearray(raw_of(make_frame('catalogue')))) == frame(make_frame('catalogue'))


def test_frame_budget_boundary_and_one_over():
    value = make_frame('read')
    raw = encode_frame(value)
    assert len(raw) < MAX_REQUEST_BYTES
    assert decode_frame(raw) == frame(value)
    padded = raw + b' ' * (MAX_REQUEST_BYTES - len(raw))
    assert len(padded) == MAX_REQUEST_BYTES
    assert decode_frame(padded) == frame(value)
    with pytest.raises(ValueError):
        decode_frame(padded + b' ')


def test_reject_strict_builtin_types():
    class StrSub(str):
        pass

    class DictSub(dict):
        pass

    class IntSub(int):
        pass

    value = make_frame('read')
    value['principal']['policy_id'] = StrSub('policy.read.v1')
    with pytest.raises(ValueError):
        frame(value)
    with pytest.raises(ValueError):
        arguments(DictSub({'work_ref': legacy_work_ref()}), 'catalogue')
    value = make_frame('read')
    value['principal']['issued_at'] = IntSub(1000)
    with pytest.raises(ValueError):
        frame(value)


def test_reject_bad_root_job_and_event_fields():
    for job_id in ('JOB-', 'job-1', 'JOB-1\n', 'JOB-1x', 'JOB-' + '9' * 253, 'JOB 1'):
        with pytest.raises(ValueError):
            arguments(dict(fresh_read_args(), root_job_id=job_id), 'fresh_read')
    assert len('JOB-' + '9' * 252) == 256
    assert arguments(
        dict(fresh_read_args(), root_job_id='JOB-' + '9' * 252), 'fresh_read'
    )['root_job_id'] == 'JOB-' + '9' * 252
    for digest_field in ('root_event_sha256', 'principal_scope_sha256'):
        value = fresh_read_args()
        value[digest_field] = hex64(0xab).upper()
        with pytest.raises(ValueError):
            arguments(value, 'fresh_read')
        value = fresh_read_args()
        value[digest_field] = hex64(7)[:63]
        with pytest.raises(ValueError):
            arguments(value, 'fresh_read')


def test_single_value_error_message():
    with pytest.raises(ValueError) as excinfo:
        frame({'secret_value': 'urn:example', 'principal': None})
    assert str(excinfo.value) == 'invalid_project_conversation_read'
    assert excinfo.value.args == ('invalid_project_conversation_read',)
    assert 'secret_value' not in repr(excinfo.value)
    for thunk in (
        lambda: frame(None),
        lambda: decode_frame(b'not json'),
        lambda: encode_frame({'schema': SCHEMA}),
        lambda: arguments({}, 'catalogue'),
    ):
        try:
            thunk()
        except ValueError as error:
            assert str(error) == 'invalid_project_conversation_read'
        else:
            assert False, 'expected ValueError'


def test_parent_actual_scope_namespace_and_nonempty_issuer_resource():
    for scopes in (['read'], ['read', SCOPE_SUBMIT]):
        value = make_frame('catalogue')
        value['principal']['scopes'] = scopes
        with pytest.raises(ValueError, match='^invalid_project_conversation_read$'):
            frame(value)
    for key in ('issuer', 'resource'):
        value = make_frame('catalogue')
        value['principal'][key] = ''
        if key == 'issuer':
            value['principal']['issuer_digest'] = sha256_hex('')
        with pytest.raises(ValueError, match='^invalid_project_conversation_read$'):
            frame(value)
