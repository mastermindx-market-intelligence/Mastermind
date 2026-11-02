"""Read-only historical proof for the retained rc75 thermal-refusal admission rejection.

This is a fixed-case diagnostic, not a reconciliation or lifecycle owner. It
never writes receipts, changes status, retries, accepts a review, admits new
work, or touches the thermal limit, route, admission or accounting policy.

The evidence model is the incumbent same-OS-principal native owner model. It is
not a remote cryptographic attestation and it does not prove the absence of all
telemetry transport. The historical selected generation is never claimed from
current selection timestamps.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import urllib.parse

from native_plain_packet_check import (
    EvidenceReadSet,
    Unqualified,
    digest,
    identity,
    strict_json,
)
from native_runtime_bindings import owner_path

HERE = Path(__file__).resolve().parent
RUN = "terminal-news-sidebar-20261102-c4-current-build-001"
ROOT = "terminal-news-sidebar-20261018-c4"
TASK_CLASS = "fix_build"
HOST = "ubuntu1"
MODE = "minimax"
POOL = "minimax"
ACCOUNT = "default"
TASK_CLASS_BROKER = "remote-minimax"
SCHEMA = "mastermind.fabric_thermal_refusal_historical_check.v1"
RECONCILIATION_SUFFIX = ".thermal-refusal-reconciliation.json"
PREDICATE = "QUALIFIED_THERMAL_ADMISSION_REFUSAL_WITHOUT_PROVIDER_EXECUTION"

ROUTE = {
    "HOST": HOST, "MODE": MODE, "MODEL": "MiniMax-M3", "POOL": POOL,
    "KEY": "-", "REASON": "minimax_first", "ESCALATE_TO": "glm-flash",
}
ROUTE_FIELDS = frozenset(ROUTE)

# The original launch binds the controller, the broker and the quota circuit.
LAUNCH_SOURCES = {
    "remote_sub.sh": "eb7ae5e3288a9f3a49eb5eab14a5481501cced21f72b646f9891fc5b83981bc0",
    "lease_broker.py": "a2847a29abe590cb168c2cd8ae34e0b1c3222b6e92ab4c00f252a342d56e6406",
    "quota_circuit.py": "0962d638a0a5655a71ea7a6eeb83088ad60af30f4a26e9c5bc47a92c3ab77945",
}
# The published support bundle binds the remote executor and its lane runtime.
SUPPORT_SOURCES = {
    "remote_sub_exec.py": "5880bad86fc4bc65a8460baf6156b46333a0ce33c24ef6742c905aa7db55ce2d",
    "lane_runtime.py": "61350902dcf90ac65800f81e20acf473092c45738bbbef9b582548777e4e0329",
}
SUPPORT_DIGEST = "87be08914d96c2574749239d63606f3dddeb83ba70a5e06554598e68d4400b23"
POLICY_SHA256 = "db4e4b1768809bd991003ef045568b480cdb42ea0715a6b73ea5353930bf90d8"

# Frozen owner state, all under state/remote_sub/<RUN>.<suffix>, mode 0600.
ARTIFACTS = {
    "request.json": "87991855a5fea09fc09f269c19a64de4f110b705967f36fcd179eef7e8da4517",
    "request-launch.json": "b7dfa2706fb5e17ae70be6e8c4f66db1b5a97af2af2d2a37c00be713c0b76020",
    "request-return.json": "46a7ee9f2c0bab424d417cfbe6d6beeeb532bce8fde55161e763f5100f479c56",
    "continuation-request.json": "5f45311a1e77c5e9dff75ee8574687ff4688d1c880efbec11d1a2e0f201762a4",
    "continuation-finished.json": "3f4e1e94632f5b8183eb6403948aabe015f11a0453f15dbc64af72dfd302e776",
    "log": "d9231139ba35bcf9be37196123ca000f8835ffbff3fc99e27cfd01b2b943501b",
    "support.json": "6a145d8c851a0875060728427688962a95042b010c3f1d58dff7a5f87333594e",
    "request.packet": "11dd579a44ae976a244e146bce9543b8fdec87e71484e672f6f13e28844feb11",
    "routing-process.jsonl": "b7e87043460ebe0a95fbfb576ad9895146130d586bf5582d517fa7024ab073d9",
    "controller-process.jsonl": "468eac3075e430eab24a9ca7d1e71eac40f1c6358fbf38eef56f58a511be887a",
}
PACKET_BYTES = 5903

# The retained owner result: one refused admission line, never a worker result.
RESULT_NAME = RUN + ".remote.stdout"
RESULT_SHA256 = "9226eff028a331231dfb4b1b0724ae44285f89240e338de98c6107b2ae6ece4d"
RESULT_BYTES = 241
RESULT_LINE = (
    'REMOTE_SUB_ADMISSION_REFUSED {"active_count":0,"allowed":false,"cpu_count":24,'
    '"json_locked_count":0,"legacy_count":0,"load1":3.733,"load_ratio_limit":0.4167,'
    '"max_active":18,"reasons":["host_temperature_at_or_above_limit"],'
    '"stale_reaped":[]}'
)

# The compatible immutable closure that still carries the frozen source bytes.
COMPATIBLE_GENERATION = "28faaf101463bcabef578ab1acabdcd270e301c7ed9cedf294e82fd459ccfcce"
COMPATIBLE_RELEASE_SHA256 = "0954bd8d5516b78b2a2c0a1354034c985e1637a89f2cdc6e448a391fc874c1f8"
COMPATIBLE_GENERATION_FILES = 102
NATIVE_SOURCES = {
    "remote_sub.sh": "eb7ae5e3288a9f3a49eb5eab14a5481501cced21f72b646f9891fc5b83981bc0",
    "remote_sub_exec.py": "5880bad86fc4bc65a8460baf6156b46333a0ce33c24ef6742c905aa7db55ce2d",
    "lane_runtime.py": "61350902dcf90ac65800f81e20acf473092c45738bbbef9b582548777e4e0329",
    "lease_broker.py": "a2847a29abe590cb168c2cd8ae34e0b1c3222b6e92ab4c00f252a342d56e6406",
    "quota_circuit.py": "0962d638a0a5655a71ea7a6eeb83088ad60af30f4a26e9c5bc47a92c3ab77945",
    "fabric_task.py": "48699864fdc9e96d12f51ff22fef74bd438a2fcd500f25c836e6fab2dea728d7",
    "fabric_continuation.py": "1a3511825ec58a323100cb60c53d483f8e0af7b2e3e9528ea489f4138a12c9c0",
    "commission_deadline.py": "9ae2b59f51902ae1f8f0cef459fad2b5f2ac10445ccabd17b33f995a26d70097",
    "pick.py": "4311200ae485ffd19b2560434e46c0c01899fbb58f0793c198292dba6004503b",
    "remote_sub_helpers.py": "0d5f5c38b60eeef70cc7cefe37ee64bd69d56d3e3bdd32644871279fc0e88556",
    "pool_ledger.py": "85d40296487f1f040ef3597b8110966e36a9b6ebee781e05a5e6172b8610d78e",
    "sub.sh": "7ceaba75dc4375bb05742b779967ade294afcc969358f610ecdb43041fa2f7d2",
}

# Frozen historical instants. The census interval is bounded independently by
# the launch artifact and by the first controller setup stage.
REQUEST_CREATED_AT = 1793585263.0200808
LAUNCH_CREATED_AT = 1793585266.357664
CONTROLLER_RC = 75
CONTROLLER_SIGNAL = "admission"
CONTROLLER_REASON = "remote_admission_refused"
DEADLINE_NS = 608489107965416
MAX_ATTEMPTS = 3
WALL_SECONDS = 7200
CONTINUATION_REASON = "continuation_evidence_unqualified"

# The one released broker row that the bounded census can reconstruct.
LEASE_ID = "9e8400f4e4d6"
LEASE_GRANTED_AT = 1793585266.9144828
LEASE_LAST_HEARTBEAT = 1793585270.660717
LEASE_TTL = 7436
LEASE_PID = 2806
LEASE_STATE = "released"
LEASE_RENEWABLE = 1
LEASE_QUOTA_SCOPE = "minimax:default"
# The census bounds are widened by one second so a lost timestamp precision can
# never hide a second acquisition of the same root and route.
CENSUS_MARGIN_SECONDS = 1.0

# The thirteen controller commission stages this run actually executed. This is
# the retained stage set, not an execution order.
CONTROLLER_LABELS = (
    "commission-host-registry", "commission-setup", "commission-support-meta",
    "commission-packet-upload", "commission-support-mkdir", "commission-support-upload",
    "commission-manifest-upload", "commission-policy-upload", "commission-support-publish",
    "commission-routing-env", "commission-launch", "commission-poll",
    "commission-admission-read",
)
CONTROLLER_NONZERO_LABEL = "commission-admission-read"
PROCESS_SCHEMA = "mastermind.local_owned_process_receipt.v1"

_LOG_PREFIX = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z \[remote_sub id=" + re.escape(RUN)
    + r" host=" + re.escape(HOST) + r"\] (.*)$")


def _log_required():
    """The contract's ordered run facts. Each must appear exactly once."""
    return (
        ("RUN_RESERVED explicit=1", "RUN_RESERVED explicit=1"),
        ("LEASE_WAIT", r"LEASE_WAIT pool=minimax wait=[0-9]+"),
        ("LEASE_OK", r"LEASE_OK pool=minimax"),
        ("SCP", r"SCP packet=\S+ support=executor-surface"),
        ("SUPPORT_VERSION_READY", r"SUPPORT_VERSION_READY digest=" + SUPPORT_DIGEST
         + r" policy=" + POLICY_SHA256),
        ("LAUNCH_ATTEMPT", r"LAUNCH_ATTEMPT attempt=1"),
        ("RC", r"RC value=75 poll=1"),
        ("REMOTE_DONE", r"REMOTE_DONE rc=75"),
        ("RSYNC", r"RSYNC stdout=\S+ out=\S+"),
        ("USAGE_RECEIPT_MISSING", r"USAGE_RECEIPT_MISSING"),
        ("REMOTE_CLEANED", r"REMOTE_CLEANED transport=1 receipt_saved=0 usage_saved=0"),
        ("DONE", r"DONE rc=75 signal=admission reason=remote_admission_refused"),
    )

