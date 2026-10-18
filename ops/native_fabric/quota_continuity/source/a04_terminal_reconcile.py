"""Exact-incident publication recovery through the incumbent pool ledger.

This imports already-settled worker facts, never executes work, retries an
operation, releases a lease, edits an original receipt, or accepts a result.
The evidence allowlist is intentionally not a general caller-authored manifest.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
from typing import Any

import pool_ledger

HERE = Path(__file__).resolve().parent
AUDIT_EVIDENCE = Path('/Volumes/Mastermind/evidence/terminal-audit20-01a10f92')
REPAIR_EVIDENCE = Path('/Volumes/Mastermind/evidence/fabric-reliability-codex-20261008/recovery-engineering')
RUN_ID = 'terminal-audit20-a04-universal-provider-adjudication-20261009'
ROOT_ID = '01a10f92-900c-7363-89d0-010e8eec9e05'
PARENT_ID = 'terminal-audit20-01a10f92'
LEASE_ID = '537553921886'
ESCALATION_REASON = 'Concurrent-copy authority requires independent review; previous provider run settled with incomplete API response and no review artifact, source unchanged'
SCHEMA = 'mastermind.fabric.terminal-reconciliation.v1'
HASHES = {
    'log': '8966750f5188f716484c7f61a7cdf8a8a196c83793ecd38b70c94b5e409a66db',
    'process': '3a680ff473e5953f3bfab73c3462cb1113c50773f96195f44631a060ca2a5f42',
    'result': '9473d83a7a8afe9cd6a65e27d9f5db0eeb4a7b0747686797f35fb83d971023d1',
    'packet': '9f0fbcd4c514215d96e5f852269e9da3ed2b1e93bf66a511b4b8fa5f6e33a6fd',
    'controller_output': '6b50c484879f64fe69d93a5518e429fad8b116eba7a4a2b216a88e57053fd3b6',
    'controller_completion': '907bf91ca211735fa787fcf3d8d8214c7bbc1e076052a9a4ab917f7e5a538546',
}


class ReconciliationError(RuntimeError):
    pass


def evidence_paths() -> dict[str, Path]:
    return {
        'log': HERE / 'state/remote_sub' / f'{RUN_ID}.log',
        'process': HERE / 'state/remote_sub' / f'{RUN_ID}.process.jsonl',
        'result': HERE / 'lanes' / f'{RUN_ID}.remote.stdout',
        'packet': AUDIT_EVIDENCE / 'commissions/a04-universal-provider-adjudication-20261009.txt',
        'controller_output': AUDIT_EVIDENCE / 'a04-universal-provider-adjudication-request-20261009.log',
        'controller_completion': REPAIR_EVIDENCE / 'a04-original-controller-completion.json',
    }


def _read(path: Path, limit: int = 1_048_576) -> bytes:
    def identity(s):
        return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit or before.st_uid != os.getuid() or before.st_mode & 0o002:
            raise ReconciliationError('unsafe evidence')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode) or identity(before) != identity(opened):
                raise ReconciliationError('evidence replaced')
            data = bytearray()
            while len(data) <= limit:
                chunk = os.read(fd, min(65536, limit + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            if len(data) != opened.st_size or identity(os.fstat(fd)) != identity(opened) or identity(path.lstat()) != identity(opened):
                raise ReconciliationError('evidence changed')
            return bytes(data)
        finally:
            os.close(fd)
    except OSError as exc:
        raise ReconciliationError('evidence unavailable') from exc


def _lease() -> None:
    path = HERE / 'broker/leases.sqlite'
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise ReconciliationError('unsafe broker database')
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute('SELECT * FROM leases WHERE id=?', (LEASE_ID,)).fetchall()
    expected = {
        'id': LEASE_ID, 'orchestrator_id': ROOT_ID, 'pool': 'minimax',
        'account': 'default', 'task_class': 'remote-minimax', 'host': 'm2studio',
        'pid': 57647, 'granted_at': 1791517348.192616, 'ttl': 7470,
        'last_heartbeat': 1791517742.875852, 'state': 'released',
        'renewable': 1, 'model': 'MiniMax-M3',
    }
    if len(rows) != 1 or any(dict(rows[0]).get(k) != v for k, v in expected.items()):
        raise ReconciliationError('original released lease witness mismatch')
    after = path.lstat()
    if (after.st_dev, after.st_ino) != (info.st_dev, info.st_ino):
        raise ReconciliationError('broker database replaced')


def _proof() -> dict[str, Any]:
    return {'schema': SCHEMA, 'run_id': RUN_ID, 'root_id': ROOT_ID,
            'lease_id': LEASE_ID, 'evidence_sha256': dict(HASHES),
            'reason': 'original_controller_shell_parse_failure_after_cleanup',
            'worker_reexecuted': False, 'parent_acceptance': False,
            'producer': 'exact_incident_importer', 'original_done': False,
            'controller_tool_receipt_sha256': HASHES['controller_completion'],
            'legacy_collision_window': {'start_ts': 1791517320, 'end_ts': 1791517800, 'pool': 'minimax'}}


def check(run_id: str, root_id: str) -> dict[str, Any]:
    # Accept only the canonical spelling and the incumbent's trusted default.
    # General abspath normalization is unsafe across an intermediate symlink.
    allowed_paths = {(HERE.parent / 'orch/fabric/ledger.jsonl').absolute(),
                     (HERE / '../orch/fabric/ledger.jsonl').absolute()}
    if Path(pool_ledger.LEDGER_PATH).absolute() not in allowed_paths:
        raise ReconciliationError('noncanonical ledger path')
    if run_id != RUN_ID or root_id != ROOT_ID:
        raise ReconciliationError('unsupported operation or original root')
    artifacts = {name: _read(path) for name, path in evidence_paths().items()}
    if any(hashlib.sha256(data).hexdigest() != HASHES[name] for name, data in artifacts.items()):
        raise ReconciliationError('immutable original evidence mismatch')
    process = json.loads(artifacts['process'])
    cleanup = process['cleanup']
    if (process['schema'] != 'mastermind.local_owned_process_receipt.v1'
            or process['label'] != RUN_ID or process['returncode'] != 0
            or process['timed_out'] is not False or process['stdout_truncated'] is not False
            or process['stderr_truncated'] is not False
            or cleanup['identity_verified'] is not True or cleanup['census_proven'] is not True
            or cleanup['residual_count'] != 0 or cleanup['stdout_capture_complete'] is not True
            or cleanup['stderr_capture_complete'] is not True or process['stdout_bytes'] != len(artifacts['result'])):
        raise ReconciliationError('worker settlement incomplete')
    controller = json.loads(artifacts['controller_completion'])
    if controller['status'] != 'completed' or controller['id'] != 'exec-ede29c50-644e-4ff9-9fc3-3032967045ab':
        raise ReconciliationError('original controller not complete')
    _lease()
    return {'run_id': RUN_ID, 'root_id': ROOT_ID, 'eligible': True,
            'worker_rc': 0, 'accepted': False, 'proof': _proof()}


def _published_job() -> dict[str, Any] | None:
    """Validate publication and fold current outcomes from one ledger snapshot."""
    path = Path(pool_ledger.LEDGER_PATH)
    try:
        data = _read(path, 64 * 1024 * 1024)
    except ReconciliationError:
        return None
    if not data.endswith(b"\n"):
        return None
    rows = []
    outcomes = []
    matching = []
    try:
        for line in data.splitlines():
            row = pool_ledger._strict_json(line)
            if (str(row.get('run_id', '')).startswith('run-') and row.get('pool') == 'minimax'
                    and 1791517320 <= row.get('ts', 0) <= 1791517800):
                return None
            if row.get('run_id') == RUN_ID:
                matching.append(row)
                if row.get('kind') == 'outcome':
                    outcomes.append(row)
                else:
                    rows.append(row)
    except (ValueError, AttributeError, TypeError):
        return None
    expected = {
        'pool': 'minimax', 'key': '-', 'window_id': 'weekly',
        'task_class': 'remote-minimax', 'job_class': 'review', 'rc': 0,
        'tokens': None, 'signal': 'ok', 'reason': 'controller_terminal_publication_reconciled',
        'escalation_reason': ESCALATION_REASON, 'run_id': RUN_ID, 'root_id': ROOT_ID,
        'parent_run_id': PARENT_ID, 'accepted_by': None, 'review_rejected': None,
        'scope_violation': None, 'retries': None, 'escalated': None, 'wall_s': None,
        'model': 'MiniMax-M3', 'input_tokens': None, 'cached_tokens': None,
        'output_tokens': None, 'credits': None, 'credit_rate': None,
        'kind': 'terminal_publication', 'terminal_reconciliation': _proof(),
    }
    valid = (len(rows) == 1 and type(rows[0].get('ts')) is int
            and not pool_ledger._outcomes_conflict(rows[0], outcomes)
            and json.dumps({k: v for k, v in rows[0].items() if k != 'ts'}, sort_keys=True, allow_nan=False)
            == json.dumps(expected, sort_keys=True, allow_nan=False))
    if not valid:
        return None
    # Ledger append order is authoritative; timestamps do not reorder outcomes.
    return pool_ledger.merge_jobs(matching)[0]



def status_from_ledger() -> dict[str, Any] | None:
    try:
        check(RUN_ID, ROOT_ID)
        job = _published_job()
        if job is None:
            return None
    except (ReconciliationError, OSError, ValueError, sqlite3.Error):
        return None
    accepted_by = job.get('accepted_by')
    if accepted_by not in ('deterministic', 'reviewer', 'none'):
        accepted_by = None
    # Acceptance is distinct from first-pass/cost accounting and from the
    # immutable recovery-time proof. Rejection, scope violation, or malformed
    # flags cannot be promoted to acceptance; legacy absent flags remain valid.
    accepted = (accepted_by in ('deterministic', 'reviewer')
                and all(job.get(key) is None or job.get(key) is False
                        for key in ('review_rejected', 'scope_violation')))
    return {'schema': 'mastermind.fabric_task_status.v1', 'run_id': RUN_ID,
            'state': 'TERMINAL', 'rc': 0, 'signal': 'ok', 'result_available': True,
            'result_bytes': 2759, 'accepted': accepted, 'accepted_by': accepted_by,
            'terminal_reconciliation': _proof()}


def reconcile(run_id: str, root_id: str) -> dict[str, Any]:
    check(run_id, root_id)
    if not pool_ledger.append(pool='minimax', task_class='remote-minimax', job_class='review',
                             rc=0, signal='ok', reason='controller_terminal_publication_reconciled',
                             run_id=RUN_ID, root_id=ROOT_ID, parent_run_id=PARENT_ID,
                             model='MiniMax-M3', window_id='weekly', escalation_reason=ESCALATION_REASON,
                             strict=True, reconciliation=_proof()):
        raise ReconciliationError('terminal publication failed or conflicts')
    result = status_from_ledger()
    if result is None:
        raise ReconciliationError('terminal publication readback incomplete')
    return result
