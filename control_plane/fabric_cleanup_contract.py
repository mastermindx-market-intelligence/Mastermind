"""Pure, separate contract for retained same-run Fabric group cleanup evidence.

The caller must retrieve ``receipt`` and the exact lane JSONL record bytes from
the authenticated original Fabric owner. Expected lineage/physical binding and
process identity must come from the immutable same-run launch, never from this
receipt. This validator establishes internal binding and completeness; hashes
do not authenticate a producer or prove that a process census actually happened.

Installed lane_runtime v1 supplies the process record/cleanup fields below, but
does not itself record host boot or OS process-start identity. Without actual
retained owner evidence of those fields there is no passing integration path.
There is deliberately no receipt builder, filesystem read, process inspection,
UID sweep, signal, lease change, retry, or effect owner here.

Passing proves only one launch's process group/session cleanup and capture.
It never satisfies Supervisor's dedicated-user isolation/sweep contract.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
from typing import Any


FABRIC_CLEANUP_SCHEMA_VERSION = "mastermind.fabric_process_group_cleanup/v1"
LANE_PROCESS_RECEIPT_SCHEMA = "mastermind.local_owned_process_receipt.v1"
MAX_LANE_RECEIPT_BYTES = 64 * 1024
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_BINDING_FIELDS = frozenset({"root_id", "job_id", "attempt_id",
                             "effective_grant_digest", "commission_sha256"})
_IDENTITY_FIELDS = frozenset({"host_ref", "boot_session_id", "pid", "pgid",
                              "session_id", "process_start_identity"})
_RECEIPT_FIELDS = frozenset({"schema_version", "binding", "physical_binding_sha256",
    "process_identity", "lane_started_at", "lane_receipt_sha256",
    "lane_receipt_bytes_sha256", "capture_complete", "cleanup_verified", "uncertainty"})
_LANE_FIELDS = frozenset({"schema", "label", "pid", "pgid", "started_at", "ended_at",
    "returncode", "timed_out", "nice_requested", "nice_applied", "stdout_bytes",
    "stderr_bytes", "stdout_truncated", "stderr_truncated", "runtime_failure_code", "cleanup"})
_LANE_CAPTURE_EXTENSIONS = frozenset({"stdout_sha256", "launch_capture", "owned_capture"})
_FILE_CAPTURE_FIELDS = frozenset({"stdout_file_capture_complete",
    "stderr_file_capture_complete", "result_file_capture_complete"})
_CLEANUP_FIELDS = frozenset({"status", "reason", "sigterm_sent", "sigkill_sent",
    "identity_verified", "census_proven", "residual_count", "error_code",
    "stdout_capture_complete", "stderr_capture_complete", "stdin_delivery_complete",
    "stdout_capture_error", "stderr_capture_error", "stdin_delivery_error"})
_SESSION_FIELDS = frozenset({"session_id", "sigterm_member_count", "sigkill_member_count"})


class FabricCleanupContractError(ValueError):
    """Closed refusal codes; never echo source data or diagnostics."""


@dataclass(frozen=True)
class FabricCleanupEvidence:
    root_id: str
    job_id: str
    attempt_id: str
    effective_grant_digest: str
    commission_sha256: str
    physical_binding_sha256: str
    host_ref: str
    boot_session_id: str
    pid: int
    pgid: int
    session_id: int
    process_start_identity: str
    lane_receipt_sha256: str
    lane_receipt_bytes_sha256: str
    receipt_sha256: str

    @property
    def capability(self) -> str:
        return "same_run_process_group_cleanup"

    @property
    def dedicated_user_isolation(self) -> bool:
        return False


def _refuse(code: str) -> None:
    raise FabricCleanupContractError(code)


def _object(value: Any, fields: frozenset[str], code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        _refuse(code)
    return value


def _text(value: Any, code: str) -> None:
    if (type(value) is not str or not value or len(value) > 512
            or value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        _refuse(code)


def _digest(value: Any) -> None:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        _refuse("invalid_digest")


def _binding(value: Any) -> Mapping[str, Any]:
    result = _object(value, _BINDING_FIELDS, "incomplete_lineage")
    for key in ("root_id", "job_id", "attempt_id"):
        if type(result[key]) is not str or _ID.fullmatch(result[key]) is None:
            _refuse("invalid_lineage")
    for key in ("effective_grant_digest", "commission_sha256"):
        _digest(result[key])
    return result


def _identity(value: Any) -> Mapping[str, Any]:
    result = _object(value, _IDENTITY_FIELDS, "incomplete_process_identity")
    for key in ("host_ref", "boot_session_id", "process_start_identity"):
        _text(result[key], "invalid_process_identity")
    for key in ("pid", "pgid", "session_id"):
        if type(result[key]) is not int or not 0 < result[key] < 2**63:
            _refuse("invalid_process_identity")
    # lane_runtime launches with start_new_session=True, and owns exactly this
    # leader's group/session. An arbitrary inherited group is not this contract.
    if result["pid"] != result["pgid"] or result["pid"] != result["session_id"]:
        _refuse("foreign_process_group")
    return result


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _refuse("invalid_json_record")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _timestamp(value: Any) -> datetime:
    _text(value, "invalid_lane_timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        _refuse("invalid_lane_timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _refuse("invalid_lane_timestamp")
    return parsed


def _lane_record(raw: Any) -> Mapping[str, Any]:
    if (type(raw) is not bytes or not 0 < len(raw) <= MAX_LANE_RECEIPT_BYTES
            or not raw.endswith(b"\n") or raw.count(b"\n") != 1):
        _refuse("incomplete_lane_bytes")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _refuse("duplicate_lane_field")
            result[key] = value
        return result

    def constant(_value):
        _refuse("invalid_json_record")

    try:
        result = json.loads(raw.decode("utf-8", errors="strict"),
                            object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, FabricCleanupContractError):
            raise
        _refuse("invalid_json_record")
    _canonical(result)  # Also rejects overflowed JSON numbers.
    if (not isinstance(result, Mapping) or not _LANE_FIELDS <= set(result)
            or set(result) - _LANE_FIELDS - _LANE_CAPTURE_EXTENSIONS):
        _refuse("incomplete_lane_record")
    return result


def _capture_extensions(lane: Mapping[str, Any]) -> None:
    """Qualify the original owner's additive capture fields without rewriting bytes.

    These remain group/capture observations, never post-exec launch authority,
    filesystem access authority, result acceptance or a dedicated UID sweep.
    Legacy records without the opt-in file capture retain their exact contract.
    """
    if "stdout_sha256" in lane:
        _digest(lane["stdout_sha256"])
    if "launch_capture" in lane:
        early = _object(lane["launch_capture"], frozenset({"phase", "receipt_sha256",
            "context_sha256", "provider_execution_attested"}), "invalid_launch_capture")
        if (early["phase"] != "PRE_EXEC_HANDSHAKE"
                or early["provider_execution_attested"] is not False):
            _refuse("invalid_launch_capture")
        _digest(early["receipt_sha256"])
        if early["context_sha256"] is not None:
            _digest(early["context_sha256"])
    if "owned_capture" not in lane:
        return
    value = _object(lane["owned_capture"], frozenset({"schema", "run_dir", "limit_bytes",
        "result_schema_sha256", "assignment", "files", "stdout_file_complete",
        "stderr_file_complete", "stdout", "stderr", "result", "provider_observations",
        "file_descriptors_closed", "result_file_complete"}), "incomplete_file_capture")
    if (value["schema"] != "mastermind.local_owned_capture_files.v1"
            or any(value[key] is not True for key in ("stdout_file_complete",
                "stderr_file_complete", "file_descriptors_closed", "result_file_complete"))
            or type(value["limit_bytes"]) is not int or value["limit_bytes"] <= 0):
        _refuse("file_capture_unproven")
    _digest(value["result_schema_sha256"])
    _text(value["run_dir"], "invalid_capture_path")
    files = _object(value["files"], frozenset({"stdout", "stderr", "result"}),
                    "incomplete_capture_files")
    for name, original in files.items():
        _object(original, frozenset({"path", "device", "inode", "parent_device", "parent_inode"}),
                "incomplete_capture_file_identity")
        _text(original["path"], "invalid_capture_path")
        if any(type(original[k]) is not int or original[k] < 0
               for k in ("device", "inode", "parent_device", "parent_inode")):
            _refuse("invalid_capture_file_identity")
        record = value[name]
        if not isinstance(record, Mapping) or any(record.get(k) != original[k]
                for k in ("path", "device", "inode")):
            _refuse("foreign_capture_file")
    for name in ("stdout", "stderr"):
        record = _object(value[name], frozenset({"path", "device", "inode", "stream_bytes",
            "stream_sha256", "file_bytes", "file_sha256", "overcap", "complete",
            "error_code", "sealed"}), "incomplete_capture_stream")
        if (record["complete"] is not True or record["sealed"] is not True
                or record["overcap"] is not False or record["error_code"] is not None
                or type(record["file_bytes"]) is not int
                or type(record["stream_bytes"]) is not int
                or not 0 <= record["file_bytes"] == record["stream_bytes"]
                    == lane[name + "_bytes"] <= value["limit_bytes"]
                or record["file_sha256"] != record["stream_sha256"]):
            _refuse("capture_stream_unproven")
        _digest(record["file_sha256"])
    if value["stdout"]["stream_sha256"] != lane.get("stdout_sha256"):
        _refuse("capture_stream_digest_mismatch")
    result = _object(value["result"], frozenset({"path", "device", "inode", "state",
        "reason", "bytes", "sha256"}), "incomplete_capture_result")
    if result["state"] == "published":
        if type(result["bytes"]) is not int or result["bytes"] <= 0 or result["reason"] is not None:
            _refuse("capture_result_unproven")
        _digest(result["sha256"])
    elif (result["state"] != "not_published" or type(result["bytes"]) is not int
            or result["bytes"] != 0 or result["sha256"] is not None
            or type(result["reason"]) is not str or not result["reason"]):
        _refuse("capture_result_unproven")
    provider = value["provider_observations"]
    if provider is not None:
        _object(provider, frozenset({"session_id", "usage", "authority"}), "invalid_provider_observation")
        if provider["authority"] is not False:
            _refuse("provider_observation_is_not_authority")


def validate_fabric_cleanup_receipt(
    receipt: Mapping[str, Any], *, expected_binding: Mapping[str, Any],
    expected_physical_binding_sha256: str,
    expected_process_identity: Mapping[str, Any], lane_receipt_bytes: bytes,
) -> FabricCleanupEvidence:
    """Refuse unknown, partial, foreign, residual, or reused-process evidence.

    ``expected_process_identity`` uses existing WorkerProcessRef field names,
    plus the trusted physical ``host_ref``. Its boot/start generation is required
    even if the leader has already exited. Missing process bytes/identity never
    mean absence. No synthetic receipt or caller assertion substitutes for the
    actual original owner's source records. Nonzero exit/timeout can prove
    cleanup; this verdict does not prove successful execution or result validity.
    """
    value = _object(receipt, _RECEIPT_FIELDS, "incomplete_cleanup_receipt")
    if value["schema_version"] != FABRIC_CLEANUP_SCHEMA_VERSION:
        _refuse("unsupported_cleanup_schema")
    expected = _binding(expected_binding)
    binding = _binding(value["binding"])
    if binding != expected:
        _refuse("foreign_lineage")
    _digest(expected_physical_binding_sha256)
    _digest(value["physical_binding_sha256"])
    if value["physical_binding_sha256"] != expected_physical_binding_sha256:
        _refuse("foreign_physical_binding")
    identity = _identity(value["process_identity"])
    if identity != _identity(expected_process_identity):
        _refuse("foreign_process_generation")
    if (value["capture_complete"] is not True or value["cleanup_verified"] is not True
            or value["uncertainty"] is not None):
        _refuse("cleanup_unproven")
    for field in ("lane_receipt_sha256", "lane_receipt_bytes_sha256"):
        _digest(value[field])
    lane = _lane_record(lane_receipt_bytes)
    if (_sha(lane_receipt_bytes) != value["lane_receipt_bytes_sha256"]
            or _sha(_canonical(lane)) != value["lane_receipt_sha256"]):
        _refuse("lane_digest_mismatch")
    if lane["schema"] != LANE_PROCESS_RECEIPT_SCHEMA:
        _refuse("unsupported_lane_schema")
    _text(lane["label"], "invalid_lane_label")
    for field in ("pid", "pgid"):
        if type(lane[field]) is not int or lane[field] != identity[field]:
            _refuse("foreign_lane_process")
    if (lane["started_at"] != value["lane_started_at"]
            or _timestamp(lane["ended_at"]) < _timestamp(lane["started_at"])):
        _refuse("foreign_lane_generation")
    if type(lane["returncode"]) is not int or type(lane["timed_out"]) is not bool:
        _refuse("incomplete_lane_exit")
    requested_nice = lane["nice_requested"]
    if requested_nice is not None and (type(requested_nice) is not int or not -20 <= requested_nice <= 19):
        _refuse("invalid_lane_record")
    # Installed lane_runtime records whether setpriority succeeded, not the
    # applied priority value. False is valid cleanup evidence even when the
    # best-effort priority change could not be applied.
    if (type(lane["nice_applied"]) is not bool
            or (lane["nice_applied"] and requested_nice is None)):
        _refuse("invalid_lane_record")
    for field in ("stdout_bytes", "stderr_bytes"):
        if type(lane[field]) is not int or not 0 <= lane[field] < 2**63:
            _refuse("invalid_capture_count")
    if (lane["stdout_truncated"] is not False or lane["stderr_truncated"] is not False
            or lane["runtime_failure_code"] is not None):
        _refuse("capture_unproven")
    _capture_extensions(lane)
    cleanup = lane["cleanup"]
    capture_fields = _FILE_CAPTURE_FIELDS if "owned_capture" in lane else frozenset()
    if not isinstance(cleanup, Mapping) or set(cleanup) not in (
            _CLEANUP_FIELDS | capture_fields, _CLEANUP_FIELDS | _SESSION_FIELDS | capture_fields):
        _refuse("incomplete_lane_cleanup")
    if any(cleanup[field] is not True for field in capture_fields):
        _refuse("capture_unproven")
    if (type(cleanup["status"]) is not str or cleanup["status"] not in {"not_needed", "terminated"}
            or cleanup["identity_verified"] is not True or cleanup["census_proven"] is not True
            or type(cleanup["residual_count"]) is not int or cleanup["residual_count"] != 0
            or cleanup["error_code"] is not None):
        _refuse("lane_cleanup_unproven")
    _text(cleanup["reason"], "invalid_cleanup_reason")
    for field in ("sigterm_sent", "sigkill_sent"):
        if type(cleanup[field]) is not bool:
            _refuse("invalid_cleanup_signal")
    if cleanup["status"] == "terminated" and not _SESSION_FIELDS.issubset(cleanup):
        _refuse("incomplete_cleanup_session")
    if _SESSION_FIELDS.issubset(cleanup):
        if type(cleanup["session_id"]) is not int or cleanup["session_id"] != identity["session_id"]:
            _refuse("foreign_cleanup_session")
        for signal in ("sigterm", "sigkill"):
            count = cleanup[f"{signal}_member_count"]
            if (type(count) is not int or not 0 <= count < 2**63
                    or cleanup[f"{signal}_sent"] != (count > 0)):
                _refuse("invalid_cleanup_signal")
    for field in ("stdout_capture_complete", "stderr_capture_complete", "stdin_delivery_complete"):
        if cleanup[field] is not True:
            _refuse("capture_unproven")
    for field in ("stdout_capture_error", "stderr_capture_error", "stdin_delivery_error"):
        if cleanup[field] is not None:
            _refuse("capture_unproven")
    return FabricCleanupEvidence(
        **binding, physical_binding_sha256=value["physical_binding_sha256"], **identity,
        lane_receipt_sha256=value["lane_receipt_sha256"],
        lane_receipt_bytes_sha256=value["lane_receipt_bytes_sha256"],
        receipt_sha256=_sha(_canonical(dict(value))),
    )
