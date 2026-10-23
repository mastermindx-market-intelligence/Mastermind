"""Canonical paid execution owner in the incumbent controller-side GLM shim.

The production constructor receives a root-qualified startup, the actual shim
context and gateway. Only the existing kernel-authenticated Control command
can start. Exactly one incumbent remote_sub controller reserves/acquires; its
private post-acquire rendezvous never transfers Control authority to Bash or
Ubuntu. Retained records use that original controller's log, not a new store.
"""
from __future__ import annotations

import asyncio
import dataclasses
import fcntl
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import pwd
import secrets
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time

from control_plane.fabric_control_start import ControlStartAuthority
from control_plane.paid_model_execution_contract import (
    ADAPTER_ID, ATTESTATION_SCHEMA, PROFILE_ID, EXECUTION_SURFACE,
    canonical, compile_request, descriptor, digest,
)

_SOURCE_QUALIFIED = object()
_JOURNAL = b'CANONICAL_PAID_OWNER '
_MAX_LOG = 8 * 1024 * 1024
_MAX_FRAME = 65536
_MAX_JOURNAL_RECORD = 4 * 1024 * 1024


class PaidOwnerRefused(ValueError):
    pass


def _refuse():
    raise PaidOwnerRefused('canonical_paid_original_owner_unavailable')


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid,
            info.st_mode, info.st_nlink, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns)


def _private_read(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1
                or not 0 < before.st_size <= limit):
            _refuse()
        raw = bytearray()
        while len(raw) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        if (_identity(before) != _identity(os.fstat(fd))
                or _identity(before) != _identity(os.lstat(path))
                or len(raw) != before.st_size):
            _refuse()
        return bytes(raw)
    finally:
        os.close(fd)


