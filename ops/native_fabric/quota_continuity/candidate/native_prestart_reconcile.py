from __future__ import annotations

import hashlib
import math
import sqlite3
import json
import os
import re
import stat
import subprocess
import time
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
RUN_ID = "paper-01a1101f-library-controller-r1"
ROOT_ID = "01a1101f-2a37-7320-9a9b-5df3ce1b890d"
LEASE_ID = "3e4b0e50d403"
HOST = "ubuntu2"
MODE = "grok"
MODEL = "grok-4.6"
POOL = "grok"
ACCOUNT = "default"
TASK_CLASS = "integration"
BROKER_TASK_CLASS = "remote-grok"
POLICY_SHA = "a1ad86305296c5b2e72c547a538072c56200798f8f3cba4194ac520bab20114d"
LOG_SHA = "4d35e48fe5d5951ff510a988706adeca15b66df53322cf2c2bc90b2eccb444e5"
LEDGER_SHA = "6a09b22174d59739097e489db5233c37f56fa8c6e4409f82f1f60455af602287"
PACKET_SHA = "bccb87382aaea54a585e2619029e503ec419ee8ab7b2419e6ec4a8119ede5add"
SUPPORT_DIGEST = "6f055b8b72776138f49441037bb2d03c55b016312323dafe009ad93313ba9fac"
NATIVE_SHA = "59b9faac90ea2b96886e819b9d75396b26546827ec1d2c2971739c5a2ccb0d6c"
EXECUTOR_SHA = "7248aab24b0b24ec6dbe2a9eb243fd81a8cca8a55f5e9e5819eb5edde774b98b"
STDOUT_BYTES = b"native_remote_run_invalid\n"
STDOUT_SHA = "eb6741398d5c3df726070e226c3b39ed5ca365065b223f07f4f9921672e173fd"
RC_BYTES = b"78\n"
RC_SHA = "b03c70ff0d641a363f1a021413a098dce02e4c68b75f3a47aa10044f42ee1784"
ISSUED_AT = 1791342749.0
DEADLINE_AT = 1791343329.0
LAST_HEARTBEAT = 1791342749.672811
SCHEMA = "mastermind.fabric_task.prestart-reconciliation.v1"
MAX_RECEIPT_BYTES = 65_536
MAX_LOG_BYTES = 1_048_576
IDENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class PrestartReconcileError(RuntimeError):
    def __init__(self, field: str, detail: str = "invalid"):
        super().__init__(f"{field}:{detail}")
        self.field = field
        self.detail = detail


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

def _regular(path: Path, limit: int, *, field: str) -> bytes:
    if HERE.parent.parent.name == "native-code-releases":
        from native_runtime_bindings import owner_path
        path = owner_path(path, HERE)
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise PrestartReconcileError(field, "not_regular")
        if info.st_size > limit:
            raise PrestartReconcileError(field, "bounded")
        with path.open("rb") as handle:
            data = handle.read(limit + 1)
        if len(data) > limit:
            raise PrestartReconcileError(field, "bounded")
        return data
    except FileNotFoundError as exc:
        raise PrestartReconcileError(field, "missing") from exc
    except PrestartReconcileError:
        raise
    except OSError as exc:
        raise PrestartReconcileError(field, "unreadable") from exc


def _safe_owner(path: Path, field: str, *, allow_link: bool = False, allow_group_write: bool = False) -> os.stat_result:
    if HERE.parent.parent.name == "native-code-releases":
        from native_runtime_bindings import owner_path
        path = owner_path(path, HERE)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) and not allow_link:
        raise PrestartReconcileError(field, "symlink")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise PrestartReconcileError(field, "owner")
    if info.st_mode & (0o002 if allow_group_write else 0o022):
        raise PrestartReconcileError(field, "writable")
    return info


