"""Bounded grant publication inside the existing global autonomy transaction.

This module extends that owner's control-only mechanics. It has no independent
lock, scheduler, provider sender, worker lifecycle, or public endpoint.
"""
from __future__ import annotations

import dataclasses
import grp
import json
import os
import re
import subprocess
import time
from pathlib import Path

from control_plane.dialogue_wake_canary_activation import (
    DialogueWakeCanaryActivationGrant, DialogueWakeCanaryCurrentFacts,
    DialogueWakeCanaryProfile, IDENTITY_FIELDS, MAX_VALIDITY_SECONDS,
    match_dialogue_wake_canary_activation,
)
from control_plane.dialogue_wake_canary_publication import (
    DialogueWakeCanaryPublicationReceipt, PUBLICATION_OPERATION,
    build_publication_receipt, canonical_digest, verify_publication_receipt,
)
from ops.executive_os import autonomy_control as owner

RECEIPT_PATH = owner.CONFIG_ROOT / "dialogue-wake-canary-publication-v1.json"
_ABSENT = b'{"schema":"mastermind.dialogue_canary_receipt_absent/v1"}\n'


def derive_candidate(configs, grant):
    """Only the grant may change; all arm flags and worker bytes are preserved."""
    if type(grant) is not DialogueWakeCanaryActivationGrant:
        raise ValueError("parsed grant required")
    control = dict(configs.control)
    control["dialogue_wake_canary_activation"] = grant.to_dict()
    raw = owner.encode_config(control)
    candidate = owner.CandidateConfigs(
        control=control, worker=configs.worker, control_bytes=raw,
        worker_bytes=configs.worker_bytes, control_sha256=owner.sha256_bytes(raw),
        worker_sha256=configs.worker_sha256,
    )
    require_preservation(configs, candidate)
    return candidate


def require_preservation(prior, candidate):
    before, after = dict(prior.control), dict(candidate.control)
    before.pop("dialogue_wake_canary_activation", None)
    after.pop("dialogue_wake_canary_activation", None)
    if (before != after or candidate.worker != prior.worker
            or candidate.worker_bytes != prior.worker_bytes
            or candidate.worker_sha256 != prior.worker_sha256):
        raise owner.TransactionEffectUnknown()


def _read_receipt():
    try:
        RECEIPT_PATH.lstat()
    except FileNotFoundError:
        return None, _ABSENT
    value, raw = owner._root_json(
        RECEIPT_PATH, modes=frozenset({0o444}), uid=0, gid=0,
    )
    return DialogueWakeCanaryPublicationReceipt.from_dict(value), raw


def load_verified_profile(*, control_sha256, release_sha, grant, worker_sha256=None):
    """Read only the fixed root receipt; disagreement is explicitly disarmed."""
    if grant is None:
        return DialogueWakeCanaryProfile(None)
    try:
        receipt, _raw = _read_receipt()
        verify_publication_receipt(
            receipt, grant=grant, installed_release_sha=release_sha,
            control_config_sha256=control_sha256,
            # Control UID450 cannot read the private worker config. Its exact
            # bytes were checked and sealed by the root publisher; this read
            # verifies publication provenance, not a fresh worker-config claim.
            worker_config_sha256=(receipt.worker_config_sha256
                                  if worker_sha256 is None else worker_sha256),
        )
    except Exception:
        return DialogueWakeCanaryProfile(None)
    return DialogueWakeCanaryProfile(grant)