# Any of these would contradict a single refused admission with no provider
# execution, no retry and no later usage or receipt publication.
_LOG_FORBIDDEN = (
    "USAGE_RECEIPT_SAVED", "USAGE_VALIDATED", "PROVIDER_OUTCOME_RECORDED",
    "PROVIDER_OUTCOME_UNQUALIFIED", "SESSION_INDEX_SAVED", "SESSION_INDEX_COPY_FAILED",
    "TRANSPORT_RECEIPT_SAVED", "ADMISSION_BUSY", "ADMISSION_RETRY",
    "ADMISSION_WAIT_EXHAUSTED", "REMOTE_CAPTURE_TRUNCATED", "REMOTE_EFFECT_UNKNOWN",
    "REMOTE_ARTIFACTS_PRESERVED", "EFFECT_UNKNOWN", "RESULT_UNAVAILABLE",
    "NATIVE_SETTLED", "NATIVE_EFFECT_UNKNOWN", "NATIVE_WINDOW",
    "TERMINAL_PUBLICATION_FAILED", "MACRO_RESULT_PUBLICATION_FAILED",
    "OUTPUT_CONTRACT_MISSING", "COMMISSION_PROCESS_UNPROVEN",
)


def _number(value):
    """Accept only a real JSON number, never a bool or a string."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _close(left, right, tolerance=1e-6):
    if left is None or right is None:
        return False
    return abs(left - right) <= tolerance


def _epoch(raw):
    """Parse a UTC instant without accepting a naive or non-UTC timestamp."""
    if not isinstance(raw, str) or not raw.endswith("Z"):
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.timestamp()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def state_dir():
    return owner_path(HERE / "state" / "remote_sub", HERE)


def lanes_dir():
    return owner_path(HERE / "lanes", HERE)


def receipt_path():
    return state_dir() / (RUN + RECONCILIATION_SUFFIX)


def exact_inventory(chain, *, allow_reconciliation=False):
    """The owner state holds only this run's original files and our receipt."""
    names = set()
    with os.scandir(chain.fd) as entries:
        for entry in entries:
            if entry.name.startswith(RUN):
                names.add(entry.name)
                if len(names) > len(ARTIFACTS) + int(allow_reconciliation):
                    raise Unqualified("contradictory_run_artifact")
    wanted = {RUN + "." + suffix for suffix in ARTIFACTS}
    receipt = RUN + RECONCILIATION_SUFFIX
    if names != wanted and not (allow_reconciliation and names == wanted | {receipt}):
        raise Unqualified("run_inventory_mismatch")
    chain.verify()
    return names


