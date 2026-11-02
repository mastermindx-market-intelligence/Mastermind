"""Root-owned nonsecret projection inside the incumbent install/transaction.

No CLI, service, grant, refresh loop or private-config permission change. A
projection never authorizes recovery. The incumbent independently admitted CEO
restore may publish after its existing proofs; publication uncertainty is read-only.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from control_plane import executive_control_observation as contract
from control_plane import executive_installed_peer as peer_owner
from ops.executive_os import autonomy_control as owner

PUBLICATION_PHASE = 'CONTROL_OBSERVATION_PUBLICATION_STARTED'
ROLLBACK_PUBLICATION_PHASE = 'ROLLBACK_OBSERVATION_PUBLICATION_STARTED'


def _source(expected_sha):
    owner.require_root_privilege(os.geteuid())
    expected = owner.SYSTEM_ROOT/'releases'/expected_sha
    if Path(__file__).resolve(strict=True) != expected/'ops/executive_os/control_observation.py':
        raise contract.ControlObservationError('publisher_installed_source_required')
    # Same closed exact-release/source closure as the actual installed peer.
    peer_owner._verify_release(peer_owner._role_topology('control'), expected_sha,
                               peer_owner._Budget(peer_owner._SERVICE_BUDGET_SECONDS))


def _snapshot(expected_sha):
    budget = peer_owner._Budget(peer_owner._SERVICE_BUDGET_SECONDS)
    before = peer_owner._observe_ancestors(contract.CONTROL_PATH, budget)
    raw, info = peer_owner._read_trusted_bytes(contract.CONTROL_PATH, budget=budget,
        maximum=contract.CONFIG_MAX_BYTES, expected_mode=0o440,
        expected_gid=contract.CONTROL_UID)
    if peer_owner._observe_ancestors(contract.CONTROL_PATH, budget) != before:
        raise contract.ControlObservationError('publisher_ancestor_changed')
    encoded = contract.encode_observation(raw, contract.object_identity(info), expected_sha)
    # Publication changes the config directory's timestamps; preserve its real
    # object/custody coordinates, and take full fresh ancestor joins on reads.
    custody = tuple((path, identity[:6]) for path, identity in before)
    return encoded, custody


def _retained():
    destination = Path(contract.OBSERVATION_PATH)
    try:
        destination.lstat()
    except FileNotFoundError:
        return None
    budget = peer_owner._Budget(peer_owner._SERVICE_BUDGET_SECONDS)
    peer_owner._observe_ancestors(contract.OBSERVATION_PATH, budget)
    raw, _ = peer_owner._read_trusted_bytes(contract.OBSERVATION_PATH, budget=budget,
        maximum=contract.MAX_BYTES, expected_mode=0o444, expected_gid=0)
    contract.parse_observation(raw)
    return raw


def _publish(expected_sha, *, allow_publication, control_sha256=None):
    target, custody = _snapshot(expected_sha)
    if (control_sha256 is not None
            and contract.parse_observation(target)['control_sha256'] != control_sha256):
        raise owner.TransactionEffectUnknown()
    old = _retained()
    created_receipt = False
    if old != target:
        if not allow_publication:
            raise owner.TransactionEffectUnknown()
        if _snapshot(expected_sha) != (target, custody):
            raise owner.TransactionEffectUnknown()
        try:
            owner._atomic_file(Path(contract.OBSERVATION_PATH), target,
                               mode=0o444, uid=0, gid=0, replace=old is not None)
        except Exception as exc:
            raise owner.TransactionEffectUnknown() from exc
        created_receipt = old is None
    if _retained() != target:
        raise owner.TransactionEffectUnknown()
    current_target, current_custody = _snapshot(expected_sha)
    if current_target != target:
        raise owner.TransactionEffectUnknown()
    if current_custody != custody:
        # APFS counts a newly created regular directory entry in st_nlink.
        # Permit exactly that one increment, only at our receipt's parent and
        # only after this call successfully created it. Replacement/readback,
        # all other ancestors and every object/owner/mode coordinate stay exact.
        receipt_parent = str(Path(contract.OBSERVATION_PATH).parent)
        creation_custody = tuple(
            (path, (*identity[:5], identity[5] + 1))
            if path == receipt_parent else (path, identity)
            for path, identity in custody
        ) if created_receipt else custody
        if current_custody != creation_custody:
            raise owner.TransactionEffectUnknown()
    return hashlib.sha256(target).hexdigest()


def publish_for_install(expected_sha):
    """Called after actual protected install publication, before service start."""
    _source(expected_sha)
    host = owner.ProductionTransactionHost()
    host._config_root_safe()
    host.require_transaction_absent()
    # The installer already owns its maintenance interval; this is not an
    # independently callable recovery/refresh operation.
    return _publish(expected_sha, allow_publication=True)


def publish_for_macro_adoption(held):
    """Publish only inside the actual live, locked offline adoption interval.

    The exact type alone is insufficient: the owner re-proves process-local
    creation, its held canonical marker inode/flock, durable publication phase,
    stopped/quiescent Runtime custody and exact installed source/config bytes.
    No serialized receipt or caller digest can construct that interval.
    """
    from ops.executive_os.macro_adoption import _HeldAdoption
    if type(held) is not _HeldAdoption:
        raise owner.TransactionEffectUnknown()
    expected_sha, config_sha256 = held.observation_publication_binding()
    _source(expected_sha)
    return _publish(expected_sha, allow_publication=True,
                    control_sha256=config_sha256)


def publish_for_transaction(host, transaction):
    """Consume this process's actual held original owner, never serialized data."""
    try:
        return _publish_for_transaction(host, transaction)
    except owner.TransactionEffectUnknown:
        raise
    except Exception as exc:
        # This is inside transaction closeout. A failed observation must not
        # enter the caller's ordinary automatic rollback path.
        raise owner.TransactionEffectUnknown() from exc


