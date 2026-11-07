"""Pure-Python admission contract for controller-owned paid Fabric operator delegation.

Public API:
    DelegationRefused      ValueError subclass; str(exc) is exactly one closed reason code.
    REASON_CODES           frozenset of every reason code this module can emit.
    CHILD_RECORD_KEYS      exact key set of the normalized child record returned.
    validate_launch(...)   validate one child delegation; return the child record or refuse.

TRUST AND EFFECT NOTICE -- read before integrating:
    validate_launch only checks the shape and binding of records. It does NOT
    authenticate the transport. It does NOT issue a grant. It does NOT reserve
    any count atomically. It does NOT verify that a live process exists. It
    does NOT permit a remote caller to supply the trusted records.
    grant / lease / launch are trusted controller read-back dictionaries; only
    request is caller-supplied. The actual owner (the installed controller
    adapter and admission path) must read the real records from its
    authoritative store, re-check them, and atomically reserve the child count
    immediately before any paid effect. Nothing in this module is installed or
    admitted runtime behavior, and a successful return reserves nothing.
    The parent lease is never reused: every result carries needs_new_lease=True
    and claims no resources. Input dictionaries are never mutated.

Standard library only; no filesystem, network, environment, or subprocess use.
"""

import math
import re
from collections.abc import Mapping

__all__ = (
    "DelegationRefused",
    "REASON_CODES",
    "CHILD_RECORD_KEYS",
    "validate_launch",
)

GRANT_SCHEMA = "mastermind.fabric_operator_grant.v1"
REQUEST_SCHEMA = "mastermind.fabric_operator_child_request.v1"
OPERATOR_TASK_CLASS = "domain_orchestration"
LEASE_TASK_CLASS_PREFIX = "remote-"
LEASE_STATES = frozenset(("held", "rented"))
LEAF_TASK_CLASSES = frozenset(
    ("mechanical", "extract", "fix_build", "census", "audit", "build")
)
TASK_COMPLEXITIES = frozenset(("C0_MECHANICAL", "C1_ROUTINE_BOUNDED"))
ALLOWED_POOL_MODEL = frozenset((("glm", "glm-5.3"), ("glm-frontier", "glm-5.3"), ("grok", "grok-4.6")))
MAX_GRANT_SECONDS = 7200
MIN_CHILD_BUDGET = 1
MAX_CHILD_BUDGET = 64
MIN_PACKET_BYTES = 1
MAX_PACKET_BYTES = 65536

CHILD_RECORD_KEYS = frozenset(
    ("root", "parent", "child_run_id", "task_class", "task_complexity",
     "packet", "needs_new_lease")
)

_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_HASH64_RE = re.compile(r"\A[0-9a-f]{64}\Z")

REASON_CODES = frozenset((
    "now_invalid",
    "grant_not_mapping", "grant_missing_field", "grant_unknown_field",
    "grant_schema", "grant_id_invalid", "grant_hash_invalid",
    "grant_pool_model_pair", "grant_budget_domain", "grant_classes_invalid",
    "grant_clock_invalid", "grant_deadline_order", "grant_duration_limit",
    "grant_window_expired",
    "lease_not_mapping", "lease_missing_field", "lease_binding_mismatch",
    "lease_task_class_mode", "lease_state_invalid", "lease_pid_invalid",
    "lease_ttl_invalid", "lease_clock_invalid", "lease_sequence_invalid",
    "lease_ttl_expired", "lease_renewable_invalid", "lease_hard_ttl_expired",
    "launch_not_mapping", "launch_missing_field", "launch_unknown_field",
    "launch_binding_mismatch", "launch_task_class_invalid",
    "request_not_mapping", "request_missing_field", "request_unknown_field",
    "request_schema", "request_root_mismatch", "request_parent_mismatch",
    "request_run_id_invalid", "request_run_id_not_distinct",
    "request_task_class_not_leaf", "request_task_class_not_granted",
    "request_complexity_invalid", "request_packet_type",
    "request_packet_encoding", "request_packet_nul", "request_packet_size",
    "used_children_invalid", "root_children_remaining_invalid",
    "grant_budget_exhausted", "root_budget_exhausted",
    "internal_reason",
))


class DelegationRefused(ValueError):
    """Admission failed. The message is exactly one code from REASON_CODES."""


