"""Installed App clients for the existing peer-bound CeoIngress socket.

The App holds no Runtime, grant handle or broker connection. Every window call
uses one fixed installed viewer/source profile, never ambient mutable identity.
"""
import asyncio
from dataclasses import dataclass
from collections.abc import Callable
from typing import Any
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from integrations.executive_content_contract import (
    ContentObserverProfile, ContentObserverProfiles, ContentProfileKey,
    load_content_profiles, ACCESS_SCHEMA, PAGE_SCHEMA, STEWARD_SCHEMA,
    MAX_PAGE_BYTES, MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, canonical, epoch,
)
from integrations.business_mcp_auth.contracts import VerifiedPrincipal, validate_resource_policy
from integrations.mastermind_window_reader.production_binding import read_installed_window
from integrations.mastermind_steward_app.live_window import LiveWindowConfig
from integrations.mastermind_window_reader.owner_read_resource import ObservationBinding


@dataclass(frozen=True)
class LiveWindowProfilesConfig:
    """Immutable configuration for installed multi-profile LiveWindow composition.

    Contains the incumbent authenticator, policy, profile_loader, ceo_ingress_socket_path,
    now callable, allowed_origin, and audit_sink. Used to construct a request-owned
    profile selector for the installed composition.
    """
    authenticator: Any
    content_policy: Any
    profile_loader: Callable[[], Any]
    ceo_ingress_socket_path: Path
    now: Callable[[], int]
    allowed_origin: str
    audit_sink: Any


class CeoIngressContentClient:
    def __init__(self, socket_path, *, timeout_seconds=10):
        self.socket_path=Path(socket_path)
        if not self.socket_path.is_absolute() or not 0.1<=timeout_seconds<=30:
            raise ValueError('INVALID_REQUEST')
        self.timeout_seconds=timeout_seconds

    async def request(self, frame):
        if type(frame) is not dict or frame.get('schema') not in (ACCESS_SCHEMA,PAGE_SCHEMA,STEWARD_SCHEMA):
            raise ValueError('INVALID_REQUEST')
        encoded=canonical(frame)+b'\n'
        if len(encoded)>MAX_REQUEST_BYTES:
            raise ValueError('OVER_BUDGET')
        ceiling=MAX_PAGE_BYTES if frame['schema']==PAGE_SCHEMA else MAX_RESPONSE_BYTES
        async def exchange():
            reader,writer=await asyncio.open_unix_connection(str(self.socket_path),limit=ceiling)
            try:
                writer.write(encoded)
                await writer.drain()
                raw=await reader.readuntil(b'\n')
                if len(raw)>ceiling:
                    raise ValueError('OVER_BUDGET')
                value=json.loads(raw)
                key='page' if frame['schema']==PAGE_SCHEMA else 'access' if frame['schema']==ACCESS_SCHEMA else 'result'
                if type(value) is not dict or set(value)!={'ok',key} or value['ok'] is not True or type(value[key]) is not dict:
                    raise ValueError('CONTENT_UNAVAILABLE')
                return value
            finally:
                writer.close()
                await writer.wait_closed()
        try:
            return await asyncio.wait_for(exchange(),self.timeout_seconds)
        except Exception:
            # No retry, remote error details, payload text or socket paths.
            raise ValueError('CONTENT_UNAVAILABLE') from None


