"""Same-run evidence transport only; no authentication, launch or retry owner."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

try:
    from . import fabric_launch_reservation as reservation
except ImportError:  # Immutable remote support bundle.
    import fabric_launch_reservation as reservation

SCHEMA = "mastermind.fabric_launch_snapshot/v1"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode() + b"\n"


def prepare_snapshot(source, log, destination, **identity):
    """Copy the exact reserved V2 context into its once-written upload sidecar."""
    correlation = reservation.load_correlation(source, **identity)
    retained = reservation.read_correlation_log(log, expected=correlation, **identity)
    value = {"schema_version": SCHEMA, "correlation": correlation,
             "reservation_sha256": retained["reservation_sha256"]}
    # Same O_EXCL, file+directory durability and consumed-name behavior as the
    # original reservation. This is transport evidence, not a second lifecycle.
    reservation._reserve_log_record(destination, value, b"")
    return hashlib.sha256(canonical(value)).hexdigest()


def load_snapshot(path, *, expected_sha256, **identity):
    if type(expected_sha256) is not str or not reservation.SHA.fullmatch(expected_sha256):
        raise reservation.ReservationRefused("bound_launch_snapshot_digest_invalid")

    def validate(value):
        if (type(value) is not dict or set(value) != {
                "schema_version", "correlation", "reservation_sha256"}
                or value["schema_version"] != SCHEMA):
            raise reservation.ReservationRefused("bound_launch_snapshot_shape")
        correlation = reservation.validate_correlation(value["correlation"], **identity)
        header = reservation.CORRELATION_PREFIX + canonical(correlation)
        if value["reservation_sha256"] != hashlib.sha256(header).hexdigest():
            raise reservation.ReservationRefused("bound_launch_snapshot_reservation_mismatch")
        if hashlib.sha256(canonical(value)).hexdigest() != expected_sha256:
            raise reservation.ReservationRefused("bound_launch_snapshot_changed")
        return value

    return reservation._load_file(path, validate)


def reserved_snapshot_digest(path, log, **identity):
    """Re-anchor the upload to the original O_EXCL log, not its own new hash.

    The log is the existing consumed-name fence. No extra launch/retry record
    is introduced. Remote validation still uses the literal digest returned
    here, so changes after this check also refuse at the remote boundary.
    """
    value = reservation._load_file(path, lambda value: value)
    digest = hashlib.sha256(canonical(value)).hexdigest()
    value = load_snapshot(path, expected_sha256=digest, **identity)
    retained = reservation.read_correlation_log(
        log, expected=value["correlation"], **identity)
    if retained["reservation_sha256"] != value["reservation_sha256"]:
        raise reservation.ReservationRefused("bound_launch_snapshot_reservation_mismatch")
    return digest


def remote_launch_arguments(home, run_id, environment):
    """Derive paths from the original run, never from prompt text or a caller path."""
    digest = environment.get("FABRIC_LAUNCH_SNAPSHOT_SHA256")
    if digest is None:
        return {}
    if type(run_id) is not str or not reservation.IDENT.fullmatch(run_id):
        raise reservation.ReservationRefused("bound_launch_run_invalid")
    directory = Path(home) / "lanes" / "tmp" / (run_id + ".launch-bound")
    value = load_snapshot(directory / "correlation.json", expected_sha256=digest,
                          run_id=run_id,
                          routing_root_id=environment.get("POOL_ORCHESTRATOR_ID"),
                          routing_parent_run_id=environment.get("POOL_PARENT_RUN_ID"))
    return {"launch_receipt_path": directory / "launch.json",
            "launch_receipt_metadata": value["correlation"]["runtime_binding"],
            "launch_receipt_context_sha256": digest}
