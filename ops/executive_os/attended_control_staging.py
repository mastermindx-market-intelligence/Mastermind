"""Stage the fixed finite definition through the existing global config owner.

No installation, service start, arm receipt, credential or Runtime admission.
Interrupted publication stays on the original transaction; recovery only proves
an already-published exact target and never replays the write.
"""
from __future__ import annotations

import json
import os
import copy
from pathlib import Path
import pwd
import stat

from control_plane.fabric_attended_routing import FINITE_DEFINITION_DIR
from ops.executive_os import autonomy_control as owner
from ops.executive_os.attended_worker_definition import build_finite_control_delta
from control_plane.executive_autonomy import validate_disarmed_interlock_document

OPERATION = 'FINITE_CONTROL_STAGE'
COMMANDS = frozenset({'finite-control-stage', 'finite-control-stage-reconcile'})
FIELDS = frozenset({'fabric_bridge_armed', 'fabric_bindings_path',
                    'fabric_bindings_sha256', 'fabric_attended_probe'})
NATIVE_FIELDS = FIELDS | {'native_capacity_v2'}


def _staged_delta(control):
    fields = NATIVE_FIELDS if 'native_capacity_v2' in control else FIELDS
    return {key: control[key] for key in fields}


def candidate(prior, delta):
    if (set(delta) not in (FIELDS, NATIVE_FIELDS) or delta.get('fabric_bridge_armed') is not False
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
    from scripts.executive_os_phase1c import _validate_fabric_bridge_config
    _validate_fabric_bridge_config(value)
    raw = owner.encode_config(value)
    return owner.CandidateConfigs(value, prior.worker, raw, prior.worker_bytes,
        owner.sha256_bytes(raw), prior.worker_sha256)


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


def _native_source_pin(worker):
    """Derive optional pins from the selected root definition and sealed source.

    Registration is checked without requiring credential enrollment or claiming
    provider readiness. No caller path, producer code execution or network read.
    The transaction rereads this exact selection before and after publication.
    """
    if 'native_capacity_enrollment' not in worker:
        return None
    from control_plane.codex_provider_realm import _native_read_config, _native_open
    from control_plane.native_capacity_acquisition import PRODUCER_RELATIVE
    from ops.executive_os import capacity_source_contract as source
    enrollment = source.validate_native_subscription_capacity_enrollment(
        worker['native_capacity_enrollment'])
    selected = enrollment['registration_source']
    export_path = source.SYSTEM_ROOT/'config/capacity-source-components-native-v2'/(
        selected['release_commit'] + '.json')
    export = _native_read_config(export_path, selected['export_sha256'])
    registration = source.validate_native_registration_document(worker, export)
    if registration['provider'] != 'minimax':
        raise ValueError('native finite source provider differs')
    source_root = source.SYSTEM_ROOT/'capacity-sources/macro'/selected['release_commit']
    producer = source_root/PRODUCER_RELATIVE
    with _native_open(producer) as (fd, _):
        content = os.read(fd, 65537)
    if not content or len(content) > 65536:
        raise ValueError('native capacity producer size is invalid')
    # Custody alone cannot bless new code bytes. Use the existing complete Git
    # source-closure owner, and require this producer in its qualified material.
    # A source profile that does not yet include V2 must continue to refuse.
    from ops.executive_os.capacity_host_artifacts import _verify_installed_repair_source
    manifest, _ = _verify_installed_repair_source(source_root, selected['release_commit'])
    rows = [row for row in manifest['material'] if row['path'] == str(PRODUCER_RELATIVE)]
    if (len(rows) != 1 or rows[0]['sha256'] != owner.sha256_bytes(content)
            or rows[0]['size'] != len(content)):
        raise ValueError('native producer is outside the qualified source material')
    if _native_read_config(export_path, selected['export_sha256']) != export:
        raise ValueError('native registration changed during staging')
    return {'macro_release': selected['release_commit'],
            'producer_sha256': rows[0]['sha256']}


class ProductionFiniteStagingHost(owner.ProductionCeoSubmitHost):
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
        # Finite staging is wholly disarmed and cannot use the armed CEO
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
        owner._atomic_file(generation/owner._FINITE_RECEIPT_ARCHIVE, raw,
            mode=0o400, uid=0, gid=0, replace=False)
        manifest = self._manifest_document(tx, 'LOCKED', operation=operation)
        manifest.update(finite_prior_receipt_present=bool(raw),
            finite_prior_receipt_sha256=owner.sha256_bytes(raw),
            finite_target_receipt_sha256=owner.sha256_bytes(target))
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
                or not owner._FINITE_RECEIPT_FIELDS <= set(manifest)):
            raise owner.TransactionEffectUnknown()
        raw, _ = owner._read_root_file(owner.AUTONOMY_TRANSACTION/owner._FINITE_RECEIPT_ARCHIVE,
            modes=frozenset({0o400}), uid=0, gid=0)
        if (owner.sha256_bytes(raw) != manifest['finite_prior_receipt_sha256']
                or bool(raw) is not manifest['finite_prior_receipt_present']):
            raise owner.TransactionEffectUnknown()
        target = owner._encoded_json(rebind_disarmed_receipt(tx, json.loads(raw))) if raw else b''
        if owner.sha256_bytes(target) != manifest['finite_target_receipt_sha256']:
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
        self._persist_phase(tx, 'FINITE_RECEIPT_REBOUND')

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
        return build_finite_control_delta(definition_dir=str(directory), worker_artifacts=artifacts,
            native_capacity_v2=_native_source_pin(worker))

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
                    'CANDIDATES_VALIDATED', 'CONTROL_REPLACED', 'FINITE_RECEIPT_REBOUND', 'FINITE_STAGE_VERIFIED'}):
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
        self._persist_phase(tx, 'FINITE_STAGE_VERIFIED')
        self.complete_transaction(tx)
        return tx.transaction_id


_WORKSPACE_KEYS = frozenset({'workspace_acquisition', 'workspace_resource_policy',
    'workspace_control_room'})


def control_boot_smoke(control):
    """Static, inert refusal of a staged Control composition that cannot boot.

    The real ``load_control_config`` still runs the candidate as the Control
    user inside ``validate_candidates``; the boot itself is proven by
    ``tests/test_attended_control_staging.py::test_staged_candidate_boots_with_zero_tcp_listeners``.
    A legacy ``{"port": int}`` stanza here would otherwise only surface on the
    Control user's next start; refusing it before the marker keeps TCP off the
    workspace Control Room forever.
    """
    from scripts.executive_os_phase1c import (ServiceError,
        _CEO_INGRESS_APP_CONFIG_KEYS, validate_workspace_control_room)
    workspace = _WORKSPACE_KEYS
    if (set(control) & workspace
            and (not workspace <= set(control)
                or not _CEO_INGRESS_APP_CONFIG_KEYS <= set(control))):
        raise ValueError('staged Control composition cannot boot: '
            'workspace acquisition requires its policy, Control Room and installed App peer')
    if 'workspace_control_room' in control:
        control_uid = control.get('control_uid')
        if type(control_uid) is not int:
            raise ValueError('staged Control composition cannot boot: '
                'workspace Control Room requires an integer control_uid')
        try:
            validate_workspace_control_room(control['workspace_control_room'],
                control_uid=control_uid)
        except ServiceError as exc:
            raise ValueError('staged Control composition cannot boot: '
                + str(exc)) from None
    return None


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
