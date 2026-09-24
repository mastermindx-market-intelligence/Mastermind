"""Closed data contract shared by the installed App and its control owner."""
from __future__ import annotations

from dataclasses import dataclass, asdict, fields
from datetime import datetime, timezone
import enum
import hashlib
import json
import re

ACCESS_SCHEMA = 'mastermind.executive_content_access.v1'
PAGE_SCHEMA = 'mastermind.executive_content_page.v1'
STEWARD_SCHEMA = 'mastermind.executive_steward_read.v1'
MAX_PAGE_BYTES = 544 * 1024
MAX_REQUEST_BYTES = 8192
MAX_RESPONSE_BYTES = 32768
ERRORS = frozenset({'CONTENT_UNAVAILABLE','ACCESS_DENIED','ACCESS_CHANGED','INVALID_REQUEST','OVER_BUDGET','GRANT_INVALIDATED'})

CONTENT_OBSERVER_PROFILES_SCHEMA = 'mastermind.executive_content_profiles.v1'


class ContentProfileKey(enum.StrEnum):
    """Exactly two slots, web and mac. No other value is valid."""
    web = 'web'
    mac = 'mac'


@dataclass(frozen=True)
class ProfileSlot:
    """One slot in the closed two-slot content profile configuration.

    enabled: a real bool, not None or int
    profile: a fully validated ContentObserverProfile v1, or None for unconfigured
    """
    enabled: bool
    profile: ContentObserverProfile | None

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise ValueError('INVALID_REQUEST')
        if self.enabled and self.profile is None:
            raise ValueError('INVALID_REQUEST')


