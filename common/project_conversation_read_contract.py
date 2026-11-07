"""Private project-conversation read wire contract (pure stdlib codec).

Shapes, bounds and detaches the JSON frames exchanged on the private
``mastermind.project_conversation_read.private.v1`` channel.  Validation is
strictly syntactic: it never authenticates a bearer or a peer, never checks
workspace ownership, and grants no authority.  The parent integration owns
authentication of the actual current bearer; the private service
independently authenticates its actual peer and source.
"""

import hashlib
import json
import re

__all__ = [
    'SCHEMA',
    'MAX_REQUEST_BYTES',
    'MAX_RESPONSE_BYTES',
    'OPERATIONS',
    'arguments',
    'frame',
    'decode_frame',
    'encode_frame',
]

SCHEMA = 'mastermind.project_conversation_read.private.v1'

MAX_REQUEST_BYTES = 8192
MAX_RESPONSE_BYTES = 32768

OPERATIONS = ('catalogue', 'read', 'fresh_references', 'fresh_read', 'execution_references', 'execution_read')

_INVALID = 'invalid_project_conversation_read'
_MAX_ARGUMENTS_BYTES = 4096
_INT53_MAX = 2 ** 53 - 1

_FRESH_REFERENCE_SCHEMA = 'mastermind.fresh_conversation_reference.v1'
_SCOPE_SUBMIT = 'mastermind.executive.intent.submit'
_SCOPE_READ = 'mastermind.executive.read'
_SCOPES_FIRST = frozenset((_SCOPE_READ,))
_SCOPES_BOTH = frozenset((_SCOPE_READ, _SCOPE_SUBMIT))

_FRAME_KEYS = frozenset(('schema', 'operation', 'principal', 'arguments'))
_PRINCIPAL_KEYS = frozenset((
    'policy_id',
    'issuer',
    'issuer_digest',
    'resource',
    'subject_digest',
    'client_ref',
    'scopes',
    'issued_at',
    'expires_at',
    'jti_digest',
))

_LEGACY_WORK_REF = re.compile(r'WS:[A-Z0-9]+(?:-[A-Z0-9]+)*')
_FRESH_WORK_REF = re.compile(r'WS:[A-Za-z0-9][A-Za-z0-9._-]{0,68}')
_CURSOR = re.compile(r'[A-Za-z0-9_=-]+')
_HEX64 = re.compile(r'[0-9a-f]{64}')
_CONVERSATION_REF = re.compile(r'conversation-[0-9a-f]{64}')
_READ_REF = re.compile(r'session-reply-[0-9a-f]{64}')
_ROOT_JOB_ID = re.compile(r'JOB-[0-9]+')


class _Invalid(Exception):
    """Internal marker, converted to the single public ValueError at the edge."""


def _fail():
    raise _Invalid()


def _text(value):
    if type(value) is not str:
        _fail()
    try:
        value.encode('utf-8')
    except (UnicodeEncodeError, ValueError):
        _fail()
    return value


def _visible(value):
    for char in _text(value):
        code = ord(char)
        if code <= 0x1F or code == 0x7F:
            _fail()
    return value


def _bounded(value, limit, minimum=0):
    text = _visible(value)
    if not minimum <= len(text) <= limit:
        _fail()
    return text


def _digest(value):
    text = _text(value)
    if _HEX64.fullmatch(text) is None:
        _fail()
    return text


def _integer(value):
    if type(value) is not int:
        _fail()
    return value


def _mapping(value):
    if type(value) is not dict:
        _fail()
    for key in value:
        if type(key) is not str:
            _fail()


def _exact_keys(value, keys):
    _mapping(value)
    if value.keys() != keys:
        _fail()


def _canonical(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
        allow_nan=False,
    ).encode('utf-8')


def _legacy_work_ref(value):
    text = _text(value)
    if _LEGACY_WORK_REF.fullmatch(text) is None:
        _fail()
    if not 2 <= len(text) - 3 <= 64:
        _fail()
    return text


def _fresh_work_ref(value):
    text = _text(value)
    if _FRESH_WORK_REF.fullmatch(text) is None or len(text) > 72:
        _fail()
    return text


def _cursor(value):
    text = _text(value)
    if _CURSOR.fullmatch(text) is None or not 1 <= len(text) <= 2048:
        _fail()
    return text


def _conversation_ref(value):
    text = _text(value)
    if _CONVERSATION_REF.fullmatch(text) is None:
        _fail()
    return text


def _read_ref(value):
    text = _text(value)
    if _READ_REF.fullmatch(text) is None:
        _fail()
    return text


def _root_job_id(value):
    text = _text(value)
    if _ROOT_JOB_ID.fullmatch(text) is None or len(text) > 256:
        _fail()
    return text


def _root_event_id(value):
    number = _integer(value)
    if not 1 <= number <= _INT53_MAX:
        _fail()
    return number