def local_evidence() -> tuple[bytes, bytes]:
    log = _regular(HERE / "state" / "remote_sub" / f"{RUN_ID}.log", MAX_LOG_BYTES, field="retained_log")
    result = _regular(HERE / "lanes" / f"{RUN_ID}.remote.stdout", 1024, field="retained_result")
    _safe_owner(HERE / "state" / "remote_sub" / f"{RUN_ID}.log", "retained_log")
    _safe_owner(HERE / "lanes" / f"{RUN_ID}.remote.stdout", "retained_result", allow_group_write=True)
    if result != STDOUT_BYTES or _sha(result) != STDOUT_SHA:
        raise PrestartReconcileError("retained_result", "diagnostic")
    _parse_log(log)
    _check_ledger()
    return log, result


def _line_identity(line: str) -> bool:
    return f"id={RUN_ID} host={HOST}" in line


def _parse_log(log: bytes) -> dict[str, Any]:
    try:
        text = log.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PrestartReconcileError("retained_log", "encoding") from exc
    if _sha(log) != LOG_SHA:
        raise PrestartReconcileError("retained_log", "original_digest")
    lines = text.splitlines()
    if not lines or not all(_line_identity(line) for line in lines):
        raise PrestartReconcileError("retained_log", "identity")
    joined = "\n".join(lines)
    required = (
        "RUN_RESERVED explicit=1",
        f"LEASE_WAIT pool={POOL}",
        f"LEASE_OK pool={POOL}",
        f"SUPPORT_VERSION_READY digest={SUPPORT_DIGEST} ",
        f"NATIVE_WINDOW issued=1791342749 deadline=1791343329 support={SUPPORT_DIGEST}",
        f"LAUNCH stdout=lanes_{RUN_ID}.stdout rc_file=ext/lanes_{RUN_ID}.rc",
        "RC value=78",
        "REMOTE_DONE rc=78",
        f"RSYNC stdout=~/lanes/ext/lanes_{RUN_ID}.stdout",
        "NATIVE_EFFECT_UNKNOWN same_carrier_reconciliation_required=1",
        "REMOTE_ARTIFACTS_PRESERVED effect_unknown=1",
        "DONE rc=78 signal=effect_unknown",
        f"LEASE_PRESERVED effect_unknown=1 lease={LEASE_ID}",
    )
    if any(item not in joined for item in required):
        raise PrestartReconcileError("retained_log", "shape")
    if joined.count("LAUNCH stdout=") != 1:
        raise PrestartReconcileError("retained_log", "launch_count")
    if joined.count("NATIVE_WINDOW ") != 1 or joined.count("REMOTE_DONE rc=") != 1:
        raise PrestartReconcileError("retained_log", "event_count")
    if "PROVIDER_START" in joined or "DONE rc=0" in joined:
        raise PrestartReconcileError("retained_log", "provider_effect")
    forbidden = ("REMOTE_CLEANUP_UNPROVEN ", "REMOTE_SUB_ADMISSION_", "REMOTE_SUB_RUNTIME_ERROR", "NATIVE_CAPTURE_TRUNCATED")
    if any(item in joined for item in forbidden):
        raise PrestartReconcileError("retained_log", "conflicting_failure")
    route_line = next((line for line in lines if " ECONOMIC_POLICY " in line), "")
    try:
        route = json.loads(route_line.split(" ECONOMIC_POLICY ", 1)[1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise PrestartReconcileError("retained_log", "route") from exc
    if route.get("requested_model") != MODEL or route.get("task_class") != TASK_CLASS:
        raise PrestartReconcileError("retained_log", "route")
    return {"sha256": _sha(log), "bytes": len(log)}


def _check_ledger():
    path = HERE.parent / "orch" / "fabric" / "ledger.jsonl"
    _safe_owner(path, "ledger")
    found = []
    with path.open("rb") as handle:
        for line in handle:
            if RUN_ID.encode() not in line:
                continue
            row = json.loads(line)
            if row.get("run_id") == RUN_ID:
                found.append((row, _sha(line)))
    if len(found) != 1 or found[0][1] != LEDGER_SHA:
        raise PrestartReconcileError("ledger", "original_digest")
    row = found[0][0]
    if (row.get("root_id"), row.get("parent_run_id"), row.get("model"), row.get("signal")) != (ROOT_ID, ROOT_ID, MODEL, "effect_unknown"):
        raise PrestartReconcileError("ledger", "original_parent")


def _load_hosts():
    path = HERE / "hosts.json"
    _safe_owner(path, "hosts_json")
    value = json.loads(_regular(path, 65536, field="hosts_json"))
    entry = value.get(HOST) if isinstance(value, dict) else None
    if not isinstance(entry, dict):
        raise PrestartReconcileError("hosts_json", "missing")
    return entry


def _probe_source() -> str:
    return r'''
import hashlib, json, os, socket, stat
from pathlib import Path
run_id, digest, issued, deadline = RUN_ARGUMENTS_PLACEHOLDER
uid = os.getuid()
root = Path.home() / "lanes"
release = root / "support-releases" / digest
def fail(field):
    print(json.dumps({"schema":"mastermind.prestart.remote-probe.v1","ok":False,"field":field}))
    raise SystemExit(0)
def regular(path, limit=None, allow_group_write=False):
    s = path.lstat()
    if stat.S_ISLNK(s.st_mode) or not stat.S_ISREG(s.st_mode) or s.st_uid != uid or s.st_mode & (0o002 if allow_group_write else 0o022):
        fail("unsafe_" + path.name)
    data = path.read_bytes()
    if limit is not None and len(data) > limit:
        fail("bounded_" + path.name)
    return data, s
def sha(data): return hashlib.sha256(data).hexdigest()
try:
    if socket.gethostname().split(".", 1)[0] != "ubuntu2": fail("hostname")
    if release.is_symlink() or not release.is_dir(): fail("release")
    manifest_data, _ = regular(release / "RELEASE.json", 65536)
    manifest = json.loads(manifest_data)
    if manifest.get("schema") != "remote-support-code.v1" or manifest.get("digest") != digest: fail("release_manifest")
    files = manifest.get("files", {})
    for name, expected in (("native_remote.py", "59b9faac90ea2b96886e819b9d75396b26546827ec1d2c2971739c5a2ccb0d6c"), ("remote_sub_exec.py", "7248aab24b0b24ec6dbe2a9eb243fd81a8cca8a55f5e9e5819eb5edde774b98b")):
        if files.get(name) != expected: fail("source_hash")
        data, _ = regular(release / "ext" / name, 1048576)
        if sha(data) != expected: fail("source_file")
    links = {}
    for name in ("lanes", "active"):
        link = release / "ext" / name
        if not link.is_symlink(): fail("release_link_" + name)
        target = Path(os.path.realpath(link))
        if root not in target.parents or target != root / "ext" / name: fail("release_link_target_" + name)
        ts = target.stat()
        if not stat.S_ISDIR(ts.st_mode) or ts.st_uid != uid or ts.st_mode & 0o002: fail("release_link_owner_" + name)
        links[name] = {"target": str(target), "directory": True, "owner_uid": ts.st_uid, "mode": stat.S_IMODE(ts.st_mode)}
    packet, packet_stat = regular(root / "tmp" / (run_id + ".txt"), 1048576)
    if sha(packet) != PACKET_SHA_PLACEHOLDER: fail("packet_digest")
    artifacts = {}
    for name, expected_hash, expected_data in (("stdout", "eb6741398d5c3df726070e226c3b39ed5ca365065b223f07f4f9921672e173fd", b"native_remote_run_invalid\n"), ("rc", "b03c70ff0d641a363f1a021413a098dce02e4c68b75f3a47aa10044f42ee1784", b"78\n")):
        path = root / "ext" / f"lanes_{run_id}.{name}"
        data, s = regular(path, 4096, allow_group_write=True)
        if sha(data) != expected_hash or data != expected_data: fail("artifact_" + name)
        if not issued <= s.st_mtime_ns / 1e9 <= deadline: fail("mtime_" + name)
        artifacts[name] = {"size": len(data), "sha256": sha(data), "owner_uid": s.st_uid, "mtime_ns": s.st_mtime_ns}
    expected_absent = {}
    paths = {
        "process_receipt": root / "ext" / "lanes" / f"{run_id}.process.jsonl",
        "native_terminal": root / "ext" / "lanes" / f"{run_id}.native-terminal.json",
        "usage": root / "ext" / "lanes" / f"{run_id}.usage.json",
        "active": root / "ext" / "active" / run_id,
        "grok_client": release / "ext" / "lanes" / f"{run_id}.grok",
    }
    for name, path in paths.items():
        exists = os.path.lexists(path)
        expected_absent[name] = not exists
        if exists: fail("present_" + name)
    matched = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit(): continue
        try:
            if entry.stat().st_uid != uid: continue
            command = (entry / "cmdline").read_bytes()
        except FileNotFoundError: continue
        except OSError: fail("process_census_unreadable")
        if run_id.encode() in command: matched.append(int(entry.name))
    unexpected = 0
    for directory in (root / "ext", release / "ext" / "lanes"):
        if not directory.exists(): fail("census_directory")
        for item in directory.iterdir():
            if run_id in item.name and item.name not in {f"lanes_{run_id}.stdout", f"lanes_{run_id}.rc"}:
                unexpected += 1
    if matched or unexpected: fail("live_effect")
    source = {"native_remote.py": NATIVE_SHA_PLACEHOLDER, "remote_sub_exec.py": EXECUTOR_SHA_PLACEHOLDER, "release_manifest": True, "manifest_sha256": sha(manifest_data), "packet_sha256": sha(packet), "links": links}
    facts = {"schema":"mastermind.prestart.remote-probe.v1","ok":True,"hostname":"ubuntu2","release":str(release),"source":source,"artifacts":artifacts,"absences":expected_absent,"process":{"matched":0,"pids":[]},"unexpected_artifacts":0}
    facts["facts_sha256"] = hashlib.sha256(json.dumps(facts, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    print(json.dumps(facts, sort_keys=True, separators=(",", ":")))
except Exception:
    fail("probe_exception")
'''.replace("NATIVE_SHA_PLACEHOLDER", repr(NATIVE_SHA)).replace("EXECUTOR_SHA_PLACEHOLDER", repr(EXECUTOR_SHA)).replace("PACKET_SHA_PLACEHOLDER", repr(PACKET_SHA)).replace("RUN_ARGUMENTS_PLACEHOLDER", repr((RUN_ID, SUPPORT_DIGEST, ISSUED_AT, DEADLINE_AT)))


def _collect_remote_facts() -> dict[str, Any]:
    entry = _load_hosts()
    alias = str(entry.get("ssh_alias") or HOST)
    if not IDENT_RE.fullmatch(alias) or alias.startswith("-"):
        raise PrestartReconcileError("hosts_json", "ssh_alias")
    hostnames = entry.get("hostnames")
    if not isinstance(hostnames, list) or any(not isinstance(item, str) or not item for item in hostnames):
        raise PrestartReconcileError("hosts_json", "hostnames")
    if HOST not in {item.split(".", 1)[0] for item in hostnames}:
        raise PrestartReconcileError("hosts_json", "hostname_identity")
    if MODE not in entry.get("allowed_modes", []) or "lanes" not in entry.get("roles", []):
        raise PrestartReconcileError("hosts_json", "mode")
    argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", alias, "python3 -"]
    try:
        proc = subprocess.run(argv, input=_probe_source().encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45, check=False)
    except subprocess.TimeoutExpired as exc:
        raise PrestartReconcileError("remote_probe", "timeout") from exc
    except OSError as exc:
        raise PrestartReconcileError("remote_probe", "transport") from exc
    if proc.returncode != 0 or len(proc.stdout) > 65_536:
        raise PrestartReconcileError("remote_probe", "bounded")
    try:
        facts = json.loads(proc.stdout)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PrestartReconcileError("remote_probe", "json") from exc
    if isinstance(facts, dict) and facts.get("ok") is False:
        raise PrestartReconcileError("remote_probe", str(facts.get("field", "refused"))[:120])
    _validate_remote_facts(facts)
    return facts


def _validate_remote_facts(facts: dict[str, Any]) -> None:
    if not isinstance(facts, dict) or facts.get("schema") != "mastermind.prestart.remote-probe.v1" or facts.get("ok") is not True:
        raise PrestartReconcileError("remote_probe", "shape")
    if facts.get("hostname") != HOST or not isinstance(facts.get("release"), str):
        raise PrestartReconcileError("remote_probe", "identity")
    if len(facts["release"]) > 1024 or not facts["release"].endswith("/support-releases/" + SUPPORT_DIGEST):
        raise PrestartReconcileError("remote_probe", "release_path")
    source = facts.get("source")
    if not isinstance(source, dict) or source.get("native_remote.py") != NATIVE_SHA or source.get("remote_sub_exec.py") != EXECUTOR_SHA or source.get("release_manifest") is not True:
        raise PrestartReconcileError("remote_probe", "source")
    links = source.get("links")
    if not isinstance(links, dict) or set(links) != {"lanes", "active"} or any(not isinstance(links[name], dict) or links[name].get("directory") is not True for name in links):
        raise PrestartReconcileError("remote_probe", "links")
    if source.get("packet_sha256") != PACKET_SHA or not re.fullmatch(r"[0-9a-f]{64}", str(source.get("manifest_sha256", ""))):
        raise PrestartReconcileError("remote_probe", "manifest_packet")
    artifacts = facts.get("artifacts")
    if not isinstance(artifacts, dict):
        raise PrestartReconcileError("remote_probe", "artifacts")
    if artifacts.get("stdout", {}).get("sha256") != STDOUT_SHA or artifacts.get("stdout", {}).get("size") != len(STDOUT_BYTES):
        raise PrestartReconcileError("remote_probe", "stdout")
    if artifacts.get("rc", {}).get("sha256") != RC_SHA or artifacts.get("rc", {}).get("size") != len(RC_BYTES):
        raise PrestartReconcileError("remote_probe", "rc")
    for name in ("stdout", "rc"):
        mtime = artifacts.get(name, {}).get("mtime_ns")
        if type(mtime) is not int or not ISSUED_AT * 1e9 <= mtime <= DEADLINE_AT * 1e9:
            raise PrestartReconcileError("remote_probe", f"{name}_mtime")
    if facts.get("absences") != {name: True for name in ("process_receipt", "native_terminal", "usage", "active", "grok_client")}:
        raise PrestartReconcileError("remote_probe", "absence")
    if facts.get("process", {}).get("matched") != 0 or facts.get("unexpected_artifacts") != 0:
        raise PrestartReconcileError("remote_probe", "live_effect")
    material = dict(facts)
    claimed = material.pop("facts_sha256", None)
    if claimed != _sha(_json(material)):
        raise PrestartReconcileError("remote_probe", "facts_hash")


def _read_broker_row():
    # Read the incumbent owner's existing DB without constructor, snapshot or GC.
    # Normal owner admission/heartbeat paths alone settle TTL expiry.
    path = HERE / "broker" / "leases.sqlite"
    _safe_owner(path, "broker_database")
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM leases WHERE id = ?", (LEASE_ID,)).fetchone()
    finally:
        conn.close()


def _row_value(row: Any, key: str) -> Any:
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return getattr(row, key, None)


def _broker_observation() -> dict[str, Any]:
    row = _read_broker_row()
    if row is None:
        raise PrestartReconcileError("broker_lease", "row_absent")
    if not _lease_identity_matches(row):
        raise PrestartReconcileError("broker_lease", "identity")
    state = str(_row_value(row, "state") or "")
    if state not in {"expired", "released"}:
        if state in {"held", "rented"}:
            return {"state": "PENDING", "lease_state": state, "read_only": True}
        raise PrestartReconcileError("broker_lease", "state")
    heartbeat = float(_row_value(row, "last_heartbeat"))
    if heartbeat != LAST_HEARTBEAT:
        raise PrestartReconcileError("broker_lease", "heartbeat")
    return {"state": state.upper(), "lease_state": state, "read_only": True, "identity": _lease_identity(row)}


def _lease_identity(row: Any) -> dict[str, Any]:
    return {key: str(_row_value(row, key)) for key in ("orchestrator_id", "pool", "account", "task_class", "model", "host")}


def _lease_identity_matches(row: Any) -> bool:
    return _lease_identity(row) == {
        "orchestrator_id": ROOT_ID,
        "pool": POOL,
        "account": ACCOUNT,
        "task_class": BROKER_TASK_CLASS,
        "model": MODEL,
        "host": HOST,
    }


def receipt_path() -> Path:
    return HERE / "state" / "remote_sub" / f"{RUN_ID}.prestart-reconciliation.json"


def _receipt_material(receipt: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in receipt.items() if key != "proof_sha256"}


def _validate_receipt(receipt: dict[str, Any], log: bytes, result: bytes) -> None:
    if type(receipt) is not dict or set(receipt) != {"schema", "run_id", "root_id", "parent_run_id", "lease_id", "created_at", "original", "broker", "remote_probe", "proof_sha256", "verdict"}:
        raise PrestartReconcileError("receipt", "closed_fields")
    if receipt.get("parent_run_id") != ROOT_ID or receipt.get("verdict") != "provider_not_started_scope_run_id_validation":
        raise PrestartReconcileError("receipt", "parent_verdict")
    if receipt.get("schema") != SCHEMA or receipt.get("run_id") != RUN_ID or receipt.get("root_id") != ROOT_ID or receipt.get("lease_id") != LEASE_ID:
        raise PrestartReconcileError("receipt", "binding")
    original = receipt.get("original")
    if original != {
        "host": HOST, "mode": MODE, "model": MODEL, "pool": POOL, "account": ACCOUNT,
        "task_class": TASK_CLASS, "support_digest": SUPPORT_DIGEST, "policy_sha256": POLICY_SHA,
        "packet_sha256": PACKET_SHA, "ledger_sha256": LEDGER_SHA,
        "native_remote_sha256": NATIVE_SHA, "remote_sub_exec_sha256": EXECUTOR_SHA,
        "log_sha256": _sha(log), "result_sha256": _sha(result), "result_bytes": len(result),
        "rc": 78, "issued_at": ISSUED_AT, "deadline_at": DEADLINE_AT,
    }:
        raise PrestartReconcileError("receipt", "original")
    broker = receipt.get("broker")
    if not isinstance(broker, dict) or broker.get("state") not in {"EXPIRED", "RELEASED"} or broker.get("identity") != _lease_identity({"orchestrator_id": ROOT_ID, "pool": POOL, "account": ACCOUNT, "task_class": BROKER_TASK_CLASS, "model": MODEL, "host": HOST}):
        raise PrestartReconcileError("receipt", "broker")
    facts = receipt.get("remote_probe")
    if not isinstance(facts, dict):
        raise PrestartReconcileError("receipt", "remote_probe")
    _validate_remote_facts(dict(facts))
    if receipt.get("proof_sha256") != _sha(_json(_receipt_material(receipt))):
        raise PrestartReconcileError("receipt", "proof_hash")
    created = receipt.get("created_at")
    if type(created) not in (int, float) or not math.isfinite(created) or not DEADLINE_AT <= created <= time.time() + 5:
        raise PrestartReconcileError("receipt", "created_at")


def _read_existing_receipt(log: bytes, result: bytes) -> dict[str, Any]:
    path = receipt_path()
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {}
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise PrestartReconcileError("receipt", "not_regular")
    if info.st_size > MAX_RECEIPT_BYTES or info.st_mode & 0o777 != 0o600:
        raise PrestartReconcileError("receipt", "mode")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise PrestartReconcileError("receipt", "owner")
    try:
        receipt = json.loads(_regular(path, MAX_RECEIPT_BYTES, field="receipt"))
    except json.JSONDecodeError as exc:
        raise PrestartReconcileError("receipt", "json") from exc
    _validate_receipt(receipt, log, result)
    return receipt


def status_from_receipt(log_bytes: bytes | None = None, result_bytes: bytes | None = None) -> dict[str, Any] | None:
    try:
        if log_bytes is None or result_bytes is None:
            log_bytes, result_bytes = local_evidence()
        receipt = _read_existing_receipt(log_bytes, result_bytes)
        if receipt:
            # This one-incident clearance is reverified through the authenticated
            # owner transport. A forged/rehashed local receipt is never authority.
            if _collect_remote_facts() != receipt["remote_probe"] or _broker_observation() != receipt["broker"]:
                return None
    except (PrestartReconcileError, OSError, ValueError, TypeError, KeyError, AttributeError):
        return None
    if not receipt:
        return None
    return {
        "schema": "mastermind.fabric_task_status.v1", "run_id": RUN_ID, "state": "RECONCILED_PRESTART_FAILURE",
        "rc": 78, "signal": "prestart_failure", "result_available": True, "result_bytes": len(result_bytes),
        "reconcile": {"schema": SCHEMA, "created_at": receipt["created_at"], "lease_state": receipt["broker"]["state"]},
    }


def _write_receipt(broker: dict[str, Any], facts: dict[str, Any], log: bytes, result: bytes) -> dict[str, Any]:
    now = time.time()
    original = {
        "host": HOST, "mode": MODE, "model": MODEL, "pool": POOL, "account": ACCOUNT,
        "task_class": TASK_CLASS, "support_digest": SUPPORT_DIGEST, "policy_sha256": POLICY_SHA,
        "packet_sha256": PACKET_SHA, "ledger_sha256": LEDGER_SHA,
        "native_remote_sha256": NATIVE_SHA, "remote_sub_exec_sha256": EXECUTOR_SHA,
        "log_sha256": _sha(log), "result_sha256": _sha(result), "result_bytes": len(result),
        "rc": 78, "issued_at": ISSUED_AT, "deadline_at": DEADLINE_AT,
    }
    receipt = {
        "schema": SCHEMA, "run_id": RUN_ID, "root_id": ROOT_ID, "lease_id": LEASE_ID,
        "created_at": now, "parent_run_id": ROOT_ID, "verdict": "provider_not_started_scope_run_id_validation",
        "original": original, "broker": broker, "remote_probe": facts,
    }
    receipt["proof_sha256"] = _sha(_json(_receipt_material(receipt)))
    _validate_receipt(receipt, log, result)
    target = receipt_path()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(target, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_json(receipt) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            target.unlink()
        except OSError:
            pass
        raise
    return receipt


def reconcile_prestart(run_id: str, root_id: str) -> dict[str, Any]:
    if run_id != RUN_ID:
        raise PrestartReconcileError("run_id", "not_bounded")
    if root_id != ROOT_ID:
        raise PrestartReconcileError("root_id", "not_bounded")
    log, result = local_evidence()
    try:
        existing = _read_existing_receipt(log, result)
    except PrestartReconcileError as exc:
        raise PrestartReconcileError("receipt_" + exc.field, exc.detail) from exc
    if existing:
        status = status_from_receipt(log, result)
        if not status:
            raise PrestartReconcileError("receipt", "owner_reverification")
        return status
    facts = _collect_remote_facts()
    broker = _broker_observation()
    if broker["state"] == "PENDING":
        return {
            "schema": "mastermind.fabric_task_status.v1", "run_id": RUN_ID, "state": "EFFECT_UNKNOWN",
            "rc": 78, "signal": "effect_unknown", "result_available": True, "result_bytes": len(result),
            "reconcile": {"state": "PENDING", "lease_state": broker["lease_state"]},
        }
    receipt = _write_receipt(broker, facts, log, result)
    return {
        "schema": "mastermind.fabric_task_status.v1", "run_id": RUN_ID, "state": "RECONCILED_PRESTART_FAILURE",
        "rc": 78, "signal": "prestart_failure", "result_available": True, "result_bytes": len(result),
        "reconcile": {"schema": SCHEMA, "created_at": receipt["created_at"], "lease_state": broker["state"]},
    }
