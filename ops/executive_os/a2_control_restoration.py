"""Restore the legacy A2 return-socket binding inside the EXISTING Executive owner.

The original A2 reverse-rebind CAS (PR #1804) is a separate effect. This
operation only changes one *disarmed* Control config field, rebinding the
existing disarm receipt in the existing autonomy-transaction archive. No
token, enrollment, service, lease, or alternate publication plane is created.

The root caller must first stop A2 and the Control/C1 read-side and reverse
A2 to an exactly sealed prior release. A recover invocation only verifies
an already-complete target; it never repeats a config replacement.
"""
from __future__ import annotations

import copy
import json
import stat
from pathlib import Path
from types import SimpleNamespace

from control_plane.executive_autonomy import validate_disarmed_interlock_document
from ops.executive_os import autonomy_control as owner
from ops.executive_os import a2_agent_relay_enrollment as a2
from ops.executive_os import release_manifest

OPERATION = "A2_RETURN_SOCKET_RESTORE"
COMMANDS = frozenset({"a2-restore-controller-socket", "a2-restore-controller-socket-reconcile"})
LEGACY_SOCKET = "/var/run/mastermind-agent-relay/agent-relay.sock"
PERSISTENT_SOCKET = "/var/db/mastermind-agent-relay/socket/agent-relay.sock"
A2_RETURN_FIELDS = frozenset(("coo_autonomy_armed", "coo_operator_harness_armed",
                              "ceo_submit_armed", "terminal_return_armed",
                              "coo_foreground_only"))


def _require_old_a2_pair(intent) -> None:
    """Read only the old A2 config/plist, never the A2/C1 token contents."""
    a2._assert_disarmed()
    if a2._assert_host_prepared() != intent.expected_sha:
        raise owner.TransactionEffectUnknown()
    if intent.previous_sha == intent.expected_sha:
        raise owner.TransactionEffectUnknown()
    manifest = release_manifest.verify(
        owner.SYSTEM_ROOT / "releases" / intent.previous_sha,
        intent.previous_sha, intent.previous_tree,
    )
    if (manifest.get("commit_sha") != intent.previous_sha
            or manifest.get("tree_sha") != intent.previous_tree
            or manifest.get("schema_version") != release_manifest.SCHEMA_VERSION):
        raise owner.TransactionEffectUnknown()
    original_config, original_plist = a2._legacy_pair_for_release(
        bot_user_id=intent.bot, previous_release_sha=intent.previous_sha,
        scopes=a2.SHARED_A2_SCOPES,
    )
    # Only metadata is permitted for the existing A2 token. The original
    # enrollment/CAS owner checks it too, but service restoration must not
    # assume that passing pair bytes proves the token inode still exists.
    token = a2.TOKEN_PATH.lstat()
    if (not stat.S_ISREG(token.st_mode) or stat.S_ISLNK(token.st_mode)
            or token.st_uid != a2.RELAY_UID or token.st_gid != a2.RELAY_GID
            or stat.S_IMODE(token.st_mode) != 0o400 or token.st_nlink != 1):
        raise owner.TransactionEffectUnknown()
    a2._rebind_acl(a2.TOKEN_PATH, token)
    if (owner.sha256_bytes(original_config) != intent.config_hash
            or owner.sha256_bytes(original_plist) != intent.plist_hash
            or a2._read_exact(a2.CONFIG_PATH, uid=a2.RELAY_UID,
                              gid=a2.RELAY_GID, mode=0o400) != original_config
            or a2._read_exact(a2.PLIST_PATH, uid=a2.PLIST_UID,
                              gid=a2.PLIST_GID, mode=0o644) != original_plist):
        raise owner.TransactionEffectUnknown()


