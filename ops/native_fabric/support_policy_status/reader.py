"""Fixed support-policy observation in the incumbent owner; no mutation.

The caller supplies an original-owner issued request, never a filesystem selector.
The module is source-only until its ordinary native cohort integration qualifies.
"""
from __future__ import annotations
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat

import artifact_delivery as delivery
import fabric_policy_snapshot as policy
import lane_runtime as lane
import support_bundle as support

SCHEMA = 'mastermind.support_policy_status.v1'
REQUEST_SCHEMA = 'mastermind.original_support_policy_status.v1'
LIMIT = 2 * 1024 * 1024


class Unavailable(ValueError):
    pass


def require(value, reason):
    if not value:
        raise Unavailable(reason)


def identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_at(parent_fd, name, limit=LIMIT):
    visible = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    require(stat.S_ISREG(visible.st_mode) and visible.st_nlink == 1
            and visible.st_uid == os.getuid() and not visible.st_mode & 0o022
            and 0 < visible.st_size <= limit, 'file_custody')
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd)
    try:
        opened = os.fstat(fd)
        require(identity(opened) == identity(visible), 'file_changed')
        data = bytearray()
        while len(data) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        require(len(data) == opened.st_size and len(data) <= limit
                and identity(os.fstat(fd)) == identity(opened)
                and identity(os.stat(name, dir_fd=parent_fd, follow_symlinks=False)) == identity(opened),
                'file_changed')
        return bytes(data), identity(opened)
    finally:
        os.close(fd)


def inventory(active_fd):
    names = sorted(os.listdir(active_fd))
    require(len(names) <= 4096, 'active_limit')
    return {name: identity(os.stat(name, dir_fd=active_fd, follow_symlinks=False))
            for name in names}


def coarse_counts(active_path, active_fd, stamps):
    # Reuse the publisher's exact retained-metadata exemption, not dotfile/pid guesses.
    exempt = nonexempt = unknown = held = 0
    for name in stamps:
        if name == '.admission.lock':
            continue
        path = active_path / name
        if support._is_retained_settlement_metadata(path):
            exempt += 1
            continue
        nonexempt += 1
        descriptor = None
        try:
            raw, stamp = read_at(active_fd, name, 1_000_000)
            require(stamp == stamps[name], 'active_changed')
            text = raw.decode('utf-8')
            if lane._is_reconciliation_hold(text):
                held += 1
            elif lane._is_json_lease(text):
                value = json.loads(text)
                if value.get('reconcile_unreleased') is True:
                    held += 1
                else:
                    # Lock availability is only a coarse observation, never settlement.
                    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                         dir_fd=active_fd)
                    require(identity(os.fstat(descriptor)) == stamp, 'active_changed')
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        held += 1
            else:
                unknown += 1
        except (OSError, ValueError, UnicodeError):
            unknown += 1
        finally:
            if descriptor is not None:
                os.close(descriptor)
    occupancy = lane.read_lane_occupancy(active_path)
    require(occupancy.status in {'known', 'held'}, 'occupancy_unknown')
    return {'nonexempt_entries': nonexempt, 'unknown_entries': unknown,
            'held_entries': held, 'retained_metadata_entries': exempt,
            'occupancy_status': occupancy.status, 'active_lanes': occupancy.active_count,
            'locked_lanes': occupancy.json_locked_count,
            'unlocked_lanes': occupancy.unlocked_count}


