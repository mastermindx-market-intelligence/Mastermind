"""Finite ASGI recorded-content consumer for an EXISTING authenticated app.

No listener, issuer, token store, grant registry, provider client or filesystem
selector lives here. Production construction requires the incumbent Business
JWT verifier, current per-source access check and qualified read callable.
Tests using OwnerFixture establish consumer semantics, not real user login.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
import hashlib
from http import HTTPStatus
import json
import re
from collections.abc import Awaitable, Callable
from typing import Protocol
from urllib.parse import urlsplit

from common.executive_workspace_contract import _check_attempt_id, _check_job_id
from integrations.mastermind_window_reader.recorded_view import (
    CaptureError,
    MAX_INPUT,
    load_capture,
    project_capture,
)

WIRE_SCHEMA='mastermind.workspace.recorded_read_candidate.v1'
WINDOW_WIRE_SCHEMA='mastermind.workspace.window_read_candidate.v1'
WINDOW_WIRE_SCHEMA_V2='mastermind.workspace.window_read_candidate.v2'
CONTENT_SCOPE='mastermind.workspace.content.read'  # proposed resource scope; not enrolled
MAX_RESPONSE_BYTES=2_000_000


@dataclass(frozen=True)
class ObservationBinding:
    """Frozen owner Job/Attempt tuple. Not a generic metadata dict."""
    job_id: str
    attempt_id: str

    def __post_init__(self):
        if not _check_job_id(self.job_id) or not _check_attempt_id(self.attempt_id):
            raise ValueError('invalid observation binding')

    def as_wire(self):
        return {'job_id': self.job_id, 'attempt_id': self.attempt_id}


def snapshot_observation_binding(value):
    """Copy and re-validate a typed owner binding. Never coerce a mapping."""
    if value is None:
        return None
    if type(value) is not ObservationBinding:
        raise ValueError('invalid observation binding')
    return ObservationBinding(job_id=value.job_id, attempt_id=value.attempt_id)

class ExistingReadOwner(Protocol):
    async def authorize(self,header:str,resource:str,source_ref:str)->tuple|None: ...
    async def read(self,source_ref:str)->bytes: ...


def _ticket(value):
    """Copy only bounded immutable owner evidence; never serialize it."""
    if type(value) is not tuple or not 1<=len(value)<=16:return None
    for item in value:
        if not (type(item) is str and 0<len(item)<=2048 or type(item) is int):return None
    return tuple(value)


def _url(value,*,origin=False):
    if not isinstance(value,str) or len(value)>2048:raise ValueError('invalid configured URL')
    p=urlsplit(value)
    if (p.scheme!='https' or not p.netloc or p.username or p.password or p.fragment or p.query
        or '%' in value or any(ord(c)<33 or ord(c)>126 for c in value) or '\\' in value):
        raise ValueError('invalid configured URL')
    if origin:
        if p.path:raise ValueError('origin must have no path')
    elif not re.fullmatch(r'/[A-Za-z0-9/_-]+',p.path) or '//' in p.path:
        raise ValueError('invalid resource path')
    return p


class NativeOutputReadResource:
    """Mount-only fixed GET resource; no automatic service or source enrollment."""
    def __init__(self,*,owner:ExistingReadOwner,resource:str,source_ref:str,
                 allowed_origin:str,max_response_bytes=MAX_RESPONSE_BYTES,timeout_seconds=15,source_kind="recorded",
                 observation_binding=None):
        if owner is None or not callable(getattr(owner,'authorize',None)) or not callable(getattr(owner,'read',None)):
            raise TypeError('existing read owner required')
        p=_url(resource);o=_url(allowed_origin,origin=True)
        if p.netloc!=o.netloc:raise ValueError('same-origin mount required')
        if source_kind not in ('recorded','live-window'):raise ValueError('unsupported explicit source kind')
        prefix='native-lane:' if source_kind=='recorded' else 'managed-window:'
        if not isinstance(source_ref,str) or not re.fullmatch(prefix+r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',source_ref) or '..' in source_ref:
            raise ValueError('invalid fixed source reference')
        if type(max_response_bytes) is not int or not 256<=max_response_bytes<=MAX_RESPONSE_BYTES:
            raise ValueError('invalid response limit')
        if type(timeout_seconds) not in (int,float) or not 0<timeout_seconds<=30:raise ValueError('invalid time limit')
        binding=snapshot_observation_binding(observation_binding)
        if binding is not None and source_kind!='live-window':
            raise ValueError('invalid observation binding')
        self._owner=owner;self._resource=resource;self._ref=source_ref;self._kind=source_kind
        self._path=p.path.encode('ascii');self._host=p.netloc.encode('ascii');self._origin=allowed_origin.encode('ascii')
        self._limit=max_response_bytes;self._timeout=timeout_seconds
        self._binding=binding

    async def __call__(self,scope,receive,send):
        async def reply(status,payload):
            status=int(status)
            raw=payload if isinstance(payload,bytes) else json.dumps(payload,separators=(',',':')).encode()
            await send({'type':'http.response.start','status':status,'headers':[
                (b'content-type',b'application/json; charset=utf-8'),(b'cache-control',b'no-store'),
                (b'pragma',b'no-cache'),(b'x-content-type-options',b'nosniff'),
                (b'referrer-policy',b'no-referrer'),(b'content-length',str(len(raw)).encode())]})
            await send({'type':'http.response.body','body':raw,'more_body':False})
        if scope.get('type')!='http':raise ValueError('HTTP resource only')
        if (scope.get('path','').encode('ascii',errors='replace')!=self._path
            or scope.get('raw_path')!=self._path or scope.get('root_path') or scope.get('query_string')):
            await reply(HTTPStatus.NOT_FOUND,{'error':'not_found'});return
        if scope.get('method')!='GET':await reply(HTTPStatus.METHOD_NOT_ALLOWED,{'error':'method_not_allowed'});return
        if scope.get('scheme')!='https':await reply(HTTPStatus.FORBIDDEN,{'error':'transport_refused'});return
        raw_headers=scope.get('headers',[])
        if not isinstance(raw_headers,(list,tuple)) or len(raw_headers)>64:
            await reply(HTTPStatus.BAD_REQUEST,{'error':'invalid_request'});return
        headers={}
        for pair in raw_headers:
            if (not isinstance(pair,(list,tuple)) or len(pair)!=2 or
                not all(isinstance(x,bytes) for x in pair) or len(pair[1])>17000):
                await reply(HTTPStatus.BAD_REQUEST,{'error':'invalid_request'});return
            k,v=pair;headers.setdefault(k.lower(),[]).append(v)
        if (len(headers.get(b'host',[]))!=1 or any(len(headers.get(k,[]))>1 for k in
              (b'authorization',b'origin',b'content-length')) or b'transfer-encoding' in headers):
            await reply(HTTPStatus.BAD_REQUEST,{'error':'invalid_request'});return
        if headers[b'host'][0]!=self._host or headers.get(b'origin',[self._origin])[0]!=self._origin:
            await reply(HTTPStatus.FORBIDDEN,{'error':'transport_refused'});return
        if headers.get(b'content-length',[b'0'])[0]!=b'0':await reply(HTTPStatus.BAD_REQUEST,{'error':'invalid_request'});return
        auths=headers.get(b'authorization',[])
        if not auths:await reply(HTTPStatus.UNAUTHORIZED,{'error':'authentication_required'});return
        try:
            header=auths[0].decode('ascii')
            if header!=header.strip() or any(ord(c)<32 or ord(c)==127 for c in header):raise ValueError()
        except (UnicodeError,ValueError):await reply(HTTPStatus.BAD_REQUEST,{'error':'invalid_request'});return
        async def empty_request_body():
            # ASGI may split even an empty GET into several empty frames.
            # Bound both frames and total wait; no content may enter this read.
            for _ in range(8):
                message=await receive()
                if not isinstance(message,dict) or message.get('type')!='http.request' or message.get('body',b'')!=b'':return False
                more=message.get('more_body',False)
                if type(more) is not bool:return False
                if not more:return True
            return False
        try:empty=await asyncio.wait_for(empty_request_body(),self._timeout)
        except Exception:empty=False
        if not empty:await reply(HTTPStatus.BAD_REQUEST,{'error':'invalid_request'});return
        try:
            first=_ticket(await asyncio.wait_for(self._owner.authorize(header,self._resource,self._ref),self._timeout))
        except Exception:first=None
        if first is None:await reply(HTTPStatus.UNAUTHORIZED,{'error':'authentication_required'});return
        encoded=None
        try:
            raw=await asyncio.wait_for(self._owner.read(self._ref),self._timeout)
            if type(raw) is not bytes or not 0<len(raw)<=MAX_INPUT:raise CaptureError('INPUT_BOUND')
            if self._kind=='recorded':
                view=project_capture(load_capture(raw))
                if view['lane']['ref']!=self._ref:raise CaptureError('SOURCE_SCOPE_MISMATCH')
                view['capture_sha256']=hashlib.sha256(raw).hexdigest()
                wire={'schema':WIRE_SCHEMA,'selection_ref':self._ref,'mode':'recorded-source-read','view':view}
            else:
                from integrations.mastermind_window_reader.live_window_read import project_window
                view=project_window(load_capture(raw))
                if view['source_ref']!=self._ref:raise CaptureError('SOURCE_SCOPE_MISMATCH')
                if self._binding is None:
                    wire={'schema':WINDOW_WIRE_SCHEMA,'selection_ref':self._ref,'mode':'observed-turn-window','view':view}
                else:
                    binding=snapshot_observation_binding(self._binding)
                    wire={'schema':WINDOW_WIRE_SCHEMA_V2,'selection_ref':self._ref,'mode':'observed-turn-window',
                          'view':view,'observation_binding':binding.as_wire()}
            encoded=json.dumps(wire,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode()
            if len(encoded)>self._limit:raise CaptureError('OUTPUT_BOUND')
        except Exception:
            encoded=None
        # Last decision is after ALL awaited source work and safe serialization.
        # This cannot retract bytes already released before a later revocation.
        try:
            final=_ticket(await asyncio.wait_for(self._owner.authorize(header,self._resource,self._ref),self._timeout))
        except Exception:final=None
        if final is None or final!=first:await reply(HTTPStatus.FORBIDDEN,{'error':'access_changed'});return
        if encoded is None:await reply(HTTPStatus.BAD_GATEWAY,{'error':'source_unavailable'});return
        await reply(200,encoded)


def from_existing_business_owner(*,authenticator,policy,current_access,read_source,source_ref,now,allowed_origin,audit_sink,source_kind="recorded",observation_binding=None):
    """Optional production-composition seam; never used to mint new authority.

    Imports the actual incumbent classes only when configured by that owner.
    The incumbent closed audit sink is mandatory; no fallback log/store exists.
    `current_access(principal, source_ref)` must be its current target-grant
    decision returning an immutable evidence tuple, or None. No default allow.
    `read_source()` is a bounded authorized visible-content reader; no path/URL
    enters from the HTTP client. No issuer, key, store, native adapter or route
    installation is created by this function. Scope enrollment remains required.
    """
    from integrations.business_mcp_auth.contracts import (VerifiedPrincipal,validate_resource_policy,AuthAuditEvent,AUTH_AUDIT_SCHEMA,AuthError,AuthErrorCode)
    from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
    if not isinstance(authenticator,JwtAuthenticator):raise TypeError('incumbent JwtAuthenticator required')
    expected=validate_resource_policy(policy)
    if expected.required_scopes!=(CONTENT_SCOPE,):raise ValueError('separate accepted content scope required')
    if not all(callable(c) for c in (current_access,read_source,now)) or not callable(getattr(audit_sink,'emit',None)):raise TypeError('current owner dependencies and audit sink required')
    class BusinessOwner:
        async def authorize(self,header,resource,ref):
            result=None;code=AuthErrorCode.SCOPE_REFUSED.value
            try:
                result=await self._authorize(header,resource,ref)
                if result is not None:code='accepted'
            except AuthError as exc:code=exc.code.value
            except Exception:code=AuthErrorCode.INTERNAL_ERROR.value
            try:
                audit_sink.emit(AuthAuditEvent(schema=AUTH_AUDIT_SCHEMA,policy_id=expected.policy_id,code=code,accepted=result is not None))
            except Exception:return None
            return result
        async def _authorize(self,header,resource,ref):
            if resource!=expected.resource or ref!=source_ref or validate_resource_policy(authenticator.policy)!=expected:return None
            instant=now()
            if type(instant) is not int:return None
            p=await authenticator.verify_authorization_header(header,now=instant)
            if not isinstance(p,VerifiedPrincipal) or validate_resource_policy(authenticator.policy)!=expected:return None
            if p.policy_id!=expected.policy_id or p.resource!=resource or p.scopes!=expected.required_scopes:return None
            stamp=_ticket(await current_access(p,ref))
            if stamp is None or len(stamp)>9 or validate_resource_policy(authenticator.policy)!=expected:return None
            # The current-access owner may await work beyond the token lifetime.
            # Reuse the pinned policy's validity ceiling after that last await.
            final_time=now()
            if type(final_time) is not int or final_time<instant or final_time>p.expires_at+expected.clock_skew_seconds:return None
            # Typed principal plus actual current owner grant; never caller JSON.
            return (p.policy_id,p.issuer_digest,p.subject_digest,p.client_ref,p.jti_digest or 'no-jti',
                    p.issued_at,p.expires_at,*stamp)
        async def read(self,ref):
            if ref!=source_ref:raise ValueError('source changed')
            return await read_source()
    return NativeOutputReadResource(owner=BusinessOwner(),resource=expected.resource,
        source_ref=source_ref,allowed_origin=allowed_origin,source_kind=source_kind,
        observation_binding=observation_binding)