def exact_lane_inventory(chain):
    """The owner lane holds only this run's retained refusal result."""
    names = set()
    with os.scandir(chain.fd) as entries:
        for entry in entries:
            if entry.name.startswith(RUN):
                names.add(entry.name)
                if len(names) > 1:
                    raise Unqualified("contradictory_lane_artifact")
    if names != {RESULT_NAME}:
        raise Unqualified("lane_inventory_mismatch")
    chain.verify()
    return names


def _process_receipts(raw, *, labels, nonzero_label):
    """Require one complete, capture-proven receipt per expected stage."""
    text = raw.decode("utf-8", errors="strict")
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        row = strict_json(line.encode())
        if type(row) is not dict or row.get("schema") != PROCESS_SCHEMA:
            raise Unqualified("process_receipt_schema")
        rows.append(row)
    if len(rows) != len(labels):
        raise Unqualified("process_receipt_count")
    seen = []
    for row in rows:
        label = row.get("label")
        if label not in labels or label in seen:
            raise Unqualified("process_receipt_label")
        seen.append(label)
        cleanup = row.get("cleanup")
        if (type(cleanup) is not dict
                or cleanup.get("identity_verified") is not True
                or cleanup.get("census_proven") is not True
                or cleanup.get("status") != "not_needed"
                or cleanup.get("reason") != "normal_completion"
                or cleanup.get("error_code", "missing") is not None
                or type(cleanup.get("residual_count")) is not int
                or cleanup["residual_count"] != 0):
            raise Unqualified("process_cleanup_unproven")
        for stem in ("stdin_delivery", "stdout_capture", "stderr_capture"):
            if (cleanup.get(stem + "_complete") is not True
                    or cleanup.get(stem + "_error", "missing") is not None):
                raise Unqualified("process_capture_unproven")
        if (row.get("timed_out") is not False
                or row.get("stdout_truncated") is not False
                or row.get("stderr_truncated") is not False
                or row.get("runtime_failure_code", "missing") is not None
                or type(row.get("pid")) is not int or row["pid"] <= 0
                or type(row.get("pgid")) is not int or row["pgid"] != row["pid"]
                or type(row.get("stdout_bytes")) is not int
                or row["stdout_bytes"] < 0
                or re.fullmatch(r"[a-f0-9]{64}", str(row.get("stdout_sha256"))) is None
                or type(row.get("stderr_bytes")) is not int
                or row["stderr_bytes"] < 0):
            raise Unqualified("process_receipt_unqualified")
        started = _epoch(row.get("started_at"))
        ended = _epoch(row.get("ended_at"))
        if started is None or ended is None or ended < started:
            raise Unqualified("process_receipt_time_invalid")
        expected_rc = 1 if label == nonzero_label else 0
        if type(row.get("returncode")) is not int or row["returncode"] != expected_rc:
            raise Unqualified("process_receipt_returncode")
    if set(seen) != set(labels):
        raise Unqualified("process_receipt_labels")
    return rows