def validate_request(request):
    require(type(request) is dict and set(request) == {
        'schema', 'run_id', 'root', 'parent', 'binding', 'support_digest',
        'desired_policy_sha256', 'desired_policy_base64', 'original_metadata_sha256'},
        'request_shape')
    require(request['schema'] == REQUEST_SCHEMA, 'request_schema')
    import re
    for key in ('run_id', 'root', 'parent'):
        require(type(request[key]) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', request[key]),
                'request_identity')
    for key in ('support_digest', 'desired_policy_sha256', 'original_metadata_sha256'):
        require(type(request[key]) is str and re.fullmatch(r'[0-9a-f]{64}', request[key]), 'request_digest')
    delivery.validate_remote_lane_root(request['binding'])
    require(type(request['desired_policy_base64']) is str
            and len(request['desired_policy_base64']) <= 4 * LIMIT // 3 + 8, 'policy_size')
    raw = base64.b64decode(request['desired_policy_base64'], validate=True)
    require(0 < len(raw) <= LIMIT and hashlib.sha256(raw).hexdigest() == request['desired_policy_sha256'],
            'desired_policy_changed')
    return raw


def observe(request):
    """One shared/no-create original namespace observation; grants no repair."""
    lock_fd = None
    try:
        desired = validate_request(request)
        desired_critical = policy.critical_fingerprint(desired)
        binding = request['binding']
        initial_layout = delivery.observe_remote_lane_layout(binding)
        root = Path(binding['path'])
        with delivery.DirectoryChain(root / 'ext/active') as active, \
                delivery.DirectoryChain(root / 'orch/fabric') as target:
            visible = os.stat('.admission.lock', dir_fd=active.fd, follow_symlinks=False)
            require(stat.S_ISREG(visible.st_mode) and visible.st_nlink == 1
                    and visible.st_uid == os.getuid() and not visible.st_mode & 0o022,
                    'admission_lock_custody')
            lock_fd = os.open('.admission.lock', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                              dir_fd=active.fd)
            lock_stamp = identity(os.fstat(lock_fd))
            require(lock_stamp == identity(visible), 'admission_lock_changed')
            fcntl.flock(lock_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            before = inventory(active.fd)
            current_stamp = None
            try:
                os.stat('pools.yaml', dir_fd=target.fd, follow_symlinks=False)
            except FileNotFoundError:
                current = None
            else:
                current, current_stamp = read_at(target.fd, 'pools.yaml')
            if current is None:
                current_sha = current_critical = None
                comparison = 'ABSENT'
            else:
                current_sha = hashlib.sha256(current).hexdigest()
                current_critical = policy.critical_fingerprint(current)
                comparison = ('IDENTICAL' if current == desired else 'CRITICALLY_COMPATIBLE'
                              if current_critical == desired_critical else 'CRITICAL_MISMATCH')
            counts = coarse_counts(root / 'ext/active', active.fd, before)
            # Rejoin AFTER all blocking reads, including the last inventory/stat.
            require(inventory(active.fd) == before, 'active_changed')
            if current_stamp is None:
                try:
                    os.stat('pools.yaml', dir_fd=target.fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise Unavailable('policy_changed')
            else:
                require(identity(os.stat('pools.yaml', dir_fd=target.fd, follow_symlinks=False)) == current_stamp,
                        'policy_changed')
            active.verify(); target.verify()
            delivery.observe_remote_lane_layout(binding, expected=initial_layout)
            # Layout qualification can block too. Rejoin policy AFTER it, then
            # rejoin the held/name lock and exact namespace before publication.
            if current_stamp is None:
                try:
                    os.stat('pools.yaml', dir_fd=target.fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise Unavailable('policy_changed')
            else:
                require(identity(os.stat('pools.yaml', dir_fd=target.fd, follow_symlinks=False)) == current_stamp,
                        'policy_changed')
            require(identity(os.fstat(lock_fd)) == lock_stamp
                    and identity(os.stat('.admission.lock', dir_fd=active.fd, follow_symlinks=False)) == lock_stamp
                    and inventory(active.fd) == before, 'final_namespace_changed')
            active.verify(); target.verify()
            return {'schema': SCHEMA, 'state': 'OBSERVED', 'run_id': request['run_id'],
                    'root': request['root'], 'parent': request['parent'],
                    'original_metadata_sha256': request['original_metadata_sha256'],
                    'support_digest': request['support_digest'],
                    'desired_policy_sha256': request['desired_policy_sha256'],
                    'desired_critical_sha256': desired_critical,
                    'current_policy_sha256': current_sha, 'current_critical_sha256': current_critical,
                    'comparison': comparison, 'counts': counts,
                    'maintenance_authorized': False, 'admission_authorized': False,
                    'historical_release_ack': False, 'execution_replayed': False}
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        public = {'request_shape', 'request_schema', 'request_identity', 'request_digest',
                  'policy_size', 'desired_policy_changed', 'active_limit', 'active_changed',
                  'file_custody', 'file_changed', 'admission_lock_custody',
                  'admission_lock_changed', 'occupancy_unknown', 'policy_changed',
                  'final_namespace_changed'}
        reason = (str(exc).upper() if type(exc) is Unavailable and str(exc) in public else
                  'ADMISSION_BUSY' if isinstance(exc, BlockingIOError) else
                  'FIXED_COMPONENT_MISSING' if isinstance(exc, FileNotFoundError) else
                  'ACCESS_UNQUALIFIED' if isinstance(exc, PermissionError) else
                  'OBSERVATION_UNQUALIFIED')
        return {'schema': SCHEMA, 'state': 'UNAVAILABLE', 'reason': reason, 'maintenance_authorized': False,
                'admission_authorized': False, 'historical_release_ack': False,
                'execution_replayed': False}
    finally:
        if lock_fd is not None:
            os.close(lock_fd)


def original_request(run_id, root, parent, *, owner_ext=None):
    """Join original prelaunch metadata, not launch/result/lease authority.

    Native thread labels prevent accidental cross-parent reads; they do not
    authenticate a caller or grant SSH. Actual effects require the existing owner.
    No packet, result, controller output or broker database is read.
    """
    import re
    import artifact_reader
    import host_pick
    here = Path(__file__).resolve().parent if owner_ext is None else Path(owner_ext)
    for value in (run_id, root, parent):
        require(type(value) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value),
                'request_identity')
    require(os.environ.get('CODEX_THREAD_ID') in {root, parent}, 'original_parent_unqualified')
    state = here / 'state/remote_sub'
    blobs = {suffix: delivery.local_file(state / (run_id + suffix), 32768)
             for suffix in ('.request.json', '.request-launch.json', '.support.json')}
    requested, launched, manifest = [artifact_reader.strict_json(blobs[name])
        for name in ('.request.json', '.request-launch.json', '.support.json')]
    for row, schema in ((requested, 'mastermind.fabric_request_artifact.v1'),
                        (launched, 'mastermind.fabric_request_launch.v1')):
        require(type(row) is dict and row.get('schema') == schema and row.get('run_id') == run_id
                and row.get('root_id') == root and row.get('parent_run_id') == parent,
                'original_metadata_scope')
    request_sha = hashlib.sha256(blobs['.request.json']).hexdigest()
    require(launched.get('request_sha256') == request_sha
            and launched.get('packet_sha256') == requested.get('packet_sha256')
            and launched.get('state') == 'LAUNCH_ATTEMPT_RESERVED', 'original_metadata_changed')
    # Reservation is prelaunch metadata, NEVER proof of worker START or release.
    route = launched.get('route')
    require(type(route) is dict and type(route.get('HOST')) is str
            and route.get('MODE') in {'glm', 'glm-codex', 'minimax', 'minimax-codex', 'qwen',
                'grok', 'cursor', 'go-codex', 'codex-native', 'claude-native', 'oc-free'},
            'original_route_unqualified')
    registry = host_pick.load_registry()
    entry = registry.get(route['HOST'])
    binding = delivery.configured_remote_lane_root(route['HOST'], entry)
    require(binding is not None, 'fixed_remote_root_unconfigured')
    delivery.validate_remote_lane_root(binding)
    # The incumbent support_meta producer retains ONLY the flat file map;
    # its digest wraps that map separately through the bundle canonicalizer.
    # A release envelope or mixed form is not original manual metadata.
    require(type(manifest) is dict and frozenset(manifest) in support.SOURCE_GENERATIONS
            and 'pools.yaml' in manifest
            and all(type(v) is str and re.fullmatch(r'[0-9a-f]{64}', v)
                    for v in manifest.values()), 'original_support_manifest')
    desired = delivery.local_file(here.parent / 'orch/fabric/pools.yaml', LIMIT)
    desired_sha = hashlib.sha256(desired).hexdigest()
    require(desired_sha == manifest['pools.yaml'], 'original_policy_source_unavailable')
    support_digest = hashlib.sha256(support._canon_manifest(manifest)).hexdigest()
    frame = {name: hashlib.sha256(raw).hexdigest() for name, raw in blobs.items()}
    frame['configured_host'] = hashlib.sha256(artifact_reader.canonical(entry)).hexdigest()
    frame['policy'] = desired_sha
    metadata_sha = hashlib.sha256(artifact_reader.canonical(frame)).hexdigest()
    request = {'schema': REQUEST_SCHEMA, 'run_id': run_id, 'root': root, 'parent': parent,
        'binding': binding, 'support_digest': support_digest,
        'desired_policy_sha256': desired_sha,
        'desired_policy_base64': base64.b64encode(desired).decode('ascii'),
        'original_metadata_sha256': metadata_sha}
    validate_request(request)
    return request, frame, binding['ssh_alias']


def validate_response(raw, request):
    import artifact_reader
    require(type(raw) is bytes and 0 < len(raw) <= 16384, 'response_size')
    response = artifact_reader.strict_json(raw)
    require(type(response) is dict and response.get('schema') == SCHEMA, 'response_shape')
    flags = {'maintenance_authorized': False, 'admission_authorized': False,
             'historical_release_ack': False, 'execution_replayed': False}
    require(all(response.get(k) is v for k, v in flags.items()), 'response_authority')
    if response.get('state') == 'UNAVAILABLE':
        require(set(response) == {'schema', 'state', 'reason', *flags}
                and response['reason'] in {
                    'REQUEST_SHAPE', 'REQUEST_SCHEMA', 'REQUEST_IDENTITY', 'REQUEST_DIGEST',
                    'POLICY_SIZE', 'DESIRED_POLICY_CHANGED', 'ACTIVE_LIMIT', 'ACTIVE_CHANGED',
                    'FILE_CUSTODY', 'FILE_CHANGED', 'ADMISSION_LOCK_CUSTODY',
                    'ADMISSION_LOCK_CHANGED', 'OCCUPANCY_UNKNOWN', 'POLICY_CHANGED',
                    'FINAL_NAMESPACE_CHANGED', 'ADMISSION_BUSY', 'FIXED_COMPONENT_MISSING',
                    'ACCESS_UNQUALIFIED', 'OBSERVATION_UNQUALIFIED'}, 'response_shape')
        return response
    require(response.get('state') == 'OBSERVED' and set(response) == {
        'schema', 'state', 'run_id', 'root', 'parent', 'original_metadata_sha256',
        'support_digest', 'desired_policy_sha256', 'desired_critical_sha256',
        'current_policy_sha256', 'current_critical_sha256', 'comparison', 'counts', *flags},
        'response_shape')
    for key in ('run_id', 'root', 'parent', 'original_metadata_sha256', 'support_digest', 'desired_policy_sha256'):
        require(response[key] == request[key], 'response_scope')
    import re
    for key in ('desired_critical_sha256', 'current_policy_sha256', 'current_critical_sha256'):
        require((response[key] is None and key != 'desired_critical_sha256')
                or (type(response[key]) is str and re.fullmatch(r'[0-9a-f]{64}', response[key])),
                'response_digest')
    require(response['comparison'] in {'ABSENT', 'IDENTICAL', 'CRITICALLY_COMPATIBLE', 'CRITICAL_MISMATCH'},
            'response_comparison')
    require((response['comparison'] == 'ABSENT') == (response['current_policy_sha256'] is None
            and response['current_critical_sha256'] is None), 'response_comparison')
    require(response['comparison'] == 'ABSENT' or (response['current_policy_sha256'] is not None
            and response['current_critical_sha256'] is not None), 'response_comparison')
    desired = validate_request(request)
    require(response['desired_critical_sha256'] == policy.critical_fingerprint(desired),
            'response_desired_fingerprint')
    if response['comparison'] == 'IDENTICAL':
        require(response['current_policy_sha256'] == response['desired_policy_sha256']
                and response['current_critical_sha256'] == response['desired_critical_sha256'],
                'response_comparison')
    elif response['comparison'] == 'CRITICALLY_COMPATIBLE':
        require(response['current_policy_sha256'] != response['desired_policy_sha256']
                and response['current_critical_sha256'] == response['desired_critical_sha256'],
                'response_comparison')
    elif response['comparison'] == 'CRITICAL_MISMATCH':
        require(response['current_policy_sha256'] != response['desired_policy_sha256']
                and response['current_critical_sha256'] != response['desired_critical_sha256'],
                'response_comparison')
    counts = response['counts']
    require(type(counts) is dict and set(counts) == {'nonexempt_entries', 'unknown_entries',
        'held_entries', 'retained_metadata_entries', 'occupancy_status', 'active_lanes',
        'locked_lanes', 'unlocked_lanes'}, 'response_counts')
    require(counts['occupancy_status'] in {'known', 'held'} and all(
        type(v) is int and 0 <= v <= 4096 for k, v in counts.items() if k != 'occupancy_status'),
        'response_counts')
    require(counts['unknown_entries'] + counts['held_entries'] <= counts['nonexempt_entries'],
            'response_counts')
    return response


def source_hashes(*, owner_ext=None):
    here = Path(__file__).resolve().parent if owner_ext is None else Path(owner_ext)
    names = ('artifact_delivery.py', 'artifact_reader.py', 'lane_runtime.py',
             'support_bundle.py', 'fabric_policy_snapshot.py', 'support_policy_status.py')
    return {name: hashlib.sha256(delivery.local_file(here / name, 512 * 1024)).hexdigest()
            for name in names}


def code_for_request(request, *, expected_hash, expected_sources):
    """Same fixed read transport; old observation scopes are never widened.

    Verify the exact byte strings before embedding them. No caller source/path
    goes into executable code. Existing pure helper modules are compressed to
    retain the incumbent fixed command's argument bound.
    """
    import gzip
    validate_request(request)
    here = Path(__file__).resolve().parent
    names = ('artifact_delivery.py', 'artifact_reader.py', 'lane_runtime.py',
             'support_bundle.py', 'fabric_policy_snapshot.py', 'support_policy_status.py')
    require(type(expected_sources) is dict and set(expected_sources) == set(names)
            and expected_sources.get('support_policy_status.py') == expected_hash,
            'reader_sources_unqualified')
    sources = {name: delivery.local_file(here / name, 512 * 1024) for name in names}
    require({name: hashlib.sha256(raw).hexdigest() for name, raw in sources.items()}
            == expected_sources, 'reader_sources_changed')
    # The incumbent portable export deliberately excludes only the Mac native
    # owner-path mapping; all its no-follow custody/layout checks are retained.
    import ast
    delivery_text = sources['artifact_delivery.py'].decode('utf-8')
    parsed = ast.parse(delivery_text)
    lines = delivery_text.splitlines(keepends=True)
    exported = {}
    for node in parsed.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            exported[node.name] = ''.join(lines[node.lineno - 1:node.end_lineno])
    chain = exported['DirectoryChain']
    local_adapter = '            path = owner_path(path, HERE)'
    require(chain.count(local_adapter) == 1, 'portable_source_changed')
    chain = chain.replace(local_adapter, '            path = Path(path)', 1)
    portable = chain + '\n\n' + '\n\n'.join(exported[name] for name in (
        'validate_remote_lane_root', 'validate_remote_lane_layout',
        'observe_remote_lane_layout', 'verify_remote_lane_release'))
    remote_delivery = ('from pathlib import Path, PurePosixPath\n'
        'import os,stat,json,hashlib\nimport artifact_reader as reader\n'
        'def digest(raw): return hashlib.sha256(raw).hexdigest()\n'
        + portable)
    sources['artifact_delivery.py'] = remote_delivery.encode()
    package = {name.removesuffix('.py'): base64.b64encode(gzip.compress(raw, mtime=0)).decode()
               for name, raw in sources.items()}
    request_sha = hashlib.sha256(json.dumps(request, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    # -I -S is retained. Do not execute site.main, .pth or sitecustomize merely
    # to obtain the incumbent PyYAML dependency. Only fixed owned system package
    # locations are considered; missing/unqualified parser remains unavailable.
    bootstrap = '''import sys,os,stat,json,hashlib,base64,gzip,types,sysconfig,site
from pathlib import Path
sys.dont_write_bytecode=True
raw=sys.stdin.buffer.read(4194305)
assert len(raw)<=4194304
def unique(pairs):
 d={}
 for k,v in pairs:
  if k in d: raise ValueError('duplicate')
  d[k]=v
 return d
request=json.loads(raw,object_pairs_hook=unique)
assert hashlib.sha256(json.dumps(request,sort_keys=True,separators=(',',':')).encode()).hexdigest()==REQUEST_SHA
try:
 interpreter_site=str(Path(sys.executable).parent.parent/'lib'/('python%d.%d'%sys.version_info[:2])/'site-packages')
 candidates=list(dict.fromkeys([interpreter_site,sysconfig.get_path('purelib'),sysconfig.get_path('platlib'),*site.getsitepackages()]))
 found=False
 for value in candidates:
  if not value: continue
  base=Path(value); package=base/'yaml'
  if not os.path.lexists(package): continue
  for directory in [*reversed(package.parents),package]:
   st=directory.lstat()
   assert stat.S_ISDIR(st.st_mode) and st.st_uid in (0,os.getuid()) and not st.st_mode&0o022
  rows={p.name:(p.lstat().st_dev,p.lstat().st_ino,p.lstat().st_mode,p.lstat().st_mtime_ns,p.lstat().st_ctime_ns) for p in package.iterdir() if p.suffix in ('.py','.so')}
  assert rows and len(rows)<=64
  for name in rows:
   st=(package/name).lstat()
   assert stat.S_ISREG(st.st_mode) and st.st_uid in (0,os.getuid()) and not st.st_mode&0o022 and st.st_nlink==1
  sys.path.append(str(base))
  import yaml
  assert Path(yaml.__file__).parent==package
  assert rows=={p.name:(p.lstat().st_dev,p.lstat().st_ino,p.lstat().st_mode,p.lstat().st_mtime_ns,p.lstat().st_ctime_ns) for p in package.iterdir() if p.suffix in ('.py','.so')}
  found=True
  break
 assert found
 modules={}
 for name in SOURCES:
  module=types.ModuleType(name);module.__file__='/fixed-read-source/'+name+'.py'
  sys.modules[name]=module;modules[name]=module
 for name in ['artifact_reader','artifact_delivery','lane_runtime','support_bundle','fabric_policy_snapshot','support_policy_status']:
  exec(compile(gzip.decompress(base64.b64decode(SOURCES[name])),modules[name].__file__,'exec'),modules[name].__dict__)
 report=modules['support_policy_status'].observe(request)
except Exception:
 report={'schema':'mastermind.support_policy_status.v1','state':'UNAVAILABLE','reason':'OBSERVATION_UNQUALIFIED','maintenance_authorized':False,'admission_authorized':False,'historical_release_ack':False,'execution_replayed':False}
print(json.dumps(report,sort_keys=True,separators=(',',':')))
'''
    code = 'REQUEST_SHA=' + repr(request_sha) + '\nSOURCES=' + repr(package) + '\n' + bootstrap
    require(len(code.encode()) <= 120000, 'reader_command_size')
    return code


def inspect_original(run_id, root, parent, *, qualified_sources, owner_ext=None):
    """Explicit single original-owner read, with local same-operation retention.

    Callers need their actual existing transport grant. No worker, lease, refresh
    or maintenance action is implied. A retained intent is never replayed.
    """
    import artifact_reader
    import provider_outcome
    here = Path(__file__).resolve().parent if owner_ext is None else Path(owner_ext)
    sources = source_hashes(owner_ext=here)
    require(sources == qualified_sources, 'reviewed_sources_changed')
    request, frame, alias = original_request(run_id, root, parent, owner_ext=here)
    intent_path = here / 'state/remote_sub' / (run_id + '.support-policy-status.intent.json')
    result_path = here / 'state/remote_sub' / (run_id + '.support-policy-status.result.json')
    closed = {'schema': SCHEMA, 'state': 'PRIOR_OR_UNKNOWN_READ',
              'maintenance_authorized': False, 'admission_authorized': False,
              'historical_release_ack': False, 'execution_replayed': False}
    if os.path.lexists(intent_path) or os.path.lexists(result_path):
        return closed
    # Existing per-operation artifact writer only: no directory creation or new ledger.
    provider_outcome.write_new(intent_path, {'schema': 'mastermind.support_policy_read_intent.v1',
        'run_id': run_id, 'root': root, 'parent': parent,
        'original_metadata_sha256': request['original_metadata_sha256'], 'reader_sources': sources})
    def current():
        again, current_frame, current_alias = original_request(run_id, root, parent, owner_ext=here)
        require(again == request and current_frame == frame and current_alias == alias
                and source_hashes(owner_ext=here) == sources, 'original_sources_changed')
    try:
        current()
        raw = delivery.transport(alias, request,
            observer_source_hash=sources['support_policy_status.py'], current_sources_sha256=sources)
        report = validate_response(raw, request)
        current()
        provider_outcome.write_new(result_path, report)
        current()
        return report
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        # Intent retained. No retry, another run ID, fallback host or acceptance.
        return closed
