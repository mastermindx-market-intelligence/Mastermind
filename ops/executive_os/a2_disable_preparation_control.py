"""A2 unloaded/disabled preparation under the existing global transaction owner.

The immutable transaction archive fences the sole launchctl disable attempt.
Recovery only reads the postcondition; it never dispatches another effect.
"""
from __future__ import annotations

import dataclasses
import json
import subprocess
from pathlib import Path

from ops.executive_os import autonomy_control as owner

OPERATION = "A2_DISABLE_PREPARATION"
RELAY_LABEL = "com.mastermind.executive.agent-relay"
RESERVED = (
    owner.CONFIG_ROOT / "agent-relay.token",
    owner.CONFIG_ROOT / "agent-relay.json",
    Path("/Library/LaunchDaemons/com.mastermind.executive.agent-relay.plist"),
    Path("/var/run/mastermind-agent-relay/agent-relay.sock"),
)


def unchanged_candidate(prior):
    return owner.CandidateConfigs(**{
        field.name: getattr(prior, field.name)
        for field in dataclasses.fields(owner.CandidateConfigs)
    })


class ProductionA2DisablePreparationHost(owner.ProductionCeoSubmitHost):
    def assert_artifacts_absent(self):
        for path in RESERVED:
            try:
                path.lstat()
            except FileNotFoundError:
                continue
            raise owner.TransactionEffectUnknown()

    @staticmethod
    def assert_unloaded():
        try:
            result = subprocess.run(
                ["/bin/launchctl", "print", "system/" + RELAY_LABEL],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=False, timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            raise owner.TransactionEffectUnknown() from None
        if result.returncode != 113:
            raise owner.TransactionEffectUnknown()

    def disabled_override(self):
        # A successfully parsed absent row is distinct from unreadable output.
        return self._read_launchd_disabled_override(RELAY_LABEL, allow_absent=True)

    @staticmethod
    def disable_once():
        # The return value is never proof of the postcondition.
        subprocess.run(
            ["/bin/launchctl", "disable", "system/" + RELAY_LABEL],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False, timeout=10,
        )

    def assert_preimages(self, transaction):
        self.require_exact_install(transaction.expected_sha)
        current = self.load_ceo_submit_configs(transaction.expected_sha)
        if (current.control_bytes != transaction.prior_configs.control_bytes
                or current.worker_bytes != transaction.prior_configs.worker_bytes):
            raise owner.TransactionEffectUnknown()

    def reconcile(self, transaction):
        self.assert_preimages(transaction)
        self.assert_artifacts_absent()
        self.assert_unloaded()
        if self.disabled_override() is not True:
            raise owner.TransactionEffectUnknown()
        self._persist_phase(transaction, "A2_DISABLE_VERIFIED")
        self.complete_transaction(transaction)
        return transaction.transaction_id

    def recover_preparation(self, expected_sha):
        self.effective_uid()
        self.require_exact_install(expected_sha)
        self._claim_transaction_owner()
        manifest = self._manifest()
        if (manifest["operation"] != OPERATION or manifest["expected_sha"] != expected_sha
                or manifest["phase"] not in {"LOCKED", "A2_DISABLE_DISPATCHED", "A2_DISABLE_VERIFIED"}
                or manifest["prior_control_sha256"] != manifest["target_control_sha256"]
                or manifest["prior_worker_sha256"] != manifest["target_worker_sha256"]):
            raise owner.TransactionEffectUnknown()
        prior = self._archived_configs(expected_sha)
        transaction = owner.TransactionContext(
            manifest["transaction_id"], expected_sha, prior, unchanged_candidate(prior), None)
        self._active_transaction = transaction
        # Even LOCKED may be recovered only by positive observation. A crash
        # never authorizes a new disable, and generic rollback cannot erase it.
        return self.reconcile(transaction)


def execute_preparation(host, expected_sha):
    host.effective_uid()
    host.require_exact_install(expected_sha)
    host.require_transaction_absent()
    prior = host.load_ceo_submit_configs(expected_sha)
    host.assert_artifacts_absent()
    host.assert_unloaded()
    if host.disabled_override() is True:
        return None  # proven already prepared, without a new effect or marker
    transaction = owner.TransactionContext(
        host.new_transaction_id(), expected_sha, prior, unchanged_candidate(prior), None)
    host._active_transaction = transaction
    host._create_marker(transaction, operation=OPERATION)
    try:
        host.assert_preimages(transaction)
        host.assert_artifacts_absent()
        host.assert_unloaded()
        if host.disabled_override() is True:
            return host.reconcile(transaction)
        host._persist_phase(transaction, "A2_DISABLE_DISPATCHED")
        try:
            host.disable_once()
        except (OSError, subprocess.SubprocessError):
            pass  # A failed/lost response still requires post-effect reconciliation.
        return host.reconcile(transaction)
    except Exception:
        # Preserve the global marker and archived identities on every uncertain
        # outcome, including a positive effect followed by failed verification.
        raise owner.TransactionEffectUnknown() from None


def run_command(args, *, host=None):
    host = ProductionA2DisablePreparationHost() if host is None else host
    try:
        if args.command == "a2-disable-prepare":
            transaction_id = execute_preparation(host, args.expected_sha)
        elif args.command == "a2-disable-prepare-reconcile":
            transaction_id = host.recover_preparation(args.expected_sha)
        else:
            raise ValueError("unknown A2 operation")
        document = owner.operation_document(
            code="a2_disable_prepared", state="A2_DISABLE_PREPARED", status="A2_DISABLE_PREPARED",
            transaction_id=transaction_id, replayed=transaction_id is None)
        exit_code = 0
    except Exception:
        document = owner.operation_document(
            code="effect_unknown", state="UNKNOWN", status="EFFECT_UNKNOWN", transaction_id=None)
        exit_code = 2
    finally:
        if host._transaction_owner_fd is not None:
            host._release_transaction_owner()
    print(json.dumps(document, sort_keys=True, separators=(",", ":")))
    return exit_code