def _validate_log(raw):
    """Bind the retained log to this run, host and refused-admission sequence."""
    text = raw.decode("utf-8", errors="strict")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines:
        raise Unqualified("log_empty")
    events = []
    for line in lines:
        match = _LOG_PREFIX.match(line)
        if match is None:
            raise Unqualified("log_line_unbound")
        event = match.group(1)
        if any(marker in event for marker in _LOG_FORBIDDEN):
            raise Unqualified("log_contradictory_event")
        events.append(event)
    positions = []
    for name, pattern in _log_required():
        found = [index for index, event in enumerate(events)
                 if re.fullmatch(pattern, event) is not None]
        if len(found) != 1:
            raise Unqualified("log_event:" + name)
        positions.append(found[0])
    if positions != sorted(positions):
        raise Unqualified("log_event_order")
    if positions[-1] != len(events) - 1:
        raise Unqualified("log_terminal_event_not_last")
    if len([event for event in events if event.startswith("LAUNCH_ATTEMPT ")]) != 1:
        raise Unqualified("log_launch_attempt_count")
    return events


def validate_chain(raw):
    """Check the semantic relationships between the retained owner records."""
    request = strict_json(raw["request.json"])
    launch = strict_json(raw["request-launch.json"])
    returned = strict_json(raw["request-return.json"])
    continuation = strict_json(raw["continuation-request.json"])
    finished = strict_json(raw["continuation-finished.json"])
    support = strict_json(raw["support.json"])
    for value in (request, launch, returned, continuation, finished):
        if type(value) is not dict:
            raise Unqualified("record_not_object")
    if type(support) is not dict or not support:
        raise Unqualified("support_manifest_invalid")
    for name, value in support.items():
        if (not isinstance(name, str) or not name
                or re.fullmatch(r"[a-f0-9]{64}", str(value)) is None):
            raise Unqualified("support_manifest_invalid")
    for value in (request, launch, returned, continuation, finished):
        if value.get("root_id") != ROOT or value.get("parent_run_id") != ROOT:
            raise Unqualified("lineage_mismatch")
    for value in (request, launch, returned):
        if value.get("run_id") != RUN:
            raise Unqualified("run_mismatch")
    packet = raw["request.packet"]
    if (request.get("schema") != "mastermind.fabric_request_artifact.v1"
            or request.get("task_class") != TASK_CLASS
            or request.get("cwd") != "~"
            or request.get("automatic_background_execution") is not False
            or request.get("packet") != RUN + ".request.packet"
            or type(request.get("packet_bytes")) is not int
            or request["packet_bytes"] != len(packet)
            or request["packet_bytes"] != PACKET_BYTES
            or request.get("packet_sha256") != digest(packet)
            or not _close(_number(request.get("created_at")), REQUEST_CREATED_AT)):
        raise Unqualified("request_binding")
    if (launch.get("schema") != "mastermind.fabric_request_launch.v1"
            or launch.get("state") != "LAUNCH_ATTEMPT_RESERVED"
            or launch.get("capacity_handoff") is not True
            or type(launch.get("route")) is not dict
            or set(launch["route"]) != set(ROUTE_FIELDS)
            or launch["route"] != ROUTE
            or launch.get("native_sources") != LAUNCH_SOURCES
            or launch.get("request_sha256") != digest(raw["request.json"])
            or launch.get("packet_sha256") != digest(packet)
            or not _close(_number(launch.get("created_at")), LAUNCH_CREATED_AT)):
        raise Unqualified("launch_binding")
    if (returned.get("schema") != "mastermind.fabric_request_return.v1"
            or returned.get("state") != "NATIVE_CONTROLLER_RETURNED"
            or type(returned.get("controller_rc")) is not int
            or returned["controller_rc"] != CONTROLLER_RC
            or returned.get("request_sha256") != digest(raw["request.json"])
            or returned.get("launch_sha256") != digest(raw["request-launch.json"])
            or returned.get("log_sha256") != digest(raw["log"])
            or "prelease_sha256" not in returned or returned["prelease_sha256"] is not None):
        raise Unqualified("controller_return_binding")
    if (continuation.get("schema") != "mastermind.fabric_continuation.v1"
            or continuation.get("origin_run_id") != RUN
            or continuation.get("background_execution") is not False
            or type(continuation.get("deadline_ns")) is not int
            or continuation["deadline_ns"] != DEADLINE_NS
            or type(continuation.get("max_attempts")) is not int
            or continuation["max_attempts"] != MAX_ATTEMPTS
            or type(continuation.get("wall_seconds")) is not int
            or continuation["wall_seconds"] != WALL_SECONDS
            or finished.get("schema") != "mastermind.fabric_continuation.v1"
            or finished.get("origin_run_id") != RUN
            or finished.get("effective_run_id") != RUN
            or finished.get("background_execution") is not False
            or type(finished.get("controller_rc")) is not int
            or finished["controller_rc"] != CONTROLLER_RC
            or finished.get("reason") != CONTINUATION_REASON):
        raise Unqualified("continuation_binding")
    support_manifest = canonical({"schema": "remote-support-code.v1", "files": support})
    if digest(support_manifest) != SUPPORT_DIGEST:
        raise Unqualified("support_digest")
    for name, expected in SUPPORT_SOURCES.items():
        if support.get(name) != expected:
            raise Unqualified("support_source_binding")
    if support.get("pools.yaml") != POLICY_SHA256:
        raise Unqualified("support_policy_binding")
    _validate_log(raw["log"])
    routing = _process_receipts(
        raw["routing-process.jsonl"], labels=(RUN + ".routing",),
        nonzero_label=None)
    controller = _process_receipts(
        raw["controller-process.jsonl"], labels=CONTROLLER_LABELS,
        nonzero_label=CONTROLLER_NONZERO_LABEL)
    return {"routing": routing, "controller": controller}


