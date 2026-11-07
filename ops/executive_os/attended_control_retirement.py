"""Authority-shrinking retirement in the existing finite configuration owner.

Only Control selection changes. The finite definitions, principals, Runtime,
historical Jobs and native enrollment remain untouched. The original global
transaction owns publication; reconciliation never replays a missing write.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import stat
from datetime import datetime, timezone

from control_plane.fabric_attended_routing import (
    FINITE_DEFINITION_DIR, RETIRED_FINITE_FIELD, RETIRED_FINITE_SCHEMA,
    retired_finite_selection,
)
from ops.executive_os import autonomy_control as owner
from ops.executive_os import attended_control_staging as staging

OPERATION = 'FINITE_CONTROL_RETIRE'
PREDECESSOR_SCHEMA = 'mastermind.executive_finite_retirement_predecessor/v1'
PREDECESSOR_NAME = 'finite-control-retirement-predecessor-v1.json'
QUIESCENCE_NAME = 'finite-control-retirement-quiescence-v1.json'
RETIREMENT_PHASES = frozenset({'LOCKED', 'FINITE_RETIRE_PREDECESSOR_RETAINED',
    'CANDIDATES_WRITTEN', 'CANDIDATES_VALIDATED', 'CONTROL_REPLACED',
    'FINITE_RECEIPT_REBOUND', 'FINITE_RETIRE_VERIFIED',
    'CONTROL_OBSERVATION_PUBLICATION_STARTED'})


def _path():
    return owner.CONFIG_ROOT / PREDECESSOR_NAME


def predecessor_bytes(prior, *, transaction_id, expected_sha, receipt):
    # Retain exact bytes, not a reserialization of the prior Control/Worker or
    # receipt. The immutable archive is Root-only, like the incumbent journal.
    raw = owner._encoded_json(dict(schema_version=PREDECESSOR_SCHEMA,
        operation=OPERATION, transaction_id=transaction_id, release_sha=expected_sha,
        prior_control=prior.control_bytes.decode('utf-8'),
        prior_worker=prior.worker_bytes.decode('utf-8'),
        prior_disarmed_receipt=receipt.decode('utf-8')))
    if len(raw) > owner._MAX_JSON_BYTES:
        raise ValueError('retirement predecessor exceeds the protected reader budget')
    return raw


def candidate(prior, delta, *, transaction_id, expected_sha, predecessor_sha256):
    if (RETIRED_FINITE_FIELD in prior.control or 'canonical_paid_fabric' in prior.control
            or set(delta) not in (staging.FIELDS, staging.NATIVE_FIELDS)
            or any(prior.control.get(key, False) is not False for key in (
                'coo_autonomy_armed', 'coo_operator_harness_armed',
                'coo_foreground_only', 'ceo_submit_armed', 'fabric_bridge_armed'))
            or prior.worker.get('operator_harness_armed') is not False
            or staging._staged_delta(prior.control) != delta):
        raise ValueError('retirement requires the exact wholly disarmed finite selection')
    value = {key: copy.deepcopy(item) for key, item in prior.control.items()
             if key not in staging.NATIVE_FIELDS}
    value[RETIRED_FINITE_FIELD] = dict(schema_version=RETIRED_FINITE_SCHEMA,
        transaction_id=transaction_id, release_sha=expected_sha,
        predecessor_sha256=predecessor_sha256, selection=copy.deepcopy(delta))
    retired_finite_selection(value)
    raw = owner.encode_config(value)
    return owner.CandidateConfigs(value, prior.worker, raw, prior.worker_bytes,
        owner.sha256_bytes(raw), prior.worker_sha256)


def _rebuild(tx):
    selected = tx.candidates.control[RETIRED_FINITE_FIELD]
    return candidate(tx.prior_configs, selected['selection'],
        transaction_id=tx.transaction_id, expected_sha=tx.expected_sha,
        predecessor_sha256=selected['predecessor_sha256'])


def rebind_disarmed_receipt(tx, payload):
    if (payload.get('state') != 'DISARMED'
            or payload.get('control_config_sha256') != tx.prior_configs.control_sha256
            or payload.get('worker_config_sha256') != tx.prior_configs.worker_sha256
            or _rebuild(tx) != tx.candidates):
        raise owner.TransactionEffectUnknown()
    value = copy.deepcopy(payload)
    value.update(control_config_sha256=tx.candidates.control_sha256,
                 prior_control_config_sha256=tx.prior_configs.control_sha256,
                 transaction_id=tx.transaction_id)
    return value


def _read_predecessor():
    owner.ProductionTransactionHost._config_root_safe()
    raw, _ = owner._read_root_file(_path(), modes=frozenset({0o400}), uid=0, gid=0)
    document = json.loads(raw)
    if (type(document) is not dict or set(document) != {
            'schema_version', 'operation', 'transaction_id', 'release_sha',
            'prior_control', 'prior_worker', 'prior_disarmed_receipt'}
            or document['schema_version'] != PREDECESSOR_SCHEMA
            or document['operation'] != OPERATION
            or any(type(document[key]) is not str for key in document)
            or owner._encoded_json(document) != raw):
        raise owner.TransactionEffectUnknown()
    control_raw = document['prior_control'].encode('utf-8')
    worker_raw = document['prior_worker'].encode('utf-8')
    prior = owner.ConfigEvidence(control_sha256=owner.sha256_bytes(control_raw),
        worker_sha256=owner.sha256_bytes(worker_raw), control=json.loads(control_raw),
        worker=json.loads(worker_raw), control_bytes=control_raw, worker_bytes=worker_raw)
    proposed = candidate(prior, staging._staged_delta(prior.control),
        transaction_id=document['transaction_id'], expected_sha=document['release_sha'],
        predecessor_sha256=owner.sha256_bytes(raw))
    tx = owner.TransactionContext(document['transaction_id'], document['release_sha'],
                                  prior, proposed, None)
    if predecessor_bytes(prior, transaction_id=tx.transaction_id, expected_sha=tx.expected_sha,
            receipt=document['prior_disarmed_receipt'].encode('utf-8')) != raw:
        raise owner.TransactionEffectUnknown()
    return raw, document, tx


def retained_selection(control):
    """Root acceptance joins inactive membership to the actual retained bytes.

    Later normal arm/paid-stage fields may change. Only the immutable retired
    projection is compared here; original retirement reconciliation additionally
    requires the complete exact target configs and paired disarm receipt.
    """
    selected = retired_finite_selection(control)
    if selected is None:
        raise ValueError('retired finite provenance is absent')
    _, _, tx = _read_predecessor()
    if control[RETIRED_FINITE_FIELD] != tx.candidates.control[RETIRED_FINITE_FIELD]:
        raise owner.TransactionEffectUnknown()
    return copy.deepcopy(selected)


class ProductionFiniteRetirementHost(staging.ProductionFiniteStagingHost):
    operation = OPERATION
    receipt_transform = staticmethod(rebind_disarmed_receipt)

    def _retirement_configs(self, expected_sha):
        """Normal cleanup predicates; strict UID observation follows cleanup.

        The only new admission is the held original retirement transaction
        below. The public transaction-absence gate remains unchanged.
        """
        owner.require_root_privilege(self.effective_uid())
        if self.require_exact_install(expected_sha) != expected_sha:
            raise owner.ArmAdmissionError('install_gate_failed')
        acceptance = self.validate_acceptance(expected_sha)
        configs = self.load_unarmed_configs(expected_sha)
        if (any(configs.control.get(key, False) is not False for key in (
                'coo_autonomy_armed', 'coo_operator_harness_armed',
                'coo_foreground_only', 'ceo_submit_armed', 'fabric_bridge_armed'))
                or configs.worker.get('operator_harness_armed') is not False):
            raise owner.ArmAdmissionError('configs_not_unarmed')
        self.require_runtime_quiescent(configs)
        self.require_services_already_stopped()
        return configs, acceptance

    def _held_retirement(self, tx):
        if self._transaction_owner_fd is None or self._active_transaction is not tx:
            raise owner.TransactionEffectUnknown()
        self._verify_published_inode(self._transaction_owner_fd)
        manifest = self._manifest()
        expected = self._manifest_document(tx, manifest['phase'], operation=OPERATION)
        if (manifest['phase'] not in RETIREMENT_PHASES
                or any(manifest.get(key) != value for key, value in expected.items())
                or self._archived_configs(tx.expected_sha) != tx.prior_configs):
            raise owner.TransactionEffectUnknown()
        pair = self._receipt_pair(tx)
        if self._current_receipt() not in pair:
            raise owner.TransactionEffectUnknown()

    @staticmethod
    def _quiescence_path():
        return owner.CONFIG_ROOT / QUIESCENCE_NAME

    def _quiescence_record(self, tx, *, allow_absent=False):
        path = self._quiescence_path()
        try:
            path.lstat()
        except FileNotFoundError:
            if allow_absent:
                return None, dict(schema_version='mastermind.executive_finite_retirement_quiescence/v1',
                    operation=OPERATION, transaction_id=tx.transaction_id, release_sha=tx.expected_sha,
                    prior_control_sha256=tx.prior_configs.control_sha256,
                    target_control_sha256=tx.candidates.control_sha256,
                    worker_sha256=tx.prior_configs.worker_sha256, observations=[])
            raise owner.TransactionEffectUnknown() from None
        raw, _ = owner._read_root_file(path, modes=frozenset({0o400}), uid=0, gid=0)
        document = json.loads(raw)
        expected = dict(schema_version='mastermind.executive_finite_retirement_quiescence/v1',
            operation=OPERATION, transaction_id=tx.transaction_id, release_sha=tx.expected_sha,
            prior_control_sha256=tx.prior_configs.control_sha256,
            target_control_sha256=tx.candidates.control_sha256,
            worker_sha256=tx.prior_configs.worker_sha256)
        if (type(document) is not dict or set(document) != set(expected) | {'observations'}
                or any(document.get(key) != value for key, value in expected.items())
                or type(document['observations']) is not list
                or not 1 <= len(document['observations']) <= 8
                or owner._encoded_json(document) != raw):
            raise owner.TransactionEffectUnknown()
        for index, item in enumerate(document['observations'], 1):
            if (type(item) is not dict or set(item) != {'ordinal', 'control_sha256',
                    'acceptance_receipt_sha256', 'started_at', 'finished_at',
                    'status', 'signalled_pids', 'refusal_code'}
                    or type(item['ordinal']) is not int or item['ordinal'] != index
                    or item['control_sha256'] not in {
                        tx.prior_configs.control_sha256, tx.candidates.control_sha256}
                    or type(item['acceptance_receipt_sha256']) is not str
                    or re.fullmatch(r'[0-9a-f]{64}', item['acceptance_receipt_sha256']) is None
                    or owner._parse_timestamp(item['started_at']) is None
                    or item['status'] not in {'STARTED', 'SUCCEEDED', 'UNKNOWN'}):
                raise owner.TransactionEffectUnknown()
            started = owner._parse_timestamp(item['started_at'])
            finished = owner._parse_timestamp(item['finished_at'])
            if (item['status'] == 'STARTED' and any(item[key] is not None
                    for key in ('finished_at', 'signalled_pids', 'refusal_code'))
                    or item['status'] != 'STARTED' and (finished is None or finished < started)
                    or item['status'] == 'UNKNOWN' and type(item['refusal_code']) is not str):
                raise owner.TransactionEffectUnknown()
            if item['status'] == 'SUCCEEDED' and (
                    owner._parse_timestamp(item['finished_at']) is None
                    or item['refusal_code'] is not None
                    or type(item['signalled_pids']) is not list
                    or any(type(pid) is not int or pid <= 1 for pid in item['signalled_pids'])):
                raise owner.TransactionEffectUnknown()
        return raw, document

    def _retain_quiescence(self, tx, before, document):
        self._held_retirement(tx)
        current, _ = self._quiescence_record(tx, allow_absent=before is None)
        if current != before:
            raise owner.TransactionEffectUnknown()
        if before is None:
            self._publish_retirement_file(tx, self._quiescence_path(),
                                          owner._encoded_json(document))
        else:
            owner._atomic_file(self._quiescence_path(), owner._encoded_json(document),
                              mode=0o400, uid=0, gid=0, replace=True)
        actual, _ = self._quiescence_record(tx)
        if actual != owner._encoded_json(document):
            raise owner.TransactionEffectUnknown()
        return actual

    def _quiesce_owned(self, tx, *, current, acceptance):
        # All expensive source/acceptance/definition/Runtime checks were just
        # completed by verify_current. Rejoin exact current bytes and held
        # original custody before the existing fixed-UID action. No alternate
        # host or transaction-existence override is installed.
        self._held_retirement(tx)
        if self.load_unarmed_configs(tx.expected_sha) != current:
            raise owner.TransactionEffectUnknown()
        before, document = self._quiescence_record(tx, allow_absent=True)
        if (len(document['observations']) >= 8
                or any(row['status'] != 'SUCCEEDED' for row in document['observations'])):
            raise owner.TransactionEffectUnknown()
        row = dict(ordinal=len(document['observations']) + 1,
            control_sha256=current.control_sha256, acceptance_receipt_sha256=acceptance,
            started_at=owner._iso(datetime.now(timezone.utc)), finished_at=None,
            status='STARTED', signalled_pids=None, refusal_code=None)
        document['observations'].append(row)
        retained = self._retain_quiescence(tx, before, document)
        signalled = None
        try:
            signalled = self.quiesce_control_uid_for_arm()
            self.require_service_uids_quiescent()
            if (type(signalled) is not tuple
                    or any(type(pid) is not int or pid <= 1 for pid in signalled)):
                raise owner.TransactionEffectUnknown()
            self._held_retirement(tx)
        except Exception as exc:
            row.update(status='UNKNOWN', signalled_pids=list(signalled) if type(signalled) is tuple else None,
                       finished_at=owner._iso(datetime.now(timezone.utc)),
                       refusal_code=getattr(exc, 'code', 'service_uid_process_unknown'))
            self._retain_quiescence(tx, retained, document)
            raise owner.TransactionEffectUnknown() from None
        row.update(status='SUCCEEDED', signalled_pids=list(signalled),
                   finished_at=owner._iso(datetime.now(timezone.utc)))
        self._retain_quiescence(tx, retained, document)

    def read_delta(self):
        # Retirement consumes the already-selected historical definition. It
        # cannot require that old finite service's manifest to become the new
        # installed release: doing so would rewrite the proof being retired.
        # No old service is started or qualified for new execution here.
        directory = Path(FINITE_DEFINITION_DIR)
        for path in (directory, *directory.parents):
            info = path.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
                    or info.st_mode & 0o022 or owner._has_acl(path)):
                raise ValueError('untrusted finite definition directory')
        artifacts = {name: owner._read_root_file(directory/name,
            modes=frozenset({0o444}), uid=0, gid=0)[0]
            for name in ('worker.json', 'bindings.json')}
        worker = json.loads(artifacts['worker.json'])
        identity = pwd.getpwnam('_mastermind_minimax')
        if (identity.pw_uid != 470 or identity.pw_gid != 470
                or worker.get('worker_uid') != 470 or worker.get('worker_gid') != 470
                or worker.get('worker_user') != '_mastermind_minimax'):
            raise ValueError('finite principal differs')
        if self._loaded_observe_only('com.mastermind.executive.fabric.minimax-finite-01'):
            raise ValueError('finite bridge must be unloaded')
        from control_plane.executive_worker_broker import _ps_pids_for_uid
        if _ps_pids_for_uid(470):
            raise ValueError('finite principal is not quiescent')
        return staging.build_finite_control_delta(definition_dir=str(directory),
            worker_artifacts=artifacts, native_capacity_v2=staging._native_source_pin(worker))

    def _seal_generation(self, generation, tx, *, operation):
        expected = predecessor_bytes(tx.prior_configs, transaction_id=tx.transaction_id,
            expected_sha=tx.expected_sha, receipt=self._current_receipt())
        if owner.sha256_bytes(expected) != tx.candidates.control[RETIRED_FINITE_FIELD]['predecessor_sha256']:
            raise owner.TransactionEffectUnknown()
        super()._seal_generation(generation, tx, operation=operation)

    def verify_current(self, tx, *, target):
        current, acceptance = self._retirement_configs(tx.expected_sha)
        expected = tx.candidates.control_bytes if target else tx.prior_configs.control_bytes
        if (current.control_bytes != expected or current.worker_bytes != tx.prior_configs.worker_bytes
                or candidate(tx.prior_configs, self.read_delta(),
                    transaction_id=tx.transaction_id, expected_sha=tx.expected_sha,
                    predecessor_sha256=tx.candidates.control[RETIRED_FINITE_FIELD]['predecessor_sha256'])
                    != tx.candidates):
            raise owner.TransactionEffectUnknown()
        if self._active_transaction is tx and self._transaction_owner_fd is not None:
            self._quiesce_owned(tx, current=current, acceptance=acceptance)
        else:
            # Completed-original reconciliation is read-only and cannot
            # recreate a cleanup interval from retained provenance.
            self.require_service_uids_quiescent()
            _, document = self._quiescence_record(tx)
            if any(row['status'] != 'SUCCEEDED' for row in document['observations']):
                raise owner.TransactionEffectUnknown()

    def verify_predecessor(self, tx):
        raw, document, retained = _read_predecessor()
        if retained != tx:
            raise owner.TransactionEffectUnknown()
        original, _ = self._receipt_pair(tx)
        if document['prior_disarmed_receipt'].encode('utf-8') != original:
            raise owner.TransactionEffectUnknown()
        return raw

    def _publish_retirement_file(self, tx, destination, payload):
        """Publish one of the two fixed first records under the existing lock.

        The held original marker must still be LOCKED at publication. The
        incumbent kernel-exclusive rename preserves even a late equal-byte
        occupant; an uncertain response never authorizes adoption or replay.
        """
        from ops.executive_os.capacity_host_artifacts import _rename_exclusive

        parent = descriptor = -1
        stage = ''
        staged_identity = None
        renamed = False
        try:
            if (destination not in {_path(), self._quiescence_path()}
                    or destination.parent != owner.CONFIG_ROOT
                    or type(payload) is not bytes
                    or not 0 < len(payload) <= owner._MAX_JSON_BYTES):
                raise owner.TransactionEffectUnknown()
            self._config_root_safe()
            self._held_retirement(tx)
            parent = self._publication_mutex()

            def require_parent():
                # Lock acquisition may block; rejoin the held directory to its
                # trusted name both after acquisition and after staging.
                self._config_root_safe()
                held, named = os.fstat(parent), owner.CONFIG_ROOT.lstat()
                if (not stat.S_ISDIR(held.st_mode)
                        or (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino)
                        or held.st_uid != owner._CONFIG_ROOT_UID
                        or held.st_gid != owner._CONFIG_ROOT_GID):
                    raise owner.TransactionEffectUnknown()

            def require_first_intent():
                self._held_retirement(tx)
                manifest = self._manifest()
                if manifest['phase'] != 'LOCKED':
                    raise owner.TransactionEffectUnknown()
                if destination == _path():
                    original, _ = self._receipt_pair(tx)
                    if payload != predecessor_bytes(tx.prior_configs,
                            transaction_id=tx.transaction_id,
                            expected_sha=tx.expected_sha, receipt=original):
                        raise owner.TransactionEffectUnknown()
                try:
                    destination.lstat()
                except FileNotFoundError:
                    pass
                else:
                    raise owner.TransactionEffectUnknown()
                return manifest

            require_parent()
            manifest = require_first_intent()
            stage = f'.{destination.name}.{os.getpid()}.{secrets.token_hex(8)}.stage'
            descriptor = os.open(stage,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=parent)
            opened = os.fstat(descriptor)
            staged_identity = (opened.st_dev, opened.st_ino)
            pending = memoryview(payload)
            while pending:
                count = os.write(descriptor, pending)
                if count <= 0:
                    raise OSError('short finite retirement evidence write')
                pending = pending[count:]
            os.fchown(descriptor, owner._CONFIG_ROOT_UID, owner._CONFIG_ROOT_GID)
            os.fchmod(descriptor, 0o400)
            os.fsync(descriptor)
            held = os.fstat(descriptor)
            if (not stat.S_ISREG(held.st_mode) or held.st_nlink != 1
                    or held.st_uid != owner._CONFIG_ROOT_UID
                    or held.st_gid != owner._CONFIG_ROOT_GID
                    or stat.S_IMODE(held.st_mode) != 0o400
                    or held.st_size != len(payload)):
                raise owner.TransactionEffectUnknown()
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.read(descriptor, len(payload) + 1) != payload:
                raise owner.TransactionEffectUnknown()
            named = os.stat(stage, dir_fd=parent, follow_symlinks=False)
            if (not stat.S_ISREG(named.st_mode) or named.st_nlink != 1
                    or (named.st_dev, named.st_ino) != staged_identity
                    or (named.st_mode, named.st_size) != (held.st_mode, held.st_size)):
                raise owner.TransactionEffectUnknown()

            require_parent()
            if require_first_intent() != manifest:
                raise owner.TransactionEffectUnknown()
            _rename_exclusive(parent, stage, parent, destination.name)
            renamed = True
            os.fsync(parent)
            require_parent()
            self._held_retirement(tx)
            if self._manifest() != manifest:
                raise owner.TransactionEffectUnknown()
            actual, published = owner._read_root_file(destination,
                modes=frozenset({0o400}), uid=0, gid=0)
            current = os.fstat(descriptor)
            if (actual != payload
                    or (published.st_dev, published.st_ino) != staged_identity
                    or (current.st_dev, current.st_ino) != staged_identity
                    or current.st_nlink != 1
                    or current.st_size != len(payload)
                    or stat.S_IMODE(current.st_mode) != 0o400):
                raise owner.TransactionEffectUnknown()
        except owner.TransactionEffectUnknown:
            raise
        except Exception as exc:
            raise owner.TransactionEffectUnknown() from exc
        finally:
            if not renamed and parent >= 0 and stage and staged_identity is not None:
                # Only an unchanged private stage is ours to remove. A
                # possibly published canonical file and original marker stay.
                try:
                    named = os.stat(stage, dir_fd=parent, follow_symlinks=False)
                    held = os.fstat(descriptor)
                    if (stat.S_ISREG(named.st_mode) and named.st_nlink == 1
                            and (named.st_dev, named.st_ino) == staged_identity
                            and (held.st_dev, held.st_ino) == staged_identity):
                        os.unlink(stage, dir_fd=parent)
                        os.fsync(parent)
                except OSError:
                    pass
            if descriptor >= 0:
                os.close(descriptor)
            if parent >= 0:
                os.close(parent)

    def publish_predecessor(self, tx):
        original, _ = self._receipt_pair(tx)
        raw = predecessor_bytes(tx.prior_configs, transaction_id=tx.transaction_id,
                                expected_sha=tx.expected_sha, receipt=original)
        self._publish_retirement_file(tx, _path(), raw)
        self.verify_predecessor(tx)
        self._persist_phase(tx, 'FINITE_RETIRE_PREDECESSOR_RETAINED')

    def reconcile_retirement(self, expected_sha):
        owner.require_root_privilege(self.effective_uid())
        self._retirement_configs(expected_sha)
        try:
            owner.AUTONOMY_TRANSACTION.lstat()
        except FileNotFoundError:
            # A lost final response does not mint another transaction. The
            # normal config-directory mutex fences a read-only join of the
            # exact original archive, complete targets and actual projection.
            mutex = self._publication_mutex()
            try:
                self._require_canonical_absent()
                _, document, tx = _read_predecessor()
                if tx.expected_sha != expected_sha:
                    raise owner.TransactionEffectUnknown()
                self.verify_current(tx, target=True)
                prior = document['prior_disarmed_receipt'].encode('utf-8')
                target = owner._encoded_json(rebind_disarmed_receipt(tx, json.loads(prior))) if prior else b''
                if self._current_receipt() != target:
                    raise owner.TransactionEffectUnknown()
                self.verify_completed_observation(tx)
                self._require_canonical_absent()
                return tx.transaction_id
            finally:
                os.close(mutex)
        self._claim_transaction_owner()
        manifest = self._manifest()
        if (manifest['operation'] != OPERATION or manifest['expected_sha'] != expected_sha
                or manifest['phase'] not in RETIREMENT_PHASES):
            raise owner.TransactionEffectUnknown()
        try:
            _, _, tx = _read_predecessor()
        except owner.HostControlError as exc:
            # The retained marker may precede predecessor publication. A
            # missing or unjoinable record leaves that original effect unknown.
            raise owner.TransactionEffectUnknown() from exc
        if (tx.transaction_id != manifest['transaction_id'] or tx.expected_sha != expected_sha
                or tx.prior_configs != self._archived_configs(expected_sha)
                or tx.candidates.control_sha256 != manifest['target_control_sha256']
                or tx.candidates.worker_sha256 != manifest['target_worker_sha256']):
            raise owner.TransactionEffectUnknown()
        self._active_transaction = tx
        # The predecessor follows initial journal publication. Recovery may
        # rejoin that original journal, never mint a missing cleanup interval.
        self._quiescence_record(tx)
        self.verify_current(tx, target=True)
        self.verify_predecessor(tx)
        self.verify_disarmed_receipt(tx, target=True)
        self.complete_transaction(tx)
        return tx.transaction_id

    def verify_completed_observation(self, tx):
        from ops.executive_os import control_observation
        control_observation._publish(tx.expected_sha, allow_publication=False,
                                    control_sha256=tx.candidates.control_sha256)


def execute_retirement(host, expected_sha, expected_control_sha256):
    owner.require_root_privilege(host.effective_uid())
    host.require_transaction_absent()
    prior, _ = host._retirement_configs(expected_sha)
    if prior.control_sha256 != expected_control_sha256:
        raise ValueError('exact current Control preimage required')
    for path in (_path(), host._quiescence_path()):
        try:
            path.lstat()
        except FileNotFoundError:
            pass
        else:
            raise ValueError('original retirement predecessor already exists; reconcile it')
    transaction_id = host.new_transaction_id()
    predecessor = predecessor_bytes(prior, transaction_id=transaction_id,
        expected_sha=expected_sha, receipt=host._current_receipt())
    proposed = candidate(prior, host.read_delta(), transaction_id=transaction_id,
        expected_sha=expected_sha, predecessor_sha256=owner.sha256_bytes(predecessor))
    staging.control_boot_smoke(proposed.control)
    tx = owner.TransactionContext(transaction_id, expected_sha, prior, proposed, None)
    host._active_transaction = tx
    host._create_marker(tx, operation=OPERATION)
    try:
        host.verify_current(tx, target=False)
        host.verify_disarmed_receipt(tx, target=False)
        host.publish_predecessor(tx)
        host.write_candidates(tx)
        host.validate_candidates(tx)
        host.verify_current(tx, target=False)
        host.verify_predecessor(tx)
        host.verify_disarmed_receipt(tx, target=False)
        host.replace_control_config(tx)
        host.verify_current(tx, target=True)
        host.publish_disarmed_receipt(tx)
        host.verify_predecessor(tx)
        host._persist_phase(tx, 'FINITE_RETIRE_VERIFIED')
        host.complete_transaction(tx)
        return tx.transaction_id
    except Exception:
        raise owner.TransactionEffectUnknown() from None


def run_command(args, *, host=None):
    host = ProductionFiniteRetirementHost() if host is None else host
    try:
        if args.command == 'finite-control-retire':
            tx = execute_retirement(host, args.expected_sha, args.expected_control_sha256)
        elif args.command == 'finite-control-retire-reconcile':
            tx = host.reconcile_retirement(args.expected_sha)
        else:
            raise ValueError('unknown finite retirement command')
        result = owner.operation_document(code='finite_control_retired', state='UNARMED',
            status='FINITE_CONTROL_RETIRED', transaction_id=tx, replayed=False)
        rc = 0
    except Exception:
        result = owner.operation_document(code='effect_unknown', state='UNKNOWN',
            status='EFFECT_UNKNOWN', transaction_id=None)
        rc = 2
    finally:
        if host._transaction_owner_fd is not None:
            host._release_transaction_owner()
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    return rc
