"""Close only the retained 9745 direct-file DISARM; never retry DISARM.

The original sole host retained its -I -S -B direct-file invocation. In this
sealed source, BOTH forward and internal rollback completion pass __main__
classes to the package publisher's unconditional first type guard. Neither
can reach publication. The incident identity below binds that adjudicated
invocation, not an arbitrary RECEIPT_REPLACED journal.

Run only from a separately protected, root-sealed, unselected repair release.
The old installed release and both configs/receipt remain immutable. A real
current flock on the original journal grants this explicit recovery context;
it never recreates the original process's fresh-publication flags.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

_ROOT = Path(__file__).resolve().parents[2]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from ops.executive_os import autonomy_control as owner
from ops.executive_os import control_observation as publisher
from ops.executive_os import release_manifest
from control_plane import executive_control_observation as observation

ORIGINAL_SHA = '9745f66669d028845786f43d5ee4999193250e35'
ORIGINAL_TRANSACTION = 'autonomy-6574622d8326'
ORIGINAL_MANIFEST = 'cf1819d2f78e53dddf9a458a5e610fbc9af222b89510464c6722dbffc0807b9a'
ORIGINAL_RECEIPT = 'f166ef4485a9628ec8b950e5f65e53b1f3fd7eda91465241fc71c70cb81d6850'
ORIGINAL_OBSERVATION = '436e77b143330fdef13210ced374e6b955e887c0fbe14e65c894b721a832b1cf'
ORIGINAL_SOURCES = {
    'ops/executive_os/autonomy_control.py': '0d8475cc639746d1c97d63cc0ea8136f33b5218e03df6132dfa0ab5114073b76',
    'ops/executive_os/control_observation.py': 'e37f64321a67843f6558a63df4269833d9ee697d0d0140709c889afe0e966506',
    'ops/executive_os/autonomy-control.sh': '70d7e4a918fc7341e3aa4ebf23862a4e1f77f65bb9ccc82f5dac606f88615a92',
}
# Original sole-host 19:18 readside-restoration before/after generations.
# Digests cover all nine metadata fields; equal config bytes cannot rebind them.
ORIGINAL_FILE_IDENTITIES = {'control.json': 'c310e25ed67805736947de1c5e6e68cea50fa66521e47040f6b95258be569c0c', 'worker-codex.json': '9bcdc55ba407a428fde60fe6da71a61805e97db271a59b7bc7d153628ee690d2', 'autonomy-state-v1.json': '3993e1b86df65fb478026fbd08c3cd18c9afec9927c605624d37ed0466f12ac9', 'autonomy-transaction.lock/prior-control.json': 'b8a78de9814b4b35494100feac333c28dbeda969c209e2123a20357a883a2f19', 'autonomy-transaction.lock/prior-worker.json': '92609aed08e97555a6d6940f2964432838a9807d9b8e325236b50ab4916c77be'}
ORIGINAL_DIRECTORY = (16777234, 1786085161)
ORIGINAL_MANIFEST_IDENTITY = '9aacfa42ebc371a2267039047c144a23608d2ab92daf1108d7a41be8c87f3882'
CLOSEOUT_STARTED = 'DISARM_CLOSEOUT_OBSERVATION_STARTED'


def _unknown():
    raise owner.TransactionEffectUnknown()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _identity_digest(path):
    return _sha(json.dumps(observation.object_identity(path.lstat()),
                           separators=(',', ':')).encode())


@dataclasses.dataclass(frozen=True)
class _Qualification:
    pid: int
    descriptor: int
    transaction: owner.TransactionContext
    repair_sha: str
    config_objects: tuple
    journal_inode: tuple


def _verify_repair_source(repair_sha):
    """The staging owner supplies one normal protected whole-release seal."""
    owner.require_root_privilege(os.geteuid())
    if (type(repair_sha) is not str or owner._SHA_RE.fullmatch(repair_sha) is None
            or repair_sha == ORIGINAL_SHA):
        _unknown()
    root = owner.SYSTEM_ROOT / 'releases' / repair_sha
    if (Path(__file__).resolve(strict=True) != root / 'ops/executive_os/disarm_closeout.py'
            or Path(owner.__file__).resolve(strict=True) != root / 'ops/executive_os/autonomy_control.py'
            or Path(publisher.__file__).resolve(strict=True) != root / 'ops/executive_os/control_observation.py'):
        _unknown()
    manifest, _ = owner._root_json(root / release_manifest.MANIFEST_NAME,
                                  modes=frozenset({0o444}), uid=0, gid=0)
    if manifest.get('commit_sha') != repair_sha:
        _unknown()
    release_manifest.verify(root, repair_sha, manifest.get('tree_sha'))


def _verify_original_source(host):
    if host.require_exact_install(ORIGINAL_SHA) != ORIGINAL_SHA:
        _unknown()
    root = owner.SYSTEM_ROOT / 'releases' / ORIGINAL_SHA
    read = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
    execute = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    # Exact Git-source modes and their root-read-only sealed counterparts.
    source_modes = frozenset({read, read | execute, read | stat.S_IWUSR,
                             read | stat.S_IWUSR | execute})
    for relative, digest in ORIGINAL_SOURCES.items():
        raw, _ = owner._read_root_file(root / relative,
            modes=source_modes, uid=0, gid=0)
        if _sha(raw) != digest:
            _unknown()


def _journal(host):
    manifest = host._manifest()
    if (manifest.get('operation') != 'DISARM'
            or manifest.get('transaction_id') != ORIGINAL_TRANSACTION
            or manifest.get('expected_sha') != ORIGINAL_SHA
            or manifest.get('phase') not in {'RECEIPT_REPLACED', CLOSEOUT_STARTED}):
        _unknown()
    # Only our single monotonic phase may differ from the original retained
    # journal. Old publication/rollback phases and extra fields cannot qualify.
    original = dict(manifest, phase='RECEIPT_REPLACED')
    if _sha(owner._encoded_json(original)) != ORIGINAL_MANIFEST:
        _unknown()
    if (manifest['phase'] == 'RECEIPT_REPLACED'
            and _identity_digest(host._manifest_path()) != ORIGINAL_MANIFEST_IDENTITY):
        _unknown()
    return manifest


def _config_objects(host, transaction):
    manifest = _journal(host)
    for relative, expected_identity in ORIGINAL_FILE_IDENTITIES.items():
        if _identity_digest(owner.CONFIG_ROOT / relative) != expected_identity:
            _unknown()
    prior = host._archived_configs(ORIGINAL_SHA)
    if prior != transaction.prior_configs:
        _unknown()
    candidates = owner.derive_candidate_configs(prior, armed=False)
    if (candidates != transaction.candidates
            or manifest['target_control_sha256'] != candidates.control_sha256
            or manifest['target_worker_sha256'] != candidates.worker_sha256):
        _unknown()
    control, worker, cdigest, wdigest, _, _ = host._configs()
    if (cdigest != candidates.control_sha256 or wdigest != candidates.worker_sha256
            or control.get('proof_base_sha') != ORIGINAL_SHA
            or control.get('coo_autonomy_armed') is not False
            or control.get('coo_operator_harness_armed') is not False
            or control.get('ceo_submit_armed') is not False
            or worker.get('operator_harness_armed') is not False):
        _unknown()
    raw, _ = owner._read_root_file(owner.AUTONOMY_RECEIPT,
                                  modes=frozenset({0o444}), uid=0, gid=0)
    if _sha(raw) != ORIGINAL_RECEIPT:
        _unknown()
    receipt = json.loads(raw)
    now = owner._parse_timestamp(receipt.get('observed_at'))
    if (now is None or receipt != owner.build_transaction_receipt(
            transaction, state='DISARMED', now=now)):
        _unknown()
    if set(os.listdir(owner.AUTONOMY_TRANSACTION)) != {
            'transaction.json', 'prior-control.json', 'prior-worker.json'}:
        _unknown()
    for candidate in host._candidate_paths(ORIGINAL_TRANSACTION):
        try:
            candidate.lstat()
        except FileNotFoundError:
            continue
        _unknown()
    # No deletion of configs, receipts or a leftover candidate is part of this
    # closeout. Preserve their actual file generations, not just equal bytes.
    return tuple(observation.object_identity(path.lstat()) for path in (
        owner.CONTROL_CONFIG, owner.WORKER_CONFIG, owner.AUTONOMY_RECEIPT,
        *host._archive_paths()))


def _held(host, transaction):
    q = getattr(host, '_disarm_closeout_qualification', None)
    if (type(host) is not owner.ProductionTransactionHost
            or type(transaction) is not owner.TransactionContext
            or type(q) is not _Qualification or q.transaction is not transaction
            or host._active_transaction is not transaction
            or q.pid != os.getpid() or q.descriptor != host._transaction_owner_fd
            or host._transaction_owner_fd is None):
        _unknown()
    host._config_root_safe()
    host._verify_published_inode(q.descriptor)
    info = os.fstat(q.descriptor)
    if (info.st_dev, info.st_ino) != q.journal_inode or q.journal_inode != ORIGINAL_DIRECTORY:
        _unknown()
    host.require_services_already_stopped()
    if _config_objects(host, transaction) != q.config_objects:
        _unknown()
    return q


def verify_admitted_readback(host, transaction):
    """Existing terminal cleanup may ONLY verify this recovery's observation."""
    q = _held(host, transaction)
    if _journal(host)['phase'] != CLOSEOUT_STARTED:
        _unknown()
    # No source path override: the distinct repair seal and unchanged installed
    # source were checked before admission. This is not original-writer custody.
    if q.repair_sha == ORIGINAL_SHA:
        _unknown()
    result = publisher._publish(ORIGINAL_SHA, allow_publication=False,
        control_sha256=transaction.candidates.control_sha256)
    _held(host, transaction)
    return result


