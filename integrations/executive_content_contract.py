"""Closed data contract shared by the installed App and its control owner."""
from dataclasses import dataclass, asdict, fields
from datetime import datetime, timezone
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
