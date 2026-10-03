"""Preserve a quiescent runtime while the existing host acceptance proves a release.

This is an opt-in acceptance owner, not a scheduler or an admission API. Its
root-sealed descriptor permits one predecessor proof quota recovery. Only a
passing acceptance can publish an exact queued-root compatibility receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
import tempfile
from typing import Any

_RELEASE = Path(__file__).resolve().parents[2]
if str(_RELEASE) not in sys.path:
    sys.path.insert(0, str(_RELEASE))
from control_plane.fs_security import has_macos_acl

SYSTEM_ROOT = Path("/Library/Application Support/MastermindExecutive")
SCHEMA = "mastermind.executive_acceptance_maintenance/v1"
_TRUSTED_UID = 0
_SHA = re.compile(r"[0-9a-f]{40}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_TERMINAL = {"COMPLETED", "FAILED", "LOST", "CANCELLED", "RATE_LIMITED"}
_HEARTBEAT = {"last_seen_at_ms", "updated_at_ms", "version"}
_QUOTA_MUTABLE = _HEARTBEAT | {"status", "held_attempt_id", "fence_counter"}
_JOB_MUTABLE = {"status", "assigned_worker_id", "assigned_quota_class",
                "current_attempt_id", "attempt_count", "checkpoint", "result", "updated_at"}
_DESCRIPTOR_KEYS = {"schema_version", "predecessor_sha", "successor_sha", "root_job_id",
                    "root_identity_sha256", "root_event_id", "root_event_sha256",
                    "recovery_job_id", "recovery_attempt_id", "recovery_job_sha256",
                    "worker_id", "quota_class", "baseline_sha256", "backup_sha256",
                    "inventory_sha256", "prior_canary_sha256"}

class MaintenanceError(RuntimeError):
    pass

def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()

def _file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def bundle_path(sha: str) -> Path:
    if not isinstance(sha, str) or _SHA.fullmatch(sha) is None:
        raise MaintenanceError("invalid maintenance release")
    return SYSTEM_ROOT / "acceptance-maintenance" / sha

def _identity(info: os.stat_result) -> tuple:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

def _sealed_ancestors(path: Path) -> list:
    ancestors = []
    for parent in path.parents:
        info = parent.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != _TRUSTED_UID
                or info.st_mode & 0o022 or has_macos_acl(parent)):
            raise MaintenanceError("maintenance ancestor is not sealed")
        ancestors.append((parent, _identity(info)))
    return ancestors

def sealed_json(path: Path) -> dict[str, Any]:
    """Read a root-owned immutable document through a stable no-follow FD."""
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise MaintenanceError("maintenance document path is not canonical")
    ancestors = _sealed_ancestors(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != _TRUSTED_UID
                or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) not in {0o400, 0o444}
                or before.st_size > 16 * 1024 * 1024 or has_macos_acl(path)):
            raise MaintenanceError("maintenance document is not sealed")
        with os.fdopen(os.dup(fd), "rb") as stream:
            value = json.load(stream)
        if (_identity(before) != _identity(os.fstat(fd))
                or _identity(before) != _identity(path.lstat())
                or any(_identity(p.lstat()) != identity for p, identity in ancestors)):
            raise MaintenanceError("maintenance document changed during read")
    finally:
        os.close(fd)
    if not isinstance(value, dict):
        raise MaintenanceError("maintenance document is not an object")
    return value

def descriptor_for(sha: str) -> dict[str, Any] | None:
    path = bundle_path(sha) / "descriptor.json"
    if not path.exists() and not path.is_symlink():
        return None
    value = sealed_json(path)
    if set(value) != _DESCRIPTOR_KEYS or value.get("schema_version") != SCHEMA:
        raise MaintenanceError("maintenance descriptor schema mismatch")
    if (value["successor_sha"] != sha or not isinstance(value["predecessor_sha"], str)
            or _SHA.fullmatch(value["predecessor_sha"]) is None
            or value["predecessor_sha"] == sha):
        raise MaintenanceError("maintenance descriptor release mismatch")
    for key in ("root_identity_sha256", "root_event_sha256", "recovery_job_sha256",
                "baseline_sha256", "backup_sha256", "inventory_sha256", "prior_canary_sha256"):
        if not isinstance(value[key], str) or _DIGEST.fullmatch(value[key]) is None:
            raise MaintenanceError("maintenance descriptor digest is invalid")
    for key in ("root_job_id", "recovery_job_id", "recovery_attempt_id", "worker_id", "quota_class"):
        if not isinstance(value[key], str) or not value[key] or len(value[key]) > 128:
            raise MaintenanceError("maintenance descriptor identity is invalid")
    if type(value["root_event_id"]) is not int or value["root_event_id"] <= 0:
        raise MaintenanceError("maintenance descriptor event is invalid")
    return value

def root_identity(job: Any) -> str:
    return digest({k: v for k, v in job.to_dict().items() if k not in _JOB_MUTABLE})

def frozen_binding(job: Any, current: dict, store: Any) -> dict:
    """Return a predecessor base for only the exact PASS-qualified root.

    Every other binding field retains the current service value. Normal
    dispatch, source custody and arming gates continue to own all effects.
    """
    if job.constraints.get("base_sha") == current["base_sha"]:
        return current
    descriptor = descriptor_for(current["base_sha"])
    if descriptor is None or job.job_id != descriptor["root_job_id"]:
        return current
    if root_identity(job) != descriptor["root_identity_sha256"]:
        raise MaintenanceError("preserved root identity drifted")
    _summary, raw = summary_document(current["base_sha"])
    validate_carry_receipt(current["base_sha"], hashlib.sha256(raw).hexdigest())
    with store.read() as conn:
        event = conn.execute("SELECT * FROM events WHERE event_id=?", (descriptor["root_event_id"],)).fetchone()
    if event is None or digest(dict(event)) != descriptor["root_event_sha256"]:
        raise MaintenanceError("preserved root admission event drifted")
    # CEO-submit admits while the harness is closed. Later global arming
    # enables capacity, but must not promote this root's admitted profile.
    if (job.constraints.get("operator_harness_armed") is not False
            or type(current.get("operator_harness_armed")) is not bool):
        raise MaintenanceError("preserved root harness admission drifted")
    expected = dict(current, base_sha=descriptor["predecessor_sha"],
                    operator_harness_armed=False)
    if any(job.constraints.get(k) != v for k, v in expected.items()):
        raise MaintenanceError("preserved root non-base binding drifted")
    return expected

def summary_document(sha: str) -> tuple[dict, bytes]:
    # Reuse the current arming owner's exact control-principal file contract.
    import pwd
    import grp
    from ops.executive_os.autonomy_control import (
        _root_json, validate_acceptance_document, CONTROL_USER, CONTROL_GROUP, RUNTIME_ROOT,
        ArmAdmissionError, HostControlError,
    )
    try:
        value, raw = _root_json(
            RUNTIME_ROOT/"control"/"acceptance"/sha/"acceptance-summary.json",
            modes=frozenset({0o400}), uid=pwd.getpwnam(CONTROL_USER).pw_uid,
            gid=grp.getgrnam(CONTROL_GROUP).gr_gid)
        validate_acceptance_document(value, expected_sha=sha)
        return value, raw
    except (ArmAdmissionError, HostControlError, OSError, KeyError, ValueError) as exc:
        raise MaintenanceError("maintenance acceptance summary is invalid") from exc

def validate_carry_receipt(sha: str, summary_sha256: str) -> None:
    descriptor = descriptor_for(sha)
    if descriptor is None:
        return
    receipt = sealed_json(bundle_path(sha)/"carry-forward.json")
    if (set(receipt) != {"schema_version", "passed", "descriptor_sha256",
                         "acceptance_summary_sha256", "baseline_preserved"}
            or receipt["schema_version"] != SCHEMA or receipt["passed"] is not True
            or receipt["baseline_preserved"] is not True
            or receipt["descriptor_sha256"] != digest(descriptor)
            or receipt["acceptance_summary_sha256"] != summary_sha256):
        raise MaintenanceError("preserved root has no matching maintenance PASS receipt")

def recovery_permitted(job: Any, attempt_id: str, sha: str, worker_id: str, quota_class: str) -> bool:
    descriptor = descriptor_for(sha)
    if descriptor is None:
        return False
    active = sealed_json(bundle_path(sha) / "run-started.json")
    return bool(active == {"schema_version": SCHEMA, "descriptor_sha256": digest(descriptor)}
                and not ((bundle_path(sha) / "carry-forward.json").exists()
                         or (bundle_path(sha) / "carry-forward.json").is_symlink())
                and descriptor["recovery_job_id"] == job.job_id
                and descriptor["recovery_attempt_id"] == attempt_id
                and descriptor["worker_id"] == worker_id
                and descriptor["quota_class"] == quota_class
                and digest(job.to_dict()) == descriptor["recovery_job_sha256"]
                and job.constraints.get("base_sha") == descriptor["predecessor_sha"])

def snapshot(database: Path) -> dict:
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN")
        if conn.execute("PRAGMA quick_check").fetchall()[0][0] != "ok" or conn.execute("PRAGMA foreign_key_check").fetchall():
            raise MaintenanceError("runtime integrity check failed")
        schema = [list(row) for row in conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")]
        tables = {}
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            name = row[0]
            if re.fullmatch(r"[a-z_]+", name) is None:
                raise MaintenanceError("unexpected runtime table name")
            # Canonical row sorting also covers optional schema-owned tables.
            tables[name] = sorted(
                (dict(item) for item in conn.execute('SELECT * FROM "' + name + '"')),
                key=lambda item: json.dumps(item, sort_keys=True, allow_nan=False))
        return {"schema": schema, "tables": tables}

def _key(row: dict, table: str) -> Any:
    keys = {"jobs": ("job_id",), "attempts": ("attempt_id",), "events": ("event_id",),
            "workers": ("worker_id",), "worker_quota_classes": ("worker_id", "quota_class"),
            "harness_session_epochs": ("session_epoch_id",),
            "process_generations": ("process_generation_id",)}
    return tuple(row[k] for k in keys[table])

def _validate_recovery_event(event: dict, job_id: str, attempt_id: str, descriptor: dict) -> None:
    from control_plane.executive_runtime import WorkerRegistry, RuntimeProofError
    try:
        WorkerRegistry._validate_proof_recovery_receipt(
            json.loads(event["payload_json"]), job_id=job_id, lost_attempt_id=attempt_id,
            worker_id=descriptor["worker_id"], quota_class=descriptor["quota_class"])
    except (RuntimeProofError, ValueError, KeyError, TypeError) as exc:
        raise MaintenanceError("maintenance recovery receipt is invalid") from exc
    if (event["aggregate_type"] != "quota_class"
            or event["aggregate_id"] != descriptor["worker_id"]+":"+descriptor["quota_class"]
            or event["actor"] != "executive-control-service"
            or event["worker_id"] != descriptor["worker_id"] or event["quota_class"] != descriptor["quota_class"]
            or event["command_id"] != "proof-capacity-recover:"+job_id+":"+attempt_id):
        raise MaintenanceError("maintenance recovery event identity mismatch")

def verify_preserved(before: dict, after: dict, descriptor: dict, proof_ids: list[str]) -> None:
    """All old history stays exact; additions must be the observed proof lineage."""
    if before["schema"] != after["schema"] or set(before["tables"]) != set(after["tables"]):
        raise MaintenanceError("runtime schema changed during acceptance")
    bt, at = before["tables"], after["tables"]
    new = {}
    mutable = {"workers": _HEARTBEAT, "worker_quota_classes": _QUOTA_MUTABLE}
    appendable = {"jobs", "attempts", "events", "harness_session_epochs", "process_generations"}
    for table in bt:
        if table not in appendable | set(mutable):
            if digest(bt[table]) != digest(at[table]):
                raise MaintenanceError("unrelated runtime table changed")
            continue
        old = {_key(row, table): row for row in bt[table]}
        now = {_key(row, table): row for row in at[table]}
        for key, row in old.items():
            if key not in now or {k:v for k,v in row.items() if k not in mutable.get(table,set())} != {
                    k:v for k,v in now.get(key,{}).items() if k not in mutable.get(table,set())}:
                raise MaintenanceError("baseline runtime row changed: " + table)
        new[table] = [row for key,row in now.items() if key not in old]
        if table in mutable and new[table]:
            raise MaintenanceError("maintenance unexpectedly registered capacity")
    if len(proof_ids) != 2 or len(set(proof_ids)) != 2 or {r["job_id"] for r in new["jobs"]} != set(proof_ids):
        raise MaintenanceError("maintenance proof job lineage mismatch")
    if any(r["status"] != "COMPLETED" or r["orchestration_role"] is not None for r in new["jobs"]):
        raise MaintenanceError("maintenance proof did not complete")
    predecessor_proof = next(r for r in bt["jobs"] if r["job_id"] == descriptor["recovery_job_id"])
    proof_fields = ("objective", "department", "priority", "authority_level", "attempt_limit",
                    "requested_authorities_json", "allowed_write_paths_json", "validation_commands_json")
    for job in new["jobs"]:
        constraints = json.loads(predecessor_proof["constraints_json"])
        constraints["base_sha"] = descriptor["successor_sha"]
        if (any(job[field] != predecessor_proof[field] for field in proof_fields)
                or json.loads(job["constraints_json"]) != constraints):
            raise MaintenanceError("maintenance job is not the fixed successor proof")
    attempts = {r["attempt_id"]:r for r in new["attempts"]}
    if len(attempts) != 3 or any(
            r["job_id"] not in proof_ids or r["status"] not in _TERMINAL
            or r["worker_id"] != descriptor["worker_id"] or r["quota_class"] != descriptor["quota_class"]
            for r in attempts.values()):
        raise MaintenanceError("maintenance attempt lineage mismatch")
    for job_id, statuses in zip(proof_ids, [("COMPLETED",), ("LOST", "COMPLETED")]):
        lineage = sorted((r for r in attempts.values() if r["job_id"] == job_id),
                         key=lambda r: r["attempt_number"])
        job = next(r for r in new["jobs"] if r["job_id"] == job_id)
        if (tuple(r["status"] for r in lineage) != statuses
                or [r["attempt_number"] for r in lineage] != list(range(1,len(statuses)+1))
                or job["attempt_count"] != len(statuses)
                or job["current_attempt_id"] != lineage[-1]["attempt_id"]):
            raise MaintenanceError("maintenance proof topology mismatch")
    if new["harness_session_epochs"] or new["process_generations"]:
        raise MaintenanceError("sealed proof unexpectedly created operator harness history")
    recovery = []
    fences = {}
    event_families = {
        "JOB_CREATED", "JOB_CLAIMED", "ATTEMPT_PROCESS_RECORDED", "ATTEMPT_RUNNING",
        "ATTEMPT_HEARTBEAT", "JOB_CHECKPOINTED", "ATTEMPT_PROCESS_EXITED", "JOB_COMPLETED",
        "ATTEMPT_ADOPTED", "ATTEMPT_LOST", "JOB_REQUEUED", "PROOF_WORKSPACE_ROTATED",
        "PROOF_CAPACITY_RECOVERED",
    }
    for event in new["events"]:
        if event["event_type"] not in event_families:
            raise MaintenanceError("event outside acceptance event families")
        if (event["event_type"] == "PROOF_CAPACITY_RECOVERED"
                and event["job_id"] == descriptor["recovery_job_id"]
                and event["attempt_id"] == descriptor["recovery_attempt_id"]
                and event["worker_id"] == descriptor["worker_id"] and event["quota_class"] == descriptor["quota_class"]):
            _validate_recovery_event(event,descriptor["recovery_job_id"],
                                     descriptor["recovery_attempt_id"],descriptor)
            recovery.append(event)
            continue
        if event["job_id"] not in proof_ids or (event["attempt_id"] is not None and event["attempt_id"] not in attempts):
            raise MaintenanceError("event outside maintenance proof lineage")
        if event["event_type"] in {"JOB_CLAIMED", "ATTEMPT_ADOPTED"}:
            if event["worker_id"] != descriptor["worker_id"] or event["quota_class"] != descriptor["quota_class"]:
                raise MaintenanceError("maintenance fence names foreign capacity")
            try:
                fence = json.loads(event["payload_json"])["fence_generation"]
            except (ValueError, KeyError, TypeError) as exc:
                raise MaintenanceError("maintenance fence event is malformed") from exc
            if type(fence) is not int or fence <= 0:
                raise MaintenanceError("maintenance fence event is invalid")
            fences.setdefault((event["worker_id"],event["quota_class"]), []).append(
                (event["event_id"], fence))
    if sum(e["event_type"] == "PROOF_CAPACITY_RECOVERED" for e in new["events"]) != 2:
        raise MaintenanceError("maintenance recovery event count mismatch")
    if len(recovery) != 1:
        raise MaintenanceError("maintenance predecessor recovery is not unique")
    lost = next(r for r in attempts.values() if r["job_id"] == proof_ids[1] and r["status"] == "LOST")
    current_recoveries = [r for r in new["events"] if r["event_type"] == "PROOF_CAPACITY_RECOVERED"
                          and r["job_id"] == proof_ids[1] and r["attempt_id"] == lost["attempt_id"]]
    if len(current_recoveries) != 1:
        raise MaintenanceError("maintenance current proof recovery is not unique")
    _validate_recovery_event(current_recoveries[0],proof_ids[1],lost["attempt_id"],descriptor)
    for attempt in attempts.values():
        owned = [e for e in new["events"] if e["attempt_id"] == attempt["attempt_id"]]
        claims = [e for e in owned if e["event_type"] == "JOB_CLAIMED"]
        adoptions = [e for e in owned if e["event_type"] == "ATTEMPT_ADOPTED"]
        if (len(claims) != 1 or len(adoptions) > 1
                or (adoptions and attempt["attempt_id"] != lost["attempt_id"])):
            raise MaintenanceError("maintenance attempt fence lineage mismatch")
        last = max(claims+adoptions,key=lambda e:e["event_id"])
        if attempt["fence_generation"] != json.loads(last["payload_json"])["fence_generation"]:
            raise MaintenanceError("maintenance final attempt fence mismatch")
    old_quotas = {_key(r,"worker_quota_classes"): r for r in bt["worker_quota_classes"]}
    for row in at["worker_quota_classes"]:
        key = _key(row,"worker_quota_classes")
        old = old_quotas[key]
        sequence = [f for _,f in sorted(fences.get(key, []))]
        if sequence != list(range(old["fence_counter"]+1, old["fence_counter"]+len(sequence)+1)):
            raise MaintenanceError("maintenance quota fence chain has a gap")
        target = key == (descriptor["worker_id"],descriptor["quota_class"])
        expected_status = "AVAILABLE" if sequence or target else old["status"]
        if (row["fence_counter"] != old["fence_counter"]+len(sequence)
                or row["held_attempt_id"] is not None or row["status"] != expected_status):
            raise MaintenanceError("maintenance final quota state mismatch")

def inventory(roots: list[Path]) -> dict:
    """Preserve existing artifacts, including link text without following links."""
    result = {}
    for root in roots:
        root = root.resolve(strict=True)
        if not root.exists():
            raise MaintenanceError("maintenance artifact root is absent")
        for path in [root, *sorted(root.rglob("*"))]:
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                content = {"directory": True, "device":info.st_dev, "inode":info.st_ino}
            elif stat.S_ISLNK(info.st_mode):
                content = {"link": os.readlink(path)}
            elif stat.S_ISREG(info.st_mode):
                content = {"sha256": _file_digest(path)}
            else:
                raise MaintenanceError("special file in preserved artifact tree")
            if has_macos_acl(path, expected_identity=info, allow_symlink=stat.S_ISLNK(info.st_mode)):
                raise MaintenanceError("preserved artifact has an ACL")
            if not stat.S_ISDIR(info.st_mode):
                content["nlink"] = info.st_nlink
            result[str(path)] = {"uid":info.st_uid, "gid":info.st_gid,
                                 "mode":stat.S_IMODE(info.st_mode), **content}
    return result

def verify_inventory(baseline: dict) -> None:
    for name, expected in baseline.items():
        path = Path(name)
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            content = {"directory":True,"device":info.st_dev,"inode":info.st_ino}
        elif stat.S_ISLNK(info.st_mode):
            content = {"link":os.readlink(path)}
        elif stat.S_ISREG(info.st_mode):
            content = {"sha256":_file_digest(path)}
        else:
            raise MaintenanceError("preserved artifact became a special file")
        if has_macos_acl(path, expected_identity=info, allow_symlink=stat.S_ISLNK(info.st_mode)):
            raise MaintenanceError("preserved artifact gained an ACL")
        if not stat.S_ISDIR(info.st_mode):
            content["nlink"] = info.st_nlink
        if {"uid":info.st_uid,"gid":info.st_gid,"mode":stat.S_IMODE(info.st_mode),**content} != expected:
            raise MaintenanceError("preserved artifact changed")

def write_sealed(path: Path, value: dict, *, public: bool = False) -> None:
    data = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+"\n").encode()
    fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(os.dup(fd),"wb") as stream:
            stream.write(data)
            stream.flush()
        os.fchmod(fd, 0o444 if public else 0o400)
        os.fsync(fd)
    finally:
        os.close(fd)
    parent = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)

def require_disarmed(config: dict) -> None:
    if any(config.get(k) is not False for k in
           ("ceo_submit_armed", "coo_autonomy_armed", "coo_operator_harness_armed")):
        raise MaintenanceError("maintenance requires all control intake arms closed")

def require_stopped() -> None:
    for label in ("com.mastermind.executive.control", "com.mastermind.executive.worker.codex"):
        probe = subprocess.run(["/bin/launchctl","print","system/"+label], capture_output=True)
        if probe.returncode == 0:
            raise MaintenanceError("maintenance preparation requires stopped Executive services")

def prepare(args: argparse.Namespace) -> Path:
    if os.geteuid() != 0 or sys.platform != "darwin":
        raise MaintenanceError("maintenance preparation requires root on macOS")
    require_stopped()
    config = json.loads((SYSTEM_ROOT/"config/control.json").read_text())
    require_disarmed(config)
    worker_config = json.loads((SYSTEM_ROOT/"config/worker-codex.json").read_text())
    if worker_config.get("operator_harness_armed") is not False:
        raise MaintenanceError("maintenance requires closed worker harness")
    if config["proof_base_sha"] != args.predecessor_sha:
        raise MaintenanceError("predecessor differs from installed release")
    database = Path(config["runtime_root"])/"data/control_plane/executive.sqlite3"
    before = snapshot(database)
    from control_plane.executive_runtime import Runtime
    runtime = Runtime.at(config["runtime_root"], create=False)
    root = runtime.jobs.get_job(args.root_job_id)
    proof = runtime.jobs.get_job(args.recovery_job_id)
    if (root is None or proof is None or root.status.value != "QUEUED"
            or root.orchestration_role != "aggregation" or root.attempt_count != 0
            or root.current_attempt_id is not None or root.parent_job_id is not None
            or root.root_job_id != root.job_id or root.depth != 0
            or root.constraints.get("base_sha") != args.predecessor_sha
            or root.constraints.get("operator_harness_armed") is not False
            or not root.orchestration_provenance_digest):
        raise MaintenanceError("preserved root is not an untouched strict-v2 queued root")
    tables = before["tables"]
    if (any(r["status"] not in _TERMINAL for r in tables["attempts"])
            or any(r["held_attempt_id"] is not None for r in tables["worker_quota_classes"])
            or any(r["parent_job_id"] == root.job_id for r in tables["jobs"])):
        raise MaintenanceError("maintenance runtime is not quiescent")
    runtime.workers.proof_capacity_recovery_snapshot(
        proof.job_id,args.recovery_attempt_id,worker_id=config["worker_id"],quota_class=config["quota_class"])
    events = [r for r in tables["events"] if r["job_id"]==root.job_id and r["event_type"]=="JOB_CREATED"]
    if len(events) != 1:
        raise MaintenanceError("preserved root admission is not unique")
    artifact_roots = [Path(config[k]) for k in ("proof_workspace_root","worker_runs_root","receipts_root","backup_root")]
    artifact_roots.append(Path(config["runtime_root"]).parent.parent/"canary-fixtures")
    artifacts = inventory(artifact_roots)
    parent = bundle_path(args.successor_sha).parent
    parent.mkdir(mode=0o755, exist_ok=True)
    parent_info = parent.lstat()
    if parent_info.st_uid != _TRUSTED_UID or not stat.S_ISDIR(parent_info.st_mode) or parent.is_symlink():
        raise MaintenanceError("maintenance bundle parent is not root-owned")
    os.chmod(parent, 0o755)
    _sealed_ancestors(parent/"unused")
    final_bundle = bundle_path(args.successor_sha)
    if final_bundle.exists() or final_bundle.is_symlink():
        raise MaintenanceError("maintenance descriptor already exists; reconcile the existing operation")
    bundle = Path(tempfile.mkdtemp(prefix=".preparing-"+args.successor_sha+"-",dir=parent))
    write_sealed(bundle/"preparing.json",{"schema_version":SCHEMA})
    backup = bundle/"prestate.sqlite3"
    fd = os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    os.close(fd)
    with sqlite3.connect(database.as_uri()+"?mode=ro",uri=True) as source, sqlite3.connect(backup) as destination:
        source.backup(destination)
    os.chmod(backup,0o400)
    with backup.open("rb") as stream:
        os.fsync(stream.fileno())
    if snapshot(backup) != before or snapshot(database) != before:
        raise MaintenanceError("runtime changed during maintenance preparation")
    prior_canary = Path(config["secret_canary_receipt_path"])
    prior_canary_value = json.loads(prior_canary.read_text())
    write_sealed(bundle/"prior-secret-canary.json",prior_canary_value)
    write_sealed(bundle/"baseline.json",before)
    write_sealed(bundle/"inventory.json",artifacts)
    descriptor = dict(schema_version=SCHEMA,predecessor_sha=args.predecessor_sha,
        successor_sha=args.successor_sha,root_job_id=root.job_id,root_identity_sha256=root_identity(root),
        root_event_id=events[0]["event_id"],root_event_sha256=digest(events[0]),
        recovery_job_id=proof.job_id,recovery_attempt_id=args.recovery_attempt_id,
        recovery_job_sha256=digest(proof.to_dict()),worker_id=config["worker_id"],quota_class=config["quota_class"],
        baseline_sha256=digest(before),backup_sha256=_file_digest(backup),inventory_sha256=digest(artifacts),
        prior_canary_sha256=digest(prior_canary_value))
    write_sealed(bundle/"descriptor.json",descriptor,public=True)
    os.chmod(bundle,0o755)
    directory_fd = os.open(bundle,os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    # A final namespace is published only when every baseline file is durable.
    # Failed preparation directories remain private evidence and are never read
    # by the service, nor deleted by an automatic retry.
    os.rename(bundle,final_bundle)
    directory_fd = os.open(parent,os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    descriptor_for(args.successor_sha)
    return final_bundle

class Maintenance:
    def __init__(self, sha: str, expected_digest: str, config: dict):
        self.bundle = bundle_path(sha)
        self.descriptor = descriptor_for(sha)
        if self.descriptor is None or digest(self.descriptor) != expected_digest:
            raise MaintenanceError("maintenance descriptor digest mismatch")
        require_disarmed(config)
        require_stopped()
        self.database = Path(config["runtime_root"])/"data/control_plane/executive.sqlite3"
        self.before = sealed_json(self.bundle/"baseline.json")
        self.inventory = sealed_json(self.bundle/"inventory.json")
        prior_canary = sealed_json(self.bundle/"prior-secret-canary.json")
        if (digest(prior_canary) != self.descriptor["prior_canary_sha256"]
                or digest(json.loads(Path(config["secret_canary_receipt_path"]).read_text())) != self.descriptor["prior_canary_sha256"]
                or digest(self.before) != self.descriptor["baseline_sha256"]
                or digest(self.inventory) != self.descriptor["inventory_sha256"]
                or _file_digest(self.bundle/"prestate.sqlite3") != self.descriptor["backup_sha256"]
                or snapshot(self.database) != self.before):
            raise MaintenanceError("maintenance prestate drifted")
        verify_inventory(self.inventory)
        write_sealed(self.bundle/"run-started.json",
                     {"schema_version":SCHEMA,"descriptor_sha256":digest(self.descriptor)},public=True)

    def verify(self, proof_ids: list[str]) -> None:
        verify_preserved(self.before,snapshot(self.database),self.descriptor,proof_ids)
        verify_inventory(self.inventory)

    def finish(self, proof_ids: list[str], summary: Path) -> None:
        self.verify(proof_ids)
        _value, raw = summary_document(self.descriptor["successor_sha"])
        write_sealed(self.bundle/"carry-forward.json",dict(
            schema_version=SCHEMA,passed=True,baseline_preserved=True,
            descriptor_sha256=digest(self.descriptor),acceptance_summary_sha256=hashlib.sha256(raw).hexdigest()),public=True)

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predecessor-sha",required=True)
    parser.add_argument("--successor-sha",required=True)
    parser.add_argument("--root-job-id",required=True)
    parser.add_argument("--recovery-job-id",required=True)
    parser.add_argument("--recovery-attempt-id",required=True)
    args = parser.parse_args()
    try:
        bundle = prepare(args)
        descriptor = descriptor_for(args.successor_sha)
        print(json.dumps({"bundle":str(bundle),"descriptor_sha256":digest(descriptor)}))
        return 0
    except (MaintenanceError,OSError,ValueError) as exc:
        print("maintenance error: "+str(exc),file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