def _setup_stage_start(controller_rows):
    """The controller setup stage bounds the acquisition interval.

    The retained receipts hold exactly one setup stage, so this is the only
    setup start. The bound is independent of the launch artifact's own
    creation time.
    """
    for row in controller_rows:
        if row.get("label") == "commission-setup":
            return _epoch(row.get("started_at"))
    raise Unqualified("controller_setup_stage_missing")


def _host_registry_end(controller_rows):
    for row in controller_rows:
        if row.get("label") == "commission-host-registry":
            return _epoch(row.get("ended_at"))
    raise Unqualified("controller_host_registry_stage_missing")


def _broker_db_path():
    """Resolve the incumbent broker database without constructing a broker."""
    try:
        import lease_broker
    except ImportError as exc:
        raise Unqualified("broker_owner_unavailable") from exc
    configured = os.environ.get("POOL_BROKER_DB")
    raw = configured or lease_broker.DEFAULT_DB
    return owner_path(Path(raw), HERE)


def _db_identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_mode, info.st_uid)


def _journal_mode(path):
    """Read the SQLite header's write format without opening the database."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise Unqualified("broker_db_custody")
        header = os.pread(fd, 20, 0)
    except OSError as exc:
        raise Unqualified("broker_db_unavailable") from exc
    finally:
        os.close(fd)
    if len(header) < 20 or header[:16] != b"SQLite format 3\x00":
        raise Unqualified("broker_db_not_sqlite")
    return "wal" if header[18] == 2 else "rollback"


def _sidecars(path):
    """Snapshot the broker's own write-ahead sidecars without creating them."""
    state = {}
    for suffix in ("-wal", "-shm"):
        side = Path(str(path) + suffix)
        try:
            info = side.lstat()
        except FileNotFoundError:
            state[suffix] = None
            continue
        except OSError as exc:
            raise Unqualified("broker_sidecar_unreadable") from exc
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise Unqualified("broker_sidecar_custody")
        state[suffix] = (info.st_dev, info.st_ino, info.st_size)
    return state


