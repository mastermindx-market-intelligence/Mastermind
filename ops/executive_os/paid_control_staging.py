"""Stage only the qualified paid source through the existing global owner.

No inference arm, worker readiness, lease or service start. Interrupted writes
remain in AUTONOMY_TRANSACTION and reconciliation only accepts exact postimages.
"""
from __future__ import annotations
import json
import copy
from pathlib import Path
from ops.executive_os import autonomy_control as owner
from control_plane.executive_autonomy import validate_disarmed_interlock_document
from control_plane.paid_model_execution_contract import digest

OPERATION='PAID_CONTROL_STAGE'
FIELDS=frozenset({'canonical_paid_fabric'})
DEFINITION=owner.CONFIG_ROOT/'fabric-glm-paid-01'


def _staged_delta(control):
    return {key:control[key] for key in FIELDS}


def candidate(prior,delta):
    if (type(delta) is not dict or set(delta)!=FIELDS
            or any(prior.control.get(k,False) is not False for k in (
                'coo_autonomy_armed','coo_operator_harness_armed','coo_foreground_only',
                'ceo_submit_armed','fabric_bridge_armed'))
            or prior.worker.get('operator_harness_armed') is not False
            or any(k in prior.control for k in ('fabric_attended_probe','native_capacity_v2','fabric_bindings_path'))):
        raise ValueError('paid staging requires disarmed unmixed Control')
    selected=delta['canonical_paid_fabric']
    import re
    if (type(selected) is not dict or set(selected)!={'bindings_path','bindings_sha256'}
            or selected['bindings_path']!=str(DEFINITION/'bindings.json')
            or type(selected['bindings_sha256']) is not str
            or re.fullmatch(r'[0-9a-f]{64}',selected['bindings_sha256']) is None
            or ('canonical_paid_fabric' in prior.control and prior.control['canonical_paid_fabric']!=selected)):
        raise ValueError('paid selection differs')
    value=dict(prior.control,**copy.deepcopy(delta))
    raw=owner.encode_config(value)
    return owner.CandidateConfigs(value,prior.worker,raw,prior.worker_bytes,
        owner.sha256_bytes(raw),prior.worker_sha256)


def rebind_disarmed_receipt(tx, payload):
    """Preserve existing disarm authority and timestamps; change correlation only."""
    if (payload.get('state') != 'DISARMED'
            or payload.get('control_config_sha256') != tx.prior_configs.control_sha256
            or payload.get('worker_config_sha256') != tx.prior_configs.worker_sha256
            or candidate(tx.prior_configs, _staged_delta(tx.candidates.control)) != tx.candidates):
        raise owner.TransactionEffectUnknown()
    value = copy.deepcopy(payload)
    value.update(control_config_sha256=tx.candidates.control_sha256,
                 prior_control_config_sha256=tx.prior_configs.control_sha256,
                 transaction_id=tx.transaction_id)
    return value

