"""Fixed installed-context GLM observations, never Capacity or launch authority.

The opaque Root qualification object is not used here. Each refresh owns a new
observation; installed commitments are expected DATA and never ready flags.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import base64
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import shlex
import stat
import sys
import time

CONTEXT_SCHEMA = 'mastermind.paid_host_readiness_context/v1'
SCHEMA = 'mastermind.glm_qualified_account_readiness/v1'
SCOPE = 'qualified_glm_context.v1'
MAX_AGE = 600
MAX_BYTES = 65536
_CONTEXT_FIELDS = frozenset('schema_version host transport_alias worker_id account model boot_id source_config_sha256 release_manifest_sha256 registry_sha256 initializer_commitment_sha256 validator_sha256 readiness_source_sha256'.split())
_FIELDS = frozenset('schema host transport_alias mode config_scope validator_sha256 observed_at status accounts context config_identity'.split())
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
_BOOT = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z')
_SEAL = object()
_DEFINITION = Path('/Library/Application Support/MastermindExecutive/config/fabric-glm-paid-01')
_RELEASES = Path('/Library/Application Support/MastermindExecutive/releases')
_OWNER = Path('/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext')
_EXT = 'ops/native_fabric/quota_continuity/rollout/native-code-stage/ext'
_SELF = 'paid_host_readiness.py'


class ReadinessRefused(ValueError):
    def __init__(self):
        super().__init__('qualified_host_readiness_refused')


def _refuse():
    raise ReadinessRefused() from None


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=True, allow_nan=False).encode('ascii')
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _refuse()


def _digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _refuse()
            result[key] = value
        return result
    def constant(_):
        _refuse()
    try:
        if type(raw) is not bytes or not 0 < len(raw) <= 4*1024*1024:
            _refuse()
        result = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
        canonical(result)
        return result
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _refuse()


def validate_context_binding(value):
    if type(value) is not dict or set(value) != _CONTEXT_FIELDS:
        _refuse()
    if (value['schema_version'] != CONTEXT_SCHEMA or value['host'] != 'ubuntu0'
            or value['model'] != 'glm-5.3-flash'):
        _refuse()
    for key in ('host', 'transport_alias', 'worker_id', 'account'):
        if type(value[key]) is not str or not _ID.fullmatch(value[key]):
            _refuse()
    if type(value['boot_id']) is not str or not _BOOT.fullmatch(value['boot_id']):
        _refuse()
    for key in _CONTEXT_FIELDS:
        if key.endswith('_sha256') and (type(value[key]) is not str or not _SHA.fullmatch(value[key])):
            _refuse()
    return _decode(canonical(value))


def _fresh(at, now, maximum=MAX_AGE):
    return (type(at) in (int, float) and type(now) in (int, float)
        and math.isfinite(at) and math.isfinite(now) and at > 0
        and at <= now+1 and now-at <= maximum)


def validate_observation(value, *, binding, now):
    expected = validate_context_binding(binding)
    if (type(value) is not dict or set(value) != _FIELDS
            or len(canonical(value)) > MAX_BYTES
            or value['schema'] != SCHEMA or value['config_scope'] != SCOPE
            or value['mode'] != 'glm' or value['context'] != expected
            or any(type(value[k]) is not str or value[k] != expected[k]
                   for k in ('host', 'transport_alias', 'validator_sha256'))
            or not _fresh(value['observed_at'], now)
            or value['status'] not in ('known', 'unknown', 'refused')
            or type(value['accounts']) is not dict):
        _refuse()
    flags = value['accounts']
    if value['status'] == 'known':
        if set(flags) != {expected['account']} or type(flags[expected['account']]) is not bool:
            _refuse()
    elif flags:
        _refuse()
    info=value['config_identity']
    if value['status']=='known':
        if (type(info) is not list or len(info)!=9 or any(type(v) is not int or v<0 for v in info)
                or not stat.S_ISREG(info[2]) or stat.S_IMODE(info[2])!=0o600 or info[3]<=0
                or info[5]!=1 or not 0<info[6]<=1024*1024):_refuse()
    elif info is not None:_refuse()
    return _decode(canonical(value))


def filter_accounts(accounts, document, *, binding, host, transport_alias, model,
                    validator_sha256, now, preferred=None):
    """A stricter new-schema intersection; no credential/config/clock reads."""
    try:
        expected = validate_context_binding(binding)
        if (host != expected['host'] or transport_alias != expected['transport_alias']
                or model != expected['model'] or validator_sha256 != expected['validator_sha256']
                or type(document) is not dict or document.get('host') != host
                or document.get('reachable') is not True
                or document.get('boot_id') != expected['boot_id']
                or not _fresh(document.get('ts'), now, 180)
                or type(accounts) not in (list, tuple) or len(accounts) > 64):
            _refuse()
        observation = validate_observation(document.get('glm_local_account_readiness'),
                                           binding=expected, now=now)
        names = [row.get('name') for row in accounts if type(row) is dict]
        if (len(names) != len(accounts) or len(set(names)) != len(names)
                or any(type(n) is not str or not _ID.fullmatch(n) for n in names)
                or preferred not in (None, '', expected['account'])):
            _refuse()
        if observation['status'] != 'known' or observation['accounts'].get(expected['account']) is not True:
            return [], 'qualified_account_unknown'
        return [row for row in accounts if row['name'] == expected['account']], 'ok'
    except (ValueError, TypeError, KeyError, OverflowError):
        return [], 'qualified_context_unavailable'


def _identity(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid,
            s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def _root_interfaces():
    # This first read selects only a fixed protected release directory. It is
    # NOT source authority: full owner/ACL/manifest verification follows before
    # any observation or private remote input can be prepared.
    path = _DEFINITION/'profile.json'
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or before.st_gid != 0
                or before.st_mode & 0o022 or before.st_nlink != 1
                or not 0 < before.st_size <= MAX_BYTES):
            _refuse()
        raw = os.read(fd, MAX_BYTES+1)
        if len(raw) != before.st_size or _identity(before) != _identity(os.fstat(fd)):
            _refuse()
    finally:
        os.close(fd)
    profile = _decode(raw)
    release = profile.get('release_commit') if type(profile) is dict else None
    if type(release) is not str or not re.fullmatch(r'[0-9a-f]{40}', release):
        _refuse()
    root = _RELEASES/release
    # The fixed Root installation is the code-trust premise, as for the normal
    # installed owner. No caller directory, PYTHONPATH or fallback is accepted.
    for name, loaded in tuple(sys.modules.items()):
        if name == 'control_plane' or name.startswith(('control_plane.', 'ops.')):
            origin = getattr(loaded, '__file__', None)
            if origin is not None and not Path(origin).absolute().is_relative_to(root):
                _refuse()
    sys.path.insert(0, str(root))
    try:
        qualification = importlib.import_module('ops.executive_os.canonical_paid_qualification')
        manifest = importlib.import_module('ops.executive_os.release_manifest')
        native = importlib.import_module('control_plane.codex_provider_realm')
        backend = importlib.import_module('control_plane.paid_fabric_backend')
        for module in (qualification, manifest, native, backend):
            if not Path(module.__file__).absolute().is_relative_to(root):
                _refuse()
        return root, qualification, manifest, native._native_open, backend._root_source
    finally:
        sys.path.remove(str(root))


class InstalledReadinessContext:
    """A live local owner check, not a serializable or remote capability."""
    def __init__(self, seal, *, binding, commitment, sources, root, checks):
        if seal is not _SEAL:
            _refuse()
        self._binding = canonical(validate_context_binding(binding))
        self._commitment = canonical(commitment)
        self._sources = sources
        self._root = root
        self._checks = checks
        self._closed = False

    def __setattr__(self,name,value):
        if hasattr(self,name):_refuse()
        object.__setattr__(self,name,value)

    def __reduce_ex__(self, _):
        _refuse()

    @property
    def binding(self):
        self.check()
        return _decode(self._binding)

    @property
    def initializer_commitment(self):
        self.check()
        return _decode(self._commitment)

    @property
    def source_hashes(self):
        self.check()
        return {name: hashlib.sha256(raw).hexdigest() for name, raw in self._sources.items()}

    def check(self):
        if self._closed:
            _refuse()
        for check in self._checks:
            check()


def _context_material(verified, *, manifest_sha256, registry_sha256,
                      validator_sha256, readiness_source_sha256):
    profile, rows = verified['profile'], verified['bindings']
    if type(rows) is not list or len(rows) != 1:
        _refuse()
    row = rows[0]
    source = row['source_config']
    q = source['qualification']
    commitment = q['initializer_commitment']
    if (commitment['initialization_contract']!='paid-host-env-held-fd-token-data.v1'
            or commitment['startup']['profile']!='cpython-3.12-linux-root-prefix-nosite.v1'
            or q['registry_key'] != 'ubuntu0' or profile['registration']['account_label'] == ''
            or q['registry_sha256'] != registry_sha256
            or q['qualifier_source_manifest_sha256'] != manifest_sha256
            or _digest(commitment) != q['initializer_commitment_sha256']):
        _refuse()
    binding = dict(schema_version=CONTEXT_SCHEMA, host=q['registry_key'],
        transport_alias=q['transport_alias'], worker_id=source['worker_id'],
        account=profile['registration']['account_label'], model=source['model'],
        boot_id=q['boot_id'], source_config_sha256=_digest(source),
        release_manifest_sha256=manifest_sha256, registry_sha256=registry_sha256,
        initializer_commitment_sha256=q['initializer_commitment_sha256'],
        validator_sha256=validator_sha256, readiness_source_sha256=readiness_source_sha256)
    return validate_context_binding(binding), _decode(canonical(commitment))


@contextmanager
def open_installed_context():
    """Only the fixed real Root definition/release; no caller DATA input."""
    result = None
    try:
        root, owner, release_manifest, native_open, root_read = _root_interfaces()
        with ExitStack() as stack:
            checks = []
            def held(path):
                fd, info = stack.enter_context(native_open(path))
                before = _identity(info)
                if not 0 < info.st_size <= 4*1024*1024:
                    _refuse()
                raw = bytearray()
                while len(raw) <= info.st_size:
                    block = os.read(fd, min(65536, info.st_size+1-len(raw)))
                    if not block:
                        break
                    raw.extend(block)
                if len(raw) != info.st_size:
                    _refuse()
                def check():
                    if _identity(os.fstat(fd)) != before or _identity(os.lstat(path)) != before:
                        _refuse()
                checks.append(check);check()
                return bytes(raw)
            files = {name: held(_DEFINITION/name) for name in owner.base.FILES}
            verified = owner.verify_qualified_artifacts(files)
            profile = verified['profile']
            if profile['release_commit'] != root.name:
                _refuse()
            manifest_raw = held(root/'.executive-release-manifest.json')
            manifest = _decode(manifest_raw)
            manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
            if manifest_sha != profile['release_manifest_sha256']:
                _refuse()
            release_manifest.verify(root, root.name, profile['release_tree'])
            ext = root/_EXT
            sources = {name: held(ext/name) for name in
                ('paid_initializer.py','paid_initializer_token_data.py','paid_initializer_nested_data.py',
                 'paid_host_qualification.py','host_pull.sh','host_pull_backend.py','glm_keys.py',_SELF)}
            entries = {entry['path']: entry for entry in manifest['entries']}
            for name, raw in sources.items():
                if entries[_EXT+'/'+name]['sha256'] != hashlib.sha256(raw).hexdigest():
                    _refuse()
            # The actually executing native copy must equal the sealed owner.
            if Path(__file__).read_bytes() != sources[_SELF]:
                _refuse()
            qualifier_name = '_qualified_recurring_host_initializer'
            # Registry uses the existing incumbent owner reader, never a new
            # path, file authority or caller-supplied expected digest.
            import importlib.util
            spec = importlib.util.spec_from_file_location(qualifier_name, ext/'paid_host_qualification.py')
            qualifier = importlib.util.module_from_spec(spec);spec.loader.exec_module(qualifier)
            registry_raw, registry_info = qualifier._read_owned(_OWNER/'hosts.json', owners={0,501})
            def registry_check():
                if qualifier._read_owned(_OWNER/'hosts.json', owners={0,501}) != (registry_raw, registry_info):
                    _refuse()
            checks.append(registry_check)
            registry = _decode(registry_raw)
            entry = registry.get('ubuntu0')
            if (type(entry) is not dict or entry.get('platform') != 'linux'
                    or 'lanes' not in entry.get('roles', [])
                    or 'glm' not in entry.get('allowed_modes', [])
                    or 'glm' in entry.get('qualification_only_modes', [])):
                _refuse()
            binding, commitment = _context_material(verified, manifest_sha256=manifest_sha,
                registry_sha256=hashlib.sha256(registry_raw).hexdigest(),
                validator_sha256=hashlib.sha256(sources['glm_keys.py']).hexdigest(),
                readiness_source_sha256=hashlib.sha256(sources[_SELF]).hexdigest())
            if entry.get('ssh_alias') != binding['transport_alias']:
                _refuse()
            q = verified['bindings'][0]['source_config']['qualification']
            for name, expected in q['qualifier_sources_sha256'].items():
                raw = sources.get(name)
                if raw is None:
                    raw = held(ext/name)
                    sources[name]=raw
                if hashlib.sha256(raw).hexdigest() != expected:
                    _refuse()
            # Reuse exact current context and keep definition namespace closed.
            def definition_check():
                observed, _ = owner._read_definition_bytes(_DEFINITION)
                if observed != files:
                    _refuse()
            checks.append(definition_check)
            result = InstalledReadinessContext(_SEAL, binding=binding, commitment=commitment,
                sources=sources, root=root, checks=checks)
            result.check()
            try:
                yield result
                result.check()
            finally:
                object.__setattr__(result,'_closed',True)
    except Exception:
        _refuse()

# Fixed code only. This runs AFTER the exact held startup has validated actual
# HOME/config/Python selection. Private configuration is a held DATA snapshot;
# neither it nor credential exceptions are printed, evaluated or put in argv.
READINESS_PROBE = r'''
import base64,errno,hashlib,json,os,stat,time,types
from pathlib import Path
r={'schema':'mastermind.glm_qualified_account_readiness/v1',
 'host':_p['context']['host'],'transport_alias':_p['context']['transport_alias'],
 'mode':'glm','config_scope':'qualified_glm_context.v1',
 'validator_sha256':_p['context']['validator_sha256'],'observed_at':time.time(),
 'status':'unknown','accounts':{},'context':_p['context'],'config_identity':None}
fds=[];edges=[]
def ident(s):
 return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def no_acl(fd):
 for name in ('system.posix_acl_access','system.posix_acl_default'):
  try:os.getxattr(fd,name)
  except OSError as exc:
   if exc.errno not in (errno.ENODATA,getattr(errno,'ENOATTR',errno.ENODATA)):raise ValueError()
  else:raise PermissionError()
def check():
 for parent,name,fd,before in edges:
  if ident(os.fstat(fd))!=before or ident(os.stat(name,dir_fd=parent,follow_symlinks=False))!=before:raise PermissionError()
try:
 if Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=_p['context']['boot_id']:raise ValueError()
 env=_p['initializer_commitment']['initialized_context']
 if os.environ.get('HOME')!=env['home'] or (os.environ.get('GLM_CONFIG') or env['home']+'/.glm/config.json')!=env['glm_config']:raise ValueError()
 source=base64.b64decode(_p['validator_b64'],validate=True)
 if hashlib.sha256(source).hexdigest()!=r['validator_sha256']:raise ValueError()
 flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK
 parent=os.open('/',flags|os.O_DIRECTORY);fds.append(parent)
 root=os.fstat(parent)
 if not stat.S_ISDIR(root.st_mode) or root.st_uid!=0 or root.st_mode&0o022:raise ValueError()
 no_acl(parent)
 parts=Path(env['glm_config']).parts[1:]
 for index,name in enumerate(parts):
  final=index==len(parts)-1
  fd=os.open(name,flags|(0 if final else os.O_DIRECTORY),dir_fd=parent);fds.append(fd)
  info=os.fstat(fd);no_acl(fd)
  if info.st_uid not in ({os.geteuid()} if final else {0,os.geteuid()}) or info.st_mode&0o022:raise PermissionError()
  if final:
   if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o600 or info.st_gid!=os.getegid() or info.st_nlink!=1 or not 0<info.st_size<=1024*1024:raise PermissionError()
  elif not stat.S_ISDIR(info.st_mode):raise ValueError()
  edges.append((parent,name,fd,ident(info)));parent=fd
 data=bytearray()
 while len(data)<=info.st_size:
  part=os.read(fd,min(65536,info.st_size+1-len(data)))
  if not part:break
  data.extend(part)
 if len(data)!=info.st_size:raise ValueError()
 raw=json.loads(data)
 if type(raw)is not dict or not raw:raise ValueError()
 module=types.ModuleType('qualified_readiness_validator')
 module.__file__=env['home']+'/lanes/ext/glm_keys.py'
 exec(compile(source,'<qualified-glm-validator>','exec'),module.__dict__)
 module._load_raw=lambda:raw
 accounts=module.accounts(quiet=True)
 name=_p['context']['account']
 try:module.selected_account_key(name,accounts);ready=True
 except (ValueError,TypeError):ready=False
 check()
 r.update(status='known',accounts={name:ready},config_identity=list(ident(info)))
except PermissionError:
 r.update(status='refused',accounts={},config_identity=None)
except Exception:
 r.update(status='unknown',accounts={},config_identity=None)
finally:
 for fd in reversed(fds):os.close(fd)
print(json.dumps({'readiness':r},sort_keys=True,separators=(',',':'),allow_nan=False))
'''


def _qualifier(context):
    # No mutable import search: these bytes are pinned/held by installed context.
    from types import ModuleType
    context.check()
    value = ModuleType('_qualified_recurring_readiness_compiler')
    value.__file__ = str(context._root/_EXT/'paid_host_qualification.py')
    exec(compile(context._sources['paid_host_qualification.py'], value.__file__, 'exec'), value.__dict__)
    return value


def _probe(context, qualifier):
    """Reuse the actual host/image observer, with a separate fixed DATA result."""
    source = qualifier._REMOTE_PROBE
    marker = "if __name__=='__main__':"
    if source.count(marker) != 1:
        _refuse()
    # Keep every original host/image/capture check. The new observer owns only
    # the one fixed account read and uses the real prior observer result.
    source = source.split(marker)[0]
    result = READINESS_PROBE.replace(
        "print(json.dumps({'readiness':r},sort_keys=True,separators=(',',':'),allow_nan=False))",
        "print(json.dumps({'readiness':r,'host_observation':_host_observation},sort_keys=True,separators=(',',':'),allow_nan=False))")
    return source + "\np=_p\n_host_observation=observe(p)\n" + result


def prepare_refresh(context, *, nonce=None):
    if type(context) is not InstalledReadinessContext:
        _refuse()
    context.check()
    q = _qualifier(context)
    binding = context.binding
    commitment = context.initializer_commitment
    probe = _probe(context, q)
    if nonce is None:
        nonce = secrets.token_hex(32)
    if type(nonce) is not str or not _SHA.fullmatch(nonce):
        _refuse()
    # A new observation request, not an old qualification object or its time.
    request = dict(schema='mastermind.paid_readiness_probe/v1',host_ref='ubuntu0',
        transport_alias=binding['transport_alias'],nonce=nonce,
        python_path=commitment['launch_python']['path'],
        capture_root=commitment['lane_root']+'/ext/lanes',
        release_sha=context._root.name,source_manifest_sha256=binding['release_manifest_sha256'],
        preimage_sha256=binding['source_config_sha256'],registry_sha256=binding['registry_sha256'],
        sources_sha256=context.source_hashes,probe_sha256=hashlib.sha256(probe.encode()).hexdigest(),
        context=q._CONTEXT,initializer_commitment=commitment,
        initializer_commitment_sha256=binding['initializer_commitment_sha256'])
    # _p.context is reserved by incumbent host observer; the readiness context
    # has its own closed key and is installed only in the fixed new probe code.
    request['readiness_context'] = binding
    request['validator_b64'] = base64.b64encode(context._sources['glm_keys.py']).decode('ascii')
    probe = probe.replace("_p['context']", "_p['readiness_context']")
    request['probe_sha256'] = hashlib.sha256(probe.encode()).hexdigest()
    peers = {name: context._sources[name] for name in (
        'paid_initializer.py','paid_initializer_token_data.py','paid_initializer_nested_data.py')}
    expected = {name: hashlib.sha256(raw).hexdigest() for name,raw in peers.items()}
    payload = canonical(dict(request=request,probe=probe,
        sources={name:base64.b64encode(raw).decode('ascii') for name,raw in peers.items()},
        expected=expected))
    if len(payload) > 256*1024:
        _refuse()
    # Unlike telemetry spool, this command starts the explicit committed image
    # directly, with the exact early policy before any package/stdlib imports.
    package_namespace = {};exec(q._PACKAGE_LOADER, package_namespace)
    parent = package_namespace['_load_qualified_package'](peers, expected)
    early = parent.NO_SITE_PREAMBLE
    entry = early + r'''
import base64,hashlib,json,sys
raw=sys.stdin.buffer.read(262145)
if len(raw)>262144 or hashlib.sha256(raw).hexdigest()!=sys.argv[1]:raise SystemExit(78)
p=json.loads(raw)
''' + q._PACKAGE_LOADER + r'''
try:
 sources={name:base64.b64decode(raw,validate=True) for name,raw in p['sources'].items()}
 module=_load_qualified_package(sources,p['expected'])
 module.require_no_site_policy()
 sys.stdout.buffer.write(module.run_bootstrap(p['request'],p['probe']))
 module.require_no_site_policy()
except Exception:raise SystemExit(78)
'''
    command = shlex.quote(commitment['bootstrap_python']['path']) + ' -I -S -B -c ' + shlex.quote(entry) + ' ' + hashlib.sha256(payload+b'\n').hexdigest()
    if len(command.encode())+1 > 100000:
        _refuse()
    context.check()
    return dict(alias=binding['transport_alias'], command=command,
                stdin=payload.decode('ascii')+'\n', request=request)


def validate_refresh_result(raw, plan, context, *, now):
    context.check()
    result = _decode(raw)
    if type(result) is not dict or set(result) != {'readiness','host_observation','pre_execution'}:
        _refuse()
    q = _qualifier(context)
    host_observation = result['host_observation']
    if type(host_observation) is not dict or 'pre_execution' in host_observation:
        _refuse()
    host_observation = dict(host_observation, pre_execution=result['pre_execution'])
    actual = q._observation(canonical(host_observation), plan['request'])
    if actual['boot_id'] != context.binding['boot_id']:
        _refuse()
    observation = validate_observation(result['readiness'],binding=context.binding,now=now)
    if observation['status']=='known':
        account=context.initializer_commitment['account']
        if observation['config_identity'][3:5]!=[account['uid'],account['gid']]:_refuse()
    context.check()
    return observation


class ObservationUnavailable(RuntimeError):
    def __init__(self):
        super().__init__('qualified_observation_unavailable')


def _transport_outcome(code, output, error):
    # Only an exact local OpenSSH pre-connect failure establishes that this
    # observation did not reach remote startup. Never retain/echo stderr.
    # Authentication/trust failures, silence and ambiguous loss remain held.
    if code == 0 and output and not error:
        return 'RETURNED'
    if code == 255 and not output and len(error) <= 4096 and re.fullmatch(
            rb'ssh: connect to host [A-Za-z0-9.:%_-]{1,253} port [0-9]{1,5}: '
            rb'(?:Connection timed out|Operation timed out|No route to host|'
            rb'Network is unreachable|Connection refused)\n', error):
        return 'PRECONNECT_UNAVAILABLE'
    return 'REFUSED'


def _transport(context, request, *, correction_sha=None):
    """One existing host-pull transport child, bounded stdout and lifetime."""
    import selectors
    import signal
    import subprocess
    context.check()
    if sys.platform != 'darwin' or os.getuid() != os.geteuid() or os.geteuid() not in (0,501):
        _refuse()
    q = _qualifier(context)
    principal = q._transport_principal()
    env = dict(HOME=principal['home'],USER=principal['user'],LOGNAME=principal['user'],
        LC_ALL='C',LANG='C',PATH=str(Path(sys.executable).parent)+':/usr/bin:/bin:/usr/sbin:/sbin',
        PYTHONDONTWRITEBYTECODE='1')
    options = {}
    if os.geteuid()==0:
        options=dict(user=principal['uid'],group=principal['gid'],extra_groups=[])
    elif os.getgid()!=principal['gid']:
        _refuse()
    command=['/bin/bash',str(context._root/_EXT/'host_pull.sh'),
             '--qualified-readiness-transport','ubuntu0']
    outgoing=canonical(request)
    if len(outgoing)>MAX_BYTES:
        _refuse()
    context.check()
    peer=child_peer=None
    if correction_sha is not None:
        if os.geteuid()!=0 or type(correction_sha)is not str or not _SHA.fullmatch(correction_sha):_refuse()
        import socket
        peer,child_peer=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
        os.set_inheritable(peer.fileno(),False)
        env['H1_READINESS_CORRECTION_FD']='9'
        options['pass_fds']=(child_peer.fileno(),)
        command=[sys.executable,'-I','-S','-B',str(context._root/_EXT/_SELF),
                 'transport-spawn',str(child_peer.fileno())]
    try:
        child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,env=env,cwd='/',start_new_session=True,close_fds=True,**options)
    except BaseException:
        if peer is not None:peer.close()
        if child_peer is not None:child_peer.close()
        raise ReadinessRefused() from None
    if child_peer is not None:child_peer.close()
    if peer is not None:
        try:
            frame=canonical(dict(schema='mastermind.qualified_readiness_correction/v1',
                context_sha256=_digest(context.binding),request_sha256=_digest(request),
                refusal_sha256=correction_sha))
            peer.sendall(frame);peer.shutdown(1)
        except BaseException:
            for stream in (child.stdin,child.stdout,child.stderr):
                if stream is not None and not stream.closed:stream.close()
            try:os.killpg(child.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid,signal.SIGKILL);child.wait()
            raise ReadinessRefused() from None
        finally:peer.close()
    started=time.monotonic();captured=bytearray();errors=bytearray();offset=0
    try:
        with selectors.DefaultSelector() as selected:
            os.set_blocking(child.stdin.fileno(),False)
            selected.register(child.stdin,selectors.EVENT_WRITE,'in')
            selected.register(child.stdout,selectors.EVENT_READ,'out')
            selected.register(child.stderr,selectors.EVENT_READ,'err')
            while selected.get_map():
                left=40-(time.monotonic()-started)
                if left<=0:
                    _refuse()
                for key,_ in selected.select(min(left,0.25)):
                    if key.data=='in':
                        try:offset+=os.write(key.fileobj.fileno(),outgoing[offset:offset+4096])
                        except BlockingIOError:continue
                        except BrokenPipeError:
                            selected.unregister(key.fileobj);child.stdin.close();continue
                        if offset==len(outgoing):
                            selected.unregister(key.fileobj);child.stdin.close()
                    else:
                        data=os.read(key.fileobj.fileno(),8192)
                        if not data:selected.unregister(key.fileobj)
                        else:
                            sink=errors if key.data=='err' else captured
                            sink.extend(data)
                            if len(sink)>(4096 if key.data=='err' else MAX_BYTES):_refuse()
        code=child.wait(timeout=max(0.01,40-(time.monotonic()-started)))
        outcome=_transport_outcome(code,bytes(captured),bytes(errors))
        if outcome=='PRECONNECT_UNAVAILABLE':raise ObservationUnavailable()
        if outcome!='RETURNED':_refuse()
        context.check()
        return bytes(captured)
    except (subprocess.TimeoutExpired, OSError, ValueError):
        raise ReadinessRefused() from None
    finally:
        for stream in (child.stdin,child.stdout,child.stderr):
            if stream is not None and not stream.closed:stream.close()
        if child.poll() is None:
            # Only this newly owned finite transport session; never a Fabric
            # controller, provider, lease or pre-existing remote operation.
            try:os.killpg(child.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid,signal.SIGKILL);child.wait()


def _state_read(directory):
    directory=Path(directory)
    dfd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=os.fstat(dfd)
        if before.st_uid!=501 or before.st_mode&0o022:_refuse()
        fd=os.open('ubuntu0.json',os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=dfd)
        try:
            info=os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid!=501 or info.st_mode&0o022
                    or info.st_nlink!=1 or not 0<info.st_size<=1024*1024):_refuse()
            data=bytearray()
            while len(data)<=info.st_size:
                part=os.read(fd,min(65536,info.st_size+1-len(data)))
                if not part:break
                data.extend(part)
            if (len(data)!=info.st_size or _identity(info)!=_identity(os.fstat(fd))
                    or _identity(info)!=_identity(os.stat('ubuntu0.json',dir_fd=dfd,follow_symlinks=False))):_refuse()
            return bytes(data),_identity(info),(before.st_dev,before.st_ino)
        finally:os.close(fd)
    finally:os.close(dfd)


def _publish(directory, context, observation, *, expected_refusal=None):
    """Existing host snapshot only; never update its physical timestamp."""
    import fcntl
    import tempfile
    directory=Path(directory)
    dfd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    temporary=None
    try:
        fcntl.flock(dfd,fcntl.LOCK_EX)
        raw,identity,origin=_state_read(directory)
        old=_decode(raw)
        prior=old.get('glm_local_account_readiness')
        if expected_refusal is not None:
            if type(prior)is not dict or prior.get('status')!='refused' or _digest(prior)!=expected_refusal:_refuse()
        elif type(prior)is dict and prior.get('status')=='refused':
            # Refusal is original observation evidence, not an expiring hold.
            _refuse()
        if observation is not None:
            observation=validate_observation(observation,binding=context.binding,now=time.time())
            if (old.get('host')!='ubuntu0' or old.get('reachable') is not True
                    or old.get('telemetry_mode')!='physical-only.v1'
                    or old.get('boot_id')!=context.binding['boot_id']
                    or not _fresh(old.get('ts'),time.time(),180)):_refuse()
            old['glm_local_account_readiness']=observation
        else:
            old.pop('glm_local_account_readiness',None)
        context.check()
        fd,temporary=tempfile.mkstemp(prefix='ubuntu0.',suffix='.tmp',dir=directory)
        payload=canonical(old)+b'\n'
        with os.fdopen(fd,'wb') as handle:
            handle.write(payload);handle.flush();os.fsync(handle.fileno())
            os.fchmod(handle.fileno(),0o644)
            if os.geteuid()==0:os.fchown(handle.fileno(),501,identity[4])
        if (_state_read(directory)!=(raw,identity,origin)
                or (os.stat(directory,follow_symlinks=False).st_dev,
                    os.stat(directory,follow_symlinks=False).st_ino)!=origin):_refuse()
        context.check()
        os.replace(temporary,directory/'ubuntu0.json');temporary=None
        os.fsync(dfd)
        published=_decode(_state_read(directory)[0])
        if published!=old:_refuse()
        context.check()
        return published
    finally:
        if temporary is not None:
            try:os.unlink(temporary)
            except FileNotFoundError:pass
        os.close(dfd)


def qualified_config_identity(context):
    """Same fresh installed observation for actual canonical provider entry.

    This metadata is not a remote capability. The remote owner must independently
    hold/recheck its real selected file through credential/provider entry.
    """
    if type(context)is not InstalledReadinessContext:_refuse()
    context.check()
    before=_state_read(_OWNER/'state/hosts')
    document=_decode(before[0]);binding=context.binding
    rows,reason=filter_accounts([{'name':binding['account']}],document,
        binding=binding,host=binding['host'],transport_alias=binding['transport_alias'],
        model=binding['model'],validator_sha256=binding['validator_sha256'],now=time.time())
    if not rows or reason!='ok':_refuse()
    observation=validate_observation(document['glm_local_account_readiness'],binding=binding,now=time.time())
    info=observation['config_identity']
    account=context.initializer_commitment['account']
    if info[3]!=account['uid'] or info[4]!=account['gid']:_refuse()
    context.check()
    if _state_read(_OWNER/'state/hosts')!=before:_refuse()
    return list(info)


def _refusal(context, *, now):
    b=context.binding
    return dict(schema=SCHEMA,host=b['host'],transport_alias=b['transport_alias'],mode='glm',
        config_scope=SCOPE,validator_sha256=b['validator_sha256'],observed_at=now,
        status='refused',accounts={},context=b,config_identity=None)


def _observe(context, *, correction_sha=None):
    plan=prepare_refresh(context)
    raw=_transport(context,plan['request'],correction_sha=correction_sha)
    return validate_refresh_result(raw,plan,context,now=time.time())


def refresh():
    """Normal recurring owner: unavailable reads may have a later new cycle."""
    if os.getuid()!=501 or os.geteuid()!=501:_refuse()
    with open_installed_context() as context:
        directory=_OWNER/'state/hosts'
        prior=_decode(_state_read(directory)[0]).get('glm_local_account_readiness')
        if type(prior)is dict and prior.get('status')=='refused':_refuse()
        try:
            observation=_observe(context)
        except ObservationUnavailable:
            _publish(directory,context,None)
            return 'UNAVAILABLE'
        except ReadinessRefused:
            _publish(directory,context,_refusal(context,now=time.time()))
            raise
        _publish(directory,context,observation)
        return {'known':'OBSERVED','unknown':'UNAVAILABLE','refused':'REFUSED'}[observation['status']]


@contextmanager
def _correction_interval():
    # The SAME existing canonical CONFIG_ROOT publication mutex serializes
    # explicit administrative corrections and install/qualification writers.
    import fcntl
    _root,_owner,_manifest,native_open,_read=_root_interfaces()
    with native_open(_DEFINITION.parent,directory=True) as (fd,_info):
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:_refuse()
        try:yield
        finally:fcntl.flock(fd,fcntl.LOCK_UN)


def correct_refusal(*, expected_context_sha256, expected_refusal_sha256):
    """Explicit normal Root-owner action; not permission to bypass a denial.

    Its invocation remains held until that denial's supported resolution and
    actual admission exist. Root/CAS alone cannot clear an OS/tool/provider gate.
    Only a genuine successful newly permitted observation can replace evidence.
    """
    if (os.getuid()!=0 or os.geteuid()!=0 or sys.platform!='darwin'
            or not sys.flags.isolated or not sys.flags.no_site or not sys.dont_write_bytecode):_refuse()
    if any(type(v)is not str or not _SHA.fullmatch(v) for v in
           (expected_context_sha256,expected_refusal_sha256)):_refuse()
    with _correction_interval():
        with open_installed_context() as context:
            if _digest(context.binding)!=expected_context_sha256:_refuse()
            directory=_OWNER/'state/hosts'
            prior=_decode(_state_read(directory)[0]).get('glm_local_account_readiness')
            if (type(prior)is not dict or prior.get('status')!='refused'
                    or _digest(prior)!=expected_refusal_sha256):_refuse()
            # Any failure leaves the exact original refusal in place. No flagclear,
            # metadata-only "resolution", automatic restart or new source epoch.
            observation=_observe(context,correction_sha=expected_refusal_sha256)
            if observation['status']!='known':_refuse()
            _publish(directory,context,observation,expected_refusal=expected_refusal_sha256)
            return 'OBSERVED'

def _kernel_peer_uid(sock):
    import socket
    if sock.family!=socket.AF_UNIX or sock.type&0xf!=socket.SOCK_STREAM:_refuse()
    if hasattr(sock,'getpeereid'):
        return sock.getpeereid()[0]
    if sys.platform=='darwin':
        import ctypes
        library=ctypes.CDLL('/usr/lib/libSystem.B.dylib',use_errno=True)
        function=library.getpeereid
        function.argtypes=[ctypes.c_int,ctypes.POINTER(ctypes.c_uint),ctypes.POINTER(ctypes.c_uint)]
        function.restype=ctypes.c_int
        uid,gid=ctypes.c_uint(),ctypes.c_uint()
        if function(sock.fileno(),ctypes.byref(uid),ctypes.byref(gid))!=0:_refuse()
        return uid.value
    if sys.platform=='linux':
        import struct
        return struct.unpack('3i',sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))[1]
    _refuse()


def prepare_transport_request(raw):
    """Internal DATA compiler also enforces the actual original refusal edge."""
    import socket
    request=_decode(raw)
    if type(request)is not dict:_refuse()
    with open_installed_context() as context:
        plan=prepare_refresh(context,nonce=request.get('nonce'))
        if canonical(request)!=canonical(plan['request']):_refuse()
        prior=_decode(_state_read(_OWNER/'state/hosts')[0]).get('glm_local_account_readiness')
        supplied=os.environ.get('H1_READINESS_CORRECTION_FD')
        if type(prior)is dict and prior.get('status')=='refused':
            if (type(supplied)is not str or not re.fullmatch(r'[0-9]{1,4}',supplied)
                    or not 3<=int(supplied)<=1024):_refuse()
            with socket.socket(fileno=int(supplied)) as peer:
                peer.settimeout(5)
                if _kernel_peer_uid(peer)!=0:_refuse()
                data=bytearray()
                while len(data)<=4096:
                    chunk=peer.recv(min(4097-len(data),4096))
                    if not chunk:break
                    data.extend(chunk)
                if len(data)>4096:_refuse()
                message=_decode(bytes(data))
            expected=dict(schema='mastermind.qualified_readiness_correction/v1',
                context_sha256=_digest(context.binding),request_sha256=_digest(request),
                refusal_sha256=_digest(prior))
            if message!=expected:_refuse()
        elif supplied is not None:
            # A correction cannot race with an unrelated cache replacement.
            _refuse()
        context.check()
        return plan


def _spawn_transport(raw_fd):
    """Fixed FD9 handoff, matching the incumbent controller spawn pattern."""
    import socket
    if type(raw_fd)is not str or not re.fullmatch(r'[0-9]{1,4}',raw_fd) or not 3<=int(raw_fd)<=1024:_refuse()
    fd=int(raw_fd)
    peer=socket.socket(fileno=os.dup(fd))
    try:
        if _kernel_peer_uid(peer)!=0:_refuse()
    finally:peer.close()
    script=Path(__file__).absolute().with_name('host_pull.sh')
    if script.is_symlink():_refuse()
    if fd!=9:
        os.dup2(fd,9,inheritable=True);os.close(fd)
    else:os.set_inheritable(9,True)
    env=dict(os.environ,H1_READINESS_CORRECTION_FD='9')
    os.execve('/bin/bash',['/bin/bash',str(script),'--qualified-readiness-transport','ubuntu0'],env)


if __name__=='__main__':
    try:
        if len(sys.argv)==3 and sys.argv[1]=='transport-spawn':
            _spawn_transport(sys.argv[2]);_refuse()
        elif sys.argv[1:]==['refresh']:
            result=refresh()
        elif (len(sys.argv)==6 and sys.argv[1]=='correct-refusal'
                and sys.argv[2]=='--expected-context-sha256'
                and sys.argv[4]=='--expected-refusal-sha256'):
            result=correct_refusal(expected_context_sha256=sys.argv[3],expected_refusal_sha256=sys.argv[5])
        else:_refuse()
        print('qualified_readiness='+result)
        raise SystemExit(78 if result=='REFUSED' else 0)
    except ObservationUnavailable:
        print('qualified_readiness=UNAVAILABLE');raise SystemExit(75)
    except Exception:
        print('qualified_readiness=REFUSED');raise SystemExit(78)