def broker_census(*, lower, upper):
    """Read the incumbent broker database once, read-only, and prove one row.

    The database is never constructed, snapshotted, garbage collected or
    released here, and the census never creates the broker's write-ahead
    sidecars: an empty or absent write-ahead log is read as an immutable
    complete database, and a populated one is read only while the broker's own
    shared-memory index is already present. An absent, ambiguous, mutating or
    incomplete census is a refusal, never an inferred proof.
    """
    path = _broker_db_path()
    try:
        info = path.lstat()
    except OSError as exc:
        raise Unqualified("broker_db_unavailable") from exc
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_nlink != 1 or info.st_mode & 0o022):
        raise Unqualified("broker_db_custody")
    before = _db_identity(info)
    journal = _journal_mode(path)
    before_sidecars = _sidecars(path)
    write_ahead = before_sidecars["-wal"]
    if journal == "wal" and (write_ahead is None or write_ahead[2] == 0):
        # The main database file already holds every committed row. An
        # immutable read cannot create a sidecar and cannot lose a commit.
        read_mode = "immutable_complete"
        uri = "file:" + urllib.parse.quote(str(path)) + "?mode=ro&immutable=1"
    elif journal == "wal":
        if before_sidecars["-shm"] is None:
            raise Unqualified("broker_sidecar_absent")
        read_mode = "wal_attached"
        uri = "file:" + urllib.parse.quote(str(path)) + "?mode=ro"
    else:
        read_mode = "rollback_journal"
        uri = "file:" + urllib.parse.quote(str(path)) + "?mode=ro"
    query = (
        "SELECT id, orchestrator_id, pool, account, task_class, model, host, pid,"
        " granted_at, ttl, last_heartbeat, state, renewable, quota_scope,"
        " quota_outcome_sha256 FROM leases WHERE granted_at BETWEEN ? AND ?"
        " AND orchestrator_id = ? AND pool = ? AND account = ? AND task_class = ?"
        " AND host = ?")
    params = (lower, upper, ROOT, POOL, ACCOUNT, TASK_CLASS_BROKER, HOST)
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=10)
    except sqlite3.Error as exc:
        raise Unqualified("broker_db_unavailable") from exc
    try:
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN DEFERRED")
            rows = connection.execute(query, params).fetchall()
        except sqlite3.Error as exc:
            raise Unqualified("broker_census_incomplete") from exc
        census = [dict(row) for row in rows]
    finally:
        try:
            connection.close()
        except sqlite3.Error:
            pass
    try:
        after_info = path.lstat()
    except OSError as exc:
        raise Unqualified("broker_db_unavailable") from exc
    if _db_identity(after_info) != before:
        raise Unqualified("broker_census_mutated")
    after_sidecars = _sidecars(path)
    if after_sidecars != before_sidecars:
        # A write-ahead commit or a sidecar this census would have created
        # both mean the observed row set is not a stable bounded census.
        raise Unqualified("broker_census_mutated")
    if len(census) != 1:
        raise Unqualified("broker_census_row_count:" + str(len(census)))
    row = census[0]
    if (row.get("id") != LEASE_ID
            or row.get("orchestrator_id") != ROOT
            or row.get("pool") != POOL
            or row.get("account") != ACCOUNT
            or row.get("task_class") != TASK_CLASS_BROKER
            or row.get("model") != ROUTE["MODEL"]
            or row.get("host") != HOST
            or type(row.get("pid")) is not int or row["pid"] != LEASE_PID
            or not _close(_number(row.get("granted_at")), LEASE_GRANTED_AT)
            or type(row.get("ttl")) is not int or row["ttl"] != LEASE_TTL
            or not _close(_number(row.get("last_heartbeat")), LEASE_LAST_HEARTBEAT)
            or row.get("state") != LEASE_STATE
            or type(row.get("renewable")) is not int
            or row["renewable"] != LEASE_RENEWABLE
            or row.get("quota_scope") != LEASE_QUOTA_SCOPE
            or row.get("quota_outcome_sha256") is not None):
        raise Unqualified("broker_lease_row_unqualified")
    return row, {"read_mode": read_mode, "journal_mode": journal,
                 "sidecars_present_before": {
                     "wal": before_sidecars["-wal"] is not None,
                     "shm": before_sidecars["-shm"] is not None},
                 "sidecars_created_by_census": False}