def verify_ceo_rollback_readback(host, transaction, admission):
    """Only verify an already-restored original CEO transaction; no effects.

    Recovery may close an already-published result, never recreate its config,
    receipts or observation. A service/override mismatch also remains unknown.
    """
    try:
        manifest = host._manifest()
        if manifest.get('phase') not in {'CONTROL_OVERRIDE_RESTORED', ROLLBACK_PUBLICATION_PHASE}:
            raise owner.TransactionEffectUnknown()
        current = host.load_ceo_submit_configs(transaction.expected_sha)
        prior = transaction.prior_configs
        if (current.control_sha256 != prior.control_sha256
                or current.worker_sha256 != prior.worker_sha256
                or host._read_control_launchd_disabled_override()
                   is not manifest[owner._CONTROL_LAUNCHD_PREIMAGE_FIELD]):
            raise owner.TransactionEffectUnknown()
        if owner._full_autonomy_flags(prior):
            retained, archives = host._coexistence_archives(transaction)
            for path, expected in zip((owner.AUTONOMY_RECEIPT, owner.CEO_SUBMIT_RECEIPT), archives):
                if path == owner.CEO_SUBMIT_RECEIPT and not retained['prior_ceo_receipt_present']:
                    try:
                        path.lstat()
                    except FileNotFoundError:
                        continue
                    raise owner.TransactionEffectUnknown()
                actual, _ = owner._read_root_file(path, modes=frozenset({0o444}), uid=0, gid=0)
                if actual != expected:
                    raise owner.TransactionEffectUnknown()
        else:
            receipt = host.existing_ceo_submit_receipt()
            armed = prior.control['ceo_submit_armed']
            if not owner.validate_ceo_submit_receipt_document(receipt, armed=armed):
                raise owner.TransactionEffectUnknown()
            expected = owner.build_ceo_submit_receipt(transaction, admission,
                armed=armed, now=owner._parse_timestamp(receipt['observed_at']))
            if receipt != expected:
                raise owner.TransactionEffectUnknown()
        publish_for_transaction(host, transaction)  # recovered context is read-only
        if (host._loaded(owner.CONTROL_LABEL)
                and not host._ceo_admission_probe(transaction.expected_sha, prior.control_sha256)):
            raise owner.TransactionEffectUnknown()
        publish_for_transaction(host, transaction)
    except owner.TransactionEffectUnknown:
        raise
    except Exception as exc:
        raise owner.TransactionEffectUnknown() from exc