def _scopes(value):
    if type(value) is not list or not value:
        _fail()
    seen = set()
    result = []
    for item in value:
        text = _text(item)
        if text not in _SCOPES_BOTH or text in seen:
            _fail()
        seen.add(text)
        result.append(text)
    if seen != _SCOPES_FIRST and seen != _SCOPES_BOTH:
        _fail()
    return result


def _principal(value):
    _exact_keys(value, _PRINCIPAL_KEYS)
    policy_id = _bounded(value['policy_id'], 256, minimum=1)
    issuer = _bounded(value['issuer'], 2048, minimum=1)
    issuer_digest = _digest(value['issuer_digest'])
    if issuer_digest != hashlib.sha256(issuer.encode('utf-8')).hexdigest():
        _fail()
    resource = _bounded(value['resource'], 2048, minimum=1)
    subject_digest = _digest(value['subject_digest'])
    client_ref = _bounded(value['client_ref'], 256, minimum=1)
    scopes = _scopes(value['scopes'])
    issued_at = _integer(value['issued_at'])
    if issued_at < 0:
        _fail()
    expires_at = _integer(value['expires_at'])
    if not issued_at < expires_at <= _INT53_MAX:
        _fail()
    jti_digest = None if value['jti_digest'] is None else _digest(value['jti_digest'])
    return {
        'policy_id': policy_id,
        'issuer': issuer,
        'issuer_digest': issuer_digest,
        'resource': resource,
        'subject_digest': subject_digest,
        'client_ref': client_ref,
        'scopes': scopes,
        'issued_at': issued_at,
        'expires_at': expires_at,
        'jti_digest': jti_digest,
    }


def _catalogue(value):
    _mapping(value)
    if 'work_ref' not in value or not value.keys() <= {'work_ref', 'cursor'}:
        _fail()
    result = {'work_ref': _legacy_work_ref(value['work_ref'])}
    if 'cursor' in value:
        result['cursor'] = None if value['cursor'] is None else _cursor(value['cursor'])
    return result


def _read(value):
    _exact_keys(value, frozenset(('work_ref', 'conversation_ref', 'revision', 'requests')))
    work_ref = _legacy_work_ref(value['work_ref'])
    conversation_ref = _conversation_ref(value['conversation_ref'])
    revision = _digest(value['revision'])
    requests_value = value['requests']
    if type(requests_value) is not list or not 1 <= len(requests_value) <= 4:
        _fail()
    seen_refs = set()
    requests = []
    for item in requests_value:
        _exact_keys(item, frozenset(('read_ref', 'request_revision')))
        read_ref = _read_ref(item['read_ref'])
        request_revision = _digest(item['request_revision'])
        if read_ref in seen_refs:
            _fail()
        seen_refs.add(read_ref)
        requests.append({'read_ref': read_ref, 'request_revision': request_revision})
    return {
        'work_ref': work_ref,
        'conversation_ref': conversation_ref,
        'revision': revision,
        'requests': requests,
    }


def _fresh_references(value):
    _exact_keys(value, frozenset(('work_ref',)))
    return {'work_ref': _fresh_work_ref(value['work_ref'])}


def _input_fragment(value):
    _mapping(value)
    kind = _text(value.get('kind'))
    if kind not in ('initial_input', 'turn_input'):
        _fail()
    keys = frozenset(('kind', 'source_event_id', 'source_event_sha256', 'sha256', 'offset_utf8'))
    _exact_keys(value, keys | ({'turn_key'} if kind == 'turn_input' else set()))
    offset = _integer(value['offset_utf8'])
    if not 0 <= offset < 131072:
        _fail()
    result = dict(kind=kind, source_event_id=_root_event_id(value['source_event_id']),
        source_event_sha256=_digest(value['source_event_sha256']), sha256=_digest(value['sha256']),
        offset_utf8=offset)
    if kind == 'turn_input':
        key = _bounded(value['turn_key'], 96, 1)
        if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,95}', key) is None:
            _fail()
        result['turn_key'] = key
    return result


def _native_content(value):
    _exact_keys(value, frozenset(('native_ref', 'offset_bytes', 'expected_sha256')))
    from control_plane.native_conversation_result import NativeConversationResultRef
    try:
        reference = NativeConversationResultRef.from_wire(value['native_ref']).to_wire()
    except (ValueError, TypeError):
        _fail()
    offset = _integer(value['offset_bytes'])
    digest = None if value['expected_sha256'] is None else _digest(value['expected_sha256'])
    if not 0 <= offset < 4*1024*1024 or offset > 0 and digest is None:
        _fail()
    return dict(native_ref=reference, offset_bytes=offset, expected_sha256=digest)


