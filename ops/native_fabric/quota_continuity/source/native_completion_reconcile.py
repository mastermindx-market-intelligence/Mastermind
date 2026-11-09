"""Exact retained completion recovery through the existing ledger owner.

No launch, retry, cancellation, lease mutation, fabricated DONE, or acceptance.
Only explicit reconcile(..., apply=True) may call incumbent accounting owner.
Parent must confirm the failed controller has exited before that one action.
"""
from __future__ import annotations
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import pool_ledger

HERE = Path(__file__).resolve().parent
RUN_ID = 'prophet-r6-b06-clock-final-review-r2-01a11e89'
ROOT_ID = '01a11e89-b35d-7a81-9404-5fce2c6170cb'
LEASE_ID = '01bca183cf1a'
HOST = 'ubuntu2'
MODE = 'grok'
MODEL = 'grok-4.6'  # requested model, never serving attestation
TERMINAL_SHA = 'fadcfd85387f7fa91d94b21aa7a7f0d301291b639987e82ed6d631c35b336a80'
LOG_SHA = '179417b5c7edd32c9d104342fbaf972ba0757a818ed445205623952062cfc2a4'
STDOUT_SHA = '460f00968e7dcc34c9dcee7105d28da02a619be4006b6228d7913f1653d4e9c3'
SUPPORT_SHA = 'a811c5a16d7795a97c9bb639c7c4efb69c98ccf4676b11edbe9932e105be0de2'
OUTPUT_BYTES = 4610
GMI_RUN_ID = 'gmi-econ-chunk-test-20261010-astra-001'
GMI_ROOT_ID = 'theme-fabric-e2e-20261008-sol-001'
GMI_OUTPUT_BYTES = 11967
GMI_PACKET_PATH = Path('/Users/chriswong/agent-evidence/theme-fabric-e2e-20261008-sol-001/astra-takeover-20261010/econ-chunk-test-packet.md')
KNOWN_RUNS = frozenset((RUN_ID, GMI_RUN_ID))


def _verified_gmi_record(run_id, root):
    require(run_id == GMI_RUN_ID and root == GMI_ROOT_ID, 'run/root binding mismatch')
    packet_sha = 'c307ba6aac2cc6c6e13144bcff29ab577d58fdc0efe7d5b0db1d3e438298b66f'
    _pinned(GMI_PACKET_PATH, packet_sha, 1048576)
    log_sha = '4bb5a378e01e48def8eba490388d340cdabd43f1d60a0d25228a87beeed1a370'
    process_sha = 'a5785d6c5bbe66b99ffac104bb1b2a0901afa389e00d4218a25b217b004a109f'
    stdout_sha = '90117751a3af42fe14eb8ac56ee4a509b70b10476cb874bb286c50bb87b473e1'
    support_sha = '23c635d30efc79c0a73b79bc94a36c936a6d9b437a899f089e78840dcbe8da5f'
    log = _pinned(HERE/'state/remote_sub'/(run_id+'.log'), log_sha, 1048576).decode('utf-8')
    require(not any(t in log for t in ('LEASE_PRESERVED effect_unknown=1',
            'REMOTE_EFFECT_UNKNOWN', 'signal=effect_unknown', 'RESULT_UNAVAILABLE')),
            'uncertain or unavailable effects are sticky')
    require(' REMOTE_DONE rc=0' in log and ' REMOTE_CLEANED transport=1 receipt_saved=1 usage_saved=0' in log
            and ' DONE rc=' not in log and 'SUPPORT_VERSION_READY digest='+support_sha in log,
            'not the reviewed incomplete-controller result')
    raw = _pinned(HERE/'state/remote_sub'/(run_id+'.process.jsonl'), process_sha, 1048576)
    require(len(raw.splitlines()) == 1, 'ambiguous process receipt')
    receipt = json.loads(raw)
    require(receipt.get('schema') == 'mastermind.local_owned_process_receipt.v1'
            and receipt.get('label') == run_id and receipt.get('pid') == receipt.get('pgid') == 665354
            and receipt.get('started_at') == '2026-10-11T00:04:40.056Z'
            and receipt.get('ended_at') == '2026-10-11T00:16:31.352Z'
            and type(receipt.get('returncode')) is int and receipt['returncode'] == 0
            and receipt.get('timed_out') is False and receipt.get('runtime_failure_code') is None,
            'original process completion not proven')
    cleanup = receipt.get('cleanup', {})
    require(all(cleanup.get(k) is True for k in ('census_proven','identity_verified',
            'stdout_capture_complete','stderr_capture_complete','stdin_delivery_complete')),
            'process cleanup/capture not proven')
    require(type(cleanup.get('residual_count')) is int and cleanup['residual_count'] == 0
            and cleanup.get('reason') == 'normal_completion' and cleanup.get('status') == 'not_needed'
            and all(cleanup.get(k) is None for k in ('error_code','stdout_capture_error',
                                                   'stderr_capture_error','stdin_delivery_error')),
            'process residual or capture error')
    require(receipt.get('stdout_bytes') == GMI_OUTPUT_BYTES and receipt.get('stderr_bytes') == 113
            and receipt.get('stdout_truncated') is False and receipt.get('stderr_truncated') is False,
            'process output incomplete')
    require(len(_pinned(HERE/'lanes'/(run_id+'.remote.stdout'), stdout_sha, 1048576)) == GMI_OUTPUT_BYTES,
            'retained output length mismatch')
    _verify_released_lease({'id':'2457567adade','orchestrator_id':root,'pool':'minimax',
        'account':'default','task_class':'remote-minimax','host':'m2studio',
        'state':'released','model':'MiniMax-M3'})
    return {
        'kind':'terminal_publication','run_id':run_id,'root_id':root,
        'pool':'minimax','key':'-','window_id':'unknown','task_class':'remote-minimax',
        'job_class':'fix_build','rc':0,'signal':'ok','model':'MiniMax-M3',
        'accepted_by':None,'tokens':None,'input_tokens':None,'cached_tokens':None,
        'output_tokens':None,'wall_s':None,'credits':None,'credit_rate':None,
        'reason':'verified_owned_process_completion_after_controller_failure',
        'escalation_reason':'','review_rejected':None,'scope_violation':None,
        'retries':None,'escalated':None,
        'terminal_reconciliation':{'lease_id':'2457567adade','process_receipt_sha256':process_sha,
            'stdout_sha256':stdout_sha,'log_sha256':log_sha,'support_sha256':support_sha,
            'packet_sha256':packet_sha},
    }