@dataclass(frozen=True)
class ContentObserverProfiles:
    """Closed two-slot content profile envelope.

    Exactly two keys (web, mac) are required. Each slot has enabled (real bool)
    and profile (validated v1 or null). Enabled requires non-null profile.
    Disabled retains full binding for explicit status/revoke.
    """
    web: ProfileSlot
    mac: ProfileSlot

    def __post_init__(self) -> None:
        # Validate both slots have proper structure (are ProfileSlot instances)
        for slot in (self.web, self.mac):
            if type(slot) is not ProfileSlot:
                raise ValueError('INVALID_REQUEST')
        # Verify both required keys are present (already ensured by dataclass fields)
        if self.web is None or self.mac is None:
            raise ValueError('INVALID_REQUEST')

    def to_mapping(self):
        return {
            'schema': CONTENT_OBSERVER_PROFILES_SCHEMA,
            'profiles': {
                key: {
                    'enabled': slot.enabled,
                    'profile': asdict(slot.profile) if slot.profile is not None else None,
                }
                for key, slot in (('web', self.web), ('mac', self.mac))
            },
        }

    @classmethod
    def from_mapping(cls, value: dict) -> 'ContentObserverProfiles':
        """Parse the closed two-slot envelope.

        Rejects unknown fields, malformed slots, duplicate bindings across slots,
        and mixed installation/resource/scope/source/admitted-turn coordinates.
        """
        if type(value) is cls:
            value = value.to_mapping()
        if type(value) is not dict:
            raise ValueError('INVALID_REQUEST')
        if value.get('schema') != CONTENT_OBSERVER_PROFILES_SCHEMA:
            raise ValueError('INVALID_REQUEST')

        # Check for unknown fields
        if set(value) != {'schema', 'profiles'}:
            raise ValueError('INVALID_REQUEST')

        raw_profiles = value.get('profiles')
        if type(raw_profiles) is not dict or set(raw_profiles) != {'web', 'mac'}:
            raise ValueError('INVALID_REQUEST')

        slots = {}
        validated_profiles = []
        for key_str in ('web', 'mac'):
            slot_data = raw_profiles[key_str]
            if type(slot_data) is not dict or set(slot_data) != {'enabled', 'profile'}:
                raise ValueError('INVALID_REQUEST')
            enabled = slot_data['enabled']
            if type(enabled) is not bool:
                raise ValueError('INVALID_REQUEST')
            profile = slot_data['profile']
            if profile is None:
                # Null profile only valid for disabled slots
                if enabled:
                    raise ValueError('INVALID_REQUEST')
                slots[key_str] = ProfileSlot(enabled=False, profile=None)
            elif type(profile) is dict:
                validated = ContentObserverProfile.from_mapping(profile)
                if re.fullmatch(r'[0-9a-f]{64}', validated.client_ref) is None:
                    raise ValueError('INVALID_REQUEST')
                slots[key_str] = ProfileSlot(enabled=enabled, profile=validated)
                validated_profiles.append(validated)
            else:
                raise ValueError('INVALID_REQUEST')

        # Cross-slot validation: profiles must share same installation/release,
        # content resource/scope/source, and admitted turn binding coordinates.
        if len(validated_profiles) == 2:
            p0, p1 = validated_profiles
            # Same installation and release
            if p0.installation_id != p1.installation_id:
                raise ValueError('INVALID_REQUEST')
            if p0.installation_generation != p1.installation_generation:
                raise ValueError('INVALID_REQUEST')
            if p0.policy_id != p1.policy_id or p0.issuer_digest != p1.issuer_digest:
                raise ValueError('INVALID_REQUEST')
            if p0.release_sha != p1.release_sha:
                raise ValueError('INVALID_REQUEST')
            # Same content resource and scope
            if p0.content_resource != p1.content_resource:
                raise ValueError('INVALID_REQUEST')
            if p0.content_scope != p1.content_scope:
                raise ValueError('INVALID_REQUEST')
            # Same source ref
            if p0.source_ref != p1.source_ref:
                raise ValueError('INVALID_REQUEST')
            # Same admitted turn binding
            for field in ('job_id', 'attempt_id', 'session_epoch_id',
                          'process_generation_id', 'local_turn_id'):
                if getattr(p0, field) != getattr(p1, field):
                    raise ValueError('INVALID_REQUEST')
            # Check for duplicate client_ref, operation_id, permission_digest,
            # viewer_binding_digest, and profile_digest across slots.
            for field in ('client_ref', 'operation_id', 'permission_digest',
                          'viewer_binding_digest', 'profile_digest'):
                if getattr(p0, field) == getattr(p1, field):
                    raise ValueError('INVALID_REQUEST')

        return cls(
            web=slots['web'],
            mac=slots['mac'],
        )


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',',':'), ensure_ascii=True, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def epoch(value):
    if not isinstance(value, str) or re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ',value) is None:
        raise ValueError('INVALID_REQUEST')
    return int(datetime.strptime(value,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp())


@dataclass(frozen=True)
class ContentObserverProfile:
    schema: str
    installation_id: str
    installation_generation: str
    profile_digest: str
    permission_digest: str
    viewer_binding_digest: str
    policy_id: str
    content_resource: str
    content_scope: str
    issuer_digest: str
    subject_digest: str
    client_ref: str
    source_ref: str
    job_id: str
    attempt_id: str
    session_epoch_id: str
    process_generation_id: str
    local_turn_id: str
    operation_id: str
    expires_at: str
    content_decision: str
    release_sha: str

    @classmethod
    def from_mapping(cls, value):
        if type(value) is not dict or set(value) != {f.name for f in fields(cls)}:
            raise ValueError('INVALID_REQUEST')
        if any(type(v) is not str or not 1 <= len(v) <= 256 or any(ord(c)<32 for c in v) for v in value.values()):
            raise ValueError('INVALID_REQUEST')
        if value['schema'] != 'mastermind.executive_content_profile.v1' or value['content_decision'] != 'allowed_visible_response':
            raise ValueError('ACCESS_DENIED')
        if (re.fullmatch(r'managed-window:[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',value['source_ref']) is None
                or '..' in value['source_ref'] or value['client_ref']=='oauth-client-unavailable'
                or re.fullmatch(r'[0-9a-f]{40}',value['release_sha']) is None):
            raise ValueError('INVALID_REQUEST')
        for key in ('profile_digest','permission_digest','viewer_binding_digest','issuer_digest','subject_digest'):
            if re.fullmatch(r'[0-9a-f]{64}',value[key]) is None:
                raise ValueError('INVALID_REQUEST')
        from urllib.parse import urlsplit
        resource=urlsplit(value['content_resource'])
        if (resource.scheme!='https' or not resource.netloc or not resource.path or resource.username or resource.password
                or resource.query or resource.fragment or value['content_scope']!='mastermind.workspace.content.read'):
            raise ValueError('INVALID_REQUEST')
        epoch(value['expires_at'])
        if value['viewer_binding_digest'] != digest({k:value[k] for k in ('policy_id','issuer_digest','subject_digest','client_ref')}):
            raise ValueError('ACCESS_DENIED')
        if value['profile_digest'] != digest({k:v for k,v in value.items() if k!='profile_digest'}):
            raise ValueError('ACCESS_DENIED')
        return cls(**value)

    def validated(self):
        return self.from_mapping(asdict(self))

    def broker_payload(self):
        return dict(attempt=self.attempt_id,epoch=self.session_epoch_id,generation=self.process_generation_id,
                    turn=self.local_turn_id,operation_id=self.operation_id,profile_digest=self.profile_digest,
                    permission_digest=self.permission_digest,viewer_binding_digest=self.viewer_binding_digest)

    def frame(self, schema):
        return dict(schema=schema,profile_digest=self.profile_digest,source_ref=self.source_ref,
                    viewer_binding_digest=self.viewer_binding_digest)


def load_content_profiles(value):
    """Validate every slot of the existing sealed installation configuration."""
    if type(value) is ContentObserverProfile:
        return value.validated()
    if type(value) is dict and value.get('schema') == 'mastermind.executive_content_profile.v1':
        return ContentObserverProfile.from_mapping(value)
    return ContentObserverProfiles.from_mapping(value)