class ProductionDialogueCanaryHost(owner.ProductionCeoSubmitHost):
    """Reuse only the incumbent global marker and control-only host machinery."""

    def __init__(self):
        super().__init__()
        self._sealed_identity = None
        self._prior_receipt = None
        self._target_receipt = None

    @staticmethod
    def now_epoch_seconds():
        return int(time.time())

    def begin_ceo_submit_transaction(self, *args, **kwargs):
        raise owner.TransactionEffectUnknown()

    def _manifest_document(self, transaction, phase, *, operation):
        value = super()._manifest_document(transaction, phase, operation=operation)
        if operation != PUBLICATION_OPERATION or self._sealed_identity is None:
            raise owner.TransactionEffectUnknown()
        # Recovery may restore prior bytes, but never relabel the original
        # target hashes: every partial postimage remains classifiable after crash.
        value.update(self._sealed_identity)
        value["phase"] = phase
        return value

    def _seal_generation(self, generation, transaction, *, operation):
        if operation != PUBLICATION_OPERATION or self._prior_receipt is None:
            raise owner.TransactionEffectUnknown()
        super()._seal_generation(generation, transaction, operation=operation)
        owner._atomic_file(
            generation / owner._CANARY_RECEIPT_ARCHIVE, self._prior_receipt,
            mode=0o400, uid=0, gid=0, replace=False,
        )
        owner._fsync_directory(generation)

    def begin_publication(self, transaction, receipt):
        self.require_transaction_absent()
        old, raw = _read_receipt()
        prior_grant = transaction.prior_configs.control.get("dialogue_wake_canary_activation")
        if prior_grant is not None:
            parsed_prior = DialogueWakeCanaryActivationGrant.from_dict(prior_grant)
            if self.now_epoch_seconds() < parsed_prior.expires_at_epoch_seconds:
                raise ValueError("an unexpired canary publication cannot be replaced")
            verify_publication_receipt(
                old, grant=parsed_prior,
                installed_release_sha=transaction.expected_sha,
                control_config_sha256=transaction.prior_configs.control_sha256,
                worker_config_sha256=transaction.prior_configs.worker_sha256,
            )
        elif old is not None:
            raise ValueError("unbound prior publication receipt")
        self._prior_receipt = raw
        self._target_receipt = owner._encoded_json(receipt.to_dict())
        self._sealed_identity = owner.ProductionTransactionHost._manifest_document(
            transaction, "LOCKED", operation=PUBLICATION_OPERATION,
        )
        self._sealed_identity.pop("phase")
        self._sealed_identity.update(
            prior_canary_receipt_present=old is not None,
            prior_canary_receipt_sha256=owner.sha256_bytes(raw),
            target_canary_receipt_sha256=owner.sha256_bytes(self._target_receipt),
        )
        self._active_transaction = transaction
        self._create_marker(transaction, operation=PUBLICATION_OPERATION)
        # Recheck preimages under the held canonical marker.
        current = self.load_ceo_submit_configs(transaction.expected_sha)
        if (current.control_sha256 != transaction.prior_configs.control_sha256
                or current.worker_sha256 != transaction.prior_configs.worker_sha256
                or _read_receipt()[1] != raw):
            raise owner.TransactionEffectUnknown()

    def validate_candidates(self, transaction):
        value, raw, worker_raw = self._read_validated_control_candidate(transaction)
        require_preservation(transaction.prior_configs, transaction.candidates)
        if (value != transaction.candidates.control
                or owner.sha256_bytes(raw) != transaction.candidates.control_sha256
                or worker_raw != transaction.prior_configs.worker_bytes):
            raise owner.TransactionEffectUnknown()
        self._persist_phase(transaction, "CANDIDATES_VALIDATED")

    def write_publication_receipt(self, transaction):
        if self._target_receipt is None or self._transaction_owner_fd is None:
            raise owner.TransactionEffectUnknown()
        current, raw = _read_receipt()
        if raw != self._prior_receipt:
            raise owner.TransactionEffectUnknown()
        owner._atomic_file(
            RECEIPT_PATH, self._target_receipt, mode=0o444, uid=0, gid=0,
            replace=current is not None,
        )
        if _read_receipt()[1] != self._target_receipt:
            raise owner.TransactionEffectUnknown()
        self._persist_phase(transaction, "CANARY_RECEIPT_REPLACED")

    def prove_control_config_bound(self, transaction, *, restored=False):
        digest = (transaction.prior_configs.control_sha256 if restored
                  else transaction.candidates.control_sha256)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if (self._loaded(owner.CONTROL_LABEL)
                    and self._control_config_probe(transaction.expected_sha, digest)):
                self._persist_phase(transaction, "CONTROL_CONFIG_BOUND")
                return
            time.sleep(1)
        raise RuntimeError("control did not bind the exact publication configuration")

    def derive_proposal(self, *, expected_sha, read_ref, validity_seconds):
        # The installed Relay accepts only UID450. Use its existing read identity,
        # fixed pinned source and empty environment; never change the peer ACL.
        release = owner.SYSTEM_ROOT / "releases" / expected_sha
        code = (
            "import sys;sys.path.insert(0,sys.argv[1]);"
            "from integrations.session_bridge.canary_source import installed_proposal_json;"
            "print(installed_proposal_json(sys.argv[2],sys.argv[3],int(sys.argv[4])))"
        )
        completed = subprocess.run([
            "/usr/bin/sudo", "-u", owner.CONTROL_USER, "/usr/bin/env", "-i",
            f"HOME={owner.RUNTIME_ROOT / 'control' / 'home'}",
            "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "LANG=C.UTF-8", "LC_ALL=C.UTF-8",
            "PYTHONDONTWRITEBYTECODE=1", os.fspath(owner.PINNED_PYTHON),
            "-I", "-S", "-B", "-c", code, os.fspath(release),
            expected_sha, read_ref, str(validity_seconds),
        ], cwd=release, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=30, check=False)
        if completed.returncode or len(completed.stdout) > 16384:
            raise ValueError("current continuation source unavailable")
        value = json.loads(completed.stdout)
        if type(value) is not dict or set(value) != {"grant", "read_ref", "source_event_sha256", "facts_sha256"}:
            raise ValueError("source proposal is malformed")
        from integrations.session_bridge.canary_source import CanaryGrantProposal
        grant = DialogueWakeCanaryActivationGrant.from_dict(value["grant"])
        facts = DialogueWakeCanaryCurrentFacts(**{k: getattr(grant, k) for k in IDENTITY_FIELDS})
        if (value["read_ref"] != read_ref or grant.installed_release_sha != expected_sha
                or grant.expires_at_epoch_seconds - grant.valid_from_epoch_seconds != validity_seconds
                or value["facts_sha256"] != canonical_digest(facts.to_dict())):
            raise ValueError("source proposal binding changed")
        return CanaryGrantProposal(
            grant=grant, read_ref=read_ref, source_event_sha256=value["source_event_sha256"],
            facts_sha256=value["facts_sha256"],
        )

    def refresh_proposal(self, proposal):
        fresh = self.derive_proposal(
            expected_sha=proposal.grant.installed_release_sha, read_ref=proposal.read_ref,
            validity_seconds=proposal.grant.expires_at_epoch_seconds - proposal.grant.valid_from_epoch_seconds,
        )
        facts = DialogueWakeCanaryCurrentFacts(**{k: getattr(fresh.grant, k) for k in IDENTITY_FIELDS})
        match_dialogue_wake_canary_activation(
            proposal.grant, facts, now_epoch_seconds=fresh.grant.valid_from_epoch_seconds,
        )
        if (fresh.source_event_sha256 != proposal.source_event_sha256
                or fresh.facts_sha256 != proposal.facts_sha256):
            raise ValueError("source changed before publication")

    def rollback_publication(self, transaction):
        manifest = self._manifest()
        if (self._transaction_owner_fd is None
                or manifest["operation"] != PUBLICATION_OPERATION
                or manifest["transaction_id"] != transaction.transaction_id):
            raise owner.TransactionEffectUnknown()
        current = self.load_ceo_submit_configs(transaction.expected_sha)
        _receipt, raw = _read_receipt()
        if (current.control_sha256 not in {
                manifest["prior_control_sha256"], manifest["target_control_sha256"]}
                or current.worker_sha256 != manifest["prior_worker_sha256"]
                or owner.sha256_bytes(raw) not in {
                    manifest["prior_canary_receipt_sha256"], manifest["target_canary_receipt_sha256"]}):
            raise owner.TransactionEffectUnknown()
        archive = owner.AUTONOMY_TRANSACTION / owner._CANARY_RECEIPT_ARCHIVE
        prior_raw, _info = owner._read_root_file(archive, modes=frozenset({0o400}), uid=0, gid=0)
        if owner.sha256_bytes(prior_raw) != manifest["prior_canary_receipt_sha256"]:
            raise owner.TransactionEffectUnknown()
        if not manifest["prior_canary_receipt_present"] and prior_raw != _ABSENT:
            raise owner.TransactionEffectUnknown()
        candidate, _ = self._candidate_paths(transaction.transaction_id)
        self._remove_candidate(candidate)
        owner._atomic_file(
            candidate, transaction.prior_configs.control_bytes, mode=0o440,
            uid=0, gid=grp.getgrnam(owner.CONTROL_GROUP).gr_gid, replace=False,
        )
        self._replace_candidate(candidate, owner.CONTROL_CONFIG,
                                gid=grp.getgrnam(owner.CONTROL_GROUP).gr_gid)
        if manifest["prior_canary_receipt_present"]:
            owner._atomic_file(RECEIPT_PATH, prior_raw, mode=0o444, uid=0, gid=0,
                               replace=_receipt is not None)
        elif _receipt is not None:
            RECEIPT_PATH.unlink()
            owner._fsync_directory(owner.CONFIG_ROOT)
        self._persist_phase(transaction, "CANARY_PREIMAGES_RESTORED")
        if self._loaded(owner.CONTROL_LABEL):
            if not self._control_config_probe(transaction.expected_sha, transaction.prior_configs.control_sha256):
                self.reconcile_control_service(transaction.expected_sha)
            self.prove_control_config_bound(transaction, restored=True)
        self._restore_control_launchd_preimage_if_recorded(transaction)
        restored = self.load_ceo_submit_configs(transaction.expected_sha)
        if (restored.control_bytes != transaction.prior_configs.control_bytes
                or restored.worker_bytes != transaction.prior_configs.worker_bytes
                or _read_receipt()[1] != prior_raw):
            raise owner.TransactionEffectUnknown()
        self.complete_transaction(transaction)

    def recover_publication(self, expected_sha):
        self.effective_uid()
        self.require_exact_install(expected_sha)
        self._claim_transaction_owner()
        manifest = self._manifest()
        if manifest["operation"] != PUBLICATION_OPERATION or manifest["expected_sha"] != expected_sha:
            raise owner.TransactionEffectUnknown()
        prior = self._archived_configs(expected_sha)
        self._sealed_identity = {k: v for k, v in manifest.items() if k != "phase"}
        candidates = owner.CandidateConfigs(
            control=prior.control, worker=prior.worker,
            control_bytes=prior.control_bytes, worker_bytes=prior.worker_bytes,
            control_sha256=prior.control_sha256, worker_sha256=prior.worker_sha256,
        )
        transaction = owner.TransactionContext(manifest["transaction_id"], expected_sha, prior, candidates, None)
        self._active_transaction = transaction
        self.rollback_publication(transaction)
        return transaction.transaction_id