def _root_source(path):
    """Existing protected path observer; no user/source lookup fallback."""
    from control_plane.codex_provider_realm import _native_open
    with _native_open(Path(path)) as (fd, info):
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 4 * 1024 * 1024:
            _refuse()
        raw = bytearray()
        while len(raw) <= info.st_size:
            chunk = os.read(fd, min(65536, info.st_size + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        if len(raw) != info.st_size:
            _refuse()
        return bytes(raw)


@dataclasses.dataclass(frozen=True)
class _QualifiedPaidStartup:
    release_root: Path
    native_ext: Path
    owner_ext: Path
    log_dir: Path
    bridge_uid: int
    sources: dict
    installed: dict | None = None
    config: object = None
    _qualified: object = dataclasses.field(default=None, repr=False)


def qualify_paid_startup(release_root, *, config):
    """Only root-installed, fixed source composition, not a caller boolean.

    The full root release manifest must name the actual controller/support and
    external shim overlay bytes. The three external preimages remain immutable
    audit inputs; source merge does not select or install this composition.
    """
    from control_plane.executive_fabric_bridge_broker import _TRUSTED_CONFIG
    root = Path(release_root)
    if (config._trust is not _TRUSTED_CONFIG or config.adapter_id != ADAPTER_ID
            or os.geteuid() != config.bridge_uid or config.bridge_uid != 501
            or root != Path(__file__).resolve().parents[1]):
        _refuse()
    # This fixed incumbent owner namespace is the current M2 adapter package.
    # It is not a CLI/config-selected credential or broker directory.
    owner = Path('/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext')
    native = root / 'ops/native_fabric/quota_continuity/rollout/native-code-stage/ext'
    required = ('remote_sub.sh', 'paid_controller_spawn.py', 'paid_controller_channel.py',
                'paid_model_owner.py', 'paid_glm_model_client.py', 'linux_process_identity.py',
                'paid_incumbent_state.py','host_pull.sh','host_pull_backend.py',
                'host_pull_probe.template','paid_host_qualification.py')
    manifest = json.loads(_root_source(root / '.executive-release-manifest.json'))
    if (type(manifest) is not dict
            or set(manifest) != {'schema_version', 'commit_sha', 'tree_sha', 'entries'}
            or manifest['schema_version'] != 'mastermind.executive_release_manifest/v1'
            or manifest['commit_sha'] != root.name or type(manifest['entries']) is not list):
        _refuse()
    files = {}
    for entry in manifest['entries']:
        if type(entry) is not dict or type(entry.get('path')) is not str or entry['path'] in files:
            _refuse()
        files[entry['path']] = entry
    sources = {}
    paths = [native / name for name in required]
    paths += [root / 'scripts/executive_paid_fabric_shim.py']
    paths += [root / 'ops/native_fabric/paid_canonical_glm/candidate' / name
              for name in ('glm_shim.py', 'glm_lease_gateway.py', 'glm_lease_capability.py')]
    for path in paths:
        raw = _root_source(path)
        sha = hashlib.sha256(raw).hexdigest()
        expected = files.get(str(path.relative_to(root)))
        info = path.lstat()
        if (type(expected) is not dict or expected.get('type') != 'file'
                or expected.get('sha256') != sha or expected.get('size') != len(raw)
                or expected.get('uid') != 0 or expected.get('gid') != 0
                or expected.get('mode') != stat.S_IMODE(info.st_mode)):
            _refuse()
        sources[str(path.relative_to(root))] = sha
    log_dir = owner / 'state/remote_sub'
    for path in (owner, owner / 'state', log_dir):
        info = path.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != config.bridge_uid
                or info.st_mode & (0o077 if path == log_dir else 0o022)):
            _refuse()
    sources['_manifest_sha256']=hashlib.sha256(_root_source(root/'.executive-release-manifest.json')).hexdigest()
    from control_plane.executive_paid_fabric_composition import verify_installed_source
    installed=verify_installed_source(config,Path('/Library/Application Support/MastermindExecutive/config/fabric-glm-paid-01'),root)
    return _QualifiedPaidStartup(root, native, owner, log_dir,
                                 config.bridge_uid, sources, installed, config, _SOURCE_QUALIFIED)


@dataclasses.dataclass
class _Original:
    payload: dict
    authority: ControlStartAuthority
    proc: subprocess.Popen
    nonce: str
    packet: Path
    log_path: Path
    output_path: Path
    launch_ready: threading.Event = dataclasses.field(default_factory=threading.Event)
    terminal_ready: threading.Event = dataclasses.field(default_factory=threading.Event)
    lock: threading.RLock = dataclasses.field(default_factory=threading.RLock)
    image: dict | None = None
    lease: dict | None = None
    capsule: dict | None = None
    intent: object = None
    issuance_attempted: bool = False
    log_fd: int | None = None
    start_result: dict | None = None
    launch_frame: dict | None = None
    terminal_frame: dict | None = None
    failed: bool = False
    complete: bool = False


class CanonicalPaidBackend:
    """One concrete owner, never a structural admission projection."""
    def __init__(self, startup, incumbent):
        if type(startup) is not _QualifiedPaidStartup or startup._qualified is not _SOURCE_QUALIFIED:
            _refuse()
        shim=sys.modules.get('glm_shim')
        if (shim is None or Path(shim.__file__).resolve()!=startup.release_root/'ops/native_fabric/paid_canonical_glm/candidate/glm_shim.py'):
            _refuse()
        context,gateway=shim.require_canonical_incumbent(incumbent)
        self._incumbent=incumbent
        self._shim=shim
        if (type(startup) is not _QualifiedPaidStartup
                or startup._qualified is not _SOURCE_QUALIFIED
                or os.geteuid() != startup.bridge_uid
                or gateway._db_path != startup.owner_ext / 'broker/leases.sqlite'
                or getattr(gateway, '_canonical_owner', None) is not None
                or context.account_table is None
                or frozenset(context.account_table.names()) != gateway._accounts):
            _refuse()
        self._startup, self._gateway, self._context = startup, gateway, context
        self._operations = {}
        self._lock = threading.RLock()
        self._http_active = 0
        self._metadata_active = 0
        self._stop_fence = None
        gateway._canonical_owner = self
        # Fixed qualified source modules, loaded by the sole root entrypoint.
        channel = sys.modules.get('paid_controller_channel')
        if channel is None or Path(channel.__file__).resolve() != startup.native_ext / 'paid_controller_channel.py':
            gateway._canonical_owner = None
            _refuse()
        self._channel = channel

    def require_gateway(self, gateway):
        context,current=self._shim.require_canonical_incumbent(self._incumbent)
        if context is not self._context or current is not self._gateway:_refuse()
        if (gateway is not self._gateway or gateway._canonical_owner is not self
                or self._startup._qualified is not _SOURCE_QUALIFIED
                or os.geteuid() != self._startup.bridge_uid):
            _refuse()

    def enter_http_request(self):
        self.require_gateway(self._gateway)
        with self._lock:
            if self._stop_fence is not None:return False
            self._http_active+=1
            return True

    def leave_http_request(self):
        with self._lock:
            if self._http_active<=0:_refuse()
            self._http_active-=1

    def _idle_for_stop(self):
        if self._http_active or self._metadata_active:_refuse()
        if any(not o.terminal_ready.is_set() or o.proc.poll() is None for o in self._operations.values()):_refuse()
        connection=self._gateway._connection()
        try:
            count=connection.execute("SELECT COUNT(*) FROM leases WHERE pool='glm' AND state IN ('held','rented')").fetchone()[0]
            if type(count) is not int or count!=0:_refuse()
        finally:connection.close()
        with self._context.account_table._lock:
            if any(s.get('canonical_status_state')=='PENDING' for s in self._context.account_table._state.values()):_refuse()

    def service_quiesce(self,authority,*,stop_intent,phase,fence_id=None):
        from control_plane.paid_stop_authority import require_stop_authority
        origin=require_stop_authority(authority,stop_intent=stop_intent).to_dict()
        intent=origin['stop_intent']
        import re
        if (type(intent) is not dict or set(intent)!={'request_id','request_sha256','release_sha','expected_definition_sha256'}
                or type(intent['request_id']) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{2,63}',intent['request_id']) is None
                or any(type(intent[k]) is not str or re.fullmatch(r'[0-9a-f]{64}',intent[k]) is None
                    for k in ('request_sha256','expected_definition_sha256'))
                or intent['release_sha']!=self._startup.release_root.name
                or phase not in {'acquire','revalidate','release'}):_refuse()
        with self._lock:
            readiness=self.service_readiness()
            if digest(readiness['definition_hashes'])!=intent['expected_definition_sha256']:_refuse()
            if phase=='acquire':
                if self._stop_fence is not None:_refuse()
                self._idle_for_stop()
                self._stop_fence=dict(schema_version='mastermind.canonical_paid_quiescence/v1',
                    stop_intent=json.loads(canonical(intent)),fence_id=secrets.token_hex(32),
                    process=readiness['process'],quiesced=True,
                    broker_process=origin['broker_process'],receipt_sha256=origin['receipt_sha256'])
            else:
                held=self._stop_fence
                if (held is None or held['stop_intent']!=intent or held['fence_id']!=fence_id
                        or held['process']!=readiness['process']
                        or held['broker_process']!=origin['broker_process']
                        or held['receipt_sha256']!=origin['receipt_sha256']):_refuse()
                if phase=='revalidate':self._idle_for_stop()
            if require_stop_authority(authority,stop_intent=intent).to_dict()!=origin:_refuse()
            result=json.loads(canonical(self._stop_fence))
            if phase=='release':self._stop_fence=None
            return result

    def bind_activated_socket(self,activated):
        # Sole root entrypoint supplies the actual already-qualified launchd
        # socket object, never a serialized fd/receipt or alternate listener.
        if getattr(self,'_activated_socket',None) is not None:_refuse()
        self.require_gateway(self._gateway)
        config=self._startup.config
        if (type(activated) is not socket.socket or activated.family!=socket.AF_UNIX
                or activated.getsockname()!=str(config.socket_path)
                or activated.getsockopt(socket.SOL_SOCKET,socket.SO_ACCEPTCONN)!=1):_refuse()
        info=config.socket_path.lstat()
        if (not stat.S_ISSOCK(info.st_mode) or info.st_uid!=0 or info.st_gid!=450
                or stat.S_IMODE(info.st_mode)!=0o660 or info.st_nlink!=1):_refuse()
        self._activated_socket=activated
        self._activated_identity=(os.fstat(activated.fileno()).st_dev,os.fstat(activated.fileno()).st_ino)
        self._socket_identity=(info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode)

    def service_readiness(self):
        self.require_gateway(self._gateway)
        activated=getattr(self,'_activated_socket',None)
        if type(activated) is not socket.socket:_refuse()
        fd=os.fstat(activated.fileno())
        config=self._startup.config
        info=config.socket_path.lstat()
        if (activated.getsockname()!=str(config.socket_path)
                or activated.getsockopt(socket.SOL_SOCKET,socket.SO_ACCEPTCONN)!=1
                or (fd.st_dev,fd.st_ino)!=self._activated_identity
                or (info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode)!=self._socket_identity):_refuse()
        installed=self._installed_source()
        from control_plane.darwin_process_image import inspect_owned_darwin_image
        image=inspect_owned_darwin_image(os.getpid())
        if (image['effective_uid']!=self._startup.bridge_uid or image['real_uid']!=self._startup.bridge_uid
                or image['effective_gid']!=os.getegid() or image['real_gid']!=os.getgid()):_refuse()
        process=dict(pid=os.getpid(),effective_uid=image['effective_uid'],effective_gid=image['effective_gid'],
            real_uid=image['real_uid'],real_gid=image['real_gid'],
            start_identity=image['start_identity'],boot_id=image['boot_id'])
        self.require_gateway(self._gateway)
        return dict(schema_version='mastermind.canonical_paid_service_readiness/v1',adapter_id=ADAPTER_ID,
            profile_id=PROFILE_ID,execution_surface=EXECUTION_SURFACE,release_sha=self._startup.release_root.name,
            manifest_sha256=self._startup.sources['_manifest_sha256'],definition_hashes=installed['hashes'],
            process=process,socket=dict(path=str(config.socket_path),device=info.st_dev,inode=info.st_ino,
                uid=info.st_uid,gid=info.st_gid,mode=info.st_mode),adopted=dict(device=fd.st_dev,inode=fd.st_ino),
            incumbent_context='QUALIFIED_SAME_PROCESS')

    def _occupied(self, run_id):
        # The already-required sealed input precedes Popen. Its residue closes
        # the pre-log crash window as UNKNOWN; absence of a Bash log alone is
        # never proof that the original owner did not spawn. No new store.
        return (run_id in self._operations
            or (self._startup.log_dir/(run_id+'.log')).exists()
            or any(self._startup.log_dir.glob('.'+run_id+'.canonical-input.*')))

    def _original(self, run_id):
        with self._lock:
            value = self._operations.get(run_id)
        if type(value) is not _Original:
            _refuse()
        return value

    def _kernel_controller(self, operation):
        from control_plane.darwin_process_image import inspect_owned_darwin_image
        if operation.proc.poll() is not None:
            _refuse()
        image = inspect_owned_darwin_image(operation.proc.pid)
        if (image['parent_pid'] != os.getpid()
                or image['effective_uid'] != self._startup.bridge_uid
                or image['real_uid'] != self._startup.bridge_uid
                or image['executable_path'] != '/bin/bash'):
            _refuse()
        if operation.image is not None and image != operation.image:
            _refuse()
        return image

    def _installed_source(self):
        from control_plane.executive_paid_fabric_composition import load_paid_config,verify_installed_source
        directory=Path('/Library/Application Support/MastermindExecutive/config/fabric-glm-paid-01')
        config=load_paid_config(directory/'bridge.json')
        if config!=self._startup.config or config.source_sha256!=self._startup.config.source_sha256:_refuse()
        current=verify_installed_source(config,directory,self._startup.release_root)
        if current!=self._startup.installed:_refuse()
        return current

    def require_capacity_scope(self,worker_id,quota_class):
        # SOURCE-only owner join exists before Job/Attempt. It grants neither
        # launch nor availability and cannot fabricate a LaunchSpec to bootstrap.
        self.require_gateway(self._gateway)
        current=self._installed_source()
        rows=[row for row in current['bindings']
            if row['physical_binding']['worker_id']==worker_id and row['quota_class']==quota_class]
        if len(rows)!=1:_refuse()
        row=rows[0];registration=current['profile']['registration']
        if registration['worker_id']!=worker_id or registration['quota_class']!=quota_class:_refuse()
        self._require_source_data(row['physical_binding'],row['source_config'])
        return (json.loads(canonical(row['physical_binding'])),
                json.loads(canonical(row['source_config'])),registration['account_label'])

    def _require_source_data(self,physical,source):
        from control_plane.paid_fabric_wire import require_paid_source
        physical=require_paid_source(physical,source)
        q=physical['qualification']
        if q['qualifier_source_manifest_sha256']!=self._startup.sources['_manifest_sha256']:_refuse()
        for name,sha in q['qualifier_sources_sha256'].items():
            path=str((self._startup.native_ext/name).relative_to(self._startup.release_root))
            if self._startup.sources.get(path)!=sha:_refuse()
        import paid_host_qualification as qualifier
        if Path(qualifier.__file__).resolve()!=self._startup.native_ext/'paid_host_qualification.py':_refuse()
        raw,_=qualifier._read_owned(self._startup.owner_ext/'hosts.json',owners={0,501})
        if hashlib.sha256(raw).hexdigest()!=q['registry_sha256']:_refuse()
        entry=json.loads(raw).get(q['registry_key'])
        if type(entry) is not dict or entry.get('ssh_alias')!=q['transport_alias']:_refuse()

    def _require_account_status(self,account):
        # No select()/refresh()/provider IO. A generic or partial/manual table
        # reading cannot become canonical admission through a recent timestamp.
        self.require_gateway(self._gateway)
        now=self._gateway._clock()
        with self._context.account_table._lock:
            state=dict(self._context.account_table._state.get(account,{}))
        at=state.get('observed_at')
        hold=state.get('exhausted_until_ts')
        pair=[state.get('last_pct_5h'),state.get('last_pct_week')]
        if (type(now) not in (int,float) or not math.isfinite(now)
                or state.get('canonical_status_state')!='OBSERVED'
                or type(at) not in (int,float) or not math.isfinite(at)
                or state.get('canonical_status_observed_at')!=at
                or not 0<=now-at<300
                or type(hold) not in (int,float) or not math.isfinite(hold) or hold>now
                or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<100 for v in pair)):
            _refuse()
        self.require_gateway(self._gateway)

    def _require_source_context(self,payload):
        from control_plane.paid_fabric_wire import require_paid_physical
        physical=require_paid_physical(payload)
        expected,source,account=self.require_capacity_scope(physical['worker_id'],payload['paid_quota_class'])
        if (physical!=expected or source!=payload['paid_source_config']
                or account!=payload['paid_account']):_refuse()
        self._require_account_status(account)

    def require_original_controller(self, payload, lease, *, expected=None):
        self.require_gateway(self._gateway)
        self._require_source_context(payload)
        operation = self._original(payload['binding']['attempt_id'])
        operation.authority.require(payload)
        if operation.payload != payload or operation.failed or lease.get('pid') != operation.proc.pid:
            _refuse()
        if operation.log_fd is None:_refuse()
        pinned=os.fstat(operation.log_fd);visible=operation.log_path.lstat()
        if (_identity(pinned)[:6]!=_identity(visible)[:6]
                or pinned.st_nlink!=1 or stat.S_IMODE(pinned.st_mode)!=0o600):_refuse()
        image = self._kernel_controller(operation)
        identity = dict(pid=operation.proc.pid,
                        start_identity=image['process_start_identity'], boot_id=image['boot_id'])
        if expected is not None and expected != identity:
            _refuse()
        if operation.image is None:
            operation.image = image
        return identity

    def begin_capsule_issue(self, payload, authority, lease):
        operation = self._original(payload['binding']['attempt_id'])
        self.require_original_controller(payload, lease)
        with operation.lock:
            if authority is not operation.authority or operation.issuance_attempted:
                _refuse()
            operation.issuance_attempted = True

    def _journal(self, operation, kind, value):
        material=dict(kind=kind,value=value)
        tag=hmac.new(self._gateway._signing_key,b'mastermind.paid.owner-journal/v1\0'+canonical(material),
                     hashlib.sha256).hexdigest()
        raw = _JOURNAL + canonical(dict(material,tag=tag)) + b'\n'
        if len(raw) > _MAX_JOURNAL_RECORD or operation.log_fd is None:
            _refuse()
        with operation.lock:
            fd = operation.log_fd
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                if os.fstat(fd).st_size + len(raw) > _MAX_LOG:
                    _refuse()
                if os.write(fd, raw) != len(raw):
                    _refuse()
                os.fsync(fd)
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)

    def _bind_log(self, operation):
        fd = os.open(operation.log_path, os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                    or (info.st_dev, info.st_ino) !=
                    (operation.log_path.lstat().st_dev, operation.log_path.lstat().st_ino)):
                _refuse()
            prefix = ('CANONICAL_PAID_REQUIRED schema=1 payload_sha256='
                      + operation.authority.payload_sha256 + '\n').encode()
            if os.pread(fd, len(prefix), 0) != prefix:
                _refuse()
            operation.log_fd = fd
            operation.intent = self._channel.ProviderIntent(fd,
                payload_sha256=operation.authority.payload_sha256)
        except BaseException:
            os.close(fd)
            raise

    def _post_acquire(self, operation, sock):
        try:
            sock.settimeout(30)
            lease_id = self._channel.receive_lease(sock,
                run_id=operation.payload['binding']['attempt_id'], nonce=operation.nonce)
            self._bind_log(operation)  # actual incumbent O_EXCL reservation
            with self._gateway._connection() as connection:
                lease = self._gateway._lease_lookup(connection, lease_id)
            self.require_original_controller(operation.payload, lease)
            operation.lease = dict(lease)
            ttl = min(int(operation.authority.expires_at - time.time()) - 1,
                      int(operation.payload['launch_spec']['timeout_seconds']))
            if ttl < 1:
                _refuse()
            capsule = self._gateway._issue_canonical(operation.payload,
                authority=operation.authority, lease_id=lease_id, ttl=ttl,
                request_body=json.loads(compile_request(operation.payload)))
            operation.capsule = capsule
            self._channel.answer_lease(sock, run_id=operation.payload['binding']['attempt_id'],
                lease_id=lease_id, nonce=operation.nonce, capsule=capsule)
        except BaseException:
            operation.failed = True
            operation.launch_ready.set()
        finally:
            sock.close()

    def require_canonical_request(self, claims):
        operation = self._original(claims['attempt_id'])
        operation.authority.require(operation.payload)
        if (operation.failed or operation.lease is None or operation.capsule is None
                or claims['payload_sha256'] != operation.authority.payload_sha256
                or claims['lease_id'] != operation.lease['id']
                or claims['account'] != operation.lease['account']):
            _refuse()
        self.require_original_controller(operation.payload, operation.lease)
        # One HTTP request may wait for the original authenticated transport's
        # launch proof. This is not a retry, queue or model-provided proof.
        remaining = min(90.0, operation.authority.expires_at - time.time())
        if remaining <= 0 or not operation.launch_ready.wait(remaining):
            _refuse()
        if operation.failed or operation.start_result is None:
            _refuse()
        operation.authority.require(operation.payload)
        self.require_original_controller(operation.payload, operation.lease)

    def consume_provider_intent(self, claims):
        self.require_canonical_request(claims)
        operation = self._original(claims['attempt_id'])
        if operation.intent is None:
            _refuse()
        # Failure/partial intent never becomes permission to call again.
        operation.intent.consume()

    def _accept_launch(self, operation, frame):
        from control_plane.paid_fabric_wire import paid_start_from_owned_launch
        if operation.launch_frame is not None:
            _refuse()
        self.require_original_controller(operation.payload, operation.lease)
        support = json.loads(_private_read(
            self._startup.log_dir/(operation.payload['binding']['attempt_id']+'.support.json'), 65536))
        if type(support) is not dict:
            _refuse()
        for name, sha in support.items():
            if Path(name).name != name:
                _refuse()
            if name == 'pools.yaml':
                import paid_incumbent_state
                if (Path(paid_incumbent_state.__file__).resolve()
                        !=self._startup.native_ext/'paid_incumbent_state.py'):_refuse()
                raw=paid_incumbent_state.read_policy()
            else:
                raw=_root_source(self._startup.native_ext/name)
            if hashlib.sha256(raw).hexdigest() != sha:
                _refuse()
        support_sha = hashlib.sha256(json.dumps(
            {'schema':'remote-support-code.v1','files':support},
            sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if frame.get('source_manifest_sha256') != support_sha:
            _refuse()
        result = paid_start_from_owned_launch(operation.payload, frame,
            capsule=operation.capsule, lease=operation.lease,
            controller=operation.image, authority=operation.authority)
        # fsync original START before marking the request eligible for provider.
        self._journal(operation, 'start', result)
        operation.launch_frame, operation.start_result = frame, result
        operation.launch_ready.set()

    def _drain(self, operation, stream):
        try:
            total = 0
            while True:
                line = stream.readline(_MAX_FRAME + 1)
                if not line:
                    break
                total += len(line)
                if len(line) > _MAX_FRAME or total > 4 * 1024 * 1024:
                    _refuse()
                if line.startswith(b'CANONICAL_PAID_LAUNCH '):
                    frame = json.loads(line[len(b'CANONICAL_PAID_LAUNCH '):])
                    self._accept_launch(operation, frame)
                elif line.startswith(b'CANONICAL_PAID_TERMINAL '):
                    if operation.terminal_frame is not None:
                        _refuse()
                    frame = json.loads(line[len(b'CANONICAL_PAID_TERMINAL '):])
                    from control_plane.paid_fabric_wire import validate_owned_terminal
                    validate_owned_terminal(frame, operation.launch_frame)
                    self._journal(operation, 'terminal', frame)
                    operation.terminal_frame = frame
            rc = operation.proc.wait()
            if rc != 0 or operation.terminal_frame is None:
                _refuse()
            raw = _private_read(operation.output_path, 2 * 1024 * 1024)
            from control_plane.paid_fabric_wire import paid_collection_from_owned_terminal
            collection = paid_collection_from_owned_terminal(operation.payload,
                operation.start_result, operation.terminal_frame, raw)
            self._journal(operation, 'collection', collection)
            self._journal(operation, 'observation', dict(owned_launch=operation.launch_frame,
                owned_terminal=operation.terminal_frame,
                capture=dict(schema_version='mastermind.paid_model_capture_evidence/v1',
                    stdout_utf8=raw.decode('utf-8'),stdout_sha256=hashlib.sha256(raw).hexdigest(),
                    stdout_bytes=len(raw),stderr_sha256=hashlib.sha256(b'').hexdigest(),stderr_bytes=0)))
            operation.complete = True
        except BaseException:
            # The same controller remains owner; no kill, release or replay.
            operation.failed = True
        finally:
            stream.close()
            operation.launch_ready.set()
            operation.terminal_ready.set()
            # Retain original request/result/custody on unknown effects.

    async def start_owned(self, payload, *, authority):
        self.require_gateway(self._gateway)
        if type(authority) is not ControlStartAuthority:
            _refuse()
        authority.require(payload)
        body = compile_request(payload)
        self._require_source_context(payload)
        from control_plane.paid_fabric_wire import require_paid_physical
        require_paid_physical(payload)
        run_id = payload['binding']['attempt_id']
        with self._lock:
            if self._stop_fence is not None:_refuse()
            if self._occupied(run_id):
                _refuse()  # original record is never reconstructed into START
            fd, name = tempfile.mkstemp(prefix='.' + run_id + '.canonical-input.',
                                        dir=self._startup.log_dir)
            try:
                if os.write(fd, body) != len(body):
                    _refuse()
                os.fsync(fd)
            finally:
                os.close(fd)
            owner_sock, child_sock = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
            os.set_inheritable(owner_sock.fileno(), False)
            nonce = secrets.token_hex(32)
            host=payload['paid_physical_binding']['qualification']['registry_key']
            model=payload['paid_route']['model']
            output = self._startup.owner_ext / 'lanes' / (run_id + '.remote.stdout')
            env = dict(PATH='/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin',
                HOME=pwd.getpwuid(self._startup.bridge_uid).pw_dir,
                LANG='en_US.UTF-8', PYTHONDONTWRITEBYTECODE='1',
                POOL_ORCHESTRATOR_ID=payload['binding']['root_id'],
                POOL_PARENT_RUN_ID=payload['paid_route']['parent_job_id'] or payload['binding']['root_id'],
                REMOTE_SUB_LOG_DIR=str(self._startup.log_dir),
                FABRIC_CANONICAL_PAID_STATE_EXT=str(self._startup.owner_ext),
                POOL_BROKER_DB=str(self._startup.owner_ext/'broker/leases.sqlite'),
                POOL_BROKER_LOCK=str(self._startup.owner_ext/'broker/leases.lock'),
                POOL_ACCOUNTS_YAML=str(self._startup.owner_ext.parent/'orch/fabric/accounts.yaml'),
                POOL_STATUS_JSON=str(self._startup.owner_ext.parent/'orch/fabric/status.json'),
                POOL_LEDGER_PATH=str(self._startup.owner_ext.parent/'orch/fabric/ledger.jsonl'),
                POOL_POLICY_YAML=str(self._startup.owner_ext.parent/'orch/fabric/pools.yaml'),
                POOL_TASK_CLASS='research', POOL_TASK_COMPLEXITY='C2_COMPLEX_BOUNDED',
                REMOTE_SUB_PYTHON=sys.executable,
                FABRIC_CANONICAL_PAID_MODE='sealed-model-only-v1',
                FABRIC_CANONICAL_PAID_NONCE=nonce,
                FABRIC_CANONICAL_PAID_PAYLOAD_SHA256=authority.payload_sha256,
                FABRIC_CANONICAL_PAID_HOST=host)
            command = [sys.executable, '-I', '-S', '-B',
                str(self._startup.native_ext / 'paid_controller_spawn.py'),
                str(child_sock.fileno()), str(self._startup.native_ext / 'remote_sub.sh'),
                host, 'glm', name, '~', model, '--run-id', run_id, '--out', str(output)]
            authority.require(payload)
            try:
                proc = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    close_fds=True, pass_fds=(child_sock.fileno(),), env=env)
            except BaseException:
                owner_sock.close()
                child_sock.close()
                # A failed process constructor is not proof of no effect.
                raise
            child_sock.close()
            operation = _Original(json.loads(canonical(payload)), authority, proc, nonce,
                Path(name), self._startup.log_dir / (run_id + '.log'), output)
            self._operations[run_id] = operation
            threading.Thread(target=self._post_acquire, args=(operation, owner_sock),
                             daemon=True).start()
            threading.Thread(target=self._drain, args=(operation, proc.stdout),
                             daemon=True).start()
        # Only actual remote launch identity, retained by this owner, can make
        # the original canonical Attempt RUNNING. No queued receipt suffices.
        await asyncio.to_thread(operation.launch_ready.wait,
            max(0, min(float(payload['launch_spec']['timeout_seconds']),
                       authority.expires_at - time.time())))
        if operation.failed or operation.start_result is None:
            _refuse()
        return json.loads(canonical(operation.start_result))

    def _records(self, payload):
        path = self._startup.log_dir / (payload['binding']['attempt_id'] + '.log')
        if not path.exists():
            return []
        raw = _private_read(path, _MAX_LOG)
        records = []
        for line in raw.splitlines():
            if line.startswith(_JOURNAL):
                value = json.loads(line[len(_JOURNAL):])
                if type(value) is not dict or set(value) != {'kind', 'value', 'tag'}:
                    _refuse()
                tag=value.pop('tag')
                expected=hmac.new(self._gateway._signing_key,
                    b'mastermind.paid.owner-journal/v1\0'+canonical(value),hashlib.sha256).hexdigest()
                if type(tag) is not str or not hmac.compare_digest(tag,expected):_refuse()
                records.append(value)
        return records

    def _quota_bootstrap_owned(self,operation_id,scope,*,allow_start):
        """Explicit status IO retained in the incumbent original-owner log.

        The fixed account/route log survives process loss. An incomplete intent,
        refused/unknown prior read, malformed bytes or a lost issuer key never
        authorizes another GET. Same-ID terminal reads only return retained DATA.
        """
        import re
        if type(operation_id) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',operation_id) is None:
            _refuse()
        stable={key:scope[key] for key in ('worker_id','account_label','provider','transport_host','model')}
        path=self._startup.log_dir/('paid-quota-'+digest(stable)+'.log')
        if allow_start:
            try:fd=os.open(path,os.O_RDWR|os.O_APPEND|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            except FileExistsError:fd=os.open(path,os.O_RDWR|os.O_APPEND|os.O_NOFOLLOW)
        else:
            # Read-only same-operation reconciliation never creates a logfile
            # or turns an absent receipt into permission for provider status IO.
            fd=os.open(path,os.O_RDWR|os.O_APPEND|os.O_NOFOLLOW)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX)
            info=os.fstat(fd)
            visible=os.lstat(path)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid()
                    or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1
                    or (info.st_dev,info.st_ino)!=(visible.st_dev,visible.st_ino)
                    or info.st_size>_MAX_LOG):_refuse()
            records=[]
            if info.st_size:
                raw=_private_read(path,_MAX_LOG)
                for line in raw.splitlines():
                    if not line.startswith(_JOURNAL):_refuse()
                    record=json.loads(line[len(_JOURNAL):])
                    if type(record) is not dict or set(record)!={'kind','value','tag'}:_refuse()
                    tag=record.pop('tag')
                    expected=hmac.new(self._gateway._signing_key,
                        b'mastermind.paid.owner-journal/v1\0'+canonical(record),hashlib.sha256).hexdigest()
                    if type(tag) is not str or not hmac.compare_digest(tag,expected):_refuse()
                    records.append(record)
                if len(records)%2:_refuse()  # intent without terminal = UNKNOWN
                for intent,terminal in zip(records[::2],records[1::2]):
                    if (intent['kind']!='quota-intent' or terminal['kind']!='quota-terminal'
                            or intent['value']['scope']!=stable
                            or terminal['value']['operation_id']!=intent['value']['operation_id']):_refuse()
                    if intent['value']['operation_id']==operation_id:
                        return terminal['value']['result']
                if not records or records[-1]['value']['result']['state']!='OBSERVED':_refuse()
            if not allow_start:_refuse()
            # Keep the real descriptor's kernel lock across reservation, bounded
            # GET and terminal retention; there is no callback writer or new DB.
            def retain(kind,value):
                record=dict(kind=kind,value=value)
                tag=hmac.new(self._gateway._signing_key,
                    b'mastermind.paid.owner-journal/v1\0'+canonical(record),hashlib.sha256).hexdigest()
                raw=_JOURNAL+canonical(dict(record,tag=tag))+b'\n'
                if len(raw)>65536 or os.fstat(fd).st_size+len(raw)>_MAX_LOG:_refuse()
                if os.write(fd,raw)!=len(raw):_refuse()
                os.fsync(fd)
            self.require_capacity_scope(scope['worker_id'],scope['quota_class'])
            retain('quota-intent',dict(operation_id=operation_id,scope=stable,
                source_sha256=scope['source_sha256'],physical_sha256=scope['physical_sha256']))
            from control_plane.paid_fabric_bootstrap import bootstrap_paid_account
            with self._lock:
                if self._stop_fence is not None:_refuse()
                self._metadata_active+=1
            try:
                result=bootstrap_paid_account(self,account_label=scope['account_label'])
                self.require_capacity_scope(scope['worker_id'],scope['quota_class'])
                retain('quota-terminal',dict(operation_id=operation_id,result=result))
                return result
            finally:
                with self._lock:self._metadata_active-=1
        finally:
            fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)

    async def capacity_observation(self,worker_id,quota_class,*,mode,operation_id=None):
        if mode not in {'observe','bootstrap','reconcile'}:_refuse()
        physical,source,account=self.require_capacity_scope(worker_id,quota_class)
        bootstrap=None
        if mode in {'bootstrap','reconcile'}:
            # Explicit separately authorized metadata action, before inference
            # eligibility. The actual helper owns one bounded status GET;
            # passive observation never falls through to this branch.
            scope=dict(worker_id=worker_id,quota_class=quota_class,account_label=account,
                provider=physical['provider'],transport_host=source['qualification']['registry_key'],
                model=physical['model'],source_sha256=digest(source),physical_sha256=digest(physical))
            bootstrap=await asyncio.to_thread(self._quota_bootstrap_owned,operation_id,scope,allow_start=mode=='bootstrap')
        self.require_capacity_scope(worker_id,quota_class)
        from control_plane.paid_fabric_capacity import observe_paid_capacity
        observed=observe_paid_capacity(self,physical=physical,source_config=source,
            account_label=account,quota_class=quota_class)
        return dict(observation=observed,bootstrap=bootstrap,
                    physical_binding_sha256=digest(physical),worker_source_config_digest=digest(source),
                    worker_id=worker_id,quota_class=quota_class,account_label=account)

    async def execute(self, operation, payload):
        self.require_gateway(self._gateway)
        common = dict(adapter_id=ADAPTER_ID, binding=payload['binding'],
                      physical_binding_sha256=payload['physical_binding_sha256'])
        records = self._records(payload)
        starts = [r['value'] for r in records if r['kind'] == 'start']
        if len(starts) > 1:
            _refuse()
        if starts and (starts[0]['binding'] != payload['binding']
                or starts[0]['physical_binding_sha256'] != payload['physical_binding_sha256']):
            _refuse()
        if operation == 'status' and 'start_request_sha256' in payload:
            if starts:
                if starts[0]['request_sha256'] != payload['start_request_sha256']:
                    _refuse()
                return dict(common, request_sha256=payload['start_request_sha256'],
                            start_state='EXISTS', start_result=starts[0])
            occupied = self._occupied(payload['binding']['attempt_id'])
            if occupied:
                _refuse()  # original reservation without full receipt is UNKNOWN
            return dict(common, request_sha256=payload['start_request_sha256'],
                        start_state='NO_RETAINED_START')
        if not starts:
            _refuse()
        if operation == 'status':
            collections = [r['value'] for r in records if r['kind'] == 'collection']
            if len(collections) > 1:
                _refuse()
            if collections and len([r for r in records if r['kind']=='observation'])!=1:_refuse()
            current = self._operations.get(payload['binding']['attempt_id'])
            if not collections and (current is None or current.failed):
                _refuse()
            return dict(common, run=dict(run_id=payload['run_id'],
                status='SUCCEEDED' if collections else 'RUNNING',
                process_ref=starts[0]['process_ref']))
        if operation == 'collect':
            collections = [r['value'] for r in records if r['kind'] == 'collection']
            if len(collections) != 1:
                _refuse()
            observations=[r['value'] for r in records if r['kind']=='observation']
            if len(observations)!=1:_refuse()
            return dict(common, collection=collections[0],paid_observation=observations[0])
        # No fabricated cancellation, assignment seal, native probe or test run.
        _refuse()
