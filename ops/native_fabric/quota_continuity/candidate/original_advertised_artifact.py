"""Exact source-admitted recovery of one advertised artifact (read-only).

This module adds one prospective, closed-scope read under the incumbent
``artifact_delivery`` transport. It recovers bytes that an original run
already advertised in its own retained stdout. It does not create, accept or
re-attribute any outcome, does not attest the original producer, and never
mutates the original operation, its retained evidence, or any ledger, lease,
controller or process state.

Design constraints held by this source:

* The scope is one exact constant. The caller, the path, the advertised
  digest, the host and the account are not configurable.
* The local half qualifies the CURRENT retained evidence of that original run
  (stdout, log, process receipt, request packet, provider outcome), pins every
  one of those bytes by digest, and re-reads them before and after the single
  transport and around publication.
* The remote half is this module's own bytes, executed once by the incumbent
  transport. It walks the exact absolute path from ``/`` with ``O_NOFOLLOW``
  directory descriptors, reads one regular file with one bounded read, and
  returns bytes only when they match the advertised digest.
* Every failure is a fixed, typed refusal. No exception text, private path,
  provider detail or account value crosses a boundary.

The incumbent imports are delayed into local functions so that this exact
source is also a self-contained remote program.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import sys
import time

SCHEMA = 'mastermind.source_admitted_advertised_artifact_read.v1'
RECEIPT_SCHEMA = 'mastermind.source_admitted_advertised_artifact_recovery_receipt.v1'
MODULE_NAME = 'original_advertised_artifact.py'

# The remote account home is a fixed expectation, never an environment value.
REMOTE_HOME = '/home/longr'

MAX_FILE = 262144
MAX_REQUEST = 16384
MAX_RESPONSE = 1048576
MAX_LOCAL = 4194304

RUN_ID = 'mm-u0-revision-lens-component-20261105-root'
ROOT_ID = '01a1333c-a475-7052-95a8-72c623fb12e1'
PARENT_ID = '01a1333c-a475-7052-95a8-72c623fb12e1'
DESTINATION = ('/Volumes/Mastermind/evidence/market-memory-20261012-01a1333c/'
               'revision-lens-component-20261105/advertised-patch-recovery-v1')
HOST = 'ubuntu1'
ADVERTISED_PATH = ('/home/longr/lanes/scratch/p15t1s2-revision-lens-20261105-01/'
                   'market_memory_revision_lens.patch')
ADVERTISED_SHA256 = '0337b34f526a9c155d2c5ac3b52485a6d95b1abf88287fc767f6f8930083a3bd'
STDOUT_SHA256 = 'b8a7cb1e01bbb384026a39beafd0ff1eee8d4fa850bdb6c1b96a714a034ca63e'

# The exact closed scope. The request is this object and nothing else.
SCOPE = {
    'schema': SCHEMA,
    'run_id': RUN_ID,
    'root': ROOT_ID,
    'parent': PARENT_ID,
    'host': HOST,
    'stdout_sha256': STDOUT_SHA256,
    'path': ADVERTISED_PATH,
    'sha256': ADVERTISED_SHA256,
}

# The CURRENT retained local evidence of that run, pinned byte for byte.
EVIDENCE_SHA256 = {
    'stdout': STDOUT_SHA256,
    'process': '862ad6d0d358633fbe82773b4bfc71c572de838047b3487904c6d2796d3110a6',
    'log': '4b8c4211b8fecad7d458e04b6d37d6127ea918ff2e02eedb293db6284c527048',
    'packet': '4eab8898d2d2528e7139e074a196f2cc9897c6a65644e56a0da5030e6342b3ea',
    'provider': '11b26c9a061e801bcd8ec64f391810ba0562eee6bb17381bcd5d7a0f4b5b7cb6',
}

# Per-evidence read bounds. The pinned digests remain the authority.
LOCAL_LIMITS = {
    'stdout': 1048576,
    'process': 262144,
    'log': 1048576,
    'packet': MAX_LOCAL,
    'provider': 65536,
}

PROVIDER_MODE = 'minimax'
PROVIDER_MODEL = 'MiniMax-M3'

ALIAS_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
HEX_RE = re.compile(r'[0-9a-f]{64}\Z')
LEASE_RE = re.compile(r'[0-9a-f]{12}\Z')
ACCOUNT_RE = re.compile(r'[A-Za-z0-9_.:-]{1,128}\Z')
LOG_RE = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z \[remote_sub id=(?P<rid>[A-Za-z0-9][A-Za-z0-9_.:-]{0,127})'
                    r' host=(?P<host>[A-Za-z0-9_.-]+)\] (?P<event>.*)')

# Closed remote refusal reasons. Nothing else may cross the transport.
REMOTE_REASONS = frozenset({
    'missing_at_read',
    'home_unavailable',
    'home_mismatch',
    'path_outside_home',
    'path_invalid',
    'directory_owner_or_mode',
    'directory_chain_changed',
    'file_owner_mode_or_type',
    'size_limit',
    'changed_during_read',
    'content_digest_mismatch',
    'filesystem_refused',
})


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    # Identical to the incumbent reader's canonical form.
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate_key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_mode, info.st_uid, info.st_nlink)


def _delivery():
    # Delayed on purpose: this source is also the remote program.
    import artifact_delivery
    return artifact_delivery


def _read_local(path, limit):
    return _delivery().local_file(path, limit)


def validate_request(request):
    """The request is the closed scope; no field is configurable."""
    if type(request) is not dict or set(request) != set(SCOPE) or request != SCOPE:
        raise ValueError('advertised_request_mismatch')
    return request


def _require_native_caller(request):
    """Only the original parent/root context may drive this recovery."""
    current = os.environ.get('CODEX_THREAD_ID')
    if current != request['parent'] or current != request['root']:
        raise ValueError('advertised_native_caller_mismatch')
    orchestrator = os.environ.get('POOL_ORCHESTRATOR_ID', request['root'])
    if orchestrator != request['root']:
        raise ValueError('advertised_native_orchestrator_mismatch')


def _status(run_id):
    import fabric_task
    try:
        return fabric_task.inspect_run(run_id)
    except fabric_task.FabricTaskError as exc:
        raise ValueError('advertised_run_status_unavailable') from exc


def _status_qualified(status, request):
    if (type(status) is not dict
            or status.get('run_id') != request['run_id']
            or status.get('state') != 'TERMINAL'
            or type(status.get('rc')) is not int or status.get('rc') != 0
            or status.get('signal') != 'ok'
            or status.get('result_available') is not True
            or status.get('root_id') != request['root']
            or status.get('parent_run_id') != request['parent']
            or status.get('acceptance_state') not in ('ACCEPTED', 'NOT_ACCEPTED')):
        raise ValueError('advertised_run_status_unqualified')
    return status


def _evidence_paths(run_id):
    """The incumbent's fixed local evidence locations for one run."""
    here = _delivery().HERE
    return {
        'stdout': here / 'lanes' / (run_id + '.remote.stdout'),
        'process': here / 'state' / 'remote_sub' / (run_id + '.process.jsonl'),
        'provider': here / 'state' / 'remote_sub' / (run_id + '.provider.json'),
        'log': here / 'state' / 'remote_sub' / (run_id + '.log'),
        'packet': here / 'state' / 'remote_sub' / (run_id + '.request.packet'),
    }