def execute_publication(host, *, expected_sha, read_ref, validity_seconds):
    host.effective_uid()
    if (type(validity_seconds) is not int or not 0 < validity_seconds <= MAX_VALIDITY_SECONDS
            or type(read_ref) is not str
            or re.fullmatch(r"session-reply-[0-9a-f]{64}", read_ref) is None):
        raise ValueError("bounded continuation reference required")
    host.require_exact_install(expected_sha)
    host.require_transaction_absent()
    configs = host.load_ceo_submit_configs(expected_sha)
    proposal = host.derive_proposal(
        expected_sha=expected_sha, read_ref=read_ref, validity_seconds=validity_seconds,
    )
    candidate = derive_candidate(configs, proposal.grant)
    transaction = owner.TransactionContext(
        host.new_transaction_id(), expected_sha, configs, candidate, None,
    )
    receipt = build_publication_receipt(
        grant=proposal.grant,
        current=DialogueWakeCanaryCurrentFacts(**{k: getattr(proposal.grant, k) for k in IDENTITY_FIELDS}),
        transaction_id=transaction.transaction_id,
        control_config_sha256=candidate.control_sha256, worker_config_sha256=candidate.worker_sha256,
        source_read_ref=read_ref, source_event_sha256=proposal.source_event_sha256,
        published_epoch_seconds=proposal.grant.valid_from_epoch_seconds,
    )
    host.begin_publication(transaction, receipt)
    try:
        host.refresh_proposal(proposal)
        host.write_candidates(transaction)
        host.validate_candidates(transaction)
        host.refresh_proposal(proposal)
        host.replace_control_config(transaction)
        host.write_publication_receipt(transaction)
        host.reconcile_control_service(expected_sha)
        host.prove_control_config_bound(transaction)
        host.complete_transaction(transaction)
    except owner.TransactionEffectUnknown:
        raise
    except Exception as exc:
        try:
            host.rollback_publication(transaction)
        except Exception as rollback:
            raise owner.TransactionEffectUnknown() from rollback
        raise ValueError("canary publication rolled back") from exc
    return transaction.transaction_id