def _fresh_read(value):
    _mapping(value)
    keys = frozenset((
        'schema',
        'work_ref',
        'root_job_id',
        'root_event_id',
        'root_event_sha256',
        'principal_scope_sha256',
    ))
    extension = value.keys() & {'before_event_id', 'fragment', 'content'}
    if len(extension) > 1:
        _fail()
    _exact_keys(value, keys | extension)
    schema = _text(value['schema'])
    if schema != _FRESH_REFERENCE_SCHEMA:
        _fail()
    return {
        'schema': schema,
        'work_ref': _fresh_work_ref(value['work_ref']),
        'root_job_id': _root_job_id(value['root_job_id']),
        'root_event_id': _root_event_id(value['root_event_id']),
        'root_event_sha256': _digest(value['root_event_sha256']),
        'principal_scope_sha256': _digest(value['principal_scope_sha256']),
        **({'before_event_id': _root_event_id(value['before_event_id'])} if 'before_event_id' in value else {}),
        **({'fragment': _input_fragment(value['fragment'])} if 'fragment' in value else {}),
        **({'content': _native_content(value['content'])} if 'content' in value else {}),
    }


def _execution_references(value):
    _exact_keys(value, frozenset(('work_ref',)))
    return {'work_ref': _legacy_work_ref(value['work_ref'])}


def _execution_read(value):
    _exact_keys(value, frozenset((
        'schema', 'work_ref', 'root_job_id', 'root_event_id', 'root_event_sha256',
        'project_execution_source_sha256', 'principal_scope_sha256',
    )))
    if _text(value['schema']) != 'mastermind.project_execution_reference.v1':
        _fail()
    return {
        'schema': value['schema'],
        'work_ref': _legacy_work_ref(value['work_ref']),
        'root_job_id': _root_job_id(value['root_job_id']),
        'root_event_id': _root_event_id(value['root_event_id']),
        'root_event_sha256': _digest(value['root_event_sha256']),
        'project_execution_source_sha256': _digest(value['project_execution_source_sha256']),
        'principal_scope_sha256': _digest(value['principal_scope_sha256']),
    }


_ARGUMENT_BUILDERS = {
    'catalogue': _catalogue,
    'read': _read,
    'fresh_references': _fresh_references,
    'fresh_read': _fresh_read,
    'execution_references': _execution_references,
    'execution_read': _execution_read,
}


def _arguments_body(value, operation):
    builder = _ARGUMENT_BUILDERS.get(operation) if type(operation) is str else None
    if builder is None:
        _fail()
    result = builder(value)
    if len(_canonical(result)) > _MAX_ARGUMENTS_BYTES:
        _fail()
    return result


def _frame(value):
    _exact_keys(value, _FRAME_KEYS)
    schema = _text(value['schema'])
    if schema != SCHEMA:
        _fail()
    operation = value['operation']
    if type(operation) is not str or operation not in OPERATIONS:
        _fail()
    result = {
        'schema': schema,
        'operation': operation,
        'principal': _principal(value['principal']),
        'arguments': _arguments_body(value['arguments'], operation),
    }
    if len(_canonical(result)) + 1 > MAX_REQUEST_BYTES:
        _fail()
    return result


def _object_pairs(pairs):
    result = {}
    for key, item in pairs:
        if key in result:
            _fail()
        result[key] = item
    return result


def _reject_float(_literal):
    _fail()


def _reject_constant(_literal):
    _fail()


def _decode(raw):
    if type(raw) not in (bytes, bytearray):
        _fail()
    if len(raw) > MAX_REQUEST_BYTES:
        _fail()
    try:
        text = bytes(raw).decode('utf-8')
    except (UnicodeDecodeError, ValueError):
        _fail()
    decoder = json.JSONDecoder(
        object_pairs_hook=_object_pairs,
        parse_float=_reject_float,
        parse_constant=_reject_constant,
    )
    start = 0
    while start < len(text) and text[start] in ' \t\n\r':
        start += 1
    try:
        value, end = decoder.raw_decode(text, start)
    except _Invalid:
        raise
    except Exception:
        _fail()
    if text[end:].strip(' \t\n\r'):
        _fail()
    return _frame(value)


def arguments(value, operation):
    """Validate request arguments for ``operation`` and return detached data."""
    try:
        return _arguments_body(value, operation)
    except Exception:
        raise ValueError(_INVALID) from None


def frame(value):
    """Validate a private read frame and return it detached."""
    try:
        return _frame(value)
    except Exception:
        raise ValueError(_INVALID) from None


def decode_frame(raw):
    """Decode one strict UTF-8 JSON frame (at most one trailing whitespace run)."""
    try:
        return _decode(raw)
    except Exception:
        raise ValueError(_INVALID) from None


def encode_frame(value):
    """Encode a validated frame as compact sorted JSON plus one trailing LF."""
    try:
        encoded = _canonical(_frame(value)) + b'\n'
        if len(encoded) > MAX_REQUEST_BYTES:
            _fail()
        return encoded
    except Exception:
        raise ValueError(_INVALID) from None
