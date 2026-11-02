"""Explicit fixed-case reconciliation for the retained rc75 thermal refusal.

This command records a verified historical disposition only. It never dispatches
work, rewrites original evidence, retries, accepts a review, admits new work
or changes the thermal limit, route, admission or accounting policy. A partial
or invalid receipt stays preserved and unqualified; there is no deletion,
repair-in-place, generic recovery, quota successor or provider fallback.
"""
from __future__ import annotations

import json
import os
import re
import stat

import native_thermal_refusal_check as check

SCHEMA = "mastermind.fabric_thermal_refusal_reconciliation.v1"
DISPOSITION = "TERMINAL_ADMISSION_REFUSAL_RECONCILED_NO_REPLAY"


class PublicationUnqualified(check.Unqualified):
    """Creation was attempted; only fresh same-carrier readback can settle it."""
    effect_state = "EFFECT_UNKNOWN"


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode()


def receipt_path():
    return check.receipt_path()


def expected_receipt(proof):
    lease = proof["reconstructed_lease"]
    return {
        "schema": SCHEMA, "run_id": check.RUN, "root_id": check.ROOT,
        "parent_run_id": check.ROOT,
        "proof_sha256": proof["proof_sha256"],
        "artifact_sha256": proof["artifact_sha256"],
        "result_sha256": proof["result_sha256"],
        "result_bytes": proof["result_bytes"],
        "historical_source_sha256": proof["historical_source_sha256"],
        "launch_native_sources": proof["launch_native_sources"],
        "support_source_sha256": proof["support_source_sha256"],
        "compatible_generation": proof["compatible_generation"],
        "original_selected_generation_recorded": False,
        "disposition": DISPOSITION,
        "controller_rc": check.CONTROLLER_RC, "signal": check.CONTROLLER_SIGNAL,
        "reason": check.CONTROLLER_REASON,
        "reconstructed_lease_id": lease["lease_id"],
        "reconstructed_lease_state": lease["state"],
        "reconstructed_lease_granted_at": lease["granted_at"],
        "reconstructed_census_interval": proof["census_interval"],
        "lease_id_bound_by_run_artifact": False,
        "original_acquisition_receipt_claimed": False,
        "release_before_original_return_claimed": False,
        "worker_provider_execution_absent": True,
        "telemetry_transport_absence_claimed": False,
        "remote_cryptographic_attestation_claimed": False,
        "retry_allowed": False, "acceptance_eligible": False,
        "result_available": True, "new_work_admission": "UNCHANGED",
    }


def read_receipt(held, proof):
    raw = held.read(receipt_path(), mode=0o600, limit=65536)
    # Exact canonical bytes make unknown fields, duplicate keys, weak types,
    # different source/subject and partial writes ineligible.
    if raw != canonical(expected_receipt(proof)):
        raise check.Unqualified("reconciliation_receipt_unqualified")
    held.verify()
    return raw


def status_from_receipt():
    """A read-only exact-run projection; an absent receipt has no new meaning."""
    path = receipt_path()
    try:
        path.lstat()
    except FileNotFoundError:
        return None
    with check.EvidenceReadSet() as held:
        proof = check._historical_proof(held, check.RUN, check.ROOT,
                                        allow_reconciliation=True)
        raw = read_receipt(held, proof)
        check.exact_inventory(held.chain(check.state_dir()),
                              allow_reconciliation=True)
        check.exact_lane_inventory(held.chain(check.lanes_dir()))
        held.verify()
        return {
            "schema": "mastermind.fabric_task_status.v1", "run_id": check.RUN,
            "root_id": check.ROOT, "parent_run_id": check.ROOT,
            "state": "TERMINAL", "rc": check.CONTROLLER_RC,
            "signal": check.CONTROLLER_SIGNAL, "reason": check.CONTROLLER_REASON,
            "result_available": True, "result_bytes": check.RESULT_BYTES,
            "execution_absence_proven": True,
            "execution_absence_scope": (
                "original_request_remote_admission_worker_and_model_provider_execution"),
            "request_retained": True, "same_run_replay_allowed": False,
            "retry_allowed": False, "acceptance_eligible": False,
            "new_work_admission": "UNCHANGED",
            "reconciliation": {
                "schema": SCHEMA, "receipt_sha256": check.digest(raw),
                "proof_sha256": proof["proof_sha256"],
                "disposition": DISPOSITION,
                "telemetry_transport_absence_claimed": False,
                "original_selected_generation_recorded": False,
                "new_work_admission": "UNCHANGED",
            },
        }