class InstalledWindowSource:
    def __init__(self, *, profile, client, now):
        self.profile=profile.validated()
        self.client=client
        self.now=now

    async def access(self):
        p=self.profile
        instant=self.now()
        if type(instant) is not int or instant>=epoch(p.expires_at):
            raise ValueError('ACCESS_DENIED')
        access=(await self.client.request(p.frame(ACCESS_SCHEMA)))['access']
        if (set(access)!={'ticket_digest','retained_scope','expires_at'}
                or type(access['ticket_digest']) is not str or re.fullmatch(r'[0-9a-f]{64}',access['ticket_digest']) is None
                or type(access['retained_scope']) is not list or len(access['retained_scope'])!=2
                or any(type(x) is not str or not 1<=len(x)<=256 for x in access['retained_scope'])
                or access['retained_scope'][0]!=p.process_generation_id
                or access['expires_at']!=p.expires_at or self.now()>=epoch(p.expires_at)):
            raise ValueError('ACCESS_CHANGED')
        return access

    async def current_access(self, principal, source_ref):
        p=self.profile
        if (type(principal) is not VerifiedPrincipal or source_ref!=p.source_ref
                or principal.resource!=p.content_resource or principal.scopes!=(p.content_scope,)
                or any(getattr(principal,k)!=getattr(p,k) for k in ('policy_id','issuer_digest','subject_digest','client_ref'))):
            return None
        try:
            access=await self.access()
            return (p.profile_digest,access['ticket_digest'],access['expires_at'])
        except Exception:
            return None

    async def read_source(self):
        p=self.profile
        before=await self.access()
        async def read_page(ticket,cursor,max_items):
            frame=dict(p.frame(PAGE_SCHEMA),access_ticket_digest=ticket,cursor=cursor,max_items=max_items)
            return (await self.client.request(frame))['page']
        raw=await read_installed_window(source_ref=p.source_ref,access=before,read_page=read_page,
            now=lambda:datetime.fromtimestamp(self.now(),timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
        if before!=await self.access():
            raise ValueError('ACCESS_CHANGED')
        return raw


def _select_profile_for_principal(profiles_config, principal):
    """Select only from the validated configuration and incumbent A1 principal."""
    if type(principal) is not VerifiedPrincipal:
        return None
    value = load_content_profiles(profiles_config.profile_loader())
    profiles = (value,) if type(value) is ContentObserverProfile else tuple(
        slot.profile for slot in (value.web, value.mac)
        if slot.enabled and slot.profile is not None
    )
    matches = [
        profile for profile in profiles
        if principal.resource == profile.content_resource
        and principal.scopes == (profile.content_scope,)
        and all(getattr(principal, field) == getattr(profile, field)
                for field in ('policy_id', 'issuer_digest', 'subject_digest', 'client_ref'))
    ]
    return matches[0] if len(matches) == 1 else None


def construct_installed_live_window(*, profile, authenticator, content_policy, audit_sink,
                                    ceo_ingress_socket_path, now, allowed_origin):
    p=profile.validated() if type(profile) is ContentObserverProfile else ContentObserverProfile.from_mapping(profile)
    policy=validate_resource_policy(content_policy)
    if policy.policy_id!=p.policy_id or policy.resource!=p.content_resource or policy.required_scopes!=(p.content_scope,):
        raise ValueError('ACCESS_DENIED')
    source=InstalledWindowSource(profile=p,client=CeoIngressContentClient(ceo_ingress_socket_path),now=now)
    # The installed path always derives the typed owner tuple from the validated
    # profile. A profile whose Job/Attempt tokens are noncanonical is a closed
    # typed refusal here — never a silent fallback to the generic v1 shape.
    binding=ObservationBinding(job_id=p.job_id,attempt_id=p.attempt_id)
    return LiveWindowConfig(authenticator=authenticator,content_policy=policy,current_access=source.current_access,
        read_source=source.read_source,source_ref=p.source_ref,now=now,allowed_origin=allowed_origin,audit_sink=audit_sink,
        observation_binding=binding)


def build_installed_steward_app(*, profile, steward_policy, steward_token_verifier,
                                content_authenticator, content_policy, audit_sink,
                                ceo_ingress_socket_path, now, allowed_origin):
    """Compose both concrete read transports into the existing Steward factory.

    The launcher supplies its existing A1 verifier/cache/audit owners and sealed
    public profile. This function creates neither credentials nor permissions.
    """
    from integrations.mastermind_steward_app.installed_grounding import CeoIngressStewardReadPort
    from integrations.mastermind_steward_app.server import build_contract_server
    from integrations.mastermind_steward_app.app import build_authenticated_app
    window=construct_installed_live_window(profile=profile,authenticator=content_authenticator,
        content_policy=content_policy,audit_sink=audit_sink,ceo_ingress_socket_path=ceo_ingress_socket_path,
        now=now,allowed_origin=allowed_origin)
    port=CeoIngressStewardReadPort(CeoIngressContentClient(ceo_ingress_socket_path))
    return build_authenticated_app(build_contract_server(port),policy=steward_policy,
        token_verifier=steward_token_verifier,allowed_origins=(allowed_origin,),live_window=window)


def build_installed_steward_app_with_profiles(
    *, profiles_config, steward_policy, steward_token_verifier, audit_sink=None,
):
    """Compose both qualified clients on the existing fixed content mount."""
    from urllib.parse import urlsplit
    from integrations.mastermind_steward_app.installed_grounding import CeoIngressStewardReadPort
    from integrations.mastermind_steward_app.server import build_contract_server
    from integrations.mastermind_steward_app.app import build_authenticated_app, _canonical_raw_path
    from integrations.mastermind_steward_app.live_window import LiveWindowDispatch
    from integrations.mastermind_steward_app.installed_profiles import live_window_reader_with_profiles

    resource = urlsplit(steward_policy.resource)
    metadata_path = urlsplit(steward_policy.resource_metadata_url).path
    reader, path = live_window_reader_with_profiles(
        profiles_config, steward_resource=steward_policy.resource,
        reserved_paths=(resource.path, metadata_path, '/healthz', '/readyz'),
    )
    port = CeoIngressStewardReadPort(CeoIngressContentClient(profiles_config.ceo_ingress_socket_path))
    app = build_authenticated_app(
        build_contract_server(port), policy=steward_policy,
        token_verifier=steward_token_verifier,
        allowed_origins=(profiles_config.allowed_origin,),
    )
    return LiveWindowDispatch(
        app, reader=reader, path=path, canonical_raw_path=_canonical_raw_path,
    )