def run_command(args, *, host=None):
    host = ProductionDialogueCanaryHost() if host is None else host
    try:
        if args.command == "dialogue-canary-publish":
            transaction_id = execute_publication(
                host, expected_sha=args.expected_sha, read_ref=args.read_ref,
                validity_seconds=args.validity_seconds,
            )
            state = "DIALOGUE_CANARY_PUBLISHED"
        elif args.command == "dialogue-canary-reconcile":
            transaction_id = host.recover_publication(args.expected_sha)
            state = "DIALOGUE_CANARY_PREIMAGES_RESTORED"
        else:
            raise ValueError("unknown canary operation")
        document = owner.operation_document(
            code=state.lower(), state=state, status=state,
            transaction_id=transaction_id, replayed=False,
        )
        exit_code = 0
    except owner.TransactionEffectUnknown:
        document = owner.operation_document(
            code="effect_unknown", state="UNKNOWN", status="EFFECT_UNKNOWN",
            transaction_id=None,
        )
        exit_code = 2
    except Exception:
        # The public error never includes source messages, native handles,
        # subprocess output, or any filesystem/credential content.
        state = ("EFFECT_UNKNOWN" if args.command == "dialogue-canary-reconcile"
                 else "DIALOGUE_CANARY_UNVERIFIED")
        document = owner.operation_document(
            code=state.lower(), state="UNKNOWN", status=state, transaction_id=None,
        )
        exit_code = 2
    print(json.dumps(document, sort_keys=True, separators=(",", ":")))
    return exit_code