def ledger_identity():
    """Read the retained terminal identity; never adjudicate or accept it."""
    try:
        import pool_ledger
    except ImportError as exc:
        raise Unqualified("ledger_owner_unavailable") from exc
    observed = pool_ledger.read_execution_identity(
        RUN, expected_rc=CONTROLLER_RC, expected_signal=CONTROLLER_SIGNAL)
    if (type(observed) is not dict
            or observed.get("lineage_state") != "VERIFIED_TERMINAL"
            or observed.get("root_id") != ROOT
            or observed.get("parent_run_id") != ROOT):
        raise Unqualified("ledger_execution_identity_unqualified")
    return observed


def verify_compatible_generation(held, store):
    """Require the frozen relevant source bytes from the compatible closure."""
    root = store / COMPATIBLE_GENERATION
    for directory, mode in ((store, 0o700), (root, 0o555), (root / "ext", 0o555)):
        held.require_directory(directory, mode=mode)
    manifest_raw = held.read(root / "RELEASE.json", mode=0o444, limit=262144)
    if digest(manifest_raw) != COMPATIBLE_RELEASE_SHA256:
        raise Unqualified("compatible_generation_release_digest")
    manifest = strict_json(manifest_raw)
    if (type(manifest) is not dict or set(manifest) != {
            "digest", "schema", "files", "links", "entrypoints", "stable_ext"}
            or manifest["schema"] != "native-code-generation.v1"
            or manifest["digest"] != COMPATIBLE_GENERATION
            or manifest["stable_ext"] != str(store.parent / "ext")
            or type(manifest["files"]) is not dict
            or len(manifest["files"]) != COMPATIBLE_GENERATION_FILES
            or manifest["entrypoints"] != {
                "pool": "pool", "remote": "ext/remote_sub.sh",
                "task": "ext/fabric_task.py"}):
        raise Unqualified("compatible_generation_binding")
    material = {key: value for key, value in manifest.items() if key != "digest"}
    if digest(canonical(material)) != COMPATIBLE_GENERATION:
        raise Unqualified("compatible_generation_digest")
    for name, expected in NATIVE_SOURCES.items():
        if manifest["files"].get("ext/" + name) != expected:
            raise Unqualified("compatible_source_manifest")
        data = held.read(root / "ext" / name, mode=0o555, limit=2097152)
        if digest(data) != expected:
            raise Unqualified("compatible_source_bytes")
    return {"compatible_generation": COMPATIBLE_GENERATION,
            "compatible_release_sha256": COMPATIBLE_RELEASE_SHA256,
            "compatible_generation_files": COMPATIBLE_GENERATION_FILES}


