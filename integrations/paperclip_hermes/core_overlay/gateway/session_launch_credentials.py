"""Finite tool grants in the existing local launch-key and admission owners."""
from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import replace
from functools import wraps

from agent.launch_credential_binding import (
    PRIVATE_FIELD, CredentialLease, LaunchCredentialError, canonical, digest,
    execution_scope, validate,
)
from hermes_state_runtime import RuntimeStoreError

PUBLIC_FIELD = 'launch_binding_v1'
_PREFIX = 'run-credentials:'


def _slot(authority, session_id):
    return f'{_PREFIX}{authority.instance_id}:{authority.epoch}:{session_id}'


def prepare_creation(authority, actor, params, *, client_local):
    """Consume the private field before policy, receipts or launch-request projection."""
    if PRIVATE_FIELD not in params:
        return None
    if (not client_local or actor.profile_id != authority.profile_id
            or params.get('source', 'cli') not in {'cli', 'oneshot', 'tool'}
            or params.get('safe_mode') or params.get('ignore_user_config')):
        raise RuntimeStoreError('launch_credentials_scope_mismatch')
    payload = params[PRIVATE_FIELD]
    if not isinstance(payload, dict) or not isinstance(payload.get('binding_id'), str):
        raise RuntimeStoreError('invalid_launch_credentials_shape')
    from gateway.session_authorities import owner_scope
    from hermes_cli.plugins_launch_credentials import declaration_for
    try:
        with owner_scope(authority):
            spec = declaration_for(payload.get('binding_id'))
        values, context, public = validate(spec, payload)
    except LaunchCredentialError as exc:
        raise RuntimeStoreError(str(exc)) from None
    client_context = params.get('client_env') or {}
    if any(client_context.get(name) != value for name, value in context.items()):
        raise RuntimeStoreError('launch_credentials_context_mismatch')
    return {'values': values, 'context': context, 'public': public, 'principal': actor.subject}


def public_policy(authority, policy, prepared):
    if prepared is None:
        return policy
    require_supported_policy(authority, policy)
    request = json.loads(policy.request_json)
    request[PUBLIC_FIELD] = prepared['public']
    return replace(policy, request_json=canonical(request))


def require_supported_policy(authority, policy):
    config = policy.config(authority, secrets=False)
    backend = str(json.loads(policy.terminal_json).get('TERMINAL_ENV') or 'local').strip().lower()
    if (backend != 'local' or config.get('gateway', {}).get('managed_workers') is True
            or policy.ignore_user_config or policy.kanban_json is not None):
        raise RuntimeStoreError('launch_credentials_execution_mode_unsupported')


def marker(policy):
    return json.loads(policy.request_json).get(PUBLIC_FIELD)


def _keys(authority):
    keys = getattr(authority, '_local_launch_keys', None)
    if keys is None:
        keys = authority._local_launch_keys = {}
    return keys


def assert_existing(authority, session_id, policy, prepared):
    public = marker(policy)
    if public is None and prepared is None:
        return
    if public is None or prepared is None or digest(public) != digest(prepared['public']):
        raise RuntimeStoreError('admission_conflict')
    held = _keys(authority).get(_slot(authority, session_id))
    if not isinstance(held, CredentialLease) or held.public != public:
        raise RuntimeStoreError('launch_credentials_unavailable')
    try:
        held._live()
    except LaunchCredentialError as exc:
        raise RuntimeStoreError(str(exc)) from None


class _Publication:
    """Compose with prefill's transaction-owned publication, never publish a loser."""

    def __init__(self, previous, authority, lease):
        self.previous, self.authority, self.lease = previous, authority, lease
        self.published = False

    def read(self):
        try:
            self.lease._live()
            if self.previous is not None:
                self.previous.read()
        except BaseException:
            self.lease.retire()
            raise

    def publish(self):
        slot = _slot(self.authority, self.lease.session_id)
        keys = _keys(self.authority)
        if slot in keys:
            raise RuntimeStoreError('admission_conflict')
        self.lease._live()
        keys[slot] = self.lease
        self.published = True
        if self.previous is not None:
            self.previous.publish()

    def withdraw(self):
        try:
            if self.previous is not None:
                self.previous.withdraw()
        finally:
            slot = _slot(self.authority, self.lease.session_id)
            keys = _keys(self.authority)
            if keys.get(slot) is self.lease:
                keys.pop(slot)
            self.lease.retire()

    def finish(self):
        if not self.published:
            self.lease.retire()
        previous_finish = getattr(self.previous, 'finish', None)
        if previous_finish is not None:
            previous_finish()


def stage_publication(staged, authority, prepared):
    if prepared is None:
        return staged
    lease = CredentialLease(
        profile_id=authority.profile_id, principal_id=prepared['principal'],
        session_id=staged['session_id'], instance_id=authority.instance_id,
        owner_epoch=authority.epoch, public=prepared['public'],
        _values=prepared['values'], _context=prepared['context'])
    staged.on_create = _Publication(staged.on_create, authority, lease)
    return staged


def release(authority, session_ids):
    """Called by native retirement/cancellation, in addition to execution's finally."""
    keys = _keys(authority)
    for session_id in session_ids:
        held = keys.pop(_slot(authority, str(session_id)), None)
        if isinstance(held, CredentialLease):
            held.retire()


def release_unclaimed(authority, session_id):
    """A queued cancel cannot revoke another already-running admission's claim."""
    slot = _slot(authority, session_id)
    held = _keys(authority).get(slot)
    if isinstance(held, CredentialLease):
        with held._lock:
            if held._claim is None:
                held.retire()
                if _keys(authority).get(slot) is held:
                    _keys(authority).pop(slot)


def finish_publication(function):
    """Retire an unpublished loser even when serialization or transaction setup fails."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        publication = getattr(kwargs.get('receipt'), 'on_create', None)
        try:
            return function(*args, **kwargs)
        finally:
            finish = getattr(publication, 'finish', None)
            if finish is not None:
                finish()
    return wrapped


@contextmanager
def admission_scope(authority, ref, row):
    from gateway.session_policy import policy_for_source
    source = authority.sessions[ref.session_id].source
    policy = policy_for_source(authority.runner, source)
    if policy is None and _slot(authority, ref.session_id) in _keys(authority):
        raise RuntimeStoreError('launch_credentials_policy_unavailable')
    public = marker(policy) if policy is not None else None
    if public is None:
        yield
        return
    require_supported_policy(authority, policy)
    held = _keys(authority).get(_slot(authority, ref.session_id))
    if not isinstance(held, CredentialLease) or held.public != public:
        raise RuntimeStoreError('launch_credentials_unavailable')
    entered = False
    try:
        claim = held.claim(
            profile_id=authority.profile_id, principal_id=row['principal_id'],
            session_id=ref.session_id, instance_id=authority.instance_id,
            owner_epoch=authority.epoch, admission_id=row['admission_id'],
            generation=row['generation'], finite=row['payload'].get('finite') is True)
        def owns_transcript(session_id):
            from hermes_constants import get_hermes_home
            return (str(get_hermes_home()) == authority.profile_id
                    and session_id in authority.db.get_compression_lineage(ref.session_id))

        with execution_scope(held, claim, transcript_check=owns_transcript):
            entered = True
            yield
    except LaunchCredentialError as exc:
        raise RuntimeStoreError(str(exc)) from None
    finally:
        if entered:
            slot = _slot(authority, ref.session_id)
            if _keys(authority).get(slot) is held:
                _keys(authority).pop(slot)
            held.retire()