def _candidate(prior):
    if (any(prior.control.get(k) is not False for k in A2_RETURN_FIELDS)
            or prior.worker.get("operator_harness_armed") is not False
            or prior.control.get("terminal_return_socket_path")
               not in (PERSISTENT_SOCKET, LEGACY_SOCKET)):
        raise owner.TransactionEffectUnknown()
    value = dict(prior.control, terminal_return_socket_path=LEGACY_SOCKET)
    raw = owner.encode_config(value)
    return owner.CandidateConfigs(
        control=value, worker=prior.worker, control_bytes=raw,
        worker_bytes=prior.worker_bytes, control_sha256=owner.sha256_bytes(raw),
        worker_sha256=prior.worker_sha256,
    )


def _rebased_disarm_receipt(tx, receipt):
    if (receipt.get("state") != "DISARMED"
            or receipt.get("control_config_sha256") != tx.prior_configs.control_sha256
            or receipt.get("worker_config_sha256") != tx.prior_configs.worker_sha256
            or tx.candidates != _candidate(tx.prior_configs)):
        raise owner.TransactionEffectUnknown()
    result = copy.deepcopy(receipt)
    result.update(
        control_config_sha256=tx.candidates.control_sha256,
        prior_control_config_sha256=tx.prior_configs.control_sha256,
        transaction_id=tx.transaction_id,
    )
    return result