def reconcile(*, repair_sha, host=None):
    """One original-journal closeout; config/receipt/service writes forbidden."""
    host = owner.ProductionTransactionHost() if host is None else host
    if type(host) is not owner.ProductionTransactionHost:
        _unknown()
    _verify_repair_source(repair_sha)
    _verify_original_source(host)
    host._claim_transaction_owner()
    try:
        manifest = _journal(host)
        prior = host._archived_configs(ORIGINAL_SHA)
        transaction = owner.TransactionContext(ORIGINAL_TRANSACTION, ORIGINAL_SHA,
            prior, owner.derive_candidate_configs(prior, armed=False), None)
        host._active_transaction = transaction
        objects = _config_objects(host, transaction)
        host.require_services_already_stopped()
        info = os.fstat(host._transaction_owner_fd)
        host._disarm_closeout_qualification = _Qualification(
            os.getpid(), host._transaction_owner_fd, transaction, repair_sha,
            objects, (info.st_dev, info.st_ino))
        _held(host, transaction)
        if manifest['phase'] == 'RECEIPT_REPLACED':
            retained = publisher._retained()
            if retained is None or _sha(retained) != ORIGINAL_OBSERVATION:
                _unknown()
            # This incident's sealed direct-entry code proves the old publisher
            # could not pass its FIRST guard, even on internal rollback. Record
            # a DISTINCT admitted recovery boundary before the only new write.
            host._persist_phase(transaction, CLOSEOUT_STARTED)
            _held(host, transaction)
            if _journal(host)['phase'] != CLOSEOUT_STARTED:
                _unknown()
            publisher._publish(ORIGINAL_SHA, allow_publication=True,
                control_sha256=transaction.candidates.control_sha256)
        # A repeated reconciliation after any publication uncertainty is solely
        # readback. Missing/stale data can never re-enter the write branch.
        verify_admitted_readback(host, transaction)
        host.complete_transaction(transaction)
        return owner.TransactionResult('DISARMED', 'UNARMED', ORIGINAL_TRANSACTION, True)
    except Exception as exc:
        raise owner.TransactionEffectUnknown() from exc
    finally:
        host._disarm_closeout_qualification = None
        if host._transaction_owner_fd is not None:
            host._release_transaction_owner()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repair-sha', required=True)
    args = parser.parse_args(argv)
    try:
        result = reconcile(repair_sha=args.repair_sha)
        document = dataclasses.asdict(result)
        rc = 0
    except Exception:
        document = dict(state='UNKNOWN', status='EFFECT_UNKNOWN',
                        transaction_id=ORIGINAL_TRANSACTION, replayed=False)
        rc = 2
    print(json.dumps(document, sort_keys=True))
    return rc


if __name__ == '__main__':
    from ops.executive_os.disarm_closeout import main as canonical_main
    raise SystemExit(canonical_main())