class CompletionError(ValueError):
    pass


def require(ok, why):
    if not ok:
        raise CompletionError(why)


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def read_regular(path, limit):
    # O_NONBLOCK prevents a malicious FIFO from blocking before the type check.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        visible = path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and not info.st_mode & 0o002, 'unsafe artifact')
        require(_identity(info) == _identity(visible)
                and info.st_size <= limit, 'changed or oversized artifact')
        with os.fdopen(os.dup(fd), 'rb') as handle:
            data = handle.read(limit + 1)
        after = os.fstat(fd)
        require(len(data) == info.st_size and len(data) <= limit
                and _identity(after) == _identity(info)
                and _identity(path.lstat()) == _identity(info),
                'artifact changed during read')
        return data
    finally:
        os.close(fd)


def _pinned(path, digest, limit):
    data = read_regular(path, limit)
    require(hashlib.sha256(data).hexdigest() == digest, 'artifact hash mismatch')
    return data


def verified_record(run_id, root):
    if run_id == GMI_RUN_ID:
        return _verified_gmi_record(run_id, root)
    require(run_id == RUN_ID and root == ROOT_ID, 'run/root binding mismatch')
    log = _pinned(HERE / 'state/remote_sub' / (RUN_ID + '.log'), LOG_SHA, 1048576).decode('utf-8')
    require(not any(token in log for token in ('LEASE_PRESERVED effect_unknown=1',
            'REMOTE_EFFECT_UNKNOWN', 'signal=effect_unknown', 'RESULT_UNAVAILABLE')),
            'uncertain or unavailable effects are sticky')
    require(' REMOTE_DONE rc=0' in log and ' REMOTE_CLEANED transport=1 receipt_saved=1 usage_saved=0' in log
            and ' USAGE_RECEIPT_MISSING' in log and ' DONE rc=' not in log,
            'not the reviewed incomplete-controller result')
    terminal = json.loads(_pinned(HERE / 'state/remote_sub' / (RUN_ID + '.native-terminal.json'),
                                 TERMINAL_SHA, 1048576))
    expected = {'root': ROOT_ID, 'lease_id': LEASE_ID, 'account': 'default', 'host': HOST,
                'run_id': RUN_ID, 'schema': 'mastermind.native.remote-terminal.v1',
                'mode': MODE, 'model': MODEL}
    require(all(terminal.get(k) == v for k, v in expected.items()), 'native identity mismatch')
    require(terminal.get('started') is True and type(terminal.get('returncode')) is int
            and terminal['returncode'] == 0 and terminal.get('output_complete') is True
            and terminal.get('cleanup_proven') is True, 'native completion not proven')
    cleanup = terminal.get('cleanup', {})
    require(all(cleanup.get(k) is True for k in ('census_proven', 'identity_verified',
            'stdout_capture_complete', 'stderr_capture_complete', 'stdin_delivery_complete')),
            'native cleanup/capture not proven')
    require(type(cleanup.get('residual_count')) is int and cleanup['residual_count'] == 0
            and cleanup.get('reason') == 'normal_completion'
            and cleanup.get('status') == 'not_needed'
            and all(cleanup.get(k) is None for k in ('error_code', 'stdout_capture_error',
                                                   'stderr_capture_error', 'stdin_delivery_error')),
            'native residual or capture error')
    capture = terminal.get('capture', {})
    require(type(capture.get('stdout_bytes')) is int and capture['stdout_bytes'] == OUTPUT_BYTES
            and type(capture.get('stderr_bytes')) is int and capture['stderr_bytes'] == 0
            and capture.get('stdout_truncated') is False and capture.get('stderr_truncated') is False,
            'native output incomplete')
    require(terminal.get('launch_timing', {}).get('support_digest') == SUPPORT_SHA,
            'support identity mismatch')
    output = _pinned(HERE / 'lanes' / (RUN_ID + '.remote.stdout'), STDOUT_SHA, 1048576)
    require(len(output) == OUTPUT_BYTES, 'retained output length mismatch')
    expected_lease = {'id': LEASE_ID, 'orchestrator_id': ROOT_ID, 'pool': MODE, 'account': 'default',
                      'task_class': 'remote-grok', 'host': HOST, 'state': 'released', 'model': MODEL}
    _verify_released_lease(expected_lease)
    return {
        'kind': 'terminal_publication', 'run_id': RUN_ID, 'root_id': ROOT_ID,
        'pool': MODE, 'key': '-', 'window_id': 'unknown', 'task_class': 'remote-grok',
        'job_class': 'review', 'rc': 0, 'signal': 'ok', 'model': MODEL,
        'accepted_by': None, 'tokens': None, 'input_tokens': None, 'cached_tokens': None,
        'output_tokens': None, 'wall_s': None, 'credits': None, 'credit_rate': None,
        'reason': 'verified_native_completion_after_controller_failure',
        'escalation_reason': '', 'review_rejected': None, 'scope_violation': None,
        'retries': None, 'escalated': None,
        'terminal_reconciliation': {'lease_id': LEASE_ID, 'terminal_sha256': TERMINAL_SHA,
                                'stdout_sha256': STDOUT_SHA, 'log_sha256': LOG_SHA},
    }