def _evidence_bytes(run_id):
    paths = _evidence_paths(run_id)
    raw = {}
    for name in sorted(paths):
        raw[name] = _read_local(paths[name], LOCAL_LIMITS[name])
    return raw


def _process_receipt(raw, stdout, request):
    """One ordinary worker process receipt; never an artifact production."""
    delivery = _delivery()
    try:
        rows = [strict_json(raw)]
    except ValueError:
        rows = []
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise ValueError('advertised_process_not_utf8') from exc
        for line in text.splitlines():
            if not line.strip():
                continue
            rows.append(strict_json(line))
    if not rows or any(type(row) is not dict for row in rows):
        raise ValueError('advertised_process_shape')
    if any('artifact_production' in row for row in rows):
        raise ValueError('advertised_process_artifact_production_unexpected')
    selected = [row for row in rows if row.get('label') == request['run_id']]
    if len(selected) != 1:
        raise ValueError('advertised_process_receipt_count')
    delivery.validate_capsule_process(canonical(selected[0]), stdout, request['run_id'])
    return selected[0]


def _provider_qualified(raw, request):
    provider = strict_json(raw)
    if type(provider) is not dict:
        raise ValueError('advertised_provider_shape')
    expected = {
        'schema': 'mastermind.provider_outcome.v1',
        'run_id': request['run_id'],
        'root_id': request['root'],
        'host': request['host'],
        'provider': PROVIDER_MODE,
        'model': PROVIDER_MODEL,
        'stdout_sha256': request['stdout_sha256'],
        'kind': 'success',
        'cli_subtype': 'success',
        'cli_terminal_reason': 'completed',
    }
    for key, value in expected.items():
        if provider.get(key) != value:
            raise ValueError('advertised_provider_mismatch')
    if (type(provider.get('command_rc')) is not int or provider.get('command_rc') != 0
            or type(provider.get('cli_command_rc')) is not int or provider.get('cli_command_rc') != 0
            or provider.get('complete_event_capture') is not True
            or provider.get('initial_rejection') is not False
            or provider.get('permission_denials_role') != 'none'
            or type(provider.get('permission_denial_count')) is not int
            or provider.get('permission_denial_count') != 0
            or provider.get('api_status') is not None
            or type(provider.get('lease_id')) is not str
            or LEASE_RE.fullmatch(provider['lease_id']) is None
            or type(provider.get('account')) is not str
            or ACCOUNT_RE.fullmatch(provider['account']) is None):
        raise ValueError('advertised_provider_mismatch')
    return provider


