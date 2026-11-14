"""Explicit installed OAuth-account -> incumbent native-profile read composition.

The fixed mapping is a host access allowlist, not a credential, account, fleet or
worker registry. It reuses the existing current OAuth policy and digest-pinned
native profile. A tunnel label is never converted into an authenticated principal.
No desktop credential is copied into the Executive service or model context.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath

from control_plane.principal_projection import NeutralPrincipalProjection
from .reply_policy_selection import ReplyPolicySelection
from .t3_dot_native_owner import NativeDotFleetOwner, read_profile
from .t3_native_client import Scope, Unavailable, Conflict
from .web_reply_subscription_owner import owner_key

_SHA = re.compile(r"[0-9a-f]{64}\Z")


def validate_native_return_config(value):
    if (type(value) is not dict or set(value) != {'enabled', 'profiles'} or value['enabled'] is not True
            or type(value['profiles']) is not list or not 1 <= len(value['profiles']) <= 32):
        raise ValueError('Explicit bounded original-return native profile selection required')
    seen, rows = set(), []
    for row in value['profiles']:
        if type(row) is not dict or set(row) != {'owner_key', 'profile_path', 'profile_sha256'}:
            raise ValueError('Closed account-native profile selection required')
        if any(type(row[key]) is not str or not _SHA.fullmatch(row[key]) for key in ('owner_key', 'profile_sha256')):
            raise ValueError('Exact current account key and profile digest required')
        path = row['profile_path']
        if (type(path) is not str or not path or len(path) > 4096
                or not PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts
                or any(ord(char) < 32 or ord(char) == 127 for char in path)
                or row['owner_key'] in seen):
            raise ValueError('Unambiguous host-owned native profile path required')
        seen.add(row['owner_key'])
        rows.append(dict(row))
    return {'enabled': True, 'profiles': rows}


class InstalledT3ReplyNativeAccess:
    def __init__(self, policies: ReplyPolicySelection, configuration: dict, *,
                 owner_factory=NativeDotFleetOwner, current_selection=None):
        selected = getattr(policies, 'native_returns_selected', None) if current_selection is None else current_selection
        if (not isinstance(policies, ReplyPolicySelection) or not callable(owner_factory)
                or not callable(selected)):
            raise TypeError('Incumbent current OAuth policy, explicit native selection and native owner required')
        self.policies, self.current_selection = policies, selected
        self.configuration = validate_native_return_config(configuration)
        self.rows = {row['owner_key']: row for row in self.configuration['profiles']}
        self.owner_factory = owner_factory
        self._owners = {}  # Reuse incumbent catalog metadata only; no credential/session cache.

    def _profile(self, principal):
        if type(principal) is not NeutralPrincipalProjection:
            raise Unavailable('Current authenticated original account required')
        if self.current_selection() is not True:
            raise Unavailable('Original native return selection is not current')
        self.policies.select(principal)
        row = self.rows.get(owner_key(principal))
        if row is None:
            raise Unavailable('Original account has no selected native return profile')
        profile = read_profile(row['profile_path'], row['profile_sha256'])
        required = {'t3_thread_read', 't3_run_result', 't3_questions_read'}
        if not required <= set(profile['operations']):
            raise Unavailable('Original native return read capabilities are not enrolled')
        return row, profile

    def current(self, principal):
        self._profile(principal)  # Recheck policy AND native-profile custody on every source admission.
        return principal

    async def __call__(self, principal, scope):
        if type(scope) is not Scope:
            raise TypeError('Exact original native scope required')
        row, profile = self._profile(principal)
        if scope.connection_id != profile['connection_id']:
            raise Conflict('Original native connection does not match the selected account profile')
        key = owner_key(principal)
        owner = self._owners.get(key)
        if owner is None:
            owner = self.owner_factory(profile,
                current_profile=lambda: read_profile(row['profile_path'], row['profile_sha256']))
            if not isinstance(owner, NativeDotFleetOwner):
                raise TypeError('Existing native profile owner required')
            self._owners[key] = owner
        if owner.profile != profile:
            raise Unavailable('Selected native profile changed; cached capabilities are not authority')
        await owner.authorize(profile['principal_key'], operation='t3_run_result',
            environment_id=scope.environment_id, project_id=scope.project_id,
            thread_id=None, arguments={})
        client = await owner.client(profile['principal_key'], scope.environment_id, scope.project_id)
        self.current(principal)
        if client.scope != scope:
            raise Conflict('Native profile returned a different original scope')
        return client