class ProductionA2ControlRestorationHost(owner.ProductionCeoSubmitHost):
    """The existing AUTONOMY_TRANSACTION and Config/Launchd owners, no new store."""

    def _current_receipt(self):
        try:
            owner.AUTONOMY_RECEIPT.lstat()
        except FileNotFoundError:
            return b""
        raw, _ = owner._read_root_file(
            owner.AUTONOMY_RECEIPT, modes=frozenset({0o444}), uid=0, gid=0,
        )
        if not raw:
            raise owner.TransactionEffectUnknown()
        return raw

    def _seal_generation(self, generation, tx, *, operation):
        if operation != OPERATION:
            raise owner.TransactionEffectUnknown()
        prior = self._current_receipt()
        target = b""
        if prior:
            document, metadata = owner.load_receipt_file(owner.AUTONOMY_RECEIPT)
            if json.loads(prior) != document:
                raise owner.TransactionEffectUnknown()
            validate_disarmed_interlock_document(
                document, metadata=metadata,
                control_config_sha256=tx.prior_configs.control_sha256,
                worker_config_sha256=tx.prior_configs.worker_sha256,
            )
            target = owner._encoded_json(_rebased_disarm_receipt(tx, document))
        owner.ProductionTransactionHost._seal_generation(
            self, generation, tx, operation=operation,
        )
        owner._atomic_file(
            generation / owner._A2_RESTORE_RECEIPT_ARCHIVE, prior,
            mode=0o400, uid=0, gid=0, replace=False,
        )
        marker = self._manifest_document(tx, "LOCKED", operation=operation)
        marker.update(
            a2_prior_receipt_present=bool(prior),
            a2_prior_receipt_sha256=owner.sha256_bytes(prior),
            a2_target_receipt_sha256=owner.sha256_bytes(target),
        )
        owner._atomic_file(
            generation / owner._TRANSACTION_MANIFEST_NAME,
            owner._encoded_json(marker), mode=0o400, uid=0, gid=0, replace=True,
        )
        owner._fsync_directory(generation)

    def new_transaction_id(self):
        # Fresh publications may not silently adopt a foreign existing marker.
        return "autonomy-" + owner.secrets.token_hex(6)

    def _receipt_pair(self, tx):
        if (self._transaction_owner_fd is None
                or self._active_transaction is not tx):
            raise owner.TransactionEffectUnknown()
        self._verify_published_inode(self._transaction_owner_fd)
        manifest = self._manifest()
        if (manifest["operation"] != OPERATION
                or manifest["transaction_id"] != tx.transaction_id
                or manifest["expected_sha"] != tx.expected_sha
                or not owner._A2_RESTORE_RECEIPT_FIELDS <= set(manifest)):
            raise owner.TransactionEffectUnknown()
        old, _ = owner._read_root_file(
            owner.AUTONOMY_TRANSACTION / owner._A2_RESTORE_RECEIPT_ARCHIVE,
            modes=frozenset({0o400}), uid=0, gid=0,
        )
        if (owner.sha256_bytes(old) != manifest["a2_prior_receipt_sha256"]
                or bool(old) is not manifest["a2_prior_receipt_present"]):
            raise owner.TransactionEffectUnknown()
        new = owner._encoded_json(_rebased_disarm_receipt(tx, json.loads(old))) if old else b""
        if owner.sha256_bytes(new) != manifest["a2_target_receipt_sha256"]:
            raise owner.TransactionEffectUnknown()
        return old, new

    def verify_receipt(self, tx, *, target):
        pair = self._receipt_pair(tx)
        if self._current_receipt() != pair[1 if target else 0]:
            raise owner.TransactionEffectUnknown()

    def publish_receipt(self, tx):
        self.verify_state(tx, target=True)
        before, after = self._receipt_pair(tx)
        self.verify_receipt(tx, target=False)
        if before:
            owner._atomic_file(
                owner.AUTONOMY_RECEIPT, after,
                mode=0o444, uid=0, gid=0, replace=True,
            )
        self.verify_receipt(tx, target=True)
        self._persist_phase(tx, "A2_RECEIPT_REBOUND")

    def checked_configs(self, expected_sha):
        if self.require_exact_install(expected_sha) != expected_sha:
            raise owner.TransactionEffectUnknown()
        self.require_services_already_stopped()
        self.require_service_uids_quiescent()
        prior = self.load_unarmed_configs(expected_sha)
        self.require_runtime_quiescent(prior)
        return prior

    def verify_state(self, tx, *, target):
        self.check_intent()
        current = self.checked_configs(tx.expected_sha)
        required = tx.candidates.control_bytes if target else tx.prior_configs.control_bytes
        if (current.control_bytes != required
                or current.worker_bytes != tx.prior_configs.worker_bytes
                or _candidate(tx.prior_configs) != tx.candidates):
            raise owner.TransactionEffectUnknown()

    def validate_candidates(self, tx):
        value, raw, worker = self._read_validated_control_candidate(tx)
        if (value != dict(tx.candidates.control)
                or raw != tx.candidates.control_bytes
                or worker != tx.prior_configs.worker_bytes):
            raise owner.TransactionEffectUnknown()
        self._persist_phase(tx, "CANDIDATES_VALIDATED")

    def check_intent(self):
        _require_old_a2_pair(self._a2_intent)

    def settle_readback(self, tx):
        self.verify_state(tx, target=True)
        self.verify_receipt(tx, target=True)
        self._persist_phase(tx, "A2_CONTROL_RESTORED")
        self.complete_transaction(tx)
        return tx.transaction_id

    def reconcile(self, intent):
        owner.require_root_privilege(self.effective_uid())
        self._a2_intent = intent
        self.checked_configs(intent.expected_sha)
        self._claim_transaction_owner()
        manifest = self._manifest()
        if (manifest["operation"] != OPERATION
                or manifest["expected_sha"] != intent.expected_sha
                or manifest["phase"] not in {
                    "LOCKED", "CANDIDATES_WRITTEN", "CANDIDATES_VALIDATED",
                    "CONTROL_REPLACED", "A2_RECEIPT_REBOUND",
                    "A2_CONTROL_RESTORED", "CONTROL_OBSERVATION_PUBLISHED",
                }):
            raise owner.TransactionEffectUnknown()
        previous = self._archived_configs(intent.expected_sha)
        target = _candidate(previous)
        if (manifest["target_control_sha256"] != target.control_sha256
                or manifest["target_worker_sha256"] != target.worker_sha256
                or previous.control_sha256 != intent.control_hash):
            raise owner.TransactionEffectUnknown()
        tx = owner.TransactionContext(
            manifest["transaction_id"], intent.expected_sha, previous, target, None,
        )
        self._active_transaction = tx
        return self.settle_readback(tx)