def reconcile_original(run_id, root_id, expected_proof_sha256):
    """Append one exclusive receipt after a fresh proof; it is then read-only."""
    if (type(expected_proof_sha256) is not str
            or re.fullmatch("[a-f0-9]{64}", expected_proof_sha256) is None):
        raise check.Unqualified("expected_proof_digest_required")
    creation_attempted = False
    try:
        with check.EvidenceReadSet() as held:
            proof = check._historical_proof(held, run_id, root_id,
                                            allow_reconciliation=True)
            if proof["proof_sha256"] != expected_proof_sha256:
                raise check.Unqualified("expected_proof_digest_mismatch")
            path = receipt_path()
            chain = held.chain(path.parent)
            try:
                os.stat(path.name, dir_fd=chain.fd, follow_symlinks=False)
            except FileNotFoundError:
                exists = False
            else:
                exists = True
            if exists:
                raw = read_receipt(held, proof)
                check.exact_inventory(chain, allow_reconciliation=True)
                held.verify()
                return {"schema": SCHEMA, "action": "ALREADY_RECORDED",
                        "run_id": check.RUN, "root_id": check.ROOT,
                        "receipt_sha256": check.digest(raw),
                        "effect_state": "APPLIED", "receipt_written_by_this_call": False,
                        "proof_sha256": proof["proof_sha256"], "retry_allowed": False,
                        "worker_dispatch_performed": False,
                        "new_work_admission": "UNCHANGED"}
            # Keep every historical file and directory open through publication.
            # A failure after this exclusive creation leaves the receipt intact.
            held.verify()
            raw = canonical(expected_receipt(proof))
            creation_attempted = True
            fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=chain.fd)
            try:
                created = os.fstat(fd)
                if (not stat.S_ISREG(created.st_mode) or created.st_uid != os.getuid()
                        or stat.S_IMODE(created.st_mode) != 0o600
                        or created.st_nlink != 1):
                    raise check.Unqualified("new_receipt_custody")
                written = 0
                while written < len(raw):
                    count = os.write(fd, raw[written:])
                    if count <= 0:
                        raise OSError("short reconciliation receipt write")
                    written += count
                os.fsync(fd)
                after = os.fstat(fd)
                visible = os.stat(path.name, dir_fd=chain.fd, follow_symlinks=False)
                if (check.identity(after) != check.identity(visible)
                        or (created.st_dev, created.st_ino, created.st_uid,
                            created.st_mode, created.st_nlink)
                        != (after.st_dev, after.st_ino, after.st_uid,
                            after.st_mode, after.st_nlink)
                        or after.st_size != len(raw)):
                    raise check.Unqualified("new_receipt_identity_changed")
                held.verify()
                os.fsync(chain.fd)
                # Read the same visible receipt and bind it to the open writer
                # before reporting a committed disposition. A replaced same-byte
                # file fails.
                observed = read_receipt(held, proof)
                if (check.identity(os.fstat(fd)) != check.identity(after)
                        or check.identity(after) != check.identity(
                            os.stat(path.name, dir_fd=chain.fd, follow_symlinks=False))):
                    raise check.Unqualified("new_receipt_replaced_after_readback")
                check.exact_inventory(chain, allow_reconciliation=True)
                held.verify()
            finally:
                os.close(fd)
            return {"schema": SCHEMA, "action": "RECORDED", "run_id": check.RUN,
                    "root_id": check.ROOT, "receipt_sha256": check.digest(observed),
                    "effect_state": "APPLIED", "receipt_written_by_this_call": True,
                    "proof_sha256": proof["proof_sha256"], "retry_allowed": False,
                    "worker_dispatch_performed": False,
                    "new_work_admission": "UNCHANGED"}
    except Exception as exc:
        # This scope includes all retained-descriptor cleanup after publication.
        # A failed acknowledgment cannot erase a potentially visible receipt.
        if creation_attempted:
            raise PublicationUnqualified(
                "receipt_publication_unqualified:" + type(exc).__name__ + ": " + str(exc)) from exc
        raise