class ProductionPaidStagingHost(owner.ProductionCeoSubmitHost):
    @staticmethod
    def _current_receipt():
        try:
            owner.AUTONOMY_RECEIPT.lstat()
        except FileNotFoundError:
            return b''
        raw = owner._read_root_file(owner.AUTONOMY_RECEIPT,
            modes=frozenset({0o444}), uid=0, gid=0)[0]
        # Only positive filesystem absence has the empty sentinel. An existing
        # empty receipt is invalid evidence, including during reconciliation.
        if not raw:
            raise ValueError('existing disarm receipt is empty')
        return raw

    def _seal_generation(self, generation, tx, *, operation):
        # Paid staging is wholly disarmed and cannot use the armed CEO
        # coexistence transformer. Retain its receipt in the SAME global owner.
        if operation != OPERATION:
            raise owner.TransactionEffectUnknown()
        raw = self._current_receipt()
        target = b''
        if raw:
            payload, metadata = owner.load_receipt_file(owner.AUTONOMY_RECEIPT)
            if json.loads(raw) != payload:
                raise owner.TransactionEffectUnknown()
            validate_disarmed_interlock_document(payload, metadata=metadata,
                control_config_sha256=tx.prior_configs.control_sha256,
                worker_config_sha256=tx.prior_configs.worker_sha256)
            target = owner._encoded_json(rebind_disarmed_receipt(tx, payload))
        owner.ProductionTransactionHost._seal_generation(self, generation, tx, operation=operation)
        owner._atomic_file(generation/owner._PAID_RECEIPT_ARCHIVE, raw,
            mode=0o400, uid=0, gid=0, replace=False)
        manifest = self._manifest_document(tx, 'LOCKED', operation=operation)
        manifest.update(paid_definition_sha256=self._paid_definition_sha256,paid_prior_receipt_present=bool(raw),
            paid_prior_receipt_sha256=owner.sha256_bytes(raw),
            paid_target_receipt_sha256=owner.sha256_bytes(target))
        owner._atomic_file(generation/owner._TRANSACTION_MANIFEST_NAME,
            owner._encoded_json(manifest), mode=0o400, uid=0, gid=0, replace=True)
        owner._fsync_directory(generation)

    def _receipt_pair(self, tx):
        if (self._transaction_owner_fd is None or self._active_transaction is None
                or self._active_transaction.transaction_id != tx.transaction_id):
            raise owner.TransactionEffectUnknown()
        self._verify_published_inode(self._transaction_owner_fd)
        manifest = self._manifest()
        if (manifest['operation'] != OPERATION or manifest['transaction_id'] != tx.transaction_id
                or manifest['expected_sha'] != tx.expected_sha
                or manifest['paid_definition_sha256']!=self._paid_definition_sha256
                or not owner._PAID_RECEIPT_FIELDS <= set(manifest)):
            raise owner.TransactionEffectUnknown()
        raw, _ = owner._read_root_file(owner.AUTONOMY_TRANSACTION/owner._PAID_RECEIPT_ARCHIVE,
            modes=frozenset({0o400}), uid=0, gid=0)
        if (owner.sha256_bytes(raw) != manifest['paid_prior_receipt_sha256']
                or bool(raw) is not manifest['paid_prior_receipt_present']):
            raise owner.TransactionEffectUnknown()
        target = owner._encoded_json(rebind_disarmed_receipt(tx, json.loads(raw))) if raw else b''
        if owner.sha256_bytes(target) != manifest['paid_target_receipt_sha256']:
            raise owner.TransactionEffectUnknown()
        return raw, target

    def verify_disarmed_receipt(self, tx, *, target):
        pair = self._receipt_pair(tx)
        if self._current_receipt() != pair[1 if target else 0]:
            raise owner.TransactionEffectUnknown()

    def publish_disarmed_receipt(self, tx):
        self.verify_current(tx, target=True)
        prior, target = self._receipt_pair(tx)
        self.verify_disarmed_receipt(tx, target=False)
        if prior:
            owner._atomic_file(owner.AUTONOMY_RECEIPT, target,
                mode=0o444, uid=0, gid=0, replace=True)
        self.verify_disarmed_receipt(tx, target=True)
        self._persist_phase(tx, 'PAID_RECEIPT_REBOUND')

    def new_transaction_id(self):
        # Unlike recovery-oriented inherited helpers, a fresh publication may
        # never lock/adopt a marker that appeared after its absence preflight.
        return 'autonomy-' + owner.secrets.token_hex(6)

    def read_delta(self):
        from control_plane.executive_paid_fabric_composition import load_paid_config,verify_installed_source
        from control_plane.paid_fabric_backend import _root_source
        config=load_paid_config(DEFINITION/'bridge.json')
        installed=verify_installed_source(config,DEFINITION,
            owner.SYSTEM_ROOT/'releases'/self._paid_expected_sha)
        if (installed['profile']['schema_version']!='mastermind.executive_paid_fabric_profile/v2'
                or digest(installed['hashes'])!=self._paid_definition_sha256
                or len(installed['bindings'])!=1
                or self._loaded_observe_only('com.mastermind.executive.fabric.glm-paid-01')):
            raise ValueError('qualified paid definition differs or is loaded')
        # Genuine Root-read source constructor; this is DATA selection, not
        # account availability or an inferred execution arm.
        from control_plane.executive_paid_fabric_composition import PaidBindingSource
        path=DEFINITION/'bindings.json'
        sha=owner.sha256_bytes(_root_source(path))
        selected=PaidBindingSource.from_path(path,sha);selected._current()
        return {'canonical_paid_fabric':{'bindings_path':str(path),'bindings_sha256':sha}}

    def checked_configs(self, expected_sha):
        if self.require_exact_install(expected_sha) != expected_sha:
            raise ValueError('installed release differs')
        self._paid_expected_sha = expected_sha
        self.require_services_already_stopped()
        self.require_service_uids_quiescent()
        prior = self.load_unarmed_configs(expected_sha)
        self.require_runtime_quiescent(prior)
        return prior

    def validate_candidates(self, transaction):
        value, raw, worker_raw = self._read_validated_control_candidate(transaction)
        if (raw != transaction.candidates.control_bytes
                or value != dict(transaction.candidates.control)
                or worker_raw != transaction.prior_configs.worker_bytes):
            raise owner.TransactionEffectUnknown()
        self._persist_phase(transaction, 'CANDIDATES_VALIDATED')

    def verify_current(self, tx, *, target):
        current = self.checked_configs(tx.expected_sha)
        expected = tx.candidates.control_bytes if target else tx.prior_configs.control_bytes
        if (current.control_bytes != expected or current.worker_bytes != tx.prior_configs.worker_bytes
                or candidate(tx.prior_configs, self.read_delta()) != tx.candidates):
            raise owner.TransactionEffectUnknown()

    def reconcile_staging(self, expected_sha):
        owner.require_root_privilege(self.effective_uid())
        self.checked_configs(expected_sha)
        self._claim_transaction_owner()
        manifest = self._manifest()
        if (manifest['operation'] != OPERATION or manifest['expected_sha'] != expected_sha
                or manifest['paid_definition_sha256']!=self._paid_definition_sha256
                or manifest['phase'] not in {'LOCKED', 'CANDIDATES_WRITTEN',
                    'CANDIDATES_VALIDATED', 'CONTROL_REPLACED', 'PAID_RECEIPT_REBOUND', 'PAID_STAGE_VERIFIED'}):
            raise owner.TransactionEffectUnknown()
        prior = self._archived_configs(expected_sha)
        proposed = candidate(prior, self.read_delta())
        if (proposed.control_sha256 != manifest['target_control_sha256']
                or proposed.worker_sha256 != manifest['target_worker_sha256']):
            raise owner.TransactionEffectUnknown()
        tx = owner.TransactionContext(manifest['transaction_id'], expected_sha, prior, proposed, None)
        self._active_transaction = tx
        self.verify_current(tx, target=True)
        # Recovery accepts both exact postimages only. It never republishes a
        # missing/partial receipt or replays the original config replacement.
        self.verify_disarmed_receipt(tx, target=True)
        self._persist_phase(tx, 'PAID_STAGE_VERIFIED')
        self.complete_transaction(tx)
        return tx.transaction_id


