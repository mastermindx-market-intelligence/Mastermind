"""Optional attended-Fabric transport; existing Runtime/Fabric own every effect.

The injected reviewed Backend MUST atomically fence original Attempt + canonical
start hash in its existing durable receipts before provider I/O. A status saying
UNSTARTED_PROVEN is not a reusable authorization: execute('start') must recheck
and consume that same fence. This module owns no execution ledger, retry, account
selection, UID sweep or scheduler. Reopened/lost-response starts query status;
existing or uncertain effects are never sent to start again.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping, Protocol

from ops.executive_os.capacity_broker_topology import CONTROL_UID

from control_plane.executive_worker_broker import (
    BROKER_REQUEST_SCHEMA_VERSION, BROKER_RESPONSE_SCHEMA_VERSION,
    PeerCredentials, PeerAuthorizationError, get_peer_credentials,
)
from control_plane.worker_execution_contract import (
    BinaryAttestation, LaunchAttestation, OrchestrationLaunchSpec,
    WorkerProcessRef, LAUNCH_ATTESTATION_SCHEMA_VERSION, CancelReceipt,
    ValidationReceipt, CollectionReceipt, WorkerResult, WorkerRunStatus, ArtifactReceipt,
)

CONFIG_SCHEMA_VERSION = 'mastermind.executive_fabric_bridge_config/v1'
ADAPTER_ID = 'attended-fabric'
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}')
_DIGEST = re.compile(r'[0-9a-f]{64}')
_COMMIT = re.compile(r'[0-9a-f]{40}')
_BINDING_FIELDS = frozenset({'root_id','job_id','attempt_id','effective_grant_digest','commission_sha256'})
_OPERATIONS = frozenset({'start','status','collect','cancel','validate'})
_TRUSTED_CONFIG = object()
_ERROR_CODES = frozenset({'BrokerProtocolError','PeerAuthorizationError','ConfigTrustError',
    'EFFECT_UNKNOWN','BridgeIdentityError','SocketBindingError','BackendNotConfiguredError',
    'BackendUnavailableError','BackendRefusedError','CANCEL_UNAVAILABLE_USE_EXISTING_OWNER',
    'PRE_EFFECT_REFUSED','UnsupportedValidationError','PlatformRefusal'})


class BridgeProtocolError(RuntimeError):
    """Closed, secret-free failure; code is carried in the standard envelope."""
    def __init__(self, code: str, message: str = 'Fabric bridge refused the operation'):
        self.code = code if code in _ERROR_CODES else 'BackendRefusedError'
        super().__init__(f'{self.code}: {message}')


class Backend(Protocol):
    async def execute(self, operation: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """Use only existing original-id receipts; fence before effects, no replay.

        start/status preflight returns adapter_id, binding, request_sha256,
        start_state UNSTARTED_PROVEN/EXISTS/EFFECT_UNKNOWN. EXISTS additionally
        returns the retained start_result. start gets broker-computed
        start_request_sha256, which must be compared in the durable fence.
        Every payload carries the Runtime-pinned physical_binding_sha256.
        The backend must compare that route atomically at its effect boundary;
        broker status preflight is not permission to reroute between calls.
        Neither missing receipt nor NOT_FOUND proves safe first use.
        """
        ...


def _refuse(code='BrokerProtocolError', message='Request does not match the closed bridge contract'):
    raise BridgeProtocolError(code, message)


def _object(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        _refuse()
    return value


def _identifier(value):
    if type(value) is not str or _ID.fullmatch(value) is None:
        _refuse()
    return value


def _digest(value):
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        _refuse()
    return value


def _absolute(value):
    if type(value) is not str or not value or '\x00' in value:
        _refuse()
    path=Path(value)
    if not path.is_absolute() or '..' in path.parts or str(path) != value:
        _refuse()
    return path


def _under(value, root):
    path=_absolute(value)
    if path == root or not path.is_relative_to(root):
        _refuse()
    return path


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                          allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise BridgeProtocolError('BrokerProtocolError') from exc


def _pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            _refuse(message='Duplicate JSON keys are forbidden')
        result[key]=value
    return result


def _strict_json(raw):
    def constant(_value):
        _refuse(message='Nonfinite JSON values are forbidden')
    try:
        value=json.loads(raw.decode('utf-8',errors='strict'), object_pairs_hook=_pairs,
                         parse_constant=constant)
        _canonical(value)  # Reject overflowed numeric literals and lone surrogates too.
        return value
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise BridgeProtocolError('BrokerProtocolError','Invalid bounded UTF-8 JSON') from exc


def decode_request(raw: bytes, *, max_bytes: int):
    if type(raw) is not bytes or not raw or len(raw)>max_bytes or not raw.endswith(b'\n'):
        _refuse(message='Invalid request framing')
    return _object(_strict_json(raw), {'schema_version','request_id','operation','payload'})


@dataclasses.dataclass(frozen=True)
class BridgeConfig:
    schema_version: str
    adapter_id: str
    bridge_uid: int
    control_uid: int
    launchd_socket_name: str
    socket_path: Path
    workspace_root: Path
    run_root: Path
    max_request_bytes: int
    max_response_bytes: int
    request_timeout_seconds: float
    validation_commands: tuple[tuple[str,...],...]
    source_sha256: str = ''
    _trust: object = dataclasses.field(default=None,repr=False,compare=False)

    @classmethod
    def from_document(cls, value):
        fields={f.name for f in dataclasses.fields(cls)}-{'source_sha256','_trust'}
        _object(value,fields)
        if (value['schema_version']!=CONFIG_SCHEMA_VERSION or value['adapter_id']!=ADAPTER_ID
                or type(value['bridge_uid']) is not int or value['bridge_uid']<=0
                or value['bridge_uid']==CONTROL_UID
                or type(value['control_uid']) is not int or value['control_uid']!=CONTROL_UID):
            _refuse('ConfigTrustError','Fixed bridge/control principal or schema mismatch')
        _identifier(value['launchd_socket_name'])
        for key,minimum,maximum in [('max_request_bytes',1024,1024*1024),
                                    ('max_response_bytes',1024,4*1024*1024)]:
            if type(value[key]) is not int or not minimum<=value[key]<=maximum:
                _refuse('ConfigTrustError','Invalid frame ceiling')
        timeout=value['request_timeout_seconds']
        if type(timeout) not in (int,float) or not math.isfinite(timeout) or not .1<=timeout<=3600:
            _refuse('ConfigTrustError','Invalid bounded timeout')
        commands=value['validation_commands']
        if type(commands) is not list or len(commands)>32:
            _refuse('ConfigTrustError','Invalid validation allowlist')
        normalized=[]
        for argv in commands:
            if (type(argv) is not list or not 1<=len(argv)<=128
                    or any(type(arg) is not str or not arg or '\x00' in arg or len(arg)>4096 for arg in argv)):
                _refuse('ConfigTrustError','Invalid validation argv')
            _absolute(argv[0])
            if Path(argv[0]).name in {'sh','bash','dash','zsh','csh','tcsh','fish','env'}:
                _refuse('ConfigTrustError','Shell validation is forbidden')
            normalized.append(tuple(argv))
        result=dict(value)
        for key in ('socket_path','workspace_root','run_root'):
            result[key]=_absolute(value[key])
        if result['workspace_root']==result['run_root']:
            _refuse('ConfigTrustError','Workspace and run roots must be distinct')
        result['validation_commands']=tuple(normalized)
        return cls(**result)


def _trusted_parent_chain(path: Path):
    for parent in path.parents:
        info=parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_mode & 0o022:
            _refuse('ConfigTrustError','Config parent is not root-controlled')


def load_config(path: Path) -> BridgeConfig:
    """Read one bounded root-installed file; no repairs, credentials or defaults."""
    path=_absolute(str(path))
    fd=None
    try:
        _trusted_parent_chain(path)
        fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0))
        before=os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid!=0
                or before.st_mode & 0o022 or before.st_size>65536):
            _refuse('ConfigTrustError','Config is not a bounded root-owned regular file')
        raw=os.read(fd,65537)
        after=os.fstat(fd)
        visible=path.stat(follow_symlinks=False)
        if (len(raw)>65536 or len(raw)!=before.st_size or (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)
                !=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)
                or (after.st_dev,after.st_ino)!=(visible.st_dev,visible.st_ino)):
            _refuse('ConfigTrustError','Config identity changed while reading')
        config=BridgeConfig.from_document(_strict_json(raw))
        return dataclasses.replace(config,source_sha256=hashlib.sha256(raw).hexdigest(),_trust=_TRUSTED_CONFIG)
    except OSError as exc:
        raise BridgeProtocolError('ConfigTrustError','Root-installed config is unavailable') from exc
    finally:
        if fd is not None:os.close(fd)


def start_request_sha256(payload):
    material={key:value for key,value in payload.items() if key!='start_request_sha256'}
    return hashlib.sha256(_canonical({'operation':'start','payload':material})).hexdigest()


def _binding(value):
    _object(value,_BINDING_FIELDS)
    for key in ('root_id','job_id','attempt_id'):_identifier(value[key])
    for key in ('effective_grant_digest','commission_sha256'):_digest(value[key])
    return value


def _same_backend_binding(result, binding, digest=None):
    if (type(result) is not dict or result.get('adapter_id')!=ADAPTER_ID
            or result.get('binding')!=binding
            or type(result.get('physical_binding_sha256')) is not str
            or _DIGEST.fullmatch(result['physical_binding_sha256']) is None
            or (digest is not None and result.get('request_sha256')!=digest)):
        _refuse('EFFECT_UNKNOWN','Backend receipt is not bound to the original Attempt')


def _complete_start_result(result,binding,digest,spec):
    _same_backend_binding(result,binding,digest)
    _object(result,{'adapter_id','binding','request_sha256','physical_binding_sha256','process_ref','launch_attestation'})
    ref=_object(result['process_ref'],{f.name for f in dataclasses.fields(WorkerProcessRef)})
    binary=_object(ref['binary'],{f.name for f in dataclasses.fields(BinaryAttestation)})
    required={f.name for f in dataclasses.fields(LaunchAttestation)
              if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING}
    allowed={f.name for f in dataclasses.fields(LaunchAttestation)}
    att=result['launch_attestation']
    if type(att) is not dict or not required<=set(att)<=allowed:
        _refuse('EFFECT_UNKNOWN','Complete launch attestation is required')
    if (att['schema_version']!=LAUNCH_ATTESTATION_SCHEMA_VERSION or ref['run_id']!=binding['attempt_id']
            or att['binary']!=binary or att['launch_nonce']!=ref['launch_nonce']
            or att['observed_base_sha']!=ref['base_sha'] or ref['base_sha']!=spec['expected_base_sha']
            or att['expected_base_sha']!=spec['expected_base_sha']
            or att.get('isolation_manifest_sha256')!=spec.get('isolation_manifest_sha256')
            or att['prompt_sha256']!=hashlib.sha256(spec['prompt'].encode()).hexdigest()
            or att['executable_path']!=binary['real_path']):
        _refuse('EFFECT_UNKNOWN','Launch attestation does not match the original contract')
    for key in ('pid','pgid','session_id'):
        if type(ref[key]) is not int or ref[key]<=0:
            _refuse('EFFECT_UNKNOWN','Actual owned process identity is required')
    if ref['pid']!=ref['pgid'] or ref['pid']!=ref['session_id']:
        _refuse('EFFECT_UNKNOWN','Owned process/session identity disagrees')
    for key in ('effective_uid','effective_gid','real_uid','real_gid'):
        if type(ref[key]) is not int or ref[key]<0:
            _refuse('EFFECT_UNKNOWN','Actual process UID/GID is required')
    expected={key:ref[key] for key in ('pid','pgid','session_id','effective_uid','effective_gid','real_uid','real_gid')}
    expected.update(start_identity=ref['process_start_identity'],boot_id=ref['boot_session_id'])
    if att['process_identity']!=expected:
        _refuse('EFFECT_UNKNOWN','Attested process identity disagrees')
    for key in ('process_start_identity','boot_session_id','launch_nonce','started_at'):
        if type(ref[key]) is not str or not 1<=len(ref[key])<=128:
            _refuse('EFFECT_UNKNOWN','Missing process provenance')
    _digest(binary['sha256']);_digest(att['permission_profile_sha256']);_digest(att['isolation_manifest_sha256'])
    for key in ('path','real_path'):_absolute(binary[key])
    for key in ('size','device','inode','mode','uid','gid','mtime_ns'):
        if type(binary[key]) is not int or binary[key]<0:
            _refuse('EFFECT_UNKNOWN','Incomplete binary identity')
    if (type(binary['version']) is not str or not binary['version']
            or binary['size']==0 or not binary['mode'] & 0o111
            or (binary['team_identifier'] is not None and type(binary['team_identifier']) is not str)):
        _refuse('EFFECT_UNKNOWN','Incomplete binary attestation')
    for key in ('stdout_path','stderr_path','result_path'):_under(ref[key],Path(spec['run_dir']))
    for key in ('created_at','executable_path'):
        if type(att[key]) is not str or not 1<=len(att[key])<=4096:
            _refuse('EFFECT_UNKNOWN','Missing launch provenance')
    for key in ('workspace_identity','worker_identity','provider_home_identity','secret_canary_verdict'):
        if type(att[key]) is not dict or not att[key]:
            _refuse('EFFECT_UNKNOWN','Missing complete launch provenance')
    path_fields={'path','device','inode','uid','gid','mode','mtime_ns'}
    for key in ('workspace_identity','provider_home_identity'):
        identity=att[key]
        if not path_fields<=set(identity) or set(identity)-path_fields-{'git_head'}:
            _refuse('EFFECT_UNKNOWN','Incomplete filesystem identity')
        _absolute(identity['path'])
        if any(type(identity[k]) is not int or identity[k]<0 for k in path_fields-{'path'}):
            _refuse('EFFECT_UNKNOWN','Invalid filesystem identity')
    worker=att['worker_identity']
    if (set(worker)!={'requested_user','observed_user','expected_uid','expected_gid',
                      'effective_uid','effective_gid','real_uid','real_gid'}
            or worker['requested_user']!=spec.get('worker_user')
            or worker['observed_user']!=worker['requested_user']
            or worker['expected_uid']!=ref['effective_uid']
            or worker['expected_gid']!=ref['effective_gid']
            or att['provider_home_identity']['uid']!=ref['effective_uid']
            or att['provider_home_identity']['gid']!=ref['effective_gid']
            or att['secret_canary_verdict'].get('passed') is not True):
        _refuse('EFFECT_UNKNOWN','Worker/home/canary provenance is incomplete')
    if spec.get('expected_worker_uid') is not None and spec['expected_worker_uid']!=ref['effective_uid']:
        _refuse('EFFECT_UNKNOWN','LaunchSpec worker UID differs')
    if spec.get('expected_worker_gid') is not None and spec['expected_worker_gid']!=ref['effective_gid']:
        _refuse('EFFECT_UNKNOWN','LaunchSpec worker GID differs')
    if att['workspace_identity'].get('path')!=spec['workspace_path']:
        _refuse('EFFECT_UNKNOWN','Workspace attestation differs from LaunchSpec')
    for key in ('effective_uid','effective_gid','real_uid','real_gid'):
        if att['worker_identity'].get(key)!=ref[key]:
            _refuse('EFFECT_UNKNOWN','Worker principal attestation disagrees')
    for key in ('rendered_argv','environment_keys'):
        if type(att[key]) is not list or not att[key] or any(type(v) is not str for v in att[key]):
            _refuse('EFFECT_UNKNOWN','Missing launch argv/environment provenance')
    return result


class FabricBridgeBroker:
    adapter_id=ADAPTER_ID

    def __init__(self,config: BridgeConfig,backend: Backend,*,peer_resolver=get_peer_credentials):
        if not isinstance(config,BridgeConfig) or config._trust is not _TRUSTED_CONFIG:
            _refuse('ConfigTrustError','Broker requires a root-installed immutable config')
        self.config=config
        self.backend=backend
        self.peer_resolver=peer_resolver

    def require_service_identity(self):
        if os.geteuid()!=self.config.bridge_uid:
            _refuse('BridgeIdentityError','Bridge must run as its configured principal')
        # The bridge principal is shared: NEVER enumerated, swept or claimed dedicated.

    def _authorize_peer(self,peer):
        if (not isinstance(peer,PeerCredentials) or type(peer.uid) is not int
                or peer.uid!=CONTROL_UID):
            _refuse('PeerAuthorizationError','Only the authenticated Control principal is accepted')

    def _payload(self,operation,payload):
        extra={'start':{'launch_spec','validation_commands'},'status':{'run_id'},
               'collect':{'run_id'},'cancel':{'run_id','reason'},'validate':{'run_id','argv','timeout_seconds'}}[operation]
        if operation=='status' and type(payload) is dict and 'start_request_sha256' in payload:
            extra=extra|{'start_request_sha256'}
            _digest(payload['start_request_sha256'])
        _object(payload,{'binding','physical_binding_sha256'}|extra)
        _digest(payload['physical_binding_sha256'])
        binding=_binding(payload['binding'])
        if operation!='start':
            if payload['run_id']!=binding['attempt_id']:_refuse()
            _identifier(payload['run_id'])
        if operation=='start':
            spec=payload['launch_spec']
            fields={f.name for f in dataclasses.fields(OrchestrationLaunchSpec)}
            required={'run_id','job_id','worker_id','workspace_path','run_dir','prompt','result_schema_path',
                      'effective_grant_digest','expected_base_sha','isolation_manifest_sha256'}
            if type(spec) is not dict or not required<=set(spec)<=fields:_refuse()
            if (spec['run_id']!=binding['attempt_id'] or spec['job_id']!=binding['job_id']
                    or spec['effective_grant_digest']!=binding['effective_grant_digest']):_refuse()
            _identifier(spec['worker_id'])
            for name in ('model','worker_user'):
                if name in spec:_identifier(spec[name])
            for name in ('expected_worker_uid','expected_worker_gid'):
                if type(spec.get(name)) is not int or spec[name]<0:_refuse()
            for name in ('timeout_seconds','cancel_grace_seconds'):
                if name in spec and (type(spec[name]) not in (int,float)
                        or not math.isfinite(spec[name]) or spec[name]<0):_refuse()
            if 'authorities' in spec and (type(spec['authorities']) is not list
                    or any(type(v) is not str or not v for v in spec['authorities'])):_refuse()
            _under(spec['workspace_path'],self.config.workspace_root)
            run=_under(spec['run_dir'],self.config.run_root)
            _under(spec['result_schema_path'],run)
            if type(spec['prompt']) is not str or '\x00' in spec['prompt']:_refuse()
            if type(spec['expected_base_sha']) is not str or _COMMIT.fullmatch(spec['expected_base_sha']) is None:_refuse()
            _digest(spec['isolation_manifest_sha256'])
            commands=payload['validation_commands']
            if type(commands) is not list or len(commands)>32:_refuse()
            for argv in commands:self._validation_argv(argv)
        elif operation=='cancel':
            if type(payload['reason']) is not str or not 1<=len(payload['reason'])<=500 or '\x00' in payload['reason']:_refuse()
        elif operation=='validate':
            self._validation_argv(payload['argv'])
            seconds=payload['timeout_seconds']
            if type(seconds) not in (int,float) or not math.isfinite(seconds) or not .1<=seconds<=self.config.request_timeout_seconds:_refuse()
        return binding

    def _validation_argv(self,argv):
        if type(argv) is not list or any(type(v) is not str for v in argv) or tuple(argv) not in self.config.validation_commands:
            _refuse(message='Validation argv is not in the root-installed allowlist')

    def _operation_result(self,operation,result,payload):
        common={'adapter_id','binding','physical_binding_sha256'}
        if result.get('physical_binding_sha256')!=payload['physical_binding_sha256']:
            _refuse('EFFECT_UNKNOWN','Backend route differs from the Runtime-pinned physical binding')
        if operation=='status' and 'start_request_sha256' in payload:
            _same_backend_binding(result,payload['binding'],payload['start_request_sha256'])
            extra={'start_state','request_sha256'}
            if result.get('start_state')=='EXISTS':
                extra=extra|{'start_result'}
                retained=result['start_result']
                _same_backend_binding(retained,payload['binding'],payload['start_request_sha256'])
                _object(retained,common|{'request_sha256','process_ref','launch_attestation'})
                _object(retained['process_ref'],{f.name for f in dataclasses.fields(WorkerProcessRef)})
                att=retained['launch_attestation']
                required={f.name for f in dataclasses.fields(LaunchAttestation)
                          if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING}
                if (type(att) is not dict or not required<=set(att)
                        or att.get('schema_version')!=LAUNCH_ATTESTATION_SCHEMA_VERSION
                        or retained['physical_binding_sha256']!=result['physical_binding_sha256']):
                    _refuse('EFFECT_UNKNOWN','Retained start is not complete original-route evidence')
            elif result.get('start_state')!='UNSTARTED_PROVEN':
                _refuse('EFFECT_UNKNOWN','Original start remains uncertain; no replay')
            _object(result,common|extra)
            return
        key={'status':'run','collect':'collection','cancel':'cancellation','validate':'validation'}[operation]
        _object(result,common|{key})
        receipt=result[key]
        if operation=='status':
            _object(receipt,{'run_id','status','process_ref'})
            if receipt['run_id']!=payload['run_id'] or receipt['status'] not in {s.value for s in WorkerRunStatus}:
                _refuse('EFFECT_UNKNOWN','Status is not a bound proven worker state')
            _object(receipt['process_ref'],{f.name for f in dataclasses.fields(WorkerProcessRef)})
            if receipt['process_ref']['run_id']!=payload['run_id']:
                _refuse('EFFECT_UNKNOWN','Status process belongs to another Attempt')
        elif operation=='cancel':
            _object(receipt,{f.name for f in dataclasses.fields(CancelReceipt)})
            if (receipt['run_id']!=payload['run_id'] or receipt['reason']!=payload['reason']
                    or any(type(receipt[k]) is not bool for k in ('signal_sent','escalated_to_sigkill','already_exited'))
                    or type(receipt['finished_at']) is not str or not receipt['finished_at']):
                _refuse('EFFECT_UNKNOWN','Cancellation is not a complete bound receipt')
        elif operation=='validate':
            _object(receipt,{f.name for f in dataclasses.fields(ValidationReceipt)})
            if (receipt['argv']!=payload['argv'] or type(receipt['timed_out']) is not bool
                    or any(type(receipt[k]) is not int or receipt[k]<0 for k in ('stdout_size','stderr_size'))
                    or (receipt['exit_code'] is not None and type(receipt['exit_code']) is not int)
                    or (receipt['error'] is not None and type(receipt['error']) is not str)):
                _refuse('EFFECT_UNKNOWN','Validation is not a complete bound receipt')
            _digest(receipt['stdout_sha256']);_digest(receipt['stderr_sha256'])
        else:
            _object(receipt,{f.name for f in dataclasses.fields(CollectionReceipt)})
            ref=_object(receipt['process_ref'],{f.name for f in dataclasses.fields(WorkerProcessRef)})
            output=_object(receipt['result'],{f.name for f in dataclasses.fields(WorkerResult)})
            if (ref['run_id']!=payload['run_id'] or output['run_id']!=payload['run_id']
                    or output['job_id']!=payload['binding']['job_id']
                    or output['status'] not in {s.value for s in WorkerRunStatus}
                    or type(output['artifact_manifest']) is not list):
                _refuse('EFFECT_UNKNOWN','Collection is not bound to the original Attempt/Job')
            _identifier(output['worker_id'])
            for artifact in output['artifact_manifest']:
                _object(artifact,{f.name for f in dataclasses.fields(ArtifactReceipt)})
                _digest(artifact['sha256'])
                if type(artifact['size']) is not int or artifact['size']<0:
                    _refuse('BrokerProtocolError','Invalid collection artifact size')
            _digest(receipt['stdout_sha256']);_digest(receipt['stderr_sha256'])
            if receipt['result_sha256'] is not None:_digest(receipt['result_sha256'])

    async def execute(self,request,*,peer):
        self._authorize_peer(peer)
        _object(request,{'schema_version','request_id','operation','payload'})
        if request['schema_version']!=BROKER_REQUEST_SCHEMA_VERSION:_refuse()
        _identifier(request['request_id'])
        operation=request['operation']
        if type(operation) is not str or operation not in _OPERATIONS:_refuse()
        if len(_canonical(request))+1>self.config.max_request_bytes:_refuse(message='Request ceiling exceeded')
        # Canonical JSON copy prevents trusted backend mutation from rewriting the
        # caller's binding/hash while a response is being checked.
        payload=_strict_json(_canonical(request['payload']))
        binding=self._payload(operation,payload)
        if operation=='start':
            digest=start_request_sha256(payload)
            query={'run_id':binding['attempt_id'],'binding':dict(binding),'start_request_sha256':digest,
                   'physical_binding_sha256':payload['physical_binding_sha256']}
            try:
                status=_strict_json(_canonical(await self.backend.execute('status',_strict_json(_canonical(query)))))
                _same_backend_binding(status,binding,digest)
                self._operation_result('status',status,query)
                if status.get('start_state')=='EXISTS':
                    result=_complete_start_result(status.get('start_result'),binding,digest,payload['launch_spec'])
                    if result['physical_binding_sha256']!=status['physical_binding_sha256']:
                        _refuse('EFFECT_UNKNOWN','Retained receipt route differs from original observation')
                elif status.get('start_state')=='UNSTARTED_PROVEN':
                    forwarded={**payload,'start_request_sha256':digest}
                    result=_strict_json(_canonical(await self.backend.execute('start',_strict_json(_canonical(forwarded)))))
                    result=_complete_start_result(result,binding,digest,payload['launch_spec'])
                    if result['physical_binding_sha256']!=status['physical_binding_sha256']:
                        _refuse('EFFECT_UNKNOWN','Physical route changed after original first-use observation')
                else:
                    _refuse('EFFECT_UNKNOWN','Existing receipt does not prove original Attempt first use')
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                raise BridgeProtocolError('EFFECT_UNKNOWN','Original Attempt requires status-only reconciliation') from exc
        else:
            try:
                if operation in {'cancel','validate'}:
                    query={key:payload[key] for key in ('binding','run_id','physical_binding_sha256')}
                    observed=_strict_json(_canonical(await self.backend.execute('status',_strict_json(_canonical(query)))))
                    _same_backend_binding(observed,binding)
                    self._operation_result('status',observed,query)
                result=_strict_json(_canonical(await self.backend.execute(operation,_strict_json(_canonical(payload)))))
                _same_backend_binding(result,binding)
                self._operation_result(operation,result,payload)
            except asyncio.CancelledError:
                raise
            except BridgeProtocolError as exc:
                raise BridgeProtocolError(exc.code,'Backend refused the bound operation; no automatic retry') from exc
            except Exception as exc:
                code='EFFECT_UNKNOWN' if operation in {'cancel','validate'} else 'BackendUnavailableError'
                raise BridgeProtocolError(code,'Backend operation unavailable; no automatic retry') from exc
        response=dict(schema_version=BROKER_RESPONSE_SCHEMA_VERSION,request_id=request['request_id'],
                      operation=operation,ok=True,result=result)
        if len(_canonical(response))+1>self.config.max_response_bytes:
            _refuse('EFFECT_UNKNOWN' if operation in {'start','cancel','validate'} else 'BrokerProtocolError',
                    'Backend response ceiling exceeded; reconcile the original Attempt')
        return response

    async def handle_connection(self,reader,writer):
        request_id=operation='invalid'
        effect_possible=False
        response=None
        try:
            sock=writer.get_extra_info('socket')
            if sock is None:_refuse('PeerAuthorizationError','Missing Unix peer socket')
            try:
                peer=self.peer_resolver(sock)
            except (PeerAuthorizationError,OSError) as exc:
                raise BridgeProtocolError('PeerAuthorizationError','Unix peer identity unavailable') from exc
            self._authorize_peer(peer)  # Authenticate before reading payload bytes.
            raw=await asyncio.wait_for(reader.readline(),timeout=self.config.request_timeout_seconds)
            request=decode_request(raw,max_bytes=self.config.max_request_bytes)
            if type(request.get('request_id')) is str and _ID.fullmatch(request['request_id']):
                request_id=request['request_id']
            if type(request.get('operation')) is str and request['operation'] in _OPERATIONS:operation=request['operation']
            effect_possible=operation in {'start','cancel','validate'}
            response=await asyncio.wait_for(self.execute(request,peer=peer),timeout=self.config.request_timeout_seconds)
        except asyncio.CancelledError:
            raise
        except BridgeProtocolError as exc:
            response=self._error(request_id,operation,exc.code,str(exc))
        except (ValueError,asyncio.LimitOverrunError):
            response=self._error(request_id,operation,'BrokerProtocolError','Request framing ceiling exceeded')
        except Exception:
            response=self._error(request_id,operation,'EFFECT_UNKNOWN' if effect_possible else 'BackendUnavailableError',
                                 'Operation interrupted; reconcile the original Attempt without replay')
        finally:
            try:
                if response is not None:
                    writer.write(_canonical(response)+b'\n')
                    await writer.drain()
            finally:
                writer.close()
                try:await writer.wait_closed()
                except (BrokenPipeError,ConnectionResetError):pass

    @staticmethod
    def _error(request_id,operation,code,message):
        return dict(schema_version=BROKER_RESPONSE_SCHEMA_VERSION,request_id=request_id,operation=operation,
                    ok=False,error={'code':code,'message':message[:500]})