def _log_events(raw, request):
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError('advertised_log_not_utf8') from exc
    events = []
    for line in text.splitlines():
        match = LOG_RE.fullmatch(line)
        if match is None:
            continue
        if match.group('rid') != request['run_id'] or match.group('host') != request['host']:
            raise ValueError('advertised_log_identity')
        events.append(match.group('event'))
    if not events:
        raise ValueError('advertised_log_shape')
    return events


def _log_qualified(events, request):
    """One launch attempt, one lease, one support witness, one terminal DONE."""
    rid = request['run_id']

    def once(prefix, exact=None):
        found = [event for event in events if event.startswith(prefix)]
        if len(found) != 1 or (exact is not None and found[0] != exact):
            raise ValueError('advertised_log_event_count')
        return found[0]

    lease = once('LEASE_OK ', 'LEASE_OK pool=' + PROVIDER_MODE)
    support = once('SUPPORT_VERSION_READY ')
    if re.fullmatch(r'SUPPORT_VERSION_READY digest=[0-9a-f]{64} policy=[0-9a-f]{64}', support) is None:
        raise ValueError('advertised_log_support_witness')
    launch = once('LAUNCH ')
    if re.fullmatch(r'LAUNCH stdout=lanes_' + re.escape(rid)
                    + r'\.stdout rc_file=ext/lanes_' + re.escape(rid) + r'\.rc cwd=\S+',
                    launch) is None:
        raise ValueError('advertised_log_launch_shape')
    attempt = once('LAUNCH_ATTEMPT ', 'LAUNCH_ATTEMPT attempt=1')
    remote_done = once('REMOTE_DONE ', 'REMOTE_DONE rc=0')
    done = once('DONE ', 'DONE rc=0 signal=ok')
    order = [events.index(event) for event in (lease, support, launch, attempt, remote_done, done)]
    if order != sorted(order):
        raise ValueError('advertised_log_event_order')
    for event in events:
        # Only an effect-unknown or held settlement contradicts a clean
        # terminal DONE. A transient controller poll line does not.
        lowered = event.lower()
        if ('effect_unknown' in lowered or 'lease_preserved' in lowered
                or 'remote_artifacts_preserved' in lowered):
            raise ValueError('advertised_log_uncertainty_marker')
    return {'lease': lease, 'support': support, 'launch': launch, 'attempt': attempt,
            'remote_done': remote_done, 'done': done}


def _advertisement(text, request):
    """The retained stdout names this exact backticked path and adjacent SHA."""
    path_token = '`' + request['path'] + '`'
    sha_token = '`' + request['sha256'] + '`'
    if text.count(path_token) != 1:
        raise ValueError('advertised_advertisement_path_count')
    if text.count(sha_token) != 1:
        raise ValueError('advertised_advertisement_digest_count')
    lines = text.splitlines()
    index = next(index for index, line in enumerate(lines) if path_token in line)
    following = next((line for line in lines[index + 1:] if line.strip()), '')
    if sha_token not in following:
        raise ValueError('advertised_advertisement_digest_not_adjacent')
    return {'path': request['path'], 'sha256': request['sha256']}


def _registry(request):
    """The current fixed receiver registry; the caller never names a host."""
    raw = _read_local(_delivery().HERE / 'hosts.json', 65536)
    registry = strict_json(raw)
    entry = registry.get(request['host']) if type(registry) is dict else None
    alias = entry.get('ssh_alias') if type(entry) is dict else None
    allowed = entry.get('allowed_modes') if type(entry) is dict else None
    if (type(entry) is not dict or type(allowed) is not list
            or PROVIDER_MODE not in allowed
            or type(alias) is not str or ALIAS_RE.fullmatch(alias) is None):
        raise ValueError('advertised_registry_mismatch')
    return raw, alias