from ops.executive_os.attended_control_staging import control_boot_smoke


def execute_staging(host, expected_sha, expected_control_sha256):
    owner.require_root_privilege(host.effective_uid())
    host.require_transaction_absent()
    prior = host.checked_configs(expected_sha)
    if prior.control_sha256 != expected_control_sha256:
        raise ValueError('exact current Control preimage required')
    proposed = candidate(prior, host.read_delta())
    control_boot_smoke(proposed.control)
    if proposed.control_bytes == prior.control_bytes:
        return None
    tx = owner.TransactionContext(host.new_transaction_id(), expected_sha, prior, proposed, None)
    # Claim the original global owner before any config write. Failed claims
    # retain their own existing semantics; never adopt a foreign marker.
    host._active_transaction = tx
    host._create_marker(tx, operation=OPERATION)
    try:
        host.verify_current(tx, target=False)
        host.verify_disarmed_receipt(tx, target=False)
        host.write_candidates(tx)
        host.validate_candidates(tx)
        host.verify_current(tx, target=False)
        host.verify_disarmed_receipt(tx, target=False)
        host.replace_control_config(tx)
        host.verify_current(tx, target=True)
        host.publish_disarmed_receipt(tx)
        host._persist_phase(tx, 'PAID_STAGE_VERIFIED')
        host.complete_transaction(tx)
        return tx.transaction_id
    except Exception:
        raise owner.TransactionEffectUnknown() from None


def run_command(args,*,host=None):
    host=ProductionPaidStagingHost() if host is None else host
    try:
        import re
        if (type(args.expected_definition_sha256) is not str
                or re.fullmatch(r'[0-9a-f]{64}',args.expected_definition_sha256) is None):
            raise ValueError('exact paid definition required')
        host._paid_definition_sha256=args.expected_definition_sha256
        if args.command=='paid-control-stage':
            tx=execute_staging(host,args.expected_sha,args.expected_control_sha256)
        elif args.command=='paid-control-stage-reconcile':
            tx=host.reconcile_staging(args.expected_sha)
        else:raise ValueError('closed paid staging action required')
        document={'state':'STAGED_DISARMED_PAID_CONTROL','transaction_id':tx,'replayed':tx is None}
        rc=0
    except Exception:
        document={'state':'EFFECT_UNKNOWN','transaction_id':None};rc=2
    finally:
        if host._transaction_owner_fd is not None:host._release_transaction_owner()
    print(json.dumps(document,sort_keys=True,separators=(',',':')))
    return rc