def _historical_proof(held, run_id, root_id, *, allow_reconciliation=False):
    if run_id != RUN or root_id != ROOT:
        raise Unqualified("unsupported_original_request")
    state = state_dir()
    store = state.parents[2] / "native-code-releases"
    state_chain = held.chain(state)
    lanes = lanes_dir()
    lanes_chain = held.chain(lanes)
    inventory = exact_inventory(state_chain, allow_reconciliation=allow_reconciliation)
    exact_lane_inventory(lanes_chain)
    raw = {}
    limits = {"request.packet": 65536, "controller-process.jsonl": 1048576,
              "log": 1048576, "routing-process.jsonl": 1048576}
    for suffix, expected in ARTIFACTS.items():
        data = held.read(state / (RUN + "." + suffix), mode=0o600,
                         limit=limits.get(suffix, 65536))
        if digest(data) != expected:
            raise Unqualified("historical_artifact_digest:" + suffix)
        raw[suffix] = data
    result = held.read(lanes / RESULT_NAME, mode=0o600, limit=65536)
    if digest(result) != RESULT_SHA256 or len(result) != RESULT_BYTES:
        raise Unqualified("historical_result_digest")
    if result != (RESULT_LINE + "\n").encode():
        raise Unqualified("historical_result_content")
    records = validate_chain(raw)
    setup_start = _setup_stage_start(records["controller"])
    registry_end = _host_registry_end(records["controller"])
    lower = LAUNCH_CREATED_AT - CENSUS_MARGIN_SECONDS
    upper = setup_start + CENSUS_MARGIN_SECONDS
    if not (lower <= LEASE_GRANTED_AT <= upper):
        raise Unqualified("census_interval_excludes_grant")
    lease, census_state = broker_census(lower=lower, upper=upper)
    ledger = ledger_identity()
    generation = verify_compatible_generation(held, store)
    if exact_inventory(state_chain, allow_reconciliation=allow_reconciliation) != inventory:
        raise Unqualified("run_inventory_changed")
    if exact_lane_inventory(lanes_chain) != {RESULT_NAME}:
        raise Unqualified("lane_inventory_changed")
    held.verify()
    proof = {
        "schema": SCHEMA, "run_id": RUN, "root_id": ROOT, "parent_run_id": ROOT,
        "predicate": PREDICATE,
        "evidence_basis": "retained_native_owner_hash_chain_and_historical_control_flow",
        "artifact_sha256": dict(ARTIFACTS), "result_sha256": RESULT_SHA256,
        "result_bytes": RESULT_BYTES,
        "historical_source_sha256": dict(NATIVE_SOURCES),
        "launch_native_sources": dict(LAUNCH_SOURCES),
        "support_source_sha256": dict(SUPPORT_SOURCES),
        "support_digest": SUPPORT_DIGEST, "policy_sha256": POLICY_SHA256,
        "controller_rc": CONTROLLER_RC, "signal": CONTROLLER_SIGNAL,
        "reason": CONTROLLER_REASON,
        "controller_process_labels": list(CONTROLLER_LABELS),
        "host_registry_ended_at": registry_end,
        "first_setup_started_at": setup_start,
        "census_interval": {"lower": lower, "upper": upper,
                            "lower_basis": "launch_artifact_created_at",
                            "upper_basis": "controller_setup_stage_started_at",
                            "margin_seconds": CENSUS_MARGIN_SECONDS},
        "broker_census": census_state,
        "reconstructed_lease": {
            "lease_id": lease["id"], "state": lease["state"],
            "orchestrator_id": lease["orchestrator_id"], "pool": lease["pool"],
            "account": lease["account"], "task_class": lease["task_class"],
            "model": lease["model"], "host": lease["host"], "pid": lease["pid"],
            "granted_at": lease["granted_at"], "ttl": lease["ttl"],
            "last_heartbeat": lease["last_heartbeat"],
            "renewable": lease["renewable"], "quota_scope": lease["quota_scope"],
            "lease_id_bound_by_run_artifact": False,
            "lease_id_source": "reconstructed_unique_bounded_broker_census",
            "pid_corroboration_only": True,
            "original_acquisition_receipt_claimed": False,
            "released_at_observation": "observed_released_state_at_check_time",
            "release_before_original_return_claimed": False,
        },
        "ledger_lineage_state": ledger["lineage_state"],
        "original_selected_generation_recorded": False,
        "compatible_generation": generation["compatible_generation"],
        "compatible_generation_release_sha256": generation["compatible_release_sha256"],
        "compatible_generation_files": generation["compatible_generation_files"],
        "compatible_generation_is_original_selection": False,
        "telemetry_transport_absence_claimed": False,
        "remote_cryptographic_attestation_claimed": False,
        "same_os_principal_native_evidence_model": True,
        "canonical_state_changed": False, "reconciliation_performed": False,
        "retry_allowed": False, "acceptance_eligible": False,
        "new_work_admission": "UNCHANGED", "review_result_available": False,
    }
    proof["proof_sha256"] = digest(canonical(proof))
    return proof


def check_original(run_id, root_id):
    """Read-only fixed-case proof; it never writes or changes any state.

    The own reconciliation receipt is an allowed member of the closed owner
    inventory, so a repeated check after a reconciliation still qualifies.
    """
    with EvidenceReadSet() as held:
        return _historical_proof(held, run_id, root_id, allow_reconciliation=True)