def _verify_released_lease(expected_lease):
    # Read a stable canonical main-file snapshot without opening SQLite on a
    # mutable pathname. Live sidecars refuse; they cannot be silently omitted.
    db_path = HERE / 'broker/leases.sqlite'
    def no_sidecar():
        for suffix in ('-wal', '-journal'):
            try:
                Path(str(db_path) + suffix).lstat()
            except FileNotFoundError:
                continue
            raise CompletionError('broker snapshot has live sidecar')
    no_sidecar()
    visible_db = db_path.lstat()
    require(stat.S_ISREG(visible_db.st_mode) and visible_db.st_uid == os.getuid()
            and not visible_db.st_mode & 0o002, 'unsafe broker file')
    raw_db = read_regular(db_path, 16777216)
    no_sidecar()
    require(raw_db[:16] == b'SQLite format 3\x00' and len(raw_db) >= 100
            and raw_db[18] in (1, 2) and raw_db[19] in (1, 2), 'broker snapshot header')
    # Same no-WAL snapshot technique used by the installed artifact delivery.
    snapshot = raw_db[:18] + b'\x01\x01' + raw_db[20:]
    with closing(sqlite3.connect(':memory:')) as db:
        db.deserialize(snapshot)
        db.execute('PRAGMA query_only=ON')
        db.row_factory = sqlite3.Row
        rows = db.execute('SELECT id,orchestrator_id,pool,account,task_class,host,state,model '
                          'FROM leases WHERE id=?', (expected_lease['id'],)).fetchall()
    no_sidecar()
    require(read_regular(db_path, 16777216) == raw_db, 'broker snapshot changed')
    no_sidecar()
    require(len(rows) == 1 and dict(rows[0]) == expected_lease, 'canonical released lease not proven')