def qualify(request):
    """Qualify the CURRENT retained evidence of the original run, or refuse."""
    validate_request(request)
    _require_native_caller(request)
    status = _status_qualified(_status(request['run_id']), request)
    raw = _evidence_bytes(request['run_id'])
    for name in sorted(raw):
        if digest(raw[name]) != EVIDENCE_SHA256[name]:
            raise ValueError('advertised_evidence_changed_' + name)
    process = _process_receipt(raw['process'], raw['stdout'], request)
    provider = _provider_qualified(raw['provider'], request)
    events = _log_events(raw['log'], request)
    settlement = _log_qualified(events, request)
    try:
        text = raw['stdout'].decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError('advertised_stdout_not_utf8') from exc
    advertisement = _advertisement(text, request)
    registry_raw, alias = _registry(request)
    source = _qualified_module_source(_delivery().ADVERTISED_RECOVERY_SOURCE_SHA256)
    return {
        'evidence_sha256': {name: digest(raw[name]) for name in sorted(raw)},
        'registry_sha256': digest(registry_raw),
        'recovery_source_sha256': digest(source),
        'ssh_alias': alias,
        'advertisement': advertisement,
        'settlement_events': settlement,
        'original_projection': status,
        'process_label': process.get('label'),
        'lease_id': provider.get('lease_id'),
        'account': provider.get('account'),
        'provider': provider.get('provider'),
        'model': provider.get('model'),
        'historical_joint_seal': 'NOT_RETAINED',
        'authority': 'source-admitted current task-owner intent; not producer attestation',
    }


def validate_response(raw, request):
    """One bounded, strictly bound remote answer for the exact request."""
    if len(raw) > MAX_RESPONSE:
        raise ValueError('advertised_response_limit')
    value = strict_json(raw)
    if (type(value) is not dict or set(value) != {'schema', 'request_sha256', 'files'}
            or value.get('schema') != SCHEMA
            or value.get('request_sha256') != digest(canonical(request))
            or type(value.get('files')) is not list or len(value['files']) != 1):
        raise ValueError('advertised_response_identity')
    item = value['files'][0]
    if type(item) is not dict or item.get('path') != request['path']:
        raise ValueError('advertised_response_path')
    if item.get('status') == 'RETRIEVED':
        if set(item) != {'path', 'status', 'bytes', 'sha256', 'data_base64', 'observed_file'}:
            raise ValueError('advertised_response_file_shape')
        try:
            data = base64.b64decode(item['data_base64'], validate=True)
        except (TypeError, ValueError) as exc:
            raise ValueError('advertised_response_encoding') from exc
        if (type(item.get('bytes')) is not int or item['bytes'] != len(data)
                or len(data) > MAX_FILE
                or type(item.get('sha256')) is not str or HEX_RE.fullmatch(item['sha256']) is None
                or digest(data) != item['sha256']
                or item['sha256'] != request['sha256']):
            raise ValueError('advertised_response_integrity')
        observed = item['observed_file']
        if (type(observed) is not dict
                or set(observed) != {'device', 'inode', 'size', 'mtime_ns', 'ctime_ns',
                                     'mode', 'uid', 'links'}
                or any(type(number) is not int or number < 0 for number in observed.values())):
            raise ValueError('advertised_response_metadata')
        return ({key: item[key] for key in item if key != 'data_base64'}, data)
    if (set(item) == {'path', 'status', 'reason'}
            and item.get('status') in ('NOT_FOUND', 'UNAVAILABLE')
            and item.get('reason') in REMOTE_REASONS):
        return (dict(item), None)
    raise ValueError('advertised_response_status')


def _failure_label(exc):
    """A closed local label. Exception text never crosses a boundary."""
    if isinstance(exc, PermissionError) or (isinstance(exc, OSError) and exc.errno in (1, 13)):
        return 'advertised_local_permission_refused'
    if isinstance(exc, ValueError) and str(exc).startswith('advertised_'):
        return str(exc)
    return 'advertised_local_failure_unclassified'


def _module_source():
    """The exact current bytes of this module, read through the incumbent."""
    delivery = _delivery()
    # The generation's single module path is authoritative. A failed or denied
    # read never falls back to another source copy or an alternate carrier.
    return delivery.advertised_recovery_source()


