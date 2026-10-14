"""Stage the fixed finite definition through the existing global config owner.

No installation, service start, arm receipt, credential or Runtime admission.
Interrupted publication stays on the original transaction; recovery only proves
an already-published exact target and never replays the write.
"""
from __future__ import annotations

import json
from pathlib import Path
import pwd
import stat

from control_plane.fabric_attended_routing import FINITE_DEFINITION_DIR
from ops.executive_os import autonomy_control as owner
from ops.executive_os.attended_worker_definition import build_finite_control_delta

OPERATION = 'FINITE_CONTROL_STAGE'
COMMANDS = frozenset({'finite-control-stage', 'finite-control-stage-reconcile'})
FIELDS = frozenset({'fabric_bridge_armed', 'fabric_bindings_path',
                    'fabric_bindings_sha256', 'fabric_attended_probe'})


def candidate(prior, delta):
    if (set(delta) != FIELDS or delta.get('fabric_bridge_armed') is not False
            or any(prior.control.get(key, False) is not False for key in (
                'coo_autonomy_armed', 'coo_operator_harness_armed',
                'coo_foreground_only', 'ceo_submit_armed', 'fabric_bridge_armed'))
            or prior.worker.get('operator_harness_armed') is not False):
        raise ValueError('finite staging requires wholly disarmed configs')
    # First installation or byte-identical existing selection only. This verb
    # cannot repoint an existing worker definition to a new one.
    if any(key in prior.control and prior.control[key] != value for key, value in delta.items()):
        raise ValueError('existing finite selection differs')
    value = dict(prior.control, **delta)
    raw = owner.encode_config(value)
    return owner.CandidateConfigs(value, prior.worker, raw, prior.worker_bytes,
        owner.sha256_bytes(raw), prior.worker_sha256)


class ProductionFiniteStagingHost(owner.ProductionCeoSubmitHost):
    def new_transaction_id(self):
        # Unlike recovery-oriented inherited helpers, a fresh publication may
        # never lock/adopt a marker that appeared after its absence preflight.
        return 'autonomy-' + owner.secrets.token_hex(6)

    def read_delta(self):
        directory = Path(FINITE_DEFINITION_DIR)
        for path in (directory, *directory.parents):
            info = path.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
                    or info.st_mode & 0o022 or owner._has_acl(path)):
                raise ValueError('untrusted finite definition directory')
        artifacts = {name: owner._read_root_file(directory/name,
            modes=frozenset({0o444}), uid=0, gid=0)[0] for name in ('worker.json', 'bindings.json')}
        from control_plane.executive_fabric_composition import _bindings
        physical, = _bindings(artifacts['bindings.json'])
        manifest, _ = owner._read_root_file(
            owner.SYSTEM_ROOT/'releases'/self._finite_expected_sha/'.executive-release-manifest.json',
            modes=frozenset({0o444}), uid=0, gid=0)
        if physical.service_source_sha256 != owner.sha256_bytes(manifest):
            raise ValueError('finite definition belongs to a different installed release')
        worker = json.loads(artifacts['worker.json'])
        identity = pwd.getpwnam('_mastermind_minimax')
        if (identity.pw_uid != 470 or identity.pw_gid != 470
                or worker.get('worker_uid') != 470 or worker.get('worker_gid') != 470
                or worker.get('worker_user') != '_mastermind_minimax'):
            raise ValueError('finite principal does not match selected host')
        if self._loaded_observe_only('com.mastermind.executive.fabric.minimax-finite-01'):
            raise ValueError('finite bridge must be unloaded')
        from control_plane.executive_worker_broker import _ps_pids_for_uid
        if _ps_pids_for_uid(470):
            raise ValueError('finite principal is not quiescent')
        return build_finite_control_delta(definition_dir=str(directory), worker_artifacts=artifacts)

    def checked_configs(self, expected_sha):
        if self.require_exact_install(expected_sha) != expected_sha:
            raise ValueError('installed release differs')
        self._finite_expected_sha = expected_sha
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
                or manifest['phase'] not in {'LOCKED', 'CANDIDATES_WRITTEN',
                    'CANDIDATES_VALIDATED', 'CONTROL_REPLACED', 'FINITE_STAGE_VERIFIED'}):
            raise owner.TransactionEffectUnknown()
        prior = self._archived_configs(expected_sha)
        proposed = candidate(prior, self.read_delta())
        if (proposed.control_sha256 != manifest['target_control_sha256']
                or proposed.worker_sha256 != manifest['target_worker_sha256']):
            raise owner.TransactionEffectUnknown()
        tx = owner.TransactionContext(manifest['transaction_id'], expected_sha, prior, proposed, None)
        self._active_transaction = tx
        self.verify_current(tx, target=True)
        self._persist_phase(tx, 'FINITE_STAGE_VERIFIED')
        self.complete_transaction(tx)
        return tx.transaction_id


def execute_staging(host, expected_sha, expected_control_sha256):
    owner.require_root_privilege(host.effective_uid())
    host.require_transaction_absent()
    prior = host.checked_configs(expected_sha)
    if prior.control_sha256 != expected_control_sha256:
        raise ValueError('exact current Control preimage required')
    proposed = candidate(prior, host.read_delta())
    if proposed.control_bytes == prior.control_bytes:
        return None
    tx = owner.TransactionContext(host.new_transaction_id(), expected_sha, prior, proposed, None)
    # Claim the original global owner before any config write. Failed claims
    # retain their own existing semantics; never adopt a foreign marker.
    host._active_transaction = tx
    host._create_marker(tx, operation=OPERATION)
    try:
        host.verify_current(tx, target=False)
        host.write_candidates(tx)
        host.validate_candidates(tx)
        host.verify_current(tx, target=False)
        host.replace_control_config(tx)
        host.verify_current(tx, target=True)
        host._persist_phase(tx, 'FINITE_STAGE_VERIFIED')
        host.complete_transaction(tx)
        return tx.transaction_id
    except Exception:
        raise owner.TransactionEffectUnknown() from None


def run_command(args, *, host=None):
    host = ProductionFiniteStagingHost() if host is None else host
    try:
        if args.command == 'finite-control-stage':
            tx = execute_staging(host, args.expected_sha, args.expected_control_sha256)
        elif args.command == 'finite-control-stage-reconcile':
            tx = host.reconcile_staging(args.expected_sha)
        else:
            raise ValueError('unknown finite staging command')
        document = owner.operation_document(code='finite_control_staged', state='UNARMED',
            status='FINITE_CONTROL_STAGED', transaction_id=tx, replayed=tx is None)
        rc = 0
    except Exception:
        document = owner.operation_document(code='effect_unknown', state='UNKNOWN',
            status='EFFECT_UNKNOWN', transaction_id=None)
        rc = 2
    finally:
        if host._transaction_owner_fd is not None:
            host._release_transaction_owner()
    print(json.dumps(document, sort_keys=True, separators=(',', ':')))
    return rc