def _publish_for_transaction(host, transaction):
    if (not isinstance(host, owner.ProductionTransactionHost)
            or type(transaction) is not owner.TransactionContext
            or host._active_transaction is not transaction
            or host._transaction_owner_fd is None):
        raise owner.TransactionEffectUnknown()
    if getattr(host, '_disarm_closeout_qualification', None) is not None:
        # Separately admitted original DISARM recovery. This branch can only
        # read back its completed observation; it cannot grant publication.
        from ops.executive_os.disarm_closeout import verify_admitted_readback
        return verify_admitted_readback(host, transaction)
    _source(transaction.expected_sha)
    host._config_root_safe()
    host._verify_published_inode(host._transaction_owner_fd)
    manifest = host._manifest()
    if (manifest['transaction_id'] != transaction.transaction_id
            or manifest['expected_sha'] != transaction.expected_sha
            or manifest['prior_control_sha256'] != transaction.prior_configs.control_sha256):
        raise owner.TransactionEffectUnknown()
    if manifest['target_control_sha256'] != transaction.candidates.control_sha256:
        # The incumbent CEO rollback context intentionally carries the archived
        # preimage as its candidate, while its original journal keeps the
        # attempted target. Join real archived bytes and completed rollback.
        prior = host._archived_configs(transaction.expected_sha)
        if (manifest.get('operation') not in owner.CEO_SUBMIT_OPERATIONS
                or manifest.get('phase') not in {
                    'ROLLBACK_CONTROL_PROVEN', 'CONTROL_OVERRIDE_RESTORED', ROLLBACK_PUBLICATION_PHASE}
                or prior.control_sha256 != manifest['prior_control_sha256']
                or prior.worker_sha256 != manifest['prior_worker_sha256']
                or transaction.candidates.control_sha256 != prior.control_sha256
                or transaction.candidates.worker_sha256 != prior.worker_sha256):
            raise owner.TransactionEffectUnknown()
    raw, _ = owner._read_root_file(owner.CONTROL_CONFIG, modes=frozenset({0o440}),
                                   uid=0, gid=contract.CONTROL_UID)
    if owner.sha256_bytes(raw) != transaction.candidates.control_sha256:
        raise owner.TransactionEffectUnknown()
    # A successful original write, or the incumbent admitted restore followed
    # by its live/launchd proofs, may publish once. Record the boundary in the
    # existing journal before publication: even this process cannot replay it.
    identity = (os.getpid(), host._transaction_owner_fd,
                transaction.transaction_id, transaction.expected_sha)
    restored = (getattr(host, '_control_observation_rollback_proven', None) is transaction
                and manifest.get('phase') in {'ROLLBACK_CONTROL_PROVEN', 'CONTROL_OVERRIDE_RESTORED'})
    # A2 return-route restoration may reclaim its ORIGINAL global marker
    # after a proven complete Config + DISARMED receipt pair, but ONLY before
    # any earlier observation publication was attempted. The original marker
    # and exact recovered process/held-inode identity fence this one effect.
    # Publication-attempt phase is durable BEFORE _publish can be invoked.
    a2_restore_admitted = (
        manifest.get('operation') == 'A2_RETURN_SOCKET_RESTORE'
        and manifest.get('phase') == 'A2_CONTROL_RESTORED'
        and getattr(host, '_a2_restore_observation_recovery_proven', None) is transaction
        and getattr(host, '_control_observation_recovery_owner', None) == identity
        and getattr(host, '_control_observation_fresh_transaction', None) is not transaction
    )
    fresh = (
        (getattr(host, '_control_observation_fresh_transaction', None) is transaction
         and (getattr(host, '_control_observation_origin', None) == identity
              or (restored and getattr(host, '_control_observation_recovery_owner', None) == identity))
         and manifest.get('phase') not in {PUBLICATION_PHASE, ROLLBACK_PUBLICATION_PHASE})
        or a2_restore_admitted
    )
    if fresh:
        phase = ROLLBACK_PUBLICATION_PHASE if restored else PUBLICATION_PHASE
        host._persist_phase(transaction, phase)
        reread = host._manifest()
        if (reread.get('phase') != phase
                or reread.get('transaction_id') != transaction.transaction_id
                or reread.get('expected_sha') != transaction.expected_sha):
            raise owner.TransactionEffectUnknown()
    result = _publish(transaction.expected_sha, allow_publication=fresh,
                      control_sha256=transaction.candidates.control_sha256)
    host._verify_published_inode(host._transaction_owner_fd)
    return result