def _refuse(code):
    if code not in REASON_CODES:
        code = "internal_reason"
    raise DelegationRefused(code)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_finite_real(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _is_id(value):
    return isinstance(value, str) and _ID_RE.match(value) is not None


def _is_hash64(value):
    return isinstance(value, str) and _HASH64_RE.match(value) is not None


def _as_record(raw, code):
    if not isinstance(raw, Mapping):
        _refuse(code)
    return dict(raw)


def _require_exact_keys(record, fields, missing_code, unknown_code):
    keys = set(record)
    required = set(fields)
    if required - keys:
        _refuse(missing_code)
    if keys - required:
        _refuse(unknown_code)


def _is_valid_class_list(classes):
    if not isinstance(classes, (list, tuple)) or not classes:
        return False
    if any(not isinstance(item, str) for item in classes):
        return False
    if len(set(classes)) != len(classes):
        return False
    return set(classes) <= LEAF_TASK_CLASSES


_GRANT_FIELDS = (
    "schema", "root", "operator_run", "lease_id", "pool", "model", "account",
    "host", "support_sha256", "packet_sha256", "issued_at", "expires_at",
    "child_budget", "allowed_classes",
)
_GRANT_ID_FIELDS = ("root", "operator_run", "lease_id", "account", "host")
_GRANT_HASH_FIELDS = ("support_sha256", "packet_sha256")


def _validate_grant(raw, now):
    grant = _as_record(raw, "grant_not_mapping")
    _require_exact_keys(grant, _GRANT_FIELDS, "grant_missing_field",
                        "grant_unknown_field")
    if grant["schema"] != GRANT_SCHEMA:
        _refuse("grant_schema")
    for field in _GRANT_ID_FIELDS:
        if not _is_id(grant[field]):
            _refuse("grant_id_invalid")
    if not isinstance(grant["pool"], str) or not isinstance(grant["model"], str):
        _refuse("grant_pool_model_pair")
    if (grant["pool"], grant["model"]) not in ALLOWED_POOL_MODEL:
        _refuse("grant_pool_model_pair")
    for field in _GRANT_HASH_FIELDS:
        if not _is_hash64(grant[field]):
            _refuse("grant_hash_invalid")
    budget = grant["child_budget"]
    if not _is_int(budget) or not (MIN_CHILD_BUDGET <= budget <= MAX_CHILD_BUDGET):
        _refuse("grant_budget_domain")
    if not _is_valid_class_list(grant["allowed_classes"]):
        _refuse("grant_classes_invalid")
    issued_at = grant["issued_at"]
    expires_at = grant["expires_at"]
    if not _is_finite_real(issued_at) or not _is_finite_real(expires_at):
        _refuse("grant_clock_invalid")
    if not (issued_at > 0) or not (expires_at > 0):
        _refuse("grant_clock_invalid")
    if not issued_at < expires_at:
        _refuse("grant_deadline_order")
    if expires_at - issued_at > MAX_GRANT_SECONDS:
        _refuse("grant_duration_limit")
    if not (issued_at <= now < expires_at):
        _refuse("grant_window_expired")
    return grant


_LEASE_FIELDS = (
    "id", "orchestrator_id", "pool", "account", "task_class", "model", "host",
    "pid", "granted_at", "ttl", "last_heartbeat", "state", "renewable",
)
_LEASE_BINDING_FIELDS = ("pool", "model", "account", "host")


def _validate_lease(raw, grant, now):
    # Lease mirrors the real broker record; extra canonical broker fields are
    # tolerated and ignored. Only the required subset is checked and bound.
    # This validates numbers only; it never asserts process existence.
    lease = _as_record(raw, "lease_not_mapping")
    if not set(_LEASE_FIELDS) <= set(lease):
        _refuse("lease_missing_field")
    if lease["id"] != grant["lease_id"] or lease["orchestrator_id"] != grant["root"]:
        _refuse("lease_binding_mismatch")
    for field in _LEASE_BINDING_FIELDS:
        if lease[field] != grant[field]:
            _refuse("lease_binding_mismatch")
    task_class = lease["task_class"]
    if not isinstance(task_class, str) or task_class != (
        LEASE_TASK_CLASS_PREFIX + ("glm" if grant["pool"] == "glm-frontier" else grant["pool"])
    ):
        _refuse("lease_task_class_mode")
    state = lease["state"]
    if not isinstance(state, str) or state not in LEASE_STATES:
        _refuse("lease_state_invalid")
    if not _is_int(lease["pid"]) or lease["pid"] <= 0:
        _refuse("lease_pid_invalid")
    if not _is_int(lease["ttl"]) or lease["ttl"] <= 0:
        _refuse("lease_ttl_invalid")
    granted_at = lease["granted_at"]
    heartbeat = lease["last_heartbeat"]
    if not _is_finite_real(granted_at) or not _is_finite_real(heartbeat):
        _refuse("lease_clock_invalid")
    if not (granted_at <= heartbeat <= now):
        _refuse("lease_sequence_invalid")
    if not (now < heartbeat + lease["ttl"]):
        _refuse("lease_ttl_expired")
    renewable = lease["renewable"]
    if not _is_int(renewable) or renewable not in (0, 1):
        _refuse("lease_renewable_invalid")
    if renewable == 0 and not (now < granted_at + lease["ttl"]):
        _refuse("lease_hard_ttl_expired")
    return lease


_LAUNCH_FIELDS = (
    "root", "run_id", "lease_id", "pool", "model", "account", "host",
    "support_sha256", "packet_sha256", "task_class",
)


def _validate_launch(raw, grant):
    # Controller-retained launch metadata; not remote-supplied environment.
    launch = _as_record(raw, "launch_not_mapping")
    _require_exact_keys(launch, _LAUNCH_FIELDS, "launch_missing_field",
                        "launch_unknown_field")
    expected = (
        ("root", grant["root"]),
        ("run_id", grant["operator_run"]),
        ("lease_id", grant["lease_id"]),
        ("pool", grant["pool"]),
        ("model", grant["model"]),
        ("account", grant["account"]),
        ("host", grant["host"]),
        ("support_sha256", grant["support_sha256"]),
        ("packet_sha256", grant["packet_sha256"]),
    )
    for field, want in expected:
        if launch[field] != want:
            _refuse("launch_binding_mismatch")
    if not isinstance(launch["task_class"], str) or (
        launch["task_class"] != OPERATOR_TASK_CLASS
    ):
        _refuse("launch_task_class_invalid")
    return launch


_REQUEST_FIELDS = (
    "schema", "root", "parent", "run_id", "task_class", "task_complexity",
    "packet",
)


def _normalize_packet(packet):
    if isinstance(packet, str):
        try:
            encoded = packet.encode("utf-8")
        except UnicodeEncodeError:
            _refuse("request_packet_encoding")
        text = packet
    elif isinstance(packet, bytes):
        try:
            text = packet.decode("utf-8")
        except UnicodeDecodeError:
            _refuse("request_packet_encoding")
        encoded = packet
    else:
        _refuse("request_packet_type")
    if "\x00" in text:
        _refuse("request_packet_nul")
    if not (MIN_PACKET_BYTES <= len(encoded) <= MAX_PACKET_BYTES):
        _refuse("request_packet_size")
    return text


def _validate_request(raw, grant):
    request = _as_record(raw, "request_not_mapping")
    _require_exact_keys(request, _REQUEST_FIELDS, "request_missing_field",
                        "request_unknown_field")
    if request["schema"] != REQUEST_SCHEMA:
        _refuse("request_schema")
    if request["root"] != grant["root"]:
        _refuse("request_root_mismatch")
    if request["parent"] != grant["operator_run"]:
        _refuse("request_parent_mismatch")
    run_id = request["run_id"]
    if not _is_id(run_id):
        _refuse("request_run_id_invalid")
    if run_id == grant["root"] or run_id == grant["operator_run"]:
        _refuse("request_run_id_not_distinct")
    task_class = request["task_class"]
    if not isinstance(task_class, str) or task_class not in LEAF_TASK_CLASSES:
        _refuse("request_task_class_not_leaf")
    if task_class not in set(grant["allowed_classes"]):
        _refuse("request_task_class_not_granted")
    complexity = request["task_complexity"]
    if not isinstance(complexity, str) or complexity not in TASK_COMPLEXITIES:
        _refuse("request_complexity_invalid")
    packet = _normalize_packet(request["packet"])
    return {
        "run_id": run_id,
        "task_class": task_class,
        "task_complexity": complexity,
        "packet": packet,
    }


def _validate_counts(used_children, root_children_remaining, child_budget):
    if not _is_int(used_children) or used_children < 0:
        _refuse("used_children_invalid")
    if not _is_int(root_children_remaining) or root_children_remaining < 0:
        _refuse("root_children_remaining_invalid")
    if used_children >= child_budget:
        _refuse("grant_budget_exhausted")
    if root_children_remaining <= 0:
        _refuse("root_budget_exhausted")


def validate_launch(grant, lease, launch, request, *, now, used_children,
                    root_children_remaining):
    """Admit one Fabric operator child delegation or refuse with a closed code.

    grant, lease, launch are trusted controller read-back dicts; request is
    the only caller-supplied dict. now is the controller clock, used_children
    counts children already consumed by this grant, and root_children_remaining
    is the root-level remaining allowance. See the module notice: nothing here
    authenticates transport, issues grants, reserves counts, verifies live
    processes, or admits remote-supplied trusted records. The owner must read
    real records and atomically recheck/reserve before effect. Inputs are not
    mutated; the parent lease is never reused (needs_new_lease=True).
    """
    if not _is_finite_real(now):
        _refuse("now_invalid")
    checked_grant = _validate_grant(grant, now)
    _validate_lease(lease, checked_grant, now)
    _validate_launch(launch, checked_grant)
    child = _validate_request(request, checked_grant)
    _validate_counts(used_children, root_children_remaining,
                     checked_grant["child_budget"])
    return {
        "root": checked_grant["root"],
        "parent": checked_grant["operator_run"],
        "child_run_id": child["run_id"],
        "task_class": child["task_class"],
        "task_complexity": child["task_complexity"],
        "packet": child["packet"],
        "needs_new_lease": True,
    }
