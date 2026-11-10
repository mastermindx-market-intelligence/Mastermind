"""Private, finite-launch credential values; no profile or persistent secret store.

Declarations come from an enabled plugin. The gateway, not the caller, binds
profile, principal, session, admission and generation. Issuers still verify
their tokens; reading an expiry claim here is not signature verification.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import threading
import time
import uuid
import inspect
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import wraps
from urllib.parse import urlsplit

CAPABILITY = 'finite-launch-credentials-v1'
PRIVATE_FIELD = 'launch_credentials_v1'
_NAME = re.compile(r'^[A-Z][A-Z0-9_]{0,127}$')
_BINDING = re.compile(r'^[a-z][a-z0-9_.-]{0,95}$')
_BOUND = ContextVar('finite_launch_credentials', default=None)
_TOOL_BOUND = ContextVar('finite_launch_tool_credentials', default=None)
_MAX_SECRET = 32768
_MAX_LIFETIME = 48 * 60 * 60


class LaunchCredentialError(ValueError):
    """Only a fixed public reason code, never input values, belongs in an error."""


def _fail(code):
    raise LaunchCredentialError(code) from None


def _closed(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        _fail('invalid_launch_credentials_shape')


def _names(values):
    if (not isinstance(values, list) or len(values) > 32
            or any(not isinstance(v, str) or not _NAME.fullmatch(v) for v in values)
            or len(values) != len(set(values))):
        _fail('invalid_launch_credentials_declaration')
    return tuple(values)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def declaration(binding_id, value):
    """Validate a primitive declaration that also crosses the plugin-host wire."""
    if not isinstance(binding_id, str) or not _BINDING.fullmatch(binding_id):
        _fail('invalid_launch_credentials_declaration')
    if isinstance(value, dict) and 'withheld_env' not in value:
        value = {**value, 'withheld_env': []}
    _closed(value, {'version', 'operation_env', 'context_env', 'required_context', 'credentials',
                    'context_types', 'same_origin', 'withheld_env'})
    context = _names(value['context_env'])
    required = _names(value['required_context'])
    if (type(value['version']) is not int or value['version'] != 1
            or value['operation_env'] not in required or not set(required) <= set(context)):
        _fail('invalid_launch_credentials_declaration')
    credentials = value['credentials']
    if not isinstance(credentials, list) or not 1 <= len(credentials) <= 8:
        _fail('invalid_launch_credentials_declaration')
    _declaration_context_rules(value, context)
    names = [_credential_declaration(item, context) for item in credentials]
    withheld = _names(value['withheld_env'])
    for name in withheld:
        _credential_name(name, context)
    if len(names) != len(set(names)) or set(names) & set(withheld):
        _fail('invalid_launch_credentials_declaration')
    return json.loads(canonical({'binding_id': binding_id, **value}))


def manifest_bindings(raw):
    """Parse metadata before any plugin code or host process starts."""
    if raw is None:
        return {}
    if not isinstance(raw, dict) or len(raw) > 8:
        _fail('invalid_launch_credentials_declaration')
    result = {}
    for binding_id, value in raw.items():
        parsed = declaration(binding_id, value)
        parsed.pop('binding_id')
        result[binding_id] = parsed
    return result


def _credential_name(name, context):
    if (not isinstance(name, str) or not _NAME.fullmatch(name) or name in context
            or name.startswith('HERMES_')
            or not any(part in name.split('_') for part in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD'))):
        _fail('invalid_launch_credentials_declaration')


def _credential_declaration(item, context):
    _closed(item, {'env', 'required', 'expiry_env', 'jwt_exp', 'jwt_claims', 'required_context'})
    name, expiry = item['env'], item['expiry_env']
    _credential_name(name, context)
    if type(item['required']) is not bool or type(item['jwt_exp']) is not bool:
        _fail('invalid_launch_credentials_declaration')
    if (item['jwt_exp'] and expiry is not None) or (not item['jwt_exp'] and expiry not in context):
        _fail('invalid_launch_credentials_declaration')
    claims = item['jwt_claims']
    if (not isinstance(claims, dict) or len(claims) > 16
            or any(not isinstance(key, str) or not 0 < len(key) <= 128 for key in claims)
            or not set(claims.values()) <= set(context) or (claims and not item['jwt_exp'])
            or not set(_names(item['required_context'])) <= set(context)):
        _fail('invalid_launch_credentials_declaration')
    return name


def _declaration_context_rules(spec, context):
    kinds = spec['context_types']
    if (not isinstance(kinds, dict) or not set(kinds) <= set(context)
            or not set(kinds.values()) <= {'uuid', 'http_url', 'string'}):
        _fail('invalid_launch_credentials_declaration')
    pairs = spec['same_origin']
    if not isinstance(pairs, list) or len(pairs) > 8:
        _fail('invalid_launch_credentials_declaration')
    for pair in pairs:
        if (not isinstance(pair, list) or len(pair) != 2
                or any(kinds.get(name) != 'http_url' for name in pair)):
            _fail('invalid_launch_credentials_declaration')


def _url_origin(value):
    try:
        url = urlsplit(value)
        if (url.scheme not in {'http', 'https'} or not url.hostname
                or url.username is not None or url.password is not None or url.fragment or url.query):
            _fail('invalid_launch_credentials_context')
        port = url.port
        if port is None:
            port = 443 if url.scheme == 'https' else 80
        return url.scheme, url.hostname.lower(), port
    except ValueError:
        _fail('invalid_launch_credentials_context')


def _check_context_types(spec, context):
    for name, kind in spec['context_types'].items():
        if name not in context:
            continue
        value = context[name]
        if kind == 'uuid':
            try:
                if str(uuid.UUID(value)) != value:
                    _fail('invalid_launch_credentials_context')
            except ValueError:
                _fail('invalid_launch_credentials_context')
        elif kind == 'http_url':
            _url_origin(value)
    for left, right in spec['same_origin']:
        if left in context and right in context and _url_origin(context[left]) != _url_origin(context[right]):
            _fail('launch_credentials_endpoint_mismatch')


def _context(spec, value):
    if (not isinstance(value, dict) or not set(value) <= set(spec['context_env'])
            or not set(spec['required_context']) <= set(value)):
        _fail('invalid_launch_credentials_context')
    for item in value.values():
        if not isinstance(item, str) or not 0 < len(item) <= 4096 or '\x00' in item:
            _fail('invalid_launch_credentials_context')
    _check_context_types(spec, value)
    return dict(value)


def _timestamp(value):
    try:
        stamp = datetime.fromisoformat(value)
        if stamp.tzinfo is None:
            _fail('invalid_launch_credentials_expiry')
        return stamp.astimezone(UTC).timestamp()
    except (ValueError, TypeError, AttributeError, OverflowError):
        _fail('invalid_launch_credentials_expiry')


def _jwt_expiry(token, expected, context):
    """Read an untrusted issuer expiry, never authenticate or authorize the token."""
    try:
        parts = token.split('.')
        if len(parts) != 3:
            _fail('invalid_launch_credentials_expiry')
        raw = base64.urlsafe_b64decode(parts[1] + '=' * (-len(parts[1]) % 4))
        claims = json.loads(raw)
        expiry = claims.get('exp') if isinstance(claims, dict) else None
        if type(expiry) not in (int, float):
            _fail('invalid_launch_credentials_expiry')
        if any(claims.get(key) != context.get(name) or name not in context for key, name in expected.items()):
            _fail('launch_credentials_identity_mismatch')
        return float(expiry)
    except LaunchCredentialError:
        raise
    except (ValueError, TypeError, UnicodeError, OverflowError):
        _fail('invalid_launch_credentials_expiry')


def validate(spec, payload, *, now=None):
    """Return validated private values and public metadata; errors contain no input."""
    _closed(payload, {'binding_id', 'declaration_digest', 'context', 'credentials'})
    if (payload['binding_id'] != spec['binding_id']
            or not isinstance(payload['declaration_digest'], str)
            or not re.fullmatch(r'[a-f0-9]{64}', payload['declaration_digest'])
            or not hmac.compare_digest(payload['declaration_digest'], digest(spec))):
        _fail('launch_credentials_declaration_changed')
    context = _context(spec, payload['context'])
    values = payload['credentials']
    names = {item['env'] for item in spec['credentials']}
    if not isinstance(values, dict) or not set(values) <= names:
        _fail('invalid_launch_credentials_values')
    expiries, required_expiries = {}, []
    for item in spec['credentials']:
        token = values.get(item['env'])
        if item['env'] not in values:
            if item['required'] or (item['expiry_env'] and item['expiry_env'] in context):
                _fail('launch_credentials_missing')
            continue
        if not isinstance(token, str) or not 8 <= len(token) <= _MAX_SECRET or '\x00' in token:
            _fail('invalid_launch_credentials_values')
        if not set(item['required_context']) <= set(context):
            _fail('launch_credentials_context_missing')
        expiry = (_jwt_expiry(token, item['jwt_claims'], context) if item['jwt_exp']
                  else _timestamp(context.get(item['expiry_env'])))
        expiries[item['env']] = expiry
        if item['required']:
            required_expiries.append(expiry)
    instant = time.time() if now is None else now
    if not expiries or not all(instant < value <= instant + _MAX_LIFETIME for value in expiries.values()):
        _fail('launch_credentials_expired')
    public = {'binding_id': spec['binding_id'], 'operation_id': context[spec['operation_env']],
              'declaration_digest': digest(spec), 'context_digest': digest(context),
              'credential_fingerprints': {name: hashlib.sha256(value.encode()).hexdigest()
                                          for name, value in values.items()},
              'credential_expiries': expiries,
              'expires_at': min(required_expiries or expiries.values())}
    return dict(values), context, public


def collect(spec, environ, *, now=None):
    """An enabled declaration activates only in its originating launch process."""
    if not environ.get(spec['operation_env']):
        return None
    payload = {'binding_id': spec['binding_id'], 'declaration_digest': digest(spec),
               'context': {name: environ[name] for name in spec['context_env'] if environ.get(name)},
               'credentials': {item['env']: environ[item['env']] for item in spec['credentials']
                               if environ.get(item['env'])}}
    validate(spec, payload, now=now)
    return payload


@dataclass(repr=False)
class CredentialLease:
    """One record in the incumbent gateway launch-key custody, never a new store."""
    profile_id: str
    principal_id: str
    session_id: str
    instance_id: str
    owner_epoch: int
    public: dict
    _values: dict = field(repr=False)
    _context: dict = field(repr=False)
    _claim: tuple | None = field(default=None, repr=False)
    _retired: bool = False
    _executing: bool = False
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def __repr__(self):
        return 'CredentialLease(<private>)'

    def _live(self, now=None):
        if self._retired or (time.time() if now is None else now) >= self.public['expires_at']:
            self.retire()
            _fail('launch_credentials_unavailable')

    def claim(self, *, profile_id, principal_id, session_id, instance_id, owner_epoch,
              admission_id, generation, finite, now=None):
        with self._lock:
            self._live(now)
            bound = (self.profile_id, self.principal_id, self.session_id, self.instance_id, self.owner_epoch)
            sent = (profile_id, principal_id, session_id, instance_id, owner_epoch)
            if bound != sent or finite is not True or not admission_id or type(generation) is not int:
                _fail('launch_credentials_scope_mismatch')
            claim = (admission_id, generation)
            if self._claim is not None and self._claim != claim:
                _fail('launch_credentials_already_claimed')
            self._claim = claim
            return claim

    def values(self, claim, *, session_id, now=None):
        with self._lock:
            self._live(now)
            if self._claim != claim or session_id != self.session_id:
                _fail('launch_credentials_scope_mismatch')
            instant = time.time() if now is None else now
            for name, expiry in self.public.get('credential_expiries', {}).items():
                if instant >= expiry:
                    self._values.pop(name, None)
            return dict(self._values)

    def retire(self):
        with self._lock:
            self._retired = True
            self._values.clear()
            self._context.clear()


@dataclass(frozen=True, repr=False)
class BoundCredentials:
    lease: CredentialLease
    claim: tuple
    redactions: tuple = field(repr=False)
    transcript_check: object = field(default=None, repr=False)


@dataclass(repr=False)
class ToolCredentials:
    bound: BoundCredentials
    transcript_id: str
    parent: object = None
    active: bool = True


@contextmanager
def execution_scope(lease, claim, *, transcript_check=None):
    """Only the native execution owner enters this scope, including worker bootstrap."""
    with lease._lock:
        values = lease.values(claim, session_id=lease.session_id)
        if lease._executing:
            _fail('launch_credentials_execution_already_active')
        lease._executing = True
    token = _BOUND.set(BoundCredentials(lease, claim, tuple(values.values()), transcript_check))
    try:
        yield
    finally:
        lease.retire()
        lease._executing = False
        _BOUND.reset(token)


def tool_environment():
    """Only an active validated tool dispatch can obtain values; no caller identity override."""
    bound = _BOUND.get()
    if bound is None:
        return {}
    tool = _TOOL_BOUND.get()
    if tool is None:
        return {}
    _check_tool(tool)
    return bound.lease.values(bound.claim, session_id=bound.lease.session_id)


def _check_dispatcher():
    from agent.delegation_context import (
        is_delegated_child_process_context, is_dispatcher_owned_worker_context,
    )
    if is_delegated_child_process_context() or not is_dispatcher_owned_worker_context():
        _fail('launch_credentials_child_scope_refused')


def _check_tool(tool):
    _check_dispatcher()
    current = tool
    while current is not None:
        if not current.active:
            _fail('launch_credentials_tool_scope_retired')
        current = current.parent
    if tool.bound is not _BOUND.get():
        _fail('launch_credentials_scope_mismatch')
    tool.bound.lease._live()
    check = tool.bound.transcript_check
    if check is None or not check(tool.transcript_id):
        _fail('launch_credentials_transcript_mismatch')


@contextmanager
def tool_dispatch_scope(session_id, function_name, function_args):
    bound = _BOUND.get()
    if bound is None:
        yield
        return
    parent = _TOOL_BOUND.get()
    if not session_id:
        if parent is None:
            _fail('launch_credentials_tool_context_missing')
        _check_tool(parent)
        session_id = parent.transcript_id
    tool = ToolCredentials(bound, session_id, parent)
    _check_tool(tool)
    if function_name == 'terminal' and function_args.get('background'):
        _fail('launch_credentials_background_unsupported')
    token = _TOOL_BOUND.set(tool)
    try:
        yield
    finally:
        tool.active = False
        _TOOL_BOUND.reset(token)


def guard_tool_call(function):
    """Wrap the existing dispatch owner; nested code-cell calls inherit its active scope."""
    signature = inspect.signature(function)

    @wraps(function)
    def guarded(*args, **kwargs):
        if _BOUND.get() is None:
            return function(*args, **kwargs)
        parameters = signature.bind_partial(*args, **kwargs).arguments
        try:
            with tool_dispatch_scope(parameters.get('session_id'), parameters['function_name'],
                                     parameters.get('function_args') or {}):
                return redact(function(*args, **kwargs))
        except LaunchCredentialError as exc:
            from tools.registry import tool_error
            return tool_error(str(exc))

    return guarded


def redact_tool_result(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        return redact(function(*args, **kwargs))
    return guarded


def snapshot_exclusion_names():
    """Names remain available after retirement; terminal exclusions accumulate monotonically."""
    bound = _BOUND.get()
    return set(bound.lease.public['credential_fingerprints']) if bound is not None else set()


def redact(value):
    """Mandatory exact-value scrubbing before canonical history, independent of display flags."""
    bound = _BOUND.get()
    if bound is None:
        return value
    if isinstance(value, str):
        for secret in bound.redactions:
            value = value.replace(secret, '[REDACTED_LAUNCH_CREDENTIAL]')
        return value
    if isinstance(value, dict):
        return {redact(key): redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    return value


def bound_credentials():
    return _BOUND.get()


def sanitize_log_record(record):
    """Scrub on the producing thread, before a listener loses the run context."""
    # The WebSocket library's DEBUG frame dump occurs before private JSON-RPC
    # validation/binding. A diagnostic opt-in must never turn the wire into a vault.
    args = record.args
    frame = args[0] if isinstance(args, tuple) and len(args) == 1 else None
    if (type(record.msg) is str and record.msg in ('< %s', '> %s') and frame is not None
            and type(frame).__module__ == 'websockets.frames' and type(frame).__name__ == 'Frame'):
        record.msg, record.args = 'websocket_frame_diagnostic_withheld', ()
        record.exc_info, record.exc_text, record.stack_info = None, None, None
        return record
    if _BOUND.get() is None:
        return record
    import traceback
    try:
        record.msg = redact(record.getMessage())
        record.args = ()
        record.stack_info = redact(record.stack_info) if record.stack_info else None
        if record.exc_info:
            record.exc_text = redact(''.join(traceback.format_exception(*record.exc_info)))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = redact(record.exc_text)
        # QueueHandler runs after logging has attached structured `extra` fields.
        for key, value in list(vars(record).items()):
            if isinstance(value, (str, dict, list, tuple)):
                setattr(record, key, redact(value))
            elif value is not None and type(value) not in (int, float, bool):
                setattr(record, key, '[REDACTED_LAUNCH_LOG_OBJECT]')
    except Exception:  # health: allow BLE001 -- arbitrary log formatting needs a fixed safe record; logging failure could leak or recurse
        import logging
        safe = logging.LogRecord('hermes.private', 40, '', 0, 'launch_credential_log_format_refused', (), None)
        record.__dict__.clear()
        record.__dict__.update(vars(safe))
        record.session_tag, record.hermes_home = '', ''
    return record
