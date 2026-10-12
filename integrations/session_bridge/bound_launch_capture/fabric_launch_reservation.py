"""Bind the existing remote_sub run-log reservation before its first effect.

This helper belongs inside the incumbent controller's O_EXCL reservation. It
adds no retry store or launch authority. A retained reservation means that an
effect may have happened; neither an empty nor a missing log proves unused
authority. Runtime/physical admission and authenticated collection remain with
the existing owners. Correlation supplied by a caller is not authentication.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat

PREFIX = b"FABRIC_BOUND_START_V1\t"
CORRELATION_PREFIX = b"FABRIC_BOUND_START_V2\t"
CORRELATION_SCHEMA = "mastermind.fabric_launch_correlation/v2"
LIMIT = 8192
IDS = frozenset({"root_id", "job_id", "attempt_id"})
DIGESTS = frozenset({"effective_grant_sha256", "commission_sha256",
                     "physical_binding_sha256", "start_request_sha256"})
IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")


class ReservationRefused(ValueError):
    """Closed error codes only; no source payload or credentials in errors."""


def validate_binding(value, *, run_id, root_id):
    if (type(value) is not dict or set(value) != IDS | DIGESTS
            or any(type(value[k]) is not str or not IDENT.fullmatch(value[k]) for k in IDS)
            or any(type(value[k]) is not str or not SHA.fullmatch(value[k]) for k in DIGESTS)
            or value["attempt_id"] != run_id or value["root_id"] != root_id):
        raise ReservationRefused("bound_launch_identity_invalid")
    return dict(value)


def validate_correlation(value, *, run_id, routing_root_id, routing_parent_run_id):
    """Keep Fabric lineage separate from Runtime Job identity; neither grants rights."""
    if (type(value) is not dict or set(value) != {
            "schema_version", "routing_root_id", "routing_parent_run_id", "runtime_binding"}
            or value["schema_version"] != CORRELATION_SCHEMA
            or any(type(value[k]) is not str or not IDENT.fullmatch(value[k])
                   for k in ("routing_root_id", "routing_parent_run_id"))
            or value["routing_root_id"] != routing_root_id
            or value["routing_parent_run_id"] != routing_parent_run_id
            or type(value["runtime_binding"]) is not dict):
        raise ReservationRefused("bound_launch_routing_invalid")
    binding = value["runtime_binding"]
    # Here Runtime root is syntax-checked only. Supplying it as its own expected
    # value does not authenticate it. The Backend must independently compare it
    # with the original Runtime Job; the Fabric routing root is a different ID.
    binding = validate_binding(binding, run_id=run_id, root_id=binding.get("root_id"))
    return {**value, "runtime_binding": binding}


def backend_binding(correlation):
    """Project Runtime identity into the bridge's exact five-field binding.

    Physical route and start hash are separate enclosing bridge fields, not
    permitted keys inside binding. Use backend_start_context for all seven.
    """
    fields = correlation["runtime_binding"]
    return {"root_id": fields["root_id"], "job_id": fields["job_id"],
            "attempt_id": fields["attempt_id"], "commission_sha256": fields["commission_sha256"],
            "effective_grant_digest": fields["effective_grant_sha256"]}


def backend_start_context(correlation):
    """Lossless bridge spelling/placement conversion; conveys no authority."""
    fields = correlation["runtime_binding"]
    return {"binding": backend_binding(correlation),
            "physical_binding_sha256": fields["physical_binding_sha256"],
            "start_request_sha256": fields["start_request_sha256"]}


def _decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ReservationRefused("bound_launch_duplicate_key")
            result[key] = value
        return result
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ReservationRefused("bound_launch_json_invalid") from exc


def _private_directory(path):
    if not path.is_absolute() or ".." in path.parts:
        raise ReservationRefused("bound_launch_path_invalid")
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077):
        raise ReservationRefused("bound_launch_directory_unsafe")
    return info


def _load_file(path, validate):
    """Read one owner-private input file; it conveys correlation, not authority."""
    path = Path(path)
    _private_directory(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) & 0o077 or before.st_nlink != 1
                or not 0 < before.st_size <= LIMIT):
            raise ReservationRefused("bound_launch_file_unsafe")
        raw = os.read(fd, LIMIT + 1)
        after, visible = os.fstat(fd), path.lstat()
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_mode", "st_uid", "st_nlink")
        if (len(raw) != before.st_size or len(raw) > LIMIT
                or tuple(getattr(before, f) for f in fields) != tuple(getattr(after, f) for f in fields)
                or (after.st_dev, after.st_ino) != (visible.st_dev, visible.st_ino)):
            raise ReservationRefused("bound_launch_input_moved")
        return validate(_decode(raw))
    finally:
        os.close(fd)


def load_binding(path, *, run_id, root_id):
    return _load_file(path, lambda value: validate_binding(value, run_id=run_id, root_id=root_id))


def load_correlation(path, *, run_id, routing_root_id, routing_parent_run_id):
    return _load_file(path, lambda value: validate_correlation(
        value, run_id=run_id, routing_root_id=routing_root_id,
        routing_parent_run_id=routing_parent_run_id))


def reserve_bound_log(path, binding, *, run_id, root_id):
    """Reserve the original log once. Any failure leaves its name consumed.

    FileExistsError is deliberately never interpreted as permission to resume,
    even when its bytes match. The existing owner must reconcile that run.
    """
    value = validate_binding(binding, run_id=run_id, root_id=root_id)
    return _reserve_log_record(path, value, PREFIX)


def reserve_correlation_log(path, correlation, *, run_id, routing_root_id, routing_parent_run_id):
    value = validate_correlation(correlation, run_id=run_id, routing_root_id=routing_root_id,
                                 routing_parent_run_id=routing_parent_run_id)
    return _reserve_log_record(path, value, CORRELATION_PREFIX)


def _reserve_log_record(path, value, prefix):
    record = prefix + json.dumps(value, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=True, allow_nan=False).encode() + b"\n"
    if len(record) > LIMIT:
        raise ReservationRefused("bound_launch_record_oversize")
    path = Path(path)
    before = _private_directory(path.parent)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    fd = None
    try:
        opened = os.fstat(directory)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ReservationRefused("bound_launch_directory_moved")
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        offset = 0
        while offset < len(record):
            written = os.write(fd, record[offset:])
            if written <= 0:
                raise ReservationRefused("bound_launch_short_write")
            offset += written
        os.fsync(fd)
        os.fsync(directory)
        after = _private_directory(path.parent)
        held = os.fstat(fd)
        if (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
            raise ReservationRefused("bound_launch_reservation_moved")
        visible = path.lstat()
        if ((held.st_dev, held.st_ino) != (visible.st_dev, visible.st_ino)
                or held.st_size != len(record) or held.st_nlink != 1):
            raise ReservationRefused("bound_launch_reservation_moved")
        return hashlib.sha256(record).hexdigest()
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)


def read_bound_log(path, *, expected, run_id, root_id):
    """Read the retained original header. This never reports safe-to-start."""
    value = validate_binding(expected, run_id=run_id, root_id=root_id)
    return _read_log_record(path, value, PREFIX,
                            lambda row: validate_binding(row, run_id=run_id, root_id=root_id))


def read_correlation_log(path, *, expected, run_id, routing_root_id, routing_parent_run_id):
    def validate(row):
        return validate_correlation(row, run_id=run_id, routing_root_id=routing_root_id,
                                    routing_parent_run_id=routing_parent_run_id)
    return _read_log_record(path, validate(expected), CORRELATION_PREFIX, validate)


def _read_log_record(path, value, prefix, validate):
    path = Path(path)
    _private_directory(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o077 or info.st_nlink != 1):
            raise ReservationRefused("bound_launch_log_unsafe")
        raw = os.read(fd, LIMIT + 1)
        line, separator, _tail = raw.partition(b"\n")
        if not separator or not line.startswith(prefix) or len(line) + 1 > LIMIT:
            raise ReservationRefused("bound_launch_header_unavailable")
        retained = validate(_decode(line[len(prefix):]))
        if os.pread(fd, len(line) + 1, 0) != line + b"\n":
            raise ReservationRefused("bound_launch_header_moved")
        visible = path.lstat()
        if (info.st_dev, info.st_ino) != (visible.st_dev, visible.st_ino):
            raise ReservationRefused("bound_launch_log_moved")
        if retained != value:
            raise ReservationRefused("bound_launch_request_conflict")
        return {"binding": retained, "reservation_sha256": hashlib.sha256(line + b"\n").hexdigest(),
                "start_authorized": False, "effect_state": "UNRESOLVED_BY_RESERVATION"}
    finally:
        os.close(fd)