def _qualified_module_source(expected_hash):
    """Bind one byte string to the incumbent's protected generation hash."""
    if (type(expected_hash) is not str or HEX_RE.fullmatch(expected_hash) is None
            or expected_hash != _delivery().ADVERTISED_RECOVERY_SOURCE_SHA256):
        raise ValueError('advertised_remote_source_hash_unqualified')
    raw = _module_source()
    if digest(raw) != expected_hash:
        raise ValueError('advertised_remote_source_changed')
    return raw


def code_for_request(request, *, expected_hash):
    """Transport exactly the checked bytes; never reread or fall back."""
    validate_request(request)
    return _qualified_module_source(expected_hash).decode('utf-8')


def collect(run_id, destination):
    """Read the one advertised artifact under the closed scope, once."""
    import sqlite3
    import subprocess
    request = dict(SCOPE)
    if run_id != request['run_id']:
        raise ValueError('advertised_run_id_mismatch')
    if str(destination) != DESTINATION:
        raise ValueError('advertised_destination_mismatch')
    evidence = qualify(request)
    delivery = _delivery()
    chain = delivery.reserve_destination(destination)
    receipt = {
        'schema': RECEIPT_SCHEMA,
        'request': request,
        'evidence': evidence,
        'destination': str(destination),
        'state': 'READ_PENDING',
        'files': [],
        'recovery_basis': 'source_admitted_current_read',
        'advertised_digest_matched': False,
        'historical_producer_attestation': False,
        'historical_joint_seal': 'NOT_RETAINED',
        'execution_replayed': False,
        'outcome_accepted': False,
        'original_operation_mutated': False,
        'read_transport_state': 'MAY_START_AFTER_THIS_INTENT',
        'provenance': ('Current bytes read from the exact source-admitted advertised path; '
                       'no historical producer attestation, no outcome acceptance and no '
                       'change to the original operation.'),
    }

    def unchanged():
        if qualify(request) != evidence:
            raise ValueError('advertised_sources_changed')

    try:
        delivery.write_exclusive(chain.fd, 'request.json', canonical(receipt))
        try:
            unchanged()
            chain.verify()
            receipt['read_transport_state'] = 'ATTEMPTED_UNCONFIRMED'
            raw = delivery.transport(evidence['ssh_alias'], request)
            receipt['read_transport_state'] = 'RESPONSE_RECEIVED'
            item, data = validate_response(raw, request)
            unchanged()
            chain.verify()
            entry = dict(item)
            if data is not None:
                name = request['path'].rsplit('/', 1)[1]
                if name in {'request.json', 'receipt.json'}:
                    raise ValueError('advertised_reserved_output_name')
                delivery.write_exclusive(chain.fd, name, data)
                entry['local_name'] = name
            receipt['files'].append(entry)
            delivery.verify_delivered(chain, receipt['files'])
            receipt['state'] = 'COMPLETE' if entry.get('status') == 'RETRIEVED' else 'UNAVAILABLE'
            receipt['advertised_digest_matched'] = receipt['state'] == 'COMPLETE'
        except (OSError, ValueError, TypeError, KeyError, RecursionError,
                subprocess.SubprocessError, sqlite3.Error) as exc:
            # A lost or failed read is never retried; the exclusive request
            # record above preserves the attempted intent.
            receipt['state'] = 'UNAVAILABLE'
            receipt['advertised_digest_matched'] = False
            receipt['failure_diagnostic'] = _failure_label(exc)
            if receipt['read_transport_state'] == 'ATTEMPTED_UNCONFIRMED':
                receipt['read_transport_state'] = 'FAILED_UNCONFIRMED'
        receipt['observed_at_epoch'] = time.time()
        delivery.publish_receipt(chain, receipt, {'paths': [request['path']]}, verify_source=unchanged)
        return receipt
    finally:
        chain.close()


# --------------------------------------------------------------------------
# Remote half. These functions are the whole remote program.
# --------------------------------------------------------------------------

def _current_home():
    """The authenticated account home. HOME is never consulted."""
    return pwd.getpwuid(os.getuid()).pw_dir


def _remote_unavailable(request, reason):
    return {'path': request['path'], 'status': 'UNAVAILABLE', 'reason': reason}