def _publication_present(record):
    """Bounded stable read of the existing owner's exact terminal envelope."""
    def identity(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
                info.st_ctime_ns, info.st_mode, info.st_uid)
    try:
        os.lstat(pool_ledger.LEDGER_PATH)
    except FileNotFoundError:
        return False
    with pool_ledger._strict_open(pool_ledger.LEDGER_PATH, os.O_RDONLY, 'r') as handle:
        before = os.fstat(handle.fileno())
        require(before.st_size <= pool_ledger.ACCEPTANCE_MAX_BYTES, 'ledger exceeds bound')
        data = handle.buffer.read(pool_ledger.ACCEPTANCE_MAX_BYTES + 1)
        require(len(data) == before.st_size and (not data or data.endswith(b'\n')),
                'incomplete ledger snapshot')
        rows = []
        for line in data.splitlines():
            require(len(line) <= pool_ledger.ACCEPTANCE_MAX_LINE_BYTES, 'ledger row exceeds bound')
            item = pool_ledger._strict_json(line.decode('utf-8'))
            if item.get('run_id') == record['run_id']:
                rows.append(item)
        retained = os.lstat(pool_ledger.LEDGER_PATH)
        require(identity(os.fstat(handle.fileno())) == identity(before)
                and identity(retained) == identity(before), 'ledger changed during read')
    if not rows:
        return False
    terminals = [r for r in rows if r.get('kind') != 'outcome']
    outcomes = [r for r in rows if r.get('kind') == 'outcome']
    require(len(terminals) == 1 and rows[0] is terminals[0], 'conflicting terminal history')
    terminal = terminals[0]
    pool_ledger._validate_outcome_source(terminal, outcomes)
    require(json.dumps({k: v for k, v in terminal.items() if k != 'ts'}, sort_keys=True, allow_nan=False)
            == json.dumps(record, sort_keys=True, allow_nan=False), 'conflicting terminal facts')
    return True


def reconcile(run_id, root, *, apply=False):
    record = verified_record(run_id, root)
    present = _publication_present(record)
    if not apply:
        return {'state': 'ALREADY_RECORDED' if present else 'WOULD_APPEND',
                'run_id': record['run_id'], 'root_id': record['root_id']}
    # Existing strict owner provides lock, conflict checks, durability and replay.
    # Explicit empty correlation prevents the caller environment reparenting it.
    ok = pool_ledger.append(
        pool=record['pool'], key=record['key'], window_id=record['window_id'],
        task_class=record['task_class'], job_class=record['job_class'],
        run_id=record['run_id'], root_id=record['root_id'], parent_run_id='', escalation_reason='',
        rc=record['rc'], signal=record['signal'], reason=record['reason'],
        model=record['model'], strict=True, reconciliation=record['terminal_reconciliation'])
    require(ok is True, 'terminal publication unverified; effect may have occurred')
    require(_publication_present(record), 'terminal publication readback incomplete')
    require(verified_record(run_id, root) == record, 'completion evidence changed during publication')
    # The owner returns a durable boolean, not who won a concurrent first append.
    return {'state': 'RECORDED', 'run_id': record['run_id'], 'root_id': record['root_id']}


def status_from_receipt(run_id=RUN_ID):
    """Fresh immutable evidence plus existing durable record; never acceptance."""
    scope = {RUN_ID: (ROOT_ID, OUTPUT_BYTES), GMI_RUN_ID: (GMI_ROOT_ID, GMI_OUTPUT_BYTES)}.get(run_id)
    if scope is None:
        return None
    root, output_bytes = scope
    try:
        result = reconcile(run_id, root, apply=False)
    except (OSError, ValueError, sqlite3.Error):
        return None
    if result['state'] != 'ALREADY_RECORDED':
        return None
    return {'schema': 'mastermind.fabric_task_status.v1', 'run_id': run_id,
            'state': 'TERMINAL', 'rc': 0, 'signal': 'ok', 'result_available': True,
            'result_bytes': output_bytes, 'reconciliation': 'canonical_completion_record'}