def execute(host, intent):
    owner.require_root_privilege(host.effective_uid())
    host.require_transaction_absent()
    host._a2_intent = intent
    host.check_intent()
    prior = host.checked_configs(intent.expected_sha)
    target = _candidate(prior)
    if prior.control.get("terminal_return_socket_path") == LEGACY_SOCKET:
        # Idempotency must also prove the paired receipt and A2 fixed consumer
        # configuration before reporting positive read-only replay.
        qualify_restored_readside(host, intent)
        return None
    if prior.control_sha256 != intent.control_hash:
        raise owner.TransactionEffectUnknown()
    tx = owner.TransactionContext(
        host.new_transaction_id(), intent.expected_sha, prior, target, None,
    )
    host._active_transaction = tx
    host._create_marker(tx, operation=OPERATION)
    try:
        host.verify_state(tx, target=False)
        host.verify_receipt(tx, target=False)
        host.write_candidates(tx)
        host.validate_candidates(tx)
        host.verify_state(tx, target=False)
        host.verify_receipt(tx, target=False)
        host.replace_control_config(tx)
        host.verify_state(tx, target=True)
        host.publish_receipt(tx)
        return host.settle_readback(tx)
    except Exception:
        # Do not replay or make a second write after uncertain publication.
        raise owner.TransactionEffectUnknown() from None


def qualify_restored_readside(host, intent) -> None:
    """Read-only fixed service-start gate after the global restore settled.

    A2 and Control/C1 must be unloaded; service-control.sh owns every actual
    start. Never attempt to repair foreign/missing files or start a service.
    """
    owner.require_root_privilege(host.effective_uid())
    host.require_transaction_absent()
    host._a2_intent = intent
    _require_old_a2_pair(intent)
    current = host.checked_configs(intent.expected_sha)
    if (current.control.get("terminal_return_armed") is not False
            or current.control.get("terminal_return_socket_path") != LEGACY_SOCKET
            or current.worker.get("operator_harness_armed") is not False):
        raise owner.TransactionEffectUnknown()
    # Reconstruct the one permitted preimage from the restored Control
    # document. Binding the caller's original digest even AFTER transaction
    # settlement prevents a foreign/incorrect witness from starting services.
    original_control = dict(current.control, terminal_return_socket_path=PERSISTENT_SOCKET)
    if owner.sha256_bytes(owner.encode_config(original_control)) != intent.control_hash:
        raise owner.TransactionEffectUnknown()
    prior = host._current_receipt()
    if prior:
        document, metadata = owner.load_receipt_file(owner.AUTONOMY_RECEIPT)
        if json.loads(prior) != document:
            raise owner.TransactionEffectUnknown()
        validate_disarmed_interlock_document(
            document, metadata=metadata,
            control_config_sha256=current.control_sha256,
            worker_config_sha256=current.worker_sha256,
        )


def intent_from_args(args):
    return SimpleNamespace(
        expected_sha=args.expected_sha,
        control_hash=args.expected_control_sha256,
        previous_sha=args.expected_previous_release_sha,
        previous_tree=args.expected_previous_tree_sha,
        config_hash=args.expected_previous_config_sha256,
        plist_hash=args.expected_previous_plist_sha256,
        bot=args.expected_bot_user_id,
    )


def run_command(args, *, host=None):
    host = ProductionA2ControlRestorationHost() if host is None else host
    try:
        intent = intent_from_args(args)
        if args.command == "a2-restore-controller-socket":
            transaction_id = execute(host, intent)
        elif args.command == "a2-restore-controller-socket-reconcile":
            transaction_id = host.reconcile(intent)
        elif args.command == "a2-restored-readside-preflight":
            qualify_restored_readside(host, intent)
            transaction_id = None
        else:
            raise ValueError("unrecognized A2 controller restore")
        result = owner.operation_document(
            code="a2_controller_socket_restored",
            state="UNARMED", status="A2_CONTROLLER_SOCKET_RESTORED",
            transaction_id=transaction_id, replayed=transaction_id is None,
        )
        rc = 0
    except Exception:
        result = owner.operation_document(
            code="effect_unknown", state="UNKNOWN", status="EFFECT_UNKNOWN",
            transaction_id=None,
        )
        rc = 2
    finally:
        if host._transaction_owner_fd is not None:
            host._release_transaction_owner()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return rc