def remote_read(request):
    """Read the exact advertised file once, from /, without following links."""
    if type(request) is not dict or request != SCOPE:
        raise ValueError('advertised_remote_scope_mismatch')
    path = request['path']
    expected = request['sha256']
    try:
        home = _current_home()
    except (KeyError, OSError):
        return _remote_unavailable(request, 'home_unavailable')
    if home != REMOTE_HOME:
        return _remote_unavailable(request, 'home_mismatch')
    if not path.startswith(REMOTE_HOME + '/'):
        return _remote_unavailable(request, 'path_outside_home')
    components = path.split('/')[1:]
    if (not components or any(component in ('', '.', '..') for component in components)
            or any('/' in component for component in components)):
        return _remote_unavailable(request, 'path_invalid')
    fds = []
    edges = []
    try:
        fds.append(os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
        root_info = os.fstat(fds[0])
        if (not stat.S_ISDIR(root_info.st_mode)
                or root_info.st_uid not in (0, os.getuid()) or root_info.st_mode & 0o022):
            return _remote_unavailable(request, 'directory_owner_or_mode')
        for component in components[:-1]:
            parent = fds[-1]
            fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            fds.append(fd)
            info = os.fstat(fd)
            if (not stat.S_ISDIR(info.st_mode)
                    or info.st_uid not in (0, os.getuid())
                    or info.st_mode & 0o022):
                return _remote_unavailable(request, 'directory_owner_or_mode')
            edges.append((component, len(fds) - 2, info))
        parent = fds[-1]
        name = components[-1]
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        fds.append(fd)
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.getuid()
                or before.st_nlink != 1
                or before.st_mode & 0o022):
            return _remote_unavailable(request, 'file_owner_mode_or_type')
        if before.st_size > MAX_FILE:
            return _remote_unavailable(request, 'size_limit')
        budget = MAX_FILE + 1
        chunks = []
        while budget:
            chunk = os.read(fd, min(65536, budget))
            if not chunk:
                break
            chunks.append(chunk)
            budget -= len(chunk)
        raw = b''.join(chunks)
        if len(raw) > MAX_FILE:
            return _remote_unavailable(request, 'size_limit')
        after = os.fstat(fd)
        named = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (identity(before) != identity(after)
                or identity(before) != identity(named)
                or len(raw) != before.st_size):
            return _remote_unavailable(request, 'changed_during_read')
        for component, parent_index, info in edges:
            held = os.fstat(fds[parent_index + 1])
            visible = os.stat(component, dir_fd=fds[parent_index], follow_symlinks=False)
            if identity(info) != identity(held) or identity(info) != identity(visible):
                return _remote_unavailable(request, 'directory_chain_changed')
        if identity(root_info) != identity(os.fstat(fds[0])):
            return _remote_unavailable(request, 'directory_chain_changed')
        if digest(raw) != expected:
            return _remote_unavailable(request, 'content_digest_mismatch')
        return {
            'path': path,
            'status': 'RETRIEVED',
            'bytes': len(raw),
            'sha256': digest(raw),
            'data_base64': base64.b64encode(raw).decode(),
            'observed_file': {
                'device': before.st_dev,
                'inode': before.st_ino,
                'size': before.st_size,
                'mtime_ns': before.st_mtime_ns,
                'ctime_ns': before.st_ctime_ns,
                'mode': stat.S_IMODE(before.st_mode),
                'uid': before.st_uid,
                'links': before.st_nlink,
            },
        }
    except FileNotFoundError:
        return _remote_unavailable(request, 'missing_at_read')
    except (OSError, ValueError):
        return _remote_unavailable(request, 'filesystem_refused')
    finally:
        for fd in reversed(fds):
            try:
                os.close(fd)
            except OSError:
                pass


def _is_remote_program():
    """The remote program is the incumbent transport's isolated interpreter."""
    return (sys.flags.isolated == 1 and sys.flags.no_site == 1
            and bool(sys.argv) and sys.argv[0] == '-c')


def remote_main():
    """One request on stdin, one bounded answer on stdout."""
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST:
            raise SystemExit(65)
        if not _is_remote_program():
            raise SystemExit(65)
        request = strict_json(raw)
        if type(request) is not dict or request != SCOPE:
            raise SystemExit(65)
        result = remote_read(request)
        answer = {'schema': SCHEMA, 'request_sha256': digest(canonical(request)), 'files': [result]}
        sys.stdout.buffer.write(canonical(answer))
        sys.stdout.buffer.flush()
    except SystemExit:
        raise
    except (OSError, ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        raise SystemExit(65)


if __name__ == "__main__":
    remote_main()
