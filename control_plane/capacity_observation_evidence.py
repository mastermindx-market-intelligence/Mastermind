"""Retain one existing read-only Wake observation; report an explicit input set.

These private evidence files are not a campaign registry, scheduler or Runtime
state. Source bytes and host UTC readings do not attest an installed release,
continuous coverage, model reasoning time or product acceptance. A report never
qualifies the R2 seven-day campaign, even when recorded timestamps span a week.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import time
from typing import Callable

from control_plane.fs_security import FilesystemSecurityError, has_macos_acl
from control_plane.wake_ledger import SourceReadHealth

RECEIPT_SCHEMA = "mastermind.capacity_observation_receipt.v1"
INSTALLED_RECEIPT_SCHEMA = "mastermind.capacity_observation_receipt.v2"
REPORT_SCHEMA = "mastermind.capacity_observation_collection.v1"
MAX_RECEIPT_BYTES = 16 * 1024 * 1024
MAX_COLLECTION_BYTES = 128 * 1024 * 1024
MAX_RECEIPTS = 512
_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z\Z")
_UNPROVEN = (
    "installed_source_and_runtime_attestation", "continuous_seven_day_coverage",
    "ordinary_and_busy_demand_census", "model_reasoning_duration",
    "secretary_desktop_occupancy_and_consumption", "job_queue_delay",
    "complete_review_backlog", "original_parent_disposition_consumption",
    "actual_total_cost_per_accepted_outcome", "relieved_principal_rejection",
)


class ObservationEvidenceError(ValueError):
    """Evidence custody, shape or bounds cannot be established."""


def _require(condition, code):
    if not condition:
        raise ObservationEvidenceError(code)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json(raw: str | bytes):
    def unique(items):
        value = {}
        for key, item in items:
            _require(key not in value, "DUPLICATE_JSON_KEY")
            value[key] = item
        return value

    def invalid(_):
        raise ObservationEvidenceError("NONFINITE_JSON")

    try:
        return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)
    except RecursionError as exc:
        raise ObservationEvidenceError("JSON_NESTING_LIMIT") from exc


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _stamp(value) -> datetime:
    _require(isinstance(value, str) and _STAMP.fullmatch(value) is not None,
             "INVALID_OBSERVATION_TIMESTAMP")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class _EvidenceFile:
    """Hold the private parent and one direct, single-link receipt descriptor."""

    def __init__(self, path: Path, *, create: bool):
        self.path = Path(os.path.abspath(path))
        self.parent = self.path.parent
        self.directory = self.fd = None
        try:
            # Resolve only for a comparison: neither acquisition follows an alias.
            _require(self.parent.resolve(strict=True) == self.parent,
                     "EVIDENCE_PARENT_ALIAS")
            before = self.parent.lstat()
            self.directory = os.open(self.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            current = os.fstat(self.directory)
            _require(_identity(current) == _identity(before)
                     and stat.S_ISDIR(current.st_mode) and current.st_uid == os.geteuid()
                     and not current.st_mode & 0o077, "EVIDENCE_PARENT_CUSTODY")
            _require(not has_macos_acl(self.parent, expected_identity=current, descriptor=self.directory),
                     "EVIDENCE_PARENT_ACL")
            self.parent_identity = (current.st_dev, current.st_ino, current.st_mode,
                                    current.st_uid, current.st_gid)
            flags = (os.O_RDWR | os.O_CREAT | os.O_EXCL) if create else os.O_RDONLY
            self.fd = os.open(self.path.name, flags | os.O_NOFOLLOW | os.O_NONBLOCK,
                              0o600, dir_fd=self.directory)
            self.check(mode=0o600 if create else 0o400)
        except BaseException:
            self.close()
            raise

    def check(self, *, mode=0o400):
        _require(self.parent.resolve(strict=True) == self.parent, "EVIDENCE_PARENT_ALIAS")
        parent = os.fstat(self.directory)
        path_parent = self.parent.lstat()
        for item in (parent, path_parent):
            _require((item.st_dev, item.st_ino, item.st_mode, item.st_uid, item.st_gid)
                     == self.parent_identity, "EVIDENCE_PARENT_CHANGED")
        info = os.fstat(self.fd)
        linked = os.stat(self.path.name, dir_fd=self.directory, follow_symlinks=False)
        _require(_identity(info) == _identity(linked) and stat.S_ISREG(info.st_mode)
                 and info.st_uid == os.geteuid() and info.st_nlink == 1
                 and stat.S_IMODE(info.st_mode) == mode, "EVIDENCE_FILE_CUSTODY")
        _require(not has_macos_acl(self.path, expected_identity=info, descriptor=self.fd),
                 "EVIDENCE_FILE_ACL")
        return info

    def write(self, raw):
        _require(len(raw) <= MAX_RECEIPT_BYTES, "RECEIPT_BOUND_EXCEEDED")
        self.check(mode=0o600)
        view = memoryview(raw)
        while view:
            written = os.write(self.fd, view)
            _require(written > 0, "RECEIPT_WRITE_INCOMPLETE")
            view = view[written:]
        os.fsync(self.fd)
        os.fchmod(self.fd, 0o400)
        os.fsync(self.fd)
        self.check()
        os.fsync(self.directory)

    def read(self):
        before = self.check()
        _require(before.st_size <= MAX_RECEIPT_BYTES, "RECEIPT_BOUND_EXCEEDED")
        raw = bytearray()
        while len(raw) <= MAX_RECEIPT_BYTES:
            block = os.read(self.fd, min(65536, MAX_RECEIPT_BYTES + 1 - len(raw)))
            if not block:
                break
            raw.extend(block)
        _require(len(raw) == before.st_size and _identity(self.check()) == _identity(before),
                 "RECEIPT_CHANGED_DURING_READ")
        return bytes(raw)

    def close(self):
        for name in ("fd", "directory"):
            value = getattr(self, name, None)
            if value is not None:
                os.close(value)
                setattr(self, name, None)


def _source_files(paths):
    return {str(Path(path).absolute()): _sha(Path(path).read_bytes()) for path in paths}


def capture_observation(
    path: Path, observe: Callable[..., int], *, runtime_root: Path | None,
    boot_packet_origin: str, source_files: tuple[Path, ...],
    installed_release_sha: str | None = None,
) -> tuple[int, str, str]:
    """Reserve once, invoke the existing observer once, retain its exact streams.

    A crash leaves an incomplete exclusive file; it is never silently overwritten
    or treated as a completed observation. No timestamps/provenance are accepted
    from the command line. The callback is the existing observe-only CLI owner.
    """
    evidence = _EvidenceFile(path, create=True)
    try:
        started = _utc_now()
        tick = time.monotonic_ns()
        installed = None
        if installed_release_sha is not None:
            from ops.executive_os.installed_capacity_observation import (
                InstalledSourceObservation, source_paths,
            )
            _require(runtime_root is None and not source_files
                     and boot_packet_origin in ("owner_collected", "not_collected"),
                     "INSTALLED_OBSERVATION_OVERRIDE_REFUSED")
            installed = InstalledSourceObservation(installed_release_sha)
            runtime_root = installed.runtime_root
            source_files = source_paths(installed_release_sha)
        before_sources = _source_files(source_files)
        before_observer = time.monotonic_ns()
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = observe(runtime_root) if installed is not None else observe()
        after_observer = time.monotonic_ns()
        _require(type(code) is int and code in (0, 2, 3), "UNEXPECTED_OBSERVER_EXIT")
        out, err = stdout.getvalue(), stderr.getvalue()
        after_sources = _source_files(source_files)
        binding = installed.finish() if installed is not None else None
        done = time.monotonic_ns()
        finished = _utc_now()
        receipt = {
            "schema": RECEIPT_SCHEMA, "writer_uid": os.geteuid(),
            "capture_started_at": started, "capture_finished_at": finished,
            "acquisition_monotonic_ns": done - tick,
            "execution_provenance": "UNATTESTED_SOURCE_OBSERVATION",
            "installed_coverage_claimed": False, "campaign_qualified": False,
            "runtime_root": str(runtime_root), "boot_packet_origin": boot_packet_origin,
            "source_files_before": before_sources, "source_files_after": after_sources,
            "source_binding_scope": "OBSERVED_FILE_BYTES_NOT_EXECUTING_RELEASE_ATTESTATION",
            "observer_return_code": code, "stdout": out, "stderr": err,
            "stdout_sha256": _sha(out.encode()), "stderr_sha256": _sha(err.encode()),
        }
        if binding is not None:
            from ops.executive_os.installed_capacity_observation import PROVENANCE, SOURCE_SCOPE
            receipt.update(
                schema=INSTALLED_RECEIPT_SCHEMA, execution_provenance=PROVENANCE,
                source_binding_scope=SOURCE_SCOPE, installed_source_binding=binding,
                acquisition_phases_monotonic_ns={
                    "installed_preflight": before_observer - tick,
                    "observer": after_observer - before_observer,
                    "installed_recheck": done - after_observer,
                },
            )
            # A refused final join never becomes a source-only fallback receipt.
            _validate(receipt)
        evidence.write((json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + "\n").encode())
        return code, out, err
    finally:
        evidence.close()


def _validate(receipt):
    _require(isinstance(receipt, dict) and receipt.get("schema") in (RECEIPT_SCHEMA, INSTALLED_RECEIPT_SCHEMA),
             "INVALID_RECEIPT_SCHEMA")
    installed = receipt["schema"] == INSTALLED_RECEIPT_SCHEMA
    fields = {"schema", "writer_uid", "capture_started_at", "capture_finished_at",
             "acquisition_monotonic_ns", "execution_provenance", "installed_coverage_claimed",
             "campaign_qualified", "runtime_root", "boot_packet_origin", "source_files_before",
             "source_files_after", "source_binding_scope", "observer_return_code", "stdout",
             "stderr", "stdout_sha256", "stderr_sha256"}
    if installed:
        fields.update({"installed_source_binding", "acquisition_phases_monotonic_ns"})
    _require(set(receipt) == fields, "INVALID_RECEIPT_FIELDS")
    _require(receipt.get("writer_uid") == os.geteuid()
             and type(receipt.get("writer_uid")) is int, "WRITER_CUSTODY_MISMATCH")
    provenance = "UNATTESTED_SOURCE_OBSERVATION"
    scope = "OBSERVED_FILE_BYTES_NOT_EXECUTING_RELEASE_ATTESTATION"
    if installed:
        from ops.executive_os.installed_capacity_observation import (
            PROVENANCE, SOURCE_FILES, SOURCE_SCOPE, source_paths, validate_binding,
        )
        provenance, scope = PROVENANCE, SOURCE_SCOPE
        _require(receipt["writer_uid"] == 0, "INSTALLED_OBSERVATION_ROOT_WRITER_REQUIRED")
        binding = validate_binding(receipt["installed_source_binding"])
        _require(receipt["runtime_root"] == binding["resolved_runtime_root"]
                 and receipt["boot_packet_origin"] in ("owner_collected", "not_collected"),
                 "INSTALLED_OBSERVATION_INPUT_MISMATCH")
        # JSON object order is not authority; join each fixed relative path.
        expected_sources = {str(path): binding["qualified_source_files"][relative]
                            for path, relative in zip(source_paths(binding["release_sha"]), SOURCE_FILES, strict=True)}
        _require(receipt["source_files_before"] == expected_sources,
                 "INSTALLED_OBSERVATION_SOURCE_MISMATCH")
        phases = receipt["acquisition_phases_monotonic_ns"]
        _require(type(phases) is dict and set(phases) == {
            "installed_preflight", "observer", "installed_recheck"}
            and all(type(value) is int and value >= 0 for value in phases.values())
            and sum(phases.values()) == receipt["acquisition_monotonic_ns"],
            "INVALID_INSTALLED_ACQUISITION_TIMING")
    _require(receipt.get("execution_provenance") == provenance
             and receipt.get("source_binding_scope") == scope
             and receipt.get("installed_coverage_claimed") is False
             and receipt.get("campaign_qualified") is False, "UNSUPPORTED_PROVENANCE_CLAIM")
    start, end = _stamp(receipt.get("capture_started_at")), _stamp(receipt.get("capture_finished_at"))
    _require(end >= start and type(receipt.get("acquisition_monotonic_ns")) is int
             and receipt["acquisition_monotonic_ns"] >= 0, "OBSERVATION_CLOCK_REGRESSED")
    for key in ("stdout", "stderr"):
        _require(isinstance(receipt.get(key), str)
                 and _sha(receipt[key].encode()) == receipt.get(key + "_sha256"), "STREAM_DIGEST_MISMATCH")
    sources = receipt.get("source_files_before")
    _require(isinstance(sources, dict) and sources and all(
        isinstance(k, str) and Path(k).is_absolute() and isinstance(v, str)
        and re.fullmatch(r"[0-9a-f]{64}", v) for k, v in sources.items()), "INVALID_SOURCE_OBSERVATION")
    _require(sources == receipt.get("source_files_after"), "SOURCE_BYTES_CHANGED_DURING_OBSERVATION")
    _require(isinstance(receipt.get("runtime_root"), str) and Path(receipt["runtime_root"]).is_absolute()
             and receipt.get("boot_packet_origin") in ("owner_collected", "saved_file", "not_collected"),
             "INVALID_OBSERVATION_INPUT_IDENTITY")
    code = receipt.get("observer_return_code")
    _require(type(code) is int and code in (0, 2, 3), "INVALID_OBSERVER_EXIT")
    report = _json(receipt["stdout"]) if receipt["stdout"].strip() else None
    if report is not None:
        _require(isinstance(report, dict) and report.get("mode") == "observe_only"
                 and report.get("writes_applied") is False
                 and report.get("requested") == report.get("resolved") == [], "NOT_READ_ONLY_OBSERVATION")
        point = report.get("capacity_observation")
        _require(isinstance(point, dict) and point.get("schema") == "mastermind.capacity_campaign_observation.v1"
                 and point.get("campaign_qualified") is False
                 and point.get("point_status") in ("OBSERVED", "PARTIAL", "CONTRADICTORY"),
                 "INVALID_POINT_OBSERVATION")
        if code == 0:
            _require(point["point_status"] == "OBSERVED"
                     and not any(report.get(name) for name in (
                         "degraded", "contradictions", "unsupported_attention"))
                     and not point.get("degraded") and not point.get("contradictions")
                     and all(report.get(name) == SourceReadHealth.HEALTHY.value for name in (
                         "runtime_health", "inbox_runtime_health", "agentos_health")),
                     "OBSERVER_SUCCESS_OUTCOME_MISMATCH")
    else:
        _require(code != 0, "SUCCESS_WITHOUT_OBSERVATION")
    return start, end, report


def summarize_observations(paths: list[Path]) -> dict:
    """Deterministic close/report of exactly the supplied immutable receipt set.

    No Runtime is opened and no clock is read. Missing files, duplicate bytes,
    invalid custody and mixed source/runtime inputs remain explicit. Wall-clock
    span/gaps are descriptive only; two points a week apart prove no coverage.
    """
    _require(0 < len(paths) <= MAX_RECEIPTS, "COLLECTION_INPUT_BOUND")
    inputs, points, failures, seen = [], [], [], set()
    total = 0
    for path in sorted(map(lambda p: Path(os.path.abspath(p)), paths), key=str):
        row = {"path": str(path), "sha256": None, "bytes": None}
        if total > MAX_COLLECTION_BYTES:
            row.update(state="UNAVAILABLE", reason="NOT_READ_COLLECTION_BYTES_BOUND")
            inputs.append(row)
            failures.append({"path": str(path), "reason": row["reason"]})
            continue
        try:
            evidence = _EvidenceFile(path, create=False)
            try:
                raw = evidence.read()
            finally:
                evidence.close()
            row.update(sha256=_sha(raw), bytes=len(raw))
            total += len(raw)
            _require(total <= MAX_COLLECTION_BYTES, "COLLECTION_BYTES_BOUND")
            _require(row["sha256"] not in seen, "DUPLICATE_OBSERVATION_BYTES")
            seen.add(row["sha256"])
            receipt = _json(raw)
            start, end, report = _validate(receipt)
            points.append((start, end, row["sha256"], receipt, report))
            row["state"] = "RETAINED"
        except (OSError, ValueError, FilesystemSecurityError) as exc:
            reason = str(exc) if isinstance(exc, ObservationEvidenceError) else type(exc).__name__
            row.update(state="UNAVAILABLE", reason=reason)
            failures.append({"path": str(path), "reason": reason})
        inputs.append(row)
    points.sort(key=lambda item: (item[0], item[1], item[2]))
    identities = {json.dumps([p[3]["runtime_root"], p[3]["source_files_before"], p[3]["boot_packet_origin"],
                             p[3]["execution_provenance"], p[3].get("installed_source_binding")],
                            sort_keys=True) for p in points}
    if len(identities) > 1:
        failures.append({"path": None, "reason": "MIXED_RUNTIME_SOURCE_OR_BOOT_INPUTS"})
    gaps = [{"previous_sha256": a[2], "next_sha256": b[2],
             "recorded_gap_seconds": (b[0] - a[1]).total_seconds()}
            for a, b in zip(points, points[1:])]
    details = []
    for start, end, digest, receipt, report in points:
        point = report["capacity_observation"] if report else None
        details.append({"sha256": digest, "capture_started_at": receipt["capture_started_at"],
                        "capture_finished_at": receipt["capture_finished_at"],
                        "observer_return_code": receipt["observer_return_code"],
                        "acquisition_monotonic_ns": receipt["acquisition_monotonic_ns"],
                        "acquisition_phases_monotonic_ns": receipt.get("acquisition_phases_monotonic_ns"),
                        "execution_provenance": receipt["execution_provenance"],
                        "installed_source_binding": receipt.get("installed_source_binding"),
                        "point_status": point["point_status"] if point else "UNAVAILABLE",
                        "unavailable_metrics": point.get("unavailable_metrics") if point else None,
                        "source_coverage": point.get("source_coverage") if point else None,
                        "runtime_workload": point.get("runtime_workload") if point else None,
                        "current_attention_by_kind": point.get("current_attention_by_kind") if point else None,
                        "interval_summaries": point.get("interval_summaries") if point else None})
    installed_points = [p for p in points if p[3]["schema"] == INSTALLED_RECEIPT_SCHEMA]
    source_set_qualified = bool(installed_points) and len(installed_points) == len(points) and not failures
    unproven = {name: {"state": "UNAVAILABLE", "value": None,
                      "reason": "NO_QUALIFIED_PRODUCER_JOIN_IN_THIS_COLLECTION"}
                for name in _UNPROVEN}
    if source_set_qualified:
        unproven["installed_source_and_runtime_attestation"] = {
            "state": "PARTIAL", "value": None,
            "reason": "INSTALLED_SOURCE_AND_CONFIG_CUSTODY_JOINED; LIVE_SERVICE_PEER_AND_RUNTIME_NAMESPACE_UNPROVEN",
        }
    return {
        "schema": REPORT_SCHEMA, "mode": "closed_explicit_input_set_report",
        "scope": "SUPPLIED_RECEIPTS_NOT_COMPLETE_CAMPAIGN_CENSUS",
        "writes_applied": False, "campaign_qualified": False, "installed_coverage_claimed": False,
        "state": "INPUTS_INCOMPLETE" if failures else "UNQUALIFIED_OBSERVATIONS_REPORTED",
        "inputs": inputs, "input_count_requested": len(paths), "failures": failures,
        "observations": details, "observation_count": len(points),
        "installed_source_bound_observation_count": len(installed_points),
        "healthy_installed_source_bound_observation_count": sum(p[3]["observer_return_code"] == 0 for p in installed_points),
        "installed_source_and_config_custody_qualified": source_set_qualified,
        "installed_service_peer_attested": False, "runtime_namespace_continuity_attested": False,
        "observer_failure_count": sum(p[3]["observer_return_code"] != 0 for p in points),
        "recorded_wall_clock_span_seconds": (max(p[1] for p in points) - points[0][0]).total_seconds() if points else None,
        "recorded_gaps": gaps,
        "max_recorded_gap_seconds": max((g["recorded_gap_seconds"] for g in gaps), default=None),
        "clock_scope": "HOST_UTC_LABELS; PHYSICAL_ELAPSED_ACCURACY_AND_CONTINUOUS_COVERAGE_UNPROVEN",
        "unproven_requirements": unproven,
    }
